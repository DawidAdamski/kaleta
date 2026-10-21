---
status: in-progress
issue: (none — chore from docs/plans/chores.md)
---

# Rebuild `_sync_url` structurally instead of `str.replace`

## Intent
`setup_service._sync_url` translates an async DB URL into the sync
(`psycopg2`) URL used by Alembic/sync engines. It swapped the driver with a
whole-string `str.replace("+asyncpg", "+psycopg2")`, which corrupts any
password that happens to contain the substring `+asyncpg`. Rebuild the URL
structurally with `make_url(...).set(drivername=...)` so the password is never
touched, while keeping the existing asyncpg→psycopg2 SSL-argument translation.

## Scope
- `src/kaleta/services/setup_service.py` — only the body of `_sync_url`
  (signature `(_: str) -> str` and semantics unchanged).
- `tests/unit/services/test_setup_service.py` — new unit test for `_sync_url`.

Not in scope: callers of `_sync_url`, the SSL mapping dictionary values (kept
as-is), any other function in the module.

## Acceptance
- A password containing `+asyncpg` survives the rewrite intact.
- The driver is switched to the sync driver (`postgresql+psycopg2`).
- `ssl=require` → `sslmode=require`; `ssl=true`/`ssl=false` →
  `sslmode=require`/`sslmode=disable`; a URL with no SSL arg stays SSL-free.
- Gates green: `ruff check`, `ruff format --check`, `mypy src/`,
  `lint-imports`, `pytest -m "not slow"`, `spec_coverage.py`.

## Touchpoints
- `src/kaleta/services/setup_service.py::_sync_url`
- `tests/unit/services/test_setup_service.py`

## BDD
No new `KAL-` scenario. This is an internal correctness fix to a private
helper (`_sync_url`) with no observable change to any user-facing flow — the
produced sync URL still connects the same way for every URL the app actually
emits. Per Working Agreement rule 5 (new *user-facing behaviour* = new
scenario), a unit test at the helper level is the correct coverage.

## Implementation notes
- SQLAlchemy `URL` is immutable; `make_url(url).set(drivername=...)` returns a
  new URL and parses the password structurally (verified: a literal `+` in the
  password round-trips through `render_as_string(hide_password=False)`).
- Forcing `drivername="postgresql+psycopg2"` also fixes the bare
  `postgresql://` case (psycopg3 under SQLAlchemy 2.1, which Kaleta does not
  install) — consistent with the existing docstring. Non-postgresql URLs are
  returned unchanged, matching the previous behaviour.
