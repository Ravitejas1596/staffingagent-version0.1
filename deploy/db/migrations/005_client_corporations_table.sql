-- Migration 005: Client corporations table

BEGIN;

CREATE TABLE client_corporations (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id INTEGER NOT NULL,
    name        TEXT,
    company_url TEXT,
    date_added  DATE,
    status      TEXT,
    raw_data    JSONB NOT NULL DEFAULT '{}',
    synced_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_client_corps_tenant ON client_corporations(tenant_id);
CREATE INDEX idx_client_corps_status ON client_corporations(status);
CREATE INDEX idx_client_corps_name   ON client_corporations(name);

GRANT SELECT, INSERT, UPDATE, DELETE ON client_corporations TO app_user;

COMMIT;
