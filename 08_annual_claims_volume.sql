-- 08_annual_claims_volume.sql
-- Tracks how many times we billed each CPT code under each contract in a given year.
-- This is what makes the revenue gap math possible:
--   annual_revenue_current    = allowed_amount × annual_volume
--   annual_revenue_at_target  = target_allowed  × annual_volume
--   annual_revenue_gap        = at_target - current

CREATE TABLE IF NOT EXISTS annual_claims_volume (
    volume_id       SERIAL PRIMARY KEY,
    contract_id     INTEGER     NOT NULL REFERENCES contracts(contract_id),
    cpt_code        VARCHAR(10) NOT NULL REFERENCES cpt_codes(cpt_code),
    modifier        VARCHAR(10),             -- match the modifier used in fee_schedule_lines
    calendar_year   INTEGER     NOT NULL,    -- e.g. 2025
    annual_volume   INTEGER     NOT NULL CHECK (annual_volume >= 0),
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),

    UNIQUE (contract_id, cpt_code, modifier, calendar_year)
);

CREATE INDEX IF NOT EXISTS idx_acv_contract  ON annual_claims_volume(contract_id);
CREATE INDEX IF NOT EXISTS idx_acv_cpt       ON annual_claims_volume(cpt_code);
CREATE INDEX IF NOT EXISTS idx_acv_year      ON annual_claims_volume(calendar_year);
