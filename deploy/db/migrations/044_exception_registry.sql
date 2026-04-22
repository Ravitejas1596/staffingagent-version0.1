-- Migration 044: exception_registry shared platform primitive.
--
-- Tracks exceptions, dismissals, and suppressions shared across ALL agents.
-- Every agent's Detect stage MUST query this table before firing any alert.
-- Reference: Time_Anomaly_Agent_v1_Build_Spec.md §7.1 (Cortney Maiden).
--
-- Scope semantics:
--   permanent          -- never fire this alert again for this entity (hard ignore)
--   per_cycle          -- suppress for one pay period / billing cycle, then re-enable
--   suppression_window -- suppress for expires_at duration, reset if magnitude
--                         exceeds magnitude_threshold * original trigger magnitude
--
-- Group C false-positive dismissals write suppression_window rows with a 60-day
-- expiry and 2.0x magnitude multiplier by default (both tenant-configurable).

BEGIN;

CREATE TABLE IF NOT EXISTS exception_registry (
    exception_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id              TEXT NOT NULL,           -- 'time_anomaly', 'risk_alert', etc.
    alert_type            TEXT NOT NULL,           -- e.g. 'group_c_variance', 'group_a1_first_miss'
    scope                 TEXT NOT NULL
                          CHECK (scope IN ('permanent', 'per_cycle', 'suppression_window')),
    entity_type           TEXT NOT NULL
                          CHECK (entity_type IN ('employee', 'placement', 'billable_charge')),
    entity_id             TEXT NOT NULL,           -- Bullhorn record id as text (int or uuid)
    trigger_context       JSONB,                   -- original alert payload for reference
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by            TEXT NOT NULL,           -- user uuid (HITL) or 'agent'
    expires_at            TIMESTAMPTZ,             -- NULL for permanent / per_cycle
    magnitude_threshold   NUMERIC(10, 4),          -- for suppression_window only (e.g. 2.0 = 2x)
    original_magnitude    NUMERIC(10, 4),          -- magnitude of the dismissed trigger
    notes                 TEXT
);

CREATE INDEX IF NOT EXISTS idx_exception_registry_lookup
    ON exception_registry (tenant_id, agent_id, alert_type, entity_type, entity_id)
    WHERE expires_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_exception_registry_expiry
    ON exception_registry (expires_at)
    WHERE expires_at IS NOT NULL;

-- RLS: standard per-tenant isolation, same pattern as migration 041.
ALTER TABLE exception_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE exception_registry FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS exception_registry_isolation ON exception_registry;
CREATE POLICY exception_registry_isolation ON exception_registry
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
