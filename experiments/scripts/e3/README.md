# E3 setup: price baseline with and without the scraped listings

Everything runs in working copies outside the repo: `~/rentsafe_experiments_data/e3_price/`. Nothing writes to the repo's data, seeds or database.

1. Make two identical copies, `full/` and `no_scraped/`, each with the repo layout. Each copy contains:
   - `scripts/` (the baseline build and its scrapers config)
   - `data/raw/baseline/` (scraped CSVs and `_cache/`) and `data/raw/manual/manual_price_entry.xlsx`
   - `data/price/mudah-apartment-kl-selangor.csv`
   - from `backend/`: `package.json`, `scripts/{price_loo_eval.js,csv.js,strata.js}`, `src/services/{price.service.js,metadata.service.js}`, `src/config/{index.js,areas.js}` and `src/utils/logger.js`
   - `backend/src/db/pool.js` replaced by `pool_stub.js`, so the scorer can never reach PostgreSQL
   - empty `data/processed/` and `database/seeds/`
2. **Current baseline:** in `full/`, run
   `python -E -s -B -X utf8 -m scripts.baseline.build`, then `cd backend && node scripts/price_loo_eval.js`.
   This must reproduce the repo's `baseline_listings.csv` and seed files byte for byte.
3. **Without the scrape:** copy `run_no_scraped.py` into `no_scraped/` and run it there with the same flags, then the leave-one-out as in step 2.
4. **Blind cases:** `node experiments/scripts/e3/rescore_blind.mjs` re-scores cases 3, 4, 5, 12 and 14 against both builds. It writes `experiments/results/e3/rescore_blind.json`.

The Python used was the nlp-service venv (pandas and openpyxl), with nothing installed into it. Node 24.
