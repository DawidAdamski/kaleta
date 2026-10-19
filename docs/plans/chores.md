# Chore inbox

One-liners spotted mid-task: dead code, naming nits, missing guards, tiny
refactors, flaky tests. Not everything deserves a plan and an issue — see
the "Small findings" section of `AGENTS.md` for the rule of thumb.

**How to use it**

- Add a one-line checkbox while the finding is fresh. Say where it is and
  why it matters; a line nobody can act on six weeks later is worse than
  no line.
- Fix it *here* only if it belongs to the branch you already have open —
  same file or area, trivially small. Never as a drive-by on an unrelated
  branch (Working Agreement §9).
- Triage periodically: tick it off, or promote it to a plan in
  `docs/plans/` when it turns out to span layers or need a design
  decision.

---

## Open

- [x] `IrregularItemService.create_funding_plan` dedupes a planned transfer by
      `existing.amount == plan.monthly_total` (`irregular_item_service.py`).
      Now that the gifts total folds into `monthly_total` (`gifts-irregular-fund`),
      changing the gift list moves the proposed monthly amount, so a second
      transfer can be planned next to the now-stale one. Pre-existing behaviour
      (a stored-item edit already does this), not a regression — but gifts make
      it easier to hit. Consider keying the dedupe on the fund/route rather than
      the exact amount, or updating the existing active plan in place.
      Fixed in `funding-plan-refresh-amount` (KAL-IRR-006): the dedupe now keys
      on the route (source → fund account), not the amount; an equal amount
      still conflicts ("already planned"), but a changed contribution refreshes
      the one transfer's amount in place instead of adding a second.

- [x] Two orphaned i18n keys in `settings` (pre-existing, spotted during
      `settings-seed-panel-unify`): `settings.dark_mode` and
      `settings.rate_label` have no `t()` reference anywhere in `src/` or
      `tests/` (the `dark_mode` hits are `app.storage.user["dark_mode"]`, a
      different thing). Drop both from `en.json`/`pl.json`.
      Dropped in `i18n-hygiene-orphans-and-gender` (both locales).

- [x] `scripts/seed.py` (and so Settings → Data → Example data) fails on a
      fresh registry-layout family: the `taxonomy` seeder inserts the 8
      `CANONICAL_TAGS`, which the new family already has, and dies on
      `uq_tags_name_bidx`. Skip tags that exist, as it already does for the
      subscription children. Found while measuring the compose stack for
      `self-host-guide`.
      Fixed in `seed-fresh-family-canonical-tags`: the seeder now skips
      canonical tags already filed (by blind index), like the subscription
      children. Confirmed live in dogfooding ("seed everything" on a fresh
      family); it succeeded after a wipe+reseed because the wipe clears the
      tags first. Covered by KAL-PLT-011.
- [ ] `docs/plans/README.md`: the archived `postgres-only` row has Effort and
      Status swapped (`archived | draft`), and `scripts/plan_archive.sh` makes
      the same swap on every run (the archiver corrected it by hand for
      `instance-admin-panel`).
- [ ] Any WARNING+ logged after `_register_views()` but before `ui.run()`
      crashes startup ("ui.page cannot be used in NiceGUI scripts…"). The log
      ring buffer's session resolver `views/error_handling.current_client_id`
      touches `context.client`, and that access outside a page flips NiceGUI
      into script mode. Guard it (e.g. return `None` while
      `not app.is_started`) so a late startup log line cannot kill the app.
      Found while wiring `warn_secure_cookie_in_debug()`, which now runs early
      in `run_web`/`run_app` to stay clear of it.

- [ ] Reports render the service's English display strings, in every locale.
      `SavedReportService` returns *words*, not keys: column headers
      (`"Category"`, `"Total Amount"` …, `saved_report_service.py:535-540`,
      `:584-629`), `_WEEKDAY_NAMES` (`:39`), the `type` dimension's raw enum,
      and the `"Uncategorised"` / `"No Institution"` fallbacks. A Polish
      session reads them in English in the table's column heads, the bar rows'
      labels and the pivot's column heads. `reports.dim_*`, `reports.metric_*`
      and `reports.type_*` already hold every one of those words. Durable fix:
      the results carry dimension/metric *keys* (and weekday ordinals) and the
      views resolve them through `t()` — a shape change across both result
      types, so it wants a plan rather than a line here if nobody gets to it.
      Pre-existing; `plan/reports-second-dimension-pivot` localized the pivot
      grid's own row header off the sentence and left the rest alone.

- [ ] `scripts/seed.py` aborts on any alembic-created schema:
      `TransactionsSeeder` raises `KeyError: 'Żywność'` because
      `categories_by_name` (top-level only) comes back without the catalog's
      expense categories. Repro: fresh `HOME` + empty SQLite, `uv run alembic
      upgrade head`, `uv run python scripts/seed.py`. The same script on a
      `Base.metadata.create_all` schema seeds all 2362 rows, so it is model
      vs. migration drift, not the catalog. It takes
      `scripts/restyle_fidelity.py shoot` down with it — the ephemeral app it
      screenshots is seeded that way — which is why all thirteen fidelity
      reports are stale and `check all` is red on `main`. Found from
      `plan/reports-second-dimension-pivot`, whose artboard `3e` criteria
      could not be made executable because of it.

