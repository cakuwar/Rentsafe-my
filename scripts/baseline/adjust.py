"""Time adjustment between an older external source and our Aug 2026 scrape.

factor = median, over whole-unit strata scorable in BOTH sources, of
(scraped median / external median), on raw prices. It is applied only when at
least MIN_STRATA strata support it; otherwise prices stay unadjusted and the
fallbacks are reported for a decision. Rooms are never used to estimate it.
"""
import statistics

import pandas as pd

from .schema import MIN_BUILDINGS, MIN_LISTINGS, WHOLE_UNIT_KEY, building_key, stratum_status

MIN_STRATA = 3

# Which estimate becomes price_adjusted; both are always reported.
#
# DECISION (author, 2026-10-15) — building_matched (same building and bedroom
# count in both sources). The stratum median gave 1.86 over 14 strata with
# ratios from 1.05 to 3.24: in KLCC and Mont Kiara the scrape is mostly luxury
# towers, so the ratio measured which buildings each source held, not the
# year. Applied, it lifted the Kajang 3BR condo median from RM1,200 to RM2,236.
# Either estimate still mixes time with platform (Mudah vs iProperty asking
# prices); this data cannot separate the two.
METHOD = "building_matched"
MIN_PAIRS = 3

FALLBACKS = [
    "a published Malaysian rent index (e.g. NAPIC rental data or DOSM CPI 'actual rentals "
    "for housing') between the Kaggle collection date and Aug 2026",
    "relax to >= 3 listings per stratum (both sources) for estimating the factor only; "
    "scoring eligibility stays at >= 5 listings / >= 3 buildings",
    "no adjustment: use Kaggle prices as listed and state the data age as a limitation",
]

CAVEATS = [
    "The ratio mixes time and platform: Kaggle is Mudah asking prices, the scrape is "
    "iProperty / PropertyGuru asking prices, which skew to agent-listed and higher-end "
    "units. This data cannot separate the two effects.",
    "The overlap strata are all condo strata in KL / Selangor districts the scrape happened "
    "to reach; the factor is assumed to hold for apartments and other areas.",
]


def stratum_stats(df):
    """Per whole-unit stratum: listings, distinct buildings, median raw price."""
    units = df[df["property_type"] != "room"].copy()
    units["_bkey"] = [building_key(b) for b in units["building"]]
    grouped = units.groupby(WHOLE_UNIT_KEY, dropna=False)
    return pd.DataFrame({
        "listings": grouped.size(),
        "buildings": grouped["_bkey"].nunique(),
        "median": grouped["price_raw"].median(),
    }).reset_index()


def building_matched(external, reference):
    """Median ratio over (building, bedrooms) pairs present in both sources.

    Controls for which buildings each source happened to contain, which the
    stratum median does not: in KLCC / Mont Kiara the scrape is mostly luxury
    towers, so a stratum ratio there measures the mix, not the year."""
    def grouped(df):
        units = df[df["property_type"] != "room"].copy()
        units["_bkey"] = [building_key(b) for b in units["building"]]
        units = units[units["_bkey"].notna()]
        return units.groupby(["_bkey", "bedrooms"])["price_raw"].agg(["count", "median"])

    pairs = grouped(external).join(grouped(reference), lsuffix="_ext", rsuffix="_ref", how="inner")
    pairs["ratio"] = pairs["median_ref"] / pairs["median_ext"]
    strict = pairs[(pairs["count_ext"] >= 3) & (pairs["count_ref"] >= 2)]

    def summary(p):
        if len(p) < MIN_PAIRS:
            return {"pairs": len(p), "factor": None}
        return {"pairs": len(p), "factor": round(float(p["ratio"].median()), 4),
                "iqr": [round(float(p["ratio"].quantile(0.25)), 4),
                        round(float(p["ratio"].quantile(0.75)), 4)],
                "min_ratio": round(float(p["ratio"].min()), 4),
                "max_ratio": round(float(p["ratio"].max()), 4)}

    return {
        "method": "median over (building, bedrooms) pairs listed in both sources of "
                  "reference median / external median, raw prices",
        "all_pairs": summary(pairs),
        "pairs_with_3plus_external_2plus_reference": summary(strict),
    }


