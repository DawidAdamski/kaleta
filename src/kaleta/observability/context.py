# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-request correlation context shared by logs, events and bug reports.

The values live in :class:`~contextvars.ContextVar`s so an HTTP request and
everything it triggers agree on one ``request_id``. A NiceGUI event handler
runs outside the HTTP middleware, so the session id may instead come from a
resolver the UI layer installs — that keeps this module free of any UI import.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass

_request_id: ContextVar[str | None] = ContextVar("kaleta_request_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("kaleta_session_id", default=None)
_route: ContextVar[str | None] = ContextVar("kaleta_route", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("kaleta_tenant_id", default=None)
_user_id: ContextVar[int | None] = ContextVar("kaleta_user_id", default=None)
_event_id: ContextVar[str | None] = ContextVar("kaleta_event_id", default=None)

SessionResolver = Callable[[], str | None]
_session_resolver: SessionResolver | None = None


@dataclass(frozen=True)
class ContextTokens:
    """Reset handles returned by :func:`bind_request`."""

    request_id: Token[str | None]
    session_id: Token[str | None]
    route: Token[str | None]
    tenant_id: Token[str | None]
    user_id: Token[int | None]
    event_id: Token[str | None]


def new_request_id() -> str:
    """Return a fresh correlation id for a request that arrived without one."""
    return uuid.uuid4().hex


def bind_request(
    *,
    request_id: str | None = None,
    route: str | None = None,
    session_id: str | None = None,
    tenant_id: str | None = None,
    user_id: int | None = None,
) -> ContextTokens:
    """Bind the correlation values for the current task; reset with :func:`reset`."""
    return ContextTokens(
        request_id=_request_id.set(request_id or new_request_id()),
        session_id=_session_id.set(session_id),
        route=_route.set(route),
        tenant_id=_tenant_id.set(tenant_id),
        user_id=_user_id.set(user_id),
        event_id=_event_id.set(None),
    )


def reset(tokens: ContextTokens) -> None:
    """Undo a :func:`bind_request` in the task that made it."""
    _request_id.reset(tokens.request_id)
    _session_id.reset(tokens.session_id)
    _route.reset(tokens.route)
    _tenant_id.reset(tokens.tenant_id)
    _user_id.reset(tokens.user_id)
    _event_id.reset(tokens.event_id)


def bind_event_id(event_id: str | None) -> None:
    """Record the event id issued during this request."""
    _event_id.set(event_id)


def set_session_resolver(resolver: SessionResolver | None) -> None:
    """Install a fallback that knows the session id outside an HTTP request."""
    global _session_resolver
    _session_resolver = resolver


def current_request_id() -> str | None:
    return _request_id.get()


def current_route() -> str | None:
    return _route.get()


def current_tenant_id() -> str | None:
    return _tenant_id.get()


def current_user_id() -> int | None:
    return _user_id.get()


def current_event_id() -> str | None:
    return _event_id.get()


def current_session_id() -> str | None:
    """Session id from the request context, or from the UI resolver."""
    bound = _session_id.get()
    if bound is not None:
        return bound
    if _session_resolver is None:
        return None
    try:
        return _session_resolver()
    except Exception:  # pragma: no cover - a resolver must never break logging
        return None


def context_fields() -> dict[str, object]:
    """Correlation fields present right now, ready to merge into a log record."""
    fields: dict[str, object] = {
        "request_id": current_request_id(),
        "session_id": current_session_id(),
        "route": current_route(),
        "tenant_id": current_tenant_id(),
        "user_id": current_user_id(),
        "event_id": current_event_id(),
    }
    return {key: value for key, value in fields.items() if value is not None}
