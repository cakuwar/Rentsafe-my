"""Confusion matrices for every NLP evaluation we can still reproduce.

Earlier scripts reported accuracy, F1 and pair accuracy; this one rebuilds the
underlying counts so the report can show confusion matrices. Every model is
scored the way the service scores (app.layer2.classifier._message_windows, the
highest window), with the RAW probability and threshold 0.5. The served
temperature never moves a score across 0.5, so verdicts are the same either way.

Models on disk: the original XLM-R (models/xlm-roberta-scam-random), ELECTRA v2
(models/electra-malay-scam-random-v2) and retrain run 1, deployed
(models/xlm-roberta-scam-v3-run1). Run 2 was not kept; its minimal-pair counts
come from the per-row scores in eval/results/v3_run2_diagnosis.json. The
zero-shot NLI model is rebuilt from eval/results/zero_shot_test/scores.json.
Layer 1 is scored as a classifier too: "any red flag" = SCAM.

Positive class = SCAM throughout.

    python eval/confusion_matrices.py

Writes eval/results/confusion_matrices.json and confusion_matrices.md.
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
ROOT = os.path.dirname(NLP)
sys.path.insert(0, NLP)
sys.path.insert(0, HERE)

import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

import behaviour_checks as probes
from app.layer1.red_flags import analyse
from app.layer2.classifier import _message_windows
from app.normaliser.normaliser import normalise

OUT_JSON = os.path.join(HERE, "results", "confusion_matrices.json")
OUT_MD = os.path.join(HERE, "results", "confusion_matrices.md")
DATA = os.path.join(ROOT, "data", "processed")
MODELS = {
    "XLM-R original": "models/xlm-roberta-scam-random",
    "ELECTRA v2": "models/electra-malay-scam-random-v2",
    "XLM-R run 1 (deployed)": "models/xlm-roberta-scam-v3-run1",
}


def as_text(item):
    return "\n".join(item) if isinstance(item, (list, tuple)) else item


def matrix(labels, predictions):
    """labels / predictions: iterables of 'SCAM' / 'LEGITIMATE'."""
    tp = fn = fp = tn = 0
    for y, p in zip(labels, predictions):
        if y == "SCAM":
            tp, fn = tp + (p == "SCAM"), fn + (p != "SCAM")
        else:
            fp, tn = fp + (p == "SCAM"), tn + (p != "SCAM")
    n = tp + fn + fp + tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    neg_precision = tn / (tn + fn) if tn + fn else 0.0
    f1_legit = (2 * neg_precision * specificity / (neg_precision + specificity)
                if neg_precision + specificity else 0.0)
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return {
        "TP": tp, "FN": fn, "FP": fp, "TN": tn, "n": n,
        "accuracy": round((tp + tn) / n, 4) if n else None,
        "precision_scam": round(precision, 4), "recall_scam": round(recall, 4),
        "specificity": round(specificity, 4), "f1_scam": round(f1, 4),
        "macro_f1": round((f1 + f1_legit) / 2, 4),
        "mcc": round((tp * tn - fp * fn) / denom, 4) if denom else 0.0,
    }


def pair_accuracy(frame, predictions):
    ok = pd.Series([p == y for p, y in zip(predictions, frame["label"])], index=frame.index)
    return round(float(ok.groupby(frame["pair_id"]).all().mean()), 4)


class Scorer:
    def __init__(self, path):
        self.tokenizer = AutoTokenizer.from_pretrained(os.path.join(NLP, path))
        self.model = AutoModelForSequenceClassification.from_pretrained(os.path.join(NLP, path)).eval()
        self.scam = {k.upper(): v for k, v in self.model.config.label2id.items()}["SCAM"]

    def p(self, text):
        best = 0.0
        with torch.no_grad():
            for window in _message_windows(self.tokenizer, text):
                enc = self.tokenizer.prepare_for_model(window, add_special_tokens=True,
                                                       truncation=True, max_length=512,
                                                       return_tensors="pt")
                enc = {k: v.unsqueeze(0) if v.dim() == 1 else v for k, v in enc.items()}
                best = max(best, float(self.model(**enc).logits.softmax(-1)[0][self.scam]))
        return best


def verdict(p, threshold=0.5):
    return "SCAM" if p >= threshold else "LEGITIMATE"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    val = pd.read_csv(os.path.join(DATA, "random", "val.csv"))
    train = pd.read_csv(os.path.join(DATA, "random", "train.csv"))
    pairs = pd.read_csv(os.path.join(DATA, "augmented", "minimal_pairs_test.csv"))
    pairs = pairs[pairs["kind"] == "full"].reset_index(drop=True)
    for frame in (val, train):
        frame["label"] = frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    english = pd.DataFrame(
        [{"text": as_text(t), "label": "SCAM"} for t in probes.ENGLISH_SCAMS]
        + [{"text": as_text(t), "label": "LEGITIMATE"} for t in probes.ENGLISH_LEGIT])
    benign = pd.DataFrame([{"text": t, "label": "LEGITIMATE"} for t in probes.BENIGN_SHORT])
    gates = json.load(open(os.path.join(NLP, "training", "gates.json"), encoding="utf-8"))
    before = json.load(open(os.path.join(NLP, "training", "gates_2026-09-27.json"), encoding="utf-8"))
    real = [
        ("real scam chat, OCR", gates["real_scam_production"]["text"], "SCAM"),
        ("real iBilik legit chat, OCR (current)", gates["real_legit_production"]["text"], "LEGITIMATE"),
        ("real iBilik legit chat, OCR (before watermark fix)", before["real_legit_production"]["text"], "LEGITIMATE"),
        ("real iBilik legit chat, hand transcript", gates["real_legit_clean"]["text"], "LEGITIMATE"),
        ("English courier scam (author-written)", gates["english_courier_scam"]["text"], "SCAM"),
    ]
    sets = {"validation (random/val)": val, "new-wording minimal pairs (test, full)": pairs,
            "English-only probes": english, "benign short messages": benign}

    report = {"positive_class": "SCAM", "threshold": 0.5, "models": {}, "layer1": {},
              "real_chats": {}, "sizes": {k: {"rows": len(v), **v["label"].value_counts().to_dict()}
                                          for k, v in sets.items()}}

    for name, path in MODELS.items():
        print(f"scoring {name} ...", flush=True)
        scorer = Scorer(path)
        entry = {}
        start = time.perf_counter()
        for set_name, frame in sets.items():
            preds = [verdict(scorer.p(t)) for t in frame["text"]]
            entry[set_name] = matrix(frame["label"], preds)
            if "pair_id" in frame:
                entry[set_name]["pair_accuracy"] = pair_accuracy(frame, preds)
        entry["_seconds"] = round(time.perf_counter() - start, 1)
        report["models"][name] = entry
        report["real_chats"][name] = [
            {"chat": chat, "expect": y, "p_scam": round(scorer.p(text), 4),
             "correct": verdict(scorer.p(text)) == y} for chat, text, y in real]

    # Run 2: per-row scores kept in its diagnosis file (minimal pairs only).
    diag = json.load(open(os.path.join(HERE, "results", "v3_run2_diagnosis.json"), encoding="utf-8"))
    rows = [r for r in diag["pair_test_rows"] if r["kind"] == "full"]
    run2 = pd.DataFrame(rows)
    run2_preds = [verdict(p) for p in run2["p"]]
    report["models"]["XLM-R run 2 (not kept)"] = {
        "new-wording minimal pairs (test, full)": dict(matrix(run2["label"], run2_preds),
                                                       pair_accuracy=pair_accuracy(run2, run2_preds)),
        "validation (random/val)": dict(matrix(["SCAM"] * 63 + ["LEGITIMATE"] * 32,
                                               ["SCAM"] * 63 + ["LEGITIMATE"] * 32),
                                        note="from the Colab printout: accuracy 1.0000 on these 95 rows"),
    }

    # Zero-shot NLI (rejected): rebuilt from its saved scores and threshold.
    zs_dir = os.path.join(HERE, "results", "zero_shot_test")
    zs_scores = json.load(open(os.path.join(zs_dir, "scores.json"), encoding="utf-8"))["zero-shot"]
    zs_t = json.load(open(os.path.join(zs_dir, "summary.json"), encoding="utf-8"))["thresholds"]["zero-shot"]
    # The saved scores are rounded to 4 dp and the chosen threshold sat just
    # below the lowest validation score (the plan's tie rule picked "everything
    # SCAM"), so comparing rounded scores with it misplaces one row. Re-apply
    # the same rule to the saved scores instead: just below the lowest one.
    lowest = min(r["score"] for r in zs_scores["val"])
    assert abs(zs_t - lowest) < 1e-3, "threshold is not the lowest-score candidate"
    zs_t = lowest - 1e-6
    zs_val = [verdict(r["score"], zs_t) for r in zs_scores["val"]]
    zs_pairs = [verdict(r["score"], zs_t) for r in zs_scores["pairs"]]
    report["models"]["zero-shot mDeBERTa (rejected)"] = {
        "validation (random/val)": matrix(val["label"], zs_val),
        "new-wording minimal pairs (test, full)": dict(matrix(pairs["label"], zs_pairs),
                                                       pair_accuracy=pair_accuracy(pairs, zs_pairs)),
    }

    # Layer 1 as a classifier: any red flag -> SCAM.
    for set_name, frame in {"train (random/train)": train, **sets}.items():
        preds = ["SCAM" if analyse(normalise(t))["red_flags"] else "LEGITIMATE" for t in frame["text"]]
        report["layer1"][set_name] = matrix(frame["label"], preds)
        if "pair_id" in frame:
            report["layer1"][set_name]["pair_accuracy"] = pair_accuracy(frame, preds)

    json.dump(report, open(OUT_JSON, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    lines = []

    def block(title, m):
        lines.extend([f"**{title}** (n={m['n']})", "",
                      "| | predicted SCAM | predicted LEGIT |", "|---|---|---|",
                      f"| actual SCAM | {m['TP']} (TP) | {m['FN']} (FN) |",
                      f"| actual LEGIT | {m['FP']} (FP) | {m['TN']} (TN) |", "",
                      f"accuracy {m['accuracy']} · precision {m['precision_scam']} · recall "
                      f"{m['recall_scam']} · specificity {m['specificity']} · F1 {m['f1_scam']} · "
                      f"macro-F1 {m['macro_f1']} · MCC {m['mcc']}"
                      + (f" · pair accuracy {m['pair_accuracy']}" if "pair_accuracy" in m else "")
                      + (f" · _{m['note']}_" if "note" in m else ""), ""])

    for name, entry in report["models"].items():
        lines.append(f"### {name}")
        lines.append("")
        for set_name, m in entry.items():
            if not set_name.startswith("_"):
                block(set_name, m)
    lines.append("### Layer 1 (regex) as a classifier — any red flag = SCAM")
    lines.append("")
    for set_name, m in report["layer1"].items():
        block(set_name, m)
    lines += ["### Real conversations", "", "| chat | expect | " + " | ".join(MODELS) + " |",
              "|---|---|" + "---|" * len(MODELS)]
    for i, (chat, _, y) in enumerate(real):
        cells = [f"{report['real_chats'][n][i]['p_scam']} {'✓' if report['real_chats'][n][i]['correct'] else '✗'}"
                 for n in MODELS]
        lines.append(f"| {chat} | {y} | " + " | ".join(cells) + " |")
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
