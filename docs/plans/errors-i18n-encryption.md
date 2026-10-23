---
plan_id: errors-i18n-encryption
title: Localize data-passphrase & local-identity error toasts
area: cross-cutting
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Localize data-passphrase & local-identity error toasts

## Intent
A follow-up slice of [`errors-i18n-message-keys`](archive/errors-i18n-message-keys.md),
which shipped the carrier (`KaletaError.message_key` + `params`), the
`error_handling.resolve_toast_text` wiring, and migrated the first cohort.
This slice examines the **encryption / identity** services — `key_service.py`
(the data passphrase) and `local_identity_service.py` (the registry logins) —
and migrates only the raises whose `exc.message` reaches a **key-resolving**
path (`notify_kaleta_error` / `resolve_toast_text`), so those toasts read in
the session's language, while logs, event capture and the API keep reading the
English `exc.message`.

Only `notify_kaleta_error` / `resolve_toast_text` resolve a `message_key`. A
view that renders `exc.message` **inline** (`say(exc.message)` /
`error.set_text(exc.message)`), that catches the raise **by type** and
substitutes its own localized key, or that **navigates away** without showing
the message, resolves no key — so a key on such a raise would be dead and is
**not** added.

## Scope
Covers:
- `key_service.py`, `local_identity_service.py`: add
  `message_key="errors.<ns>.<slug>"` to each raise whose `exc.message` actually
  reaches `notify_kaleta_error`, keeping the English string byte-identical as
  the positional `message` fallback. `code` values, control flow and behaviour
  unchanged.
- The `errors.key` and `errors.local_identity` blocks in `en.json` and
  `pl.json`, appended at the END of the existing `errors` object.
- `docs/bdd.md`: `KAL-ERR-008` + a covering integration test.

Does NOT cover:
- Any other service (each gets its own follow-up slice — the chore line in
  `chores.md` stays open; this plan does NOT tick it).
