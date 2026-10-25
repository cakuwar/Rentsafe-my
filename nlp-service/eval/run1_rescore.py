"""Re-score the retrain RUN 1 model locally. Diagnosis only — its verdict stands.

Run 1 was judged with fixed-offset windows and failed (A3, A6). Run 2 changed
two things at once — message-aligned windows and new training rows — and got
worse. This separates them, using the run-1 weights:

  1. gates with run 1's own fixed-offset windows   (must reproduce Colab exactly)
  2. gates with message-aligned windows            (the window change alone)
  3. run 2's held-out test split, by row kind       (are prefix/core rows
                                                     hard even for a model never
                                                     trained on them?)

Raw probabilities (temperature 1), as the notebook's pass/fail uses.

    python eval/run1_rescore.py

Needs models/xlm-roberta-scam-v3-run1/ (the run-1 download; not deployed).
Writes eval/results/run1_rescore.json.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.layer2.classifier import WINDOW, _message_windows, _window_starts

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
MODEL = os.path.join(NLP, "models", "xlm-roberta-scam-v3-run1")
GATES = os.path.join(NLP, "training", "gates.json")
PAIR_TEST = os.path.join(NLP, "..", "data", "processed", "augmented", "minimal_pairs_test.csv")
OUT = os.path.join(HERE, "results", "run1_rescore.json")

tokenizer = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForSequenceClassification.from_pretrained(MODEL).eval()
SCAM = {k.upper(): v for k, v in model.config.label2id.items()}["SCAM"]


def score(window):
    enc = tokenizer.prepare_for_model(window, add_special_tokens=True, return_tensors="pt")
    enc = {k: v.unsqueeze(0) if v.dim() == 1 else v for k, v in enc.items()}
    with torch.no_grad():
        return float(model(**enc).logits.softmax(-1)[0][SCAM])


def offset_windows(text):
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    body = WINDOW - 2
    return [ids[s:s + body] for s in _window_starts(len(ids), body)]


def p(text, windows):
    return max(score(w) for w in windows(text))


def main():
    gates = {k: v for k, v in json.load(open(GATES, encoding="utf-8")).items()
             if not k.startswith("_")}
    report = {"model": "retrain run 1 (not accepted)", "gates": {}, "run2_test_by_kind": {}}
    print(f"{'gate':<30}{'expect':<12}{'offset':>8}{'message':>9}")
    for name, gate in gates.items():
        a = p(gate["text"], offset_windows)
        b = p(gate["text"], lambda t: _message_windows(tokenizer, t))
        report["gates"][name] = {"expect": gate["expect"], "offset_windows": round(a, 4),
                                 "message_windows": round(b, 4)}
        mark = lambda x: "ok" if (x >= 0.5) == (gate["expect"] == "SCAM") else "FAIL"
        print(f"{name:<30}{gate['expect']:<12}{a:>8.4f}{b:>9.4f}   {mark(a):>4} -> {mark(b)}")

    test = pd.read_csv(PAIR_TEST)
    test["p"] = [p(t, lambda x: _message_windows(tokenizer, x)) for t in test["text"]]
    test["correct"] = (test["p"] >= 0.5) == (test["label"] == "SCAM")
    print("\nrun 2's held-out test split, scored by the run-1 model:")
    for kind, rows in test.groupby("kind"):
        entry = {"rows": int(len(rows)), "row_accuracy": round(float(rows["correct"].mean()), 4)}
        by_label = rows.groupby("label")["correct"].mean().round(4).to_dict()
        entry["by_label"] = {k: float(v) for k, v in by_label.items()}
        if kind in ("full", "fragment", "truncated"):
            entry["pair_accuracy"] = round(float(rows.groupby("pair_id")["correct"].all().mean()), 4)
        report["run2_test_by_kind"][kind] = entry
        print(f"  {kind:<10} {entry}")

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
