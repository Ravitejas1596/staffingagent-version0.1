-- Migration 029: Add remaining columns to timesheets needed by platform API model
-- Migration 002 created timesheets without status, bill_rate, ot_rate, total_amount.

BEGIN;

ALTER TABLE timesheets
    ADD COLUMN IF NOT EXISTS status       TEXT,
    ADD COLUMN IF NOT EXISTS bill_rate    NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS ot_rate      NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS total_amount NUMERIC(12, 2);

COMMIT;
