"""Experiment: semantic red flags to extend layer 1's coverage. Evaluation only -
nothing here is wired into the service or the band rules.

Rule (set by the author before any result): adopt only if, on the new-wording
minimal-pair test set, the semantic flags catch at least half of the scam twins
layer 1's regex misses, AND flag no legitimate twin beyond what layer 1 already
flags, AND raise no new red flag on the real iBilik chat. Otherwise report and
drop.

Everything tunable is fixed in eval/results/semantic_flags/plan.json before any
scoring; the script refuses to run if plan.json or the example bank changes.

    python eval/semantic_flags.py

Writes eval/results/semantic_flags/: plan.json, thresholds.json, test_flags.json,
real_chats.json, baseline.json, summary.json, table.md.
"""
import hashlib
import json
import math
import os
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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

from app.layer1.red_flags import analyse
from app.normaliser.normaliser import normalise
from build_semantic_bank import messages
from embedders import E5, MESOLITICA, Embedder

OUT = os.path.join(HERE, "results", "semantic_flags")
BANK = os.path.join(NLP, "app", "layer1", "semantic_tactics.json")
DATA = os.path.join(ROOT, "data", "processed")
MARGIN = 0.01


def bank_hash():
    with open(BANK, encoding="utf-8") as handle:
        return hashlib.sha256(handle.read().encode("utf-8")).hexdigest()


PLAN = {
    "fixed": "2026-09-30, before any scoring on the evaluation sets",
    "candidates": [E5, MESOLITICA],
    "bank": {"file": "app/layer1/semantic_tactics.json", "sha256": None,
             "built_by": "eval/build_semantic_bank.py (layer 1 rules + development scam chat only)"},
    "messages": "a labelled line ('Owner: ' / 'Renter: ') plus its unlabelled continuation "
                "lines; only Owner messages are matched",
    "similarity": "cosine between L2-normalised embeddings; a message's score for a tactic is "
                  "its highest similarity to any of that tactic's examples",
    "threshold": "per tactic and model: the highest score that tactic reaches on any Owner "
                 "message of a LEGITIMATE conversation in data/processed/random train+val, "
                 f"plus {MARGIN} - i.e. no false alarm on that data by construction",
    "semantic_flag": "a conversation carries tactic k if any Owner message scores >= threshold_k",
    "layer1": "app.layer1.red_flags.analyse(normalise(full text)) - as /classify runs it",
    "evaluation": {
        "pairs": "data/processed/augmented/minimal_pairs_test.csv, full conversations "
                 "(72 pairs, wording never in training)",
        "real": ["real scam chat (development chat; the bank was drawn from it - not independent)",
                 "real iBilik chat: current OCR, pre-fix OCR, hand transcript"],
    },
    "model_choice": "on the minimal-pair results with layer 1 + semantic: (1) fewer legitimate "
                    "twins flagged, (2) more of the layer-1-missed scam twins caught, (3) less CPU "
                    "time. The author asked for the choice to use these results, which makes the "
                    "chosen model's numbers slightly optimistic (a choice between two).",
    "adopt_if_all": {
        "a": "the semantic flags catch >= ceil(half) of the scam twins layer 1 misses",
        "b": "legitimate twins flagged by layer 1 + semantic <= those flagged by layer 1 alone",
        "c": "no semantic flag on any version of the real iBilik chat",
    },
    "baseline": "conversation vector = mean of all its message embeddings (both speakers); "
                "sklearn LogisticRegression(C=1.0, class_weight='balanced', max_iter=2000); "
                "trained on random/train.csv + run 1's minimal_pairs_train (rebuilt exactly by "
                "eval/run2_data_comparison.py), the data run 1 was trained on; threshold 0.5; "
                "scored on random/val.csv and the minimal-pair test full conversations",
    "cpu_time": "per chat, with the embedding cache emptied first: embed its Owner messages "
                "and compare with the bank",
}


def write_plan():
    os.makedirs(OUT, exist_ok=True)
    plan = dict(PLAN, bank=dict(PLAN["bank"], sha256=bank_hash()))
    text = json.dumps(plan, indent=2, ensure_ascii=False)
    path = os.path.join(OUT, "plan.json")
    if os.path.exists(path):
        if open(path, encoding="utf-8").read() != text:
            sys.exit("plan.json (or the bank it hashes) differs from what was fixed before "
                     "scoring - refusing to run. Delete plan.json only to start over.")
    else:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)


def owner_messages(text):
    return [body for speaker, body in messages(text) if speaker == "Owner"]


