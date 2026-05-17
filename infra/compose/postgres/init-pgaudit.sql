-- SafeContext — PostgreSQL pgAudit initialization
-- This script runs once on first container startup.

CREATE EXTENSION IF NOT EXISTS pgaudit;

ALTER SYSTEM SET pgaudit.log = 'write, ddl';
ALTER SYSTEM SET pgaudit.log_relation = 'on';
ALTER SYSTEM SET pgaudit.log_catalog = 'off';

SELECT pg_reload_conf();

-- Apply security_barrier to all critical tables when they already exist
-- (idempotent: the DO block is a no-op on a fresh DB before migrations run).
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'operations') THEN
    EXECUTE 'ALTER TABLE operations SET (security_barrier = true)';
    EXECUTE 'ALTER TABLE findings SET (security_barrier = true)';
    EXECUTE 'ALTER TABLE redactions SET (security_barrier = true)';
    EXECUTE 'ALTER TABLE artifacts SET (security_barrier = true)';
  END IF;
END $$;
