CREATE VIEW v_fee_vs_medicare AS
SELECT
    f.fee_schedule_line_id,
    c.contract_id,
    p.payer_name,
    pe.legal_name AS provider_name,
    pe.npi_number,
    c.product_line,
    f.cpt_code,
    cc.short_description,
    f.modifier,
    f.place_of_service,
    f.allowed_amount AS payer_allowed,
    b.allowed_amount AS medicare_allowed,
    CASE 
        WHEN b.allowed_amount IS NULL THEN NULL
        ELSE ROUND(f.allowed_amount / b.allowed_amount * 100, 1)
    END AS pct_of_medicare
FROM fee_schedule_lines f
JOIN contracts c
    ON f.contract_id = c.contract_id
JOIN payers p
    ON c.payer_id = p.payer_id
JOIN provider_entities pe
    ON c.provider_entity_id = pe.provider_entity_id
JOIN cpt_codes cc
    ON f.cpt_code = cc.cpt_code
LEFT JOIN benchmark_fee_schedule b
    ON b.cpt_code    = f.cpt_code
   AND b.source_name = 'Medicare 2026'
   AND b.locality    = 'FL'
   AND b.effective_year = 2026
WHERE (c.end_date IS NULL OR c.end_date >= CURRENT_DATE)
  AND (f.end_date IS NULL OR f.end_date >= CURRENT_DATE);
