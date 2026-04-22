-- Migration 017: VMS match results and name alias learning tables

BEGIN;

CREATE TABLE IF NOT EXISTS vms_matches (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    run_id           UUID        REFERENCES agent_runs(id) ON DELETE SET NULL,
    vms_record_id    UUID        NOT NULL REFERENCES vms_records(id) ON DELETE CASCADE,
    placement_id     UUID        REFERENCES placements(id) ON DELETE SET NULL,
    bullhorn_id      INTEGER,
    confidence       NUMERIC(4,3),
    match_method     TEXT,        -- 'alias', 'exact', 'fuzzy', 'llm', 'manual', 'unmatched'
    name_similarity  NUMERIC(4,3),
    rate_delta       NUMERIC(10,2),
    hours_delta      NUMERIC(8,2),
    financial_impact NUMERIC(12,2),
    llm_explanation  TEXT,
    status           TEXT        NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|dismissed|corrected
    reviewed_by      UUID        REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at      TIMESTAMPTZ,
    review_notes     TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Name alias table — the learning layer
CREATE TABLE IF NOT EXISTS vms_name_aliases (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    vms_name         TEXT        NOT NULL,
    canonical_first  TEXT        NOT NULL,
    canonical_last   TEXT        NOT NULL,
    bullhorn_id      INTEGER,
    learned_from     UUID        REFERENCES vms_matches(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, vms_name)
);

CREATE INDEX IF NOT EXISTS idx_vms_matches_tenant   ON vms_matches(tenant_id);
CREATE INDEX IF NOT EXISTS idx_vms_matches_run      ON vms_matches(run_id);
CREATE INDEX IF NOT EXISTS idx_vms_matches_status   ON vms_matches(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_vms_matches_vms      ON vms_matches(vms_record_id);
CREATE INDEX IF NOT EXISTS idx_vms_aliases_tenant   ON vms_name_aliases(tenant_id);
CREATE INDEX IF NOT EXISTS idx_vms_aliases_name     ON vms_name_aliases(tenant_id, vms_name);

COMMIT;