- [ ] `tests/integration/test_reset_password_cli.py::global_db_restored`
      restores the shared `AsyncSessionFactory` only under postgres; on the
      default SQLite run `ResetPasswordCli`'s `configure_database(tmp_path)`
      is left pointing at the test's throwaway file for the rest of the
      session. Pre-existing — the two oldest cases skip under postgres for
      the same reason — but `plan/auth-two-factor` grew the number of cases
      that repoint the global factory from two to six, so a future SQLite
      test reaching for `with_session` would fail pointing at the wrong
      database. Capture and re-apply whatever URL was configured on entry,
      unconditionally.

- [ ] `EncryptedString` (`src/kaleta/db/types.py`) calls `_key_source()`
      *inside* `process_bind_param` / `process_result_value`, so every bind
      and every result value runs a fresh HKDF-SHA256. Invisible with the one
      encrypted column `auth-two-factor` shipped; `hosted-field-encryption`
      turns it into one derivation per row per column across a table of them.
      Memoize on `settings.secret_key` (or the tenant key version, once the
      key ring exists) so the "read at call time" property the docstring
      relies on — a rotated key takes effect without a restart, and tests can
      swap the source — still holds. Belongs to whoever picks up that plan.

- [ ] argon2 work runs synchronously on the NiceGUI event loop:
      `MfaService.disable()` does one password verify plus up to ten
      recovery-hash verifies (its own docstring prices that at roughly a
      second), and `confirm_enrolment()` / `regenerate_recovery_codes()` each
      hash ten codes in a row. `AuthService` already blocks once per login,
      so this is a 10x of an accepted pattern rather than a new one — but the
      single-process app stops serving for the duration.
      `asyncio.to_thread(...)` around the loops would free the loop and keep
      the deliberately constant cost.

- [ ] `tests/unit/db/test_encrypted_columns.py::TestStatementCacheKey`
      asserts on SQLAlchemy's private `_static_cache_key`. The invariant is
      real and worth pinning — `cache_ok = True` is a lie if the AAD is not
      part of the type identity — but a private attribute can change shape
      across point releases and would then fail as a confusing
      `AttributeError` rather than as the caching bug it is guarding against.
      A round-trip through two differently-AAD'd columns on one engine would
      pin the same thing against public behaviour.

### Carried over from GitHub issue #20

Migrated verbatim on 2026-09-23 when this file replaced the issue as the
inbox. **Not re-verified** — treat each as a lead, not a finding, and
check it still reproduces before acting on it.

- [ ] `SavedReportService._flow_dimension`: unreachable final return
      references `Category` without a join — replace with `raise ValueError`
      / `assert_never` so a future new dimension fails loudly.
- [ ] e2e round-trip for KAL-API-001 (create via API → visible in the
      Transactions UI).
- [ ] `SettingsSection._update_currency_warning` (import view): warns
      `File currency () differs from account currency (PLN)` when the file's
      currency is unknown — `validate_import_readiness` already skips on a
      falsy currency, and the warning path should too.
- [ ] `tests/e2e/test_navigation.py::test_every_nav_entry_routes` is flaky:
      failed once in three consecutive `verify.sh --e2e` runs on an
      otherwise green tree, passes in isolation. It clicks every nav entry
      in a loop and likely races the drawer re-render after
      `_ensure_group_expanded`.
- [ ] `tests/e2e/test_transactions.py::test_split_row_action_prearms_editor`
      and `::test_add_edit_split_transaction` are flaky: Save stayed disabled
      for the whole 10s, i.e. the split lines never balanced — the race
      `_set_split_amount` already documents, where under load the `Tab` that
      commits the first line's amount loses to the "Fill last" click. A
      deterministic fix would wait for the server to reflect the typed
      figure before clicking Fill last.
- [ ] `tests/e2e/test_transactions.py::test_split_row_indicator_and_plain_row`
      joins the two above: failed once in five full `verify.sh --e2e` runs
      on a green tree, passed either side. Same split-dialog family, same
      suspected race.
- [ ] `test_add_edit_split_transaction` failed once in six full
      `verify.sh --e2e` runs for a different reason: the dialog had closed
      (the save went through) but the new row was not on page 1 — the suite
      leaves 800+ movements, many dated today, so a fresh row can land past
      the 50th. Find the row through the search chip rather than
      `get_by_text(...).first` on page 1.
- [ ] `tests/e2e/test_csv_import.py::test_map_unrecognised_csv_and_import`
      (KAL-CSV-005) failed once in a full `verify.sh --e2e` run on a green
      tree, passing in isolation and with its whole file (27/27). Observed
      during `feat/import-format-first`, which touches only the import page
      and whose import tests all pass together — so a cross-file shared-state
      race, not that change. It walks Format → Upload → mapping; the suspect
      is the mapping step not being on screen yet when the panel assertion
      fires under load. A `to_be_visible` already has a 10s timeout, so the
      fix is likely waiting on the file's parse state, not a longer timeout.
