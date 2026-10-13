# SPDX-License-Identifier: AGPL-3.0-or-later
"""Several replicas starting together migrate the database once.

The startup migration (``ensure_multi_tenant_current``) runs under a Postgres
advisory lock so N replicas coming up at the same time do not run Alembic
against one database concurrently. These tests use the real suite database:
advisory locks are per-session (per-connection), so two threads each opening
their own lock connection model two replicas exactly.

Covers: KAL-TEN-026
"""

from __future__ import annotations

import os
import threading
import time

import pytest
from sqlalchemy import create_engine, text

from kaleta.services import setup_service
from kaleta.services.setup_service import (
    _MIGRATION_LOCK_KEY,
    _migration_advisory_lock,
    _sync_url,
)

_DB_URL = os.environ["KALETA_DB_URL"]


def _try_lock_elsewhere() -> bool:
    """Whether a fresh, independent session can take the migration lock now."""
    engine = create_engine(_sync_url(_DB_URL))
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        got = bool(
            conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": _MIGRATION_LOCK_KEY}
            ).scalar()
        )
        if got:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _MIGRATION_LOCK_KEY})
        return got
    finally:
        conn.close()
        engine.dispose()


def test_the_lock_blocks_a_second_session_and_frees_on_exit() -> None:
    """Covers: KAL-TEN-026"""
    assert _try_lock_elsewhere() is True  # nobody holds it to begin with
    with _migration_advisory_lock(_DB_URL):
        assert _try_lock_elsewhere() is False  # a run holds it: others must wait
    assert _try_lock_elsewhere() is True  # the run let go on exit


def test_a_run_that_raises_still_releases_the_lock() -> None:
    """A replica dying mid-migration must not strand the lock.

    Covers: KAL-TEN-026
    """
    boom = RuntimeError("migration blew up")
    try:
        with _migration_advisory_lock(_DB_URL):
            raise boom
    except RuntimeError as exc:
        assert exc is boom
    assert _try_lock_elsewhere() is True


def test_concurrent_runs_never_migrate_at_the_same_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two replicas starting together: the lock lets only one run the body.

    The migration body is stubbed to record how many threads are inside it at
    once; the real advisory lock around it must keep that at one.

    Covers: KAL-TEN-026
    """
    active = 0
    max_active = 0
    counter_lock = threading.Lock()
    both_ready = threading.Barrier(2)

    def _fake_body(db_url: str) -> setup_service.TenantMigrationRun:
        nonlocal active, max_active
        with counter_lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.2)  # hold the lock long enough for the other thread to collide
        with counter_lock:
            active -= 1
        return setup_service.TenantMigrationRun()

    monkeypatch.setattr(setup_service, "_migrate_registry_and_tenants", _fake_body)

    def _worker() -> None:
        both_ready.wait()
        setup_service.ensure_multi_tenant_current(_DB_URL)

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert max_active == 1  # the advisory lock never let both bodies run at once
