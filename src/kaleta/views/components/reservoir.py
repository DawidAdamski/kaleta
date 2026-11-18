# SPDX-License-Identifier: AGPL-3.0-or-later
"""A reserve fund drawn as a reservoir: water standing at the fund's level.

The reservoir is an inline SVG — the ECharts build NiceGUI bundles has no
``liquidFill`` series, and SVG themes from the ``--k-reservoir-*`` CSS
variables, so dark mode needs no second code path. The shape encodes the
percentage; the *width* encodes the target amount relative to the largest
target on the page, so two equally full funds of very different size do not
read as the same thing.

Every number stays in the DOM as text: the SVG carries an ``aria-label`` and a
``<title>``, and the percentage is SVG ``<text>``, not a picture of one.
"""

from __future__ import annotations

import enum
import itertools
from dataclasses import dataclass
from decimal import Decimal
from html import escape

from nicegui import ui

from kaleta.i18n import t

#: The narrowest reservoir, as a share of the widest one. Below this a small
#: fund's percentage label no longer fits inside it.
MIN_WIDTH_RATIO = Decimal("0.35")

#: Pixel geometry of the SVG. Height is fixed; width scales with the target.
_HEIGHT = 132
_MAX_WIDTH = 520
_RIM_TOP = 18  # headroom above the rim for the overflow spill
_PAD = 4
_WAVE_AMPLITUDE = 4

_ids = itertools.count(1)


class ReservoirState(enum.StrEnum):
    """What the reservoir shows. ``UNAVAILABLE`` is the degraded empty state."""

    UNAVAILABLE = "unavailable"
    EMPTY = "empty"
    PARTIAL = "partial"
    FULL = "full"
    OVERFLOW = "overflow"


@dataclass(frozen=True)
class ReservoirLevel:
    """How full a reservoir is — the pure arithmetic behind the picture.

    ``percent`` is rounded exactly as the bar layout rounds its label (the
    service quantizes the fraction to 0.01, the view rounds ×100), so the two
    layouts never disagree about the same fund. ``fill`` is the drawn height,
    clamped to 0…1.
    """

    state: ReservoirState
    percent: int
    fill: Decimal

    @classmethod
    def of(cls, current: Decimal, target: Decimal, *, available: bool = True) -> ReservoirLevel:
        """Level for ``current`` against ``target``.

        A target of zero (or less) or a fund with no backing account has no
        meaningful level: it degrades to ``UNAVAILABLE`` with nothing drawn,
        never a division by zero.
        """
        if not available or target <= 0:
            return cls(ReservoirState.UNAVAILABLE, 0, Decimal("0"))
        fraction = (current / target).quantize(Decimal("0.01"))
        percent = round(float(fraction) * 100)
        if fraction <= 0:
            return cls(ReservoirState.EMPTY, percent, Decimal("0"))
        if fraction > 1:
            return cls(ReservoirState.OVERFLOW, percent, Decimal("1"))
        if fraction == 1:
            return cls(ReservoirState.FULL, percent, Decimal("1"))
        return cls(ReservoirState.PARTIAL, percent, fraction)


def width_ratio(target: Decimal, largest_target: Decimal) -> Decimal:
    """A reservoir's width as a share of the widest one on the page.

    Linear in the target, floored at :data:`MIN_WIDTH_RATIO` so the smallest
    fund stays legible. With no positive target anywhere every reservoir is
    full width.
    """
    if largest_target <= 0 or target >= largest_target:
        return Decimal("1")
    if target <= 0:
        return MIN_WIDTH_RATIO
    return max(MIN_WIDTH_RATIO, target / largest_target)


