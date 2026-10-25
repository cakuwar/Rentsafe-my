"""Wiring tests for POST /classify.

These call the endpoint coroutine directly rather than through a test client,
so they need no extra HTTP dependency.

The regression these exist for: the endpoint originally passed the *normalised*
text to layer 2. Normalisation lowercases, rewrites words ("Owner:" ->
"pemilik:", "come" -> "comel") and collapses newlines, so the model received
input unlike its training data and the turn count always came out as 1 -
sending every request into the short-input guard. Unit tests on layer 2 alone
could not see it; only the assembled endpoint could.
"""
import asyncio

import pytest

from app import main
from app.schemas.io import ClassifyRequest

CONVERSATION = "\n".join([
    "Renter: Hi, is the room still available?",
    "Owner: Yes it is. When do you plan to move in?",
    "Renter: Early next month. Can I view it first?",
    "Owner: Sure, come by on Saturday afternoon.",
    "Renter: How much is the deposit?",
    "Owner: Two months, paid after you view and sign.",
])


@pytest.fixture
def captured(monkeypatch):
    """Capture what each layer is called with, independently."""
    seen = {}

    def fake_classify(text, language="auto"):
        seen["layer2_text"] = text
        seen["language"] = language
        return {"scam_probability": 0.42, "model_probability": 0.42}

    def fake_analyse(text):
        seen["layer1_text"] = text
        return {
            "red_flags": ["upfront_payment"],
            "evidence": [{"id": "upfront_payment", "severity": "medium"}],
            "patterns": [],
            "legit_signals": [],
            "suppressed": [],
            "entities": {},
            "clean_text": text,
            "token_count": len(text.split()),
        }

    monkeypatch.setattr(main, "l2_classify", fake_classify)
    monkeypatch.setattr(main, "l1_analyse", fake_analyse)
    return seen


def call(text, language="auto"):
    return asyncio.run(
        main.classify_endpoint(ClassifyRequest(text=text, language=language))
    )


def test_layer2_receives_the_raw_text_not_the_normalised_text(captured):
    call(CONVERSATION)
    assert captured["layer2_text"] == CONVERSATION


def test_layer2_receives_text_with_line_breaks_intact(captured):
    """Turn counting depends on newlines surviving into layer 2."""
    call(CONVERSATION)
    assert captured["layer2_text"].count("\n") == 5


def test_layer2_receives_original_casing(captured):
    """The deployed model is cased, so lowercasing would shift the input."""
    call(CONVERSATION)
    assert "Renter:" in captured["layer2_text"]
    assert "Owner:" in captured["layer2_text"]


def test_layer1_reads_the_normalised_text(captured):
    """Layer 1's patterns depend on the normaliser's expansions."""
    call("Owner: KENA BAYAR deposit dulu")
    assert captured["layer1_text"] == main.normalise("Owner: KENA BAYAR deposit dulu")
    assert captured["layer1_text"] != captured["layer2_text"]


# --- the two layers are independent ----------------------------------------

def test_layer2_is_not_given_the_red_flags(captured):
    """Layer 1's findings must not reach the model's scoring path."""
    import inspect
    source = inspect.getsource(main.classify_endpoint)
    assert "red_flags=" not in source.split("ClassifyResponse")[0]


def test_score_is_layer2_alone_even_with_flags_present(captured):
    """A red flag fired, but the probability is untouched by it."""
    response = call(CONVERSATION)

    assert response.red_flags == ["upfront_payment"]
    assert response.scam_probability == 0.42
    assert response.layer2["model_probability"] == 0.42


def test_layer1_output_is_returned_for_the_narrator(captured):
    """The narrator needs evidence, not just flag ids."""
    response = call(CONVERSATION)

    assert response.layer1["evidence"]
    assert "patterns" in response.layer1
    assert "legit_signals" in response.layer1
    assert "entities" in response.layer1


def test_response_still_reports_the_normalised_text(captured):
    """The API contract exposes the normalised text even though layer 2 skips it."""
    response = call(CONVERSATION)
    assert response.normalised_text != CONVERSATION
    assert "pemilik" in response.normalised_text


def test_language_is_passed_through(captured):
    call(CONVERSATION, language="ms")
    assert captured["language"] == "ms"


def test_scam_probability_comes_from_layer2(captured):
    response = call(CONVERSATION)
    assert response.scam_probability == 0.42
    assert response.layer2["scam_probability"] == 0.42
