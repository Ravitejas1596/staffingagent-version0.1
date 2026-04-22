-- Migration 021: Convert users.role from user_role enum to TEXT
-- The platform API ORM model uses Text for role; avoid cast errors on INSERT/UPDATE.

BEGIN;

ALTER TABLE users
    ALTER COLUMN role TYPE TEXT USING role::TEXT;

COMMIT;
