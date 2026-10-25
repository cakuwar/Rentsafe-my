"""Coverage matrices, the target-area comparison and the manual-room gap list."""
import pandas as pd

from .schema import (MIN_BUILDINGS, MIN_LISTINGS, ROOM_KEY, ROOM_TYPES, WHOLE_UNIT_KEY,
                     building_key, stratum_status)

# The 14 target areas of the 2026-10-14 audit: PRD §18.4's ten plus four
# university areas. Audit name -> canonical area now.
TARGETS = [
    ("Cyberjaya", "Cyberjaya"), ("Petaling Jaya", "Petaling Jaya"), ("Shah Alam", "Shah Alam"),
    ("Subang Jaya", "Subang Jaya"), ("Cheras", "Cheras (KL)"), ("Setapak", "Setapak"),
    ("KLCC", "KLCC"), ("Bangsar", "Bangsar"), ("Puchong", "Puchong (Selangor)"),
    ("Klang", "Klang"), ("Bukit Jalil", "Bukit Jalil"), ("Seri Kembangan", "Seri Kembangan"),
    ("Kajang", "Kajang"), ("Gombak", "Gombak (Selangor)"),
]
TARGET_CELLS = [("condo", 1), ("condo", 2), ("condo", 3), ("apartment", 2), ("apartment", 3),
                ("landed", 3), ("landed", 4)]

# The audit's figures (scrape only, the old 18-area mapping; its "KLCC" was the
# portal's "KL City Centre", Pudu included), as [listings, buildings].
AUDIT_BEFORE = {
    "Petaling Jaya": {"condo_2": [1, 1], "condo_3": [4, 4], "landed_3": [1, 1]},
    "Shah Alam": {"condo_2": [1, 1]},
    "Subang Jaya": {"condo_2": [2, 2], "condo_3": [2, 2]},
    "Cheras": {"condo_1": [4, 3], "condo_2": [1, 1], "condo_3": [3, 3]},
    "Setapak": {"condo_3": [4, 3]},
    "KLCC": {"condo_1": [18, 10], "condo_2": [27, 19], "condo_3": [15, 14]},
    "Bangsar": {"condo_1": [4, 2], "condo_2": [7, 3], "condo_3": [1, 1]},
    "Puchong": {"apartment_3": [1, 1]},
    "Klang": {"landed_4": [1, 1]},
    "Bukit Jalil": {"condo_2": [1, 1], "condo_3": [5, 3]},
    "Seri Kembangan": {"condo_2": [3, 2], "condo_3": [2, 2]},
}


def cells(df, key):
    """One dict per stratum: listings, buildings, adjusted median/p25/p75,
    contributing sources and status."""
    if df.empty:
        return []
    df = df.copy()
    df["_bkey"] = [building_key(b) for b in df["building"]]
    out = []
    for values, g in df.groupby(key, dropna=False):
        values = values if isinstance(values, tuple) else (values,)
        price = g["price_adjusted"].astype(float)
        n, b = len(g), int(g["_bkey"].nunique())
        cell = dict(zip(key, values))
        if "bedrooms" in cell:
            cell["bedrooms"] = int(cell["bedrooms"])
        cell.update({
            "listings": n,
            "buildings": b,
            "median": round(float(price.median()), 2),
            "p25": round(float(price.quantile(0.25)), 2),
            "p75": round(float(price.quantile(0.75)), 2),
            "median_raw": round(float(g["price_raw"].astype(float).median()), 2),
            "sources": "+".join(sorted(g["source"].unique())),
            "by_source": {s: int(c) for s, c in g["source"].value_counts().items()},
            "status": stratum_status(n, b),
        })
        out.append(cell)
    return out


def _index(cell_list, key):
    return {tuple(c[k] for k in key): c for c in cell_list}


def target_table(unit_cells):
    """Per target area, the seven required cells before (audit) and after (pooled)."""
    idx = _index(unit_cells, WHOLE_UNIT_KEY)
    rows = []
    for name, area in TARGETS:
        row = {"target": name, "area": area, "cells": {}}
        before_scorable = after_scorable = 0
        for ptype, br in TARGET_CELLS:
            label = f"{ptype}_{br}"
            n0, b0 = AUDIT_BEFORE.get(name, {}).get(label, [0, 0])
            after = idx.get((area, ptype, br))
            n1, b1 = (after["listings"], after["buildings"]) if after else (0, 0)
            before_status, after_status = stratum_status(n0, b0), stratum_status(n1, b1)
            before_scorable += before_status == "scorable"
            after_scorable += after_status == "scorable"
            row["cells"][label] = {
                "before": {"listings": n0, "buildings": b0, "status": before_status},
                "after": {"listings": n1, "buildings": b1, "status": after_status,
                          "median": after["median"] if after else None,
                          "sources": after["sources"] if after else None},
            }
        row["scorable_before"], row["scorable_after"] = before_scorable, after_scorable
        rows.append(row)
    return rows


def room_needs(room_cells, areas):
    """Rows to add per room cell to reach MIN_LISTINGS listings from
    MIN_BUILDINGS buildings, assuming each new row is from a new building."""
    idx = _index(room_cells, ROOM_KEY)
    needs = []
    for area in areas:
        for room_type in ROOM_TYPES:
            cell = idx.get((area, room_type))
            n, b = (cell["listings"], cell["buildings"]) if cell else (0, 0)
            rows = max(MIN_LISTINGS - n, MIN_BUILDINGS - b, 0)
            if rows:
                needs.append({"area": area, "room_type": room_type, "listings": n, "buildings": b,
                              "rows_needed": rows,
                              "new_buildings_needed": max(MIN_BUILDINGS - b, 0)})
    return needs


def report(pooled):
    units = pooled[pooled["property_type"] != "room"]
    rooms = pooled[pooled["property_type"] == "room"]
    unit_cells = cells(units, WHOLE_UNIT_KEY)
    room_cells = cells(rooms, ROOM_KEY)

    target_areas = {area for _, area in TARGETS}
    targets = target_table(unit_cells)
    still_empty = [
        {"target": t["target"], "area": t["area"], "cell": label}
        for t in targets for label, c in t["cells"].items() if c["after"]["status"] == "empty"
    ]
    rooms_empty = [
        {"target": name, "area": area, "room_type": rt}
        for name, area in TARGETS for rt in ROOM_TYPES
        if (area, rt) not in _index(room_cells, ROOM_KEY)
    ]
    outside = sorted({c["area"] for c in unit_cells if c["status"] == "scorable"} - target_areas)
    room_areas = [area for _, area in TARGETS] + sorted({c["area"] for c in room_cells} - target_areas)

    def counts(cell_list):
        return pd.Series([c["status"] for c in cell_list]).value_counts().to_dict() if cell_list else {}

    return {
        "whole_units": {"key": WHOLE_UNIT_KEY, "status_counts": counts(unit_cells), "cells": unit_cells},
        "rooms": {"key": ROOM_KEY, "status_counts": counts(room_cells), "cells": room_cells},
        "targets": targets,
        "scorable_target_cells": {
            "before": sum(t["scorable_before"] for t in targets),
            "after": sum(t["scorable_after"] for t in targets),
            "of": len(TARGETS) * len(TARGET_CELLS),
        },
        "still_empty": {"whole_units": still_empty, "rooms": rooms_empty},
        "new_scorable_areas_outside_targets": [
            {"area": area, "cells": [f"{c['property_type']}_{c['bedrooms']}" for c in unit_cells
                                     if c["area"] == area and c["status"] == "scorable"]}
            for area in outside
        ],
        "manual_room_rows_needed": room_needs(room_cells, room_areas),
    }
