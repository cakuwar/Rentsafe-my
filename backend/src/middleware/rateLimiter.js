// Protects the Serper/Anthropic budget by capping requests per IP.
import rateLimit from "express-rate-limit";

// Every route: 100 requests per IP per 15 minutes, enough for normal use
// while stopping one client from spending the paid search and LLM quota
// (osint.service.js adds daily search limits on top).
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
