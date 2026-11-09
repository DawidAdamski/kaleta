#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hold the restyle to its artboards: split the canvas, shoot both sides, gate on a report.

The first restyle pass was planned from the handoff's prose and closed with
``[manual]`` criteria nobody ran, so no step ever put the rendered app next
to the artboard it was copying. This script is that step.

    uv run python scripts/restyle_fidelity.py split
    uv run python scripts/restyle_fidelity.py shoot 2a        # or: all
    uv run python scripts/restyle_fidelity.py critique 2a     # or: all
    uv run python scripts/restyle_fidelity.py check 2a        # or: all

``split``     cuts ``Kaleta Dashboard.dc.html`` into one static file per target
              artboard under ``docs/design/restyle/artboards/``. Each is 10-25 KB:
              small enough to read whole, which the 300 KB canvas is not.
``shoot``     starts an ephemeral, seeded Kaleta (nothing of the developer's is
              touched), screenshots the app and the artboard at the artboard's
              width and theme into ``.fidelity/<id>/``, measures the difference
              between the two on a 4x4 grid, and stamps the report with the
              tiles and a hash of the screen's source files.
``critique``  hands the two screenshots, the artboard and the screen's view
              sources to a fresh, read-only ``claude -p`` session that did not
              build the screen, and writes the report rows it returns.
``check``     is the executable acceptance criterion: the report exists, was
              written by the critic against the screenshots on disk and the
              code as it is now, has no ``open`` row, every ``deviation`` says
              why, and the tiles that differ most are named by a deviation.

The implementer shoots and asks for a critique; it does not write the report.
That was self-assessment (ADR-39), and the screens drifted under it.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

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
#: ``scripts/reset_demo.py``'s defaults: the demo family's login and passphrase.
EMAIL = "demo@kaleta.app"
PASSWORD = "demo-kaleta"
DATA_PASSPHRASE = "demo-kaleta-data"
#: The developer's PostgreSQL (``./scripts/test_db.sh up``) unless
#: ``KALETA_DB_URL`` names another; the shoot gets a database of its own on it.
DEFAULT_DB_URL = "postgresql+asyncpg://kaleta:kaleta@127.0.0.1:55432/kaleta"
MIN_REPORT_ROWS = 8
STATUSES = ("match", "deviation", "open")
#: The owner's profile; ``[fidelity] tile_threshold`` is read from it.
PROFILE = ROOT / "docs" / "harness" / "profile.toml"
#: The run log the gate and the critic write (``gate-audit-log``).
HARNESS_DIR = ROOT / "scripts" / "harness"
ACTIVE_PLAN = ROOT / ".claude" / "state" / "active-plan"
#: Rows A-D top to bottom, columns 1-4 left to right: ``A1`` is top left.
GRID = 4
TILE_NAMES = tuple(f"{'ABCD'[r]}{c + 1}" for r in range(GRID) for c in range(GRID))
#: Until the owner sets ``tile_threshold``, the worst this many must be named.
WORST_REQUIRED = 3
#: ``KALETA_FIDELITY_MODEL``, else the review critic's ``KALETA_REVIEW_MODEL``.
DEFAULT_CRITIC_MODEL = "sonnet"


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


# ── measure ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TileMeasure:
    """Mean absolute difference, in percent of full scale, per tile and overall."""

    whole: float
    tiles: dict[str, float]

    def worst(self, n: int) -> list[str]:
        """The ``n`` tiles that differ most (ties broken by name); never a 0.00 tile."""
        ranked = sorted(
            (name for name, value in self.tiles.items() if value > 0),
            key=lambda name: (-self.tiles[name], name),
        )
        return ranked[:n]

    def above(self, threshold: float) -> list[str]:
        return [name for name in TILE_NAMES if self.tiles[name] > threshold]

    def header_tiles(self) -> str:
        return " ".join(f"{name}={self.tiles[name]:.2f}" for name in TILE_NAMES)


