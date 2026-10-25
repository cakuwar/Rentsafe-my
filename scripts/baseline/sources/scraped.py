"""Our own iProperty / PropertyGuru scrape (data/raw/baseline/*.csv, Aug 2026).

The CSVs predate the room-type parser fix, so rooms in them look like
0-bedroom condos. Room type, tenants and the portal's own subtype are re-read
from the page cache with the fixed parser (scripts/scrapers/next_data.py) —
no network access. The listing URL is used here for dedupe and then dropped:
PropertyGuru URLs carry the agent's name.
"""
import glob
import os
import re

import pandas as pd

from scripts.scrapers import config, next_data
from scripts.scrapers.normalize import normalize_property_type, normalize_room_type

from ..areas import refine_scraped_area

_LISTING_ID = re.compile(r"(\d{6,})/?$")


def _cached_cards():
    """listing_url -> the fixed parser's row, for every card in the page cache."""
    cards = {}
    for path in glob.glob(os.path.join(config.CACHE_DIR, "*.html")):
        with open(path, encoding="utf-8", errors="ignore") as f:
            data = next_data.extract_next_data(f.read())
        for ld in next_data.listings_from_next_data(data):
            for base in (config.SITE_BASE_URLS["iproperty"], config.SITE_BASE_URLS["propertyguru"]):
                row = next_data.row_from_listing_data(ld, base)
                cards.setdefault(row["listing_url"], row)
    return cards


def load(source, log):
    paths = sorted(glob.glob(os.path.join(config.ROOT, source.path, "*.csv")))
    # mudah_*.csv is header-only: that scraper is disabled by design.
    frames = [f for f in (pd.read_csv(p) for p in paths if os.path.getsize(p) > 0) if not f.empty]
    raw = pd.concat(frames, ignore_index=True)
    log.rows_in[source.name] = len(raw)

    # iProperty first, so a listing posted on both sites keeps the iProperty
    # row: its URL carries the district slug the area refinement reads.
    raw = raw.sort_values("source", key=lambda s: s != "iproperty", kind="stable")
    raw = log.drop(raw, raw.duplicated("listing_url"), source.name, "duplicate_url")

    cards = _cached_cards()
    card = [cards.get(url, {}) for url in raw["listing_url"]]
    room_type = [normalize_room_type(c.get("room_type")) for c in card]
    log.note(source.name, "room_type_read_from_cache", sum(r is not None for r in room_type))
    log.note(source.name, "not_found_in_cache", sum(not c for c in card))

    bedrooms = pd.to_numeric(raw["bedrooms"], errors="coerce")
    studio = raw["is_studio"].astype(str).eq("True") | raw["property_type"].eq("studio") | (bedrooms < 0)
    bedrooms[studio] = 0
    ptype = raw["property_type"].replace({"studio": "condo"})
    # The CSVs predate the flat type: a "Flat" subtype was written as apartment.
    subtype = [c.get("property_subtype") for c in card]
    ptype = pd.Series([("room" if r else "flat" if normalize_property_type(st) == "flat" else p)
                       for r, st, p in zip(room_type, subtype, ptype)], index=raw.index)

    df = pd.DataFrame({
        "source": source.name,
        "source_listing_id": raw["listing_url"].str.extract(_LISTING_ID)[0],
        "building": raw["title"].fillna("").str.split(",").str[0]
                       .str.replace(r"\s*\(.*\)", "", regex=True).str.strip().replace("", None),
        "area": [refine_scraped_area(t, u, a, s) for t, u, a, s in
                 zip(raw["title"], raw["listing_url"], raw["area"], raw["state"])],
        "property_type": ptype,
        "source_subtype": subtype,
        "bedrooms": bedrooms,
        "room_type": room_type,
        "private_bathroom": None,  # the room cards carry no usable bathroom flag
        "size_sqft": raw["size_sqft"],
        "price_raw": raw["price_myr"],
        "price_adjusted": None,
        "collected_at": raw["scraped_at"].astype(str).str[:10],
        "_studio_confirmed": studio,
    }, index=raw.index)

    unmapped = df.loc[df["area"].isna()]
    info = {
        "files": [os.path.relpath(p, config.ROOT).replace("\\", "/") for p in paths],
        "unmapped_areas": raw.loc[unmapped.index, "area"].value_counts().to_dict(),
    }
    df = log.drop(df, df["area"].isna(), source.name, "unmapped_area")
    df = log.drop(df, df["property_type"].isna(), source.name, "unknown_type")
    return df, info
