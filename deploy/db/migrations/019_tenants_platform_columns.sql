-- Migration 019: Add platform API columns to tenants table

BEGIN;

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS tier            TEXT NOT NULL DEFAULT 'assess',
    ADD COLUMN IF NOT EXISTS bullhorn_config JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS settings        JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS client_memory   JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS updated_at      TIMESTAMPTZ;

-- Back-fill updated_at from created_at where null
UPDATE tenants SET updated_at = created_at WHERE updated_at IS NULL;

COMMIT;
