-- Migration 045: agent_alerts — alert lifecycle container.
--
-- One row per fired alert. Tracks the alert's progression through the 5-stage
-- state machine: Detect -> Outreach -> Wait/Recheck -> Escalate HITL -> Close.
-- Reference: Time_Anomaly_Agent_v1_Build_Spec.md §4, build plan R1 decision.
--
-- Distinct from agent_plan_actions:
--   agent_alerts        = "why" — the alert and its lifecycle state
--   agent_plan_actions  = "what" — individual actions (send_sms, etc.) the agent
--                         proposes, some auto-approved, some pending HITL
--   agent_alert_events  = "what happened" — append-only event log (migration 046)

BEGIN;

CREATE TABLE IF NOT EXISTS agent_alerts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_type              TEXT NOT NULL,              -- 'time_anomaly', 'risk_alert', etc.
    alert_type              TEXT NOT NULL,              -- 'group_a1_first_miss', 'group_b_reg_over_limit', etc.
    severity                TEXT NOT NULL
                            CHECK (severity IN ('medium', 'high')),
    state                   TEXT NOT NULL DEFAULT 'detected'
                            CHECK (state IN ('detected', 'outreach_sent', 'wait_recheck',
                                             'escalated_hitl', 'resolved')),
    resolution              TEXT
                            CHECK (resolution IS NULL OR resolution IN (
                                'employee_corrected',
                                'hitl_resolved',
                                'excluded',
                                'dismissed_false_positive'
                            )),

    -- entity under alert (either placement_id, candidate_id, or both populated)
    placement_id            UUID REFERENCES placements(id) ON DELETE SET NULL,
    candidate_id            UUID REFERENCES candidates(id) ON DELETE SET NULL,

    pay_period_start        DATE,
    pay_period_end          DATE,

    trigger_context         JSONB NOT NULL,              -- original detection payload
    assigned_to             UUID REFERENCES users(id) ON DELETE SET NULL,
    langgraph_thread_id     TEXT,                        -- LangGraph checkpoint lookup

    -- lifecycle timestamps
    detected_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    outreach_sent_at        TIMESTAMPTZ,
    first_reminder_at       TIMESTAMPTZ,
    escalated_at            TIMESTAMPTZ,
    resolved_at             TIMESTAMPTZ,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        (state = 'resolved' AND resolution IS NOT NULL)
        OR (state <> 'resolved' AND resolution IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_agent_alerts_tenant_state
    ON agent_alerts (tenant_id, agent_type, state)
    WHERE state <> 'resolved';

CREATE INDEX IF NOT EXISTS idx_agent_alerts_placement_period
    ON agent_alerts (tenant_id, placement_id, pay_period_start);

CREATE INDEX IF NOT EXISTS idx_agent_alerts_assigned
    ON agent_alerts (tenant_id, assigned_to)
    WHERE assigned_to IS NOT NULL AND state = 'escalated_hitl';

CREATE INDEX IF NOT EXISTS idx_agent_alerts_thread
    ON agent_alerts (langgraph_thread_id)
    WHERE langgraph_thread_id IS NOT NULL;

-- updated_at trigger — keep in sync automatically
CREATE OR REPLACE FUNCTION agent_alerts_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_alerts_updated_at ON agent_alerts;
CREATE TRIGGER trg_agent_alerts_updated_at
    BEFORE UPDATE ON agent_alerts
    FOR EACH ROW
    EXECUTE FUNCTION agent_alerts_set_updated_at();

-- RLS: standard per-tenant isolation, same pattern as migration 041.
ALTER TABLE agent_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_alerts FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_alerts_isolation ON agent_alerts;
CREATE POLICY agent_alerts_isolation ON agent_alerts
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
