// LLM narrative module (FYP2 — P9).
// Writes a plain-language explanation, in English and Malay, of the
// ALREADY-COMPUTED result. The score is fixed before this runs, and nothing
// here can change it (verifiability):
//   - the model sees only narrativeFacts(result): band, score, red-flag labels
//     and advice from the lexicon, price figures and OSINT counts. Never the
//     renter's chat, snippets, names or phone numbers — the OSINT judge's rule,
//     since the Gemini free tier may use inputs for product improvement
//   - checkNarrative() rejects a text that names another band or writes a
//     number that is not in the facts
//   - evidence.legitSignals go in as context only, never as a reason the
//     listing is safe: measured on the corpus, every legitimacy signal fires
//     more often on scams than on honest chats (scammers imitate proper
//     lettings), and even after withholding they appear on 5.4% of scams vs
//     5.7% of legitimate ones (nlp-service/eval/results/legit_signal_rates.json)
//
// DECISION (2026-10-25) — on any failure the narrative is null, not a generic
// template. NarrativeCard.jsx already assembles an explanation from the
// result's own fields when there is none, which says more than a template
// written here could.
//
// Provider and model are the OSINT judge's (LLM_VERIFIER_PROVIDER,
// GEMINI_MODEL / ANTHROPIC_MODEL) unless NARRATIVE_PROVIDER names another.
// One call per new result within a 15 s budget, retried once after a 5xx,
// and cached by the facts so an identical result is not paid for twice.
import { createHash } from "node:crypto";
import Anthropic from "@anthropic-ai/sdk";
import { GoogleGenAI, Type } from "@google/genai";
import { config } from "../config/index.js";
import { cacheGet, cacheSet } from "./cache.service.js";
import { classifyJudgeError } from "./llmVerifier.js";
import { isRealKey, redactSecrets } from "../utils/keys.js";
import { NARRATIVE_PROMPT_VERSION, NARRATIVE_SYSTEM_PROMPT } from "../prompts/narrative.prompt.js";
import { logger } from "../utils/logger.js";

const TIMEOUT_MS = 15_000;
const RETRY_DELAY_MS = 1000;
const CACHE_TTL_SECONDS = 7 * 24 * 3600;
const MAX_CHARS = 1200;
const MAX_ERROR_CHARS = 300;
const DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001";

const GEMINI_SCHEMA = {
  type: Type.OBJECT,
  properties: {
    en: { type: Type.STRING },
    ms: { type: Type.STRING },
  },
  required: ["en", "ms"],
};

// Same contract for Claude, enforced by forcing a tool call (this SDK version
// has no response-schema option).
const ANTHROPIC_TOOL = {
  name: "record_narrative",
  description: "Record the explanation in English and in Malay.",
  input_schema: {
    type: "object",
    properties: {
      en: { type: "string" },
      ms: { type: "string" },
    },
    required: ["en", "ms"],
  },
};

const warned = new Set();
function warnOnce(key, message) {
  if (warned.has(key)) return;
  warned.add(key);
  logger.warn(message);
}

/**
 * narrativeSettings() -> { enabled, provider, model }
 * provider and model are null when the narrative is off.
 */
export function narrativeSettings() {
  const off = { enabled: false, provider: null, model: null };
  if (config.llmNarrative === false) return off;

  const provider = config.narrativeProvider ?? config.llmVerifierProvider;
  if (provider !== "gemini" && provider !== "anthropic") {
    warnOnce(`provider:${provider}`, `narrative provider "${provider}" is not gemini or anthropic; narrative off`);
    return off;
  }

  const key = provider === "gemini" ? config.geminiApiKey : config.anthropicApiKey;
  if (!isRealKey(key)) {
    if (config.llmNarrative === true) {
      warnOnce(`key:${provider}`, `LLM_NARRATIVE is on but no ${provider} API key is set; narrative off`);
    }
    return off;
  }

  const model = provider === "gemini"
    ? config.geminiModel
    : config.anthropicModel || DEFAULT_ANTHROPIC_MODEL;
  if (!model) {
    warnOnce("model:gemini", "GEMINI_MODEL is empty; narrative off (copy the model ID from Google AI Studio)");
    return off;
  }
  return { enabled: true, provider, model };
}

// OSINT context the renter may be told about: a report naming someone with
// the same name, which did not score because a name can be someone else's.
const UNSCORED_MENTIONS = new Set(["name_only_match", "unverified_mention"]);

function pickFields(item, fields) {
  return Object.fromEntries(fields.filter((field) => item?.[field] != null).map((field) => [field, item[field]]));
}

/**
 * narrativeFacts(result) -> the only data the model is shown.
 * result is the finished analysis (pipeline.service.js), narrative aside.
 * Everything here is produced by the system itself; nothing is copied from
 * the chat or from a search result except the source's domain.
 */
