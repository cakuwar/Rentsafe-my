"""Complete evaluation of the deployed model, XLM-R retrain run 1, in one place.

Computes what was not computed before (confusion matrices, ROC-AUC, PR-AUC,
calibration on every set, per-language results, the misclassified cases, CPU
time) and gathers what was (acceptance gates, short-input sweep, behaviour
checks, the Colab training printout) so the evaluation document traces to one
file.

Scoring is the service's: message-aligned windows, highest window, threshold
0.5 on the raw probability. "Served" probabilities apply the checkpoint's
calibration temperature, as the API does; they never cross 0.5 differently.

    python eval/run1_evaluation.py

Writes eval/results/run1_evaluation.json.
"""
import json
import math
import os
import re
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
ROOT = os.path.dirname(NLP)
sys.path.insert(0, NLP)
sys.path.insert(0, HERE)

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import average_precision_score, roc_auc_score
from transformers import AutoModelForSequenceClassification, AutoTokenizer

import behaviour_checks as probes
from app.layer2.classifier import _message_windows
from confusion_matrices import as_text, matrix, pair_accuracy

MODEL = os.path.join(NLP, "models", "xlm-roberta-scam-v3-run1")
DATA = os.path.join(ROOT, "data", "processed")
RESULTS = os.path.join(HERE, "results")
OUT = os.path.join(RESULTS, "run1_evaluation.json")


class Run1:
    def __init__(self):
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL)
        self.model = AutoModelForSequenceClassification.from_pretrained(MODEL).eval()
        self.scam = {k.upper(): v for k, v in self.model.config.label2id.items()}["SCAM"]
        self.legit = 1 - self.scam
        self.temperature = float(self.model.config.calibration_temperature)
        self.params = sum(p.numel() for p in self.model.parameters())

    def margin(self, text):
        best, windows = -1e9, _message_windows(self.tokenizer, text)
        with torch.no_grad():
            for window in windows:
                enc = self.tokenizer.prepare_for_model(window, add_special_tokens=True,
                                                       return_tensors="pt")
                enc = {k: v.unsqueeze(0) if v.dim() == 1 else v for k, v in enc.items()}
                logits = self.model(**enc).logits[0]
                best = max(best, float(logits[self.scam] - logits[self.legit]))
        return best, len(windows)


def sigmoid(x, t=1.0):
    return 1.0 / (1.0 + math.exp(-x / t))


def ece(p, y, bins=10):
    p, y = np.asarray(p), np.asarray(y)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p < hi) if hi < 1 else (p >= lo)
        if mask.any():
            total += mask.mean() * abs(p[mask].mean() - y[mask].mean())
    return round(float(total), 4)


def evaluate(model, frame, name, timing):
    rows = []
    for record in frame.itertuples():
        start = time.perf_counter()
        margin, windows = model.margin(record.text)
        timing.append(time.perf_counter() - start)
        rows.append({"margin": margin, "windows": windows})
    raw = [sigmoid(r["margin"]) for r in rows]
    served = [sigmoid(r["margin"], model.temperature) for r in rows]
    y = [int(label == "SCAM") for label in frame["label"]]
    preds = ["SCAM" if p >= 0.5 else "LEGITIMATE" for p in raw]
    result = {"set": name, **matrix(frame["label"], preds)}
    if len(set(y)) == 2:
        result["roc_auc"] = round(float(roc_auc_score(y, raw)), 4)
        result["pr_auc"] = round(float(average_precision_score(y, raw)), 4)
    result["brier_raw"] = round(float(np.mean((np.array(raw) - y) ** 2)), 4)
    result["brier_served"] = round(float(np.mean((np.array(served) - y) ** 2)), 4)
    result["ece_raw"] = ece(raw, y)
    result["ece_served"] = ece(served, y)
    result["saturated_share_raw"] = round(float(np.mean([(p > 0.99) or (p < 0.01) for p in raw])), 4)
    result["saturated_share_served"] = round(float(np.mean([(p > 0.99) or (p < 0.01) for p in served])), 4)
    result["multi_window_rows"] = sum(r["windows"] > 1 for r in rows)
    if "pair_id" in frame:
        result["pair_accuracy"] = pair_accuracy(frame, preds)
    frame = frame.assign(p_raw=raw, p_served=served, pred=preds)
    return result, frame


