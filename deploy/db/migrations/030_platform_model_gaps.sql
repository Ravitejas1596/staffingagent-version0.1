-- Migration 030: Add all remaining columns/tables required by platform API models

BEGIN;

-- invoices: add missing columns
ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS paid_date        DATE,
    ADD COLUMN IF NOT EXISTS days_outstanding INTEGER,
    ADD COLUMN IF NOT EXISTS synced_at        TIMESTAMPTZ NOT NULL DEFAULT now();

-- audit_log: drop and recreate (may have been partially created by botched earlier run)
DROP TABLE IF EXISTS audit_log;
CREATE TABLE IF NOT EXISTS audit_log (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id                TEXT NOT NULL,
    action_type             TEXT NOT NULL,
    target_resource         TEXT NOT NULL DEFAULT '',
    input_hash              TEXT NOT NULL DEFAULT '',
    output_summary          TEXT NOT NULL DEFAULT '',
    status                  TEXT NOT NULL DEFAULT 'success',
    human_approval_required BOOLEAN NOT NULL DEFAULT false,
    approved_by             UUID REFERENCES users(id),
    parent_task_id          UUID,
    verification_status     TEXT,
    token_usage             JSONB,
    duration_ms             INTEGER NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_tenant ON audit_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_agent  ON audit_log(tenant_id, agent_id);

GRANT SELECT, INSERT ON audit_log TO app_user;

COMMIT;
