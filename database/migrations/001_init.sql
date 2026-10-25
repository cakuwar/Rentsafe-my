-- Migration 001 — initial schema (standalone, runnable via `npm run migrate`).
-- Canonical schema also lives in database/schema.sql (auto-run by docker-compose).
-- Keep the two in sync if you change the model.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

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

CREATE TABLE IF NOT EXISTS price_baseline (
    id            SERIAL PRIMARY KEY,
    area          TEXT NOT NULL,
    bedrooms      INTEGER,
    property_type TEXT,
    median_price  NUMERIC(10, 2) NOT NULL,
    p25_price     NUMERIC(10, 2),
    p75_price     NUMERIC(10, 2),
    sample_size   INTEGER DEFAULT 0,
    source        TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (area, bedrooms, property_type)
);

CREATE TABLE IF NOT EXISTS red_flag_lexicon (
    id       SERIAL PRIMARY KEY,
    category TEXT NOT NULL,
    phrase   TEXT NOT NULL,
    language TEXT CHECK (language IN ('ms','en','mixed')),
    weight   REAL DEFAULT 1.0,
    UNIQUE (category, phrase)
);

CREATE TABLE IF NOT EXISTS osint_cache (
    id            SERIAL PRIMARY KEY,
    lookup_key    TEXT NOT NULL,
    query         TEXT,
    result        JSONB,
    risk_fraction REAL,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (lookup_key)
);

CREATE TABLE IF NOT EXISTS dataset_examples (
    id         SERIAL PRIMARY KEY,
    text       TEXT NOT NULL,
    label      TEXT NOT NULL CHECK (label IN ('SCAM','LEGITIMATE')),
    origin     TEXT NOT NULL CHECK (origin IN ('real','synthetic')),
    source     TEXT,
    split      TEXT CHECK (split IN ('train','val','test')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dataset_label ON dataset_examples (label, split);
