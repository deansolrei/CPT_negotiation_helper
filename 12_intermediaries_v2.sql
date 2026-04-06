-- 12_intermediaries_v2.sql
-- Migrates the intermediary_rates table to use payer_name (text) instead of
-- a FK to the payers table. This allows intermediaries like Headway to have
-- payers (e.g. BCBS MA, Carelon, Quest) that Solrei doesn't directly contract with.
--
-- Also adds:
--   - intermediary_payer_map: maps Headway/Alma/Grow payer names → Solrei direct payer names
--   - CPT codes 98000–98007 (new 2025 synchronous audio-video telehealth E/M codes)
--   - Rewrites v_channel_comparison to work across ALL payers (not just direct-contract ones)
--
-- Run AFTER 11_intermediaries.sql
-- Then run: python3 backend/load_headway_fl.py


-- ──────────────────────────────────────────────────────────────────
-- 1. Add payer_name (text) column to intermediary_rates
-- ──────────────────────────────────────────────────────────────────
ALTER TABLE intermediary_rates ADD COLUMN IF NOT EXISTS payer_name TEXT;

-- Back-fill payer_name for any existing rows that used payer_id
UPDATE intermediary_rates ir
SET    payer_name = p.payer_name
FROM   payers p
WHERE  ir.payer_id = p.payer_id
  AND  ir.payer_name IS NULL;

-- Drop the old payer_id-based unique constraint and replace with payer_name-based one
-- (PostgreSQL auto-generates the constraint name — cover both truncation possibilities)
ALTER TABLE intermediary_rates
    DROP CONSTRAINT IF EXISTS intermediary_rates_intermediary_id_payer_id_cpt_code_state_eff_key;
ALTER TABLE intermediary_rates
    DROP CONSTRAINT IF EXISTS intermediary_rates_intermediary_id_payer_id_cpt_code_state_effe_key;
ALTER TABLE intermediary_rates
    DROP CONSTRAINT IF EXISTS intermediary_rates_unique;

ALTER TABLE intermediary_rates
    ADD CONSTRAINT intermediary_rates_unique
    UNIQUE (intermediary_id, payer_name, cpt_code, state, effective_date);

-- Add index on payer_name for fast lookups
CREATE INDEX IF NOT EXISTS idx_ir_payer_name ON intermediary_rates(payer_name);


-- ──────────────────────────────────────────────────────────────────
-- 2. Payer name mapping table
-- Maps the payer name as Headway/Alma/Grow uses it → the payer_name
-- in Solrei's direct payers table (NULL if no direct contract exists).
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS intermediary_payer_map (
    map_id                  SERIAL PRIMARY KEY,
    intermediary_payer_name TEXT NOT NULL UNIQUE,   -- as it appears in Headway/Alma CSV
    direct_payer_name       TEXT,                   -- matches payers.payer_name, or NULL
    notes                   TEXT
);

-- Seed known mappings
INSERT INTO intermediary_payer_map (intermediary_payer_name, direct_payer_name, notes)
VALUES
    -- Direct matches
    ('Aetna',                                                   'Aetna',        'Exact match'),
    ('Cigna',                                                   'Cigna',        'Exact match'),
    ('Florida Blue',                                            'Florida Blue', 'Exact match'),
    ('United Healthcare (Optum)',                               'Optum/UHC',    'Optum/UHC in Solrei contracts'),
    ('Oscar (Optum)',                                           'Optum/UHC',    'Oscar routes through Optum network'),
    ('Oxford (Optum)',                                          'Optum/UHC',    'Oxford routes through Optum network'),

    -- No direct Solrei contract (intermediary-only access)
    ('Blue Cross Blue Shield of Massachusetts(Virtual network)', NULL,          'No direct contract — intermediary only'),
    ('Carelon Behavioral Health',                                NULL,          'No direct contract — intermediary only'),
    ('Florida Blue Medicare Advantage',                          NULL,          'Medicare Advantage — separate from commercial FL Blue'),
    ('Horizon Blue Cross and Blue Shield of New Jersey(Virtual network)', NULL, 'NJ virtual network — intermediary only'),
    ('Independence Blue Cross Pennsylvania(Virtual network)',    NULL,          'PA virtual network — intermediary only'),
    ('Quest Behavioral Health',                                  NULL,          'No direct contract — intermediary only'),
    ('Ambetter',                                                'Ambetter',     'Exact match'),
    ('Wellmark Blue Cross Blue Shield',                         'Wellmark Blue Cross Blue Shield', 'Exact match')

