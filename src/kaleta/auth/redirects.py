# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where a sign-in flow may send the browser once it is done.

Here rather than beside the sign-in pages: the session-rotation route is the
last hop of every login and lives in the auth layer, which may not import views.
"""

from __future__ import annotations

#: Removed from a URL by the WHATWG parser before anything else looks at it,
#: so a guard that inspects the raw string is not reading what the browser
#: will act on: ``/%09/evil.com`` arrives here as ``/\t/evil.com`` and leaves
#: the browser as ``//evil.com``.
_URL_STRIPPED = "\t\n\r"


def safe_redirect(path: str) -> str:
    """The ``redirect_to`` a sign-in page may follow, or ``/``.

    Only a path on this origin. ``//evil.com`` is a protocol-relative URL, and
    so are ``/\\evil.com`` (the browser normalises the backslash) and
    ``/\t/evil.com`` (it drops the tab) — an auth page that followed any of
    them would hand an attacker a link that shows Kaleta's sign-in form and
    lands somewhere else.

    The judging is done on the string the browser will see, not the one that
    arrived, which is why the strip comes first.
    """
    seen = path.translate(str.maketrans("", "", _URL_STRIPPED))
    if seen.startswith("/") and seen[1:2] not in ("/", "\\"):
        return seen
    return "/"
