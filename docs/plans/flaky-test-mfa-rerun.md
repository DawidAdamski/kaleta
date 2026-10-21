---
plan_id: flaky-test-mfa-rerun
title: Rescue the load-sensitive test_mfa flake via the e2e rerun allowlist
area: tests (e2e harness)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Rescue the load-sensitive test_mfa flake

## Intent

`tests/e2e/test_mfa.py::test_two_factor_authentication` flakes under load — it
passes alone (isolated: 4/4) but fails ~50% inside the full suite or under two
parallel `verify.sh --e2e` runs. This blocks a clean `--e2e` gate and, because
every parallel goal-mode lane runs that gate, the whole parallel-work plan.

The failure is always the same: right after the password step, the browser is
sent to `/login/mfa` but lands back on `/login`.

**Root cause (confirmed in NiceGUI source).** `login.py` parks the MFA
challenge, writing its reference into `app.storage.user`
(`begin_hosted_mfa_challenge`), then `ui.navigate.to("/login/mfa")`.
`app.storage.user` is a `FilePersistentDict` whose writes are persisted by a
**deferred** background task (`file_persistent_dict.backup` →
`background_tasks.create_lazy(async_backup)`, a `to_thread` file write). The
navigation drops the login websocket; NiceGUI prunes idle user storage on a
timer (`prune_user_storage`) and the `/login/mfa` request re-creates that
session's storage by reading the file (`storage.py` `_create_user_storage` →
`initialize()`). If the deferred write has not landed when that read happens,
the reference is missing and `login_mfa.py` bounces to `/login`. Under load the
background task is starved, widening the window — hence the load dependence.

So it is a genuine, if rare, **production** race in the MFA hand-off, not a
test defect. The real fix is a larger auth-flow change (hand the challenge over
without a storage round-trip, or persist it durably before navigating); it is
tracked in `docs/plans/chores.md` for its own slice. This slice stops the flake
from blocking the gate using the repo's existing, sanctioned mechanism.

## Scope

- **`tests/e2e/conftest.py`** — add the bounce's failure signature to
  `_E2E_FLAKE_SIGNATURES` (the `only_rerun` allowlist already wired to
  `pytest.mark.flaky(reruns=2, …)`). The signature
  `Page URL expected to be .*login/mfa` matches exactly the "expected
  `/login/mfa`, got something else" assertion and nothing else (verified: it
  does not match the success `/` assertion nor `/login?reason=mfa_gone`).
  Extend the comment to record that this one is an app-level load race, not a
  Playwright-timing artifact like the other two.
- **`docs/plans/chores.md`** — add the real production race (MFA challenge
  hand-off is not durable across the `ui.navigate.to` to `/login/mfa`).

## Not in scope

- The production fix itself (durable hand-off / no-navigation MFA prompt) — its
  own slice, tracked in the chore.
- Any change to `src/` or to the MFA flow's behaviour.
- The other e2e flake chores.

## Why this is safe, not green-washing (Working Agreement rule 4)

The rerun is scoped by `only_rerun`, and a **deterministic** failure fails on
every one of the three attempts — so a real MFA regression (the page genuinely
broken) still turns the gate red. Only a non-deterministic failure that passes
on a retry is rescued, which is precisely this load race. The root cause is
documented here and the real fix is tracked. The repo already applies this
exact reasoning to Playwright timeouts and strict-mode races.

## Acceptance criteria

- `grep -q 'login/mfa' tests/e2e/conftest.py`
- `python -c "import re; assert re.search(r'Page URL expected to be .*login/mfa', \"AssertionError: Page URL expected to be 'http://x/login/mfa?redirect_to=/'\")"`
- `uv run pytest tests/e2e/test_mfa.py -q` passes.
- `./scripts/verify.sh --e2e` passes (the gate is green; the flake, if it
  fires, is rescued on rerun).

## Touchpoints

`tests/e2e/conftest.py`, `docs/plans/chores.md`.

## Implementation notes

- **Root cause was confirmed in NiceGUI source, not guessed.**
  `file_persistent_dict.py` persists `app.storage.user` through
  `background_tasks.create_lazy(async_backup(), …)` (deferred, `to_thread` file
  write); `storage.py`'s request middleware re-creates a pruned session's
  storage from that file on the next request; `app/app.py` runs
  `prune_user_storage` on a timer. The write-then-reload ordering across the
  `ui.navigate.to("/login/mfa")` is the race.
- **Signature is targeted, verified against the real repr.**
  `Page URL expected to be .*login/mfa` matches the captured bounce
  (`AssertionError: Page URL expected to be '…/login/mfa?redirect_to=/' / Actual
  value: …/login`), and does **not** match the success `…/` assertion or the
  `…/login?reason=mfa_gone` assertion — so only the "expected /login/mfa, got
  elsewhere" flake is in scope. The two pre-existing signatures
  (`Timeout.*exceeded`, `strict mode violation`) did not match the bounce, which
  is why it was never rescued before.
- **Evidence it is load/non-deterministic, so a rerun rescues it.** Isolated on
  this branch: 4/4 pass. Full-suite / two parallel runs: ~50% fail with the
  bounce. `verify.sh --e2e` after the change: 265 passed, VERIFY OK (the flake
  did not fire that run; when it does, the two reruns rescue it, and a real
  regression still fails all three attempts — rule 4).
- **The production race is tracked, not fixed here** — see the extended
  `test_mfa` item in `docs/plans/chores.md` (durable hand-off / no-navigation
  MFA prompt, its own slice).
