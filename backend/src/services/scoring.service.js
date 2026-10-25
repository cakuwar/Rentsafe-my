// Deterministic risk-scoring engine.
// Each signal returns a normalised 0..1 confidence; map it onto its weighted
// ceiling (see SCORE_WEIGHTS in config/index.js) and sum. Keep this simple
// and auditable — the LLM must NOT be involved in producing the number.
import { SCORE_WEIGHTS, RISK_BANDS } from "../config/index.js";

// Layer 2 statuses where scam_probability is NOT a risk estimate.
//
// The NLP service returns 0.5 in both cases, meaning "cannot judge" — not
// "medium risk". Multiplying that by the 60-point weight would put 30 points on
// the board and render a conversation nobody could assess as MODERATE, which is
// the opposite of what the service was saying. The signal is excluded instead.
const UNUSABLE_NLP_STATUSES = new Set([
  "insufficient_context",
  "model_unavailable",
]);

const SHORT_INPUT_MESSAGE = {
  en: "Send more of the conversation — there is not enough here to judge.",
  ms: "Hantar lagi perbualan — tidak cukup maklumat untuk menilai.",
};

const MODEL_DOWN_MESSAGE = {
  en: "Automated checking is unavailable; this score uses the other signals only.",
  ms: "Semakan automatik tidak tersedia; skor ini menggunakan isyarat lain sahaja.",
};

// Reported when no signal could be scored. Not a band on the 0-100 scale: a
// conversation nobody could assess is not low risk, and showing LOW next to
// "send more of the conversation" tells the renter the opposite of the truth.
const UNKNOWN_BAND = { band: "UNKNOWN", colour: "grey" };

function bandFor(total, anyIncluded) {
  if (!anyIncluded) return UNKNOWN_BAND;
  const found = RISK_BANDS.find((entry) => total >= entry.min && total <= entry.max);
  return found ?? RISK_BANDS[RISK_BANDS.length - 1];
}

function fraction(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return Math.min(1, Math.max(0, value));
}

/**
 * aggregateScore({ nlp, osint, price }) -> {
 *   total, maxPossible, band, colour, components, excluded,
 *   nlpStatus, nlpConfidence, message
 * }
 *
 * `total` is null when no signal could be scored, and `band` is then UNKNOWN.
 *
 * - nlp.scamProbability, osint.riskFraction, price.anomalyFraction are each 0..1
 * - points for a signal = fraction * that signal's weight
 * - total = sum of points, rounded, capped at 100
 * - band = whichever RISK_BANDS entry total falls into
 *
 * Weights are NOT redistributed when a signal is missing. A score built from
 * fewer signals is a weaker claim, and saying so plainly — via `maxPossible` and
 * `excluded` — is more honest than scaling the remainder up to 100 and hiding
 * that the evidence was thinner. The consequence is real and deliberate: with
 * only the NLP signal available the ceiling is 60, so the result can reach HIGH
 * but never CRITICAL. Corroboration is what earns the top band.
 */
