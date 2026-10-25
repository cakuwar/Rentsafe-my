// POST /api/search: validation and pass-through, with fake req/res objects.
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockLookup } = vi.hoisted(() => ({ mockLookup: vi.fn() }));
vi.mock("../src/services/osint.service.js", () => ({ searchAgentReputation: mockLookup }));

import { searchAgent } from "../src/controllers/search.controller.js";
import { errorHandler } from "../src/middleware/errorHandler.js";

function fakeRes() {
  return {
    statusCode: 200,
    body: undefined,
    headersSent: false,
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

async function post(body) {
  const res = fakeRes();
  let forwarded = null;
  await searchAgent({ body }, res, (error) => {
    forwarded = error;
  });
  if (forwarded) errorHandler(forwarded, { method: "POST", originalUrl: "/api/search" }, res, () => {});
  return res;
}

beforeEach(() => {
  mockLookup.mockReset();
});

describe("POST /api/search", () => {
  it("rejects a body with neither a phone nor a full name", async () => {
    for (const body of [{}, { name: "Ahmad" }, { ren: "REN 12345" }, { phone: "   " }]) {
      const res = await post(body);
      expect(res.statusCode, JSON.stringify(body)).toBe(400);
      expect(res.body.error).toBe("Validation failed");
    }
    expect(mockLookup).not.toHaveBeenCalled();
  });

  it("rejects a phone that is not a Malaysian mobile number", async () => {
    const res = await post({ phone: "12345" });
    expect(res.statusCode).toBe(400);
    expect(res.body.details[0].field).toBe("phone");
  });

  it("passes the details through and returns the result with a disclaimer", async () => {
    mockLookup.mockResolvedValue({ status: "ok", points: 8, riskFraction: 0.32, evidence: [] });
    const res = await post({ phone: "012-345 6789", name: " Ahmad Faizal ", ren: "REN 12345", company: "" });

    expect(mockLookup).toHaveBeenCalledWith({
      phone: "012-345 6789",
      agentName: "Ahmad Faizal",
      renNumber: "REN 12345",
      company: undefined,
      identitySource: "form",
    });
    expect(res.statusCode).toBe(200);
    expect(res.body.points).toBe(8);
    expect(res.body.disclaimer.en).toMatch(/not verified/);
    expect(res.body.disclaimer.ms).toMatch(/bukan penemuan yang disahkan/);
    expect(res.body).not.toHaveProperty("riskScore");
  });

  it("maps quota and configuration statuses to HTTP codes", async () => {
    mockLookup.mockResolvedValue({ status: "quota_exceeded", riskFraction: null });
    expect((await post({ phone: "0123456789" })).statusCode).toBe(429);

    mockLookup.mockResolvedValue({ status: "not_configured", riskFraction: null });
    expect((await post({ phone: "0123456789" })).statusCode).toBe(503);
  });
});
