-- ============================================================
-- 26_fee_schedule_state.sql
-- Adds state-awareness to fee_schedule_lines so direct billing
-- rates can vary by state (e.g., Aetna FL vs Aetna MN).
-- Updates the channel comparison direct_rates CTE to filter
-- by the active state setting.
-- ============================================================

-- 1. Add state column (nullable — NULL = applies to all states)
ALTER TABLE fee_schedule_lines
    ADD COLUMN IF NOT EXISTS state CHAR(2) DEFAULT NULL;

-- 2. Replace unique constraint to include state
ALTER TABLE fee_schedule_lines
    DROP CONSTRAINT IF EXISTS fee_schedule_lines_contract_id_cpt_code_modifier_place_of_s_key;

ALTER TABLE fee_schedule_lines
    DROP CONSTRAINT IF EXISTS fee_schedule_lines_unique;

ALTER TABLE fee_schedule_lines
    ADD CONSTRAINT fee_schedule_lines_unique
    UNIQUE (contract_id, cpt_code, modifier, place_of_service, state, effective_date);

-- 3. Existing rows (Regence etc.) keep state = NULL → visible in all states
-- Tag them properly with their actual state for accuracy
UPDATE fee_schedule_lines fsl
SET state = 'OR'
FROM contracts c
JOIN payers p ON p.payer_id = c.payer_id
WHERE fsl.contract_id = c.contract_id
  AND fsl.state IS NULL
  AND p.payer_name = 'Regence BlueCross BlueShield of Oregon';

-- 4. Refresh the multistate views so the direct_rates CTE respects state
-- (Full SQL from 22_multistate_views.sql — only direct_rates CTE is changed here;
--  run this file after 22_multistate_views.sql is already applied.)