ON CONFLICT (intermediary_payer_name) DO UPDATE SET
    direct_payer_name = EXCLUDED.direct_payer_name,
    notes             = EXCLUDED.notes;


-- ──────────────────────────────────────────────────────────────────
-- 3. New CPT codes: 98000–98007
--    Synchronous audio-video telehealth E/M codes (introduced 2025)
--    Note: Medicare does NOT reimburse these separately (status "I").
--    Commercial payers and intermediaries (Headway etc.) do use them.
-- ──────────────────────────────────────────────────────────────────
INSERT INTO cpt_codes (cpt_code, short_description, full_description, category, typical_time_minutes)
VALUES
    ('98000', 'Telehealth E/M new pt, straightforward, 15 min',
     'Synchronous audio-video visit, new patient, straightforward MDM, 15 min',
     'Telehealth E/M', 15),
    ('98001', 'Telehealth E/M new pt, low MDM, 30 min',
     'Synchronous audio-video visit, new patient, low medical decision making, 30 min',
     'Telehealth E/M', 30),
    ('98002', 'Telehealth E/M new pt, moderate MDM, 45 min',
     'Synchronous audio-video visit, new patient, moderate medical decision making, 45 min',
     'Telehealth E/M', 45),
    ('98003', 'Telehealth E/M new pt, high MDM, 60 min',
     'Synchronous audio-video visit, new patient, high medical decision making, 60 min',
     'Telehealth E/M', 60),
    ('98004', 'Telehealth E/M est pt, straightforward, 10 min',
     'Synchronous audio-video visit, established patient, straightforward MDM, 10 min',
     'Telehealth E/M', 10),
    ('98005', 'Telehealth E/M est pt, low MDM, 20 min',
     'Synchronous audio-video visit, established patient, low medical decision making, 20 min',
     'Telehealth E/M', 20),
    ('98006', 'Telehealth E/M est pt, moderate MDM, 30 min',
     'Synchronous audio-video visit, established patient, moderate medical decision making, 30 min',
     'Telehealth E/M', 30),
    ('98007', 'Telehealth E/M est pt, high MDM, 40 min',
     'Synchronous audio-video visit, established patient, high medical decision making, 40 min',
     'Telehealth E/M', 40)
ON CONFLICT (cpt_code) DO UPDATE SET
    short_description = EXCLUDED.short_description,
    full_description  = EXCLUDED.full_description,
    category          = EXCLUDED.category,
    typical_time_minutes = EXCLUDED.typical_time_minutes;


-- ──────────────────────────────────────────────────────────────────
-- 4. Rewrite v_channel_comparison
--    Now works across ALL payers — direct-contract and intermediary-only.
--    Joins direct rates via the payer name mapping table.
-- ──────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_channel_comparison AS
WITH

-- Direct rates from Solrei's own fee schedule (NPI2 / group entity)
direct_rates AS (
    SELECT
        p.payer_name,
        fsl.cpt_code,
        MAX(fsl.allowed_amount) AS direct_rate   -- use MAX in case of modifier duplication
    FROM fee_schedule_lines fsl
    JOIN contracts         c   ON fsl.contract_id = c.contract_id
    JOIN payers            p   ON c.payer_id      = p.payer_id
    JOIN provider_entities pe  ON c.entity_id     = pe.entity_id
    WHERE pe.entity_type = 'NPI2'
    GROUP BY p.payer_name, fsl.cpt_code
),

