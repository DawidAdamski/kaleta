# SPDX-License-Identifier: AGPL-3.0-or-later
"""The sign-in pages only ever follow a path on this origin."""

from __future__ import annotations

import pytest

from kaleta.views.auth_common import safe_redirect


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
    ],
)
def test_anything_that_can_leave_this_origin_is_not(given: str) -> None:
    assert safe_redirect(given) == "/"
