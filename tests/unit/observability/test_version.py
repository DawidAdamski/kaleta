# SPDX-License-Identifier: AGPL-3.0-or-later
"""The app version is git-derived and traceable, not a hard-coded literal.

Covers: KAL-OPS-001
"""

from __future__ import annotations

import re
from importlib.metadata import version as pkg_version

import kaleta
from kaleta.observability import app_version

#: PEP 440: a release (``0.3.0``) or a dev build between tags
#: (``0.3.1.dev5+g1a2b3c4``), optionally with a local dirty-date suffix.
_PEP440 = re.compile(r"^\d+\.\d+(\.\d+)?([.+].+)?$")


def test_version_is_not_the_old_hardcoded_literal() -> None:
    """Covers: KAL-OPS-001"""
    assert kaleta.__version__
    assert kaleta.__version__ != "0.1.0"


def test_version_has_a_pep440_shape() -> None:
    """Covers: KAL-OPS-001"""
    assert _PEP440.match(kaleta.__version__), kaleta.__version__


def test_all_sources_agree() -> None:
    """Covers: KAL-OPS-001 — ``__version__``, ``app_version()`` and metadata are one value."""
    assert app_version() == kaleta.__version__ == pkg_version("kaleta")


def test_fits_the_event_column_width() -> None:
    """``bug_report`` / ``app_event`` store the version in ``String(40)``."""
    assert len(kaleta.__version__) <= 40
