-- 09_seed_data.sql
-- Seed data for Solrei Behavioral Health, Inc.
-- Run AFTER all schema files (01–08) have been executed.
-- Safe to re-run: uses INSERT ... ON CONFLICT DO NOTHING where possible.

-- ============================================================
-- PAYERS
-- ============================================================
INSERT INTO payers (payer_name, payer_display_name, payer_type, payer_notes) VALUES
    ('Florida Blue',  'Florida Blue (BCBS)',        'Commercial', 'Blue Cross Blue Shield of Florida. Group PID: 1FMCO, Individual PID: GLH30'),
    ('Wellmark Iowa', 'Wellmark Blue Cross Iowa',   'Commercial', 'BCBS affiliate for Iowa. Group PID: 1FMCO'),
    ('Aetna',         'Aetna',                      'Commercial', 'Group PID: TBD. Individual (Jodene Jensen) PID: 8646882'),
    ('Ambetter',      'Ambetter (Sunshine Health)', 'Exchange',   'ACA marketplace plan. Group ICM: 305011'),
    ('Cigna',         'Cigna',                      'Commercial', 'Individual (Jodene Jensen) PID: 62308'),
    ('Optum / UHC',   'Optum / United Health Care', 'Commercial', 'Group PID: 008492809. Individual (Jodene Jensen) PID: 008492810')
ON CONFLICT DO NOTHING;


-- ============================================================
-- PROVIDER ENTITIES
-- ============================================================
INSERT INTO provider_entities (legal_name, npi_number, entity_type, tax_id, active, notes) VALUES
    ('Solrei Behavioral Health, Inc.', '1003521006', 'NPI2', '921227672', TRUE,  'Group practice. Address: 9100 Conroy Windermere Rd, Windermere FL 34786'),
    ('Jodene Jensen, PMHNP-BC',        '1093433955', 'NPI1', '921227672', TRUE,  'Psychiatric Mental Health Nurse Practitioner'),
    ('Katherine Robins, PMHNP-BC',     '1831127117', 'NPI1', '921227672', TRUE,  'Psychiatric Mental Health Nurse Practitioner'),
    ('Megan Ramirez, PMHNP-BC',        '1801895636', 'NPI1', '921227672', TRUE,  'Psychiatric Mental Health Nurse Practitioner'),
    ('Lori Kistler, PMHNP-BC',         '1376234641', 'NPI1', '921227672', TRUE,  'Psychiatric Mental Health Nurse Practitioner')
ON CONFLICT DO NOTHING;


