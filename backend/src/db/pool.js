// Shared PostgreSQL connection pool.
import pg from "pg";
import { config } from "../config/index.js";
import { logger } from "../utils/logger.js";

// A down database must fail fast: the price check runs alongside the NLP call
// and an endless connect would hold the whole analysis.
export const pool = new pg.Pool({
  connectionString: config.databaseUrl,
  connectionTimeoutMillis: 3000,
});

// An idle client losing its connection emits "error" on the pool; unhandled,
// that would crash the process.
pool.on("error", (error) => {
  logger.warn(`postgres idle client error: ${error.message}`);
});

export const query = (text, params) => pool.query(text, params);
