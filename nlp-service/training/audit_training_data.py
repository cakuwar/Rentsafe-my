"""Check a training set for shortcuts before any GPU time is spent on it.

The first model learned "itemised prices -> scam" because the data rewarded it.
This measures, for the combined training set, how well each cheap surface
feature predicts the label on its own. If any of them is a strong predictor, a
model will learn it instead of the mechanics, and retraining is wasted.

Also checks the augmented set cannot leak into evaluation: no row may match the
validation split, the sealed test set, or the real screenshot transcripts.

    python training/audit_training_data.py

Writes eval/results/training_data_audit.json. Exit status 1 if a shortcut or
leak is found, so it can gate the notebook.
"""
import glob
import io
import json
import os
import re
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
NLP = os.path.join(ROOT, "nlp-service")
OUT = os.path.join(NLP, "eval", "results", "training_data_audit.json")

# A single surface feature predicting the label this well is a shortcut.
MAX_FEATURE_ACCURACY = 0.65

AMOUNT = re.compile(r"\brm\s?\d", re.IGNORECASE)


def load(path):
    frame = pd.read_csv(path)
    frame["label"] = frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    return frame


def features(text):
    text = str(text)
    return {
        "rm_amounts": len(AMOUNT.findall(text)),
        "messages": len([l for l in text.splitlines() if l.strip()]),
        "characters": len(text),
        "question_marks": text.count("?"),
        "english_share": (
            len(re.findall(r"\b(?:the|and|you|is|it|to|for|can|will)\b", text, re.I))
            / max(1, len(text.split()))
        ),
    }


def best_single_threshold(values, labels):
    """Highest accuracy any one threshold on one feature achieves."""
    pairs = sorted(zip(values, labels))
    best = max(labels.count(1), labels.count(0)) / len(labels)
    for cut in sorted(set(values)):
        for direction in (1, -1):
            predicted = [
                1 if (value > cut if direction == 1 else value <= cut) else 0
                for value, _ in pairs
            ]
            accuracy = sum(p == l for p, (_, l) in zip(predicted, pairs)) / len(pairs)
            best = max(best, accuracy)
    return best


def audit(frame, name):
    rows = [features(t) for t in frame["text"]]
    labels = [1 if label == "SCAM" else 0 for label in frame["label"]]
    majority = max(labels.count(1), labels.count(0)) / len(labels)
    result = {"rows": len(frame), "scam": labels.count(1),
              "legitimate": labels.count(0), "majority_baseline": round(majority, 3),
              "features": {}}
    print(f"\n{name}: {len(frame)} rows ({labels.count(1)} scam / "
          f"{labels.count(0)} legitimate, majority {majority:.1%})")
    print(f"  {'feature':<16}{'scam mean':>11}{'legit mean':>12}{'1-feature acc':>15}")
    for feature in rows[0]:
        values = [row[feature] for row in rows]
        scam = [v for v, l in zip(values, labels) if l == 1]
        legit = [v for v, l in zip(values, labels) if l == 0]
        accuracy = best_single_threshold(values, labels)
        flag = "  <-- SHORTCUT" if accuracy > MAX_FEATURE_ACCURACY else ""
        print(f"  {feature:<16}{sum(scam) / len(scam):>11.2f}"
              f"{sum(legit) / len(legit):>12.2f}{accuracy:>15.1%}{flag}")
        result["features"][feature] = {
            "scam_mean": round(sum(scam) / len(scam), 3),
            "legit_mean": round(sum(legit) / len(legit), 3),
            "single_feature_accuracy": round(accuracy, 3),
            "shortcut": accuracy > MAX_FEATURE_ACCURACY,
        }
    rm4 = [(r["rm_amounts"] >= 4, l) for r, l in zip(rows, labels)]
    with_4 = [l for flag, l in rm4 if flag]
    if with_4:
        share = sum(with_4) / len(with_4)
        result["p_scam_given_4_amounts"] = round(share, 3)
        print(f"  P(SCAM | >= 4 RM amounts) = {share:.1%}  (n={len(with_4)})")
    return result


def key(text):
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def main():
    original = load(os.path.join(ROOT, "data", "processed", "random", "train.csv"))
    augmented = load(os.path.join(ROOT, "data", "processed", "augmented",
                                  "minimal_pairs_train.csv"))
    combined = pd.concat([original[["text", "label"]], augmented[["text", "label"]]],
                         ignore_index=True)

    report = {
        "original_train": audit(original, "ORIGINAL training set"),
        "augmented_only": audit(augmented, "MINIMAL PAIRS only"),
        "combined": audit(combined, "COMBINED (what the notebook trains on)"),
    }

    # --- leakage into evaluation ------------------------------------------
    print("\nLEAKAGE into anything used for evaluation:")
    augmented_keys = {key(t) for t in augmented["text"]}
    protected = {
        "validation split": [key(t) for t in load(os.path.join(
            ROOT, "data", "processed", "random", "val.csv"))["text"]],
        "sealed test set": [
            key(t) for path in glob.glob(os.path.join(ROOT, "data", "test_real", "*.csv"))
            for t in load(path)["text"]
        ],
        "minimal-pair test split": [key(t) for t in load(os.path.join(
            ROOT, "data", "processed", "augmented", "minimal_pairs_test.csv"))["text"]],
    }
    transcripts = glob.glob(os.path.join(
        NLP, "eval", "results", "blind_legit", "diagnosis", "transcript_*.txt"))
    protected["real legit transcript"] = [
        key(io.open(path, encoding="utf-8").read()) for path in transcripts
    ]
    leaks = {}
    for name, keys in protected.items():
        overlap = sum(1 for k in keys if k in augmented_keys)
        leaks[name] = overlap
        print(f"  {name:<26} {overlap} overlapping rows")
    report["leakage"] = leaks

    shortcut = [
        name for name, feature in report["combined"]["features"].items()
        if feature["shortcut"]
    ]
    report["verdict"] = {
        "shortcuts_in_combined": shortcut,
        "leaks": {k: v for k, v in leaks.items() if v},
        "ok": not shortcut and not any(leaks.values()),
    }
    print()
    print("VERDICT:", "OK to train" if report["verdict"]["ok"] else
          f"NOT OK - shortcuts {shortcut}, leaks {report['verdict']['leaks']}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as handle:
        json.dump(report, handle, indent=2)
    return 0 if report["verdict"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
