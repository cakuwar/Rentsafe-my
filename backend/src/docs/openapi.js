// OpenAPI 3 description of the backend, served by Swagger UI at /api/docs.
// docs/API_SPEC.md is the prose reference; keep the two in step when a route
// or response shape changes.

const agentFields = {
  name: { type: "string", maxLength: 120, example: "Ahmad Faizal", description: "Agent's name. Searched only when it has 2+ words." },
  phone: { type: "string", maxLength: 30, example: "012-345 6789", description: "Malaysian mobile number, any common spelling (+60 12-345 6789, 0123456789, ...)." },
  ren: { type: "string", maxLength: 20, example: "REN 12345", description: "Registration number with its REN / PEA / E prefix. Digits alone are not searched." },
  company: { type: "string", maxLength: 120, example: "Maju Jaya Realty Sdn Bhd", description: "Searched only when 2+ words remain after removing Sdn Bhd / Bhd / Berhad." },
};

// The "Listing details" form — the only source of the rent (never parsed
// from the chat). Every field may be blank: what the stratum still needs comes
// back as price status missing_input, not a 400.
const propertyFields = {
  price: { type: "number", example: 1200, description: "Monthly rent in RM, > 0 and <= 100,000. \"RM1,500\", \"1,500\" and \"RM 1 500\" are accepted." },
  area: { type: "string", maxLength: 60, example: "Wangsa Maju", description: "A canonical area name from GET /api/price/areas (trimmed, any case). Anything else is price status unknown_area; a plain two-state name (\"Cheras\") gets the hint \"Cheras (KL) or Cheras (Selangor)\"." },
  propertyType: { type: "string", enum: ["condo", "apartment", "flat", "landed", "room", "studio"], description: "Form labels: Studio -> studio (compared as a 0-bedroom condo); Condo / Serviced residence -> condo; Apartment -> apartment; Flat / PPR -> flat; Landed -> landed (always no_baseline); Room -> room + roomType." },
  bedrooms: { type: "integer", minimum: 0, maximum: 20, example: 2, description: "Required for condo, apartment, flat and landed; ignored for room and studio. 5+ is compared as 4; \"4+\" is accepted as 4." },
  roomType: { type: "string", enum: ["master", "common", "middle", "single"], description: "Required when propertyType is room; ignored otherwise. Middle and single are compared as common." },
};

const validationError = {
  description: "Validation failed",
  content: { "application/json": { schema: { $ref: "#/components/schemas/ValidationError" } } },
};

