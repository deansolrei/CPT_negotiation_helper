-- 10_views_negotiation_dashboard.sql
-- Views that power the negotiation dashboard.
-- Run AFTER all schema files (01–09) have been executed.
--
-- Views created:
--   v_fee_vs_medicare         : Raw rate comparison (payer allowed vs Medicare)
--   v_negotiation_dashboard   : Full dashboard with targets, gap, and revenue impact
--   v_negotiation_summary     : Rolled-up by payer (which payer to call first)


-- ============================================================
-- VIEW 1: v_fee_vs_medicare
-- Basic comparison of payer allowed amounts vs. Medicare rates.
-- ============================================================
CREATE OR REPLACE VIEW v_fee_vs_medicare AS
SELECT
    f.fee_schedule_line_id,
    c.contract_id,
    p.payer_id,
    p.payer_name,
    pe.provider_entity_id,
    pe.legal_name          AS provider_name,
    pe.npi_number,
    pe.entity_type,
    c.payer_contract_id,
    c.product_line,
    f.cpt_code,
    cc.short_description,
    cc.category,
    cc.telehealth_eligible,
    cc.is_addon,
    f.modifier,
    f.place_of_service,
    f.unit_type,
    f.allowed_amount                                        AS payer_allowed,
    b.allowed_amount                                        AS medicare_allowed,
    CASE
        WHEN b.allowed_amount IS NULL OR b.allowed_amount = 0 THEN NULL
        ELSE ROUND(f.allowed_amount / b.allowed_amount * 100, 1)
    END                                                     AS pct_of_medicare,
    f.effective_date,
    f.end_date
FROM fee_schedule_lines f
JOIN contracts c          ON f.contract_id         = c.contract_id
JOIN payers p             ON c.payer_id            = p.payer_id
JOIN provider_entities pe ON c.provider_entity_id  = pe.provider_entity_id
JOIN cpt_codes cc         ON f.cpt_code            = cc.cpt_code
LEFT JOIN benchmark_fee_schedule b
    ON  b.cpt_code        = f.cpt_code
    AND b.source_name     = 'Medicare 2026'
    AND b.locality        = 'FL'
    AND b.effective_year  = 2026
WHERE (c.end_date IS NULL OR c.end_date >= CURRENT_DATE)
  AND (f.end_date IS NULL OR f.end_date >= CURRENT_DATE)
  AND c.active = TRUE;


-- ============================================================
-- VIEW 2: v_negotiation_dashboard
-- Full dashboard: payer rates vs Medicare, target rates,
-- revenue gap, and annual dollar impact by contract + code.
-- ============================================================
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
        -- Resolve target: most specific wins (payer+code > payer > global)
        COALESCE(
            (SELECT target_pct_of_medicare FROM negotiation_targets
             WHERE payer_id = fm.payer_id AND cpt_code = fm.cpt_code),
            (SELECT target_pct_of_medicare FROM negotiation_targets
             WHERE payer_id = fm.payer_id AND cpt_code IS NULL),
            (SELECT target_pct_of_medicare FROM negotiation_targets
             WHERE payer_id IS NULL AND cpt_code IS NULL)
        )                                                   AS target_pct_of_medicare
    FROM v_fee_vs_medicare fm
),

-- Join in annual claims volume for the most recent year available
volumes AS (
    SELECT DISTINCT ON (contract_id, cpt_code, modifier)
        contract_id,
        cpt_code,
        modifier,
        annual_volume,
        calendar_year
    FROM annual_claims_volume
    ORDER BY contract_id, cpt_code, modifier, calendar_year DESC
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

    -- Rate columns
    t.payer_allowed,
    t.medicare_allowed,
    t.pct_of_medicare,
    t.target_pct_of_medicare,

    -- Target allowed amount (what we want the payer to pay per unit)
    CASE
        WHEN t.medicare_allowed IS NULL THEN NULL
        ELSE ROUND(t.medicare_allowed * t.target_pct_of_medicare / 100, 2)
    END                                                     AS target_allowed,

    -- Rate gap per unit (positive = underpaid; negative = above target)
    CASE
        WHEN t.medicare_allowed IS NULL THEN NULL
        ELSE ROUND((t.medicare_allowed * t.target_pct_of_medicare / 100) - t.payer_allowed, 2)
    END                                                     AS rate_gap_per_unit,

    -- Flag: is this code underpaid relative to our target?
    CASE
        WHEN t.pct_of_medicare IS NULL OR t.target_pct_of_medicare IS NULL THEN NULL
        WHEN t.pct_of_medicare < t.target_pct_of_medicare THEN TRUE
        ELSE FALSE
    END                                                     AS is_underpaid,

    -- Volume (NULL until annual_claims_volume is loaded)
    v.annual_volume,
    v.calendar_year                                         AS volume_year,

    -- Revenue impact (NULL until volume data is loaded)
    CASE
        WHEN v.annual_volume IS NULL THEN NULL
        ELSE ROUND(t.payer_allowed * v.annual_volume, 2)
    END                                                     AS annual_revenue_current,

    CASE
        WHEN v.annual_volume IS NULL OR t.medicare_allowed IS NULL THEN NULL
        ELSE ROUND((t.medicare_allowed * t.target_pct_of_medicare / 100) * v.annual_volume, 2)
    END                                                     AS annual_revenue_at_target,

    CASE
        WHEN v.annual_volume IS NULL OR t.medicare_allowed IS NULL THEN NULL
        ELSE ROUND(
            ((t.medicare_allowed * t.target_pct_of_medicare / 100) - t.payer_allowed) * v.annual_volume,
        2)
    END                                                     AS annual_revenue_gap

FROM targets t
LEFT JOIN volumes v
    ON  v.contract_id = t.contract_id
    AND v.cpt_code    = t.cpt_code
    AND (v.modifier = t.modifier OR (v.modifier IS NULL AND t.modifier IS NULL))

ORDER BY
    -- Surface the biggest dollar opportunities first once volume is loaded
    CASE WHEN v.annual_volume IS NOT NULL THEN 0 ELSE 1 END,
    annual_revenue_gap DESC NULLS LAST,
    t.payer_name,
    t.cpt_code;


-- ============================================================
-- VIEW 3: v_negotiation_summary
-- Rolled up by payer — answers "which payer to call first?"
-- ============================================================
CREATE OR REPLACE VIEW v_negotiation_summary AS
SELECT
    payer_id,
    payer_name,
    COUNT(DISTINCT cpt_code)                                        AS codes_with_rates,
    COUNT(DISTINCT cpt_code) FILTER (WHERE is_underpaid = TRUE)     AS codes_underpaid,
    ROUND(AVG(pct_of_medicare), 1)                                  AS avg_pct_of_medicare,
    ROUND(AVG(target_pct_of_medicare), 1)                           AS avg_target_pct,
    SUM(annual_revenue_current)                                     AS total_revenue_current,
    SUM(annual_revenue_at_target)                                   AS total_revenue_at_target,
    SUM(annual_revenue_gap)                                         AS total_revenue_gap
FROM v_negotiation_dashboard
GROUP BY payer_id, payer_name
ORDER BY total_revenue_gap DESC NULLS LAST;
