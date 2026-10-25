// Lightweight metadata parser: pulls phone, REN number and company hints out
// of raw listing text using regex heuristics, and merges in the agent details
// the renter typed into the form (form values win — the scammer's number is
// often only in the WhatsApp header, never in the chat body).
//
// It also holds the area vocabulary the price form is checked against. Price
// details are never parsed from the chat (decided 2026-10-15): they come only
// from the form.
import { CANONICAL_AREAS, DUAL_STATE_AREAS } from "../config/areas.js";

// Malaysian mobile numbers: +60 / 60 / 0, then 1x, then 7-8 digits in groups.
// The digit look-arounds stop it matching inside a bank account or IC number;
// the optional spaces around separators accept "012 - 345 6789" and the
// WhatsApp header form "+60 12-345 6789".
export const PHONE_SOURCE =
  String.raw`(?<!\d)(?:\+?60\s?|0)1\d\s?[-\s]?\s?\d{3,4}\s?[-\s]?\s?\d{4}(?!\d)`;

/**
 * phonePattern() -> a NEW global RegExp on every call. A shared /g RegExp
 * keeps lastIndex between scans, so the second snippet scanned would start
 * part-way through and miss numbers.
 */
export function phonePattern() {
  return new RegExp(PHONE_SOURCE, "g");
}

// Agent registration numbers: REN (negotiator), PEA (probationary estate
// agent) or E (estate agent). Bare digits are never treated as a REN.
const REN_SOURCE = String.raw`\b(REN|PEA|E)[\s:.\-]*(\d{1,6})\b`;

