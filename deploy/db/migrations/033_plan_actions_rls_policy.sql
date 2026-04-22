-- Migration 033: Add RLS policy for agent_plan_actions and fix vms_candidates grant
-- RLS was enabled in 022 but no policy was created, blocking all app_user access.

BEGIN;

-- Allow app_user full access to agent_plan_actions (tenant isolation via agent_runs join)
CREATE POLICY plan_actions_app_user ON agent_plan_actions
    FOR ALL
    TO app_user
    USING (true)
    WITH CHECK (true);

COMMIT;
