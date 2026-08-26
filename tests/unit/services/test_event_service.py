# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for anonymous app event capture."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.services.event_capture import _should_capture
from kaleta.services.event_service import EventService, event_payload_fields, stack_hash


def test_event_payload_has_no_free_text_pii_fields() -> None:
    """Covers: KAL-OBS-001 (payload shape)."""
    fields = event_payload_fields(RuntimeError("secret payee name"))
    assert set(fields.keys()) == {
        "level",
        "exception_class",
        "stack_hash",
        "stack_trace",
        "app_version",
    }


def test_stack_hash_is_stable_for_same_exception() -> None:
    exc = ValueError("boom")
    assert stack_hash(exc) == stack_hash(exc)


def test_should_not_capture_validation_errors() -> None:
    """Covers: KAL-OBS-002."""
    assert _should_capture(ValidationError("bad input"), user_events_enabled=True) is False


def test_should_capture_unhandled_exceptions_when_enabled() -> None:
    assert _should_capture(RuntimeError("boom"), user_events_enabled=True) is True


def test_user_opt_out_blocks_capture() -> None:
    assert _should_capture(RuntimeError("boom"), user_events_enabled=False) is False


@pytest.mark.asyncio
async def test_record_and_lookup_event(session: AsyncSession) -> None:
    """Covers: KAL-OBS-001."""
    svc = EventService(session)
    event_id = await svc.record(RuntimeError("test failure"), route="/dashboard")
    assert len(event_id) == 8
    row = await svc.get_by_event_id(event_id)
    assert row is not None
    assert row.route == "/dashboard"
    assert row.exception_class == "RuntimeError"


@pytest.mark.asyncio
async def test_purge_older_than(session: AsyncSession) -> None:
    """Covers: KAL-OBS-003."""
    from datetime import UTC, datetime, timedelta

    from kaleta.models.app_event import AppEvent

    svc = EventService(session)
    old = AppEvent(
        event_id="OLDEVENT1",
        occurred_at=datetime.now(UTC) - timedelta(days=30),
        level="ERROR",
        route="/old",
        exception_class="RuntimeError",
        stack_hash="abc",
        stack_trace="(none)",
        app_version="test",
    )
    session.add(old)
    await session.commit()
    deleted = await svc.purge_older_than(7)
    assert deleted >= 1
    assert await svc.get_by_event_id("OLDEVENT1") is None
