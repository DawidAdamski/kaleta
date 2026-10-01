# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where a magic sign-in link lands: ``/auth/magic?token_hash=…`` (hosted only).

The Supabase "Magic Link" e-mail template points here (see
``docs/deployment.md``). The page has nothing to show: it verifies the link,
runs the same ``SignInFlow`` a password sign-in does — so the first sign-in of
a confirmed identity provisions its account — and redirects into the one
session-rotation hop every login goes through. A stale or reused link goes
back to the login page, which says so.
"""

from __future__ import annotations

from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.providers import get_auth_provider
from kaleta.auth.session import is_authenticated, park_login
from kaleta.auth.sign_in import SignInFlow
from kaleta.exceptions import EmailNotVerifiedError, KaletaError, ValidationError

MAGIC_LINK_PATH = "/auth/magic"


def register() -> None:
    @ui.page(MAGIC_LINK_PATH)
    async def magic_link_page(token_hash: str = "") -> RedirectResponse:
        provider = get_auth_provider()
        if provider.name != "supabase" or is_authenticated():
            return RedirectResponse("/")
        if not token_hash:
            return RedirectResponse("/login?reason=link_expired")
        try:
            identity = await provider.verify_magic_link(token_hash)
        except EmailNotVerifiedError:
            return RedirectResponse("/login")
        except ValidationError:
            # Only the link itself: a provisioning refusal below is not "expired".
            return RedirectResponse("/login?reason=link_expired")
        except KaletaError:
            return RedirectResponse("/login?reason=link_failed")
        try:
            signed_in = await SignInFlow().complete(identity)
        except KaletaError:
            # Unreachable provider, a closed account: the login page is where
            # a person can try again, and it never says which one it was.
            return RedirectResponse("/login?reason=link_failed")
        return RedirectResponse(
            park_login(
                user_id=signed_in.user_id,
                username=signed_in.username,
                target="/",
                tenant=signed_in.tenant,
            )
        )
