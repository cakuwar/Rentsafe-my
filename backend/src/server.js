// Entry point: boots the HTTP server.
import "dotenv/config";
import app from "./app.js";
import { config } from "./config/index.js";
import { logger } from "./utils/logger.js";

const server = app.listen(config.port, () => {
	logger.info(`RentSafe backend listening on http://localhost:${config.port}`);
});

function shutdown(signal) {
	logger.info(`${signal} received; shutting down`);
	server.close(() => process.exit(0));
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
