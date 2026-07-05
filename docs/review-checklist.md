# PR Review Checklist

Used by the automated PR reviewer (`.github/workflows/pr-review.yml`)
and by humans. Every PR is reviewed **against its plan**, not in a
vacuum. The PR description must link the plan file in `docs/plans/`
(or state explicitly that no plan applies — small fixes only).

## 1. Scope

- [ ] The diff implements what the referenced plan (or its named
      section) covers — and nothing from the plan's **Not in scope**.
- [ ] No drive-by changes: repo-wide formatting, unrelated lint
      fixes, or opportunistic refactors belong in a separate PR.
- [ ] If the diff exceeds the plan, the excess is called out in the
      PR description with a reason — undeclared scope creep is a
      change-request.

## 2. Acceptance criteria

- [ ] Every executable criterion (backtick command) from the plan's
      `## Acceptance criteria` has been run, and the PR description
      shows the output — claims without output are not verification.
- [ ] `[manual]` criteria are listed as open items for the owner,
      not silently marked done.
- [ ] `./scripts/verify.sh` output is included; `--e2e` when
      anything under `src/kaleta/views/` changed (Working Agreement
      rule 8).

## 3. No green-washing (Working Agreement rules 4, 10)

- [ ] No new `skip` / `xfail`, loosened assertions, raised timeouts,
      or broadened exception handlers introduced to make checks pass.
- [ ] No new `ignore_imports` entries; import-linter ignore lists
      may only shrink.
- [ ] No type erosion: no `Any` replacing a real type, no enum → str,
      no removed annotations. Typing-only imports go under
      `TYPE_CHECKING`.

## 4. Tests

- [ ] Bug fixes come with a regression test that failed before the
      fix (red→green shown in the PR description).
- [ ] New user-facing behaviour has a `KAL-` scenario in
      `docs/bdd.md` (tagged `@automated` only when a test covers it)
      and `Covers:` references in test docstrings.
- [ ] Business logic added to services has unit tests; logic is not
      hiding in views (spot-check the diff for computation/queries in
      `views/`).

## 5. Data & migrations

- [ ] New/changed models come with an Alembic migration; migration
      is reversible and works on both SQLite and PostgreSQL (CI
      postgres job green).
- [ ] Applied migrations from history are not rewritten (forward
      edits only), unless the PR explicitly justifies it.
- [ ] No secrets, no real personal/financial data, no `.db` files in
      the diff.

## 6. Documentation & housekeeping

- [ ] Plan's `## Implementation notes` updated with decisions and
      resolved open questions.
- [ ] User-facing changes reflected in README / `docs/` where
      relevant; new env vars documented in `docs/tech-stack.md`.
- [ ] Architectural decisions recorded as an ADR in `docs/adr/` when
      the PR changes structure, dependencies-of-record, or
      conventions.

## Reviewer output format

For the automated reviewer: post one summary comment — verdict
(**approve** / **request changes**) followed by findings grouped by
the sections above, each finding referencing a file/line. Do not
rubber-stamp: if the plan reference is missing or acceptance-criteria
output is absent, that alone is a request-changes.
