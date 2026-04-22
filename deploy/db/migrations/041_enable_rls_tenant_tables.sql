-- Migration 041: Enforce tenant isolation at the database layer via RLS.
--
-- Before this migration, tenant isolation relied entirely on application-level
-- WHERE tenant_id = ... clauses. Any forgotten filter, IDOR, or SQL-injection
-- path could leak cross-tenant data. After this migration, PostgreSQL RLS
-- blocks cross-tenant reads and writes even if the application query is wrong.
--
-- Session contract (set by the application in get_tenant_session /
-- get_platform_session in app_platform/api/database.py):
--   SET LOCAL app.tenant_id   = '<uuid>'   -- tenant-scoped session
--   SET LOCAL app.bypass_rls  = 'on'       -- super_admin / platform session
--
-- The bypass flag is preferred over creating a BYPASSRLS role because it
-- avoids adding a second DB password to Secrets Manager and keeps the
-- bypass decision in application code (guarded by require_super_admin).
--
-- The policies below grant app_user full access on rows matching the
-- session tenant_id, OR when app.bypass_rls is 'on'. Admin migrations
-- continue to run as the postgres superuser (DATABASE_ADMIN_URL) which
-- bypasses RLS by default.

BEGIN;

-- ---------------------------------------------------------------------------
-- Reusable helper: every tenant table gets an identical policy shape.
-- We inline the USING/WITH CHECK expressions rather than a function because
-- Postgres inlines simple CTEs better than PL/pgSQL here.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- tenants: the row's PK column is `id`, not `tenant_id`.
-- ---------------------------------------------------------------------------
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenants_isolation ON tenants;
CREATE POLICY tenants_isolation ON tenants
    FOR ALL TO app_user
    USING (
        current_setting('app.bypass_rls', true) = 'on'
        OR id::text = current_setting('app.tenant_id', true)
    )
    WITH CHECK (
        current_setting('app.bypass_rls', true) = 'on'
        OR id::text = current_setting('app.tenant_id', true)
    );

-- ---------------------------------------------------------------------------
-- Standard tenant-scoped tables (rows have a `tenant_id UUID` column).
-- Using a DO block so we can apply the same policy shape to every table
-- and skip tables that do not exist yet in a given environment.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    t TEXT;
    tables TEXT[] := ARRAY[
        'users',
        'placements',
        'timesheets',
        'timesheet_entries',
        'vms_uploads',
        'vms_records',
        'vms_matches',
        'vms_name_aliases',
        'invoices',
        'agent_runs',
        'agent_results',
        'audit_log',
        'client_corporations',
        'job_orders',
        'candidates',
        'billable_charges',
        'bill_masters',
        'bill_master_transactions',
        'payable_charges',
        'pay_masters',
        'pay_master_transactions',
        'timeops_exclusions',
        'riskops_resolutions',
        'subscription_state',
        'sync_state',
        'sync_history'
    ];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = t AND column_name = 'tenant_id'
        ) THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_isolation', t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    FOR ALL TO app_user
                    USING (
                        current_setting('app.bypass_rls', true) = 'on'
                        OR tenant_id::text = current_setting('app.tenant_id', true)
                    )
                    WITH CHECK (
                        current_setting('app.bypass_rls', true) = 'on'
                        OR tenant_id::text = current_setting('app.tenant_id', true)
                    )
            $pol$, t || '_isolation', t);
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- agent_plan_actions has no tenant_id column; isolation flows through its
-- parent agent_runs row. Replace the permissive USING (true) policy that
-- was added in migration 033.
-- ---------------------------------------------------------------------------
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'agent_plan_actions'
    ) THEN
        ALTER TABLE agent_plan_actions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE agent_plan_actions FORCE ROW LEVEL SECURITY;

        DROP POLICY IF EXISTS plan_actions_app_user ON agent_plan_actions;
        DROP POLICY IF EXISTS agent_plan_actions_isolation ON agent_plan_actions;

        CREATE POLICY agent_plan_actions_isolation ON agent_plan_actions
            FOR ALL TO app_user
            USING (
                current_setting('app.bypass_rls', true) = 'on'
                OR EXISTS (
                    SELECT 1 FROM agent_runs r
                    WHERE r.id = agent_plan_actions.run_id
                      AND r.tenant_id::text = current_setting('app.tenant_id', true)
                )
            )
            WITH CHECK (
                current_setting('app.bypass_rls', true) = 'on'
                OR EXISTS (
                    SELECT 1 FROM agent_runs r
                    WHERE r.id = agent_plan_actions.run_id
                      AND r.tenant_id::text = current_setting('app.tenant_id', true)
                )
            );
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Ensure app_user can still read agent_runs inside the sub-select above.
-- It already has SELECT on agent_runs from earlier migrations; reassert.
-- ---------------------------------------------------------------------------
GRANT SELECT ON agent_runs TO app_user;

COMMIT;
