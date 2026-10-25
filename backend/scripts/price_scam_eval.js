// Price check on labelled cases: does it flag scams more than legit lettings
// when a renter fills in the form?
//
// data/eval/price_form_cases.csv: one row per case, holding what a renter would
// type into the "Listing details" form (blank where the source does not say).
//   case_id  PFC-S.. / PFC-L..  a real labelled chat (scam / legit)
//            PFC-N..            a news / police-reported scam (label scam,
//                               source_url required)
// Each row goes through the same validation (validation/property.schema.js) and
// scorePriceAnomaly as a request, against the seeded baseline. Results are
// reported for chat cases, news cases and both combined, each by label.
//
// Every case gets one outcome. Coverage is judged before completeness: a case
// in an area or of a type the baseline does not cover could never be scored,
// whatever else is filled in, so it is "outside coverage", not a failure.
//   scored               status ok (flagged10: >= 10 points; flagged15: 15)
//   outside_coverage     area not one of ours (Seremban, Kedah, ...), landed,
//                        or no stratum for it
//   insufficient_data    a stratum exists but is below D4 (thin_baseline)
//   input_incomplete     missing_input, a two-state area without its state
//                        ("Cheras"), or a value the form would reject (400)
//   unavailable          the baseline could not be read
//
// Rows whose notes start with "draft" are unverified; the script refuses to run
// while any remain (--allow-draft for a dry run only).
//
//   node backend/scripts/price_scam_eval.js   (from the repo root, or
//   node scripts/price_scam_eval.js from backend/) [--input path] [--output path] [--allow-draft]
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import dotenv from "dotenv";
import { parseCsv } from "./csv.js";
import { canonicalArea, dualStateOptions } from "../src/services/metadata.service.js";

const BACKEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = path.resolve(BACKEND, "..");

// backend/.env holds DATABASE_URL. Loaded by path, not from the working
// directory: run from the repo root, "dotenv/config" would read the root .env
// (docker-compose settings, no DATABASE_URL) and every case would come back
// baseline_unavailable.
dotenv.config({ path: path.join(BACKEND, ".env") });

export const COLUMNS = ["case_id", "label", "source_conversation", "source_url", "price", "area",
                        "property_type", "bedrooms", "room_type", "notes"];
const KIND_LABEL = { S: "scam", L: "legit", N: "scam" };

/** caseKind("PFC-N01") -> "news"; S / L -> "chat"; anything else -> null. */
export function caseKind(caseId) {
  const prefix = /^(?:PFC-)?([SLN])\d/i.exec(caseId ?? "")?.[1]?.toUpperCase();
  return prefix ? (prefix === "N" ? "news" : "chat") : null;
}

/** validateRows(rows) -> a list of problems (empty when the file is usable). */
export function validateRows(rows) {
  const problems = [];
  if (rows.length) {
    const absent = COLUMNS.filter((c) => !(c in rows[0]));
    if (absent.length) problems.push(`missing columns: ${absent.join(", ")}`);
  }
  for (const r of rows) {
    const prefix = /^(?:PFC-)?([SLN])\d/i.exec(r.case_id ?? "")?.[1]?.toUpperCase();
    if (!prefix) {
      problems.push(`${r.case_id || "(blank)"}: case_id must be PFC-S.., PFC-L.. or PFC-N..`);
      continue;
    }
    if (r.label !== KIND_LABEL[prefix]) {
      problems.push(`${r.case_id}: a ${prefix} case must be labelled ${KIND_LABEL[prefix]}, not "${r.label}"`);
    }
    if (prefix === "N" && !(r.source_url ?? "").trim()) {
      problems.push(`${r.case_id}: a news case needs its source_url`);
    }
  }
  const seen = new Set();
  for (const r of rows) {
    if (seen.has(r.case_id)) problems.push(`${r.case_id}: duplicate case_id`);
    seen.add(r.case_id);
  }
  return problems;
}

/**
 * outcome(result, row) -> { outcome, detail }, with coverage judged first
 * (see the header). `result` is scorePriceAnomaly's output, or
 * { status: "invalid_input" } when validation rejected the form.
 */
export function outcome(result, row) {
  const area = (row.area ?? "").trim();
  const type = (row.property_type ?? "").trim().toLowerCase();
  if (area && !canonicalArea(area) && !dualStateOptions(area)) {
    return { outcome: "outside_coverage", detail: "area_not_covered" };
  }
  if (type === "landed") return { outcome: "outside_coverage", detail: "landed" };

  switch (result.status) {
    case "ok": return { outcome: "scored", detail: null };
    case "no_baseline": return { outcome: "outside_coverage", detail: "no_stratum" };
    case "thin_baseline": return { outcome: "insufficient_data", detail: "thin_baseline" };
    case "unknown_area": return { outcome: "input_incomplete", detail: "ambiguous_area" };
    case "missing_input": return { outcome: "input_incomplete", detail: "missing_input" };
    case "invalid_input": return { outcome: "input_incomplete", detail: "invalid_input" };
    default: return { outcome: "unavailable", detail: result.status };
  }
}

