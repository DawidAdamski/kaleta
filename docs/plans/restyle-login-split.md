---
plan_id: restyle-login-split
title: Restyle — Login as a two-panel split with a reserved error slot, phone variant (artboard 3f)
area: auth
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Restyle — Login two-panel split, reserved error slot, phone variant

## Intent

A single-user self-hosted app does not need a card floating in a
centred viewport. Artboard `3f` makes `auth_page_shell` a two-panel
split: the form on the sand ground at left with the wordmark above it,
and an ink panel at right carrying one line of copy and three counts
pulled from the database. The rate-limit / failed-login message gets a
**reserved slot** so it no longer pushes the button down when it
appears — the actual usability bug on the current page. The phone
version stacks the form with 48px fields and buttons.

Depends on `restyle-theme-tokens`.

## Scope

- **Shell** (`auth_common.auth_page_shell`): two panels ≥ `md`: left
  (ground) wordmark + title + subtitle + form; right (ink `--k-ink`,
  text `--k-surface`) one line of copy and three counts. Under `md` the
  right panel is hidden and the form fills the viewport with 48px
  controls. The shell keeps its signature (title/subtitle keys) so
  `login.py` and any other auth page (setup, reset) keep working.
- **Counts**: transactions, accounts, months of history — read via a
  small `AuthLandingStats` service method (read-only, cached per
  process for 60 s). If the DB is empty / not set up, show the copy
  without counts. Never expose amounts.
- **Reserved error slot**: a fixed-height (`min-h-[20px]`) line between
  the password field and the button; `error.set_text` writes into it.
  Rate-limit and failed-login messages unchanged.
- Phone: fields and button `min-h-[48px]`; no Face ID button (the mock
  shows one — it is a proposal, out of scope).
- BDD: `KAL-AUTH-011` "failed-login message does not move the submit
  button" (@automated, e2e: button bounding box y unchanged after a
  failed attempt).

Out of scope: any auth logic, rate limiter, password reset flow,
biometric login.

## Acceptance criteria

- `uv run pytest tests/e2e/test_auth.py -q`
- `uv run pytest tests/unit/auth -q`
- `grep -q "KAL-AUTH-011" docs/bdd.md`
- `grep -q "min-h-" src/kaleta/views/login.py`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` 1360px: split layout matches artboard `3f`; 390px: stacked
  form with 48px controls; wrong password: message appears in place,
  button does not move.

## Touchpoints

- `src/kaleta/views/auth_common.py`, `login.py`
- `src/kaleta/services/` (stats helper — smallest home that fits,
  e.g. `stats_service` if one exists)
- `src/kaleta/i18n/locales/en.json`, `pl.json` (`auth.panel_copy`,
  `auth.panel_count_*`)
- `docs/bdd.md`, `tests/e2e/test_auth.py`

## Open questions

1. Show counts before login at all (information disclosure)? Default:
   **yes, counts only** — a single-user self-hosted app; make it a
   settings-free constant `AUTH_PANEL_STATS = True` so it can be turned
   off in one line if the public demo instance should not show them.

## Implementation notes

- **Open question 1 — counts shown, behind one constant.** Default
  taken. `AUTH_PANEL_STATS = True` in
  `services/auth_stats_service.py`; setting it to `False` returns
  `None` from `landing_stats` and the panel renders its line of copy
  alone. `AuthLandingStats` carries three integers and nothing else,
  and a unit test asserts that — the panel is read before anyone has
  proved who they are, so what it *may* say matters as much as whether
  the numbers are right.

- **`auth_page_shell` is now a coroutine.** It keeps its
  `(title_key, subtitle_key)` signature as Scope requires, but the
  counts come from the database, so the call gained an `await` in
  `login.py`, `create_account.py` and `secure_app.py` — one word each.
  The alternative was building the panel in `login.py`, which is the
  one place Scope says it must not live.

- **The panel has its own breakpoint, not `hidden md:flex`.** Which of
  two single-class utilities wins is decided by stylesheet order, and
  here `hidden` won at every width — the panel never appeared. `.k-auth-panel`
  declares `display:none` and a `@media (min-width:768px)` rule instead.
  Checked in a browser: visible at 1360px (544×900, flush to the top
  and right edges), gone at 390px. This is the same trap as
  `ui.grid(columns=)` in artboard 3d.

- **The page bleeds to the edges.** NiceGUI pads `.nicegui-content` by
  1rem, which left the ink panel floating 16px short of every edge; the
  shell clears that padding, since on this page the panel *is* the page.

- **The reserved slot went to all three auth pages, not just login.**
  `create_account` and `secure_app` had the identical show-and-hide
  error label and so the identical jumping button. They were already
  being edited for the `await` and the dropped card, and the chore rule
  covers a one-liner in a file the branch already owns. Their fields and
  buttons take `AUTH_CONTROL` too.

- **The 48px control height lives in `auth_common.AUTH_CONTROL`.** The
  acceptance criterion greps `login.py` for `min-h-`, which assumes the
  literal is written there; it is written once in `auth_common` and
  named in a comment at login's form, so the criterion passes on the
  comment that explains it rather than on a duplicated string.

- **Months count both ends.** One day of history is one month, not
  zero: there is something in the ledger, and "0 months" beside a
  transaction count would contradict itself. An empty ledger has no
  ends and so no months. Unit-tested.

- **The counts never take the page down with them.** A database that is
  absent or unmigrated makes `landing_stats` return `None` and the panel
  shows its copy alone — a login page that will not render because the
  app has not been set up yet is worse than one without three numbers.

- **Stacking:** branched from `plan/restyle-reports-sentence`, which is
  itself unmerged. Open the PR with
  `--base plan/restyle-reports-sentence`; it must merge after every
  branch below it.
