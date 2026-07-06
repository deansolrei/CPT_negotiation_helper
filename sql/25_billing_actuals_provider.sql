-- ============================================================
-- 25_billing_actuals_provider.sql
-- Adds provider_name dimension to billing_actuals table.
-- Drops and recreates the table + view with provider support.
-- Run AFTER 24_billing_actuals.sql has been applied.
-- ============================================================

-- Drop dependent view first
DROP VIEW IF EXISTS v_billing_actuals;

-- Recreate table with provider_name column
DROP TABLE IF EXISTS billing_actuals;

CREATE TABLE billing_actuals (
    id             SERIAL        PRIMARY KEY,
    intermediary   VARCHAR(50)   NOT NULL,
    provider_name  VARCHAR(100)  NOT NULL DEFAULT 'All',
    insurance_plan VARCHAR(200)  NOT NULL,
    state          CHAR(2)       NOT NULL,
    primary_cpt    VARCHAR(10)   NOT NULL,
    addon_cpt      VARCHAR(10),
    avg_payment    NUMERIC(10,2) NOT NULL,
    session_count  INTEGER       NOT NULL DEFAULT 1,
    min_payment    NUMERIC(10,2),
    max_payment    NUMERIC(10,2),
    effective_year INTEGER       NOT NULL DEFAULT 2026,
    created_at     TIMESTAMPTZ   DEFAULT NOW(),
    updated_at     TIMESTAMPTZ   DEFAULT NOW(),

    CONSTRAINT billing_actuals_unique
        UNIQUE (intermediary, provider_name, insurance_plan, state, primary_cpt, addon_cpt)
);

-- Updated view with provider_name and session_type label
CREATE OR REPLACE VIEW v_billing_actuals AS
SELECT
    id,
    intermediary,
    provider_name,
    insurance_plan,
    state,
    primary_cpt,
    addon_cpt,
    CASE
        WHEN addon_cpt IS NOT NULL THEN primary_cpt || '+' || addon_cpt
        ELSE primary_cpt
    END AS session_type,
    avg_payment,
    session_count,
    min_payment,
    max_payment,
    effective_year,
    updated_at
FROM billing_actuals;

CREATE INDEX IF NOT EXISTS billing_actuals_state_provider_idx
    ON billing_actuals (state, provider_name, primary_cpt, addon_cpt);

CREATE INDEX IF NOT EXISTS billing_actuals_intermediary_idx
    ON billing_actuals (intermediary, state, provider_name);
