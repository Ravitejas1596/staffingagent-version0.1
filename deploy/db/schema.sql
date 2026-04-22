-- StaffingAgent database schema
-- Run against Aurora PostgreSQL: psql -h <db_endpoint> -U postgres -d staffingagent -f platform/db/schema.sql

BEGIN;

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enum types
CREATE TYPE tenant_tier AS ENUM ('assess', 'transform', 'enterprise');
CREATE TYPE user_role AS ENUM ('admin', 'operator', 'reviewer');
CREATE TYPE agent_type AS ENUM ('vms_reconciliation', 'invoice_matching', 'time_anomaly', 'collections', 'compliance');
CREATE TYPE run_status AS ENUM ('queued', 'running', 'completed', 'failed', 'review');
CREATE TYPE review_decision AS ENUM ('approved', 'rejected', 'modified');

-- Tenants
CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    tier        tenant_tier NOT NULL DEFAULT 'assess',
    config      JSONB NOT NULL DEFAULT '{}',
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE tenants IS 'Customer organizations — maps to AgentState.tenant_id';
COMMENT ON COLUMN tenants.config IS 'Tenant configuration (nBrain, Bullhorn, enabled agents) — see config/tenant_example.json';

-- Users
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email       TEXT NOT NULL,
    name        TEXT NOT NULL,
    role        user_role NOT NULL DEFAULT 'operator',
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email)
);

-- Agent Runs (one row per agent invocation)
CREATE TABLE agent_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_type      agent_type NOT NULL,
    status          run_status NOT NULL DEFAULT 'queued',
    input_state     JSONB,
    token_usage     JSONB DEFAULT '[]',
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN agent_runs.token_usage IS 'Array of token usage records for billing passthrough (actual + 30%)';

-- Agent Results (detailed outputs per run)
CREATE TABLE agent_results (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id                  UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    result_type             TEXT NOT NULL,
    result_data             JSONB NOT NULL DEFAULT '{}',
    confidence              NUMERIC(4,3),
    human_review_required   BOOLEAN NOT NULL DEFAULT false,
    reviewer_id             UUID REFERENCES users(id),
    review_decision         review_decision,
    review_notes            TEXT,
    reviewed_at             TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN agent_results.result_type IS 'E.g. proposed_matches, anomalies, violations, prioritization';
COMMENT ON COLUMN agent_results.confidence IS 'Agent confidence score (0.000 to 1.000)';

-- Audit Log
CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID REFERENCES tenants(id) ON DELETE SET NULL,
    user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,
    entity_type TEXT,
    entity_id   UUID,
    details     JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_agent_runs_tenant ON agent_runs(tenant_id);
CREATE INDEX idx_agent_runs_status ON agent_runs(status);
CREATE INDEX idx_agent_runs_agent_type ON agent_runs(agent_type);
CREATE INDEX idx_agent_runs_created ON agent_runs(created_at DESC);
CREATE INDEX idx_agent_results_run ON agent_results(run_id);
CREATE INDEX idx_agent_results_review ON agent_results(human_review_required) WHERE human_review_required = true;
CREATE INDEX idx_audit_log_tenant ON audit_log(tenant_id);
CREATE INDEX idx_audit_log_created ON audit_log(created_at DESC);
CREATE INDEX idx_audit_log_entity ON audit_log(entity_type, entity_id);

-- Application user (used by the API, not the master postgres user)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user WITH LOGIN PASSWORD 'CHANGE_ME_AFTER_CREATION';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE staffingagent TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO app_user;

COMMIT;