- [ ] `tests/e2e/test_rules.py::test_rules_apply_during_csv_import` (KAL-RUL-002)
      failed once in a parallel `--e2e` run, passed on re-run and 2/2 in
      isolation. Same import-wizard step-node-click-under-`-n auto` fragility
      the `_goto` fix (`fix/import-step-reclick-wedge`) addressed for the
      deterministic re-click case: a raw `page.locator('[data-step=N]').click()`
      followed immediately by `expect(panel).to_be_visible()` can race the
      `_sync_step` refreshable rebuild under load. The shared `_import_step` /
      `_step` helpers across the import e2e should wait on the step node's
      `aria-current`/active state before asserting the panel, rather than
      racing the repaint.
- [ ] Payment calendar: `_out` / `_net` sum the day's subscription charges
      inside `views/payment_calendar.py`, mirroring `day_marks` beside them.
      Nothing callable from a service owns "what leaves on a day", so the
      sheet and the grid can drift apart again. — *done on
      `plan/restyle-fidelity-screens` as `services/day_totals.py::DayTotals`,
      pending that PR.*
- [ ] `views/payment_calendar.py::_load_grid` returns `tuple[MonthGrid, Any]`,
      so the wizard projection sources it hands back are untyped. Name the
      type rather than leaving `Any` in a signature.
- [ ] The desktop "Needs attention" banner's rows
      (`dashboard_widgets/wizard_actions.py::_render_row`) are `div`s with a
      click handler and no `role`, `tabindex` or key handler, so each item is
      pointer-only. The phone card's rows got `role="button"`, `tabindex="0"`
      and Enter/Space on `plan/restyle-fidelity-phone-widgets`; the banner
      beside it did not.
- [ ] Four restyle plans spell their human sign-off `[owner]` where
      `docs/plans/README.md` defines `[manual]`:
      `docs/plans/archive/restyle-fidelity-screens.md`,
      `restyle-fidelity-shell-dashboard.md`, `restyle-dashboard-rethink.md`
      (all archived) and `restyle-fidelity-phone-widgets.md` (fixed on its
      own branch). `.claude/hooks/dod-gate.sh` only skips `[manual]`, so it
      tried to run `[owner]` as a shell command. Normalise the three
      archived ones, or teach the gate both spellings.

- [x] Reserve fund balances never follow the ledger. → promoted to
      [`accounts-ledger-balances`](archive/accounts-ledger-balances.md) (2026-09-30).
      `ReserveFundService._account_balance` (`reserve_fund_service.py`)
      reads `Account.balance`, and nothing but the seeder and the account
      form writes it — `AccountService.adjust_balance` has no caller. So a
      transfer into a fund's backing account leaves the fund card, its
      progress and the below-target warning where they were. Blocks
      `funds-savings-goals` (GOL-002) and `funds-irregular-items`
      (IRR-004/005); likely wants a plan of its own (derive balances from
      transactions vs keep a running column), since forecast and net worth
      read the same column. Found by `plan/audit-planned-vs-code`.

- [ ] `ReserveFundService.list_with_progress` runs the 12-month expense
      aggregate once per fund with `target_from_spending`
      (`_effective_target` → `target_monthly_expense`). Compute it once
      per call and pass it down if funds ever multiply. Found by review of
      `plan/funds-reserve-derived-target`.

- [x] `PayeeService.merge` (manual merge on /payees and
      `POST /api/v1/payees/merge`) does not reassign `Subscription.payee_id`,
      so subscriptions keep pointing at the deleted payee;
      `DedupeService.merge_payees` does. Make one delegate to the other.
      Found by `plan/payees-merge-suggestions-gaps`. Fixed in
      `plan/payees-identities-automerge` (it now reassigns subscriptions
      too; the two merges still exist side by side).

- [x] `WizardProjectionService._monthly_from_subscription` still amortises
      a subscription as `amount × 30 / cadence_days` (120.00 yearly →
      9.86/mo) with its own 27–33 / 350–380 cadence ranges, while the
      Subscriptions panel now counts a yearly bill as a twelfth (KAL-SUB-002).
      Reuse `subscription_service._to_monthly` and its
      `MONTHLY_CADENCE_RANGE` / `YEARLY_CADENCE_RANGE`. Found by
      `plan/subscriptions-panel-gaps`.
      Fixed in `projection-subscription-monthly` (KAL-SUB-009): the projection
      now delegates to `_to_monthly`, so the builder and the panel agree
      (yearly 120.00 → 10.00). The `_subscription_cadence_label` ranges are
      still inlined — a cosmetic duplicate, left as a separate follow-up below.
- [x] `wizard_projection_service._subscription_cadence_label` inlines the same
      27–33 / 350–380 day ranges as `subscription_service`'s
      `MONTHLY_CADENCE_RANGE` / `YEARLY_CADENCE_RANGE`. Point it at the shared
      constants too (zero behaviour change) — deferred from
      `projection-subscription-monthly` to keep that diff single-purpose.
      Done in `chore/cadence-label-shared-ranges`: the label now reads
      `in MONTHLY_CADENCE_RANGE` / `in YEARLY_CADENCE_RANGE`.

