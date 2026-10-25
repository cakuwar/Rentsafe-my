-- RentSafe MY — full database schema (PostgreSQL 15)
-- Five primary tables per Chapter 4.4 of the research document.
-- This file is auto-run by docker-compose on first DB boot.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. listings ---------------------------------------------------------------
-- User-submitted listings + parsed metadata + computed result.
CREATE TABLE IF NOT EXISTS listings (
    listing_id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_text         TEXT NOT NULL,
    source_type      TEXT NOT NULL CHECK (source_type IN ('text', 'screenshot')),
    agent_name       TEXT,
    agent_phone      TEXT,
    ren_number       TEXT,
    company_name     TEXT,
    price            NUMERIC(10, 2),
    area             TEXT,
    bedrooms         INTEGER,
    property_type    TEXT,
    risk_score       INTEGER CHECK (risk_score BETWEEN 0 AND 100),
    risk_band        TEXT CHECK (risk_band IN ('LOW','MODERATE','HIGH','CRITICAL')),
    component_scores JSONB,
    narrative        TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_listings_phone ON listings (agent_phone);
CREATE INDEX IF NOT EXISTS idx_listings_created ON listings (created_at);

-- 2. price_baseline ---------------------------------------------------------
-- Stratified KL/Selangor rent baseline (area + bedrooms + property_type),
-- built by scripts/baseline from several sources (migration 002).
CREATE TABLE IF NOT EXISTS price_baseline (
    id                SERIAL PRIMARY KEY,
    area              TEXT NOT NULL,
    bedrooms          INTEGER,
    property_type     TEXT,
    median_price      NUMERIC(10, 2) NOT NULL,
    p25_price         NUMERIC(10, 2),
    p75_price         NUMERIC(10, 2),
    sample_size       INTEGER DEFAULT 0,
    source            TEXT,
    building_count    INTEGER,
    sources           TEXT,          -- 'kaggle+scraped'
    adjustment_factor NUMERIC(6, 4), -- applied to the stratum's time-adjusted rows; NULL if none
    source_vintages   JSONB,         -- {"kaggle": "2023 (inferred)", "scraped": "2026-08-27"}
    status            TEXT,          -- scorable | few-bldg | thin | sparse
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (area, bedrooms, property_type)
);

-- 2a. room_price_baseline ---------------------------------------------------
-- Room rentals, per room: area + room_type (master | common).
CREATE TABLE IF NOT EXISTS room_price_baseline (
    id                     SERIAL PRIMARY KEY,
    area                   TEXT NOT NULL,
    room_type              TEXT NOT NULL CHECK (room_type IN ('master', 'common')),
    median_price           NUMERIC(10, 2) NOT NULL,
    p25_price              NUMERIC(10, 2),
    p75_price              NUMERIC(10, 2),
    sample_size            INTEGER NOT NULL,
    building_count         INTEGER NOT NULL,
    private_bathroom_share REAL,
    sources                TEXT,
    adjustment_factor      NUMERIC(6, 4),
    source_vintages        JSONB,
    status                 TEXT,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (area, room_type)
);

-- 2b. scraped_listings --------------------------------------------------
-- Per-listing raw output of scripts/scrapers/run_scraper.py (post
-- normalize.py filtering), kept as an audit trail of what price_baseline
-- was aggregated from. See database/seeds/script_data.sql.
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
    portal_listing_id TEXT,
    property_subtype  TEXT,
    room_type         TEXT,
    max_tenants       INTEGER,
    tenant_gender     TEXT,
    UNIQUE (listing_url)
);

-- 3. red_flag_lexicon -------------------------------------------------------
-- Bilingual red-flag phrases used by Layer 1 (kept in DB for easy updates).
CREATE TABLE IF NOT EXISTS red_flag_lexicon (
    id         SERIAL PRIMARY KEY,
    category   TEXT NOT NULL,
    phrase     TEXT NOT NULL,
    language   TEXT CHECK (language IN ('ms','en','mixed')),
    weight     REAL DEFAULT 1.0,
    UNIQUE (category, phrase)
);

-- 4. osint_cache ------------------------------------------------------------
-- Persistent record of Serper.dev lookups (Redis is the hot cache; this is
-- the durable audit log so results are reproducible for evaluation).
CREATE TABLE IF NOT EXISTS osint_cache (
    id           SERIAL PRIMARY KEY,
    lookup_key   TEXT NOT NULL,
    query        TEXT,
    result       JSONB,
    risk_fraction REAL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (lookup_key)
);

-- 5. dataset_examples -------------------------------------------------------
-- The labelled research dataset (real scam + real legit + reviewed synthetic).
CREATE TABLE IF NOT EXISTS dataset_examples (
    id          SERIAL PRIMARY KEY,
    text        TEXT NOT NULL,
    label       TEXT NOT NULL CHECK (label IN ('SCAM','LEGITIMATE')),
    origin      TEXT NOT NULL CHECK (origin IN ('real','synthetic')),
    source      TEXT,
    split       TEXT CHECK (split IN ('train','val','test')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dataset_label ON dataset_examples (label, split);
