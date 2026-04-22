-- Migration 003: Candidates table

BEGIN;

CREATE TABLE candidates (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id INTEGER NOT NULL,
    first_name  TEXT,
    last_name   TEXT,
    full_name   TEXT,
    email       TEXT,
    mobile      TEXT,
    phone       TEXT,
    status      TEXT,
    date_added  DATE,
    owner_first TEXT,
    owner_last  TEXT,
    raw_data    JSONB NOT NULL DEFAULT '{}',
    synced_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_candidates_tenant ON candidates(tenant_id);
CREATE INDEX idx_candidates_status ON candidates(status);
CREATE INDEX idx_candidates_name   ON candidates(last_name, first_name);

GRANT SELECT, INSERT, UPDATE, DELETE ON candidates TO app_user;

COMMIT;
