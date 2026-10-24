---
plan_id: errors-i18n-admin-infra
title: Localize the toast-reaching admin / infra error raises
area: cross-cutting
effort: small
status: archived
archived_at: 2026-10-24
roadmap_ref: ../../roadmap.md#cross-cutting-principles
---

# Localize the toast-reaching admin / infra error raises

## Intent
A follow-up cohort slice of
[`errors-i18n-message-keys`](errors-i18n-message-keys.md), which shipped
the carrier (`KaletaError.message_key` + `params`), the
`error_handling.resolve_toast_text` wiring, and migrated the first cohort. This
slice covers five hosted / admin / infra services:
`tenant_service`, `instance_admin_service`, `backup_service`,
`nbp_rate_service` and `bug_report_service`. Only raises whose `exc.message`
actually reaches a key-resolving path (`notify_kaleta_error` →
`resolve_toast_text`) get a `message_key`; logs, event capture and the API keep
reading the English `exc.message`.

## Scope
Covers:
- The five services above: add `message_key="errors.<service>.<slug>"` (+ `params`
  where the message interpolates) to each raise whose message reaches
  `notify_kaleta_error`, keeping the English string byte-identical as the
  positional `message`. `code` values, control flow and behaviour unchanged.
- The `errors.tenant`, `errors.instance_admin`, `errors.nbp_rate` and
  `errors.bug_report` blocks in `en.json` / `pl.json`, appended at the END of
  the `errors` object. **No `errors.backup` block** — backup migrates zero
  raises.
- `docs/bdd.md`: `KAL-ERR-009` + a covering integration test.

Does NOT cover:
- Any other service (each cohort is its own slice).
- Changing `code` values, control flow or behaviour.
- The REST API error contract (API responses stay English).
- Localizing raises the surfacing view renders **inline** (`set_text` / `_say`),
  catches **by type**, or that run only in a **background job** / **CLI** — a
  `message_key` there would be a dead key (CRITICAL lesson from slices #362 /
  #363: there is no global NiceGUI exception handler).

## Acceptance criteria
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `uv run python scripts/check_doc_links.py`
- `grep -q "KAL-ERR-009" docs/bdd.md`
- `uv run pytest tests/integration tests/unit -k "tenant or admin or backup or nbp or rate or bug_report or error_i18n or error" -n 2 -m "not slow"`

## Touchpoints
- `src/kaleta/services/tenant_service.py`
- `src/kaleta/services/instance_admin_service.py`
- `src/kaleta/services/backup_service.py` (read-only — zero migrations)
- `src/kaleta/services/nbp_rate_service.py`
- `src/kaleta/services/bug_report_service.py`
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `docs/bdd.md` — `KAL-ERR-009`; `tests/integration/test_error_i18n_admin_infra.py`

## Open questions
- Resolved to plan defaults (no user input while armed).

## Implementation notes

### Totals
**48 raise statements across five services; 25 migrated, 23 left English.**
23 distinct keys (two are shared: nbp_rate `network_unavailable` by two raises,
and bug_report `report_not_found` by `get` + `delete`, each pair carrying the
same English message). Low yield is the honest outcome: most raises are reached
only from the sign-in / join / login forms (which render `exc.message`
**inline**), from the CLI (`kaleta-admin`), from a background scheduler, from
the REST API, or are caught **by type** — none of those resolve a key.

### Surfacing-path facts (the evidence)
- **`admin.py::_AdminPage._act`** (line 164) is the one admin-panel arm that
  routes a `KaletaError` to `notify_kaleta_error`. The panel's family
  suspend / resume / delete / create and login reset buttons run through it.
  Every panel action runs `with_admin_service` → `InstanceAdminService.for_actor`
  (`auth/admin.py:113`) **inside** that `except KaletaError` arm, so a
  `for_actor` `NotFoundError` (admin demoted mid-session) reaches the toast too.
  The **initial page load** (`admin_page`) and the post-action `_refresh` catch
  `NotFoundError` **by type** to answer 404 / redirect (lines 115, 137) — those
  paths ignore a key, but the action path localizes, so migrating `for_actor` is
  correct and harmless.
- **`data_tab.py::_fetch_nbp`** (line 214) catches `KaletaError →
  notify_kaleta_error`, so every raise `NbpRateService.import_latest` can reach
  surfaces as a localized toast. The daily **scheduler**
  (`nbp_rate_scheduler.py`) only `logger.warning`s — background, no toast — but
  it shares the same raise sites, and a `message_key` is simply ignored there.
- **`data_tab.py::_do_restore`** (line 287) and `_do_export` catch **bare
  `Exception`** and render `str(exc)` inside a localized `settings.restore_error`
  template — they never call `resolve_toast_text`. Every `BackupService` raise
  surfaces this way → a key would be dead → **backup migrates zero**.
- **`bug_report_dialog.py::_submit`** (line 206) catches `KaletaError →
  notify_kaleta_error`, so the `BugReportService.create` raise chain localizes.
  The **privacy tab's "my reports"** list (`settings/privacy_tab.py::_remove`,
  line 191) also catches `KaletaError → notify_kaleta_error` around
  `_delete_report` → `BugReportService.delete` → `get`, so the `get` / `delete`
  not-found raises localize too. (`mark` / `attach_external_ref` stay CLI / API
  / delivery only.)