export function aggregateScore({ nlp, osint, price }) {
  const nlpUsable =
    nlp != null &&
    !UNUSABLE_NLP_STATUSES.has(nlp.status) &&
    fraction(nlp.scamProbability) !== null;

  const signals = [
    {
      name: "nlp",
      weight: SCORE_WEIGHTS.nlp,
      value: nlpUsable ? fraction(nlp.scamProbability) : null,
    },
    {
      name: "osint",
      weight: SCORE_WEIGHTS.osint,
      value: fraction(osint?.riskFraction),
    },
    {
      name: "price",
      weight: SCORE_WEIGHTS.price,
      value: fraction(price?.anomalyFraction),
    },
  ];

  const components = {};
  let total = 0;
  let maxPossible = 0;
  const excluded = [];

  for (const signal of signals) {
    const included = signal.value !== null;
    if (included) {
      total += signal.value * signal.weight;
      maxPossible += signal.weight;
    } else {
      excluded.push(signal.name);
    }
    components[signal.name] = {
      points: included ? Math.round(signal.value * signal.weight) : 0,
      max: included ? signal.weight : 0,
      included,
    };
  }

  const anyIncluded = maxPossible > 0;
  // null, not 0, when nothing could be scored. A frontend rendering `riskScore`
  // would otherwise print "0" beside "send more of the conversation", and 0 on a
  // 0-100 scale reads as "safe" — the opposite of what the service determined.
  // null forces the caller to handle the case instead of mis-rendering it.
  total = anyIncluded ? Math.min(100, Math.round(total)) : null;
  const { band, colour } = bandFor(total ?? 0, anyIncluded);

  let message = null;
  if (nlp?.status === "insufficient_context") message = SHORT_INPUT_MESSAGE;
  else if (nlp?.status === "model_unavailable") message = MODEL_DOWN_MESSAGE;

  return {
    total,
    maxPossible,
    band,
    colour,
    components,
    excluded,
    // Carried through unchanged so the UI can explain itself rather than
    // presenting a number it cannot justify.
    nlpStatus: nlp?.status ?? null,
    nlpConfidence: nlp?.confidence ?? null,
    message,
  };
}

// ---------------------------------------------------------------------------
// Does the evidence support the score?
//
// A real, legitimate agent conversation scored HIGH (60/60) with zero red
// flags and no message: the renter was told a genuine letting was high risk,
// with nothing to justify it. The model's number and layer 1's evidence are
// independent, and when they disagree the renter should be told — not left
// with a confident number and no reason.
//
// This function only reports. The band is capped separately, by
// capUnsupportedScore below — see the decision recorded there.
// ---------------------------------------------------------------------------

const STRONG = new Set(["critical", "high"]);

const SUPPORT_MESSAGES = {
  none: {
    en: "The model rated this as risky, but no specific scam tactic was found. "
      + "Verify the landlord and the unit before paying anything.",
    ms: "Model menilai ini berisiko, tetapi tiada taktik penipuan khusus ditemui. "
      + "Sahkan pemilik dan unit sebelum membuat sebarang bayaran.",
  },
  contradicted: {
    en: "Our automated check rated this as lower risk, but it contains warning "
      + "signs listed below. Treat it with caution.",
    ms: "Semakan automatik menilai ini kurang berisiko, tetapi terdapat tanda "
      + "amaran di bawah. Berhati-hati.",
  },
};

/**
 * assessEvidenceSupport({ scamProbability, status, evidence }) -> {
 *   evidenceSupport, strongFlags, message
 * }
 *
 *   model HIGH + a critical/high red flag   -> "corroborated"
 *   model HIGH + only medium/low flags      -> "partial"
 *   model HIGH + no red flags               -> "none"          (explain)
 *   model LOW  + no red flags               -> "consistent"
 *   model LOW  + a critical/high red flag   -> "contradicted"  (warn)
 *   model LOW  + only medium/low flags      -> "partial"
 *   layer 2 could not judge                 -> "not_scored"
 */
export function assessEvidenceSupport({ scamProbability, status, evidence = [] }) {
  if (status !== "ok" || typeof scamProbability !== "number") {
    return { evidenceSupport: "not_scored", strongFlags: 0, message: null };
  }

  const strong = evidence.filter((item) => STRONG.has(item.severity)).length;
  const any = evidence.length;
  const high = scamProbability >= 0.5;

  let support;
  if (high) {
    support = strong ? "corroborated" : any ? "partial" : "none";
  } else {
    support = strong ? "contradicted" : any ? "partial" : "consistent";
  }

  return {
    evidenceSupport: support,
    strongFlags: strong,
    message: SUPPORT_MESSAGES[support] ?? null,
  };
}