export function narrativeFacts(result) {
  const evidence = result.evidence ?? {};
  const { osint, price } = evidence;
  const component = (name) => pickFields(result.components?.[name], ["points", "max", "included"]);

  return {
    band: result.riskBand,
    score: result.riskScore,
    maxPossibleScore: result.maxPossibleScore,
    bandCap: result.bandCap?.applied ? pickFields(result.bandCap, ["uncappedScore", "uncappedBand"]) : null,
    evidenceSupport: result.evidenceSupport ?? null,
    nlp: { status: result.nlpStatus ?? null, confidence: result.nlpConfidence ?? null, ...component("nlp") },
    excludedSignals: result.excludedSignals ?? [],
    notice: result.message ?? null,
    redFlags: (evidence.details ?? []).map((flag) =>
      pickFields(flag, ["id", "severity", "label_en", "label_ms", "advice_en", "advice_ms"]),
    ),
    patterns: (evidence.patterns ?? []).map((pattern) =>
      pickFields(pattern, ["id", "label_en", "label_ms", "description_en"]),
    ),
    legitSignals: (evidence.legitSignals ?? []).map((signal) => pickFields(signal, ["id", "label_en", "note_en"])),
    osint: osint
      ? {
          status: osint.status ?? null,
          ...component("osint"),
          strongHit: Boolean(osint.strongHit),
          reports: (osint.evidence ?? []).map((item) => pickFields(item, ["domain", "tier", "foundBy", "label"])),
          unscoredMentions: (osint.context ?? [])
            .filter((item) => UNSCORED_MENTIONS.has(item.type))
            .map((item) => pickFields(item, ["domain", "tier", "foundBy", "type"])),
        }
      : null,
    price: price
      ? {
          status: price.status ?? null,
          ...component("price"),
          tier: price.tier ?? null,
          listedPrice: price.listedPrice ?? null,
          deviationPct: typeof price.deviation === "number" ? Math.round(price.deviation * 100) : null,
          median: price.baseline?.median ?? null,
          sampleSize: price.baseline?.sampleSize ?? null,
          ...pickFields(price.stratum, ["area", "propertyType", "roomType"]),
          missing: price.missing ?? [],
          message: price.message ?? null,
        }
      : null,
  };
}

// --- the check ---------------------------------------------------------------

// Band names as a renter would read them. The guide calls MODERATE "Medium"
// and CRITICAL "Very High"; Malay follows ms.json result.bandWord.
const BAND_WORDS = {
  en: { "very high": "CRITICAL", critical: "CRITICAL", high: "HIGH", moderate: "MODERATE", medium: "MODERATE", low: "LOW" },
  ms: { "sangat tinggi": "CRITICAL", kritikal: "CRITICAL", tinggi: "HIGH", sederhana: "MODERATE", rendah: "LOW" },
};
const BAND_PHRASES = {
  en: /\b(very high|critical|high|moderate|medium|low)(?:[ -]scam)?[ -]risk\b/gi,
  ms: /\b(?:risiko|berisiko)(?:\s+penipuan)?(?:\s+yang)?\s+(sangat tinggi|kritikal|tinggi|sederhana|rendah)\b/gi,
};
const BAND_CODES = /\b(LOW|MODERATE|HIGH|CRITICAL|UNKNOWN)\b/g;

function numbersIn(text) {
  return (String(text).match(/\d[\d,]*(?:\.\d+)?/g) ?? []).map((token) => Number(token.replace(/,/g, "")));
}

function bandsNamed(text, language) {
  const phrases = [...text.matchAll(BAND_PHRASES[language])].map((match) => BAND_WORDS[language][match[1].toLowerCase()]);
  const codes = [...text.matchAll(BAND_CODES)].map((match) => match[1]);
  return [...phrases, ...codes];
}

/**
 * checkNarrative(raw, facts) -> { ok: true, narrative: { en, ms } } | { ok: false, reason }
 *
 * The prompt says the score is final; this makes it so. A text is rejected
 * when either language is empty or over MAX_CHARS, writes a number that
 * appears nowhere in the facts (100, the scale, aside), or names a band other
 * than the result's — or, when the band was capped, the band before the cap,
 * which the narrative is asked to explain.
 */
