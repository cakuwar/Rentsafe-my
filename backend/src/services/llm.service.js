// LLM narrative module (FYP2 — P9).
// Generates a plain-language BM/EN explanation of the ALREADY-COMPUTED score.
// Design constraint for your report: the model must be told the score is
// fixed and must explain it, never recompute or change it (verifiability).
import Anthropic from "@anthropic-ai/sdk";
import { config } from "../config/index.js";
import { cacheGet, cacheSet } from "./cache.service.js";
import { logger } from "../utils/logger.js";

/**
 * generateNarrative({ scoring, meta, nlp, osint, price, language }) -> string
 * - cache by a key derived from the inputs so identical listings don't re-bill
 * - build a prompt that:
 *     - states the score is already computed and must not be changed
 *     - asks for a short (3-4 sentence) explanation in the right language
 *     - includes the component breakdown + concrete evidence (red flags,
 *       complaint hit count, price deviation, agent/phone)
 *     - treats evidence.legitSignals as context, NEVER as a reason the listing
 *       is safe: measured on the corpus, every legitimacy signal fires more
 *       often on scams than on honest chats (scammers imitate proper lettings),
 *       and even after withholding they appear on 5.4% of scams vs 5.7% of
 *       legitimate ones (nlp-service/eval/results/legit_signal_rates.json)
 * - call the Anthropic API, cache and return the text
 * - on failure, fall back to a generic templated explanation (never throw —
 *   a broken narrative should not break the whole analysis response)
 */
export async function generateNarrative({ scoring, meta, nlp, osint, price, language }) {
  // TODO: implement
}
