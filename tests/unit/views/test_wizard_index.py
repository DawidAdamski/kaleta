# SPDX-License-Identifier: AGPL-3.0-or-later
"""The order of the routines index (artboard 3d).

The page used to group these by topic across six cards, which scattered the
five working steps among eight that are not built yet — the index read as a
roadmap rather than as a list of things to do. Presentational; no BDD
scenario claims it.
"""

from __future__ import annotations

from kaleta.views.wizard import _STEP_ROUTES, _STEPS, WizardStep, ordered_steps


class TestOrderedSteps:
    def test_every_step_is_listed_exactly_once(self) -> None:
        # The index is the whole map of the wizard, not a filtered view of it.
        keys = [s.key for s in ordered_steps()]
        assert sorted(keys) == sorted(key for _icon, key, _section in _STEPS)
        assert len(keys) == len(set(keys))

    def test_the_ones_you_can_open_come_first(self) -> None:
        openable = [s.is_open for s in ordered_steps()]
        assert openable == sorted(openable, reverse=True)

    def test_section_order_survives_inside_each_half(self) -> None:
        # A reader who knows a step lives under "funds" still finds it beside
        # the other funds steps, within whichever half it landed in.
        declared = [key for _icon, key, _section in _STEPS]
        rows = ordered_steps()
        for half in ([s for s in rows if s.is_open], [s for s in rows if not s.is_open]):
            positions = [declared.index(s.key) for s in half]
            assert positions == sorted(positions)

    def test_a_step_carries_the_route_the_table_gives_it(self) -> None:
        by_key = {s.key: s for s in ordered_steps()}
        for key, route in _STEP_ROUTES.items():
            assert by_key[key].route == route
            assert by_key[key].is_open

    def test_a_step_with_no_page_behind_it_says_so(self) -> None:
        """The rule, not a census: ``is_open`` is exactly "has a route".

        This used to read the rule off the index's unrouted half. The
        what-if panel was the last routine without a page, so the half is
        empty and the rule is asserted on a step built by hand instead — it
        has to keep holding for the next routine added to ``_STEPS`` before
        its page exists.
        """
        unbuilt = WizardStep(icon="science", key="not_built_yet", section="budget", route=None)
        assert unbuilt.is_open is False
        assert WizardStep(
            icon="science", key="built", section="budget", route="/wizard/scenarios"
        ).is_open

    def test_every_routine_now_has_a_page(self) -> None:
        """The index stopped being a roadmap when the what-if panel landed."""
        assert [s.key for s in ordered_steps() if not s.is_open] == []
