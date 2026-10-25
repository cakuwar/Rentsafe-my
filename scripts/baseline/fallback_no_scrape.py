"""Prepared, not applied: the baseline without our Aug 2026 iProperty /
PropertyGuru scrape (source "scraped"), in case its terms of use rule it out.

Runs build.py's pipeline twice in memory — every source, then every source
but "scraped" — and compares the two. Writes ONLY
data/processed/fallback_no_scrape.json: no seeds, no listings CSV, no
database change.

Usage:
    nlp-service/.venv/Scripts/python -m scripts.baseline.fallback_no_scrape
"""
import json
import os
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.scrapers import config  # noqa: E402

from scripts.baseline import adjust, coverage  # noqa: E402
from scripts.baseline.cleaning import DropLog, clean, dedupe_across  # noqa: E402
from scripts.baseline.manual_workbook import TARGETS, cell_key  # noqa: E402
from scripts.baseline.schema import (MIN_BUILDINGS, MIN_LISTINGS, ROOM_KEY, WHOLE_UNIT_KEY,  # noqa: E402
                                     conform, empty_frame)
from scripts.baseline.sources import REGISTRY  # noqa: E402

REMOVED = "scraped"
OUT = os.path.join(config.DATA_PROCESSED, "fallback_no_scrape.json")


def _typed_empty():
    """An empty source with the numeric dtypes the adjustment's merges expect."""
    return empty_frame().astype({"bedrooms": "float64", "price_raw": "float64", "size_sqft": "float64"})


def pool(exclude=()):
    """build.py's pipeline up to the pooled listings, in memory."""
    log = DropLog()
    loaded = {}
    for name, source in REGISTRY.items():
        if name in exclude:
            continue
        df, _ = source.loader(source, log)
        loaded[name] = clean(df, name, log, source.dedupe_unit_key)
    ordered = sorted(loaded.items(), key=lambda kv: REGISTRY[kv[0]].priority)
    frames = dict(dedupe_across(ordered, log))

    adjustment = adjust.compute(frames["kaggle"], frames.get(REMOVED, _typed_empty()))
    pooled = conform(pd.concat([conform(df) for df in frames.values()], ignore_index=True))
    adjusted_sources = [n for n, s in REGISTRY.items() if s.time_adjusted]
    pooled = adjust.apply(pooled, adjustment["factor"], adjusted_sources)
    pooled["bedrooms"] = pooled["bedrooms"].astype("Int64")
    cleaning = log.summary(pooled["source"].value_counts().to_dict())
    return pooled, adjustment, cleaning


def index_cells(pooled):
    units = pooled[pooled["property_type"] != "room"]
    rooms = pooled[pooled["property_type"] == "room"]
    out = {}
    for c in coverage.cells(units, WHOLE_UNIT_KEY):
        out[f"{c['area']} | {c['property_type']} {c['bedrooms']}BR"] = c
    for c in coverage.cells(rooms, ROOM_KEY):
        out[f"{c['area']} | {c['room_type']} room"] = c
    return out


def compact(c):
    if c is None:
        return None
    return {"status": c["status"], "listings": c["listings"], "buildings": c["buildings"],
            "median": c["median"], "sources": c["sources"]}


def ratio_summary(ratios):
    if not ratios:
        return None
    q = statistics.quantiles(ratios, n=4) if len(ratios) > 1 else [ratios[0]] * 3
    return {"strata": len(ratios), "median": round(statistics.median(ratios), 4),
            "iqr": [round(q[0], 4), round(q[2], 4)], "min": round(min(ratios), 4), "max": round(max(ratios), 4)}


def priority_cells(cells):
    """The manual workbook's 18 target cells under these cells."""
    rows = []
    for priority, area, kind in TARGETS:
        label = f"{area} | condo 0BR" if kind == "studio" else f"{area} | {kind} room"
        c = cells.get(label)
        n, b = (c["listings"], c["buildings"]) if c else (0, 0)
        rows.append({"priority": priority, "cell": cell_key(area, kind), "listings": n, "buildings": b,
                     "rows_needed": max(0, MIN_LISTINGS - n, MIN_BUILDINGS - b)})
    return rows


