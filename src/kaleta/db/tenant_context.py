# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which tenant schema the current request or UI event is working in.

``KALETA_TENANCY=multi`` only (ADR-35). The auth middleware and the API
dependencies set the context for HTTP requests; a NiceGUI event handler runs
over the websocket, past every middleware, so for those the auth layer installs
a *resolver* that reads the same answer from the session. ``_SessionProxy``
asks ``current_tenant()`` for every session it opens and refuses to open one
when the answer is ``None`` — a request that does not know its tenant gets an
error, never somebody else's rows.

In ``single`` mode nothing sets a context and nothing asks for one.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from kaleta.db.tenant_schemas import require_valid_schema_name


@dataclass(frozen=True)
class TenantContext:
    """One tenant's schema, and the member acting in it.

    ``member_user_id`` is the member's row in the tenant's own ``users`` table;
    new rows on user-owned tables are attributed to it. ``key_ring`` is the
    slot ``hosted-field-encryption`` fills with the unlocked data key; this
    plan never sets it.
    """

    tenant_id: int
    schema: str
    member_user_id: int | None = None
    key_ring: object | None = None

    def __post_init__(self) -> None:
        require_valid_schema_name(self.schema)


class TenantContextMissingError(RuntimeError):
    """A tenant-schema session was asked for with no tenant known.

    A ``RuntimeError`` rather than a ``KaletaError`` on purpose: it is a bug in
    whichever route forgot to resolve the tenant, and it has to surface as a
    500, not as a friendly 4xx that a client might retry around.
    """


_current: ContextVar[TenantContext | None] = ContextVar("kaleta_tenant", default=None)
_resolver: Callable[[], TenantContext | None] | None = None


def current_tenant() -> TenantContext | None:
    """The tenant set for this request, else whatever the installed resolver says."""
    ctx = _current.get()
    if ctx is not None:
        return ctx
    if _resolver is None:
        return None
    return _resolver()


def set_tenant(ctx: TenantContext | None) -> None:
    """Set the tenant for the rest of the current task (a request, a dependency)."""
    _current.set(ctx)


@contextmanager
def use_tenant(ctx: TenantContext | None) -> Iterator[None]:
    """Work in ``ctx`` for the duration of the block."""
    token = _current.set(ctx)
    try:
        yield
    finally:
        _current.reset(token)


def install_tenant_resolver(resolver: Callable[[], TenantContext | None] | None) -> None:
    """Register the fallback used when nothing set a context for this task."""
    global _resolver
    _resolver = resolver
