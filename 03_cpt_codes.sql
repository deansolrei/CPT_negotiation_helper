CREATE TABLE cpt_codes (
    cpt_code              VARCHAR(10) PRIMARY KEY,   -- e.g. '99214'
    short_description     VARCHAR(255) NOT NULL,
    category              VARCHAR(50)  NOT NULL,
    typical_time_minutes  INTEGER,
    is_time_based         BOOLEAN NOT NULL,
    is_addon              BOOLEAN NOT NULL,
    primary_code_required BOOLEAN NOT NULL,
    primary_code_family   VARCHAR(100),
    telehealth_eligible   BOOLEAN NOT NULL,
    typical_use           VARCHAR(100),
    notes                 TEXT
);
