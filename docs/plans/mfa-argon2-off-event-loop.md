---
plan_id: mfa-argon2-off-event-loop
title: Move MfaService argon2 work off the event loop
area: auth
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Move MfaService argon2 work off the event loop

## Intent
argon2 hashing and verification are deliberately expensive (~100ms each) and
run synchronously. Three `MfaService` methods do up to ten of them in a row
on the single NiceGUI event loop, so the one-process app stops serving every
other request for up to a second while they run. Moving the blocking argon2
work to a worker thread with `asyncio.to_thread(...)` frees the loop while
keeping the deliberately constant cost. Behaviour-preserving: same hashes,
same results, just off the loop.

## Scope
Covers, and only covers, the blocking argon2 loops in three methods of
`src/kaleta/services/mfa_service.py`:

- `confirm_enrolment()` — hashing the ten recovery codes.
- `regenerate_recovery_codes()` — hashing the ten new recovery codes.
- `disable()` — the up-to-ten recovery-hash **verifies** (`_find_recovery_code`).

Does **not** cover:
- `AuthService` (one argon2 verify per login) — a separate, accepted pattern.
- `LocalIdentityService.verify_password` — the single password verify that
  `disable()` performs lives in that service, not in `MfaService`; moving it
  off the loop would mean editing a service outside this plan's scope.
- Any change to hashing parameters, results, or exception behaviour.

## Acceptance criteria
- `uv run pytest tests/unit/services/test_mfa_service.py -q`
- `uv run mypy src/`
- `uv run ruff check src/kaleta/services/mfa_service.py && uv run ruff format --check src/kaleta/services/mfa_service.py`
- `uv run lint-imports`
- `grep -q "asyncio.to_thread" src/kaleta/services/mfa_service.py`

## Touchpoints
- `src/kaleta/services/mfa_service.py` — add `import asyncio`; wrap the three
  argon2 loops; small pure-CPU helpers (`_hash_recovery_codes`,
  `_match_recovery_hash`, `_find_recovery_code_off_thread`).
- `tests/unit/services/test_mfa_service.py` — the existing suite already pins
  the behaviour (confirm/regenerate/disable, wrong secret raises the same
  typed error, concurrent claims); add a focused test that the worker-thread
  path still verifies a recovery code at `disable()`.

## Implementation notes
- The pure hash/verify helpers take plain `str` / `list[str]` and never touch
  the session or ORM attributes, so no async IO is attempted off the loop.
  ORM attribute reads (`row.recovery_codes_hash`) stay on the event loop; only
  the argon2 comparisons move to the worker thread.
- `disable()`'s mismatch handling is unchanged: the verify is wrapped in
  `_verify_hash`, which swallows `VerifyMismatchError`/`InvalidHashError`
  inside the worker and returns a bool — nothing new is raised to the awaiter.
- `_login_password_matches` (the one password verify in `disable()`) is left
  on the loop because the argon2 call sits inside `LocalIdentityService`,
  which is out of scope here.
