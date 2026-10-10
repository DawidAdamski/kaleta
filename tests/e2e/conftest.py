# SPDX-License-Identifier: AGPL-3.0-or-later
"""Playwright e2e test configuration.

Default: pytest launches an isolated Kaleta instance on port 8081, in a fresh
database ``<suite database>_e2e`` on the suite's PostgreSQL server. Like every
instance (ADR-38) it keeps a registry and one schema per family: the e2e login
is the instance's administrator, a local login in the registry, and owns the one
family the suite works in. The apps run with ``KALETA_ENCRYPTION=off``
(accepted under ``KALETA_DEBUG``), so no test has to unlock first; the
encryption e2e tests start apps of their own with it on.

Prerequisites:
  1. Install browsers once:  uv run playwright install chromium
  2. Run tests:              uv run pytest tests/e2e/ -q

Debug against an already-running app (mutates that app's database):

  KALETA_E2E_BASE_URL=http://localhost:8080 uv run pytest tests/e2e/ -q
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import threading
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from playwright.sync_api import Browser, BrowserContext

from kaleta.config import settings
from kaleta.db.tenant_context import TenantContext
from tests.e2e import seed_helpers
from tests.suite_database import fresh_database_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
E2E_PORT = 8081
DEFAULT_E2E_BASE = f"http://127.0.0.1:{E2E_PORT}"
E2E_EMAIL = "e2e@example.com"
E2E_PASSWORD = "e2e-test-password"
E2E_API_TOKEN: str | None = None
#: What every e2e app runs with, whatever the environment pytest was started in.
E2E_APP_ENV = {
    "KALETA_DEBUG": "true",
    "KALETA_AUTH_BACKEND": "local",
    "KALETA_ENCRYPTION": "off",
}

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
    """Wait until the Kaleta HTTP server responds."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{base_url}/api-docs", timeout=2.0)
            if resp.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Kaleta e2e server at {base_url} did not become ready") from last_error


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


@dataclass(frozen=True)
class E2ELogin:
    """The e2e login's family, and a bearer token of its own."""

    family: TenantContext
    api_token: str


