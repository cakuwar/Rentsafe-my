// Price-anomaly module: the tier rule, every status, and how the result
// reaches the score. The database is mocked.
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockQuery } = vi.hoisted(() => ({ mockQuery: vi.fn() }));
vi.mock("../src/db/pool.js", () => ({ query: mockQuery, pool: {} }));

import {
  MIN_BUILDINGS,
  MIN_LISTINGS,
  isScorable,
  listBaselineStrata,
  scoreAgainstBaseline,
  scorePriceAnomaly,
} from "../src/services/price.service.js";
import { aggregateScore, capUnsupportedScore } from "../src/services/scoring.service.js";
import { propertyFields } from "../src/validation/property.schema.js";

const BASE = { median: 2000, p25: 1900 };

function row(overrides = {}) {
  return {
    median_price: "2000.00", p25_price: "1900.00", p75_price: "2300.00",
    sample_size: 12, building_count: 6, sources: "kaggle+scraped",
    adjustment_factor: "1.2000", source_vintages: { kaggle: "2023 (inferred)", scraped: "2026-08-27" },
    status: "scorable", ...overrides,
  };
}

beforeEach(() => {
  mockQuery.mockReset();
  mockQuery.mockResolvedValue({ rows: [row()] });
});

describe("scoreAgainstBaseline (D1: research doc §5.4.2, from 30% below the median)", () => {
  const noGuard = { p25Guard: false };

  it("puts each boundary in its tier", () => {
    const cases = [
      [1401, 0, "within_range"],       // 29.95% below
      [1400, 10, "suspicious"],        // exactly 30%
      [1399, 10, "suspicious"],        // just over 30%
      [1101, 10, "suspicious"],        // just under 45%
      [1100, 10, "suspicious"],        // exactly 45%
      [1099, 15, "highly_suspicious"], // just over 45%
      [2500, 0, "within_range"],       // above market
    ];
    for (const [price, points, tier] of cases) {
      expect(scoreAgainstBaseline(price, BASE, noGuard), String(price)).toMatchObject({ points, tier });
    }
  });

  it("has no 5-point tier: 15-29% below scores nothing", () => {
    for (const price of [1700, 1600, 1500]) expect(scoreAgainstBaseline(price, BASE, noGuard).points).toBe(0);
  });

  it("does not count a price that a quarter of real listings undercut (p25 guard, on)", () => {
    const wide = { median: 2000, p25: 1160 };
    expect(scoreAgainstBaseline(1200, wide, noGuard).points).toBe(10);
    expect(scoreAgainstBaseline(1200, wide)).toMatchObject({ points: 0, tier: "within_range", guard: "at_or_above_p25" });
    expect(scoreAgainstBaseline(1160, wide).guard).toBe("at_or_above_p25");
    expect(scoreAgainstBaseline(1159, wide)).toMatchObject({ points: 10, guard: null });
  });

  it("passes 20 validation cases: 10 anomalous, 10 within range (§7.1.1)", () => {
    const anomalous = [1400, 1350, 1300, 1250, 1200, 1100, 1050, 1000, 800, 600];
    const inRange = [1960, 1900, 2000, 2100, 2400, 3000, 1950, 1980, 1901, 1999];
    expect(anomalous.map((p) => scoreAgainstBaseline(p, BASE).points >= 10)).toEqual(Array(10).fill(true));
    expect(inRange.map((p) => scoreAgainstBaseline(p, BASE).points)).toEqual(Array(10).fill(0));
  });

  it("applies D4 eligibility", () => {
    expect(isScorable(MIN_LISTINGS, MIN_BUILDINGS)).toBe(true);
    expect(isScorable(MIN_LISTINGS - 1, 10)).toBe(false);
    expect(isScorable(40, MIN_BUILDINGS - 1)).toBe(false);
  });
});

