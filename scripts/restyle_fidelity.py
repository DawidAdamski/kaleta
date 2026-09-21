#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hold the restyle to its artboards: split the canvas, shoot both sides, gate on a report.

The first restyle pass was planned from the handoff's prose and closed with
``[manual]`` criteria nobody ran, so no step ever put the rendered app next
to the artboard it was copying. This script is that step.

    uv run python scripts/restyle_fidelity.py split
    uv run python scripts/restyle_fidelity.py shoot 2a        # or: all
    uv run python scripts/restyle_fidelity.py check 2a        # or: all

``split``  cuts ``Kaleta Dashboard.dc.html`` into one static file per target
           artboard under ``docs/design/restyle/artboards/``. Each is 10-25 KB:
           small enough to read whole, which the 300 KB canvas is not.
``shoot``  starts an ephemeral, seeded Kaleta (nothing of the developer's is
           touched), screenshots the app and the artboard at the artboard's
           width and theme into ``.fidelity/<id>/``, and stamps the report
           with a hash of the screen's source files.
``check``  is the executable acceptance criterion: the report exists, was
           written against the code as it is now, has no ``open`` row, and
           every ``deviation`` says why.

Look at the two pictures before writing the report. That is the whole point.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

ROOT = Path(__file__).resolve().parents[1]
RESTYLE_DIR = ROOT / "docs" / "design" / "restyle"
CANVAS = RESTYLE_DIR / "Kaleta Dashboard.dc.html"
ARTBOARD_DIR = RESTYLE_DIR / "artboards"
REPORT_DIR = RESTYLE_DIR / "fidelity"
SHOT_DIR = ROOT / ".fidelity"
VIEWS = "src/kaleta/views"
#: Every screen wears the shell and the tokens, so a change to either is a
#: change to every screen.
SHELL_SOURCES = (f"{VIEWS}/theme.py", f"{VIEWS}/layout.py")

PORT = 8082  # 8080 is the developer's app, 8081 is the e2e suite's.
USERNAME = "demo"
PASSWORD = "demo-kaleta"
MIN_REPORT_ROWS = 8
STATUSES = ("match", "deviation", "open")


@dataclass(frozen=True)
class Artboard:
    """One target artboard and where its counterpart lives in the app."""

    id: str
    title: str
    route: str
    sources: tuple[str, ...]
    theme: str = "light"
    #: The app is shot once per viewport; the first one is the artboard's own.
    viewports: tuple[tuple[int, int], ...] = ((1360, 900),)
    #: Name of a ``Shooter._prepare_*`` method that walks to the right state.
    prepare: str | None = None
    needs_login: bool = True
    settle_ms: int = 1500
    #: The dashboard is drawn with the 236px drawer, every working screen with
    #: the 64px mini one. ``None`` where there is no drawer (phone, login).
    drawer: str | None = "mini"


_DASHBOARD = (f"{VIEWS}/dashboard.py", f"{VIEWS}/dashboard_widgets")

#: The owner's targets. `1a` (before-picture), `1b` and `1e` are on the canvas
#: but are NOT targets — `1e` in particular was built once by mistake.
ARTBOARDS: tuple[Artboard, ...] = (
    Artboard("1c", "Dashboard, light", "/", _DASHBOARD, drawer="full"),
    Artboard("1d", "Dashboard, dark", "/", _DASHBOARD, theme="dark", drawer="full"),
    Artboard("1f", "Dashboard, phone", "/", _DASHBOARD, viewports=((390, 844),), drawer=None),
    Artboard(
        "2a",
        "Transactions",
        "/transactions",
        (f"{VIEWS}/transactions", f"{VIEWS}/components"),
        prepare="ledger",
    ),
    Artboard(
        "2b",
        "Budgets - Realization",
        "/budgets",
        (f"{VIEWS}/budgets",),
        prepare="realization_tab",
    ),
    Artboard("2c", "Budget Plan", "/budget-plan", (f"{VIEWS}/budget_plan",)),
    Artboard(
        "2d",
        "Import, step 3 (mapping)",
        "/import",
        (f"{VIEWS}/import_view",),
        prepare="import_mapping",
    ),
    Artboard(
        "3a",
        "Forecast",
        "/forecast",
        (f"{VIEWS}/forecast.py", f"{VIEWS}/chart_utils.py"),
        settle_ms=6000,
        prepare="rest_pointer",
    ),
    Artboard("3b", "Net Worth", "/net-worth", (f"{VIEWS}/net_worth.py",)),
    Artboard(
        "3c",
        "Payment Calendar",
        "/payment-calendar",
        (f"{VIEWS}/payment_calendar.py",),
        prepare="calendar_day",
    ),
    Artboard(
        "3d",
        "Financial Wizard",
        "/wizard",
        (f"{VIEWS}/wizard.py",),
        prepare="wizard_setup_open",
    ),
    Artboard(
        "3e",
        "Report builder",
        "/reports/builder",
        (f"{VIEWS}/reports",),
        prepare="report_run",
    ),
    Artboard(
        "3f",
        "Login, desktop and phone",
        "/login",
        (f"{VIEWS}/login.py", f"{VIEWS}/auth_common.py"),
        viewports=((1360, 900), (390, 844)),
        needs_login=False,
        drawer=None,
        prepare="login_error",
    ),
)
BY_ID = {a.id: a for a in ARTBOARDS}