class TileDiff:
    """A number for the difference between artboard and app that needs nobody's eyes.

    The app is brought to the artboard's width (keeping its aspect ratio) and
    laid over the artboard from the top: the artboard's frame is what is
    compared, so the rows of a full-page app shot that run on below the card
    are not on the artboard and do not count, and an app shorter than the card
    is padded with white, which counts against it. That frame is split into a
    4x4 grid. Pixels are compared in RGB; the value is the mean absolute
    channel difference as a percentage of 255, so 0 is identical and 100 is
    inverse.
    """

    @staticmethod
    def measure(artboard_png: Path, app_png: Path) -> TileMeasure:
        from PIL import Image, ImageChops, ImageStat

        with Image.open(artboard_png) as raw_spec, Image.open(app_png) as raw_app:
            spec = raw_spec.convert("RGB")
            app = raw_app.convert("RGB")
        width, height = spec.size
        if width < GRID or height < GRID or app.width < 1 or app.height < 1:
            raise FidelityError(f"{artboard_png.parent.name}: a screenshot is too small to grid")
        scaled = app.resize((width, max(1, round(app.height * width / app.width))))
        framed = Image.new("RGB", (width, height), "white")
        framed.paste(scaled.crop((0, 0, width, min(height, scaled.height))), (0, 0))

        def mean(a: Any, b: Any) -> float:
            stat = ImageStat.Stat(ImageChops.difference(a, b))
            return round(sum(stat.mean) / len(stat.mean) / 255 * 100, 2)

        tiles: dict[str, float] = {}
        for index, name in enumerate(TILE_NAMES):
            row, col = divmod(index, GRID)
            box = (
                col * width // GRID,
                row * height // GRID,
                (col + 1) * width // GRID,
                (row + 1) * height // GRID,
            )
            tiles[name] = mean(spec.crop(box), framed.crop(box))
        return TileMeasure(mean(spec, framed), tiles)


