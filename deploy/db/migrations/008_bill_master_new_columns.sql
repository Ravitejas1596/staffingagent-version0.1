-- Migration 008: Add new columns to billable_charges, bill_masters, bill_master_transactions

BEGIN;

-- billable_charges: billing profile + adjustment flag
ALTER TABLE billable_charges
    ADD COLUMN IF NOT EXISTS has_adjustment       BOOLEAN,
    ADD COLUMN IF NOT EXISTS billing_profile_id   INTEGER,
    ADD COLUMN IF NOT EXISTS billing_profile_title TEXT;

-- bill_masters: sync batch, invoiceable flag, external ID
ALTER TABLE bill_masters
    ADD COLUMN IF NOT EXISTS billing_sync_batch_id INTEGER,
    ADD COLUMN IF NOT EXISTS can_invoice           BOOLEAN,
    ADD COLUMN IF NOT EXISTS external_id           TEXT;

-- bill_master_transactions: accounting period, custom rate, unbilled flag
ALTER TABLE bill_master_transactions
    ADD COLUMN IF NOT EXISTS accounting_period_id   INTEGER,
    ADD COLUMN IF NOT EXISTS accounting_period_date DATE,
    ADD COLUMN IF NOT EXISTS is_custom_rate         BOOLEAN,
    ADD COLUMN IF NOT EXISTS was_unbilled           BOOLEAN;

COMMIT;
