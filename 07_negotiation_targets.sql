-- 07_negotiation_targets.sql
-- Stores target reimbursement rates (as % of Medicare) per payer and CPT code.
-- A NULL payer_id means the target applies globally (all payers).
-- A NULL cpt_code means the target applies to all codes for that payer.
-- Specificity wins: payer+code > payer-only > global default.

CREATE TABLE IF NOT EXISTS negotiation_targets (
    target_id              SERIAL PRIMARY KEY,
    payer_id               INTEGER REFERENCES payers(payer_id),     -- NULL = global default
    cpt_code               VARCHAR(10) REFERENCES cpt_codes(cpt_code), -- NULL = all codes
    target_pct_of_medicare NUMERIC(6,2) NOT NULL,                   -- e.g. 130.00 = 130%
    notes                  TEXT,
    created_at             TIMESTAMP DEFAULT NOW(),
    updated_at             TIMESTAMP DEFAULT NOW(),

    -- Prevent duplicate target rows for the same payer+code combination
    UNIQUE (payer_id, cpt_code)
);

-- Index to speed up lookups when the dashboard resolves targets
CREATE INDEX IF NOT EXISTS idx_negotiation_targets_payer ON negotiation_targets(payer_id);
CREATE INDEX IF NOT EXISTS idx_negotiation_targets_code  ON negotiation_targets(cpt_code);

-- Helper function: resolve the most specific target for a given payer+code pair.
-- Priority: (payer+code) > (payer only) > (global default)
CREATE OR REPLACE FUNCTION resolve_target_pct(p_payer_id INTEGER, p_cpt_code VARCHAR)
RETURNS NUMERIC AS $$
    SELECT COALESCE(
        -- Most specific: payer + code
        (SELECT target_pct_of_medicare FROM negotiation_targets
         WHERE payer_id = p_payer_id AND cpt_code = p_cpt_code),
        -- Payer-level default (code is NULL)
        (SELECT target_pct_of_medicare FROM negotiation_targets
         WHERE payer_id = p_payer_id AND cpt_code IS NULL),
        -- Global default (both NULL)
        (SELECT target_pct_of_medicare FROM negotiation_targets
         WHERE payer_id IS NULL AND cpt_code IS NULL)
    );
$$ LANGUAGE SQL STABLE;
