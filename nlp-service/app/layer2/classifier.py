"""Layer 2 — transformer-based scam classification.

Single fine-tuned model, no zero-shot second model. The first reason given for
that - "the fine-tuned classifier separates the validation set cleanly" - did
not hold: validation later proved to reward memorised wording rather than
reading scam behaviour (docs/MODEL_COMPARISON.md section 14.9). The decision now
rests on a direct test, eval/zero_shot_test.py (section 14.12), with its
hypotheses, score and pass mark fixed before it ran: a multilingual NLI model
(mDeBERTa-v3-base-xnli) scored no better than always answering SCAM on
validation (0.663), 0.0 pair accuracy on scam/legit twins in new wording, and
got the real iBilik chat wrong in every version, at about 20x the CPU time of
this model. A zero-shot model could not have calibrated this one in any case:
calibration comes from the checkpoint's own temperature (below), and the
independent check on the score is layer 1's evidence plus the backend's band
cap.

The model is lazy-loaded on first request so the API starts fast and the tests
run without touching the weights. If the weights are missing the service still
answers, reporting an unknown probability and saying so in `status`.

This layer produces a probability and nothing else. Layer 1's red flags are not
an input here and add no points - see the note beside MAX_LENGTH.

Short input is treated as a special case. eval/truncation_sweep.py measures the
deployed model against how many **messages** are visible, on the 72 validation
conversations with at least 8 (51 scam / 21 legitimate). For the deployed
retrain run 1 (the previous model's sweep: truncation_sweep_xlmr_random.json):

    messages   1      2      3      4      5      6      7      8    all
    accuracy 0.292  0.319  0.375  0.542  0.667  0.792  0.889  0.903  1.000

Answering SCAM unconditionally scores 0.708 on that subset. So up to and
including **5 messages the model is worse than a trivial classifier**, and 6 is
the first count that beats it — which is where the guard fires. Below it the
model does not merely hesitate, it fails toward LEGITIMATE, and a confident low
score on a two-message screenshot would tell a renter that a scam looks safe.

The threshold is the same for both models measured: 6.

An earlier revision guarded below 4, a number picked by eye from a sweep measured
in lines. At 4 messages the previous model scored 0.597 against a 0.708
baseline (run 1: 0.542), so that guard let through exactly the band it existed
to catch.
"""
import logging
import threading

from app import config
from app.turns import count_messages

logger = logging.getLogger("rentsafe.layer2")

# Long conversations are read in overlapping windows rather than truncated.
#
# The real legitimate conversation is 655-733 tokens; the training data never
# exceeded 241 (eval/results/length_mismatch.json). Cut at 256, the model saw
# only the first 35-39% of it — the listing and the price breakdown — and none
# of the part where the viewing was arranged and the keys handed over. It could
# not have seen the evidence of legitimacy even had it known to look.
#
# Windows are cut BETWEEN messages, never inside one (_message_windows): each
# holds up to WINDOW tokens of whole messages, and the next starts about STRIDE
# tokens later. The conversation's score is the highest window: a scam is a scam
# if the evidence appears anywhere in it.
#
# Cutting at fixed token offsets was the first version, and retrain run 1 showed
# its cost. The OCR text of the real legitimate chat had its first window end
# inside a message: "...Login using your registered mobile number and password
# ... Please take a screenshot and send it to" — with "me after signing ya" in
# the next window. That window scored 0.78; removing any earlier line, which let
# the sentence finish, dropped it to 0.09-0.33 (eval/results/v3_run1_*). No
# training example ever ends mid-sentence, so a window that does is input the
# model has never seen.
WINDOW = 512
STRIDE = 256
MAX_LENGTH = WINDOW  # kept for callers that read it

# Layer 1 contributes nothing to this number, by design. The model was
# fine-tuned on conversations containing the very phrases layer 1 matches, so
# adding a rule bonus on top would count the same evidence twice - and it would
# mean a new regex silently changed every score the service reports, making the
# model's measured performance unreproducible from its own API.
#
# Layer 1's job is evidence for the narrator and the renter; this layer's job is
# a probability. They are combined once, in the backend's aggregateScore, where
# OSINT and price are weighed too.

# Message counts from the table above, all set by eval/truncation_sweep.py.
# "insufficient" is the band where measured accuracy sits below the always-SCAM
# baseline of 0.708 on that subset; the rest track the curve as it climbs.
#
#   >= 8 messages  0.903 - 1.000   high
#      7 messages  0.889           moderate
#      6 messages  0.792           low
#   <= 5 messages  0.667 and below insufficient  <- below baseline
MIN_TURNS_FOR_HIGH_CONFIDENCE = 8
MIN_TURNS_FOR_MODERATE_CONFIDENCE = 7
MIN_TURNS_FOR_ANY_CONFIDENCE = 6

