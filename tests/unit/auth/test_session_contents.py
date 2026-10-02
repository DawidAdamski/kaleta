# SPDX-License-Identifier: AGPL-3.0-or-later
"""Nothing secret goes into ``app.storage.user`` — enforced, not remembered.

ADR-035 keeps session storage free of secrets: it is a JSON file per browser
on disk, or a Redis key on a hosted instance, and either can be read by more
than the process that wrote it. These tests pin that for ``auth/session.py``,
the module that writes the session: every key it writes is a ``SESSION_*``
constant, no constant names a secret, and every value the writers leave
behind is a flag, an id, a username, a timestamp, a purpose or a nonce — never
a password hash, TOTP secret, recovery code or key.
"""

from __future__ import annotations

import ast
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from kaleta.auth import session as session_mod
from kaleta.schemas.identity import Identity, MfaRequired

_SESSION_PY = Path(session_mod.__file__)

#: ``SESSION_*`` constants that are not storage keys.
_NOT_KEYS = {"SESSION_COOKIE_NAME", "SESSION_ROTATE_PATH"}

_SECRET_WORDS = re.compile(
    r"password|passwd|hash|secret|totp|recovery|otp_|_key|token|salt|cipher|encrypt",
    re.IGNORECASE,
)

_USER_ID = 7
_USERNAME = "ania"
# A hosted sign-in also leaves its account behind: an id, a schema name, the
# provider's opaque subject and the e-mail — still no secret among them.
_TENANT = session_mod.SessionTenant(
    tenant_id=3,
    schema="t_0123456789ab",
    auth_subject="0b7c2c8e-6f1a-4c55-9d7e-1c2b3a4d5e6f",
    email="ania@example.com",
)

_ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiJ9.aal1-access-token.c2ln"  # noqa: S105 — a fixture
_HOSTED_PENDING = MfaRequired(
    identity=Identity(
        subject=_TENANT.auth_subject,
        email=_TENANT.email,
        email_verified=True,
        access_token=_ACCESS_TOKEN,
    ),
    factor_id="f-1",
)


def _storage_key_constants() -> dict[str, str]:
    return {
        name: value
        for name, value in vars(session_mod).items()
        if name.startswith("SESSION_") and name not in _NOT_KEYS and isinstance(value, str)
    }


def _names_written_by_session_py() -> set[str]:
    """Every ``X`` in ``app.storage.user[X] = …`` inside ``auth/session.py``."""
    tree = ast.parse(_SESSION_PY.read_text(encoding="utf-8"))
    written: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Subscript):
                continue
            if ast.unparse(target.value) != "app.storage.user":
                continue
            if not isinstance(target.slice, ast.Name):
                pytest.fail(
                    f"auth/session.py:{node.lineno} writes app.storage.user with a "
                    f"non-constant key: {ast.unparse(target.slice)}"
                )
            written.add(target.slice.id)
    return written


def test_every_key_session_py_writes_is_a_session_constant() -> None:
    """The constant list is the whole list, so the checks below see every key."""
    written = _names_written_by_session_py()
    assert written, "found no app.storage.user writes — the scan is broken"
    assert written <= set(_storage_key_constants())


def test_no_session_key_names_a_secret() -> None:
    for name, value in _storage_key_constants().items():
        assert not _SECRET_WORDS.search(name), name
        assert not _SECRET_WORDS.search(value), f"{name} = {value!r}"


@pytest.fixture
def bucket(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    store: dict[str, Any] = {}
    monkeypatch.setattr(session_mod.app, "storage", type("S", (), {"user": store})())
    monkeypatch.setattr(session_mod.ui.navigate, "to", lambda *_a, **_k: None)
    return store


def _is_iso_timestamp(value: str) -> bool:
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def test_values_written_by_every_writer_are_harmless(bucket: dict[str, Any]) -> None:
    """Drive every writer, then look at what is left in the bucket and what passed through."""
    seen: dict[str, set[Any]] = {}

    def snapshot() -> None:
        for key, value in bucket.items():
            seen.setdefault(key, set()).add(value)

    session_mod.begin_mfa_challenge(user_id=_USER_ID, username=_USERNAME)
    snapshot()
    # The hosted variant parks an aal1 access token — in process memory only;
    # the bucket gets a reference to it.
    session_mod.begin_hosted_mfa_challenge(_HOSTED_PENDING)
    snapshot()
    session_mod.finish_login(
        user_id=_USER_ID, username=_USERNAME, target="/", mfa_verified=True, tenant=_TENANT
    )
    snapshot()
    session_mod.login_session(user_id=_USER_ID, username=_USERNAME, tenant=_TENANT)
    session_mod.mark_mfa_verified()
    session_mod.keep_session_after_revocation(_USER_ID)
    bucket.pop(session_mod.SESSION_LAST_SEEN_AT)
    session_mod.touch_session()
    snapshot()
    nonce = session_mod.stamp_rotation_nonce("logout")
    snapshot()
    session_mod.finish_logout()
    snapshot()

    keys = set(_storage_key_constants().values())
    # Every key was written at least once, and nothing else was.
    assert set(seen) == keys, set(seen) ^ keys

    for key, values in seen.items():
        for value in values:
            if isinstance(value, bool) or value in (_USER_ID, _TENANT.tenant_id):
                continue
            assert isinstance(value, str), f"{key} holds {type(value).__name__}"
            assert (
                value == _USERNAME
                or value in {"login", "logout"}
                or value in {_TENANT.schema, _TENANT.auth_subject, _TENANT.email}
                or _is_iso_timestamp(value)
                or (key == session_mod.SESSION_ROTATE_NONCE and len(value) == len(nonce))
                or (
                    key == session_mod.SESSION_HOSTED_MFA_REF
                    and len(value) == len(nonce)
                    and _ACCESS_TOKEN not in value
                )
            ), f"{key} holds an unexpected value {value!r}"
    assert not any(_ACCESS_TOKEN in str(v) for vs in seen.values() for v in vs)