- [ ] A cancellation scheduled for a future date (KAL-SUB-004) only flips
      to `cancelled` when `SubscriptionService.settle_due_cancellations`
      runs, which today is on opening `/wizard/subscriptions`. Until then,
      readers that filter on `status != CANCELLED` (unplanned radar, the
      detector's tracked-payee set, `GET /api/v1/subscriptions`) still see
      it as active. Settle at startup / in the backup scheduler tick if that
      lag ever matters. Found by `plan/subscriptions-panel-gaps`.

- [ ] Loan-linked transactions (KAL-DBT-004) are excluded from
      `ReportService` and `MoneyFlowService` only. Other income/expense
      readers still count them: `BudgetService` actuals, `ForecastService`,
      `SavedReportService`, `SalaryService`, `UnplannedRadarService`,
      `MonthlyReadinessService`, `ScenarioService`, `ReserveFundService`.
      Add `Transaction.id.not_in(loan_linked_transaction_ids())` where the
      figure means "spending" rather than "cash moved". Found by
      `plan/debts-ledger-link`.

- [ ] `uv run alembic check` on a fresh head DB reports index drift
      unrelated to any recent plan: `ix_categorisation_rules_pattern`,
      `ix_import_rules_filename_pattern`, `ix_import_runs_account_id`,
      `ix_import_runs_created_at` exist in migrations but not in the models
      (or vice versa). Reconcile with one migration or `index=True`. Found by
      `plan/debts-ledger-link`.
- [ ] Move `merchant_key_from_description` out of `subscription_service` into
      a shared helper module. The radar and `PlannedPriceDriftService` import
      it from there, and `subscription_service` now imports
      `PlannedTransactionService`. Nothing is circular yet, but the services
      are coupled. Found by `plan/recurring-to-planned`.
- [ ] `setup_service._sync_url` rewrites drivers with a whole-string
      `str.replace`. A password containing `+asyncpg` gets corrupted, and
      asyncpg's `?ssl=require` is not psycopg2's `sslmode=require`. Rebuild the
      URL with `make_url(...).set(drivername=...)` and translate the SSL query
      arg. Found by `plan/deps-sqlalchemy-2-1`.
- [ ] Report builder: on a one-dimensional month/year report with a
      change or moving-average column on, `top_n` is not applied (a trend
      needs every period), but the sentence still reads "top 10". Grey the
      top-N slot out or say "all periods" there. Found by
      `plan/reports-trend-columns`.
- [ ] e2e servers spawned by `tests/e2e/conftest.py` (and the secure-cookie
      one in `test_auth.py`) inherit `NICEGUI_STORAGE_PATH` from the pytest
      process, which importing `kaleta` pinned to the developer's real
      `~/.kaleta/nicegui` — so e2e session files land there, not under the
      temp `HOME`. Drop the variable from the child env, as the restart test
      does. Found by `plan/auth-session-hosted-readiness`.
- [ ] With `KALETA_REDIS_URL` set and Redis unreachable, the rate limiter
      raises inside the login/MFA click handlers (fail closed, by design);
      the views do not catch it, so the user gets no message. Wrap the
      limiter calls in `views/login.py`, `views/login_mfa.py` and
      `views/settings/security_tab.py` and show a "try again shortly" toast.
      Found by `plan/auth-session-hosted-readiness`.
- [ ] `MoneyFlowService` reads a transfer's direction as "lower id is the
      source leg" (`src.id < dst.id`). Rows paired after the fact
      (`TransactionService.pair_as_transfer`, import "accept") can have the
      incoming leg older than the outgoing one, so the flow is drawn
      backwards. Store the direction (or read it from which leg was the
      expense) instead of inferring it from ids. Found by
      `plan/transfers-manual-pairing`. The direction is stored now
      (`Transaction.transfer_direction`, `plan/accounts-ledger-balances`):
      join on the `out` leg instead of the id order.
- [ ] A planned transfer (`SalaryService.create_salary_plan`, "Pay
      yourself a salary") posts only its outgoing leg on the source
      account. The target account is named only in the description, so
      now that balances follow the ledger the money leaves one account and
      arrives nowhere. Give `PlannedTransaction` a target account and post
      both legs through `create_transfer`. Net worth's month-by-month
      history (`NetWorthService._monthly_history`) skips every transfer row,
      so it does not see that lone leg either, while the current balance
      does. Found by `plan/accounts-ledger-balances`.
- [ ] The ledger shows every transfer leg as money out
      (`TransactionService.signed_amount` signs by type only), so the
      incoming leg of a goal contribution reads "-500.00" on the account
      it arrived on. Sign it by `transfer_direction`, which rows now
      carry. Found by `plan/funds-savings-goals`.
- [ ] e2e tests still click options straight from an open `.q-menu`
      (`page.locator(".q-menu").get_by_text(...).click()`) instead of
      `tests/e2e/ledger.pick_open_menu_option`, so they break once the shared
      instance holds enough rows to push their option out of the rendered
      slice. Sweep them onto the helper. Found by
      `plan/funds-savings-goals`.

- [ ] `notify_kaleta_error` toasts `exc.message` verbatim, so service errors
      reach Polish users in English — now common with payee identity
      conflicts ("'…' is already an identity of payee '…'") and merge undo.
      Map error codes to `t()` keys. Found by
      `plan/payees-identities-automerge`.

- [ ] A settings validation error prints pydantic's `input_value` dict, which
      includes the start of `KALETA_SECRET_KEY` (and any other secret set in
      the environment or `.env`) on stderr at startup. Wrap `Settings()` so a
      `ValidationError` is reported by message only. Found by
      `plan/hosted-tenancy-foundation`.

- [ ] "Seed example data" fails with `KeyError: 'Żywność'`
      (`seeders/transactions.py`) on any database built by the migrations —
      self-hosted and hosted alike, also on `main`. The migrations seed the
      Subscriptions category tree, so `TaxonomySeeder.count()` (all
      categories) is non-zero, the taxonomy step is skipped, and the later
      seeders look up categories that were never created. Tests miss it
      because they build the schema with `create_all`, which has no seed
      rows. Count only the seeder's own categories (or check for
      "Żywność"), and add a test on a migrated database. Found in the manual
      run of `hosted-tenancy-foundation`.
- [ ] **Flaky e2e `test_a_late_upload_does_not_take_the_step_you_chose`
      (KAL-CSV-028).** Failed once in a full `verify.sh --e2e` run (1 of 219)
      and passed 3/3 when rerun on its own. Under load, step panel 2 stays
      hidden for 5 s after its node is clicked (`_step` in
      `tests/e2e/test_csv_import.py`). Most likely the second file's upload
      handler finishes late and takes the step back. Look for the race in the
      view, not the timeout. Seen on `plan/auth-hosted-email-links`, which
      does not touch import.
- [ ] **Two e2e runs at once share ports and corrupt each other.** The e2e
      servers use fixed ports (8081–8086), and `_wait_for_server` in
      `tests/e2e/conftest.py` accepts whichever server answers. A second
      `pytest tests/e2e/` started during a first one logs in to the *first*
      run's instance. If that instance's `test_mfa` has already enrolled 2FA,
      every login lands on `/login/mfa` and around 200 tests error with 401s
      and timeouts. It happened when the goal-mode DoD gate ran
      `verify.sh --e2e` while `review_gate.sh`'s reviewer was running the e2e
      suite too. Fix: fail fast when the port is already bound before
      spawning, or pick free ports.
- [ ] **`test_a_days_totals_count_its_subscription_charges` fails on the 2nd
      of every month** (`tests/e2e/test_planned_transactions.py`). It seeds
      its subscription on day 2 "because no other test in this file seeds
      it". But when today *is* the 2nd, the file's other tests seed "today",
      so the cell reads `-3 273.99`, not `-12.99`. It passes alone and fails
      with its file, on `main` too (seen 2026-10-02). Fix: pick a day that is
      neither today nor seeded, e.g. the 3rd, or the 4th when today is the 3rd.
- [ ] **`alembic check` reports drift that predates the models it names**:
      `ix_import_runs_account_id` and `ix_import_runs_created_at` exist in the
      migrations but not on `ImportRun`; on Postgres also `TIMESTAMP` vs
      `DateTime(timezone=True)` on `currency_rates`, `saved_reports`, `tags`,
      `reserve_funds.archived_at`, and the `fk_categories_parent_id` ondelete.
      Seen while checking `hosted-field-encryption`'s revision, which is clean.
      Fix: declare the indexes on the model (or drop them) and align the types
      in one revision.
- [ ] **CI does not run the suite with `KALETA_ENCRYPTION=passphrase`.**
      `hosted-field-encryption` made `uv run pytest tests/unit tests/integration`
      green in that mode on SQLite and Postgres, but only locally; add a
      matrix entry (SQLite + the Postgres job) so a regression under
      encryption is caught.
- [ ] **No `.containerignore`: every image build sends the whole repo.**
      `podman compose -f compose.hosted-dev.yml up --build` ships ~180 MB of
      build context (`.venv`, `site/`, caches, `.env`) to the builder, though
      the Containerfiles `COPY` only `src/`, `alembic*/` and the lock files.
      Seen in `hosted-supabase-rollout`. Fix: a `.containerignore` (and
      `.dockerignore` symlink) that excludes everything but those paths.
- [ ] **No retention sweep for error events and bug reports in `multi` mode.**
      `main._register_event_retention_scheduler` returns early on a hosted
      instance (the tables live in every tenant schema), so events and
      reports stay until the account is deleted — `docs/privacy.md` says so.
      Seen in `hosted-supabase-rollout`. Fix: sweep each tenant schema in turn.
- [ ] **`scripts/plan_archive.sh` writes the status into the wrong column.**
      Archiving `test-suite-speed` put "archived" in the Effort column of the
      programme table (Plan | Effort | Status | Depends on) and added a
      spurious "no touchpoints matched" note; fixed by hand in PR #193. Also:
      `.github/workflows/plan-archive.yml` fires for any merged `plan/*`
      branch and failed on `plan/postgres-only-programme`, which is a
      programme branch, not a plan id. Seen while archiving `test-suite-speed`.
- [ ] **The password form has no per-account throttle.** `login_rate_limiter`
      is keyed by client address, so guesses against one e-mail from many
      addresses are unbounded (every backend). Seen in the review of
      `postgres-only` part A. Fix: a second limiter keyed by the normalised
      e-mail, with the same lock-out sentence.
- [x] **`kaleta.db.base.engine` is built at import and used by nobody.**
      `create_engine()` runs when `kaleta.db` is imported and is re-exported
      from `kaleta.db.__init__`, but every session goes through
      `AsyncSessionFactory`. Seen in `postgres-only` part B2b. Deleted in
      part B3 (it was the last SQLite `connect_args` branch).
- [ ] **`SignedIn.tenant` and the `login_session` family are still optional.**
      Since ADR-38 every sign-in has a family and `rotate_session` refuses one
      without; `tenant: SessionTenant | None = None` in `auth/sign_in.py` and
      `auth/session.py` only lets a caller forget it. Seen in `postgres-only`
      part B2b. Fix: make it required and drop the `None` branches.
- [ ] **`install_data_key_resolver` may have no caller left that needs it.**
      A family's `TenantContext.key_ring` wins whenever a context is set, and
      every data session has one now; the resolver answers only outside a
      family. Seen in `postgres-only` part B2b. Fix: find what still reads a
      data key with no context, then drop the resolver (and
      `install_unlock_resolver`) or say why it stays.
- [ ] **Flaky e2e `test_mfa.py::test_two_factor_authentication` at KAL-AUTH-015.**
      Once in four full `verify.sh --e2e` runs on `postgres-only` part B2b, the
      password sign-in after `clear_cookies()` stayed on `/login` with no
      message (line ~178); `test_auth.py` + `test_mfa.py` passed 3/3 together
      and the file passes alone. Cause not found — a click before the page's
      websocket is up is the suspect. Fix: find it before adding any wait.
      Seen again on `funds-irregular-items` (2026-10-12) one step earlier, at
      KAL-AUTH-014 (the first password sign-in after enrolling): 1 of 3 runs of
      the file *alone* failed in 15 s, so it reproduces without the suite —
      on `main` too (a674bc0: 1 of 4 alone), and twice running in full
      `verify.sh --e2e` on that branch at line ~178.
- [ ] **"Fetch NBP rates" has no throttle.** Any member of any family can
      press it, and each press is one request to api.nbp.pl for the whole
      instance (idempotent, public data). Seen in the review of `postgres-only`
      part B2c. Fix: a per-instance minimum interval, or skip when today's
      table is already stored after NBP's publication hour.
- [ ] **Some family timestamp columns are `timestamp without time zone`.**
      The models say `DateTime(timezone=True)` (`TimestampMixin`) but the
      migrations built `tags`, `currency_rates` and `saved_reports`
      `created_at`/`updated_at` naive on PostgreSQL; `audit_log.timestamp`
      and `personal_loans.settled_at` are naive in the models too. Seen in
      `postgres-only` part B3, which dropped the "SQLite hands back naive
      datetimes" fallbacks only where the columns are `timestamptz`. Fix: one
      migration to `timestamptz` (`USING … AT TIME ZONE 'UTC'`) and the models
      to match.
- [ ] **Household name and the "MFA on/off" column are not built.**
      `hosted-household-sharing` §5 lists both on Settings → Household; Part B
      left them out (a new `EncryptedText` column and migration with nothing
      reading it yet; a provider call per member on every render). Fix: the
      column on `tenants` or the family's settings, and an MFA status cached
      at sign-in.
- [ ] **Disabling a login from `/admin` forgets the wrong revocation-cache
      entry.** `forget_revoked_member` calls `revocation_cache.forget(user_id)`,
      which keys by the *current* tenant — the administrator's family, not the
      disabled member's — so another family's member keeps a cached watermark
      for up to `TTL_SECONDS` (60 s). Seen while wiring household removal (same
      family there, so not affected). Fix: `forget(user_id, tenant_id=…)`.
- [ ] **The stale-write guard covers only the transaction dialog.** Part C of
      `hosted-household-sharing` refuses a save over a newer version of a
      transaction (`TransactionUpdate.expected_updated_at`). Accounts, budgets,
      planned transactions and the rest still let the last save win silently;
      each editor would pass the `updated_at` it loaded the same way.
- [x] **`safety_funds.archived_section_body` (pl) is masculine-only** — "Fundusze,
      które wycofałeś". Gender-neutral: "Wycofane fundusze. Możesz je przywrócić w
      każdej chwili." Seen by the i18n check of `funds-irregular-items`.
      Rewritten to the gender-neutral wording in `i18n-hygiene-orphans-and-gender`.
- [ ] **Merging duplicate transactions drops their links.** `DedupeService.merge_transactions`
      deletes the non-keepers; a duplicate's `irregular_item_id` (and, as before,
      `planned_transaction_id`) is not moved to the keeper. Seen in the review of
      `funds-irregular-items` Part B.
