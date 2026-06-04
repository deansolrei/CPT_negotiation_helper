-- 22_multistate_views.sql
-- Upgrade: parameterize benchmark locality so the dashboard can show
-- Medicare rates for any state, not just FL.
--
-- Technique: PostgreSQL session-level configuration variable
--   SET LOCAL app.benchmark_locality = 'AZ';
--   SELECT * FROM v_fee_vs_medicare;   -- now returns AZ Medicare rates
--
-- The backend sets this before querying:
--   cur.execute("SET LOCAL app.benchmark_locality = %s", (state,))
--
-- If the variable is not set (direct psql usage), views fall back to 'FL'.
--
-- Run:
--   psql solrei_cpt -f 22_multistate_views.sql

SELECT '=== Upgrading views for multi-state Medicare benchmarks ===' AS info;

-- ──────────────────────────────────────────────────────────────────────────────
-- VIEW 1: v_fee_vs_medicare  (replaces the FL-hardcoded version)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_fee_vs_medicare AS
SELECT
    f.fee_schedule_line_id,
    c.contract_id,
    p.payer_id,
    p.payer_name,
    pe.provider_entity_id,
    pe.legal_name          AS provider_name,
    pe.npi_number,
    pe.entity_type,
    c.payer_contract_id,
    c.product_line,
    f.cpt_code,
    cc.short_description,
    cc.category,
    cc.telehealth_eligible,
    cc.is_addon,
    f.modifier,
    f.place_of_service,
    f.unit_type,
    f.allowed_amount                                        AS payer_allowed,
    b.allowed_amount                                        AS medicare_allowed,
    CASE
        WHEN b.allowed_amount IS NULL OR b.allowed_amount = 0 THEN NULL
        ELSE ROUND(f.allowed_amount / b.allowed_amount * 100, 1)
    END                                                     AS pct_of_medicare,
    f.effective_date,
    f.end_date
FROM fee_schedule_lines f
JOIN contracts c          ON f.contract_id         = c.contract_id
JOIN payers p             ON c.payer_id            = p.payer_id
JOIN provider_entities pe ON c.provider_entity_id  = pe.provider_entity_id
JOIN cpt_codes cc         ON f.cpt_code            = cc.cpt_code
LEFT JOIN benchmark_fee_schedule b
    ON  b.cpt_code        = f.cpt_code
    AND b.source_name     = 'Medicare 2026'
    AND b.locality        = COALESCE(
                                NULLIF(current_setting('app.benchmark_locality', TRUE), ''),
                                'FL'
                            )
    AND b.effective_year  = 2026
WHERE (c.end_date IS NULL OR c.end_date >= CURRENT_DATE)
  AND (f.end_date IS NULL OR f.end_date >= CURRENT_DATE)
  AND c.active = TRUE;

SELECT 'v_fee_vs_medicare updated ✓' AS info;