class FidelityError(Exception):
    """A step could not do its job; the message says what to fix."""


# ── split ────────────────────────────────────────────────────────────────


class CanvasSplitter:
    """Cut the design canvas into one self-contained file per target artboard."""

    _DIV = re.compile(r"<div\b|</div>")
    #: Self-hosted faces first, so an artboard renders the same offline as the
    #: app does; the canvas's own Google Fonts link stays for the icon font.
    _FONTS = "../../../../src/kaleta/static/fonts"

    def __init__(self, canvas: Path = CANVAS) -> None:
        if not canvas.exists():
            raise FidelityError(f"canvas not found: {canvas}")
        self._source = canvas.read_text(encoding="utf-8")

    def run(self, out_dir: Path = ARTBOARD_DIR) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for artboard in ARTBOARDS:
            path = out_dir / f"{artboard.id}.html"
            path.write_text(self._page(artboard), encoding="utf-8")
            written.append(path)
        return written

    def _page(self, artboard: Artboard) -> str:
        start = self._source.find(f'id="{artboard.id}"')
        if start < 0:
            raise FidelityError(f"artboard {artboard.id} is not on the canvas")
        card_at = self._source.find('<div class="dv-card"', start)
        card = self._balanced_div(card_at)
        note = self._designer_note(start, card_at)
        fonts = self._FONTS
        return (
            "<!DOCTYPE html>\n"
            f"<!-- Artboard {artboard.id} - {artboard.title}.\n"
            "     Generated by scripts/restyle_fidelity.py split from\n"
            "     'Kaleta Dashboard.dc.html'. Do not edit; re-run split.\n"
            "     This markup IS the spec: element order, nesting and every\n"
            "     inline value. Content is sample data; SVG charts are sketches.\n"
            f"     Designer's note: {note}\n"
            "-->\n"
            '<html><head><meta charset="utf-8">\n'
            f"<title>Kaleta artboard {artboard.id}</title>\n"
            f"{self._font_link()}\n"
            "<style>\n"
            "@font-face{font-family:'Libre Franklin';font-weight:100 900;"
            f"src:url('{fonts}/libre-franklin-var.woff2') format('woff2')}}\n"
            "@font-face{font-family:'IBM Plex Mono';font-weight:400;"
            f"src:url('{fonts}/ibm-plex-mono-400.woff2') format('woff2')}}\n"
            "@font-face{font-family:'IBM Plex Mono';font-weight:500;"
            f"src:url('{fonts}/ibm-plex-mono-500.woff2') format('woff2')}}\n"
            "body{margin:0;background:#E9E4DA;"
            "font-family:'Libre Franklin',system-ui,sans-serif}\n"
            "a{color:#9A4E1F;text-decoration:none}\n"
            f"{self._icon_rule()}\n"
            ".dv-card{overflow:hidden}\n"
            "</style></head>\n<body>\n"
            f"{card}\n"
            "</body></html>\n"
        )

    def _balanced_div(self, at: int) -> str:
        depth = 0
        for match in self._DIV.finditer(self._source, at):
            depth += 1 if match.group() != "</div>" else -1
            if depth == 0:
                return self._source[at : match.end()]
        raise FidelityError("unbalanced <div> while cutting an artboard")

    def _designer_note(self, start: int, card_at: int) -> str:
        label = self._source[start:card_at]
        text = html.unescape(re.sub(r"<[^>]+>", " ", label.split(">", 1)[-1]))
        return re.sub(r"\s+", " ", text).replace("--", "-").strip()

    def _font_link(self) -> str:
        match = re.search(r'<link href="https://fonts\.googleapis\.com/css2[^>]+>', self._source)
        return match.group() if match else ""

    def _icon_rule(self) -> str:
        match = re.search(r"\.ms\{[^}]+\}", self._source)
        return match.group() if match else ""


