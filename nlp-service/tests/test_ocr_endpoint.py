"""Tests for POST /ocr with one or more screenshots.

The endpoint coroutine is called directly, so no HTTP client dependency is
needed. Tesseract itself is stubbed out in most tests — what is under test is
the multi-file handling, not the OCR engine.
"""
import asyncio
import io

import pytest
from fastapi import HTTPException, UploadFile

from app import main
from app.ocr.ocr import combine_pages


def upload(name, payload=b"fake-image-bytes"):
    return UploadFile(filename=name, file=io.BytesIO(payload))


def call(files):
    return asyncio.run(main.ocr_endpoint(files=files))


def _text_result(texts):
    """What screenshots_to_conversation returns on the plain-text fallback."""
    return {
        "method": "text",
        "text": combine_pages(texts),
        "messages": [],
        "page_texts": texts,
    }


@pytest.fixture
def fake_ocr(monkeypatch):
    """One line of text per page, so turn counting is predictable."""
    def fake(pages):
        return _text_result([f"Owner: page {i}" for i, _ in enumerate(pages)])
    monkeypatch.setattr(main, "screenshots_to_conversation", fake)


@pytest.fixture
def failing_ocr(monkeypatch):
    """Middle page is unreadable."""
    def fake(pages):
        return _text_result([
            "" if i == 1 else f"Owner: page {i}" for i, _ in enumerate(pages)
        ])
    monkeypatch.setattr(main, "screenshots_to_conversation", fake)


@pytest.fixture
def bubble_ocr(monkeypatch):
    """Segmentation succeeded and recovered speakers."""
    def fake(pages):
        messages = [
            {"speaker": "renter", "text": "Is the room still available?"},
            {"speaker": "owner", "text": "Yes, come and view on Saturday."},
            {"speaker": "renter", "text": "Great, see you then."},
        ]
        return {
            "method": "bubbles",
            "text": "\n".join(
                f"{m['speaker'].capitalize()}: {m['text']}" for m in messages
            ),
            "messages": messages,
            "page_texts": ["page text"] * len(pages),
        }
    monkeypatch.setattr(main, "screenshots_to_conversation", fake)


# --- combine_pages ---------------------------------------------------------

def test_combine_pages_joins_with_newlines():
    assert combine_pages(["a", "b"]) == "a\nb"


def test_combine_pages_preserves_order():
    assert combine_pages(["first", "second", "third"]).splitlines() == [
        "first", "second", "third",
    ]


def test_combine_pages_drops_blank_pages():
    assert combine_pages(["a", "", "   ", "b"]) == "a\nb"


# --- multiple files --------------------------------------------------------

def test_accepts_several_files(fake_ocr):
    response = call([upload("p1.png"), upload("p2.png"), upload("p3.png")])

    assert response.page_count == 3
    assert len(response.pages) == 3
    assert response.extracted_text.count("\n") == 2


def test_turns_accumulate_across_files(fake_ocr):
    """The point of multi-upload: more screenshots, more usable context."""
    one = call([upload("p1.png")])
    three = call([upload("p1.png"), upload("p2.png"), upload("p3.png")])

    assert one.turns == 1
    assert three.turns == 3


def test_pages_report_filenames_in_order(fake_ocr):
    response = call([upload("b.png"), upload("a.png")])
    assert [page.filename for page in response.pages] == ["b.png", "a.png"]


def test_upload_order_is_not_sorted(fake_ocr):
    """IMG_10 must not be reordered before IMG_2 - that would scramble a chat."""
    response = call([upload("IMG_2.png"), upload("IMG_10.png")])
    assert [page.filename for page in response.pages] == ["IMG_2.png", "IMG_10.png"]


# --- failure handling ------------------------------------------------------

def test_unreadable_page_is_marked_but_does_not_fail_the_request(failing_ocr):
    response = call([upload("a.png"), upload("bad.png"), upload("c.png")])

    assert [page.ok for page in response.pages] == [True, False, True]
    assert response.page_count == 3
    # Text from the readable pages survives.
    assert response.turns == 2


def test_empty_file_list_is_rejected():
    """FastAPI rejects a missing field; this covers an empty list reaching us."""
    with pytest.raises(HTTPException) as caught:
        call([])
    assert caught.value.status_code == 422


def test_too_many_files_is_rejected(fake_ocr):
    too_many = [upload(f"p{i}.png") for i in range(main.MAX_OCR_PAGES + 1)]
    with pytest.raises(HTTPException) as caught:
        call(too_many)
    assert caught.value.status_code == 413


def test_exactly_the_limit_is_allowed(fake_ocr):
    at_limit = [upload(f"p{i}.png") for i in range(main.MAX_OCR_PAGES)]
    assert call(at_limit).page_count == main.MAX_OCR_PAGES


