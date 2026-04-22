-- Migration 025: Convert agent_runs.status from run_status enum to TEXT

BEGIN;

ALTER TABLE agent_runs
    ALTER COLUMN status TYPE TEXT USING status::TEXT;

COMMIT;
