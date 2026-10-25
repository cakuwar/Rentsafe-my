"""Why retrain run 2 did worse than run 1: what changed in the training data.

Rebuilds run 1's pair data exactly (the current generator without the block
added after run 1; the run-1 model scores 0.9444 pair accuracy on the rebuilt
test split, as it did in Colab), and compares it with run 2's:

  * how often each training mechanic sentence is repeated
  * how many "core" rows (labelled SCAM) hold nothing but a viewing refusal
  * where "reserve" appears, and with which label
  * which words in the scam lines run 2 missed never occur in training
    (needs eval/results/v3_run2_diagnosis.json)

    python eval/run2_data_comparison.py

Writes eval/results/run2_data_comparison.json.
"""
import collections
import json
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
sys.path.insert(0, NLP)

import pandas as pd

from training import make_minimal_pairs as mmp

DATA = os.path.join(NLP, "..", "data", "processed")
DIAGNOSIS = os.path.join(HERE, "results", "v3_run2_diagnosis.json")
OUT = os.path.join(HERE, "results", "run2_data_comparison.json")


def run1_generator():
    """The generator as it was for run 1: without the prefix/core/truncated block."""
    path = os.path.join(NLP, "training", "make_minimal_pairs.py")
    src = open(path, encoding="utf-8").read()
    start = src.index("    # Cuts that give the label a meaning at the level of a WINDOW.")
    end = src.index("    return rows", start)
    module = types.ModuleType("make_minimal_pairs_run1")
    module.__file__ = path
    exec(compile(src[:start] + src[end:], path, "exec"), module.__dict__)
    return module


def body(line):
    return line.split(": ", 1)[-1]


def words(text):
    return set(re.findall(r"[a-z]{3,}", text.lower()))


def main():
    run1 = run1_generator()
    rows1, test1 = run1.generate(480, 7, 0.15)
    rows2 = pd.read_csv(os.path.join(DATA, "augmented", "minimal_pairs_train.csv")).to_dict("records")
    original = pd.read_csv(os.path.join(DATA, "random", "train.csv"))
    report = {"run1_rebuild": {"train_rows": len(rows1), "test_rows": len(test1)}}

    for name, rows in (("run1", rows1), ("run2", rows2)):
        mech = mmp.mechanic_lines(rows)
        seen = collections.Counter(body(l) for r in rows for l in r["text"].split("\n")
                                   if body(l) in mech)
        report[name] = {
            "rows": len(rows),
            "distinct_mechanic_sentences": len(mech),
            "mean_repeats_per_sentence": round(sum(seen.values()) / len(mech), 1),
            "legit_rows_without_any_mechanic": sum(
                1 for r in rows if r["label"] == "LEGITIMATE"
                and not any(body(l) in mech for l in r["text"].split("\n"))),
        }

    viewing = {a for options in mmp.FAMILIES["train"]["scam_viewing"].values() for _, a in options}
    full = {}
    for r in rows2:
        if r["kind"] == "full":
            full.setdefault(r["source_group"], {})[r["label"]] = set(r["text"].split("\n"))
    cores = [r for r in rows2 if r["kind"] == "core"]
    only_viewing = sum(
        all(body(l) in viewing for l in r["text"].split("\n")
            if l not in full[r["source_group"]]["LEGITIMATE"]) for r in cores)
    report["run2_cores"] = {"rows": len(cores), "only_viewing_refusal": only_viewing,
                            "share": round(only_viewing / len(cores), 3)}

    report["reserve"] = {}
    for name, frame in (("run1_pairs", pd.DataFrame(rows1)), ("run2_pairs", pd.DataFrame(rows2)),
                        ("original_corpus", original)):
        hit = frame[frame["text"].str.contains(r"\breserve", case=False)]
        report["reserve"][name] = {
            "rows": int(len(hit)),
            "by_label": {k: int(v) for k, v in hit["label"].value_counts().items()},
            "run2_core_rows": int((hit.get("kind") == "core").sum()) if "kind" in hit else 0,
        }

    if os.path.exists(DIAGNOSIS):
        diagnosis = json.load(open(DIAGNOSIS, encoding="utf-8"))
        vocabulary = set().union(*[words(t) for t in
                                   pd.concat([pd.Series([r["text"] for r in rows2]), original["text"]])])
        unseen = collections.Counter()
        for pair in diagnosis["D_failing_pairs"]:
            for _, scam in pair["differing_lines"]:
                unseen.update(w for w in words(body(scam)) if w not in vocabulary)
        missed = collections.Counter(p["lang"] for p in diagnosis["D_failing_pairs"])
        totals = collections.Counter(r["lang"] for r in diagnosis["pair_test_rows"]
                                     if r["kind"] == "full" and r["label"] == "SCAM")
        report["run2_misses"] = {
            "missed_scam_twins_by_language": {k: f"{missed[k]}/{totals[k]}" for k in sorted(totals)},
            "words_never_in_training": unseen.most_common(15),
        }

    print(json.dumps(report, indent=2, ensure_ascii=False))
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
