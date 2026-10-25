"""Source registry. Adding a source = one loader module + one entry here.

A loader is `load(source, log) -> (DataFrame in schema.FIELDS plus internal
"_" columns, info dict)`. It maps the source onto the common schema and drops
only what is source-specific (an unmappable area, an unknown type); the shared
rules in cleaning.py run afterwards.
"""
from dataclasses import dataclass
from typing import Callable

from . import kaggle, manual, scraped


@dataclass(frozen=True)
class Source:
    name: str
    path: str                 # relative to the repo root
    origin: str
    license: str | None       # None = not verified
    collected_at: str | None  # None = not stated by the source
    collected_at_note: str
    time_adjusted: bool       # prices scaled by adjust.py's factor
    priority: int             # cross-source dedupe: the lower number wins
    loader: Callable
    dedupe_unit_key: bool = False  # one row per building+price+size+area+bedrooms
    vintage: str | None = None     # data-age label when rows carry no date


REGISTRY = {
    source.name: source
    for source in (
        Source(
            name="manual",
            path="data/raw/manual/manual_price_entry.xlsx",
            origin="room and studio listings recorded by hand while browsing (Rooms and Studios sheets)",
            license="own records",
            collected_at=None,
            collected_at_note="per row: date_seen",
            time_adjusted=False,
            priority=0,
            loader=manual.load,
        ),
        Source(
            name="scraped",
            path="data/raw/baseline",
            origin="iproperty.com.my, propertyguru.com.my search pages (scripts/scrapers)",
            license="scraped asking prices; terms of use not verified",
            collected_at="2026-08-27",
            collected_at_note="per row: scraped_at",
            time_adjusted=False,
            priority=1,
            loader=scraped.load,
        ),
        Source(
            name="kaggle",
            path="data/price/mudah-apartment-kl-selangor.csv",
            origin="Kaggle ariewijaya/rent-pricing-kuala-lumpur-malaysia, scraped from mudah.my",
            license=None,
            collected_at=None,
            collected_at_note="not in the file; inferred 2023 or later (192 rows in "
                              "buildings completed 2023, 10 in 2024) — confirm on the Kaggle page",
            time_adjusted=True,
            priority=2,
            loader=kaggle.load,
            dedupe_unit_key=True,
            vintage="2023 (inferred)",
        ),
    )
}
