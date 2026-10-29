"""Where the risk-band cut-points should sit, measured on the data we have.

The PRD (§8.4) says the band thresholds 25 / 50 / 75 were chosen by ROC
analysis: plot scam recall (TPR) against false-alarm rate (FPR) for every
threshold and take the point where recall >= 85% at an acceptable FPR. This
runs that analysis on the final 0-100 risk score.

Each threshold t is read as the rule "score >= t is flagged". For every t from
0 to 101 it reports TPR and FPR, then:

  * AUC (ties count half)
  * the thresholds that reach recall >= 85% with the lowest FPR (PRD rule)
  * the thresholds that maximise Youden's J (TPR - FPR)
  * the candidate cuts under both conventions: the code's bands start at
    25 / 50 / 75 (">= 25"), the PRD's at 26 / 51 / 76 ("> 25"), each with a
    Wilson 95% interval on recall and on the false-alarm rate
  * every score that lands exactly on 25, 50 or 75 - the only scores the two
    conventions put in different bands

Sets:
  random/val            NLP only (max 60). The checkpoint was selected on it,
                        so it is optimistic.
  minimal_pairs_test    NLP only, held-out wording ("full" rows, as cap_cost.py)
  blind test            full pipeline (NLP + OSINT + price), the recorded run in
                        data/test_real/cases/results.csv - not re-scored. All 5
                        legitimate cases and case08 are role-played.

random/train is left out: the model was trained on it. Corpus scores come from
the backend's real code (aggregateScore + capUnsupportedScore), so a high model
score with no red flag is held at 49 here exactly as in production.
Conversations the service refuses to score (UNKNOWN band) are counted, not
ranked.

    python eval/band_thresholds.py

Writes eval/results/band_thresholds.json.
"""
import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
ROOT = os.path.dirname(NLP)
sys.path.insert(0, NLP)

from app import config
from app.layer1.red_flags import analyse
from app.layer2.classifier import classify
from app.normaliser.normaliser import normalise
from cap_cost import bands, load_sets

BLIND = os.path.join(ROOT, "data", "test_real", "cases", "results.csv")
OUT = os.path.join(HERE, "results", "band_thresholds.json")

CORPUS_SETS = ("random/val", "minimal_pairs_test (held-out wording)")
BOUNDARIES = (25, 50, 75)
TARGET_RECALL = 0.85
Z95 = 1.959964


def wilson(k, n, z=Z95):
    """Wilson score interval for k of n. Unlike the normal approximation it
    stays inside 0..1 and is not zero-width at 0/n or n/n, which matters with
    5 legitimate cases."""
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z / (1 + z * z / n) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    # Exact at the ends; the formula leaves float noise there (2.8e-17, 0.99999...).
    return [0.0 if k == 0 else centre - half, 1.0 if k == n else centre + half]


def corpus_scores(frame):
    rows = []
    for record in frame.itertuples():
        layer2 = classify(record.text)
        flags = analyse(normalise(record.text))["red_flags"]
        rows.append({"p": layer2["scam_probability"], "status": layer2["status"],
                     "confidence": layer2["confidence"], "redFlags": flags})
    scored = bands(rows)
    return [(record.label, s["capped"]["total"]) for record, s in zip(frame.itertuples(), scored)]


