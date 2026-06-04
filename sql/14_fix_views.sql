-- 14_fix_views.sql
-- 1. Limits v_negotiation_summary to the 12 tracked CPT codes so "CODES W/ RATES"
--    never shows more than 12 (fixes the "42 codes" display for Florida Blue).
-- 2. Recreates v_channel_comparison with MAX() deduplication (re-applies the fix
--    from 13_fix_duplicates.sql in case it didn't fully complete).
--
-- Run from your project folder:
--   psql solrei_cpt -f 14_fix_views.sql

-- ── Tracked CPT codes (single source of truth) ──────────────
-- Order matches the dashboard display order exactly.

-- ──────────────────────────────────────────────────────────────────
-- 1. v_negotiation_summary — add WHERE filter to 12 CPT codes
-- ──────────────────────────────────────────────────────────────────
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
WHERE cpt_code IN (
    '99214','99215','90833','90836','90838',
    '99204','99205','90785',
    '98002','98003','98006','98007'
)
GROUP BY payer_id, payer_name
ORDER BY total_revenue_gap DESC NULLS LAST;

-- ──────────────────────────────────────────────────────────────────
-- 2. v_channel_comparison — rebuild with MAX() per (payer, CPT)
--    so duplicates in intermediary_rates never cause duplicate rows
-- ──────────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS v_channel_comparison;
CREATE VIEW v_channel_comparison AS
WITH

direct_rates AS (
    SELECT p.payer_name, fsl.cpt_code, MAX(fsl.allowed_amount) AS direct_rate
    FROM fee_schedule_lines fsl
    JOIN contracts         c   ON fsl.contract_id = c.contract_id
    JOIN payers            p   ON c.payer_id      = p.payer_id
    JOIN provider_entities pe  ON c.provider_entity_id = pe.provider_entity_id
    WHERE pe.entity_type = 'NPI2'
    GROUP BY p.payer_name, fsl.cpt_code
),

medicare AS (
    SELECT cpt_code, allowed_amount AS medicare_allowed
    FROM   benchmark_fee_schedule
    WHERE  source_name = 'Medicare 2026'
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
),

name_resolved AS (
    SELECT
        ac.payer_name AS intermediary_payer_name,
        COALESCE(
            ipm.direct_payer_name,
            (SELECT p.payer_name FROM payers p
             WHERE lower(p.payer_name) = lower(ac.payer_name) LIMIT 1)
        ) AS direct_payer_name
    FROM all_combos ac
    LEFT JOIN intermediary_payer_map ipm
           ON ipm.intermediary_payer_name = ac.payer_name
),

headway AS (
    SELECT ir.payer_name, ir.cpt_code, MAX(ir.allowed_amount) AS headway_rate
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Headway' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
    GROUP  BY ir.payer_name, ir.cpt_code
),

alma AS (
    SELECT ir.payer_name, ir.cpt_code, MAX(ir.allowed_amount) AS alma_rate
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Alma' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
    GROUP  BY ir.payer_name, ir.cpt_code
),

grow AS (
    SELECT ir.payer_name, ir.cpt_code, MAX(ir.allowed_amount) AS grow_rate
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Grow Therapy' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
    GROUP  BY ir.payer_name, ir.cpt_code
)

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
    a.alma_rate,
    g.grow_rate,
    CASE
        WHEN GREATEST(
            COALESCE(dr.direct_rate, 0),
            COALESCE(h.headway_rate, 0),
            COALESCE(a.alma_rate,    0),
            COALESCE(g.grow_rate,    0)
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
LEFT JOIN direct_rates  dr ON dr.payer_name = nr.direct_payer_name AND dr.cpt_code = ac.cpt_code
LEFT JOIN payers        p  ON p.payer_name  = nr.direct_payer_name
LEFT JOIN headway       h  ON h.payer_name  = ac.payer_name AND h.cpt_code = ac.cpt_code
LEFT JOIN alma          a  ON a.payer_name  = ac.payer_name AND a.cpt_code = ac.cpt_code
LEFT JOIN grow          g  ON g.payer_name  = ac.payer_name AND g.cpt_code = ac.cpt_code

ORDER BY ac.payer_name, ac.cpt_code;

-- ── Verify ───────────────────────────────────────────────────
SELECT 'v_negotiation_summary rows' AS check, COUNT(*)::text AS result FROM v_negotiation_summary
UNION ALL
SELECT 'v_channel_comparison rows',           COUNT(*)::text FROM v_channel_comparison
UNION ALL
SELECT 'duplicate (payer,cpt) in channel',
       COUNT(*)::text
FROM (
    SELECT payer_name, cpt_code, COUNT(*) AS n
    FROM   v_channel_comparison
    GROUP  BY payer_name, cpt_code
    HAVING COUNT(*) > 1
) dups;