- **Sign-in / join / login forms** (`login.py`, `login_mfa.py`, `join.py`,
  `reset_password.py`) render `exc.message` **inline** via `auth_error_slot`
  (`_say`) — `TenantService`'s sign-in / join / invitation raises are dead keys
  there and stay English. No **view** imports `TenantService` directly (it is
  reached through `sign_in.py`, `household_service`, `account_deletion_service`
  and `instance_admin_service`); the only toast path into it is transitive,
  through `InstanceAdminService` × `admin._act`.

### Per-raise decision tables

#### `tenant_service.py` → `errors.tenant.*` (14 raises; **3 migrated**, 11 English)

| Raise (method @ line, pre-edit) | Surfacing path | Decision → key |
|---|---|---|
| `provision` @187 confirm e-mail | sign-in → login form inline; unreachable via admin (`email_verified=True`) | **English** (inline) |
| `provision` @203 e-mail belongs to other account | admin "New family" → `create_family` → `admin._act` toast (also sign-in inline) | **migrate** → `email_belongs_to_other_account` |
| `membership_for_sign_in` @298 registry changed | sign-in → login form inline (`_say`) | **English** (inline) |
| `membership_for_sign_in` @300 rekeying | sign-in → login form inline | **English** (inline) |
| `membership_for_sign_in` @303 not available | sign-in → login form inline | **English** (inline) |
| `membership_for_sign_in` @312 awaiting approval | sign-in → login form inline | **English** (inline) |
| `membership_for_sign_in` @315 not active | sign-in → login form inline | **English** (inline) |
| `_rejoin` @324 no longer a member | sign-in → login form inline | **English** (inline) |
| `invitation_by_token` @336 invite gone | join view inline (`say`) | **English** (inline) |
| `join` @376 invite gone | join / sign-in inline | **English** (inline) |
| `join` @380 household not available | join / sign-in inline | **English** (inline) |
| `join` @389 e-mail belongs to other account | join / sign-in inline | **English** (inline) |
| `resume` @448 not suspended | admin "Resume" button → `admin._act` toast (concurrent status change) | **migrate** → `not_suspended` (`{tenant_id}`, `{status}`) |
| `_require_tenant` @481 not found | admin suspend/resume → `admin._act` toast (concurrent delete) | **migrate** → `not_found` (`{tenant_id}`) |

#### `instance_admin_service.py` → `errors.instance_admin.*` (10 raises; **6 migrated**, 4 English)

| Raise (method @ line) | Surfacing path | Decision → key |
|---|---|---|
| `for_actor` @217 not found | every panel action runs `for_actor` inside `admin._act`'s `except KaletaError` (admin demoted mid-session); the by-type 404 / redirect paths ignore the key | **migrate** → `not_found` |
| `family` @297 tenant not found | admin "Delete" flow → `admin._act` toast (concurrent delete) | **migrate** → `family_not_found` (`{tenant_id}`) |
| `create_family` @311 give a name | admin "New family" → `admin._act` toast | **migrate** → `family_name_required` |
| `create_family` @313 name too long | admin "New family" → `admin._act` toast | **migrate** → `family_name_too_long` (`{max}`) |
| `delete` @356 type the name | `typed is None` only from CLI `--yes`; panel always submits a string | **English** (CLI-only) |
| `delete` @359 name mismatch | admin delete dialog → `admin._act` toast | **migrate** → `family_name_mismatch` |
| `login_by_email` @401 no login `{email}` | only caller is CLI `tenant_admin.py` | **English** (CLI-only) |
| `reset_password` @450 no such login | admin "Reset password" → `admin._act` toast (concurrent removal) | **migrate** → `login_not_found` |
| `reset_password` @459 MFA family not active | guarded by `disable_mfa`, passed `True` only from CLI (panel uses default `False`) | **English** (CLI-only) |
| `_require_local` @537 logins live in Supabase | panel buttons are UI-gated to the `local` backend; reached only by CLI / programmatic use | **English** (UI-gated / CLI) |

#### `backup_service.py` → **zero migrated** (8 raises, all English)

| Raise (fn @ line) | Surfacing path | Decision |
|---|---|---|
| `_current_alembic_revision` @52 no head | export has no handler; restore catches bare `Exception` | **English** (dev invariant) |
| `_deserialize_value` @131 not base64 | restore → `_do_restore` bare `except Exception` → `str(exc)` inline | **English** (inline, non-key path) |
| `_deserialize_value` @137 not a base64 string | restore → bare `except Exception` inline | **English** (inline) |
| `restore` @223 missing metadata.json | restore → bare `except Exception` inline | **English** (inline) |
| `restore` @226 unsupported version | restore → bare `except Exception` inline | **English** (inline) |
| `restore` @232 missing alembic_revision | restore → bare `except Exception` inline | **English** (inline) |
| `restore` @237 revision mismatch | restore → bare `except Exception` inline | **English** (inline) |
| `restore` @278 unknown columns | restore → bare `except Exception` inline | **English** (inline) |

