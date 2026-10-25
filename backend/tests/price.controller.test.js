// The "Listing details" form contract (property.schema.js) and the price
// routes, with fake req/res.
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockScore, mockList } = vi.hoisted(() => ({ mockScore: vi.fn(), mockList: vi.fn() }));
vi.mock("../src/services/price.service.js", () => ({
  scorePriceAnomaly: mockScore,
  listBaselineStrata: mockList,
}));

import { checkPrice, listAreas } from "../src/controllers/price.controller.js";
import { errorHandler } from "../src/middleware/errorHandler.js";
import { propertyFields } from "../src/validation/property.schema.js";

function fakeRes() {
  return {
    statusCode: 200,
    body: undefined,
    headersSent: false,
    status(code) { this.statusCode = code; return this; },
    json(body) { this.body = body; return this; },
  };
}

async function call(handler, query) {
  const res = fakeRes();
  let forwarded = null;
  await handler({ query }, res, (error) => { forwarded = error; });
  if (forwarded) errorHandler(forwarded, { method: "GET", originalUrl: "/api/price" }, res, () => {});
  return res;
}

beforeEach(() => {
  mockScore.mockReset();
  mockScore.mockResolvedValue({ status: "ok", points: 0 });
  mockList.mockReset();
});

describe("propertyFields — the form contract", () => {
  const parse = (form) => propertyFields.parse(form);

  it("reads the rent from a number or 'RM1,500' / '1,500' / 'RM 1 500'", () => {
    for (const price of [1500, "1500", "1,500", "RM1,500", "rm 1 500", " RM1,500 "]) {
      expect(parse({ price }).price, String(price)).toBe(1500);
    }
    for (const price of ["abc", "0", "-5", "100001", "1.5k"]) {
      expect(() => parse({ price }), price).toThrow();
    }
  });

  it("normalises studio to a 0-bedroom condo, ignoring any bedrooms sent", () => {
    expect(parse({ propertyType: "Studio", bedrooms: "3" })).toEqual({ propertyType: "condo", bedrooms: 0 });
    expect(parse({ propertyType: "studio" })).toEqual({ propertyType: "condo", bedrooms: 0 });
  });

  it("buckets bedrooms above 4 into 4, and reads '4+' as 4", () => {
    expect(parse({ propertyType: "condo", bedrooms: "7" }).bedrooms).toBe(4);
    expect(parse({ propertyType: "flat", bedrooms: "4+" }).bedrooms).toBe(4);
    expect(parse({ propertyType: "apartment", bedrooms: "0" }).bedrooms).toBe(0);
    for (const bedrooms of ["2.5", "21", "-1", "two"]) expect(() => parse({ bedrooms }), bedrooms).toThrow();
  });

  it("maps single and middle rooms to common, drops bedrooms for a room and roomType for a unit", () => {
    expect(parse({ propertyType: "room", roomType: "Single", bedrooms: "2" }))
      .toEqual({ propertyType: "room", roomType: "common" });
    expect(parse({ propertyType: "room", roomType: "middle" }).roomType).toBe("common");
    expect(parse({ propertyType: "room", roomType: "master" }).roomType).toBe("master");
    expect(parse({ propertyType: "condo", bedrooms: "2", roomType: "master" })).toEqual({ propertyType: "condo", bedrooms: 2 });
    expect(() => parse({ roomType: "penthouse" })).toThrow();
    expect(() => parse({ propertyType: "villa" })).toThrow();
  });

  it("treats every empty string as not given — multipart bedrooms '' is never 0", () => {
    expect(parse({ price: "", area: "", propertyType: "", bedrooms: "", roomType: "" })).toEqual({});
    expect(parse({ propertyType: "condo", bedrooms: "" })).toEqual({ propertyType: "condo" });
    expect(parse({})).toEqual({});
  });
});

describe("GET /api/price/check", () => {
  it("passes the normalised form through, with a disclaimer", async () => {
    const res = await call(checkPrice, { price: "RM1,200", area: "Kajang", propertyType: "Flat", bedrooms: "3" });
    expect(res.statusCode).toBe(200);
    expect(mockScore.mock.calls[0][0]).toEqual({ price: 1200, area: "Kajang", propertyType: "flat", bedrooms: 3 });
    expect(res.body.disclaimer.en).toMatch(/asking prices/);
  });

  it("answers an empty or partial form with the check's own status, not an error", async () => {
    mockScore.mockResolvedValue({ status: "missing_input", missing: ["price", "area", "propertyType"] });
    const res = await call(checkPrice, {});
    expect(res.statusCode).toBe(200);
    expect(mockScore.mock.calls[0][0]).toEqual({});
    expect(res.body.status).toBe("missing_input");
  });

  it("rejects a malformed value with 400", async () => {
    for (const query of [{ price: "abc" }, { bedrooms: "2.5" }, { propertyType: "villa" }, { roomType: "penthouse" }]) {
      expect((await call(checkPrice, query)).statusCode, JSON.stringify(query)).toBe(400);
    }
    expect(mockScore).not.toHaveBeenCalled();
  });

  it("answers 503 when the baseline cannot be read", async () => {
    mockScore.mockResolvedValue({ status: "baseline_unavailable" });
    const res = await call(checkPrice, { price: "1200", area: "Kajang", propertyType: "condo", bedrooms: "2" });
    expect(res.statusCode).toBe(503);
  });
});

describe("GET /api/price/areas", () => {
  it("returns the areas and data note, or 503 when the database is down", async () => {
    mockList.mockResolvedValue({ areas: [{ name: "Kajang", state: "Selangor", strata: [] }], dataNote: { en: "…", ms: "…" } });
    const ok = await call(listAreas, {});
    expect(ok.body.areas[0].name).toBe("Kajang");
    expect(ok.body.dataNote.en).toBeTruthy();
    mockList.mockRejectedValue(new Error("down"));
    expect((await call(listAreas, {})).statusCode).toBe(503);
  });
});
