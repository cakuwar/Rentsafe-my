// Identity parsing for the OSINT search: phone, REN, company, and the merge
// of form values over what was parsed from the chat.
import { describe, it, expect } from "vitest";
import {
  canonicalArea,
  companyCore,
  dualStateOptions,
  findRens,
  mergeAgentDetails,
  normalisePhone,
  normaliseRen,
  normaliseRoomType,
  parseMetadata,
  phonePattern,
  phoneVariants,
  renDisplay,
} from "../src/services/metadata.service.js";

describe("phone numbers", () => {
  it("accepts the spellings Malaysian numbers are written in", () => {
    const cases = {
      "012-345 6789": "0123456789",
      "012 - 345 6789": "0123456789",
      "+60 12-345 6789": "0123456789",
      "+6012-3456789": "0123456789",
      "60123456789": "0123456789",
      "0123456789": "0123456789",
      "011-1234 5678": "01112345678",
    };
    for (const [raw, canonical] of Object.entries(cases)) {
      expect(normalisePhone(raw), raw).toBe(canonical);
    }
  });

  it("never matches a phone embedded in a longer digit string", () => {
    expect(normalisePhone("acct 5641230123456789012")).toBeNull();
    expect(normalisePhone("ref 1234012345678999")).toBeNull();
    expect(normalisePhone("03-1234 5678")).toBeNull(); // landline, not mobile
  });

  it("finds numbers in two snippets scanned one after the other", () => {
    // A shared /g RegExp would start the second scan at lastIndex 17 — past
    // the end of the 10-character second string — and miss it.
    expect(phonePattern().test("call 012-345 6789 now")).toBe(true);
    expect(phonePattern().test("0198765432")).toBe(true);
    expect(phonePattern()).not.toBe(phonePattern());
  });

  it("lists the variants a web page might use", () => {
    expect(phoneVariants("+60 12-345 6789")).toEqual(["012-345 6789", "0123456789", "+60123456789"]);
    expect(phoneVariants("01112345678")).toEqual(["011-1234 5678", "01112345678", "+601112345678"]);
    expect(phoneVariants("nope")).toEqual([]);
  });
});

describe("REN numbers", () => {
  it("accepts only prefixed values", () => {
    expect(normaliseRen("REN 12345")).toBe("ren12345");
    expect(normaliseRen("ren-12345")).toBe("ren12345");
    expect(normaliseRen("REN12345")).toBe("ren12345");
    expect(normaliseRen("PEA 1234")).toBe("pea1234");
    expect(normaliseRen("E 1234")).toBe("e1234");
    expect(normaliseRen("12345")).toBeNull();
    expect(normaliseRen("RENT 123")).toBeNull();
    expect(renDisplay("ren12345")).toBe("REN 12345");
  });

  it("finds RENs on word boundaries only", () => {
    expect(findRens("Contact REN 12345 or 0123456789")).toEqual(["ren12345"]);
    expect(findRens("call 0123456789")).toEqual([]);
    expect(findRens("Warren 12345")).toEqual([]);
  });
});

describe("companyCore", () => {
  it("needs two words once the suffix is gone", () => {
    expect(companyCore("Maju Sdn Bhd")).toBeNull();
    expect(companyCore("Maju Bhd")).toBeNull();
    expect(companyCore("Maju Jaya Realty Sdn. Bhd.")).toBe("Maju Jaya Realty");
    expect(companyCore("Hartanah Maju Berhad")).toBe("Hartanah Maju");
  });
});

describe("parseMetadata", () => {
  it("pulls phone, REN and company out of a chat", () => {
    const meta = parseMetadata(
      "Hi, saya Aina dari Maju Jaya Realty Sdn Bhd, REN 31234. WhatsApp +60 12-345 6789 atau 019-876 5432.",
    );
    expect(meta.phone).toBe("0123456789");
    expect(meta.allPhones).toEqual(["0123456789", "0198765432"]);
    expect(meta.renNumber).toBe("REN 31234");
    expect(meta.company).toBe("Maju Jaya Realty Sdn Bhd");
    expect(meta.agentName).toBeNull();
    // The rent and property come from the form only, never from the chat.
    expect(meta).not.toHaveProperty("price");
  });

  it("does not read an address block as a REN", () => {
    expect(parseMetadata("Unit at Block E 12, call 0123456789").renNumber).toBeNull();
  });
});

describe("mergeAgentDetails", () => {
  it("lets form values win over parsed ones", () => {
    const parsed = parseMetadata("call 0123456789 for viewing");
    const merged = mergeAgentDetails(parsed, { phone: "019-876 5432", name: "  Ahmad   Faizal " });
    expect(merged.phone).toBe("0198765432");
    expect(merged.agentName).toBe("Ahmad Faizal");
    expect(merged.allPhones).toEqual(["0198765432", "0123456789"]);
    expect(merged.identitySource).toBe("form");
  });

  it("reports where the identity came from", () => {
    expect(mergeAgentDetails(parseMetadata("call 0123456789"), undefined).identitySource).toBe("text");
    const empty = mergeAgentDetails(null, undefined);
    expect(empty.identitySource).toBeNull();
    expect(empty.phone).toBeNull();
    expect(empty.allPhones).toEqual([]);
  });
});

describe("area and room-type vocabulary (price form)", () => {
  it("accepts only a canonical area for the form, trimmed and in any case", () => {
    expect(canonicalArea(" cheras (kl) ")).toBe("Cheras (KL)");
    expect(canonicalArea("Wangsa  Maju")).toBe("Wangsa Maju");
    expect(canonicalArea("Cheras")).toBeNull();
    expect(canonicalArea("PJ")).toBeNull();
    expect(canonicalArea("Atlantis")).toBeNull();
  });

  it("names both areas behind a two-state name", () => {
    expect(dualStateOptions("cheras")).toEqual(["Cheras (KL)", "Cheras (Selangor)"]);
    expect(dualStateOptions("Kajang")).toBeNull();
  });

  it("prices single and middle rooms as common", () => {
    expect(normaliseRoomType("single")).toBe("common");
    expect(normaliseRoomType("Middle")).toBe("common");
    expect(normaliseRoomType("Master Room")).toBe("master");
    expect(normaliseRoomType("penthouse")).toBeNull();
  });
});
