"""Score the deployed model on the sealed held-out conversations.

This is the only evaluation in the project whose number means anything about
real-world performance: everything else is measured on data the model trained on
or was selected against. See data/test_real/README.md.

Refuses to run on an empty folder rather than reporting a vacuous pass, and
refuses to score any row that overlaps the training splits.

    python eval/test_real.py

Writes eval/results/test_real.json.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_recall_fscore_support,
)
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app import config
from app.layer1.red_flags import analyse
from app.normaliser.normaliser import normalise
from app.turns import count_messages

HERE = os.path.dirname(os.path.abspath(__file__))
TEST_DIR = os.path.join(HERE, "..", "..", "data", "test_real")
PROCESSED = os.path.join(HERE, "..", "..", "data", "processed")
OUT = os.path.join(HERE, "results", "test_real.json")
LABELS = {"LEGITIMATE": 0, "SCAM": 1}
MAX_LENGTH = 256


def load_held_out() -> pd.DataFrame:
    paths = sorted(glob.glob(os.path.join(TEST_DIR, "*.csv")))
    if not paths:
        raise SystemExit(
            "data/test_real/ holds no CSV files.\n"
            "This evaluation is the only one that speaks to real-world\n"
            "performance, so it will not report a number until there is\n"
            "something sealed to report on. See data/test_real/README.md."
        )
    frame = pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)
    frame["label"] = frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    return frame


def training_texts() -> set[str]:
    texts = set()
    for path in glob.glob(os.path.join(PROCESSED, "*", "*.csv")):
        frame = pd.read_csv(path)
        if "text" in frame.columns:
            texts.update(" ".join(str(t).split()).lower() for t in frame["text"])
    return texts


def check_sealed(frame: pd.DataFrame) -> list[int]:
    """Row numbers that also appear in train or val."""
    seen = training_texts()
    return [
        index
        for index, text in enumerate(frame["text"])
        if " ".join(str(text).split()).lower() in seen
    ]


def main():
    frame = load_held_out()
    overlap = check_sealed(frame)
    if overlap:
        raise SystemExit(
            f"{len(overlap)} row(s) also appear in data/processed — rows "
            f"{overlap}.\nThey are not held out and cannot be scored here."
        )

    tokenizer = AutoTokenizer.from_pretrained(config.FINETUNED_MODEL_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(
        config.FINETUNED_MODEL_DIR
    )
    model.eval()
    scam_index = {
        str(label).upper(): index
        for label, index in (model.config.label2id or {}).items()
    }.get("SCAM", 1)

    probabilities = []
    with torch.no_grad():
        for start in range(0, len(frame), 16):
            batch = frame["text"].iloc[start:start + 16].tolist()
            encoded = tokenizer(
                batch, truncation=True, max_length=MAX_LENGTH,
                padding=True, return_tensors="pt",
            )
            probabilities.extend(
                model(**encoded).logits.softmax(-1)[:, scam_index].tolist()
            )

    actual = np.array([LABELS[label] for label in frame["label"]])
    predicted = (np.array(probabilities) >= 0.5).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        actual, predicted, average="binary", zero_division=0
    )
    matrix = confusion_matrix(actual, predicted, labels=[0, 1])

    print(f"{len(frame)} sealed conversations "
          f"({int(actual.sum())} scam / {int((1 - actual).sum())} legitimate)")
    print()
    print(classification_report(
        actual, predicted, target_names=["LEGITIMATE", "SCAM"],
        digits=4, zero_division=0,
    ))
    print(f"macro-F1 {f1_score(actual, predicted, average='macro'):.4f}   "
          f"MCC {matthews_corrcoef(actual, predicted):.4f}")

    result = {
        "model": config.PRIMARY_MODEL,
        "weights": os.path.basename(config.FINETUNED_MODEL_DIR),
        "conversations": int(len(frame)),
        "scam": int(actual.sum()),
        "legitimate": int((1 - actual).sum()),
        "accuracy": round(float(accuracy_score(actual, predicted)), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "macro_f1": round(float(f1_score(actual, predicted, average="macro")), 4),
        "mcc": round(float(matthews_corrcoef(actual, predicted)), 4),
        "confusion_matrix": {
            "legit_correct": int(matrix[0][0]),
            "false_alarms": int(matrix[0][1]),
            "missed_scams": int(matrix[1][0]),
            "scam_correct": int(matrix[1][1]),
        },
        "rows": [
            {
                "label": row["label"],
                "p_scam": round(float(probability), 4),
                "messages": count_messages(row["text"]),
                "red_flags": analyse(normalise(row["text"]))["red_flags"],
            }
            for (_, row), probability in zip(frame.iterrows(), probabilities)
        ],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as handle:
        json.dump(result, handle, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