# ── report ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Row:
    """One compared element, as the critic wrote it."""

    element: str
    artboard: str
    app: str
    status: str
    note: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    """``path`` relative to the repo when it is inside it (the critic runs there)."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def _cell(text: str) -> str:
    """A value fit for one markdown table cell."""
    return re.sub(r"\s+", " ", text.replace("|", "\\|")).strip()


def fidelity_threshold(profile: Path = PROFILE) -> float | None:
    """``[fidelity] tile_threshold`` from the owner's profile; ``None`` while unset."""
    if not profile.exists():
        return None
    try:
        raw = tomllib.loads(profile.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise FidelityError(f"{profile.name} is not valid TOML: {exc}") from exc
    value = raw.get("fidelity", {}).get("tile_threshold")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FidelityError("[fidelity] tile_threshold in the profile must be a number")
    return float(value)


@dataclass
class Report:
    """``docs/design/restyle/fidelity/<id>.md`` — what was compared, and the verdict."""

    artboard: Artboard
    report_dir: Path = REPORT_DIR
    shot_dir: Path = SHOT_DIR
    profile: Path = PROFILE
    path: Path = field(init=False)

    _TILE_RE = re.compile(r"\b([A-D][1-4])\b")

    def __post_init__(self) -> None:
        self.path = self.report_dir / f"{self.artboard.id}.md"

    # ── what is on disk ──

    @property
    def shots(self) -> Path:
        return self.shot_dir / self.artboard.id

    def shot_files(self) -> list[Path]:
        """The pictures the critic looks at: the artboard and every app viewport."""
        names = ["artboard.png", *(f"app-{w}.png" for w, _ in self.artboard.viewports)]
        return [self.shots / name for name in names]

    def shot_hashes(self) -> dict[str, str]:
        missing = [p.name for p in self.shot_files() if not p.exists()]
        if missing:
            raise FidelityError(
                f"{self.artboard.id}: no {', '.join(missing)} in "
                f"{self.shots.relative_to(self.shot_dir.parent)} - run `shoot {self.artboard.id}`"
            )
        return {p.name: _sha256(p) for p in self.shot_files()}

    def measure(self) -> TileMeasure:
        """Artboard against the app at the artboard's own (first) viewport."""
        self.shot_hashes()  # raises with the right advice when a picture is missing
        width = self.artboard.viewports[0][0]
        return TileDiff.measure(self.shots / "artboard.png", self.shots / f"app-{width}.png")

    def required_tiles(self, measure: TileMeasure) -> list[str]:
        threshold = fidelity_threshold(self.profile)
        if threshold is None:
            return measure.worst(WORST_REQUIRED)
        return measure.above(threshold)

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

    def source_files(self) -> list[Path]:
        files: list[Path] = []
        for source in (*SHELL_SOURCES, *self.artboard.sources):
            root = ROOT / source
            files.extend(sorted(root.rglob("*.py")) if root.is_dir() else [root])
        return files

    # ── writing ──

    def stamp(self, measure: TileMeasure) -> None:
        """Record what code and what difference the screenshots show; create the report if new."""
        self.report_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.date.today().isoformat()
        if not self.path.exists():
            self.path.write_text(self._template(today, measure), encoding="utf-8")
            return
        text = self.path.read_text(encoding="utf-8")
        for key, value in (
            ("views_hash", self.source_hash()),
            ("shot_at", today),
            ("diff_whole", f"{measure.whole:.2f}"),
            ("tiles", measure.header_tiles()),
        ):
            text = self._set_header(text, key, value)
        self.path.write_text(text, encoding="utf-8")

    def write_critique(self, result: CriticResult, measure: TileMeasure) -> None:
        """Replace the report with the critic's rows, under a header that says who and on what."""
        if not self.path.exists():
            raise FidelityError(f"no report at {self.path.name} - run `shoot {self.artboard.id}`")
        old = self.path.read_text(encoding="utf-8")
        a = self.artboard
        header = {
            "artboard": a.id,
            "views_hash": self.header(old).get("views_hash", self.source_hash()),
            "shot_at": self.header(old).get("shot_at", ""),
            "author": "critic",
            "critic_run": result.run_id,
            "critic_model": result.model,
            "critiqued_at": datetime.date.today().isoformat(),
            "shots": " ".join(f"{name}={sha}" for name, sha in result.shots.items()),
            "diff_whole": f"{measure.whole:.2f}",
            "tiles": measure.header_tiles(),
        }
        rows = "\n".join(
            f"| {n} | {_cell(r.element)} | {_cell(r.artboard)} | {_cell(r.app)} "
            f"| {r.status} | {_cell(r.note)} |"
            for n, r in enumerate(result.rows, start=1)
        )
        self.path.write_text(
            "---\n" + "".join(f"{key}: {value}\n" for key, value in header.items()) + "---\n\n"
            f"# Fidelity report - {a.id} {a.title}\n\n"
            f"Spec: [`artboards/{a.id}.html`](../artboards/{a.id}.html). "
            f"Pictures: `.fidelity/{a.id}/index.html` after `shoot {a.id}`.\n\n"
            "Written by `restyle_fidelity.py critique`: a read-only critic session that\n"
            "saw the two screenshots, the artboard and the view sources, and not the\n"
            "conversation that built the screen. `shots` are the sha256 of the pictures\n"
            "it saw; `tiles` the mean absolute difference per tile (rows A-D top to\n"
            "bottom, columns 1-4 left to right, percent of full scale). Do not edit by\n"
            "hand - shoot and critique again.\n\n"
            "| # | Element | Artboard | App | Status | Note |\n"
            "|---|---|---|---|---|---|\n"
            f"{rows}\n",
            encoding="utf-8",
        )

    # ── checking ──

    def problems(self) -> list[str]:
        if not self.path.exists():
            return [f"no report at {self.path.name} - run `shoot {self.artboard.id}`"]
        text = self.path.read_text(encoding="utf-8")
        head = self.header(text)
        found: list[str] = []
        if head.get("views_hash") != self.source_hash():
            found.append("the screen's source changed since the last `shoot` - shoot and re-review")
        if head.get("author") != "critic":
            found.append(
                f"author is '{head.get('author', 'missing')}', not 'critic' - "
                f"run `critique {self.artboard.id}`; the implementer does not write the report"
            )
        found.extend(self._shot_problems(head))
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

    def _shot_problems(self, head: dict[str, str]) -> list[str]:
        try:
            on_disk = self.shot_hashes()
            measure = self.measure()
        except FidelityError as exc:
            return [str(exc)]
        found: list[str] = []
        seen = dict(pair.split("=", 1) for pair in head.get("shots", "").split() if "=" in pair)
        if seen != on_disk:
            found.append(
                "the screenshots on disk are not the ones the critic saw - "
                f"run `critique {self.artboard.id}` on the current shots"
            )
        if head.get("tiles") != measure.header_tiles():
            found.append("the report's tiles do not match the screenshots - shoot and critique")
        named = self.named_tiles(self.path.read_text(encoding="utf-8"))
        found.extend(
            f"tile {tile} differs by {measure.tiles[tile]:.2f}% and no deviation row names it"
            for tile in self.required_tiles(measure)
            if tile not in named
        )
        return found

    @classmethod
    def named_tiles(cls, text: str) -> set[str]:
        """Tiles a ``deviation`` row names (``tile B3``, ``tiles B3, C4``)."""
        named: set[str] = set()
        for _, element, status, note in cls._rows(text):
            cells = f"{element} {note}"
            if status == "deviation" and re.search(r"\btiles?\b", cells, flags=re.I):
                named.update(cls._TILE_RE.findall(cells))
        return named

    @staticmethod
    def header(text: str) -> dict[str, str]:
        match = re.match(r"---\n(.*?)\n---\n", text, flags=re.S)
        if match is None:
            return {}
        pairs = (line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
        return {key.strip(): value.strip() for key, value in pairs}

    @staticmethod
    def _set_header(text: str, key: str, value: str) -> str:
        line = f"{key}: {value}"
        if re.search(rf"^{key}:.*$", text, flags=re.M):
            return re.sub(rf"^{key}:.*$", lambda _m: line, text, count=1, flags=re.M)
        return re.sub(r"\A(---\n.*?\n)(---\n)", lambda m: f"{m[1]}{line}\n{m[2]}", text, flags=re.S)

    @staticmethod
    def _rows(text: str) -> list[tuple[str, str, str, str]]:
        rows = []
        for line in text.splitlines():
            cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
            if len(cells) == 6 and cells[0].isdigit():
                rows.append((cells[0], cells[1], cells[4].lower(), cells[5]))
        return rows

    def _template(self, today: str, measure: TileMeasure) -> str:
        a = self.artboard
        return (
            "---\n"
            f"artboard: {a.id}\n"
            f"views_hash: {self.source_hash()}\n"
            f"shot_at: {today}\n"
            "author: pending\n"
            f"diff_whole: {measure.whole:.2f}\n"
            f"tiles: {measure.header_tiles()}\n"
            "---\n\n"
            f"# Fidelity report - {a.id} {a.title}\n\n"
            f"Shot, not yet critiqued. Run `restyle_fidelity.py critique {a.id}`.\n"
        )


# ── critique ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CriticResult:
    run_id: str
    model: str
    rows: list[Row]
    shots: dict[str, str]


#: Runs one critic session: (prompt, model, allowed tools, raw-output path) -> (payload, run id).
CriticRunner = Callable[[str, str, str, Path], tuple[dict[str, Any], str]]

CRITIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "minItems": MIN_REPORT_ROWS,
            "items": {
                "type": "object",
                "properties": {
                    "element": {"type": "string"},
                    "artboard": {"type": "string"},
                    "app": {"type": "string"},
                    "status": {"type": "string", "enum": list(STATUSES)},
                    "note": {"type": "string"},
                },
                "required": ["element", "artboard", "app", "status", "note"],
            },
        }
    },
    "required": ["rows"],
}

