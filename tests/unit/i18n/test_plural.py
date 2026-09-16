# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plural forms: the widest rule the app's languages need.

English has two forms and Polish three, so ``plural_key`` follows the Polish
rule and a two-form language simply gives ``few`` and ``many`` the same
wording. Keys are ``<prefix>_one`` / ``_few`` / ``_many``.
"""

from __future__ import annotations

import json
import pathlib

import kaleta.i18n
from kaleta.i18n import plural_key


class TestPluralKey:
    def test_one_is_the_only_singular(self) -> None:
        assert plural_key("import.rows_count", 1) == "import.rows_count_one"

    def test_counts_ending_in_two_to_four_take_the_few_form(self) -> None:
        # "3 wierszy" is wrong Polish; few is what 2-4 take.
        forms = [plural_key("x", n) for n in (2, 3, 4, 22, 104, 1_002)]
        assert forms == ["x_few"] * 6

    def test_the_teens_are_many_even_though_they_end_in_two_to_four(self) -> None:
        forms = [plural_key("x", n) for n in (12, 13, 14, 112, 1_013)]
        assert forms == ["x_many"] * 5

    def test_zero_and_the_rest_are_many(self) -> None:
        forms = [plural_key("x", n) for n in (0, 5, 11, 25, 100)]
        assert forms == ["x_many"] * 5

    def test_the_prefix_is_carried_through_untouched(self) -> None:
        assert plural_key("a.b.c", 7) == "a.b.c_many"


class TestEveryLocaleCarriesEveryForm:
    """A key with only one form is the bug the helper exists to prevent."""

    def test_the_row_count_caption_has_all_three_in_both_locales(self) -> None:
        locales = pathlib.Path(kaleta.i18n.__file__).parent / "locales"
        for lang in ("en", "pl"):
            data = json.loads((locales / f"{lang}.json").read_text(encoding="utf-8"))
            forms = data["import"]
            for suffix in ("one", "few", "many"):
                assert f"rows_count_{suffix}" in forms, (lang, suffix)

    def test_polish_really_declines_the_noun(self) -> None:
        locales = pathlib.Path(kaleta.i18n.__file__).parent / "locales"
        pl = json.loads((locales / "pl.json").read_text(encoding="utf-8"))["import"]
        assert pl["rows_count_one"] == "{count} wiersz"
        assert pl["rows_count_few"] == "{count} wiersze"
        assert pl["rows_count_many"] == "{count} wierszy"
