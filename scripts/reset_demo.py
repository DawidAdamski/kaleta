#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reset a Kaleta demo instance to a known user + seeded dataset.

Typical use: nightly cron on a hosted demo backed by Supabase Postgres.

Requires ``KALETA_DEMO=true`` (or ``--force`` for local dry-runs).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kaleta.config.settings import Settings
from kaleta.config.setup_config import save_db
from kaleta.db import configure_database
from kaleta.services import AuthService, with_session
from kaleta.services.data_service import DataService

DEFAULT_DEMO_USERNAME = "demo"
DEFAULT_DEMO_PASSWORD = "demo-kaleta"


async def _ensure_demo_user(password: str) -> str:
    async def _run(session):  # noqa: ANN001
        auth = AuthService(session)
        state = await auth.auth_state()
        if state == "no_user":
            user = await auth.create_user(DEFAULT_DEMO_USERNAME, password)
            return user.username
        if state == "placeholder":
            user = await auth.secure_placeholder(DEFAULT_DEMO_USERNAME, password)
            return user.username
        user = await auth.reset_password(password)
        return user.username

    return await with_session(_run)


async def _seed_demo_data() -> dict[str, int]:
    async def _run(session):  # noqa: ANN001
        return await DataService(session).seed()

    return await with_session(_run)


async def reset_demo(*, password: str) -> None:
    username = await _ensure_demo_user(password)
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
        "--password",
        default=DEFAULT_DEMO_PASSWORD,
        help=f"Demo login password (default: {DEFAULT_DEMO_PASSWORD!r}).",
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
        asyncio.run(reset_demo(password=args.password))
    except Exception as exc:
        print(f"[ERROR] Demo reset failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