CRITIC_TEMPLATE = """You are an independent design critic. You did NOT build this screen and you
do not fix it. Compare a running screen of the Kaleta app with the artboard it
was built from, and report what you observe. Do not edit anything.

Artboard {id} - {title}. App route {route}, {theme} theme, drawn at {width}px.

Read these, and only these:
  {artboard_png}   the artboard, rendered
  {app_pngs}   the app, screenshotted at each viewport
  {artboard_html}   the artboard's markup: element order, nesting and every
      inline value are the spec; its text is sample data and its SVG charts
      are sketches
  the screen's view sources (to name the code behind a value):
{sources}

A machine compared the two pictures on a 4x4 grid (rows A-D top to bottom,
columns 1-4 left to right; mean absolute difference, percent of full scale;
the whole picture: {whole}):
{tiles}
These tiles must each be named by a "deviation" row that explains what differs
there (write "tile B3" in the element or the note): {required}.
If what differs in such a tile is a real mismatch rather than an explainable
difference, report it as "open" AND name the tile in a deviation row that says
which open row it belongs to.

Write at least {min_rows} rows, one per element you compared, in the artboard's
own terms ("Hero figure", "Pace bar", "Overdue strip"), not generic ones.
"artboard" and "app" hold the values you observed on each side (sizes, weights,
colours, order, spacing), never "ok". "status" is:
  "match"      the app shows what the artboard draws
  "deviation"  it differs for a reason the note states: sample vs seeded data,
               a sketch vs a real chart, a Quasar limit, an owner decision.
               "Close enough" is not a reason.
  "open"       it differs and should be fixed
Return ONLY the JSON object the schema asks for.
"""