# ── report ───────────────────────────────────────────────────────────────


@dataclass
class Report:
    """``docs/design/restyle/fidelity/<id>.md`` — what was compared, and the verdict."""

    artboard: Artboard
    path: Path = field(init=False)

    _TEMPLATE_ROWS = (
        "Shell: header (height, ground, contents)",
        "Shell: drawer / tab bar (width, items, active state)",
        "Title block: eyebrow, title size and weight, actions on the title row",
        "Layout: columns, widths, order of sections",
        "Surfaces: what is a card and what is bare type on the ground",
        "Card geometry: radius, padding, shadow, gaps",
        "Typography: sizes, weights, letter-spacing per role",
        "Numbers: IBM Plex Mono, tabular, muted decimals",
        "Colour: ink / muted / accent / income / expense where the artboard has them",
        "Controls: buttons, chips, pills, toggles, inputs",
        "Tables and lists: columns, alignment, dividers, row height",
        "Charts: series colours, axes, legend, annotations",
    )

    def __post_init__(self) -> None:
        self.path = REPORT_DIR / f"{self.artboard.id}.md"

    def source_hash(self) -> str:
        digest = hashlib.sha256()
        for source in (*SHELL_SOURCES, *self.artboard.sources):
            root = ROOT / source
            files = sorted(root.rglob("*.py")) if root.is_dir() else [root]
            for file in files:
                if not file.exists():
                    raise FidelityError(f"{self.artboard.id}: source not found: {source}")
                digest.update(file.relative_to(ROOT).as_posix().encode())
                digest.update(file.read_bytes())
        return digest.hexdigest()[:16]

    def stamp(self) -> None:
        """Record what code the screenshots were taken of; create the report if new."""
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.date.today().isoformat()
        if not self.path.exists():
            self.path.write_text(self._template(today), encoding="utf-8")
            return
        text = self.path.read_text(encoding="utf-8")
        text = re.sub(r"^views_hash:.*$", f"views_hash: {self.source_hash()}", text, flags=re.M)
        text = re.sub(r"^shot_at:.*$", f"shot_at: {today}", text, flags=re.M)
        self.path.write_text(text, encoding="utf-8")

    def problems(self) -> list[str]:
        if not self.path.exists():
            return [f"no report at {self.path.relative_to(ROOT)} - run `shoot {self.artboard.id}`"]
        text = self.path.read_text(encoding="utf-8")
        found: list[str] = []
        stamped = re.search(r"^views_hash:\s*(\S+)", text, flags=re.M)
        if stamped is None or stamped.group(1) != self.source_hash():
            found.append("the screen's source changed since the last `shoot` - shoot and re-review")
        rows = self._rows(text)
        if len(rows) < MIN_REPORT_ROWS:
            found.append(f"{len(rows)} compared elements; at least {MIN_REPORT_ROWS} expected")
        for number, element, status, note in rows:
            if status not in STATUSES:
                found.append(f"row {number}: status '{status}' is not one of {', '.join(STATUSES)}")
            elif status == "open":
                found.append(f"row {number} still open: {element}")
            elif status == "deviation" and not note:
                found.append(f"row {number} is a deviation with no reason: {element}")
        return found

    @staticmethod
    def _rows(text: str) -> list[tuple[str, str, str, str]]:
        rows = []
        for line in text.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) == 6 and cells[0].isdigit():
                rows.append((cells[0], cells[1], cells[4].lower(), cells[5]))
        return rows

    def _template(self, today: str) -> str:
        a = self.artboard
        rows = "\n".join(
            f"| {n} | {element} |  |  | open |  |"
            for n, element in enumerate(self._TEMPLATE_ROWS, start=1)
        )
        return (
            "---\n"
            f"artboard: {a.id}\n"
            f"views_hash: {self.source_hash()}\n"
            f"shot_at: {today}\n"
            "---\n\n"
            f"# Fidelity report - {a.id} {a.title}\n\n"
            f"Spec: [`artboards/{a.id}.html`](../artboards/{a.id}.html). "
            f"Pictures: `.fidelity/{a.id}/index.html` after `shoot {a.id}`.\n\n"
            "One row per element you compared. Replace the generic rows with the\n"
            'artboard\'s real elements ("Hero figure", "Pace bar", "Overdue strip").\n'
            '`Artboard` and `App` hold the observed values, not "ok". Status is\n'
            "`match`, `deviation` (the Note says why: sample data, a Quasar limit,\n"
            "an owner decision) or `open` (still to fix - `check` fails on these).\n\n"
            "| # | Element | Artboard | App | Status | Note |\n"
            "|---|---|---|---|---|---|\n"
            f"{rows}\n"
        )


