// The band cap: a high model score with no layer-1 red flag is held at
// MODERATE. Decision of 2026-09-28, recorded in scoring.service.js.
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  aggregateScore,
  assessEvidenceSupport,
  capUnsupportedScore,
} from "../src/services/scoring.service.js";

const ok = (scamProbability) => ({ scamProbability, status: "ok", confidence: "high" });
const capped = (nlp, others = {}, redFlags = []) =>
  capUnsupportedScore(aggregateScore({ nlp, ...others }), {
    scamProbability: nlp.scamProbability,
    status: nlp.status,
    redFlags,
  });

describe("capUnsupportedScore", () => {
  it("holds a high score with no red flags at MODERATE, score 49", () => {
    // The iBilik case: 0.94 through OCR, zero red flags -> 56 points, HIGH.
    const result = capped(ok(0.9411));
    expect(result.band).toBe("MODERATE");
    expect(result.colour).toBe("yellow");
    expect(result.total).toBe(49);
    expect(result.bandCap).toEqual({
      applied: true, reason: "no_red_flags", uncappedScore: 56, uncappedBand: "HIGH",
    });
  });

  it("never drops a high score with no red flags below MODERATE", () => {
    for (let p = 0.5; p <= 1.0001; p += 0.01) {
      for (const others of [{}, { osint: { riskFraction: 0 }, price: { anomalyFraction: 0 } }]) {
        const result = capped(ok(p), others);
        expect(result.band, `p=${p.toFixed(2)}`).toBe("MODERATE");
        expect(result.total).toBeGreaterThanOrEqual(25);
        expect(result.total).toBeLessThanOrEqual(49);
      }
    }
  });

  it("caps CRITICAL too when nothing in the text backs the model", () => {
    const result = capped(ok(1), { osint: { riskFraction: 1 }, price: { anomalyFraction: 1 } });
    expect(result.band).toBe("MODERATE");
    expect(result.total).toBe(49);
    expect(result.bandCap.uncappedBand).toBe("CRITICAL");
    expect(result.bandCap.uncappedScore).toBe(100);
  });

  it("leaves the result alone when red flags are present", () => {
    const high = capped(ok(0.9853), {}, ["pay_before_viewing"]);
    expect(high.band).toBe("HIGH");
    expect(high.total).toBe(59);
    expect(high.bandCap).toBeNull();

    const critical = capped(ok(1), { osint: { riskFraction: 1 }, price: { anomalyFraction: 1 } },
      ["upfront_payment"]);
    expect(critical.band).toBe("CRITICAL");
    expect(critical.bandCap).toBeNull();
  });

  it("leaves the result alone when the model score is low", () => {
    const low = capped(ok(0.08));
    expect(low.band).toBe("LOW");
    expect(low.bandCap).toBeNull();

    // Even if other signals push the total up, the rule is about the model.
    const pushed = capped(ok(0.3), { osint: { riskFraction: 1 }, price: { anomalyFraction: 1 } });
    expect(pushed.total).toBe(58);
    expect(pushed.band).toBe("HIGH");
    expect(pushed.bandCap).toBeNull();
  });

  it("does nothing when the score is already MODERATE or below", () => {
    const result = capped(ok(0.6));            // 36 points
    expect(result.band).toBe("MODERATE");
    expect(result.total).toBe(36);
    expect(result.bandCap).toBeNull();
  });

  it("keeps UNKNOWN when layer 2 could not judge", () => {
    for (const status of ["insufficient_context", "model_unavailable"]) {
      const result = capped({ scamProbability: 0.5, status, confidence: "insufficient" });
      expect(result.band).toBe("UNKNOWN");
      expect(result.total).toBeNull();
      expect(result.bandCap).toBeNull();
    }
  });

  it("reports evidenceSupport 'none' with the verify message on a capped result", () => {
    const support = assessEvidenceSupport({ scamProbability: 0.9411, status: "ok", evidence: [] });
    expect(support.evidenceSupport).toBe("none");
    expect(support.message.en).toMatch(/no specific scam tactic was found/i);
    expect(support.message.en).toMatch(/verify the landlord and the unit before paying/i);
    expect(support.message.ms).toMatch(/tiada taktik penipuan khusus/i);
  });
});

