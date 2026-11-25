"""E3 variant: rebuild the price baseline without the iProperty/PropertyGuru
scrape, in a working copy only (writes to ./data/processed and ./database/seeds
of that copy). This file is a record: it runs from inside the copy,
~/rentsafe_experiments_data/e3_price/no_scraped/ (see README.md beside it).

The build code is the project's, unchanged. Two things are swapped in at run time:
  1. the "scraped" source loads, then returns no rows, so the whole pipeline
     (cleaning, cross-source dedupe, pooling, strata, seeds) runs without it;
  2. the time factor is held at the full build's 1.20. It is estimated from
     buildings listed in both the scrape and Kaggle, so it cannot be recomputed
     once the scrape is removed.

    ..\\..\\.venv\\Scripts\\python.exe -E -s -B -X utf8 run_no_scraped.py
"""
import dataclasses
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from scripts.baseline import adjust, build  # noqa: E402
from scripts.baseline.sources import REGISTRY  # noqa: E402

FULL_ADJUSTMENT = json.load(open(os.path.join(HERE, "..", "full", "data", "processed",
                                              "time_adjustment.json"), encoding="utf-8"))
assert FULL_ADJUSTMENT["factor"] == 1.2, FULL_ADJUSTMENT["factor"]

_load_scraped = REGISTRY["scraped"].loader


def without_rows(source, log):
    df, info = _load_scraped(source, log)
    return df.iloc[0:0].copy(), {**info, "experiment_E3": f"all {len(df)} loaded rows removed"}


def fixed_factor(external, reference, *args, **kwargs):
    out = {k: v for k, v in FULL_ADJUSTMENT.items() if k != "generated_at"}
    out["note_E3"] = ("factor 1.2 carried over from the full build; it needs the scraped "
                      "rows to be recomputed")
    return out


REGISTRY["scraped"] = dataclasses.replace(REGISTRY["scraped"], loader=without_rows)
adjust.compute = fixed_factor
build.main()
