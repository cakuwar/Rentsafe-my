// Price-anomaly module (P5).
// Compares the rent the renter typed into the "Listing details" form with the
// stratified KL/Selangor baseline built by scripts/baseline (area + property
// type + bedrooms, or area + room type for a room) — never a city-wide
// average: rents vary up to 280% between districts (Razali et al., 2021). A
// rent far below its stratum is a classic "too good to be true" scam signal;
// it is a corroborating signal, worth at most 15.
//
// DECISION (author, 2026-10-15) — D8, form only. The rent and the property
// come ONLY from the form (`property` on /analyze, multipart fields on
// /analyze/screenshot). Nothing is parsed from the chat: a deposit, a booking
// fee or a negotiated figure read as the rent would score a listing on a
// number its landlord never asked for.
import { SCORE_WEIGHTS } from "../config/index.js";
import { CANONICAL_AREAS } from "../config/areas.js";
import { query } from "../db/pool.js";
import { canonicalArea, dualStateOptions } from "./metadata.service.js";
import { logger } from "../utils/logger.js";

// ---------------------------------------------------------------------------
// DECISION (author, 2026-10-15) — D1, tiers: research doc §5.4.2's decision
// rule (anomalous below 70% of the stratum), graded by §5.4.3, on the stratum
// MEDIAN (D2: not the mean — the strata have heavy outliers). With
// d = (median - price) / median:
//   d < 30%            -> 0  within_range
//   30% <= d <= 45%    -> 10 suspicious
//   d > 45%            -> 15 highly_suspicious
//   above market       -> 0
// Chosen over §5.4.3's 15% start (a 5-point tier) on the leave-one-out run over
// 12,550 legitimate portal listings (data/processed/
// price_loo_eval_threshold_choice.json): false-positive rate at > 0 points /
// >= 10 points was 21.3% / 8.5% at 15% with the p25 guard, 25.8% / 8.8%
// without it; 8.5% / 8.5% at 30% with the guard, 8.8% / 8.8% without. The
// 5-point tier added ~13 points of false positives and no >= 10-point catch.
// Boundaries are compared by cross-multiplication, never float division.
//
// DECISION (author, 2026-10-15) — D3, p25 guard (kept): a price at or above
// the stratum's 25th percentile scores 0 — a quarter of the real listings are
// that cheap.
// ---------------------------------------------------------------------------
export const THRESHOLD_PCT = 30;
export const HIGH_THRESHOLD_PCT = 45;
export const P25_GUARD = true;

// D4 — a stratum is scored only with this many listings from this many
// distinct buildings, so one development cannot set a district's price
// (Pavilion Damansara Heights was 13 of 18 "Damansara 1BR" scraped rows).
export const MIN_LISTINGS = 5;
export const MIN_BUILDINGS = 3;

// ---------------------------------------------------------------------------
// DECISION (author, 2026-10-19) — D10, minimum-rent floor: a sanity rule, not a
// market comparison. A monthly rent below the floor is below any real rent for
// the type in KL / Selangor, so it scores the top tier (15, highly_suspicious,
// guard "below_floor") before any baseline lookup — even where the stratum is
// thin or missing, as it is for most studios and every room: RM100 for a
// Subang Jaya studio (a 2-listing stratum) scored nothing. Applied only to a
// canonical area (our coverage) and a complete form.
//   wholeUnit: whole units, studios and landed — the RM300 the baseline
//              cleaning already uses to drop per-day prices
//              (scripts/baseline/cleaning.py), so no baseline listing is below it
//   room:      the cheapest room in the baseline is RM600
// Like any price signal it never lifts the no-red-flag cap (D9).
// ---------------------------------------------------------------------------
export const RENT_FLOOR = Object.freeze({ wholeUnit: 300, room: 150 });

const MAX_POINTS = SCORE_WEIGHTS.price;
const NEEDS_BEDROOMS = new Set(["condo", "apartment", "flat", "landed"]);

/**
 * scoreAgainstBaseline(price, { median, p25 }, { p25Guard }) -> { points, tier, deviation, guard }
 * Pure: shared by scorePriceAnomaly and backend/scripts/price_loo_eval.js
 * (which turns the guard off to measure it).
 */