-- ──────────────────────────────────────────────────────────────────────────────
-- VIEW 2: v_negotiation_dashboard  (unchanged except inherits the locality fix)
-- Rebuilt here to ensure it's consistent with the updated base view.
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_negotiation_dashboard AS
WITH
targets AS (
    SELECT
        fm.fee_schedule_line_id,
        fm.contract_id,
        fm.payer_id,
        fm.payer_name,
        fm.provider_entity_id,
        fm.provider_name,
        fm.npi_number,
        fm.entity_type,
        fm.payer_contract_id,
        fm.product_line,
        fm.cpt_code,
        fm.short_description,
        fm.category,
        fm.telehealth_eligible,
        fm.is_addon,
        fm.modifier,
        fm.place_of_service,
        fm.unit_type,
        fm.payer_allowed,
        fm.medicare_allowed,
        fm.pct_of_medicare,
        fm.effective_date,
        fm.end_date,
        COALESCE(
            (SELECT target_pct_of_medicare FROM negotiation_targets
             WHERE payer_id = fm.payer_id AND cpt_code = fm.cpt_code),
            (SELECT target_pct_of_medicare FROM negotiation_targets
             WHERE payer_id = fm.payer_id AND cpt_code IS NULL),
            (SELECT target_pct_of_medicare FROM negotiation_targets
             WHERE payer_id IS NULL AND cpt_code IS NULL)
        ) AS target_pct_of_medicare
    FROM v_fee_vs_medicare fm
),
volumes AS (
    SELECT DISTINCT ON (contract_id, cpt_code, modifier)
        contract_id,
        cpt_code,
        modifier,
        annual_volume,
        calendar_year
    FROM annual_claims_volume
    ORDER BY contract_id, cpt_code, modifier, calendar_year DESC
)
SELECT
    t.fee_schedule_line_id,
    t.contract_id,
    t.payer_id,
    t.payer_name,
    t.provider_entity_id,
    t.provider_name,
    t.npi_number,
    t.entity_type,
    t.payer_contract_id,
    t.product_line,
    t.cpt_code,
    t.short_description,
    t.category,
    t.telehealth_eligible,
    t.is_addon,
    t.modifier,
    t.place_of_service,
    t.unit_type,
    t.effective_date,
    t.payer_allowed,
    t.medicare_allowed,
    t.pct_of_medicare,
    t.target_pct_of_medicare,
    CASE
        WHEN t.medicare_allowed IS NULL THEN NULL
        ELSE ROUND(t.medicare_allowed * t.target_pct_of_medicare / 100, 2)
    END AS target_allowed,
    CASE
        WHEN t.medicare_allowed IS NULL THEN NULL
        ELSE ROUND((t.medicare_allowed * t.target_pct_of_medicare / 100) - t.payer_allowed, 2)
    END AS rate_gap_per_unit,
    CASE
        WHEN t.pct_of_medicare IS NULL OR t.target_pct_of_medicare IS NULL THEN NULL
        WHEN t.pct_of_medicare < t.target_pct_of_medicare THEN TRUE
        ELSE FALSE
    END AS is_underpaid,
    v.annual_volume,
    v.calendar_year                                         AS volume_year,
    CASE
        WHEN v.annual_volume IS NULL THEN NULL
        ELSE ROUND(t.payer_allowed * v.annual_volume, 2)
    END AS annual_revenue_current,
    CASE
        WHEN v.annual_volume IS NULL OR t.medicare_allowed IS NULL THEN NULL
        ELSE ROUND((t.medicare_allowed * t.target_pct_of_medicare / 100) * v.annual_volume, 2)
    END AS annual_revenue_at_target,
    CASE
        WHEN v.annual_volume IS NULL OR t.medicare_allowed IS NULL THEN NULL
        ELSE ROUND(
            ((t.medicare_allowed * t.target_pct_of_medicare / 100) - t.payer_allowed) * v.annual_volume,
        2)
    END AS annual_revenue_gap
FROM targets t
LEFT JOIN volumes v
    ON  v.contract_id = t.contract_id
    AND v.cpt_code    = t.cpt_code
    AND (v.modifier = t.modifier OR (v.modifier IS NULL AND t.modifier IS NULL))
ORDER BY
    CASE WHEN v.annual_volume IS NOT NULL THEN 0 ELSE 1 END,
    annual_revenue_gap DESC NULLS LAST,
    t.payer_name,
    t.cpt_code;

SELECT 'v_negotiation_dashboard updated ✓' AS info;


-- ──────────────────────────────────────────────────────────────────────────────
-- VIEW 3: v_negotiation_summary  (rebuilt to inherit fix)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_negotiation_summary AS
SELECT
    payer_id,
    payer_name,
    COUNT(DISTINCT cpt_code)                                        AS codes_with_rates,
    COUNT(DISTINCT cpt_code) FILTER (WHERE is_underpaid = TRUE)     AS codes_underpaid,
    ROUND(AVG(pct_of_medicare), 1)                                  AS avg_pct_of_medicare,
    ROUND(AVG(target_pct_of_medicare), 1)                           AS avg_target_pct,
    SUM(annual_revenue_current)                                     AS total_revenue_current,
    SUM(annual_revenue_at_target)                                   AS total_revenue_at_target,
    SUM(annual_revenue_gap)                                         AS total_revenue_gap