-- ============================================================
-- CPT CODES
-- ============================================================
INSERT INTO cpt_codes (
    cpt_code, short_description, category, typical_time_minutes,
    is_time_based, is_addon, primary_code_required, primary_code_family,
    telehealth_eligible, typical_use, notes
) VALUES
    -- Evaluation & Management
    ('99202', 'New patient E/M low complexity',                        'E/M',                   20, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'intake med management',           'Office/telehealth new patient'),
    ('99203', 'New patient E/M moderate complexity',                   'E/M',                   30, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'intake med management',           NULL),
    ('99204', 'New patient E/M mod-high complexity',                   'E/M',                   45, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'intake complex med management',   'Common for psych intakes'),
    ('99205', 'New patient E/M high complexity',                       'E/M',                   60, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'intake complex med management',   NULL),
    ('99212', 'Est patient E/M brief',                                 'E/M',                   15, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'brief med check',                 NULL),
    ('99213', 'Est patient E/M low complexity',                        'E/M',                   20, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'follow-up med management',        NULL),
    ('99214', 'Est patient E/M moderate complexity',                   'E/M',                   30, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'follow-up med management',        'High-volume psychiatry visit'),
    ('99215', 'Est patient E/M high complexity',                       'E/M',                   40, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'complex follow-up',               NULL),

    -- Diagnostic / Psychiatric Evaluation
    ('90791', 'Psychiatric diagnostic evaluation (no medical)',         'Diagnostic',           NULL, FALSE, FALSE, FALSE, NULL,                                         TRUE,  'intake',                          'Used when no medical services/med mgmt'),
    ('90792', 'Psychiatric diagnostic evaluation with medical services','Diagnostic / E/M',    NULL, FALSE, FALSE, FALSE, NULL,                                         TRUE,  'intake med management',           'Prescriber intake option'),

    -- Psychotherapy (standalone)
    ('90832', 'Individual psychotherapy 30 minutes',                   'Psychotherapy',         30, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'therapy only',                    NULL),
    ('90834', 'Individual psychotherapy 45 minutes',                   'Psychotherapy',         45, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'therapy only',                    'Very common weekly session'),
    ('90837', 'Individual psychotherapy 60 minutes',                   'Psychotherapy',         60, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'therapy only',                    NULL),

    -- Add-on psychotherapy (with E/M)
    ('90833', 'Add-on psychotherapy 30 min with E/M',                  'Add-on Psychotherapy',  30, TRUE,  TRUE,  TRUE,  'Office E/M 99202-99205, 99212-99215',        TRUE,  'med management + therapy',        'Report with appropriate E/M'),
    ('90836', 'Add-on psychotherapy 45 min with E/M',                  'Add-on Psychotherapy',  45, TRUE,  TRUE,  TRUE,  'Office E/M 99202-99205, 99212-99215',        TRUE,  'med management + therapy',        NULL),
    ('90838', 'Add-on psychotherapy 60 min with E/M',                  'Add-on Psychotherapy',  60, TRUE,  TRUE,  TRUE,  'Office E/M 99202-99205, 99212-99215',        TRUE,  'med management + therapy',        NULL),

    -- Family
    ('90846', 'Family psychotherapy without patient',                  'Family',                50, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'family work',                     NULL),
    ('90847', 'Family psychotherapy with patient',                     'Family',                50, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'family work',                     NULL),

    -- Group
    ('90853', 'Group psychotherapy',                                   'Group',                NULL, FALSE, FALSE, FALSE, NULL,                                          TRUE,  'group therapy',                   'Per patient'),

    -- Crisis
    ('90839', 'Psychotherapy for crisis first 60 minutes',             'Crisis',                60, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'crisis intervention',             'Face-to-face, initial 30-74 minutes'),
    ('90840', 'Each additional 30 min crisis psychotherapy',           'Crisis Add-on',         30, TRUE,  TRUE,  TRUE,  '90839',                                      TRUE,  'crisis intervention',             'Add-on time beyond 90839'),

    -- Screening
    ('96127', 'Brief emotional/behavioral assessment (per instrument)','Screening',            NULL, FALSE, FALSE, FALSE, NULL,                                          TRUE,  'screening',                       'Per instrument (e.g., PHQ-9, GAD-7)'),

    -- Psychological Testing
    ('96130', 'Psychological testing evaluation first hour',           'Testing',               60, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'testing evaluation',              'By qualified professional'),
    ('96136', 'Psych/neuropsych testing by physician/NP first 30 min', 'Testing',               30, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'testing administration',          NULL),
    ('96138', 'Psych/neuropsych testing by technician first 30 min',   'Testing',               30, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'testing administration',          'Use if you add tech-based testing'),

    -- Behavioral Health Integration
    ('99484', 'General behavioral health integration (BHI) 20+ min',  'BHI',                   20, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'chronic behavioral health mgmt',  'Monthly care management'),

    -- Prolonged Services
    ('99417', 'Prolonged office/other E/M beyond typical time',        'Prolonged',             15, TRUE,  TRUE,  TRUE,  'Office E/M 99205, 99215',                    TRUE,  'extended E/M time',               'Add-on per 15 minutes beyond threshold'),
    ('99354', 'Prolonged service face-to-face first 30-60 min',        'Prolonged',             45, TRUE,  TRUE,  TRUE,  'Office E/M 99202-99205, 99212-99215',        FALSE, 'extended in-person visit',        'Check payer-specific allowances'),
    ('99355', 'Prolonged service face-to-face each additional 30 min', 'Prolonged',             30, TRUE,  TRUE,  TRUE,  '99354',                                      FALSE, 'extended in-person visit',        'Check payer-specific allowances'),

    -- Health Behavior
    ('99406', 'Smoking/tobacco cessation counseling 3-10 min',         'Health Behavior',       10, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'brief health behavior change',    'Can be added when appropriate'),
    ('99407', 'Smoking/tobacco cessation counseling >10 min',          'Health Behavior',       15, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'health behavior change',          'Intensive session'),
    ('96156', 'Health behavior assessment/reassessment',               'Health Behavior',       30, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'health behavior assessment',      'Used for behavior affecting health'),
    ('96158', 'Health behavior intervention individual first 30 min',  'Health Behavior',       30, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'health behavior intervention',    'Individual'),
    ('96159', 'Health behavior intervention individual addl 15 min',   'Health Behavior',       15, TRUE,  TRUE,  TRUE,  '96158',                                      TRUE,  'health behavior intervention',    NULL),
    ('96164', 'Health behavior intervention group first 30 min',       'Health Behavior',       30, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'group health behavior',           NULL),
    ('96165', 'Health behavior intervention group each addl 15 min',   'Health Behavior',       15, TRUE,  TRUE,  TRUE,  '96164',                                      TRUE,  'group health behavior',           NULL),
    ('96167', 'Health behavior intervention family w/ patient 30 min', 'Health Behavior',       30, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'family health behavior',          NULL),
    ('96168', 'Health behavior intervention family w/ patient addl 15','Health Behavior',       15, TRUE,  TRUE,  TRUE,  '96167',                                      TRUE,  'family health behavior',          NULL),

    -- Collaborative Care Model (G-codes)
    ('G0568', 'CoCM 60 minutes initial month',                         'BHI',                   60, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'collaborative care',              'For collaborative care model where applicable'),
    ('G0569', 'CoCM 30 minutes subsequent month',                      'BHI',                   30, TRUE,  FALSE, FALSE, NULL,                                          TRUE,  'collaborative care',              NULL),
    ('G0570', 'Each additional 30 minutes CoCM',                       'BHI',                   30, TRUE,  TRUE,  TRUE,  'G0568, G0569',                               TRUE,  'collaborative care',              NULL)

