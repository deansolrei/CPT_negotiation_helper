-- ============================================================
-- 29_rename_payers_v8.sql
-- Comprehensive payer rename and cleanup for v3 MASTER naming.
--
-- GOAL: Every Blue Cross / Blue Shield entry in the DB must
-- be prefixed with 'BCBS - ' and match the exact names used
-- in populate_slave_v8.gs. All old-name duplicates are removed.
--
-- SAFE TO RUN MULTIPLE TIMES (UPDATE/DELETE WHERE old_name
-- no longer exists is a no-op).
--
-- RECOMMENDED ORDER:
--   1. Import fresh CSVs from populate_slave_v8 run
--   2. Run this script
--   3. Verify with the SELECT statements at the bottom
-- ============================================================


-- ════════════════════════════════════════════════════════════
-- SECTION 1: intermediary_rates — targeted renames first
--   (rename before the bulk delete so nothing is lost)
-- ════════════════════════════════════════════════════════════

-- ── Non-BCBS renames ────────────────────────────────────────
UPDATE intermediary_rates SET payer_name = 'UHC / Oscar / Optum'
  WHERE payer_name IN ('UHC/Oscar/Optum', 'Optum/UHC/Oscar');

-- ── BCBS - Florida Blue ─────────────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Florida Blue'
  WHERE payer_name IN (
    'Florida Blue',
    'BCBS - Florida',
    'Blue Cross Blue Shield of Florida',
    'Florida Blue Cross Blue Shield'
  );

-- ── BCBS - Florida Blue Medicare Advantage ──────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Florida Blue Medicare Advantage'
  WHERE payer_name IN (
    'Florida Blue Medicare Advantage',
    'Florida Blue (Medicare Advantage)',
    'BCBS - Florida Blue (Medicare Advantage)'
  );

-- ── BCBS - of Arizona ───────────────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - of Arizona'
  WHERE payer_name IN (
    'Blue Cross Blue Shield of Arizona',
    'Blue Cross and Blue Shield of Arizona',
    'BCBS Arizona',
    'BCBS of Arizona'
  );

-- ── BCBS - of Massachusetts ─────────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - of Massachusetts'
  WHERE payer_name IN (
    'Blue Cross Blue Shield of Massachusetts',
    'Blue Cross and Blue Shield of Massachusetts',
    'BCBS Massachusetts',
    'BCBS - Massachusetts (virtual network)'
  );

-- ── BCBS - of Minnesota ─────────────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - of Minnesota'
  WHERE payer_name IN (
    'Blue Cross and Blue Shield of Minnesota',
    'Blue Cross Blue Shield of Minnesota',
    'BCBS Minnesota',
    'BCBS of Minnesota'
  );

-- ── BCBS - Minnesota Medicaid ───────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Minnesota Medicaid'
  WHERE payer_name IN (
    'Blue Cross and Blue Shield of Minnesota Medicaid',
    'Blue Cross Blue Shield of Minnesota Medicaid',
    'BCBS Minnesota Medicaid'
  );

-- ── BCBS - Minnesota Medicaid Advantage ─────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Minnesota Medicaid Advantage'
  WHERE payer_name IN (
    'Blue Cross and Blue Shield of Minnesota Medicaid Advantage',
    'Blue Cross and Blue Shield of Minnesota Medicare Advantage',
    'Blue Cross Blue Shield of Minnesota Medicare Advantage',
    'BCBS Minnesota Medicaid Advantage',
    'BCBS Minnesota Medicare Advantage'
  );

-- ── BCBS - Anthem (Colorado HMO) ────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Anthem (Colorado HMO)'
  WHERE payer_name IN (
    'Anthem BCBS Colorado HMO',
    'Anthem Blue Cross Blue Shield Colorado HMO',
    'Anthem Blue Cross and Blue Shield Colorado HMO'
  );

-- ── BCBS - Anthem (Colorado PPO) ────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Anthem (Colorado PPO)'
  WHERE payer_name IN (
    'Anthem BCBS Colorado PPO',
    'Anthem Blue Cross Blue Shield Colorado PPO',
    'Anthem Blue Cross and Blue Shield Colorado PPO'
  );

