"""Tests for RegexDetector (T4).

Covers all six built-in rules plus edge-cases (clean text, multiple matches,
span ordering). No external I/O — all tests are pure-Python and fast.
"""

from __future__ import annotations

import pytest

from workers.ml.regex_detector import RegexDetector


@pytest.fixture
def detector() -> RegexDetector:
    return RegexDetector()


# ---------------------------------------------------------------------------
# Individual rule tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_postgresql_connection_string(detector: RegexDetector) -> None:
    text = "DATABASE_URL=postgresql://admin:secret@db.internal:5432/prod"
    findings = await detector.detect(text, {})
    rule_ids = [f.rule_id for f in findings]
    assert "regex_connection_string" in rule_ids
    assert any(f.severity == "critical" for f in findings)


@pytest.mark.asyncio
async def test_detects_mysql_connection_string(detector: RegexDetector) -> None:
    text = "mysql://user:pass@localhost/mydb"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_connection_string" for f in findings)


@pytest.mark.asyncio
async def test_detects_mongodb_connection_string(detector: RegexDetector) -> None:
    text = "Connect using: mongodb://admin:hunter2@mongo:27017/appdb"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_connection_string" for f in findings)


@pytest.mark.asyncio
async def test_connection_string_confidence_is_1(detector: RegexDetector) -> None:
    text = "redis://localhost:6379/0"
    findings = await detector.detect(text, {})
    conn_findings = [f for f in findings if f.rule_id == "regex_connection_string"]
    assert conn_findings, "Expected at least one connection string finding"
    assert conn_findings[0].confidence == 1.0


