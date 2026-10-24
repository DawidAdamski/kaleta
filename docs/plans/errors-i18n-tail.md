---
plan_id: errors-i18n-tail
title: Localize the toast-reaching long-tail error raises
area: cross-cutting
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Localize the toast-reaching long-tail error raises

## Intent
The final cohort slice of
[`errors-i18n-message-keys`](archive/errors-i18n-message-keys.md), which shipped
the carrier (`KaletaError.message_key` + `params`), the
`error_handling.resolve_toast_text` wiring, and migrated the first cohort. The
earlier slices covered transactions, funds, irregular items, core CRUD,
household, 2FA, encryption and admin/infra. This slice mops up the remaining
long tail of services that still had plain-English `KaletaError` raises reaching
a toast: `import_rule_service`, `annual_review_service`,
`unplanned_radar_service`, `planned_transaction_service`,
`planned_price_drift_service`, `category_template_service`,
`saved_report_service`, `report_columns`, `monthly_readiness_service`,
`institution_logo_service`, `audit_service`, `account_deletion_service`,
`scenario_service` and `forecast_service`. Only raises whose `exc.message`
actually reaches a key-resolving path (`notify_kaleta_error` →
`resolve_toast_text`) get a `message_key`; logs, event capture and the API keep
reading the English `exc.message`.

## Scope
Covers:
- The services above: add `message_key="errors.<service>.<slug>"` (+ `params`
  where the message interpolates) to each raise whose message reaches
  `notify_kaleta_error`, keeping the English string byte-identical as the
  positional `message`. `code` values, control flow and behaviour unchanged.
- The `errors.import_rule`, `errors.annual_review`, `errors.unplanned_radar`,
  `errors.planned_transaction`, `errors.planned_price_drift` and
  `errors.account_deletion` blocks in `en.json` / `pl.json`, appended at the END
  of the `errors` object (after `errors.bug_report`).
- `docs/bdd.md`: `KAL-ERR-010` + a covering integration test.

Does NOT cover:
- Any other service (each cohort is its own slice).
- Changing `code` values, control flow or behaviour.
- The REST API error contract (API responses stay English).
- Localizing raises the surfacing view renders **inline** (`set_text` /
  `state["error"]`), catches **by type** to substitute its own key, that have
  **no `except KaletaError` arm** at all, or that run only in a **background job**
  / **CLI** — a `message_key` there would be a dead key (there is no global
  NiceGUI exception handler).
- Bare `RuntimeError` / `ValueError` raises (not `KaletaError`, cannot carry a
  key).

## Acceptance criteria
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `uv run python scripts/check_doc_links.py`
- `grep -q "KAL-ERR-010" docs/bdd.md`
- `uv run pytest tests/integration/test_error_i18n_tail.py -n 2 -m "not slow"`

## Touchpoints
- `src/kaleta/services/import_rule_service.py`
- `src/kaleta/services/annual_review_service.py`
- `src/kaleta/services/unplanned_radar_service.py`
- `src/kaleta/services/planned_transaction_service.py`
- `src/kaleta/services/planned_price_drift_service.py`
- `src/kaleta/services/account_deletion_service.py`
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `docs/bdd.md` — `KAL-ERR-010`; `tests/integration/test_error_i18n_tail.py`

## Open questions
- Resolved to plan defaults (no user input while armed).

## Implementation notes

### Totals
**26 `KaletaError`-subclass raises triaged across 12 services (two services have
zero raises); 13 migrated, 13 left English.** 12 distinct keys (the two
`annual_review` subscription-not-found raises share one key). Low yield is the
honest outcome, as expected for the long tail: most raises are post-commit
invariants, inline-rendered, caught by type, or reached only through a view
caller that has no `except KaletaError` arm.

### Surfacing-path facts (the evidence)
No global NiceGUI exception handler exists; only a raise reaching a view arm that
does `except KaletaError as exc: notify_kaleta_error(exc)` is localized. Each
raise was traced to its view caller(s):

- **`settings/import_tab.py`** — the rule-edit dialog's save (`:63`) and the
  active toggle (`:173`) both wrap `ImportRuleService.update` in
  `except KaletaError: notify_kaleta_error(exc)`. `update` (not-found),
  `_require_account` (account not-found, via `update`) and `_normalise_pattern`
  (pattern empty / too long, via `update`) therefore toast. (The `import_view`
  `upsert_from_import` path is caught by a broad `except Exception` rendered
  inline as `import.rule_save_failed`, and `import_rules.py` is API-only — both
  ignore a key, but the settings path localizes, so migrating is correct.)