def main():
    current, adj_cur, clean_cur = pool()
    fallback, adj_fb, clean_fb = pool(exclude={REMOVED})
    cur, fb = index_cells(current), index_cells(fallback)

    # Status of every stratum before -> after ("absent" = no row at all).
    changes, transitions = [], Counter()
    for key in sorted(set(cur) | set(fb)):
        before = cur[key]["status"] if key in cur else "absent"
        after = fb[key]["status"] if key in fb else "absent"
        if before != after:
            transitions[f"{before} -> {after}"] += 1
            changes.append({"stratum": key, "current": compact(cur.get(key)), "fallback": compact(fb.get(key))})

    def status_counts(cells, kind):
        return dict(Counter(c["status"] for k, c in cells.items() if k.endswith(" room") == (kind == "rooms")))

    lost = [c["stratum"] for c in changes if c["current"] and c["current"]["status"] == "scorable"]
    gained = [c["stratum"] for c in changes if c["fallback"] and c["fallback"]["status"] == "scorable"]

    # Median shift for strata scorable in both builds.
    ratios = {"kaggle_only": [], "mixed": []}
    for key in set(cur) & set(fb):
        if cur[key]["status"] == fb[key]["status"] == "scorable":
            group = "kaggle_only" if cur[key]["sources"] == "kaggle" else "mixed"
            ratios[group].append(fb[key]["median"] / cur[key]["median"])

    kaggle_fb = fallback[fallback["source"] == "kaggle"]
    unadjusted = bool((kaggle_fb["price_adjusted"].astype(float) == kaggle_fb["price_raw"].astype(float)).all())
    cov_cur, cov_fb = coverage.report(current), coverage.report(fallback)
    prio_cur, prio_fb = priority_cells(cur), priority_cells(fb)
    factor_now = adj_cur["factor"]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "applied": False,
        "what": f"the baseline with source '{REMOVED}' (our Aug 2026 iProperty / PropertyGuru scrape) removed; "
                "computed in memory — seeds, baseline_listings.csv and the database are unchanged",
        "to_apply": [f"remove the '{REMOVED}' entry from scripts/baseline/sources/__init__.py REGISTRY",
                     "re-run: nlp-service/.venv/Scripts/python -m scripts.baseline.build",
                     "then: cd backend && npm run seed",
                     "then re-run backend/scripts/price_loo_eval.js: the false-positive rate was measured "
                     "on adjusted prices"],
        "pooled_listings": {
            "current": current["source"].value_counts().to_dict(),
            "fallback": fallback["source"].value_counts().to_dict(),
            "kaggle_rows_regained": int((fallback["source"] == "kaggle").sum() - (current["source"] == "kaggle").sum()),
            "kaggle_rows_regained_note": "Kaggle rows that the current build drops as duplicates of a scraped "
                                         "listing (cross-source dedupe) come back once the scrape is gone",
        },
        "time_adjustment": {
            "current": {"factor": factor_now, "status": adj_cur["status"],
                        "pairs": adj_cur["building_matched"]["all_pairs"]["pairs"],
                        "iqr": adj_cur["building_matched"]["all_pairs"].get("iqr")},
            "fallback": {"factor": adj_fb["factor"], "effective_factor": 1.0, "status": adj_fb["status"],
                         "pairs": adj_fb["building_matched"]["all_pairs"]["pairs"],
                         "kaggle_prices_used_as_listed": unadjusted,
                         "fallbacks_reported_by_adjust_py": adj_fb["fallbacks"]},
            "data_age_limitation": (
                "With no scrape there is nothing to estimate a time factor from, so it falls back to 1.00: "
                "Kaggle prices are used as listed — Mudah asking prices from about 2023 (inferred; the file "
                "has no date). The current build put Aug 2026 asking prices at "
                f"{factor_now}× those (IQR {adj_cur['building_matched']['all_pairs'].get('iqr')}), so fallback "
                f"medians sit about {round((1 - 1 / factor_now) * 100)}% below today's asking prices: a bait "
                "price looks less far below its median (fewer flags, more misses). The backend's data note "
                "would drop the 'scaled ×1.20' clause and the iProperty / PropertyGuru source."
                if factor_now else "the current build applied no factor either"),
        },
        "strata": {
            "whole_units": {"current": status_counts(cur, "units"), "fallback": status_counts(fb, "units")},
            "rooms": {"current": status_counts(cur, "rooms"), "fallback": status_counts(fb, "rooms"),
                      "note": "every room stratum came from the scrape (manual rows: none yet), so the room "
                              "baseline is empty without it: every room is no_baseline until manual rows exist"},
        },
        "status_changes": {
            "strata_changed": len(changes),
            "by_transition": dict(transitions.most_common()),
            "scorable_lost": len(lost),
            "scorable_gained": len(gained),
            "scorable_lost_list": lost,
            "scorable_gained_list": gained,
        },
        "median_shift_where_scorable_in_both": {
            "kaggle_only_strata": ratio_summary(ratios["kaggle_only"]),
            "mixed_source_strata": ratio_summary(ratios["mixed"]),
            "note": "fallback median / current median. Kaggle-only strata move by exactly 1/factor; "
                    "mixed strata also lose their scraped rows",
        },
        "coverage": {
            "scorable_target_cells": {"current": cov_cur["scorable_target_cells"],
                                      "fallback": cov_fb["scorable_target_cells"]},
            "targets": [{"target": a["target"], "area": a["area"], "scorable_current": a["scorable_after"],
                         "scorable_fallback": b["scorable_after"]}
                        for a, b in zip(cov_cur["targets"], cov_fb["targets"])],
        },
        "manual_priority_cells": {
            "current": prio_cur, "fallback": prio_fb,
            "rows_needed": {"current": sum(r["rows_needed"] for r in prio_cur),
                            "fallback": sum(r["rows_needed"] for r in prio_fb)},
        },
        "changes": changes,
        "cleaning": {"current": clean_cur, "fallback": clean_fb},
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    sc = report["status_changes"]
    tc = report["coverage"]["scorable_target_cells"]
    print(f"wrote {OUT}  (not applied: seeds and database unchanged)")
    print(f"listings: {report['pooled_listings']['current']} -> {report['pooled_listings']['fallback']} "
          f"(+{report['pooled_listings']['kaggle_rows_regained']} Kaggle rows regained from dedupe)")
    print(f"time factor: {factor_now} ({adj_cur['status']}) -> {adj_fb['factor']} ({adj_fb['status']}); "
          f"Kaggle used as listed: {unadjusted}")
    print(f"strata changing status: {sc['strata_changed']}  {sc['by_transition']}")
    print(f"scorable strata lost: {sc['scorable_lost']}, gained: {sc['scorable_gained']}")
    print(f"whole-unit status: {report['strata']['whole_units']['current']} -> "
          f"{report['strata']['whole_units']['fallback']}")
    print(f"room status: {report['strata']['rooms']['current']} -> {report['strata']['rooms']['fallback']}")
    print(f"target cells scorable: {tc['current']['after']} -> {tc['fallback']['after']} of {tc['current']['of']}")
    print(f"medians, Kaggle-only strata: {report['median_shift_where_scorable_in_both']['kaggle_only_strata']}")
    print(f"medians, mixed strata: {report['median_shift_where_scorable_in_both']['mixed_source_strata']}")
    print(f"manual rows needed (18 priority cells): {report['manual_priority_cells']['rows_needed']}")


if __name__ == "__main__":
    main()
