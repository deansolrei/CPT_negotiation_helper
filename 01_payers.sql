CREATE TABLE IF NOT EXISTS payers (
    payer_id           SERIAL PRIMARY KEY,
    payer_name         VARCHAR(100) NOT NULL,      -- e.g. 'Florida Blue'
    payer_display_name VARCHAR(150),               -- e.g. 'Florida Blue (BCBS)'
    payer_type         VARCHAR(50),                -- 'Commercial','Medicaid','Medicare Advantage','Exchange'
    payer_notes        TEXT
);
