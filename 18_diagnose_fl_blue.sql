-- 18_diagnose_fl_blue.sql
-- Diagnoses why Florida Blue direct rates differ between sections.
-- Run: psql solrei_cpt -f 18_diagnose_fl_blue.sql

SELECT '=== 1. What entity_type does v_channel_comparison use for direct rates? ===' AS step;
-- If this shows NPI2 rows, the 17_fix file has NOT been applied yet.
SELECT
    pe.entity_type,
    pe.legal_name,
    pe.npi_number,
    fsl.cpt_code,
    fsl.allowed_amount
FROM fee_schedule_lines fsl
JOIN contracts         c   ON fsl.contract_id       = c.contract_id
JOIN payers            p   ON c.payer_id            = p.payer_id
JOIN provider_entities pe  ON c.provider_entity_id  = pe.provider_entity_id
WHERE lower(p.payer_name) LIKE '%florida%'
  AND fsl.cpt_code IN ('99214','99215','90833','90836','90838')
ORDER BY fsl.cpt_code, pe.entity_type;

SELECT '=== 2. What does v_channel_comparison currently return for Florida Blue? ===' AS step;
SELECT payer_name, cpt_code, direct_rate, headway_rate, alma_rate, grow_rate
FROM v_channel_comparison
WHERE lower(payer_name) LIKE '%florida%'
ORDER BY cpt_code;

SELECT '=== 3. What does v_negotiation_dashboard return for Florida Blue NPI1? ===' AS step;
-- This is what the Rate Comparison section uses (after JS prefers JODENE NPI).
SELECT DISTINCT ON (cpt_code)
    payer_name, npi_number, entity_type, cpt_code, payer_allowed
FROM v_negotiation_dashboard
WHERE lower(payer_name) LIKE '%florida%'
  AND cpt_code IN ('99214','99215','90833','90836','90838')
ORDER BY cpt_code,
         CASE entity_type WHEN 'NPI1' THEN 0 ELSE 1 END,
         payer_allowed DESC;

SELECT '=== 4. Side-by-side comparison (should be identical if fix worked) ===' AS step;
SELECT
    nd.cpt_code,
    nd.payer_allowed   AS rate_comparison_rate,
    cc.direct_rate     AS channel_comparison_rate,
    nd.payer_allowed = cc.direct_rate AS rates_match
FROM (
    SELECT DISTINCT ON (cpt_code) cpt_code, payer_allowed
    FROM v_negotiation_dashboard
    WHERE lower(payer_name) LIKE '%florida%'
      AND cpt_code IN ('99214','99215','90833','90836','90838')
    ORDER BY cpt_code,
             CASE entity_type WHEN 'NPI1' THEN 0 ELSE 1 END,
             payer_allowed DESC
) nd
JOIN v_channel_comparison cc ON cc.cpt_code = nd.cpt_code
WHERE lower(cc.payer_name) LIKE '%florida%'
ORDER BY nd.cpt_code;
