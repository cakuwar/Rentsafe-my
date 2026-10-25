import { config } from "../config/index.js";

// Whether an API key from .env is a real one or the template's placeholder
// ("your_serper_dev_key"). Real Serper, SerpApi, Gemini and Anthropic keys are
// all well over 32 characters.
export function isRealKey(key) {
  if (typeof key !== "string") return false;
  const trimmed = key.trim();
  return trimmed.length >= 32 && !/^(your|change)|xxx|placeholder/i.test(trimmed);
}

// Key shapes that may turn up in an SDK error message even when the value is
// not the configured one: Google "AIza…" and "AQ.…", Anthropic "sk-ant-…".
const KEY_SHAPES = [
  /AIza[0-9A-Za-z_-]{20,}/g,
  /AQ\.[0-9A-Za-z_.-]{20,}/g,
  /sk-ant-[0-9A-Za-z_-]{10,}/g,
];

/** Strip api_key=..., every configured key, and anything shaped like a key. */
export function redactSecrets(text) {
  let out = String(text ?? "").replace(/(api_key=)[^&\s"']+/gi, "$1[redacted]");
  const keys = [config.serperApiKey, config.serpapiApiKey, config.geminiApiKey, config.anthropicApiKey];
  for (const key of keys) {
    if (typeof key === "string" && key.trim().length >= 8) out = out.split(key.trim()).join("[redacted]");
  }
  for (const shape of KEY_SHAPES) out = out.replace(shape, "[redacted]");
  return out;
}
