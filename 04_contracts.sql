CREATE TABLE contracts (
    contract_id         SERIAL PRIMARY KEY,
    payer_id            INTEGER NOT NULL REFERENCES payers(payer_id),
    provider_entity_id  INTEGER NOT NULL REFERENCES provider_entities(provider_entity_id),
    payer_contract_id   VARCHAR(50),          -- PID or contract number from payer
    product_line        VARCHAR(100),         -- e.g. 'Commercial PPO','Medicaid','Exchange'
    line_of_business    VARCHAR(100),         -- optional; e.g. 'Florida Blue HMO'
    effective_date      DATE,
    end_date            DATE,
    active              BOOLEAN DEFAULT TRUE,
    notes               TEXT
);
