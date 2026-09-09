# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a Wise statement's download name says, and what it must never carry.

Wise's QIF export names no currency in the file body, so the download name is
the only place the currency-mismatch guard can read one. These tests pin the
exact name shape Wise produces
(``statement_136577258_JPY_2026-04-01_2026-06-30.qif``, recorded in
``tests/e2e/fixtures/import/wise/NOTES.md``), the refusal to guess at anything
else, and the fact that the account-id segment never reaches the caller.
"""

from __future__ import annotations

import datetime

import pytest

from kaleta.services.import_profiles import WiseFilenameMetadata, parse_wise_filename

WISE_QIF_NAME = "statement_136577258_JPY_2026-04-01_2026-06-30.qif"


class TestWiseDownloadNameIsRead:
    def test_currency_and_period_come_off_the_real_name(self) -> None:
        meta = parse_wise_filename(WISE_QIF_NAME)
        assert meta is not None
        assert meta.currency == "JPY"
        assert meta.date_from == datetime.date(2026, 4, 1)
        assert meta.date_to == datetime.date(2026, 6, 30)

    @pytest.mark.parametrize(
        "extension",
        ["qif", "csv", "xlsx", "mt940"],
        ids=["qif", "csv", "xlsx", "mt940"],
    )
    def test_every_format_wise_offers_shares_one_name_shape(self, extension: str) -> None:
        """Wise names all four downloads alike; only QIF needs the currency today."""
        meta = parse_wise_filename(f"statement_136577258_PLN_2026-01-01_2026-03-31.{extension}")
        assert meta is not None
        assert meta.currency == "PLN"

    def test_a_lowercased_name_still_yields_an_uppercase_currency(self) -> None:
        """Some browsers and file managers lowercase a download on save."""
        meta = parse_wise_filename("statement_136577258_jpy_2026-04-01_2026-06-30.qif")
        assert meta is not None
        assert meta.currency == "JPY"


class TestUnrecognisedNamesStayUnknown:
    @pytest.mark.parametrize(
        "name",
        [
            "",
            "foo.qif",
            "jpy-travel-sample.qif",
            "statement_136577258_JPY_2026-04-01.qif",
            "statement_136577258_2026-04-01_2026-06-30.qif",
            "statement_136577258_JAPAN_2026-04-01_2026-06-30.qif",
            "statement_JPY_2026-04-01_2026-06-30.qif",
            "wise_136577258_JPY_2026-04-01_2026-06-30.qif",
            "statement_136577258_JPY_2026-04-01_2026-06-30",
            "statement_136577258_JPY_01-04-2026_30-06-2026.qif",
        ],
    )
    def test_anything_but_the_wise_shape_is_none(self, name: str) -> None:
        """Unknown is the honest answer — callers must not block on it."""
        assert parse_wise_filename(name) is None

    def test_a_well_shaped_but_impossible_date_is_not_a_wise_name(self) -> None:
        assert parse_wise_filename("statement_1_JPY_2026-13-45_2026-06-30.qif") is None

    def test_a_prefixed_name_does_not_match(self) -> None:
        """Anchored at both ends, so a name merely containing the shape is unknown."""
        assert parse_wise_filename(f"copy of {WISE_QIF_NAME}") is None


class TestTheAccountIdIsDiscarded:
    def test_the_wallet_id_is_on_no_field_of_the_result(self) -> None:
        """``<account_id>`` identifies the user's wallet — it must not be carried."""
        meta = parse_wise_filename(WISE_QIF_NAME)
        assert meta is not None
        assert "136577258" not in repr(meta)

    def test_the_result_holds_currency_and_period_only(self) -> None:
        assert WiseFilenameMetadata.__dataclass_fields__.keys() == {
            "currency",
            "date_from",
            "date_to",
        }
