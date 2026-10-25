"""Run the baseline pipeline: load every registered source, clean, dedupe,
time-adjust, report coverage. Writes (and touches nothing else):

    data/processed/baseline_listings.csv    pooled listings, schema.FIELDS
    data/processed/time_adjustment.json
    data/processed/external_coverage.json
    database/seeds/001_price_baseline.sql   price_baseline strata
    database/seeds/003_room_price_baseline.sql

Usage:
    nlp-service/.venv/Scripts/python -m scripts.baseline.build
"""
import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.scrapers import config  # noqa: E402

from scripts.baseline import adjust, coverage  # noqa: E402
from scripts.baseline.cleaning import DropLog, clean, dedupe_across  # noqa: E402
from scripts.baseline.manual_workbook import TARGETS, cell_key  # noqa: E402
from scripts.baseline.schema import (MIN_BUILDINGS, MIN_LISTINGS, ROOM_KEY, WHOLE_UNIT_KEY,  # noqa: E402
                                     building_key, conform)
from scripts.baseline.seeds import PRICE_SEED, ROOM_SEED, write_seeds  # noqa: E402
from scripts.baseline.sources import REGISTRY  # noqa: E402

OUT_LISTINGS = os.path.join(config.DATA_PROCESSED, "baseline_listings.csv")
OUT_ADJUST = os.path.join(config.DATA_PROCESSED, "time_adjustment.json")
OUT_COVERAGE = os.path.join(config.DATA_PROCESSED, "external_coverage.json")


def subtype_check(pooled, source="kaggle"):
    """Per (area, bedrooms), the price gap between subtypes: Flat vs Apartment
    (now separate types) and Service Residence vs Condominium (both condo)."""
    df = pooled[(pooled["source"] == source) & (pooled["property_type"] != "room")]
    pairs = {"flat_vs_apartment": ("Flat", "Apartment"), "condo": ("Service Residence", "Condominium")}
    out = []
    for ptype, (a, b) in pairs.items():
        for (area, br), g in df.groupby(["area", "bedrooms"]):
            ga, gb = g[g["source_subtype"] == a], g[g["source_subtype"] == b]
            if len(ga) >= MIN_LISTINGS and len(gb) >= MIN_LISTINGS:
                ma, mb = ga["price_adjusted"].median(), gb["price_adjusted"].median()
                out.append({"property_type": ptype, "area": area, "bedrooms": int(br),
                            a: {"listings": len(ga), "median": float(ma)},
                            b: {"listings": len(gb), "median": float(mb)},
                            "gap": round(float(ma / mb - 1), 4)})
    return out


def print_manual_report(info):
    """The workbook import: what was accepted, and every rejected row."""
    if not info.get("exists"):
        print(f"manual workbook: {info['file']} not found")
        return
    accepted = ", ".join(f"{s} {n}" for s, n in info["accepted"].items())
    print(f"manual workbook: accepted {accepted}; rejected {len(info['rejected'])}; "
          f"skipped {info['skipped_example']} example row(s)")
    for r in info["rejected"]:
        print(f"  REJECTED {r['sheet']} row {r['row']}: {r['reason']}")
    for r in info["mapped_to_common"]:
        print(f"  {r['sheet']} row {r['row']}: room_type {r['room_type']!r} recorded as common")
    if info["no_date"]:
        print(f"  {len(info['no_date'])} row(s) without date_seen")


def print_progress(pooled):
    """The workbook's Progress cells after the rebuild, from the pooled listings."""
    units = {(c["area"], c["bedrooms"]): c for c in coverage.cells(
        pooled[(pooled["property_type"] == "condo") & (pooled["bedrooms"] == 0)], WHOLE_UNIT_KEY)}
    rooms = {(c["area"], c["room_type"]): c for c in coverage.cells(
        pooled[pooled["property_type"] == "room"], ROOM_KEY)}
    print("progress (manual workbook cells):")
    for priority, area, kind in TARGETS:
        c = units.get((area, 0)) if kind == "studio" else rooms.get((area, kind))
        n, b = (c["listings"], c["buildings"]) if c else (0, 0)
        manual = c["by_source"].get("manual", 0) if c else 0
        done = "✅" if n >= MIN_LISTINGS and b >= MIN_BUILDINGS else "  "
        print(f"  {done} {priority:<9} {cell_key(area, kind):<32} {n:>3} rows / {b:>2} bldg  ({manual} manual)")


