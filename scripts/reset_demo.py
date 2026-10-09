#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reset a Kaleta demo instance to a known user + seeded dataset.

Typical use: nightly cron on a hosted demo backed by Supabase Postgres.

Requires ``KALETA_DEMO=true`` (or ``--force`` for local dry-runs).

With ``KALETA_ENCRYPTION=passphrase`` the demo user's data passphrase is the
published ``DEFAULT_DEMO_PASSPHRASE`` (see ``docs/deployment.md``): the first
reset sets it up, every later one unlocks with it.

On a hosted instance (``KALETA_TENANCY=multi``) pass ``--tenant demo``: the
demo is then one account among the others, owned by ``--email``. The script
signs that identity in at the provider and provisions its account if it is
missing. With Supabase the identity must exist and be confirmed (add it once,
"auto confirm", in the Supabase dashboard); the debug ``fake`` backend signs it
up on the first run.
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
from kaleta.config.setup_config import save_db
from kaleta.crypto import DataKey
from kaleta.db import AsyncSessionFactory, configure_database
from kaleta.db.tenant_context import use_tenant
from kaleta.db.types import use_data_key
from kaleta.exceptions import UnauthorizedError
from kaleta.services import AuthService, with_session
from kaleta.services.data_service import DataService
from kaleta.services.key_service import KeyService, KeyStore, LocalKeyStore, TenantKeyStore
from kaleta.services.tenant_service import TenantService

DEFAULT_DEMO_USERNAME = "demo"
DEFAULT_DEMO_PASSWORD = "demo-kaleta"
#: Published with the login — the demo is public; see the module docstring.
DEFAULT_DEMO_PASSPHRASE = "demo-kaleta-data"
#: The hosted demo account's owner (``--tenant``).
DEFAULT_DEMO_EMAIL = "demo@kaleta.app"


async def _ensure_demo_user(password: str) -> tuple[int, str]:
    async def _run(session):
        auth = AuthService(session)
        state = await auth.auth_state()
        if state == "no_user":
            user = await auth.create_user(DEFAULT_DEMO_USERNAME, password)
        elif state == "placeholder":
            user = await auth.secure_placeholder(DEFAULT_DEMO_USERNAME, password)
        else:
            user = await auth.reset_password(password)
        return user.id, user.username

    return await with_session(_run)


async def _open_or_set_up(service: KeyService, passphrase: str) -> DataKey | None:
    """The demo's data key: set up on the first reset, opened on every later one."""
    if await service.status() == "setup_required":
        setup = await service.setup(None, passphrase)
        print("[OK] Demo data passphrase set up.")
        return setup.data_key
    data_key, _private_key = await service.open(passphrase)
    return data_key


async def _demo_data_key(user_id: int, passphrase: str) -> DataKey | None:
    if not active_settings.encryption_enabled:
        return None

    async def _run(session):
        return await _open_or_set_up(
            KeyService(LocalKeyStore(session, user_id), session), passphrase
        )

    return await with_session(_run)


async def _demo_identity(provider: AuthProvider, email: str, password: str) -> Identity:
    """Sign the demo owner in; the debug backend signs it up the first time."""
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
    """The hosted demo: one account like any other, provisioned on first run."""
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
            data_key = await _open_or_set_up(KeyService(store, data), passphrase)
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


async def _seed_demo_data() -> dict[str, int]:
    async def _run(session):
        return await DataService(session).seed()

    return await with_session(_run)


async def reset_demo(
    *, password: str, seed: bool = True, passphrase: str = DEFAULT_DEMO_PASSPHRASE
) -> None:
    user_id, username = await _ensure_demo_user(password)
    data_key = await _demo_data_key(user_id, passphrase)
    if not seed:
        print(f"[OK] Demo user {username!r} ready; data left as it is.")
        return
    with use_data_key(data_key):
        counts = await _seed_demo_data()
    print(
        f"[OK] Demo reset for user {username!r}: "
        f"{counts.get('institutions', 0)} institutions, "
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
        help=(
            "Demo data passphrase when KALETA_ENCRYPTION=passphrase "
            f"(default: {DEFAULT_DEMO_PASSPHRASE!r})."
        ),
    )
    parser.add_argument(
        "--tenant",
        metavar="NAME",
        help=(
            "Hosted instances (KALETA_TENANCY=multi): reset the demo as an account of its "
            "own, provisioning it if missing. NAME is a label for the logs; the account "
            "is the one --email owns."
        ),
    )
    parser.add_argument(
        "--email",
        default=DEFAULT_DEMO_EMAIL,
        help=f"With --tenant: the demo owner's e-mail address (default: {DEFAULT_DEMO_EMAIL!r}).",
    )
    args = parser.parse_args()

    settings = Settings()
    if not settings.demo and not args.force:
        print(
            "Refusing to reset: set KALETA_DEMO=true or pass --force.",
            file=sys.stderr,
        )
        return 1
    if (settings.tenancy == "multi") != (args.tenant is not None):
        print(
            "Refusing to reset: --tenant goes with KALETA_TENANCY=multi, and only with it.",
            file=sys.stderr,
        )
        return 1

    configure_database(settings.db_url, debug=settings.debug)
    if args.tenant is not None:
        job = reset_demo_tenant(
            email=args.email,
            password=args.password,
            seed=not args.no_seed,
            passphrase=args.data_passphrase,
        )
    else:
        save_db(settings.db_url, name="demo")
        job = reset_demo(
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
