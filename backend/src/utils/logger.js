// Minimal logger: one timestamped line per message, info to stdout and
// warn / error to stderr. Messages that could carry a secret or a phone
// number are redacted or masked by the caller (utils/keys.js, maskPhone).
function write(method, message) {
	console[method](`[${new Date().toISOString()}] ${message}`);
}

export const logger = {
	info: (message) => write("log", message),
	warn: (message) => write("warn", message),
	error: (message) => write("error", message),
};
