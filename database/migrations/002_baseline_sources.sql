-- Migration 002 — price baseline from several sources, and a room baseline.
-- Mirrors database/schema.sql; keep the two in sync.
--
-- price_baseline is now built by scripts/baseline (Kaggle / Mudah ~2023 prices
-- time-adjusted, our Aug 2026 iProperty / PropertyGuru scrape, manual rows),
-- so each stratum records where its listings came from, the factor applied
-- to the older ones, and their age. Rooms get their own table: they are
-- priced per room and keyed by room type, not bedrooms.

ALTER TABLE price_baseline
    ADD COLUMN IF NOT EXISTS building_count    INTEGER,
    ADD COLUMN IF NOT EXISTS sources           TEXT,          -- 'kaggle+scraped'
    ADD COLUMN IF NOT EXISTS adjustment_factor NUMERIC(6, 4), -- applied to the stratum's time-adjusted rows; NULL if none
    ADD COLUMN IF NOT EXISTS source_vintages   JSONB,         -- {"kaggle": "2023 (inferred)", "scraped": "2026-08-27"}
    ADD COLUMN IF NOT EXISTS status            TEXT;          -- scorable | few-bldg | thin | sparse

CREATE TABLE IF NOT EXISTS room_price_baseline (
    id                     SERIAL PRIMARY KEY,
    area                   TEXT NOT NULL,
    room_type              TEXT NOT NULL CHECK (room_type IN ('master', 'common')),
    median_price           NUMERIC(10, 2) NOT NULL,
    p25_price              NUMERIC(10, 2),
    p75_price              NUMERIC(10, 2),
    sample_size            INTEGER NOT NULL,
    building_count         INTEGER NOT NULL,
    private_bathroom_share REAL,      -- share of listings with a private bathroom; NULL if none recorded
    sources                TEXT,
    adjustment_factor      NUMERIC(6, 4),
    source_vintages        JSONB,
    status                 TEXT,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (area, room_type)
);

-- The per-listing audit table (also in schema.sql) and the scraper's new fields.
CREATE TABLE IF NOT EXISTS scraped_listings (
    id                SERIAL PRIMARY KEY,
    title             TEXT,
    price_myr         NUMERIC(10, 2),
    area              TEXT,
    state             TEXT,
    bedrooms          INTEGER,
    is_studio         BOOLEAN DEFAULT FALSE,
    bathrooms         INTEGER,
    property_type     TEXT,
    size_sqft         NUMERIC(10, 2),
    furnishing        TEXT,
    listing_url       TEXT NOT NULL,
    source            TEXT,
    scraped_at        TIMESTAMPTZ,
    area_needs_review BOOLEAN DEFAULT FALSE,
    UNIQUE (listing_url)
);

ALTER TABLE scraped_listings
    ADD COLUMN IF NOT EXISTS portal_listing_id TEXT,
    ADD COLUMN IF NOT EXISTS property_subtype  TEXT,
    ADD COLUMN IF NOT EXISTS room_type         TEXT,
    ADD COLUMN IF NOT EXISTS max_tenants       INTEGER,
    ADD COLUMN IF NOT EXISTS tenant_gender     TEXT;
