"""FastAPI entry point for the RentSafe MY NLP microservice.

Endpoints:
  POST /classify  - normalise text, then run both layers concurrently
  POST /ocr       - extract text from one or more WhatsApp screenshots
  GET  /health    - liveness only; never loads the model

/classify runs the two layers independently and returns both:

  layer 1  regex red-flag detection -> evidence for the LLM narrator to explain
           to the renter. Produces no score.
  layer 2  the fine-tuned transformer -> scam_probability, from the model alone.

Red flags add nothing to scam_probability. The backend combines them once, in
aggregateScore, where the documented formula weighs this probability at 60
alongside OSINT and price.

The layer-2 model is loaded at startup (`lifespan`), before the server accepts
requests. If that fails the server starts anyway: /health, /docs, /ocr and
layer 1 do not need the model, and /classify tries loading it once more.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from uvicorn.logging import DefaultFormatter
from app.schemas.io import (
    ClassifyRequest,
    ClassifyResponse,
    OCRMessage,
    OCRPageResult,
    OCRResponse,
)
from app.normaliser.normaliser import normalise
from app.layer1.red_flags import analyse as l1_analyse
from app.layer2.classifier import classify as l2_classify, count_turns, load as l2_load
from app.ocr.ocr import (
    combine_pages,
    images_bytes_to_text,
    screenshots_to_conversation,
)
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool

# Uvicorn configures only its own loggers. Without a handler here, the service's
# "rentsafe.*" INFO lines (model loading) were dropped and its errors printed
# with no level, so give them uvicorn's format to read as part of the same log.
_log = logging.getLogger("rentsafe")
if not _log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(DefaultFormatter("%(levelprefix)s %(name)s: %(message)s"))
    _log.addHandler(_handler)
    _log.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the layer-2 model before the server takes requests.

    Otherwise the first /classify pays for it, which on a fresh Space includes
    the Hub download. l2_load logs a failure and returns; it never raises, so a
    missing model cannot stop the server from starting.
    """
    await run_in_threadpool(l2_load)
    yield


app = FastAPI(title="RentSafe MY NLP Service", version="0.1.0", lifespan=lifespan)

#################################################################################
# ERROR HANDLING
#################################################################################

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    errors = []

    for error in exc.errors():
        location = tuple(error["loc"])

        if location == ("body", "text") and error["type"] == "missing":
          message = "Text listing cant be empty."

        elif (
            location == ("body", "text")
            and error["type"] == "string_too_short"
        ):
            input_value = error.get("input", "")

            if input_value == "":
                message = "Text listing can't be empty."
            elif len(input_value) == 1:
                message = "Text listing atleast 2 characters."
            else:
                message = "Text listing too short."

        else:
            message = error["msg"]

        errors.append({
            "field": ".".join(str(item) for item in location),
            "message": message,
        })
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation failed",
            "details": errors,
        },
    )

#################################################################################
# ENDPOINTS
#################################################################################
MAX_OCR_PAGES = 20


@app.get("/health")
async def health():
    """Liveness check: the server is up and answering.

    Deliberately touches neither the model nor anything else, so it answers even
    while layer 2 is unavailable. Whether the model loaded is in the startup log
    and in /classify's `layer2.status`.
    """
    return {"status": "ok"}


@app.post("/ocr", response_model=OCRResponse)
async def ocr_endpoint(files: list[UploadFile] = File(...)):
    """Extract text from one or more WhatsApp screenshots.

    A chat rarely fits in a single screenshot, so attach one `files` entry per
    page and the text is stitched into a single conversation. Pages are joined in
    the order given, which is the upload order and not filename order — "IMG_10"
    sorts before "IMG_2" as a string, so sorting here would scramble a chat.

    An unreadable page yields empty text and `ok: false` for that page instead of
    failing the whole request.

    Only `files` is accepted. Earlier revisions also took `file` and `image` as
    aliases, but Swagger UI posts the unused ones as empty strings, which failed
    validation and made the form unusable.
    """
    uploads = [upload for upload in files if upload is not None]

    if not uploads:
        raise HTTPException(
            status_code=422,
            detail="Attach at least one screenshot as 'files' (repeatable).",
        )
    if len(uploads) > MAX_OCR_PAGES:
        raise HTTPException(
            status_code=413,
            detail=f"Too many screenshots: {len(uploads)} (max {MAX_OCR_PAGES}).",
        )

    payloads = [await upload.read() for upload in uploads]
    # Tesseract is blocking and runs once per page, so keep it off the loop.
    result = await run_in_threadpool(screenshots_to_conversation, payloads)

    if result["method"] == "bubbles":
        turns = len(result["messages"])
    else:
        turns = count_turns(result["text"])

    return OCRResponse(
        extracted_text=result["text"],
        page_count=len(uploads),
        turns=turns,
        method=result["method"],
        messages=[OCRMessage(**message) for message in result["messages"]],
        pages=[
            OCRPageResult(
                filename=upload.filename,
                extracted_text=text,
                characters=len(text),
                ok=bool(text.strip()),
            )
            for upload, text in zip(uploads, result["page_texts"])
        ],
    )

@app.post("/classify", response_model=ClassifyResponse)
async def classify_endpoint(request: ClassifyRequest):
    """Normalise + classify listing text -> scam probability + red flags."""
    normalised_text = normalise(request.text)

    # The two layers are independent and run concurrently. Layer 1 produces
    # evidence for the narrator; layer 2 produces the probability. Neither feeds
    # the other, so a change to the red-flag patterns cannot move the score.
    
    # They read different text on purpose. Layer 1 wants the normalised form,
    # whose expansions its patterns rely on. Layer 2 wants the text as sent: the
    # model was fine-tuned on raw conversations, and normalising lowercases,
    # rewrites words and collapses the line breaks that mark turns, which shifts
    # the input away from its training distribution and hides the turn count.
    layer1_result, layer2_result = await asyncio.gather(
        run_in_threadpool(l1_analyse, normalised_text),
        run_in_threadpool(l2_classify, request.text, request.language),
    )

    return ClassifyResponse(
        normalised_text=normalised_text,
        red_flags=layer1_result["red_flags"],
        scam_probability=layer2_result["scam_probability"],
        layer1=layer1_result,
        layer2=layer2_result,
    )
