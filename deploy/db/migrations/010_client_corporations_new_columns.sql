-- Migration 010: Expand client_corporations with full field set from Bullhorn SDK

BEGIN;

ALTER TABLE client_corporations
    ADD COLUMN IF NOT EXISTS date_last_modified             DATE,
    ADD COLUMN IF NOT EXISTS phone                          TEXT,
    ADD COLUMN IF NOT EXISTS fax                            TEXT,
    ADD COLUMN IF NOT EXISTS billing_phone                  TEXT,
    ADD COLUMN IF NOT EXISTS external_id                    TEXT,
    ADD COLUMN IF NOT EXISTS num_employees                  INTEGER,
    ADD COLUMN IF NOT EXISTS revenue                        NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS annual_revenue                 NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS fee_arrangement                NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS tax_rate                       NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS work_week_start                INTEGER,
    ADD COLUMN IF NOT EXISTS billing_frequency              TEXT,
    ADD COLUMN IF NOT EXISTS invoice_format                 TEXT,
    ADD COLUMN IF NOT EXISTS ownership                      TEXT,
    ADD COLUMN IF NOT EXISTS ticker_symbol                  TEXT,
    ADD COLUMN IF NOT EXISTS date_founded                   DATE,
    ADD COLUMN IF NOT EXISTS twitter_handle                 TEXT,
    ADD COLUMN IF NOT EXISTS linkedin_profile_name          TEXT,
    ADD COLUMN IF NOT EXISTS facebook_profile_name          TEXT,
    ADD COLUMN IF NOT EXISTS address1                       TEXT,
    ADD COLUMN IF NOT EXISTS address2                       TEXT,
    ADD COLUMN IF NOT EXISTS city                           TEXT,
    ADD COLUMN IF NOT EXISTS state                          TEXT,
    ADD COLUMN IF NOT EXISTS zip                            TEXT,
    ADD COLUMN IF NOT EXISTS billing_address1               TEXT,
    ADD COLUMN IF NOT EXISTS billing_address2               TEXT,
    ADD COLUMN IF NOT EXISTS billing_city                   TEXT,
    ADD COLUMN IF NOT EXISTS billing_state                  TEXT,
    ADD COLUMN IF NOT EXISTS billing_zip                    TEXT,
    ADD COLUMN IF NOT EXISTS parent_client_corporation_id   INTEGER,
    ADD COLUMN IF NOT EXISTS parent_client_corporation_name TEXT,
    ADD COLUMN IF NOT EXISTS department_id                  INTEGER,
    ADD COLUMN IF NOT EXISTS department_name                TEXT,
    ADD COLUMN IF NOT EXISTS branch_id                      INTEGER,
    ADD COLUMN IF NOT EXISTS branch_name                    TEXT,
    ADD COLUMN IF NOT EXISTS billing_contact_id             INTEGER,
    ADD COLUMN IF NOT EXISTS billing_contact_first          TEXT,
    ADD COLUMN IF NOT EXISTS billing_contact_last           TEXT;

CREATE INDEX IF NOT EXISTS idx_client_corps_city  ON client_corporations(city);
CREATE INDEX IF NOT EXISTS idx_client_corps_state ON client_corporations(state);

COMMIT;
