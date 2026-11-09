# SPDX-License-Identifier: AGPL-3.0-or-later
"""The measured difference ``restyle_fidelity.py shoot`` writes into a report header.

Plan ``fidelity-independent-critic``: both screenshots at the artboard's width,
a 4x4 grid, mean absolute difference per tile and for the whole screen.
Synthetic pictures, so every expected value is exact.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

#: The bottom-right sixteenth of a 400x400 picture.
D4 = (300, 300, 400, 400)


def test_identical_pictures_differ_by_nothing(
    fidelity: ModuleType, picture: Callable[..., Path]
) -> None:
    spec = picture("artboard.png", black=[(0, 0, 100, 100)])
    app = picture("app.png", black=[(0, 0, 100, 100)])

    measure = fidelity.TileDiff.measure(spec, app)

    assert measure.whole == 0.0
    assert set(measure.tiles.values()) == {0.0}
    assert measure.worst(3) == []


def test_a_difference_lands_in_its_own_tile_only(
    fidelity: ModuleType, picture: Callable[..., Path]
) -> None:
    spec = picture("artboard.png")
    app = picture("app.png", black=[D4])

    measure = fidelity.TileDiff.measure(spec, app)

    assert measure.tiles["D4"] == 100.0
    assert all(value == 0.0 for name, value in measure.tiles.items() if name != "D4")
    assert measure.whole == 6.25  # one tile of sixteen, fully inverted
    assert measure.worst(3) == ["D4"]


def test_tiles_are_named_row_letter_then_column_number(
    fidelity: ModuleType, picture: Callable[..., Path]
) -> None:
    spec = picture("artboard.png")
    app = picture("app.png", black=[(100, 0, 200, 100)])  # top row, second column

    measure = fidelity.TileDiff.measure(spec, app)

    assert fidelity.TILE_NAMES[:5] == ("A1", "A2", "A3", "A4", "B1")
    assert measure.tiles["A2"] == 100.0
    assert measure.header_tiles().split()[1] == "A2=100.00"
    assert len(measure.header_tiles().split()) == 16


def test_the_app_is_brought_to_the_artboard_width(
    fidelity: ModuleType, picture: Callable[..., Path]
) -> None:
    """An app shot twice as wide and twice as tall as the card is the same picture."""
    spec = picture("artboard.png", black=[D4])
    app = picture("app.png", size=(800, 800), black=[(600, 600, 800, 800)])

    measure = fidelity.TileDiff.measure(spec, app)

    assert measure.tiles["D4"] < 1.0
    assert measure.whole < 1.0


def test_rows_are_quarters_of_each_pictures_own_height(
    fidelity: ModuleType, picture: Callable[..., Path]
) -> None:
    """A full-page app shot taller than the card still lines its quarters up."""
    spec = picture("artboard.png", black=[D4])
    app = picture("app.png", size=(400, 1000), black=[(300, 750, 400, 1000)])

    measure = fidelity.TileDiff.measure(spec, app)

    assert max(measure.tiles.values()) < 1.0


def test_worst_ranks_by_value_then_name(fidelity: ModuleType) -> None:
    tiles = dict.fromkeys(fidelity.TILE_NAMES, 0.0) | {"C3": 9.0, "B2": 4.0, "A4": 4.0, "D1": 1.0}
    measure = fidelity.TileMeasure(whole=1.13, tiles=tiles)

    assert measure.worst(3) == ["C3", "A4", "B2"]
    assert measure.above(3.99) == ["A4", "B2", "C3"]
    assert measure.above(9.0) == []


def test_a_picture_too_small_to_grid_is_refused(
    fidelity: ModuleType, picture: Callable[..., Path]
) -> None:
    spec = picture("artboard.png", size=(3, 3))
    app = picture("app.png")

    with pytest.raises(fidelity.FidelityError, match="too small"):
        fidelity.TileDiff.measure(spec, app)
