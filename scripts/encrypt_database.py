#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Switch field-level encryption on (or off) for an existing self-hosted database.

Run with the setting the app will run with:

    KALETA_ENCRYPTION=passphrase uv run python scripts/encrypt_database.py
    KALETA_ENCRYPTION=passphrase uv run python scripts/encrypt_database.py --decrypt

Encrypting: takes a backup (Settings → Data format, plaintext — delete it once
the encrypted database opens), sets up the local user's data passphrase and
prints its recovery code once, then rewrites every user-written text column
under the new data key and recomputes every blind index. Re-running it on an
already encrypted database asks for the passphrase and finishes any rows a
broken run left behind.

Decrypting (``--decrypt``): opens the data key with the passphrase, takes a
backup, rewrites every column in plaintext format under the plaintext-mode
index key and removes the key material — then run the app with
``KALETA_ENCRYPTION=off``. Needed before downgrading past the migration that
introduced encryption.

Single-tenant installs only: a hosted account encrypts its data at its
owner's first unlock.

The passphrase comes from ``KALETA_DATA_PASSPHRASE`` or a prompt.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data_passphrase import data_passphrase
from sqlalchemy import delete

from kaleta.config import settings
from kaleta.db import AsyncSessionFactory, configure_database
from kaleta.db.types import use_data_key
from kaleta.models.local_key_material import LocalKeyMaterial
from kaleta.services import AuthService, BackupService
from kaleta.services.data_encryption_service import DataEncryptionService
from kaleta.services.key_service import KeyService, LocalKeyStore, open_local_data_key


async def _backup(label: str) -> Path:
    async with AsyncSessionFactory() as session:
        archive = await BackupService(session).export()
    target_dir = Path(settings.backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = target_dir / f"kaleta-{label}-{stamp}.zip"
    path.write_bytes(archive)
    path.chmod(0o600)
    return path


def _new_passphrase() -> str:
    first = data_passphrase("New data passphrase: ")
    if sys.stdin.isatty() and data_passphrase("Repeat it: ") != first:
        raise SystemExit("[ERROR] The two passphrases differ.")
    return first


async def encrypt(username: str | None) -> None:
    async with AsyncSessionFactory() as session:
        auth = AuthService(session)
        user = (
            await auth.get_user_by_username(username) if username else await auth.get_single_user()
        )
        if user is None:
            raise SystemExit("[ERROR] No such user; create the account first.")
        if username is None and await auth.count_users() > 1:
            raise SystemExit("[ERROR] Several users: name the key holder with --user.")
        service = KeyService(LocalKeyStore(session, user.id), session)
        status = await service.status()

    if status == "ready":
        async with AsyncSessionFactory() as session:
            data_key = await open_local_data_key(session, data_passphrase())
            with use_data_key(data_key):
                counts = await DataEncryptionService(session).rewrite_all()
                await session.commit()
        print(f"[OK] Already set up; rewrote {sum(counts.values())} rows under the data key.")
        return

    backup = await _backup("pre-encryption")
    print(f"[OK] Backup written to {backup} — plaintext: delete it once the app opens.")
    passphrase = _new_passphrase()
    async with AsyncSessionFactory() as session:
        setup = await KeyService(LocalKeyStore(session, user.id), session).setup(None, passphrase)
    print("[OK] Data passphrase set up and every row encrypted.")
    print()
    print("    Your recovery code (shown once — write it down and keep it safe):")
    print(f"    {setup.recovery_code}")
    print()
    print("    Without the passphrase and this code your data cannot be opened.")


async def decrypt() -> None:
    async with AsyncSessionFactory() as session:
        data_key = await open_local_data_key(session, data_passphrase())
    with use_data_key(data_key):
        backup = await _backup("pre-decryption")
        print(f"[OK] Backup written to {backup}.")
        # Read under the key, write in plaintext format: the column types
        # decide on the setting, the reads on the key bound above.
        settings.encryption = "off"
        async with AsyncSessionFactory() as session:
            counts = await DataEncryptionService(session).rewrite_all()
            await session.execute(delete(LocalKeyMaterial))
            await session.commit()
    print(f"[OK] {sum(counts.values())} rows decrypted; the key material is removed.")
    print("    Run the app with KALETA_ENCRYPTION=off from now on.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--decrypt", action="store_true", help="Turn encryption off again.")
    parser.add_argument("--user", help="Username of the key holder (default: the only user).")
    args = parser.parse_args()

    if settings.tenancy == "multi":
        print("[ERROR] Hosted accounts encrypt at their owner's first unlock.", file=sys.stderr)
        return 1
    if not settings.encryption_enabled:
        print(
            "[ERROR] Run with KALETA_ENCRYPTION=passphrase — the setting the app will "
            "run with (and, with --decrypt, the one it ran with until now).",
            file=sys.stderr,
        )
        return 1

    configure_database(settings.db_url, debug=settings.debug)
    try:
        asyncio.run(decrypt() if args.decrypt else encrypt(args.user))
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