def prepare_e2e_database(db_url: str) -> E2ELogin:
    """A registry in ``db_url``, the e2e login as its administrator, and that login's family.

    Done before the app starts, as an administrator's first run would leave it.
    In a worker thread: Playwright's sync API keeps an event loop running in
    the test thread, and the registry's migrations run one of their own.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_prepare, db_url).result()


def _prepare(db_url: str) -> E2ELogin:
    import asyncio

    from kaleta.services.setup_service import upgrade_public_to_head

    upgrade_public_to_head(db_url)
    return asyncio.run(_provision_e2e_login(db_url))


async def _provision_e2e_login(db_url: str) -> E2ELogin:
    from kaleta.db import AsyncSessionFactory, configure_database
    from kaleta.db.tenant_context import use_tenant
    from kaleta.schemas.identity import Identity
    from kaleta.services import ApiTokenService
    from kaleta.services.local_identity_service import LocalIdentityService, subject_of
    from kaleta.services.tenant_service import AlembicSchemaProvisioner, TenantService

    configure_database(db_url, debug=True)
    try:
        async with AsyncSessionFactory.public() as public:
            row = await LocalIdentityService(public).create(E2E_EMAIL, E2E_PASSWORD, admin=True)
            tenants = TenantService(
                public, provisioner=AlembicSchemaProvisioner(db_url, AsyncSessionFactory.public)
            )
            membership = await tenants.membership_for_sign_in(
                Identity(subject=subject_of(row.id), email=E2E_EMAIL, email_verified=True)
            )
        family = membership.context()
        if family.member_user_id is None:
            msg = "the e2e family has no owner row"
            raise RuntimeError(msg)
        with use_tenant(family):
            async with AsyncSessionFactory() as session:
                _token_row, raw = await ApiTokenService(session).create_token(
                    user_id=family.member_user_id, label="e2e"
                )
        return E2ELogin(family=family, api_token=raw)
    finally:
        # The connections belong to this loop, which ends here.
        await AsyncSessionFactory.dispose()


@pytest.fixture(autouse=True)
def _session_pool_per_test() -> None:
    """Overrides the suite's async one: Playwright's sync API owns the test thread's loop.

    No e2e test uses the suite's session pool; the helpers open and dispose
    their own, in worker threads (``seed_helpers._run_async_worker``).
    """


@pytest.fixture(scope="session", autouse=True)
def _plaintext_like_the_apps() -> Generator[None]:
    """The helpers that write through the service layer do so as the apps read it."""
    previous = settings.encryption
    settings.encryption = "off"
    yield
    settings.encryption = previous


@pytest.fixture(scope="session")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[str]:
    """Start an ephemeral Kaleta web app, or reuse ``KALETA_E2E_BASE_URL``."""
    global _server_log_path, E2E_API_TOKEN

    external = os.environ.get("KALETA_E2E_BASE_URL")
    if external:
        _server_log_path = None
        seed_helpers.configure(external)
        _wait_for_server(external.rstrip("/"))
        yield external.rstrip("/")
        return

    home = tmp_path_factory.mktemp("e2e_home")
    log_dir = tmp_path_factory.mktemp("e2e_logs")
    db_url = fresh_database_url("e2e")
    _server_log_path = log_dir / "kaleta-e2e-server.log"

    e2e_login = prepare_e2e_database(db_url)

    env = os.environ.copy()
    env.update(E2E_APP_ENV)
    env["HOME"] = str(home)
    env["KALETA_PORT"] = str(E2E_PORT)
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
        E2E_API_TOKEN = e2e_login.api_token
        seed_helpers.configure(
            base_url, db_url=db_url, api_token=E2E_API_TOKEN, family=e2e_login.family
        )
        yield base_url
    except Exception:
        raise
    finally:
        _terminate_process(proc)
        pump.join(timeout=5)


@pytest.fixture(scope="session")
def base_url(e2e_server: str) -> str:
    return e2e_server


@pytest.fixture(scope="session")
def e2e_api_token() -> str:
    assert E2E_API_TOKEN is not None, "e2e API token was not created"
    return E2E_API_TOKEN


def session_cookie(context: BrowserContext) -> str:
    """The raw ``kaleta_session`` cookie the browser holds."""
    for cookie in context.cookies():
        if cookie["name"] == "kaleta_session":
            return cookie["value"]
    raise AssertionError("no kaleta_session cookie in the browser")


def storage_id(raw_cookie: str) -> str:
    """The NiceGUI storage id inside a signed ``kaleta_session`` cookie.

    The raw value is re-signed with a fresh timestamp on every response, so it
    changes all the time; the id it wraps changes only when the session moves.
    """
    payload = raw_cookie.split(".", 1)[0]
    decoded = json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4)))
    return str(decoded["id"])


def login(page, base_url: str) -> None:
    """Sign in via the login page using the shared e2e credentials."""
    page.goto(f"{base_url}/login")
    page.get_by_label("E-mail", exact=True).fill(E2E_EMAIL)
    page.get_by_label("Password", exact=True).fill(E2E_PASSWORD)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url(lambda url: "/login" not in url, timeout=15000)


@pytest.fixture(scope="session")
def auth_storage_state(browser, base_url: str):
    context = browser.new_context()
    page = context.new_page()
    login(page, base_url)
    state = context.storage_state()
    context.close()
    return state


@pytest.fixture(scope="session")
def browser_context_args(
    browser_context_args: dict[str, Any],
    auth_storage_state,
) -> dict[str, Any]:
    return {**browser_context_args, "storage_state": auth_storage_state}


@pytest.fixture
def renew_shared_login(browser, base_url: str, auth_storage_state) -> Generator[None]:
    """Sign the shared login in again after a test that revokes sessions.

    Every page in the suite starts from ``auth_storage_state``, one login shared
    by all of them. A test that bumps the revocation watermark — a credential
    change, or "Sign out everywhere" — ends that login as well, and every test
    after it would land on ``/login``. The state is replaced in place, since
    ``browser_context_args`` holds a reference to this very dict.
    """
    yield
    context = browser.new_context()
    page = context.new_page()
    login(page, base_url)
    fresh = context.storage_state()
    context.close()
    auth_storage_state.clear()
    auth_storage_state.update(fresh)


@pytest.fixture
def page_no_auth(browser: Browser):
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()
