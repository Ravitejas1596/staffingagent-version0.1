-- Migration 020: Add remaining platform API columns to users table

BEGIN;

-- bullhorn_user_id required by platform API User model
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS bullhorn_user_id TEXT;

-- Ensure role column exists as TEXT (may already be a user_role enum type)
-- We add a new text column only if role doesn't exist; if it exists as enum that's fine
-- since SQLAlchemy Text type is compatible with PostgreSQL enum reads.
-- (No action needed for role — it already exists.)

-- agent_type already exists as an enum column in agent_runs; no changes needed.

-- AgentResult: add columns required by model that may be missing
ALTER TABLE agent_results
    ADD COLUMN IF NOT EXISTS vms_snapshot   JSONB,
    ADD COLUMN IF NOT EXISTS ats_snapshot   JSONB,
    ADD COLUMN IF NOT EXISTS risk_level     TEXT;

COMMIT;
