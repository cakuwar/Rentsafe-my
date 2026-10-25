// The analyse form: its empty state, the demo sample, and how it maps onto
// the API's `agent` and `property` objects.

export const EMPTY_FORM = {
  listingText: "",
  phone: "",
  agentName: "",
  ren: "",
  company: "",
  rent: "",
  area: "",
  propertyType: "",
  bedrooms: "",
  roomType: "",
};

// The form table in docs/API_SPEC.md ("The Listing details form"): bedrooms
// for whole units, a room type for rooms, neither for a studio.
export const PROPERTY_TYPES = ["studio", "condo", "apartment", "flat", "landed", "room"];
export const BEDROOM_TYPES = ["condo", "apartment", "flat", "landed"];
export const BEDROOM_OPTIONS = ["1", "2", "3", "4+"];
export const ROOM_TYPES = ["master", "common"];

// DECISION (author, 2026-10-15) — the design's sample was one line ("Fully
// furnished studio near KLCC, RM750/month, wifi included, pls whatsapp fast
// deal."). Layer 2 returns insufficient_context below about six messages, so
// that sample would always come back UNKNOWN. This chat keeps the design's
// listing, agent and rent; checked against layer 1 it has 9 messages and
// fires pay_before_viewing, key_courier, viewing_denial and five more.
// The rent still comes only from the form fields below (D8), never this text.
export const SAMPLE_FORM = {
  listingText: [
    "Agent: Fully furnished studio near KLCC, RM750/month, wifi included. Pls whatsapp fast deal.",
    "Renter: Hi, studio KLCC tu masih available ke?",
    "Agent: Ya masih ada. Ramai org tgh tanya unit ni, kena cepat.",
    "Renter: Boleh saya tengok unit dulu?",
    "Agent: Sorry owner duduk overseas, tak boleh viewing. Lepas bayar saya pos kunci.",
    "Agent: Kena byr deposit RM1500 dulu baru boleh dapat kunci.",
    "Renter: Boleh bayar masa sign agreement?",
    "Agent: Fast deal je bro. Transfer hari ni sebelum 6pm, kalau lambat saya bagi org lain.",
    "Agent: Bank in ke akaun Maybank isteri saya, lepas tu hantar resit kat sini.",
  ].join("\n"),
  phone: "+60 12-345 6789",
  agentName: "Encik Razak",
  ren: "",
  company: "Prime Realty Holdings",
  rent: "750",
  area: "KLCC",
  propertyType: "studio",
  bedrooms: "",
  roomType: "",
};

function compact(fields) {
  const out = {};
  for (const [key, value] of Object.entries(fields)) {
    const text = typeof value === "string" ? value.trim() : value;
    if (text !== undefined && text !== null && text !== "") out[key] = text;
  }
  return Object.keys(out).length ? out : undefined;
}

/** toRequest(form) -> { agent, property }, each undefined when nothing was filled in. */
export function toRequest(form) {
  const type = form.propertyType;
  return {
    agent: compact({
      name: form.agentName,
      phone: form.phone,
      ren: form.ren,
      company: form.company,
    }),
    property: compact({
      price: form.rent,
      area: form.area,
      propertyType: type,
      bedrooms: BEDROOM_TYPES.includes(type) ? form.bedrooms : undefined,
      roomType: type === "room" ? form.roomType : undefined,
    }),
  };
}

// API validation paths -> form fields. /analyze nests them ("agent.phone");
// /analyze/screenshot validates flat multipart fields ("phone").
const FIELD_FOR_PATH = {
  text: "listingText",
  files: "files",
  name: "agentName",
  phone: "phone",
  ren: "ren",
  company: "company",
  price: "rent",
  area: "area",
  propertyType: "propertyType",
  bedrooms: "bedrooms",
  roomType: "roomType",
};

/** fieldErrors(apiFields) -> { [formField]: message } */
export function fieldErrors(apiFields = {}) {
  const out = {};
  for (const [path, message] of Object.entries(apiFields)) {
    const field = FIELD_FOR_PATH[path.split(".").pop()];
    if (field) out[field] = message;
  }
  return out;
}

/** Whether OSINT has something to search on: a phone, or a name of 2+ words. */
export function hasSearchableIdentity(form) {
  return form.phone.trim() !== "" || form.agentName.trim().split(/\s+/).filter(Boolean).length >= 2;
}
