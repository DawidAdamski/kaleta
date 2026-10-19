---
plan_id: api-docs-gated
title: Gate /api-docs behind a flag so the schema is not handed to every client
area: security (api)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Gate /api-docs behind a flag so the schema is not handed to every client

## Intent
Security assessment finding **F-2** (`docs/security/assessment-2026-10-12.md`):
`/api-docs` (Swagger UI) and `/api-docs/openapi.json` are served
**unconditionally** (`src/kaleta/main.py`), so any unauthenticated client gets
the full API schema. Low severity — the API itself is fully auth-gated — but
the always-on schema eases enumeration, and once the instance hosts several
families there is no reason to publish the surface map to the open internet.

This slice gates the docs behind a setting that **defaults to `debug`**:
- development (`KALETA_DEBUG=true`): docs on, as today;
- a production-shaped run (debug off): docs **off** by default (404);
- a self-hoster who wants them can force either way with `KALETA_API_DOCS`.

The API endpoints and their auth are unchanged — only whether the *schema and
the Swagger page* are published.

## Scope
- **`src/kaleta/config/settings.py`**: add `api_docs: bool | None = None`
  (env `KALETA_API_DOCS`) and a resolved property
  `api_docs_enabled -> bool` = the override when set, else `self.debug`.
- **`src/kaleta/api/docs.py`** (new): move the OpenAPI-spec builder and the two
  route definitions out of `main.py` into `build_api_spec()` (cached) and
  `mount_api_docs(app) -> bool`, which mounts `/api-docs` + `/api-docs/openapi.json`
  **only when `settings.api_docs_enabled`** and returns whether it did. Keeping
  it a function on an app makes it testable against a fresh `FastAPI()`.
- **`src/kaleta/main.py`**: delegate to `mount_api_docs(nicegui_app)` inside
  `_register_api()`; drop the inline route defs and the module-level
  `_openapi_spec` cache (now in `api/docs.py`).
- **`src/kaleta/views/layout.py`**: the sidebar's "API docs" link follows the
  same flag — it is rendered only when `settings.api_docs_enabled`, so a
  production run with the docs gated off does not show a dead link to a 404
  (the hairline separator shows only when the API-docs or admin item does).
- **`docs/bdd.md`**: add **KAL-SEC-002 @automated** — the OpenAPI docs are
  gated (off in a production-shaped run unless opted in).
- **`docs/security/assessment-2026-10-12.md`**: flip F-2 to **Fixed** with the
  flag and the KAL-SEC-002 reference; update the recon row.
- Tests: `tests/integration/test_api_docs.py` (new) — docs 404 when debug off
  and `api_docs` unset; 200 when `api_docs=True`; 200 when debug on; the
  OpenAPI JSON is a valid schema when served.

### Resolution (binding)
- `settings.api_docs is None` → follow `settings.debug`.
- `settings.api_docs is True/False` → honour it verbatim (opt-in in prod, or
  opt-out in dev).
- When gated off, **both** `/api-docs` and `/api-docs/openapi.json` are absent
  (404), not just the HTML page — the JSON is the schema and must not leak.

**Not in scope (binding):**
- No change to the API routes, their auth, or the error contract.
- No auth gate *on* the docs (the choice is on/off by environment, not a login
  wall on Swagger); an authenticated-docs mode is a possible later slice.
- F-3 (cookie `Secure` warning) and F-4 (upload byte cap) are their own slices.

## Acceptance criteria
- `uv run pytest tests/integration/test_api_docs.py -q`
- `./scripts/verify.sh --e2e` (the sidebar link in `src/kaleta/views/layout.py`
  is gated too → view change → e2e gate, rule 8)
- Fail-on-old: the new test asserts `/api-docs/openapi.json` is 404 when debug
  is off and `api_docs` unset; on the pre-change code it is served
  unconditionally (200) → the test fails. Verified by a backup swap.

## Touchpoints
- `src/kaleta/config/settings.py`
- `src/kaleta/api/docs.py` (new)
- `src/kaleta/main.py`
- `src/kaleta/views/layout.py` (sidebar "API docs" link gated by the flag)
- `tests/integration/test_api_docs.py` (new)
- `tests/integration/test_openapi.py` (imports the spec builder from its new home)
- `docs/bdd.md` (KAL-SEC-002 added; KAL-API-003 reworded)
- `docs/tech-stack.md` (the `KALETA_API_DOCS` env var)
- `docs/security/assessment-2026-10-12.md`
- `docs/plans/chores.md` (the security chore note)

## Open questions
- None blocking. Owner chose "do all three" (F-2..F-4); the default-follows-debug
  resolution keeps dev unchanged and closes the production leak without a new
  required knob.

## Implementation notes
- **Default follows `debug`.** `settings.api_docs_enabled` returns `settings.debug`
  when `api_docs` is unset, so development is unchanged (docs on) and a
  production-shaped run (debug off) gets them off without a new required knob.
  `KALETA_API_DOCS=true/false` forces either way (a self-hoster who wants the
  docs in prod, or a dev who wants them off).
- **Both routes are gated, not just the page.** `mount_api_docs` returns before
  defining either route, so `/api-docs/openapi.json` (the schema itself) is 404
  when gated, not only the Swagger HTML. Gating only the page would still leak
  the surface map.
- **The spec builder moved.** `main._api_spec` / `main._openapi_spec` became
  `kaleta.api.docs.build_api_spec` (same cached logic) so the mount logic is
  testable against a fresh `FastAPI()`. `tests/integration/test_openapi.py` and
  `main.py` now import it from there; `main.py` dropped the now-unused `Any`,
  `HTMLResponse` and `get_swagger_ui_html` imports. No circular import:
  `kaleta.api.docs` imports `create_api_router` from `kaleta.api`, which does not
  import `docs`.
- **The sidebar link is gated too (scope extension).** `views/layout.py` showed
  an always-visible "API docs" item; left as-is it would be a dead link to a 404
  in a gated production run. It now renders only when `settings.api_docs_enabled`,
  and the hairline separator above it shows only when the API-docs or the admin
  item does (no dangling separator). Because this touches `src/kaleta/views/`,
  the acceptance gate is `./scripts/verify.sh --e2e` (rule 8). No new i18n key —
  `nav.api_docs` already exists.
- **Fail-on-old verified.** Removing the `if not settings.api_docs_enabled:
  return False` guard from `mount_api_docs` (a backup swap) makes
  `test_docs_are_absent_in_a_production_shaped_run` and
  `test_api_docs_false_overrides_debug` fail (the docs mount regardless of the
  flag); restoring the guard restores green.
