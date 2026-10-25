// Unit tests for the deterministic scoring engine (scoring.service.js).
import { describe, it, expect } from "vitest";
import { aggregateScore } from "../src/services/scoring.service.js";
import { SCORE_WEIGHTS } from "../src/config/index.js";

const ok = (scamProbability) => ({
  scamProbability,
  status: "ok",
  confidence: "high",
});

describe("aggregateScore", () => {
  it("returns 0 / LOW for all-clear signals", () => {
    const result = aggregateScore({
      nlp: ok(0),
      osint: { riskFraction: 0 },
      price: { anomalyFraction: 0 },
    });

    expect(result.total).toBe(0);
    expect(result.band).toBe("LOW");
  });

  it("caps at 100 / CRITICAL when every signal maxes out", () => {
    const result = aggregateScore({
      nlp: ok(1),
      osint: { riskFraction: 1 },
      price: { anomalyFraction: 1 },
    });

    expect(result.total).toBe(100);
    expect(result.band).toBe("CRITICAL");
  });

  it("respects the nlp/osint/price weighting for a mixed-signal input", () => {
    const result = aggregateScore({
      nlp: ok(0.5),
      osint: { riskFraction: 0.2 },
      price: { anomalyFraction: 1 },
    });

    // 0.5*60 + 0.2*25 + 1*15 = 30 + 5 + 15 = 50
    expect(result.total).toBe(50);
    expect(result.components.nlp.points).toBe(30);
    expect(result.components.osint.points).toBe(5);
    expect(result.components.price.points).toBe(15);
  });

  it("scores scam_probability x 60 when the status is ok", () => {
    const result = aggregateScore({ nlp: ok(1) });
    expect(result.components.nlp.points).toBe(SCORE_WEIGHTS.nlp);
  });
});

// ---------------------------------------------------------------------------
// Layer 2 status handling
//
// The NLP service returns 0.5 on "insufficient_context" and "model_unavailable",
// meaning "cannot judge". Scoring that as 0.5 x 60 = 30 points would present a
// conversation nobody could assess as MODERATE risk — the opposite of what the
// service said. These are the tests that stop that happening.
// ---------------------------------------------------------------------------

describe("aggregateScore with an unusable NLP signal", () => {
  it("excludes layer 2 on insufficient_context instead of scoring 0.5", () => {
    const result = aggregateScore({
      nlp: { scamProbability: 0.5, status: "insufficient_context", confidence: "insufficient" },
      osint: { riskFraction: 0 },
      price: { anomalyFraction: 0 },
    });

    expect(result.components.nlp.included).toBe(false);
    expect(result.components.nlp.points).toBe(0);
    expect(result.excluded).toContain("nlp");
    // osint and price were scored, so there is still a number.
    expect(result.total).toBe(0);
  });

  it("excludes layer 2 on model_unavailable", () => {
    const result = aggregateScore({
      nlp: { scamProbability: 0.5, status: "model_unavailable", confidence: "insufficient" },
    });

    expect(result.components.nlp.included).toBe(false);
    expect(result.excluded).toContain("nlp");
  });

  it("never lets a guarded 0.5 reach MODERATE on its own", () => {
    const guarded = aggregateScore({
      nlp: { scamProbability: 0.5, status: "insufficient_context", confidence: "insufficient" },
    });

    // null rather than 0: a frontend printing "0" beside "send more of the
    // conversation" would tell the renter it is safe.
    expect(guarded.total).toBeNull();
    expect(guarded.band).toBe("UNKNOWN");
  });

  it("lowers maxPossible so a thinner score is visible as thinner", () => {
    const full = aggregateScore({
      nlp: ok(1),
      osint: { riskFraction: 1 },
      price: { anomalyFraction: 1 },
    });
    const guarded = aggregateScore({
      nlp: { scamProbability: 0.5, status: "insufficient_context" },
      osint: { riskFraction: 1 },
      price: { anomalyFraction: 1 },
    });

    expect(full.maxPossible).toBe(100);
    expect(guarded.maxPossible).toBe(40);
  });

  it("carries status, confidence and a bilingual message through", () => {
    const result = aggregateScore({
      nlp: { scamProbability: 0.5, status: "insufficient_context", confidence: "insufficient" },
    });

    expect(result.nlpStatus).toBe("insufficient_context");
    expect(result.nlpConfidence).toBe("insufficient");
    expect(result.message.en).toMatch(/send more of the conversation/i);
    expect(result.message.ms).toBeTruthy();
  });

  it("gives a different message when the model is down", () => {
    const result = aggregateScore({
      nlp: { scamProbability: 0.5, status: "model_unavailable" },
    });

    expect(result.message.en).toMatch(/unavailable/i);
  });

  it("reports no message when the status is ok", () => {
    expect(aggregateScore({ nlp: ok(0.9) }).message).toBeNull();
  });
});

