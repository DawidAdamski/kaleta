# SPDX-License-Identifier: AGPL-3.0-or-later
"""The sign-in flow only ever follows a path on this origin."""

from __future__ import annotations

import pytest

from kaleta.auth.redirects import safe_redirect


@pytest.mark.parametrize(
    "given",
    ["/transactions", "/settings?tab=security", "/", "/a/b/c"],
)
def test_a_path_on_this_origin_is_followed(given: str) -> None:
    assert safe_redirect(given) == given


@pytest.mark.parametrize(
    "given",
    [
        "//evil.com",
        # A browser normalises the backslash to a slash, so this is the same
        # protocol-relative URL as the line above wearing a different hat.
        "/\\evil.com",
        "https://evil.com",
        "http://evil.com",
        "evil.com",
        "",
        "\\\\evil.com",
        # The WHATWG parser drops tab, LF and CR before anything else reads
        # the URL, so `/%09/evil.com` reaches the browser as `//evil.com`.
        "/\t/evil.com",
        "/\n/evil.com",
        "/\r/evil.com",
        "/\t\\evil.com",
    ],
)
def test_anything_that_can_leave_this_origin_is_not(given: str) -> None:
    assert safe_redirect(given) == "/"


def test_a_stripped_character_inside_a_real_path_does_not_survive_it() -> None:
    """What is followed is what the browser would see, not what arrived."""
    assert safe_redirect("/trans\tactions") == "/transactions"
