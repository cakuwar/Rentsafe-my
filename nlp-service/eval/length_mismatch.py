"""How much of a real conversation the model could see, before and after windowing.

The deployed model was fine-tuned with 256-token inputs on conversations that
almost all fit. Real conversations through the OCR path are longer. This
measures, with the deployed tokenizer:

  * token lengths of the training and validation splits,
  * token lengths of the real conversations in training/gates.json,
  * the share of each real conversation a single 256-token pass could read,
  * how many message-aligned windows `app.layer2.classifier` now scores instead.

    python eval/length_mismatch.py

Writes eval/results/length_mismatch.json. Needs no model weights, only the
tokenizer.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from transformers import AutoTokenizer

from app import config
from app.layer2.classifier import STRIDE, WINDOW, _message_windows

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
DATA = os.path.join(NLP, "..", "data", "processed")
GATES = os.path.join(NLP, "training", "gates.json")
OUT = os.path.join(HERE, "results", "length_mismatch.json")

OLD_MAX_LENGTH = 256   # what the first model was trained and served with
REAL = ("real_legit_production", "real_legit_clean", "real_scam_production")


def lengths(tokenizer, texts):
    return [len(tokenizer(text, add_special_tokens=True)["input_ids"]) for text in texts]


def describe(values):
    series = pd.Series(values)
    return {
        "rows": int(series.size),
        "median": int(series.median()),
        "p95": int(series.quantile(0.95)),
        "max": int(series.max()),
        "over_256": int((series > OLD_MAX_LENGTH).sum()),
        "over_512": int((series > WINDOW).sum()),
    }


def main():
    tokenizer = AutoTokenizer.from_pretrained(config.FINETUNED_MODEL_DIR)
    tokenizer.model_max_length = 10**6   # measuring, not encoding for the model

    report = {"tokenizer": config.FINETUNED_MODEL_DIR,
              "old_max_length": OLD_MAX_LENGTH, "window": WINDOW, "stride": STRIDE,
              "splits": {}, "real": {}}

    for split in ("train", "val"):
        frame = pd.read_csv(os.path.join(DATA, "random", f"{split}.csv"))
        report["splits"][f"random/{split}"] = describe(lengths(tokenizer, frame["text"]))
    pairs = pd.read_csv(os.path.join(DATA, "augmented", "minimal_pairs_train.csv"))
    report["splits"]["augmented/minimal_pairs_train"] = describe(
        lengths(tokenizer, pairs["text"]))

    with open(GATES, encoding="utf-8") as handle:
        gates = json.load(handle)
    for name in REAL:
        tokens = lengths(tokenizer, [gates[name]["text"]])[0]
        report["real"][name] = {
            "tokens": tokens,
            "seen_at_256_pct": round(100 * min(1.0, OLD_MAX_LENGTH / tokens), 1),
            "windows_now": len(_message_windows(tokenizer, gates[name]["text"])),
        }

    print(f"{'set':<34}{'median':>8}{'p95':>6}{'max':>6}{'>256':>6}{'>512':>6}")
    for name, stats in report["splits"].items():
        print(f"{name:<34}{stats['median']:>8}{stats['p95']:>6}{stats['max']:>6}"
              f"{stats['over_256']:>6}{stats['over_512']:>6}")
    print()
    for name, stats in report["real"].items():
        print(f"{name:<24} {stats['tokens']:>4} tokens   seen at 256: "
              f"{stats['seen_at_256_pct']:>5}%   windows now: {stats['windows_now']}")

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