- **`views/annual_review.py`** — `_save_adjust` (`:318`) and `_drop` (`:330`)
  wrap `AnnualReviewService.adjust` / `drop` in
  `except KaletaError: notify_kaleta_error(exc)`, so the subscription-not-found
  raises toast. **`carry`** (`:133`) runs `with_session(_load)` with **no
  try/except**, so its `ValidationError` would be unhandled, not a toast — and
  the UI clamps the input to `-100` anyway, so the guard is unreachable: DEAD.
- **`views/wizard_unplanned_radar.py`** — the dialog's `save()` closure (`:332`)
  wraps `UnplannedRadarService.create_planned_from_candidate` in
  `except KaletaError: notify_kaleta_error(exc)`; both the name and amount guards
  toast.
- **`views/payment_calendar.py`**, **`views/planned_transactions.py`**,
  **`views/dashboard_widgets/upcoming_planned.py`**, **`views/auto_post.py`** —
  every call into `PlannedTransactionService.post_occurrence` /
  `post_occurrences` / `post_due` sits inside an
  `except KaletaError: notify_kaleta_error(exc)` arm. So `_ensure_posted`
  (not-found) and `post_occurrences` (posted-rows-missing invariant) toast.
- **`views/planned_transactions.py::_accept_drift`** (`:332`) wraps
  `PlannedPriceDriftService.accept` in `except KaletaError: notify_kaleta_error`,
  so both its guards toast.
- **`views/settings/delete_account_section.py`** (`:88`) wraps
  `delete_signed_in_account` (→ `AccountDeletionService.delete`) in
  `except WrongPassphraseError: … except KaletaError as exc:
  notify_kaleta_error(exc)`; the unknown-tenant not-found toasts.

### Per-service decision tables

#### `import_rule_service.py` → `errors.import_rule.*` (4 raises; **4 migrated**)

| Raise (method @ line) | Surfacing path | Decision → key |
|---|---|---|
| `update` @78 not found | import_tab save / toggle → toast | **migrate** → `not_found` (`{rule_id}`) |
| `_require_account` @217 account not found | import_tab save → `update` → toast | **migrate** → `account_not_found` (`{account_id}`) |
| `_normalise_pattern` @224 pattern empty | import_tab save → `update` → toast (view pre-empts the empty case inline, but the arm would localize) | **migrate** → `pattern_empty` |
| `_normalise_pattern` @226 pattern too long | import_tab save → `update` → toast (view does not length-check) | **migrate** → `pattern_too_long` |

Three `RuntimeError` invariants (@66/@91/@169, "missing right after commit") are
**not** `KaletaError` and were left untouched.

#### `annual_review_service.py` → `errors.annual_review.*` (3 raises; **2 migrated**, 1 English)

| Raise (method @ line) | Surfacing path | Decision → key |
|---|---|---|
| `carry` @109 decrease > 100% | `annual_review.carry` runs `with_session` with **no `except` arm**; UI clamps input to -100 so the guard is unreachable | **English** (no toast arm + unreachable) |
| `adjust` @217 subscription not found | `_save_adjust` → `except KaletaError` toast | **migrate** → `subscription_not_found` (`{commitment_id}`) |
| `drop` @227 subscription not found | `_drop` → `except KaletaError` toast | **migrate** → `subscription_not_found` (shared, same English) |

#### `unplanned_radar_service.py` → `errors.unplanned_radar.*` (2 raises; **2 migrated**)

| Raise (method @ line) | Surfacing path | Decision → key |
|---|---|---|
| `create_planned_from_candidate` @212 needs a name | wizard dialog `save()` → `except KaletaError` toast | **migrate** → `name_required` |
| `create_planned_from_candidate` @215 needs a positive amount | wizard dialog `save()` → toast (view does not reject `<= 0`) | **migrate** → `amount_not_positive` |

#### `planned_transaction_service.py` → `errors.planned_transaction.*` (2 raises; **2 migrated**)

| Raise (method @ line) | Surfacing path | Decision → key |
|---|---|---|
| `post_occurrences` @534 posted rows missing | payment-calendar `_post_overdue` → toast (a post-commit invariant **deliberately** raised as a domain `ConflictError` so the view toasts rather than 500 — see the inline comment) | **migrate** → `posted_rows_missing` (`{missing}`) |
| `_ensure_posted` @585 not found | reached from post_occurrence / post_occurrences / post_due across payment_calendar, planned_transactions, upcoming_planned, auto_post — all `except KaletaError` toast | **migrate** → `not_found` (`{planned_id}`) |

