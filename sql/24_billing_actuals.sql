-- ============================================================
-- 24_billing_actuals.sql
-- Actual 2026 session payment data from Headway and Alma
-- billing exports. Stores aggregated real payment amounts
-- by (intermediary, insurance_plan, state, session type).
-- ============================================================

-- Table: billing_actuals
-- Each row = average payment received for a specific
-- (intermediary, insurance plan, state, primary CPT, add-on CPT)
-- combination, derived from actual 2026 billing data.

CREATE TABLE IF NOT EXISTS billing_actuals (
    id             SERIAL        PRIMARY KEY,
    intermediary   VARCHAR(50)   NOT NULL,     -- 'Headway' or 'Alma'
    insurance_plan VARCHAR(200)  NOT NULL,     -- specific plan name
    state          CHAR(2)       NOT NULL,
    primary_cpt    VARCHAR(10)   NOT NULL,
    addon_cpt      VARCHAR(10),               -- NULL if no add-on code
    avg_payment    NUMERIC(10,2) NOT NULL,     -- average provider take-home
    session_count  INTEGER       NOT NULL DEFAULT 1,
    min_payment    NUMERIC(10,2),
    max_payment    NUMERIC(10,2),
    effective_year INTEGER       NOT NULL DEFAULT 2026,
    created_at     TIMESTAMPTZ   DEFAULT NOW(),
    updated_at     TIMESTAMPTZ   DEFAULT NOW(),

    CONSTRAINT billing_actuals_unique
        UNIQUE (intermediary, insurance_plan, state, primary_cpt, addon_cpt)
);

-- Convenience view: adds session label and handles NULL addon_cpt display
CREATE OR REPLACE VIEW v_billing_actuals AS
SELECT
    id,
    intermediary,
    insurance_plan,
    state,
    primary_cpt,
    addon_cpt,
    CASE
        WHEN addon_cpt IS NOT NULL THEN primary_cpt || '+' || addon_cpt
        ELSE primary_cpt
    END                       AS session_type,
    avg_payment,
    session_count,
    min_payment,
    max_payment,
    effective_year,
    updated_at
FROM billing_actuals;

-- Index for fast state + session type lookups
CREATE INDEX IF NOT EXISTS billing_actuals_state_idx
    ON billing_actuals (state, primary_cpt, addon_cpt);

CREATE INDEX IF NOT EXISTS billing_actuals_intermediary_idx
    ON billing_actuals (intermediary, state);
