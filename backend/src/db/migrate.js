// Runs SQL migration files in database/migrations in order.
// Usage: npm run migrate
import "dotenv/config";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { pool } from "./pool.js";

const MIGRATIONS_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../database/migrations",
);

async function run() {
  const files = fs.readdirSync(MIGRATIONS_DIR).filter((f) => f.endsWith(".sql")).sort();
  for (const file of files) {
    console.log(`Applying ${file}...`);
    await pool.query(fs.readFileSync(path.join(MIGRATIONS_DIR, file), "utf8"));
  }
  console.log(`Migrations complete (${files.length}).`);
}

run()
  .then(() => pool.end())
  .catch(async (error) => {
    console.error(error);
    await pool.end();
    process.exit(1);
  });