describe("scorePriceAnomaly (form input only)", () => {
  const unit = { price: 1000, area: "Wangsa Maju", propertyType: "condo", bedrooms: 2 };

  it("scores a whole unit against its stratum and names the data age", async () => {
    const result = await scorePriceAnomaly(unit);
    expect(result).toMatchObject({ status: "ok", points: 15, max: 15, tier: "highly_suspicious" });
    expect(result.anomalyFraction).toBe(1);
    expect(result.baseline).toMatchObject({ median: 2000, sampleSize: 12, buildings: 6,
                                            sources: ["kaggle", "scraped"], adjustmentFactor: 1.2 });
    expect(result.message.en).toMatch(/^RM1,000 is 50% below the median of 12 comparable listings \(RM2,000\)\./);
    expect(result.message.en).toMatch(/Mudah asking prices from about 2023, scaled ×1\.20/);
    expect(result.message.en).toMatch(/iProperty \/ PropertyGuru asking prices from Aug 2026/);
    expect(result.message.ms).toMatch(/harga tawaran Mudah sekitar 2023/);
    expect(result).not.toHaveProperty("inputSource");
    expect(mockQuery.mock.calls[0][1]).toEqual(["Wangsa Maju", "condo", 2]);
  });

  it("says a price inside the range is within the normal range", async () => {
    for (const price of [1950, 2600]) {
      const result = await scorePriceAnomaly({ ...unit, price });
      expect(result).toMatchObject({ status: "ok", points: 0, anomalyFraction: 0 });
      expect(result.message.en).toMatch(/is within the normal range for 2-bedroom condos in Wangsa Maju/);
    }
  });

  it("does not mention Mudah when no Kaggle row is in the stratum", async () => {
    mockQuery.mockResolvedValue({ rows: [row({ sources: "scraped", adjustment_factor: null,
                                               source_vintages: { scraped: "2026-08-27" } })] });
    expect((await scorePriceAnomaly(unit)).message.en).not.toMatch(/Mudah/);
  });

  it("accepts a canonical area in any case, nothing else", async () => {
    await scorePriceAnomaly({ ...unit, area: " wangsa maju " });
    expect(mockQuery.mock.calls[0][1][0]).toBe("Wangsa Maju");
    expect((await scorePriceAnomaly({ ...unit, area: "PJ" })).status).toBe("unknown_area");
  });

  it("scores a room against the room baseline", async () => {
    const result = await scorePriceAnomaly(propertyFields.parse(
      { price: "400", area: "Setapak", propertyType: "room", roomType: "single" }));
    expect(result.status).toBe("ok");
    expect(result.stratum).toEqual({ area: "Setapak", propertyType: "room", roomType: "common" });
    expect(mockQuery.mock.calls[0][0]).toMatch(/room_price_baseline/);
  });

  it("reports what is missing, and leaves price out of the score", async () => {
    const cases = [
      [undefined, ["price", "area", "propertyType"]],
      [{}, ["price", "area", "propertyType"]],
      [{ area: "Setapak", propertyType: "condo", bedrooms: 2 }, ["price"]],
      [{ price: 1000, area: "Setapak", propertyType: "condo" }, ["bedrooms"]],
      [{ price: 1000, area: "Setapak", propertyType: "landed" }, ["bedrooms"]],
      [{ price: 600, area: "Setapak", propertyType: "room" }, ["roomType"]],
    ];
    for (const [form, missing] of cases) {
      const result = await scorePriceAnomaly(form);
      expect(result.status, JSON.stringify(form)).toBe("missing_input");
      expect(result.missing).toEqual(missing);
      expect(result.anomalyFraction).toBeNull();
    }
    expect((await scorePriceAnomaly({})).message.en)
      .toBe("Fill in rent, area and property type to compare with market prices.");
    expect(mockQuery).not.toHaveBeenCalled();
  });

  it("asks which Cheras for a two-state name", async () => {
    const result = await scorePriceAnomaly({ ...unit, area: "Cheras" });
    expect(result.status).toBe("unknown_area");
    expect(result.message.en).toBe("Choose which Cheras: Cheras (KL) or Cheras (Selangor).");
  });

  it("never queries for landed: there is no landed baseline", async () => {
    const result = await scorePriceAnomaly({ price: 2500, area: "Shah Alam", propertyType: "landed", bedrooms: 3 });
    expect(result.status).toBe("no_baseline");
    expect(result.message.en).toMatch(/^Landed property isn't covered yet/);
    expect(mockQuery).not.toHaveBeenCalled();
  });

  it("reports no_baseline when the stratum has no row", async () => {
    mockQuery.mockResolvedValue({ rows: [] });
    const result = await scorePriceAnomaly(unit);
    expect(result.status).toBe("no_baseline");
    expect(result.message.en).toBe("No price data yet for 2-bedroom condos in Wangsa Maju.");
  });

  it("shows but does not score a thin stratum (D4)", async () => {
    for (const thin of [{ sample_size: 4 }, { building_count: 2 }]) {
      mockQuery.mockResolvedValue({ rows: [row(thin)] });
      const result = await scorePriceAnomaly(unit);
      expect(result.status).toBe("thin_baseline");
      expect(result.baseline.median).toBe(2000);
      expect(result.points).toBeNull();
      expect(result.message.en).toMatch(/too few to score\. Their median is RM2,000\./);
    }
  });

  it("never throws when the database is down", async () => {
    mockQuery.mockRejectedValue(new Error("connect ECONNREFUSED"));
    const result = await scorePriceAnomaly(unit);
    expect(result.status).toBe("baseline_unavailable");
    expect(result.anomalyFraction).toBeNull();
  });
});

describe("minimum-rent floor (D10: a sanity rule, not a market comparison)", () => {
  const studio = (price, area = "Subang Jaya") =>
    propertyFields.parse({ price: String(price), area, propertyType: "studio" });
  const room = (price, roomType = "common") =>
    propertyFields.parse({ price: String(price), area: "Setapak", propertyType: "room", roomType });

  it("scores RM100 for a Subang Jaya studio although its stratum is too thin to compare", async () => {
    mockQuery.mockResolvedValue({ rows: [row({ sample_size: 2, building_count: 2, median_price: "1980.00" })] });
    expect((await scorePriceAnomaly(studio(1000))).status).toBe("thin_baseline");
    mockQuery.mockClear();

    const result = await scorePriceAnomaly(studio(100));
    expect(result).toMatchObject({
      status: "ok", points: 15, anomalyFraction: 1, tier: "highly_suspicious", guard: "below_floor",
      listedPrice: 100, deviation: null, baseline: null,
      stratum: { area: "Subang Jaya", propertyType: "condo", bedrooms: 0 },
    });
    expect(result.message).toEqual({
      en: "RM100/month is far below any real rent for this property type in Subang Jaya.",
      ms: "RM100/bulan jauh di bawah mana-mana sewa sebenar untuk jenis hartanah ini di Subang Jaya.",
    });
    expect(mockQuery).not.toHaveBeenCalled(); // applied before the baseline lookup
  });

  it("leaves RM310 for a common room to the market comparison", async () => {
    mockQuery.mockResolvedValue({ rows: [row({ sample_size: 1, building_count: 1 })] });
    const result = await scorePriceAnomaly(room(310));
    expect(result).toMatchObject({ status: "thin_baseline", points: null, guard: null });
    expect(mockQuery.mock.calls[0][0]).toMatch(/room_price_baseline/);
  });

  it("floors a whole unit below RM300, not at RM300", async () => {
    mockQuery.mockResolvedValue({ rows: [] });
    const unit = (price) => ({ price, area: "Shah Alam", propertyType: "condo", bedrooms: 2 });
    expect(await scorePriceAnomaly(unit(299))).toMatchObject({ status: "ok", points: 15, guard: "below_floor" });
    const almost = await scorePriceAnomaly(unit(299.5));
    expect(almost).toMatchObject({ points: 15, guard: "below_floor" });
    expect(almost.message.en).toMatch(/^RM299\.5\/month /); // never rounded up to the floor
    expect(await scorePriceAnomaly(unit(300))).toMatchObject({ status: "no_baseline", points: null, guard: null });
  });

  it("floors a room below RM150, not at RM150", async () => {
    mockQuery.mockResolvedValue({ rows: [] });
    expect(await scorePriceAnomaly(room(149))).toMatchObject({ status: "ok", points: 15, guard: "below_floor" });
    expect(await scorePriceAnomaly(room(149, "master"))).toMatchObject({ guard: "below_floor" });
    expect(await scorePriceAnomaly(room(150))).toMatchObject({ status: "no_baseline", points: null, guard: null });
  });

  it("is not applied outside our KL / Selangor coverage", async () => {
    for (const area of ["Seremban", "Johor Bahru", "Cheras"]) {
      const result = await scorePriceAnomaly(studio(100, area));
      expect(result.status, area).toBe("unknown_area");
      expect(result).toMatchObject({ points: null, guard: null });
    }
    expect(mockQuery).not.toHaveBeenCalled();
  });

  it("covers landed as a whole unit, though there is no landed baseline", async () => {
    const landed = (price) => ({ price, area: "Shah Alam", propertyType: "landed", bedrooms: 3 });
    expect(await scorePriceAnomaly(landed(250))).toMatchObject({ status: "ok", points: 15, guard: "below_floor" });
    expect((await scorePriceAnomaly(landed(2500))).status).toBe("no_baseline");
  });

  it("needs a complete form, and reports both floors in `rule`", async () => {
    expect((await scorePriceAnomaly({ price: 100, area: "Setapak", propertyType: "room" })).status)
      .toBe("missing_input");
    expect((await scorePriceAnomaly(studio(100))).rule.rentFloor).toEqual({ wholeUnit: 300, room: 150 });
  });
});

describe("price in the overall score", () => {
  const nlp = (p) => ({ scamProbability: p, status: "ok", confidence: "high" });

  it("adds the tier's points and counts toward maxPossible when included", async () => {
    const price = await scorePriceAnomaly({ price: 1400, area: "Wangsa Maju", propertyType: "condo", bedrooms: 2 });
    const scoring = aggregateScore({ nlp: nlp(0.2), price });
    expect(scoring.components.price).toEqual({ points: 10, max: 15, included: true });
    expect(scoring.maxPossible).toBe(75);
    expect(scoring.total).toBe(22);
  });

  it("is excluded when the form was not filled in", async () => {
    const price = await scorePriceAnomaly(undefined);
    const scoring = aggregateScore({ nlp: nlp(0.2), price });
    expect(scoring.excluded).toContain("price");
    expect(scoring.components.price).toEqual({ points: 0, max: 0, included: false });
    expect(scoring.maxPossible).toBe(60);
  });

  it("does not lift the no-red-flag cap on its own (D9)", async () => {
    const price = await scorePriceAnomaly({ price: 900, area: "Wangsa Maju", propertyType: "condo", bedrooms: 2 });
    const capped = capUnsupportedScore(aggregateScore({ nlp: nlp(0.95), price }), {
      scamProbability: 0.95, status: "ok", redFlags: [], osint: null,
    });
    expect(price.points).toBe(15);
    expect(capped.band).toBe("MODERATE");
    expect(capped.total).toBe(49);
  });

  it("counts the floor's 15 points, and the floor does not lift the cap either (D9)", async () => {
    const price = await scorePriceAnomaly({ price: 100, area: "Subang Jaya", propertyType: "condo", bedrooms: 0 });
    expect(aggregateScore({ nlp: nlp(0.2), price }).components.price).toEqual({ points: 15, max: 15, included: true });
    const capped = capUnsupportedScore(aggregateScore({ nlp: nlp(0.95), price }), {
      scamProbability: 0.95, status: "ok", redFlags: [], osint: null,
    });
    expect(capped.band).toBe("MODERATE");
  });
});

describe("listBaselineStrata (GET /api/price/areas)", () => {
  it("lists every canonical area, KL first, with its strata and a data note", async () => {
    mockQuery
      .mockResolvedValueOnce({ rows: [
        { area: "Kajang", property_type: "condo", bedrooms: 3, sample_size: 456, building_count: 48,
          sources: "kaggle", adjustment_factor: "1.2000", source_vintages: { kaggle: "2023 (inferred)" } },
        { area: "Setapak", property_type: "flat", bedrooms: 3, sample_size: 4, building_count: 2,
          sources: "scraped", adjustment_factor: null, source_vintages: { scraped: "2026-08-27" } },
      ] })
      .mockResolvedValueOnce({ rows: [{ area: "Setapak", room_type: "common", sample_size: 5, building_count: 1 }] });
    const { areas, dataNote } = await listBaselineStrata();
    expect(areas).toHaveLength(125);
    expect(areas[0]).toMatchObject({ name: "Ampang (KL)", state: "KL" });
    expect(areas.at(-1).state).toBe("Selangor");
    expect(areas.find((a) => a.name === "Cyberjaya").strata).toEqual([]);
    expect(areas.find((a) => a.name === "Setapak").strata).toEqual([
      { propertyType: "flat", bedrooms: 3, sampleSize: 4, buildings: 2, scorable: false },
      { propertyType: "room", roomType: "common", sampleSize: 5, buildings: 1, scorable: false },
    ]);
    expect(areas.find((a) => a.name === "Kajang").strata[0].scorable).toBe(true);
    expect(dataNote.en).toMatch(/Mudah asking prices from about 2023, scaled ×1\.20.*Aug 2026.*Landed property isn't covered yet/);
  });
});
