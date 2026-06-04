-- 21_fix_channel_all_payers.sql
-- Fix: v_channel_comparison was invisible to payers that have a direct
-- contract but no intermediary (Headway / Alma / Grow Therapy) rates.
--
-- Root cause: the all_combos CTE was driven solely by intermediary_rates.
-- If a payer like Wellmark Iowa has no rows in intermediary_rates, it
-- never enters the view — direct_rate stays NULL and the payer is absent.
--
-- Fix: expand all_combos to UNION direct contract payers with intermediary
-- payers. Payers appear whether they are on intermediaries, direct, or both.
--
-- Run: psql solrei_cpt -f 21_fix_channel_all_payers.sql

SELECT '=== Rebuilding v_channel_comparison — all direct-contract payers included ===' AS info;

CREATE OR REPLACE VIEW v_channel_comparison AS
WITH

-- Direct rates: prefer NPI1 (individual provider), fall back to NPI2.
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

-- Medicare: one row per CPT
medicare AS (
    SELECT cpt_code, MAX(allowed_amount) AS medicare_allowed
    FROM   benchmark_fee_schedule
    WHERE  source_name = 'Medicare 2026'
    GROUP  BY cpt_code
),

-- All unique (payer_name, cpt_code) pairs — from BOTH intermediaries AND
-- direct contracts. This ensures every payer with a direct contract appears
-- in the Channel Comparison, even if they have no intermediary rates.
all_combos AS (
    -- Payers appearing in intermediary rate data (Headway / Alma / Grow)
    SELECT DISTINCT payer_name, cpt_code
    FROM   intermediary_rates
    WHERE  payer_name IS NOT NULL
      AND  cpt_code IN (
               '99214','99215','90833','90836','90838',
               '99204','99205','90785',
               '98002','98003','98006','98007'
           )

    UNION

    -- Payers with direct contracts (so direct-only payers are included)
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

-- Map each payer_name (as used in all_combos) to the canonical DB payer_name.
-- For intermediary-sourced names, use intermediary_payer_map; otherwise fall
-- back to a case-insensitive match against the payers table.
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
    headway_rate, alma_rate, grow_rate,
    best_channel_type, has_direct_contract
FROM combined
ORDER BY payer_name, cpt_code;

-- ── Verify ────────────────────────────────────────────────────────────────────
SELECT
    payer_name,
    COUNT(DISTINCT cpt_code)                                     AS cpt_codes,
    COUNT(*) FILTER (WHERE direct_rate   IS NOT NULL)            AS has_direct,
    COUNT(*) FILTER (WHERE headway_rate  IS NOT NULL)            AS has_headway,
    COUNT(*) FILTER (WHERE alma_rate     IS NOT NULL)            AS has_alma,
    COUNT(*) FILTER (WHERE grow_rate     IS NOT NULL)            AS has_grow
FROM v_channel_comparison
GROUP BY payer_name
ORDER BY payer_name;
-- Wellmark Iowa should now appear with has_direct > 0
