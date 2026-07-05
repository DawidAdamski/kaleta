---
plan_id: q3-views-refactor
title: Views refactor — split god-objects, shared components, retire controllers
area: views
effort: large
status: archived
roadmap_ref: ../../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Views refactor — split god-objects, shared components, retire controllers

## Intent

`views/reports_canned.py` (1 247 LOC) and `views/transactions.py`
(1 234 LOC) mix rendering, state, and business logic; four more views
exceed 600 LOC. This blocks outside contributors and makes every UI
change risky. Implements **ADR-032**: the controller layer is retired,
views call services directly, and business logic that leaked into
views moves down into services.

**Blocked by:** `q3-test-safety-net` — do not start until e2e is green.

## Scope

- New `src/kaleta/views/components/` package with shared components,
  extracted from existing duplicated code (not invented new):
  - `transaction_table` (used by transactions, subscriptions, credit,
    reports),
  - `amount_label` — semantic colouring helper (income green, expense
    red, transfer neutral) used everywhere an amount renders,
  - `filter_bar` (account/category/date-range/description),
  - `empty_state`.
- Split every view file > 800 LOC into a thin page module (routing,
  layout, wiring) + per-section component modules. Order:
  1. `transactions.py`, 2. `reports_canned.py`, 3. `import_view.py`,
  4. `settings.py`, 5. `dashboard_widgets.py`, 6. `budget_plan.py`.
  One PR per view — do not batch.
- While splitting: any computation, aggregation, or persistence found
  inline in a view moves to the owning service (with a unit test).
- ADR-032 cleanup: delete `src/kaleta/controllers/`, update the
  architecture diagram and layer description in `CLAUDE.md`,
  `AGENTS.md`, `docs/architecture.md`.
- **Not in scope:** visual redesign, new features, i18n changes beyond
  moving keys, renaming routes.

## Acceptance criteria

- No file in `src/kaleta/views/` exceeds 500 LOC.
- `grep` finds no SQLAlchemy imports and no `session` usage in
  `views/` (data access only via services).
- Amount colouring comes from the single `amount_label` component in
  all views (no local colour logic left).
- Full e2e suite green after **each** PR, not just the last one.
- `src/kaleta/controllers/` no longer exists; docs updated per
  ADR-032.
- ruff + mypy strict pass.

## Touchpoints

All of `src/kaleta/views/`, `src/kaleta/services/` (logic moving
down), `CLAUDE.md`, `AGENTS.md`, `docs/architecture.md`,
`tests/unit/` (new service tests), i18n keys move with their
components.

## Open questions

- Component API convention: plain functions returning NiceGUI
  elements vs small classes? (Suggest: functions; classes only where
  the component holds refreshable state.)
- Does `dashboard_widgets.py` split per-widget (one file each) or by
  size group? **Resolved:** per-widget modules under `views/dashboard_widgets/`,
  with KPI/half/full size metadata in `registry.py`; layout persistence in
  `layout.py`.

## Implementation notes

### dashboard_widgets (2026-07-04)

- Split `dashboard_widgets.py` (766 LOC) into `views/dashboard_widgets/` package:
  one module per widget, shared `registry.py` (Widget type, `register`, `WIDGETS`,
  `DEFAULT_WIDGETS`, `cycle_size`), `helpers.py` (card/chart UI helpers),
  `layout.py` (`default_layout`, `resolve_user_layout`, legacy migration).
- Removed sqlalchemy imports from views; widgets use `AsyncSession` via
  `TYPE_CHECKING` and `TransactionType` from `kaleta.schemas.transaction`.
- Removed `pyproject.toml` lint-import ignores for `dashboard_widgets`.

### import_view (2026-07-04)

- Split `import_view.py` (800 LOC) into `views/import_view/` package: thin
  `page.py` (wiring) + one module per wizard section.
- Moved inline logic to `import_service.py`: `auto_decode`, `parse_queued_file`,
  preview row classification, queue settings inheritance, import readiness
  validation. Unit tests in `test_import_service.py`.
- Views now use `with_session` (no `kaleta.db` / model imports); category
  pickers use `CategoryService.build_option_labels`.
- Reused `amount_label.amount_body_cell_slot` for preview amounts and
  `empty_state.table_no_data_slot` for empty queue.
- Removed `pyproject.toml` lint-import ignores for `import_view`.

### settings (2026-07-04)

- Split `settings.py` (785 LOC) into `views/settings/` package: thin
  `page.py` + one module per tab (General, Appearance, Features, Data,
  History, About).
- Moved inline logic to services: `AuditService.list_for_display` /
  `changed_field_names`, `CurrencyRateService.build_relevant_pairs` /
  `list_recent_for_pairs` / `create_with_inverse`, `BackupService.export_filename`.
  Unit tests in `test_settings_services.py`.
