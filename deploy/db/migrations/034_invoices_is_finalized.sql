-- Migration 034: Add is_finalized to invoices

BEGIN;

ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS is_finalized BOOLEAN;

CREATE INDEX IF NOT EXISTS idx_invoices_finalized ON invoices(tenant_id, is_finalized);

COMMIT;
