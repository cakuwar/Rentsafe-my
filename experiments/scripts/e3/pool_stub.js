// EXPERIMENT STUB (not the project's pool.js). The real file opens a
// PostgreSQL pool. The offline leave-one-out evaluation never needs the
// database, so any attempt to query it fails loudly instead of connecting.
const refuse = () => { throw new Error("database disabled in the experiment copy"); };
export const pool = { query: refuse, connect: refuse, end: async () => {} };
export const query = refuse;
