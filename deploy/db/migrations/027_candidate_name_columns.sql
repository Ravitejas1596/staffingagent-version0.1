-- Migration 027: Add candidate_name to placements and timesheets
-- The platform API model uses candidate_name; the DB has candidate_first/candidate_last.

BEGIN;

ALTER TABLE placements
    ADD COLUMN IF NOT EXISTS candidate_name TEXT;

UPDATE placements
    SET candidate_name = TRIM(COALESCE(candidate_first, '') || ' ' || COALESCE(candidate_last, ''))
    WHERE candidate_name IS NULL;

ALTER TABLE timesheets
    ADD COLUMN IF NOT EXISTS candidate_name TEXT;

COMMIT;