export function scoreAgainstBaseline(price, baseline, { p25Guard = P25_GUARD } = {}) {
  const median = Number(baseline.median);
  const p25 = baseline.p25 === null || baseline.p25 === undefined ? null : Number(baseline.p25);
  const below = median - price;
  const deviation = Math.round((below / median) * 10000) / 10000;

  let points = 0;
  let tier = "within_range";
  if (below * 100 > HIGH_THRESHOLD_PCT * median) [points, tier] = [15, "highly_suspicious"];
  else if (below * 100 >= THRESHOLD_PCT * median) [points, tier] = [10, "suspicious"];

  if (points > 0 && p25Guard && p25 !== null && price >= p25) {
    return { points: 0, tier: "within_range", deviation, guard: "at_or_above_p25" };
  }
  return { points, tier, deviation, guard: null };
}

/** D4 eligibility, from the stratum's own counts. */
export function isScorable(sampleSize, buildings) {
  return sampleSize >= MIN_LISTINGS && buildings >= MIN_BUILDINGS;
}

// ---------------------------------------------------------------------------
// Messages (the result screen shows these)
// ---------------------------------------------------------------------------

const rm = (value) => `RM${Math.round(Number(value)).toLocaleString("en-MY")}`;
const MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_MS = ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogos", "Sep", "Okt", "Nov", "Dis"];

function monthYear(iso, months) {
  const match = /^(\d{4})-(\d{2})/.exec(iso ?? "");
  return match ? `${months[Number(match[2]) - 1]} ${match[1]}` : iso;
}

/** dataNote(sources, vintages, factor) -> { en, ms }: where the prices come from and how old they are. */
export function dataNote(sources, vintages = {}, factor = null) {
  const scale = factor ? Number(factor).toFixed(2) : null;
  const year = String(vintages.kaggle ?? "2023").replace(" (inferred)", "");
  const en = [];
  const ms = [];
  for (const source of sources) {
    if (source === "kaggle") {
      en.push(`Mudah asking prices from about ${year}${scale ? `, scaled ×${scale} to current prices` : ""}`);
      ms.push(`harga tawaran Mudah sekitar ${year}${scale ? `, diselaraskan ×${scale} ke harga semasa` : ""}`);
    } else if (source === "scraped") {
      en.push(`iProperty / PropertyGuru asking prices from ${monthYear(vintages.scraped, MONTHS_EN)}`);
      ms.push(`harga tawaran iProperty / PropertyGuru ${monthYear(vintages.scraped, MONTHS_MS)}`);
    } else if (source === "manual") {
      en.push(`listings recorded by hand${vintages.manual ? ` (${monthYear(vintages.manual, MONTHS_EN)})` : ""}`);
      ms.push(`iklan yang direkod secara manual${vintages.manual ? ` (${monthYear(vintages.manual, MONTHS_MS)})` : ""}`);
    }
  }
  return {
    en: `Based on ${en.join("; ")}. Asking prices, not agreed rents.`,
    ms: `Berdasarkan ${ms.join("; ")}. Harga tawaran, bukan sewa sebenar.`,
  };
}

function stratumLabel(stratum) {
  if (stratum.propertyType === "room") {
    return {
      en: `${stratum.roomType} rooms in ${stratum.area}`,
      ms: `bilik ${stratum.roomType === "master" ? "master" : "biasa"} di ${stratum.area}`,
    };
  }
  const beds = stratum.bedrooms === 0 ? "studio" : `${stratum.bedrooms}${stratum.bedrooms === 4 ? "+" : ""}-bedroom`;
  const bilik = stratum.bedrooms === 0 ? "studio" : `${stratum.bedrooms}${stratum.bedrooms === 4 ? "+" : ""} bilik`;
  return { en: `${beds} ${stratum.propertyType}s in ${stratum.area}`, ms: `${stratum.propertyType} ${bilik} di ${stratum.area}` };
}

