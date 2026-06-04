-- 11_intermediaries.sql
-- Tracks third-party billing intermediaries (Headway, Alma, Grow Therapy, etc.)
-- and the rates they pay providers for each payer + CPT code combination.
--
-- Run AFTER all prior schema files (01–10) have been executed.
-- Then run: python3 backend/load_intermediaries.py  (seeds the three platforms)

-- ──────────────────────────────────────────────────────────────────
-- TABLE: intermediaries
-- The platforms themselves (Headway, Alma, Grow Therapy, etc.)
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS intermediaries (
    intermediary_id   SERIAL PRIMARY KEY,
    name              VARCHAR(100) NOT NULL UNIQUE,  -- 'Headway'
    display_name      VARCHAR(150),                  -- 'Headway (BCBS + Aetna network)'
    website           VARCHAR(200),
    fee_description   TEXT,                          -- e.g. '0% fee — rates pre-negotiated'
    notes             TEXT,
    active            BOOLEAN DEFAULT TRUE
);

-- ──────────────────────────────────────────────────────────────────
-- TABLE: intermediary_rates
-- What each intermediary pays the provider per CPT code, per payer,
-- in a given state. This is the "take-home" rate after any platform
-- fee has already been accounted for.
--
-- Key design decisions:
--   - payer_id can be NULL → rate applies to ALL payers on that platform
--   - state can be NULL   → rate applies nationally
--   - If a more specific row exists (payer + state), it wins over
--     a more general one (payer only, or NULL payer).
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS intermediary_rates (
    rate_id           SERIAL PRIMARY KEY,
    intermediary_id   INTEGER      NOT NULL REFERENCES intermediaries(intermediary_id),
    payer_id          INTEGER      REFERENCES payers(payer_id),      -- NULL = all payers
    cpt_code          VARCHAR(10)  NOT NULL REFERENCES cpt_codes(cpt_code),
    state             VARCHAR(2)   DEFAULT 'FL',
    allowed_amount    NUMERIC(10,2) NOT NULL,                         -- provider take-home rate
    effective_date    DATE,
    notes             TEXT,
    created_at        TIMESTAMP DEFAULT NOW(),
    updated_at        TIMESTAMP DEFAULT NOW(),

    UNIQUE (intermediary_id, payer_id, cpt_code, state, effective_date)
);

CREATE INDEX IF NOT EXISTS idx_ir_intermediary ON intermediary_rates(intermediary_id);
CREATE INDEX IF NOT EXISTS idx_ir_payer        ON intermediary_rates(payer_id);
CREATE INDEX IF NOT EXISTS idx_ir_cpt          ON intermediary_rates(cpt_code);
CREATE INDEX IF NOT EXISTS idx_ir_state        ON intermediary_rates(state);


-- ──────────────────────────────────────────────────────────────────
-- VIEW: v_channel_comparison
-- Side-by-side comparison of direct billing vs. each intermediary
-- for every payer + CPT code combination we have rates for.
--
-- "Best channel" is the one with the highest allowed_amount.
-- ──────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_channel_comparison AS
WITH

-- All direct rates (from fee_schedule_lines / v_fee_vs_medicare)
direct AS (
    SELECT
        fm.payer_id,
        fm.payer_name,
        fm.cpt_code,
        fm.short_description,
        fm.category,
        fm.modifier,
        fm.payer_allowed          AS direct_rate,
        fm.medicare_allowed,
        fm.pct_of_medicare        AS direct_pct_of_medicare
    FROM v_fee_vs_medicare fm
    WHERE fm.entity_type = 'NPI2'   -- use group rates for comparison baseline
),

-- Intermediary rates, resolved most-specific first (payer+state > payer > state > global)
intermediary_resolved AS (
    SELECT DISTINCT ON (ir.intermediary_id, ir.cpt_code, COALESCE(ir.payer_id, -1))
        i.intermediary_id,
        i.name             AS intermediary_name,
        ir.payer_id,
        p.payer_name       AS intermediary_payer_name,
        ir.cpt_code,
        ir.state,
        ir.allowed_amount  AS intermediary_rate,
        ir.notes
    FROM intermediary_rates ir
    JOIN intermediaries i ON ir.intermediary_id = i.intermediary_id
    LEFT JOIN payers p    ON ir.payer_id        = p.payer_id
    WHERE i.active = TRUE
      AND (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
    ORDER BY
        ir.intermediary_id,
        ir.cpt_code,
        COALESCE(ir.payer_id, -1),
        -- Most specific wins: payer_id NOT NULL first, then most recent date
        (ir.payer_id IS NULL) ASC,
        ir.effective_date DESC NULLS LAST
)

-- Pivot intermediaries as columns alongside direct rate
SELECT
    d.payer_id,
    d.payer_name,
    d.cpt_code,
    d.short_description,
    d.category,
    d.modifier,
    d.medicare_allowed,
    d.direct_pct_of_medicare,

    -- Direct billing rate
    d.direct_rate,

    -- Headway rate (payer-specific if available, else platform-wide)
    COALESCE(
        (SELECT intermediary_rate FROM intermediary_resolved
         WHERE intermediary_name = 'Headway'
           AND cpt_code = d.cpt_code
           AND payer_id = d.payer_id),
        (SELECT intermediary_rate FROM intermediary_resolved
         WHERE intermediary_name = 'Headway'
           AND cpt_code = d.cpt_code
           AND payer_id IS NULL)
    ) AS headway_rate,

    -- Alma rate
    COALESCE(
        (SELECT intermediary_rate FROM intermediary_resolved
         WHERE intermediary_name = 'Alma'
           AND cpt_code = d.cpt_code
           AND payer_id = d.payer_id),
        (SELECT intermediary_rate FROM intermediary_resolved
         WHERE intermediary_name = 'Alma'
           AND cpt_code = d.cpt_code
           AND payer_id IS NULL)
    ) AS alma_rate,

    -- Grow Therapy rate
    COALESCE(
        (SELECT intermediary_rate FROM intermediary_resolved
         WHERE intermediary_name = 'Grow Therapy'
           AND cpt_code = d.cpt_code
           AND payer_id = d.payer_id),
        (SELECT intermediary_rate FROM intermediary_resolved
         WHERE intermediary_name = 'Grow Therapy'
           AND cpt_code = d.cpt_code
           AND payer_id IS NULL)
    ) AS grow_rate,

    -- Best channel (name of the highest-paying option)
    CASE GREATEST(
        d.direct_rate,
        COALESCE((SELECT intermediary_rate FROM intermediary_resolved
                  WHERE intermediary_name = 'Headway' AND cpt_code = d.cpt_code
                    AND (payer_id = d.payer_id OR payer_id IS NULL)
                  ORDER BY (payer_id IS NULL) LIMIT 1), 0),
        COALESCE((SELECT intermediary_rate FROM intermediary_resolved
                  WHERE intermediary_name = 'Alma' AND cpt_code = d.cpt_code
                    AND (payer_id = d.payer_id OR payer_id IS NULL)
                  ORDER BY (payer_id IS NULL) LIMIT 1), 0),
        COALESCE((SELECT intermediary_rate FROM intermediary_resolved
                  WHERE intermediary_name = 'Grow Therapy' AND cpt_code = d.cpt_code
                    AND (payer_id = d.payer_id OR payer_id IS NULL)
                  ORDER BY (payer_id IS NULL) LIMIT 1), 0)
    )
        WHEN d.direct_rate THEN 'Direct'
        ELSE 'Intermediary'
    END AS best_channel_type

FROM direct d
ORDER BY d.payer_name, d.cpt_code;