-- ── BCBS - Anthem (Connecticut) ─────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Anthem (Connecticut)'
  WHERE payer_name IN (
    'Anthem Blue Cross and Blue Shield',
    'Anthem Blue Cross Blue Shield (Connecticut)',
    'Anthem Blue Cross and Blue Shield Connecticut',
    'Anthem BCBS Connecticut'
  )
  AND state = 'CT';

-- ── BCBS - Anthem (Indiana) ─────────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Anthem (Indiana)'
  WHERE payer_name IN (
    'Anthem Blue Cross Blue Shield (Indiana)',
    'Anthem Blue Cross and Blue Shield Indiana',
    'Anthem BCBS Indiana'
  );

-- ── BCBS - Anthem (Maine) ───────────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Anthem (Maine)'
  WHERE payer_name IN (
    'Anthem Blue Cross and Blue Shield Maine',
    'Anthem Blue Cross Blue Shield (Maine)',
    'Anthem BCBS Maine'
  );

-- ── BCBS - Anthem (Nevada) ──────────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Anthem (Nevada)'
  WHERE payer_name IN (
    'Anthem Blue Cross and Blue Shield',
    'Anthem Blue Cross Blue Shield (Nevada)',
    'Anthem Blue Cross and Blue Shield Nevada',
    'Anthem BCBS Nevada'
  )
  AND state = 'NV';

-- ── BCBS - Anthem (New Hampshire) ───────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Anthem (New Hampshire)'
  WHERE payer_name IN (
    'Anthem Blue Cross and Blue Shield',
    'Anthem Blue Cross Blue Shield (New Hampshire)',
    'Anthem Blue Cross and Blue Shield New Hampshire',
    'Anthem BCBS New Hampshire'
  )
  AND state = 'NH';

-- ── Remove the generic 'BCBS - Anthem (Colorado)' that was
--    replaced by explicit HMO / PPO entries above ────────────
DELETE FROM intermediary_rates
  WHERE payer_name IN (
    'BCBS - Anthem (Colorado)',
    'Anthem Blue Cross and Blue Shield',
    'Anthem Blue Cross and Blue Shield Colorado'
  )
  AND state = 'CO';

-- ── BCBS - Horizon (New Jersey) ─────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Horizon (New Jersey)'
  WHERE payer_name IN (
    'Horizon Blue Cross and Blue Shield of New Jersey',
    'Horizon Blue Cross Blue Shield of New Jersey',
    'Horizon BCBS New Jersey',
    'Horizon BCBS NJ'
  );

-- ── BCBS - Independence (Pennsylvania) ──────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Independence (Pennsylvania)'
  WHERE payer_name IN (
    'Independence Blue Cross Pennsylvania',
    'Independence Blue Cross (Pennsylvania)',
    'Independence Blue Cross',
    'Independence BCBS Pennsylvania'
  );

-- ── BCBS - Premera (Washington) ─────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Premera (Washington)'
  WHERE payer_name IN (
    'Premera Blue Cross Washington',
    'Premera Blue Cross',
    'Premera BCBS Washington'
  );

-- ── BCBS - Regence (Washington) ─────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Regence (Washington)'
  WHERE payer_name IN (
    'Regence BlueShield of Washington',
    'Regence BlueShield (Washington)',
    'Regence BCBS Washington'
  );

-- ── BCBS - Regence (Oregon) ─────────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Regence (Oregon)'
  WHERE payer_name IN (
    'Regence BlueCross BlueShield of Oregon',
    'Regence BlueShield of Oregon',
    'Regence BCBS Oregon'
  );

-- ── BCBS - Wellmark (Iowa) ──────────────────────────────────
UPDATE intermediary_rates SET payer_name = 'BCBS - Wellmark (Iowa)'
  WHERE payer_name IN (
    'Wellmark',
    'BCBS - Wellmark',
    'Wellmark Iowa',
    'Wellmark Blue Cross Blue Shield',
    'Wellmark Blue Cross and Blue Shield of Iowa'
  );


-- ════════════════════════════════════════════════════════════
-- SECTION 2: intermediary_rates — bulk delete remaining
--   Blue Cross / Blue Shield variants not prefixed with 'BCBS -'
--   These are duplicate orphans from the original dashboard import.
-- ════════════════════════════════════════════════════════════