#: Nothing that writes, runs or reaches out; the earlier reports are not its to read.
CRITIC_DENIED = "Bash,Edit,Write,MultiEdit,NotebookEdit,WebFetch,WebSearch,Task,Agent"


class Critic:
    """A fresh ``claude -p`` that writes the report rows from the pictures, not from memory."""

    def __init__(self, model: str | None = None, runner: CriticRunner | None = None) -> None:
        self.model = (
            model
            or os.environ.get("KALETA_FIDELITY_MODEL")
            or os.environ.get("KALETA_REVIEW_MODEL")
            or DEFAULT_CRITIC_MODEL
        )
        self._runner = runner or self._claude

    def critique(self, report: Report) -> CriticResult:
        shots = report.shot_hashes()
        measure = report.measure()
        prompt = self.prompt(report, measure)
        payload, run_id = self._runner(
            prompt, self.model, self.allowed_tools(report), report.shots / "critic-raw.json"
        )
        rows = self._rows(payload, report.artboard.id)
        # The pictures must not have changed under the critic.
        if report.shot_hashes() != shots:
            raise FidelityError(f"{report.artboard.id}: screenshots changed during the critique")
        result = CriticResult(run_id, self.model, rows, shots)
        report.write_critique(result, measure)
        return result

    @staticmethod
    def prompt(report: Report, measure: TileMeasure) -> str:
        a = report.artboard
        app_pngs = [p for p in report.shot_files() if p.name.startswith("app-")]
        tiles = "\n".join(
            "  " + "  ".join(f"{name} {measure.tiles[name]:6.2f}" for name in TILE_NAMES[r : r + 4])
            for r in range(0, len(TILE_NAMES), GRID)
        )
        return CRITIC_TEMPLATE.format(
            id=a.id,
            title=a.title,
            route=a.route,
            theme=a.theme,
            width=a.viewports[0][0],
            artboard_png=_rel(report.shots / "artboard.png"),
            app_pngs="\n  ".join(_rel(p) for p in app_pngs),
            artboard_html=_rel(ARTBOARD_DIR / f"{a.id}.html"),
            sources="\n".join(f"    {_rel(p)}" for p in report.source_files()),
            whole=f"{measure.whole:.2f}",
            tiles=tiles,
            required=", ".join(report.required_tiles(measure)) or "none",
            min_rows=MIN_REPORT_ROWS,
        )

    @staticmethod
    def allowed_tools(report: Report) -> str:
        """Read, and only on the pictures, the artboard and the screen's sources."""
        paths = [f"{report.shots}/**", str(ARTBOARD_DIR / f"{report.artboard.id}.html")]
        for source in (*SHELL_SOURCES, *report.artboard.sources):
            root = ROOT / source
            paths.append(f"{root}/**" if root.is_dir() else str(root))
        return ",".join(f"Read(/{path})" for path in paths)

    @staticmethod
    def _rows(payload: dict[str, Any], artboard_id: str) -> list[Row]:
        raw = payload.get("rows")
        if not isinstance(raw, list):
            raise FidelityError(f"{artboard_id}: the critic returned no rows")
        rows = []
        for item in raw:
            if not isinstance(item, dict):
                raise FidelityError(f"{artboard_id}: the critic returned a malformed row")
            status = str(item.get("status", "")).strip().lower()
            if status not in STATUSES:
                raise FidelityError(f"{artboard_id}: the critic returned status '{status}'")
            rows.append(
                Row(
                    element=str(item.get("element", "")),
                    artboard=str(item.get("artboard", "")),
                    app=str(item.get("app", "")),
                    status=status,
                    note=str(item.get("note", "")),
                )
            )
        if len(rows) < MIN_REPORT_ROWS:
            raise FidelityError(
                f"{artboard_id}: the critic compared {len(rows)} elements; "
                f"at least {MIN_REPORT_ROWS} expected"
            )
        return rows

    @staticmethod
    def _claude(prompt: str, model: str, tools: str, raw_out: Path) -> tuple[dict[str, Any], str]:
        if not shutil.which("claude"):
            raise FidelityError("the claude CLI is not on PATH; `critique` needs it")
        env = {
            k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
        }
        # A Claude Code session in this repo loads the project's hooks; this
        # tells the Stop hook it is a critic, not the implementer.
        env["KALETA_CRITIC_SESSION"] = "1"
        cmd = [
            "claude", "-p", prompt,
            "--model", model,
            "--permission-mode", "dontAsk",
            "--allowedTools", tools,
            "--disallowedTools", f"{CRITIC_DENIED},Read(/{REPORT_DIR}/**)",
            "--max-turns", "30",
            "--output-format", "json",
            "--json-schema", json.dumps(CRITIC_SCHEMA),
        ]  # fmt: skip
        done = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, errors="replace", env=env, check=False
        )
        raw_out.write_text(done.stdout or done.stderr, encoding="utf-8")
        try:
            raw = json.loads(done.stdout)
        except json.JSONDecodeError:
            raw = {}
        payload = raw.get("structured_output") if isinstance(raw, dict) else None
        if payload is None and isinstance(raw, dict) and isinstance(raw.get("result"), str):
            match = re.search(r"\{.*\}", raw["result"], re.S)
            try:
                payload = json.loads(match.group(0)) if match else None
            except json.JSONDecodeError:
                payload = None
        if not isinstance(payload, dict):
            raise FidelityError(
                f"the critic's output could not be parsed - see {raw_out.relative_to(ROOT)}"
            )
        run_id = str(raw.get("session_id") or uuid.uuid4())
        return payload, run_id


