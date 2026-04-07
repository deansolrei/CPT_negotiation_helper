-- 13_fix_duplicates.sql
-- Fixes duplicate rows in intermediary_rates that bypass the UNIQUE constraint
-- because PostgreSQL treats NULL != NULL (multiple NULL effective_dates are allowed).
--
-- Also rewrites v_channel_comparison so each (payer, CPT) pair shows exactly ONE row
-- even if the underlying table has duplicates.
--
-- Run this ONCE from psql:
--   psql -d solrei_cpt -f backend/../13_fix_duplicates.sql
-- or inside psql:
--   \i 13_fix_duplicates.sql


-- ──────────────────────────────────────────────────────────────────
-- 1. Delete duplicate rows from intermediary_rates
--    Keep the row with the highest allowed_amount for each
--    (intermediary_id, payer_name, cpt_code, state, effective_date).
--    For rows where effective_date IS NULL (the common case), keep
--    the one with the largest intermediary_rate_id (most recent insert).
-- ──────────────────────────────────────────────────────────────────
DELETE FROM intermediary_rates
WHERE rate_id NOT IN (
    SELECT MAX(rate_id)
    FROM   intermediary_rates
    GROUP  BY intermediary_id,
              payer_name,
              cpt_code,
              state,
              effective_date   -- NULLs group together in GROUP BY (unlike UNIQUE)
);

-- Confirm how many rows remain
SELECT COUNT(*) AS remaining_rows FROM intermediary_rates;


-- ──────────────────────────────────────────────────────────────────
-- 2. Rewrite v_channel_comparison with deduplication in every CTE
--    Uses MAX(allowed_amount) grouped by (payer_name, cpt_code) so
--    even if duplicates sneak back in, the view always returns one row.
-- ──────────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS v_channel_comparison;
CREATE VIEW v_channel_comparison AS
WITH

-- Direct rates from Solrei's own fee schedule (NPI2 / group entity)
direct_rates AS (
    SELECT
        p.payer_name,
        fsl.cpt_code,
        MAX(fsl.allowed_amount) AS direct_rate
    FROM fee_schedule_lines fsl
    JOIN contracts         c   ON fsl.contract_id = c.contract_id
    JOIN payers            p   ON c.payer_id      = p.payer_id
    JOIN provider_entities pe  ON c.provider_entity_id = pe.provider_entity_id
    WHERE pe.entity_type = 'NPI2'
    GROUP BY p.payer_name, fsl.cpt_code
),

-- Medicare benchmark rates
medicare AS (
    SELECT cpt_code, allowed_amount AS medicare_allowed
    FROM   benchmark_fee_schedule
    WHERE  source_name = 'Medicare 2026'
),

-- All unique (payer_name, cpt_code) combinations across ALL intermediaries
all_combos AS (
    SELECT DISTINCT payer_name, cpt_code
    FROM   intermediary_rates
    WHERE  payer_name IS NOT NULL
),

-- Resolve intermediary payer name → Solrei direct payer name
name_resolved AS (
    SELECT
        ac.payer_name  AS intermediary_payer_name,
        COALESCE(
            ipm.direct_payer_name,
            (SELECT p.payer_name FROM payers p
             WHERE lower(p.payer_name) = lower(ac.payer_name) LIMIT 1)
        ) AS direct_payer_name
    FROM all_combos ac
    LEFT JOIN intermediary_payer_map ipm
           ON ipm.intermediary_payer_name = ac.payer_name
),

-- Headway rates — MAX per (payer_name, cpt_code) prevents duplicate rows
headway AS (
    SELECT ir.payer_name, ir.cpt_code,
           MAX(ir.allowed_amount) AS headway_rate
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Headway' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
    GROUP  BY ir.payer_name, ir.cpt_code
),

-- Alma rates — MAX per (payer_name, cpt_code)
alma AS (
    SELECT ir.payer_name, ir.cpt_code,
           MAX(ir.allowed_amount) AS alma_rate
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Alma' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
    GROUP  BY ir.payer_name, ir.cpt_code
),

-- Grow Therapy rates — MAX per (payer_name, cpt_code)
grow AS (
    SELECT ir.payer_name, ir.cpt_code,
           MAX(ir.allowed_amount) AS grow_rate
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
JOIN  cpt_codes cc  ON cc.cpt_code = ac.cpt_code
LEFT JOIN medicare m ON m.cpt_code = ac.cpt_code
LEFT JOIN name_resolved nr ON nr.intermediary_payer_name = ac.payer_name
LEFT JOIN direct_rates dr ON dr.payer_name = nr.direct_payer_name
                          AND dr.cpt_code  = ac.cpt_code
LEFT JOIN payers p ON p.payer_name = nr.direct_payer_name
LEFT JOIN headway h ON h.payer_name = ac.payer_name AND h.cpt_code = ac.cpt_code
LEFT JOIN alma    a ON a.payer_name = ac.payer_name AND a.cpt_code = ac.cpt_code
LEFT JOIN grow    g ON g.payer_name = ac.payer_name AND g.cpt_code = ac.cpt_code

ORDER BY ac.payer_name, ac.cpt_code;

-- Verify: each (payer_name, cpt_code) should appear exactly once
SELECT payer_name, cpt_code, COUNT(*) AS row_count
FROM   v_channel_comparison
GROUP  BY payer_name, cpt_code
HAVING COUNT(*) > 1
ORDER  BY row_count DESC;
-- (should return 0 rows)
