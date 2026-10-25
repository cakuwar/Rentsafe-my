# RentSafe MY — price-baseline scrapers

Scrapes the raw listings that `scripts/baseline` pools with the other sources
(Kaggle, manual rooms) into the `price_baseline` / `room_price_baseline` seeds
from real KL/Selangor rental listings, stratified by `(area, bedrooms,
property_type)`. Academic-use, rate-limited, single-threaded.

## Status per site

| Site | Status | Notes |
| --- | --- | --- |
| **iProperty** | ✅ working | `/property-for-rent` search pages embed full listing data as JSON (`__NEXT_DATA__`), so one page fetch = ~20 listings with no per-listing requests needed. |
| **PropertyGuru** | ✅ working | Same underlying platform as iProperty; identical JSON shape. Rate-limits more aggressively — expect occasional early stops around page 8–10, which is by design (see Etiquette below). |
| **Mudah.my** | ❌ disabled on purpose | `robots.txt` states: *"It is expressly forbidden to use spiders or other automated methods to access mudah.my. Only if mudah.my has given special permit such access is allowed."* `mudah.py` makes zero HTTP requests and exists only as a documented stub. If the project obtains written permission from Mudah, a real implementation can be added following the same pattern as `iproperty.py`. |

## Setup

```bash
pip install -r scripts/requirements.txt
```

Playwright is a listed dependency for future JS-rendered pages, but neither
working scraper currently needs it — both read data straight out of
server-rendered HTML. Do **not** run `playwright install`; if a future site
needs rendering, launch Chromium via
`executable_path='/opt/pw-browsers/chromium'` (see `base.py:fetch_rendered`).

## Usage

```bash
# 1. Scrape (writes data/raw/baseline/<site>_<timestamp>.csv)
python -m scripts.scrapers.run_scraper --site iproperty --pages 15
python -m scripts.scrapers.run_scraper --site propertyguru --pages 15

# 2. Aggregate every raw CSV into the baseline seed
python -m scripts.scrapers.aggregate_baseline   # scrape-only strata CSV (legacy)

# 3. Pool every source and write the seeds (database/seeds/001 and 003)
nlp-service/.venv/Scripts/python -m scripts.baseline.build
```

`aggregate_baseline.py` writes:
- `data/processed/price_baseline.csv` — the aggregated strata (sample_size >= 3 only)
- a scrape-only SQL seed only with `--sql-out PATH` (the real seed now comes from
  `scripts/baseline/build.py`)
- `data/processed/price_baseline_needs_review.csv` — raw listings whose area
  string didn't confidently map onto the canonical `KL_SEL_AREAS` list (e.g.
  "KL City Centre", "Mont Kiara", "Seri Kembangan"). These are **excluded**
  from the SQL seed because the app looks up `price_baseline.area` by the
  canonical list — an unmapped area would just be dead data. Add an alias to
  `config.AREA_ALIASES` and re-run `aggregate_baseline.py` to reclaim them.

Run tests with:

```bash
python tests/test_normalize.py -v
```

## Scraping etiquette (built in, not optional)

- **robots.txt is a hard gate.** `base.py` fetches each site's `robots.txt`
  itself (with the same browser-like UA as everything else — `urllib.robotparser`'s
  own fetcher uses a bare `Python-urllib/x.y` UA that gets 403'd by these
  sites' anti-bot fronts, which would otherwise make it fail closed and
  report the whole site as blocked) and refuses to fetch any disallowed path.
- **Rate limiting**: randomised 3–6s delay between every request, one request
  in flight at a time, one site at a time.
- **Identification**: the User-Agent string includes an academic-research
  contact note so a site operator reviewing logs can reach out.
- **Retry/backoff**: `tenacity`-based exponential backoff, max 3 attempts; a
  persistent 403/429/5xx causes the scraper to log and stop cleanly rather
  than hammer the site (this happened live against PropertyGuru during
  development — it backed off correctly).
- **Caching**: every fetched page is cached to `data/raw/baseline/_cache/<hash>.html`,
  so re-running a scraper (e.g. after fixing a parsing bug) replays from disk
  instead of re-hitting the site.
- **Volume cap**: `--pages` bounds each run; keep it modest.
- **Dedup**: rows are deduped by `listing_url`, both within a single scrape
  and again across CSVs in `aggregate_baseline.py`.

## Legal/ToS caveat

Automated access sits in a gray area even when `robots.txt` is technically
permissive — respecting `robots.txt` and rate limits reduces but does not
eliminate ToS risk. This tooling is intended for modest, one-off academic
dataset construction (an FYP price baseline), not continuous or
high-volume harvesting. Re-check each site's current `robots.txt` and Terms
of Service before any future run, since both can change.
