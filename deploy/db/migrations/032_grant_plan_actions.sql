-- Migration 032: Grant app_user access to agent_plan_actions table

BEGIN;

GRANT SELECT, INSERT, UPDATE ON agent_plan_actions TO app_user;

COMMIT;
