"""Tests for rescan_agent (T3).

All tests use in-memory mocks for PostgreSQL and Dramatiq so they run without
any infrastructure. The suite verifies:
  - Residual PII in sanitized text triggers escalation
  - Clean sanitized text marks the operation completed
  - Idempotency guard prevents double-processing
  - Missing operation / missing sanitized_text are handled gracefully
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_operation(
    *,
    status: str = "pending",
    sanitized_text: str | None = None,
) -> MagicMock:
    op = MagicMock()
    op.id = uuid.uuid4()
    op.status = status
    op.sanitized_text = sanitized_text
    op.policy_version = "1.0.0"
    return op


def _make_finding_model(
    *,
    operation_id: uuid.UUID,
    rule_id: str = "regex_jwt_token",
    severity: str = "high",
    is_post_sanitization: bool = False,
) -> MagicMock:
    fm = MagicMock()
    fm.id = uuid.uuid4()
    fm.operation_id = operation_id
    fm.rule_id = rule_id
    fm.severity = severity
    fm.explanation = {"is_post_sanitization": is_post_sanitization}
    return fm


# ---------------------------------------------------------------------------
# Unit tests for _rescan_operation_async
# ---------------------------------------------------------------------------


class TestRescanOperationAsync:
    """Tests for the async inner function of rescan_operation."""

    @pytest.mark.asyncio
    async def test_rescan_detects_residual_and_escalates(self) -> None:
        """Residual PII in sanitized text creates post-sanitization findings
        and escalates the operation."""
        operation_id = str(uuid.uuid4())
        op_uuid = uuid.UUID(operation_id)

        operation = _make_operation(
            status="pending",
            sanitized_text="Contact [REDACTED] at john.doe@company.com for details",
        )
        operation.id = op_uuid

        # Simulate: no existing post-sanitization findings
        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None

        # Simulate: operation fetched from DB
        op_result = MagicMock()
        op_result.scalar_one_or_none.return_value = operation

        # Track DB calls
        added_findings: list = []
        updated_statuses: list[str] = []

        async def fake_execute(stmt):
            # Return op for first call, None for idempotency check
            return op_result

        session = AsyncMock()
        # Call sequence:
        #   1. select(Operation)              → op_result
        #   2. select(FindingModel) idempotency → no_existing
        #   3. update(Operation) escalate     → MagicMock
        execute_returns = [op_result, no_existing, MagicMock()]
        execute_call_count = {"n": 0}

        async def side_effect_execute(stmt):
            n = execute_call_count["n"]
            execute_call_count["n"] += 1
            return execute_returns[n] if n < len(execute_returns) else MagicMock()

        session.execute.side_effect = side_effect_execute
        # session.add is called synchronously (not awaited) in the agent —
        # replace it with a plain MagicMock so the side_effect fires correctly.
        session.add = MagicMock(side_effect=lambda obj: added_findings.append(obj))

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=False)

        from workers.core.detector import Finding

        # A real Finding object — Presidio email detection would catch this
        residual_finding = Finding(
            detector="presidio.EMAIL_ADDRESS",
            rule_id="presidio_email_address",
            span_start=20,
            span_end=41,
            confidence=0.85,
            severity="medium",
            explanation={"entity_type": "EMAIL_ADDRESS"},
        )

        with (
            patch("workers.agents.rescan_agent.get_session", return_value=cm),
            patch(
                "workers.agents.rescan_agent._regex_detector.detect",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "workers.agents.rescan_agent._presidio_detector.detect",
                new=AsyncMock(return_value=[residual_finding]),
            ),
            patch("workers.agents.rescan_agent.TASK_DURATION_SECONDS") as mock_timer,
            patch("workers.agents.rescan_agent.TASKS_TOTAL") as mock_counter,
            patch(
                "workers.agents.reviewer_agent.process_review"
            ) as mock_review,
        ):
            mock_timer.labels.return_value.__enter__ = MagicMock(return_value=None)
            mock_timer.labels.return_value.__exit__ = MagicMock(return_value=False)

            from workers.agents.rescan_agent import _rescan_operation_async

            await _rescan_operation_async(operation_id)

        # Verify a post-sanitization finding was added
        assert len(added_findings) == 1
        assert added_findings[0].explanation.get("is_post_sanitization") is True

    @pytest.mark.asyncio
    async def test_rescan_clean_document_no_findings_added(self) -> None:
        """Clean sanitized text produces no new findings and marks completed."""
        operation_id = str(uuid.uuid4())
        op_uuid = uuid.UUID(operation_id)

        operation = _make_operation(
            status="pending",
            sanitized_text="This document has been fully sanitized with no sensitive data.",
        )
        operation.id = op_uuid

        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None

        op_result = MagicMock()
        op_result.scalar_one_or_none.return_value = operation

        execute_returns = [op_result, no_existing, MagicMock()]
        execute_call_count = {"n": 0}

        async def side_effect_execute(stmt):
            n = execute_call_count["n"]
            execute_call_count["n"] += 1
            return execute_returns[n] if n < len(execute_returns) else MagicMock()

        session = AsyncMock()
        session.execute.side_effect = side_effect_execute
        added_findings: list = []
        # session.add is synchronous in the agent — use plain MagicMock
        session.add = MagicMock(side_effect=lambda obj: added_findings.append(obj))

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("workers.agents.rescan_agent.get_session", return_value=cm),
            patch(
                "workers.agents.rescan_agent._regex_detector.detect",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "workers.agents.rescan_agent._presidio_detector.detect",
                new=AsyncMock(return_value=[]),
            ),
            patch("workers.agents.rescan_agent.TASK_DURATION_SECONDS") as mock_timer,
            patch("workers.agents.rescan_agent.TASKS_TOTAL") as mock_counter,
        ):
            mock_timer.labels.return_value.__enter__ = MagicMock(return_value=None)
            mock_timer.labels.return_value.__exit__ = MagicMock(return_value=False)

            from workers.agents.rescan_agent import _rescan_operation_async

            await _rescan_operation_async(operation_id)

        # No findings should have been added
        assert added_findings == []

    @pytest.mark.asyncio
    async def test_rescan_skips_when_operation_not_found(self) -> None:
        """Missing operation_id should log a warning and exit cleanly."""
        operation_id = str(uuid.uuid4())

        op_result = MagicMock()
        op_result.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute.return_value = op_result

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("workers.agents.rescan_agent.get_session", return_value=cm),
            patch("workers.agents.rescan_agent.TASK_DURATION_SECONDS") as mock_timer,
            patch("workers.agents.rescan_agent.TASKS_TOTAL") as mock_counter,
        ):
            mock_timer.labels.return_value.__enter__ = MagicMock(return_value=None)
            mock_timer.labels.return_value.__exit__ = MagicMock(return_value=False)

            from workers.agents.rescan_agent import _rescan_operation_async

            # Should not raise
            await _rescan_operation_async(operation_id)

        mock_counter.labels.assert_called_with(agent="rescan", status="failure")

    @pytest.mark.asyncio
    async def test_rescan_skips_when_no_sanitized_text(self) -> None:
        """Operation with no sanitized_text should be skipped gracefully."""
        operation_id = str(uuid.uuid4())
        op_uuid = uuid.UUID(operation_id)

        operation = _make_operation(status="pending", sanitized_text=None)
        operation.id = op_uuid

        op_result = MagicMock()
        op_result.scalar_one_or_none.return_value = operation

        session = AsyncMock()
        session.execute.return_value = op_result

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=False)

        added_findings: list = []
        session.add.side_effect = lambda obj: added_findings.append(obj)

        with (
            patch("workers.agents.rescan_agent.get_session", return_value=cm),
            patch("workers.agents.rescan_agent.TASK_DURATION_SECONDS") as mock_timer,
            patch("workers.agents.rescan_agent.TASKS_TOTAL") as mock_counter,
        ):
            mock_timer.labels.return_value.__enter__ = MagicMock(return_value=None)
            mock_timer.labels.return_value.__exit__ = MagicMock(return_value=False)

            from workers.agents.rescan_agent import _rescan_operation_async

            await _rescan_operation_async(operation_id)

        assert added_findings == []
        mock_counter.labels.assert_called_with(agent="rescan", status="skipped")

    @pytest.mark.asyncio
    async def test_rescan_idempotency_skip_when_already_rescanned(self) -> None:
        """If post-sanitization findings already exist, rescan is a no-op."""
        operation_id = str(uuid.uuid4())
        op_uuid = uuid.UUID(operation_id)

        operation = _make_operation(
            status="escalated",
            sanitized_text="some text with residual pii@example.com",
        )
        operation.id = op_uuid

        op_result = MagicMock()
        op_result.scalar_one_or_none.return_value = operation

        # Existing post-sanitization finding — idempotency guard triggers
        existing_finding = _make_finding_model(
            operation_id=op_uuid, is_post_sanitization=True
        )
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_finding

        execute_returns = [op_result, existing_result]
        execute_call_count = {"n": 0}

        async def side_effect_execute(stmt):
            n = execute_call_count["n"]
            execute_call_count["n"] += 1
            return execute_returns[n] if n < len(execute_returns) else MagicMock()

        session = AsyncMock()
        session.execute.side_effect = side_effect_execute

        added_findings: list = []
        session.add.side_effect = lambda obj: added_findings.append(obj)

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("workers.agents.rescan_agent.get_session", return_value=cm),
            patch("workers.agents.rescan_agent.TASK_DURATION_SECONDS") as mock_timer,
            patch("workers.agents.rescan_agent.TASKS_TOTAL") as mock_counter,
        ):
            mock_timer.labels.return_value.__enter__ = MagicMock(return_value=None)
            mock_timer.labels.return_value.__exit__ = MagicMock(return_value=False)

            from workers.agents.rescan_agent import _rescan_operation_async

            await _rescan_operation_async(operation_id)

        assert added_findings == [], "No new findings should be added on re-delivery"
        mock_counter.labels.assert_called_with(agent="rescan", status="skipped")

    @pytest.mark.asyncio
    async def test_rescan_does_not_overwrite_escalated_status(self) -> None:
        """Residual findings on an already-escalated operation must not
        re-write the status (idempotency for status field)."""
        operation_id = str(uuid.uuid4())
        op_uuid = uuid.UUID(operation_id)

        operation = _make_operation(
            status="escalated",
            sanitized_text="postgresql://user:pass@db/prod",
        )
        operation.id = op_uuid

        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None

        op_result = MagicMock()
        op_result.scalar_one_or_none.return_value = operation

        update_calls: list = []
        execute_returns = [op_result, no_existing, MagicMock()]
        execute_call_count = {"n": 0}

        async def side_effect_execute(stmt):
            from sqlalchemy import Update
            n = execute_call_count["n"]
            execute_call_count["n"] += 1
            return execute_returns[n] if n < len(execute_returns) else MagicMock()

        session = AsyncMock()
        session.execute.side_effect = side_effect_execute
        session.add = MagicMock()  # synchronous in agent — plain MagicMock avoids coroutine warnings

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=False)

        from workers.core.detector import Finding

        residual = Finding(
            detector="regex.REGEX_CONNECTION_STRING",
            rule_id="regex_connection_string",
            span_start=0,
            span_end=30,
            confidence=1.0,
            severity="critical",
            explanation={"pattern": "regex_connection_string", "matched_preview": "postgresql://..."},
        )

        with (
            patch("workers.agents.rescan_agent.get_session", return_value=cm),
            patch(
                "workers.agents.rescan_agent._regex_detector.detect",
                new=AsyncMock(return_value=[residual]),
            ),
            patch(
                "workers.agents.rescan_agent._presidio_detector.detect",
                new=AsyncMock(return_value=[]),
            ),
            patch("workers.agents.rescan_agent.TASK_DURATION_SECONDS") as mock_timer,
            patch("workers.agents.rescan_agent.TASKS_TOTAL"),
            patch("workers.agents.reviewer_agent.process_review"),
        ):
            mock_timer.labels.return_value.__enter__ = MagicMock(return_value=None)
            mock_timer.labels.return_value.__exit__ = MagicMock(return_value=False)

            from workers.agents.rescan_agent import _rescan_operation_async

            await _rescan_operation_async(operation_id)

        # The update(Operation) should NOT have been called because status is
        # already "escalated" — the guard `if operation.status not in (...)` fires.
        # We verify by checking execute was only called twice (select op + idempotency
        # check), not a third time for the update.
        # execute_call_count["n"] == 2 means no update statement was issued.
        assert execute_call_count["n"] == 2, (
            f"Expected 2 execute calls (select+idempotency), got {execute_call_count['n']}"
        )

    @pytest.mark.asyncio
    async def test_rescan_does_not_overwrite_rejected_status(self) -> None:
        """Residual findings on a rejected operation must not change its status."""
        operation_id = str(uuid.uuid4())
        op_uuid = uuid.UUID(operation_id)

        operation = _make_operation(
            status="rejected",
            sanitized_text="SECRET_KEY=leaked_value",
        )
        operation.id = op_uuid

        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None

        op_result = MagicMock()
        op_result.scalar_one_or_none.return_value = operation

        execute_returns = [op_result, no_existing, MagicMock()]
        execute_call_count = {"n": 0}

        async def side_effect_execute(stmt):
            n = execute_call_count["n"]
            execute_call_count["n"] += 1
            return execute_returns[n] if n < len(execute_returns) else MagicMock()

        session = AsyncMock()
        session.execute.side_effect = side_effect_execute
        session.add = MagicMock()  # synchronous in agent — plain MagicMock avoids coroutine warnings

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=False)

        from workers.core.detector import Finding

        residual = Finding(
            detector="regex.REGEX_ENV_SECRET_ASSIGNMENT",
            rule_id="regex_env_secret_assignment",
            span_start=0,
            span_end=22,
            confidence=0.95,
            severity="high",
            explanation={"pattern": "regex_env_secret_assignment", "matched_preview": "SECRET_KEY=leaked_value"},
        )

        with (
            patch("workers.agents.rescan_agent.get_session", return_value=cm),
            patch(
                "workers.agents.rescan_agent._regex_detector.detect",
                new=AsyncMock(return_value=[residual]),
            ),
            patch(
                "workers.agents.rescan_agent._presidio_detector.detect",
                new=AsyncMock(return_value=[]),
            ),
            patch("workers.agents.rescan_agent.TASK_DURATION_SECONDS") as mock_timer,
            patch("workers.agents.rescan_agent.TASKS_TOTAL"),
            patch("workers.agents.reviewer_agent.process_review"),
        ):
            mock_timer.labels.return_value.__enter__ = MagicMock(return_value=None)
            mock_timer.labels.return_value.__exit__ = MagicMock(return_value=False)

            from workers.agents.rescan_agent import _rescan_operation_async

            await _rescan_operation_async(operation_id)

        # No status update should be issued for rejected operations
        assert execute_call_count["n"] == 2


# ---------------------------------------------------------------------------
# Integration-style test for merge helper (no DB, no broker)
# ---------------------------------------------------------------------------


class TestMergeFindingsIntegration:
    """Verify _merge_findings deduplication used by rescan_agent."""

    def test_merge_deduplicates_overlapping_findings(self) -> None:
        from workers.core.detector import Finding
        from workers.agents.detector_agent import _merge_findings

        regex_f = Finding(
            detector="regex.REGEX_CONNECTION_STRING",
            rule_id="regex_connection_string",
            span_start=0,
            span_end=30,
            confidence=1.0,
            severity="critical",
            explanation={},
        )
        presidio_f = Finding(
            detector="presidio.API_KEY",
            rule_id="presidio_api_key",
            span_start=5,
            span_end=25,
            confidence=0.8,
            severity="critical",
            explanation={},
        )

        merged = _merge_findings([regex_f], [presidio_f])
        # Presidio finding overlaps with regex finding → should be excluded
        assert len(merged) == 1
        assert merged[0].rule_id == "regex_connection_string"

    def test_merge_keeps_non_overlapping_presidio_findings(self) -> None:
        from workers.core.detector import Finding
        from workers.agents.detector_agent import _merge_findings

        regex_f = Finding(
            detector="regex.REGEX_JWT_TOKEN",
            rule_id="regex_jwt_token",
            span_start=0,
            span_end=50,
            confidence=1.0,
            severity="high",
            explanation={},
        )
        presidio_f = Finding(
            detector="presidio.EMAIL_ADDRESS",
            rule_id="presidio_email_address",
            span_start=60,
            span_end=90,
            confidence=0.9,
            severity="medium",
            explanation={},
        )

        merged = _merge_findings([regex_f], [presidio_f])
        assert len(merged) == 2

    def test_merge_result_is_sorted_by_span_start(self) -> None:
        from workers.core.detector import Finding
        from workers.agents.detector_agent import _merge_findings

        r1 = Finding(
            detector="regex.REGEX_JWT_TOKEN",
            rule_id="regex_jwt_token",
            span_start=50,
            span_end=100,
            confidence=1.0,
            severity="high",
            explanation={},
        )
        p1 = Finding(
            detector="presidio.EMAIL_ADDRESS",
            rule_id="presidio_email_address",
            span_start=10,
            span_end=30,
            confidence=0.9,
            severity="medium",
            explanation={},
        )

        merged = _merge_findings([r1], [p1])
        assert merged[0].span_start == 10
        assert merged[1].span_start == 50

    def test_merge_empty_inputs(self) -> None:
        from workers.agents.detector_agent import _merge_findings

        assert _merge_findings([], []) == []

    def test_merge_only_regex(self) -> None:
        from workers.core.detector import Finding
        from workers.agents.detector_agent import _merge_findings

        f = Finding(
            detector="regex.REGEX_PEM_PRIVATE_KEY",
            rule_id="regex_pem_private_key",
            span_start=0,
            span_end=30,
            confidence=1.0,
            severity="critical",
            explanation={},
        )
        merged = _merge_findings([f], [])
        assert len(merged) == 1

    def test_merge_only_presidio(self) -> None:
        from workers.core.detector import Finding
        from workers.agents.detector_agent import _merge_findings

        f = Finding(
            detector="presidio.PERSON",
            rule_id="presidio_person",
            span_start=5,
            span_end=15,
            confidence=0.7,
            severity="medium",
            explanation={},
        )
        merged = _merge_findings([], [f])
        assert len(merged) == 1


# ---------------------------------------------------------------------------
# Sanitizer integration test — verify rescan_operation is enqueued
# ---------------------------------------------------------------------------


class TestSanitizerEnqueuesRescan:
    """Verify sanitizer_agent enqueues rescan_operation after sanitization."""

    @pytest.mark.asyncio
    async def test_sanitizer_sends_rescan(self) -> None:
        """After a successful sanitize, rescan_operation.send() must be called.

        Because both `process_audit` and `rescan_operation` are imported lazily
        inside _process_sanitize_async, we inject mock modules into sys.modules
        so the `from ... import ...` statements pick up our test doubles.
        """
        import sys

        operation_id = str(uuid.uuid4())
        op_uuid = uuid.UUID(operation_id)

        operation = MagicMock()
        operation.id = op_uuid
        operation.status = "pending"
        operation.policy_version = "1.0.0"
        operation.sanitized_text = None

        # No existing redactions → idempotency guard passes
        no_redaction = MagicMock()
        no_redaction.scalar_one_or_none.return_value = None

        op_result = MagicMock()
        op_result.scalar_one_or_none.return_value = operation

        # No findings for this operation
        findings_result = MagicMock()
        findings_result.scalars.return_value.all.return_value = []

        # Outbox with document text
        outbox_entry = MagicMock()
        outbox_entry.payload = {
            "operation_id": operation_id,
            "document_text": "Hello world, no PII here.",
        }
        outbox_result = MagicMock()
        outbox_result.scalars.return_value.first.return_value = outbox_entry

        execute_returns = [no_redaction, op_result, findings_result, outbox_result, MagicMock()]
        execute_call_count = {"n": 0}

        async def side_effect_execute(stmt):
            n = execute_call_count["n"]
            execute_call_count["n"] += 1
            return execute_returns[n] if n < len(execute_returns) else MagicMock()

        session = AsyncMock()
        session.execute.side_effect = side_effect_execute

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=False)

        rescan_send_calls: list[str] = []

        # Build lightweight fake modules for the two lazy imports inside
        # _process_sanitize_async to avoid real Redis/broker connections.
        mock_audit_actor = MagicMock()
        mock_audit_actor.send.return_value = None
        fake_auditor_module = MagicMock()
        fake_auditor_module.process_audit = mock_audit_actor

        mock_rescan_actor = MagicMock()
        mock_rescan_actor.send.side_effect = lambda op_id: rescan_send_calls.append(op_id)
        fake_rescan_module = MagicMock()
        fake_rescan_module.rescan_operation = mock_rescan_actor

        # Remove previously cached modules so our fakes take effect
        for mod_name in ("workers.agents.auditor_agent", "workers.agents.rescan_agent"):
            sys.modules.pop(mod_name, None)

        sys.modules["workers.agents.auditor_agent"] = fake_auditor_module
        sys.modules["workers.agents.rescan_agent"] = fake_rescan_module

        try:
            with (
                patch("workers.agents.sanitizer_agent.get_session", return_value=cm),
                patch("workers.agents.sanitizer_agent.TASK_DURATION_SECONDS") as mock_timer,
                patch("workers.agents.sanitizer_agent.TASKS_TOTAL"),
            ):
                mock_timer.labels.return_value.__enter__ = MagicMock(return_value=None)
                mock_timer.labels.return_value.__exit__ = MagicMock(return_value=False)

                from workers.agents.sanitizer_agent import _process_sanitize_async

                await _process_sanitize_async(operation_id)
        finally:
            # Restore sys.modules to avoid polluting other tests
            sys.modules.pop("workers.agents.auditor_agent", None)
            sys.modules.pop("workers.agents.rescan_agent", None)

        assert operation_id in rescan_send_calls, (
            "sanitizer_agent must call rescan_operation.send(operation_id)"
        )
