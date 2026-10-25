"""Tests for Layer 2 scam classification.

Split three ways:
  - logic tests that stub the model, so they run fast and without weights
  - fallback tests for the missing-weights path
  - integration tests that need the real weights, skipped when absent
"""
import os

import pytest

from app import config
from app.layer2 import classifier
from app.layer2.classifier import classify, count_turns

CONVERSATION = "\n".join([
    "Renter: Hi, is the room still available?",
    "Owner: Yes it is. When do you plan to move in?",
    "Renter: Early next month. Can I view it first?",
    "Owner: Sure, come by on Saturday.",
    "Renter: How much is the deposit?",
    "Owner: Two months, paid after you view and sign.",
    "Renter: Great, see you Saturday.",
    "Owner: See you.",
])

WEIGHTS_PRESENT = os.path.isdir(config.FINETUNED_MODEL_DIR)
needs_weights = pytest.mark.skipif(
    not WEIGHTS_PRESENT,
    reason=f"no weights at {config.FINETUNED_MODEL_DIR}",
)


@pytest.fixture
def stub_model(monkeypatch):
    """Replace the transformer with a settable probability."""
    def set_probability(value):
        monkeypatch.setattr(
            classifier, "_model_probability", lambda text: value
        )
    return set_probability


@pytest.fixture
def no_model(monkeypatch):
    """Simulate missing weights."""
    monkeypatch.setattr(classifier, "_model_probability", lambda text: None)


# --- turn counting ---------------------------------------------------------

def test_count_turns_ignores_blank_lines():
    assert count_turns("boleh view\n\n\nsaya free esok\n  \nok tuan") == 3


def test_count_turns_is_messages_not_lines():
    """Delegates to app.turns; tests/test_turns.py holds the full contract."""
    wrapped = "Owner: sewa rm800 sebulan,\ndeposit dua bulan,\nbayar masa sign."
    assert len(wrapped.splitlines()) == 3
    assert count_turns(wrapped) == 1


def test_count_turns_on_single_line():
    assert count_turns("Bayar deposit dulu") == 1


def test_count_turns_on_empty_text():
    assert count_turns("") == 0


# --- confidence bands ------------------------------------------------------

@pytest.mark.parametrize("turns,expected", [
    # Bands come from eval/truncation_sweep.py, measured in messages against an
    # always-SCAM baseline of 0.708 on that subset.
    (1, "insufficient"),   # 0.292  (deployed retrain run 1)
    (3, "insufficient"),   # 0.375
    (4, "insufficient"),   # 0.542 - below baseline
    (5, "insufficient"),   # 0.667 - still below baseline
    (6, "low"),            # 0.792 - first count that beats it
    (7, "moderate"),       # 0.889
    (8, "high"),           # 0.903
    (20, "high"),          # 1.000
])
def test_confidence_bands_follow_measured_accuracy(turns, expected):
    text = "\n".join(f"Owner: line {i}" for i in range(turns))
    assert classifier._confidence_for(count_turns(text)) == expected


# --- the short-input guard -------------------------------------------------

def test_short_low_score_is_reported_as_unknown(stub_model):
    """A confident 'legitimate' on 1 line must not become a false all-clear."""
    stub_model(0.03)
    result = classify("Transfer the deposit first and I post the keys.")

    assert result["status"] == "insufficient_context"
    assert result["scam_probability"] == 0.5
    assert result["model_probability"] == 0.03
    assert "note" in result


def test_short_high_score_is_still_reported(stub_model):
    """Guarding against false all-clears must not suppress a scam warning."""
    stub_model(0.97)
    result = classify("Bayar deposit dulu baru boleh viewing.")

    assert result["scam_probability"] > 0.9
    assert result["confidence"] == "insufficient"
    assert result["status"] == "ok"


def test_long_low_score_is_trusted(stub_model):
    """With the full conversation visible, a low score means low risk."""
    stub_model(0.02)
    result = classify(CONVERSATION)

    assert result["confidence"] == "high"
    assert result["status"] == "ok"
    assert result["scam_probability"] < 0.1


# --- independence from layer 1 ---------------------------------------------
#
# Layer 1 is evidence for the narrator, not an input to the score. These tests
# exist so a future change cannot quietly reintroduce a rule bonus: that would
# double-count phrases the model already saw in training, and would make the
# model's measured F1 unreproducible from the service's own API.

def test_classify_takes_no_red_flags_argument():
    """The signature itself is the contract."""
    import inspect
    parameters = list(inspect.signature(classify).parameters)
    assert parameters == ["text", "language"]


def test_score_is_exactly_the_model_probability(stub_model):
    stub_model(0.6123)
    result = classify(CONVERSATION)

    assert result["scam_probability"] == pytest.approx(0.6123)
    assert result["model_probability"] == pytest.approx(0.6123)


