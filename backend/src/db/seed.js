// Loads seed SQL (price and room baselines, red-flag lexicon, scraped listings)
// into the DB, in filename order. Each baseline seed is its own transaction.
// Usage: npm run seed
import "dotenv/config";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { pool } from "./pool.js";

const SEEDS_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../database/seeds");

async function run() {
  const files = fs.readdirSync(SEEDS_DIR).filter((f) => f.endsWith(".sql")).sort();
  for (const file of files) {
    console.log(`Seeding ${file}...`);
    await pool.query(fs.readFileSync(path.join(SEEDS_DIR, file), "utf8"));
  }
  console.log(`Seeding complete (${files.length}).`);
}

run()
  .then(() => pool.end())
  .catch(async (error) => {
    console.error(error);
    await pool.end();
    process.exit(1);
  });