- [ ] **`GET /api/v1/budgets/?year=` ignores the year without `month`.** The route
      documents "Use `year` to filter by year", but `BudgetService.list` only filters
      when `month` is given, so every year's budgets come back. Seen writing the
      `budgets-annual-review` e2e. Fix: filter by `year` alone too (and a test).
- [ ] **The budget builder's Apply stacks handlers.** `views/budget_builder.py` calls
      `diff_apply_btn.on_click(_confirm)` on every opening of the diff dialog, so the
      n-th confirmation runs `apply` n times (idempotent upserts, but n commits). Seen
      while reusing its dialog for the annual review, which builds its own once.
- [ ] **The plan archiver writes "archived" into the wrong column** of the gap-closing
      table in `docs/plans/README.md` (`| Plan | Issue | Effort | Status | … |`): the
      Issue column (losing e.g. `#10 IRR`) while Status keeps `draft`. Every archived row
      of that table shows it.
- [ ] **Three copies of the version resolver.** `kaleta.__version__`
      (`src/kaleta/__init__.py`), `views/layout.py` (`_APP_VERSION`) and
      `views/auth_common.py` (`app_version`) each read the package version
      independently, with their own `"v0.1.0"` offline fallback. Point the two view
      helpers at `kaleta.observability.app_version()` so there is one resolver (deferred
      from `auto-versioning` Part 1 to keep that PR off the view layer — touching a view
      forces the e2e gate).
