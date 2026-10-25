// Handles GET /api/price/areas and GET /api/price/check — the price
// comparison on its own, without a chat. GET is fine here: nothing in a rent,
// an area or a bedroom count identifies anyone. No paid calls are made, so
// only the global rate limit applies.
import { propertyFields } from "../validation/property.schema.js";
import { listBaselineStrata, scorePriceAnomaly } from "../services/price.service.js";

const DISCLAIMER = {
  en: "Compared with asking prices on listing sites, not agreed rents. A price far below "
    + "market is a warning sign, not proof of a scam; a normal price is not proof of safety.",
  ms: "Dibandingkan dengan harga tawaran di laman iklan, bukan sewa sebenar. Harga yang jauh "
    + "di bawah pasaran ialah tanda amaran, bukan bukti penipuan; harga biasa bukan bukti selamat.",
};

/**
 * GET /api/price/check?price=&area=&propertyType=&bedrooms=&roomType=
 * The same form contract as /analyze's `property`: a field not filled in gives
 * status missing_input (200), a malformed one a 400.
 */
export async function checkPrice(req, res, next) {
  try {
    const result = await scorePriceAnomaly(propertyFields.parse(req.query ?? {}));
    res.status(result.status === "baseline_unavailable" ? 503 : 200).json({ ...result, disclaimer: DISCLAIMER });
  } catch (error) {
    next(error);
  }
}

/** GET /api/price/areas — every canonical area and its strata, for the dropdown. */
export async function listAreas(req, res) {
  try {
    res.json(await listBaselineStrata());
  } catch {
    res.status(503).json({ error: "Price data is unavailable right now" });
  }
}
