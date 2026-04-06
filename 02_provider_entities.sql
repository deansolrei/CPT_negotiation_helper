CREATE TABLE provider_entities (
    provider_entity_id SERIAL PRIMARY KEY,
    legal_name         VARCHAR(150) NOT NULL,      -- e.g. 'Solrei Behavioral Health, Inc.'
    npi_number         VARCHAR(10)  NOT NULL,
    entity_type        VARCHAR(10)  NOT NULL,      -- 'NPI1' or 'NPI2'
    tax_id             VARCHAR(15),                -- EIN
    active             BOOLEAN DEFAULT TRUE,
    notes              TEXT
);
