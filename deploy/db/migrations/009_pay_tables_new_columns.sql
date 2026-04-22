-- Migration 009: Add new columns to payable_charges, pay_masters, pay_master_transactions

BEGIN;

-- payable_charges: GL segments, currency, entry type, adjustment flag (mirrors billable_charges)
ALTER TABLE payable_charges
    ADD COLUMN IF NOT EXISTS transaction_type   TEXT,
    ADD COLUMN IF NOT EXISTS currency_unit      TEXT,
    ADD COLUMN IF NOT EXISTS entry_type         TEXT,
    ADD COLUMN IF NOT EXISTS external_id        TEXT,
    ADD COLUMN IF NOT EXISTS description        TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment1_number TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment1_name   TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment2_number TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment2_name   TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment3_number TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment3_name   TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment4_number TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment4_name   TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment5_number TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment5_name   TEXT,
    ADD COLUMN IF NOT EXISTS gl_service_code    TEXT,
    ADD COLUMN IF NOT EXISTS has_adjustment     BOOLEAN;

-- pay_masters: mirrors bill_masters additions + missing date/status fields
ALTER TABLE pay_masters
    ADD COLUMN IF NOT EXISTS date_added         DATE,
    ADD COLUMN IF NOT EXISTS date_last_modified DATE,
    ADD COLUMN IF NOT EXISTS charge_type        TEXT,
    ADD COLUMN IF NOT EXISTS transaction_status TEXT,
    ADD COLUMN IF NOT EXISTS pay_sync_batch_id  INTEGER,
    ADD COLUMN IF NOT EXISTS can_pay            BOOLEAN,
    ADD COLUMN IF NOT EXISTS external_id        TEXT;

-- pay_master_transactions: mirrors bill_master_transactions additions
ALTER TABLE pay_master_transactions
    ADD COLUMN IF NOT EXISTS is_unbillable          BOOLEAN,
    ADD COLUMN IF NOT EXISTS needs_review           BOOLEAN,
    ADD COLUMN IF NOT EXISTS accounting_period_id   INTEGER,
    ADD COLUMN IF NOT EXISTS accounting_period_date DATE,
    ADD COLUMN IF NOT EXISTS is_custom_rate         BOOLEAN,
    ADD COLUMN IF NOT EXISTS was_unbilled           BOOLEAN;

COMMIT;