- [x] **Orphaned subscriptions i18n keys.** `subscriptions.notes_show`,
      `notes_hide` and `note_indicator` exist in both `en.json`/`pl.json` but are
      referenced nowhere in `src/` (leftovers from an earlier notes-toggle refactor;
      `rows.py::_render_sub_row_notes` no longer uses them). Drop them from both
      locales. Spotted by i18n-verifier during `subscriptions-categories` Part B.
      Dropped in `i18n-hygiene-orphans-and-gender` (both locales).
- [ ] **Security assessment findings F-1..F-4 await fixes.** The 2026-10-12
      assessment (`docs/security/assessment-2026-10-12.md`) recorded four
      Low/Info items — `/health` info disclosure, always-on OpenAPI docs,
      cookie not `Secure`-by-default with no prod warning, and no server-side
      upload byte cap. Slice 2 of `security-assessment` plans their fixes
      (each with a `KAL-SEC-*` regression test); logged here so none is lost
      if Slice 2 slips.
- [ ] **`api/v1` `update_*` endpoints return an ORM model as a Response.** The
      `update_*` handlers in `transactions/payees/institutions/categories/budgets`
      return `Service.update(...)` which is typed `Model | None`, while the
      endpoint is annotated `-> XxxResponse`; FastAPI serialises it via
      `response_model`, and every sibling `create/get/list` carries
      `# type: ignore[return-value]`. `lint-hardening-part-2` added the missing
      ignore to the `update_*` ones (they were only hidden by a stale mypy cache).
      Consider typing these returns properly (e.g. `XxxResponse.model_validate`,
      or a shared helper) and dropping the whole family of `# type: ignore`.
