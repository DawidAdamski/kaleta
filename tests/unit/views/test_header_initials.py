# SPDX-License-Identifier: AGPL-3.0-or-later
"""The header avatar's two letters (artboards 1c / 1d / 2a)."""

from __future__ import annotations

import pytest

from kaleta.views.layout import _initials


@pytest.mark.parametrize(
    ("username", "expected"),
    [
        # One word: its first two letters, which is what "demo" has to offer.
        ("demo", "DE"),
        ("d", "D"),
        # Two word-ish parts: one letter from each, however they are joined.
        ("dawid.adamski", "DA"),
        ("dawid_adamski", "DA"),
        ("dawid-adamski", "DA"),
        ("dawid adamski", "DA"),
        # Three: the first two, because the disc is 28px wide.
        ("a.b.c", "AB"),
        ("DAWID", "DA"),
        ("user42", "US"),
    ],
)
def test_initials_read_the_account_name(username: str, expected: str) -> None:
    assert _initials(username) == expected


@pytest.mark.parametrize("username", ["", "   ", "...", "@@@"])
def test_a_name_with_no_letters_falls_back_to_the_app(username: str) -> None:
    """An empty disc says less than the app's own letter does."""
    assert _initials(username) == "K"
