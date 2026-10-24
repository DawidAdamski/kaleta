---
plan_id: mfa-handoff-url-ref
title: Hand the MFA challenge over the URL, not a racy storage write
area: auth / login
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#settings
---

# Hand the MFA challenge over the URL, not a racy storage write

## Intent
The password step parks the challenge reference in `app.storage.user`
(`begin_hosted_mfa_challenge`) and immediately `ui.navigate.to("/login/mfa")`.
`app.storage.user` is a NiceGUI `FilePersistentDict` whose write is deferred
to a background task; the navigation drops the login websocket, NiceGUI's
storage-prune timer can evict the session, and the `/login/mfa` request then
re-reads the file. If the deferred write has not landed, the reference is
missing and the page bounces to `/login`. Load starves the background task,
so it flakes under the full suite and passes alone — a real, if rare,
production race (chores.md, cause found 2026-10-21). It is currently masked
in CI by a `flaky-test-mfa-rerun` `only_rerun` allowlist entry.

Fix: hand the challenge reference to `/login/mfa` **in the URL** (as
`/auth/session/rotate` already hands its nonce), so the page no longer
depends on the cross-request file write. The page adopts the ref into its
own session storage on load — an in-process write it then reads, with seconds
(the user typing the code) before anything re-reads the file.

## Scope
Covers:
- `begin_hosted_mfa_challenge(pending)` returns the ref (still writes it to
  storage as a belt-and-braces fallback).
- A new `adopt_hosted_mfa_challenge(ref)` in `auth/session.py`: if `ref` names
  a live challenge in the server-side `hosted_mfa_challenges` store, write it
  (and its `_AT` stamp) into this session's `app.storage.user`; an unknown or
  expired ref is ignored (falls through to the normal checks).
- `views/login.py` and `views/magic_link.py` append `&c=<ref>` / `?c=<ref>`
  to the `/login/mfa` URL.
- `views/login_mfa.py` accepts `c: str = ""`, adopts it before the existing
  `is_hosted_mfa_pending()` / `hosted_mfa_pending()` checks. Everything
  downstream (`_submit` re-check, reload-within-TTL, the magic-link storage
  path) is unchanged.
- Remove the `"Page URL expected to be .*login/mfa"` signature from the e2e
  `only_rerun` allowlist (`tests/e2e/conftest.py`) and trim its comments — the
  rescue must not outlive the bug.
- Update the exact-URL assertions in `tests/e2e/test_mfa.py` to allow the
  optional `&c=<token>` the hand-off now carries.
- Archive `docs/plans/flaky-test-mfa-rerun.md` is NOT in scope here; tick the
  chores.md real-fix item.

Explicitly NOT in scope:
- Removing `/login/mfa` or prompting for the code on `/login` — the hosted
  magic-link flow depends on the page, so it stays.
- The two general e2e flake signatures (`Timeout`, `strict mode`) stay — they
  are not this bug.
- KAL-AUTH-021 (`@planned`, reload/expiry) is untouched.

## Acceptance criteria

- `uv run pytest tests/unit/auth/test_mfa_guard.py -q`
- `grep -q 'c: str' src/kaleta/views/login_mfa.py`
- `test "$(grep -c 'login/mfa' tests/e2e/conftest.py)" -eq 0 || grep -q 'Timeout' tests/e2e/conftest.py`
- `./scripts/verify.sh --e2e`
- `[manual]` `tests/e2e/test_mfa.py` passes with **no reruns** across several
  runs (the race reproduced ~1/3 alone before).

## Touchpoints
- `src/kaleta/auth/session.py` — `begin_hosted_mfa_challenge` returns ref;
  `adopt_hosted_mfa_challenge`.
- `src/kaleta/views/login.py`, `src/kaleta/views/magic_link.py` — URL carries `c`.
- `src/kaleta/views/login_mfa.py` — accept + adopt `c`.
- `tests/e2e/conftest.py` — drop the MFA rerun signature.
- `tests/e2e/test_mfa.py` — URL assertions tolerate `&c=`.
- `docs/plans/chores.md` — tick the real-fix item.

## Implementation notes
- **Security.** `c` is validated against the in-process `hosted_mfa_challenges`
  store, so a forged value names no challenge and is ignored. A leaked valid
  ref is a short-lived (`MFA_CHALLENGE_TTL_MINUTES`) capability that still
  needs the TOTP code — the same class of URL token as the rotation nonce.
  Possible future hardening (not done, to keep the diff minimal and the e2e
  URL assertions honest): strip `c` from the address bar with
  `history.replaceState` after adoption.
- **Why the race is gone.** The only file round-trip was the cross-page hop.
  Once on `/login/mfa`, reads hit the same in-process `app.storage.user`, and
  the adopt-time write has seconds to flush before a reload re-reads the file.
- **Tests.** `adopt_hosted_mfa_challenge` is covered in
  `tests/unit/auth/test_mfa_guard.py::TestUrlHandoff` — a live ref is adopted
  (ref + `_AT` set), and a forged, empty, or expired ref is ignored and leaves
  storage untouched; `begin_hosted_mfa_challenge` returning the ref is pinned
  too. `tests/e2e/test_mfa.py` ran 3× with no reruns (the race reproduced
  ~1/3 alone before), satisfying the `[manual]` criterion.
