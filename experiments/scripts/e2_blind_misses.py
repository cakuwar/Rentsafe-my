"""Why did TF-IDF variant B miss blind cases 5 and 13? Diagnosis only, after the
result: nothing here changes E2's settings or scores.

  1. word-level contributions (coefficient x TF-IDF value) of each case's own
     n-grams, towards SCAM and towards LEGITIMATE
  2. the same model applied to windows of 15 consecutive messages (stride 5),
     taking the highest window, as run 1 does with its token windows: if one
     window scores clearly higher than the whole chat, the scam signal was
     diluted by the rest of a long conversation

Run: nlp-service/.venv/Scripts/python.exe -I -B -X utf8 experiments/scripts/e2_blind_misses.py
Numbers go to experiments/results/e2/blind_misses.json; the n-gram lists, which
come from the chat text, go OUTSIDE the repo (~/rentsafe_experiments_data/e2/).
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BLIND_FILE, LABELS, PRIVATE, run1_split, save_json  # noqa: E402
from e2_tfidf_lr import make_pipeline, p_scam  # noqa: E402

WINDOW, STRIDE = 15, 5


def windows(text):
    lines = [l for l in str(text).split("\n") if l.strip()]
    if len(lines) <= WINDOW:
        return ["\n".join(lines)]
    starts = list(range(0, len(lines) - WINDOW + 1, STRIDE))
    if starts[-1] + WINDOW < len(lines):
        starts.append(len(lines) - WINDOW)
    return ["\n".join(lines[s:s + WINDOW]) for s in starts]


def main():
    _, _, train_b, _ = run1_split()
    pipe = make_pipeline(10).fit(train_b["text"], train_b["label"].map(LABELS))   # C chosen in E2
    union = pipe.named_steps["tfidf"]
    coef = pipe.named_steps["lr"].coef_[0]
    names = union.get_feature_names_out()
    blind = pd.read_csv(BLIND_FILE)
    public, private = {}, {}
    for _, row in blind.iterrows():
        whole = float(p_scam(pipe, [row.text])[0])
        win = p_scam(pipe, windows(row.text))
        public[row.case_id] = {"label": row.label, "p_whole_chat": round(whole, 4),
                               "windows": int(len(win)), "p_best_window": round(float(win.max()), 4),
                               "messages": int(sum(1 for l in str(row.text).split("\n") if l.strip()))}
        if row.case_id in ("case05", "case13"):
            x = union.transform([row.text]).toarray()[0]
            contrib = x * coef
            word = [i for i in np.nonzero(x)[0] if names[i].startswith("word__")]
            order = sorted(word, key=lambda i: contrib[i])
            private[row.case_id] = {
                "towards_scam": [(names[i][6:], round(float(contrib[i]), 3)) for i in order[::-1][:12]],
                "towards_legit": [(names[i][6:], round(float(contrib[i]), 3)) for i in order[:12]],
                "share_of_positive_word_mass_from_top10": round(
                    float(sum(sorted([c for c in contrib[word] if c > 0], reverse=True)[:10])
                          / max(1e-9, sum(c for c in contrib[word] if c > 0))), 3),
                "window_scores": [round(float(p), 3) for p in win]}
    save_json(public, "e2", "blind_misses.json")
    os.makedirs(os.path.join(PRIVATE, "e2"), exist_ok=True)
    with open(os.path.join(PRIVATE, "e2", "blind_misses_features.json"), "w", encoding="utf-8") as handle:
        json.dump(private, handle, indent=1, ensure_ascii=False)
    for cid in ("case05", "case13"):
        print(cid, public[cid])
        print("   towards scam: ", private[cid]["towards_scam"])
        print("   towards legit:", private[cid]["towards_legit"])
        print("   window scores:", private[cid]["window_scores"])
    caught_by_window = sum((v["p_best_window"] >= 0.5) == (v["label"] == "SCAM") for v in public.values())
    print("blind cases right if the best window is used (diagnostic only):", caught_by_window, "of 15")


if __name__ == "__main__":
    main()
