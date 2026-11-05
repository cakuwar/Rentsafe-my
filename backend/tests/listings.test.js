// Saving and reading analysis results (listings.repo.js, GET /api/listings/:id).
// The database is mocked at pool.query; what matters is what reaches it.
import { describe, it, expect, vi, beforeEach } from "vitest";

const h = vi.hoisted(() => ({ query: vi.fn() }));
vi.mock("../src/db/pool.js", () => ({ query: h.query, pool: {} }));

import { insertListing, getListingById } from "../src/db/listings.repo.js";
import { getListing } from "../src/controllers/listing.controller.js";
import { logger } from "../src/utils/logger.js";

const ID = "0b6f3f0e-3a5c-4c55-9a43-7a0f2d5c1e11";

// A finished result with personal data wherever the pipeline puts some: the
// chat, the agent's name and phone, search snippets, red-flag snippets.
const RESULT = {
  listingId: ID,
  sourceType: "screenshot",
  riskScore: 64,
  maxPossibleScore: 85,
  riskBand: "HIGH",
  components: { nlp: { points: 59, max: 60, included: true }, osint: { points: 5, max: 25, included: true } },
  nlpStatus: "ok",
  nlpConfidence: "high",
  evidenceSupport: "supported",
  narrative: { en: "High risk.", ms: "Risiko tinggi.", provider: "openai", model: "gpt-4o-mini", promptVersion: "v4" },
  metadata: { phone: "0123456789", agentName: "Encik Marker" },
  ocrText: "Owner: CHAT-MARKER bayar dulu",
  evidence: {
    redFlags: ["pay_before_viewing"],
    details: [{ id: "pay_before_viewing", severity: "critical", label_en: "Payment before viewing", snippet: "CHAT-MARKER bayar dulu" }],
    patterns: [],
    legitSignals: [],
    osint: {
      status: "ok",
      points: 5,
      identity: { phone: "0123456789", name: "Encik Marker" },
      evidence: [{ domain: "facebook.com", tier: "social", foundBy: "phone", label: "complaint", snippet: "SNIPPET-MARKER 0123456789 penipu" }],
      context: [],
    },
    price: null,
  },
};

const PROPERTY = { price: 450, area: "Cyberjaya", propertyType: "room", roomType: "common" };

const ROW = {
  listing_id: ID,
  created_at: new Date("2026-11-05T08:00:00Z"),
  source_type: "screenshot",
  price: "450.00",
  area: "Cyberjaya",
  bedrooms: null,
  property_type: "room",
  risk_score: 64,
  risk_band: "HIGH",
  component_scores: RESULT.components,
  facts: { band: "HIGH", score: 64 },
  narrative: RESULT.narrative,
};

function fakeRes() {
  return {
    statusCode: 200,
    body: undefined,
    status(code) {
      this.statusCode = code;
      return this;
    },
    json(body) {
      this.body = body;
      return this;
    },
  };
}

async function get(id) {
  const res = fakeRes();
  await getListing({ params: { id } }, res);
  return res;
}

beforeEach(() => {
  h.query.mockReset().mockResolvedValue({ rows: [ROW] });
  vi.spyOn(logger, "warn").mockImplementation(() => {});
});

describe("insertListing", () => {
  it("stores the result, never the chat or the agent's identifiers", async () => {
    await insertListing(RESULT, PROPERTY);
    const [sql, params] = h.query.mock.calls[0];

    const stored = JSON.stringify(params);
    for (const personal of ["0123456789", "Encik Marker", "CHAT-MARKER", "SNIPPET-MARKER"]) {
      expect(stored).not.toContain(personal);
    }
    expect(sql).not.toMatch(/raw_text|agent_name|agent_phone|ren_number|company_name/);
  });

  it("is parameterised, with the score, band, facts, narrative and form fields", async () => {
    await insertListing(RESULT, PROPERTY);
    const [sql, params] = h.query.mock.calls[0];

    expect(sql).toMatch(/VALUES \(\$1, \$2, \$3, \$4, \$5, \$6, \$7, \$8, \$9, \$10, \$11\)/);
    expect(params.slice(0, 8)).toEqual([ID, "screenshot", 450, "Cyberjaya", null, "room", 64, "HIGH"]);
    expect(JSON.parse(params[8])).toEqual(RESULT.components);
    expect(JSON.parse(params[9])).toMatchObject({ band: "HIGH", score: 64, osint: { reports: [{ domain: "facebook.com" }] } });
    expect(JSON.parse(params[10])).toEqual(RESULT.narrative);
  });

  it("stores an UNKNOWN result with no score, no narrative and no form", async () => {
    await insertListing({ ...RESULT, riskScore: null, riskBand: "UNKNOWN", narrative: null, components: null });
    const [, params] = h.query.mock.calls[0];
    expect(params.slice(2, 8)).toEqual([null, null, null, null, null, "UNKNOWN"]);
    expect(params[8]).toBeNull();
    expect(params[10]).toBeNull();
  });

  it("returns the saved listing in the API's shape", async () => {
    expect(await insertListing(RESULT, PROPERTY)).toMatchObject({
      listingId: ID,
      createdAt: "2026-11-05T08:00:00.000Z",
      riskBand: "HIGH",
      property: { price: 450, area: "Cyberjaya", bedrooms: null, propertyType: "room" },
    });
  });
});

describe("getListingById", () => {
  it("looks the id up with a parameter and maps the row", async () => {
    const listing = await getListingById(ID);
    expect(h.query).toHaveBeenCalledWith(expect.stringMatching(/WHERE listing_id = \$1$/), [ID]);
    expect(listing).toMatchObject({ listingId: ID, riskScore: 64, narrative: RESULT.narrative });
    expect(listing.property.price).toBe(450);
  });

  it("is null when there is no such row", async () => {
    h.query.mockResolvedValue({ rows: [] });
    expect(await getListingById(ID)).toBeNull();
  });
});

describe("GET /api/listings/:id", () => {
  it("returns the saved result", async () => {
    const res = await get(ID);
    expect(res.statusCode).toBe(200);
    expect(res.body).toMatchObject({ listingId: ID, riskBand: "HIGH" });
  });

  it("is 400 for an id that is not a UUID, without touching the database", async () => {
    const res = await get("1 OR 1=1");
    expect(res.statusCode).toBe(400);
    expect(h.query).not.toHaveBeenCalled();
  });

  it("is 404 when nothing was saved under the id", async () => {
    h.query.mockResolvedValue({ rows: [] });
    expect((await get(ID)).statusCode).toBe(404);
  });

  it("is 503, not an NLP error, when the database is down", async () => {
    h.query.mockRejectedValue(Object.assign(new Error("connect ECONNREFUSED 127.0.0.1:5432"), { code: "ECONNREFUSED" }));
    const res = await get(ID);
    expect(res.statusCode).toBe(503);
    expect(res.body.error).toBe("Result store unavailable");
  });
});
