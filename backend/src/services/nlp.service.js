// Thin client over the Python FastAPI NLP microservice.
import axios from "axios";
import FormData from "form-data";
import { config } from "../config/index.js";

// The first /classify of a process pays for loading the transformer weights,
// which takes several seconds on CPU. A short timeout would fail exactly once
// per deploy, at the worst possible moment, so this is deliberately generous.
const FIRST_LOAD_ALLOWANCE_MS = 60_000;

const client = axios.create({
  baseURL: config.nlpServiceUrl,
  timeout: FIRST_LOAD_ALLOWANCE_MS,
  headers: { Accept: "application/json" },
});

/**
 * classifyText({ text, language }) -> POST /classify on the NLP service.
 * Returns { scam_probability, normalised_text, red_flags, layer1, layer2 }.
 *
 * layer2.status matters as much as the probability: on "insufficient_context"
 * or "model_unavailable" the 0.5 it returns means "cannot judge", and
 * aggregateScore excludes it rather than scoring it as medium risk.
 */
export async function classifyText({ text, language = "auto" }) {
  const { data } = await client.post("/classify", { text, language });
  return data;
}

/**
 * ocrScreenshots(files) -> POST /ocr (multipart) on the NLP service.
 *
 * Takes an array of { buffer, originalname, mimetype } — a chat rarely fits in
 * one screenshot, and the service stitches the pages into a single conversation
 * in the order given. That order is the upload order, so it must be preserved
 * here: sorting by filename would put "IMG_10" before "IMG_2".
 *
 * Returns { extracted_text, page_count, turns, pages }.
 */
export async function ocrScreenshots(files) {
  const list = Array.isArray(files) ? files : [files];
  const form = new FormData();
  for (const file of list) {
    form.append("files", file.buffer, {
      filename: file.originalname ?? "screenshot.png",
      contentType: file.mimetype ?? "image/png",
    });
  }

  const { data } = await client.post("/ocr", form, {
    headers: form.getHeaders(),
    maxBodyLength: Infinity,
    maxContentLength: Infinity,
  });
  return data;
}

/** Single-file convenience wrapper, kept for callers that have just one page. */
export async function ocrScreenshot(buffer) {
  return ocrScreenshots([{ buffer, originalname: "screenshot.png" }]);
}
