-- Migration 036: Bullhorn Event Subscription cursor state

CREATE TABLE subscription_state (
    tenant_id        UUID    NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subscription_id  TEXT    NOT NULL,
    last_request_id  BIGINT  NOT NULL DEFAULT 0,
    entity_types     TEXT[]  NOT NULL DEFAULT '{}',
    registered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_polled_at   TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, subscription_id)
);

CREATE INDEX idx_subscription_state_tenant ON subscription_state(tenant_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON subscription_state TO app_user;
