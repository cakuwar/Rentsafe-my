import { ZodError } from "zod";
import { logger } from "../utils/logger.js";

/**
 * Centralised error handler. Must have 4 args (err, req, res, next) for
 * Express to recognise it as an error-handling middleware.
 *
 * Every path must end in a response. While this was a stub that returned
 * without sending anything, a single validation failure left the connection
 * open until the client gave up — the request never appeared to finish.
 */
export function errorHandler(err, req, res, next) { // eslint-disable-line no-unused-vars
  if (res.headersSent) {
    return;
  }

  if (err instanceof ZodError) {
    return res.status(400).json({
      error: "Validation failed",
      details: err.errors.map((issue) => ({
        field: issue.path.join("."),
        message: issue.message,
      })),
    });
  }

  // Multer rejects oversized or too-numerous uploads with a code, not a status.
  if (err?.code === "LIMIT_FILE_SIZE") {
    return res.status(413).json({ error: "Screenshot too large (max 5MB)." });
  }
  if (err?.code === "LIMIT_FILE_COUNT" || err?.code === "LIMIT_UNEXPECTED_FILE") {
    return res.status(413).json({ error: "Too many screenshots (max 20)." });
  }

  // The NLP service being down should read as a dependency failure, not as a
  // bug in this service.
  if (err?.code === "ECONNREFUSED" || err?.code === "ECONNABORTED") {
    logger.error(`NLP service unreachable: ${err.message}`);
    return res.status(503).json({
      error: "Analysis service unavailable",
      message: "The NLP service is not responding. Try again shortly.",
    });
  }

  const status = err?.status ?? err?.statusCode ?? 500;
  if (status >= 500) {
    logger.error(`${req.method} ${req.originalUrl} -> ${err?.stack ?? err}`);
  }

  res.status(status).json({
    error: status >= 500 ? "Internal server error" : (err?.message ?? "Request failed"),
    ...(status < 500 && err?.message ? { message: err.message } : {}),
  });
}
