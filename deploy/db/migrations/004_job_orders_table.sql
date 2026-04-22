-- Migration 004: Job orders table

BEGIN;

CREATE TABLE job_orders (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id             INTEGER NOT NULL,
    title                   TEXT,
    status                  TEXT,
    num_openings            INTEGER,
    is_open                 BOOLEAN,
    date_added              DATE,
    date_last_published     DATE,
    client_corporation_id   INTEGER,
    client_corporation_name TEXT,
    owner_bullhorn_id       INTEGER,
    raw_data                JSONB NOT NULL DEFAULT '{}',
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_job_orders_tenant ON job_orders(tenant_id);
CREATE INDEX idx_job_orders_status ON job_orders(status);
CREATE INDEX idx_job_orders_client ON job_orders(client_corporation_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON job_orders TO app_user;

COMMIT;
