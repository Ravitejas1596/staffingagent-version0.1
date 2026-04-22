-- Migration 015: Add sync_state and sync_history tables for incremental sync

BEGIN;

CREATE TABLE IF NOT EXISTS sync_state (
    tenant_id      UUID        NOT NULL,
    entity         TEXT        NOT NULL,
    last_synced_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, entity)
);

CREATE TABLE IF NOT EXISTS sync_history (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID        NOT NULL,
    entity       TEXT        NOT NULL,
    sync_date    DATE        NOT NULL DEFAULT CURRENT_DATE,
    record_count INTEGER     NOT NULL,
    synced_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sync_history_tenant_entity ON sync_history(tenant_id, entity, sync_date);

COMMIT;