function join(message, note) {
  return note ? { en: `${message.en} ${note.en}`, ms: `${message.ms} ${note.ms}` } : message;
}

function baselineNote(baseline) {
  return dataNote(baseline.sources, baseline.vintages, baseline.adjustmentFactor);
}

function okMessage({ listedPrice, deviation, points, baseline, stratum }) {
  const n = baseline.sampleSize;
  const median = rm(baseline.median);
  if (points > 0) {
    const pct = Math.round(deviation * 100);
    return join({
      en: `${rm(listedPrice)} is ${pct}% below the median of ${n} comparable listings (${median}).`,
      ms: `${rm(listedPrice)} ialah ${pct}% di bawah median ${n} iklan setanding (${median}).`,
    }, baselineNote(baseline));
  }
  const label = stratumLabel(stratum);
  return join({
    en: `${rm(listedPrice)} is within the normal range for ${label.en} (median ${median} across ${n} comparable listings).`,
    ms: `${rm(listedPrice)} berada dalam julat biasa untuk ${label.ms} (median ${median} daripada ${n} iklan setanding).`,
  }, baselineNote(baseline));
}

const MISSING_DETAIL = {
  bedrooms: { en: "Add the number of bedrooms to compare with market prices.",
              ms: "Masukkan bilangan bilik tidur untuk dibandingkan dengan harga pasaran." },
  roomType: { en: "Add the room type (master or common) to compare with market prices.",
              ms: "Masukkan jenis bilik (master atau biasa) untuk dibandingkan dengan harga pasaran." },
};

function missingMessage(missing) {
  if (missing.some((f) => ["price", "area", "propertyType"].includes(f))) {
    return {
      en: "Fill in rent, area and property type to compare with market prices.",
      ms: "Isikan sewa, kawasan dan jenis hartanah untuk dibandingkan dengan harga pasaran.",
    };
  }
  return MISSING_DETAIL[missing[0]];
}

function unknownAreaMessage(area) {
  const options = dualStateOptions(area);
  if (options) {
    return {
      en: `Choose which ${area}: ${options.join(" or ")}.`,
      ms: `Pilih ${area} yang mana: ${options.join(" atau ")}.`,
    };
  }
  return {
    en: `"${area}" isn't an area in the price data. Pick one from the list.`,
    ms: `"${area}" bukan kawasan dalam data harga. Pilih daripada senarai.`,
  };
}

// Exact, not rounded: RM299.50 is under the RM300 floor and must not read "RM300".
const rmExact = (value) => `RM${Number(value).toLocaleString("en-MY", { maximumFractionDigits: 2 })}`;

function floorMessage(price, area) {
  return {
    en: `${rmExact(price)}/month is far below any real rent for this property type in ${area}.`,
    ms: `${rmExact(price)}/bulan jauh di bawah mana-mana sewa sebenar untuk jenis hartanah ini di ${area}.`,
  };
}

const LANDED_MESSAGE = {
  en: "Landed property isn't covered yet: the price data has almost no landed listings.",
  ms: "Hartanah landed belum diliputi: data harga hampir tiada iklan rumah landed.",
};

const UNAVAILABLE_MESSAGE = {
  en: "The price check is unavailable right now.",
  ms: "Semakan harga tidak tersedia buat masa ini.",
};

function noBaselineMessage(stratum) {
  const label = stratumLabel(stratum);
  return { en: `No price data yet for ${label.en}.`, ms: `Belum ada data harga untuk ${label.ms}.` };
}

function thinMessage(stratum, baseline) {
  const label = stratumLabel(stratum);
  return join({
    en: `Only ${baseline.sampleSize} comparable listings from ${baseline.buildings} building(s) for ${label.en}`
      + ` — too few to score. Their median is ${rm(baseline.median)}.`,
    ms: `Hanya ${baseline.sampleSize} iklan setanding daripada ${baseline.buildings} bangunan untuk ${label.ms}`
      + ` — terlalu sedikit untuk dinilai. Median mereka ${rm(baseline.median)}.`,
  }, baselineNote(baseline));
}

