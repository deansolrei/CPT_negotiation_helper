CREATE TABLE IF NOT EXISTS fee_schedule_lines (
    fee_schedule_line_id SERIAL PRIMARY KEY,
    contract_id          INTEGER NOT NULL REFERENCES contracts(contract_id),
    cpt_code             VARCHAR(10) NOT NULL REFERENCES cpt_codes(cpt_code),
    modifier             VARCHAR(10),            -- e.g. '95', 'GT', 'HQ'; NULL if none
    place_of_service     VARCHAR(5),             -- e.g. '10', '11'; NULL if not differentiated
    unit_type            VARCHAR(20) NOT NULL,   -- 'per_service','per_minute','per_15min'
    allowed_amount       NUMERIC(10,2) NOT NULL, -- your contracted rate
    effective_date       DATE,
    end_date             DATE,
    notes                TEXT,
    UNIQUE (contract_id, cpt_code, modifier, place_of_service, effective_date)
);
