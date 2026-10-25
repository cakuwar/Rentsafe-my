"""Do layer 1's legitimacy signals actually indicate legitimacy?

A signal that fires more often on scams than on honest conversations is not
evidence of honesty — scammers imitate the language of a proper letting. This
measures, per signal, the share of scam and legitimate conversations it fires
on, before and after `analyse()` withholds legitimacy language that appears
alongside a red flag.

    python eval/legit_signal_rates.py

Writes eval/results/legit_signal_rates.json.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from app.layer1.red_flags import LEGIT_SIGNALS, analyse
from app.normaliser.normaliser import normalise

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "data", "processed", "random")
OUT = os.path.join(HERE, "results", "legit_signal_rates.json")


def main():
    frame = pd.concat(
        [pd.read_csv(os.path.join(DATA, name)) for name in ("train.csv", "val.csv")],
        ignore_index=True,
    )
    frame["label"] = frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    totals = frame["label"].value_counts().to_dict()

    ids = [signal["id"] for signal in LEGIT_SIGNALS]
    raw = {i: {"SCAM": 0, "LEGITIMATE": 0} for i in ids}
    shown = {i: {"SCAM": 0, "LEGITIMATE": 0} for i in ids}
    any_raw = {"SCAM": 0, "LEGITIMATE": 0}
    any_shown = {"SCAM": 0, "LEGITIMATE": 0}

    for _, row in frame.iterrows():
        label = row["label"]
        result = analyse(normalise(row["text"]))
        kept = {s["id"] for s in result["legit_signals"]}
        held = {s["id"] for s in result["legit_signals_withheld"]}
        for signal in kept | held:
            raw[signal][label] += 1
        for signal in kept:
            shown[signal][label] += 1
        any_raw[label] += bool(kept | held)
        any_shown[label] += bool(kept)

    def pct(count, label):
        return round(100 * count / totals[label], 1)

    report = {"totals": totals, "signals": {}, "any_signal": {}}
    print(f"{'signal':<22}{'raw scam%':>10}{'raw legit%':>11}"
          f"{'shown scam%':>13}{'shown legit%':>13}")
    for signal in ids:
        entry = {
            "raw_scam_pct": pct(raw[signal]["SCAM"], "SCAM"),
            "raw_legit_pct": pct(raw[signal]["LEGITIMATE"], "LEGITIMATE"),
            "shown_scam_pct": pct(shown[signal]["SCAM"], "SCAM"),
            "shown_legit_pct": pct(shown[signal]["LEGITIMATE"], "LEGITIMATE"),
        }
        entry["fires_more_on_scams"] = entry["raw_scam_pct"] > entry["raw_legit_pct"]
        report["signals"][signal] = entry
        print(f"{signal:<22}{entry['raw_scam_pct']:>10}{entry['raw_legit_pct']:>11}"
              f"{entry['shown_scam_pct']:>13}{entry['shown_legit_pct']:>13}")

    report["any_signal"] = {
        "raw_scam_pct": pct(any_raw["SCAM"], "SCAM"),
        "raw_legit_pct": pct(any_raw["LEGITIMATE"], "LEGITIMATE"),
        "shown_scam_pct": pct(any_shown["SCAM"], "SCAM"),
        "shown_legit_pct": pct(any_shown["LEGITIMATE"], "LEGITIMATE"),
    }
    fired = [s for s, e in report["signals"].items()
             if e["raw_scam_pct"] or e["raw_legit_pct"]]
    report["signals_that_fire"] = len(fired)
    report["of_which_fire_more_on_scams"] = sum(
        report["signals"][s]["fires_more_on_scams"] for s in fired)
    a = report["any_signal"]
    print(f"\n{'ANY signal':<22}{a['raw_scam_pct']:>10}{a['raw_legit_pct']:>11}"
          f"{a['shown_scam_pct']:>13}{a['shown_legit_pct']:>13}")
    print(f"{report['of_which_fire_more_on_scams']} of {len(fired)} signals that fire "
          "at all fire more often on scams")

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