def blind_scores():
    with open(BLIND, encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    label = {"SCAM": "SCAM", "LEGIT": "LEGITIMATE"}
    return [(label[r["truth"]], int(r["api_score"]) if r["api_score"] else None) for r in rows], rows


def spans(values):
    """[3, 4, 5, 9] -> "3-5, 9"."""
    out, start = [], None
    for i, v in enumerate(values):
        if start is None:
            start = v
        if i + 1 == len(values) or values[i + 1] != v + 1:
            out.append(f"{start}" if start == v else f"{start}-{v}")
            start = None
    return ", ".join(out) or "none"


def analyse_set(labelled):
    scored = [(label, score) for label, score in labelled if score is not None]
    scam = [score for label, score in scored if label == "SCAM"]
    legit = [score for label, score in scored if label == "LEGITIMATE"]

    roc = []
    for t in range(0, 102):
        tp = sum(1 for s in scam if s >= t)
        fp = sum(1 for s in legit if s >= t)
        roc.append({"t": t, "tp": tp, "fp": fp, "tpr": tp / len(scam), "fpr": fp / len(legit)})

    pairs = [1.0 if s > g else 0.5 if s == g else 0.0 for s in scam for g in legit]
    auc = sum(pairs) / len(pairs)

    meets = [r for r in roc if r["tpr"] >= TARGET_RECALL]
    best_fpr = min(r["fpr"] for r in meets)
    recall_rule = [r["t"] for r in meets if r["fpr"] == best_fpr]

    best_j = max(r["tpr"] - r["fpr"] for r in roc)
    youden = [r["t"] for r in roc if abs((r["tpr"] - r["fpr"]) - best_j) < 1e-12]

    return {
        "scam": len(scam), "legitimate": len(legit),
        "unscored": len(labelled) - len(scored),
        "auc": auc,
        "recall_rule": {"target_recall": TARGET_RECALL, "fpr": best_fpr, "thresholds": spans(recall_rule)},
        "youden": {"j": best_j, "thresholds": spans(youden)},
        "candidates": {str(t): {**{k: roc[t][k] for k in ("tp", "fp", "tpr", "fpr")},
                                "tpr_ci95": wilson(roc[t]["tp"], len(scam)),
                                "fpr_ci95": wilson(roc[t]["fp"], len(legit))}
                       for b in BOUNDARIES for t in (b, b + 1)},
        "on_a_boundary": {str(b): [label for label, score in scored if score == b] for b in BOUNDARIES},
        "highest": {"scam": max(scam), "legitimate": max(legit)},
        "roc": roc,
    }


def show(name, result):
    print(f"\n== {name}: {result['scam']} scam, {result['legitimate']} legitimate"
          f", {result['unscored']} unscored | AUC {result['auc']:.3f}"
          f" | highest score: scam {result['highest']['scam']}, legitimate {result['highest']['legitimate']}")
    print(f"  {'cut':<6}{'t':>4}  {'recall [95% CI]':>22}  {'FPR [95% CI]':>22}")
    for b in BOUNDARIES:
        for t, who in ((b, "code"), (b + 1, "PRD")):
            c = result["candidates"][str(t)]
            recall = f"{c['tpr']:.3f} [{c['tpr_ci95'][0]:.3f}, {c['tpr_ci95'][1]:.3f}]"
            fpr = f"{c['fpr']:.3f} [{c['fpr_ci95'][0]:.3f}, {c['fpr_ci95'][1]:.3f}]"
            print(f"  {who:<6}{t:>4}  {recall:>22}  {fpr:>22}   ({c['tp']} scams, {c['fp']} legitimate)")
    rule = result["recall_rule"]
    print(f"  recall >= {rule['target_recall']:.0%} at the lowest FPR ({rule['fpr']:.3f}): t = {rule['thresholds']}")
    print(f"  Youden's J max ({result['youden']['j']:.3f}): t = {result['youden']['thresholds']}")
    hits = {b: labels for b, labels in result["on_a_boundary"].items() if labels}
    print(f"  scores exactly on 25 / 50 / 75: {hits or 'none'}")


def main():
    report = {"model": config.FINETUNED_MODEL_DIR.replace("\\", "/").split("/")[-1], "sets": {}}
    sets = load_sets()
    for name in CORPUS_SETS:
        report["sets"][name] = analyse_set(corpus_scores(sets[name]))
        show(name, report["sets"][name])

    labelled, rows = blind_scores()
    result = analyse_set(labelled)
    result["each"] = [{"case": r["case_id"], "truth": r["truth"], "origin": r["origin"],
                       "score": int(r["api_score"]), "band": r["api_band"]} for r in rows]
    report["sets"]["blind test (full pipeline, recorded run)"] = result
    show("blind test (full pipeline, recorded run)", result)

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
