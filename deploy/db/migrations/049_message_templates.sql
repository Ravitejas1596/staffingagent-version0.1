-- Migration 049: message_templates — per-tenant override system for outbound
-- SMS / email copy used by agents.
--
-- Lookup semantics (highest to lowest precedence):
--   1. (tenant_id = X, template_key, language) active row
--   2. (tenant_id IS NULL, template_key, language) active platform default
--   3. raise TemplateNotFoundError
--
-- Platform-default rows (tenant_id IS NULL) are seeded in migration 050 with
-- DRAFT copy; Cortney's Apr 24 deliverable replaces that copy before pilot.
--
-- Body uses Jinja2 template syntax. Variables are whitelisted in
-- app_platform/api/message_templates.py — unknown variables raise at render
-- time rather than silently emitting empty strings.
--
-- Reference: Time Anomaly build plan, Week 1 Day 4.

BEGIN;

CREATE TABLE IF NOT EXISTS message_templates (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID REFERENCES tenants(id) ON DELETE CASCADE,
                      -- NULL = platform default, non-NULL = tenant override
    template_key      TEXT NOT NULL,
                      -- e.g. 'time_anomaly.group_a1.sms',
                      --      'time_anomaly.group_a2.email_subject'
    channel           TEXT NOT NULL
                      CHECK (channel IN ('sms', 'email_subject', 'email_body')),
    language          TEXT NOT NULL DEFAULT 'en',
    subject           TEXT,
                      -- only populated when channel='email_subject' at the
                      -- adjacent 'email_body' row; kept for query convenience
    body              TEXT NOT NULL,
    active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_by        UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Uniqueness: at most one active row per (tenant scope, key, language).
-- Two partial unique indexes because NULL tenant_id doesn't participate in a
-- regular UNIQUE constraint.
CREATE UNIQUE INDEX IF NOT EXISTS uq_message_templates_tenant_key_lang
    ON message_templates (tenant_id, template_key, language)
    WHERE tenant_id IS NOT NULL AND active;

CREATE UNIQUE INDEX IF NOT EXISTS uq_message_templates_platform_key_lang
    ON message_templates (template_key, language)
    WHERE tenant_id IS NULL AND active;

CREATE INDEX IF NOT EXISTS idx_message_templates_lookup
    ON message_templates (template_key, language, tenant_id)
    WHERE active;

CREATE OR REPLACE FUNCTION message_templates_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_message_templates_updated_at ON message_templates;
CREATE TRIGGER trg_message_templates_updated_at
    BEFORE UPDATE ON message_templates
    FOR EACH ROW
    EXECUTE FUNCTION message_templates_set_updated_at();

-- RLS: tenant-scoped rows are isolated per tenant. Platform-default rows
-- (tenant_id IS NULL) are readable by every tenant's queries but writeable
-- only with bypass_rls (admin migration path).
ALTER TABLE message_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE message_templates FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS message_templates_read ON message_templates;
CREATE POLICY message_templates_read ON message_templates
    FOR SELECT TO app_user
    USING (
        current_setting('app.bypass_rls', true) = 'on'
        OR tenant_id IS NULL
        OR tenant_id::text = current_setting('app.tenant_id', true)
    );

DROP POLICY IF EXISTS message_templates_write ON message_templates;
CREATE POLICY message_templates_write ON message_templates
    FOR ALL TO app_user
    USING (
        current_setting('app.bypass_rls', true) = 'on'
        OR tenant_id::text = current_setting('app.tenant_id', true)
    )
    WITH CHECK (
        current_setting('app.bypass_rls', true) = 'on'
        OR tenant_id::text = current_setting('app.tenant_id', true)
    );

COMMIT;
