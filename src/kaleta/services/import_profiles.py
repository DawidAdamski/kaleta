# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bank CSV import profile registry.

Extension point for bank-specific import formats. **Do not invent profiles
without a real anonymized export fixture** — see
``tests/e2e/fixtures/import/README.md``.

### Adding a profile (checklist)

1. Drop an anonymized sample under
   ``tests/e2e/fixtures/import/<profile_id>/sample.csv`` (follow the README).
2. Implement a preprocessor (mirror ``MBankPreprocessor`` in
   ``import_service``) — extract metadata / data section as needed.
3. Register a :class:`BankProfileSpec` in :data:`BANK_PROFILES` with a
   ``detect`` callable when auto-detect from the generic picker should
   work.
4. Wire the parse branch in ``ImportService.parse_queued_file``.
5. Add i18n keys (``import.profile_<id>``) in ``en.json`` / ``pl.json``.
6. Add unit tests that load the fixture; retag BDD ``KAL-CSV-*`` when
   covered. Prefer one bank per PR.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

GENERIC_PROFILE = "generic"
MBANK_PROFILE = "mbank"
WISE_PROFILE = "wise"

METADATA_PROFILES: frozenset[str] = frozenset({MBANK_PROFILE, WISE_PROFILE})

DetectFn = Callable[[str], bool]


def is_mbank_content(content: str) -> bool:
    """Heuristic: content looks like an mBank CSV export."""
    return "#Numer rachunku" in content or "#Rodzaj rachunku" in content


_QIF_BANK_HEADER = "!Type:Bank"
_WISE_QIF_REFERENCE = re.compile(r"^N(?:CARD|TRANSFER)-\w+", re.MULTILINE)


def is_wise_qif_content(content: str) -> bool:
    """Heuristic: content looks like a Wise QIF statement export.

    QIF is a generic format, so the ``!Type:Bank`` header alone is not enough
    to claim the file as Wise's. Wise stamps every record with its own
    transaction id in the ``N`` field (``CARD-…`` / ``TRANSFER-…``, the same
    tokens as the CSV export's ``TransferWise ID`` column) — that pairing is
    what identifies the dialect.

    Only the two prefixes the real export actually contains are matched; a
    file whose ids Kaleta has not seen falls through to the generic path
    rather than being claimed on a guess.
    """
    if _QIF_BANK_HEADER not in content[:64]:
        return False
    return _WISE_QIF_REFERENCE.search(content) is not None


def is_wise_content(content: str) -> bool:
    """Heuristic: content looks like a Wise (TransferWise) CSV or QIF export."""
    sample = content[:512]
    if "TransferWise ID" in sample or "transferwise id" in sample.lower():
        return True
    return is_wise_qif_content(content)


@dataclass(frozen=True, slots=True)
class BankProfileSpec:
    """One selectable import format.

    ``detect`` is optional. When set, ``detect_bank_profile`` may promote
    a ``generic`` upload to this profile. Only enable (``enabled=True``)
    profiles that have a real fixture and a working parse path.
    """

    key: str
    label_key: str
    icon: str
    enabled: bool
    detect: DetectFn | None = None


BANK_PROFILES: tuple[BankProfileSpec, ...] = (
    BankProfileSpec(
        key=GENERIC_PROFILE,
        label_key="import.profile_generic",
        icon="table_chart",
        enabled=True,
    ),
    BankProfileSpec(
        key=MBANK_PROFILE,
        label_key="import.profile_mbank",
        icon="account_balance",
        enabled=True,
        detect=is_mbank_content,
    ),
    BankProfileSpec(
        key=WISE_PROFILE,
        label_key="import.profile_wise",
        icon="language",
        enabled=True,
        detect=is_wise_content,
    ),
    # Next bank: append BankProfileSpec here only after a real fixture lands.
    # Example (do not uncomment without fixtures/import/<id>/sample.csv):
    # BankProfileSpec(
    #     key="example_bank",
    #     label_key="import.profile_example_bank",
    #     icon="account_balance",
    #     enabled=True,
    #     detect=is_example_bank_content,
    # ),
)


def iter_ui_profiles() -> list[tuple[str, str, str, bool]]:
    """Return ``(key, label_key, icon, enabled)`` rows for the profile picker."""
    return [(p.key, p.label_key, p.icon, p.enabled) for p in BANK_PROFILES]


def detect_bank_profile(content: str) -> str | None:
    """Return the first non-generic profile whose ``detect`` matches *content*."""
    for spec in BANK_PROFILES:
        if spec.key == GENERIC_PROFILE or spec.detect is None:
            continue
        if spec.detect(content):
            return spec.key
    return None


def enabled_profile_keys() -> frozenset[str]:
    """Keys of profiles shown as selectable in the UI."""
    return frozenset(p.key for p in BANK_PROFILES if p.enabled)
