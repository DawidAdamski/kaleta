---
plan_id: errors-i18n-2fa
title: Localize MFA, hosted-MFA & API-token error toasts
area: cross-cutting
effort: small
status: archived
archived_at: 2026-10-23
roadmap_ref: ../../roadmap.md#cross-cutting-principles
---

# Localize MFA, hosted-MFA & API-token error toasts

## Intent
A follow-up slice of [`errors-i18n-message-keys`](errors-i18n-message-keys.md),
which shipped the carrier (`KaletaError.message_key` + `params`), the
`error_handling.resolve_toast_text` wiring, and migrated the first cohort.
This slice examines the **two-factor / token family** — `mfa_service.py`,
`hosted_mfa_service.py`, `api_token_service.py` — and migrates the raises whose
`exc.message` reaches a **key-resolving** path (`notify_kaleta_error` /
`resolve_toast_text`), so those toasts read in the session's language, while
logs, event capture and the API keep reading the English `exc.message`. Only
`notify_kaleta_error`/`resolve_toast_text` resolve `message_key`; an inline
`error.set_text(exc.message)` label always renders English, so a key on a
raise the view only surfaces inline would be dead and is **not** added.

## Scope
Covers:
- `mfa_service.py`, `hosted_mfa_service.py`, `api_token_service.py`: add
  `message_key="errors.<ns>.<slug>"` to each raise whose `exc.message` actually
  reaches a user, keeping the English string byte-identical as the positional
  `message` fallback. `code` values, control flow and behaviour unchanged.
- The `errors.mfa` and `errors.api_token` blocks in `en.json` and `pl.json`,
  appended at the END of the existing `errors` object. (`hosted_mfa_service`
  has no raise on a key-resolving path, so no `errors.hosted_mfa` block.)
- `docs/bdd.md`: `KAL-ERR-007` + a covering integration test.

Does NOT cover:
- Any other service (each gets its own follow-up slice — the chore line in
  `chores.md` stays open until all services are done; this plan does NOT tick it).
- Changing `code` values, control flow or any behaviour.
- The REST API error contract (still English `message` everywhere a view does
  not localize).
- Raises whose `exc.message` the view never renders (swallowed by a
  type-specific `except` that shows its own localized string) or that are
  developer invariants / pre-validated upstream — see the skip table.

## Acceptance criteria
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `uv run python scripts/check_doc_links.py`
- `grep -q "KAL-ERR-007" docs/bdd.md`
- `uv run pytest tests/integration tests/unit -k "mfa or token or two_factor or error_i18n or error" -n 2 -m "not slow"`

## Touchpoints
- `src/kaleta/services/mfa_service.py` — migrated raises.
- `src/kaleta/services/api_token_service.py` — migrated raise.
- `src/kaleta/services/hosted_mfa_service.py` — examined; no raise migrated.
- `src/kaleta/i18n/locales/en.json`, `pl.json` — `errors.mfa.*`,
  `errors.api_token.*`.
- `docs/bdd.md` — `KAL-ERR-007`;
  `tests/integration/test_error_i18n_2fa.py`.

## Open questions
- Resolved to plan defaults (no user input while armed).

## Implementation notes

### Slice boundary
Covers the three 2FA/token services only. `chores.md` follow-up line stays
unticked. No view file is touched.

### The defining finding — the 2FA views already localize at the view layer
Unlike `household_service` (whose views render `exc.message` directly or via
`notify_kaleta_error`), the two-factor dialogs in
`views/settings/security_tab.py` (and `views/login_mfa.py`) catch the domain
exceptions **by type** and substitute their own purpose-built localized keys:

- `except ConflictError:` → `t("settings.mfa_stale")` (setup/confirm/recovery/
  disable dialogs) or, in `login_mfa._submit`, navigates to login with
  `"mfa_gone"`.
- `except ValidationError:` → `t("settings.mfa_enrol_failed")` /
  `t("settings.mfa_disable_failed")` / `t("auth.mfa_failed")` (+ rate-limit
  variants), recording a failure.
- `except EncryptionError:` → `t("settings.mfa_unreadable")`.
- Only the trailing `except KaletaError as exc` arm — reached by a
  `KaletaError` that is *not* Conflict/Validation/Encryption — renders
  `exc.message` (inline label) or `notify_kaleta_error(exc)` (toast).

So a `message_key` on a raise the view swallows would be a **dead key**
(nothing resolves it, and the view will never resolve it by design). Two more
things matter for "does the key resolve":