class Flagger:
    def __init__(self, embedder, bank):
        self.embedder = embedder
        self.examples = {k: [e["text"] for e in v] for k, v in bank["tactics"].items()}
        self.vectors = {k: embedder.encode(v) for k, v in self.examples.items()}
        self.thresholds = {}

    def scores(self, msgs):
        """For each message: {tactic: (similarity, example)}."""
        if not msgs:
            return []
        vecs = self.embedder.encode(msgs)
        out = [{} for _ in msgs]
        for tactic, examples in self.vectors.items():
            sims = vecs @ examples.T
            best = sims.argmax(1)
            for i, j in enumerate(best):
                out[i][tactic] = (float(sims[i, j]), self.examples[tactic][j])
        return out

    def fit(self, legit_texts):
        top = {k: -1.0 for k in self.vectors}
        where = {}
        for text in legit_texts:
            msgs = owner_messages(text)
            for msg, per in zip(msgs, self.scores(msgs)):
                for tactic, (sim, _) in per.items():
                    if sim > top[tactic]:
                        top[tactic], where[tactic] = sim, msg
        self.thresholds = {k: round(v + MARGIN, 4) for k, v in top.items()}
        return {k: {"threshold": self.thresholds[k], "highest_legit_score": round(top[k], 4),
                    "highest_legit_message": where.get(k)} for k in top}

    def flag(self, text):
        msgs = owner_messages(text)
        hits = []
        for msg, per in zip(msgs, self.scores(msgs)):
            for tactic, (sim, example) in per.items():
                if sim >= self.thresholds[tactic]:
                    hits.append({"tactic": tactic, "similarity": round(sim, 4),
                                 "threshold": self.thresholds[tactic], "message": msg,
                                 "matched_example": example})
        return hits


def layer1(text):
    return analyse(normalise(text))["red_flags"]


