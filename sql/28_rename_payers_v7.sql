-- ============================================================
-- 28_rename_payers_v7.sql
-- Rename payer names in intermediary_rates and payers tables
-- to match the new MASTER / populate_slave_v7 naming convention.
--
-- RUN AFTER importing fresh CSVs from populate_slave_v7.
-- Safe to run multiple times (UPDATE … WHERE payer_name = old
-- is a no-op if the old name no longer exists).
-- ============================================================


-- ── 1. INTERMEDIARY RATES — simple renames ───────────────────
-- These are straight 1-to-1 name changes with no state ambiguity.

UPDATE intermediary_rates SET payer_name = 'UHC / Oscar / Optum'
  WHERE payer_name = 'UHC/Oscar/Optum';

UPDATE intermediary_rates SET payer_name = 'BCBS - Florida Blue'
  WHERE payer_name = 'Florida Blue';

UPDATE intermediary_rates SET payer_name = 'BCBS - Florida Blue Medicare Advantage'
  WHERE payer_name = 'Florida Blue Medicare Advantage';

UPDATE intermediary_rates SET payer_name = 'BCBS - of Arizona'
  WHERE payer_name = 'Blue Cross Blue Shield of Arizona';

UPDATE intermediary_rates SET payer_name = 'BCBS - of Massachusetts'
  WHERE payer_name = 'Blue Cross Blue Shield of Massachusetts';

UPDATE intermediary_rates SET payer_name = 'BCBS - of Minnesota'
  WHERE payer_name IN (
    'Blue Cross and Blue Shield of Minnesota',
    'Blue Cross and Blue Shield of Minnesota Medicaid',
    'Blue Cross and Blue Shield of Minnesota Medicare Advantage'
  );

UPDATE intermediary_rates SET payer_name = 'BCBS - Anthem (Indiana)'
  WHERE payer_name IN (
    'Anthem Blue Cross Blue Shield (Indiana)',
    'Anthem Blue Cross and Blue Shield Indiana'
  );

UPDATE intermediary_rates SET payer_name = 'BCBS - Horizon (New Jersey)'
  WHERE payer_name IN (
    'Horizon Blue Cross and Blue Shield of New Jersey',
    'Horizon Blue Cross Blue Shield of New Jersey'
  );

UPDATE intermediary_rates SET payer_name = 'BCBS - Independence (Pennsylvania)'
  WHERE payer_name IN (
    'Independence Blue Cross Pennsylvania',
    'Independence Blue Cross (Pennsylvania)'
  );

UPDATE intermediary_rates SET payer_name = 'BCBS - Premera (Washington)'
  WHERE payer_name = 'Premera Blue Cross Washington';

UPDATE intermediary_rates SET payer_name = 'BCBS - Regence (Washington)'
  WHERE payer_name IN (
    'Regence BlueShield of Washington',
    'Regence BlueShield (Washington)'
  );


-- ── 2. INTERMEDIARY RATES — state-specific Anthem renames ────
-- 'Anthem Blue Cross and Blue Shield' was used for CO / CT / NV / NH
-- in v6 (all via the same col 14 Alma mapping).
-- Rename each by state to the correct new plan name.

UPDATE intermediary_rates SET payer_name = 'BCBS - Anthem (Colorado)'
  WHERE payer_name IN (
    'Anthem Blue Cross and Blue Shield',
    'Anthem Blue Cross and Blue Shield Colorado HMO',
    'Anthem Blue Cross and Blue Shield Colorado PPO'
  )
  AND state = 'CO';

UPDATE intermediary_rates SET payer_name = 'BCBS - Anthem (Connecticut)'
  WHERE payer_name = 'Anthem Blue Cross and Blue Shield'
  AND state = 'CT';

UPDATE intermediary_rates SET payer_name = 'BCBS - Anthem (Nevada)'
  WHERE payer_name = 'Anthem Blue Cross and Blue Shield'
  AND state = 'NV';

UPDATE intermediary_rates SET payer_name = 'BCBS - Anthem (New Hampshire)'
  WHERE payer_name = 'Anthem Blue Cross and Blue Shield'
  AND state = 'NH';


-- ── 3. INTERMEDIARY RATES — remove orphaned plans ────────────
-- Regence OR is no longer in the plan list.
-- Medicaid / Medicare Advantage sub-plans consolidated above.
-- Delete any remaining rows with these old names.

DELETE FROM intermediary_rates
  WHERE payer_name IN (
    'Regence BlueCross BlueShield of Oregon',
    'Regence BlueShield of Oregon'
  );


-- ── 4. PAYERS TABLE — rename for direct billing ──────────────
-- Used by fee_schedule_lines (SBH / clinic-submit rates).

DO $$
DECLARE
  r RECORD;
BEGIN
  -- Rename map: old_name → new_name
  FOR r IN SELECT * FROM (VALUES
    ('Optum/UHC/Oscar',                    'UHC / Oscar / Optum'),
    ('UHC/Oscar/Optum',                    'UHC / Oscar / Optum'),
    ('Blue Cross Blue Shield of Massachusetts', 'BCBS - of Massachusetts'),
    ('BCBS - Massachusetts (virtual network)',  'BCBS - of Massachusetts')
  ) AS t(old_name, new_name)
  LOOP
    DECLARE
      old_id  INTEGER;
      new_id  INTEGER;
    BEGIN
      SELECT payer_id INTO old_id FROM payers WHERE payer_name = r.old_name;
      IF old_id IS NULL THEN
        RAISE NOTICE 'Payer not found (already renamed?): %', r.old_name;
        CONTINUE;
      END IF;

      SELECT payer_id INTO new_id FROM payers WHERE payer_name = r.new_name;

      IF new_id IS NOT NULL THEN
        -- Target name already exists — merge: re-point contracts, delete old row
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


-- ── 5. VERIFY ────────────────────────────────────────────────

-- Any old-style names still lurking in intermediary_rates?
SELECT 'intermediary_rates old names still present' AS check, payer_name, COUNT(*) AS rows
FROM intermediary_rates
WHERE payer_name IN (
  'UHC/Oscar/Optum',
  'Florida Blue',
  'Florida Blue Medicare Advantage',
  'Blue Cross Blue Shield of Arizona',
  'Blue Cross Blue Shield of Massachusetts',
  'Blue Cross and Blue Shield of Minnesota',
  'Blue Cross and Blue Shield of Minnesota Medicaid',
  'Blue Cross and Blue Shield of Minnesota Medicare Advantage',
  'Anthem Blue Cross and Blue Shield',
  'Anthem Blue Cross and Blue Shield Colorado HMO',
  'Anthem Blue Cross and Blue Shield Colorado PPO',
  'Anthem Blue Cross Blue Shield (Indiana)',
  'Anthem Blue Cross and Blue Shield Indiana',
  'Horizon Blue Cross and Blue Shield of New Jersey',
  'Horizon Blue Cross Blue Shield of New Jersey',
  'Independence Blue Cross Pennsylvania',
  'Premera Blue Cross Washington',
  'Regence BlueShield of Washington',
  'Regence BlueCross BlueShield of Oregon'
)
GROUP BY payer_name
ORDER BY payer_name;

-- New payer names now in intermediary_rates
SELECT 'intermediary_rates current payers' AS check, payer_name, COUNT(*) AS rows
FROM intermediary_rates
GROUP BY payer_name
ORDER BY payer_name;

-- Payers table after rename
SELECT 'payers table' AS check, payer_name
FROM payers
ORDER BY payer_name;
