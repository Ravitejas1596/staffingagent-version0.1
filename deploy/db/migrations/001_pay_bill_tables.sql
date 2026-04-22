-- Migration 001: Bullhorn pay/bill data tables
-- Run: psql -h <db_endpoint> -U postgres -d staffingagent -f platform/db/migrations/001_pay_bill_tables.sql

BEGIN;

-- Placements synced from Bullhorn
CREATE TABLE placements (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id         INTEGER NOT NULL,
    candidate_first     TEXT,
    candidate_last      TEXT,
    job_title           TEXT,
    client_name         TEXT,
    pay_rate            NUMERIC(12, 4),
    bill_rate           NUMERIC(12, 4),
    ot_pay_rate         NUMERIC(12, 4),
    ot_bill_rate        NUMERIC(12, 4),
    start_date          DATE,
    end_date            DATE,
    status              TEXT,
    employment_type     TEXT,
    raw_data            JSONB NOT NULL DEFAULT '{}',
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_placements_tenant ON placements(tenant_id);
CREATE INDEX idx_placements_status ON placements(status);
CREATE INDEX idx_placements_dates ON placements(start_date, end_date);

-- Timesheets (TimeLaborEval in Bullhorn)
CREATE TABLE timesheets (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id         INTEGER NOT NULL,
    placement_bullhorn_id INTEGER,
    candidate_first     TEXT,
    candidate_last      TEXT,
    week_ending         DATE,
    regular_hours       NUMERIC(8, 2) NOT NULL DEFAULT 0,
    ot_hours            NUMERIC(8, 2) NOT NULL DEFAULT 0,
    double_time_hours   NUMERIC(8, 2) NOT NULL DEFAULT 0,
    status              TEXT,
    raw_data            JSONB NOT NULL DEFAULT '{}',
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_timesheets_tenant ON timesheets(tenant_id);
CREATE INDEX idx_timesheets_week ON timesheets(week_ending);
CREATE INDEX idx_timesheets_placement ON timesheets(placement_bullhorn_id);

-- Invoices (InvoiceStatement in Bullhorn)
CREATE TABLE invoices (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id         INTEGER NOT NULL,
    invoice_number      TEXT,
    client_name         TEXT,
    amount              NUMERIC(14, 2),
    balance             NUMERIC(14, 2),
    status              TEXT,
    invoice_date        DATE,
    due_date            DATE,
    raw_data            JSONB NOT NULL DEFAULT '{}',
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_invoices_tenant ON invoices(tenant_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_due_date ON invoices(due_date);

-- Grant app_user access to new tables
GRANT SELECT, INSERT, UPDATE, DELETE ON placements TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON timesheets TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON invoices TO app_user;

COMMIT;
