# SPDX-License-Identifier: AGPL-3.0-or-later
"""The reservoir component: its arithmetic, its SVG and its motion budget.

Covers: KAL-RSV-002, KAL-RSV-003, KAL-RSV-004 — the pure half of each: a fund
at its target is drawn full, an overfunded one in the overflow state, and a
fund with no target or no backing account degrades to the empty state without
dividing by zero. The e2e tests in ``tests/e2e/test_reserve_funds.py`` check
the same states on the page.
"""

from __future__ import annotations

import re
from decimal import Decimal

from kaleta.views import theme
from kaleta.views.components.reservoir import (
    MIN_WIDTH_RATIO,
    Reservoir,
    ReservoirLevel,
    ReservoirState,
    width_ratio,
)


class TestReservoirLevel:
    def test_half_full(self) -> None:
        level = ReservoirLevel.of(Decimal("1500.00"), Decimal("3000.00"))
        assert level == ReservoirLevel(ReservoirState.PARTIAL, 50, Decimal("0.50"))

    def test_at_target_is_full(self) -> None:
        """Covers: KAL-RSV-002"""
        level = ReservoirLevel.of(Decimal("3000.00"), Decimal("3000.00"))
        assert level.state is ReservoirState.FULL
        assert level.percent == 100
        assert level.fill == Decimal("1")

    def test_over_target_overflows_but_draws_no_higher_than_full(self) -> None:
        """Covers: KAL-RSV-003"""
        level = ReservoirLevel.of(Decimal("3900.00"), Decimal("3000.00"))
        assert level.state is ReservoirState.OVERFLOW
        assert level.percent == 130
        assert level.fill == Decimal("1")

    def test_nothing_saved_is_empty(self) -> None:
        level = ReservoirLevel.of(Decimal("0.00"), Decimal("3000.00"))
        assert level == ReservoirLevel(ReservoirState.EMPTY, 0, Decimal("0"))

    def test_a_negative_balance_draws_nothing_but_keeps_its_percent(self) -> None:
        # The bar layout prints the same negative percentage.
        level = ReservoirLevel.of(Decimal("-300.00"), Decimal("3000.00"))
        assert level.state is ReservoirState.EMPTY
        assert level.percent == -10
        assert level.fill == Decimal("0")

    def test_zero_target_degrades_instead_of_dividing_by_zero(self) -> None:
        """Covers: KAL-RSV-004"""
        level = ReservoirLevel.of(Decimal("500.00"), Decimal("0"))
        assert level == ReservoirLevel(ReservoirState.UNAVAILABLE, 0, Decimal("0"))

    def test_no_backing_account_degrades(self) -> None:
        """Covers: KAL-RSV-004"""
        level = ReservoirLevel.of(Decimal("0.00"), Decimal("3000.00"), available=False)
        assert level.state is ReservoirState.UNAVAILABLE

    def test_percent_rounds_like_the_bar_label(self) -> None:
        # Service: (balance / target).quantize(0.01); bar: round(pct * 100).
        level = ReservoirLevel.of(Decimal("1234.56"), Decimal("4000.00"))
        assert level.percent == 31
        assert level.fill == Decimal("0.31")


class TestWidthRatio:
    def test_the_largest_target_is_full_width(self) -> None:
        assert width_ratio(Decimal("15600"), Decimal("15600")) == Decimal("1")

    def test_width_is_linear_in_the_target(self) -> None:
        assert width_ratio(Decimal("7800"), Decimal("15600")) == Decimal("0.5")

    def test_a_small_fund_is_floored_so_it_stays_legible(self) -> None:
        assert width_ratio(Decimal("300"), Decimal("15600")) == MIN_WIDTH_RATIO

    def test_a_zero_target_gets_the_floor(self) -> None:
        assert width_ratio(Decimal("0"), Decimal("15600")) == MIN_WIDTH_RATIO

    def test_no_positive_target_anywhere_means_full_width(self) -> None:
        assert width_ratio(Decimal("0"), Decimal("0")) == Decimal("1")


