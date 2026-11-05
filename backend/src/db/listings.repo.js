// Data-access layer for the `listings` table: one row per analysis.
//
// DECISION (2026-11-05): no personal data is stored. The table was designed
// in FYP1 to keep the renter's chat and the agent's name, phone, REN number
// and company; those columns stay NULL (database/migrations/003). A row holds
// what the system produced: score, band, components, the narrative, and
// `facts`, the narrative's own input (narrativeFacts), which by design holds
// no chat text and no identifier. The listing details typed into the form
// (rent, area, type, bedrooms) are kept: they describe the property, not a
// person. This is data minimisation under the PDPA 2010, the same reason the
// OSINT cache keys are HMACs.
import { query } from "./pool.js";
import { narrativeFacts } from "../services/llm.service.js";

const COLUMNS = `listing_id, created_at, source_type, price, area, bedrooms, property_type,
  risk_score, risk_band, component_scores, facts, narrative`;

const json = (value) => (value == null ? null : JSON.stringify(value));

/** A row as the API returns it: camelCase, numbers as numbers. */
function toListing(row) {
  return {
    listingId: row.listing_id,
    createdAt: row.created_at instanceof Date ? row.created_at.toISOString() : row.created_at,
    sourceType: row.source_type,
    riskScore: row.risk_score,
    riskBand: row.risk_band,
    components: row.component_scores,
    facts: row.facts,
    narrative: row.narrative,
    property: {
      // pg returns NUMERIC as a string, to keep its precision.
      price: row.price == null ? null : Number(row.price),
      area: row.area,
      bedrooms: row.bedrooms,
      propertyType: row.property_type,
    },
  };
}

/**
 * insertListing(result, property) -> the saved listing
 *
 * result is the finished analysis (pipeline.service.js); property is the
 * validated Listing details form, or null. Parameterised: no value is ever
 * concatenated into the SQL.
 */
export async function insertListing(result, property = null) {
  const { rows } = await query(
    `INSERT INTO listings (listing_id, source_type, price, area, bedrooms, property_type,
       risk_score, risk_band, component_scores, facts, narrative)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
     RETURNING ${COLUMNS}`,
    [
      result.listingId,
      result.sourceType,
      property?.price ?? null,
      property?.area ?? null,
      property?.bedrooms ?? null,
      property?.propertyType ?? null,
      result.riskScore ?? null,
      result.riskBand,
      json(result.components),
      json(narrativeFacts(result)),
      json(result.narrative),
    ],
  );
  return rows[0] ? toListing(rows[0]) : null;
}

/** getListingById(listingId) -> the saved listing, or null when there is none. */
export async function getListingById(listingId) {
  const { rows } = await query(`SELECT ${COLUMNS} FROM listings WHERE listing_id = $1`, [listingId]);
  return rows[0] ? toListing(rows[0]) : null;
}
