-- =============================================================
-- 23_add_regence_oregon.sql  (v2 — fixed for actual schema)
-- Adds Regence BlueCross BlueShield of Oregon as a direct-billing
-- payer in Payer Summary and Rate Comparison.
-- Rates from MASTER col R, effective 3/30/26:
--   99214=$161  99215=$216  90833=$108  90836=$137  90838=$181
-- Run: psql solrei_cpt -f sql/23_add_regence_oregon.sql
-- =============================================================

-- 1. Insert Regence as a payer (no unique constraint on payer_name,
--    so guard with NOT EXISTS)
INSERT INTO payers (payer_name, payer_display_name, payer_type, payer_notes)
SELECT
  'Regence BlueCross BlueShield of Oregon',
  'Regence BCBS Oregon (Direct)',
  'Commercial',
  'Direct billing — Oregon MAC 0230299/0230201. Rates from MASTER col R, 3/30/26.'
WHERE NOT EXISTS (
  SELECT 1 FROM payers WHERE payer_name = 'Regence BlueCross BlueShield of Oregon'
);

-- 2. Create one contract per provider entity
INSERT INTO contracts
  (payer_id, provider_entity_id, product_line, line_of_business,
   effective_date, active, notes)
SELECT
  p.payer_id,
  pe.provider_entity_id,
  'Commercial PPO',
  'Regence BlueCross BlueShield of Oregon — Direct',
  '2026-03-30',
  TRUE,
  'Direct contract — Oregon. Effective 3/30/26.'
FROM payers p
CROSS JOIN provider_entities pe
WHERE p.payer_name = 'Regence BlueCross BlueShield of Oregon'
  AND NOT EXISTS (
    SELECT 1 FROM contracts c2
    WHERE c2.payer_id          = p.payer_id
      AND c2.provider_entity_id = pe.provider_entity_id
  );

-- 3. Add fee schedule lines for the 5 core CPT codes
INSERT INTO fee_schedule_lines
  (contract_id, cpt_code, unit_type, allowed_amount, effective_date, notes)
SELECT
  c.contract_id,
  cpt.cpt_code,
  'per_service',
  cpt.rate,
  '2026-03-30',
  'Regence BCBS Oregon direct rate — MASTER col R 3/30/26'
FROM contracts c
JOIN payers p ON c.payer_id = p.payer_id
CROSS JOIN (VALUES
  ('99214', 161.00),
  ('99215', 216.00),
  ('90833', 108.00),
  ('90836', 137.00),
  ('90838', 181.00)
) AS cpt(cpt_code, rate)
WHERE p.payer_name = 'Regence BlueCross BlueShield of Oregon'
ON CONFLICT (contract_id, cpt_code, modifier, place_of_service, effective_date)
DO UPDATE SET
  allowed_amount = EXCLUDED.allowed_amount,
  notes          = EXCLUDED.notes;

-- 4. Verify — show what was inserted
SELECT
  p.payer_name,
  pe.legal_name   AS provider,
  fl.cpt_code,
  fl.allowed_amount,
  fl.effective_date
FROM fee_schedule_lines fl
JOIN contracts         c  ON fl.contract_id        = c.contract_id
JOIN payers            p  ON c.payer_id             = p.payer_id
JOIN provider_entities pe ON c.provider_entity_id   = pe.provider_entity_id
WHERE p.payer_name = 'Regence BlueCross BlueShield of Oregon'
ORDER BY pe.legal_name, fl.cpt_code;