def test_no_boost_field_is_reported(stub_model):
    stub_model(0.60)
    result = classify(CONVERSATION)

    assert "red_flag_boost" not in result
    assert "matched_red_flags" not in result


def test_module_exposes_no_rule_weights():
    assert not hasattr(classifier, "MAX_RED_FLAG_BOOST")
    assert not hasattr(classifier, "RED_FLAG_WEIGHTS")


def test_probability_stays_in_range(stub_model):
    for value in (0.0, 0.5, 0.99, 1.0):
        stub_model(value)
        result = classify(CONVERSATION)
        assert 0.0 <= result["scam_probability"] <= 1.0


# --- when the weights are missing ------------------------------------------

def test_missing_weights_report_unknown_not_a_score(no_model):
    """Fabricating a number would be worse than admitting we cannot judge."""
    result = classify(CONVERSATION)

    assert result["status"] == "model_unavailable"
    assert result["model_probability"] is None
    assert result["scam_probability"] == 0.5
    assert "note" in result


# --- with the real weights -------------------------------------------------

@needs_weights
def test_real_model_flags_a_scam_conversation():
    scam = "\n".join([
        "Renter: Hi, is the room still available?",
        "Owner: Yes. Nak masuk bila ya?",
        "Renter: Boleh pergi viewing dulu tak?",
        "Owner: I'm outstation in Sabah, cannot open the unit.",
        "Owner: Kalau nak lock the room, transfer deposit RM800 dulu.",
        "Renter: Can I see it first before paying?",
        "Owner: Ramai orang tengah tanya. Transfer dulu, lepas tu saya pos kunci.",
        "Renter: Ok let me think about it.",
    ])
    result = classify(scam)

    assert result["status"] == "ok"
    assert result["confidence"] == "high"
    assert result["scam_probability"] > 0.5


@needs_weights
def test_real_model_clears_a_legitimate_conversation():
    result = classify(CONVERSATION)

    assert result["status"] == "ok"
    assert result["scam_probability"] < 0.5


@needs_weights
def test_real_model_is_loaded_once():
    classify(CONVERSATION)
    first = classifier._model
    classify(CONVERSATION)
    assert classifier._model is first


# --- the guard threshold traces to measured data ---------------------------

def test_guard_threshold_matches_the_truncation_sweep():
    """The constants must track eval/results/truncation_sweep.json.

    They were once set by eye at 4, where the model scores 0.597 against a 0.708
    baseline — the guard let through the band it existed to catch.
    """
    import json
    import os

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "eval", "results", "truncation_sweep.json",
    )
    if not os.path.exists(path):
        pytest.skip("run eval/truncation_sweep.py first")

    with open(path) as handle:
        result = json.load(handle)

    assert classifier.MIN_TURNS_FOR_ANY_CONFIDENCE == result["guard_threshold_messages"]

    baseline = result["baseline_always_scam"]["accuracy"]
    for row in result["sweep"]:
        if row["messages"] is None:
            continue
        guarded = row["messages"] < classifier.MIN_TURNS_FOR_ANY_CONFIDENCE
        below_baseline = row["accuracy"] <= baseline
        assert guarded == below_baseline, (
            f"{row['messages']} messages: accuracy {row['accuracy']} vs baseline "
            f"{baseline}, guarded={guarded}"
        )


def test_short_input_with_a_high_score_is_reported_not_guarded(stub_model):
    """The guard is one-directional: it suppresses false all-clears only.

    A scam that is obvious from four messages must still reach the user. Only a
    LOW score on short input becomes 0.5 — a HIGH one is reported as-is, with
    confidence "insufficient" so the caller knows the context was thin.
    """
    stub_model(0.9997)
    text = "\n".join([
        "Owner: Kalau nak lock the room,",
        "Owner: transfer deposit RM800 dulu.",
        "Renter: Can I see it first?",
        "Owner: Lepas transfer saya pos kunci.",
    ])
    result = classify(text)

    assert result["turns"] < classifier.MIN_TURNS_FOR_ANY_CONFIDENCE
    assert result["confidence"] == "insufficient"
    assert result["status"] == "ok"
    assert result["scam_probability"] > 0.9


@pytest.mark.parametrize("probability,expected_status", [
    (0.02, "insufficient_context"),   # low  -> suppressed
    (0.49, "insufficient_context"),   # just below neutral -> suppressed
    (0.51, "ok"),                     # just above neutral -> reported
    (0.9997, "ok"),                   # high -> reported
])
def test_guard_only_suppresses_low_scores(stub_model, probability, expected_status):
    stub_model(probability)
    assert classify("one short line")["status"] == expected_status


# --- long input is read in full ---------------------------------------------
#
# Real screenshots run to ~700 tokens. Truncated at 256, the model saw only the
# first 37% of a real legitimate conversation — never the part where viewing was
# arranged and keys handed over.

