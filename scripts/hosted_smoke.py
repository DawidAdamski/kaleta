#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Smoke-test a hosted Kaleta end to end — run after every deploy.

    uv run python scripts/hosted_smoke.py https://kaleta.example.com

One throwaway identity walks the whole hosted path: sign-up, sign-in, choosing
the data passphrase (unlock), minting an API token, ``POST`` one transaction
and ``GET`` it back (its description round-trips through field encryption),
then "Delete my account" from Settings, after which the old password must be
refused. Usually started through ``scripts/hosted_smoke.sh``, which brings the
``compose.hosted-dev.yml`` stack up first when no URL is given.

How the identity is made depends on the instance's ``auth_backend`` (read from
``/api/v1/health``):

- ``fake`` (``compose.hosted-dev.yml``): signs up through the page; the debug
  backend confirms every address at once.
- ``supabase``: created already confirmed through GoTrue's admin API, so no
  mailbox is needed — set ``KALETA_SUPABASE_URL`` and
  ``KALETA_SUPABASE_SERVICE_ROLE_KEY`` in the environment of this script.

Needs the dev dependencies and a Playwright Chromium (``uv sync --group dev``,
``uv run playwright install chromium``). Exit status 0 when every step passed;
1 with the failing step named otherwise. A run that fails after sign-up says
which address it left behind (``kaleta-admin delete`` removes it).
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import secrets
import sys
from collections.abc import Callable
from typing import Any

import httpx
from playwright.sync_api import Page, expect, sync_playwright

_TIMEOUT_MS = 30_000
_ON_UNLOCK = re.compile(r"/unlock")
_ON_LOGIN = re.compile(r"/login(\?|$)")


class SmokeError(Exception):
    """A step did not do what it should; the message names the step."""


