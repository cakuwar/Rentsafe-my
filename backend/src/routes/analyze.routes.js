// POST /api/analyze            -> analyse a text listing
// POST /api/analyze/screenshot -> OCR screenshots then analyse
import { Router } from "express";
import multer from "multer";
import { analyzeText, analyzeScreenshot } from "../controllers/analyze.controller.js";

// Memory storage: screenshots are forwarded straight to the NLP service and
// never need to touch disk. The NLP service caps a request at 20 pages.
const MAX_FILE_BYTES = 5 * 1024 * 1024;
const MAX_FILES = 20;

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: MAX_FILE_BYTES, files: MAX_FILES },
});

const router = Router();

router.post("/", analyzeText);
// "files" is the field name; "image" is accepted so an older client still works.
router.post(
  "/screenshot",
  upload.fields([
    { name: "files", maxCount: MAX_FILES },
    { name: "image", maxCount: MAX_FILES },
  ]),
  (req, _res, next) => {
    // Flatten multer's per-field map into the flat array the controller wants,
    // preserving upload order: page order is conversation order.
    req.files = [...(req.files?.files ?? []), ...(req.files?.image ?? [])];
    next();
  },
  analyzeScreenshot,
);

export default router;
