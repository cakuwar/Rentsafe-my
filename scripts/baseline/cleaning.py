"""Cleaning rules shared by every source, with a count per drop reason.

Order: dedupe within the source, then price rules, then structure. Cross-source
dedupe runs once every source is clean (dedupe_across).
"""
from collections import Counter, defaultdict

import pandas as pd

from .schema import ROOM_TYPES, building_key

PRICE_MIN, PRICE_MAX = 100, 100_000   # RM / month, the outer bounds

# A monthly whole-unit rent below RM300 in KL / Selangor is a per-day or
# per-week price, a room, or a placeholder: in the Kaggle data a 1,500 sq ft
# 4BR at RM100 and a 3BR at RM120. Rooms are exempt (a shared room can be RM300).
WHOLE_UNIT_MIN_PRICE = 300
# RM per sq ft per month. Measured on Kaggle: median 1.62, 99.5th percentile
# 5.26. Above 12 the "rent" is a sale price or a typo (RM45,000 for a 603 sq ft
# flat; RM12,500 for a 750 sq ft Empire Damansara unit); below 0.30 it is
# per-day or a placeholder. Applied only when the size itself is plausible.
# Not 10: real KLCC luxury rents reach 11.5 (TRX Residences RM14,000 for
# 1,216 sq ft; Sofitel Residences RM13,800). Known miss: a Kajang 3BR "rent" of
# RM12,000 (11.5/sq ft) stays in; a single outlier does not move a median.
SALE_MIN_PSF = 12
PER_DAY_MAX_PSF = 0.30
# A size outside this is a data-entry error (1 sq ft; 100,000,000 sq ft): the
# size is emptied, the listing kept.
SIZE_MIN, SIZE_MAX = 200, 10_000


class DropLog:
    """Rows in, rows out and a count per reason, per source."""

    def __init__(self):
        self.rows_in = Counter()
        self.drops = defaultdict(Counter)
        self.notes = defaultdict(Counter)

    def drop(self, df, mask, source, reason):
        mask = mask.fillna(False).astype(bool)
        n = int(mask.sum())
        if n:
            self.drops[source][reason] += n
        return df[~mask]

    def note(self, source, key, n=1):
        if n:
            self.notes[source][key] += int(n)

    def summary(self, rows_out):
        return {
            source: {
                "rows_in": self.rows_in[source],
                "rows_out": rows_out.get(source, 0),
                "dropped": dict(self.drops[source].most_common()),
                "notes": dict(self.notes[source].most_common()),
            }
            for source in self.rows_in
        }


def clean(df, source, log, dedupe_unit_key=False):
    """Apply the shared rules to one source's listings (common schema plus the
    internal `_studio_confirmed` column). `dedupe_unit_key` also collapses
    repeats of one unit under different listing IDs (Kaggle)."""
    df = df.copy()
    df = log.drop(df, df["source_listing_id"].notna() & df.duplicated("source_listing_id"),
                  source, "duplicate_listing_id")

    df["price_raw"] = pd.to_numeric(df["price_raw"], errors="coerce")
    df = log.drop(df, df["price_raw"].isna(), source, "missing_price")
    df = log.drop(df, (df["price_raw"] < PRICE_MIN) | (df["price_raw"] > PRICE_MAX),
                  source, "price_outside_RM100_100000")

    df["size_sqft"] = pd.to_numeric(df["size_sqft"], errors="coerce")
    bad_size = df["size_sqft"].notna() & ((df["size_sqft"] < SIZE_MIN) | (df["size_sqft"] > SIZE_MAX))
    log.note(source, "size_implausible_set_empty", bad_size.sum())
    df.loc[bad_size, "size_sqft"] = None

    psf = df["price_raw"] / df["size_sqft"]
    whole = df["property_type"] != "room"
    df = log.drop(df, psf > SALE_MIN_PSF, source, "looks_like_sale_price")
    psf = df["price_raw"] / df["size_sqft"]
    whole = df["property_type"] != "room"
    df = log.drop(df, whole & ((df["price_raw"] < WHOLE_UNIT_MIN_PRICE) | (psf < PER_DAY_MAX_PSF)),
                  source, "looks_like_per_day_or_week")

    whole = df["property_type"] != "room"
    df["bedrooms"] = pd.to_numeric(df["bedrooms"], errors="coerce")
    df = log.drop(df, whole & df["bedrooms"].isna(), source, "missing_bedrooms")
    over = df["bedrooms"] > 4
    log.note(source, "bedrooms_5plus_bucketed_to_4", over.sum())
    df.loc[over, "bedrooms"] = 4

    # 0 bedrooms with no size and nothing saying "studio" was how room
    # rentals hid in the scrape; it is never assumed to be a studio.
    studio = df.get("_studio_confirmed", pd.Series(False, index=df.index)).eq(True)
    df = log.drop(df, (df["property_type"] == "condo") & (df["bedrooms"] == 0)
                  & df["size_sqft"].isna() & ~studio, source, "zero_bedroom_no_size_unconfirmed")

    rooms = df["property_type"] == "room"
    df = log.drop(df, rooms & ~df["room_type"].isin(ROOM_TYPES), source, "room_type_unknown")
    df.loc[df["property_type"] == "room", "bedrooms"] = None

    # DECISION (author, 2026-10-15) — Kaggle: one listing per building + price
    # + size + area + bedrooms. 30% of its rows repeated another row's unit
    # under a different ad ID: an agent re-posting a unit counts it several
    # times and narrows the spread around its price. Only rows with a known
    # building and size are grouped.
    if dedupe_unit_key:
        key = pd.DataFrame({"b": [building_key(b) for b in df["building"]], "p": df["price_raw"],
                            "s": df["size_sqft"], "a": df["area"], "r": df["bedrooms"]}, index=df.index)
        complete = key["b"].notna() & key["s"].notna()
        df = log.drop(df, complete & key.duplicated(), source, "duplicate_unit_key")
    return df


def dedupe_across(frames, log):
    """Drop a listing already present in a higher-priority source, matched on
    building + price + size + area (sources share no listing IDs). `frames` is
    a list of (source, df) in priority order: the fresher source wins.

    Matching is one-to-one: a listing can duplicate one other listing, not
    every identical unit. Matching against a set removed eight Laguna Biru
    rows (850 sq ft, RM800, Rawang) for one scraped listing."""
    seen = Counter()
    out = []
    for source, df in frames:
        keys = [
            (building_key(b), float(p), round(float(s)), a)
            if building_key(b) and pd.notna(s) else None
            for b, p, s, a in zip(df["building"], df["price_raw"], df["size_sqft"], df["area"])
        ]
        available = seen.copy()
        dup = []
        for k in keys:
            hit = k is not None and available[k] > 0
            if hit:
                available[k] -= 1
            dup.append(hit)
        out.append((source, log.drop(df, pd.Series(dup, index=df.index), source,
                                     "duplicate_across_sources")))
        seen.update(k for k, d in zip(keys, dup) if k is not None and not d)
    return out
