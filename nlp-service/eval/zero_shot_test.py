"""One-off test: would a zero-shot NLI model beat the deployed run-1 model?

Decision rule (set by the author before any result existed): if the zero-shot
model does not clearly beat run 1 on the new-wording minimal pairs AND the real
iBilik chat, it is dropped with this table as the evidence. If it does, it may
be added later as an extra evidence signal (like a layer-1 red flag) - never as
calibration. No other outcome starts new work.

Everything that could be tuned to the result - hypotheses, score, threshold
rule, what "clearly" means - is written to plan.json BEFORE any scoring, and
the script refuses to run if plan.json exists with different content.

    python eval/zero_shot_test.py

Writes eval/results/zero_shot_test/: plan.json, scores.json, summary.json,
table.md. Local only; nothing is trained.
"""
import json
import os
import platform
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
ROOT = os.path.dirname(NLP)
sys.path.insert(0, NLP)

import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app import config
from app.layer2.classifier import _message_windows

OUT = os.path.join(HERE, "results", "zero_shot_test")
DATA = os.path.join(ROOT, "data", "processed")
ZERO_SHOT = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"

PLAN = {
    "fixed": "2026-09-28, before any scoring",
    "zero_shot_model": ZERO_SHOT,
    "compared_with": "deployed run 1 (models/xlm-roberta-scam-v3-run1), raw probability, threshold 0.5",
    "hypotheses": {
        "scam": {
            "payment_before_viewing": [
                "The owner asks for money before the renter can view the unit.",
                "Pemilik meminta wang sebelum penyewa dapat melihat rumah."],
            "keys_by_courier": [
                "The owner offers to send the keys by post or courier.",
                "Pemilik menawarkan untuk menghantar kunci melalui pos atau kurier."],
            "owner_unavailable": [
                "The owner says they are away and cannot show the unit.",
                "Pemilik berkata dia berada di luar kawasan dan tidak dapat menunjukkan rumah."],
            "pay_someone_else": [
                "The owner asks the renter to pay into another person's bank account.",
                "Pemilik meminta penyewa membayar ke akaun bank orang lain."],
            "urgency": [
                "The owner pressures the renter to pay quickly before someone else takes the unit.",
                "Pemilik mendesak penyewa membayar segera sebelum orang lain mengambil rumah itu."],
        },
        "legitimate": {
            "viewing_arranged": [
                "The renter and the owner arrange a time to view the unit.",
                "Penyewa dan pemilik menetapkan masa untuk melihat rumah."],
            "agreement_via_platform": [
                "The tenancy agreement is signed through a rental platform or agency.",
                "Perjanjian sewa ditandatangani melalui platform atau agensi sewaan."],
            "keys_in_person": [
                "The keys are handed over in person.",
                "Kunci diserahkan secara bersemuka."],
        },
    },
    "entailment": "P(entailment) = softmax over the [entailment, contradiction] logits "
                  "(neutral dropped) - the standard multi-label zero-shot recipe",
    "windows": "app.layer2.classifier._message_windows with the zero-shot tokenizer, "
               "sized so window + longest hypothesis + 3 special tokens fit 512",
    "chat_score": "S - L. S = highest P(entailment) of any scam hypothesis in any window; "
                  "L = the same for legitimacy hypotheses. SCAM if S - L >= threshold.",
    "threshold": "chosen on data/processed/random/val.csv only: of the midpoints between "
                 "adjacent sorted scores, the one with the highest accuracy; ties -> "
                 "nearest 0",
    "evaluated_on": [
        "random/val.csv (threshold chosen here: in-sample for the zero-shot model; "
        "run 1 used it for early stopping)",
        "minimal_pairs_test.csv, full conversations only (new wording, 72 pairs)",
        "real scam chat, current OCR text (training/gates.json)",
        "real iBilik legitimate chat, current OCR text (training/gates.json)",
        "real iBilik legitimate chat, pre-fix OCR text (training/gates_2026-09-27.json)",
        "real iBilik legitimate chat, hand transcript (for information)",
        "english_courier_scam gate",
    ],
    "clearly_beats": {
        "pairs": "zero-shot pair accuracy >= run-1 pair accuracy + 0.05 (at least 4 more "
                 "of 72 pairs right)",
        "ibilik": "zero-shot calls the real iBilik chat LEGITIMATE on BOTH the current and "
                  "the pre-fix OCR text (run 1 is right on the first only by a window-"
                  "boundary margin, and wrong on the second)",
        "rule": "both must hold, else drop",
    },
    "disclosure": "Before these hypotheses were written, one load-check pair was scored "
                  "('Owner: transfer the deposit first, then I will post you the keys.' vs "
                  "'The owner asks for payment before the renter can view the unit.': "
                  "entailment 0.0146, neutral 0.9848, contradiction 0.0007). Nothing here "
                  "was changed because of it.",
}


def write_plan():
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "plan.json")
    text = json.dumps(PLAN, indent=2, ensure_ascii=False)
    if os.path.exists(path):
        if open(path, encoding="utf-8").read() != text:
            sys.exit("plan.json differs from the plan in this script - the plan was fixed "
                     "before scoring and must not change. Delete it only to start over.")
    else:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)


