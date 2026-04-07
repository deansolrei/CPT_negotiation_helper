-- 15_fix_channel_dedup.sql
-- The channel comparison still returns 7 rows per (payer, CPT).
-- This script first diagnoses WHICH join is the source, then applies a
-- triple-layer fix that guarantees exactly 1 row per (payer, CPT).
--
-- Run:  psql solrei_cpt -f 15_fix_channel_dedup.sql

-- ── Diagnostic: find which table has 7 rows per CPT ─────────
SELECT '=== DIAGNOSTIC ===' AS info;

SELECT 'benchmark_fee_schedule rows per CPT (Medicare 2026)' AS check, cpt_code, COUNT(*) AS n
FROM benchmark_fee_schedule WHERE source_name = 'Medicare 2026'
GROUP BY cpt_code HAVING COUNT(*) > 1
ORDER BY n DESC LIMIT 5;

SELECT 'cpt_codes rows per cpt_code' AS check, cpt_code, COUNT(*) AS n
FROM cpt_codes GROUP BY cpt_code HAVING COUNT(*) > 1 LIMIT 5;

SELECT 'intermediary_payer_map rows per intermediary_payer_name' AS check,
       intermediary_payer_name, COUNT(*) AS n
FROM intermediary_payer_map
GROUP BY intermediary_payer_name HAVING COUNT(*) > 1 LIMIT 5;

SELECT 'intermediary_rates rows per (intermediary_id, payer_name, cpt_code)' AS check,
       intermediary_id, payer_name, cpt_code, COUNT(*) AS n
FROM intermediary_rates
GROUP BY intermediary_id, payer_name, cpt_code HAVING COUNT(*) > 1 LIMIT 5;

-- ── Fix: rebuild v_channel_comparison with DISTINCT ON everywhere ──
SELECT '=== APPLYING FIX ===' AS info;

DROP VIEW IF EXISTS v_channel_comparison;
CREATE VIEW v_channel_comparison AS
WITH

-- Direct rates: one row per (payer, CPT), highest rate wins
direct_rates AS (
    SELECT p.payer_name, fsl.cpt_code, MAX(fsl.allowed_amount) AS direct_rate
    FROM fee_schedule_lines fsl
    JOIN contracts         c   ON fsl.contract_id = c.contract_id
    JOIN payers            p   ON c.payer_id      = p.payer_id
    JOIN provider_entities pe  ON c.provider_entity_id = pe.provider_entity_id
    WHERE pe.entity_type = 'NPI2'
    GROUP BY p.payer_name, fsl.cpt_code
),

-- Medicare: one row per CPT — MAX guards against multiple locality rows
medicare AS (
    SELECT cpt_code, MAX(allowed_amount) AS medicare_allowed
    FROM   benchmark_fee_schedule
    WHERE  source_name = 'Medicare 2026'
    GROUP  BY cpt_code
),

-- All unique (payer_name, cpt_code) pairs across intermediaries, 12 codes only
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

-- Payer name mapping: one row per intermediary_payer_name (take first match)
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

-- Headway: one row per (payer_name, cpt_code)
headway AS (
    SELECT ir.payer_name, ir.cpt_code, MAX(ir.allowed_amount) AS headway_rate
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Headway' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
    GROUP  BY ir.payer_name, ir.cpt_code
),

-- Alma: one row per (payer_name, cpt_code)
alma AS (
    SELECT ir.payer_name, ir.cpt_code, MAX(ir.allowed_amount) AS alma_rate
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Alma' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
    GROUP  BY ir.payer_name, ir.cpt_code
),

-- Grow Therapy: one row per (payer_name, cpt_code)
grow AS (
    SELECT ir.payer_name, ir.cpt_code, MAX(ir.allowed_amount) AS grow_rate
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Grow Therapy' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
    GROUP  BY ir.payer_name, ir.cpt_code
),

-- Combine everything — one candidate row per (payer_name, cpt_code)
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

-- Final DISTINCT ON as absolute guarantee: one row per (payer, CPT)
SELECT DISTINCT ON (payer_name, cpt_code)
    payer_id, payer_name, cpt_code, short_description, category,
    medicare_allowed, direct_rate, direct_pct_of_medicare,
    headway_rate, alma_rate, grow_rate,
    best_channel_type, has_direct_contract
FROM combined
ORDER BY payer_name, cpt_code;

-- ── Verify ───────────────────────────────────────────────────
SELECT
    COUNT(*)                                             AS total_rows,
    COUNT(DISTINCT (payer_name, cpt_code))               AS unique_payer_cpt_pairs,
    (SELECT COUNT(*) FROM (
        SELECT payer_name, cpt_code FROM v_channel_comparison
        GROUP BY payer_name, cpt_code HAVING COUNT(*) > 1
    ) d)                                                 AS duplicate_pairs
FROM v_channel_comparison;
-- total_rows should equal unique_payer_cpt_pairs, duplicate_pairs should be 0
