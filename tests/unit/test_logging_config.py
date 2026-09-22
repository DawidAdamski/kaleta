# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured logging: correlation fields, redaction and the session buffer."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from kaleta.logging_config import JsonFormatter, RequestContextMiddleware
from kaleta.observability import (
    MAX_ARG_CHARS,
    MAX_RECORDS,
    RedactingFilter,
    RingBufferHandler,
    SessionRingBuffer,
    bind_event_id,
    bind_request,
    context_fields,
    redact,
    reset,
    set_session_resolver,
)


def _record(msg: str, *args: Any, name: str = "kaleta.test") -> logging.LogRecord:
    return logging.LogRecord(name, logging.INFO, "test.py", 1, msg, args, None)


class TestJsonRecords:
    def test_record_carries_the_correlation_fields(self) -> None:
        tokens = bind_request(request_id="req-1", route="/api/v1/health", session_id="sess-1")
        bind_event_id("EV123456")
        try:
            payload = json.loads(JsonFormatter().format(_record("boom")))
        finally:
            reset(tokens)

        assert payload["msg"] == "boom"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "kaleta.test"
        assert payload["request_id"] == "req-1"
        assert payload["route"] == "/api/v1/health"
        assert payload["session_id"] == "sess-1"
        assert payload["event_id"] == "EV123456"
        assert payload["app_version"]
        assert payload["ts"]

    def test_fields_nobody_bound_are_left_out(self) -> None:
        payload = json.loads(JsonFormatter().format(_record("plain")))
        assert "request_id" not in payload
        assert "tenant_id" not in payload

    def test_an_absent_request_id_is_generated_per_request(self) -> None:
        first = bind_request()
        generated = context_fields()["request_id"]
        reset(first)
        second = bind_request()
        assert context_fields()["request_id"] != generated
        reset(second)

    def test_the_exception_text_is_redacted_too(self) -> None:
        try:
            raise RuntimeError("mail to dawid@example.com")
        except RuntimeError as exc:
            record = _record("failed")
            record.exc_info = (type(exc), exc, exc.__traceback__)
        payload = json.loads(JsonFormatter().format(record))
        assert "dawid@example.com" not in payload["exc"]


class TestRedaction:
    def test_the_token_after_a_bearer_scheme_is_masked(self) -> None:
        # The scheme sits between the header name and the secret; masking only
        # the next word would redact "Bearer" and leave the token in the clear.
        assert redact("Authorization: Bearer abc123xyzTOKEN") == "Authorization [redacted]"

    def test_a_bare_bearer_token_is_masked(self) -> None:
        assert redact("Bearer abc123xyzTOKEN") == "Bearer [redacted]"

    def test_credentials_in_key_value_form_are_masked(self) -> None:
        assert redact("authorization=abc123def") == "authorization [redacted]"
        assert redact("password: hunter2 and the rest") == "password [redacted] and the rest"

    def test_email_addresses_are_masked(self) -> None:
        assert redact("login for ana.k+tag@example.co.uk failed") == ("login for [redacted] failed")

    def test_query_strings_are_dropped_but_the_path_stays(self) -> None:
        assert redact("GET /api/v1/transactions?q=zabka&token=abc") == (
            "GET /api/v1/transactions?[redacted]"
        )

    def test_long_arguments_are_cut_before_the_message_is_built(self) -> None:
        record = _record("payload=%s", "x" * (MAX_ARG_CHARS + 50))
        RedactingFilter().filter(record)
        assert "truncated" in record.getMessage()
        assert len(record.getMessage()) < MAX_ARG_CHARS + 60

    def test_the_filter_formats_once_and_clears_the_args(self) -> None:
        record = _record("hello %s", "world")
        RedactingFilter().filter(record)
        assert record.getMessage() == "hello world"
        assert not record.args


class TestSessionRingBuffer:
    @pytest.fixture(autouse=True)
    def _clean(self):
        SessionRingBuffer.clear()
        set_session_resolver(None)
        yield
        SessionRingBuffer.clear()
        set_session_resolver(None)

    def test_records_are_kept_per_session_and_capped(self) -> None:
        handler = RingBufferHandler()
        handler.addFilter(RedactingFilter())
        tokens = bind_request(request_id="r", session_id="sess-A")
        try:
            for index in range(MAX_RECORDS + 25):
                handler.emit(_record("line %s", index))
        finally:
            reset(tokens)

        lines = SessionRingBuffer.records("sess-A")
        assert len(lines) == MAX_RECORDS
        assert lines[0]["msg"] == f"line {25}"
        assert lines[-1]["msg"] == f"line {MAX_RECORDS + 24}"

    def test_lines_are_redacted_on_the_way_in(self) -> None:
        handler = RingBufferHandler()
        handler.addFilter(RedactingFilter())
        tokens = bind_request(request_id="r", session_id="sess-B")
        try:
            record = _record("welcome %s", "ana@example.com")
            handler.handle(record)
        finally:
            reset(tokens)
        assert "ana@example.com" not in SessionRingBuffer.records("sess-B")[0]["msg"]

    def test_a_session_without_an_id_is_not_buffered(self) -> None:
        handler = RingBufferHandler()
        handler.emit(_record("orphan"))
        assert SessionRingBuffer.records(None) == []

    def test_dropping_a_session_forgets_its_lines(self) -> None:
        SessionRingBuffer.append("sess-C", {"msg": "one"})
        SessionRingBuffer.drop("sess-C")
        assert SessionRingBuffer.records("sess-C") == []

    def test_the_ui_resolver_names_the_session_outside_a_request(self) -> None:
        set_session_resolver(lambda: "sess-UI")
        handler = RingBufferHandler()
        handler.emit(_record("from a nicegui handler"))
        assert SessionRingBuffer.records("sess-UI")[0]["msg"] == "from a nicegui handler"


class TestRequestContextMiddleware:
    @pytest.mark.asyncio
    async def test_an_incoming_request_id_is_kept_and_returned(self) -> None:
        seen: dict[str, Any] = {}
        sent: list[dict[str, Any]] = []

        async def app(_scope: Any, _receive: Any, send: Any) -> None:
            seen.update(context_fields())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def receive() -> dict[str, Any]:
            return {"type": "http.request"}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/health",
            "headers": [(b"x-request-id", b"from-the-edge")],
        }
        await RequestContextMiddleware(app)(scope, receive, send)

        assert seen["request_id"] == "from-the-edge"
        assert seen["route"] == "/api/v1/health"
        headers = dict(sent[0]["headers"])
        assert headers[b"x-request-id"] == b"from-the-edge"

    @pytest.mark.asyncio
    async def test_the_context_does_not_outlive_the_request(self) -> None:
        async def app(_scope: Any, _receive: Any, send: Any) -> None:
            await send({"type": "http.response.start", "status": 204, "headers": []})

        async def receive() -> dict[str, Any]:
            return {"type": "http.request"}

        async def send(_message: dict[str, Any]) -> None:
            return None

        scope = {"type": "http", "method": "GET", "path": "/x", "headers": []}
        await RequestContextMiddleware(app)(scope, receive, send)
        assert context_fields() == {}

    @pytest.mark.asyncio
    async def test_non_http_scopes_pass_straight_through(self) -> None:
        calls: list[str] = []

        async def app(scope: Any, _receive: Any, _send: Any) -> None:
            calls.append(scope["type"])

        async def receive() -> dict[str, Any]:
            return {}

        async def send(_message: dict[str, Any]) -> None:
            return None

        await RequestContextMiddleware(app)({"type": "websocket"}, receive, send)
        assert calls == ["websocket"]
