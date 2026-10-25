# Architecture

Three-tier web architecture with a separate Python NLP microservice.

```
 ┌─────────────────────────────────────────────────────────────┐
 │ Presentation:  React 18 + Tailwind (Vite)      :5173         │
 └───────────────┬─────────────────────────────────────────────┘
                 │ REST (JSON / multipart)
 ┌───────────────▼─────────────────────────────────────────────┐
 │ Application:   Node.js + Express               :4000         │
 │   pipeline.service  ── orchestrates everything               │
 │   ├─ metadata.service   (regex parse phone/price/area)       │
 │   ├─ nlp.service        ──► Python NLP service (internal)    │
 │   ├─ osint.service      ──► Serper.dev  (+ Redis cache)      │
 │   ├─ price.service      ──► PostgreSQL price_baseline        │
 │   ├─ scoring.service    (deterministic 60/25/15 aggregate)   │
 │   └─ llm.service        ──► Anthropic Claude Haiku           │
 └───────┬───────────────────────────┬─────────────────────────┘
         │ internal REST             │
 ┌───────▼──────────────┐    ┌───────▼──────────┐   ┌──────────┐
 │ NLP service (FastAPI)│    │ PostgreSQL 15    │   │ Redis 7  │
 │  normaliser  :8000   │    │ 5 tables         │   │ cache    │
 │  layer1 red flags    │    └──────────────────┘   └──────────┘
 │  layer2 transformers │
 │  ocr (Tesseract+PIL) │
 └──────────────────────┘
```

## Data flow (one analysis)

1. React posts listing text/screenshot to `POST /api/analyze`.
2. Backend parses metadata, then fires **three concurrent** calls:
   NLP classify, OSINT search, price-anomaly lookup.
3. `scoring.service` combines the three normalised confidences into a 0–100 score.
4. `llm.service` asks Claude Haiku to explain the **already-computed** score.
5. Result persisted to `listings`, returned to the frontend.

## Why the score/explanation split
The number is produced by auditable code; the LLM only narrates it. This keeps
the risk assessment verifiable (Arrieta et al. 2020) — the model cannot inflate
or deflate the score.

## Module → file map
| Module | Lives in |
| --- | --- |
| Shortform Normaliser | `nlp-service/app/normaliser/` |
| Layer 1 red flags | `nlp-service/app/layer1/red_flags.py` |
| Layer 2 transformers | `nlp-service/app/layer2/classifier.py` |
| OCR | `nlp-service/app/ocr/ocr.py` |
| OSINT / web intel | `backend/src/services/osint.service.js` |
| Price anomaly | `backend/src/services/price.service.js` |
| Risk scoring engine | `backend/src/services/scoring.service.js` |
| LLM narrative | `backend/src/services/llm.service.js` |
