-- ============================================================
-- 27_cleanup_states_payers.sql
-- 1. Remove VT, ME, KS from all rate/billing tables
-- 2. Rename BCBS virtual network payer to proper name
-- ============================================================

-- ── Remove VT, ME, KS from intermediary_rates ────────────────
DELETE FROM intermediary_rates
WHERE state IN ('VT', 'ME', 'KS');

-- ── Remove old "virtual network" name from intermediary_rates ─
DELETE FROM intermediary_rates
WHERE payer_name = 'BCBS - Massachusetts (virtual network)';

-- ── Remove VT, ME, KS from billing_actuals ───────────────────
DELETE FROM billing_actuals
WHERE state IN ('VT', 'ME', 'KS');

-- ── Remove VT, ME, KS from benchmark_fee_schedule ────────────
DELETE FROM benchmark_fee_schedule
WHERE locality IN ('VT', 'ME', 'KS');

-- ── Rename payer in payers table (used for direct rates) ─────
-- If 'Blue Cross Blue Shield of Massachusetts' already exists,
-- re-point contracts to it then delete the old payer.
-- If it doesn't exist, just rename.
DO $$
DECLARE
  old_id  INTEGER;
  new_id  INTEGER;
BEGIN
  SELECT payer_id INTO old_id
  FROM payers WHERE payer_name = 'BCBS - Massachusetts (virtual network)';

  IF old_id IS NULL THEN
    RAISE NOTICE 'BCBS virtual network payer not found — nothing to rename.';
    RETURN;
  END IF;

  SELECT payer_id INTO new_id
  FROM payers WHERE payer_name = 'Blue Cross Blue Shield of Massachusetts';

  IF new_id IS NOT NULL THEN
    -- Merge: re-point contracts from old payer to existing payer
    UPDATE contracts SET payer_id = new_id WHERE payer_id = old_id;
    DELETE FROM payers WHERE payer_id = old_id;
    RAISE NOTICE 'Merged payer % into %', old_id, new_id;
  ELSE
    -- Simple rename
    UPDATE payers
    SET payer_name = 'Blue Cross Blue Shield of Massachusetts'
    WHERE payer_id = old_id;
    RAISE NOTICE 'Renamed payer % to Blue Cross Blue Shield of Massachusetts', old_id;
  END IF;
END $$;

-- ── Verify ────────────────────────────────────────────────────
SELECT 'intermediary_rates removed' AS check,
       COUNT(*) AS remaining_rows
FROM intermediary_rates
WHERE state IN ('VT','ME','KS')
   OR payer_name = 'BCBS - Massachusetts (virtual network)';

SELECT 'payers check' AS check, payer_name
FROM payers
WHERE payer_name LIKE '%Massachusetts%'
ORDER BY payer_name;