DELETE FROM intermediary_rates
  WHERE (
       payer_name ILIKE '%blue cross%'
    OR payer_name ILIKE '%blue shield%'
    OR payer_name ILIKE '%bluecross%'
    OR payer_name ILIKE '%blueshield%'
    OR payer_name ILIKE 'Anthem %'
    OR payer_name ILIKE 'Florida Blue%'
    OR payer_name ILIKE 'Horizon Blue%'
    OR payer_name ILIKE 'Independence Blue%'
    OR payer_name ILIKE 'Premera %'
    OR payer_name ILIKE 'Regence %'
    OR payer_name ILIKE 'Wellmark%'
  )
  AND payer_name NOT LIKE 'BCBS - %';


-- ════════════════════════════════════════════════════════════
-- SECTION 3: payers table — rename for direct billing
--   (used by fee_schedule_lines / SBH clinic-submit rates)
-- ════════════════════════════════════════════════════════════

DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN SELECT * FROM (VALUES
    ('Optum/UHC/Oscar',                              'UHC / Oscar / Optum'),
    ('UHC/Oscar/Optum',                              'UHC / Oscar / Optum'),
    ('Florida Blue',                                 'BCBS - Florida Blue'),
    ('BCBS - Florida',                               'BCBS - Florida Blue'),
    ('Florida Blue Medicare Advantage',              'BCBS - Florida Blue Medicare Advantage'),
    ('Blue Cross Blue Shield of Arizona',            'BCBS - of Arizona'),
    ('Blue Cross and Blue Shield of Arizona',        'BCBS - of Arizona'),
    ('Blue Cross Blue Shield of Massachusetts',      'BCBS - of Massachusetts'),
    ('Blue Cross and Blue Shield of Massachusetts',  'BCBS - of Massachusetts'),
    ('BCBS - Massachusetts (virtual network)',       'BCBS - of Massachusetts'),
    ('Blue Cross and Blue Shield of Minnesota',      'BCBS - of Minnesota'),
    ('Blue Cross Blue Shield of Minnesota',          'BCBS - of Minnesota'),
    ('Anthem Blue Cross Blue Shield (Indiana)',      'BCBS - Anthem (Indiana)'),
    ('Anthem Blue Cross and Blue Shield Indiana',    'BCBS - Anthem (Indiana)'),
    ('Horizon Blue Cross and Blue Shield of New Jersey', 'BCBS - Horizon (New Jersey)'),
    ('Horizon Blue Cross Blue Shield of New Jersey', 'BCBS - Horizon (New Jersey)'),
    ('Independence Blue Cross Pennsylvania',         'BCBS - Independence (Pennsylvania)'),
    ('Independence Blue Cross (Pennsylvania)',       'BCBS - Independence (Pennsylvania)'),
    ('Independence Blue Cross',                      'BCBS - Independence (Pennsylvania)'),
    ('Premera Blue Cross Washington',                'BCBS - Premera (Washington)'),
    ('Premera Blue Cross',                           'BCBS - Premera (Washington)'),
    ('Regence BlueShield of Washington',             'BCBS - Regence (Washington)'),
    ('Regence BlueShield (Washington)',              'BCBS - Regence (Washington)'),
    ('Regence BlueCross BlueShield of Oregon',       'BCBS - Regence (Oregon)'),
    ('Regence BlueShield of Oregon',                 'BCBS - Regence (Oregon)'),
    ('Wellmark',                                     'BCBS - Wellmark (Iowa)'),
    ('BCBS - Wellmark',                              'BCBS - Wellmark (Iowa)'),
    ('Wellmark Iowa',                                'BCBS - Wellmark (Iowa)'),
    ('Wellmark Blue Cross Blue Shield',              'BCBS - Wellmark (Iowa)'),
    ('Anthem BCBS Colorado HMO',                     'BCBS - Anthem (Colorado HMO)'),
    ('Anthem Blue Cross Blue Shield Colorado HMO',   'BCBS - Anthem (Colorado HMO)'),
    ('Anthem BCBS Colorado PPO',                     'BCBS - Anthem (Colorado PPO)'),
    ('Anthem Blue Cross Blue Shield Colorado PPO',   'BCBS - Anthem (Colorado PPO)'),
    ('BCBS - Anthem (Colorado)',                     NULL)  -- NULL = delete, no longer valid
  ) AS t(old_name, new_name)
  LOOP
    DECLARE
      old_id  INTEGER;
      new_id  INTEGER;
    BEGIN
      SELECT payer_id INTO old_id FROM payers WHERE payer_name = r.old_name;
      IF old_id IS NULL THEN
        RAISE NOTICE 'Payer not found (already renamed or never existed): %', r.old_name;
        CONTINUE;
      END IF;

      IF r.new_name IS NULL THEN
        -- Delete obsolete payer (e.g. generic 'BCBS - Anthem (Colorado)')
        DELETE FROM contracts WHERE payer_id = old_id;
        DELETE FROM payers WHERE payer_id = old_id;
        RAISE NOTICE 'Deleted obsolete payer: %', r.old_name;
        CONTINUE;
      END IF;

      SELECT payer_id INTO new_id FROM payers WHERE payer_name = r.new_name;

      IF new_id IS NOT NULL THEN
        -- Target already exists — merge: re-point contracts, delete old row
        UPDATE contracts SET payer_id = new_id WHERE payer_id = old_id;
        DELETE FROM payers WHERE payer_id = old_id;
        RAISE NOTICE 'Merged payer "%" (id=%) into "%" (id=%)', r.old_name, old_id, r.new_name, new_id;
      ELSE
        -- Simple rename
        UPDATE payers SET payer_name = r.new_name WHERE payer_id = old_id;
        RAISE NOTICE 'Renamed payer "%" → "%"', r.old_name, r.new_name;
      END IF;
    END;
  END LOOP;