ON CONFLICT (cpt_code) DO NOTHING;


-- ============================================================
-- CONTRACTS
-- (Linking payers to provider entities with PIDs)
-- Payer IDs and provider_entity IDs are resolved by name/NPI
-- since SERIAL values are assigned at runtime.
-- ============================================================

-- Florida Blue × Solrei Group
INSERT INTO contracts (payer_id, provider_entity_id, payer_contract_id, product_line, effective_date, active, notes)
SELECT p.payer_id, pe.provider_entity_id, '1FMCO', 'Commercial', '2024-01-01', TRUE,
       'Florida Blue Group contract. EIN: 921227672'
FROM payers p, provider_entities pe
WHERE p.payer_name = 'Florida Blue' AND pe.npi_number = '1003521006';

-- Florida Blue × Jodene Jensen Individual
INSERT INTO contracts (payer_id, provider_entity_id, payer_contract_id, product_line, effective_date, active, notes)
SELECT p.payer_id, pe.provider_entity_id, 'GLH30', 'Commercial', '2024-01-01', TRUE,
       'Florida Blue Individual contract. EIN: 921227672'
FROM payers p, provider_entities pe
WHERE p.payer_name = 'Florida Blue' AND pe.npi_number = '1093433955';

-- Wellmark Iowa × Solrei Group
INSERT INTO contracts (payer_id, provider_entity_id, payer_contract_id, product_line, effective_date, active, notes)
SELECT p.payer_id, pe.provider_entity_id, '1FMCO', 'Commercial', '2024-01-01', TRUE,
       'Wellmark Iowa Group contract. EIN: 921227672'
FROM payers p, provider_entities pe
WHERE p.payer_name = 'Wellmark Iowa' AND pe.npi_number = '1003521006';

-- Aetna × Solrei Group
INSERT INTO contracts (payer_id, provider_entity_id, payer_contract_id, product_line, effective_date, active, notes)
SELECT p.payer_id, pe.provider_entity_id, NULL, 'Commercial', '2024-01-01', TRUE,
       'Aetna Group contract. PID TBD. EIN: 921227672'
FROM payers p, provider_entities pe
WHERE p.payer_name = 'Aetna' AND pe.npi_number = '1003521006';

-- Aetna × Jodene Jensen Individual
INSERT INTO contracts (payer_id, provider_entity_id, payer_contract_id, product_line, effective_date, active, notes)
SELECT p.payer_id, pe.provider_entity_id, '8646882', 'Commercial', '2024-01-01', TRUE,
       'Aetna Individual contract. EIN: 921227672'
FROM payers p, provider_entities pe
WHERE p.payer_name = 'Aetna' AND pe.npi_number = '1093433955';

-- Ambetter × Solrei Group
INSERT INTO contracts (payer_id, provider_entity_id, payer_contract_id, product_line, effective_date, active, notes)
SELECT p.payer_id, pe.provider_entity_id, '305011', 'Exchange', '2024-01-01', TRUE,
       'Ambetter Group contract. ICM: 305011. EIN: 921227672'
FROM payers p, provider_entities pe
WHERE p.payer_name = 'Ambetter' AND pe.npi_number = '1003521006';

-- Cigna × Jodene Jensen Individual
INSERT INTO contracts (payer_id, provider_entity_id, payer_contract_id, product_line, effective_date, active, notes)
SELECT p.payer_id, pe.provider_entity_id, '62308', 'Commercial', '2024-01-01', TRUE,
       'Cigna Individual contract. EIN: 921227672'
FROM payers p, provider_entities pe
WHERE p.payer_name = 'Cigna' AND pe.npi_number = '1093433955';

-- Optum/UHC × Solrei Group
INSERT INTO contracts (payer_id, provider_entity_id, payer_contract_id, product_line, effective_date, active, notes)
SELECT p.payer_id, pe.provider_entity_id, '008492809', 'Commercial', '2024-01-01', TRUE,
       'Optum/UHC Group contract. EIN: 921227672'
FROM payers p, provider_entities pe
WHERE p.payer_name = 'Optum / UHC' AND pe.npi_number = '1003521006';

-- Optum/UHC × Jodene Jensen Individual
INSERT INTO contracts (payer_id, provider_entity_id, payer_contract_id, product_line, effective_date, active, notes)
SELECT p.payer_id, pe.provider_entity_id, '008492810', 'Commercial', '2024-01-01', TRUE,
       'Optum/UHC Individual contract. EIN: 921227672'
FROM payers p, provider_entities pe
WHERE p.payer_name = 'Optum / UHC' AND pe.npi_number = '1093433955';


-- ============================================================
-- NEGOTIATION TARGETS (global default: 130% of Medicare)
-- You can add payer-specific or code-specific targets later.
-- ============================================================
INSERT INTO negotiation_targets (payer_id, cpt_code, target_pct_of_medicare, notes)
VALUES (NULL, NULL, 130.00, 'Global default target: 130% of Medicare for all payers and codes')
ON CONFLICT (payer_id, cpt_code) DO NOTHING;
