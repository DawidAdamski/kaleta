# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-side upload size guard (KAL-SEC-004, security assessment F-4).

The import wizard's ``ui.upload(max_file_size=…)`` is a browser-side limit a
crafted POST can bypass. This guard is the server's own cap: it reads the
uploaded file's declared size (``FileUpload.size()`` reports it without
materialising the body) and the handler rejects anything larger before calling
``read()``, so an oversize upload never becomes an in-memory ``bytes`` object.
"""

from __future__ import annotations

from typing import Protocol

from kaleta.config import settings


class SupportsSize(Protocol):
    """A thing that can report its size in bytes — NiceGUI's ``FileUpload`` does."""

    def size(self) -> int: ...


def upload_exceeds_cap(file: SupportsSize, cap_bytes: int | None = None) -> bool:
    """Whether ``file`` is larger than the cap (``settings.max_upload_bytes`` by default)."""
    cap = settings.max_upload_bytes if cap_bytes is None else cap_bytes
    return file.size() > cap
