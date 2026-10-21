# SPDX-License-Identifier: AGPL-3.0-or-later
"""A settings validation failure is reported by message only — no secret leaks.

pydantic's ``ValidationError`` records each offending field's raw ``input``.
For settings those inputs come from the environment, so an unsanitised error
can echo the start of ``KALETA_SECRET_KEY`` onto stderr or into logs.
``load_settings`` must name the offending field without ever echoing a value.
"""

from __future__ import annotations

import pytest

from kaleta.config.settings import load_settings
from kaleta.exceptions import ValidationError

# A literal, obviously-secret marker; must never appear in any error output.
_SENTINEL_SECRET = "SENTINEL_SECRET_do_not_leak_0123456789abcdef"


def test_load_settings_names_field_without_leaking_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A real secret is present in the environment...
    monkeypatch.setenv("KALETA_DEBUG", "true")
    monkeypatch.setenv("KALETA_SECRET_KEY", _SENTINEL_SECRET)
    # ...and an unrelated field is invalid, so construction fails.
    monkeypatch.setenv("KALETA_PORT", "not-a-port")

    with pytest.raises(ValidationError) as excinfo:
        load_settings()

    message = str(excinfo.value)
    # (a) the offending field is named
    assert "port" in message
    # (b) the secret value never appears in the sanitised message...
    assert _SENTINEL_SECRET not in message
    assert "SENTINEL_SECRET" not in message
    # ...nor anywhere in the raised exception: load_settings raises outside the
    # except block, so the pydantic error (which still holds the raw input) is
    # attached neither as __cause__ nor as __context__.
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None


def test_load_settings_does_not_leak_secret_when_the_secret_field_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A valid secret is present in the environment while an unrelated field
    # (the log level) is the one pydantic refuses — the failure must still not
    # echo the secret that happens to be set alongside it.
    monkeypatch.delenv("KALETA_DEBUG", raising=False)
    monkeypatch.setenv("KALETA_SECRET_KEY", _SENTINEL_SECRET)
    monkeypatch.setenv("KALETA_LOG_LEVEL", "NOPE")

    with pytest.raises(ValidationError) as excinfo:
        load_settings()

    message = str(excinfo.value)
    assert "log_level" in message
    assert _SENTINEL_SECRET not in message
    assert "SENTINEL_SECRET" not in message