class ZeroShot:
    def __init__(self):
        self.tokenizer = AutoTokenizer.from_pretrained(ZERO_SHOT)
        self.model = AutoModelForSequenceClassification.from_pretrained(ZERO_SHOT).eval()
        labels = {v.lower(): k for k, v in self.model.config.id2label.items()}
        self.entail, self.contra = labels["entailment"], labels["contradiction"]
        self.hypotheses = [(side, name, sentence)
                           for side in ("scam", "legitimate")
                           for name, sentences in PLAN["hypotheses"][side].items()
                           for sentence in sentences]
        self.hyp_ids = [self.tokenizer(h, add_special_tokens=False)["input_ids"]
                        for _, _, h in self.hypotheses]
        self.body = 512 - 3 - max(len(ids) for ids in self.hyp_ids)

    def score(self, text):
        best = {"scam": (0.0, None), "legitimate": (0.0, None)}
        windows = _message_windows(self.tokenizer, text, body=self.body)
        with torch.no_grad():
            for window in windows:
                batch = self.tokenizer.pad(
                    [self.tokenizer.prepare_for_model(window, hyp, add_special_tokens=True)
                     for hyp in self.hyp_ids], return_tensors="pt")
                logits = self.model(**batch).logits
                pair = torch.stack([logits[:, self.entail], logits[:, self.contra]], dim=1)
                entail = pair.softmax(-1)[:, 0].tolist()
                for (side, name, _), p in zip(self.hypotheses, entail):
                    if p > best[side][0]:
                        best[side] = (p, name)
        return {"score": best["scam"][0] - best["legitimate"][0],
                "S": best["scam"][0], "S_hypothesis": best["scam"][1],
                "L": best["legitimate"][0], "L_hypothesis": best["legitimate"][1],
                "windows": len(windows)}


class Run1:
    def __init__(self):
        self.tokenizer = AutoTokenizer.from_pretrained(config.FINETUNED_MODEL_DIR)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            config.FINETUNED_MODEL_DIR).eval()
        self.scam = {k.upper(): v for k, v in self.model.config.label2id.items()}["SCAM"]

    def score(self, text):
        best = 0.0
        windows = _message_windows(self.tokenizer, text)
        with torch.no_grad():
            for window in windows:
                enc = self.tokenizer.prepare_for_model(window, add_special_tokens=True,
                                                       return_tensors="pt")
                enc = {k: v.unsqueeze(0) if v.dim() == 1 else v for k, v in enc.items()}
                best = max(best, float(self.model(**enc).logits.softmax(-1)[0][self.scam]))
        return {"score": best, "windows": len(windows)}


def timed(model, text):
    start = time.perf_counter()
    result = model.score(text)
    result["seconds"] = time.perf_counter() - start
    return result


def choose_threshold(scores, labels):
    values = sorted(set(scores))
    candidates = [values[0] - 1e-6] + [(a + b) / 2 for a, b in zip(values, values[1:])] \
        + [values[-1] + 1e-6]

    def accuracy(t):
        return sum((s >= t) == (y == "SCAM") for s, y in zip(scores, labels)) / len(scores)

    return max(candidates, key=lambda t: (round(accuracy(t), 9), -abs(t)))


