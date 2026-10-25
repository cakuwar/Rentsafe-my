// The scam eval's case rules: kinds, validation, outcomes and grouping.
import { describe, it, expect } from "vitest";
import { caseKind, outcome, summarise, validateRows } from "../scripts/price_scam_eval.js";

const row = (overrides = {}) => ({
  case_id: "PFC-S01", label: "scam", source_conversation: "REAL-S01", source_url: "",
  price: "800", area: "", property_type: "room", bedrooms: "", room_type: "", notes: "", ...overrides,
});

describe("caseKind", () => {
  it("splits chat (S / L) from news (N) cases", () => {
    expect(caseKind("PFC-S04")).toBe("chat");
    expect(caseKind("PFC-L08")).toBe("chat");
    expect(caseKind("PFC-N01")).toBe("news");
    expect(caseKind("N02")).toBe("news");
    expect(caseKind("PFC-X01")).toBeNull();
  });
});

describe("validateRows", () => {
  it("accepts chat and news cases that follow the rules", () => {
    expect(validateRows([
      row(), row({ case_id: "PFC-L01", label: "legit" }),
      row({ case_id: "PFC-N01", source_conversation: "", source_url: "https://www.thestar.com.my/news/..." }),
    ])).toEqual([]);
  });

  it("rejects a news case that is not a scam or has no source_url, a mislabelled chat, a bad id, a duplicate", () => {
    const problems = validateRows([
      row({ case_id: "PFC-N01", label: "legit", source_url: "https://example.com" }),
      row({ case_id: "PFC-N02" }),
      row({ case_id: "PFC-L01", label: "scam" }),
      row({ case_id: "CASE-7" }),
      row({ case_id: "PFC-S01" }),
      row({ case_id: "PFC-S01" }),
    ]);
    expect(problems.join("\n")).toMatch(/PFC-N01: a N case must be labelled scam/);
    expect(problems.join("\n")).toMatch(/PFC-N02: a news case needs its source_url/);
    expect(problems.join("\n")).toMatch(/PFC-L01: a L case must be labelled legit/);
    expect(problems.join("\n")).toMatch(/CASE-7: case_id must be/);
    expect(problems.join("\n")).toMatch(/PFC-S01: duplicate case_id/);
  });

  it("requires every column, source_url included", () => {
    const { source_url: _, ...noUrl } = row();
    expect(validateRows([noUrl])[0]).toMatch(/missing columns: source_url/);
  });
});

describe("outcome", () => {
  it("counts an area outside KL / Selangor as outside coverage, even if the form is incomplete", () => {
    expect(outcome({ status: "missing_input" }, row({ area: "Penang", property_type: "" })))
      .toEqual({ outcome: "outside_coverage", detail: "area_not_covered" });
    expect(outcome({ status: "unknown_area" }, row({ area: "Serdang, Kedah" })))
      .toEqual({ outcome: "outside_coverage", detail: "area_not_covered" });
  });

  it("counts landed and a missing stratum as outside coverage", () => {
    expect(outcome({ status: "missing_input" }, row({ area: "Kajang", property_type: "landed" })).detail).toBe("landed");
    expect(outcome({ status: "no_baseline" }, row({ area: "Kajang" })))
      .toEqual({ outcome: "outside_coverage", detail: "no_stratum" });
  });

  it("keeps input problems apart from coverage", () => {
    expect(outcome({ status: "missing_input" }, row()).outcome).toBe("input_incomplete");
    expect(outcome({ status: "unknown_area" }, row({ area: "Cheras" })))
      .toEqual({ outcome: "input_incomplete", detail: "ambiguous_area" });
    expect(outcome({ status: "invalid_input" }, row({ area: "Kajang" })).detail).toBe("invalid_input");
  });

  it("maps the remaining statuses", () => {
    expect(outcome({ status: "ok" }, row({ area: "Setapak" })).outcome).toBe("scored");
    expect(outcome({ status: "thin_baseline" }, row({ area: "Setapak" })).outcome).toBe("insufficient_data");
    expect(outcome({ status: "baseline_unavailable" }, row({ area: "Setapak" })).outcome).toBe("unavailable");
  });
});

describe("summarise", () => {
  it("reports chat, news and combined, each by label", () => {
    const cases = [
      { kind: "chat", label: "scam", outcome: "scored", points: 15 },
      { kind: "chat", label: "legit", outcome: "scored", points: 0 },
      { kind: "chat", label: "legit", outcome: "outside_coverage", detail: "area_not_covered" },
      { kind: "news", label: "scam", outcome: "scored", points: 10 },
      { kind: "news", label: "scam", outcome: "input_incomplete", detail: "missing_input" },
    ];
    const { chat, news, combined } = summarise(cases);
    expect(chat.scam).toMatchObject({ cases: 1, scored: 1, flagged10: 1, flagged15: 1 });
    expect(chat.legit.outside_coverage).toEqual({ total: 1, area_not_covered: 1, landed: 0, no_stratum: 0 });
    expect(news.scam).toMatchObject({ cases: 2, scored: 1, flagged10: 1, flagged15: 0 });
    expect(news.scam.input_incomplete.missing_input).toBe(1);
    expect(combined.scam).toMatchObject({ cases: 3, scored: 2, flagged10: 2, flagged15: 1 });
    expect(combined.all.cases).toBe(5);
    expect(news.legit).toBeUndefined();
  });
});
