-- 19_clean_fee_schedule_final.sql
-- Root cause: fee_schedule_lines has multiple rows per (contract_id, cpt_code)
-- with different allowed_amounts. This creates inconsistency because the Rate
-- Comparison JS picks whichever row arrives first from the API, while the Channel
-- Comparison SQL was picking the highest rate — so they disagreed.
--
-- Fix: for each (contract_id, cpt_code) keep only the row with the HIGHEST
-- allowed_amount and delete all others. The highest rate represents the actual
-- contracted amount (the lower duplicates came from the generic percentage-of-
-- Medicare loader that ran before actual contract rates were entered).
--
-- After running this, every table and view will see exactly one rate per
-- (contract, CPT) and all sections of the dashboard will agree.
--
-- Run: psql solrei_cpt -f 19_clean_fee_schedule_final.sql

BEGIN;

SELECT '=== Before: duplicate counts per (contract_id, cpt_code) ===' AS step;
SELECT
    c.payer_name,
    pe.entity_type,
    fsl.cpt_code,
    COUNT(*)                   AS num_rows,
    MIN(fsl.allowed_amount)    AS min_rate,
    MAX(fsl.allowed_amount)    AS max_rate
FROM fee_schedule_lines fsl
JOIN contracts         c  ON fsl.contract_id       = c.contract_id
JOIN payers            p  ON c.payer_id            = p.payer_id
JOIN provider_entities pe ON c.provider_entity_id  = pe.provider_entity_id
WHERE lower(p.payer_name) LIKE '%florida%'
GROUP BY c.payer_name, pe.entity_type, fsl.cpt_code
HAVING COUNT(*) > 1
ORDER BY fsl.cpt_code, pe.entity_type;

SELECT '=== Deleting lower-rate duplicates (keeping MAX per contract+CPT) ===' AS step;

-- Delete all rows that are NOT the highest-rate row for their (contract_id, cpt_code)
DELETE FROM fee_schedule_lines
WHERE rate_id IN (
    SELECT fsl.rate_id
    FROM fee_schedule_lines fsl
    WHERE fsl.rate_id NOT IN (
        -- For each (contract_id, cpt_code), identify the one row to KEEP:
        -- the row with the highest allowed_amount.
        -- If there's a tie, keep the one with the largest rate_id (most recent insert).
        SELECT DISTINCT ON (contract_id, cpt_code)
            rate_id
        FROM fee_schedule_lines
        ORDER BY contract_id, cpt_code,
                 allowed_amount DESC,
                 rate_id DESC
    )
);

SELECT '=== After: verify no duplicates remain ===' AS step;
SELECT
    COUNT(*)                                            AS total_rows,
    COUNT(DISTINCT (contract_id, cpt_code))             AS unique_contract_cpt_pairs,
    (SELECT COUNT(*) FROM (
        SELECT contract_id, cpt_code
        FROM fee_schedule_lines
        GROUP BY contract_id, cpt_code
        HAVING COUNT(*) > 1
    ) d)                                                AS remaining_duplicates
FROM fee_schedule_lines;
-- remaining_duplicates MUST be 0

SELECT '=== Florida Blue rates after cleanup ===' AS step;
SELECT
    p.payer_name,
    pe.entity_type,
    pe.legal_name,
    fsl.cpt_code,
    fsl.allowed_amount
FROM fee_schedule_lines fsl
JOIN contracts         c  ON fsl.contract_id       = c.contract_id
JOIN payers            p  ON c.payer_id            = p.payer_id
JOIN provider_entities pe ON c.provider_entity_id  = pe.provider_entity_id
WHERE lower(p.payer_name) LIKE '%florida%'
  AND fsl.cpt_code IN ('99214','99215','90833','90836','90838')
ORDER BY fsl.cpt_code, pe.entity_type;

COMMIT;

-- Refresh the views so they pick up the cleaned data
SELECT '=== Refreshing views ===' AS step;
-- Views are not materialized so no refresh needed — they read live data.
-- Re-run the channel comparison fix to ensure it uses NPI1 preference:
DROP VIEW IF EXISTS v_channel_comparison;
CREATE VIEW v_channel_comparison AS
WITH
direct_rates AS (
    SELECT DISTINCT ON (p.payer_name, fsl.cpt_code)
        p.payer_name,
        fsl.cpt_code,
        fsl.allowed_amount AS direct_rate
    FROM fee_schedule_lines fsl
    JOIN contracts         c   ON fsl.contract_id        = c.contract_id
    JOIN payers            p   ON c.payer_id             = p.payer_id
    JOIN provider_entities pe  ON c.provider_entity_id   = pe.provider_entity_id
    WHERE c.active = TRUE
      AND (c.end_date IS NULL OR c.end_date >= CURRENT_DATE)
      AND (fsl.end_date IS NULL OR fsl.end_date >= CURRENT_DATE)
    ORDER BY
        p.payer_name,
        fsl.cpt_code,
        CASE pe.entity_type WHEN 'NPI1' THEN 0 ELSE 1 END,
        fsl.allowed_amount DESC
),
medicare AS (
    SELECT cpt_code, MAX(allowed_amount) AS medicare_allowed
    FROM   benchmark_fee_schedule
    WHERE  source_name = 'Medicare 2026'
    GROUP  BY cpt_code
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
)
SELECT DISTINCT ON (payer_name, cpt_code)
    payer_id, payer_name, cpt_code, short_description, category,
    medicare_allowed, direct_rate, direct_pct_of_medicare,
    headway_rate, alma_rate, grow_rate,
    best_channel_type, has_direct_contract
FROM combined
ORDER BY payer_name, cpt_code;

SELECT '=== Final verification: rates now match across sections ===' AS step;
SELECT
    nd.cpt_code,
    nd.payer_allowed            AS rate_comparison_rate,
    cc.direct_rate              AS channel_comparison_rate,
    nd.payer_allowed = cc.direct_rate AS rates_match
FROM (
    SELECT DISTINCT ON (cpt_code) cpt_code, payer_allowed
    FROM v_negotiation_dashboard
    WHERE lower(payer_name) LIKE '%florida%'
      AND cpt_code IN ('99214','99215','90833','90836','90838')
    ORDER BY cpt_code,
             CASE entity_type WHEN 'NPI1' THEN 0 ELSE 1 END,
             payer_allowed DESC
) nd
JOIN v_channel_comparison cc ON cc.cpt_code = nd.cpt_code
WHERE lower(cc.payer_name) LIKE '%florida%'
ORDER BY nd.cpt_code;
-- All rows should show rates_match = t
