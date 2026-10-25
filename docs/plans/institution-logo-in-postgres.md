---
plan_id: institution-logo-in-postgres
title: Store institution logos in Postgres, not on the pod filesystem
area: institutions / storage
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#institutions
---

# Store institution logos in Postgres, not on the pod filesystem

## Intent
Institution logos are uploaded as files to `~/.kaleta/logos/` and served as
static `/logos/<uuid>.<ext>`; the DB keeps only `institutions.logo_path`. On
k3s that directory is pod-local (`emptyDir` for multi-replica, or a
node-bound `local-path` PVC), so **every redeploy that replaces the pod wipes
the files while the DB paths survive** — the avatar then renders a broken
image. Seen again right after the 0.8.0 deploy on the hosted instance
(`logo_path` set, `/logos/<name>` 404s). The files are also outside the
backup/restore and encryption story that covers the rest of a family's data.

Fix: store the logo **bytes in Postgres**, in the family's own schema, and
serve them through an authenticated route that streams from the DB. Logos
then survive any redeploy / replica topology / node reschedule, ride along
with backups, and — encrypted — stop leaking the institution identity that
`institutions.name` is encrypted to hide.

## Scope

Covers:
- **Model** (`models/institution.py`): drop `logo_path` (`String(255)`); add
  - `logo_mime: Mapped[str | None]` (`String(100)`, nullable, always loaded) —
    the cheap "has a logo" signal and the `Content-Type` for the route;
  - `logo_b64: Mapped[str | None]` (`EncryptedText("institutions.logo_b64")`,
    nullable, `deferred`) — the image bytes base64-encoded and encrypted under
    the account data key, only loaded by the serving route, never by `list()`.
- **Schema** (`schemas/institution.py`): drop `logo_path` from `Base` /
  `Create` / `Update`; `InstitutionResponse` exposes `has_logo: bool`
  (derived from `logo_mime`), not a path. Logo upload/removal is no longer
  part of the create/update payload.
- **Service** (`services/institution_service.py`): `set_logo(id, filename,
  content)` (validates format + size, derives mime, stores
  `base64(content)` + mime), `clear_logo(id)`, `get_logo(id) -> tuple[bytes,
  str] | None` (explicit `select(logo_b64, logo_mime)` — async-safe, no lazy
  attribute load — then base64-decode). The response mapper sets `has_logo`.
- **Route** (`api/v1/institutions.py`): `GET /{id}/logo` → `Response(content,
  media_type)` with a private `Cache-Control`; `Depends(get_current_user_id)`
  + `Depends(get_session)` for auth + tenant + data-key; 404 when no logo.
  `/api/v1/` is exempt from the UI `AuthMiddleware` and guarded by `api/deps`,
  and cookie auth is allowed for the safe `GET` an `<img>` makes.
- **View** (`views/institutions.py`): the Add/Edit upload calls the service
  (holding bytes + mime in memory during Add, since the row has no id yet;
  preview via a `data:` URL before save, via the route after). Remove the
  `save_logo` / `delete_logo` imports.
- **Avatar** (`views/institution_avatar.py`): render the image from
  `/api/v1/institutions/{id}/logo` when `has_logo`; add an `onerror`
  graceful fallback so a 404 degrades to the brand letter-circle instead of a
  broken-image icon.
- **Remove the file store**: delete `services/institution_logo_service.py`,
  the `/logos` static registration in `pwa.py`, and `/logos/` from
  `_PUBLIC_PREFIXES` in `auth/middleware.py`.
- **Migration**: drop `logo_path`, add `logo_mime` (`String(100)`) + `logo_b64`
  (`LargeBinary`, the storage impl of `EncryptedText`) per family (via
  `schema_translate_map`, like `a1c7e2f84b50`). Dead `logo_path` values
  vanish with the column, so the broken images on existing instances become
  letter-circles immediately; users re-upload and it now persists.
- **BDD**: new `KAL-INS-010 @automated` — a logo lives in the database and
  survives a fresh session/restart. Covered by an integration test.

Explicitly NOT in scope:
- Fetching logos automatically from a bank's website / Clearbit — unchanged.
- Changing the avatar's letter-circle fallback styling or the colour token.
- The `/static` route (app assets, shipped in the image — correctly static).
- A new `bytes`-native encrypted type — reusing `EncryptedText` over base64
  means backup and re-key already cover the column (see notes), so a binary
  type is not worth its separate backup/re-key integration.

## Acceptance criteria

- `uv run pytest tests/integration/test_institution_logo.py -q`
- `grep -q 'logo_b64' src/kaleta/models/institution.py && ! grep -q 'logo_path' src/kaleta/models/institution.py`
- `test ! -f src/kaleta/services/institution_logo_service.py`
- `! grep -rq '/logos' src/kaleta/auth/middleware.py src/kaleta/pwa.py`
- `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` (against the test DB)
- `./scripts/verify.sh --e2e` (views change)

