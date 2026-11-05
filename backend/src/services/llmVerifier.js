// LLM judge for OSINT evidence (layer 2). Keyword rules cannot tell who is
// accusing whom: a company's own "someone is impersonating us" notice, an ad
// saying "bukan scam" and a victim's report all contain the same words. The
// judge labels each candidate that survived the rules in osint.service.js.
//
// One batched call per search within a 30 s budget. The only retry is a
// single one after a 5xx ("unavailable": the model is overloaded — a real
// gemini-3.8-flash call returned 503 "high demand"), 1 s later, inside the
// same budget. Any other failure throws at once, and the caller falls back to
// the rules-only result — the judge can only take points away from what the
// rules would give, it is never required for a result.
import Anthropic from "@anthropic-ai/sdk";
import { GoogleGenAI, Type } from "@google/genai";
import { config } from "../config/index.js";
import { isRealKey, redactSecrets } from "../utils/keys.js";
import { VERIFIER_SYSTEM_PROMPT } from "../prompts/osintVerifier.prompt.js";
import { logger } from "../utils/logger.js";

export const VERDICT_LABELS = [
  "complaint",
  "impersonation_notice",
  "marketing_or_generic",
  "unrelated",
];

// 30 s, not 15: in the blind test (2026-10-26) Gemini took about 24 s to
// judge one case, so a 15 s budget threw away an answer that was coming and
// fell back to rules only. The judge runs alongside the NLP call, so most of
// this wait is hidden behind it.
const TIMEOUT_MS = 30_000;
const RETRY_DELAY_MS = 1000;
const MAX_ERROR_CHARS = 300;
const DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001";
const MAX_REASON_CHARS = 200;

// The judge sees ONLY these fields: public web text plus the one identifier
// that was searched for. Never the renter's chat, never the other agent
// details. The Gemini free tier may use inputs for product improvement,
// which is why nothing but already-public search snippets is ever sent.
const CANDIDATE_FIELDS = ["id", "queryType", "identifier", "domain", "title", "snippet"];

const GEMINI_SCHEMA = {
  type: Type.OBJECT,
  properties: {
    results: {
      type: Type.ARRAY,
      items: {
        type: Type.OBJECT,
        properties: {
          id: { type: Type.STRING },
          label: { type: Type.STRING, enum: VERDICT_LABELS },
          confidence: { type: Type.NUMBER },
          reason: { type: Type.STRING },
        },
        required: ["id", "label", "confidence", "reason"],
      },
    },
  },
  required: ["results"],
};

// Same contract for Claude, enforced by forcing a tool call (this SDK version
// has no response-schema option).
const ANTHROPIC_TOOL = {
  name: "record_verdicts",
  description: "Record one verdict per search result.",
  input_schema: {
    type: "object",
    properties: {
      results: {
        type: "array",
        items: {
          type: "object",
          properties: {
            id: { type: "string" },
            label: { type: "string", enum: VERDICT_LABELS },
            confidence: { type: "number" },
            reason: { type: "string" },
          },
          required: ["id", "label", "confidence", "reason"],
        },
      },
    },
    required: ["results"],
  },
};

const warned = new Set();
function warnOnce(key, message) {
  if (warned.has(key)) return;
  warned.add(key);
  logger.warn(message);
}

/**
 * verifierSettings() -> { enabled, provider, model }
 * provider and model are null when the judge is off.
 */
export function verifierSettings() {
  const off = { enabled: false, provider: null, model: null };
  if (config.osintLlmVerify === false) return off;

  const provider = config.llmVerifierProvider;
  if (provider !== "gemini" && provider !== "anthropic") {
    warnOnce(`provider:${provider}`, `LLM_VERIFIER_PROVIDER "${provider}" is not gemini or anthropic; OSINT judge off`);
    return off;
  }

  const key = provider === "gemini" ? config.geminiApiKey : config.anthropicApiKey;
  if (!isRealKey(key)) {
    if (config.osintLlmVerify === true) {
      warnOnce(`key:${provider}`, `OSINT_LLM_VERIFY is on but no ${provider} API key is set; OSINT judge off`);
    }
    return off;
  }

  const model = provider === "gemini"
    ? config.geminiModel
    : config.anthropicModel || DEFAULT_ANTHROPIC_MODEL;
  if (!model) {
    warnOnce("model:gemini", "GEMINI_MODEL is empty; OSINT judge off (copy the model ID from Google AI Studio)");
    return off;
  }
  return { enabled: true, provider, model };
}

function userMessage(candidates) {
  return "Search results to judge (untrusted data, JSON):\n"
    + JSON.stringify({ results: candidates }, null, 2);
}

async function callGemini(model, candidates, signal) {
  const ai = new GoogleGenAI({ apiKey: config.geminiApiKey });
  const response = await ai.models.generateContent({
    model,
    contents: [{ role: "user", parts: [{ text: userMessage(candidates) }] }],
    config: {
      systemInstruction: VERIFIER_SYSTEM_PROMPT,
      temperature: 0,
      responseMimeType: "application/json",
      responseSchema: GEMINI_SCHEMA,
      abortSignal: signal,
      httpOptions: { timeout: TIMEOUT_MS, retryOptions: { attempts: 1 } },
    },
  });
  try {
    return JSON.parse(response.text ?? "");
  } catch {
    throw new JudgeError("bad_json", "judge returned text that is not JSON");
  }
}

