// Leave-one-out false-positive check on the 18 cells filled by hand
// (data/raw/manual/manual_price_entry.xlsx; the cells are
// scripts/baseline/manual_workbook.py TARGETS), with the production scorer.
//
// Every listing in those cells (manual, scraped or Kaggle) is a real asking
// price, assumed legitimate. Three views, all with scoreAgainstBaseline:
//
//   loo         the production rule: hold the listing out, rebuild its cell
//               from the others, apply D4 (>= 5 listings, >= 3 buildings)
//               AFTER the removal, score the held-out price. A cell at the
//               minimum (5 listings) is ineligible once one is removed, so its
//               listings are "not scored" here — by the rule, not by choice.
//   loo_no_d4   the same without the eligibility rule: how each listing fares
//               against the other four. A sensitivity view only; production
//               never scores a 4-listing cell.
//   in_sample   each listing's price against its whole cell, as seeded: what
//               /api/price/check answers today for that exact price.
//
// Each view is scored with the p25 guard on (production) and off; a listing
// the guard "saved" gets points without it and 0 with it. Also reported: how
// far removing one listing moves its cell's median (flagged above 15%).
//
//   node scripts/price_loo_manual_cells.js -> data/processed/price_loo_manual_cells.json
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { isScorable, scoreAgainstBaseline } from "../src/services/price.service.js";
import { parseCsv } from "./csv.js";
import { buildingKey, quantile } from "./strata.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const LISTINGS = path.join(ROOT, "data/processed/baseline_listings.csv");
const OUT = path.join(ROOT, "data/processed/price_loo_manual_cells.json");
const MEDIAN_SHIFT_FLAG = 0.15;

const SEVEN = ["Setapak", "Cheras (KL)", "Seri Kembangan", "Puchong (Selangor)", "Shah Alam",
  "Petaling Jaya", "Subang Jaya"];
const STUDIOS = ["Setapak", "Cheras (KL)", "Puchong (Selangor)", "Subang Jaya"];
const CELLS = [
  ...SEVEN.map((area) => ({ label: `${area} | common room`, key: `room|${area}|common` })),
  ...STUDIOS.map((area) => ({ label: `${area} | studio`, key: `unit|${area}|condo|0` })),
  ...SEVEN.map((area) => ({ label: `${area} | master room`, key: `room|${area}|master` })),
];

function stratumKey(r) {
  return r.property_type === "room"
    ? `room|${r.area}|${r.room_type}`
    : `unit|${r.area}|${r.property_type}|${r.bedrooms}`;
}

function baselineOf(rows) {
  const prices = rows.map((r) => r.price).sort((a, b) => a - b);
  return { median: quantile(prices, 0.5), p25: quantile(prices, 0.25) };
}

function score(price, baseline) {
  const on = scoreAgainstBaseline(price, baseline, { p25Guard: true });
  const off = scoreAgainstBaseline(price, baseline, { p25Guard: false });
  return { points: on.points, deviation: on.deviation, guardSaved: off.points > 0 && on.points === 0 };
}

function tally(results) {
  const scored = results.filter((r) => r !== null);
  return {
    scored: scored.length,
    points10: scored.filter((r) => r.points === 10).length,
    points15: scored.filter((r) => r.points === 15).length,
    flagged: scored.filter((r) => r.points >= 10).length,
    guardSaved: scored.filter((r) => r.guardSaved).length,
    rate: scored.length ? Math.round((scored.filter((r) => r.points >= 10).length / scored.length) * 1000) / 1000 : null,
  };
}

