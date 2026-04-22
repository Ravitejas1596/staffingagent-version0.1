-- Migration 028: Add columns to timesheets required by platform API model

BEGIN;

ALTER TABLE timesheets
    ADD COLUMN IF NOT EXISTS regular_hours  NUMERIC(8, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ot_hours       NUMERIC(8, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS bill_rate      NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS ot_rate        NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS total_amount   NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS bullhorn_id    TEXT,
    ADD COLUMN IF NOT EXISTS synced_at      TIMESTAMPTZ NOT NULL DEFAULT now();

-- Also add missing columns to placements
ALTER TABLE placements
    ADD COLUMN IF NOT EXISTS ot_rate        NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS state          TEXT,
    ADD COLUMN IF NOT EXISTS po_number      TEXT,
    ADD COLUMN IF NOT EXISTS synced_at      TIMESTAMPTZ NOT NULL DEFAULT now();

COMMIT;
