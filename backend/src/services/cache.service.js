// Redis cache helper (Serper results, LLM narratives).
//
// Best-effort throughout: the cache saves search credits, it is never
// load-bearing. A Redis that is down or slow costs a call at most
// CALL_TIMEOUT_MS and reads as a miss — it never throws.
import Redis from "ioredis";
import { config } from "../config/index.js";
import { logger } from "../utils/logger.js";

const CALL_TIMEOUT_MS = 1000;

export const redis = config.redisUrl
  ? new Redis(config.redisUrl, {
      lazyConnect: true,
      maxRetriesPerRequest: 1,
      connectTimeout: 2000,
    })
  : null;

// ioredis keeps reconnecting in the background and emits an error per attempt.
// One warning per outage is enough; it re-arms once the connection is back.
let outage = false;
redis?.on("error", (error) => {
  if (outage) return;
  outage = true;
  logger.warn(
    `Redis unavailable, continuing without cache: ${error.message || error.code || "connection failed"}`,
  );
});
redis?.on("ready", () => {
  outage = false;
});

// During a known outage, skip Redis outright instead of waiting out the
// timeout on every call — a search makes three cache calls.
function unavailable() {
  return !redis || (outage && redis.status !== "ready");
}

function withTimeout(promise) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error("redis call timed out")), CALL_TIMEOUT_MS);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

/**
 * cacheGet(key) -> parsed value, or null on miss/error (cache is best-effort).
 */
export async function cacheGet(key) {
  if (unavailable()) return null;
  try {
    const value = await withTimeout(redis.get(key));
    return value ? JSON.parse(value) : null;
  } catch {
    return null;
  }
}

/**
 * cacheSet(key, value, ttlSeconds = 3600) -> void. Swallow errors.
 */
export async function cacheSet(key, value, ttlSeconds = 3600) {
  if (unavailable()) return;
  try {
    await withTimeout(redis.set(key, JSON.stringify(value), "EX", ttlSeconds));
  } catch {
    // best-effort
  }
}

/**
 * counterIncrBy(key, by, ttlSeconds) -> the counter's new value, or null when
 * Redis is unavailable (the caller decides what to fall back to). The TTL is
 * set when this call created the key.
 */
export async function counterIncrBy(key, by, ttlSeconds) {
  if (unavailable()) return null;
  try {
    const value = await withTimeout(redis.incrby(key, by));
    if (value === by) await withTimeout(redis.expire(key, ttlSeconds));
    return value;
  } catch {
    return null;
  }
}
