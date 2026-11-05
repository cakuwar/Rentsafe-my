// End-to-end analysis pipeline orchestration.
import { randomUUID } from "node:crypto";
import { mergeAgentDetails, parseMetadata } from "./metadata.service.js";
import { classifyText } from "./nlp.service.js";
import { searchAgentReputation } from "./osint.service.js";
import { scorePriceAnomaly } from "./price.service.js";
import {
  aggregateScore,
  assessEvidenceSupport,
  capUnsupportedScore,
} from "./scoring.service.js";
import { generateNarrative } from "./llm.service.js";
import { insertListing } from "../db/listings.repo.js";
import { logger } from "../utils/logger.js";

/** Run a signal without letting its failure take the whole analysis down. */
async function attempt(name, work) {
  try {
    return await work();
  } catch (error) {
    logger?.warn?.(`${name} signal unavailable: ${error.message}`);
    return null;
  }
}

/**
 * runAnalysisPipeline({ rawText, sourceType, language, agent, property }) -> full result object
 *
 * Order matters and is deliberate:
 *   1. mint a listing id, parse metadata from the raw text and lay the agent
 *      details from the form over it (the form wins). The rent and property
 *      come from the form alone (`property`) — never from the chat
 *   2. run NLP, OSINT and price concurrently — they are independent, and the
 *      NLP call is the slow one, so waiting on it serially would dominate
 *   3. combine them into a deterministic score. The LLM has seen nothing at
 *      this point: it explains the score, it does not set it
 *   4. generate the narrative FROM the finished result: the score is set by
 *      then, and the narrative is checked against it (llm.service.js)
 *   5. save the result (no personal data: listings.repo.js) in the
 *      background, so the answer never waits on the database and a database
 *      failure is only logged
 *
 * Each signal is attempted independently, so an unimplemented or failing
 * service degrades the score's ceiling rather than the request.
 */
export async function runAnalysisPipeline({
  rawText, sourceType, language = "auto", agent = null, property = null,
}) {
  const listingId = randomUUID();
  const parsed = await attempt("metadata", () => parseMetadata(rawText));
  const metadata = mergeAgentDetails(parsed, agent);

  const [nlpRaw, osint, price] = await Promise.all([
    attempt("nlp", () => classifyText({ text: rawText, language })),
    attempt("osint", () => searchAgentReputation(metadata)),
    attempt("price", () => scorePriceAnomaly(property)),
  ]);

  // Flatten what the scorer needs out of the NLP response. `status` and
  // `confidence` decide whether the probability may be scored at all.
  const nlp = nlpRaw
    ? {
        scamProbability: nlpRaw.scam_probability,
        status: nlpRaw.layer2?.status ?? null,
        confidence: nlpRaw.layer2?.confidence ?? null,
        modelProbability: nlpRaw.layer2?.model_probability ?? null,
        redFlags: nlpRaw.red_flags ?? [],
        evidence: nlpRaw.layer1?.evidence ?? [],
        patterns: nlpRaw.layer1?.patterns ?? [],
        legitSignals: nlpRaw.layer1?.legit_signals ?? [],
        normalisedText: nlpRaw.normalised_text ?? null,
      }
    : null;

  // Score, then check it against the evidence. A high model score with no red
  // flag behind it is capped at MODERATE unless a strong OSINT hit backs it
  // (decisions recorded in scoring.service.js); the model's own probability is
  // passed through as is.
  const support = assessEvidenceSupport({
    scamProbability: nlp?.scamProbability,
    status: nlp?.status,
    evidence: nlp?.evidence ?? [],
  });
  const scoring = capUnsupportedScore(aggregateScore({ nlp, osint, price }), {
    scamProbability: nlp?.scamProbability,
    status: nlp?.status,
    redFlags: nlp?.redFlags ?? [],
    osint,
  });

  const result = {
    listingId,
    sourceType,
    language,
    riskScore: scoring.total,
    maxPossibleScore: scoring.maxPossible,
    riskBand: scoring.band,
    riskColour: scoring.colour,
    // Set when a high model score had no red flag behind it and the band was
    // held at MODERATE; carries the score and band before the cap.
    bandCap: scoring.bandCap,
    // The model's own output, never capped.
    modelProbability: nlp?.scamProbability ?? null,
    components: scoring.components,
    excludedSignals: scoring.excluded,
    // Passed through unchanged. A UI that renders only riskScore would show a
    // guarded result as though it were a judgement, which is exactly what the
    // short-input guard exists to prevent.
    nlpStatus: scoring.nlpStatus,
    nlpConfidence: scoring.nlpConfidence,
    // The guard's "send more of the conversation" takes precedence; otherwise
    // explain a score the evidence does not support.
    message: scoring.message ?? support.message,
    evidenceSupport: support.evidenceSupport,
    // Filled in below, once the rest of the result exists.
    narrative: null,
    metadata,
    evidence: {
      redFlags: nlp?.redFlags ?? [],
      details: nlp?.evidence ?? [],
      patterns: nlp?.patterns ?? [],
      legitSignals: nlp?.legitSignals ?? [],
      osint: osint ?? null,
      price: price ?? null,
    },
  };

  result.narrative = (await attempt("llm", () => generateNarrative(result))) ?? null;

  // Not awaited: with the database down, its 3 s connect timeout would be
  // added to every answer. attempt() catches and logs any failure.
  void attempt("persist", () => insertListing(result, property));
  return result;
}