# Returned when the input is too short to judge. Neither "likely scam" nor
# "likely safe" — the caller should ask for more of the conversation.
UNKNOWN_PROBABILITY = 0.5

# Probability calibration. A retrained checkpoint may carry a `temperature` in
# its config.json, fitted on held-out data after training (train_colab_v3):
# logits are divided by it before softmax. It never changes which side of 0.5 a
# score falls on — only how far from it — so every SCAM/LEGITIMATE decision is
# the same with or without it. A checkpoint without one uses 1.0, unchanged.
DEFAULT_TEMPERATURE = 1.0

_model = None
_tokenizer = None
_scam_index = 1
_temperature = DEFAULT_TEMPERATURE
_load_lock = threading.Lock()
_load_failed = False


def _load():
    """Load the fine-tuned weights once, on first use.

    Returns (tokenizer, model) or (None, None) if the weights are unavailable,
    in which case the caller reports an unknown probability.
    """
    global _model, _tokenizer, _scam_index, _temperature, _load_failed

    if _model is not None:
        return _tokenizer, _model
    if _load_failed:
        return None, None

    with _load_lock:
        # Another thread may have finished while this one waited.
        if _model is not None:
            return _tokenizer, _model
        if _load_failed:
            return None, None

        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )

            logger.info("loading layer-2 model from %s", config.FINETUNED_MODEL_DIR)
            tokenizer = AutoTokenizer.from_pretrained(config.FINETUNED_MODEL_DIR)
            model = AutoModelForSequenceClassification.from_pretrained(
                config.FINETUNED_MODEL_DIR
            )
            model.eval()

            # Do not assume SCAM is index 1 — read it off the checkpoint.
            label2id = {
                str(label).upper(): index
                for label, index in (model.config.label2id or {}).items()
            }
            _scam_index = label2id.get("SCAM", 1)
            _temperature = _temperature_of(model.config)

            _tokenizer, _model = tokenizer, model
            logger.info(
                "layer-2 model ready (%.0fM parameters, SCAM is index %d, "
                "temperature %.3f)",
                model.num_parameters() / 1e6,
                _scam_index,
                _temperature,
            )
            return _tokenizer, _model

        except Exception:
            _load_failed = True
            logger.warning(
                "could not load layer-2 weights from %s - /classify will "
                "report an unknown probability. Train a model or fix "
                "FINETUNED_MODEL_DIR.",
                config.FINETUNED_MODEL_DIR,
                exc_info=True,
            )
            return None, None


def _temperature_of(model_config) -> float:
    """The checkpoint's calibration temperature, or 1.0 if absent or invalid."""
    value = getattr(model_config, "calibration_temperature", None)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TEMPERATURE
    # A non-positive or absurd value would invert or flatten every score.
    return value if 0.05 <= value <= 20.0 else DEFAULT_TEMPERATURE


def count_turns(text: str) -> int:
    """Messages of conversation visible in the text.

    Delegates to app.turns, which counts chat bubbles rather than lines. The
    name is kept because callers and the docs use it, but the unit is a message:
    OCR wraps one bubble across several lines, and counting lines inflated two
    real screenshot sets to 146 and 103.
    """
    return count_messages(text)


def _confidence_for(turns: int) -> str:
    """Map visible turns onto a confidence band from the measured accuracy."""
    if turns >= MIN_TURNS_FOR_HIGH_CONFIDENCE:
        return "high"
    if turns >= MIN_TURNS_FOR_MODERATE_CONFIDENCE:
        return "moderate"
    if turns >= MIN_TURNS_FOR_ANY_CONFIDENCE:
        return "low"
    return "insufficient"


def _window_starts(length: int, body: int) -> list[int]:
    """Start offsets covering `length` tokens in windows of `body`, STRIDE apart.

    The last window is pinned to the end, so the tail of a conversation — where
    payment demands and key handovers tend to be — is always read in full.
    """
    if length <= body:
        return [0]
    starts = list(range(0, length - body + 1, STRIDE))
    if starts[-1] + body < length:
        starts.append(length - body)
    return starts