class HostedSmoke:
    def __init__(self, base_url: str, *, email_domain: str, headed: bool = False) -> None:
        self.base = base_url.rstrip("/")
        tag = secrets.token_hex(4)
        self.email = f"kaleta-smoke-{tag}@{email_domain}"
        self.password = f"smoke-pw-{secrets.token_urlsafe(12)}"
        self.passphrase = f"smoke passphrase {secrets.token_urlsafe(12)}"
        self.headed = headed
        self.signed_up = False
        self.deleted = False
        self._step = "start"

    # ── Run ──────────────────────────────────────────────────────────────────

    def run(self) -> None:
        backend = self._step_health()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not self.headed)
            try:
                page = browser.new_context().new_page()
                page.set_default_timeout(_TIMEOUT_MS)
                self._step_identity(page, backend)
                self._step_choose_passphrase(page)
                token = self._step_api_token(page)
                self._step_transaction_round_trip(token)
                self._step_delete_account(page)
                self._step_old_password_refused(page)
            finally:
                browser.close()

    def _do[T](self, name: str, fn: Callable[[], T]) -> T:
        self._step = name
        print(f"hosted_smoke: {name} …", flush=True)
        try:
            return fn()
        except SmokeError:
            raise
        except Exception as exc:
            raise SmokeError(f"{name}: {exc}") from exc

    # ── Steps ────────────────────────────────────────────────────────────────

    def _step_health(self) -> str:
        def _check() -> str:
            body = httpx.get(f"{self.base}/api/v1/health", timeout=15).json()
            if body.get("status") != "ok":
                raise SmokeError(f"health: not a healthy instance: {body}")
            if body.get("migrations_pending"):
                raise SmokeError(f"health: migrations pending: {body}")
            return str(body.get("auth_backend"))

        return self._do("health", _check)

    def _step_identity(self, page: Page, backend: str) -> None:
        if backend == "fake":
            self._do("sign up", lambda: self._sign_up_through_the_page(page))
        elif backend == "supabase":
            self._do("create confirmed identity", self._create_supabase_identity)
            self._do("log in", lambda: self._log_in(page))
        else:
            raise SmokeError(f"identity: unsupported auth_backend {backend!r}")

    def _sign_up_through_the_page(self, page: Page) -> None:
        page.goto(f"{self.base}/create-account")
        page.get_by_label("E-mail", exact=True).fill(self.email)
        page.get_by_label("Password", exact=True).fill(self.password)
        page.get_by_label("Confirm password", exact=True).fill(self.password)
        page.get_by_role("button", name="Sign up").click()
        self.signed_up = True
        expect(page).to_have_url(_ON_UNLOCK)

    def _create_supabase_identity(self) -> None:
        url = os.environ.get("KALETA_SUPABASE_URL")
        key = os.environ.get("KALETA_SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise SmokeError(
                "create confirmed identity: set KALETA_SUPABASE_URL and "
                "KALETA_SUPABASE_SERVICE_ROLE_KEY for a Supabase-backed instance"
            )
        response = httpx.post(
            f"{url.rstrip('/')}/auth/v1/admin/users",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            json={"email": self.email, "password": self.password, "email_confirm": True},
            timeout=15,
        )
        if response.status_code >= 400:
            raise SmokeError(f"create confirmed identity: GoTrue answered {response.status_code}")
        self.signed_up = True

    def _log_in(self, page: Page) -> None:
        page.goto(f"{self.base}/login")
        page.get_by_label("E-mail", exact=True).fill(self.email)
        page.get_by_label("Password", exact=True).fill(self.password)
        page.get_by_role("button", name="Log in").click()
        expect(page).to_have_url(_ON_UNLOCK)

    def _step_choose_passphrase(self, page: Page) -> None:
        def _choose() -> None:
            page.get_by_label("New data passphrase", exact=True).fill(self.passphrase)
            page.get_by_label("Repeat the passphrase", exact=True).fill(self.passphrase)
            page.get_by_role("button", name="Set passphrase").click()
            expect(page.get_by_test_id("recovery-code")).to_be_visible()
            page.get_by_text("I have saved my recovery code").click()
            page.get_by_role("button", name="Continue").click()
            expect(page).not_to_have_url(_ON_UNLOCK)

        self._do("unlock (choose data passphrase)", _choose)

    def _step_api_token(self, page: Page) -> str:
        def _mint() -> str:
            page.goto(f"{self.base}/settings")
            page.get_by_role("tab", name="Security").click()
            page.get_by_label("Label", exact=True).fill("hosted smoke")
            page.get_by_role("button", name="Create token").click()
            field = page.get_by_label("Token", exact=True)
            expect(field).not_to_have_value("")
            token = field.input_value()
            page.keyboard.press("Escape")
            return token

        return self._do("mint API token", _mint)

    def _step_transaction_round_trip(self, token: str) -> None:
        description = f"hosted smoke {secrets.token_hex(3)}"

        def _round_trip() -> None:
            with httpx.Client(
                base_url=f"{self.base}/api/v1",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            ) as api:
                account = _created(
                    api.post(
                        "/accounts/",
                        json={
                            "name": "Smoke",
                            "type": "checking",
                            "balance": "0.00",
                            "currency": "PLN",
                        },
                    )
                )
                category = _created(
                    api.post("/categories/", json={"name": "Smoke", "type": "expense"})
                )
                created = _created(
                    api.post(
                        "/transactions/",
                        json={
                            "account_id": account["id"],
                            "category_id": category["id"],
                            "amount": "12.34",
                            "type": "expense",
                            "date": datetime.date.today().isoformat(),
                            "description": description,
                        },
                    )
                )
                fetched = api.get(f"/transactions/{created['id']}")
                if fetched.status_code != 200:
                    raise SmokeError(f"GET transaction: HTTP {fetched.status_code}")
                body = fetched.json()
                if body.get("description") != description or body.get("amount") != "12.34":
                    raise SmokeError(f"GET transaction: came back different: {body}")

        self._do("POST and GET one transaction", _round_trip)

    def _step_delete_account(self, page: Page) -> None:
        def _delete() -> None:
            page.goto(f"{self.base}/settings")
            page.get_by_role("tab", name="Data").click()
            page.get_by_role("button", name="Delete my account").click()
            expect(page.get_by_test_id("delete-account-members")).to_contain_text(self.email)
            page.get_by_role("button", name="Continue").click()
            page.get_by_label("Data passphrase", exact=True).fill(self.passphrase)
            page.get_by_role("button", name="Delete for good").click()
            expect(page).to_have_url(_ON_LOGIN)
            self.deleted = True

        self._do("delete the account", _delete)

    def _step_old_password_refused(self, page: Page) -> None:
        def _refused() -> None:
            page.get_by_label("E-mail", exact=True).fill(self.email)
            page.get_by_label("Password", exact=True).fill(self.password)
            page.get_by_role("button", name="Log in").click()
            expect(page.get_by_text("Invalid e-mail or password.")).to_be_visible()

        self._do("old password refused", _refused)


def _created(response: httpx.Response) -> dict[str, Any]:
    if response.status_code not in (200, 201):
        raise SmokeError(
            f"{response.request.method} {response.request.url.path}: "
            f"HTTP {response.status_code} {response.text[:200]}"
        )
    body: dict[str, Any] = response.json()
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("base_url", help="the instance, e.g. https://kaleta.example.com")
    parser.add_argument(
        "--email-domain",
        default=os.environ.get("KALETA_SMOKE_EMAIL_DOMAIN", "example.com"),
        help="domain of the throwaway address (default: example.com)",
    )
    parser.add_argument("--headed", action="store_true", help="show the browser")
    args = parser.parse_args()

    smoke = HostedSmoke(args.base_url, email_domain=args.email_domain, headed=args.headed)
    try:
        smoke.run()
    except SmokeError as exc:
        print(f"hosted_smoke: FAILED at {exc}", file=sys.stderr)
        if smoke.signed_up and not smoke.deleted:
            print(
                f"hosted_smoke: {smoke.email} was left behind; remove it with "
                "kaleta-admin delete <tenant id> --yes",
                file=sys.stderr,
            )
        return 1
    print(f"hosted_smoke: OK ({smoke.base})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
