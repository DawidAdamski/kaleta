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
    WISE_PROFILE,
    detect_bank_profile,
    enabled_profile_keys,
    is_mbank_content,
    is_wise_content,
    is_wise_qif_content,
    iter_ui_profiles,
)

FIXTURES_IMPORT = Path(__file__).resolve().parents[2] / "e2e" / "fixtures" / "import"


class TestBankProfileRegistry:
    def test_enabled_profiles_are_generic_mbank_and_wise(self) -> None:
        assert enabled_profile_keys() == frozenset({GENERIC_PROFILE, MBANK_PROFILE, WISE_PROFILE})

    def test_ui_profiles_match_registry_order(self) -> None:
        ui = iter_ui_profiles()
        assert [row[0] for row in ui] == [p.key for p in BANK_PROFILES]
        assert all(len(row) == 4 for row in ui)

    def test_mbank_and_wise_have_detectors_generic_does_not(self) -> None:
        by_key = {p.key: p for p in BANK_PROFILES}
        assert by_key[GENERIC_PROFILE].detect is None
        assert by_key[MBANK_PROFILE].detect is is_mbank_content
        assert by_key[WISE_PROFILE].detect is is_wise_content

    def test_detect_bank_profile_promotes_mbank(self) -> None:
        content = "#Numer rachunku\n55 1140 2004\n#Rodzaj rachunku\nEKONTO\n"
        assert detect_bank_profile(content) == MBANK_PROFILE

    def test_detect_bank_profile_promotes_wise(self) -> None:
        content = '"TransferWise ID",Date,Amount,Currency,Description\nX,01-01-2024,-1,EUR,Test\n'
        assert detect_bank_profile(content) == WISE_PROFILE

    def test_detect_bank_profile_promotes_wise_qif(self) -> None:
        content = "!Type:Bank\nD05/17/2026\nT-1.00\nPShop\nNCARD-3802617048\n^\n"
        assert is_wise_qif_content(content) is True
        assert detect_bank_profile(content) == WISE_PROFILE

    def test_detect_bank_profile_ignores_qif_without_wise_ids(self) -> None:
        """Generic QIF stays unclaimed — only the Wise dialect is supported."""
        content = "!Type:Bank\nD01/15/2024\nT-10.00\nPCoffee\n^\n"
        assert is_wise_qif_content(content) is False
        assert detect_bank_profile(content) is None

    def test_detect_bank_profile_ignores_plain_csv(self) -> None:
        content = "date,amount,description\n2024-01-15,-10.00,Coffee\n"
        assert detect_bank_profile(content) is None

    def test_wise_fixture_directory_ships_both_supported_shapes(self) -> None:
        wise = FIXTURES_IMPORT / "wise"
        assert (wise / "jpy-travel-sample.csv").is_file()
        assert (wise / "jpy-travel-sample.qif").is_file()

    def test_fixture_contribution_readme_exists(self) -> None:
        readme = FIXTURES_IMPORT / "README.md"
        assert readme.is_file()
        text = readme.read_text(encoding="utf-8")
        assert "Anonymization checklist" in text
        assert "import_profiles.py" in text
