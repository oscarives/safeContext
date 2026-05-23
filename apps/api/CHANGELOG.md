# API Changelog

All notable changes to the SafeContext API are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-05-23

### Added

- **POST /v1/waivers** - Create policy waivers for specific rule IDs
- **GET /v1/waivers** - List active waivers with filtering
- **DELETE /v1/waivers/{waiver_id}** - Revoke a waiver
- **GET /v1/audit/verification-key** - Retrieve HMAC public verification key
- **Scan deduplication** - `POST /v1/scan` returns cached result for identical document+policy combinations
- **Dual auth on /v1/scan** - Accepts both MCP agent tokens and Keycloak JWTs (web UI attribution)
- **Outbox pattern** - Scan operations use transactional outbox for reliable async processing
- **Redis pipeline batch** - `BrokerPort.enqueue_batch()` for atomic multi-message enqueue
- **Configurable connection pool** - `DB_POOL_SIZE`, `DB_POOL_MAX_OVERFLOW`, `DB_POOL_RECYCLE`, `DB_POOL_TIMEOUT` env vars
- **OPA policy waivers** - `decision_with_waivers(findings, waivers)` extends policy evaluation
- **Centralized enums** - `OperationStatus`, `ActorType`, `Severity`, `RedactionType`, `ArtifactType`, `WaiverStatus` as StrEnum
- **Centralized constants** - Timeouts, limits, and policy defaults in `core.constants`

### Changed

- **GET /v1/operations** - Added `total_completed`, `total_escalated`, `total_rejected` aggregate fields
- **POST /v1/review/{finding_id}/approve** - Enforces segregation of duties (cannot self-approve)
- **POST /v1/review/{finding_id}/reject** - Enforces segregation of duties (cannot self-reject)
- **GET /v1/audit/{trace_id}** - Added `sanitized_document` field to response; access control enforced (owner, reviewer, or admin)
- **Pydantic schemas** - Stricter `Literal` types for severity, redaction_type, artifact_type in audit schemas
- **Health check** - Timeout configurable via `HEALTH_CHECK_TIMEOUT` constant

### Security

- Segregation of duties on review endpoints (no self-approval)
- Audit access control by role and ownership
- MFA enforcement configurable via `API_REQUIRE_MFA`
- Span-merging in sanitization prevents corruption from overlapping findings
- UNIQUE constraint on `Finding(operation_id, rule_id, span_start, span_end)` prevents duplicate findings

## [1.0.0] - 2026-05-21

### Added

- **POST /v1/scan** - Submit documents for PII scanning
- **GET /v1/health** - Liveness + dependency status (Postgres, Redis, MinIO, Broker)
- **GET /v1/operations** - List operations with pagination and filtering
- **GET /v1/review/pending** - List findings pending human review
- **POST /v1/review/{finding_id}/approve** - Approve a finding with justification
- **POST /v1/review/{finding_id}/reject** - Reject a finding with justification
- **GET /v1/audit/{trace_id}** - Export audit trail with HMAC signature
- **MCP Server** - `GET /mcp/tools` and `POST /mcp/call` for AI agent integration
- OIDC authentication via Keycloak
- OpenTelemetry tracing and Prometheus metrics
- Alembic migrations with monthly partitioning for operations table
