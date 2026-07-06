-- Migration 24: Add provider column to intermediary_rates
-- Tracks which provider a rate applies to: JJ, KR, LK, or COMMON (all)
-- Run once on the Mac Mini:
--   ssh sbhserver1@192.168.88.178 "cd /Users/sbhserver1/cpt_dashboard && \
--   /opt/homebrew/opt/postgresql@16/bin/psql solrei_cpt -f sql/24_add_provider_to_intermediary_rates.sql"

BEGIN;

-- 1. Add provider column (NULL = applies to all providers, same as COMMON)
ALTER TABLE intermediary_rates
    ADD COLUMN IF NOT EXISTS provider VARCHAR(10) DEFAULT NULL;

COMMENT ON COLUMN intermediary_rates.provider IS
    'Provider code this rate applies to: JJ=Jodene Jensen, KR=Katherine Robins, LK=Lori Kistler, NULL=all providers (COMMON)';

-- 2. Add SBH as an intermediary (Direct Submit through clinic)
INSERT INTO intermediaries (name, display_name, website, fee_description, notes, active)
VALUES (
    'SBH',
    'SBH Direct Submit',
    NULL,
    'Clinic direct contract rate — no intermediary fee',
    'Solrei Behavioral Health direct payer contracts. Source of truth: MASTER Google Sheet.',
    TRUE
)
ON CONFLICT (name) DO UPDATE SET
    display_name  = EXCLUDED.display_name,
    fee_description = EXCLUDED.fee_description,
    active        = TRUE;

-- 3. Drop and recreate the unique constraint to include provider
--    (same payer+cpt+state can now have different rates per provider)
ALTER TABLE intermediary_rates
    DROP CONSTRAINT IF EXISTS intermediary_rates_unique;

ALTER TABLE intermediary_rates
    ADD CONSTRAINT intermediary_rates_unique
    UNIQUE (intermediary_id, payer_name, cpt_code, state, provider);

-- 4. Create index for provider filtering
CREATE INDEX IF NOT EXISTS idx_intermediary_rates_provider
    ON intermediary_rates (provider);

COMMIT;

-- Verify
SELECT
    'intermediaries' AS tbl,
    name,
    display_name,
    active
FROM intermediaries
ORDER BY name;
