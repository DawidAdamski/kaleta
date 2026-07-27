# SPDX-License-Identifier: AGPL-3.0-or-later
"""Registry contracts for bank import profiles.

Covers: extension-point scaffolding for import-bank-profiles plan.
No speculative bank keys may appear as enabled profiles.
"""

from __future__ import annotations

from pathlib import Path

from kaleta.services.import_profiles import (
    BANK_PROFILES,
    GENERIC_PROFILE,
    MBANK_PROFILE,
    detect_bank_profile,
    enabled_profile_keys,
    is_mbank_content,
    iter_ui_profiles,
)

FIXTURES_IMPORT = Path(__file__).resolve().parents[2] / "e2e" / "fixtures" / "import"


class TestBankProfileRegistry:
    def test_enabled_profiles_are_only_generic_and_mbank(self) -> None:
        assert enabled_profile_keys() == frozenset({GENERIC_PROFILE, MBANK_PROFILE})

    def test_ui_profiles_match_registry_order(self) -> None:
        ui = iter_ui_profiles()
        assert [row[0] for row in ui] == [p.key for p in BANK_PROFILES]
        assert all(len(row) == 4 for row in ui)

    def test_mbank_has_detector_generic_does_not(self) -> None:
        by_key = {p.key: p for p in BANK_PROFILES}
        assert by_key[GENERIC_PROFILE].detect is None
        assert by_key[MBANK_PROFILE].detect is is_mbank_content

    def test_detect_bank_profile_promotes_mbank(self) -> None:
        content = "#Numer rachunku\n55 1140 2004\n#Rodzaj rachunku\nEKONTO\n"
        assert detect_bank_profile(content) == MBANK_PROFILE

    def test_detect_bank_profile_ignores_plain_csv(self) -> None:
        content = "date,amount,description\n2024-01-15,-10.00,Coffee\n"
        assert detect_bank_profile(content) is None

    def test_fixture_contribution_readme_exists(self) -> None:
        readme = FIXTURES_IMPORT / "README.md"
        assert readme.is_file()
        text = readme.read_text(encoding="utf-8")
        assert "Anonymization checklist" in text
        assert "import_profiles.py" in text
