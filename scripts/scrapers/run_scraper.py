"""CLI entry point for the RentSafe MY price-baseline scrapers.

Usage:
    python -m scripts.scrapers.run_scraper --site iproperty --pages 20
    python -m scripts.scrapers.run_scraper --site propertyguru --pages 10 --out data/raw/baseline
    python -m scripts.scrapers.run_scraper --site mudah --pages 5   # refuses — see mudah.py

Scrapes up to --pages search-result pages from --site, applies the
area/property-type normalisation and price sanity filter (normalize.py), and
writes one row per surviving listing to
<out>/<site>_<YYYYMMDD_HHMMSS>.csv
"""
import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.scrapers import config
from scripts.scrapers.normalize import normalize_row
from scripts.scrapers.mudah import MudahScraper
from scripts.scrapers.iproperty import IPropertyScraper
from scripts.scrapers.propertyguru import PropertyGuruScraper

SCRAPERS = {
    "mudah": MudahScraper,
    "iproperty": IPropertyScraper,
    "propertyguru": PropertyGuruScraper,
}

CSV_FIELDS = [
    "title", "price_myr", "area", "state", "bedrooms", "is_studio",
    "bathrooms", "property_type", "property_subtype", "size_sqft", "furnishing",
    "room_type", "max_tenants", "tenant_gender", "portal_listing_id",
    "listing_url", "source", "scraped_at", "area_needs_review",
]


def run(site, pages, out_dir):
    scraper_cls = SCRAPERS[site]
    scraper = scraper_cls(out_dir=out_dir)

    raw_rows = scraper.scrape(max_pages=pages)

    rows = []
    dropped = 0
    for raw_row in raw_rows:
        row = normalize_row(dict(raw_row))
        if row is None:
            dropped += 1
            continue
        rows.append(row)

    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"{site}_{timestamp}.csv")

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"[{site}] scraped {len(raw_rows)} raw listing(s), "
          f"kept {len(rows)} after normalisation ({dropped} dropped)")
    print(f"[{site}] wrote {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site", required=True, choices=sorted(SCRAPERS.keys()))
    parser.add_argument("--pages", type=int, default=5, help="max search-result pages to crawl (default: 5)")
    parser.add_argument("--out", default=config.DATA_RAW_BASELINE, help="output directory for the raw CSV")
    args = parser.parse_args()

    run(args.site, args.pages, args.out)


if __name__ == "__main__":
    main()
