-- Migration 051: agent_settings — per-tenant configuration for agents.
--
-- Keyed by (tenant_id, agent_type, setting_key) so any agent can store its
-- own configuration without needing a dedicated table. setting_value is
-- JSONB so complex nested settings (e.g. Group C tolerance with per-variant
-- overrides) live in one row without schema churn.
--
-- Platform-default settings are NOT stored here — defaults live in code
-- (src/agents/<agent>/config.py) and this table only holds tenant overrides.
-- Detect stage reads: override ? override : platform_default.
--
-- Reference: Time Anomaly build plan, Week 2 Day 4.

BEGIN;

CREATE TABLE IF NOT EXISTS agent_settings (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_type     TEXT NOT NULL,               -- 'time_anomaly', etc.
    setting_key    TEXT NOT NULL,               -- dotted path, e.g. 'group_c.tolerance_pct'
    setting_value  JSONB NOT NULL,
    updated_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_agent_settings_tenant_agent_key
        UNIQUE (tenant_id, agent_type, setting_key)
);

CREATE INDEX IF NOT EXISTS idx_agent_settings_lookup
    ON agent_settings (tenant_id, agent_type);

CREATE OR REPLACE FUNCTION agent_settings_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_settings_updated_at ON agent_settings;
CREATE TRIGGER trg_agent_settings_updated_at
    BEFORE UPDATE ON agent_settings
    FOR EACH ROW
    EXECUTE FUNCTION agent_settings_set_updated_at();

ALTER TABLE agent_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_settings FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_settings_isolation ON agent_settings;
CREATE POLICY agent_settings_isolation ON agent_settings
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