- Only `notify_kaleta_error` / `resolve_toast_text` resolve a `message_key`.
  The trailing `except KaletaError as exc: error.set_text(exc.message)` arm
  (in `_begin_hosted` and `_open_disable`) renders the English `exc.message`
  **inline** and resolves no key. A raise surfaced only there is therefore
  still a dead key today, and is left English.
- So the only live reach path in this family is `notify_kaleta_error` — used
  by `_open_setup` (local `begin_enrolment`), `_open_recovery` and the token
  handlers (`_create_token`, `_revoke`).

Per the `errors-i18n-household` precedent (its `waiting_room` skip) and the
project's "no dead keys" rule, every raise that does not reach
`notify_kaleta_error` is left English **without** a key, with the exact
`except`-block evidence recorded below.

### Totals
30 `KaletaError` raise statements across the three services; **4 migrated**
(4 distinct keys), **26 left English with evidence**. By service:
`mfa_service` 3 migrated / 13 English, `api_token_service` 1 / 2,
`hosted_mfa_service` 0 / 11. All raises are `KaletaError` subclasses
(`ConflictError` / `ValidationError` / `NotFoundError`); no plain
`Exception`/form-error types exist in these services (nothing out-of-scope to
note).

### Per-raise classification (caller-searched)

Caller search: `create_token`/`revoke_token`/`list_tokens`,
`begin_enrolment`/`confirm_enrolment`/`regenerate_recovery_codes`/`disable`,
`begin_hosted_enrolment`/`confirm_hosted_enrolment`/`disable_hosted` are each
called **only** from `views/settings/security_tab.py`; `recover` only from
`auth/sign_in.py::SignInFlow.recover` → `views/login_mfa.py::_submit`;
`prove`/`verify_challenge` (via `auth/admin.py`) and `authenticate_bearer`/
`tenant_id_from_token` (the only `api/` callers) return `bool`/`int|None` and
raise none of these. No token CRUD exists in `src/kaleta/api/`.

#### mfa_service.py (16 raises → 3 migrated, 13 English)

| Raise (method @ msg) | Caller / handler | Decision |
|---|---|---|
| `begin_enrolment` "User not found" `NotFoundError` | `security_tab._open_setup` → trailing `except KaletaError` → `notify_kaleta_error` | **migrate → `errors.mfa.user_not_found`** |
| `begin_enrolment` "…already enabled" `ConflictError` ×3 | `_open_setup` `except ConflictError:` → `t("settings.mfa_stale")` | English (swallowed) |
| `confirm_enrolment` "Start the two-factor setup…" `ConflictError` | `_open_setup._confirm` `except ConflictError:` → `mfa_stale` | English (swallowed) |
| `confirm_enrolment` "…already enabled" `ConflictError` ×2 | same `except ConflictError:` → `mfa_stale` | English (swallowed) |
| `confirm_enrolment` "That code is not right…" `ValidationError` | `_confirm` `except ValidationError:` → `t("settings.mfa_enrol_failed")` | English (swallowed) |
| `regenerate_recovery_codes` "Enable two-factor…" `ValidationError` | `_open_recovery` (no `except ValidationError`) → `except KaletaError` → `notify_kaleta_error` | **migrate → `errors.mfa.enable_before_recovery_codes`** |
| `regenerate_recovery_codes` "Confirm with a two-factor code before reissuing…" `ValidationError` | `_open_recovery` → `notify_kaleta_error` | **migrate → `errors.mfa.confirm_before_recovery_codes`** |
| `regenerate_recovery_codes` "Your recovery codes changed…" `ConflictError` | `_open_recovery` `except ConflictError:` → `mfa_stale` | English (swallowed) |
| `disable` "…not enabled" `ConflictError` ×2 (@542,@598) | `_open_disable` `except ConflictError:` → `mfa_stale` | English (swallowed) |
| `disable` "User not found" `NotFoundError` | `_open_disable` trailing `except KaletaError as exc` → `error.set_text(exc.message)` (inline label — resolves no key) | English (inline only; key would be dead) |
| `disable` "That password or code is not right." `ValidationError` ×2 | `_open_disable` `except ValidationError:` → `t("settings.mfa_disable_failed")` | English (swallowed) |

#### hosted_mfa_service.py (11 raises → 0 migrated, 11 English)

No raise here reaches `notify_kaleta_error`: the password error is surfaced
only inline, and every other raise is swallowed by a type-specific `except`.

