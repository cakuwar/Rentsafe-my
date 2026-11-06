// Axios instance + API calls to the RentSafe backend (contract: docs/API_SPEC.md).
import axios from "axios";

// Analysis can take a while: NLP + OSINT (with its 30 s judge budget) run in
// parallel, and screenshots go through OCR first.
//
// "/api" is relative: the request goes to whatever address served the page,
// and the Vite server passes it on to the backend (vite.config.js).
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  timeout: 120000,
});

/**
 * analyzeText(text, language, { agent, property }) -> POST /analyze, returns the result JSON.
 * `agent` and `property` (the Listing details form) are optional; blank fields
 * are left out by the caller.
 */
export async function analyzeText(text, language = "auto", { agent, property } = {}) {
  const { data } = await api.post("/analyze", { text, language, agent, property });
  return data;
}

/**
 * analyzeScreenshot(files, { agent, property, language }) -> POST /analyze/screenshot
 * as multipart/form-data. `files` is one File or an array in chat order: the
 * NLP service stitches pages in upload order and never re-sorts them.
 */
export async function analyzeScreenshot(files, { agent = {}, property = {}, language = "auto" } = {}) {
  const form = new FormData();
  for (const file of [files].flat()) form.append("files", file);

  // Same details as /analyze, under the multipart field names. An empty
  // string would mean "not given" anyway; it is simply not sent.
  const fields = {
    agentName: agent.name,
    agentPhone: agent.phone,
    renNumber: agent.ren,
    company: agent.company,
    price: property.price,
    area: property.area,
    propertyType: property.propertyType,
    bedrooms: property.bedrooms,
    roomType: property.roomType,
    language,
  };
  for (const [name, value] of Object.entries(fields)) {
    if (value !== undefined && value !== null && value !== "") form.append(name, String(value));
  }

  const { data } = await api.post("/analyze/screenshot", form);
  return data;
}

/** getAreas() -> GET /price/areas: { areas: [{ name, state, strata }], dataNote }. */
export async function getAreas() {
  const { data } = await api.get("/price/areas");
  return data;
}

/**
 * describeError(error) -> { status, network, message, fields }
 * `fields` maps the API's validation paths ("agent.phone", "price", ...) to
 * their messages.
 */
export function describeError(error) {
  const response = error?.response;
  const body = response?.data ?? null;
  const fields = {};
  for (const detail of body?.details ?? []) {
    if (detail?.field) fields[detail.field] = detail.message;
  }
  return {
    status: response?.status ?? null,
    network: !response,
    message: body?.message ?? body?.error ?? null,
    fields,
  };
}