One `RuntimeError` invariant (@490) is not a `KaletaError` and was left
untouched.

#### `planned_price_drift_service.py` → `errors.planned_price_drift.*` (2 raises; **2 migrated**)

| Raise (method @ line) | Surfacing path | Decision → key |
|---|---|---|
| `accept` @103 positive amount | `_accept_drift` → `except KaletaError` toast | **migrate** → `positive_amount` |
| `accept` @106 not found | `_accept_drift` → toast | **migrate** → `not_found` (`{planned_id}`) |

#### `account_deletion_service.py` → `errors.account_deletion.*` (1 raise; **1 migrated**)

| Raise (method @ line) | Surfacing path | Decision → key |
|---|---|---|
| `delete` @111 tenant not found | `delete_signed_in_account` (does not catch) → `delete_account_section._delete` → `except KaletaError` toast | **migrate** → `tenant_not_found` (`{tenant_id}`) |

#### Services that migrated **zero** (13 English raises)

| Service → raise | Decision | Why |
|---|---|---|
| `category_template_service.get` @62 | **English** | only caller `views/categories.py` has no `except KaletaError`; key fed from the catalogue, unknown-key unreachable |
| `category_template_service._ensure_root` @178 | **English** | post-lookup race invariant; same view has no toast arm |
| `institution_logo_service.save_logo` @33 | **English** | `views/institutions.py` catches **by type** (`except ValidationError`) and emits its own key `institutions.logo_invalid_format` |
| `monthly_readiness_service.mark_stage` @65 | **English** | `views/monthly_readiness.py::_mark_stage` has no `except` arm; `stage` is always a hardcoded 1–4 literal, guard unreachable |
| `saved_report_service.execute` @325 | **English** | `views/reports/page.py` catches bare `Exception` → `state["error"] = str(exc)`, rendered **inline** in `chart_zone`, never a toast |
| `saved_report_service._rows_to_pivot` @546 | **N/A** | bare `ValueError`, not a `KaletaError` |
| `report_columns.moving_averages` @177 | **English** | reached only through `execute` → same inline reports path |
| `audit_service.revert` @97 | **English** | `views/settings/history_tab.py` toasts its **own** key `audit.revert_failed` with `error=str(exc)`; `message_key` never read |
| `scenario_service` (whole module) | **N/A** | **zero** `raise` statements |
| `forecast_service` (whole module) | **N/A** | **zero** `raise` statements; `ForecastUnavailableError` is defined but never raised anywhere in `src/` |

### Interpolation notes (honest)
- `errors.planned_transaction.posted_rows_missing` interpolates `{missing}`, the
  list of orphaned transaction ids (an internal detail). The English fallback is
  byte-identical to the old f-string; only the sentence frame localizes.
- `errors.import_rule.*`, `errors.annual_review.subscription_not_found`,
  `errors.planned_transaction.not_found`, `errors.planned_price_drift.not_found`
  and `errors.account_deletion.tenant_not_found` interpolate their id param; the
  id itself is not localized.

### i18n placement
`import_rule`, `annual_review`, `unplanned_radar`, `planned_transaction`,
`planned_price_drift`, `account_deletion` appended as the last siblings of the
`errors` object (after `errors.bug_report`), to avoid a textual git conflict with
sibling lanes editing earlier `errors.*` blocks. en/pl key sets verified
identical (2547 keys each, zero diff).

### What the test drives directly
`tests/integration/test_error_i18n_tail.py` (`Covers: KAL-ERR-010`):
- Both-locales key-presence + locale-format tables over all 12 new keys.
- Real migrated raises driven directly: the pure
  `UnplannedRadarService.create_planned_from_candidate` name/amount guards (no DB
  needed) and `PlannedPriceDriftService.accept` positive-amount guard, each
  asserting the raise carries the expected `message_key` and that
  `t(exc.message_key, **exc.params)` reproduces the unchanged English
  `exc.message`.
- Polish / English literals from KAL-ERR-010 asserted against the locale files
  (BDD literals, rule 11).
- A representative **DEAD** raise (`SavedReportService.execute` grouping the same
  dimension twice) is asserted to carry **no** `message_key`, documenting the
  deliberate zero-migration decision for the inline reports path.

### View changes
None — every migrated raise lives in a service, and the test is
integration-only (no file under `src/kaleta/views/` touched).