# ── shoot ────────────────────────────────────────────────────────────────


class EphemeralApp:
    """A seeded Kaleta on its own port, HOME and SQLite file — the e2e recipe."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="kaleta-fidelity-")
        self._proc: subprocess.Popen[bytes] | None = None
        self._log: BinaryIO | None = None
        self.base_url = f"http://127.0.0.1:{PORT}"

    def __enter__(self) -> EphemeralApp:
        home = Path(self._tmp.name)
        db_url = f"sqlite+aiosqlite:///{home / 'fidelity.db'}"
        env = {
            **os.environ,
            "HOME": str(home),
            "KALETA_DB_URL": db_url,
            "KALETA_MIGRATE_URL": db_url,
            "KALETA_PORT": str(PORT),
            "KALETA_HOST": "127.0.0.1",
        }
        env.pop("KALETA_DEMO", None)  # the demo banner is not on any artboard
        (home / ".kaleta").mkdir()
        (home / ".kaleta" / "config.json").write_text(
            json.dumps({"db_url": db_url, "name": "fidelity"}), encoding="utf-8"
        )
        # `scripts/seed.py`, not the demo seed: the artboards are drawn on a
        # ledger that has payees, tags, planned transactions, subscriptions and
        # physical assets in it, and `DataService.seed` carries none of those.
        # It drops and recreates every table from the models, so the schema is
        # stamped back to head afterwards and the demo login made separately.
        self._run(["uv", "run", "alembic", "upgrade", "head"], env)
        self._run(["uv", "run", "python", "scripts/seed.py"], env)
        self._run(["uv", "run", "alembic", "stamp", "head"], env)
        self._run(["uv", "run", "python", "scripts/reset_demo.py", "--force", "--no-seed"], env)
        self._log = (home / "server.log").open("wb")
        self._proc = subprocess.Popen(
            ["uv", "run", "kaleta"], cwd=ROOT, env=env, stdout=self._log, stderr=subprocess.STDOUT
        )
        self._wait(home / "server.log")
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._log is not None:
            self._log.close()
        self._tmp.cleanup()

    @staticmethod
    def _run(command: list[str], env: dict[str, str]) -> None:
        done = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        if done.returncode != 0:
            raise FidelityError(f"{' '.join(command)} failed:\n{done.stdout}\n{done.stderr}")

    def _wait(self, log: Path, timeout: float = 90.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"{self.base_url}/api-docs", timeout=2) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                time.sleep(0.3)
        tail = log.read_text(encoding="utf-8", errors="replace")[-2000:]
        raise FidelityError(f"Kaleta did not come up on {self.base_url}:\n{tail}")


class Shooter:
    """Screenshot the app and the artboard, same width, same theme, side by side."""

    def __init__(self, browser: Browser, base_url: str) -> None:
        self._browser = browser
        self._base_url = base_url.rstrip("/")

    def shoot(self, artboards: list[Artboard]) -> None:
        for theme in ("light", "dark"):
            batch = [a for a in artboards if a.theme == theme]
            if not batch:
                continue
            # One context per theme: `dark_mode` lives in the user's storage,
            # and a fresh context is the only honest way back to light.
            # Two contexts, not one: an authenticated session answers /login
            # with a redirect to the dashboard, so an artboard drawn signed
            # out has to be shot before anything signs in. `3f` was a picture
            # of `1c` until this split.
            for signed_in in (True, False):
                wanted = [a for a in batch if a.needs_login is signed_in]
                if not wanted:
                    continue
                context = self._browser.new_context()
                page = context.new_page()
                if signed_in:
                    self._login(page)
                    if theme == "dark":
                        self._go_dark(page)
                for artboard in wanted:
                    self._shoot_one(page, artboard)
                context.close()

    def _shoot_one(self, page: Page, artboard: Artboard) -> None:
        out = SHOT_DIR / artboard.id
        out.mkdir(parents=True, exist_ok=True)
        app_shots = []
        for width, height in artboard.viewports:
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{self._base_url}{artboard.route}")
            self._set_drawer(page, artboard.drawer)
            if artboard.prepare is not None:
                getattr(self, f"_prepare_{artboard.prepare}")(page)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(artboard.settle_ms)
            shot = out / f"app-{width}.png"
            page.screenshot(path=str(shot), full_page=True)
            app_shots.append(shot.name)

        spec = ARTBOARD_DIR / f"{artboard.id}.html"
        if not spec.exists():
            raise FidelityError(f"{spec.relative_to(ROOT)} missing - run `split` first")
        spec_page = self._browser.new_page(viewport={"width": 1400, "height": 900})
        spec_page.goto(spec.as_uri())
        spec_page.wait_for_timeout(800)
        spec_page.locator(".dv-card").first.screenshot(path=str(out / "artboard.png"))
        spec_page.close()

        (out / "index.html").write_text(self._index(artboard, app_shots), encoding="utf-8")
        Report(artboard).stamp()
        print(f"[shot] {artboard.id}: {(out / 'index.html').relative_to(ROOT)}")

    def _login(self, page: Page) -> None:
        page.goto(f"{self._base_url}/login")
        page.get_by_label("Username", exact=True).fill(USERNAME)
        page.get_by_label("Password", exact=True).fill(PASSWORD)
        page.get_by_role("button", name="Log in").click()
        page.wait_for_url(lambda url: "/login" not in url, timeout=15000)

    @staticmethod
    def _go_dark(page: Page) -> None:
        page.locator("button:has(i.q-icon:text-is('dark_mode'))").first.click()
        page.wait_for_timeout(600)

    @staticmethod
    def _set_drawer(page: Page, state: str | None) -> None:
        """Put the docked drawer in the state the artboard draws it in.

        The toggle is found by ``data-drawer-mini-toggle``; a shell without one
        (the top-bar shell this pass removes) is shot as it stands.
        """
        toggle = page.locator("[data-drawer-mini-toggle]")
        if state is None or toggle.count() == 0:
            return
        is_mini = page.locator(".q-drawer--mini").count() > 0
        if is_mini != (state == "mini"):
            toggle.first.click()
            page.wait_for_timeout(400)
        # Off the toggle afterwards: the pointer left there opens its tooltip,
        # and a tooltip nobody asked for was being photographed on every
        # screen whose prepare hook did not happen to move the mouse.
        page.mouse.move(0, 0)
        page.wait_for_timeout(250)

    @staticmethod
    def _prepare_ledger(page: Page) -> None:
        """Week separators and a live selection — the two states `2a` draws.

        The grouping toggle and the checkboxes are the app's own controls, so
        the picture is of the ledger a reader would have in front of them,
        not of a ledger dressed up for the camera.
        """
        page.locator(".k-chip-types").first.click()
        page.locator(".q-menu .q-field__native").first.click()
        page.locator(".q-menu .q-item").filter(has_text="Expense").first.click()
        page.keyboard.press("Escape")
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)
        page.get_by_role("button", name="Week", exact=True).click()
        page.wait_for_timeout(600)
        boxes = page.locator(".k-ledger-card tbody .q-checkbox")
        for index in range(min(3, boxes.count())):
            boxes.nth(index).click()
        page.wait_for_timeout(400)

    @staticmethod
    def _prepare_login_error(page: Page) -> None:
        """A failed attempt, which is the state artboard `3f` is drawn in.

        The reserved strip is the point of that artboard: it is what keeps the
        button from moving out from under a second try, and an empty one says
        nothing about whether it works.
        """
        page.get_by_label("Username", exact=True).fill("dawid")
        page.get_by_label("Password", exact=True).fill("not-the-password")
        page.get_by_role("button", name="Log in").click()
        # Off the button before the shutter: a pointer left resting on it
        # photographs its hover state, which is not what the artboard draws.
        page.mouse.move(0, 0)
        page.wait_for_timeout(1200)

    @staticmethod
    def _prepare_rest_pointer(page: Page) -> None:
        """Take the pointer off whatever it landed on.

        A shot taken with the cursor parked over a drawer button photographs
        that button's tooltip, which is not on any artboard.
        """
        page.mouse.move(0, 0)
        page.wait_for_timeout(400)

    @staticmethod
    def _prepare_wizard_setup_open(page: Page) -> None:
        """Open the Setup section, which artboard `3d` draws expanded.

        The page collapses it once all four steps are ticked — the artboard
        annotates that behaviour and still draws the open state, so the shot
        has to click it open.
        """
        cards = page.locator("[data-setup-step]").first
        if cards.is_visible():
            return
        page.locator('[data-section="setup"]').click()
        cards.wait_for(timeout=5000)

    @staticmethod
    def _prepare_report_run(page: Page) -> None:
        """Run the report: artboard `3e` draws the answer, not the empty frame."""
        page.get_by_role("button", name="Run").click()
        page.locator(".k-report-bar-row").first.wait_for(timeout=15000)
        page.mouse.move(0, 0)
        page.wait_for_timeout(400)

    @staticmethod
    def _prepare_calendar_day(page: Page) -> None:
        """Open the 14th: a planned row and a subscription charge, as `3c` draws.

        Today is whatever day the shoot runs on and usually has nothing on
        it, so the sheet would be photographed empty. The 14th is the day the
        seed puts one of each on, which is the sheet the artboard is a
        picture of - both its sections, with something under each.
        """
        page.locator('[data-day$="-14"]').click()
        page.locator(".k-day-panel .k-day-item").first.wait_for(timeout=5000)
        page.mouse.move(0, 0)
        page.wait_for_timeout(400)

    @staticmethod
    def _prepare_realization_tab(page: Page) -> None:
        page.get_by_role("tab", name="Realization").click()

    @staticmethod
    def _prepare_import_mapping(page: Page) -> None:
        page.locator('input[type="file"]').set_input_files(str(ROOT / "test_import.csv"))
        page.locator("[data-page-eyebrow]").filter(has_text="test_import.csv").wait_for(
            timeout=10000
        )
        page.keyboard.press("Escape")
        page.locator('[data-step="3"]').click()
        page.locator('[data-step-panel="3"]').wait_for(timeout=5000)

    @staticmethod
    def _index(artboard: Artboard, app_shots: list[str]) -> str:
        apps = "".join(f'<img src="{name}" alt="app">' for name in app_shots)
        return (
            '<!DOCTYPE html><meta charset="utf-8">'
            f"<title>{artboard.id} - artboard vs app</title>"
            "<style>body{margin:0;font:13px system-ui;background:#ddd}"
            ".pair{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px}"
            "h2{margin:0 0 8px;font-size:13px}img{max-width:100%;display:block;"
            "margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,.3)}</style>"
            '<div class="pair">'
            f'<div><h2>Artboard {artboard.id}</h2><img src="artboard.png" alt="artboard"></div>'
            f"<div><h2>App {artboard.route} ({artboard.theme})</h2>{apps}</div></div>"
        )


# ── cli ──────────────────────────────────────────────────────────────────


class Cli:
    def run(self, argv: list[str]) -> int:
        parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
        commands = parser.add_subparsers(dest="command", required=True)
        commands.add_parser("split", help="cut the canvas into per-artboard files")
        for name, text in (("shoot", "screenshot app and artboard"), ("check", "gate")):
            sub = commands.add_parser(name, help=text)
            sub.add_argument("artboard", help="an artboard id, or 'all'")
            if name == "shoot":
                sub.add_argument(
                    "--base-url",
                    help="shoot an app that is already running (seeded, with the login "
                    f"{USERNAME}/{PASSWORD}) instead of starting an ephemeral one",
                )
        args = parser.parse_args(argv)
        try:
            if args.command == "split":
                for path in CanvasSplitter().run():
                    print(f"[split] {path.relative_to(ROOT)}")
                return 0
            targets = self._targets(args.artboard)
            if args.command == "shoot":
                return self._shoot(targets, args.base_url)
            return self._check(targets)
        except FidelityError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1

    @staticmethod
    def _targets(name: str) -> list[Artboard]:
        if name == "all":
            return list(ARTBOARDS)
        if name not in BY_ID:
            raise FidelityError(f"unknown artboard '{name}'; targets are {', '.join(BY_ID)}")
        return [BY_ID[name]]

    @staticmethod
    def _shoot(targets: list[Artboard], base_url: str | None) -> int:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                if base_url:
                    Shooter(browser, base_url).shoot(targets)
                else:
                    with EphemeralApp() as app:
                        Shooter(browser, app.base_url).shoot(targets)
            finally:
                browser.close()
        return 0

    @staticmethod
    def _check(targets: list[Artboard]) -> int:
        failed = False
        for artboard in targets:
            problems = Report(artboard).problems()
            print(f"[{'FAIL' if problems else ' OK '}] {artboard.id} {artboard.title}")
            for problem in problems:
                print(f"       - {problem}")
            failed = failed or bool(problems)
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(Cli().run(sys.argv[1:]))