async function callAnthropic(model, candidates, signal) {
  const client = new Anthropic({ apiKey: config.anthropicApiKey, maxRetries: 0, timeout: TIMEOUT_MS });
  const message = await client.messages.create(
    {
      model,
      max_tokens: 2048,
      temperature: 0,
      system: VERIFIER_SYSTEM_PROMPT,
      tools: [ANTHROPIC_TOOL],
      tool_choice: { type: "tool", name: ANTHROPIC_TOOL.name },
      messages: [{ role: "user", content: userMessage(candidates) }],
    },
    { signal, maxRetries: 0, timeout: TIMEOUT_MS },
  );
  const block = message?.content?.find((item) => item.type === "tool_use");
  if (!block) throw new JudgeError("bad_json", "judge returned no tool call");
  return block.input;
}

/**
 * A judge failure, already classified and safe to log: the message is
 * redacted and truncated, and nothing from the SDK error object is kept.
 *   verifierError: "timeout" | "429" | "invalid_model" | "unavailable" | "bad_json" | "other"
 */
export class JudgeError extends Error {
  constructor(verifierError, message, status = null) {
    super(redactSecrets(message).slice(0, MAX_ERROR_CHARS));
    this.name = "JudgeError";
    this.verifierError = verifierError;
    this.status = status;
    this.retried = false;
  }
}

export function classifyJudgeError(error) {
  if (error instanceof JudgeError) return error.verifierError;
  const status = typeof error?.status === "number" ? error.status : null;
  const message = String(error?.message ?? "");
  if (status === 429) return "429";
  if (status === 404 || (status === 400 && /\bmodel\b/i.test(message))) return "invalid_model";
  if (status !== null && status >= 500) return "unavailable";
  if (/^(AbortError|TimeoutError|APIConnectionTimeoutError)$/.test(error?.name ?? "") || /timed? ?out/i.test(message)) {
    return "timeout";
  }
  if (error instanceof SyntaxError) return "bad_json";
  return "other";
}

function toJudgeError(error) {
  if (error instanceof JudgeError) return error;
  const status = typeof error?.status === "number" ? error.status : null;
  return new JudgeError(classifyJudgeError(error), String(error?.message ?? "judge call failed"), status);
}

function pause(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new JudgeError("timeout", "judge timed out"));
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new JudgeError("timeout", "judge timed out"));
    }, { once: true });
  });
}

/**
 * sanitiseVerdicts(raw, candidates) -> [{ id, label, confidence, reason }]
 * Drops unknown ids, labels outside VERDICT_LABELS and repeats; clamps
 * confidence to 0..1. Candidates left without a verdict are the caller's to
 * treat as unrelated.
 */
export function sanitiseVerdicts(raw, candidates) {
  const ids = new Set(candidates.map((candidate) => candidate.id));
  const verdicts = new Map();
  for (const item of Array.isArray(raw?.results) ? raw.results : []) {
    if (!ids.has(item?.id) || verdicts.has(item.id) || !VERDICT_LABELS.includes(item?.label)) continue;
    const confidence = typeof item.confidence === "number" && Number.isFinite(item.confidence)
      ? Math.min(1, Math.max(0, item.confidence))
      : 0;
    const reason = typeof item.reason === "string" ? item.reason.slice(0, MAX_REASON_CHARS) : "";
    verdicts.set(item.id, { id: item.id, label: item.label, confidence, reason });
  }
  return [...verdicts.values()];
}

/**
 * verifyCandidates(candidates, settings = verifierSettings())
 *   -> { verdicts: [{ id, label, confidence, reason }], retried }
 * candidates: [{ id, queryType, identifier, domain, title, snippet }]; any
 * other field is stripped before sending. Throws a JudgeError (with
 * .verifierError and .retried) on failure. Retries once, 1 s later, only when
 * the provider is unavailable (5xx); the 30 s budget covers both attempts.
 */
export async function verifyCandidates(candidates, settings = verifierSettings()) {
  if (!settings.enabled) throw new JudgeError("other", "OSINT judge is not configured");
  const payload = candidates.map((candidate) =>
    Object.fromEntries(CANDIDATE_FIELDS.map((field) => [field, candidate[field] ?? ""])),
  );

  const controller = new AbortController();
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject(new JudgeError("timeout", `judge gave no answer within ${TIMEOUT_MS / 1000} s`));
    }, TIMEOUT_MS);
  });

  let retried = false;
  const call = () =>
    settings.provider === "gemini"
      ? callGemini(settings.model, payload, controller.signal)
      : callAnthropic(settings.model, payload, controller.signal);
  const attempt = async () => {
    try {
      return await call();
    } catch (error) {
      if (classifyJudgeError(error) !== "unavailable") throw error;
      retried = true;
      await pause(RETRY_DELAY_MS, controller.signal);
      return call();
    }
  };

  try {
    const raw = await Promise.race([attempt(), deadline]);
    if (!Array.isArray(raw?.results)) throw new JudgeError("bad_json", "judge output has no results array");
    return { verdicts: sanitiseVerdicts(raw, payload), retried };
  } catch (error) {
    const failure = toJudgeError(error);
    failure.retried = retried;
    throw failure;
  } finally {
    clearTimeout(timer);
  }
}
