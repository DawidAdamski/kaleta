# SPDX-License-Identifier: AGPL-3.0-or-later
"""The sign-in pages only ever follow a path on this origin."""

from __future__ import annotations

import pytest

from kaleta.views.auth_common import safe_redirect
from kaleta.views.login_mfa import _back_to_login


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


def test_a_bail_out_keeps_the_reason_and_the_destination() -> None:
    """Someone deep-linked to /transactions should land there once they have
    signed in again, not on the dashboard."""
    assert _back_to_login("mfa_gone", "/") == "/login?reason=mfa_gone"
    assert (
        _back_to_login("mfa_expired", "/transactions")
        == "/login?reason=mfa_expired&redirect_to=/transactions"
    )
    assert "%3F" in _back_to_login("mfa_gone", "/a?b=c")
    # The same builder serves the page-load bail-out, so an expired reload
    # keeps both halves too.
    assert _back_to_login("mfa_expired", safe_redirect("//evil.com")) == "/login?reason=mfa_expired"
