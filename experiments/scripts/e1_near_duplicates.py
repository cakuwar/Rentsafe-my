"""E1. Near-duplicate check between the 15 blind-test transcripts and the training data.

Fixed before any result was seen:
  training items  the 474 corpus conversations (random/train.csv 379 + random/val.csv 95)
                  and run 1's 932 minimal-pair training rows = 1,406 items
  preprocessing   speaker labels ("Renter:", "Owner:") removed from the start of each
                  line (they occur in every text); lowercase; words = [a-z0-9]+
  1. cosine       character 3-5-gram TF-IDF (fitted on the 1,406 items + 15 cases), cosine
  2. containment  share of the case's word 8-grams that also occur in the item
  3. longest run  longest common sequence of consecutive words (difflib, autojunk off)
  flag            cosine >= 0.80 OR containment >= 0.20 OR longest run >= 15 words
  reference       the same three figures between cases 2/6/10 and 12/13 (known shared scripts)

Run with the nlp-service venv: .venv/Scripts/python.exe -I -B experiments/scripts/e1_near_duplicates.py
Numbers and item ids go to experiments/results/e1/near_duplicates.json. The overlapping
text (redacted) goes OUTSIDE the repo: ~/rentsafe_experiments_data/e1/overlaps.md.
"""
import difflib
import os
import re
import sys
from itertools import combinations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anonymise import anonymise  # noqa: E402
from common import BLIND_FILE, DATA, PRIVATE, load, save_json  # noqa: E402

COS, CONTAIN, RUN = 0.80, 0.20, 15
LABEL = re.compile(r"^\s*(renter|owner)\s*:\s*", re.IGNORECASE | re.MULTILINE)
REFERENCE = [("case02", "case06"), ("case02", "case10"), ("case06", "case10"), ("case12", "case13")]


def clean(text):
    return LABEL.sub("", str(text))


def words(text):
    return re.findall(r"[a-z0-9]+", clean(text).lower())


def grams(tokens, n=8):
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def containment(a_tokens, b_grams):
    g = grams(a_tokens)
    return len(g & b_grams) / len(g) if g else 0.0


def longest_run(a, b):
    m = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return m.size, " ".join(a[m.a:m.a + m.size])


def training_items():
    items = []
    for name, split in (("train.csv", "train"), ("val.csv", "val")):
        for i, r in load(name).iterrows():
            items.append({"id": f"corpus:{split}:{i}", "origin": r.origin, "group": r.source_group,
                          "label": r.label, "text": r.text})
    for _, r in load("run1_minimal_pairs_train.csv").iterrows():
        items.append({"id": f"pairs:{r.pair_id}:{r.label[:5]}", "origin": "minimal_pair",
                      "group": r.source_group, "label": r.label, "text": r.text})
    assert len(items) == 1406, len(items)
    return items


def main():
    items = training_items()
    blind = pd.read_csv(BLIND_FILE)
    cases = blind.to_dict("records")
    vec = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), lowercase=True)
    matrix = vec.fit_transform([clean(t["text"]) for t in items] + [clean(c["text"]) for c in cases])
    train_m, case_m = matrix[:len(items)], matrix[len(items):]
    cos = (case_m @ train_m.T).toarray()                   # rows are L2-normalised
    item_words = [words(t["text"]) for t in items]
    item_grams = [grams(w) for w in item_words]

    report, overlaps = {"settings": __doc__, "cases": {}, "reference_pairs": {}}, []
    for ci, case in enumerate(cases):
        cw = words(case["text"])
        cont = np.array([containment(cw, g) for g in item_grams])
        runs = [longest_run(cw, w) for w in item_words]
        run_len = np.array([r[0] for r in runs])
        top = {"cosine": int(cos[ci].argmax()), "containment": int(cont.argmax()), "longest_run": int(run_len.argmax())}
        best = {k: {"item": items[j]["id"], "origin": items[j]["origin"], "group": items[j]["group"],
                    "label": items[j]["label"], "cosine": round(float(cos[ci, j]), 4),
                    "containment": round(float(cont[j]), 4), "longest_run_words": int(run_len[j])}
                for k, j in top.items()}
        flagged = (cos[ci].max() >= COS) or (cont.max() >= CONTAIN) or (run_len.max() >= RUN)
        report["cases"][case["case_id"]] = {
            "label": case["label"], "origin": case["origin"], "words": len(cw),
            "max_cosine": round(float(cos[ci].max()), 4), "max_containment": round(float(cont.max()), 4),
            "max_longest_run_words": int(run_len.max()), "flagged": bool(flagged), "best": best,
            "items_over_threshold": int(((cos[ci] >= COS) | (cont >= CONTAIN) | (run_len >= RUN)).sum()),
        }
        j = top["longest_run"]
        overlaps.append((case["case_id"], items[j]["id"], int(run_len[j]), runs[j][1], flagged))

    texts = {c["case_id"]: c["text"] for c in cases}
    for a, b in REFERENCE:
        wa, wb = words(texts[a]), words(texts[b])
        va, vb = vec.transform([clean(texts[a])]), vec.transform([clean(texts[b])])
        size, run = longest_run(wa, wb)
        report["reference_pairs"][f"{a}~{b}"] = {
            "cosine": round(float((va @ vb.T).toarray()[0, 0]), 4),
            "containment_a_in_b": round(containment(wa, grams(wb)), 4),
            "containment_b_in_a": round(containment(wb, grams(wa)), 4),
            "longest_run_words": size}
        overlaps.append((a, b, size, run, None))

    # The case-to-case maximum over ALL other cases, for context.
    report["max_between_any_two_cases"] = {}
    for a, b in combinations(sorted(texts), 2):
        wa, wb = words(texts[a]), words(texts[b])
        report["max_between_any_two_cases"][f"{a}~{b}"] = {
            "cosine": round(float((vec.transform([clean(texts[a])]) @ vec.transform([clean(texts[b])]).T).toarray()[0, 0]), 4),
            "containment_max": round(max(containment(wa, grams(wb)), containment(wb, grams(wa))), 4),
            "longest_run_words": longest_run(wa, wb)[0]}

    path = save_json(report, "e1", "near_duplicates.json")
    os.makedirs(os.path.join(PRIVATE, "e1"), exist_ok=True)
    lines = ["# E1 overlapping text (redacted). Personal data: keep outside the repo.", ""]
    for a, b, size, run, flagged in overlaps:
        tag = "reference pair" if flagged is None else ("FLAGGED" if flagged else "not flagged")
        lines += [f"## {a} vs {b}: {size} words ({tag})", "", "> " + anonymise(run)[0], ""]
    open(os.path.join(PRIVATE, "e1", "overlaps.md"), "w", encoding="utf-8").write("\n".join(lines))

    print(f"{'case':<7}{'label':<11}{'origin':<10}{'max cos':>8}{'max cont':>9}{'max run':>8}  flagged  best-cosine item")
    for cid, r in report["cases"].items():
        print(f"{cid:<7}{r['label']:<11}{r['origin']:<10}{r['max_cosine']:>8.3f}{r['max_containment']:>9.3f}"
              f"{r['max_longest_run_words']:>8}  {'YES' if r['flagged'] else 'no ':<7}  {r['best']['cosine']['item']} ({r['best']['cosine']['origin']})")
    print("reference pairs:", report["reference_pairs"])
    print("wrote", path)


if __name__ == "__main__":
    main()
