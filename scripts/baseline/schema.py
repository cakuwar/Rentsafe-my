"""The common listing schema every source loader produces, and the stratum rules.

PDPA: a loader keeps these fields and nothing else — no agent names, phone
numbers, emails, listing URLs (PropertyGuru URLs embed the agent's name) or
free-text descriptions.
"""
import pandas as pd

FIELDS = [
    "source",             # kaggle | scraped | manual (later: ieee)
    "source_listing_id",  # the source's own ad / listing ID, for dedupe
    "building",           # development name or street; counts distinct buildings
    "area",               # canonical (scripts/scrapers/config.CANONICAL_AREAS)
    "property_type",      # condo | apartment | flat | landed | room
    "source_subtype",     # the source's own type, e.g. "Flat", "Service Residence"
    "bedrooms",           # 0-4 (0 = studio, 4 = 4+); empty for rooms
    "room_type",          # master | common; rooms only
    "private_bathroom",   # True / False / empty; rooms only, never a stratum key
    "size_sqft",
    "price_raw",          # monthly rent as listed, RM
    "price_adjusted",     # price_raw x the source's time factor (adjust.py)
    "collected_at",       # ISO date the listing was seen, when known
]

PROPERTY_TYPES = ("condo", "apartment", "flat", "landed", "room")
ROOM_TYPES = ("master", "common")
WHOLE_UNIT_KEY = ["area", "property_type", "bedrooms"]
ROOM_KEY = ["area", "room_type"]

# A stratum is scorable with at least this many listings from at least this
# many distinct buildings (the P5 plan's D4): one development must not set a
# district's price.
MIN_LISTINGS = 5
MIN_BUILDINGS = 3


def stratum_status(listings, buildings):
    """scorable | few-bldg | thin | sparse | empty. Only "scorable" is ever scored;
    the rest are reporting labels."""
    if listings >= MIN_LISTINGS and buildings >= MIN_BUILDINGS:
        return "scorable"
    if listings >= MIN_LISTINGS:
        return "few-bldg"
    if listings >= 3:
        return "thin"
    if listings >= 1:
        return "sparse"
    return "empty"


def building_key(name):
    """Case- and punctuation-folded building name; None when unknown."""
    if not isinstance(name, str):
        return None
    key = " ".join("".join(ch if ch.isalnum() else " " for ch in name.lower()).split())
    return key or None


def empty_frame():
    return pd.DataFrame(columns=FIELDS)


def conform(df):
    """Exactly FIELDS, in order; anything a loader added beyond them is dropped."""
    for field in FIELDS:
        if field not in df.columns:
            df[field] = None
    return df[FIELDS].reset_index(drop=True)
