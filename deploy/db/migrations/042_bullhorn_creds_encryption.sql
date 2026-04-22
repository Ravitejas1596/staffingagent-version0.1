-- Migration 042: Encrypt Bullhorn credentials at rest.
--
-- Before this migration, tenants.bullhorn_config (JSONB) stored client_id,
-- client_secret, api_user, api_password as plaintext. Any DB snapshot,
-- read-replica credential leak, or stolen backup exposed every tenant's
-- Bullhorn production API keys.
--
-- After this migration, the secret fields are stored as a Fernet-encrypted
-- blob in bullhorn_credentials_ciphertext, keyed by BULLHORN_CREDS_KEK (an
-- env var sourced from AWS Secrets Manager). Non-secret config (region,
-- corp_id, etc.) remains in bullhorn_config JSONB.
--
-- After applying this migration, run:
--   python scripts/encrypt_existing_bullhorn_creds.py
-- to re-encrypt existing plaintext rows. The script also clears the
-- plaintext secret fields from bullhorn_config.

BEGIN;

-- pgcrypto not strictly required (encryption happens in the Python app),
-- but enabling it keeps the option open to move to SQL-side encryption
-- later without another migration.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS bullhorn_credentials_ciphertext BYTEA,
    ADD COLUMN IF NOT EXISTS bullhorn_credentials_version INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS bullhorn_credentials_updated_at TIMESTAMPTZ;

COMMENT ON COLUMN tenants.bullhorn_credentials_ciphertext IS
    'Fernet-encrypted JSON blob of Bullhorn API credentials (client_id, client_secret, api_user, api_password). Key is BULLHORN_CREDS_KEK.';
COMMENT ON COLUMN tenants.bullhorn_credentials_version IS
    'KEK version used to encrypt this row. Supports zero-downtime key rotation via MultiFernet.';

COMMIT;