- Views now use `with_session` (no `kaleta.db` / model imports).
- Removed `pyproject.toml` lint-import ignores for `settings`.

### budget_plan (2026-07-04)

- Split `budget_plan.py` (690 LOC) into `views/budget_plan/` package: thin
  `page.py` (wiring) + `grid.py`, `dialogs.py`, `toolbar.py`, `constants.py`,
  `helpers.py`.
- Moved inline grid computation to `budget_service.py`: `uniform_monthly_amount`,
  `build_category_plan_row`, `build_annual_plan_grid`, `load_annual_plan_grid`.
  `CategoryService.sort_with_children` for hierarchical category ordering.
  Unit tests in `test_budget_service.py`.
- Views now use `with_session` (no `kaleta.db` / model imports).
- Removed `pyproject.toml` lint-import ignores for `budget_plan`.

### subscriptions (2026-07-04)

- Split `subscriptions.py` (626 LOC) into `views/subscriptions/` package: thin
  `page.py` (wiring) + `dialogs.py`, `rows.py`, `helpers.py`, `constants.py`.
- Moved inline logic to `subscription_service.py`: `build_notes_preview`,
  `category_group_monthly_total`, `parse_subscription_form`. Unit tests in
  `test_subscription_service.py`.
- Views now use `with_session` (no `kaleta.db` / model imports); category
  pickers use `CategoryService.build_option_labels`; amounts use `amount_label`.
- Removed `pyproject.toml` lint-import ignores for `subscriptions`.

### reports (2026-07-04)

- Split `reports.py` (541 LOC) into `views/reports/` package: thin `page.py`
  (wiring) + `saved_section.py`, `palette.py`, `config_zone.py`, `chart_zone.py`,
  `constants.py`.
- Moved inline logic to `saved_report_service.py`: `chart_type_icon`,
  `report_config_from_builder_state`, `build_report_table_data`. Unit tests in
  `test_saved_report_service.py`.
- Views now use `with_session` (no `kaleta.db` / model imports); category
  pickers use `CategoryService.build_option_labels`.
- Removed `pyproject.toml` lint-import ignores for `reports`.

### personal_loans (2026-07-04)

- Split `personal_loans.py` (540 LOC) into `views/personal_loans/` package: thin
  `page.py` (wiring) + `dialogs.py`, `rows.py`, `helpers.py`.
- Moved inline logic to `personal_loan_service.py`: `compute_remaining`,
  `parse_loan_form`, `parse_repayment_form`. Unit tests in
  `test_personal_loan_service.py`.
- Views now use `with_session` (no `kaleta.db` / model imports); category
  pickers use `CategoryService.build_option_labels`; amounts use `amount_label`.
- Removed `pyproject.toml` lint-import ignores for `personal_loans`.

### budgets (2026-07-04)

- Split `budgets.py` (514 LOC) into `views/budgets/` package: thin `page.py`
  (wiring) + `overview.py`, `realization.py`, `dialogs.py`, `chart.py`,
  `helpers.py`, `constants.py`.
- Moved inline logic to `budget_service.py`: `date_range_for_key`,
  `format_date_range_label`. Unit tests in `test_budget_service.py` and
  `test_budget_range.py`.
- Views now use `with_session` (no `kaleta.db` / model imports); category
  pickers use `CategoryService.build_option_labels`.
- Removed `pyproject.toml` lint-import ignores for `budgets`.

### views burn-down part 1 (2026-07-05)

- Converted `accounts`, `categories`, `credit`, `dashboard`, `forecast`,
  `housekeeping`, `institution_avatar`, `institutions`, `layout` to the
  established pattern: `with_session`, schema responses/enums, `TYPE_CHECKING`
  for sqlalchemy typing-only imports.
- Added `dispose_sessions()` to `kaleta.services.session` for layout close-db.
- Credit loan schedule preview uses `CreditService.amortisation` instead of
  constructing `LoanProfile` in the view.
- Removed 18 `pyproject.toml` lint-import ignores for the above modules.

### views burn-down part 2 (2026-07-05)

- Converted `budget_builder`, `monthly_readiness`, `net_worth`, `payees`,
  `payment_calendar`, `planned_transactions`, `safety_funds`, `setup`, `tags`,
  `wizard` to the established pattern: `with_session`, schema responses/enums,
  `CategoryService.build_option_labels` where applicable.
- Moved first-run DB activation (`run_migrations`, `configure_database`,
  `save_db`) to `kaleta.services.setup_service.activate_database`.
- Re-exported `AssetType`, `ReserveFundKind`, `ReserveFundBackingMode` from
  schema modules for view-layer enum imports.
- Removed all remaining `pyproject.toml` `ignore_imports` entries from the
  `views-no-data-access` contract (list deleted entirely).

### Exit criteria — LOC cap (2026-07-04)

Verified with `wc -l src/kaleta/views/**/*.py` after the final split:

