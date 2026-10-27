// The result narrative (llm.service.js). Both provider SDKs are mocked, as in
// osintJudge.test.js; the provider-specific tests run once through each.
import { describe, it, expect, vi, beforeEach } from "vitest";

const h = vi.hoisted(() => ({
  gemini: vi.fn(),
  anthropic: vi.fn(),
  cache: { get: vi.fn(), set: vi.fn() },
  classifyText: vi.fn(),
}));

vi.mock("../src/services/cache.service.js", () => ({
  cacheGet: h.cache.get,
  cacheSet: h.cache.set,
  counterIncrBy: vi.fn(),
}));
vi.mock("../src/services/nlp.service.js", () => ({ classifyText: h.classifyText, ocrScreenshots: vi.fn() }));
vi.mock("../src/services/osint.service.js", () => ({ searchAgentReputation: async () => null }));
vi.mock("@google/genai", async (importOriginal) => ({
  ...(await importOriginal()),
  GoogleGenAI: class {
    constructor() {
      this.models = { generateContent: h.gemini };
    }
  },
}));
vi.mock("@anthropic-ai/sdk", () => ({
  default: class {
    constructor() {
      this.messages = { create: h.anthropic };
    }
  },
}));

import { config } from "../src/config/index.js";
import { logger } from "../src/utils/logger.js";
import {
  checkNarrative,
  generateNarrative,
  narrativeFacts,
  narrativeSettings,
} from "../src/services/llm.service.js";
import { runAnalysisPipeline } from "../src/services/pipeline.service.js";
import { NARRATIVE_PROMPT_VERSION } from "../src/prompts/narrative.prompt.js";

const KEYS = {
  gemini: `AIza${"3".repeat(35)}`,
  anthropic: `sk-ant-${"4".repeat(40)}`,
};

// Shaped like a real saved result (blind-test case03), with markers wherever
// chat text, search text or an identifier sits.
const RESULT = {
  listingId: "test-listing",
  sourceType: "screenshot",
  language: "auto",
  riskScore: 11,
  maxPossibleScore: 100,
  riskBand: "LOW",
  riskColour: "green",
  bandCap: null,
  modelProbability: 0.0186,
  components: {
    nlp: { points: 1, max: 60, included: true },
    osint: { points: 0, max: 25, included: true },
    price: { points: 10, max: 15, included: true },
  },
  excludedSignals: [],
  nlpStatus: "ok",
  nlpConfidence: "high",
  message: null,
  evidenceSupport: "partial",
  narrative: null,
  metadata: { phone: "0198765432", agentName: "Puan Marker", identitySource: "form" },
  evidence: {
    redFlags: ["agreement_irregularity"],
    details: [{
      id: "agreement_irregularity",
      category: "tenancy",
      severity: "medium",
      label_en: "The tenancy terms are irregular",
      label_ms: "Terma perjanjian sewa tidak teratur",
      advice_en: "Insist on a stamped written tenancy.",
      advice_ms: "Tegaskan perjanjian bertulis bersetem.",
      snippet: "...pemilik: CHAT-MARKER-7f3a agreement nanti...",
      speaker: "owner",
      sources: ["regex"],
    }],
    patterns: [],
    legitSignals: [],
    osint: {
      status: "ok",
      points: 0,
      max: 25,
      strongHit: false,
      identity: { phone: "0198765432", name: "Puan Marker" },
      queries: [{ type: "phone", q: "0198765432 scam" }],
      evidence: [],
      context: [{
        title: "SEARCH-TITLE-MARKER",
        link: "https://www.facebook.com/groups/marker/posts/1",
        snippet: "SEARCH-SNIPPET-MARKER Puan Marker tipu",
        domain: "facebook.com",
        tier: "social",
        query: "name",
        foundBy: "name",
        label: "complaint",
        confidence: 0.95,
        reason: "JUDGE-REASON-MARKER",
        type: "name_only_match",
      }],
    },
    price: {
      status: "ok",
      points: 10,
      max: 15,
      tier: "suspicious",
      deviation: 0.4406,
      listedPrice: 400,
      stratum: { area: "Shah Alam", propertyType: "room", roomType: "common" },
      baseline: { median: 715, p25: 662.5, sampleSize: 6 },
      missing: [],
      message: {
        en: "RM400 is 44% below the median of 6 comparable listings (RM715).",
        ms: "RM400 ialah 44% di bawah median 6 iklan setanding (RM715).",
      },
    },
  },
  ocrText: "Renter: CHAT-MARKER-7f3a boleh tengok bilik?",
};

const GOOD = {
  en: "This listing is low risk. One warning sign was found: the tenancy terms are irregular. "
    + "The rent of RM400 is 44% below the median of RM715 for 6 similar rooms. Insist on a stamped written tenancy.",
  ms: "Iklan ini berisiko rendah. Satu tanda amaran ditemui: terma perjanjian sewa tidak teratur. "
    + "Sewa RM400 ialah 44% di bawah median RM715 bagi 6 bilik setanding. Tegaskan perjanjian bertulis bersetem.",
};

