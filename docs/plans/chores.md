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

- [ ] Reserve fund balances never follow the ledger.
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