# ── run log ──────────────────────────────────────────────────────────────


class RunLog:
    """One ``fidelity`` record per checked artboard, in the plan's hash-chained run log."""

    def __init__(self, root: Path = ROOT) -> None:
        self._root = root

    def plan_id(self) -> str | None:
        """The armed plan, else the ``plan/<id>`` branch; ``None`` outside a plan."""
        active = self._root / ".claude" / "state" / "active-plan"
        if active.exists() and active.read_text(encoding="utf-8").strip():
            return active.read_text(encoding="utf-8").strip()
        done = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self._root,
            capture_output=True,
            text=True,
            check=False,
        )
        branch = done.stdout.strip()
        return branch.removeprefix("plan/") if branch.startswith("plan/") else None

    def record(self, report: Report, problems: list[str]) -> str | None:
        plan_id = self.plan_id()
        if plan_id is None:
            return None
        if str(HARNESS_DIR) not in sys.path:
            sys.path.insert(0, str(HARNESS_DIR))
        import gate_log

        head = (
            report.header(report.path.read_text(encoding="utf-8")) if report.path.exists() else {}
        )
        gate_log.append(
            self._root,
            plan_id,
            "fidelity",
            {
                "artboard": report.artboard.id,
                "ok": not problems,
                "problems": problems,
                "author": head.get("author"),
                "critic_run": head.get("critic_run"),
                "critic_model": head.get("critic_model"),
                "shots": head.get("shots"),
                "diff_whole": head.get("diff_whole"),
                "tiles": head.get("tiles"),
                "tile_threshold": fidelity_threshold(report.profile),
            },
        )
        return plan_id


# ── shoot ────────────────────────────────────────────────────────────────


