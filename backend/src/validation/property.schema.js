// The "Listing details" form (PRD "Input D"): the ONLY source of the rent and
// the property the price check compares — prices are never read from the chat.
// Shared by POST /api/analyze (`property`), POST /api/analyze/screenshot
// (multipart fields) and GET /api/price/check.
//
// Every field is optional here: a blank field means "not given" (multipart
// sends "", which must never become 0), and what the stratum still needs is
// reported by the price check as missing_input — not a 400. A value that is
// given but malformed (bedrooms "2.5", price "abc") is a 400.
import { z } from "zod";
import { PROPERTY_TYPES } from "../config/areas.js";
import { normaliseRoomType } from "../services/metadata.service.js";

/** What the form may send for propertyType: the stratum types plus "studio". */
export const FORM_PROPERTY_TYPES = [...PROPERTY_TYPES, "studio"];

const blank = (value) => value === undefined || value === null || (typeof value === "string" && value.trim() === "");

// 1500, "1500", "1,500", "RM1,500", "RM 1 500".
const price = z.preprocess(
  (value) => {
    if (blank(value)) return undefined;
    if (typeof value === "number") return value;
    const text = String(value).trim().replace(/^(?:rm|myr)/i, "").replace(/[,\s]/g, "");
    return /^\d+(?:\.\d+)?$/.test(text) ? Number(text) : Number.NaN;
  },
  z.number({ invalid_type_error: "price must be a monthly rent in RM, e.g. 1500 or RM1,500" })
    .positive("price must be more than 0")
    .max(100000, "price must be at most RM100,000 a month")
    .optional(),
);

const area = z.preprocess(
  (value) => (blank(value) ? undefined : String(value).trim().replace(/\s+/g, " ")),
  z.string().max(60).optional(),
);

const propertyType = z.preprocess(
  (value) => (blank(value) ? undefined : String(value).trim().toLowerCase()),
  z.enum(FORM_PROPERTY_TYPES, {
    errorMap: () => ({ message: `propertyType must be one of ${FORM_PROPERTY_TYPES.join(", ")}` }),
  }).optional(),
);

// 0-20; "4+" is 4. Bucketing 5+ into 4 happens in normaliseProperty.
const bedrooms = z.preprocess(
  (value) => {
    if (blank(value)) return undefined;
    if (typeof value === "number") return value;
    const text = String(value).trim();
    if (text === "4+") return 4;
    return /^\d+$/.test(text) ? Number(text) : Number.NaN;
  },
  z.number({ invalid_type_error: "bedrooms must be a whole number from 0 to 20 (0 = studio)" })
    .int("bedrooms must be a whole number from 0 to 20 (0 = studio)")
    .min(0)
    .max(20)
    .optional(),
);

// single / middle are priced as common rooms.
const roomType = z.preprocess(
  (value) => (blank(value) ? undefined : normaliseRoomType(value) ?? "invalid"),
  z.enum(["master", "common"], {
    errorMap: () => ({ message: "roomType must be master or common (single and middle count as common)" }),
  }).optional(),
);

/**
 * normaliseProperty(form) -> { price, area, propertyType, bedrooms, roomType }
 * on the stratum's terms:
 *   studio            -> condo, bedrooms 0 (any bedrooms sent is ignored)
 *   room              -> bedrooms ignored; roomType kept
 *   other types       -> bedrooms 5+ bucketed to 4; roomType ignored
 * Fields not given stay undefined.
 */
export function normaliseProperty(form) {
  const out = { ...form };
  if (out.propertyType === "studio") {
    out.propertyType = "condo";
    out.bedrooms = 0;
  }
  if (out.propertyType === "room") {
    delete out.bedrooms;
  } else {
    delete out.roomType;
    if (out.bedrooms !== undefined) out.bedrooms = Math.min(4, out.bedrooms);
  }
  return out;
}

export const propertyFields = z
  .object({ price, area, propertyType, bedrooms, roomType })
  .transform(normaliseProperty);