class TestReservoirSvg:
    def _svg(self, current: str, target: str) -> str:
        return Reservoir("Poduszka", Decimal(current), Decimal(target), "PLN").svg()

    def test_numbers_stay_in_the_dom(self) -> None:
        svg = self._svg("1500.00", "3000.00")
        assert 'role="img"' in svg
        assert 'aria-label="Poduszka: 1,500.00 of 3,000.00 PLN, 50%"' in svg
        assert "<title>Poduszka: 1,500.00 of 3,000.00 PLN, 50%</title>" in svg
        assert ">50%</text>" in svg

    def test_water_height_is_proportional(self) -> None:
        svg = self._svg("1500.00", "3000.00")
        water = re.search(r'class="k-reservoir__water"[^>]*height="([\d.]+)"', svg)
        assert water is not None
        # Inner basin: 132 − 4 − 18 = 110 px; half of it is water.
        assert float(water.group(1)) == 55.0

    def test_full_reservoir_state(self) -> None:
        """Covers: KAL-RSV-002"""
        svg = self._svg("3000.00", "3000.00")
        assert 'data-state="full"' in svg
        assert 'data-fill="1"' in svg
        assert "k-reservoir__spill" not in svg

    def test_overflow_draws_the_spill(self) -> None:
        """Covers: KAL-RSV-003"""
        svg = self._svg("3900.00", "3000.00")
        assert 'data-state="overflow"' in svg
        assert "k-reservoir__spill" in svg
        assert ">130% — over target</text>" in svg

    def test_unavailable_draws_no_water(self) -> None:
        """Covers: KAL-RSV-004"""
        svg = self._svg("0.00", "0.00")
        assert 'data-state="unavailable"' in svg
        assert "k-reservoir__water" not in svg
        assert "k-reservoir__wave" not in svg
        assert ">—</text>" in svg

    def test_unavailable_explains_itself_outside_the_basin(self) -> None:
        """Covers: KAL-RSV-004"""
        degraded = Reservoir("x", Decimal("0"), Decimal("0"), "PLN")
        assert degraded.unavailable_note() == "No target or backing account"
        assert Reservoir("y", Decimal("1"), Decimal("2"), "PLN").unavailable_note() is None

    def test_user_text_is_escaped(self) -> None:
        svg = Reservoir('<b>"x"</b>', Decimal("1"), Decimal("2"), "PLN").svg()
        assert "<b>" not in svg
        assert "&lt;b&gt;" in svg

    def test_clip_ids_are_unique_per_reservoir(self) -> None:
        ids = {tuple(re.findall(r'clipPath id="([^"]+)"', self._svg("1", "2"))) for _ in range(3)}
        assert len(ids) == 3

    def test_width_follows_the_ratio(self) -> None:
        wide = Reservoir("a", Decimal("1"), Decimal("2"), "PLN", width=Decimal("1"))
        narrow = Reservoir("b", Decimal("1"), Decimal("2"), "PLN", width=Decimal("0.5"))
        assert wide.pixel_width() == 520
        assert narrow.pixel_width() == 260


class TestMotionBudget:
    """The wave must hold still under reduced motion and in a hidden tab."""

    def test_reduced_motion_stops_the_wave(self) -> None:
        assert (
            "@media (prefers-reduced-motion: reduce){.k-reservoir__wave{animation:none}}"
            in theme.BASE_CSS
        )

    def test_hidden_tab_pauses_the_wave(self) -> None:
        assert ".k-tab-hidden .k-reservoir__wave{animation-play-state:paused}" in theme.BASE_CSS

    def test_reservoir_tokens_exist_in_both_modes(self) -> None:
        root = theme.BASE_CSS[theme.BASE_CSS.index(":root{") :]
        dark = theme.BASE_CSS[theme.BASE_CSS.index(".body--dark{") :]
        for token in ("--k-reservoir-water", "--k-reservoir-wave", "--k-reservoir-basin"):
            assert f"{token}:" in root[: root.index("}")], token
            assert f"{token}:" in dark[: dark.index("}")], token
