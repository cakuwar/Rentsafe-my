// GET /api/price/areas -> strata available for the area / type dropdowns
// GET /api/price/check -> compare one rent with its stratum
import { Router } from "express";
import { checkPrice, listAreas } from "../controllers/price.controller.js";

const router = Router();

router.get("/areas", listAreas);
router.get("/check", checkPrice);

export default router;