def main():
    log = DropLog()
    loaded, infos = {}, {}
    for name, source in REGISTRY.items():
        df, info = source.loader(source, log)
        loaded[name], infos[name] = clean(df, name, log, source.dedupe_unit_key), info

    ordered = sorted(loaded.items(), key=lambda kv: REGISTRY[kv[0]].priority)
    frames = dict(dedupe_across(ordered, log))

    adjustment = adjust.compute(frames["kaggle"], frames["scraped"])
    pooled = conform(pd.concat([conform(df) for df in frames.values()], ignore_index=True))
    adjusted_sources = [n for n, s in REGISTRY.items() if s.time_adjusted]
    pooled = adjust.apply(pooled, adjustment["factor"], adjusted_sources)
    pooled["bedrooms"] = pooled["bedrooms"].astype("Int64")

    rows_out = pooled["source"].value_counts().to_dict()
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cov = coverage.report(pooled)

    sources = {}
    cleaning = log.summary(rows_out)
    for name, source in REGISTRY.items():
        sources[name] = {
            "path": source.path, "origin": source.origin, "license": source.license,
            "collected_at": source.collected_at, "collected_at_note": source.collected_at_note,
            "time_adjusted": source.time_adjusted, "cleaning": cleaning.get(name), "loader": infos[name],
        }

    os.makedirs(config.DATA_PROCESSED, exist_ok=True)
    pooled.to_csv(OUT_LISTINGS, index=False)
    with open(OUT_ADJUST, "w", encoding="utf-8") as f:
        json.dump({"generated_at": generated, **adjustment}, f, indent=2, ensure_ascii=False)
    with open(OUT_COVERAGE, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": generated,
            "eligibility": {"min_listings": MIN_LISTINGS, "min_buildings": MIN_BUILDINGS,
                            "labels": "scorable is the only status ever scored; few-bldg, thin, "
                                      "sparse and empty are reporting labels"},
            "sources": sources,
            "pooled_listings": {"total": len(pooled), "by_source": rows_out,
                                "by_type": pooled["property_type"].value_counts().to_dict(),
                                "distinct_buildings": len({building_key(b) for b in pooled["building"]} - {None})},
            "time_adjustment": {"factor": adjustment["factor"], "applied": adjustment["applied"],
                                "status": adjustment["status"], "detail": "time_adjustment.json"},
            "subtype_check": subtype_check(pooled),
            **cov,
        }, f, indent=2, ensure_ascii=False, default=str)

    seeded = write_seeds(pooled, adjustment["factor"], REGISTRY)

    print_manual_report(infos["manual"])
    print(f"pooled listings: {len(pooled)} {rows_out}")
    for name, c in cleaning.items():
        print(f"  {name}: {c['rows_in']} in -> {c['rows_out']} out; dropped {c['dropped']}")
    print(f"time adjustment: {adjustment['status']}, factor {adjustment['factor']}, "
          f"{adjustment['strata_used']} strata")
    print(f"scorable target cells: {cov['scorable_target_cells']}")
    print(f"wrote {OUT_LISTINGS}\n      {OUT_ADJUST}\n      {OUT_COVERAGE}")
    print(f"      {PRICE_SEED} ({seeded['price_baseline']} strata)\n"
          f"      {ROOM_SEED} ({seeded['room_price_baseline']} strata)")
    print_progress(pooled)


if __name__ == "__main__":
    main()
