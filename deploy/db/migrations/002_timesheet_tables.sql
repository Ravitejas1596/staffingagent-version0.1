-- Migration 002: Rebuild timesheets table with correct Bullhorn fields,
-- add timesheet_entries table.

BEGIN;

-- Drop old timesheets table (schema was based on non-existent TimeLaborEval entity)
DROP TABLE IF EXISTS timesheets CASCADE;

-- Timesheets (Timesheet entity in Bullhorn)
CREATE TABLE timesheets (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id             INTEGER NOT NULL,
    placement_bullhorn_id   INTEGER,
    candidate_first         TEXT,
    candidate_last          TEXT,
    client_name             TEXT,
    job_title               TEXT,
    week_ending             DATE,
    hours_worked            NUMERIC(8, 2) NOT NULL DEFAULT 0,
    additional_bill_amount  NUMERIC(12, 2) NOT NULL DEFAULT 0,
    additional_pay_amount   NUMERIC(12, 2) NOT NULL DEFAULT 0,
    evaluation_state        TEXT,
    processing_status       TEXT,
    approval_status         TEXT,
    raw_data                JSONB NOT NULL DEFAULT '{}',
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_timesheets_tenant     ON timesheets(tenant_id);
CREATE INDEX idx_timesheets_week       ON timesheets(week_ending);
CREATE INDEX idx_timesheets_placement  ON timesheets(placement_bullhorn_id);
CREATE INDEX idx_timesheets_approval   ON timesheets(approval_status);

-- TimesheetEntry (individual line items within a Timesheet)
CREATE TABLE timesheet_entries (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id             INTEGER NOT NULL,
    timesheet_bullhorn_id   INTEGER,
    applicable_from         DATE,
    applicable_to           DATE,
    quantity                NUMERIC(8, 2) NOT NULL DEFAULT 0,
    bill_rate               NUMERIC(12, 4),
    pay_rate                NUMERIC(12, 4),
    comment                 TEXT,
    earn_code               TEXT,
    approval_status         TEXT,
    raw_data                JSONB NOT NULL DEFAULT '{}',
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_ts_entries_tenant     ON timesheet_entries(tenant_id);
CREATE INDEX idx_ts_entries_timesheet  ON timesheet_entries(timesheet_bullhorn_id);
CREATE INDEX idx_ts_entries_dates      ON timesheet_entries(applicable_from, applicable_to);

GRANT SELECT, INSERT, UPDATE, DELETE ON timesheets TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON timesheet_entries TO app_user;

COMMIT;
