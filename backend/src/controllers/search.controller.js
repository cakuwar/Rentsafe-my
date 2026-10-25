// Handles POST /api/search — the public agent lookup. Runs the same OSINT
// search the analysis pipeline uses, on details typed in directly, and
// returns what it found. There is no overall risk score: without the chat
// and the price there is nothing to combine it with.
//
// POST rather than GET so the phone number never lands in a URL, where
// morgan's request log would record it.
import { agentFields } from "../validation/agent.schema.js";
import { searchAgentReputation } from "../services/osint.service.js";

const searchSchema = agentFields.refine(
  (body) => Boolean(body.phone) || (body.name ?? "").split(/\s+/).filter(Boolean).length >= 2,
  {
    message: "Give a Malaysian mobile number or the agent's full name (2+ words).",
    path: ["phone"],
  },
);

const DISCLAIMER = {
  en: "These are public web mentions found by a search engine, not verified findings. "
    + "Finding nothing does not mean the agent is safe: check the REN number at "
    + "lppeh.gov.my and never pay before viewing the unit.",
  ms: "Ini ialah sebutan awam di web yang ditemui oleh enjin carian, bukan penemuan "
    + "yang disahkan. Tiada hasil tidak bermakna ejen itu selamat: semak nombor REN di "
    + "lppeh.gov.my dan jangan bayar sebelum melihat unit.",
};

const HTTP_STATUS = {
  ok: 200,
  no_identifier: 400,
  quota_exceeded: 429,
  not_configured: 503,
  search_failed: 503,
};

/**
 * searchAgent(req, res, next)
 * Body: { phone?, name?, ren?, company? } — a valid phone or a 2+ word name.
 */
export async function searchAgent(req, res, next) {
  try {
    const { phone, name, ren, company } = searchSchema.parse(req.body ?? {});
    const result = await searchAgentReputation({
      phone,
      agentName: name,
      renNumber: ren,
      company,
      identitySource: "form",
    });
    res.status(HTTP_STATUS[result.status] ?? 200).json({ ...result, disclaimer: DISCLAIMER });
  } catch (error) {
    next(error);
  }
}
