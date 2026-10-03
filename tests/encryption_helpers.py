# SPDX-License-Identifier: AGPL-3.0-or-later
"""Key holders for databases a test hands to a script in a subprocess.

A script works under the data key a local key holder's passphrase opens
(``scripts/data_passphrase.py``). In the suite's encrypted run
(``KALETA_ENCRYPTION=passphrase``) a database the test creates for a script
gets a holder whose sealed key is the suite's own ``TEST_DATA_KEY`` — so what
the script writes, the test reads back under the key every test runs under.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

import kaleta.models  # noqa: F401 — register every table
from kaleta.config import settings
from kaleta.crypto import KdfParams, create_key_material
from kaleta.db.base import Base
from kaleta.models.local_key_material import LocalKeyMaterial
from tests.conftest import TEST_DATA_KEY

TEST_PASSPHRASE = "test-data-passphrase"
#: Cheap on purpose: these keys guard throwaway files, and each script run derives once.
_FAST_KDF = KdfParams(time_cost=1, memory_kib=8 * 1024, parallelism=1)
#: Not a real user: ``local_key_material.user_id`` has no foreign key, and a
#: script only needs *a* holder whose passphrase it was given.
_HOLDER_USER_ID = 0


def script_env(db_url: str) -> dict[str, str]:
    """Extra environment for a script run against ``db_url``; prepares the database too.

    Empty while encryption is off. Otherwise creates the schema (a script
    would, but the holder's table must exist first) and the key holder, once.
    """
    if not settings.encryption_enabled:
        return {}
    asyncio.run(_add_key_holder(db_url))
    return {"KALETA_DATA_PASSPHRASE": TEST_PASSPHRASE}


async def _add_key_holder(db_url: str) -> None:
    material, _private_key = create_key_material(
        TEST_PASSPHRASE, dek=TEST_DATA_KEY.dek, recovery_code=None, params=_FAST_KDF
    )
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with engine.begin() as conn:
            held = await conn.execute(
                select(LocalKeyMaterial.id).where(LocalKeyMaterial.user_id == _HOLDER_USER_ID)
            )
            if held.first() is not None:
                return
            await conn.execute(
                LocalKeyMaterial.__table__.insert().values(
                    user_id=_HOLDER_USER_ID,
                    key_version=TEST_DATA_KEY.version,
                    public_key=material.public_key,
                    private_key_wrapped=material.private_key_wrapped,
                    private_key_salt=material.private_key_salt,
                    kdf_params=material.kdf_params,
                    dek_sealed=material.dek_sealed,
                )
            )
    finally:
        await engine.dispose()