-- Refresh v_channel_comparison to add state filter on direct_rates
CREATE OR REPLACE VIEW v_channel_comparison AS
WITH
direct_rates AS (
    SELECT DISTINCT ON (p.payer_name, fsl.cpt_code)
        p.payer_name,
        fsl.cpt_code,
        fsl.allowed_amount AS direct_rate
    FROM fee_schedule_lines fsl
    JOIN contracts         c   ON fsl.contract_id      = c.contract_id
    JOIN payers            p   ON c.payer_id           = p.payer_id
    JOIN provider_entities pe  ON c.provider_entity_id = pe.provider_entity_id
    WHERE c.active = TRUE
      AND (c.end_date   IS NULL OR c.end_date   >= CURRENT_DATE)
      AND (fsl.end_date IS NULL OR fsl.end_date >= CURRENT_DATE)
      AND (
          fsl.state IS NULL
          OR fsl.state = COALESCE(NULLIF(current_setting('app.benchmark_locality', TRUE), ''), 'FL')
      )
    ORDER BY p.payer_name, fsl.cpt_code,
        CASE pe.entity_type WHEN 'NPI1' THEN 0 ELSE 1 END,
        CASE WHEN fsl.state IS NOT NULL THEN 0 ELSE 1 END,
        fsl.allowed_amount DESC
),
medicare AS (
    SELECT cpt_code, allowed_amount AS medicare_allowed
    FROM   benchmark_fee_schedule
    WHERE  source_name    = 'Medicare 2026'
      AND  effective_year = 2026
      AND  locality = COALESCE(NULLIF(current_setting('app.benchmark_locality', TRUE), ''), 'FL')
),
channel_cpts AS (
    SELECT unnest(ARRAY[
        '99214','99215','90833','90836','90838',
        '99204','99205','90785',
        '98002','98003','98006','98007'
    ]) AS cpt_code
),
all_combos AS (
    SELECT DISTINCT ir.payer_name, ir.cpt_code
    FROM   intermediary_rates ir
    WHERE  ir.payer_name IS NOT NULL
      AND  ir.cpt_code IN (SELECT cpt_code FROM channel_cpts)
    UNION
    SELECT DISTINCT p.payer_name, fsl.cpt_code
    FROM   fee_schedule_lines fsl
    JOIN   contracts c ON fsl.contract_id = c.contract_id
    JOIN   payers    p ON c.payer_id      = p.payer_id
    WHERE  c.active = TRUE
      AND (c.end_date   IS NULL OR c.end_date   >= CURRENT_DATE)
      AND (fsl.end_date IS NULL OR fsl.end_date >= CURRENT_DATE)
      AND  fsl.cpt_code IN (SELECT cpt_code FROM channel_cpts)
),
name_resolved AS (
    SELECT DISTINCT ON (ac.payer_name)
        ac.payer_name AS intermediary_payer_name,
        COALESCE(
            ipm.direct_payer_name,
            (SELECT p2.payer_name FROM payers p2
             WHERE lower(p2.payer_name) = lower(ac.payer_name) LIMIT 1)
        ) AS direct_payer_name
    FROM  all_combos ac
    LEFT JOIN intermediary_payer_map ipm ON ipm.intermediary_payer_name = ac.payer_name
    ORDER BY ac.payer_name, ipm.direct_payer_name NULLS LAST
),
headway AS (
    SELECT DISTINCT ON (ir.payer_name, ir.cpt_code)
        ir.payer_name, ir.cpt_code,
        ir.allowed_amount AS headway_rate, ir.updated_at AS headway_updated_at
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Headway' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
      AND  ir.state = COALESCE(NULLIF(current_setting('app.benchmark_locality', TRUE), ''), 'FL')
    ORDER BY ir.payer_name, ir.cpt_code, ir.allowed_amount DESC
),
alma AS (
    SELECT DISTINCT ON (ir.payer_name, ir.cpt_code)
        ir.payer_name, ir.cpt_code,
        ir.allowed_amount AS alma_rate, ir.updated_at AS alma_updated_at
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Alma' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
      AND  ir.state = COALESCE(NULLIF(current_setting('app.benchmark_locality', TRUE), ''), 'FL')
    ORDER BY ir.payer_name, ir.cpt_code, ir.allowed_amount DESC
),
grow AS (
    SELECT DISTINCT ON (ir.payer_name, ir.cpt_code)
        ir.payer_name, ir.cpt_code,
        ir.allowed_amount AS grow_rate, ir.updated_at AS grow_updated_at
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
        h.headway_rate,    h.headway_updated_at,
        a.alma_rate,       a.alma_updated_at,
        g.grow_rate,       g.grow_updated_at,
        LEAST(h.headway_updated_at, a.alma_updated_at, g.grow_updated_at) AS oldest_intermediary_update,
        CASE
            WHEN GREATEST(COALESCE(dr.direct_rate,0),COALESCE(h.headway_rate,0),
                          COALESCE(a.alma_rate,0),COALESCE(g.grow_rate,0)) = 0 THEN 'No Data'
            WHEN COALESCE(dr.direct_rate,0) >= COALESCE(h.headway_rate,0)
             AND COALESCE(dr.direct_rate,0) >= COALESCE(a.alma_rate,0)
             AND COALESCE(dr.direct_rate,0) >= COALESCE(g.grow_rate,0)
             AND dr.direct_rate IS NOT NULL THEN 'Direct'
            ELSE 'Intermediary'
        END AS best_channel_type,
        CASE WHEN dr.direct_rate IS NOT NULL THEN TRUE ELSE FALSE END AS has_direct_contract
    FROM  all_combos ac
    JOIN  cpt_codes       cc ON cc.cpt_code  = ac.cpt_code
    LEFT JOIN medicare     m  ON m.cpt_code   = ac.cpt_code
    LEFT JOIN name_resolved nr ON nr.intermediary_payer_name = ac.payer_name
    LEFT JOIN direct_rates dr ON dr.payer_name = nr.direct_payer_name AND dr.cpt_code = ac.cpt_code
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