- [ ] **Backup restore-from-file has no UI-level e2e.** `KAL-SET-015` is
      `@automated` only at the `BackupService` level (`tests/integration/
      test_backup.py`); the Settings → Data tab upload widget itself is
      untested, which is exactly why `data_tab._on_upload` silently broke
      on the NiceGUI 2.x→3.x upload-event API change (fixed in
      `dogfooding-bugs-wave-1` slice 1, alongside the institution logo
      upload which now has an e2e). Add an e2e that uploads a backup ZIP in
      the Data tab and confirms the restore, so the UI handler is guarded.
- [ ] **Category create reported "Nazwa jest wymagana" with a name typed
      (#4, dogfooding).** Could not be reproduced on `main`
      (`dogfooding-bugs-wave-1` slice 2): typed-name + Save creates the
      category every time, including fast-typing + immediate Save; a
      duplicate raises "already exists", not "name required". Revisit if it
      recurs on a fresh deploy — capture whether it was a non-localhost
      server and whether the name was typed fast (hypothesis: stale
      build, or an input value-sync race only visible under network
      latency).
- [ ] **Enter does not submit app dialogs.** `ui.keyboard(on_key=...)` in
      the Add/Edit dialogs (categories, planned, institutions, …) never
      fires while a field is focused, because NiceGUI's `ui.keyboard`
      defaults to `ignore=['input','select','button','textarea']`. So the
      Enter-to-save wiring is dead in the normal case; only the Save button
      works. Decide on a cross-cutting fix (e.g. per-input `keydown.enter`
      submit, or a non-ignoring keyboard) rather than patching one dialog.
      Noted during `dogfooding-bugs-wave-1` slice 2.
- [ ] **Subscriptions root protection is service-layer only (follow-ups from
      `dogfooding-bugs-wave-1` slice 5).** `CategoryService.delete` refuses the
      flagged root, and the Categories view hides its delete button, but: (a)
      there is no DB-level guard (a trigger/constraint) and nothing stops
      `update()` from re-parenting the root (ruled out of scope for the slice);
      (b) `views/categories.py` `confirm_delete` does not wrap `svc.delete` in
      `notify_kaleta_error`, so a stale page that still shows the (now hidden)
      delete button would surface an unhandled `ConflictError` — same gap as
      `save_add`/`save_edit`, which also don't catch. Consider a consistent
      KaletaError toast across the Categories view's mutations, and decide
      whether the root needs re-parent/rename protection too.
- [x] **#19 Dashboard: account names overflow their card border (dogfooding).**
      Account-name text overflows the dashboard widget/tile; clip/ellipsis or
      wrap. UX/layout → candidate for wave 2.
      Fixed in `dashboard-account-name-overflow`: the balance-card tile binds
      its name label to the tile width so `truncate` clips to an ellipsis
      (with the full name on a tooltip) instead of the nowrap name spilling
      past the tile and the card.
- [x] **#20 Safety fund: cannot return to the "months to cover" input
      (dogfooding).** In the safety-funds view, switching to another sub-view
      and back loses the screen holding the target-months figure — no way back.
      Navigation/state bug; capture exact steps on retest.
      Repro (user): in the New reserve fund dialog, switch Fund type Emergency →
      Irregular → Emergency; the "Cover N months" + Derive controls don't come
      back. Fixed in `safety-funds-kind-toggle-visibility`: `_on_kind_change`
      read the raw Quasar `e.args` (not the option key) so the emergency-only
      rows never re-showed; now reads `kind_in.value`.
- [ ] **#21 New feature: Gifts (dogfooding).** List of people + events + amounts
      (like the annual plan); sum, divide by 10, feed as a monthly irregular
      reserve. Needs its own plan, not a chore — check against the existing
      `KAL-GFT` gifts scenario/issue first to avoid duplication.
- [x] **#22 Editing a transaction scrolls the page back to the top
      (dogfooding).** Scroll position is lost after an edit — tiring on a long
      ledger. UX bug in the transactions view → candidate for wave 2.
      Fixed in `transactions-keep-place-on-save`: edit and pair-as-transfer
      now refresh in place (keep the current page, restore the scroll offset);
      add/delete still reset to the top on purpose (see the plan's Scope).
- [x] **#23 Rules: the category picker lists only leaf/child categories
      (dogfooding).** Roots are missing (or only subcategories shown), so a
      category is hard to find when writing a rule. Bug/UX in the Rules view.
      Fixed in `rules-category-picker-hierarchy`: the real cause was a flat
      `{id: name}` option map, so a child showed as a bare name beside its root
      with no hierarchy. Now reuses `CategoryService.build_option_labels`
      ("Root → Child", tree order) — the same builder Reports uses.
- [ ] **#24 Subscriptions: the "all subscriptions" list disagrees with the
      categories, and there is no billing cadence (dogfooding).** The panel's
      list does not match what sits under the subscription categories; also add
      a per-subscription frequency (monthly/yearly). Bug + small feature —
      investigate with the subscriptions-root work (#6) and the subscriptions
      ADR.
- [ ] **#25 Transactions: "select all" fails with a search filter + grouping
      (dogfooding).** With a description-search filter AND grouping by
      month/week, the select-all checkbox does not select everything — it
      flashes an "x of y shown" state then re-renders. Bug in the transactions
      multi-select; shares the selection infra with #17 (bulk change-category),
      so plan the two as one slice.
      Investigated during `transactions-bulk-category` (#17): could NOT
      reproduce as a correctness failure. A targeted e2e (one account, 6 rows
      spread across two months, month grouping, header select-all — with and
      without an upcoming planned row) selected all 6 real rows and correctly
      excluded the planned one. The "flash" is `_on_selection` →
      `_keep_selected_rows` re-syncing when select-all ticks a planned row that
      has no checkbox; it settles to the right set. Likely needs a more
      specific repro (virtual scroll with many rows, or a pre-#263 state).
      Left open — #17 shipped on its own.
- [ ] **Debounce the ledger search input (perf, not correctness).** Each
      keystroke in the transactions search box fires its own `count`+`list`
      query; the render-token guard (`transactions-search-render-race`) keeps
      the UI correct, but a `debounce=300` on the Quasar input would cut a
      word from N queries to one. Left out of the race fix because debounce
      masks the race rather than fixing it (and hid the token from its test);
      do it purely for query load if it ever matters.
- [x] **The e2e tier flakes under timing load, which can block archival/CI.**
      `scripts/verify.sh --e2e` runs `pytest tests/e2e/` with no rerun; a
      transactions cluster (`test_transactions.py` row-count waits, a category
      picker "resolved to 2 elements") intermittently times out, then passes
      clean on re-run — same serial, deterministic order, so it is timing, not
      a code defect. It bit `plan_archive.sh` (which re-runs `verify --e2e` as
      an acceptance criterion) during the `rules-category-picker-hierarchy`
      archive. Options: add `pytest-rerun`/`--reruns` to the e2e tier only, or
      pin the specific flaky waits. (The `test_mfa` parallel flake is a related,
      already-noted instance.)
      Fixed in `chore/e2e-rerun-timeout-flakes`: added `pytest-rerunfailures`
      (dev dep) and a `pytest_collection_modifyitems` hook in
      `tests/e2e/conftest.py` that marks every e2e test
      `flaky(reruns=2, only_rerun=["Timeout.*exceeded", "strict mode
      violation"])`. Scoped to the e2e tier (path guard) and to timing
      signatures only: a deterministic failure does not match, or matches but
      fails on every attempt, so a real regression is never masked — only
      timing flakes are rescued (rule 4). Lives in the conftest, not
      `scripts/verify.sh` (a protected DoD gate script), so CI gets the same
      tolerance. Did not pin individual waits.
