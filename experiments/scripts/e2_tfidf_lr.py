"""E2. TF-IDF + logistic regression baseline (offline).

Fixed before any result was seen:
  features   word 1-2-gram TF-IDF + character 3-5-gram TF-IDF on the raw text
             (scikit-learn defaults otherwise: lowercase=True, min_df=1, no
             sublinear tf); fitted on the training rows only
  model      LogisticRegression(class_weight="balanced", solver="liblinear",
             random_state=42, max_iter=5000)
  C          chosen from {0.1, 1, 10} on dev macro-F1 (dev = run 1's 183 rows:
             95 validation + 88 held-out pair rows); ties -> the smaller C
  threshold  0.5, never tuned
  variant A  trained on the 379 corpus rows only
  variant B  trained on run 1's 1,223 rows (379 corpus + 844 pair rows)
Test sets are scored once with the chosen C. The validation set is part of
dev, so its scores are in-sample for the choice of C (as for run 1, which used
it for early stopping).
"""
import os
import sys

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (BLIND_FILE, LABELS, gates, load, metrics, pair_accuracy, run1_split,
                    save_json, wilson)

C_GRID = [0.1, 1, 10]


def make_pipeline(c):
    features = FeatureUnion([
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2))),
        ("char", TfidfVectorizer(analyzer="char", ngram_range=(3, 5))),
    ])
    model = LogisticRegression(C=c, class_weight="balanced", solver="liblinear",
                               random_state=42, max_iter=5000)
    return Pipeline([("tfidf", features), ("lr", model)])


def p_scam(pipe, texts):
    proba = pipe.predict_proba(list(texts))
    return proba[:, list(pipe.classes_).index(1)]


def top_features(pipe, k=20):
    names = pipe.named_steps["tfidf"].get_feature_names_out()
    coef = pipe.named_steps["lr"].coef_[0]          # positive = SCAM (class 1)
    order = np.argsort(coef)
    fmt = lambda i: {"feature": names[i], "weight": round(float(coef[i]), 3)}
    return {"SCAM": [fmt(i) for i in order[::-1][:k]],
            "LEGITIMATE": [fmt(i) for i in order[:k]]}


def evaluate(pipe, name):
    out = {}
    _, val, _, _ = run1_split()
    out["validation_95"] = metrics(val["label"], p_scam(pipe, val["text"]))

    fig = load("fig43_pairs_test.csv")
    fig = fig[fig["kind"] == "full"].reset_index(drop=True)
    p_fig = p_scam(pipe, fig["text"])
    out["new_wording_144"] = metrics(fig["label"], p_fig)
    out["new_wording_144"]["pair_accuracy"], out["new_wording_144"]["pairs"] = pair_accuracy(fig, p_fig)
    by_lang = {}
    for lang, grp in fig.groupby("lang"):
        pa, n = pair_accuracy(grp, p_fig[grp.index])
        m = metrics(grp["label"], p_fig[grp.index])
        by_lang[lang] = {"pairs": n, "pair_accuracy": pa, "row_accuracy": m["accuracy"],
                         "missed_scams": m["fn"], "false_alarms": m["fp"]}
    out["new_wording_144"]["by_language"] = by_lang

    r1 = load("run1_minimal_pairs_test.csv")
    p_r1 = p_scam(pipe, r1["text"])
    out["run1_split_166"] = metrics(r1["label"], p_r1)
    full = r1["kind"] == "full"
    out["run1_split_166"]["full_pair_accuracy"], out["run1_split_166"]["full_pairs"] = \
        pair_accuracy(r1[full], p_r1[full.to_numpy()])
    frag = r1["kind"] == "fragment"
    out["run1_split_166"]["fragment_pair_accuracy"], out["run1_split_166"]["fragment_pairs"] = \
        pair_accuracy(r1[frag], p_r1[frag.to_numpy()])

    g = gates()
    p_g = p_scam(pipe, g["text"])
    out["gates"] = {row.gate: {"expect": row.label, "p_scam": round(float(p), 4),
                               "passed": bool((p >= 0.5) == (row.label == "SCAM"))}
                    for row, p in zip(g.itertuples(), p_g)}
    out["gates_passed"] = sum(v["passed"] for v in out["gates"].values())

    if os.path.exists(BLIND_FILE):
        blind = pd.read_csv(BLIND_FILE)
        p_b = p_scam(pipe, blind["text"])
        y = blind["label"].map(LABELS).to_numpy()
        caught = int(((p_b >= 0.5) & (y == 1)).sum()); scams = int((y == 1).sum())
        alarms = int(((p_b >= 0.5) & (y == 0)).sum()); legits = int((y == 0).sum())
        out["blind_15"] = {
            "scams_caught": f"{caught}/{scams}", "recall": round(caught / scams, 3),
            "recall_wilson95": wilson(caught, scams),
            "false_alarms": f"{alarms}/{legits}", "false_alarm_rate": round(alarms / legits, 3),
            "false_alarm_wilson95": wilson(alarms, legits),
            "per_case": {c: round(float(p), 4) for c, p in zip(blind["case_id"], p_b)},
        }
    else:
        out["blind_15"] = "PENDING: no blind-test transcripts (see RESULTS.md)"
    return out


def main():
    original, val, train_b, dev = run1_split()
    report = {"settings": __doc__}
    for variant, train in (("A_corpus_379", original[["text", "label"]]), ("B_run1_1223", train_b)):
        y = train["label"].map(LABELS)
        dev_scores = {}
        for c in C_GRID:
            pipe = make_pipeline(c).fit(train["text"], y)
            dev_scores[c] = metrics(dev["label"], p_scam(pipe, dev["text"]))["macro_f1"]
        best_c = min(c for c in C_GRID if dev_scores[c] == max(dev_scores.values()))
        pipe = make_pipeline(best_c).fit(train["text"], y)
        result = {"train_rows": int(len(train)), "dev_macro_f1_by_C": dev_scores, "chosen_C": best_c,
                  "n_features": int(len(pipe.named_steps["tfidf"].get_feature_names_out()))}
        result.update(evaluate(pipe, variant))
        result["top20_features"] = top_features(pipe)
        report[variant] = result
        print(f"\n== {variant}: C={best_c} (dev macro-F1 {dev_scores})")
        print("  val acc", result["validation_95"]["accuracy"], "| new wording acc",
              result["new_wording_144"]["accuracy"], "pair", result["new_wording_144"]["pair_accuracy"],
              "| run1 split full pair", result["run1_split_166"]["full_pair_accuracy"],
              "| gates", result["gates_passed"], "/ 9")
    print("\nwrote", save_json(report, "e2", "e2_results.json"))


if __name__ == "__main__":
    main()