function run() {
  const all = parseCsv(fs.readFileSync(LISTINGS, "utf8"))
    .map((r) => ({ ...r, price: Number(r.price_adjusted), bkey: buildingKey(r.building) }));

  const cells = [];
  const listings = [];
  for (const cell of CELLS) {
    const members = all.filter((r) => stratumKey(r) === cell.key);
    const full = baselineOf(members);
    let maxShift = 0;
    for (let i = 0; i < members.length; i += 1) {
      const held = members[i];
      const others = members.filter((_, j) => j !== i);
      const buildings = new Set(others.map((o) => o.bkey).filter(Boolean)).size;
      const without = baselineOf(others);
      const shift = Math.abs(without.median - full.median) / full.median;
      maxShift = Math.max(maxShift, shift);
      listings.push({
        cell: cell.label, building: held.building, source: held.source, price: held.price,
        median_without: without.median, p25_without: without.p25, median_shift: Math.round(shift * 1000) / 1000,
        loo: isScorable(others.length, buildings) ? score(held.price, without) : null,
        loo_no_d4: score(held.price, without),
        in_sample: score(held.price, full),
      });
    }
    const buildings = new Set(members.map((m) => m.bkey).filter(Boolean)).size;
    cells.push({
      cell: cell.label, listings: members.length, buildings, median: full.median, p25: full.p25,
      max_median_shift: Math.round(maxShift * 1000) / 1000, fragile_median: maxShift > MEDIAN_SHIFT_FLAG,
    });
  }

  const flaggedIn = (view) => listings
    .filter((l) => l[view] && l[view].points >= 10)
    .map((l) => ({ cell: l.cell, building: l.building, source: l.source, price: l.price, points: l[view].points,
                   deviation: l[view].deviation, median: view === "in_sample" ? undefined : l.median_without }));
  const savedIn = (view) => listings.filter((l) => l[view]?.guardSaved)
    .map((l) => ({ cell: l.cell, building: l.building, price: l.price }));

  const report = {
    generated_at: new Date().toISOString(),
    cells: CELLS.map((c) => c.label),
    definitions: {
      loo: "held out, cell rebuilt from the others, D4 applied after removal (production rule)",
      loo_no_d4: "held out and scored against the others even when they are below D4 (sensitivity only)",
      in_sample: "scored against the whole seeded cell (what the API answers for that price today)",
      flagged: "10 or 15 points with the p25 guard on",
      guard_saved: "points with the guard off, 0 with it on",
      median_shift: "|median without the listing - cell median| / cell median",
    },
    summary: Object.fromEntries(["loo", "loo_no_d4", "in_sample"].map((v) => [v, {
      listings: listings.length, ...tally(listings.map((l) => l[v])),
      by_kind: Object.fromEntries(["room", "studio"].map((kind) => [kind, tally(listings
        .filter((l) => (kind === "studio") === l.cell.endsWith("studio")).map((l) => l[v]))])),
    }])),
    flagged: { loo: flaggedIn("loo"), loo_no_d4: flaggedIn("loo_no_d4"), in_sample: flaggedIn("in_sample") },
    guard_saved: { loo: savedIn("loo"), loo_no_d4: savedIn("loo_no_d4"), in_sample: savedIn("in_sample") },
    fragile_medians: cells.filter((c) => c.fragile_median),
    by_cell: cells,
    listings,
  };
  fs.writeFileSync(OUT, JSON.stringify(report, null, 2));

  for (const [view, s] of Object.entries(report.summary)) {
    console.log(`${view.padEnd(10)} scored ${String(s.scored).padStart(2)} of ${s.listings}  flagged ${s.flagged} `
      + `(10 pts: ${s.points10}, 15 pts: ${s.points15})  guard saved ${s.guardSaved}`);
  }
  for (const view of ["loo", "loo_no_d4", "in_sample"]) {
    for (const f of report.flagged[view]) {
      console.log(`  ${view}: ${f.cell} — ${f.building} RM${f.price} -> ${f.points} pts (${Math.round(f.deviation * 100)}% below)`);
    }
    for (const g of report.guard_saved[view]) console.log(`  ${view}: guard saved ${g.cell} — ${g.building} RM${g.price}`);
  }
  console.log("cells whose median moves > 15% when one listing is removed:");
  for (const c of report.fragile_medians) console.log(`  ${c.cell}: up to ${Math.round(c.max_median_shift * 100)}%`);
  console.log(`wrote ${OUT}`);
}

run();