def first_lines(text, n=3):
    return " | ".join(line for line in text.split("\n") if line.strip())[:160]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    model = Run1()
    timing_val, timing_other = [], []

    val = pd.read_csv(os.path.join(DATA, "random", "val.csv"))
    val["label"] = val["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    pairs = pd.read_csv(os.path.join(DATA, "augmented", "minimal_pairs_test.csv"))
    pairs = pairs[pairs["kind"] == "full"].reset_index(drop=True)
    english = pd.DataFrame(
        [{"text": as_text(t), "label": "SCAM"} for t in probes.ENGLISH_SCAMS]
        + [{"text": as_text(t), "label": "LEGITIMATE"} for t in probes.ENGLISH_LEGIT])
    benign = pd.DataFrame([{"text": t, "label": "LEGITIMATE"} for t in probes.BENIGN_SHORT])

    report = {"model": {"path": "nlp-service/models/xlm-roberta-scam-v3-run1",
                        "base": "xlm-roberta-base", "parameters_millions": round(model.params / 1e6),
                        "calibration_temperature": round(model.temperature, 4),
                        "max_window_tokens": 512, "decision_threshold": 0.5},
              "sets": {}}

    v, val_scored = evaluate(model, val, "validation", timing_val)
    p, pairs_scored = evaluate(model, pairs, "new-wording minimal pairs", timing_other)
    e, _ = evaluate(model, english, "English-only probes", timing_other)
    b, _ = evaluate(model, benign, "benign short messages", timing_other)
    report["sets"] = {"validation": v, "minimal_pairs": p, "english_probes": e, "benign_short": b}

    report["majority_baseline"] = {
        "validation_always_scam_accuracy": round(float((val["label"] == "SCAM").mean()), 4),
        "minimal_pairs_any_constant_accuracy": 0.5, "minimal_pairs_any_constant_pair_accuracy": 0.0}

    # Per-language on the minimal pairs.
    report["minimal_pairs_by_language"] = {}
    for lang, grp in pairs_scored.groupby("lang"):
        report["minimal_pairs_by_language"][lang] = {
            "pairs": int(grp["pair_id"].nunique()),
            "row_accuracy": round(float((grp["pred"] == grp["label"]).mean()), 4),
            "pair_accuracy": pair_accuracy(grp, list(grp["pred"])),
            "scams_missed": int(((grp["label"] == "SCAM") & (grp["pred"] != "SCAM")).sum()),
            "false_alarms": int(((grp["label"] == "LEGITIMATE") & (grp["pred"] == "SCAM")).sum())}

    # The misclassified cases.
    errors = []
    for frame, name in ((val_scored, "validation"), (pairs_scored, "minimal pairs")):
        for record in frame[frame["pred"] != frame["label"]].itertuples():
            entry = {"set": name, "label": record.label, "p_raw": round(record.p_raw, 4),
                     "excerpt": first_lines(record.text)}
            if name == "minimal pairs":
                twin = frame[(frame["pair_id"] == record.pair_id) & (frame["label"] != record.label)].iloc[0]
                entry.update({"pair_id": record.pair_id, "lang": record.lang,
                              "differing_owner_lines": [
                                  b.split(": ", 1)[-1] for a, b in zip(twin.text.split("\n"), record.text.split("\n"))
                                  if a != b and b.startswith("Owner:")]})
            errors.append(entry)
    report["misclassified"] = errors

    # Real conversations.
    gates = json.load(open(os.path.join(NLP, "training", "gates.json"), encoding="utf-8"))
    before = json.load(open(os.path.join(NLP, "training", "gates_2026-09-27.json"), encoding="utf-8"))
    real = [("real scam chat (4 screenshots, OCR)", gates["real_scam_production"]["text"], "SCAM"),
            ("real legitimate iBilik chat (8 screenshots, OCR, current pipeline)", gates["real_legit_production"]["text"], "LEGITIMATE"),
            ("same chat, OCR before the watermark fix", before["real_legit_production"]["text"], "LEGITIMATE"),
            ("same chat, hand transcript", gates["real_legit_clean"]["text"], "LEGITIMATE")]
    report["real_conversations"] = []
    for name, text, expect in real:
        start = time.perf_counter()
        margin, windows = model.margin(text)
        seconds = time.perf_counter() - start
        report["real_conversations"].append({
            "chat": name, "expect": expect, "p_raw": round(sigmoid(margin), 4),
            "p_served": round(sigmoid(margin, model.temperature), 4),
            "verdict": "SCAM" if sigmoid(margin) >= 0.5 else "LEGITIMATE",
            "correct": (sigmoid(margin) >= 0.5) == (expect == "SCAM"),
            "windows": windows, "cpu_seconds": round(seconds, 2)})

    report["cpu_seconds_per_conversation"] = {
        "validation_median": round(statistics.median(timing_val), 3),
        "validation_mean": round(statistics.mean(timing_val), 3),
        "real_chats_mean": round(statistics.mean(r["cpu_seconds"] for r in report["real_conversations"]), 3),
        "note": "CPU only, one conversation at a time, model already loaded"}

    # Gathered from earlier, traceable results.
    gate_file = json.load(open(os.path.join(RESULTS, "gates_xlm-roberta-scam-v3-run1.json"), encoding="utf-8"))
    report["acceptance_gates_now"] = {k: {"expect": g["expect"], "p_raw": g["p_scam"],
                                          "p_served": g.get("p_scam_served"), "passed": g["passed"]}
                                      for k, g in gate_file["gates"].items()}
    report["acceptance_gates_now_passed"] = f"{gate_file['passed']} of {gate_file['total']}"
    sweep = json.load(open(os.path.join(RESULTS, "truncation_sweep.json"), encoding="utf-8"))
    report["short_input_sweep"] = sweep
    behaviour = json.load(open(os.path.join(RESULTS, "behaviour_checks.json"), encoding="utf-8"))
    report["group_ablation"] = behaviour["group_ablation"]
    printout = open(os.path.join(RESULTS, "v3_run1_printout.txt"), encoding="utf-8").read()
    grab = lambda pattern: re.search(pattern, printout).group(1)
    report["colab_printout"] = {
        "validation_accuracy": float(grab(r"accuracy\s+([\d.]+)")),
        "validation_macro_f1": float(grab(r"macro_f1\s+([\d.]+)")),
        "pair_accuracy": float(grab(r"pair accuracy\s+([\d.]+)")),
        "fragment_pairs": grab(r"fragment pairs\s+([\d.]+)"),
        "temperature": float(grab(r"temperature ([\d.]+)")),
        "pair_test_ece_raw_to_calibrated": [float(grab(r"pair-test ECE\s+raw ([\d.]+)")),
                                            float(grab(r"ECE\s+raw [\d.]+\s+->\s+calibrated ([\d.]+)"))],
        "note": "Colab, on run 1's own minimal-pair test split (since regenerated); GPU scoring",
    }

    json.dump(report, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    for key in ("validation", "minimal_pairs", "english_probes", "benign_short"):
        m = report["sets"][key]
        print(f"{key:<16} TP {m['TP']:>3} FN {m['FN']:>3} FP {m['FP']:>3} TN {m['TN']:>3} acc {m['accuracy']} "
              f"prec {m['precision_scam']} rec {m['recall_scam']} spec {m['specificity']} F1 {m['f1_scam']} "
              f"macroF1 {m['macro_f1']} MCC {m['mcc']} AUC {m.get('roc_auc')} PR-AUC {m.get('pr_auc')} "
              f"Brier {m['brier_raw']}/{m['brier_served']} ECE {m['ece_raw']}/{m['ece_served']} "
              f"sat {m['saturated_share_raw']}/{m['saturated_share_served']}"
              + (f" pair {m['pair_accuracy']}" if "pair_accuracy" in m else ""))
    print("by language:", report["minimal_pairs_by_language"])
    print("cpu:", report["cpu_seconds_per_conversation"])
    for e in errors:
        print("ERROR", e)
    for r in report["real_conversations"]:
        print("REAL", r)
    print("printout:", report["colab_printout"])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
