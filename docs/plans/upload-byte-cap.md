---
plan_id: upload-byte-cap
title: Enforce a server-side byte cap on uploads, independent of the front-end limit
area: security (views/import)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Enforce a server-side byte cap on uploads, independent of the front-end limit

## Intent
Security assessment finding **F-4** (`docs/security/assessment-2026-10-12.md`):
the import wizard's `ui.upload(max_file_size=50 MB)` is a **front-end** limit
(enforced by the browser), but the server handler reads the body with
`raw = await e.file.read()` and has **no independent server-side cap**. A
crafted POST straight to the upload endpoint bypasses the browser limit, so a
large body could pressure process memory.

This slice adds a server-side cap, keyed to a setting that the front-end limit
also reads (so the two cannot drift), and rejects an oversize upload **before
reading its bytes** — NiceGUI's `FileUpload.size()` reports the size without
materialising the body — so an oversize file never becomes an in-memory
`bytes` object.

## Scope
- **`src/kaleta/config/settings.py`**: add `max_upload_bytes: int = 50 * 1024 * 1024`
  (env `KALETA_MAX_UPLOAD_BYTES`), with a validator refusing a value < 1.
- **`src/kaleta/views/import_view/upload_guard.py`** (new): a `SupportsSize`
  Protocol (`size() -> int`) and `upload_exceeds_cap(file, cap_bytes=None) -> bool`
  = `file.size() > (cap_bytes or settings.max_upload_bytes)`. A pure, testable
  seam.
- **`src/kaleta/views/import_view/page.py`**: in `handle_upload`, before
  `await e.file.read()`, reject when `upload_exceeds_cap(e.file)` — notify with
  a new negative toast and return, so the oversize file is neither read, parsed
  nor queued.
- **`src/kaleta/views/import_view/upload_section.py`**: `max_file_size` reads
  `settings.max_upload_bytes` instead of the hard-coded literal, so the browser
  hint and the server cap are the one value.
- **i18n**: add `import.file_too_large` (with a `{limit_mb}` param) to
  `en.json` and `pl.json`.
- **`docs/bdd.md`**: add **KAL-SEC-004 @automated** — an upload above the cap is
  rejected server-side, independent of the browser limit.
- **`docs/security/assessment-2026-10-12.md`**: flip F-4 to **Fixed** with the
  KAL-SEC-004 reference.
- Tests: `tests/integration/test_upload_byte_cap.py` (new) — `upload_exceeds_cap`
  is True just over the cap, False at/under it, and honours an explicit cap and
  the setting.

### Why a handler guard via `size()` (binding)
By the time `handle_upload` runs, Starlette's multipart parser has already
parsed the POST (NiceGUI spools large parts to disk, not RAM). Checking
`e.file.size()` and returning **before** `e.file.read()` is the strongest
handler-level defence: it never pulls an oversize body into the Python heap.
A row cap in the parser (the assessment's "and/or") would run only *after* the
read, so it does not address the memory-pressure risk; the byte cap does.

**Not in scope (binding):**
- No change to the parser or to accepted file types.
- No framework-level change to NiceGUI's multipart spooling (out of our code).
- F-1..F-3 are done; this is the last assessment hardening item. Slice C
  (dynamic runners) is separate.

## Acceptance criteria
- `uv run pytest tests/integration/test_upload_byte_cap.py -q`
- `./scripts/verify.sh --e2e` (changes under `src/kaleta/views/` → e2e gate, rule 8)
- Fail-on-old: the new test asserts `upload_exceeds_cap(file_of(cap+1))` is True;
  neutralising the guard (always False) makes it fail. Verified by a backup swap.

## Touchpoints
- `src/kaleta/config/settings.py`
- `src/kaleta/views/import_view/upload_guard.py` (new)
- `src/kaleta/views/import_view/page.py`
- `src/kaleta/views/import_view/upload_section.py`
- `src/kaleta/i18n/locales/en.json`, `src/kaleta/i18n/locales/pl.json`
- `tests/integration/test_upload_byte_cap.py` (new)
- `docs/bdd.md`
- `docs/security/assessment-2026-10-12.md`
- `docs/plans/chores.md` (the security chore note)

## Open questions
- None blocking. Cap defaults to the existing 50 MB front-end value, so no
  behaviour change for legitimate uploads.

## Implementation notes
- **`size()` before `read()`.** NiceGUI's `FileUpload` exposes `size()`, which
  reports the uploaded size without materialising the body (large parts spool to
  disk via Starlette's multipart parser). `handle_upload` checks
  `upload_exceeds_cap(e.file)` and returns before `await e.file.read()`, so an
  oversize file never becomes an in-memory `bytes` object. This is the strongest
  handler-level defence; a parser row cap (the assessment's "and/or") would run
  only after the read and so would not address the memory-pressure risk.
- **One source of truth for the limit.** `settings.max_upload_bytes`
  (`KALETA_MAX_UPLOAD_BYTES`, default 50 MiB) is read by both the server guard
  and the browser `max_file_size` in `upload_section.py`, so the two cannot
  drift. A validator refuses a value < 1.
- **Pure, testable seam.** The decision lives in `upload_guard.upload_exceeds_cap`
  (a `SupportsSize` Protocol → `size() > cap`), unit-tested through
  `tests/integration` (where `spec_coverage` looks) with a fake `size()` object;
  the handler is a NiceGUI closure that only wires the guard to a toast + early
  return. No end-to-end test drives the closure (the e2e suite can't easily send
  an oversize body past the browser limit) — the handler wiring is verified by
  reading, as in `api-docs-gated`.
- **Framework boundary.** NiceGUI/Starlette parse the whole multipart POST
  before any handler runs; capping the parse itself is framework territory and
  out of scope. The handler guard bounds what *our* code pulls into the heap.
- **Fail-on-old verified.** Neutralising the guard (`return False`, a backup
  swap) makes the two reject tests in `tests/integration/test_upload_byte_cap.py`
  fail (an oversize file is accepted); restoring restores green.