- **Result: PASS** — no file under `src/kaleta/views/` exceeds 500 LOC.
- Largest files: `budget_builder.py` (480), `credit.py` (466), `safety_funds.py`
  (465), `credit_calculator.py` (462), `forecast.py` (460).
- Previously over-cap files now split: `personal_loans` (max module 319 LOC),
  `budgets` (max module 149 LOC).

### Exit criteria — zero direct data access in views (2026-07-05)

Verified with `lint-imports` (`views-no-data-access` contract, no
`ignore_imports`) and `rg 'from kaleta\.(db|models)|AsyncSessionFactory'
src/kaleta/views/`:

- **Result: PASS** — no view module imports `kaleta.db`, `kaleta.models`, or
  `sqlalchemy` directly; session scope goes through `with_session` /
  `activate_database` (setup).
- **Both exit criteria pass:** LOC cap (≤500 per file) and zero direct data
  access in views.

## Implementation

Landed 2026-07-04 — 2026-07-05 (`af86520`..`7b219b7`).

| SHA | Author | Date | Message |
|---|---|---|---|
| `af86520` | Dawid (Ani) | 2026-07-04 | refactor(views): transactions package + shared components |
| `234cb32` | Dawid (Ani) | 2026-07-04 | refactor(views): reports_canned package |
| `7b8b77e` | Dawid (Ani) | 2026-07-04 | refactor(views): split subscriptions into package with service helpers |
| `04dec62` | Dawid (Ani) | 2026-07-04 | refactor(views): split reports builder into package with service helpers |
| `9382d41` | Dawid (Ani) | 2026-07-04 | refactor(views): import_view package |
| `2006374` | Dawid (Ani) | 2026-07-04 | refactor(views): settings package |
| `451ea63` | Dawid (Ani) | 2026-07-04 | refactor(views): dashboard_widgets per-widget package |
| `03f5fc1` | Dawid (Ani) | 2026-07-04 | refactor(views): budget_plan package |
| `3eb2d61` | Dawid (Ani) | 2026-07-04 | chore: working agreement rules 8-10, verify e2e auto-gate, bdd data-safety |
| `c71705b` | Dawid (Ani) | 2026-07-04 | Split personal_loans view into package modules. |
| `ea92d8d` | Dawid (Ani) | 2026-07-04 | Split budgets view into package modules. |
| `26c7ee3` | Dawid (Ani) | 2026-07-04 | Document personal_loans and budgets splits plus LOC exit criteria. |
| `0cc377c` | Dawid (Ani) | 2026-07-05 | refactor(views): burn down import-linter ignores for nine small views |
| `7b219b7` | Dawid (Ani) | 2026-07-05 | refactor(views): complete burn-down — with_session for remaining ten views |

**Aggregate:** 165 files changed, +11 483 / −5 763 lines (`af86520^..7b219b7`).

**What shipped:**
- Shared `views/components/` package: `transaction_table`, `amount_label`,
  `filter_bar`, `empty_state`.
- God-object splits into thin page modules + section packages for
  `transactions`, `reports_canned`, `subscriptions`, `reports`, `import_view`,
  `settings`, `dashboard_widgets`, `budget_plan`, `personal_loans`, `budgets`.
- Inline view logic moved to services with unit tests (`import_service`,
  `subscription_service`, `saved_report_service`, `personal_loan_service`,
  `budget_service`, settings helpers).
- `with_session` / schema enums pattern rolled out to all remaining single-file
  views; `setup_service.activate_database` for first-run DB wiring.
- `views-no-data-access` import-linter contract enforced with zero
  `ignore_imports` entries.
- `src/kaleta/controllers/` removed (ADR-032); e2e suite green after each
  landing commit (`./scripts/verify.sh --e2e`).

**Resolved open questions:**
- Component API: plain functions; `@ui.refreshable` classes only where state
  must be held across re-renders.
- `dashboard_widgets`: per-widget modules under `views/dashboard_widgets/`.

**Deferred / partial:**
- `amount_label` adopted in split views and transaction tables; some older
  views still use `theme.AMOUNT_*` constants directly — follow-up hygiene if
  strict single-source colouring is required.
- Architecture diagram in `docs/architecture.md` still lists `controllers/` in
  the tree sketch (ADR-032 body is current).
- Cosmetic polish drafts folded here (not separate plans): settings panel
  surface tokens (`settings-panel-color-fix`), credit dark-mode contrast
  (`credit-dark-mode-color-fix`), dashboard chart fluid height
  (`dashboard-chart-fluid-height`). Pick up opportunistically during view
  touch-ups or a dedicated Q4 polish pass.

**Verification (2026-07-05):** `./scripts/verify.sh --e2e` — VERIFY OK (1245 unit/
integration, 44 e2e); import-linter `views-no-data-access` KEPT with no ignores.