const settingsFor = (provider) => ({
  enabled: true,
  provider,
  model: provider === "gemini" ? "gemini-model-from-ai-studio" : "claude-haiku-4-5-20251001",
});

/** answer(narrative) in each provider's own format; a function is called per request. */
function answer(narrative) {
  h.gemini.mockImplementation(async () => ({ text: JSON.stringify(narrative) }));
  h.anthropic.mockImplementation(async () => ({
    content: [{ type: "tool_use", name: "record_narrative", input: narrative }],
  }));
}

function lastRequest(provider) {
  if (provider === "gemini") {
    const [request] = h.gemini.mock.calls.at(-1);
    return { user: request.contents[0].parts[0].text, raw: request };
  }
  const [body] = h.anthropic.mock.calls.at(-1);
  return { user: body.messages[0].content, raw: body };
}

const calls = () => h.gemini.mock.calls.length + h.anthropic.mock.calls.length;

beforeEach(() => {
  h.gemini.mockReset();
  h.anthropic.mockReset();
  h.classifyText.mockReset();
  h.cache.get.mockReset().mockResolvedValue(null);
  h.cache.set.mockReset().mockResolvedValue(undefined);
  Object.assign(config, {
    llmNarrative: null,
    narrativeProvider: null,
    llmVerifierProvider: "gemini",
    geminiApiKey: KEYS.gemini,
    geminiModel: "gemini-model-from-ai-studio",
    anthropicApiKey: KEYS.anthropic,
    anthropicModel: "claude-haiku-4-5-20251001",
  });
  vi.spyOn(logger, "warn").mockImplementation(() => {});
});

describe.each(["gemini", "anthropic"])("narrative via %s", (provider) => {
  it("sends only system facts: never the chat, search text, names or phone numbers", async () => {
    answer(GOOD);
    await generateNarrative(RESULT, settingsFor(provider));

    const { user } = lastRequest(provider);
    for (const secret of [
      "CHAT-MARKER-7f3a", "0198765432", "Puan Marker", "SEARCH-TITLE-MARKER",
      "SEARCH-SNIPPET-MARKER", "JUDGE-REASON-MARKER", "facebook.com/groups",
    ]) {
      expect(user).not.toContain(secret);
    }
    expect(user).toContain("agreement_irregularity");
    expect(user).toContain("Shah Alam");
  });

  it("returns both languages, with the provider, model and prompt version", async () => {
    answer(GOOD);
    const narrative = await generateNarrative(RESULT, settingsFor(provider));

    expect(narrative).toEqual({
      en: GOOD.en,
      ms: GOOD.ms,
      provider,
      model: settingsFor(provider).model,
      promptVersion: NARRATIVE_PROMPT_VERSION,
    });
    expect(h.cache.set).toHaveBeenCalledWith(expect.stringMatching(/^narrative:/), narrative, expect.any(Number));
  });

  it("asks for deterministic, structured output", async () => {
    answer(GOOD);
    await generateNarrative(RESULT, settingsFor(provider));
    const { raw } = lastRequest(provider);
    if (provider === "gemini") {
      expect(raw.config).toMatchObject({ temperature: 0, responseMimeType: "application/json" });
      expect(raw.config.responseSchema.required).toEqual(["en", "ms"]);
    } else {
      expect(raw).toMatchObject({ temperature: 0, tool_choice: { type: "tool", name: "record_narrative" } });
    }
  });

  it("drops a narrative that names another band", async () => {
    answer({ ...GOOD, en: "This listing is high risk. Do not pay before viewing." });
    expect(await generateNarrative(RESULT, settingsFor(provider))).toBeNull();
    expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining("names band HIGH"));
    expect(h.cache.set).not.toHaveBeenCalled();
  });

  it("drops a narrative that invents a number", async () => {
    answer({ ...GOOD, ms: "Iklan ini berisiko rendah. Sewa RM350 adalah murah." });
    expect(await generateNarrative(RESULT, settingsFor(provider))).toBeNull();
    expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining("writes 350"));
  });

  it("never throws: a provider error leaves the narrative null", async () => {
    const error = Object.assign(new Error("API key not valid"), { status: 400 });
    h.gemini.mockRejectedValue(error);
    h.anthropic.mockRejectedValue(error);
    expect(await generateNarrative(RESULT, settingsFor(provider))).toBeNull();
    expect(calls()).toBe(1);
  });

  it("retries once after a 5xx", async () => {
    answer(GOOD);
    const busy = Object.assign(new Error("high demand"), { status: 503 });
    h.gemini.mockRejectedValueOnce(busy);
    h.anthropic.mockRejectedValueOnce(busy);
    const narrative = await generateNarrative(RESULT, settingsFor(provider));
    expect(narrative?.en).toBe(GOOD.en);
    expect(calls()).toBe(2);
  });
});

