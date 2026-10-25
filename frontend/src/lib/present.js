// Small presentation helpers shared by the result components.

// The API's bands (scoring.service.js RISK_BANDS) in the design's colours.
export const BAND_COLOUR = {
  LOW: "#34C77B",
  MODERATE: "#E9A23B",
  HIGH: "#E07B39",
  CRITICAL: "#D64545",
  UNKNOWN: "#9aa0ac",
};
// Text on the band pill: navy where white would be unreadable.
export const BAND_TEXT = {
  LOW: "#1B2A4A",
  MODERATE: "#1B2A4A",
  HIGH: "#fff",
  CRITICAL: "#fff",
  UNKNOWN: "#1B2A4A",
};
export const BAND_ICON = { LOW: "✓", MODERATE: "⚠", HIGH: "⚠", CRITICAL: "⚠", UNKNOWN: "?" };

export function bandOf(result) {
  return BAND_COLOUR[result?.riskBand] ? result.riskBand : "UNKNOWN";
}

/** pick(value, language): the API returns some text as { en, ms }. */
export function pick(value, language) {
  if (value == null) return null;
  if (typeof value === "string") return value;
  return (language === "ms" ? value.ms : value.en) ?? value.en ?? value.ms ?? null;
}

// Up to two decimals: RM299.50 is under the RM300 floor and must not show as "RM300".
export function formatRM(amount) {
  return Number(amount).toLocaleString("en-MY", { maximumFractionDigits: 2 });
}

/** stratumLabel(t, stratum) -> "KLCC studio", "Cheras (KL) 3-bedroom condo", "Setapak common room" */
export function stratumLabel(t, stratum) {
  if (!stratum?.area) return "";
  const { area, propertyType, bedrooms, roomType } = stratum;
  if (propertyType === "room") {
    return t("result.stratum.room", { area, room: t(`result.roomName.${roomType ?? "common"}`) });
  }
  if (propertyType === "condo" && bedrooms === 0) return t("result.stratum.studio", { area });
  const type = t(`result.typeName.${propertyType}`, { defaultValue: propertyType ?? "" });
  if (bedrooms >= 4) return t("result.stratum.unit4", { area, type });
  return t("result.stratum.unit", { area, n: bedrooms, type });
}

// DECISION (author, 2026-10-16) — conflict 3: the hero's first line says
// which checks actually flagged something, built only from fields the API
// returns. Each check is flagged, clear or unchecked:
// - text: flagged when layer 1 found a red flag (evidence.details);
//   model_only when the scored model probability is ≥ 0.5 (the backend's own
//   "model says scam" line) but layer 1 found nothing; clear when scored
//   below 0.5 with no red flag; unchecked when layer 2 was excluded and
//   layer 1 found nothing.
// - online / price: flagged when status is ok and points > 0, clear when ok
//   with 0 points ("nothing found" / "within the normal range"), unchecked
//   otherwise.
// The band's Guide advice stays as the line under it (result.advice.*).
//
// DECISION (author, 2026-10-16) — model_only gets its own wording: "The chat
// text reads like known scam messages, though no specific scam tactic was
// identified." It is the same condition as the API's evidenceSupport "none",
// whose note ("…but no specific scam tactic was found") is shown under this
// line, so the two agree instead of "Scam signals found in the chat text"
// sitting above "no specific scam tactic was found". It is a sentence of its
// own, followed by the online / price sentence when either of those flagged.
//
// DECISION (author, 2026-10-19) — a price flagged by the minimum-rent floor
// (D10, guard "below_floor") says "far below any real rent for this property
// type", not "far below the area median": no median was compared.
export function checkOutcomes(result) {
  const evidence = result?.evidence ?? {};
  const nlpScored = result?.components?.nlp?.included === true;
  const redFlags = (evidence.details ?? []).length > 0;
  let text = "unchecked";
  if (redFlags) text = "flagged";
  else if (nlpScored) text = result.modelProbability >= 0.5 ? "model_only" : "clear";
  const scored = (signal) => (signal?.status === "ok" ? (signal.points > 0 ? "flagged" : "clear") : "unchecked");
  return { text, online: scored(evidence.osint), price: scored(evidence.price) };
}

function joinList(t, items) {
  if (items.length < 2) return items.join("");
  return items.slice(0, -1).join(t("result.findings.comma")) + t("result.findings.and") + items[items.length - 1];
}

/**
 * findingsSentence(t, result) -> e.g. "Scam signals found in the chat text and
 * online reports." / "The price is far below the area median, but the chat
 * text looks normal." / "The chat text reads like known scam messages, though
 * no specific scam tactic was identified." / "No strong scam signals found."
 * — or null when no check ran at all (band UNKNOWN), where the API's message
 * says why.
 */
export function findingsSentence(t, result) {
  const outcome = checkOutcomes(result);
  const modelOnly = outcome.text === "model_only" ? t("result.findings.modelOnly") : null;
  const signals = ["text", "online"].filter((key) => outcome[key] === "flagged");
  const priceFlagged = outcome.price === "flagged";
  const floor = result?.evidence?.price?.guard === "below_floor" ? "Floor" : "";
  // A model_only text is never "clear", so it isn't repeated after "but".
  const clear = ["text", "online", "price"].filter((key) => outcome[key] === "clear");

  if (!signals.length && !priceFlagged) {
    if (modelOnly) return modelOnly;
    return clear.length ? t("result.findings.none") : null;
  }

  let sentence = signals.length
    ? t("result.findings.signalsIn", { list: joinList(t, signals.map((key) => t(`result.findings.flagged.${key}`))) })
      + (priceFlagged ? t(`result.findings.priceAlso${floor}`) : "")
    : t(`result.findings.priceOnly${floor}`);
  if (clear.length) {
    sentence += t("result.findings.but", { list: joinList(t, clear.map((key) => t(`result.findings.clear.${key}`))) });
  }
  sentence += t("result.findings.end");
  return modelOnly ? `${modelOnly} ${sentence}` : sentence;
}

/**
 * formatPhone("0123456789") -> "012-345 6789". Display only (conflict 6): the
 * backend keeps a parsed phone as bare digits. Mirrors metadata.service.js
 * normalisePhone / phoneVariants; anything that isn't a Malaysian mobile is
 * shown as given.
 */
export function formatPhone(raw) {
  if (!raw) return raw;
  let digits = String(raw).replace(/\D/g, "");
  if (digits.startsWith("60")) digits = digits.slice(1);
  if (!/^01\d{8,9}$/.test(digits)) return raw;
  return `${digits.slice(0, 3)}-${digits.slice(3, -4)} ${digits.slice(-4)}`;
}

/** Ends a rule label as a sentence: "Viewing refused" -> "Viewing refused." */
export function asSentence(text) {
  if (!text) return "";
  return /[.!?]$/.test(text) ? text : `${text}.`;
}
