"""Package the acceptance-gate inputs the retraining notebook scores against.

A retrained model is only accepted if it passes behavioural gates, not just a
validation F1 — the first model reached 0.99 F1 while calling a real legitimate
conversation a scam. The notebook runs in Colab without Tesseract, so the gate
inputs are produced here, locally, through the exact pipeline production uses
(screenshots -> bubble segmentation -> "Renter:/Owner:" text), and uploaded as
one JSON file.

IMPORTANT — what these gates can and cannot show:

* The real legitimate conversation was used to DIAGNOSE the shortcut, and the
  training data was designed knowing how it failed. Passing it is necessary but
  it is NOT independent evidence the model generalises.
* The real scam conversation's text was used to write layer 1's rules.
* The minimal-pair test split is held out from training but comes from the same
  generator, so it tests "learned the mechanic as written", not "generalises".
* Only data/test_real/ — still empty — can answer the real question.

    python training/build_gates.py

Writes training/gates.json.
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
sys.path.insert(0, NLP)

from app.ocr.ocr import screenshots_to_conversation  # noqa: E402
from training.redaction import LIST, leaks, names, redact  # noqa: E402

ROOT = os.path.dirname(NLP)
SAMPLES = os.path.join(ROOT, "data", "samples")
OUT = os.path.join(HERE, "gates.json")


def read_pages(prefix, count):
    pages = []
    for number in range(1, count + 1):
        with open(os.path.join(SAMPLES, f"{prefix}_p{number}.jpg"), "rb") as handle:
            pages.append(handle.read())
    return pages


def main():
    if not names():
        sys.exit(f"refusing to build: no names to redact in {LIST}. "
                 "Real screenshots carry personal data.")

    print("running the production pipeline on the real screenshots...")
    legit = screenshots_to_conversation(read_pages("legit", 8))
    scam = screenshots_to_conversation(read_pages("scam", 4))
    print(f"  legit: method={legit['method']}, {len(legit['messages'])} messages")
    print(f"  scam:  method={scam['method']}, {len(scam['messages'])} messages")

    transcript = io.open(
        os.path.join(NLP, "eval", "results", "blind_legit", "diagnosis",
                     "transcript_b_labelled.txt"),
        encoding="utf-8",
    ).read()

    base = [
        "Renter: Hi, is the studio still available?",
        "Owner: Yes it is. When are you looking to move in?",
        "Renter: Early next month. Could I view it this weekend?",
        "Owner: Sure, Saturday afternoon works. I'll meet you at the lobby.",
        "Renter: How much is the deposit?",
        "Owner: Two months plus half a month utilities, paid on signing.",
        "Renter: Is the agreement stamped?",
        "Owner: Yes, we stamp it at the office. See you Saturday.",
    ]
    prices = ("Owner: Move-in breakdown: 1 month deposit RM 600, 1 month rental "
              "RM 300, move-in fee RM 300, access card deposit RM 100. Total "
              "move-in RM 1300.")
    terms = ("Owner: Terms: minimum 12-month tenancy. Early termination may incur "
             "a RM300 penalty.")

    scam_full = [
        "Renter: Hi, is the room still available?",
        "Owner: Yes it is. Nak masuk bila ya?",
        "Renter: Early next month.",
        "Renter: Boleh pergi viewing dulu tak?",
        "Owner: I'm outstation in Sabah now.",
        "Owner: Cannot open the unit sorry.",
        "Owner: Kalau nak lock the room, transfer deposit RM800 dulu.",
        "Renter: Can I see it first?",
        "Owner: Ramai orang tengah tanya.",
        "Owner: Lepas transfer saya pos kunci.",
    ]
    mechanics = {4, 5, 6, 8, 9}

    gates = {
        "_note": (
            "The real legitimate conversation was used to diagnose the shortcut "
            "and the training data was designed knowing how it failed; passing "
            "it is necessary, not independent evidence. Only data/test_real/ "
            "is independent."
        ),
        "real_legit_production": {
            "expect": "LEGITIMATE",
            "text": redact(legit["text"]),
            "note": "8 real iBilik screenshots through the production pipeline",
        },
        "real_legit_clean": {
            "expect": "LEGITIMATE",
            "text": redact(transcript),
            "note": "the same conversation hand-transcribed; isolates the model from OCR",
        },
        "real_scam_production": {
            "expect": "SCAM",
            "text": redact(scam["text"]),
            "note": "4 real scam screenshots through the production pipeline",
        },
        "shortcut_base": {"expect": "LEGITIMATE", "text": "\n".join(base)},
        "shortcut_plus_prices": {
            "expect": "LEGITIMATE", "text": "\n".join(base + [prices]),
            "note": "one line of itemised prices flipped the old model to 0.9492",
        },
        "shortcut_plus_prices_terms": {
            "expect": "LEGITIMATE", "text": "\n".join(base + [prices, terms]),
        },
        "ablation_full_scam": {"expect": "SCAM", "text": "\n".join(scam_full)},
        "ablation_mechanics_removed": {
            "expect": "LEGITIMATE",
            "text": "\n".join(l for i, l in enumerate(scam_full) if i not in mechanics),
            "note": "old model scored this 0.9995 with no scam content left",
        },
        "english_courier_scam": {
            "expect": "SCAM",
            "text": "\n".join([
                "Renter: Is the unit at Mont Kiara still open?",
                "Owner: Yes, but I have three people interested.",
                "Renter: I'd like to see it first.",
                "Owner: I'm outstation. I can post the access card to you.",
                "Renter: I'd prefer to meet in person.",
                "Owner: No need to meet. Pay one month rent and I'll mail the keys.",
                "Renter: How do I know the unit exists?",
                "Owner: I'll send a video call later. Transfer before 9pm tonight.",
            ]),
            "note": "old model: 0.0282 (missed). Author-written.",
        },
    }

    for name, gate in gates.items():
        if isinstance(gate, dict) and leaks(gate["text"]):
            sys.exit(f"refusing to write: gate {name!r} still contains personal data")

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(gates, handle, indent=2, ensure_ascii=False)
    print(f"\nwrote {OUT}  ({len(gates) - 1} gates)")


if __name__ == "__main__":
    main()
