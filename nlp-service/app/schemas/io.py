"""Request/response models for the NLP API (POST /classify, POST /ocr)."""

from typing import Any, Literal
from pydantic import BaseModel, Field


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=2)
    language: Literal["auto", "ms", "en"] = "auto"

class ClassifyResponse(BaseModel):
    # From layer 2 alone. Layer 1's red flags contribute nothing to it; the
    # backend combines the two in aggregateScore (score = this * 60 + ...).
    scam_probability: float = Field(ge=0.0, le=1.0)
    normalised_text: str
    # Flag ids, kept flat for callers that only need the list.
    red_flags: list[str]
    # Full layer-1 output: evidence with BM+EN labels, advice and snippets,
    # pattern rules, legitimacy signals, suppressed matches and entities. This
    # is what the LLM narrator reads to explain the verdict to the renter.
    layer1: dict[str, Any] = Field(default_factory=dict)
    layer2: dict[str, Any]

class OCRPageResult(BaseModel):
    """Per-screenshot OCR outcome, so a caller can tell which page failed."""
    filename: str | None = None
    extracted_text: str
    characters: int
    ok: bool


class OCRMessage(BaseModel):
    speaker: str   # "renter" (outgoing) or "owner" (incoming)
    text: str


class OCRResponse(BaseModel):
    # The whole conversation, ready to POST to /classify. When bubbles were
    # found it is written "Renter: ... / Owner: ...", the form the classifier
    # was trained on.
    extracted_text: str
    page_count: int
    # Messages visible. Layer 2 needs about 6 to score confidently, so this
    # tells the caller whether to ask for more screenshots.
    turns: int
    # "bubbles" when speakers were recovered from the image, "text" when OCR
    # fell back to plain text and no speaker information is available.
    method: str = "text"
    messages: list[OCRMessage] = Field(default_factory=list)
    pages: list[OCRPageResult] = Field(default_factory=list)