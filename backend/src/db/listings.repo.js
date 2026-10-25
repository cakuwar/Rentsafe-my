// Data-access layer for the `listings` table.
import { query } from "./pool.js";

/**
 * insertListing(record) -> inserted row
 * record fields: listing_id, raw_text, source_type, agent_name, agent_phone,
 * ren_number, company_name, price, area, bedrooms, property_type,
 * risk_score, risk_band, component_scores, narrative.
 * TODO: write the parameterised INSERT (never string-concatenate SQL) and
 * return the inserted row (RETURNING *).
 */
export async function insertListing(record) {
  // TODO: implement
}

/**
 * getListingById(listingId) -> row | null
 * TODO: SELECT the row by listing_id, return null if not found.
 */
export async function getListingById(listingId) {
  // TODO: implement
}