# --- character counts ------------------------------------------------------

def test_characters_match_the_extracted_text(fake_ocr):
    response = call([upload("p1.png")])
    page = response.pages[0]
    assert page.characters == len(page.extracted_text)



# --- bubble segmentation path ----------------------------------------------

def test_bubble_path_reports_its_method(bubble_ocr):
    assert call([upload("p1.png")]).method == "bubbles"


def test_bubble_path_counts_messages_not_lines(bubble_ocr):
    response = call([upload("p1.png")])
    assert response.turns == len(response.messages) == 3


def test_bubble_path_attributes_speakers(bubble_ocr):
    response = call([upload("p1.png")])
    assert [m.speaker for m in response.messages] == ["renter", "owner", "renter"]


def test_bubble_path_writes_the_training_format(bubble_ocr):
    """The classifier was trained on "Renter: ... / Owner: ..." transcripts."""
    text = call([upload("p1.png")]).extracted_text
    assert text.splitlines()[0].startswith("Renter: ")
    assert text.splitlines()[1].startswith("Owner: ")


def test_text_fallback_carries_no_speakers(fake_ocr):
    response = call([upload("p1.png")])
    assert response.method == "text"
    assert response.messages == []


# --- text inside photos (camera watermarks) is not a message -----------------

def _bubble(speaker, fill, text):
    import numpy as np
    from app.ocr.bubbles import Bubble, Line

    line = Line(text=text, left=10, top=10, right=200, bottom=30)
    line.fill, line.flat = np.array(fill, dtype=float), True
    return Bubble(speaker, [line])


def test_a_watermark_on_a_photo_is_dropped():
    """The iBilik case: a camera date stamp on a flat part of a room photo,
    read as a renter message. Its background matches neither bubble colour."""
    from app.ocr.bubbles import drop_media_text

    renter, owner = (129, 32, 20), (36, 37, 36)          # measured bubble fills
    page = [
        _bubble("renter", renter, "hi boleh saya tahu bilik ni available lagi tak?"),
        _bubble("renter", renter, "can i take look? have any picture or video?"),
        _bubble("renter", (81, 55, 39), "9 28 Aug 05,2028 Subang Jaya Selangor"),
        _bubble("renter", renter, "i plan to visit on 20/8, if you free on that date"),
        _bubble("owner", owner, "Bring your own induction cooker ya"),
    ]
    kept = [b.text for b in drop_media_text([page])[0]]
    assert not any("Selangor" in t for t in kept)
    assert len(kept) == 4


def test_quote_boxes_and_slightly_shaded_bubbles_are_kept():
    """Quote boxes and link previews sit on a darker shade of the bubble -
    measured up to 11.1 away - and are not dropped."""
    from app.ocr.bubbles import MEDIA_FILL_DISTANCE, drop_media_text

    page = [
        _bubble("renter", (129, 32, 20), "hi, can I move in earlier?"),
        _bubble("renter", (129, 32, 20), "okay already signed miss"),
        _bubble("renter", (103, 27, 16), "Please check and sign the agreement ya"),   # quote box
        _bubble("owner", (36, 37, 36), "Can move in earlier"),
    ]
    assert MEDIA_FILL_DISTANCE > 11.1
    assert len(drop_media_text([page])[0]) == 4


def test_references_come_from_the_whole_upload_not_one_page():
    """A page holding mostly a photo is judged against the conversation's
    real bubble colours, taken across all pages."""
    from app.ocr.bubbles import drop_media_text

    renter, owner = (211, 248, 212), (250, 250, 250)      # light theme
    page_one = [_bubble("renter", renter, "boleh saya tengok rumah dulu? saya free hujung minggu"),
                _bubble("renter", renter, "ok saya datang Sabtu pukul 11 pagi"),
                _bubble("owner", owner, "boleh, datang Sabtu ni")]
    page_two = [_bubble("renter", (90, 70, 60), "2:28 PM Aug 05 2026 Wed")]
    cleaned = drop_media_text([page_one, page_two])
    assert len(cleaned[0]) == 3
    assert cleaned[1] == []


def test_a_speaker_with_little_text_loses_nothing():
    """If a photo stamp carries as much text as a speaker's real messages, the
    speaker's colour is not trusted and nothing of theirs is dropped."""
    from app.ocr.bubbles import drop_media_text

    page = [
        _bubble("renter", (211, 248, 212), "boleh saya tengok rumah dulu? saya free Sabtu"),
        _bubble("owner", (250, 250, 250), "boleh, datang Sabtu ni"),
        _bubble("owner", (90, 70, 60), "2:28 PM Aug 05 2026 Wed"),
    ]
    kept = [b.text for b in drop_media_text([page])[0]]
    assert "boleh, datang Sabtu ni" in kept          # the real message survives
