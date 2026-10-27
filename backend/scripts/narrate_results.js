// Adds the narrative to analysis results saved before it existed (blind-test
// cases run while generateNarrative was a stub). Only `narrative` is written:
// score, band and evidence stay exactly as recorded, and nothing is re-run, so
// a fresh OSINT search or model call cannot change a recorded result.
//
//   node scripts/narrate_results.js <api_result.json>...            (from backend/)
//   node scripts/narrate_results.js --dry-run <api_result.json>...  print, write nothing
//   node scripts/narrate_results.js --force <api_result.json>...    replace an existing narrative
//
// A backfilled narrative carries `backfilled: true`, so it can be told apart
// from one the API wrote at analysis time.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import dotenv from "dotenv";

const BACKEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// Loaded by path and before config/index.js is imported: config reads the
// environment once, when it is first imported.
dotenv.config({ path: path.join(BACKEND, ".env") });
const { generateNarrative, narrativeSettings } = await import("../src/services/llm.service.js");
const { redis } = await import("../src/services/cache.service.js");

const flags = new Set(process.argv.slice(2).filter((arg) => arg.startsWith("--")));
const files = process.argv.slice(2).filter((arg) => !arg.startsWith("--"));

async function run() {
  const settings = narrativeSettings();
  if (!settings.enabled) throw new Error("narrative is off: check GEMINI_API_KEY / GEMINI_MODEL in backend/.env");
  if (files.length === 0) throw new Error("give one or more api_result.json files");

  let failed = 0;
  for (const file of files) {
    const raw = fs.readFileSync(file, "utf8");
    const result = JSON.parse(raw);
    const name = path.basename(path.dirname(path.resolve(file)));
    if (result.narrative && !flags.has("--force")) {
      console.log(`${name}: already has a narrative, skipped (--force to replace)`);
      continue;
    }

    const narrative = await generateNarrative({ ...result, narrative: null }, settings);
    if (!narrative) {
      failed += 1;
      console.log(`${name}: no narrative (see the warning above); file unchanged`);
      continue;
    }
    console.log(`${name}: ${result.riskBand} ${result.riskScore}/${result.maxPossibleScore}\n  en: ${narrative.en}\n  ms: ${narrative.ms}`);
    if (flags.has("--dry-run")) continue;

    // Same layout as the file had: the API writes compact JSON.
    const updated = { ...result, narrative: { ...narrative, backfilled: true } };
    fs.writeFileSync(file, raw.includes("\n  ") ? JSON.stringify(updated, null, 2) : JSON.stringify(updated));
  }
  return failed;
}

run()
  .then((failed) => {
    redis?.disconnect();
    process.exit(failed ? 1 : 0);
  })
  .catch((error) => {
    console.error(error.message);
    redis?.disconnect();
    process.exit(1);
  });
