-- Migration 018: Add auth columns to users table for platform API

BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS password_hash    TEXT,
    ADD COLUMN IF NOT EXISTS is_active        BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS permissions      JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS invited_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS invited_at       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_login_at    TIMESTAMPTZ;

-- Sync is_active from existing active column
UPDATE users SET is_active = active WHERE is_active IS DISTINCT FROM active;

-- Add missing columns used by platform API models
ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS triggered_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS trigger_type    TEXT NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS result_summary  JSONB,
    ADD COLUMN IF NOT EXISTS agent_type_col  TEXT;

-- Add slug to tenants if missing
ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS slug         TEXT,
    ADD COLUMN IF NOT EXISTS is_active    BOOLEAN NOT NULL DEFAULT true;

-- Set slug from name if null
UPDATE tenants SET slug = lower(regexp_replace(name, '[^a-zA-Z0-9]', '-', 'g')) WHERE slug IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS tenants_slug_unique ON tenants(slug);

COMMIT;
