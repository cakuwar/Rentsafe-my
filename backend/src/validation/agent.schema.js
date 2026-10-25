// Agent details a renter can type in (PRD "Input C"), shared by
// POST /api/analyze and POST /api/search. An empty string means "not given".
import { z } from "zod";
import { normalisePhone } from "../services/metadata.service.js";

export const optionalText = (max) =>
  z
    .string()
    .trim()
    .max(max)
    .optional()
    .transform((value) => value || undefined);

export const agentFields = z.object({
  name: optionalText(120),
  phone: optionalText(30).refine((value) => !value || normalisePhone(value) !== null, {
    message: "phone must be a Malaysian mobile number, e.g. 012-345 6789",
  }),
  ren: optionalText(20),
  company: optionalText(120),
});