// Decision of 2026-10-04: a phone / REN hit on a news or forum source is
// independent evidence and lifts the cap; weaker OSINT hits do not.
describe("capUnsupportedScore with OSINT evidence", () => {
  const withOsint = (osint) =>
    capUnsupportedScore(aggregateScore({ nlp: ok(0.95), osint }), {
      scamProbability: 0.95,
      status: "ok",
      redFlags: [],
      osint,
    });

  it("lets a forum or news phone hit lift the cap", () => {
    const forum = withOsint({ riskFraction: 8 / 25, strongHit: true });   // 57 + 8
    expect(forum.band).toBe("HIGH");
    expect(forum.total).toBe(65);
    expect(forum.bandCap).toBeNull();

    const news = withOsint({ riskFraction: 12 / 25, strongHit: true });   // 57 + 12
    expect(news.band).toBe("HIGH");
    expect(news.total).toBe(69);

    const all = withOsint({ riskFraction: 1, strongHit: true });          // 57 + 25
    expect(all.band).toBe("CRITICAL");
    expect(all.total).toBe(82);
  });

  it("keeps the cap for a social-only hit or a name-only hit", () => {
    const social = withOsint({ riskFraction: 5 / 25, strongHit: false }); // 62
    expect(social.band).toBe("MODERATE");
    expect(social.bandCap).toMatchObject({ applied: true, uncappedScore: 62, uncappedBand: "HIGH" });

    const nameNews = withOsint({ riskFraction: 12 / 25, strongHit: false }); // 69
    expect(nameNews.band).toBe("MODERATE");
    expect(nameNews.total).toBe(49);
  });

  it("lets phone complaints from 3+ independent social sources lift the cap", () => {
    // Golden case #2: social tier only (5 points), corroborated by 4 sources.
    const corroborated = withOsint({
      riskFraction: 5 / 25, strongHit: true, strongHitReason: "social_corroboration",
      corroboration: { sources: 4, threshold: 3, keys: [] },
    });
    expect(corroborated.band).toBe("HIGH");                               // 57 + 5
    expect(corroborated.total).toBe(62);
    expect(corroborated.bandCap).toBeNull();
  });

  it("keeps the cap for a single social source", () => {
    const single = withOsint({
      riskFraction: 5 / 25, strongHit: false, strongHitReason: null,
      corroboration: { sources: 1, threshold: 3, keys: [] },
    });
    expect(single.band).toBe("MODERATE");
    expect(single.total).toBe(49);
  });

  it("keeps the cap when the search could not run", () => {
    for (const osint of [null, { riskFraction: null, strongHit: false, status: "search_failed" }]) {
      expect(withOsint(osint).band).toBe("MODERATE");
    }
  });
});

// ---------------------------------------------------------------------------
// Through the pipeline, with every outside service mocked.
// ---------------------------------------------------------------------------

vi.mock("../src/services/nlp.service.js", () => ({ classifyText: vi.fn() }));
vi.mock("../src/services/metadata.service.js", () => ({
  parseMetadata: vi.fn(() => null),
  mergeAgentDetails: vi.fn((parsed, agent) => ({ ...parsed, agentName: agent?.name ?? null })),
}));
vi.mock("../src/services/osint.service.js", () => ({ searchAgentReputation: vi.fn(async () => null) }));
vi.mock("../src/services/price.service.js", () => ({ scorePriceAnomaly: vi.fn(async () => null) }));
vi.mock("../src/services/llm.service.js", () => ({ generateNarrative: vi.fn(async () => null) }));
vi.mock("../src/db/listings.repo.js", () => ({ insertListing: vi.fn(async () => {}) }));

const { classifyText } = await import("../src/services/nlp.service.js");
const { searchAgentReputation } = await import("../src/services/osint.service.js");
const { runAnalysisPipeline } = await import("../src/services/pipeline.service.js");

const LEGIT_SIGNALS = [
  { id: "in_person_handover" }, { id: "payment_at_handover" }, { id: "platform_agreement" },
];

