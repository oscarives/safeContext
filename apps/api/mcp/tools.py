"""MCP tool definitions — JSON schemas exposed at /v1/mcp/tools."""
from typing import Any

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "safecontext.scan",
        "version": "1.0.0",
        "description": "Scan a document for PII, secrets, and sensitive data. Returns findings with full explanation.",
        "input_schema": {
            "type": "object",
            "required": ["document", "policy_name"],
            "properties": {
                "document": {
                    "type": "string",
                    "description": "Document content to scan (text or base64 for binary)",
                },
                "document_encoding": {
                    "type": "string",
                    "enum": ["text", "base64"],
                    "default": "text",
                },
                "policy_name": {
                    "type": "string",
                    "description": "Name of the OPA policy to apply",
                },
                "policy_version": {
                    "type": "string",
                    "description": "Specific policy version (semver). Defaults to latest.",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "trace_id": {"type": "string", "format": "uuid"},
                "artifact_digest": {"type": "string"},
                "policy_version": {"type": "string"},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "format": "uuid"},
                            "detector": {"type": "string"},
                            "rule_id": {"type": "string"},
                            "span_start": {"type": "integer"},
                            "span_end": {"type": "integer"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                            "explanation": {"type": "object"},
                        },
                    },
                },
                "requires_human_review": {"type": "boolean"},
            },
        },
    },
    {
        "name": "safecontext.sanitize",
        "version": "1.0.0",
        "description": "Sanitize a document based on scan findings. Returns sanitized document and redaction map.",
        "input_schema": {
            "type": "object",
            "required": ["trace_id", "redaction_type"],
            "properties": {
                "trace_id": {"type": "string", "format": "uuid"},
                "redaction_type": {"type": "string", "enum": ["mask", "remove", "replace"]},
                "replacement_token": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "trace_id": {"type": "string", "format": "uuid"},
                "sanitized_document": {"type": "string"},
                "sanitized_artifact_digest": {"type": "string"},
                "redaction_map": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "finding_id": {"type": "string", "format": "uuid"},
                            "span_start": {"type": "integer"},
                            "span_end": {"type": "integer"},
                            "redaction_type": {"type": "string"},
                            "policy_version": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
    {
        "name": "safecontext.classify",
        "version": "1.0.0",
        "description": "Classify document sensitivity level by section.",
        "input_schema": {
            "type": "object",
            "required": ["document"],
            "properties": {
                "document": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "trace_id": {"type": "string", "format": "uuid"},
                "overall_level": {
                    "type": "string",
                    "enum": ["public", "internal", "confidential", "restricted"],
                },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section_id": {"type": "integer"},
                            "level": {"type": "string"},
                            "justification": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
    {
        "name": "safecontext.audit",
        "version": "1.0.0",
        "description": "Return complete audit evidence for an operation given its trace_id. Includes operation metadata, findings, redactions, artifacts, and HMAC signature.",
        "input_schema": {
            "type": "object",
            "required": ["trace_id"],
            "properties": {
                "trace_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Trace ID of the operation to audit",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "trace_id": {"type": "string", "format": "uuid"},
                "exported_at": {"type": "string", "format": "date-time"},
                "operation": {"type": "object"},
                "findings": {"type": "array", "items": {"type": "object"}},
                "redactions": {"type": "array", "items": {"type": "object"}},
                "artifacts": {"type": "array", "items": {"type": "object"}},
                "hmac_signature": {"type": "string"},
            },
        },
    },
    {
        "name": "safecontext.policy.get",
        "version": "1.0.0",
        "description": "Return the active OPA policy with its version. Optionally filter by policy_name or pin to a specific policy_version.",
        "input_schema": {
            "type": "object",
            "required": ["policy_name"],
            "properties": {
                "policy_name": {
                    "type": "string",
                    "description": "Name of the policy to retrieve (e.g. 'base')",
                },
                "policy_version": {
                    "type": "string",
                    "description": "Specific semver version to retrieve. Defaults to active version.",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "policy_name": {"type": "string"},
                "policy_version": {"type": "string"},
                "policy": {"type": "object", "description": "Raw policy rules from OPA"},
            },
        },
    },
]
