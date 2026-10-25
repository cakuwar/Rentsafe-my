// GET /api/listings/:id -> fetch a stored analysis result
import { Router } from "express";
import { getListing } from "../controllers/listing.controller.js";

// TODO: wire GET /:id to the getListing controller.
const router = Router();

export default router;
