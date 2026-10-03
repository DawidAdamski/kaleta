#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reset a Kaleta demo instance to a known user + seeded dataset.

Typical use: nightly cron on a hosted demo backed by Supabase Postgres.

Requires ``KALETA_DEMO=true`` (or ``--force`` for local dry-runs).

With ``KALETA_ENCRYPTION=passphrase`` the demo user's data passphrase is the
published ``DEFAULT_DEMO_PASSPHRASE`` (see ``docs/deployment.md``): the first
reset sets it up, every later one unlocks with it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kaleta.config import settings as active_settings
from kaleta.config.settings import Settings
from kaleta.config.setup_config import save_db
from kaleta.crypto import DataKey
from kaleta.db import configure_database
from kaleta.db.types import use_data_key
from kaleta.services import AuthService, with_session
from kaleta.services.data_service import DataService
from kaleta.services.key_service import KeyService, LocalKeyStore

DEFAULT_DEMO_USERNAME = "demo"
DEFAULT_DEMO_PASSWORD = "demo-kaleta"
#: Published with the login — the demo is public; see the module docstring.
DEFAULT_DEMO_PASSPHRASE = "demo-kaleta-data"


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


async def _demo_data_key(user_id: int, passphrase: str) -> DataKey | None:
    """The demo user's data key: set up on the first reset, opened on every later one."""
    if not active_settings.encryption_enabled:
        return None

    async def _run(session):
        service = KeyService(LocalKeyStore(session, user_id), session)
        if await service.status() == "setup_required":
            setup = await service.setup(None, passphrase)
            print("[OK] Demo data passphrase set up.")
            return setup.data_key
        data_key, _private_key = await service.open(passphrase)
        return data_key

    return await with_session(_run)


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
    args = parser.parse_args()

    settings = Settings()
    if not settings.demo and not args.force:
        print(
            "Refusing to reset: set KALETA_DEMO=true or pass --force.",
            file=sys.stderr,
        )
        return 1

    configure_database(settings.db_url, debug=settings.debug)
    save_db(settings.db_url, name="demo")

    try:
        asyncio.run(
            reset_demo(
                password=args.password,
                seed=not args.no_seed,
                passphrase=args.data_passphrase,
            )
        )
    except Exception as exc:
        print(f"[ERROR] Demo reset failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