def compute(external, reference, external_name="kaggle", reference_name="scraped"):
    ext, ref = stratum_stats(external), stratum_stats(reference)
    both = ext.merge(ref, on=WHOLE_UNIT_KEY, suffixes=("_ext", "_ref"))
    scorable = (
        (both["listings_ext"] >= MIN_LISTINGS) & (both["buildings_ext"] >= MIN_BUILDINGS)
        & (both["listings_ref"] >= MIN_LISTINGS) & (both["buildings_ref"] >= MIN_BUILDINGS)
    )
    both = both[scorable].copy()
    both["ratio"] = both["median_ref"] / both["median_ext"]

    strata = [
        {
            "area": row.area, "property_type": row.property_type, "bedrooms": int(row.bedrooms),
            external_name: {"listings": int(row.listings_ext), "buildings": int(row.buildings_ext),
                            "median": float(row.median_ext)},
            reference_name: {"listings": int(row.listings_ref), "buildings": int(row.buildings_ref),
                             "median": float(row.median_ref)},
            "ratio": round(float(row.ratio), 4),
        }
        for row in both.sort_values("ratio").itertuples()
    ]
    ratios = [s["ratio"] for s in strata]
    enough = len(ratios) >= MIN_STRATA

    # Near misses, so the decision on a fallback can see what relaxing would add.
    near = ext.merge(ref, on=WHOLE_UNIT_KEY, suffixes=("_ext", "_ref"))
    near = near[(near["listings_ext"] >= 3) & (near["listings_ref"] >= 3)]
    near_misses = [
        {"area": r.area, "property_type": r.property_type, "bedrooms": int(r.bedrooms),
         "status": {external_name: stratum_status(int(r.listings_ext), int(r.buildings_ext)),
                    reference_name: stratum_status(int(r.listings_ref), int(r.buildings_ref))},
         "listings": {external_name: int(r.listings_ext), reference_name: int(r.listings_ref)},
         "ratio": round(float(r.median_ref / r.median_ext), 4)}
        for r in near.itertuples()
        if not ((r.listings_ext >= MIN_LISTINGS) and (r.buildings_ext >= MIN_BUILDINGS)
                and (r.listings_ref >= MIN_LISTINGS) and (r.buildings_ref >= MIN_BUILDINGS))
    ]

    stratum_factor = round(statistics.median(ratios), 4) if enough else None
    matched = building_matched(external, reference)
    factor = stratum_factor if METHOD == "stratum_median" else matched["all_pairs"]["factor"]
    return {
        "method": f"median over strata scorable in both sources (>= {MIN_LISTINGS} listings, "
                  f">= {MIN_BUILDINGS} buildings each) of {reference_name} median / {external_name} "
                  "median, raw prices",
        "external": external_name,
        "reference": reference_name,
        "strata_used": len(strata),
        "min_strata": MIN_STRATA,
        "stratum_median_factor": stratum_factor,
        "spread": {"min_ratio": min(ratios), "max_ratio": max(ratios)} if ratios else None,
        "building_matched": matched,
        "applied_method": METHOD,
        "factor": factor,
        "applied": factor is not None,
        "status": "applied" if factor is not None else "insufficient_overlap",
        "strata": strata,
        "near_misses": near_misses,
        "caveats": CAVEATS,
        "fallbacks": [] if factor is not None else FALLBACKS,
    }


def apply(df, factor, adjusted_sources):
    """price_adjusted = price_raw x factor for the adjusted sources, else price_raw."""
    df = df.copy()
    scale = df["source"].isin(adjusted_sources) & (factor is not None)
    df["price_adjusted"] = df["price_raw"].astype(float)
    if factor is not None:
        df.loc[scale, "price_adjusted"] = (df.loc[scale, "price_raw"] * factor).round(2)
    return df