def mean_vector(embedder, text):
    bodies = [body for _, body in messages(text)] or [text]
    return embedder.encode(bodies).mean(0)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    write_plan()
    bank = json.load(open(BANK, encoding="utf-8"))

    train = pd.read_csv(os.path.join(DATA, "random", "train.csv"))
    val = pd.read_csv(os.path.join(DATA, "random", "val.csv"))
    for frame in (train, val):
        frame["label"] = frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    dev_legit = list(pd.concat([train, val]).query("label == 'LEGITIMATE'")["text"])
    dev_scam = list(pd.concat([train, val]).query("label == 'SCAM'")["text"])
    test = pd.read_csv(os.path.join(DATA, "augmented", "minimal_pairs_test.csv"))
    test = test[test["kind"] == "full"].reset_index(drop=True)
    gates = json.load(open(os.path.join(NLP, "training", "gates.json"), encoding="utf-8"))
    before = json.load(open(os.path.join(NLP, "training", "gates_2026-09-27.json"), encoding="utf-8"))
    real = {
        "real scam chat (development chat)": gates["real_scam_production"]["text"],
        "real iBilik chat (current OCR)": gates["real_legit_production"]["text"],
        "real iBilik chat (pre-fix OCR)": before["real_legit_production"]["text"],
        "real iBilik chat (hand transcript)": gates["real_legit_clean"]["text"],
    }
    ibilik = [name for name in real if "iBilik" in name]

    # Layer 1 alone, computed once.
    test["l1"] = [bool(layer1(t)) for t in test["text"]]
    scam_rows = test[test["label"] == "SCAM"]
    legit_rows = test[test["label"] == "LEGITIMATE"]
    l1_missed = scam_rows[~scam_rows["l1"]]
    needed = math.ceil(len(l1_missed) / 2)

    # Run 1's training pairs, rebuilt exactly, for the baseline's training set.
    from run2_data_comparison import run1_generator
    run1_pairs, _ = run1_generator().generate(480, 7, 0.15)
    base_texts = list(train["text"]) + [r["text"] for r in run1_pairs]
    base_labels = list(train["label"]) + [r["label"] for r in run1_pairs]

    report = {"layer1_alone": {
        "scam_twins": len(scam_rows), "scam_twins_caught": int(scam_rows["l1"].sum()),
        "scam_twins_missed": len(l1_missed), "needed_to_adopt": needed,
        "legit_twins": len(legit_rows), "legit_twins_flagged": int(legit_rows["l1"].sum()),
        "real_red_flags": {name: layer1(text) for name, text in real.items()},
    }, "models": {}}
    thresholds, test_flags, real_chats, baseline = {}, {}, {}, {}

    for name in PLAN["candidates"]:
        print(f"== {name}", flush=True)
        embedder = Embedder(name)
        flagger = Flagger(embedder, bank)
        fit = flagger.fit(dev_legit)
        dev_scam_tactics = [sorted({h["tactic"] for h in flagger.flag(t)}) for t in dev_scam]
        for tactic in fit:
            fit[tactic]["dev_scam_conversations_flagged"] = sum(tactic in f for f in dev_scam_tactics)
        fit["_any_tactic_dev_scam_flagged"] = f"{sum(bool(f) for f in dev_scam_tactics)} of {len(dev_scam)}"
        thresholds[name] = fit

        hits = [flagger.flag(t) for t in test["text"]]
        sem = [bool(h) for h in hits]
        caught_missed = sum(sem[i] for i in l1_missed.index)
        legit_combined = sum(bool(test.at[i, "l1"]) or sem[i] for i in legit_rows.index)
        scam_combined = sum(bool(test.at[i, "l1"]) or sem[i] for i in scam_rows.index)
        test_flags[name] = [
            {"pair_id": test.at[i, "pair_id"], "label": test.at[i, "label"], "layer1": bool(test.at[i, "l1"]),
             "semantic": sorted({h["tactic"] for h in hits[i]}), "hits": hits[i]}
            for i in test.index if hits[i] or test.at[i, "label"] == "SCAM"]
        real_chats[name] = {chat: flagger.flag(text) for chat, text in real.items()}

        seconds = []
        for text in list(real.values()) + list(test["text"][:20]):
            embedder.cache.clear()
            start = time.perf_counter()
            flagger.flag(text)
            seconds.append(time.perf_counter() - start)

        # Baseline: embeddings + logistic regression, trained on run 1's data.
        X = np.stack([mean_vector(embedder, t) for t in base_texts])
        y = np.array([label == "SCAM" for label in base_labels], dtype=int)
        clf = LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000).fit(X, y)
        p_val = clf.predict_proba(np.stack([mean_vector(embedder, t) for t in val["text"]]))[:, 1]
        y_val = (val["label"] == "SCAM").to_numpy().astype(int)
        p_test = clf.predict_proba(np.stack([mean_vector(embedder, t) for t in test["text"]]))[:, 1]
        ok = (p_test >= 0.5).astype(int) == (test["label"] == "SCAM").to_numpy().astype(int)
        baseline[name] = {
            "val_accuracy": round(float(((p_val >= 0.5).astype(int) == y_val).mean()), 4),
            "val_macro_f1": round(float(f1_score(y_val, (p_val >= 0.5).astype(int), average="macro")), 4),
            "pairs_row_accuracy": round(float(ok.mean()), 4),
            "pairs_pair_accuracy": round(float(pd.Series(ok).groupby(test["pair_id"]).all().mean()), 4),
            "real": {chat: round(float(clf.predict_proba(mean_vector(embedder, text)[None])[0, 1]), 4)
                     for chat, text in real.items()},
            "train_rows": len(base_texts),
        }

        report["models"][name] = {
            "scam_twins_caught_layer1_plus_semantic": scam_combined,
            "layer1_missed_caught_by_semantic": caught_missed,
            "legit_twins_flagged_layer1_plus_semantic": legit_combined,
            "legit_twins_flagged_by_semantic": sum(sem[i] for i in legit_rows.index),
            "real_semantic_flags": {chat: len(h) for chat, h in real_chats[name].items()},
            "cpu_seconds_per_chat": {"median": round(statistics.median(seconds), 3),
                                     "mean": round(statistics.mean(seconds), 3)},
        }
        m = report["models"][name]
        print(f"  thresholds: {flagger.thresholds}")
        print(f"  scam twins: layer1 {report['layer1_alone']['scam_twins_caught']} -> +semantic {scam_combined} "
              f"| of {len(l1_missed)} layer-1 misses caught: {caught_missed} | legit twins flagged: "
              f"layer1 {report['layer1_alone']['legit_twins_flagged']} -> {legit_combined}")
        print(f"  real chats: {m['real_semantic_flags']} | cpu/chat {m['cpu_seconds_per_chat']}")
        print(f"  baseline LR: {baseline[name]}", flush=True)

    # Model choice, then the decision - both as fixed in the plan.
    def rank(name):
        m = report["models"][name]
        return (m["legit_twins_flagged_layer1_plus_semantic"], -m["layer1_missed_caught_by_semantic"],
                m["cpu_seconds_per_chat"]["median"])
    chosen = min(PLAN["candidates"], key=rank)
    decisions = {}
    for name in PLAN["candidates"]:
        m = report["models"][name]
        checks = {
            "a_catches_half_of_layer1_misses": m["layer1_missed_caught_by_semantic"] >= needed,
            "b_no_extra_legit_twins": m["legit_twins_flagged_layer1_plus_semantic"]
                                     <= report["layer1_alone"]["legit_twins_flagged"],
            "c_no_flag_on_real_ibilik": all(m["real_semantic_flags"][chat] == 0 for chat in ibilik),
        }
        decisions[name] = {"checks": checks, "would_adopt": all(checks.values())}
    report["chosen_model"] = chosen
    report["decisions"] = decisions
    report["outcome"] = ("ADOPT (as evidence only; not wired into band rules yet)"
                         if decisions[chosen]["would_adopt"] else "DROP")

    run1_zs = json.load(open(os.path.join(HERE, "results", "zero_shot_test", "summary.json"),
                             encoding="utf-8"))["models"]["run 1"]
    run1_val_f1 = json.load(open(os.path.join(HERE, "results", "behaviour_checks.json"),
                                 encoding="utf-8"))["validation_metrics"]["macro_f1"]
    report["run1_reference"] = {"val_accuracy": run1_zs["val_accuracy"], "val_macro_f1": run1_val_f1,
                                "pairs_row_accuracy": run1_zs["pairs_row_accuracy"],
                                "pairs_pair_accuracy": run1_zs["pairs_pair_accuracy"],
                                "source": "eval/results/zero_shot_test/summary.json, behaviour_checks.json"}

    short = {E5: "e5-base", MESOLITICA: "mesolitica 64M"}
    l1 = report["layer1_alone"]
    lines = ["| new-wording pairs, 72 each | layer 1 alone | + semantic, e5-base | + semantic, mesolitica 64M |",
             "|---|---|---|---|",
             f"| scam twins caught | {l1['scam_twins_caught']} | "
             + " | ".join(str(report['models'][n]['scam_twins_caught_layer1_plus_semantic']) for n in PLAN['candidates']) + " |",
             f"| of the {l1['scam_twins_missed']} layer 1 misses, caught (need {needed}) | — | "
             + " | ".join(str(report['models'][n]['layer1_missed_caught_by_semantic']) for n in PLAN['candidates']) + " |",
             f"| legitimate twins flagged | {l1['legit_twins_flagged']} | "
             + " | ".join(str(report['models'][n]['legit_twins_flagged_layer1_plus_semantic']) for n in PLAN['candidates']) + " |"]
    for chat in real:
        lines.append(f"| {chat}: flags | {len(l1['real_red_flags'][chat])} red flags | "
                     + " | ".join(str(report['models'][n]['real_semantic_flags'][chat]) + " semantic" for n in PLAN['candidates']) + " |")
    lines.append("| CPU seconds per chat (median / mean) | — | "
                 + " | ".join(f"{report['models'][n]['cpu_seconds_per_chat']['median']} / {report['models'][n]['cpu_seconds_per_chat']['mean']}"
                              for n in PLAN['candidates']) + " |")
    lines += ["", "| baseline | run 1 (deployed) | e5-base + LR | mesolitica 64M + LR |", "|---|---|---|---|"]
    r1 = report["run1_reference"]
    for key, label in (("val_accuracy", "validation accuracy"), ("val_macro_f1", "validation macro-F1"),
                       ("pairs_row_accuracy", "new-wording pairs: row accuracy"),
                       ("pairs_pair_accuracy", "new-wording pairs: pair accuracy")):
        lines.append(f"| {label} | {r1[key]} | " + " | ".join(str(baseline[n][key]) for n in PLAN['candidates']) + " |")
    lines += ["", f"Chosen model (plan's rule): {short[chosen]}.",
              "Checks: " + "; ".join(f"{short[n]}: " + ", ".join(f"{k}={v}" for k, v in d['checks'].items())
                                    for n, d in decisions.items()),
              f"Outcome: **{report['outcome']}**."]
    table = "\n".join(lines)

    for filename, payload in (("thresholds.json", thresholds), ("test_flags.json", test_flags),
                              ("real_chats.json", real_chats), ("baseline.json", baseline),
                              ("summary.json", report)):
        with open(os.path.join(OUT, filename), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
    with open(os.path.join(OUT, "table.md"), "w", encoding="utf-8") as handle:
        handle.write(table + "\n")
    print("\n" + table)


if __name__ == "__main__":
    main()
