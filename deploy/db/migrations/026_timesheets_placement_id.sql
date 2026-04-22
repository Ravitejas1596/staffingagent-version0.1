-- Migration 026: Add placement_id to timesheets (referenced by time-anomaly agent)

BEGIN;

ALTER TABLE timesheets
    ADD COLUMN IF NOT EXISTS placement_id UUID REFERENCES placements(id) ON DELETE SET NULL;

COMMIT;
