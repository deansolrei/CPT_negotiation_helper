-- 20_fix_volume_join.sql
-- Fix: annual revenue gap and revenue at target showing blank in summary cards.
--
-- Root cause: the volumes CTE in v_negotiation_dashboard joined on modifier,
-- requiring an exact match (e.g. '95' = '95'). After load_florida_blue.py was
-- rewritten to read from the CSV (which has blank modifiers), the new
-- fee_schedule_lines rows have NULL modifier. The annual_claims_volume data
-- was loaded with modifier '95', so NULL ≠ '95' and the join returns nothing.
-- No volume → annual_revenue_gap = NULL → summary cards show blank.
--
-- Fix: join volumes by (contract_id, cpt_code) only — modifier is irrelevant
-- for volume tracking at a telehealth clinic that uses a single billing code
-- per visit. Also deduplicate volumes to one row per (contract, CPT).
--
-- Run: psql solrei_cpt -f 20_fix_volume_join.sql

CREATE OR REPLACE VIEW v_negotiation_dashboard AS
WITH

-- Resolve the most specific negotiation target for each payer+code pair
targets AS (
    SELECT
        fm.fee_schedule_line_id,
        fm.contract_id,
        fm.payer_id,
        fm.payer_name,
        fm.provider_entity_id,
        fm.provider_name,
        fm.npi_number,
        fm.entity_type,
        fm.payer_contract_id,
        fm.product_line,
        fm.cpt_code,
        fm.short_description,
        fm.category,
        fm.telehealth_eligible,
        fm.is_addon,
        fm.modifier,
        fm.place_of_service,
        fm.unit_type,
        fm.payer_allowed,
        fm.medicare_allowed,
        fm.pct_of_medicare,
        fm.effective_date,
        fm.end_date,
        COALESCE(
            (SELECT target_pct_of_medicare FROM negotiation_targets
             WHERE payer_id = fm.payer_id AND cpt_code = fm.cpt_code),
            (SELECT target_pct_of_medicare FROM negotiation_targets
             WHERE payer_id = fm.payer_id AND cpt_code IS NULL),
            (SELECT target_pct_of_medicare FROM negotiation_targets
             WHERE payer_id IS NULL AND cpt_code IS NULL)
        ) AS target_pct_of_medicare
    FROM v_fee_vs_medicare fm
),

-- One volume row per (contract_id, cpt_code) — most recent year.
-- Modifier is intentionally excluded from the join key: billing volume
-- at a telehealth practice doesn't vary by modifier, and requiring an
-- exact modifier match caused the join to fail when fee schedule rows
-- used a different modifier than the volume data.
volumes AS (
    SELECT DISTINCT ON (contract_id, cpt_code)
        contract_id,
        cpt_code,
        annual_volume,
        calendar_year
    FROM annual_claims_volume
    ORDER BY contract_id, cpt_code, calendar_year DESC
)

SELECT
    t.fee_schedule_line_id,
    t.contract_id,
    t.payer_id,
    t.payer_name,
    t.provider_entity_id,
    t.provider_name,
    t.npi_number,
    t.entity_type,
    t.payer_contract_id,
    t.product_line,
    t.cpt_code,
    t.short_description,
    t.category,
    t.telehealth_eligible,
    t.is_addon,
    t.modifier,
    t.place_of_service,
    t.unit_type,
    t.effective_date,

    t.payer_allowed,
    t.medicare_allowed,
    t.pct_of_medicare,
    t.target_pct_of_medicare,

    CASE
        WHEN t.medicare_allowed IS NULL THEN NULL
        ELSE ROUND(t.medicare_allowed * t.target_pct_of_medicare / 100, 2)
    END AS target_allowed,

    CASE
        WHEN t.medicare_allowed IS NULL THEN NULL
        ELSE ROUND((t.medicare_allowed * t.target_pct_of_medicare / 100) - t.payer_allowed, 2)
    END AS rate_gap_per_unit,

    CASE
        WHEN t.pct_of_medicare IS NULL OR t.target_pct_of_medicare IS NULL THEN NULL
        WHEN t.pct_of_medicare < t.target_pct_of_medicare THEN TRUE
        ELSE FALSE
    END AS is_underpaid,

    v.annual_volume,
    v.calendar_year AS volume_year,

    CASE
        WHEN v.annual_volume IS NULL THEN NULL
        ELSE ROUND(t.payer_allowed * v.annual_volume, 2)
    END AS annual_revenue_current,

    CASE
        WHEN v.annual_volume IS NULL OR t.medicare_allowed IS NULL THEN NULL
        ELSE ROUND((t.medicare_allowed * t.target_pct_of_medicare / 100) * v.annual_volume, 2)
    END AS annual_revenue_at_target,

    CASE
        WHEN v.annual_volume IS NULL OR t.medicare_allowed IS NULL THEN NULL
        ELSE ROUND(
            ((t.medicare_allowed * t.target_pct_of_medicare / 100) - t.payer_allowed) * v.annual_volume,
        2)
    END AS annual_revenue_gap

FROM targets t
-- Join on contract + CPT only — modifier excluded intentionally (see CTE note)
LEFT JOIN volumes v
    ON  v.contract_id = t.contract_id
    AND v.cpt_code    = t.cpt_code

ORDER BY
    CASE WHEN v.annual_volume IS NOT NULL THEN 0 ELSE 1 END,
    annual_revenue_gap DESC NULLS LAST,
    t.payer_name,
    t.cpt_code;

-- Verify: revenue figures should now be non-null for payers with volume data
SELECT
    payer_name,
    COUNT(DISTINCT cpt_code)                                      AS codes,
    COUNT(*) FILTER (WHERE annual_volume IS NOT NULL)             AS codes_with_volume,
    ROUND(SUM(annual_revenue_gap) FILTER (WHERE annual_volume IS NOT NULL) / 1000, 1) AS total_gap_K
FROM v_negotiation_dashboard
WHERE cpt_code IN ('99214','99215','90833','90836','90838','99204','99205','90785',
                   '98002','98003','98006','98007')
GROUP BY payer_name
ORDER BY payer_name;
-- codes_with_volume should be > 0 for any payer that has claims volume data
