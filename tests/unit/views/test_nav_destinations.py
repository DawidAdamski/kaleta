# SPDX-License-Identifier: AGPL-3.0-or-later
"""The navigation's one invariant: every page has a way in.

Since artboard `1e` the drawer is the phone's, and a wide window navigates
from the top bar and the palette. Both are built from ``NAV_SECTIONS``, so a
group that is in ``NAV_GROUPS`` and not in ``NAV_SECTIONS`` takes its pages
off the desktop entirely — silently, because nothing renders an error for a
group nobody asked about.
"""

from __future__ import annotations

from kaleta.views.layout import NAV_GROUPS, NAV_PINNED, NAV_SECTIONS, nav_destinations


def test_every_group_has_a_section_in_the_bar() -> None:
    assert {key for key, _items in NAV_GROUPS} == {key for key, _label in NAV_SECTIONS}


def test_the_bar_orders_the_groups_it_shows() -> None:
    """Same five, same order — the bar is the drawer's table of contents."""
    assert [key for key, _items in NAV_GROUPS] == [key for key, _label in NAV_SECTIONS]


def test_the_palette_holds_every_route_the_drawer_does() -> None:
    drawer_paths = [path for _icon, path, _key in NAV_PINNED]
    drawer_paths += [path for _key, items in NAV_GROUPS for _icon, path, _k in items]

    assert [path for _icon, path, _key in nav_destinations()] == drawer_paths


def test_no_route_is_listed_twice() -> None:
    """A palette that offers the same page twice has a filter bug, not a menu."""
    paths = [path for _icon, path, _key in nav_destinations()]

    assert len(paths) == len(set(paths))
