// Leave-one-out false-positive check of the price rule on the baseline's own
// listings, with the production scorer (scoreAgainstBaseline), in the spirit
// of scripts/apply_band_cap.js.
//
// Every pooled listing (data/processed/baseline_listings.csv) is an asking
// price on a listing portal, assumed legitimate. Each one is held out, its
// stratum rebuilt from the others, the D4 eligibility rule (>= 5 listings,
// >= 3 buildings) applied AFTER the removal, and the held-out price scored as
// if a renter had entered it. A listing that gets points is a false positive.
//
//   flagged       > 0 points
//   flagged >= 10 10 or 15 points (the "suspicious" tiers)
//   FP rate       flagged / listings scored (ineligible strata are not scored)
//
// Reported with and without the p25 guard, under the production tiers (from
// 30% below the median, D1). The run that chose 30% over §5.4.3's 15% start —
// all four variants — is kept in data/processed/price_loo_eval_threshold_choice.json.
// Prices are price_adjusted (Kaggle rows x the time factor), as the baseline
// medians are. Landed is never scored.
//
//   node scripts/price_loo_eval.js   -> data/processed/price_loo_eval.json
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { isScorable, scoreAgainstBaseline } from "../src/services/price.service.js";
import { parseCsv } from "./csv.js";
import { buildingKey, quantile } from "./strata.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const LISTINGS = path.join(ROOT, "data/processed/baseline_listings.csv");
const OUT = path.join(ROOT, "data/processed/price_loo_eval.json");

const VARIANTS = [
  { name: "start30_guard", p25Guard: true },
  { name: "start30_noguard", p25Guard: false },
];

function emptyTally() {
  return { scored: 0, flagged: 0, flagged10: 0, tiers: { 10: 0, 15: 0 }, guarded: 0 };
}

function rate(n, d) {
  return d ? Math.round((n / d) * 10000) / 10000 : null;
}

function run() {
  const listings = parseCsv(fs.readFileSync(LISTINGS, "utf8"))
    .map((r) => ({ ...r, price: Number(r.price_adjusted), bkey: buildingKey(r.building) }))
    .filter((r) => r.property_type !== "landed" && Number.isFinite(r.price));

  const groups = new Map();
  for (const r of listings) {
    const key = r.property_type === "room"
      ? `room|${r.area}|${r.room_type}`
      : `unit|${r.area}|${r.property_type}|${r.bedrooms}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }

  const kinds = ["whole_units", "rooms"];
  const totals = Object.fromEntries(kinds.map((k) => [k, {
    listings: 0, not_scored: 0,
    variants: Object.fromEntries(VARIANTS.map((v) => [v.name, emptyTally()])),
  }]));
  const byType = {};
  const bySource = {};
  const examples = [];

  for (const [key, members] of groups) {
    const kind = key.startsWith("room|") ? "rooms" : "whole_units";
    for (let i = 0; i < members.length; i += 1) {
      const held = members[i];
      const others = members.filter((_, j) => j !== i);
      const buildings = new Set(others.map((o) => o.bkey).filter(Boolean)).size;
      totals[kind].listings += 1;
      if (!isScorable(others.length, buildings)) {
        totals[kind].not_scored += 1;
        continue;
      }
      const prices = others.map((o) => o.price).sort((a, b) => a - b);
      const baseline = { median: quantile(prices, 0.5), p25: quantile(prices, 0.25) };
      for (const variant of VARIANTS) {
        const scored = scoreAgainstBaseline(held.price, baseline, variant);
        for (const tally of [
          totals[kind].variants[variant.name],
          ((byType[held.property_type] ??= {})[variant.name] ??= emptyTally()),
          ((bySource[held.source] ??= {})[variant.name] ??= emptyTally()),
        ]) {
          tally.scored += 1;
          if (scored.guard) tally.guarded += 1;
          if (scored.points > 0) {
            tally.flagged += 1;
            tally.tiers[scored.points] += 1;
            if (scored.points >= 10) tally.flagged10 += 1;
          }
        }
        if (variant.name === "start30_guard" && scored.points >= 10 && examples.length < 25) {
          examples.push({ stratum: key.split("|").slice(1).join(" "), building: held.building,
                          source: held.source, price: held.price, median: baseline.median,
                          p25: baseline.p25, points: scored.points, deviation: scored.deviation });
        }
      }
    }
  }

  const withRates = (tally) => ({
    ...tally,
    fp_rate_gt0: rate(tally.flagged, tally.scored),
    fp_rate_ge10: rate(tally.flagged10, tally.scored),
  });
  const mapRates = (obj) => Object.fromEntries(Object.entries(obj).map(([k, v]) =>
    [k, Object.fromEntries(Object.entries(v).map(([n, t]) => [n, withRates(t)]))]));

  const report = {
    generated_at: new Date().toISOString(),
    method: "leave-one-out over data/processed/baseline_listings.csv; D4 eligibility applied after "
      + "removing the held-out listing; production scoreAgainstBaseline; price_adjusted",
    definitions: {
      flagged: "the held-out listing receives > 0 points",
      flagged10: "the held-out listing receives >= 10 points",
      fp_rate_gt0: "flagged / scored",
      fp_rate_ge10: "flagged10 / scored",
      scored: "held-out listings whose stratum is still eligible (>= 5 listings, >= 3 buildings) without them",
    },
    variants: VARIANTS,
    whole_units: { listings: totals.whole_units.listings, not_scored: totals.whole_units.not_scored,
                   variants: Object.fromEntries(Object.entries(totals.whole_units.variants).map(([n, t]) => [n, withRates(t)])) },
    rooms: { listings: totals.rooms.listings, not_scored: totals.rooms.not_scored,
             variants: Object.fromEntries(Object.entries(totals.rooms.variants).map(([n, t]) => [n, withRates(t)])) },
    by_property_type: mapRates(byType),
    by_source: mapRates(bySource),
    examples_start30_guard_ge10: examples,
  };
  fs.writeFileSync(OUT, JSON.stringify(report, null, 2));

  console.log(`whole units: ${report.whole_units.listings} listings, ${report.whole_units.not_scored} not scored`);
  for (const [name, t] of Object.entries(report.whole_units.variants)) {
    console.log(`  ${name.padEnd(16)} scored ${t.scored}  flagged>0 ${t.flagged} (${(t.fp_rate_gt0 * 100).toFixed(1)}%)  `
      + `>=10 ${t.flagged10} (${(t.fp_rate_ge10 * 100).toFixed(1)}%)  tiers 10/15 ${t.tiers[10]}/${t.tiers[15]}`);
  }
  console.log(`rooms: ${report.rooms.listings} listings, ${report.rooms.not_scored} not scored`);
  console.log(`wrote ${OUT}`);
}

run();
