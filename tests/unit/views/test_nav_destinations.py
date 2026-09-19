# SPDX-License-Identifier: AGPL-3.0-or-later
"""The navigation's one invariant: every page has a way in.

The drawer is the navigation at every width again — docked above 767px,
an overlay behind the tab bar's "More" below it — and the ⌘K palette is
the second way to the same pages. Both are built from ``NAV_PINNED`` and
``NAV_GROUPS``, so a page that reaches neither list is a page with no way
in at all: nothing renders an error for a route nobody linked.
"""

from __future__ import annotations

from kaleta.views.layout import NAV_GROUPS, NAV_PINNED, nav_destinations


def test_the_palette_holds_every_route_the_drawer_does() -> None:
    drawer_paths = [path for _icon, path, _key in NAV_PINNED]
    drawer_paths += [path for _key, items in NAV_GROUPS for _icon, path, _k in items]

    assert [path for _icon, path, _key in nav_destinations()] == drawer_paths


def test_no_route_is_listed_twice() -> None:
    """A palette that offers the same page twice has a filter bug, not a menu."""
    paths = [path for _icon, path, _key in nav_destinations()]

    assert len(paths) == len(set(paths))
