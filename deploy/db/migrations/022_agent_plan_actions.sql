-- Migration 022: Add plan-approve-execute columns to agent_runs and create agent_plan_actions table
-- Required for the agentic execution framework (plan → approve → execute → report cycle).

BEGIN;

-- Add new columns to agent_runs (all nullable so existing rows are unaffected)
ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS plan        JSONB,
    ADD COLUMN IF NOT EXISTS execution_report JSONB,
    ADD COLUMN IF NOT EXISTS approved_by  UUID REFERENCES users(id),
    ADD COLUMN IF NOT EXISTS approved_at  TIMESTAMPTZ;

-- Create agent_plan_actions table
CREATE TABLE IF NOT EXISTS agent_plan_actions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID NOT NULL REFERENCES agent_runs(id),
    action_type       TEXT NOT NULL,
    target_ref        TEXT,
    target_name       TEXT,
    description       TEXT NOT NULL,
    confidence        NUMERIC(4,3),
    severity          TEXT,
    financial_impact  NUMERIC(12,2),
    details           JSONB,
    approval_status   TEXT NOT NULL DEFAULT 'pending',
    execution_status  TEXT NOT NULL DEFAULT 'pending',
    execution_result  JSONB,
    error_message     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plan_actions_run ON agent_plan_actions(run_id);

-- Enable RLS on the new table (tenant isolation via agent_runs.tenant_id join)
ALTER TABLE agent_plan_actions ENABLE ROW LEVEL SECURITY;

COMMIT;