def load_sets():
    val = pd.read_csv(os.path.join(DATA, "random", "val.csv"))
    val["label"] = val["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    pairs = pd.read_csv(os.path.join(DATA, "augmented", "minimal_pairs_test.csv"))
    pairs = pairs[pairs["kind"] == "full"]
    gates = json.load(open(os.path.join(NLP, "training", "gates.json"), encoding="utf-8"))
    before = json.load(open(os.path.join(NLP, "training", "gates_2026-09-27.json"),
                            encoding="utf-8"))
    real = [
        ("real scam chat (current OCR)", gates["real_scam_production"]["text"], "SCAM"),
        ("real iBilik chat (current OCR)", gates["real_legit_production"]["text"], "LEGITIMATE"),
        ("real iBilik chat (pre-fix OCR)", before["real_legit_production"]["text"], "LEGITIMATE"),
        ("real iBilik chat (hand transcript)", gates["real_legit_clean"]["text"], "LEGITIMATE"),
        ("English courier scam (gate)", gates["english_courier_scam"]["text"], "SCAM"),
    ]
    return val, pairs, real


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    write_plan()
    torch.manual_seed(0)
    val, pairs, real = load_sets()
    models = {"run 1": Run1(), "zero-shot": ZeroShot()}

    scores = {name: {} for name in models}
    for name, model in models.items():
        print(f"scoring with {name} ...", flush=True)
        scores[name]["val"] = [timed(model, t) for t in val["text"]]
        scores[name]["pairs"] = [timed(model, t) for t in pairs["text"]]
        scores[name]["real"] = [timed(model, t) for _, t, _ in real]

    thresholds = {
        "run 1": 0.5,
        "zero-shot": choose_threshold([r["score"] for r in scores["zero-shot"]["val"]],
                                      list(val["label"])),
    }

    summary = {"thresholds": thresholds, "hardware": {
        "processor": platform.processor(), "cpus": os.cpu_count(),
        "torch_threads": torch.get_num_threads()}, "models": {}}
    for name in models:
        t = thresholds[name]
        verdict = lambda r: "SCAM" if r["score"] >= t else "LEGITIMATE"
        val_ok = [verdict(r) == y for r, y in zip(scores[name]["val"], val["label"])]
        pair_rows = pairs.assign(ok=[verdict(r) == y for r, y in
                                     zip(scores[name]["pairs"], pairs["label"])])
        real_rows = [{"chat": label, "expect": y, "score": round(r["score"], 4),
                      "verdict": verdict(r), "correct": verdict(r) == y,
                      "windows": r["windows"], "seconds": round(r["seconds"], 2),
                      **({"S": round(r["S"], 4), "S_hypothesis": r["S_hypothesis"],
                          "L": round(r["L"], 4), "L_hypothesis": r["L_hypothesis"]}
                         if "S" in r else {})}
                     for (label, _, y), r in zip(real, scores[name]["real"])]
        all_seconds = [r["seconds"] for part in ("val", "pairs", "real")
                       for r in scores[name][part]]
        summary["models"][name] = {
            "threshold": round(t, 4),
            "val_accuracy": round(sum(val_ok) / len(val_ok), 4),
            "pairs_row_accuracy": round(float(pair_rows["ok"].mean()), 4),
            "pairs_pair_accuracy": round(float(pair_rows.groupby("pair_id")["ok"].all().mean()), 4),
            "real": real_rows,
            "cpu_seconds_per_chat": {
                "median": round(statistics.median(all_seconds), 2),
                "mean": round(statistics.mean(all_seconds), 2),
                "real_chats_mean": round(statistics.mean(r["seconds"] for r in scores[name]["real"]), 2),
            },
        }

    run1, zero = summary["models"]["run 1"], summary["models"]["zero-shot"]
    ibilik = {r["chat"]: r["correct"] for r in zero["real"]}
    beats_pairs = zero["pairs_pair_accuracy"] >= run1["pairs_pair_accuracy"] + 0.05
    beats_ibilik = (ibilik["real iBilik chat (current OCR)"]
                    and ibilik["real iBilik chat (pre-fix OCR)"])
    summary["decision"] = {
        "pairs_criterion_met": beats_pairs,
        "ibilik_criterion_met": beats_ibilik,
        "outcome": ("may be added later as an extra evidence signal"
                    if beats_pairs and beats_ibilik else "DROP - does not clearly beat run 1"),
    }

    lines = ["| | run 1 (deployed) | zero-shot mDeBERTa |", "|---|---|---|",
             f"| threshold | 0.5 | {zero['threshold']} (chosen on validation) |",
             f"| validation accuracy | {run1['val_accuracy']} | {zero['val_accuracy']} |",
             f"| new-wording pairs: row accuracy | {run1['pairs_row_accuracy']} | {zero['pairs_row_accuracy']} |",
             f"| new-wording pairs: pair accuracy | {run1['pairs_pair_accuracy']} | {zero['pairs_pair_accuracy']} |"]
    for a, b in zip(run1["real"], zero["real"]):
        mark = lambda r: "✓" if r["correct"] else "✗"
        lines.append(f"| {a['chat']} (expect {a['expect']}) | {a['score']} {a['verdict']} {mark(a)} "
                     f"| {b['score']} {b['verdict']} {mark(b)} |")
    lines.append(f"| CPU seconds per chat (median / mean) | {run1['cpu_seconds_per_chat']['median']} / "
                 f"{run1['cpu_seconds_per_chat']['mean']} | {zero['cpu_seconds_per_chat']['median']} / "
                 f"{zero['cpu_seconds_per_chat']['mean']} |")
    lines.append(f"| CPU seconds per real chat (mean) | {run1['cpu_seconds_per_chat']['real_chats_mean']} "
                 f"| {zero['cpu_seconds_per_chat']['real_chats_mean']} |")
    table = "\n".join(lines)
    decision = summary["decision"]
    table += (f"\n\nPairs criterion (>= run 1 + 0.05): {decision['pairs_criterion_met']}. "
              f"iBilik criterion (right on current AND pre-fix OCR): "
              f"{decision['ibilik_criterion_met']}. Outcome: **{decision['outcome']}**.\n")

    with open(os.path.join(OUT, "scores.json"), "w", encoding="utf-8") as handle:
        json.dump({name: {part: [{k: (round(v, 4) if isinstance(v, float) else v)
                                  for k, v in r.items()} for r in rows]
                          for part, rows in parts.items()}
                   for name, parts in scores.items()}, handle, indent=1)
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    with open(os.path.join(OUT, "table.md"), "w", encoding="utf-8") as handle:
        handle.write(table)
    print("\n" + table)
    for r in zero["real"]:
        print(f"  zero-shot {r['chat']}: S={r['S']} ({r['S_hypothesis']}) L={r['L']} ({r['L_hypothesis']})")


if __name__ == "__main__":
    main()