- Changing `code` values, control flow or any behaviour.
- The REST API error contract (still English `message`).
- Raises whose `exc.message` the view never renders as a toast (inline label,
  caught-by-type with the view's own key, navigate-away, or script-only) — see
  the per-raise tables.
- Any file under `src/kaleta/views/` (no view is touched — the existing
  `except KaletaError → notify_kaleta_error` arms already localize once the key
  is on the raise).

## Acceptance criteria
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `uv run python scripts/check_doc_links.py`
- `grep -q "KAL-ERR-008" docs/bdd.md`
- `uv run pytest tests/integration tests/unit -k "key or identity or encryption or passphrase or error_i18n or error" -n 2 -m "not slow"`

## Touchpoints
- `src/kaleta/services/key_service.py` — 4 migrated raises.
- `src/kaleta/services/local_identity_service.py` — 5 migrated raises.
- `src/kaleta/i18n/locales/en.json`, `pl.json` — `errors.key.*`,
  `errors.local_identity.*`.
- `docs/bdd.md` — `KAL-ERR-008`; `tests/integration/test_error_i18n_encryption.py`.

## Open questions
- Resolved to plan defaults (no user input while armed).

## Implementation notes

### Slice boundary
Covers the two encryption/identity services only. `chores.md` follow-up line
stays unticked. No view file is touched.

### The defining finding — these views mostly do NOT route to a toast
Like the 2FA slice, the yield here is low. There is **no global NiceGUI
exception handler** (`grep -rn on_exception src/kaleta` → none), so an uncaught
`KaletaError` in an event handler is logged by NiceGUI, not localized. The only
path that resolves a `message_key` is an explicit `notify_kaleta_error(exc)`.
The views that surface these two services handle errors as follows:

- **`views/unlock.py`** (drives `key_service.setup/unlock/open/recover`): every
  arm is `except ValidationError: say(t("unlock.wrong_*"))` (inline, view's own
  key) or `except ConflictError: ui.navigate.to(...)` (navigate away, message
  never shown). It **never** calls `notify_kaleta_error` for a key_service
  raise. So nothing surfaced only through `unlock.py` gets a key.
- **`views/settings/data_passphrase_card.py`** (`change_passphrase`,
  `regenerate_recovery_code`): `except ValidationError:` → the view's own key
  inline; **trailing `except KaletaError as exc: notify_kaleta_error(exc)`** →
  key-resolving toast.
- **`views/settings/delete_account_section.py`** → `auth/account_deletion.py`
  (`service.open`): `except WrongPassphraseError:` (a `ValidationError`
  subclass) inline; **trailing `except KaletaError as exc:
  notify_kaleta_error(exc)`** → key-resolving toast.
- **`views/settings/household_tab.py` `_approve`** (drives `service.unlock` →
  `open`): `except ValidationError:` inline; trailing `except KaletaError as
  exc: error.set_text(exc.message)` — **inline label, resolves no key**.
- **`views/login.py`, `views/create_account.py`, `views/change_password.py`,
  `views/join.py`** (drive `local_identity` `authenticate` / `sign_up` /
  `create` / `set_password`): every arm is `except UnauthorizedError:` (login's
  own `auth.login_failed_email` key, inline) or `except KaletaError as exc:
  _say(exc.message)` — **inline, resolves no key**.
- **`views/admin.py` `_act`** (drives `local_identity` `set_admin` /
  `set_disabled` via `InstanceAdminService`): **`except KaletaError as exc:
  notify_kaleta_error(exc)`** → key-resolving toast.

So the live reach paths are: `data_passphrase_card`, `account_deletion` /
`delete_account_section`, and the admin panel's `_act`. Everything else renders
inline, catches by type, navigates away, or is script-only.

### Totals
13 `KaletaError` raises in `key_service.py` (+2 in the module-level
`open_family_data_key` script helper) and 12 in `local_identity_service.py`.
**9 migrated** (9 distinct keys), the rest left English with evidence. By
service: `key_service` **4 migrated**, `local_identity_service` **5 migrated**.
All raises are `KaletaError` subclasses (`NotFoundError` / `ValidationError` /
`ConflictError` / `UnauthorizedError`). `key_service` also imports
`EncryptionError`, which it only **catches** (from `kaleta.crypto`, converting a
failed KDF open into a `ValidationError`) and never raises as a user toast — no
`EncryptionError` key is added.

### Per-raise classification — key_service.py (13 raises → 4 migrated)

Reach paths: the ValidationErrors (`validate_passphrase`, wrong-passphrase /
wrong-recovery) are **always** caught by a type-specific `except ValidationError`
that shows the view's own `unlock.*` / `settings.*` key — never a key here. The
non-ValidationError raises in `_material`/`open`/`_member` reach the trailing
`except KaletaError → notify_kaleta_error` in `data_passphrase_card` and
`delete_account_section`.

| Raise (method @ msg) | Caller / handler | Decision |
|---|---|---|
| `_member` "This sign-in has no membership in the account." `NotFoundError` | reached via `store.save`/`store.load` inside `change_passphrase`/`regenerate_recovery_code` (`data_passphrase_card` trailing `except KaletaError` → `notify_kaleta_error`) and `open` (`account_deletion` → `notify_kaleta_error`) | **migrate → `errors.key.no_membership`** |
| `_material` "No data passphrase is set up yet." `NotFoundError` | same three flows → `notify_kaleta_error` | **migrate → `errors.key.no_passphrase_set_up`** |
| `open` "Your data key has not been shared with you yet." `ConflictError` | via `account_deletion.open` → `delete_account_section` trailing `except KaletaError` → `notify_kaleta_error` (in `unlock._unlock` it is caught by `except ConflictError:` → navigate, no toast) | **migrate → `errors.key.data_key_not_shared`** |
| `open` `REKEYING_MESSAGE` "Your household is being re-keyed. Try again in a moment." `ConflictError` | via `account_deletion.open` → `notify_kaleta_error` (owner deleting while the household re-keys — genuinely reachable); in `unlock._unlock` caught by `except ConflictError:` → navigate | **migrate → `errors.key.rekeying`** |
| `validate_passphrase` "Choose a data passphrase of at least 12 characters." `ValidationError` | view pre-checks (`passphrase_problem` → `unlock.passphrase_too_short`); if raised, `unlock._setup_form` trailing `except KaletaError: say(exc.message)` (inline) / `data_passphrase_card except ValidationError` (inline, own key) | English (inline / pre-validated; key would be dead) |
| `validate_passphrase` "Choose a data passphrase that is not your login password." `ValidationError` | `unlock._setup_form` pre-checks `is_login_password` → `unlock.passphrase_is_password`; service guard only via `setup`'s trailing `except KaletaError: say(exc.message)` (inline) | English (inline / pre-validated) |
| `setup` "A data passphrase is already set up for this account." `ConflictError` | `unlock._setup_form` `except ConflictError:` → `ui.navigate.to(...)` (message never shown) | English (navigate-away) |
| `open` "That passphrase does not unlock your data." `ValidationError` | `unlock._unlock` `except ValidationError:` → `t("unlock.wrong_passphrase")`; `account_deletion._prove` `except ValidationError` → `WrongPassphraseError` → inline | English (caught by type) |
| `change_passphrase` "That is not your current data passphrase." `ValidationError` | `data_passphrase_card._open_change` `except ValidationError:` → `t("settings.passphrase_current_wrong")` | English (caught by type) |
| `regenerate_recovery_code` "That passphrase does not unlock your data." `ValidationError` | `data_passphrase_card._open_regenerate` `except ValidationError:` → `t("unlock.wrong_passphrase")` | English (caught by type) |
| `recover` "That recovery code does not open your data." `ValidationError` | `unlock._recover` `except ValidationError:` → `t("unlock.wrong_recovery_code")` | English (caught by type) |
| `open_family_data_key` "No data passphrase is set up in this family yet. …" `NotFoundError` | module-level helper for `scripts/seed.py` / `scripts/reset_demo.py` — no view, prints to a console | English (script-only) |
| `open_family_data_key` "That passphrase does not unlock this family's data." `ValidationError` | same script helper | English (script-only) |

### Per-raise classification — local_identity_service.py (12 raises → 5 migrated)

Reach paths: `authenticate` (the `_BAD_CREDENTIALS` trio) is surfaced only by
`login._submit`, which catches `UnauthorizedError` **by type** and shows its own
`auth.login_failed_email` / rate-limit keys. `sign_up` / `set_password` reach
only `create_account`, `change_password`, `join` — all `except KaletaError:
_say(exc.message)` **inline**. The key-resolving path is the admin panel
(`views/admin.py::_act` → `except KaletaError → notify_kaleta_error`), which
reaches: `set_admin` / `set_disabled` (and, through them, `_require`) via
`InstanceAdminService` delegation; **and `create`** via the "New family" action
(`admin._create_family` → `_act` → `InstanceAdminService.create_family` →
`self._logins.create(owner_email, …)`, the admin-typed owner e-mail, outside the
`try` that wraps only the later provision step). `create` is **also** reached
inline through `create_account` / `join`, but the admin path makes its two input
guards live. `create`'s `_validate_password` stays unreachable on every
key-resolving path (admin `create_family` and `reset_password` both pass a
generated password).

| Raise (method @ msg) | Caller / handler | Decision |
|---|---|---|
| `set_admin` "The last administrator cannot stop being one." `ValidationError` | `admin._toggle_admin` → `InstanceAdminService.set_admin` (delegates straight to `_logins.set_admin`) → `_act` `except KaletaError` → `notify_kaleta_error` | **migrate → `errors.local_identity.last_admin_cannot_demote`** |
| `set_disabled` "The last administrator cannot be disabled." `ValidationError` | `admin._toggle_disabled` → `set_login_disabled_as_admin` → `InstanceAdminService.set_disabled` → `_logins.set_disabled` → `_act` → `notify_kaleta_error` | **migrate → `errors.local_identity.last_admin_cannot_disable`** |
| `_require` "No such login." `NotFoundError` | reached via `set_admin`/`set_disabled` (`_require(identity_id)`) on the admin `_act` → `notify_kaleta_error` path | **migrate → `errors.local_identity.login_not_found`** |
| `create` "Enter an e-mail address." `ValidationError` | `admin._create_family` → `_act` → `InstanceAdminService.create_family` → `self._logins.create(owner_email, …)` → `except KaletaError` → `notify_kaleta_error` (the admin-typed owner e-mail; `create`'s guard runs before the wrapped provision step). Also inline via `create_account`/`join`. | **migrate → `errors.local_identity.email_required`** |
| `create` "An account with this e-mail address already exists." `ConflictError` | same admin `create_family` → `notify_kaleta_error` path (duplicate owner e-mail). Also inline via `create_account`/`join`. | **migrate → `errors.local_identity.email_taken`** |
| `sign_up` "Sign-up is closed on this instance. Ask its administrator for an account." `ValidationError` | `create_account._submit` inline `_say` | English (inline only) |
| `authenticate` `_BAD_CREDENTIALS` "Invalid e-mail or password." `UnauthorizedError` ×3 (@160,@165,@167) | `login._submit` `except UnauthorizedError:` → records failure, shows `auth.login_failed_email` / `auth.login_rate_limited` (own keys, inline); `admin.verify_admin_credentials` catches it and returns `False` | English (caught by type) |
| `delete` "The last administrator cannot be deleted." `ValidationError` | every caller guards admins first — `RegistryAuthProvider.delete_identity` returns on `is_instance_admin`, `household._delete_invited_login` returns on `is_instance_admin`, `InstanceAdminService._undo_family_of` deletes a freshly-provisioned (non-admin) login — so the guard never fires on a `notify_kaleta_error` path | English (unreachable from any toast path) |
| `_validate_password` "Password must be at least 8 characters." `ValidationError` | `create` (→ `create_account`/`join` inline `_say`) and `set_password` (→ `change_password` inline `_say`; admin `reset_password` passes a generated password) | English (inline only) |
| `_validate_password` "Password must be at most 1024 characters." `ValidationError` | same as above | English (inline only) |

### Which raises the test drives directly
`tests/integration/test_error_i18n_encryption.py` drives **real** raises against
the lane Postgres:
- `local_identity_service.set_admin` on the sole administrator →
  `errors.local_identity.last_admin_cannot_demote` (asserts the key and that
  `t(key)` reproduces the English `exc.message`).
- `local_identity_service.create` with a malformed e-mail →
  `errors.local_identity.email_required` (the admin "New family" action's
  reach path; `create` validates before any write).
- `key_service` rekeying raise: `KeyService.open` with the tenant frozen in the
  key ring → `errors.key.rekeying`.

It also asserts the **deliberate key-less decision**: a representative raise
these services surface only inline — `local_identity_service._validate_password`
(too-short password, `errors`-key-less) — carries `message_key is None` and
`resolve_toast_text(exc) == exc.message` (English unchanged). Every migrated key
is additionally covered by a both-locales presence table and a locale-format
table, with the Polish literals from KAL-ERR-008 asserted against `pl.json`
directly (BDD literals, rule 11). None of the migrated raises interpolates
params, so every `params` is `{}`.

### i18n placement
`errors.key` and `errors.local_identity` are appended as the last siblings of
the `errors` object (after `errors.api_token`), per the slice brief — avoids
textual git conflicts with sibling lanes editing earlier `errors.*` blocks.
`errors.key.rekeying`'s Polish reuses the existing
`errors.household.household_rekeying` wording (same English source sentence).

### View changes
None — the two files are services. The test is integration-only and touches no
file under `src/kaleta/views/`.
