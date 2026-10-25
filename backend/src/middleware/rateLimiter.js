// Protects the Serper/Anthropic budget by capping requests per IP.
import rateLimit from "express-rate-limit";

// TODO: configure and export `rateLimiter` using express-rate-limit.
// Pick a window + max requests that makes sense given Serper's free-tier
// monthly search cap (see osint.service.js) — you don't want one user's
// testing to burn your whole month's quota.
export const rateLimiter = rateLimit({
	windowMs: 15 * 60 * 1000,
	limit: 100,
	standardHeaders: "draft-7",
	legacyHeaders: false,
});

// The public lookup spends up to four paid searches per request, and anyone
// can call it, so it gets its own much tighter limit on top of the global one.
export const searchRateLimiter = rateLimit({
	windowMs: 15 * 60 * 1000,
	limit: 10,
	standardHeaders: "draft-7",
	legacyHeaders: false,
	message: { error: "Too many searches. Try again in a few minutes." },
});
