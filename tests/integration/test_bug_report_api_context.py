# SPDX-License-Identifier: AGPL-3.0-or-later
"""An API failure must be traceable from the id the user sees to the log line.

Covers: KAL-BUG-003
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from kaleta.api.errors import register_error_handlers
from kaleta.logging_config import JsonFormatter, RequestContextMiddleware
from kaleta.observability import RedactingFilter
from kaleta.services import event_capture
from tests.conftest import make_session_factory


class _JsonCapture(logging.Handler):
    """Collect what the JSON formatter would have written to stdout."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.setFormatter(JsonFormatter())
        # configure_logging() puts the same filter on every real handler.
        self.addFilter(RedactingFilter())
        self.lines: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(json.loads(self.format(record)))


@pytest_asyncio.fixture
async def failing_api(db_engine, monkeypatch: pytest.MonkeyPatch):
    """An API whose one route fails, wired to the test database."""
    factory = make_session_factory(db_engine)
    monkeypatch.setattr(event_capture, "AsyncSessionFactory", factory)

    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware, access_log=True)

    @app.get("/api/v1/boom")
    async def _boom() -> dict[str, str]:
        raise RuntimeError("seeded failure")

    @app.get("/api/v1/fine")
    async def _fine() -> dict[str, str]:
        return {"status": "ok"}

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


@pytest_asyncio.fixture
def json_log():
    handler = _JsonCapture()
    root = logging.getLogger()
    root.addHandler(handler)
    previous = root.level
    root.setLevel(logging.INFO)
    yield handler
    root.removeHandler(handler)
    root.setLevel(previous)


@pytest.mark.asyncio
async def test_event_id_and_request_id_share_a_json_log_line(failing_api, json_log) -> None:
    """Covers: KAL-BUG-003."""
    response = await failing_api.get(
        "/api/v1/boom?account=7",
        headers={"X-Request-ID": "req-from-the-edge"},
    )

    assert response.status_code == 500
    event_id = response.json()["error"]["event_id"]
    assert event_id

    correlated = [
        line
        for line in json_log.lines
        if line.get("event_id") == event_id and line.get("request_id") == "req-from-the-edge"
    ]
    assert correlated, f"no JSON log line joined {event_id} to its request: {json_log.lines}"
    assert correlated[0]["route"] == "/api/v1/boom"
    assert correlated[0]["app_version"]


@pytest.mark.asyncio
async def test_the_request_id_comes_back_on_the_response(failing_api) -> None:
    """Covers: KAL-BUG-003."""
    response = await failing_api.get("/api/v1/fine", headers={"X-Request-ID": "req-from-the-edge"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-from-the-edge"

    generated = await failing_api.get("/api/v1/fine")
    assert generated.headers["x-request-id"]
    assert generated.headers["x-request-id"] != "req-from-the-edge"


@pytest.mark.asyncio
async def test_no_log_line_carries_the_query_string(failing_api, json_log) -> None:
    """Covers: KAL-BUG-003."""
    await failing_api.get("/api/v1/boom?token=super-secret")
    assert json_log.lines
    assert not [line for line in json_log.lines if "super-secret" in line["msg"]]
