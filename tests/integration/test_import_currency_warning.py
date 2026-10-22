# SPDX-License-Identifier: AGPL-3.0-or-later
"""Currency-mismatch warning on the import settings section.

Covers: KAL-CSV-038
"""

from __future__ import annotations

import pytest

from kaleta.services.import_service import currency_mismatch_warning


class TestCurrencyMismatchWarning:
    @pytest.mark.parametrize(
        ("file_currency", "account_currency", "expected"),
        [
            ("", "PLN", False),
            ("PLN", "PLN", False),
            ("EUR", "PLN", True),
            ("PLN", "", False),
        ],
    )
    def test_warning_only_when_both_known_and_differ(
        self, file_currency: str, account_currency: str, expected: bool
    ) -> None:
        """Covers: KAL-CSV-038"""
        assert (
            currency_mismatch_warning(
                file_currency=file_currency, account_currency=account_currency
            )
            is expected
        )
