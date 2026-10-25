"""The message counter against a real WhatsApp screenshot.

Fixtures are OCR text from `data/samples/scam_p1..p4.jpg`, a genuine rental
scam, with the account holder's name and any numbers redacted. The images are
not in the repo.

This is **not** held-out evaluation data — its text was read while writing
layer 1's rules, so scoring a model on it proves nothing. What it does test is
counting, where a human hand count gives an answer no synthetic fixture can:
**26 bubbles, 25 of them text**, per page 9 / 11 / 3 / 3 (page 4's third bubble
is an image, a payment QR, which the text counter cannot see and is not expected
to count).

Every difficulty here came from this file and was invisible in hand-drawn
fixtures: timestamps mangled to "5.95", "1808" and "17684 W"; a clock alone on
its own line; quoted replies that repeat the message above them; pages that
overlap at the seam; and the contact-name header on every page.
"""
import json
import os

import pytest

from app.ocr.ocr import combine_pages
from app.turns import count_messages, split_messages

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load_pages():
    paths = [os.path.join(FIXTURES, f"real_scam_p{n}.txt") for n in (1, 2, 3, 4)]
    if not all(os.path.exists(path) for path in paths):
        pytest.skip("real screenshot fixtures not present")
    return [open(path, encoding="utf-8").read() for path in paths]


@pytest.fixture(scope="module")
def pages():
    return load_pages()


@pytest.fixture(scope="module")
def meta():
    path = os.path.join(FIXTURES, "real_scam_meta.json")
    if not os.path.exists(path):
        pytest.skip("fixture metadata missing")
    return json.load(open(path, encoding="utf-8"))


# --- the headline number ---------------------------------------------------

def test_stitched_count_matches_the_hand_count(pages, meta):
    """Within +/-2 of a human reading the actual screenshots."""
    counted = count_messages(combine_pages(pages))
    expected = meta["hand_count_text_messages"]
    assert abs(counted - expected) <= 2, f"counted {counted}, hand count {expected}"


def test_counting_lines_would_have_been_far_off(pages):
    """Why this module exists: the old line-based count was not close."""
    stitched = combine_pages(pages)
    lines = len([line for line in stitched.splitlines() if line.strip()])
    assert lines > count_messages(stitched) * 1.5


# --- the specific OCR artefacts found in this conversation -----------------

def test_mangled_timestamps_close_bubbles(pages):
    """"5.95", "1808", "17684 W" are all clocks that OCR mauled."""
    messages = split_messages(combine_pages(pages))
    for message in messages:
        assert not message.rstrip().endswith((" 1808", " 5.95", " 17684 W"))


def test_a_timestamp_alone_on_a_line_splits_two_messages(pages):
    """WhatsApp puts the clock on its own line; it still ends the bubble.

    While this was missed, "Kena bayar booking rm 500 dulu ye" and the reply
    below it were read as one message.
    """
    messages = split_messages(combine_pages(pages))
    joined = [m for m in messages if "Kena bayar booking" in m]
    assert joined, "expected the booking demand to be found"
    assert all("tak sesuai" not in m for m in joined), (
        "the booking demand was merged with the message after it"
    )


def test_quoted_reply_does_not_duplicate_the_quoted_message(pages):
    """A quote renders the earlier message again; it counts once."""
    messages = split_messages(combine_pages(pages))
    refund = [m for m in messages if "refund balik sepenuh" in m]
    assert len(refund) == 1, f"quoted text counted {len(refund)} times"


def test_the_reply_under_a_quote_survives(pages):
    """Trimming the quote must not swallow what the person actually wrote."""
    messages = split_messages(combine_pages(pages))
    assert any(m.strip().lower().startswith("ok boleh") for m in messages)


def test_page_seam_repeats_count_once(pages):
    """Consecutive captures overlap; stitching must not double-count."""
    per_page = sum(count_messages(page) for page in pages)
    stitched = count_messages(combine_pages(pages))
    assert stitched < per_page, "no seam de-duplication happened"


def test_contact_header_is_not_a_message(pages):
    """The name bar at the top of every page is chrome, not conversation."""
    messages = split_messages(combine_pages(pages))
    assert not any(m.strip().startswith("€ ES") for m in messages)


def test_the_multiline_form_is_one_message(pages):
    """Nama penuh / Status / Pekerjaan / ... is a single bubble."""
    messages = split_messages(combine_pages(pages))
    form = [m for m in messages if "Nama penuh" in m]
    assert len(form) == 1
    assert "Tempoh sewa" in form[0], "the form was split across messages"


# --- the conversation still reaches layer 1 ------------------------------

def test_layer1_flags_this_real_scam(pages):
    from app.layer1.red_flags import analyse
    from app.normaliser.normaliser import normalise

    result = analyse(normalise(combine_pages(pages)))
    for expected in ("upfront_payment", "pay_before_viewing", "refund_promise"):
        assert expected in result["red_flags"]
    assert "refundable_hold_lure" in [p["id"] for p in result["patterns"]]


def test_this_conversation_clears_the_short_input_guard(pages):
    """25 messages is well past the 6-message threshold."""
    from app.layer2.classifier import MIN_TURNS_FOR_ANY_CONFIDENCE

    assert count_messages(combine_pages(pages)) >= MIN_TURNS_FOR_ANY_CONFIDENCE


# --- privacy ---------------------------------------------------------------

def test_fixtures_carry_no_personal_data(pages):
    """Names are checked against data/samples/redact.txt, so none is written
    here; phone, IC and account numbers are checked by pattern."""
    from training.redaction import leaks, names

    found = leaks(" ".join(pages))
    assert found == [], f"not redacted: {found}"
    if not names():
        pytest.skip("numbers checked; names need data/samples/redact.txt")


def test_no_screenshot_images_in_the_repo():
    """Images stay in data/samples/, never in tests."""
    for root, _, files in os.walk(os.path.dirname(FIXTURES)):
        for name in files:
            assert not name.lower().endswith((".png", ".jpg", ".jpeg")), name