from app.layer2.classifier import STRIDE, WINDOW, _window_starts


@pytest.mark.parametrize("length", [1, 100, 510, 511, 700, 1500, 4000])
def test_windows_cover_every_token(length):
    body = WINDOW - 2
    starts = _window_starts(length, body)
    covered = set()
    for start in starts:
        covered.update(range(start, min(length, start + body)))
    assert covered == set(range(length)), f"{length} tokens not fully covered"


def test_short_input_is_one_window():
    assert _window_starts(200, WINDOW - 2) == [0]


def test_the_tail_always_gets_a_full_window():
    """Payment demands and key handovers sit late in a conversation."""
    body = WINDOW - 2
    starts = _window_starts(700, body)
    assert starts[-1] + body == 700


def test_windows_overlap_so_no_message_is_only_ever_split():
    body = WINDOW - 2
    starts = _window_starts(1500, body)
    for first, second in zip(starts, starts[1:]):
        assert second - first <= STRIDE
        assert first + body > second


def test_score_is_the_highest_window(monkeypatch):
    """Evidence anywhere in the conversation counts."""
    monkeypatch.setattr(classifier, "_window_scores", lambda text: [0.02, 0.97, 0.10])
    assert classifier._model_probability("x") == 0.97


# --- calibration temperature ------------------------------------------------

@pytest.mark.parametrize("stored, expected", [
    (None, 1.0),          # checkpoints trained before calibration existed
    (1.7, 1.7),
    ("2.5", 2.5),
    (0, 1.0),             # would divide by zero
    (-1.3, 1.0),          # would invert every score
    (500, 1.0),           # would flatten every score to 0.5
    ("warm", 1.0),
])
def test_temperature_is_read_defensively(stored, expected):
    from types import SimpleNamespace

    config = SimpleNamespace() if stored is None else SimpleNamespace(calibration_temperature=stored)
    assert classifier._temperature_of(config) == expected


def test_temperature_never_changes_the_verdict():
    """Dividing logits by T > 0 keeps every score on the same side of 0.5."""
    import torch

    logits = torch.tensor([[2.0, -1.0], [-0.3, 0.4], [0.0, 0.0], [-4.0, 5.0]])
    base = logits.softmax(-1)[:, 1] >= 0.5
    for temperature in (0.5, 1.0, 1.8, 7.0):
        assert torch.equal((logits / temperature).softmax(-1)[:, 1] >= 0.5, base)


# --- message-aligned windows ------------------------------------------------

class _WordTokenizer:
    """One token per word, so window arithmetic can be checked by hand."""

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": [hash(word) % 1000 for word in text.split()]}


def _conversation(sizes):
    return "\n".join(" ".join(f"m{i}w{j}" for j in range(size)) for i, size in enumerate(sizes))


def _as_messages(text, windows):
    """Map each window back to the message indexes it holds, or fail."""
    tokenizer = _WordTokenizer()
    messages = [tokenizer(line)["input_ids"] for line in text.split("\n")]
    spans = []
    for window in windows:
        for first in range(len(messages)):
            joined, end = [], first
            while end < len(messages) and len(joined) < len(window):
                joined += messages[end]
                end += 1
            if joined == window:
                spans.append((first, end - 1))
                break
        else:
            raise AssertionError("window does not start and end on message boundaries")
    return spans


def test_windows_never_cut_inside_a_message():
    text = _conversation([40] * 30)            # 1200 tokens
    windows = classifier._message_windows(_WordTokenizer(), text)
    assert len(windows) >= 3
    assert all(len(w) <= classifier.WINDOW - 2 for w in windows)
    _as_messages(text, windows)                # raises if any window splits a message


def test_windows_cover_every_message_and_pin_the_end():
    text = _conversation([37, 90, 12, 150, 64, 8, 120, 45, 200, 33, 71, 19])
    spans = _as_messages(text, classifier._message_windows(_WordTokenizer(), text))
    covered = {i for first, end in spans for i in range(first, end + 1)}
    assert covered == set(range(12))
    assert spans[-1][1] == 11
    # The last window is packed back from the end, so it is full, not a stub.
    tail = text.split("\n")
    assert sum(len(tail[i].split()) for i in range(spans[-1][0], 12)) > classifier.STRIDE


def test_short_text_is_one_window():
    text = _conversation([20, 30, 25])
    assert classifier._message_windows(_WordTokenizer(), text) == [
        _WordTokenizer()(text.replace("\n", " "))["input_ids"]]


def test_only_an_over_long_single_message_is_cut():
    text = _conversation([30, 900, 30])
    windows = classifier._message_windows(_WordTokenizer(), text)
    assert all(len(w) <= classifier.WINDOW - 2 for w in windows)
    words = sum(len(w) for w in windows)
    assert words >= 960                         # every token appears somewhere