function nlpResponse({ p, status = "ok", redFlags = [], evidence = [], legit = [] }) {
  return {
    scam_probability: p,
    red_flags: redFlags,
    normalised_text: "…",
    layer1: { evidence, patterns: [], legit_signals: legit },
    layer2: { scam_probability: p, model_probability: p, status, confidence: "high" },
  };
}

describe("runAnalysisPipeline with the band cap", () => {
  beforeEach(() => classifyText.mockReset());

  it("returns MODERATE, the verify message and the legit signals for the iBilik case", async () => {
    classifyText.mockResolvedValue(nlpResponse({ p: 0.9411, legit: LEGIT_SIGNALS }));
    const result = await runAnalysisPipeline({ rawText: "x".repeat(40), sourceType: "text" });

    expect(result.riskBand).toBe("MODERATE");
    expect(result.riskScore).toBe(49);
    expect(result.bandCap).toMatchObject({ applied: true, uncappedScore: 56, uncappedBand: "HIGH" });
    expect(result.evidenceSupport).toBe("none");
    expect(result.message.en).toMatch(/no specific scam tactic/i);
    expect(result.evidence.legitSignals.map((s) => s.id)).toEqual(
      ["in_person_handover", "payment_at_handover", "platform_agreement"]);
  });

  it("does not let legitimacy signals lower the band below MODERATE", async () => {
    classifyText.mockResolvedValue(nlpResponse({ p: 0.9999, legit: LEGIT_SIGNALS }));
    const result = await runAnalysisPipeline({ rawText: "x".repeat(40), sourceType: "text" });
    expect(result.riskBand).toBe("MODERATE");
    expect(result.riskBand).not.toBe("LOW");
  });

  it("passes the model's probability through untouched", async () => {
    classifyText.mockResolvedValue(nlpResponse({ p: 0.9411 }));
    const result = await runAnalysisPipeline({ rawText: "x".repeat(40), sourceType: "text" });
    expect(result.modelProbability).toBe(0.9411);
    expect(result.components.nlp.points).toBe(56);     // contribution before the cap
  });

  it("returns HIGH with the flags when the evidence backs the score", async () => {
    classifyText.mockResolvedValue(nlpResponse({
      p: 0.9853,
      redFlags: ["pay_before_viewing", "upfront_payment"],
      evidence: [{ id: "pay_before_viewing", severity: "critical" }],
    }));
    const result = await runAnalysisPipeline({ rawText: "x".repeat(40), sourceType: "text" });
    expect(result.riskBand).toBe("HIGH");
    expect(result.riskScore).toBe(59);
    expect(result.bandCap).toBeNull();
    expect(result.evidenceSupport).toBe("corroborated");
    expect(result.evidence.redFlags).toContain("pay_before_viewing");
  });

  it("keeps UNKNOWN for a guarded short conversation", async () => {
    classifyText.mockResolvedValue(nlpResponse({ p: 0.5, status: "insufficient_context" }));
    const result = await runAnalysisPipeline({ rawText: "x".repeat(40), sourceType: "text" });
    expect(result.riskBand).toBe("UNKNOWN");
    expect(result.riskScore).toBeNull();
    expect(result.bandCap).toBeNull();
  });

  it("lifts the cap when OSINT found the phone on a complaint forum", async () => {
    classifyText.mockResolvedValue(nlpResponse({ p: 0.9411 }));
    searchAgentReputation.mockResolvedValueOnce({ status: "ok", riskFraction: 8 / 25, strongHit: true });
    const result = await runAnalysisPipeline({
      rawText: "x".repeat(40),
      sourceType: "text",
      agent: { name: "Ahmad Faizal" },
    });

    expect(searchAgentReputation).toHaveBeenLastCalledWith(
      expect.objectContaining({ agentName: "Ahmad Faizal" }),
    );
    expect(result.riskBand).toBe("HIGH");
    expect(result.riskScore).toBe(64);                   // 56 + 8
    expect(result.bandCap).toBeNull();
    expect(result.components.osint).toEqual({ points: 8, max: 25, included: true });
  });
});
