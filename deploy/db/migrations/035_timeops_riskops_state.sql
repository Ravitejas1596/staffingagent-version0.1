-- Migration 035: State tables for TimeOps exclusions and RiskOps resolutions

CREATE TABLE timeops_exclusions (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    placement_bullhorn_id   TEXT NOT NULL,
    period_end_date         DATE NOT NULL,
    is_excluded             BOOLEAN NOT NULL DEFAULT TRUE,
    excluded_by             TEXT,
    excluded_at             TIMESTAMPTZ,
    last_reminder_sent_at   TIMESTAMPTZ,
    comments                TEXT NOT NULL DEFAULT '',
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, placement_bullhorn_id, period_end_date)
);

CREATE INDEX idx_timeops_excl_tenant ON timeops_exclusions(tenant_id, period_end_date);

CREATE TABLE riskops_resolutions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    record_key      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'Open',
    resolved_by     TEXT,
    resolved_at     TIMESTAMPTZ,
    comments        TEXT NOT NULL DEFAULT '',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, record_key)
);

CREATE INDEX idx_riskops_resol_tenant ON riskops_resolutions(tenant_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON timeops_exclusions TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON riskops_resolutions TO app_user;
