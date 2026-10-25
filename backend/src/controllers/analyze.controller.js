// Handles POST /api/analyze and POST /api/analyze/screenshot.
import { z } from "zod";
import { runAnalysisPipeline } from "../services/pipeline.service.js";
import { ocrScreenshots } from "../services/nlp.service.js";
import { agentFields } from "../validation/agent.schema.js";
import { propertyFields } from "../validation/property.schema.js";

// A two-character body is not a conversation. Layer 2 needs about six messages
// before its output means anything, so anything shorter than a sentence is
// rejected here rather than travelling through the whole pipeline to come back
// as "insufficient_context".
//
// `agent` is optional: when a field is blank the pipeline falls back to what it
// can parse from the text. The form matters because the scammer's number is
// usually in the WhatsApp header, not the chat body.
//
// `property` (the "Listing details" form) is optional too, but nothing stands
// in for it: the rent is never read from the chat. Absent or partial, the
// price check reports missing_input and is left out of the score — no error.
const analyzeTextSchema = z.object({
  text: z
    .string({ required_error: "text is required" })
    .trim()
    .min(20, "text is too short to analyse — paste the conversation"),
  language: z.enum(["auto", "ms", "en"]).default("auto"),
  agent: agentFields.optional(),
  property: propertyFields.optional(),
});

/**
 * analyzeText(req, res, next)
 * Validate, run the pipeline, respond with its result.
 */
export async function analyzeText(req, res, next) {
  try {
    const { text, language, agent, property } = analyzeTextSchema.parse(req.body ?? {});
    const result = await runAnalysisPipeline({
      rawText: text,
      sourceType: "text",
      language,
      agent,
      property,
    });
    res.json(result);
  } catch (error) {
    next(error);
  }
}

/**
 * analyzeScreenshot(req, res, next)
 * OCR the uploaded screenshots, then run the same pipeline on the extracted
 * text. Accepts several files: a chat rarely fits in one screenshot, and the
 * NLP service stitches the pages in upload order.
 */
export async function analyzeScreenshot(req, res, next) {
  try {
    const files = req.files?.length ? req.files : req.file ? [req.file] : [];
    if (files.length === 0) {
      return res.status(400).json({
        error: "No screenshot uploaded",
        details: [{ field: "files", message: "Attach at least one screenshot." }],
      });
    }

    // Multipart text fields, validated before any OCR is paid for.
    const agent = agentFields.parse({
      name: req.body?.agentName,
      phone: req.body?.agentPhone,
      ren: req.body?.renNumber,
      company: req.body?.company,
    });
    const property = propertyFields.parse({
      price: req.body?.price,
      area: req.body?.area,
      bedrooms: req.body?.bedrooms,
      propertyType: req.body?.propertyType,
      roomType: req.body?.roomType,
    });

    const ocr = await ocrScreenshots(files);
    const extracted = (ocr.extracted_text ?? "").trim();

    if (!extracted) {
      return res.status(422).json({
        error: "No text could be read from the screenshots",
        ocr: { pageCount: ocr.page_count, pages: ocr.pages },
      });
    }

    const result = await runAnalysisPipeline({
      rawText: extracted,
      sourceType: "screenshot",
      language: req.body?.language ?? "auto",
      agent,
      property,
    });

    // ocrText and the per-page results are returned for debugging: when a score
    // looks wrong the first question is always whether OCR read the chat.
    res.json({
      ...result,
      ocrText: extracted,
      ocr: {
        pageCount: ocr.page_count,
        messages: ocr.turns,
        pages: ocr.pages,
      },
    });
  } catch (error) {
    next(error);
  }
}
