// Central config, read once from the environment (backend/.env; every
// variable is listed in backend/.env.example). Local-dev defaults where one
// makes sense; secrets stay undefined when unset.
//
// SCORE_WEIGHTS: how much each signal can add to the 0-100 score. The NLP
// classifier reads the conversation itself, so it carries the most; OSINT
// needs public complaints to exist, and a low price alone is weak evidence.
// RISK_BANDS: the score ranges behind LOW / MODERATE / HIGH / CRITICAL; a
// score on a boundary goes to the higher band (docs/API_SPEC.md, and the ROC
// check in docs/MODEL_EVALUATION.md §4.10).

// An empty `KEY=` line in .env must fall back to the default, not become 0 —
// a daily search limit of 0 would silently disable OSINT.
function intFromEnv(name, fallback) {
  const value = Number.parseInt(process.env[name] ?? "", 10);
  return Number.isFinite(value) && value >= 0 ? value : fallback;
}

// true / false, or null when unset — "decide from what is configured".
function boolFromEnv(name) {
  const value = (process.env[name] ?? "").trim().toLowerCase();
  if (["true", "1", "yes"].includes(value)) return true;
  if (["false", "0", "no"].includes(value)) return false;
  return null;
}

export const config = {
  nodeEnv: process.env.NODE_ENV ?? "development",
  port: Number(process.env.PORT ?? 4000),
  databaseUrl: process.env.DATABASE_URL,
  redisUrl: process.env.REDIS_URL,
  nlpServiceUrl: process.env.NLP_SERVICE_URL ?? "http://localhost:8000",
  // Web search: Serper.dev is primary (2,500 free queries, one-time), SerpApi
  // the fallback (250 free a month). Daily limits keep a busy day from
  // spending the whole allowance; see osint.service.js.
  serperApiKey: process.env.SERPER_API_KEY,
  serperDailyLimit: intFromEnv("SERPER_DAILY_LIMIT", 80),
  serpapiApiKey: process.env.SERPAPI_API_KEY,
  serpapiDailyLimit: intFromEnv("SERPAPI_DAILY_LIMIT", 8),
  // HMAC secret for OSINT cache keys, so a cache key cannot be reversed into
  // the phone number it was built from.
  osintCacheSecret: process.env.OSINT_CACHE_SECRET,
  // LLM judge for OSINT evidence (services/llmVerifier.js). On by default
  // when the selected provider's key is set; OSINT_LLM_VERIFY=false turns it
  // off. GEMINI_MODEL has no default on purpose: copy the current Flash-Lite
  // model ID from Google AI Studio rather than trust a guessed one.
  llmVerifierProvider: (process.env.LLM_VERIFIER_PROVIDER ?? "").trim().toLowerCase() || "gemini",
  osintLlmVerify: boolFromEnv("OSINT_LLM_VERIFY"),
  // Result narrative (services/llm.service.js). Same provider and model as the
  // judge unless NARRATIVE_PROVIDER names another (gemini, anthropic or
  // openai); LLM_NARRATIVE=false turns
  // it off, and the frontend then builds the explanation from the result.
  narrativeProvider: (process.env.NARRATIVE_PROVIDER ?? "").trim().toLowerCase() || null,
  llmNarrative: boolFromEnv("LLM_NARRATIVE"),
  geminiApiKey: process.env.GEMINI_API_KEY,
  geminiModel: process.env.GEMINI_MODEL?.trim() || undefined,
  anthropicApiKey: process.env.ANTHROPIC_API_KEY,
  anthropicModel: process.env.ANTHROPIC_MODEL,
  // OpenAI, for the narrative only (NARRATIVE_PROVIDER=openai); the OSINT
  // judge never uses it. OPENAI_MODEL has no default on purpose: copy a
  // non-reasoning model ID from platform.openai.com/docs/models.
  openaiApiKey: process.env.OPENAI_API_KEY,
  openaiModel: process.env.OPENAI_MODEL?.trim() || undefined,
  frontendOrigin: process.env.FRONTEND_ORIGIN ?? "http://localhost:5173",
};

export const SCORE_WEIGHTS = {
  nlp: 60,
  osint: 25,
  price: 15,
};

export const RISK_BANDS = [
  { band: "LOW", min: 0, max: 24, colour: "green" },
  { band: "MODERATE", min: 25, max: 49, colour: "yellow" },
  { band: "HIGH", min: 50, max: 74, colour: "orange" },
  { band: "CRITICAL", min: 75, max: 100, colour: "red" },
];
