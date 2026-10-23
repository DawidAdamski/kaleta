---
plan_id: errors-i18n-household
title: Localize household_service error toasts
area: cross-cutting
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Localize household_service error toasts

## Intent
A follow-up slice of [`errors-i18n-message-keys`](archive/errors-i18n-message-keys.md),
which shipped the carrier (`KaletaError.message_key` + `params`), the
`error_handling.resolve_toast_text` wiring, and migrated the first cohort.
This slice migrates **only** `src/kaleta/services/household_service.py`: its
user-facing `KaletaError` raises now carry an `errors.household.*` key so a
Polish session reads the household-sharing toast in Polish, while logs, event
capture and the API keep reading the English `exc.message`.

## Scope
Covers:
- `household_service.py`: add `message_key="errors.household.<slug>"`
  (+ `params` where the message interpolates) to each user-facing raise,
  keeping the existing English string byte-identical as the positional
  `message` fallback. `code` values, control flow and behaviour unchanged.
- The `errors.household` block in `en.json` and `pl.json` (30 keys),
  appended at the END of the existing `errors` object.
- `docs/bdd.md`: `KAL-ERR-006` + a covering integration test.

Does NOT cover:
- Any other service (each gets its own follow-up slice — the chore line in
  `chores.md` stays open until all services are done; this plan does NOT tick it).
- Changing `code` values, control flow or any behaviour.
- The REST API error contract (household has no API surface at all; still the
  English `message` everywhere a view does not localize).
- `src/kaleta/exceptions.py` (the raised classes already accept
  `message_key`/`params` directly from `KaletaError`; no `StaleWriteError`
  thread needed here).

## Acceptance criteria
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `uv run python scripts/check_doc_links.py`
- `grep -q "KAL-ERR-006" docs/bdd.md`
- `uv run pytest tests/integration -k "error_i18n or household" -n 2 -m "not slow"`

## Touchpoints
- `src/kaleta/services/household_service.py` — migrated raises.
- `src/kaleta/i18n/locales/en.json`, `pl.json` — `errors.household.*`.
- `docs/bdd.md` — `KAL-ERR-006`;
  `tests/integration/test_error_i18n_household.py`.

## Open questions
- Resolved to plan defaults (no user input while armed).

## Implementation notes
- **Slice boundary.** Covers `household_service` only. `chores.md` follow-up
  line stays unticked.
- **No API surface.** A full `grep` of `src/kaleta/api/` finds no reference to
  `HouseholdService`/`HouseholdInvitations` or any household flow. Every raise
  below is reached only through the view layer: `views/settings/household_tab.py`,
  `views/unlock.py` and `views/join.py`, via the `src/kaleta/auth/household.py`
  thin wrapper (`with_household`, `approve_member`, `remove_member`,
  `leave_household`, `reset_my_keys`, `accept_invitation`). Those views either
  call `views.error_handling.notify_kaleta_error` (toast, which localizes via
  `resolve_toast_text`) or set an inline dialog/field label from `exc.message`
  (English fallback today; the key is a latent, byte-identical improvement for
  if/when those inline paths adopt `resolve_toast_text`). Both are user-facing
  presentation of the message, so both are migrated.
- **Totals:** 33 raise statements; **32 migrated**, **1 skipped**. 30 distinct
  keys (two are shared by two raises each: `hand_over_before_leaving` for the
  identical `remove` + `leave` guard, `key_not_current` for the identical
  `HouseholdRekey._claim` + `_require_current_key` guard).