export function checkNarrative(raw, facts) {
  const allowedNumbers = new Set([100, ...numbersIn(JSON.stringify(facts))]);
  const allowedBands = new Set([facts.band, facts.bandCap?.uncappedBand].filter(Boolean));
  const narrative = {};

  for (const language of ["en", "ms"]) {
    const text = typeof raw?.[language] === "string" ? raw[language].trim() : "";
    if (!text) return { ok: false, reason: `${language} is empty` };
    if (text.length > MAX_CHARS) return { ok: false, reason: `${language} is over ${MAX_CHARS} characters` };

    const number = numbersIn(text).find((value) => !allowedNumbers.has(value));
    if (number !== undefined) return { ok: false, reason: `${language} writes ${number}, which is not in the facts` };

    const band = bandsNamed(text, language).find((name) => !allowedBands.has(name));
    if (band) return { ok: false, reason: `${language} names band ${band}, result is ${facts.band}` };

    narrative[language] = text;
  }
  return { ok: true, narrative };
}

// --- the call ----------------------------------------------------------------

function userMessage(facts) {
  return "Result to explain (data, JSON):\n" + JSON.stringify(facts, null, 2);
}

async function callGemini(model, facts, signal) {
  const ai = new GoogleGenAI({ apiKey: config.geminiApiKey });
  const response = await ai.models.generateContent({
    model,
    contents: [{ role: "user", parts: [{ text: userMessage(facts) }] }],
    config: {
      systemInstruction: NARRATIVE_SYSTEM_PROMPT,
      temperature: 0,
      responseMimeType: "application/json",
      responseSchema: GEMINI_SCHEMA,
      abortSignal: signal,
      httpOptions: { timeout: TIMEOUT_MS, retryOptions: { attempts: 1 } },
    },
  });
  return JSON.parse(response.text ?? "");
}

async function callAnthropic(model, facts, signal) {
  const client = new Anthropic({ apiKey: config.anthropicApiKey, maxRetries: 0, timeout: TIMEOUT_MS });
  const message = await client.messages.create(
    {
      model,
      max_tokens: 1024,
      temperature: 0,
      system: NARRATIVE_SYSTEM_PROMPT,
      tools: [ANTHROPIC_TOOL],
      tool_choice: { type: "tool", name: ANTHROPIC_TOOL.name },
      messages: [{ role: "user", content: userMessage(facts) }],
    },
    { signal, maxRetries: 0, timeout: TIMEOUT_MS },
  );
  const block = message?.content?.find((item) => item.type === "tool_use");
  if (!block) throw new Error("narrative reply had no tool call");
  return block.input;
}

/** One call within TIMEOUT_MS, retried once 1 s later after a 5xx only. */
async function callWithBudget(settings, facts) {
  const controller = new AbortController();
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject(Object.assign(new Error(`no narrative within ${TIMEOUT_MS / 1000} s`), { name: "TimeoutError" }));
    }, TIMEOUT_MS);
  });

  const call = () =>
    settings.provider === "gemini"
      ? callGemini(settings.model, facts, controller.signal)
      : callAnthropic(settings.model, facts, controller.signal);
  const attempt = async () => {
    try {
      return await call();
    } catch (error) {
      if (classifyJudgeError(error) !== "unavailable") throw error;
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS));
      if (controller.signal.aborted) throw error;
      return call();
    }
  };

  try {
    return await Promise.race([attempt(), deadline]);
  } finally {
    clearTimeout(timer);
  }
}

function cacheKey(settings, facts) {
  // The facts hold no identifier, so a plain hash is enough here (OSINT keys
  // need an HMAC because they are built from phone numbers).
  const digest = createHash("sha256").update(JSON.stringify(facts)).digest("hex");
  return `narrative:${NARRATIVE_PROMPT_VERSION}:${settings.provider}:${settings.model}:${digest}`;
}

/**
 * generateNarrative(result, settings = narrativeSettings())
 *   -> { en, ms, provider, model, promptVersion } | null
 *
 * result is the finished analysis; only narrativeFacts(result) is sent. Never
 * throws: off, failed or rejected, the answer is null and the analysis is
 * returned without a narrative.
 */
export async function generateNarrative(result, settings = narrativeSettings()) {
  if (!settings.enabled || !result) return null;
  const facts = narrativeFacts(result);
  const key = cacheKey(settings, facts);

  const cached = await cacheGet(key);
  if (cached?.en && cached?.ms) return cached;

  try {
    const checked = checkNarrative(await callWithBudget(settings, facts), facts);
    if (!checked.ok) {
      logger.warn(`narrative rejected: ${checked.reason}`);
      return null;
    }
    const narrative = {
      ...checked.narrative,
      provider: settings.provider,
      model: settings.model,
      promptVersion: NARRATIVE_PROMPT_VERSION,
    };
    await cacheSet(key, narrative, CACHE_TTL_SECONDS);
    return narrative;
  } catch (error) {
    const reason = redactSecrets(String(error?.message ?? "")).slice(0, MAX_ERROR_CHARS);
    logger.warn(`narrative unavailable (${classifyJudgeError(error)}): ${reason}`);
    return null;
  }
}
