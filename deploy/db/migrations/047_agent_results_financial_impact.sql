BEGIN;

ALTER TABLE agent_results
    ADD COLUMN IF NOT EXISTS financial_impact NUMERIC(12, 2) NOT NULL DEFAULT 0;

ALTER TABLE agent_results
    ADD COLUMN IF NOT EXISTS severity TEXT;

ALTER TABLE agent_results
    ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);

ALTER TABLE agent_results
    ADD COLUMN IF NOT EXISTS record_ref TEXT;

ALTER TABLE agent_results
    ADD COLUMN IF NOT EXISTS candidate_name TEXT;

ALTER TABLE agent_results
    ADD COLUMN IF NOT EXISTS llm_explanation TEXT;

ALTER TABLE agent_results
    ADD COLUMN IF NOT EXISTS recommended_action TEXT;

ALTER TABLE agent_results
    ADD COLUMN IF NOT EXISTS reviewed_by UUID REFERENCES users(id);

COMMIT;