- **Per-raise classification (caller-searched, line numbers pre-edit):**

  | Raise (method @ line) | Reached from | Decision → key |
  |---|---|---|
  | `HouseholdRekey._remaining_holders` @231 | `remove`/`leave` dialogs (re-key) | migrate → `member_no_key_to_seal` |
  | `HouseholdRekey._claim` @279 | `remove`/`leave` dialogs | migrate → `household_rekeying_already` |
  | `HouseholdRekey._claim` @283 | `remove`/`leave` dialogs | migrate → `key_not_current` (shared) |
  | `for_subject` @339 | every view op via `with_household`; `household_tab._body` shows `exc.message` | migrate → `not_a_member` |
  | `waiting_room` @379 | `unlock._waiting_room`, which **catches `ConflictError` and returns `None`** — message never shown | **skip** (swallowed internal control-flow signal; a key would be dead) |
  | `invite` @417 | household_tab `_invite` → `notify_kaleta_error` | migrate → `invite_email_required` |
  | `invite` @424 | household_tab `_invite` toast | migrate → `email_belongs_to_other_account` |
  | `invite` @427 | household_tab `_invite` toast | migrate → `already_a_member` |
  | `invite` @438 (`{max_members}`) | household_tab `_invite` toast | migrate → `household_full` |
  | `approve` @488 | household_tab `_approve` dialog (inline `exc.message`) | migrate → `only_pending_can_be_approved` |
  | `approve` @493 | household_tab `_approve` dialog | migrate → `member_no_passphrase` |
  | `approve` @498 | household_tab `_approve` dialog | migrate → `member_key_changed` |
  | `decline` @514 | household_tab `_decline` → `notify_kaleta_error` | migrate → `only_pending_can_be_declined` |
  | `remove` @537 | household_tab `_remove` dialog | migrate → `hand_over_before_leaving` (shared) |
  | `remove` @540 | household_tab `_remove` dialog | migrate → `only_active_can_be_removed` |
  | `transfer_ownership` @549 | household_tab `_make_owner` → `notify_kaleta_error` | migrate → `already_the_owner` |
  | `transfer_ownership` @552 | household_tab `_make_owner` toast | migrate → `only_active_can_be_owner` |
  | `leave` @564 | household_tab `_leave` → `notify_kaleta_error` | migrate → `hand_over_before_leaving` (shared) |
  | `reset_keys` @576 | unlock `_confirm_reset` → `notify_kaleta_error` | migrate → `reset_not_a_member` |
  | `reset_keys` @579 | unlock `_confirm_reset` toast | migrate → `owner_key_cannot_reset` |
  | `set_display_name` @591 | household_tab `_save_name` → `notify_kaleta_error` | migrate → `name_required` |
  | `set_display_name` @594 (`{max_length}`) | household_tab `_save_name` toast | migrate → `name_too_long` |
  | `set_display_name` @598 | household_tab `_save_name` toast | migrate → `account_being_set_up` |
  | `_take_out` @612 | `remove`/`leave` dialogs | migrate → `member_no_account` |
  | `_take_out` @619 | `remove`/`leave` dialogs (tenant deleted in a race) | migrate → `household_gone` |
  | `_member` @647 | `approve`/`decline`/`remove`/`transfer_ownership` (member_id from UI) | migrate → `member_not_found` |
  | `_require_current_key` @720 | `approve` (owner, mid re-key) | migrate → `household_rekeying` |
  | `_require_current_key` @723 | `approve` | migrate → `key_not_current` (shared) |
  | `_require_active` @728 | every member op | migrate → `membership_pending` |
  | `_require_owner` @734 | every owner op | migrate → `only_owner` |
  | `_require_key` @740 | `approve`/`remove`/`leave` (encryption on, locked) | migrate → `unlock_first` |
  | `HouseholdInvitations.accept_with_password` @788 | join view `_submit` (inline `exc.message`) | migrate → `email_has_login` |
  | `HouseholdInvitations.accept_with_password` @795 | join view `_submit` | migrate → `invitation_just_used` |

- **The one skip — `waiting_room` @379.** It is the only raise whose message
  a user can never see. `views/unlock.py::_waiting_room` wraps the call in
  `try: … except ConflictError: return None`, so the `ConflictError` is a
  control-flow signal ("this member is no longer pending"), never rendered.
  Giving it a key would add a translation nothing resolves. Left English,
  no key.

- **`household_gone` @619.** Kept as a migrate rather than an invariant-skip:
  unlike the transaction slice's "… not found after commit" raises (which run
  inside the same committed transaction), this `Tenant` fetch can legitimately
  return `None` if the household is deleted concurrently with a `remove`/`leave`,
  and the remove/leave dialog surfaces `exc.message`. Low-cost to localize.

- **Format-spec params.** `household_full` keeps `{max_members}` and
  `name_too_long` keeps `{max_length}`; `str.format` (what `t` uses)
  reproduces the exact English fallback (`self.max_members` / `DISPLAY_NAME_MAX`),
  asserted in the integration test's locale-format table.

- **i18n placement.** `errors.household` is appended as the last sibling of
  the `errors` object (after `errors.account`), per the slice brief — avoids
  textual git conflicts with sibling lanes editing earlier `errors.*` blocks.

- **Which raises the test drives directly.** `household_service` needs a
  signed-in membership / tenant context to construct, so most raises are hard
  to trigger in a plain session fixture. The integration test drives the two
  guard raises reachable without any tenant wiring — `_require_active`
  (`membership_pending`) and `_require_owner` (`only_owner`) — through a
  minimal in-memory `TenantMembership`. For each, the test asserts the raise
  carries the expected `message_key` and that `t(exc.message_key, **exc.params)`
  reproduces the unchanged English `exc.message` (the `_assert_localizes`
  helper, as in the sibling cohort tests). The Polish literals from
  KAL-ERR-006 are asserted against `pl.json` directly (`_resolve`). Every one
  of the 30 keys is additionally covered by a both-locales key-presence and
  locale-format table (BDD literals, rule 11).

- **View changes.** None — `household_service` is not a view. The test is
  integration-only and touches no file under `src/kaleta/views/`.
</content>
</invoke>
