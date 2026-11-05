// GET /api/listings/:id -> fetch a saved analysis result
import { Router } from "express";
import { getListing } from "../controllers/listing.controller.js";

const router = Router();

router.get("/:id", getListing);

export default router;