## Touchpoints
- `src/kaleta/models/institution.py` — columns.
- `src/kaleta/schemas/institution.py` — `has_logo`, drop `logo_path`.
- `src/kaleta/services/institution_service.py` — set/clear/get logo, map `has_logo`.
- `src/kaleta/api/v1/institutions.py` — `GET /{id}/logo`.
- `src/kaleta/views/institutions.py` — upload wiring.
- `src/kaleta/views/institution_avatar.py` — route URL + `onerror` fallback.
- `src/kaleta/services/institution_logo_service.py` — **deleted**.
- `src/kaleta/pwa.py`, `src/kaleta/auth/middleware.py` — drop `/logos`.
- `alembic/versions/<new>_institution_logo_bytes.py` — down_revision `a1c7e2f84b50`.
- `tests/integration/test_institution_logo.py` — new (Covers: KAL-INS-010).
- `docs/bdd.md` — KAL-INS-010.

## Implementation notes
- **Why encrypt the bytes.** `institutions.name`, `website` and `description`
  are `EncryptedText`. A plaintext logo would be a visual oracle for the
  encrypted name (the mBank mark identifies the bank), so the image is
  encrypted with the same per-account key. `logo_mime` stays plaintext — it
  is low-entropy (`image/png`), is needed as the no-decrypt "has a logo"
  signal, and matches how `color` is stored in the clear today.
- **Why base64-in-`EncryptedText`, not a new binary type.** Backup
  (`_is_user_text`) and re-key (`_encrypted_columns`) both recognise an
  encrypted-user-content column by `isinstance(col.type, (EncryptedText,
  EncryptedJSON))`. Storing the image as base64 text inside an `EncryptedText`
  column means both already round-trip it — the backup exports it as plaintext
  base64 and re-encrypts on restore, the re-key reads and rewrites it — with
  no change to that security-sensitive code. A `bytes`-native type would need
  its own branch in each. The ~33% base64 overhead is nothing on a logo.
- **Why `deferred`.** The list and detail paths need only `has_logo`
  (from `logo_mime`); pulling and decrypting every logo on a `list()` would be
  wasteful. The route loads `logo_b64` with an explicit `select` (an async
  lazy attribute load would raise `MissingGreenlet`).
- **Serving outside a page context.** The `<img>` request carries only the
  session cookie. `get_current_user_id` → `authenticated_user_id(request)`
  binds NiceGUI storage from the bare `Request`, sets the tenant and the data
  key, so `AsyncSessionFactory()` opens on the right schema and the blob
  decrypts. No single-vs-hosted branch (ADR-38).
- **Add-before-id.** During Add the institution has no id, so the upload
  handler holds `(bytes, mime)` and the preview uses a `data:` URL; `set_logo`
  runs after `create`. Edit can call `set_logo` immediately and bust the
  `<img>` cache with a `?v=` stamp.
- **Format + size.** Keep the `.svg/.png/.jpg/.jpeg/.webp` allowlist (moved
  off the deleted file service); reuse the server-side upload size cap.

## Deviations from the plan as written
- **Scenario id.** The plan said `KAL-INS-008`; that id already exists as
  `@manual` (type-defaults-to-Bank), and `KAL-INS-009 @automated` already
  covers the upload UX, so the new persistence scenario is `KAL-INS-010
  @automated`.
- **Route auth.** The route uses `Depends(get_session)` only, not an explicit
  `Depends(get_current_user_id)`: the whole `v1_router` already carries
  `dependencies=[Depends(require_api_auth)]` (`api/v1/__init__.py`), which runs
  `get_current_user_id` — accepting a cookie for a safe `GET` and binding the
  data key. A second dependency would be redundant.
- **Size cap.** The generic `settings.max_upload_bytes` is 50 MB — far too
  large for a logo — so the service adds a focused `MAX_LOGO_BYTES` (2 MB). The
  view rejects an oversize file in the upload handler, before `set_logo` runs
  after `create()`, so an oversize logo can never orphan a logo-less row
  (reviewer finding).
- **Avatar fallback.** Implemented as `image.on("error", …)` hiding the image
  over a letter-circle underlay (works under the app's CSP), rather than an
  inline `onerror` attribute.
- **Pending upload shape.** Add holds `(bytes, filename)`, not `(bytes, mime)` —
  `set_logo` derives the mime from the filename (the trusted signal).
- **`session.refresh` in the view.** After `set_logo`/`clear_logo` commit (which
  expires the row), the view refreshes before `model_validate`, so reading
  `has_logo` never triggers an async lazy load.
- **SVG hardening.** The logo response carries `Content-Security-Policy:
  sandbox; default-src 'none'` and `Content-Disposition: inline`, so an SVG
  opened as a top-level navigation cannot run script (reviewer finding; the old
  static mount had the same exposure — closed here).
- **Route 200 test.** `tests/integration/test_institution_logo.py` asserts the
  served bytes, `Content-Type`, `Cache-Control` and sandbox header (the
  `session`/`api_client` fixtures share one DB connection), not only the 404.
