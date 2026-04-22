-- Migration 023: Add missing columns to agent_runs required by platform API model

BEGIN;

ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}';

COMMIT;
