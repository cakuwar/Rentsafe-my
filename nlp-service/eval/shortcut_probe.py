"""Is the model reading scam mechanics, or conversation length and money talk?

Hypothesis from the blind test: the training data pairs SCAM with long,
money-dense conversations and LEGITIMATE with short, plain ones, so the model
learned "long + prices + terms = scam". A real legitimate agent chat with an
itemised breakdown and T&Cs then scores 0.9997.

This isolates each ingredient by growing a known-legitimate conversation one
component at a time. Nothing scammy is ever added. If the score climbs, the
component that moved it is the shortcut.

    python eval/shortcut_probe.py

Writes eval/results/shortcut_probe.json.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app import config

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results", "shortcut_probe.json")

# A plain legitimate conversation. Scored under 0.01 in behaviour_checks.py.
BASE = [
    "Renter: Hi, is the studio still available?",
    "Owner: Yes it is. When are you looking to move in?",
    "Renter: Early next month. Could I view it this weekend?",
    "Owner: Sure, Saturday afternoon works. I'll meet you at the lobby.",
    "Renter: How much is the deposit?",
    "Owner: Two months plus half a month utilities, paid on signing.",
    "Renter: Is the agreement stamped?",
    "Owner: Yes, we stamp it at the office. See you Saturday.",
]

# Ingredients, all taken in spirit from the real iBilik conversation, none of
# them a scam mechanic. Payment is only ever discussed as after viewing.
PRICES = [
    "Owner: Move-in breakdown: 1 month deposit RM 600, 1 month rental RM 300, "
    "move-in fee RM 300, access card deposit RM 100. Total move-in RM 1300.",
]
TERMS = [
    "Owner: Terms: minimum 12-month tenancy. Early termination may incur a "
    "RM300 penalty. Move-in fee includes agreement fee and aircond servicing.",
]
PROMO = [
    "Owner: MERDEKA MONTH - book now and enjoy 50% off your first month "
    "rental. Limited time only. Limited units available.",
]
CHATTER = [
    "Renter: Is cooking allowed?",
    "Owner: Only light cooking, bring your own induction cooker.",
    "Renter: Is wifi included?",
    "Owner: Yes, free wifi and water included.",
    "Renter: Is there parking?",
    "Owner: Yes, one parking bay for the unit.",
    "Renter: Can I move in a bit earlier?",
    "Owner: Let me check with the office and get back to you.",
]


def load():
    tokenizer = AutoTokenizer.from_pretrained(config.FINETUNED_MODEL_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(
        config.FINETUNED_MODEL_DIR
    )
    model.eval()
    scam = {
        str(k).upper(): v for k, v in (model.config.label2id or {}).items()
    }.get("SCAM", 1)
    return tokenizer, model, scam


def score(tokenizer, model, scam, lines):
    with torch.no_grad():
        encoded = tokenizer(
            "\n".join(lines), truncation=True, max_length=256, return_tensors="pt"
        )
        return float(model(**encoded).logits.softmax(-1)[0][scam])


def main():
    tokenizer, model, scam = load()

    variants = [
        ("base (plain legit, 8 msgs)", BASE),
        ("+ itemised prices", BASE + PRICES),
        ("+ terms & penalties", BASE + TERMS),
        ("+ promo / 'limited units'", BASE + PROMO),
        ("+ neutral chatter (length only)", BASE + CHATTER),
        ("+ prices + terms", BASE + PRICES + TERMS),
        ("+ prices + terms + promo", BASE + PRICES + TERMS + PROMO),
        ("+ everything", BASE + PRICES + TERMS + PROMO + CHATTER),
        ("promo + prices + terms ALONE", PROMO + PRICES + TERMS),
    ]

    print(f"{'variant':<36}{'msgs':>6}{'tokens':>8}{'p(scam)':>10}")
    print("-" * 60)
    rows = []
    for label, lines in variants:
        p = score(tokenizer, model, scam, lines)
        tokens = len(tokenizer.tokenize("\n".join(lines)))
        rows.append({"variant": label, "messages": len(lines),
                     "tokens": tokens, "p_scam": round(p, 4)})
        flag = "   <-- flipped to SCAM" if p >= 0.5 else ""
        print(f"{label:<36}{len(lines):>6}{tokens:>8}{p:>10.4f}{flag}")

    base = rows[0]["p_scam"]
    length_only = rows[4]["p_scam"]
    money = rows[5]["p_scam"]
    print()
    if length_only < 0.5 and money >= 0.5:
        verdict = ("CONFIRMED: money/terms language flips a legitimate "
                   "conversation to SCAM; length alone does not.")
    elif length_only >= 0.5:
        verdict = "LENGTH is sufficient on its own to flip the verdict."
    elif money < 0.5 and rows[7]["p_scam"] < 0.5:
        verdict = ("NOT CONFIRMED: none of these ingredients flips it. The "
                   "cause is something else.")
    else:
        verdict = "MIXED: see the table."
    print(verdict)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as handle:
        json.dump({"model": config.PRIMARY_MODEL, "base_p_scam": base,
                   "variants": rows, "verdict": verdict}, handle, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
