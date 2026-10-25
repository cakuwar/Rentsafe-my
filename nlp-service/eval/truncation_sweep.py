"""Accuracy of the deployed classifier against how much conversation is visible.

Re-runs the sweep from docs/MODEL_COMPARISON.md §6.4 in the unit the guard now
uses: **messages**, counted by app.turns, not lines. The original sweep cut on
line breaks, so its thresholds did not mean what the guard assumed.

The output sets the guard: the band where the model scores below the always-SCAM
baseline is the band where reporting a low score would be worse than useless, so
that is where "insufficient_context" belongs.

    python eval/truncation_sweep.py

Writes eval/results/truncation_sweep.json.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app import config
from app.turns import split_messages

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "data", "processed", "random", "val.csv")
OUT = os.path.join(HERE, "results", "truncation_sweep.json")
LABELS = {"LEGITIMATE": 0, "SCAM": 1}
MAX_LENGTH = 256
CUTS = [1, 2, 3, 4, 5, 6, 7, 8, None]
MIN_MESSAGES = 8


def load_model():
    tokenizer = AutoTokenizer.from_pretrained(config.FINETUNED_MODEL_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(
        config.FINETUNED_MODEL_DIR
    )
    model.eval()
    scam_index = {
        str(label).upper(): index
        for label, index in (model.config.label2id or {}).items()
    }.get("SCAM", 1)
    return tokenizer, model, scam_index


def probabilities(tokenizer, model, scam_index, texts, batch=16):
    out = []
    with torch.no_grad():
        for start in range(0, len(texts), batch):
            encoded = tokenizer(
                texts[start:start + batch],
                truncation=True, max_length=MAX_LENGTH,
                padding=True, return_tensors="pt",
            )
            out.extend(model(**encoded).logits.softmax(-1)[:, scam_index].tolist())
    return np.array(out)


def main():
    frame = pd.read_csv(DATA)
    frame["label"] = frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    frame["messages"] = [split_messages(text) for text in frame["text"]]

    # Only conversations long enough to be truncated to every cut.
    frame = frame[frame["messages"].apply(len) >= MIN_MESSAGES].reset_index(drop=True)
    actual = np.array([LABELS[label] for label in frame["label"]])

    # The baseline is computed on THIS subset, not the whole validation set:
    # filtering by length changes the class balance.
    always_scam = np.ones_like(actual)
    baseline_accuracy = accuracy_score(actual, always_scam)
    _, _, baseline_f1, _ = precision_recall_fscore_support(
        actual, always_scam, average="binary", zero_division=0
    )

    print(f"{len(frame)} conversations with >= {MIN_MESSAGES} messages")
    print(f"  {int(actual.sum())} scam / {int((1 - actual).sum())} legitimate")
    print(f"  always-SCAM baseline on this subset: "
          f"accuracy {baseline_accuracy:.3f}, F1 {baseline_f1:.3f}")
    print()

    tokenizer, model, scam_index = load_model()
    rows = []
    print(f"{'messages':>9} {'accuracy':>9} {'f1':>7} {'vs baseline':>12}")
    for cut in CUTS:
        texts = [
            "\n".join(messages if cut is None else messages[:cut])
            for messages in frame["messages"]
        ]
        predicted = (probabilities(tokenizer, model, scam_index, texts) >= 0.5).astype(int)
        accuracy = accuracy_score(actual, predicted)
        _, _, f1, _ = precision_recall_fscore_support(
            actual, predicted, average="binary", zero_division=0
        )
        beats = accuracy > baseline_accuracy
        rows.append({
            "messages": cut,
            "accuracy": round(float(accuracy), 4),
            "f1": round(float(f1), 4),
            "beats_baseline": bool(beats),
        })
        label = "all" if cut is None else str(cut)
        print(f"{label:>9} {accuracy:>9.3f} {f1:>7.3f} "
              f"{accuracy - baseline_accuracy:>+12.3f}")

    usable = [row["messages"] for row in rows
              if row["beats_baseline"] and row["messages"] is not None]
    threshold = min(usable) if usable else None

    print()
    print(f"Smallest message count beating the baseline: {threshold}")
    print(f"=> guard should fire below {threshold} messages")

    result = {
        "model": config.PRIMARY_MODEL,
        "weights": os.path.basename(config.FINETUNED_MODEL_DIR),
        "unit": "messages (app.turns.split_messages)",
        "subset": {
            "conversations": int(len(frame)),
            "min_messages": MIN_MESSAGES,
            "scam": int(actual.sum()),
            "legitimate": int((1 - actual).sum()),
        },
        "baseline_always_scam": {
            "accuracy": round(float(baseline_accuracy), 4),
            "f1": round(float(baseline_f1), 4),
        },
        "sweep": rows,
        "guard_threshold_messages": threshold,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as handle:
        json.dump(result, handle, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