class Reservoir:
    """Render one fund as a reservoir.

    Built from the four figures the plan names — label, current, target,
    currency — plus the width share and whether the fund has a source of
    water at all.
    """

    def __init__(
        self,
        label: str,
        current: Decimal,
        target: Decimal,
        currency: str,
        *,
        width: Decimal = Decimal("1"),
        available: bool = True,
    ) -> None:
        self.label = label
        self.current = current
        self.target = target
        self.currency = currency
        self.width = min(max(width, MIN_WIDTH_RATIO), Decimal("1"))
        self.level = ReservoirLevel.of(current, target, available=available)
        self._uid = next(_ids)

    # ── text ────────────────────────────────────────────────────────────
    def aria_label(self) -> str:
        if self.level.state == ReservoirState.UNAVAILABLE:
            return t("safety_funds.reservoir_aria_unavailable", name=self.label)
        return t(
            "safety_funds.reservoir_aria",
            name=self.label,
            current=f"{self.current:,.2f}",
            target=f"{self.target:,.2f}",
            currency=self.currency,
            percent=self.level.percent,
        )

    def caption(self) -> str:
        """The figure drawn inside the basin.

        The degraded state draws a dash: its explanation is longer than the
        narrowest basin is wide, so it is a caption under the SVG instead
        (:meth:`unavailable_note`).
        """
        if self.level.state == ReservoirState.UNAVAILABLE:
            return "—"
        if self.level.state == ReservoirState.OVERFLOW:
            return t("safety_funds.reservoir_overflow", percent=self.level.percent)
        return f"{self.level.percent}%"

    def unavailable_note(self) -> str | None:
        """Why there is no level to draw, or ``None`` when there is one."""
        if self.level.state == ReservoirState.UNAVAILABLE:
            return t("safety_funds.reservoir_unavailable")
        return None

    # ── geometry ────────────────────────────────────────────────────────
    def pixel_width(self) -> int:
        return int((Decimal(_MAX_WIDTH) * self.width).to_integral_value())

    def svg(self) -> str:
        """The reservoir as an SVG string. Pure: no NiceGUI calls."""
        w = self.pixel_width()
        h = _HEIGHT
        inner_left, inner_right = _PAD, w - _PAD
        inner_top, inner_bottom = _RIM_TOP, h - _PAD
        inner_h = inner_bottom - inner_top
        state = self.level.state
        clip_id = f"k-res-clip-{self._uid}"
        water_y = inner_top + float(Decimal(inner_h) * (1 - self.level.fill))

        span = inner_right - inner_left
        box = f'x="{inner_left}" y="{inner_top}" width="{span}" height="{inner_h}" rx="10"'
        aria = escape(self.aria_label())
        data = (
            f'data-state="{state.value}" data-percent="{self.level.percent}" '
            f'data-fill="{self.level.fill}"'
        )

        opening = (
            f'<svg class="k-reservoir k-reservoir--{state.value}" role="img" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}" {data} '
            f'aria-label="{aria}" xmlns="http://www.w3.org/2000/svg">'
        )
        parts: list[str] = [
            opening,
            f"<title>{aria}</title>",
            f'<defs><clipPath id="{clip_id}"><rect {box}/></clipPath></defs>',
            f'<rect class="k-reservoir__basin" {box}/>',
        ]
        if self.level.fill > 0:
            water_h = inner_bottom - water_y
            wave_y = water_y - _WAVE_AMPLITUDE
            parts.append(f'<g clip-path="url(#{clip_id})">')
            parts.append(
                f'<rect class="k-reservoir__water" x="{inner_left}" y="{water_y:.2f}" '
                f'width="{span}" height="{water_h:.2f}"/>'
            )
            # The wave rides the water line; its path is two periods wide and
            # the CSS animation slides it by one, so the loop is seamless.
            parts.append(
                f'<g transform="translate({inner_left} {wave_y:.2f})">'
                f'<path class="k-reservoir__wave" d="{self._wave_path(span)}"/></g>'
            )
            parts.append("</g>")
        parts.append(f'<rect class="k-reservoir__rim" {box}/>')
        if state == ReservoirState.OVERFLOW:
            # Water spilling over both lips of the rim.
            left, right, lip = inner_left + 6, inner_right - 6, inner_top + 2
            parts.append(
                f'<path class="k-reservoir__spill" '
                f'd="M{left} {lip} q-4 -10 6 -14 M{right} {lip} q4 -10 -6 -14"/>'
            )
        label_y = inner_top + inner_h / 2 + 6
        parts.append(
            f'<text class="k-reservoir__label" x="{w / 2:.1f}" y="{label_y:.1f}" '
            f'text-anchor="middle">{escape(self.caption())}</text>'
        )
        parts.append("</svg>")
        return "".join(parts)

    @staticmethod
    def _wave_path(span: int) -> str:
        """A sine-like band two ``span`` periods wide, filled down to its base."""
        half = span / 2
        a = _WAVE_AMPLITUDE
        d = f"M0 {a}"
        for i in range(4):
            dy = -a if i % 2 == 0 else a
            d += f" q{half / 2:.2f} {dy * 2} {half:.2f} 0"
        d += f" V{a * 4} H0 Z"
        return d

    # ── NiceGUI ─────────────────────────────────────────────────────────
    def render(self) -> None:
        """Place the reservoir in the current NiceGUI container."""
        with ui.column().classes("k-reservoir-host gap-1 mt-3"):
            # Every interpolated string in ``svg()`` is escaped, and the SVG
            # must survive intact — the sanitizer would strip it.
            ui.html(self.svg(), sanitize=False)
            note = self.unavailable_note()
            if note is not None:
                ui.label(note).classes("k-reservoir__note text-xs")


#: Pauses every wave while the tab is hidden: a finance app that animates in a
#: background tab is spending the battery on nothing.
RESERVOIR_VISIBILITY_JS = """
<script>
document.addEventListener('visibilitychange', function () {
  document.documentElement.classList.toggle('k-tab-hidden', document.hidden);
});
</script>
"""