FROM v_negotiation_dashboard
GROUP BY payer_id, payer_name
ORDER BY total_revenue_gap DESC NULLS LAST;

SELECT 'v_negotiation_summary updated ✓' AS info;


-- ──────────────────────────────────────────────────────────────────────────────
-- VIEW 4: v_channel_comparison  (update medicare CTE to respect locality)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_channel_comparison AS
WITH

direct_rates AS (
    SELECT DISTINCT ON (p.payer_name, fsl.cpt_code)
        p.payer_name,
        fsl.cpt_code,
        fsl.allowed_amount AS direct_rate
    FROM fee_schedule_lines fsl
    JOIN contracts         c   ON fsl.contract_id       = c.contract_id
    JOIN payers            p   ON c.payer_id            = p.payer_id
    JOIN provider_entities pe  ON c.provider_entity_id  = pe.provider_entity_id
    WHERE c.active = TRUE
      AND (c.end_date  IS NULL OR c.end_date  >= CURRENT_DATE)
      AND (fsl.end_date IS NULL OR fsl.end_date >= CURRENT_DATE)
    ORDER BY
        p.payer_name,
        fsl.cpt_code,
        CASE pe.entity_type WHEN 'NPI1' THEN 0 ELSE 1 END,
        fsl.allowed_amount DESC
),

-- Medicare: filtered to the active state/locality (set by backend session var)
medicare AS (
    SELECT cpt_code, allowed_amount AS medicare_allowed
    FROM   benchmark_fee_schedule
    WHERE  source_name    = 'Medicare 2026'
      AND  effective_year = 2026
      AND  locality       = COALESCE(
                                NULLIF(current_setting('app.benchmark_locality', TRUE), ''),
                                'FL'
                            )
),

all_combos AS (
    SELECT DISTINCT payer_name, cpt_code
    FROM   intermediary_rates
    WHERE  payer_name IS NOT NULL
      AND  cpt_code IN (
               '99214','99215','90833','90836','90838',
               '99204','99205','90785',
               '98002','98003','98006','98007'
           )
    UNION
    SELECT DISTINCT p.payer_name, fsl.cpt_code
    FROM fee_schedule_lines fsl
    JOIN contracts         c  ON fsl.contract_id       = c.contract_id
    JOIN payers            p  ON c.payer_id            = p.payer_id
    WHERE c.active = TRUE
      AND (c.end_date  IS NULL OR c.end_date  >= CURRENT_DATE)
      AND (fsl.end_date IS NULL OR fsl.end_date >= CURRENT_DATE)
      AND fsl.cpt_code IN (
               '99214','99215','90833','90836','90838',
               '99204','99205','90785',
               '98002','98003','98006','98007'
           )
),

name_resolved AS (
    SELECT DISTINCT ON (ac.payer_name)
        ac.payer_name  AS intermediary_payer_name,
        COALESCE(
            ipm.direct_payer_name,
            (SELECT p.payer_name FROM payers p
             WHERE  lower(p.payer_name) = lower(ac.payer_name) LIMIT 1)
        ) AS direct_payer_name
    FROM all_combos ac
    LEFT JOIN intermediary_payer_map ipm
           ON ipm.intermediary_payer_name = ac.payer_name
    ORDER BY ac.payer_name, ipm.direct_payer_name NULLS LAST
),

-- Intermediary rate CTEs: exact state match only — no FL fallback.
-- If no rates have been uploaded for the active state, the rate shows as NULL
-- (blank in the dashboard), making it immediately obvious that data is missing.
-- Also surfaces updated_at so the dashboard can show "last updated" per platform.
headway AS (
    SELECT DISTINCT ON (ir.payer_name, ir.cpt_code)
        ir.payer_name,
        ir.cpt_code,
        ir.allowed_amount  AS headway_rate,
        ir.updated_at      AS headway_updated_at
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Headway' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
      AND  ir.state = COALESCE(NULLIF(current_setting('app.benchmark_locality', TRUE), ''), 'FL')
    ORDER BY ir.payer_name, ir.cpt_code, ir.allowed_amount DESC
),

