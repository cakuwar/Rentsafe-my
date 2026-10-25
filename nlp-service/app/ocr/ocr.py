"""OCR pipeline (FYP2 — P10)."""

import io
import logging
import os
import re
from pathlib import Path

from PIL import Image, ImageOps
import pytesseract

from app import config

logger = logging.getLogger("rentsafe.ocr")

if config.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
elif os.name == "nt":
    windows_tesseract = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if windows_tesseract.exists():
        pytesseract.pytesseract.tesseract_cmd = str(windows_tesseract)

tessdata_dir = Path(config.TESSDATA_DIR).resolve()
if tessdata_dir.is_dir():
    os.environ.setdefault("TESSDATA_PREFIX", str(tessdata_dir))

def _preprocess(img: Image.Image) -> Image.Image:
    gray = img.convert("L")
    # if the image is mostly dark (WhatsApp dark mode), invert to dark-on-light.
    hist = gray.histogram()
    dark_pixels = sum(hist[:128])
    light_pixels = sum(hist[128:])
    if dark_pixels > light_pixels:
        gray = ImageOps.invert(gray)
    # boost contrast + simple binary threshold.
    gray = ImageOps.autocontrast(gray)
    return gray.point(lambda p: 255 if p > 140 else 0)

def image_bytes_to_text(raw: bytes) -> str:
    try:
        img = Image.open(io.BytesIO(raw))
        processed = _preprocess(img)
        text = pytesseract.image_to_string(
            processed,
            lang=config.TESSERACT_LANGS,
            config="--psm 6",
        )
        return text.strip()
    except Exception as e:
        logger.warning(f"OCR failed: {e}")
        return ""


def images_bytes_to_text(pages: list[bytes]) -> list[str]:
    """OCR several screenshots, returning one string per input.

    A failed page yields an empty string rather than raising, so one unreadable
    screenshot does not lose the text from the others.
    """
    return [image_bytes_to_text(raw) for raw in pages]


def _strip_page_chrome(pages: list[str]) -> list[str]:
    """Remove the header WhatsApp draws at the top of every screenshot.

    The status bar and the contact-name bar are not conversation, but they read
    as ordinary text to OCR — "€ ES En<name>RumahSe.. Th & i" was being glued
    onto the first real message of every page.

    They are found by **repetition**, not by pattern: the same header appears
    near the top of every page of one conversation, while a real message does
    not. That avoids having to recognise a contact name, which cannot be done in
    general and would only ever fit one chat.
    """
    head_depth = 3

    def key_of(line: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", line.lower())

    tops: dict[str, int] = {}
    for page in pages:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        for line in lines[:head_depth]:
            key = key_of(line)
            if key:
                tops[key] = tops.get(key, 0) + 1

    repeated = {key for key, count in tops.items() if count >= 2}

    def is_contact_name(line: str) -> bool:
        """A quoted reply is attributed to the contact, by the same name.

        WhatsApp prints the sender's name above the quoted text, and for the
        other party that is the name already in the header bar. Recognising it
        here stops the quote block being read as a message of its own, which
        would swallow the actual reply underneath it.

        Matched as a prefix because the header bar truncates the name
        ("En <name> Rumah Se... :") while the quote spells it out in full.
        """
        key = key_of(line)
        if not key or len(line) > 40:
            return False
        return any(
            key.startswith(header) or header.startswith(key)
            for header in repeated
            if len(header) >= 8
        )

    stripped = []
    for page in pages:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        keep = []
        for index, line in enumerate(lines):
            if index < head_depth and key_of(line) in repeated:
                continue
            if is_contact_name(line):
                continue
            keep.append(line)
        stripped.append("\n".join(keep))
    return stripped


def combine_pages(texts: list[str]) -> str:
    """Stitch per-screenshot text into a single conversation.

    Joined with newlines and in the order the pages were given, because layer 2
    counts conversation turns as non-blank lines and scores badly when it can
    only see a fragment. A chat spanning four screenshots is one conversation,
    and it has to reach the model that way.

    Overlapping captures are not de-duplicated: consecutive screenshots often
    repeat a message or two, but people also genuinely repeat themselves, and
    dropping a real repeated line is worse than carrying a duplicate.
    """
    return "\n".join(
        text for text in _strip_page_chrome(list(texts)) if text.strip()
    )

def screenshots_to_conversation(pages: list[bytes]) -> dict:
    """Turn uploaded screenshots into one conversation, attributed by speaker.

    Tries bubble segmentation first (app/ocr/bubbles.py): it finds each bubble
    from the image itself, which recovers who sent it and does not depend on
    OCR being able to read the clock. The result is written in the
    "Renter: ... / Owner: ..." form the classifier was trained on.

    Falls back to plain text OCR when segmentation finds no bubbles at all — a
    screenshot of something other than a chat, or an image too degraded for
    layout analysis. `method` says which path produced the result.
    """
    from app.ocr.bubbles import drop_media_text, segment, stitch

    images = []
    for raw in pages:
        try:
            images.append(Image.open(io.BytesIO(raw)))
        except Exception as error:  # an unreadable page is reported, not fatal
            logger.warning(f"could not open screenshot: {error}")
            images.append(None)

    segmented = []
    for image in images:
        if image is None:
            segmented.append([])
            continue
        try:
            segmented.append(segment(image, _preprocess))
        except Exception as error:
            logger.warning(f"bubble segmentation failed on a page: {error}")
            segmented.append([])

    if any(segmented):
        # Text printed inside photos is not a message (camera date stamps).
        segmented = drop_media_text(segmented)
        messages = stitch(segmented)
        labelled = "\n".join(
            f"{speaker.capitalize()}: {text}" for speaker, text in messages
        )
        page_texts = [
            "\n".join(f"{b.speaker.capitalize()}: {b.text}" for b in page)
            for page in segmented
        ]
        return {
            "method": "bubbles",
            "text": labelled,
            "messages": [{"speaker": s, "text": t} for s, t in messages],
            "page_texts": page_texts,
        }

    texts = images_bytes_to_text(pages)
    return {
        "method": "text",
        "text": combine_pages(texts),
        "messages": [],
        "page_texts": texts,
    }