def _fresh_database(server_url: str) -> str:
    """``<database>_fidelity`` on ``server_url``'s server, dropped and created again."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    base = make_url(server_url)
    database = f"{base.database}_fidelity"
    engine = create_engine(
        base.set(drivername="postgresql+psycopg2", query={}), isolation_level="AUTOCOMMIT"
    )
    try:
        with engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{database}"'))
    finally:
        engine.dispose()
    return base.set(database=database).render_as_string(hide_password=False)


class EphemeralApp:
    """A seeded Kaleta on its own port, HOME and database — the e2e recipe."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="kaleta-fidelity-")
        self._proc: subprocess.Popen[bytes] | None = None
        self._log: BinaryIO | None = None
        self.base_url = f"http://127.0.0.1:{PORT}"

    def __enter__(self) -> EphemeralApp:
        home = Path(self._tmp.name)
        db_url = _fresh_database(os.environ.get("KALETA_DB_URL") or DEFAULT_DB_URL)
        env = {
            **os.environ,
            "HOME": str(home),
            "KALETA_DB_URL": db_url,
            "KALETA_PORT": str(PORT),
            "KALETA_HOST": "127.0.0.1",
            "KALETA_AUTH_BACKEND": "local",
            "KALETA_DATA_PASSPHRASE": DATA_PASSPHRASE,
        }
        env.pop("KALETA_DEMO", None)  # the demo banner is not on any artboard
        # The demo family first (its login, its schema, its data passphrase),
        # then `scripts/seed.py` fills that schema, so the artboards are drawn
        # on a ledger with payees, tags, planned transactions, subscriptions
        # and physical assets in it.
        self._run(["uv", "run", "python", "scripts/migrate_tenants.py"], env)
        self._run(["uv", "run", "python", "scripts/reset_demo.py", "--force", "--no-seed"], env)
        self._run(["uv", "run", "python", "scripts/seed.py"], env)
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
                with urllib.request.urlopen(f"{self.base_url}/health", timeout=2) as response:
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
        report = Report(artboard)
        report.stamp(report.measure())
        print(f"[shot] {artboard.id}: {(out / 'index.html').relative_to(ROOT)}")

    def _login(self, page: Page) -> None:
        page.goto(f"{self._base_url}/login")
        page.get_by_label("E-mail", exact=True).fill(EMAIL)
        page.get_by_label("Password", exact=True).fill(PASSWORD)
        page.get_by_role("button", name="Log in").click()
        page.wait_for_url(lambda url: "/login" not in url, timeout=15000)
        if "/unlock" in page.url:
            page.get_by_label("Data passphrase", exact=True).fill(DATA_PASSPHRASE)
            page.get_by_role("button", name="Unlock", exact=True).click()
            page.wait_for_url(lambda url: "/unlock" not in url, timeout=30000)

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
        page.get_by_label("E-mail", exact=True).fill("dawid@example.com")
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
        for name, text in (
            ("shoot", "screenshot app and artboard, measure the tiles"),
            ("critique", "have an independent critic write the report"),
            ("check", "gate"),
        ):
            sub = commands.add_parser(name, help=text)
            sub.add_argument("artboard", help="an artboard id, or 'all'")
            if name == "shoot":
                sub.add_argument(
                    "--base-url",
                    help="shoot an app that is already running (seeded, with the login "
                    f"{EMAIL}/{PASSWORD}) instead of starting an ephemeral one",
                )
            if name == "critique":
                sub.add_argument(
                    "--model",
                    help="the critic's model (default: $KALETA_FIDELITY_MODEL, "
                    f"$KALETA_REVIEW_MODEL, else {DEFAULT_CRITIC_MODEL})",
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
            if args.command == "critique":
                return self._critique(targets, args.model)
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
    def _critique(targets: list[Artboard], model: str | None) -> int:
        critic = Critic(model)
        for artboard in targets:
            report = Report(artboard)
            result = critic.critique(report)
            opened = sum(row.status == "open" for row in result.rows)
            print(
                f"[critique] {artboard.id}: {len(result.rows)} rows, {opened} open "
                f"({result.model}, run {result.run_id}) -> {report.path.relative_to(ROOT)}"
            )
        return 0

    @staticmethod
    def _check(targets: list[Artboard]) -> int:
        failed = False
        log = RunLog()
        for artboard in targets:
            report = Report(artboard)
            problems = report.problems()
            print(f"[{'FAIL' if problems else ' OK '}] {artboard.id} {artboard.title}")
            for problem in problems:
                print(f"       - {problem}")
            failed = failed or bool(problems)
            if log.record(report, problems) is None:
                print("       (no plan armed and not on a plan/ branch: no run-log record)")
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(Cli().run(sys.argv[1:]))
