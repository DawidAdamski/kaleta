---
plan_id: setup-zero-config-bootstrap
title: Setup — zero-config first-run for new users
area: setup
effort: medium
roadmap_ref: ../roadmap.md#setup
status: draft
---

# Setup — zero-config first-run for new users

## Intent

The README's "Quick Start" still tells new users to:

1. `uv sync`
2. `uv run alembic upgrade head`
3. (optional) `uv run python scripts/seed.py`
4. `uv run kaleta`

A new person on a clean machine therefore has to know about
Alembic and run a migration command before the app is even
usable. The `/setup` page already covers SQLite path
selection + migration, but only *after* the app starts and
only when `~/.kaleta/config.json` is missing the `db_url`.
For someone who runs `uv run kaleta` without thinking, the
experience should be: app launches, opens the browser,
shows the friendly setup wizard which writes the SQLite file
and runs migrations behind the scenes — never touch a CLI
flag.

This plan closes the remaining gap so step 2 of the README
can be deleted.

## Scope

- **Verify `_preload_config()` already does the right thing** —
  in `src/kaleta/main.py:53` the boot sequence reads
  `~/.kaleta/config.json` and rebinds the engine. If the file
  is missing, it leaves the default in place. Today the
  default is `sqlite:///kaleta.db` (relative to cwd) which is
  the wrong cross-platform place to put a user's database.
  Change the default `db_url` in
  `src/kaleta/config/settings.py` to `None` (un-set). When
  `db_url is None`, `_preload_config()` registers a no-op
  engine that fails fast on access — but every page already
  routes to `/setup` via the `is_configured()` check in
  `views/layout.py:60`. So the only gap is **what happens
  when a non-layout page is hit before setup**.
- **Boot-time guard** — middleware in `views/layout.py` already
  redirects unconfigured users to `/setup`. Audit every
  registered page for routes that bypass `page_layout()`
  (the `/setup` page itself does so, intentionally; the
  `/api/*` routes also do so). Confirm the API gracefully
  rejects requests pre-setup with a 503 + Setup-Required
  body so external callers know to point a human at the
  browser.
- **First-run auto-launch** — when the app starts and
  `is_configured()` is False, open the browser at
  `http://<host>:<port>/setup` directly. NiceGUI exposes
  `ui.run(show=True)`; today we explicitly pass `show=False`.
  Toggle to `show=True` whenever the config is missing, so
  desktop users on Windows / macOS see the wizard without
  manually copying a URL.
- **`/setup` "Just create it" default** — the wizard already
  has a "New database" tab with a default name and folder
  (`~/Documents/kaleta.db`). Add a fast-path button "Use
  recommended location" on the choose-storage screen that
  skips the path picker, runs migrations, and lands on `/`.
  This becomes the documented happy path.
- **Migration runs without the user knowing** — already done
  in `_run_migrations()` (`views/setup.py:22`). Verify it
  works against a non-existent SQLite file — Alembic
  `upgrade head` on a brand-new DB creates the schema from
  scratch via the `op.create_table()` calls. If the chain
  doesn't bottom out, fall back to `Base.metadata.create_all`
  + a `command.stamp("head")` to mark the DB as
  fully-migrated. (The seed script does the same trick.)
- **README rewrite** — collapse steps 2–4 into a single line:
  ```
  uv sync && uv run kaleta
  # Browser opens at http://localhost:8080/setup; pick "Use
  # recommended location" and you're done.
  ```
  Move the manual `alembic upgrade head` and seed instructions
  into a "Power user" subsection further down.
- **Smoke test** — a new pytest in `tests/integration/setup/`
  spins up the app from scratch (no `~/.kaleta` directory,
  no DB file), POSTs to the setup endpoint with
  `db_url=sqlite+aiosqlite:///:memory:`, and asserts the
  app is queryable afterwards.

Out of scope:
- Cloud / Postgres setup — that wizard tab is "coming soon"
  today and stays that way.
- A native installer (`pip install kaleta` / Windows MSI /
  macOS .app) — covered by deployment plans elsewhere.
- Telemetry / opt-in usage stats.

## Acceptance criteria

- A new user runs `uv sync && uv run kaleta` on a clean
  machine. The app boots, the browser opens at `/setup`,
  the wizard offers a one-click "Use recommended location"
  flow that creates `~/Documents/kaleta.db`, runs migrations,
  saves the URL to `~/.kaleta/config.json`, and redirects to
  `/`.
- Visiting any URL before setup completes routes to `/setup`
  (existing behaviour, regression-tested).
- API requests before setup complete with a 503 carrying a
  `setup_required: true` body.
- README's Quick Start is shortened to a single command.
- Re-running the app after setup boots straight into `/`
  without showing the wizard.

## Touchpoints

- `src/kaleta/config/settings.py` — make `db_url` default to
  `None`; document that in the docstring.
- `src/kaleta/main.py` — set `show=True` only when
  `is_configured()` returns False.
- `src/kaleta/views/setup.py` — add the "Use recommended
  location" fast-path button on `step_choose`.
- `src/kaleta/views/layout.py` — already routes to /setup;
  verify no regressions.
- `src/kaleta/api/v1/__init__.py` (or wherever routes are
  mounted) — add a small dependency that returns 503 +
  `setup_required` when `is_configured()` is False.
- `README.md` — quick-start rewrite.
- `tests/integration/setup/test_first_run.py` — new file.

## Open questions

1. **Default location** — `~/Documents/kaleta.db` on
   Windows/macOS, `~/.local/share/kaleta/kaleta.db` on
   Linux? Default: **`~/Documents/kaleta.db`** for now —
   the wizard already uses this folder and it's
   discoverable. Linux users can override on the wizard
   screen.
2. **`show=True` in `app` mode** — the desktop NiceGUI
   `native=True` mode already opens its own window. Don't
   `show=True` in that case; the conditional belongs only
   to web mode.
3. **API 503 body shape** — `{ "error": "setup_required",
   "redirect": "/setup" }`. Document under the OpenAPI
   spec.
4. **Migration vs `create_all` for first run** — Alembic
   `upgrade head` is the canonical answer; `create_all` is
   the safety net. Verify on a fresh DB before deciding
   which to ship.

## Implementation notes
_Filled in as work progresses._