// "Maju Jaya Realty Sdn Bhd": up to five capitalised words before the suffix.
const COMPANY_RE = /(?:[A-Z][\w&'.-]*\s+){1,5}[Ss][Dd][Nn]\.?\s*[Bb][Hh][Dd]\b\.?/;
const COMPANY_SUFFIX_RE = /\bsdn\.?\s*bhd\b\.?|\bberhad\b|\bbhd\b\.?/gi;

/**
 * normalisePhone(raw) -> canonical local form "01XXXXXXXX(X)", or null when
 * raw holds no Malaysian mobile number.
 */
export function normalisePhone(raw) {
  if (typeof raw !== "string") return null;
  const match = raw.match(new RegExp(PHONE_SOURCE));
  if (!match) return null;
  let digits = match[0].replace(/\D/g, "");
  if (digits.startsWith("60")) digits = digits.slice(1);
  return /^01\d{8,9}$/.test(digits) ? digits : null;
}

/**
 * phoneVariants("0123456789") -> ["012-345 6789", "0123456789", "+60123456789"]
 * The spellings a number is actually written in on web pages. A search for
 * one does not find the others.
 */
export function phoneVariants(phone) {
  const canonical = normalisePhone(phone ?? "");
  if (!canonical) return [];
  const spaced = `${canonical.slice(0, 3)}-${canonical.slice(3, -4)} ${canonical.slice(-4)}`;
  return [spaced, canonical, `+6${canonical}`];
}

function canonicalRen(prefix, digits) {
  return `${prefix.toLowerCase()}${digits}`;
}

/**
 * normaliseRen(raw) -> "ren12345" | "pea1234" | "e1234", or null. Only a value
 * carrying a REN / PEA / E prefix is accepted: digits alone could be anything.
 */
export function normaliseRen(raw) {
  if (typeof raw !== "string") return null;
  const match = raw.trim().match(new RegExp(`^${REN_SOURCE}$`, "i"));
  return match ? canonicalRen(match[1], match[2]) : null;
}

/** renDisplay("ren12345") -> "REN 12345", the form agents publish it in. */
export function renDisplay(canonical) {
  const match = /^(ren|pea|e)(\d+)$/.exec(canonical ?? "");
  return match ? `${match[1].toUpperCase()} ${match[2]}` : null;
}

/** findRens(text) -> every REN in text, normalised. Fresh RegExp per call. */
export function findRens(text) {
  if (typeof text !== "string") return [];
  return [...text.matchAll(new RegExp(REN_SOURCE, "gi"))].map((match) =>
    canonicalRen(match[1], match[2]),
  );
}

/**
 * companyCore("Maju Jaya Realty Sdn Bhd") -> "Maju Jaya Realty", or null when
 * fewer than two words remain once Sdn Bhd / Bhd / Berhad is removed — a
 * one-word name ("Maju") matches far too many unrelated pages to search on.
 */
export function companyCore(name) {
  if (typeof name !== "string") return null;
  const core = name.replace(COMPANY_SUFFIX_RE, " ").replace(/\s+/g, " ").trim();
  return core.split(" ").filter(Boolean).length >= 2 ? core : null;
}

function cleanText(value) {
  if (typeof value !== "string") return null;
  const cleaned = value.replace(/\s+/g, " ").trim();
  return cleaned || null;
}

// ---------------------------------------------------------------------------
// Areas and room types — the vocabulary the price form is validated against.
// Prices are never read from the chat: rent, area, type and bedrooms come only
// from the "Listing details" form (price.service.js).
// ---------------------------------------------------------------------------

const CANONICAL_BY_LOWER = new Map(Object.keys(CANONICAL_AREAS).map((name) => [name.toLowerCase(), name]));

/**
 * canonicalArea(" cheras (kl) ") -> "Cheras (KL)": the form's area must be one
 * of the canonical names GET /api/price/areas lists (trimmed, any case). No
 * aliases and no partial matches — the dropdown sends the exact name.
 */
export function canonicalArea(raw) {
  if (typeof raw !== "string") return null;
  return CANONICAL_BY_LOWER.get(raw.trim().replace(/\s+/g, " ").toLowerCase()) ?? null;
}

/** dualStateOptions("cheras") -> ["Cheras (KL)", "Cheras (Selangor)"], else null. */
export function dualStateOptions(raw) {
  const target = DUAL_STATE_AREAS[(raw ?? "").trim().toLowerCase()];
  return target ? Object.values(target) : null;
}

/**
 * normaliseRoomType("single") -> "common". Single and middle rooms cannot be
 * told apart in the data (portals label only "Master" / "Common"), so both
 * are priced as common rooms.
 */
export function normaliseRoomType(raw) {
  const text = (raw ?? "").toString().trim().toLowerCase();
  if (!text) return null;
  if (text.includes("master")) return "master";
  if (/common|middle|medium|single|small/.test(text)) return "common";
  return null;
}

/**
 * parseMetadata(text) -> { phone, allPhones, renNumber, agentName, company }
 * Takes the first matched phone number. agentName is always null here: a name
 * cannot be told apart from the rest of a chat reliably, so it comes from the
 * form. Rent and property details are not read from the chat at all.
 */
export function parseMetadata(text) {
  const source = typeof text === "string" ? text : "";

  const allPhones = [
    ...new Set(
      [...source.matchAll(phonePattern())]
        .map((match) => normalisePhone(match[0]))
        .filter(Boolean),
    ),
  ];
  // From free text, require 4+ digits: "Block E 12" is an address, not an
  // estate agent. A REN typed into the form is taken as given.
  const ren = findRens(source).find((value) => /\d{4,}$/.test(value)) ?? null;

  return {
    phone: allPhones[0] ?? null,
    allPhones,
    renNumber: renDisplay(ren),
    agentName: null,
    company: source.match(COMPANY_RE)?.[0].trim() ?? null,
  };
}

/**
 * mergeAgentDetails(parsed, agent) -> metadata with the form's agent details
 * laid over what was parsed from the text. A form value always wins.
 * identitySource: "form" if any form value was used, "text" if the identity
 * came from the chat alone, null if there is none.
 */
export function mergeAgentDetails(parsed, agent) {
  const merged = { ...(parsed ?? parseMetadata("")) };
  const form = {
    phone: normalisePhone(agent?.phone ?? ""),
    agentName: cleanText(agent?.name),
    renNumber: cleanText(agent?.ren),
    company: cleanText(agent?.company),
  };

  let fromForm = false;
  for (const [field, value] of Object.entries(form)) {
    if (value) {
      merged[field] = value;
      fromForm = true;
    }
  }
  if (form.phone && !merged.allPhones?.includes(form.phone)) {
    merged.allPhones = [form.phone, ...(merged.allPhones ?? [])];
  }

  const hasIdentity = Boolean(
    merged.phone || merged.agentName || merged.renNumber || merged.company,
  );
  merged.identitySource = fromForm ? "form" : hasIdentity ? "text" : null;
  return merged;
}
