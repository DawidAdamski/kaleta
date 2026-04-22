"""File-storage for institution logos.

Uploaded logos live at ``~/.kaleta/logos/`` and are served at ``/logos/`` via
NiceGUI's static-files mechanism (wired in :mod:`kaleta.pwa`).

Keeping user files out of the package directory means they survive reinstalls
and don't pollute the source tree.
"""

from __future__ import annotations

import contextlib
import uuid
from pathlib import Path

LOGOS_DIR: Path = Path.home() / ".kaleta" / "logos"
LOGO_URL_PREFIX = "/logos"
ALLOWED_SUFFIXES = {".svg", ".png", ".jpg", ".jpeg", ".webp"}


def ensure_dir() -> Path:
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGOS_DIR


def save_logo(filename: str, content: bytes) -> str:
    """Write *content* under a unique name; return the ``/logos/<name>`` URL."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"Unsupported logo format: {suffix}")
    ensure_dir()
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    (LOGOS_DIR / safe_name).write_bytes(content)
    return f"{LOGO_URL_PREFIX}/{safe_name}"


def delete_logo(url: str | None) -> None:
    """Best-effort delete — silently ignore missing or external URLs."""
    if not url or not url.startswith(f"{LOGO_URL_PREFIX}/"):
        return
    name = url[len(LOGO_URL_PREFIX) + 1 :]
    if not name or "/" in name or "\\" in name:
        return
    path = LOGOS_DIR / name
    if path.is_file():
        with contextlib.suppress(OSError):
            path.unlink()