def _message_windows(tokenizer, text: str, body: int | None = None) -> list[list[int]]:
    """Token ids of each window, cut only between messages (lines).

    Each window packs as many whole messages as fit in WINDOW - 2 tokens. The
    next window starts at the first message at least STRIDE tokens after the
    previous start — never later than the message right after the previous
    window, so nothing is skipped. The last window is packed backwards from the
    final message, so the tail is read with full context. A single message
    longer than a window is the only thing ever cut, by token windows over that
    message alone. `body` overrides the window size, for callers that must
    leave room for a second segment (eval/zero_shot_test.py: an NLI hypothesis).

    Tokenizing message by message gives the same ids as tokenizing the whole
    text for this tokenizer (checked on 416 texts), so every window is an exact
    slice of the conversation's token sequence.
    """
    if body is None:
        body = WINDOW - 2  # room for the start and end tokens
    ids = [tokenizer(line, add_special_tokens=False)["input_ids"]
           for line in text.split("\n") if line.strip()]
    if not ids:
        return [[]]
    offsets = [0]
    for message in ids:
        offsets.append(offsets[-1] + len(message))
    last = len(ids) - 1

    def pack(first):
        end, total = first, len(ids[first])
        while end < last and total + len(ids[end + 1]) <= body:
            end += 1
            total += len(ids[end])
        return end

    spans, first = [], 0
    while True:
        if len(ids[first]) > body:
            spans.append((first, first))
            end = first
        else:
            end = pack(first)
            spans.append((first, end))
        if end >= last:
            break
        target = offsets[first] + STRIDE
        following = next((i for i in range(first + 1, end + 1) if offsets[i] >= target), end + 1)
        first = min(following, end + 1)

    # Pin the last window to the end with as much context as fits.
    if len(ids[last]) <= body:
        start, total = last, len(ids[last])
        while start > 0 and total + len(ids[start - 1]) <= body:
            start -= 1
            total += len(ids[start])
        if start < spans[-1][0]:
            spans[-1] = (start, last)

    windows = []
    for first, end in spans:
        tokens = [token for message in ids[first:end + 1] for token in message]
        if len(tokens) <= body:
            windows.append(tokens)
        else:  # one message longer than a window
            windows += [tokens[s:s + body] for s in _window_starts(len(tokens), body)]
    return windows


def _window_scores(text: str) -> list[float] | None:
    """P(SCAM) for every window of the text, or None if the model is unavailable."""
    tokenizer, model = _load()
    if model is None:
        return None

    import torch

    scores = []
    with torch.no_grad():
        for window in _message_windows(tokenizer, text):
            encoded = tokenizer.prepare_for_model(
                window, add_special_tokens=True, return_tensors="pt"
            )
            encoded = {
                key: value.unsqueeze(0) if value.dim() == 1 else value
                for key, value in encoded.items()
            }
            probabilities = (model(**encoded).logits / _temperature).softmax(-1)[0]
            scores.append(float(probabilities[_scam_index]))
    return scores or [0.5]


def _model_probability(text: str) -> float | None:
    """P(SCAM) for the whole text: the highest-scoring window."""
    scores = _window_scores(text)
    return None if scores is None else max(scores)


def classify(text: str, language: str = "auto") -> dict:
    """Scam probability for `text`, from the fine-tuned model alone.

    Takes no red flags: layer 1 runs independently and its findings are evidence
    for the narrator, not an input to this number. See the note at the top of
    the module.

    Returns a dict with at least `scam_probability` (0..1). Callers should also
    read `confidence`: on "insufficient" the probability is deliberately neutral
    and means "not enough conversation to judge", not "low risk".
    """
    turns = count_turns(text)
    confidence = _confidence_for(turns)
    model_probability = _model_probability(text)

    if model_probability is None:
        # No weights on disk. Returning a fabricated score would be worse than
        # admitting we cannot judge, so this reports unknown and says why.
        return {
            "scam_probability": UNKNOWN_PROBABILITY,
            "model_probability": None,
            "turns": turns,
            "confidence": "insufficient",
            "language": language,
            "model": None,
            "status": "model_unavailable",
            "note": (
                "No classifier weights at FINETUNED_MODEL_DIR, so no probability "
                "could be computed. Layer 1 red flags are unaffected."
            ),
        }

    # Below the usable turn threshold the model fails toward LEGITIMATE, so a
    # low score here is not evidence of safety. Report unknown instead of
    # handing back a false all-clear.
    if confidence == "insufficient" and model_probability < UNKNOWN_PROBABILITY:
        scam_probability = UNKNOWN_PROBABILITY
        status = "insufficient_context"
    else:
        scam_probability = model_probability
        status = "ok"

    result = {
        "scam_probability": round(scam_probability, 4),
        "model_probability": round(model_probability, 4),
        "turns": turns,
        "confidence": confidence,
        "language": language,
        "model": config.PRIMARY_MODEL,
        "status": status,
    }

    if status == "insufficient_context":
        result["note"] = (
            f"Only {turns} message(s) visible. Accuracy below "
            f"{MIN_TURNS_FOR_ANY_CONFIDENCE} turns is worse than guessing, and "
            f"errs toward 'legitimate', so this is reported as unknown rather "
            f"than as low risk. Send more of the conversation."
        )
    elif confidence in ("low", "moderate"):
        result["note"] = (
            f"{turns} message(s) visible; measured accuracy at this length is "
            f"below full-conversation accuracy. Treat as indicative."
        )

    return result
