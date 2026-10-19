# SPDX-License-Identifier: AGPL-3.0-or-later
"""Defense-in-depth guard for cross-family isolation on the REST API.

Cross-family isolation (ADR-35/38) rests on a single control: every ``/api/v1``
data route opens its database session through ``get_session``, which runs
``resolve_request_tenant`` and binds the request to one family's schema via
``schema_translate_map``. There are no per-row ``tenant_id`` predicates to fall
back on (the security assessment's F-5, "accepted by design"), so a *new* route
that opened a session some other way — the public registry session, or a raw
session factory — would silently read across families.

This is a static guard, not a runtime test: it reads the ``api/v1`` source and
asserts the invariant by construction, so it cannot drift with a FastAPI
internals change. ``health`` is the one public route (registry only, no tenant
data) and is exempt.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TypeGuard

import pytest

V1_DIR = Path(__file__).resolve().parents[2] / "src" / "kaleta" / "api" / "v1"
# ``health`` is deliberately public (registry-only, no tenant data); ``__init__``
# wires the routers and defines no handler.
_EXEMPT = {"__init__.py", "health.py"}
_ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "head", "options", "api_route"}
# A v1 data handler must open its session through this dependency (tenant-bound),
# and it must be *this* get_session — the one in kaleta.api.deps that runs
# resolve_request_tenant, not the plain kaleta.db.session.get_session which does
# not bind a family.
_REQUIRED_SESSION_DEP = "get_session"
_SESSION_DEP_MODULE = "kaleta.api.deps"
# Opening a session any other way inside a v1 handler would bypass the family
# binding — these must never appear in v1.
_FORBIDDEN_SESSION_SOURCES = {
    "get_public_session",
    "AsyncSessionFactory",
    "make_session_factory",
    "async_session",
}


def _v1_modules() -> list[Path]:
    # rglob so a future subpackage (api/v1/foo/routes.py) is scanned too.
    return sorted(p for p in V1_DIR.rglob("*.py") if p.name not in _EXEMPT)


def _get_session_import_module(tree: ast.Module) -> str | None:
    """The module a bare ``get_session`` name is imported from, if any."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == _REQUIRED_SESSION_DEP and alias.asname is None:
                    return node.module
    return None


def _is_route_handler(node: ast.AST) -> TypeGuard[ast.AsyncFunctionDef | ast.FunctionDef]:
    """True for a function decorated with ``@router.<method>(...)``."""
    if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
        return False
    for dec in node.decorator_list:
        call = dec.func if isinstance(dec, ast.Call) else dec
        if (
            isinstance(call, ast.Attribute)
            and call.attr in _ROUTE_METHODS
            and isinstance(call.value, ast.Name)
            and call.value.id == "router"
        ):
            return True
    return False


def _depends_targets(func: ast.AsyncFunctionDef | ast.FunctionDef) -> set[str]:
    """Names passed to ``Depends(...)`` in the handler's parameter defaults."""
    args = func.args
    defaults = [*args.defaults, *args.kw_defaults]
    targets: set[str] = set()
    for default in defaults:
        if (
            isinstance(default, ast.Call)
            and isinstance(default.func, ast.Name)
            and default.func.id == "Depends"
            and default.args
            and isinstance(default.args[0], ast.Name)
        ):
            targets.add(default.args[0].id)
    return targets


def _handlers(module: Path) -> list[ast.AsyncFunctionDef | ast.FunctionDef]:
    tree = ast.parse(module.read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if _is_route_handler(n)]


@pytest.mark.parametrize("module", _v1_modules(), ids=lambda p: p.name)
def test_every_v1_handler_uses_the_tenant_bound_session(module: Path) -> None:
    """Guards security assessment F-5 (isolation is the single cross-family control).

    Every ``/api/v1`` route handler (outside the public ``health`` route) must
    take ``session=Depends(get_session)``, the tenant-resolved session. A route
    added without it would run outside any family's schema.
    """
    handlers = _handlers(module)
    assert handlers, f"{module.name}: no @router route handlers found — update the guard"
    offenders = [h.name for h in handlers if _REQUIRED_SESSION_DEP not in _depends_targets(h)]
    assert not offenders, (
        f"{module.name}: {offenders} do not depend on get_session; a v1 data route must open "
        f"its session through get_session (tenant-bound) so it is scoped to the caller's family."
    )


@pytest.mark.parametrize("module", _v1_modules(), ids=lambda p: p.name)
def test_get_session_is_the_tenant_bound_one(module: Path) -> None:
    """The ``get_session`` a v1 module uses must be ``kaleta.api.deps.get_session``.

    ``kaleta.db.session`` also defines a ``get_session`` that does NOT run
    ``resolve_request_tenant`` — importing that one would satisfy the dependency
    check above yet open an unbound session, the closest real F-5 bypass.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    uses_get_session = any(_REQUIRED_SESSION_DEP in _depends_targets(h) for h in _handlers(module))
    if not uses_get_session:
        return
    origin = _get_session_import_module(tree)
    assert origin == _SESSION_DEP_MODULE, (
        f"{module.name}: get_session must be imported from {_SESSION_DEP_MODULE} (the "
        f"tenant-bound dependency), not {origin!r} — another get_session would skip the "
        f"family binding."
    )


@pytest.mark.parametrize("module", _v1_modules(), ids=lambda p: p.name)
def test_no_v1_handler_opens_a_session_another_way(module: Path) -> None:
    """A v1 data module must not reach for the public or a raw session.

    A tripwire, not an exhaustive sieve: it matches the known bypass names as
    plain text, so an aliased import or a direct ``AsyncSession(engine)`` /
    ``engine.connect()`` would slip past. It exists to make the *common* mistakes
    (the public session, the session factory) fail loudly; the import-origin and
    dependency checks above are the primary guarantees.
    """
    source = module.read_text(encoding="utf-8")
    present = sorted(name for name in _FORBIDDEN_SESSION_SOURCES if name in source)
    assert not present, (
        f"{module.name} references {present}; a v1 data route must use get_session only, "
        f"never the public registry session or a raw session factory (cross-family leak risk)."
    )
