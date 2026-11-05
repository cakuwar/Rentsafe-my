import { z } from "zod";
import { getListingById } from "../db/listings.repo.js";
import { logger } from "../utils/logger.js";

const listingId = z.string().uuid();

/**
 * getListing(req, res)
 * GET /api/listings/:id -> a saved analysis result: score, band, components,
 * facts and narrative (never the chat or the agent's details; listings.repo.js).
 * - 400 when the id is not a UUID
 * - 404 when there is no such result
 * - 503 when the database cannot be reached. Handled here, not by
 *   errorHandler: its ECONNREFUSED branch reports the NLP service as down.
 */
export async function getListing(req, res) {
  const parsed = listingId.safeParse(req.params?.id);
  if (!parsed.success) {
    return res.status(400).json({ error: "Invalid listing id", message: "A listing id is a UUID, as returned in listingId." });
  }

  let listing;
  try {
    listing = await getListingById(parsed.data);
  } catch (error) {
    logger.warn(`listing lookup failed: ${error.message}`);
    return res.status(503).json({
      error: "Result store unavailable",
      message: "Saved results cannot be read right now. Try again shortly.",
    });
  }

  if (!listing) return res.status(404).json({ error: "Listing not found" });
  return res.json(listing);
}
