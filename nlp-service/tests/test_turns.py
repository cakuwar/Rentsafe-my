"""Tests for message counting.

The unit driving layer 2's short-input guard is a chat bubble, not a line. These
tests pin the three boundary strategies and the furniture stripping, because the
guard thresholds in classifier.py were derived from a sweep measured in this same
unit — if counting drifts, the thresholds silently stop meaning what they say.
"""
import pytest

from app.turns import count_messages, split_messages

LABELLED = "\n".join([
    "Renter: Hi, is the room still available?",
    "Owner: Yes it is. Nak masuk bila ya?",
    "Renter: Early next month.",
])

# What OCR of a WhatsApp screenshot actually produces, furniture and all.
OCR_SCREENSHOT = "\n".join([
    "10:34 a fd @",
    "rumah sewa threads",
    "rm800 imonth rental",
    "rm800 imonth deposit rm100 air api",
    "total rm1700 10:25 pm",
    "lupa nak tnya , kakak urgent ke cari penyewa 10:25pm",
    "tak kenapa ye 10:26pm",
    "@ mesej cn ¢ |",
    "45. ng + (2 g",
    "€ es dalam talian o tak a .",
])


# --- speaker labels --------------------------------------------------------

def test_labelled_conversation_counts_each_speaker_turn():
    assert count_messages(LABELLED) == 3


def test_wrapped_message_under_a_label_counts_once():
    """A bubble split across lines is one message, not three."""
    text = "\n".join([
        "Owner: Kalau nak lock the room,",
        "transfer deposit RM800 dulu.",
        "Renter: Can I see it first?",
    ])
    assert count_messages(text) == 2


def test_wrapped_content_is_joined_not_dropped():
    text = "Owner: Kalau nak lock the room,\ntransfer deposit RM800 dulu."
    assert "transfer deposit RM800 dulu" in split_messages(text)[0]


# --- timestamps ------------------------------------------------------------

def test_ocr_screenshot_counts_bubbles_not_lines():
    """Ten lines of OCR, three actual messages."""
    assert count_messages(OCR_SCREENSHOT) == 3


def test_ocr_furniture_is_not_counted():
    messages = split_messages(OCR_SCREENSHOT)
    joined = " ".join(messages)
    assert "mesej cn" not in joined
    assert "dalam talian" not in joined


def test_trailing_timestamps_are_stripped():
    for message in split_messages(OCR_SCREENSHOT):
        assert not message.rstrip().endswith("pm")


@pytest.mark.parametrize("stamp", ["10:25pm", "17.59", "4,.37pm", "10:26 pm"])
def test_ocr_mangled_timestamp_shapes_close_a_bubble(stamp):
    text = f"boleh datang tengok rumah {stamp}\nsaya free hujung minggu {stamp}"
    assert count_messages(text) == 2


# --- plain text ------------------------------------------------------------

def test_plain_lowercase_malay_lines_are_separate_messages():
    """Malay chat usually opens lowercase, so case cannot mark a continuation."""
    text = "\n".join([
        "lupa nak tnya kakak",
        "tak kenapa ye",
        "boleh saya view rumah hujung minggu ini ke",
    ])
    assert count_messages(text) == 3


def test_blank_lines_are_ignored():
    assert count_messages("boleh datang view\n\n\nsaya free esok\n  \nok tuan") == 3


# --- noise -----------------------------------------------------------------

@pytest.mark.parametrize("junk", [
    "",
    "   ",
    "@ mesej cn ¢ |",
    "45. ng + (2 g",
    "v fl i + (2 g",
    "10:34 a fd @",
    "1808",
])
def test_noise_alone_counts_as_nothing(junk):
    assert count_messages(junk) == 0


def test_a_real_short_message_is_still_counted():
    """Stripping furniture must not swallow genuine short replies."""
    assert count_messages("ok boleh") == 1
    assert count_messages("baik tuan") == 1


# --- the property the guard depends on -------------------------------------

def test_counting_is_not_inflated_by_wrapping():
    """The bug this module exists for: line counting over-reported context."""
    wrapped = "\n".join([
        "Owner: sewa rm800 sebulan,",
        "deposit dua bulan,",
        "utiliti rm50 sebulan,",
        "bayar selepas sign agreement.",
    ])
    assert len(wrapped.splitlines()) == 4
    assert count_messages(wrapped) == 1
