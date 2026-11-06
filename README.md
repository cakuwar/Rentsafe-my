# RentSafe MY

An integrated, explainable rental-scam risk-scoring platform for the Malaysian
market. A user submits a rental listing (as text or a WhatsApp screenshot) and
RentSafe MY returns a single **0–100 risk score**, a component breakdown, and a
plain-language bilingual (BM/EN) explanation.

The score combines three independent signals:

| Signal | Weight | Module |
| --- | --- | --- |
| NLP scam-text classification | ≤ 60 | Shortform Normaliser + two-stage transformer |
| OSINT complaint search | ≤ 25 | Serper.dev web-intelligence search |
| Price anomaly | ≤ 15 | KL/Selangor stratified baseline comparison |

> Score computation is **fully deterministic**. The LLM only *explains* the
> pre-computed score — it can never inflate or deflate it.

## Architecture (three tiers + NLP microservice)

```
                +------------------------+
   Browser ---> |  React 18 + Tailwind    |  (frontend, port 5173)
                +-----------+------------+
                            |  REST
                            v
                +------------------------+       +------------------+
                |  Node.js + Express API  | <---> |  PostgreSQL 15   |
                |  (backend, port 4000)   |       |  + Redis (cache) |
                +-----+-------------+-----+       +------------------+
                      |             |
       internal REST  |             |  Serper.dev + Gemini (judge) + OpenAI (narrative)
                      v             v
          +------------------------+
          |  Python 3.11 + FastAPI  |  NLP service (port 8000)
          |  Normaliser · L1 · L2   |
          |  · OCR                   |
          +------------------------+
```

## Tech stack

- **Frontend:** React 18, Vite, Tailwind CSS, i18next (BM/EN)
- **Backend:** Node.js, Express, pg, ioredis, zod
- **NLP service:** Python 3.11, FastAPI, PyTorch, HuggingFace Transformers, Tesseract + Pillow
- **Data:** PostgreSQL 15 (price baseline, saved results without personal data), Redis (cache)
- **External:** Serper.dev / SerpApi (OSINT search), Google Gemini (OSINT judge), OpenAI `gpt-4o-mini` (narrative; Gemini or Claude can write it instead)
- **Running it:** locally, with PostgreSQL and Redis in Docker. The NLP service is also packaged as a Hugging Face Docker Space (`nlp-service/README.md`); the backend and frontend are not deployed.

## Getting started

### Local ports

| Service | Port | Open in browser? |
| --- | ---: | --- |
| Frontend | 5173 | Yes: `http://localhost:5173` |
| Node backend | 4000 | Yes: `http://localhost:4000/api/docs` (Swagger UI), `/api/health` |
| FastAPI NLP/OCR | 8000 | Yes: `http://localhost:8000/docs` |
| PostgreSQL | 5432 | No, database connection only |
| Redis | 6379 | No, cache connection only |

### Easiest Windows command

After installing dependencies once, run this from the project root:

```powershell
.\scripts\run-dev.ps1
```

This starts PostgreSQL and Redis with Docker, then opens separate terminals for
the backend, NLP/OCR service, and frontend.

To let UAT testers use it from their own devices, `.\scripts\run-uat.ps1`
does the same and then shares the frontend on a public Cloudflare tunnel link
(`docs/SETUP.md` §5).

```bash
# 1. clone, then copy env templates
cp .env.example .env
cp backend/.env.example backend/.env
cp nlp-service/.env.example nlp-service/.env
cp frontend/.env.example frontend/.env

# 2. bring up Postgres + Redis (and optionally all services) with Docker
docker compose up -d db redis

# 3. once, and after pulling new migrations: bring the database up to date
cd backend && npm install && npm run migrate && npm run seed

# 4. run each service (separate terminals)
cd backend && npm run dev                          # http://localhost:4000
cd nlp-service && pip install -r requirements.txt && uvicorn app.main:app --reload  # http://localhost:8000
cd frontend && npm install && npm run dev          # http://localhost:5173
```

See `docs/SETUP.md` for full details and `docs/API_SPEC.md` for endpoints.

## Repository layout

```
rentsafe-my/
├── backend/        Node.js + Express API (scoring engine, OSINT, price, LLM)
├── nlp-service/    Python FastAPI NLP microservice (normaliser, L1, L2, OCR)
├── frontend/       React 18 + Tailwind SPA
├── database/       SQL schema, migrations, seeds
├── data/           Datasets (raw scam/legit, synthetic, processed)
├── docs/           Architecture, API spec, setup, NLP layers, model evaluation
└── scripts/        Dev / data-collection helper scripts
```

## FYP roadmap

- **FYP1 (Weeks 1–14):** setup, dataset v1.0, Shortform Normaliser, NLP classifier (F1 ≥ 0.80), price-anomaly module.
- **FYP2 (Weeks 15–28):** OSINT module, scoring engine, LLM narrative, React frontend + OCR, testing + UAT.

**Status (November 2026).** Every module is implemented and tested: normaliser,
layer 1 red flags, layer 2 classifier, OCR, OSINT search with the LLM judge,
price anomaly, scoring engine, narrative, saved results and the bilingual
frontend. The classifier's evaluation, including a 15-case blind test of the
whole system, is in `docs/MODEL_EVALUATION.md`. Not done yet: user acceptance
testing with real users.