alma AS (
    SELECT DISTINCT ON (ir.payer_name, ir.cpt_code)
        ir.payer_name,
        ir.cpt_code,
        ir.allowed_amount  AS alma_rate,
        ir.updated_at      AS alma_updated_at
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Alma' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
      AND  ir.state = COALESCE(NULLIF(current_setting('app.benchmark_locality', TRUE), ''), 'FL')
    ORDER BY ir.payer_name, ir.cpt_code, ir.allowed_amount DESC
),

grow AS (
    SELECT DISTINCT ON (ir.payer_name, ir.cpt_code)
        ir.payer_name,
        ir.cpt_code,
        ir.allowed_amount  AS grow_rate,
        ir.updated_at      AS grow_updated_at
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Grow Therapy' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
      AND  ir.state = COALESCE(NULLIF(current_setting('app.benchmark_locality', TRUE), ''), 'FL')
    ORDER BY ir.payer_name, ir.cpt_code, ir.allowed_amount DESC
),

combined AS (
    SELECT
        p.payer_id,
        ac.payer_name,
        ac.cpt_code,
        cc.short_description,
        cc.category,
        m.medicare_allowed,
        dr.direct_rate,
        CASE WHEN dr.direct_rate IS NOT NULL AND m.medicare_allowed > 0
             THEN ROUND((dr.direct_rate / m.medicare_allowed * 100)::numeric, 1)
        END AS direct_pct_of_medicare,
        h.headway_rate,
        h.headway_updated_at,
        a.alma_rate,
        a.alma_updated_at,
        g.grow_rate,
        g.grow_updated_at,
        -- Oldest update across all present intermediary rates for this row
        LEAST(
            h.headway_updated_at,
            a.alma_updated_at,
            g.grow_updated_at
        ) AS oldest_intermediary_update,
        CASE
            WHEN GREATEST(
                COALESCE(dr.direct_rate,  0),
                COALESCE(h.headway_rate,  0),
                COALESCE(a.alma_rate,     0),
                COALESCE(g.grow_rate,     0)
            ) = 0 THEN 'No Data'
            WHEN COALESCE(dr.direct_rate, 0) >= COALESCE(h.headway_rate, 0)
             AND COALESCE(dr.direct_rate, 0) >= COALESCE(a.alma_rate,    0)
             AND COALESCE(dr.direct_rate, 0) >= COALESCE(g.grow_rate,    0)
             AND dr.direct_rate IS NOT NULL
            THEN 'Direct'
            ELSE 'Intermediary'
        END AS best_channel_type,
        CASE WHEN dr.direct_rate IS NOT NULL THEN TRUE ELSE FALSE END AS has_direct_contract
    FROM all_combos ac
    JOIN  cpt_codes    cc  ON cc.cpt_code  = ac.cpt_code
    LEFT JOIN medicare     m   ON m.cpt_code   = ac.cpt_code
    LEFT JOIN name_resolved nr ON nr.intermediary_payer_name = ac.payer_name
    LEFT JOIN direct_rates  dr ON dr.payer_name = nr.direct_payer_name
                               AND dr.cpt_code  = ac.cpt_code
    LEFT JOIN payers        p  ON p.payer_name  = nr.direct_payer_name
    LEFT JOIN headway       h  ON h.payer_name  = ac.payer_name AND h.cpt_code = ac.cpt_code
    LEFT JOIN alma          a  ON a.payer_name  = ac.payer_name AND a.cpt_code = ac.cpt_code
    LEFT JOIN grow          g  ON g.payer_name  = ac.payer_name AND g.cpt_code = ac.cpt_code
)

SELECT DISTINCT ON (payer_name, cpt_code)
    payer_id, payer_name, cpt_code, short_description, category,
    medicare_allowed, direct_rate, direct_pct_of_medicare,
    headway_rate, headway_updated_at,
    alma_rate,    alma_updated_at,
    grow_rate,    grow_updated_at,
    oldest_intermediary_update,
    best_channel_type, has_direct_contract
FROM combined
ORDER BY payer_name, cpt_code;

SELECT 'v_channel_comparison updated ✓' AS info;

SELECT '=== All views updated. Run the backend and test with ?state=AZ ===' AS info;
