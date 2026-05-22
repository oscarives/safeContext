-- SafeContext — PostgreSQL pgAudit initialization
-- pgaudit is optional: if the extension is not installed in the image,
-- we log a notice and continue. All other initialization still runs.

DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS pgaudit;
  EXECUTE 'ALTER SYSTEM SET pgaudit.log = ''write, ddl''';
  EXECUTE 'ALTER SYSTEM SET pgaudit.log_relation = ''on''';
  EXECUTE 'ALTER SYSTEM SET pgaudit.log_catalog = ''off''';
  PERFORM pg_reload_conf();
  RAISE NOTICE 'pgaudit enabled successfully';
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'pgaudit not available (%). Audit logging disabled — install postgresql18-pgaudit for production.', SQLERRM;
END
$$;

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
