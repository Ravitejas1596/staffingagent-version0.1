-- Migration 007: Add billing, GL, and metadata columns to billable_charges

BEGIN;

ALTER TABLE billable_charges
    ADD COLUMN IF NOT EXISTS billing_client_contact_id       INTEGER,
    ADD COLUMN IF NOT EXISTS billing_client_contact_first    TEXT,
    ADD COLUMN IF NOT EXISTS billing_client_contact_last     TEXT,
    ADD COLUMN IF NOT EXISTS billing_client_corporation_id   INTEGER,
    ADD COLUMN IF NOT EXISTS billing_client_corporation_name TEXT,
    ADD COLUMN IF NOT EXISTS currency_unit                   TEXT,
    ADD COLUMN IF NOT EXISTS entry_type                      TEXT,
    ADD COLUMN IF NOT EXISTS external_id                     TEXT,
    ADD COLUMN IF NOT EXISTS description                     TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment1_number              TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment1_name                TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment2_number              TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment2_name                TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment3_number              TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment3_name                TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment4_number              TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment4_name                TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment5_number              TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment5_name                TEXT,
    ADD COLUMN IF NOT EXISTS gl_service_code                 TEXT,
    ADD COLUMN IF NOT EXISTS has_rebill                      BOOLEAN,
    ADD COLUMN IF NOT EXISTS invoice_term_id                 INTEGER,
    ADD COLUMN IF NOT EXISTS transaction_type                TEXT;

COMMIT;