@pytest.mark.asyncio
async def test_detects_jwt_token(detector: RegexDetector) -> None:
    text = (
        "Authorization: Bearer "
        "eyJhbGciOiJSUzI1NiJ9"
        ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_jwt_token" for f in findings)


@pytest.mark.asyncio
async def test_jwt_token_confidence_is_1(detector: RegexDetector) -> None:
    text = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ"
        ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    findings = await detector.detect(text, {})
    jwt_findings = [f for f in findings if f.rule_id == "regex_jwt_token"]
    assert jwt_findings
    assert jwt_findings[0].confidence == 1.0
    assert jwt_findings[0].severity == "high"


@pytest.mark.asyncio
async def test_detects_pem_private_key(detector: RegexDetector) -> None:
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_pem_private_key" for f in findings)


@pytest.mark.asyncio
async def test_detects_ec_pem_private_key(detector: RegexDetector) -> None:
    text = "Key material:\n-----BEGIN EC PRIVATE KEY-----\nABCDEF"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_pem_private_key" for f in findings)


@pytest.mark.asyncio
async def test_detects_openssh_pem_private_key(detector: RegexDetector) -> None:
    text = "-----BEGIN OPENSSH PRIVATE KEY-----\nABCDEF"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_pem_private_key" for f in findings)


@pytest.mark.asyncio
async def test_detects_generic_pem_private_key(detector: RegexDetector) -> None:
    text = "-----BEGIN PRIVATE KEY-----\nABCDEF"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_pem_private_key" for f in findings)


@pytest.mark.asyncio
async def test_pem_key_severity_is_critical(detector: RegexDetector) -> None:
    text = "-----BEGIN RSA PRIVATE KEY-----"
    findings = await detector.detect(text, {})
    pem_findings = [f for f in findings if f.rule_id == "regex_pem_private_key"]
    assert pem_findings
    assert pem_findings[0].severity == "critical"


@pytest.mark.asyncio
async def test_detects_env_secret_key_assignment(detector: RegexDetector) -> None:
    text = "SECRET_KEY=super_secret_value_1234"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_env_secret_assignment" for f in findings)


@pytest.mark.asyncio
async def test_detects_env_private_key_assignment(detector: RegexDetector) -> None:
    text = "PRIVATE_KEY = mysupersecretkey"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_env_secret_assignment" for f in findings)


@pytest.mark.asyncio
async def test_detects_env_api_secret_assignment(detector: RegexDetector) -> None:
    text = "export API_SECRET=abc123xyz"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_env_secret_assignment" for f in findings)


@pytest.mark.asyncio
async def test_detects_env_auth_token_assignment(detector: RegexDetector) -> None:
    text = "AUTH_TOKEN=tok_live_abcdef1234567890"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_env_secret_assignment" for f in findings)


@pytest.mark.asyncio
async def test_detects_env_database_url_assignment(detector: RegexDetector) -> None:
    # DATABASE_URL may be caught by both env_secret_assignment AND connection_string
    text = "DATABASE_URL=postgresql://user:pass@host/db"
    findings = await detector.detect(text, {})
    rule_ids = [f.rule_id for f in findings]
    assert "regex_env_secret_assignment" in rule_ids or "regex_connection_string" in rule_ids


@pytest.mark.asyncio
async def test_env_secret_assignment_is_case_insensitive(detector: RegexDetector) -> None:
    text = "secret_key=lowercase_value"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_env_secret_assignment" for f in findings)


@pytest.mark.asyncio
async def test_env_secret_confidence(detector: RegexDetector) -> None:
    text = "SECRET_KEY=abc"
    findings = await detector.detect(text, {})
    env_findings = [f for f in findings if f.rule_id == "regex_env_secret_assignment"]
    assert env_findings
    assert env_findings[0].confidence == 0.95


@pytest.mark.asyncio
async def test_detects_uuid_secret_assignment(detector: RegexDetector) -> None:
    text = "api_key=a1b2c3d4-1234-5678-abcd-ef0123456789"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_uuid_secret_assignment" for f in findings)


@pytest.mark.asyncio
async def test_detects_uuid_token_assignment(detector: RegexDetector) -> None:
    text = "token = 00000000-0000-0000-0000-000000000000"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_uuid_secret_assignment" for f in findings)


@pytest.mark.asyncio
async def test_uuid_secret_assignment_confidence(detector: RegexDetector) -> None:
    text = "password=a1b2c3d4-1234-5678-abcd-ef0123456789"
    findings = await detector.detect(text, {})
    uuid_findings = [f for f in findings if f.rule_id == "regex_uuid_secret_assignment"]
    assert uuid_findings
    assert uuid_findings[0].confidence == 0.9


@pytest.mark.asyncio
async def test_detects_credit_card_with_dashes(detector: RegexDetector) -> None:
    text = "Card: 4111-1111-1111-1111"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_credit_card_nonstandard" for f in findings)


@pytest.mark.asyncio
async def test_detects_credit_card_with_spaces(detector: RegexDetector) -> None:
    text = "Payment method 4111 1111 1111 1111 expires 12/25"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_credit_card_nonstandard" for f in findings)


@pytest.mark.asyncio
async def test_detects_credit_card_with_dots(detector: RegexDetector) -> None:
    text = "4111.1111.1111.1111"
    findings = await detector.detect(text, {})
    assert any(f.rule_id == "regex_credit_card_nonstandard" for f in findings)


@pytest.mark.asyncio
async def test_credit_card_confidence(detector: RegexDetector) -> None:
    text = "4111-1111-1111-1111"
    findings = await detector.detect(text, {})
    cc_findings = [f for f in findings if f.rule_id == "regex_credit_card_nonstandard"]
    assert cc_findings
    assert cc_findings[0].confidence == 0.85
    assert cc_findings[0].severity == "high"


# ---------------------------------------------------------------------------
# Clean-text and edge-case tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_text_returns_empty(detector: RegexDetector) -> None:
    text = "This is a public document with no sensitive information."
    findings = await detector.detect(text, {})
    assert findings == []


@pytest.mark.asyncio
async def test_empty_string_returns_empty(detector: RegexDetector) -> None:
    findings = await detector.detect("", {})
    assert findings == []


@pytest.mark.asyncio
async def test_policy_ignored_gracefully(detector: RegexDetector) -> None:
    """RegexDetector should not raise if policy contains arbitrary keys."""
    text = "postgresql://user:pass@host/db"
    findings = await detector.detect(text, {"unknown_key": "value", "score_threshold": 0.3})
    assert any(f.rule_id == "regex_connection_string" for f in findings)


@pytest.mark.asyncio
async def test_findings_are_sorted_by_span(detector: RegexDetector) -> None:
    text = "postgresql://db.host/db AND SECRET_KEY=abc123"
    findings = await detector.detect(text, {})
    if len(findings) > 1:
        for i in range(len(findings) - 1):
            assert findings[i].span_start <= findings[i + 1].span_start, (
                f"Findings not sorted: [{i}].span_start={findings[i].span_start} "
                f"> [{i+1}].span_start={findings[i+1].span_start}"
            )


@pytest.mark.asyncio
async def test_finding_spans_are_correct(detector: RegexDetector) -> None:
    text = "redis://localhost:6379/0"
    findings = await detector.detect(text, {})
    conn_findings = [f for f in findings if f.rule_id == "regex_connection_string"]
    assert conn_findings
    f = conn_findings[0]
    assert f.span_start == 0
    assert f.span_end == len(text)
    assert text[f.span_start:f.span_end] == text


@pytest.mark.asyncio
async def test_finding_explanation_has_pattern(detector: RegexDetector) -> None:
    text = "-----BEGIN PRIVATE KEY-----"
    findings = await detector.detect(text, {})
    pem_findings = [f for f in findings if f.rule_id == "regex_pem_private_key"]
    assert pem_findings
    assert "pattern" in pem_findings[0].explanation
    assert pem_findings[0].explanation["pattern"] == "regex_pem_private_key"


@pytest.mark.asyncio
async def test_finding_explanation_has_preview(detector: RegexDetector) -> None:
    text = "-----BEGIN RSA PRIVATE KEY-----"
    findings = await detector.detect(text, {})
    pem_findings = [f for f in findings if f.rule_id == "regex_pem_private_key"]
    assert pem_findings
    assert "matched_preview" in pem_findings[0].explanation


@pytest.mark.asyncio
async def test_long_match_preview_truncated(detector: RegexDetector) -> None:
    """Matches longer than 30 chars should have '...' appended in the preview."""
    text = "postgresql://verylongusername:verylongpassword@db.internal:5432/prod_database"
    findings = await detector.detect(text, {})
    conn_findings = [f for f in findings if f.rule_id == "regex_connection_string"]
    assert conn_findings
    preview = conn_findings[0].explanation["matched_preview"]
    assert preview.endswith("...")


@pytest.mark.asyncio
async def test_finding_detector_field_format(detector: RegexDetector) -> None:
    """Detector field should follow 'regex.<RULE_ID_UPPER>' convention."""
    text = "redis://localhost:6379/0"
    findings = await detector.detect(text, {})
    conn_findings = [f for f in findings if f.rule_id == "regex_connection_string"]
    assert conn_findings
    assert conn_findings[0].detector == "regex.REGEX_CONNECTION_STRING"


@pytest.mark.asyncio
async def test_multiple_matches_same_rule(detector: RegexDetector) -> None:
    """Multiple matches from the same rule should all appear in output."""
    text = (
        "Use postgresql://db1/app1 for reads and "
        "mysql://db2:3306/app2 for writes."
    )
    findings = await detector.detect(text, {})
    conn_findings = [f for f in findings if f.rule_id == "regex_connection_string"]
    assert len(conn_findings) == 2


@pytest.mark.asyncio
async def test_no_partial_jwt_match(detector: RegexDetector) -> None:
    """A truncated JWT (only one segment) should not match."""
    text = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9_only_header"
    findings = await detector.detect(text, {})
    assert not any(f.rule_id == "regex_jwt_token" for f in findings)