function emptyTally() {
  return {
    cases: 0, scored: 0, flagged10: 0, flagged15: 0,
    outside_coverage: { total: 0, area_not_covered: 0, landed: 0, no_stratum: 0 },
    insufficient_data: 0,
    input_incomplete: { total: 0, missing_input: 0, ambiguous_area: 0, invalid_input: 0 },
    unavailable: 0,
  };
}

function add(tally, c) {
  tally.cases += 1;
  if (c.outcome === "scored") {
    tally.scored += 1;
    if (c.points >= 10) tally.flagged10 += 1;
    if (c.points === 15) tally.flagged15 += 1;
  } else if (c.outcome === "outside_coverage" || c.outcome === "input_incomplete") {
    tally[c.outcome].total += 1;
    tally[c.outcome][c.detail] += 1;
  } else {
    tally[c.outcome] += 1;
  }
}

/** summarise(cases) -> { chat, news, combined }, each { scam, legit, all } tallies. */
export function summarise(cases) {
  const groups = { chat: {}, news: {}, combined: {} };
  for (const c of cases) {
    for (const group of [c.kind, "combined"]) {
      for (const label of [c.label, "all"]) add((groups[group][label] ??= emptyTally()), c);
    }
  }
  return groups;
}

async function run() {
  const arg = (name, fallback) => {
    const i = process.argv.indexOf(name);
    return i > 0 && process.argv[i + 1] ? path.resolve(process.argv[i + 1]) : fallback;
  };
  const input = arg("--input", path.join(ROOT, "data/eval/price_form_cases.csv"));
  const output = arg("--output", path.join(ROOT, "data/processed/price_scam_eval.json"));

  const rows = parseCsv(fs.readFileSync(input, "utf8"));
  const problems = validateRows(rows);
  if (problems.length) {
    console.error(`${path.basename(input)} is not usable:\n  ${problems.join("\n  ")}`);
    process.exit(1);
  }
  const drafts = rows.filter((r) => /^\s*draft\b/i.test(r.notes ?? ""));
  if (drafts.length && !process.argv.includes("--allow-draft")) {
    console.error(`${drafts.length} of ${rows.length} rows are still marked draft `
      + `(${drafts.map((r) => r.case_id).join(", ")}).\nVerify each against its source and `
      + "remove \"draft\" from its notes before reporting numbers.");
    process.exit(2);
  }

  const { propertyFields } = await import("../src/validation/property.schema.js");
  const { scorePriceAnomaly } = await import("../src/services/price.service.js");
  const { pool } = await import("../src/db/pool.js");

  const cases = [];
  for (const r of rows) {
    const form = { price: r.price, area: r.area, propertyType: r.property_type,
                   bedrooms: r.bedrooms, roomType: r.room_type };
    let result;
    try {
      result = await scorePriceAnomaly(propertyFields.parse(form));
    } catch (error) {
      result = { status: "invalid_input", points: null,
                 message: { en: error.issues?.map((i) => i.message).join("; ") ?? error.message } };
    }
    cases.push({
      case_id: r.case_id, kind: caseKind(r.case_id), label: r.label,
      source_conversation: r.source_conversation || null, source_url: r.source_url || null,
      form, status: result.status, ...outcome(result, r),
      points: result.points ?? null, tier: result.tier ?? null, missing: result.missing ?? [],
      stratum: result.stratum ?? null, median: result.baseline?.median ?? null,
      message: result.message?.en ?? null, draft: /^\s*draft\b/i.test(r.notes ?? ""),
    });
  }
  await pool.end();

  const report = {
    generated_at: new Date().toISOString(),
    input: path.relative(ROOT, input).replace(/\\/g, "/"),
    drafts_included: drafts.length,
    definitions: {
      groups: "chat = PFC-S / PFC-L (real labelled chats); news = PFC-N (news / police-reported scams); combined = both",
      scored: "status ok; flagged10 = points >= 10; flagged15 = points 15",
      outside_coverage: "area not in the baseline (judged first), landed, or no stratum — not a failure",
      insufficient_data: "stratum below D4 eligibility (thin_baseline)",
      input_incomplete: "missing_input, a two-state area without its state, or a value the form would reject",
      unavailable: "the baseline could not be read",
    },
    by_group: summarise(cases),
    cases,
  };
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, JSON.stringify(report, null, 2));

  for (const [group, labels] of Object.entries(report.by_group)) {
    for (const [label, t] of Object.entries(labels)) {
      if (label === "all") continue;
      console.log(`${group.padEnd(8)} ${label.padEnd(5)} ${t.cases} cases: scored ${t.scored} `
        + `(>=10: ${t.flagged10}, 15: ${t.flagged15}), outside coverage ${t.outside_coverage.total}, `
        + `insufficient data ${t.insufficient_data}, input incomplete ${t.input_incomplete.total}`);
    }
  }
  console.log(`wrote ${output}${drafts.length ? ` (includes ${drafts.length} unverified draft rows)` : ""}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  run().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
