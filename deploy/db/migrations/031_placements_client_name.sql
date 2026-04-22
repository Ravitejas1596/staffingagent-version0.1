-- Migration 031: Add client_name to placements (referenced by risk-alert and vms-match agents)

BEGIN;

ALTER TABLE placements
    ADD COLUMN IF NOT EXISTS client_name TEXT;

COMMIT;