`_do_restore` / `_do_export` catch bare `Exception` and render `str(exc)` through
a localized `settings.restore_error` / `settings.*_error` template — they never
call `resolve_toast_text`, so a `message_key` would be dead. Backup therefore
gets **no i18n block**.

#### `nbp_rate_service.py` → `errors.nbp_rate.*` (11 raises; **all 11 migrated**)

Every raise is reachable from the Settings → Data **"Fetch NBP"** button
(`data_tab._fetch_nbp`, `except KaletaError → notify_kaleta_error`). The daily
scheduler shares the same sites but only logs (background) — the key is ignored
there, so migrating is correct and harmless.

| Raise (method @ line) | key |
|---|---|
| `default_http_get` @64 timeout | `timeout` |
| `default_http_get` @68 HTTP error | `http_error` (`{code}`) |
| `default_http_get` @72 network unavailable | `network_unavailable` |
| `fetch_table_a_payload` @83 network unavailable | `network_unavailable` (shared, same English) |
| `fetch_table_a_payload` @89 invalid JSON | `invalid_json` |
| `fetch_table_a_payload` @91 empty response | `empty_response` |
| `fetch_table_a_payload` @94 unexpected shape | `unexpected_shape` |
| `parse_mids` @106 missing effectiveDate | `missing_effective_date` |
| `parse_mids` @110 no rates | `no_rates` |
| `parse_mids` @127 no usable mids | `no_usable_rates` |
| `import_latest` @143 invalid effectiveDate | `invalid_effective_date` (`{date!r}`) |

#### `bug_report_service.py` → `errors.bug_report.*` (5 raises; **all 5 migrated**)

| Raise (method @ line) | Surfacing path | Decision → key |
|---|---|---|
| `_required` @33 field required | report dialog `_submit` → `notify_kaleta_error` | **migrate** → `field_required` (`{field}`) |
| `get` @151 report not found | privacy tab "my reports" delete → `get` → `privacy_tab._remove` → `notify_kaleta_error` | **migrate** → `report_not_found` (`{report_id}`) |
| `delete` @172 report not found | privacy tab "my reports" delete (someone else's report) → `notify_kaleta_error` | **migrate** → `report_not_found` (shared, same English) |
| `_allocate_report_id` @193 id allocation failed | report dialog `_submit` → toast | **migrate** → `id_allocation_failed` |
| `_enforce_rate_limit` @206 too many reports | report dialog `_submit` → toast | **migrate** → `rate_limited` (`{limit}`) |

### Interpolation limitations (honest notes)
- `errors.tenant.not_suspended` interpolates `{status}`, the English enum value
  (`deleting` / `active` / …); only the sentence frame localizes. Byte-identical
  English fallback preserved.
- `errors.bug_report.field_required` interpolates `{field}`, the English column
  word (`Summary` / `Description`) — the service has no locale, so only the
  frame localizes.
- `errors.nbp_rate.invalid_effective_date` uses `{date!r}` (verified:
  `str.format` reproduces the `!r` repr byte-for-byte, matching the old
  f-string).

### i18n placement
`tenant`, `instance_admin`, `nbp_rate`, `bug_report` appended as the last
siblings of the `errors` object (after `errors.local_identity`), to avoid a
textual git conflict with sibling lanes editing earlier `errors.*` blocks.

### What the test drives directly
`tests/integration/test_error_i18n_admin_infra.py` (`Covers: KAL-ERR-009`):
- Both-locales key-presence + locale-format tables over all 21 new keys.
- Real migrated raises driven directly: the pure `NbpRateService.parse_mids` /
  `fetch_table_a_payload` raises (no DB / HTTP needed), the module-level
  `bug_report_service._required`, and `BugReportService.get` on a missing id
  (`report_not_found`, over the `session` fixture). Each asserts the raise
  carries the expected `message_key` and that `t(exc.message_key, **exc.params)`
  reproduces the unchanged English `exc.message` (`_assert_localizes`).
- Polish / English literals from KAL-ERR-009 asserted against the locale files
  (BDD literals, rule 11).
- A representative **backup** raise (`restore` over a zip missing
  `metadata.json`) is asserted to carry **no** `message_key` — documenting the
  deliberate zero-migration decision.

### View changes
None — none of the five services is a view, and the test is integration-only
(no file under `src/kaleta/views/` touched).

### Landed
Commit `3eaf8ac` (PR #364), author Dawid (Ani), merged 2026-10-24.

Files touched:
- `docs/bdd.md`
- `docs/plans/README.md`
- `src/kaleta/i18n/locales/en.json`
- `src/kaleta/i18n/locales/pl.json`
- `src/kaleta/services/bug_report_service.py`
- `src/kaleta/services/instance_admin_service.py`
- `src/kaleta/services/nbp_rate_service.py`
- `src/kaleta/services/tenant_service.py`
- `tests/integration/test_error_i18n_admin_infra.py`
