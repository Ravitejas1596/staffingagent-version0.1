-- Migration 016: Create VMS uploads and records tables (idempotent)

BEGIN;

CREATE TABLE IF NOT EXISTS vms_uploads (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    uploaded_by    UUID        REFERENCES users(id) ON DELETE SET NULL,
    filename       TEXT        NOT NULL,
    s3_key         TEXT        NOT NULL,
    vms_platform   TEXT,
    record_count   INTEGER,
    column_mapping JSONB       NOT NULL DEFAULT '{}',
    status         TEXT        NOT NULL DEFAULT 'pending',
    error_message  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS vms_records (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    upload_id      UUID        REFERENCES vms_uploads(id) ON DELETE SET NULL,
    vms_platform   TEXT,
    placement_ref  TEXT,
    candidate_name TEXT,
    week_ending    DATE,
    regular_hours  NUMERIC(8,2)  NOT NULL DEFAULT 0,
    ot_hours       NUMERIC(8,2)  NOT NULL DEFAULT 0,
    bill_rate      NUMERIC(10,2),
    ot_rate        NUMERIC(10,2),
    per_diem       NUMERIC(10,2) NOT NULL DEFAULT 0,
    total_amount   NUMERIC(12,2),
    po_number      TEXT,
    status         TEXT,
    source_type    TEXT        NOT NULL DEFAULT 'file',
    raw_data       JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vms_uploads_tenant  ON vms_uploads(tenant_id);
CREATE INDEX IF NOT EXISTS idx_vms_uploads_status  ON vms_uploads(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_vms_records_tenant  ON vms_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_vms_records_week    ON vms_records(tenant_id, week_ending);
CREATE INDEX IF NOT EXISTS idx_vms_records_upload  ON vms_records(upload_id);

COMMIT;