END $$;

-- Bulk delete remaining Blue Cross / Blue Shield orphans in payers table
DELETE FROM contracts
  WHERE payer_id IN (
    SELECT payer_id FROM payers
    WHERE (
           payer_name ILIKE '%blue cross%'
        OR payer_name ILIKE '%blue shield%'
        OR payer_name ILIKE '%bluecross%'
        OR payer_name ILIKE '%blueshield%'
        OR payer_name ILIKE 'Anthem %'
        OR payer_name ILIKE 'Florida Blue%'
        OR payer_name ILIKE 'Horizon Blue%'
        OR payer_name ILIKE 'Independence Blue%'
        OR payer_name ILIKE 'Premera %'
        OR payer_name ILIKE 'Regence %'
        OR payer_name ILIKE 'Wellmark%'
    )
    AND payer_name NOT LIKE 'BCBS - %'
  );

DELETE FROM payers
  WHERE (
       payer_name ILIKE '%blue cross%'
    OR payer_name ILIKE '%blue shield%'
    OR payer_name ILIKE '%bluecross%'
    OR payer_name ILIKE '%blueshield%'
    OR payer_name ILIKE 'Anthem %'
    OR payer_name ILIKE 'Florida Blue%'
    OR payer_name ILIKE 'Horizon Blue%'
    OR payer_name ILIKE 'Independence Blue%'
    OR payer_name ILIKE 'Premera %'
    OR payer_name ILIKE 'Regence %'
    OR payer_name ILIKE 'Wellmark%'
  )
  AND payer_name NOT LIKE 'BCBS - %';


-- ════════════════════════════════════════════════════════════
-- SECTION 4: VERIFY
-- ════════════════════════════════════════════════════════════

-- Should return 0 rows if cleanup is complete
SELECT 'intermediary_rates — non-BCBS Blue Cross orphans remaining' AS check,
       payer_name, COUNT(*) AS rows
FROM intermediary_rates
WHERE (
       payer_name ILIKE '%blue cross%'
    OR payer_name ILIKE '%blue shield%'
    OR payer_name ILIKE '%bluecross%'
    OR payer_name ILIKE '%blueshield%'
    OR payer_name ILIKE 'Anthem %'
    OR payer_name ILIKE 'Florida Blue%'
    OR payer_name ILIKE 'Horizon Blue%'
    OR payer_name ILIKE 'Premera %'
    OR payer_name ILIKE 'Regence %'
    OR payer_name ILIKE 'Wellmark%'
)
AND payer_name NOT LIKE 'BCBS - %'
GROUP BY payer_name
ORDER BY payer_name;

-- Complete payer list now in intermediary_rates (should match v8 plan names)
SELECT 'intermediary_rates — current payers' AS check,
       payer_name, COUNT(*) AS rows
FROM intermediary_rates
GROUP BY payer_name
ORDER BY payer_name;

-- Payers table after rename
SELECT 'payers table' AS check, payer_id, payer_name
FROM payers
ORDER BY payer_name;
