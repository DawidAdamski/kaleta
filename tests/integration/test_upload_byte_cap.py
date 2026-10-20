# SPDX-License-Identifier: AGPL-3.0-or-later
"""The import upload has a server-side byte cap, independent of the browser limit.

Covers: KAL-SEC-004
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from kaleta.config import settings
from kaleta.views.import_view.upload_guard import upload_exceeds_cap


@dataclass
class _FakeUpload:
    """A stand-in for NiceGUI's FileUpload: only ``size()`` matters to the guard."""

    _size: int

    def size(self) -> int:
        return self._size


def test_upload_just_over_the_cap_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A file one byte over the configured cap is rejected before it is read.

    This is the F-4 fix — before it, the handler read the whole body with no
    server-side cap, so an oversize crafted POST was accepted.

    Covers: KAL-SEC-004
    """
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    assert upload_exceeds_cap(_FakeUpload(1025)) is True


def test_upload_at_or_under_the_cap_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exactly at the cap, and below it, are allowed — no regression for real files.

    Covers: KAL-SEC-004
    """
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    assert upload_exceeds_cap(_FakeUpload(1024)) is False
    assert upload_exceeds_cap(_FakeUpload(0)) is False


def test_explicit_cap_overrides_the_setting() -> None:
    """A caller-supplied cap takes precedence over ``settings.max_upload_bytes``.

    Covers: KAL-SEC-004
    """
    assert upload_exceeds_cap(_FakeUpload(100), cap_bytes=50) is True
    assert upload_exceeds_cap(_FakeUpload(50), cap_bytes=50) is False


def test_default_cap_is_fifty_mib() -> None:
    """The out-of-the-box cap matches the browser hint (50 MiB).

    Covers: KAL-SEC-004
    """
    assert settings.max_upload_bytes == 50 * 1024 * 1024
