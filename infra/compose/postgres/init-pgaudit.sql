-- SafeContext — PostgreSQL pgAudit initialization
-- This script runs once on first container startup.

CREATE EXTENSION IF NOT EXISTS pgaudit;

ALTER SYSTEM SET pgaudit.log = 'write, ddl';
ALTER SYSTEM SET pgaudit.log_relation = 'on';

SELECT pg_reload_conf();
