---
title: RentSafe MY NLP
emoji: 🏠
colorFrom: green
colorTo: blue
sdk: docker
app_port: 8000
pinned: false
---

# RentSafe MY NLP service

The FastAPI microservice behind RentSafe MY, which scores Malaysian rental
conversations for scam risk.

- `POST /classify`: layer-1 red flags plus the fine-tuned XLM-RoBERTa scam probability
- `POST /ocr`: conversation text from WhatsApp screenshots (Tesseract, English + Malay)
- `GET /health`: liveness check, `{"status": "ok"}`
- `GET /docs`: interactive API docs

## Configuration

| Name | Kind | Value |
|---|---|---|
| `FINETUNED_MODEL_DIR` | variable | Hub repo id of the classifier (e.g. `cakuwar/rentsafe-xlmr-v3`) or a local folder |
| `HF_TOKEN` | secret | Read token; needed only when the model repo is private |

The weights are not part of the image. They download from the Hub each time the
server starts, before it accepts requests, so a (re)start takes a minute or two.
If loading fails the server still starts, and the next `/classify` retries once.

This Space is deployed from the `nlp-service/` folder of the RentSafe MY
monorepo. Make changes there, not here.
