# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for anonymous error event capture.

Covers: KAL-OBS-001, KAL-OBS-002, KAL-OBS-003
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.models.app_event import AppEvent
from kaleta.services.event_capture import _should_capture
from kaleta.services.event_service import EventService, event_payload_fields


def test_event_payload_excludes_free_text_pii_fields() -> None:
    """Covers: KAL-OBS-001."""
    fields = event_payload_fields(RuntimeError("payee secret"))
    assert "payee secret" not in str(fields.values())
    assert set(fields.keys()) == {
        "level",
        "exception_class",
        "stack_hash",
        "stack_trace",
        "app_version",
    }


def test_validation_errors_are_not_captured() -> None:
    """Covers: KAL-OBS-002."""
    assert _should_capture(ValidationError("nope"), user_events_enabled=True) is False


@pytest.mark.asyncio
async def test_record_lookup_and_retention_purge(session: AsyncSession) -> None:
    """Covers: KAL-OBS-001, KAL-OBS-003."""
    svc = EventService(session)
    event_id = await svc.record(RuntimeError("integration failure"), route="/api/v1/health")
    row = await svc.get_by_event_id(event_id)
    assert row is not None

    session.add(
        AppEvent(
            event_id="OLDCAP01",
            occurred_at=datetime.now(UTC) - timedelta(days=30),
            level="ERROR",
            route="/old",
            exception_class="RuntimeError",
            stack_hash="deadbeef",
            stack_trace="(none)",
            app_version="test",
        )
    )
    await session.commit()
    deleted = await svc.purge_older_than(7)
    assert deleted >= 1
    assert await svc.get_by_event_id("OLDCAP01") is None
