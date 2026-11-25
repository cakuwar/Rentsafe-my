"""Shared data loading and metrics for the experiments (offline)."""
import json
import math
import os

import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, f1_score, matthews_corrcoef, precision_score,
                             recall_score, roc_auc_score)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # <repo>/experiments
RESULTS = os.path.join(ROOT, "results")                                       # metrics only, no chat text
# Everything that holds chat text lives OUTSIDE the repo.
PRIVATE = os.path.join(os.path.expanduser("~"), "rentsafe_experiments_data")
DATA = os.path.join(PRIVATE, "run1_data")              # run 1's rebuilt data (from ~/electra_colab/data)
BLIND_FILE = os.path.join(PRIVATE, "blind", "blind_transcripts.csv")   # made by e1_make_transcripts.py
LABELS = {"LEGITIMATE": 0, "SCAM": 1}


def load(name):
    frame = pd.read_csv(os.path.join(DATA, name))
    frame["label"] = frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    return frame


def run1_split():
    """Run 1's data exactly as the training notebook builds it."""
    original = load("train.csv")
    val = load("val.csv")
    pairs = load("run1_minimal_pairs_train.csv")
    dev_groups = set(json.load(open(os.path.join(DATA, "run1_dev_groups.json")))["dev_groups"])
    pair_dev = pairs[pairs["source_group"].isin(dev_groups)]
    pair_train = pairs[~pairs["source_group"].isin(dev_groups)]
    train_b = pd.concat([original[["text", "label"]], pair_train[["text", "label"]]],
                        ignore_index=True).sample(frac=1, random_state=42)
    dev = pd.concat([val[["text", "label"]], pair_dev[["text", "label"]]], ignore_index=True)
    assert len(train_b) == 1223 and (train_b.label == "SCAM").sum() == 675
    assert len(dev) == 183 and len(pair_dev) == 88
    return original, val, train_b, dev


def gates():
    raw = json.load(open(os.path.join(DATA, "gates.json"), encoding="utf-8"))
    return pd.DataFrame([{"gate": k, "text": v["text"], "label": v["expect"]}
                         for k, v in raw.items() if not k.startswith("_")])


def metrics(y_true, p, threshold=0.5):
    y = np.asarray([LABELS[l] if isinstance(l, str) else l for l in y_true])
    p = np.asarray(p, dtype=float)
    pred = (p >= threshold).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
    out = {"n": int(len(y)), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
           "accuracy": accuracy_score(y, pred),
           "precision": precision_score(y, pred, zero_division=0),
           "recall": recall_score(y, pred, zero_division=0),
           "specificity": tn / (tn + fp) if tn + fp else float("nan"),
           "f1": f1_score(y, pred, zero_division=0),
           "macro_f1": f1_score(y, pred, average="macro", zero_division=0),
           "mcc": matthews_corrcoef(y, pred)}
    out["roc_auc"] = roc_auc_score(y, p) if len(set(y)) == 2 else float("nan")
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}


def pair_accuracy(frame, p, threshold=0.5):
    """Share of pair_ids whose twins are both right."""
    y = frame["label"].map(LABELS).to_numpy()
    ok = pd.Series(((np.asarray(p) >= threshold).astype(int) == y), index=frame.index)
    return round(float(ok.groupby(frame["pair_id"]).all().mean()), 4), int(frame["pair_id"].nunique())


def wilson(k, n, z=1.959964):
    if n == 0:
        return (float("nan"), float("nan"))
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (round(centre - half, 3), round(centre + half, 3))


def save_json(obj, *parts):
    path = os.path.join(RESULTS, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, indent=1, ensure_ascii=False, default=str)
    return path