export const openapiSpec = {
  openapi: "3.0.3",
  info: {
    title: "RentSafe MY backend",
    version: "0.1.0",
    description:
      "Rental-scam risk scoring for the Malaysian market. The score is deterministic: "
      + "NLP (max 60) + OSINT web search (max 25) + price anomaly (max 15). A signal that "
      + "could not be scored is excluded, not counted as 0.\n\n"
      + "The NLP/OCR microservice has its own docs at http://localhost:8000/docs.\n\n"
      + "**Note:** `POST /api/search` and `POST /api/analyze` spend paid web searches "
      + "(SerpApi free plan: 250 a month). Repeat lookups of the same details are cached for 24 h.",
  },
  servers: [{ url: "/", description: "This server" }],
  tags: [
    { name: "Health" },
    { name: "Analysis", description: "Full risk analysis of a rental conversation" },
    { name: "Public search", description: "Look an agent up on the public web (OSINT)" },
    { name: "Price", description: "Compare a rent with the KL / Selangor baseline" },
    { name: "Saved results", description: "Results of earlier analyses, without personal data" },
  ],
  paths: {
    "/api/health": {
      get: {
        tags: ["Health"],
        summary: "Liveness check",
        responses: {
          200: {
            description: "Backend is up",
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  properties: {
                    status: { type: "string", example: "ok" },
                    service: { type: "string", example: "rentsafe-backend" },
                    timestamp: { type: "string", format: "date-time" },
                  },
                },
              },
            },
          },
        },
      },
    },
    "/api/search": {
      post: {
        tags: ["Public search"],
        summary: "Search the public web for scam reports about an agent",
        description:
          "Runs up to 4 Google queries (phone, name, REN, company) and scores what it finds "
          + "by source: news 12, forum 8, social 5 (each tier once, max 25). Returns the "
          + "findings and a disclaimer, with **no overall risk score**.\n\n"
          + "Each result passes keyword rules (negation, impersonation notices, social-media "
          + "company mentions), then — when configured — an LLM judge: only a `complaint` at "
          + "confidence ≥ 0.6 scores. Everything else is listed in `context` with the reason, "
          + "and an impersonation notice adds a `warnings` entry (no points).\n\n"
          + "Needs a valid Malaysian mobile number **or** a name of 2+ words. "
          + "Rate-limited to 10 requests per 15 minutes per IP.",
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/SearchRequest" },
              examples: {
                phoneOnly: { summary: "Phone only (1 search)", value: { phone: "012-345 6789" } },
                everything: {
                  summary: "All details (up to 4 searches)",
                  value: { phone: "012-345 6789", name: "Ahmad Faizal", ren: "REN 12345", company: "Maju Jaya Realty Sdn Bhd" },
                },
              },
            },
          },
        },
        responses: {
          200: {
            description: "Search ran (`status: ok`). `points: 0` means nothing was found, not that the agent is safe.",
            content: { "application/json": { schema: { $ref: "#/components/schemas/SearchResponse" } } },
          },
          400: validationError,
          429: {
            description: "Daily search quota used up (`status: quota_exceeded`), or too many requests from this IP",
            content: { "application/json": { schema: { $ref: "#/components/schemas/SearchResponse" } } },
          },
          503: {
            description: "No search key configured (`not_configured`) or every query failed (`search_failed`)",
            content: { "application/json": { schema: { $ref: "#/components/schemas/SearchResponse" } } },
          },
        },
      },
    },
    "/api/analyze": {
      post: {
        tags: ["Analysis"],
        summary: "Analyse a pasted conversation or listing",
        description:
          "Runs NLP, OSINT and price checks and combines them into a 0-100 score. Agent "
          + "details are optional; blank fields fall back to what can be parsed from the text. The "
          + "price check uses only `property` (the Listing details form): absent or partial, price is "
          + "missing_input and left out of the score.",
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/AnalyzeRequest" },
              example: {
                text: "Owner: Unit available, RM900 only. I'm overseas so no viewing, transfer deposit first and I courier the keys.\nRenter: Can I see the unit?\nOwner: Cannot, many people want it, pay today to secure.",
                language: "auto",
                agent: { phone: "012-345 6789" },
                property: { price: 900, area: "Wangsa Maju", propertyType: "condo", bedrooms: 2 },
              },
            },
          },
        },
        responses: {
          200: {
            description: "Analysis result. Render `riskBand` and `message`, not `riskScore` alone: it is null when nothing could be scored.",
            content: { "application/json": { schema: { $ref: "#/components/schemas/AnalyzeResponse" } } },
          },
          400: validationError,
          503: {
            description: "The NLP service is not responding",
            content: { "application/json": { schema: { $ref: "#/components/schemas/Error" } } },
          },
        },
      },
    },
    "/api/analyze/screenshot": {
      post: {
        tags: ["Analysis"],
        summary: "Analyse WhatsApp screenshots",
        description:
          "OCRs up to 20 screenshots (5 MB each) **in upload order**, stitches them into one "
          + "conversation, then runs the same analysis as `/api/analyze`. Upload pages in "
          + "chronological order.",
        requestBody: {
          required: true,
          content: {
            "multipart/form-data": {
              schema: {
                type: "object",
                required: ["files"],
                properties: {
                  files: { type: "array", items: { type: "string", format: "binary" }, description: "Screenshots, oldest first" },
                  language: { type: "string", enum: ["auto", "ms", "en"], default: "auto" },
                  agentName: agentFields.name,
                  agentPhone: agentFields.phone,
                  renNumber: agentFields.ren,
                  company: agentFields.company,
                  price: propertyFields.price,
                  area: propertyFields.area,
                  bedrooms: propertyFields.bedrooms,
                  propertyType: propertyFields.propertyType,
                  roomType: propertyFields.roomType,
                },
              },
            },
          },
        },
        responses: {
          200: {
            description: "Analysis result plus the OCR output",
            content: {
              "application/json": {
                schema: {
                  allOf: [
                    { $ref: "#/components/schemas/AnalyzeResponse" },
                    {
                      type: "object",
                      properties: {
                        ocrText: { type: "string" },
                        ocr: {
                          type: "object",
                          properties: {
                            pageCount: { type: "integer" },
                            messages: { type: "integer", description: "Message count; below 6 the NLP signal returns insufficient_context" },
                            pages: { type: "array", items: { type: "object" } },
                          },
                        },
                      },
                    },
                  ],
                },
              },
            },
          },
          400: validationError,
          413: { description: "Too many screenshots or one over 5 MB", content: { "application/json": { schema: { $ref: "#/components/schemas/Error" } } } },
          422: { description: "No text could be read from the screenshots", content: { "application/json": { schema: { $ref: "#/components/schemas/Error" } } } },
        },
      },
    },
    "/api/price/areas": {
      get: {
        tags: ["Price"],
        summary: "Areas and strata in the price baseline",
        description: "For the area / type dropdowns. A stratum is scored only when `scorable` (5+ listings from 3+ buildings).",
        responses: {
          200: {
            description: "Strata per area",
            content: { "application/json": { schema: { $ref: "#/components/schemas/PriceAreas" } } },
          },
          503: { description: "The baseline could not be read", content: { "application/json": { schema: { $ref: "#/components/schemas/Error" } } } },
        },
      },
    },
    "/api/price/check": {
      get: {
        tags: ["Price"],
        summary: "Compare one rent with its stratum",
        description: "The same check `/api/analyze` runs, with the same form contract. A field not filled in "
          + "gives status missing_input (200); a malformed value is a 400. No overall risk score.",
        parameters: ["price", "area", "propertyType", "bedrooms", "roomType"].map((name) => ({
          name, in: "query", required: false, schema: propertyFields[name],
        })),
        responses: {
          200: {
            description: "Any status but baseline_unavailable",
            content: { "application/json": { schema: { allOf: [
              { $ref: "#/components/schemas/PriceResult" },
              { type: "object", properties: { disclaimer: { type: "object", properties: { en: { type: "string" }, ms: { type: "string" } } } } },
            ] } } },
          },
          400: validationError,
          503: { description: "baseline_unavailable", content: { "application/json": { schema: { $ref: "#/components/schemas/PriceResult" } } } },
        },
      },
    },
    "/api/listings/{id}": {
      get: {
        tags: ["Saved results"],
        summary: "Fetch a saved analysis result",
        description: "Every analysis is saved under its `listingId`. Only what the system produced is kept: score, "
          + "band, components, the facts the explanation was written from, the explanation, and the Listing details "
          + "form. Never the conversation, nor the agent's name, phone, REN number or company.",
        parameters: [{ name: "id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: {
          200: {
            description: "The saved result",
            content: { "application/json": { schema: { type: "object", properties: {
              listingId: { type: "string", format: "uuid" },
              createdAt: { type: "string", format: "date-time" },
              sourceType: { type: "string", enum: ["text", "screenshot"] },
              riskScore: { type: "integer", nullable: true, description: "null when the band is UNKNOWN" },
              riskBand: { type: "string", enum: ["LOW", "MODERATE", "HIGH", "CRITICAL", "UNKNOWN"] },
              components: { type: "object", nullable: true },
              facts: { type: "object", description: "The explanation's input: band, score, red-flag labels, price figures, OSINT counts" },
              narrative: { type: "object", nullable: true, properties: {
                en: { type: "string" }, ms: { type: "string" }, provider: { type: "string" }, model: { type: "string" }, promptVersion: { type: "string" },
              } },
              property: { type: "object", properties: {
                price: { type: "number", nullable: true }, area: { type: "string", nullable: true },
                bedrooms: { type: "integer", nullable: true }, propertyType: { type: "string", nullable: true },
              } },
            } } } },
          },
          400: { description: "The id is not a UUID" },
          404: { description: "No result saved under this id" },
          503: { description: "The database cannot be reached" },
        },
      },
    },
  },
  components: {
    schemas: {
      PropertyDetails: {
        type: "object",
        description: "All optional. A blank field falls back to what can be parsed from the text.",
        properties: propertyFields,
      },
      PriceBaseline: {
        type: "object",
        properties: {
          median: { type: "number" }, p25: { type: "number", nullable: true }, p75: { type: "number", nullable: true },
          sampleSize: { type: "integer" }, buildings: { type: "integer" },
          sources: { type: "array", items: { type: "string", enum: ["kaggle", "scraped", "manual"] } },
          adjustmentFactor: { type: "number", nullable: true, description: "Time factor applied to the Kaggle (Mudah ~2023) rows; mixes time and platform" },
          vintages: { type: "object", additionalProperties: { type: "string" }, example: { kaggle: "2023 (inferred)", scraped: "2026-08-27" } },
          status: { type: "string", enum: ["scorable", "few-bldg", "thin", "sparse"] },
        },
      },
      PriceResult: {
        type: "object",
        description: "evidence.price. Anything but status ok has anomalyFraction and points null: excluded from the score, never a clean 0.",
        properties: {
          status: { type: "string", enum: ["ok", "missing_input", "unknown_area", "no_baseline", "thin_baseline", "baseline_unavailable"] },
          anomalyFraction: { type: "number", nullable: true, description: "points / 15" },
          points: { type: "integer", nullable: true, enum: [0, 10, 15] },
          max: { type: "integer", example: 15 },
          tier: { type: "string", nullable: true, enum: ["within_range", "suspicious", "highly_suspicious"], description: "d < 30% within_range (0); 30-45% suspicious (10); > 45% highly_suspicious (15)" },
          deviation: { type: "number", nullable: true, description: "(median - price) / median; negative = above market" },
          guard: { type: "string", nullable: true, enum: ["at_or_above_p25", "below_floor"], description: "at_or_above_p25: the p25 guard zeroed it (D3). below_floor: under the minimum-rent floor (D10) — 15 points, no baseline consulted, deviation and baseline null" },
          listedPrice: { type: "number", nullable: true },
          stratum: { type: "object", nullable: true, properties: { area: { type: "string" }, propertyType: { type: "string" }, bedrooms: { type: "integer" }, roomType: { type: "string" } } },
          baseline: { allOf: [{ $ref: "#/components/schemas/PriceBaseline" }], nullable: true },
          missing: { type: "array", items: { type: "string", enum: ["price", "area", "propertyType", "bedrooms", "roomType"] }, description: "Form fields not filled in (missing_input)" },
          rule: { type: "object", properties: { thresholdPct: { type: "integer", example: 30 }, highThresholdPct: { type: "integer", example: 45 }, p25Guard: { type: "boolean" }, minListings: { type: "integer" }, minBuildings: { type: "integer" }, rentFloor: { type: "object", description: "D10 minimum-rent floor, RM/month", properties: { wholeUnit: { type: "integer", example: 300 }, room: { type: "integer", example: 150 } } } } },
          message: { type: "object", nullable: true, properties: { en: { type: "string" }, ms: { type: "string" } } },
        },
      },
      PriceAreas: {
        type: "object",
        description: "Every canonical area, sorted by state then name, even with no scorable stratum.",
        properties: {
          areas: { type: "array", items: { type: "object", properties: {
            name: { type: "string", example: "Cheras (KL)" },
            state: { type: "string", enum: ["KL", "Selangor"] },
            strata: { type: "array", items: { type: "object", properties: {
              propertyType: { type: "string", enum: ["condo", "apartment", "flat", "landed", "room"] },
              bedrooms: { type: "integer", description: "Whole units" },
              roomType: { type: "string", enum: ["master", "common"], description: "Rooms" },
              sampleSize: { type: "integer" }, buildings: { type: "integer" },
              scorable: { type: "boolean", description: ">= 5 listings from >= 3 buildings" },
            } } },
          } } },
          dataNote: { type: "object", properties: { en: { type: "string" }, ms: { type: "string" } }, description: "Where the prices come from and how old they are" },
        },
      },
      AgentDetails: {
        type: "object",
        description: "All optional. An empty string counts as not given.",
        properties: agentFields,
      },
      SearchRequest: {
        type: "object",
        description: "A valid phone or a 2+ word name is required.",
        properties: agentFields,
      },
      AnalyzeRequest: {
        type: "object",
        required: ["text"],
        properties: {
          text: { type: "string", minLength: 20, description: "The conversation or listing text" },
          language: { type: "string", enum: ["auto", "ms", "en"], default: "auto" },
          agent: { $ref: "#/components/schemas/AgentDetails" },
          property: { $ref: "#/components/schemas/PropertyDetails" },
        },
      },
      OsintEvidence: {
        type: "object",
        properties: {
          title: { type: "string" },
          link: { type: "string" },
          snippet: { type: "string" },
          domain: { type: "string", example: "forum.lowyat.net" },
          tier: { type: "string", enum: ["news", "forum", "social"] },
          query: {
            type: "string",
            enum: ["phone", "name", "ren", "company"],
            description: "The strongest identifier found in this result's text (phone > ren > name > company)",
          },
          foundBy: {
            type: "string",
            enum: ["phone", "name", "ren", "company"],
            description: "The search query that returned this result (may differ from `query`)",
          },
          matched: {
            type: "object",
            properties: {
              terms: { type: "array", items: { type: "string" }, example: ["scam", "scammed"] },
              ignored: {
                type: "array",
                description: "Keyword hits dropped because a negation or generic cue came just before them",
                items: { type: "object", properties: { term: { type: "string" }, cue: { type: "string" } } },
                example: [{ term: "scam", cue: "risiko" }],
              },
            },
          },
          label: { type: "string", enum: ["complaint", "impersonation_notice", "marketing_or_generic", "unrelated"], description: "The LLM judge's label (absent when the judge did not run)" },
          confidence: { type: "number", nullable: true, minimum: 0, maximum: 1 },
          reason: { type: "string", nullable: true },
          judgeMissing: { type: "boolean", description: "The judge returned no verdict for this item; treated as unrelated" },
          sourceKey: { type: "string", description: "Evidence only: the group, account or site it came from", example: "facebook:group:1107732539961661" },
        },
      },
      OsintContextItem: {
        description: "A result that mentions the identifier but scored no points, and why.",
        allOf: [
          { $ref: "#/components/schemas/OsintEvidence" },
          {
            type: "object",
            properties: {
              tier: { type: "string", enum: ["news", "forum", "social", "portal"] },
              type: {
                type: "string",
                enum: [
                  "listing_portal", "generic_mention", "impersonation_notice", "impersonation_mention",
                  "social_mention", "unverified_mention", "unjudged", "marketing_or_generic", "unrelated",
                  "low_confidence_complaint", "name_only_match",
                ],
              },
            },
          },
        ],
      },
      OsintWarning: {
        type: "object",
        description: "Never adds points. At most one.",
        properties: {
          type: { type: "string", enum: ["impersonation_notice"] },
          scope: {
            type: "string",
            enum: ["agent", "company"],
            description: "agent: a notice names this agent (phone, REN or name); company: notices about the company only",
          },
          company: { type: "string", nullable: true },
          links: { type: "array", items: { type: "string" } },
          en: { type: "string" },
          ms: { type: "string" },
        },
      },
      OsintResult: {
        type: "object",
        properties: {
          status: {
            type: "string",
            enum: ["ok", "no_identifier", "not_configured", "quota_exceeded", "search_failed"],
            description: "Anything but `ok` means the signal is excluded from the score (riskFraction null).",
          },
          provider: { type: "string", enum: ["serper", "serpapi"], nullable: true },
          riskFraction: { type: "number", nullable: true, minimum: 0, maximum: 1, description: "points / 25" },
          points: { type: "integer", nullable: true, maximum: 25 },
          max: { type: "integer", example: 25 },
          breakdown: {
            type: "object",
            properties: {
              news: { type: "integer", enum: [0, 12] },
              forum: { type: "integer", enum: [0, 8] },
              social: { type: "integer", enum: [0, 5] },
            },
          },
          strongHit: {
            type: "boolean",
            description: "Lifts the MODERATE band cap: a phone/REN complaint on a news or forum source, or phone/REN complaints from 3+ distinct social sources",
          },
          strongHitReason: { type: "string", nullable: true, enum: ["news_or_forum", "social_corroboration"] },
          corroboration: {
            type: "object",
            description: "Distinct social sources (groups / accounts) with phone or REN complaints. Several posts in one group count once.",
            properties: {
              sources: { type: "integer", example: 4 },
              threshold: { type: "integer", example: 3 },
              keys: { type: "array", items: { type: "string" }, example: ["facebook:group:1107732539961661", "threads:someuser"] },
            },
          },
          warnings: { type: "array", items: { $ref: "#/components/schemas/OsintWarning" } },
          verifier: {
            type: "string",
            nullable: true,
            enum: ["llm", "rules_only"],
            description: "How evidence was classified. rules_only with verifierProvider null: the judge is off (no key, no GEMINI_MODEL, or OSINT_LLM_VERIFY=false). rules_only with a provider: the judge call failed.",
          },
          verifierProvider: { type: "string", nullable: true, enum: ["gemini", "anthropic"] },
          verifierVersion: { type: "string", example: "v2", description: "Judge prompt version" },
          verifierError: {
            type: "string",
            nullable: true,
            enum: ["timeout", "429", "invalid_model", "unavailable", "bad_json", "other"],
            description: "Why the judge call failed (verifier is then rules_only)",
          },
          verifierRetried: { type: "boolean", description: "The judge was retried once after a 5xx (unavailable)" },
          judgeCandidates: { type: "integer", description: "Candidates actually sent to the judge (max 10)" },
          identity: {
            type: "object",
            properties: {
              phone: { type: "string", nullable: true, example: "0123456789" },
              name: { type: "string", nullable: true },
              ren: { type: "string", nullable: true, example: "REN 12345" },
              company: { type: "string", nullable: true },
              source: { type: "string", nullable: true, enum: ["form", "text"] },
            },
          },
          queries: { type: "array", items: { type: "string", enum: ["phone", "name", "ren", "company"] } },
          failedQueries: { type: "integer" },
          evidence: { type: "array", items: { $ref: "#/components/schemas/OsintEvidence" } },
          context: {
            type: "array",
            description: "Results that mention the identifier but scored nothing, each with the reason in `type`.",
            items: { $ref: "#/components/schemas/OsintContextItem" },
          },
          cached: { type: "boolean" },
          fetchedAt: { type: "string", format: "date-time", nullable: true },
        },
      },
      SearchResponse: {
        allOf: [
          { $ref: "#/components/schemas/OsintResult" },
          {
            type: "object",
            properties: {
              disclaimer: {
                type: "object",
                properties: { en: { type: "string" }, ms: { type: "string" } },
              },
            },
          },
        ],
      },
      Component: {
        type: "object",
        properties: {
          points: { type: "integer" },
          max: { type: "integer" },
          included: { type: "boolean" },
        },
      },
      AnalyzeResponse: {
        type: "object",
        properties: {
          listingId: { type: "string", format: "uuid" },
          sourceType: { type: "string", enum: ["text", "screenshot"] },
          language: { type: "string" },
          riskScore: { type: "integer", nullable: true, minimum: 0, maximum: 100, description: "null when no signal could be scored" },
          maxPossibleScore: { type: "integer", description: "The ceiling given which signals were usable" },
          riskBand: { type: "string", enum: ["LOW", "MODERATE", "HIGH", "CRITICAL", "UNKNOWN"] },
          riskColour: { type: "string", enum: ["green", "yellow", "orange", "red", "grey"] },
          bandCap: {
            type: "object",
            nullable: true,
            description: "Set when a high model score had no red flag (and no strong OSINT hit) behind it",
            properties: {
              applied: { type: "boolean" },
              reason: { type: "string", example: "no_red_flags" },
              uncappedScore: { type: "integer" },
              uncappedBand: { type: "string" },
            },
          },
          modelProbability: { type: "number", nullable: true },
          components: {
            type: "object",
            properties: {
              nlp: { $ref: "#/components/schemas/Component" },
              osint: { $ref: "#/components/schemas/Component" },
              price: { $ref: "#/components/schemas/Component" },
            },
          },
          excludedSignals: { type: "array", items: { type: "string", enum: ["nlp", "osint", "price"] } },
          nlpStatus: { type: "string", nullable: true, enum: ["ok", "insufficient_context", "model_unavailable"] },
          nlpConfidence: { type: "string", nullable: true },
          message: {
            type: "object",
            nullable: true,
            properties: { en: { type: "string" }, ms: { type: "string" } },
          },
          evidenceSupport: { type: "string", enum: ["corroborated", "partial", "none", "contradicted", "consistent", "not_scored"] },
          narrative: { type: "string", nullable: true },
          metadata: { type: "object", nullable: true, description: "Parsed and form-supplied listing details" },
          evidence: {
            type: "object",
            properties: {
              redFlags: { type: "array", items: { type: "string" } },
              details: { type: "array", items: { type: "object" } },
              patterns: { type: "array", items: { type: "object" } },
              legitSignals: { type: "array", items: { type: "object" }, description: "Context only, never evidence of safety" },
              osint: { allOf: [{ $ref: "#/components/schemas/OsintResult" }], nullable: true },
              price: { allOf: [{ $ref: "#/components/schemas/PriceResult" }], nullable: true },
            },
          },
        },
      },
      ValidationError: {
        type: "object",
        properties: {
          error: { type: "string", example: "Validation failed" },
          details: {
            type: "array",
            items: {
              type: "object",
              properties: {
                field: { type: "string", example: "phone" },
                message: { type: "string", example: "phone must be a Malaysian mobile number, e.g. 012-345 6789" },
              },
            },
          },
        },
      },
      Error: {
        type: "object",
        properties: {
          error: { type: "string" },
          message: { type: "string" },
        },
      },
    },
  },
};