// ---------------------------------------------------------------------------
// Lookup
// ---------------------------------------------------------------------------

function toBaseline(row) {
  return {
    median: Number(row.median_price),
    p25: row.p25_price === null ? null : Number(row.p25_price),
    p75: row.p75_price === null ? null : Number(row.p75_price),
    sampleSize: Number(row.sample_size),
    buildings: Number(row.building_count ?? 0),
    sources: (row.sources ?? "").split("+").filter(Boolean),
    adjustmentFactor: row.adjustment_factor === null ? null : Number(row.adjustment_factor),
    vintages: row.source_vintages ?? {},
    status: row.status ?? null,
  };
}

const COLUMNS = `median_price, p25_price, p75_price, sample_size, building_count, sources,
                 adjustment_factor, source_vintages, status`;

async function lookup(stratum) {
  const { rows } = stratum.propertyType === "room"
    ? await query(`SELECT ${COLUMNS} FROM room_price_baseline WHERE area = $1 AND room_type = $2 LIMIT 1`,
      [stratum.area, stratum.roomType])
    : await query(
      `SELECT ${COLUMNS} FROM price_baseline WHERE area = $1 AND property_type = $2 AND bedrooms = $3 LIMIT 1`,
      [stratum.area, stratum.propertyType, stratum.bedrooms],
    );
  return rows[0] ? toBaseline(rows[0]) : null;
}

function result(status, fields) {
  return {
    status,
    anomalyFraction: null,
    points: null,
    max: MAX_POINTS,
    tier: null,
    deviation: null,
    guard: null,
    listedPrice: null,
    stratum: null,
    baseline: null,
    missing: [],
    rule: { thresholdPct: THRESHOLD_PCT, highThresholdPct: HIGH_THRESHOLD_PCT, p25Guard: P25_GUARD,
            minListings: MIN_LISTINGS, minBuildings: MIN_BUILDINGS, rentFloor: RENT_FLOOR },
    message: null,
    ...fields,
  };
}

/**
 * scorePriceAnomaly(property) -> evidence.price
 *
 * `property` is the form, as validation/property.schema.js normalises it:
 * { price, area, propertyType, bedrooms, roomType }, any of them absent (or
 * the whole object). Never throws. Anything but status "ok" has
 * anomalyFraction and points null, so the signal is EXCLUDED from the score
 * (excludedSignals gains "price"), never counted as a clean 0. "ok" with 0
 * points means the price was compared and is within range. "ok" with guard
 * "below_floor" is the D10 floor: 15 points, no baseline consulted.
 *
 *   missing_input        a field the stratum needs was not filled in (`missing`)
 *   unknown_area         not a canonical area, or a two-state name without its state
 *   no_baseline          no stratum for it — including every landed input
 *   thin_baseline        a stratum below D4 eligibility; comparison shown, not scored
 *   baseline_unavailable the database could not be read
 */