-- Medicare benchmark rates
medicare AS (
    SELECT cpt_code, allowed_amount AS medicare_allowed
    FROM   benchmark_fee_schedule
    WHERE  benchmark_name = 'Medicare 2026'
),

-- All unique (payer_name, cpt_code) combinations present in any intermediary's rates
all_combos AS (
    SELECT DISTINCT payer_name, cpt_code
    FROM   intermediary_rates
    WHERE  payer_name IS NOT NULL
),

-- Resolve intermediary payer name → Solrei direct payer name (via mapping or exact match)
name_resolved AS (
    SELECT
        ac.payer_name  AS intermediary_payer_name,
        COALESCE(
            ipm.direct_payer_name,
            -- Fallback: check if the name exists verbatim in Solrei payers
            (SELECT p.payer_name FROM payers p
             WHERE lower(p.payer_name) = lower(ac.payer_name) LIMIT 1)
        ) AS direct_payer_name
    FROM all_combos ac
    LEFT JOIN intermediary_payer_map ipm
           ON ipm.intermediary_payer_name = ac.payer_name
),

-- Headway rates (payer-name based)
headway AS (
    SELECT ir.payer_name, ir.cpt_code, ir.allowed_amount AS headway_rate
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Headway' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
),

-- Alma rates
alma AS (
    SELECT ir.payer_name, ir.cpt_code, ir.allowed_amount AS alma_rate
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Alma' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
),

-- Grow Therapy rates
grow AS (
    SELECT ir.payer_name, ir.cpt_code, ir.allowed_amount AS grow_rate
    FROM   intermediary_rates ir
    JOIN   intermediaries i ON ir.intermediary_id = i.intermediary_id
    WHERE  i.name = 'Grow Therapy' AND i.active = TRUE
      AND  (ir.effective_date IS NULL OR ir.effective_date <= CURRENT_DATE)
)

SELECT
    -- Link to Solrei's payer ID if a direct contract exists (for dashboard filters)
    p.payer_id,
    ac.payer_name,
    ac.cpt_code,
    cc.short_description,
    cc.category,
    m.medicare_allowed,

    -- Direct billing rate (NULL if no direct Solrei contract with this payer)
    dr.direct_rate,
    CASE WHEN dr.direct_rate IS NOT NULL AND m.medicare_allowed > 0
         THEN ROUND((dr.direct_rate / m.medicare_allowed * 100)::numeric, 1)
    END AS direct_pct_of_medicare,

    -- Intermediary rates
    h.headway_rate,
    a.alma_rate,
    g.grow_rate,

    -- Which channel pays the most?
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

    -- Convenience: flag whether Solrei has a direct contract with this payer
    CASE WHEN dr.direct_rate IS NOT NULL THEN TRUE ELSE FALSE END AS has_direct_contract

FROM all_combos ac

-- CPT code details
JOIN  cpt_codes cc  ON cc.cpt_code = ac.cpt_code

-- Medicare benchmark
LEFT JOIN medicare m ON m.cpt_code = ac.cpt_code

-- Resolve intermediary payer name → direct payer name
LEFT JOIN name_resolved nr ON nr.intermediary_payer_name = ac.payer_name

-- Direct rate lookup (via resolved name)
LEFT JOIN direct_rates dr ON dr.payer_name = nr.direct_payer_name
                          AND dr.cpt_code  = ac.cpt_code

-- Solrei payer_id (for filter/link to negotiation dashboard)
LEFT JOIN payers p ON p.payer_name = nr.direct_payer_name

-- Intermediary rates
LEFT JOIN headway h ON h.payer_name = ac.payer_name AND h.cpt_code = ac.cpt_code
LEFT JOIN alma    a ON a.payer_name = ac.payer_name AND a.cpt_code = ac.cpt_code
LEFT JOIN grow    g ON g.payer_name = ac.payer_name AND g.cpt_code = ac.cpt_code

ORDER BY ac.payer_name, ac.cpt_code;
