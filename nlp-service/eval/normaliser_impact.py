"""Layer 1 flag rates with and without the English-homograph fix.

The shortform dictionary mapped "come" -> "comel" and "no" -> "nombor", which
rewrote ordinary English in code-switched conversations. Both are now marked
ambiguous, which the loader excludes.

This measures the corpus impact by patching the active dictionary in memory —
the CSV is not touched — so the before/after numbers come from one run rather
than from remembering what the last one said.

    python eval/normaliser_impact.py

Writes eval/results/normaliser_impact.json.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from app.layer1.red_flags import RULES, extract_red_flags
from app.normaliser import normaliser as normaliser_module
from app.normaliser.normaliser import normalise

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "data", "processed", "random")
OUT = os.path.join(HERE, "results", "normaliser_impact.json")

# The entries removed by the fix, restored for the "before" measurement.
HOMOGRAPHS = {"come": "comel", "no": "nombor"}


def find_dictionary():
    """The module-level dict the normaliser looks words up in."""
    for name in dir(normaliser_module):
        value = getattr(normaliser_module, name)
        if isinstance(value, dict) and value.get("tq") or (
            isinstance(value, dict) and len(value) > 100
            and all(isinstance(k, str) for k in list(value)[:5])
        ):
            return name, value
    raise SystemExit("could not locate the shortform dictionary on the normaliser")


def measure(frame):
    flagged = {"SCAM": 0, "LEGITIMATE": 0}
    totals = {"SCAM": 0, "LEGITIMATE": 0}
    per_rule = {rule.id: {"SCAM": 0, "LEGITIMATE": 0} for rule in RULES}

    for _, row in frame.iterrows():
        label = row["label"]
        totals[label] += 1
        flags = extract_red_flags(normalise(row["text"]))
        if flags:
            flagged[label] += 1
        for flag in flags:
            per_rule[flag][label] += 1

    return {
        "scam_flagged_pct": round(100 * flagged["SCAM"] / totals["SCAM"], 1),
        "legit_flagged_pct": round(100 * flagged["LEGITIMATE"] / totals["LEGITIMATE"], 1),
        "scam_flagged": flagged["SCAM"],
        "legit_flagged": flagged["LEGITIMATE"],
        "totals": totals,
        "per_rule": per_rule,
    }


def main():
    frame = pd.concat(
        [pd.read_csv(os.path.join(DATA, name)) for name in ("train.csv", "val.csv")],
        ignore_index=True,
    )
    frame["label"] = frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})

    name, dictionary = find_dictionary()
    print(f"patching normaliser.{name} ({len(dictionary)} entries)\n")

    after = measure(frame)

    # Put the homographs back to reproduce the old behaviour.
    dictionary.update(HOMOGRAPHS)
    before = measure(frame)
    for word in HOMOGRAPHS:
        dictionary.pop(word, None)

    print(f"{'':<22} {'before':>8} {'after':>8} {'change':>8}")
    print("-" * 50)
    for key, label in (
        ("scam_flagged_pct", "scams flagged"),
        ("legit_flagged_pct", "legitimate flagged"),
    ):
        print(f"{label:<22} {before[key]:>7.1f}% {after[key]:>7.1f}% "
              f"{after[key] - before[key]:>+7.1f}%")

    print()
    print("Per-rule changes:")
    moved = False
    for rule in RULES:
        b = before["per_rule"][rule.id]
        a = after["per_rule"][rule.id]
        if b != a:
            moved = True
            print(f"  {rule.id:<26} scam {b['SCAM']:>3} -> {a['SCAM']:<3}   "
                  f"legit {b['LEGITIMATE']:>3} -> {a['LEGITIMATE']:<3}")
    if not moved:
        print("  none — the corpus is Malay-heavy synthetic text, where these")
        print("  English homographs barely occur. The fix matters for real")
        print("  English and code-switched input, which the corpus underrepresents.")

    result = {"before": before, "after": after, "homographs_removed": HOMOGRAPHS}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as handle:
        json.dump(result, handle, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