describe("narrative cache and settings", () => {
  it("serves a cached narrative without calling the provider", async () => {
    const cached = { en: "cached en", ms: "cached ms", provider: "gemini", model: "m", promptVersion: "v1" };
    h.cache.get.mockResolvedValue(cached);
    expect(await generateNarrative(RESULT, settingsFor("gemini"))).toEqual(cached);
    expect(calls()).toBe(0);
  });

  it("follows the judge's provider and model unless NARRATIVE_PROVIDER overrides it", () => {
    expect(narrativeSettings()).toEqual({ enabled: true, provider: "gemini", model: "gemini-model-from-ai-studio" });
    config.narrativeProvider = "anthropic";
    expect(narrativeSettings()).toEqual({ enabled: true, provider: "anthropic", model: "claude-haiku-4-5-20251001" });
  });

  it("is off with LLM_NARRATIVE=false, without a real key, or without a Gemini model", async () => {
    config.llmNarrative = false;
    expect(narrativeSettings().enabled).toBe(false);
    config.llmNarrative = null;
    config.geminiApiKey = "your_gemini_key";
    expect(narrativeSettings().enabled).toBe(false);
    config.geminiApiKey = KEYS.gemini;
    config.geminiModel = undefined;
    expect(narrativeSettings().enabled).toBe(false);

    expect(await generateNarrative(RESULT)).toBeNull();
    expect(calls()).toBe(0);
  });
});

describe("checkNarrative", () => {
  const facts = narrativeFacts(RESULT);

  it("accepts numbers from the facts, written with thousands separators", () => {
    const big = narrativeFacts({ ...RESULT, evidence: { ...RESULT.evidence, price: { ...RESULT.evidence.price, listedPrice: 1100 } } });
    const text = { en: "The rent is RM1,100, out of 100 points this is low risk.", ms: "Sewa RM1,100." };
    expect(checkNarrative(text, big).ok).toBe(true);
  });

  it("catches a band named in Malay", () => {
    const result = checkNarrative({ en: GOOD.en, ms: "Iklan ini berisiko tinggi." }, facts);
    expect(result).toEqual({ ok: false, reason: "ms names band HIGH, result is LOW" });
  });

  it("catches a band code and the guide's wording", () => {
    expect(checkNarrative({ ...GOOD, en: "Rated CRITICAL." }, facts).ok).toBe(false);
    expect(checkNarrative({ ...GOOD, en: "This is a medium-risk listing." }, facts).ok).toBe(false);
    expect(checkNarrative({ ...GOOD, en: "A very high scam risk." }, facts).reason).toContain("CRITICAL");
  });

  it("lets a capped result name the band it was held from, and no other", () => {
    const capped = narrativeFacts({
      ...RESULT,
      riskBand: "MODERATE",
      riskScore: 49,
      bandCap: { applied: true, reason: "no_red_flags", uncappedScore: 55, uncappedBand: "HIGH" },
    });
    const held = {
      en: "The model rated this high risk, but with no specific tactic found it is held at moderate risk.",
      ms: "Model menilai ini berisiko tinggi, tetapi ia kekal pada risiko sederhana.",
    };
    expect(checkNarrative(held, capped).ok).toBe(true);
    expect(checkNarrative({ ...held, en: "This is critical risk." }, capped).ok).toBe(false);
  });

  it("rejects an empty or missing language and an overlong text", () => {
    expect(checkNarrative({ en: GOOD.en }, facts)).toEqual({ ok: false, reason: "ms is empty" });
    expect(checkNarrative({ ...GOOD, en: "a".repeat(1201) }, facts).ok).toBe(false);
    expect(checkNarrative(null, facts).ok).toBe(false);
  });
});

describe("pipeline", () => {
  it("writes the narrative from the finished result, never from the raw chat", async () => {
    h.classifyText.mockResolvedValue({
      scam_probability: 0.98,
      normalised_text: "CHAT-MARKER-7f3a",
      red_flags: ["upfront_payment"],
      layer1: {
        evidence: [{
          id: "upfront_payment",
          severity: "medium",
          label_en: "Money asked for up front",
          label_ms: "Wang diminta terlebih dahulu",
          snippet: "CHAT-MARKER-7f3a bayar dulu",
        }],
        patterns: [],
        legit_signals: [],
      },
      layer2: { status: "ok", confidence: "high", model_probability: 0.98 },
    });
    const narrative = {
      en: "This listing is high risk: money was asked for up front. Do not pay before viewing.",
      ms: "Iklan ini berisiko tinggi: wang diminta terlebih dahulu. Jangan bayar sebelum melihat unit.",
    };
    answer(narrative);

    const result = await runAnalysisPipeline({
      rawText: "Owner: CHAT-MARKER-7f3a bayar dulu, call 019-876 5432",
      sourceType: "text",
      agent: { name: "Puan Marker", phone: "012-345 6789" },
    });

    expect(result.riskBand).toBe("HIGH");
    expect(result.riskScore).toBe(59);
    expect(result.narrative).toMatchObject(narrative);
    const { user } = lastRequest("gemini");
    expect(user).not.toContain("CHAT-MARKER-7f3a");
    expect(user).not.toContain("5432");
    expect(user).not.toContain("6789");
    expect(user).not.toContain("Puan Marker");
    expect(user).toContain('"score": 59');
  });
});
