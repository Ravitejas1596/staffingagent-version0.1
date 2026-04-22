-- Migration 043: Audit trail for every user role change.
--
-- Security Sprint Workstream 6: we block super_admin self-promotion and
-- role-escalation attacks at the application layer (admin.py, users.py).
-- This table captures every role change so we can detect missed paths.

BEGIN;

CREATE TABLE IF NOT EXISTS role_change_audit (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID REFERENCES tenants(id) ON DELETE SET NULL,
    target_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
    caller_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
    from_role       TEXT,
    to_role         TEXT NOT NULL,
    via_endpoint    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_role_change_audit_tenant
    ON role_change_audit (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_role_change_audit_target
    ON role_change_audit (target_user_id, created_at DESC);

GRANT SELECT, INSERT ON role_change_audit TO app_user;

-- This table is append-only audit; RLS by tenant_id for isolation, except
-- super_admin (bypass) can read the whole history.
ALTER TABLE role_change_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_change_audit FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS role_change_audit_isolation ON role_change_audit;
CREATE POLICY role_change_audit_isolation ON role_change_audit
    FOR ALL TO app_user
    USING (
        current_setting('app.bypass_rls', true) = 'on'
        OR tenant_id::text = current_setting('app.tenant_id', true)
    )
    WITH CHECK (
        current_setting('app.bypass_rls', true) = 'on'
        OR tenant_id::text = current_setting('app.tenant_id', true)
    );

COMMIT;
