# Setup guide

## Prerequisites

- Node.js 20+
- Python 3.11+
- Docker Desktop (for PostgreSQL + Redis)
- Tesseract OCR (bundled in the NLP Docker image; install locally for non-Docker dev:
  `sudo apt install tesseract-ocr tesseract-ocr-msa` or `brew install tesseract tesseract-lang`)

## 1. Environment files

```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp nlp-service/.env.example nlp-service/.env
cp frontend/.env.example frontend/.env
```

Fill in `SERPER_API_KEY` (free at serper.dev) and `ANTHROPIC_API_KEY`.
These are only needed for the OSINT and narrative modules (FYP2) — the NLP and
price modules run without them.

## 2. Database + Redis

```bash
docker compose up -d db redis
# schema.sql runs automatically on first boot; then seed:
cd backend && npm install && npm run seed
```

## Ports

| Service | Port | URL |
| --- | ---: | --- |
| Frontend | 5173 | http://localhost:5173 |
| Backend API | 4000 | http://localhost:4000 |
| FastAPI NLP/OCR | 8000 | http://localhost:8000/docs |
| PostgreSQL | 5432 | Database only |
| Redis | 6379 | Cache only |

On Windows, after the one-time dependency installation, the complete local
stack can be started from the repository root with:

```powershell
.\scripts\run-dev.ps1
```

## 3. Run the three services (three terminals)

```bash
# Backend API
cd backend && npm run dev            # http://localhost:4000

# NLP service
cd nlp-service && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload        # http://localhost:8000

# Frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## 4. Verify

```bash
curl http://localhost:4000/api/health
curl http://localhost:8000/health
curl -X POST http://localhost:8000/classify \
  -H 'Content-Type: application/json' \
  -d '{"text":"byr deposit dulu, owner overseas","language":"auto"}'
```

## Tests

```bash
cd backend && npm test           # scoring engine unit tests
cd nlp-service && pytest         # normaliser + red-flag unit tests
```

## Notes

- The classifier's weights are not in the repository (`nlp-service/models/` is
  gitignored). The deployed model must be placed at
  `nlp-service/models/xlm-roberta-scam-v3-run1/` (it is trained in Colab with
  `nlp-service/train_colab_v3.ipynb`), and `nlp-service/.env` must point at it:
  `FINETUNED_MODEL_DIR=./models/xlm-roberta-scam-v3-run1`. Without the weights
  the service still runs end to end, and `/classify` reports
  `status: "model_unavailable"` with a neutral 0.5 that the backend leaves out of
  the score. The model's evaluation is in `docs/MODEL_EVALUATION.md`.
- Everything marked `TODO(FYP2)` is scaffolded but belongs to the second semester.
