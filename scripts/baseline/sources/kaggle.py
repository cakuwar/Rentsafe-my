"""Kaggle ariewijaya/rent-pricing-kuala-lumpur-malaysia (mudah-apartment-kl-selangor.csv).

Columns: ads_id, prop_name, completion_year, monthly_rent ("RM 4 200 per
month"), location ("Kuala Lumpur - Taman Desa"), property_type, rooms,
parking, bathroom, size ("1842 sq.ft."), furnished, facilities,
additional_facilities, region. None of them identifies a person; only the
fields in schema.FIELDS are kept.
"""
import os
import re
from collections import Counter

import pandas as pd

from scripts.scrapers import config

from ..areas import resolve

# Mudah's types onto ours. Studio is a condo with 0 bedrooms (the file gives
# studios rooms = 1). Flat is its own type (config.PROPERTY_TYPES decision);
# Service Residence stays condo.
TYPE_MAP = {
    "Condominium": "condo",
    "Service Residence": "condo",
    "Duplex": "condo",
    "Soho": "condo",
    "Townhouse Condo": "condo",
    "Condo / Services residence / Penthouse / Townhouse": "condo",
    "Studio": "condo",
    "Apartment": "apartment",
    "Flat": "flat",
    "Bungalow House": "landed",
    "Houses": "landed",
}

# The file has no description column: rooms can only be spotted by name.
ROOM_WORDS = re.compile(
    r"\b(?:master room|common room|middle room|single room|medium room|"
    r"room for rent|room stay|bilik|\d+\s*pax)\b", re.I)


def load(source, log):
    raw = pd.read_csv(os.path.join(config.ROOT, source.path))
    log.rows_in[source.name] = len(raw)

    locality = raw["location"].astype(str).str.split(" - ", n=1).str[1].fillna("")
    area = [resolve(loc, region) for loc, region in zip(locality, raw["region"])]

    is_room = raw["prop_name"].fillna("").str.contains(ROOM_WORDS)
    ptype = raw["property_type"].map(TYPE_MAP)
    ptype[is_room] = "room"

    rooms = raw["rooms"].astype(str).str.replace("More than 10", "11", regex=False)
    bedrooms = pd.to_numeric(rooms, errors="coerce")
    studio = raw["property_type"] == "Studio"
    bedrooms[studio] = 0

    df = pd.DataFrame({
        "source": source.name,
        "source_listing_id": raw["ads_id"].astype(str),
        "building": raw["prop_name"].where(raw["prop_name"].notna(), None),
        "area": area,
        "property_type": ptype,
        "source_subtype": raw["property_type"],
        "bedrooms": bedrooms,
        "room_type": None,  # the one room in the file names no type
        "private_bathroom": None,
        "size_sqft": pd.to_numeric(raw["size"].astype(str).str.extract(r"([\d.,]+)")[0]
                                   .str.replace(",", ""), errors="coerce"),
        "price_raw": pd.to_numeric(raw["monthly_rent"].astype(str).str.replace(r"[^\d]", "", regex=True),
                                   errors="coerce"),
        "price_adjusted": None,
        "collected_at": source.collected_at,
        "_studio_confirmed": studio,
    })

    unmapped = Counter(f"{region} - {loc}" for loc, region, a in zip(locality, raw["region"], area) if a is None)
    df = log.drop(df, df["area"].isna(), source.name, "unmapped_area")
    df = log.drop(df, df["property_type"].isna(), source.name, "unknown_type")


    info = {
        "file": source.path,
        "columns": list(raw.columns),
        "rows": len(raw),
        "unmapped_areas": dict(unmapped.most_common()),
        "rooms_found": dict(Counter(zip(df.loc[df["property_type"] == "room", "area"],
                                        df.loc[df["property_type"] == "room", "building"]))),
        "subtype_counts": dict(Counter(raw["property_type"]).most_common()),
    }
    info["rooms_found"] = [{"area": a, "building": b, "count": n} for (a, b), n in info["rooms_found"].items()]
    return df, info