export async function scorePriceAnomaly(property) {
  const form = property ?? {};
  const price = Number(form.price);
  const { propertyType = null, roomType = null } = form;
  const bedrooms = form.bedrooms === undefined || form.bedrooms === null ? null : Math.min(4, Number(form.bedrooms));

  const missing = [];
  if (!(price > 0)) missing.push("price");
  if (!form.area) missing.push("area");
  if (!propertyType) missing.push("propertyType");
  if (NEEDS_BEDROOMS.has(propertyType) && bedrooms === null) missing.push("bedrooms");
  if (propertyType === "room" && !roomType) missing.push("roomType");
  if (missing.length) {
    return result("missing_input", { missing, message: missingMessage(missing) });
  }

  const area = canonicalArea(String(form.area));
  if (!area) {
    return result("unknown_area", { listedPrice: price, message: unknownAreaMessage(String(form.area).trim()) });
  }

  const stratum = propertyType === "room" ? { area, propertyType, roomType } : { area, propertyType, bedrooms };

  // D10: below any real rent for the type — scored before, and without, the baseline.
  const floor = propertyType === "room" ? RENT_FLOOR.room : RENT_FLOOR.wholeUnit;
  if (price < floor) {
    return result("ok", {
      anomalyFraction: 15 / MAX_POINTS,
      points: 15,
      tier: "highly_suspicious",
      guard: "below_floor",
      listedPrice: price,
      stratum,
      message: floorMessage(price, area),
    });
  }

  // Landed: the sources hold 6 landed listings in all KL / Selangor, so there
  // is no landed baseline to compare with (accepted as a gap, 2026-10-15).
  if (propertyType === "landed") {
    return result("no_baseline", { listedPrice: price, stratum, message: LANDED_MESSAGE });
  }

  let baseline;
  try {
    baseline = await lookup(stratum);
  } catch (error) {
    logger?.warn?.(`price baseline lookup failed: ${error.message}`);
    return result("baseline_unavailable", { listedPrice: price, stratum, message: UNAVAILABLE_MESSAGE });
  }

  if (!baseline) {
    return result("no_baseline", { listedPrice: price, stratum, message: noBaselineMessage(stratum) });
  }
  if (!isScorable(baseline.sampleSize, baseline.buildings)) {
    return result("thin_baseline", { listedPrice: price, stratum, baseline, message: thinMessage(stratum, baseline) });
  }

  const scored = scoreAgainstBaseline(price, baseline);
  const ok = result("ok", {
    anomalyFraction: scored.points / MAX_POINTS,
    points: scored.points,
    tier: scored.tier,
    deviation: scored.deviation,
    guard: scored.guard,
    listedPrice: price,
    stratum,
    baseline,
  });
  ok.message = okMessage(ok);
  return ok;
}

// ---------------------------------------------------------------------------
// GET /api/price/areas
// ---------------------------------------------------------------------------

const STATE_LABEL = { "Kuala Lumpur": "KL", Selangor: "Selangor" };

/**
 * listBaselineStrata() -> { areas: [{ name, state, strata }], dataNote }
 *
 * Every canonical area is listed, sorted by state then name, even with no
 * strata — the renter can still pick it and be told no_baseline /
 * thin_baseline. A stratum is { propertyType, bedrooms | roomType, sampleSize,
 * buildings, scorable }. Throws on a database error (the route answers 503).
 */
export async function listBaselineStrata() {
  const [units, rooms] = await Promise.all([
    query(`SELECT area, property_type, bedrooms, sample_size, building_count, sources,
                  adjustment_factor, source_vintages
             FROM price_baseline ORDER BY area, property_type, bedrooms`),
    query(`SELECT area, room_type, sample_size, building_count
             FROM room_price_baseline ORDER BY area, room_type`),
  ]);

  const byArea = new Map(Object.entries(CANONICAL_AREAS).map(([name, state]) => [
    name, { name, state: STATE_LABEL[state] ?? state, strata: [] },
  ]));
  const vintages = {};
  let factor = null;
  for (const row of units.rows) {
    byArea.get(row.area)?.strata.push({
      propertyType: row.property_type, bedrooms: row.bedrooms, sampleSize: row.sample_size,
      buildings: row.building_count, scorable: isScorable(row.sample_size, row.building_count ?? 0),
    });
    for (const [source, vintage] of Object.entries(row.source_vintages ?? {})) {
      if (vintage && (!vintages[source] || vintage > vintages[source])) vintages[source] = vintage;
    }
    if (row.adjustment_factor !== null && row.adjustment_factor !== undefined) factor = Number(row.adjustment_factor);
  }
  for (const row of rooms.rows) {
    byArea.get(row.area)?.strata.push({
      propertyType: "room", roomType: row.room_type, sampleSize: row.sample_size,
      buildings: row.building_count, scorable: isScorable(row.sample_size, row.building_count ?? 0),
    });
  }

  const areas = [...byArea.values()].sort((a, b) => a.state.localeCompare(b.state) || a.name.localeCompare(b.name));
  const note = dataNote(Object.keys(vintages).sort(), vintages, factor);
  return {
    areas,
    dataNote: {
      en: `${note.en} Landed property isn't covered yet.`,
      ms: `${note.ms} Hartanah landed belum diliputi.`,
    },
  };
}
