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
