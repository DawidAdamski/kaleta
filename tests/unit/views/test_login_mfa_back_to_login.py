# SPDX-License-Identifier: AGPL-3.0-or-later
"""The code prompt's way back to the sign-in page keeps where the user was going."""

from __future__ import annotations

from kaleta.auth.redirects import safe_redirect
from kaleta.views.login_mfa import _back_to_login


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
