CREATE TABLE IF NOT EXISTS benchmark_fee_schedule (
    benchmark_id        SERIAL PRIMARY KEY,
    source_name         VARCHAR(100) NOT NULL,   -- 'Medicare 2026', 'FL Medicaid 2026'
    locality            VARCHAR(50),             -- e.g. 'FL', 'National'
    cpt_code            VARCHAR(10) NOT NULL REFERENCES cpt_codes(cpt_code),
    allowed_amount      NUMERIC(10,2) NOT NULL,
    effective_year      INTEGER NOT NULL,
    notes               TEXT,
    UNIQUE (source_name, locality, cpt_code, effective_year)
);
