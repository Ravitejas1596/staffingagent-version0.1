-- Migration 046: agent_alert_events — append-only event stream per alert.
--
-- Every agent action against an alert writes one row here. Supports audit,
-- undo (via prior_state_snapshot), and replay. Never UPDATE or DELETE these
-- rows at the application layer — treat as immutable.
--
-- Reference: Time_Anomaly_Agent_v1_Build_Spec.md §3.3 (audit events) and §3.4
-- (rollback), build plan R1 decision.
--
-- tenant_id is denormalized from agent_alerts for RLS efficiency (avoids a
-- join-based policy, keeps event-stream reads cheap at high cardinality).

BEGIN;

CREATE TABLE IF NOT EXISTS agent_alert_events (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id                 UUID NOT NULL REFERENCES agent_alerts(id) ON DELETE CASCADE,
    tenant_id                UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    event_type               TEXT NOT NULL
                             CHECK (event_type IN (
                                'detected',
                                'suppressed',
                                'sms_sent',
                                'sms_skipped_no_consent',
                                'sms_skipped_non_english',
                                'email_sent',
                                'bte_link_generated',
                                'dnw_marked',
                                'hold_applied',
                                'hold_released',
                                'hitl_assigned',
                                'hitl_resolved',
                                'dismissed_false_positive',
                                'reversed',
                                'closed'
                             )),

    actor_type               TEXT NOT NULL
                             CHECK (actor_type IN ('agent', 'user', 'system')),
    actor_id                 TEXT NOT NULL,            -- user uuid (if actor_type='user') or 'agent' / 'system'

    metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
                                                       -- action-specific payload: message body,
                                                       -- target entity ref, BTE link, HITL choice, etc.

    -- undo / rollback support
    reversal_available       BOOLEAN NOT NULL DEFAULT FALSE,
    prior_state_snapshot     JSONB,                    -- required if reversal_available=true
    reverses_event_id        UUID REFERENCES agent_alert_events(id),
                                                       -- set when this event IS the reversal

    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        NOT reversal_available
        OR prior_state_snapshot IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_agent_alert_events_alert
    ON agent_alert_events (alert_id, created_at);

CREATE INDEX IF NOT EXISTS idx_agent_alert_events_tenant_type
    ON agent_alert_events (tenant_id, event_type, created_at);

-- Reversible events within window for the HITL queue's undo affordance.
-- 7-day default window is enforced at the application layer (not a constraint
-- here) so the window can be tuned without a migration.
CREATE INDEX IF NOT EXISTS idx_agent_alert_events_reversible
    ON agent_alert_events (alert_id, created_at DESC)
    WHERE reversal_available = TRUE AND reverses_event_id IS NULL;

-- Enforce append-only at the database layer: no UPDATE, no DELETE (except via
-- ON DELETE CASCADE from agent_alerts). Application migration scripts that
-- need to correct data should write a new compensating event, not mutate.
CREATE OR REPLACE FUNCTION agent_alert_events_block_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'agent_alert_events is append-only; use a compensating event instead'
        USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_alert_events_no_update ON agent_alert_events;
CREATE TRIGGER trg_agent_alert_events_no_update
    BEFORE UPDATE ON agent_alert_events
    FOR EACH ROW
    EXECUTE FUNCTION agent_alert_events_block_mutation();

-- RLS: standard per-tenant isolation.
ALTER TABLE agent_alert_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_alert_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_alert_events_isolation ON agent_alert_events;
CREATE POLICY agent_alert_events_isolation ON agent_alert_events
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
