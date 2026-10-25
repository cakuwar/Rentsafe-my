// POST /api/search -> public agent lookup (phone / name / REN / company)
import { Router } from "express";
import { searchAgent } from "../controllers/search.controller.js";
import { searchRateLimiter } from "../middleware/rateLimiter.js";

const router = Router();

router.post("/", searchRateLimiter, searchAgent);

export default router;
