#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reset a Kaleta demo family to a known login + seeded dataset.

Typical use: nightly cron on a demo instance.

Requires ``KALETA_DEMO=true`` (or ``--force`` for local dry-runs).

The demo is one family among the others, owned by ``--email``. The script
signs that identity in and provisions its family if it is missing. With
``KALETA_AUTH_BACKEND=local`` it creates the login (or puts its password back)
first; with Supabase the identity must exist and be confirmed (add it once,
"auto confirm", in the Supabase dashboard); the debug ``fake`` backend signs
it up on the first run.

The demo's data passphrase is the published ``DEFAULT_DEMO_PASSPHRASE`` (see
``docs/deployment.md``): the first reset sets it up, every later one unlocks
with it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kaleta.auth.providers import AuthProvider, Identity, get_auth_provider
from kaleta.config import settings as active_settings
from kaleta.config.settings import Settings
from kaleta.crypto import DataKey
from kaleta.db import AsyncSessionFactory, configure_database
from kaleta.db.tenant_context import use_tenant
from kaleta.db.types import use_data_key
from kaleta.exceptions import UnauthorizedError
from kaleta.services.data_service import DataService
from kaleta.services.key_service import KeyService, KeyStore, TenantKeyStore
from kaleta.services.local_identity_service import LocalIdentityService
from kaleta.services.tenant_service import TenantService

DEFAULT_DEMO_PASSWORD = "demo-kaleta"
#: Published with the login — the demo is public; see the module docstring.
DEFAULT_DEMO_PASSPHRASE = "demo-kaleta-data"
#: The demo family's owner.
DEFAULT_DEMO_EMAIL = "demo@kaleta.app"


async def _open_or_set_up(service: KeyService, passphrase: str) -> DataKey | None:
    """The demo's data key: set up on the first reset, opened on every later one."""
    if await service.status() == "setup_required":
        setup = await service.setup(None, passphrase)
        print("[OK] Demo data passphrase set up.")
        return setup.data_key
    data_key, _private_key = await service.open(passphrase)
    return data_key


async def _ensure_local_login(email: str, password: str) -> None:
    """A local demo login with this password: created, or its password put back."""
    async with AsyncSessionFactory.public() as public:
        identities = LocalIdentityService(public)
        row = await identities.get_by_email(email)
        if row is None:
            await identities.create(email, password)
            print(f"[OK] Demo login {email!r} created.")
        else:
            await identities.set_password(row.id, password)


async def _demo_identity(provider: AuthProvider, email: str, password: str) -> Identity:
    """Sign the demo owner in; the debug backend signs it up the first time."""
    if provider.name == "local":
        await _ensure_local_login(email, password)
    try:
        result = await provider.sign_in(email, password)
    except UnauthorizedError:
        if provider.name != "fake":
            raise
        signed_up = await provider.sign_up(email, password)
        if signed_up.identity is None:
            raise
        print(f"[OK] Demo identity {email!r} signed up.")
        return signed_up.identity
    if not isinstance(result, Identity):
        msg = "The demo identity has a second factor; remove it."
        raise UnauthorizedError(msg)
    return result


async def reset_demo_tenant(
    *,
    email: str,
    password: str,
    seed: bool = True,
    passphrase: str = DEFAULT_DEMO_PASSPHRASE,
) -> None:
    """The demo: one family like any other, provisioned on first run."""
    identity = await _demo_identity(get_auth_provider(), email, password)
    async with AsyncSessionFactory.public() as public:
        membership = await TenantService(public).membership_for_sign_in(identity)
    ctx = membership.context()
    if ctx.member_user_id is None:
        msg = "The demo account has no owner row."
        raise UnauthorizedError(msg)
    with use_tenant(ctx):
        async with AsyncSessionFactory() as data, AsyncSessionFactory.public() as public:
            store: KeyStore = TenantKeyStore(public, ctx.tenant_id, ctx.member_user_id)
            data_key = (
                await _open_or_set_up(KeyService(store, data), passphrase)
                if active_settings.encryption_enabled
                else None
            )
        if not seed:
            print(f"[OK] Demo account {ctx.tenant_id} ready; data left as it is.")
            return
        with use_data_key(data_key):
            async with AsyncSessionFactory() as data:
                counts = await DataService(data).seed()
    print(
        f"[OK] Demo reset for account {ctx.tenant_id} ({email}): "
        f"{counts.get('accounts', 0)} accounts, "
        f"{counts.get('transactions', 0)} transactions."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset Kaleta demo data to the seed snapshot.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even when KALETA_DEMO is not true (local dev only).",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help=(
            "Only make sure the demo login exists; leave whatever data is already "
            "there. Used by scripts/restyle_fidelity.py, which has already run "
            "scripts/seed.py and must not have its ledger wiped again."
        ),
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_DEMO_PASSWORD,
        help=f"Demo login password (default: {DEFAULT_DEMO_PASSWORD!r}).",
    )
    parser.add_argument(
        "--data-passphrase",
        default=DEFAULT_DEMO_PASSPHRASE,
        help=(f"Demo data passphrase (default: {DEFAULT_DEMO_PASSPHRASE!r})."),
    )
    parser.add_argument(
        "--tenant",
        metavar="NAME",
        help="Accepted for older cron lines and ignored: the family is the one --email owns.",
    )
    parser.add_argument(
        "--email",
        default=DEFAULT_DEMO_EMAIL,
        help=f"The demo owner's e-mail address (default: {DEFAULT_DEMO_EMAIL!r}).",
    )
    args = parser.parse_args()

    settings = Settings()
    if not settings.demo and not args.force:
        print(
            "Refusing to reset: set KALETA_DEMO=true or pass --force.",
            file=sys.stderr,
        )
        return 1
    configure_database(settings.db_url, debug=settings.debug)
    job = reset_demo_tenant(
        email=args.email,
        password=args.password,
        seed=not args.no_seed,
        passphrase=args.data_passphrase,
    )

    try:
        asyncio.run(job)
    except Exception as exc:
        print(f"[ERROR] Demo reset failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
