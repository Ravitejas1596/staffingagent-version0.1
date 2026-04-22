-- Migration 039: Remediate migrations 031-037 that were baselined (marked applied
-- but never actually executed due to DATABASE_ADMIN_URL having the wrong password).
-- All statements use IF NOT EXISTS / DO blocks so they are safe to re-run.

-- 031: placements.client_name
ALTER TABLE placements
    ADD COLUMN IF NOT EXISTS client_name TEXT;

-- 032: Grant app_user access to agent_plan_actions
GRANT SELECT, INSERT, UPDATE ON agent_plan_actions TO app_user;

-- 033: RLS policy for agent_plan_actions
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'agent_plan_actions'
          AND policyname = 'plan_actions_app_user'
    ) THEN
        CREATE POLICY plan_actions_app_user ON agent_plan_actions
            FOR ALL TO app_user
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;

-- 034: invoices.is_finalized
ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS is_finalized BOOLEAN;

CREATE INDEX IF NOT EXISTS idx_invoices_finalized ON invoices(tenant_id, is_finalized);

-- 035: timeops_exclusions and riskops_resolutions tables
CREATE TABLE IF NOT EXISTS timeops_exclusions (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    placement_bullhorn_id   TEXT NOT NULL,
    period_end_date         DATE NOT NULL,
    is_excluded             BOOLEAN NOT NULL DEFAULT TRUE,
    excluded_by             TEXT,
    excluded_at             TIMESTAMPTZ,
    last_reminder_sent_at   TIMESTAMPTZ,
    comments                TEXT NOT NULL DEFAULT '',
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, placement_bullhorn_id, period_end_date)
);

CREATE INDEX IF NOT EXISTS idx_timeops_excl_tenant ON timeops_exclusions(tenant_id, period_end_date);

CREATE TABLE IF NOT EXISTS riskops_resolutions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    record_key      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'Open',
    resolved_by     TEXT,
    resolved_at     TIMESTAMPTZ,
    comments        TEXT NOT NULL DEFAULT '',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, record_key)
);

CREATE INDEX IF NOT EXISTS idx_riskops_resol_tenant ON riskops_resolutions(tenant_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON timeops_exclusions TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON riskops_resolutions TO app_user;

-- 036: subscription_state table
CREATE TABLE IF NOT EXISTS subscription_state (
    tenant_id        UUID    NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subscription_id  TEXT    NOT NULL,
    last_request_id  BIGINT  NOT NULL DEFAULT 0,
    entity_types     TEXT[]  NOT NULL DEFAULT '{}',
    registered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_polled_at   TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, subscription_id)
);

CREATE INDEX IF NOT EXISTS idx_subscription_state_tenant ON subscription_state(tenant_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON subscription_state TO app_user;

-- 037: agent_results.review_status
ALTER TABLE agent_results
    ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'pending';