| Raise (method @ msg) | Caller / handler | Decision |
|---|---|---|
| `begin_hosted_enrolment` "That password is not right." `ValidationError` | `security_tab._begin_hosted._confirm` `except ValidationError as exc:` → `error.set_text(exc.message)` (inline label, when not rate-limited) | English (inline only; key would be dead) |
| `begin_hosted_enrolment` `_ALREADY_ON` `ConflictError` ×2 | `_begin_hosted._confirm` `except ConflictError:` → `t("settings.mfa_stale")` | English (swallowed) |
| `confirm_hosted_enrolment` "That code is not right…" `ValidationError` | `_open_setup._confirm` `except ValidationError:` → `mfa_enrol_failed` | English (swallowed) |
| `confirm_hosted_enrolment` `_ALREADY_ON` `ConflictError` | `_open_setup._confirm` `except ConflictError:` → `mfa_stale` | English (swallowed) |
| `recover` "That recovery code was used in another tab." `ConflictError` | `login_mfa._submit` `except ConflictError:` → navigates to login `"mfa_gone"` | English (swallowed) |
| `disable_hosted` `_NOT_ON` `ConflictError` ×2 | `_open_disable` `except ConflictError:` → `mfa_stale` | English (swallowed) |
| `disable_hosted` "That password or code is not right." `ValidationError` ×2 | `_open_disable` `except ValidationError:` → `mfa_disable_failed` | English (swallowed) |
| `_identity_of` "Start the two-factor setup before confirming it." `ConflictError` | reached via `confirm_hosted_enrolment` → `_open_setup._confirm` `except ConflictError:` → `mfa_stale` (and via `abandon_hosted_enrolment`, which surfaces nothing) | English (swallowed) |

#### api_token_service.py (3 raises → 1 migrated, 2 English)

| Raise (method @ msg) | Caller / handler | Decision |
|---|---|---|
| `_require_step_up` "Confirm with a two-factor code before changing API tokens." `ValidationError` | `security_tab._create_token` AND `_revoke` → `except KaletaError` → `notify_kaleta_error`. Reachable in the race the view comments call out (factor switched on in another tab after the step-up check said off). | **migrate → `errors.api_token.confirm_code_before_changing`** |
| `create_token` "Label is required" `ValidationError` | only caller `security_tab._create_token` pre-validates `if not label: ui.notify(...); return` (strips + checks) **before** calling, so the service guard is never reached from the UI; no API caller exists | English (unreachable from any caller — defensive duplicate of the view's own check) |
| `generate_raw_token` "No tenant context to mint an API token for" `ValidationError` | called inside `create_token`, after the view has established the tenant context; a developer invariant never true on the view path, and `create_token` has no API caller | English (post-context invariant) |

### Which raises the test drives directly
`tests/integration/test_error_i18n_2fa.py` drives one **real** raise per
migrated service (`mfa_service`, `api_token_service`) against the lane
Postgres (`hosted_mfa_service` migrated nothing, so it is not driven):
- `api_token_service._require_step_up` via `ApiTokenService.create_token(...)`
  with MFA enabled and a `None` `mfa_verified_at` → asserts the
  `errors.api_token.confirm_code_before_changing` key and that
  `t(key)` reproduces the English `exc.message`.
- `mfa_service.regenerate_recovery_codes` with the factor off → asserts
  `errors.mfa.enable_before_recovery_codes`.

Each uses the `_assert_localizes` helper (as the sibling cohort tests do):
`exc.message_key == expected` and `t(exc.message_key, **(exc.params or {})) ==
exc.message`. Every migrated key is additionally covered by a both-locales
presence table and a locale-format table, with the Polish literals from
KAL-ERR-007 asserted against `pl.json` directly (BDD literals, rule 11). None
of the migrated raises interpolates params, so every `params` is `{}`.

### i18n placement
`errors.mfa` and `errors.api_token` are appended as the last siblings of the
`errors` object (after `errors.household`), per the slice brief — avoids
textual git conflicts with sibling lanes editing earlier `errors.*` blocks.
Polish terminology matches the existing settings keys: "uwierzytelnianie
dwuskładnikowe", "kody zapasowe".

### View changes
None — the three files are services. The test is integration-only and touches
no file under `src/kaleta/views/`.

### Landed
Commit `163ed95` (PR #362), author Dawid (Ani), merged 2026-10-23.

Files touched:
- `docs/bdd.md`
- `docs/plans/README.md`
- `src/kaleta/i18n/locales/en.json`
- `src/kaleta/i18n/locales/pl.json`
- `src/kaleta/services/api_token_service.py`
- `src/kaleta/services/mfa_service.py`
- `tests/integration/test_error_i18n_2fa.py`
