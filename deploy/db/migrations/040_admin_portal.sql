-- 040_admin_portal.sql
-- Indexes and adjustments for admin portal functionality.
-- Adds index on tenants.is_active for filtering.
-- Adds index on tenants.slug for login lookups.

CREATE INDEX IF NOT EXISTS idx_tenants_is_active ON tenants (is_active);
CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants (slug);