describe("aggregateScore with signals missing entirely", () => {
  it("excludes an absent osint or price signal", () => {
    const result = aggregateScore({ nlp: ok(1) });

    expect(result.excluded).toEqual(expect.arrayContaining(["osint", "price"]));
    expect(result.total).toBe(60);
    expect(result.maxPossible).toBe(60);
  });

  it("does not redistribute weight to reach CRITICAL on one signal", () => {
    // Deliberate: corroboration is what earns the top band. A certain scam with
    // no OSINT or price evidence reaches HIGH, not CRITICAL.
    const result = aggregateScore({ nlp: ok(1) });
    expect(result.band).toBe("HIGH");
  });

  it("returns 0 / LOW when nothing at all is available", () => {
    const result = aggregateScore({});

    expect(result.total).toBeNull();
    expect(result.maxPossible).toBe(0);
    expect(result.excluded).toHaveLength(3);
  });

  it("clamps out-of-range fractions", () => {
    const result = aggregateScore({ nlp: ok(5), osint: { riskFraction: -2 } });
    expect(result.components.nlp.points).toBe(SCORE_WEIGHTS.nlp);
    expect(result.components.osint.points).toBe(0);
  });
});

describe("the UNKNOWN band", () => {
  it("reports UNKNOWN, not LOW, when nothing could be scored", () => {
    // A guarded scam scoring 0 out of a possible 0 is not low risk. Showing
    // LOW beside "send more of the conversation" would say the opposite.
    const result = aggregateScore({
      nlp: { scamProbability: 0.5, status: "insufficient_context" },
    });

    expect(result.total).toBeNull();
    expect(result.maxPossible).toBe(0);
    expect(result.band).toBe("UNKNOWN");
    expect(result.colour).toBe("grey");
  });

  it("still reports LOW when a signal genuinely says low risk", () => {
    const result = aggregateScore({ nlp: ok(0) });

    expect(result.band).toBe("LOW");
    expect(result.maxPossible).toBe(60);
  });
});

describe("a high score on short input still reaches the user", () => {
  it("scores a guarded-length conversation when layer 2 reports ok", () => {
    // The NLP guard is one-directional: it replaces LOW scores on short input,
    // never HIGH ones. A scam obvious from four messages arrives with
    // status "ok" and confidence "insufficient", and must be scored normally.
    const result = aggregateScore({
      nlp: { scamProbability: 0.9997, status: "ok", confidence: "insufficient" },
    });

    expect(result.components.nlp.included).toBe(true);
    expect(result.total).toBe(60);
    expect(result.band).toBe("HIGH");
    expect(result.band).not.toBe("UNKNOWN");
    expect(result.message).toBeNull();
  });

  it("passes the thin-context confidence through for the UI to show", () => {
    const result = aggregateScore({
      nlp: { scamProbability: 0.96, status: "ok", confidence: "insufficient" },
    });

    expect(result.nlpConfidence).toBe("insufficient");
    expect(result.nlpStatus).toBe("ok");
  });
});

import { assessEvidenceSupport } from "../src/services/scoring.service.js";

// A real, legitimate agent chat scored HIGH with zero red flags and no
// message. These pin that the renter is told when the evidence does not back
// the score. assessEvidenceSupport only reports; the band cap that follows
// from the same finding is tested in band_cap.test.js.
describe("assessEvidenceSupport", () => {
  const flag = (severity) => ({ id: "x", severity });

  it("reports 'none' and explains, for a high score with no evidence", () => {
    const result = assessEvidenceSupport({
      scamProbability: 0.9997, status: "ok", evidence: [],
    });
    expect(result.evidenceSupport).toBe("none");
    expect(result.message.en).toMatch(/no specific scam tactic/i);
    expect(result.message.ms).toBeTruthy();
  });

  it("reports 'corroborated' when a critical or high flag backs the score", () => {
    for (const severity of ["critical", "high"]) {
      const result = assessEvidenceSupport({
        scamProbability: 0.98, status: "ok", evidence: [flag(severity)],
      });
      expect(result.evidenceSupport).toBe("corroborated");
      expect(result.message).toBeNull();
    }
  });

  it("reports 'partial' when only medium or low flags back a high score", () => {
    const result = assessEvidenceSupport({
      scamProbability: 0.9, status: "ok", evidence: [flag("medium"), flag("low")],
    });
    expect(result.evidenceSupport).toBe("partial");
  });

  it("reports 'contradicted' when rules find danger the model rated low", () => {
    // The opposite failure: an English courier-key scam the model scored 0.0282.
    const result = assessEvidenceSupport({
      scamProbability: 0.03, status: "ok", evidence: [flag("critical")],
    });
    expect(result.evidenceSupport).toBe("contradicted");
    expect(result.message.en).toMatch(/warning signs/i);
  });

  it("reports 'consistent' when a low score has nothing against it", () => {
    const result = assessEvidenceSupport({
      scamProbability: 0.01, status: "ok", evidence: [],
    });
    expect(result.evidenceSupport).toBe("consistent");
    expect(result.message).toBeNull();
  });

  it("does not judge when layer 2 could not score", () => {
    for (const status of ["insufficient_context", "model_unavailable"]) {
      const result = assessEvidenceSupport({
        scamProbability: 0.5, status, evidence: [flag("critical")],
      });
      expect(result.evidenceSupport).toBe("not_scored");
    }
  });

  it("never changes the score itself", () => {
    // evidenceSupport is reporting only; aggregateScore is untouched by it.
    const scored = aggregateScore({ nlp: ok(0.9997) });
    const support = assessEvidenceSupport({
      scamProbability: 0.9997, status: "ok", evidence: [],
    });
    expect(scored.total).toBe(60);
    expect(support.evidenceSupport).toBe("none");
  });
});
