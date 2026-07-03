"""Playwright e2e test configuration.

Default: pytest launches an isolated Kaleta instance (ephemeral SQLite DB on
port 8081). No manual ``uv run kaleta`` and no writes to the developer's
``~/.kaleta/config.json`` or project ``kaleta.db``.

Prerequisites:
  1. Install browsers once:  uv run playwright install chromium
  2. Run tests:              uv run pytest tests/e2e/ -q

Debug against an already-running app (mutates that app's database):

  KALETA_E2E_BASE_URL=http://localhost:8080 uv run pytest tests/e2e/ -q
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.e2e import seed_helpers

PROJECT_ROOT = Path(__file__).resolve().parents[2]
E2E_PORT = 8081
DEFAULT_E2E_BASE = f"http://127.0.0.1:{E2E_PORT}"

# Set by e2e_server when it spawns a subprocess; read by pytest_runtest_makereport.
_server_log_path: Path | None = None


def _tail_lines(path: Path, n: int = 50) -> str:
    if not path.exists():
        return f"(server log not found: {path})"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return f"(server log empty: {path})"
    return "\n".join(lines[-n:])


def _pump_stdout_to_log(proc: subprocess.Popen[str], log_path: Path) -> None:
    """Drain subprocess stdout into a log file until the process exits."""
    assert proc.stdout is not None
    with log_path.open("w", encoding="utf-8") as log_file:
        for line in proc.stdout:
            log_file.write(line)
            log_file.flush()


def _wait_for_server(base_url: str, timeout: float = 90.0) -> None:
    """Wait until the Kaleta HTTP API responds."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{base_url}/api/v1/accounts/", timeout=2.0)
            if resp.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Kaleta e2e server at {base_url} did not become ready") from last_error


def _run_alembic(db_url: str) -> None:
    env = os.environ.copy()
    env["KALETA_MIGRATE_URL"] = db_url
    env["KALETA_DEBUG"] = "true"
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_kaleta_config(home: Path, db_url: str) -> None:
    config_dir = home / ".kaleta"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        json.dumps({"db_url": db_url, "name": "e2e"}),
        encoding="utf-8",
    )


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Generator[None, Any, Any]:
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call" or not rep.failed or _server_log_path is None:
        return
    tail = _tail_lines(_server_log_path)
    if hasattr(rep, "sections"):
        rep.sections.append(
            ("e2e server log (last 50 lines)", tail),
        )
    else:
        rep.longrepr = f"{rep.longrepr}\n\n--- e2e server log (last 50 lines) ---\n{tail}"


@pytest.fixture(scope="session")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[str]:
    """Start an ephemeral Kaleta web app, or reuse ``KALETA_E2E_BASE_URL``."""
    global _server_log_path

    external = os.environ.get("KALETA_E2E_BASE_URL")
    if external:
        _server_log_path = None
        seed_helpers.configure(external)
        _wait_for_server(external.rstrip("/"))
        yield external.rstrip("/")
        return

    home = tmp_path_factory.mktemp("e2e_home")
    db_dir = tmp_path_factory.mktemp("e2e_db")
    log_dir = tmp_path_factory.mktemp("e2e_logs")
    db_path = db_dir / "e2e.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    _server_log_path = log_dir / "kaleta-e2e-server.log"

    _write_kaleta_config(home, db_url)
    _run_alembic(db_url)

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["KALETA_PORT"] = str(E2E_PORT)
    env["KALETA_DEBUG"] = "true"
    env["KALETA_DB_URL"] = db_url
    # NiceGUI detects pytest and reads NICEGUI_SCREEN_TEST_PORT instead of KALETA_PORT.
    env["NICEGUI_SCREEN_TEST_PORT"] = str(E2E_PORT)

    proc = subprocess.Popen(
        ["uv", "run", "kaleta"],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    pump = threading.Thread(
        target=_pump_stdout_to_log,
        args=(proc, _server_log_path),
        daemon=True,
    )
    pump.start()

    base_url = DEFAULT_E2E_BASE
    try:
        _wait_for_server(base_url)
        from kaleta.db import configure_database

        configure_database(db_url, debug=True)
        seed_helpers.configure(base_url, db_url=db_url)
        yield base_url
    except Exception:
        raise
    finally:
        _terminate_process(proc)
        pump.join(timeout=5)


@pytest.fixture(scope="session")
def base_url(e2e_server: str) -> str:
    return e2e_server


def login(page) -> None:  # noqa: ANN001 — Playwright Page; stub until q3-auth-single-user
    """Authenticate before e2e flows.

    TODO(q3-auth-single-user): replace with real single-user login once auth lands.
    """
