"""What the MODERATE band cap costs, measured on the data we have.

The cap (backend scoring.service.js, capUnsupportedScore): a model score >= 0.5
with no layer-1 red flag is held at MODERATE. Its cost is scams the rules do
not recognise — they lose HIGH. This measures, for the deployed model:

  * scams with no red flag, and the band each gets before and after the cap
  * that no scam falls BELOW MODERATE because of the cap
  * legitimate conversations moved HIGH -> MODERATE (the intended benefit)

on the random split (train and validation reported separately: the model was
trained on train, so its scores there are optimistic), the held-out-wording
minimal-pair test split, and the two real conversations.

Each text goes through the service's own layer 1 (normalised) and layer 2
(raw text) exactly as /classify does. Bands come from the backend's real code
via backend/scripts/apply_band_cap.js, scored on NLP alone as production is
today.

    python eval/cap_cost.py

Writes eval/results/cap_cost.json.
"""
import collections
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
ROOT = os.path.dirname(NLP)
sys.path.insert(0, NLP)

import pandas as pd

from app import config
from app.layer1.red_flags import analyse
from app.layer2.classifier import classify
from app.normaliser.normaliser import normalise

DATA = os.path.join(ROOT, "data", "processed")
HELPER = os.path.join(ROOT, "backend", "scripts", "apply_band_cap.js")
OUT = os.path.join(HERE, "results", "cap_cost.json")


def load_sets():
    sets = {}
    for split in ("train", "val"):
        frame = pd.read_csv(os.path.join(DATA, "random", f"{split}.csv"))
        frame["label"] = frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
        sets[f"random/{split}"] = frame[["text", "label"]]
    pairs = pd.read_csv(os.path.join(DATA, "augmented", "minimal_pairs_test.csv"))
    sets["minimal_pairs_test (held-out wording)"] = pairs[pairs["kind"] == "full"][["text", "label"]]
    gates = json.load(open(os.path.join(NLP, "training", "gates.json"), encoding="utf-8"))
    sets["real conversations"] = pd.DataFrame(
        [{"text": gates[n]["text"], "label": gates[n]["expect"], "name": n}
         for n in ("real_scam_production", "real_legit_production", "real_legit_clean")])
    return sets


def bands(rows):
    result = subprocess.run(["node", HELPER], input=json.dumps(rows), capture_output=True,
                            text=True, check=True, cwd=os.path.join(ROOT, "backend"))
    return json.loads(result.stdout)


def main():
    report = {"model": config.FINETUNED_MODEL_DIR.replace("\\", "/").split("/")[-1], "sets": {}}
    for name, frame in load_sets().items():
        rows = []
        for record in frame.itertuples():
            layer2 = classify(record.text)
            flags = analyse(normalise(record.text))["red_flags"]
            rows.append({"p": layer2["scam_probability"], "status": layer2["status"],
                         "confidence": layer2["confidence"], "redFlags": flags,
                         "label": record.label, "name": getattr(record, "name", None)})
        scored = bands([{k: r[k] for k in ("p", "status", "confidence", "redFlags")} for r in rows])

        summary = {}
        for label in ("SCAM", "LEGITIMATE"):
            members = [(r, s) for r, s in zip(rows, scored) if r["label"] == label]
            no_flags = [(r, s) for r, s in members if not r["redFlags"]]
            moved = collections.Counter(
                f"{s['uncapped']['band']} -> {s['capped']['band']}"
                for r, s in members if s["uncapped"]["band"] != s["capped"]["band"])
            summary[label] = {
                "conversations": len(members),
                "no_red_flags": len(no_flags),
                "no_red_flags_bands_before": dict(collections.Counter(s["uncapped"]["band"] for _, s in no_flags)),
                "no_red_flags_bands_after": dict(collections.Counter(s["capped"]["band"] for _, s in no_flags)),
                "band_changes": dict(moved),
                "dropped_below_moderate_by_cap": sum(
                    1 for _, s in members
                    if s["capped"]["band"] == "LOW" and s["uncapped"]["band"] != "LOW"),
                "bands_after": dict(collections.Counter(s["capped"]["band"] for _, s in members)),
            }
        entry = {"summary": summary}
        if name == "real conversations":
            entry["each"] = [{"name": r["name"], "p": r["p"], "red_flags": len(r["redFlags"]),
                              "before": s["uncapped"], "after": s["capped"]}
                             for r, s in zip(rows, scored)]
        report["sets"][name] = entry

        print(f"\n== {name}")
        for label, s in summary.items():
            print(f"  {label:<10} {s['conversations']:>4} conversations | no red flag: {s['no_red_flags']:>3}"
                  f" | bands before (no-flag ones): {s['no_red_flags_bands_before']}"
                  f" -> after: {s['no_red_flags_bands_after']}")
            print(f"  {'':<10} band changes: {s['band_changes'] or 'none'}"
                  f" | dropped below MODERATE by the cap: {s['dropped_below_moderate_by_cap']}")
        for each in entry.get("each", []):
            print(f"    {each['name']:<24} p={each['p']:.4f} flags={each['red_flags']}"
                  f"  {each['before']['band']} -> {each['after']['band']} ({each['after']['total']})")

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
