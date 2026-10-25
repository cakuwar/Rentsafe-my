// Minimal logger. Swap for pino/winston later if needed.
// TODO: export a `logger` object with info/warn/error(message) methods,
// each printing a timestamped line to the appropriate console stream.
function write(method, message) {
	console[method](`[${new Date().toISOString()}] ${message}`);
}

export const logger = {
	info: (message) => write("log", message),
	warn: (message) => write("warn", message),
	error: (message) => write("error", message),
};
