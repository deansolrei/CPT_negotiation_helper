-- 16_clean_fee_schedule.sql
-- Cleans fee_schedule_lines down to exactly the 12 tracked CPT codes,
-- one row per contract+CPT (keeps the highest rate where duplicates exist).
--
-- Run:  psql solrei_cpt -f 16_clean_fee_schedule.sql

-- ── Step 1: Show what will be deleted ───────────────────────
SELECT 'CPT codes currently in fee_schedule_lines (non-12)' AS info,
       cpt_code, COUNT(*) AS rows_to_delete
FROM fee_schedule_lines
WHERE cpt_code NOT IN (
    '99214','99215','90833','90836','90838',
    '99204','99205','90785',
    '98002','98003','98006','98007'
)
GROUP BY cpt_code
ORDER BY cpt_code;

-- ── Step 2: Delete all non-12-code rows ─────────────────────
DELETE FROM fee_schedule_lines
WHERE cpt_code NOT IN (
    '99214','99215','90833','90836','90838',
    '99204','99205','90785',
    '98002','98003','98006','98007'
);

-- ── Step 3: Delete duplicate modifier rows ───────────────────
-- For each (contract_id, cpt_code), keep only the row with the
-- highest allowed_amount. Ties broken by most recent line id.
DELETE FROM fee_schedule_lines
WHERE fee_schedule_line_id NOT IN (
    SELECT DISTINCT ON (contract_id, cpt_code)
        fee_schedule_line_id
    FROM fee_schedule_lines
    ORDER BY contract_id, cpt_code,
             allowed_amount DESC NULLS LAST,
             fee_schedule_line_id DESC
);

-- ── Step 4: Show what remains ────────────────────────────────
SELECT
    p.payer_name,
    fsl.cpt_code,
    fsl.allowed_amount,
    fsl.modifier
FROM fee_schedule_lines fsl
JOIN contracts c ON fsl.contract_id = c.contract_id
JOIN payers    p ON c.payer_id      = p.payer_id
ORDER BY p.payer_name, fsl.cpt_code;

-- ── Step 5: Verify — should be 0 ────────────────────────────
SELECT 'Duplicate (contract, cpt_code) remaining' AS check, COUNT(*) AS n
FROM (
    SELECT contract_id, cpt_code, COUNT(*) AS cnt
    FROM fee_schedule_lines
    GROUP BY contract_id, cpt_code
    HAVING COUNT(*) > 1
) dups;

SELECT 'Non-12-code rows remaining' AS check, COUNT(*) AS n
FROM fee_schedule_lines
WHERE cpt_code NOT IN (
    '99214','99215','90833','90836','90838',
    '99204','99205','90785',
    '98002','98003','98006','98007'
);
