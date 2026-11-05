-- Migration 003 — store analysis results without personal data.
-- Mirrors database/schema.sql; keep the two in sync. Safe to re-run
-- (npm run migrate applies every file each time).
--
-- listings was designed in FYP1 to keep the renter's chat (raw_text) and the
-- agent's name, phone, REN number and company. Nothing ever wrote to it. From
-- now on a row holds only what the system produced: score, band, components
-- and `facts` (the narrative's input, llm.service.js narrativeFacts, which by
-- design holds no identifier), the narrative, and the listing details typed
-- into the form. The chat and the agent identifiers stay out: data
-- minimisation (PDPA 2010), the same reason OSINT cache keys are HMACs.
-- The old columns are kept, always NULL, so earlier code and docs still read.

ALTER TABLE listings ALTER COLUMN raw_text DROP NOT NULL;

-- UNKNOWN is a real band: nothing could be scored (scoring.service.js), and
-- such a result has no score.
ALTER TABLE listings DROP CONSTRAINT IF EXISTS listings_risk_band_check;
ALTER TABLE listings ADD CONSTRAINT listings_risk_band_check
    CHECK (risk_band IN ('LOW', 'MODERATE', 'HIGH', 'CRITICAL', 'UNKNOWN'));

ALTER TABLE listings ADD COLUMN IF NOT EXISTS facts JSONB;

-- The narrative is { en, ms, provider, model, promptVersion }, not one text.
DO $$
BEGIN
    IF (SELECT data_type FROM information_schema.columns
        WHERE table_name = 'listings' AND column_name = 'narrative') = 'text' THEN
        ALTER TABLE listings ALTER COLUMN narrative TYPE JSONB USING to_jsonb(narrative);
    END IF;
END $$;

-- Phone numbers are never stored, so nothing is ever looked up by one.
DROP INDEX IF EXISTS idx_listings_phone;