// ---------------------------------------------------------------------------
// Band cap when a high model score has no red flag behind it.
//
// DECISION (author, 2026-09-28) — reverses the earlier rule that layer 1 never
// affects the result. The motivating case: a real, legitimate iBilik agent
// conversation, through OCR, scored 0.94 by the deployed model with zero red
// flags and three legitimacy signals (keys in person, payment at handover, a
// platform agreement). The model's number was HIGH with nothing in the text to
// point to.
//
// The rule touches the band only:
//   model high (scam_probability >= 0.5, status ok) AND no red flags
//       -> band at most MODERATE; riskScore lowered to MODERATE's top (49) if
//          it was above it, so score and band never disagree
//   red flags present            -> unchanged (HIGH / CRITICAL possible)
//   model low                    -> unchanged
//   layer 2 could not judge      -> unchanged (UNKNOWN stays UNKNOWN)
//
// It never lowers below MODERATE: a model-high score is at least 30 points on
// its own (0.5 x 60), and the cap only removes bands above MODERATE. Legitimacy
// signals play no part — they can be faked, and measured on the corpus every
// one fires more often on scams — so they are listed as context, never used to
// lower the band. Layer 2 is untouched: scam_probability and model_probability
// still reach the response as the model produced them.
//
// Cost, measured by nlp-service/eval/cap_cost.py on the corpus: see
// docs/MODEL_COMPARISON.md section 14.11.
//
// DECISION (author, 2026-10-04) — a strong OSINT hit lifts the cap. The cap
// exists because the model's number had nothing behind it; the agent's phone
// number or REN in scam reports is evidence independent of the chat text, so
// HIGH / CRITICAL is allowed even when layer 1 found no red flag. Deliberately
// narrow (osint.strongHit, with osint.strongHitReason):
//   phone / REN complaint on a news or forum source       -> lifts the cap
//                                                            ("news_or_forum")
//   phone / REN complaints from 3+ independent social     -> lifts the cap
//   sources (distinct groups / accounts; several posts       ("social_corroboration")
//   in one group count once)
//   phone / REN on fewer than 3 social sources            -> does not
//   name or company hit, any source or number of sources  -> does not (names
//                                                            are shared; the
//                                                            hit may be someone else)
// Those weaker hits still add their OSINT points; they just cannot carry the
// result past MODERATE on their own. The motivating case for corroboration: a
// real scam number reported in four separate Facebook groups and on Threads,
// none of them a news site or forum.
//
// DECISION (author, 2026-10-15) — a price anomaly does NOT lift the cap. A
// rent far below its stratum still adds its points, but on its own it cannot
// carry a no-red-flag result past MODERATE: the research doc (§5.5.1) treats
// price as "a corroborating signal rather than a primary indicator", and
// legitimate landlords do under-price (vacancy, condition, circumstances).
// ---------------------------------------------------------------------------

const CAP_BAND = RISK_BANDS.find((entry) => entry.band === "MODERATE");

/**
 * capUnsupportedScore(scoring, { scamProbability, status, redFlags, osint }) -> scoring
 *
 * Returns the scoring object with `bandCap` added: null when the cap did not
 * change anything, otherwise
 *   { applied: true, reason: "no_red_flags", uncappedScore, uncappedBand }
 * and `total`, `band`, `colour` lowered to the MODERATE band.
 */
export function capUnsupportedScore(scoring, { scamProbability, status, redFlags = [], osint = null }) {
  const modelHigh =
    status === "ok" && typeof scamProbability === "number" && scamProbability >= 0.5;
  const unsupported = modelHigh && redFlags.length === 0 && !osint?.strongHit;
  const aboveCap = typeof scoring.total === "number" && scoring.total > CAP_BAND.max;

  if (!unsupported || !aboveCap) {
    return { ...scoring, bandCap: null };
  }
  return {
    ...scoring,
    total: CAP_BAND.max,
    band: CAP_BAND.band,
    colour: CAP_BAND.colour,
    bandCap: {
      applied: true,
      reason: "no_red_flags",
      uncappedScore: scoring.total,
      uncappedBand: scoring.band,
    },
  };
}
