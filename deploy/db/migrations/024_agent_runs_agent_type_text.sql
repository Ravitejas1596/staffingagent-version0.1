-- Migration 024: Convert agent_runs.agent_type from enum to TEXT

BEGIN;

ALTER TABLE agent_runs
    ALTER COLUMN agent_type TYPE TEXT USING agent_type::TEXT;

COMMIT;
