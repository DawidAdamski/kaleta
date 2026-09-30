---
plan_id: payees-identities-automerge
title: Payees — multiple identities and automatic merge
area: payees
effort: medium
roadmap_ref: ../roadmap.md#cross-cutting-automatic-deduplication-suggestions
status: in-progress
deferred_to: q4-2026
---

# Payees — multiple identities and automatic merge

## Intent

Banks spell the same merchant many different ways: *"PKO BP"*,
*"PKO BANK POLSKI O"*, *"PKO BP ORLEN"*. Today each variant
becomes a separate `Payee` row, so spend-by-payee reports are
fragmented and users must manually merge in Housekeeping every
time a new spelling appears.

Two complementary changes:

1. **Multiple identities per payee** — a `Payee` gains a list of
   `PayeeIdentity` aliases. New transactions matched by *any*
   identity belong to the same logical payee.
2. **Automatic merge proposals** — a background pass proposes
   merges of near-duplicate payee names (beyond the Levenshtein
   threshold already used in Housekeeping), ranking by
   confidence. High-confidence matches can auto-merge under a
   user-controlled setting; lower-confidence stay as suggestions
   the user confirms.

Together these cut the long tail of payee variants down to a
handful of canonical entities.

## Scope

- **Model**: new `PayeeIdentity` table —
  `id`, `payee_id FK`, `pattern` (literal string by default;
  optional `is_regex BOOL`), `case_sensitive BOOL` (default
  false), `created_at`. A payee has N identities; at least one
  per payee. An identity's `pattern` is what the CSV importer
  and transaction-create flow match against (payer name / raw
  bank line).
- **Migration**: backfill — for every existing payee, create a
  single identity with `pattern = payee.name`.
- **Matching rule in import + manual create**:
  - On transaction create / import, if a payee name is provided,
    look up existing identities for an exact (case-insensitive)
    match; if found, attach the transaction to that payee.
  - If no match, create a new payee + a single identity from the
    raw name (today's behaviour).
- **Payees page**:
  - Each payee row shows its identity count with a chevron to
    expand inline.
  - Adding / editing identities inline.
  - Deleting the last identity requires deleting the payee.
- **Auto-merge engine** — `PayeeMergeService.propose_merges()`:
  - For every unordered pair of payees, compute a similarity
    score combining:
    - Normalised Levenshtein distance on payee name.
    - Normalised Levenshtein on longest matching identity pair.
    - Overlap of merchant-key prefixes (first word uppercase).
  - Output a ranked list of proposals: `{left_id, right_id,
    score, reason}`.
  - Score thresholds (configurable in Settings):
    - ≥ 0.92 → **auto-merge** (when the setting is on).
    - ≥ 0.75 → **propose in Housekeeping**.
    - < 0.75 → ignored.
- **Settings → Housekeeping** section gains:
  - Toggle "Auto-merge payees above confidence" (default: off).
  - Threshold slider (0.80 – 0.99).
  - "Run merge scan now" button (triggers the service
    immediately; otherwise runs on the same daily scheduler as
    the notifications system, if available — else on demand).
- **Housekeeping page** — the existing dedupe list is
  extended to include the `PayeeMergeService` output; the
  existing merge action wires in the new identities of the
  winning payee.
- **Undo window** — auto-merges emit a `NotificationService`
  entry (if available) with a 7-day undo link. Lacking the
  notification system, surface it as a "Recently merged"
  section in Housekeeping.
- **API**: `/api/v1/payees/{id}/identities` (CRUD) and
  `/api/v1/payees/merges/proposals` (list, dismiss).
- **Unit tests** — backfill, matching precedence (identity
  hit before name hit), `propose_merges` for a seeded dataset.

Out of scope:
- Fuzzy matching at import time (using similarity, not just
  exact). Defer — users can add identities explicitly.
- Per-transaction overrides of payee when a match is wrong;
  the existing edit flow handles it.
- Multi-user payee aliases.
- Machine-learning classifier — heuristic scoring only.

## Acceptance criteria

- Creating a payee "Lidl sp z o o" and adding an identity
  "LIDL POZNAN" results in a single payee; a subsequent
  transaction with raw name "LIDL POZNAN" attaches to that
  same payee, not a new one.
- Existing merge flow in Housekeeping still works and now also
  consolidates identities into the winning payee.
- With the auto-merge setting on at threshold 0.92, a pair of
  payees with Levenshtein similarity 0.95 merges automatically
  on the next scan; a pair at 0.85 stays as a proposal.
- Deleting the last identity of a payee prompts the user to
  delete the payee entirely.
- Backfill migration produces one identity per existing payee
  with `pattern = payee.name`.

## Touchpoints

- New model `src/kaleta/models/payee_identity.py`.
- Extend `src/kaleta/models/payee.py` with `identities`
  relationship.
- New schemas `src/kaleta/schemas/payee_identity.py`.
- Extend `src/kaleta/services/payee_service.py` with identity
  CRUD + the match-by-identity hook used by importers.
- New `src/kaleta/services/payee_merge_service.py`.
- `alembic/versions/NNN_add_payee_identities.py` —
  add table + backfill + indexes on `pattern` for lookup.
- `src/kaleta/services/import_service.py` — use
  `PayeeService.match_or_create_from_name()` (new) which
  consults identities first.
- `src/kaleta/views/payees.py` — identity management UI.
- `src/kaleta/views/housekeeping.py` — surface merge proposals.
- `src/kaleta/views/settings.py` — Housekeeping section gets
  the auto-merge toggle + threshold.
- `src/kaleta/api/v1/payees.py` — new routes.
- `src/kaleta/i18n/locales/{en,pl}.json` — new keys.

## Open questions

1. **Regex identities** — v1 off (literal only)? Default:
   **yes, literal only**; regex is a footgun.
2. **Matching case sensitivity** — default case-insensitive?
   Default: **yes**; virtually every bank uppercases.
3. **Scoring weights** — name distance vs identity distance
   vs merchant-key overlap. Default: **0.5 / 0.3 / 0.2** —
   tune after real-data testing.
4. **Auto-merge default** — off. Users opt in after trusting
   the proposals.
5. **Merge direction** — which payee wins? Default: the one
   with more transactions; tie broken by earlier
   `created_at`. The loser's identities move to the winner.

## Implementation notes

### Resolved open questions (defaults taken)
1. **Regex identities** — literal only. The `is_regex` column was not added
   at all (it would be a column nothing can set); add it with the feature.
2. **Case sensitivity** — case-insensitive by default; `case_sensitive`
   exists per identity (API only, no UI toggle yet).
3. **Scoring weights** — 0.5 name / 0.3 identity / 0.2 merchant key
   (`WEIGHT_*` in `payee_merge_service.py`).
4. **Auto-merge default** — off (`DEFAULT_PAYEE_AUTOMERGE_ENABLED`).
5. **Merge direction** — more transactions wins, then older `created_at`,
   then lower id. `left_id` of a proposal is the would-be keeper.

### Decisions
- **Lookup key.** `payee_identities.pattern_key` holds the casefolded,
  whitespace-collapsed pattern and is indexed; SQLite `lower()` only folds
  ASCII, so "ŻABKA" could never meet "żabka" through SQL. The migration
  computes it in Python with a frozen copy of the function.
- **No UNIQUE on `pattern_key`.** Payee names are unique case-*sensitively*,
  so the backfill can legitimately produce "LIDL" and "Lidl" identities on
  two payees. The service refuses a *new* spelling another payee holds
  (409); lookups break ties exact-case first, then oldest identity.
- **Every payee has ≥ 1 identity** via a `before_flush` listener in
  `models/payee_identity.py`, so seeders, import, manual entry and merge
  undo can't create an identity-less payee.
- **Matching precedence** (`PayeeService.match_or_create_from_name`, now
  used by mBank import *and* manual entry, replacing `find_or_create` /
  `match_or_create_by_name`): exact identity → case-insensitive identity
  → exact payee name → create. Behaviour change: mBank import was
  case-sensitive (one payee per exact spelling); per open question 2 it
  now folds case, so "Lidl Poznan" joins "LIDL POZNAN".
- **Rename** adds the new name as an identity and keeps the old one (bank
  lines still arrive under it), unless the new spelling is already held.
- **Merges** (both `PayeeService.merge` and `DedupeService.merge_payees`)
  move the merged payees' identities to the keeper through
  `PayeeService.absorb_identities`, dropping spellings the keeper already
  has. Loaded `identities` collections of the merged payees are expired
  first — otherwise the delete-orphan cascade would delete the moved rows.
- **Scheduler.** There is no notifications system/scheduler, and the
  auto-merge settings live in per-browser `app.storage.user`, so the scan
  runs on demand only ("Run merge scan now" in Settings → Features →
  Housekeeping). Housekeeping shows proposals on page load but never
  auto-merges there.
- **Undo window.** No `NotificationService` exists, so auto-merges are
  logged in `payee_auto_merges` (JSON snapshot: payee fields, moved
  identity ids, re-pointed transaction/planned/subscription ids) and listed
  under "Recently merged" in Housekeeping for 7 days with an Undo button.
  Undo restores the payee, its moved identities and the rows still pointing
  at the keeper; rows the keeper gained after the merge stay. Subscription
  dismissals (`dismissed_candidate_patterns`, CASCADE) of the merged payee
  are not restored. Manual merges are not logged (unchanged behaviour: the
  confirm dialog already warns they are final).
- **Dismissals** persist in `dismissed_payee_merges` (ids stored lowest
  first, CASCADE on either payee).
- **Housekeeping list.** Proposals whose two payees already sit in one
  `DedupeService.similar_payees` group are hidden
  (`propose_merges(grouped=...)`), so a pair is never offered twice; the rest render under "Similar payees" with confidence,
  reason and a "Not the same" (dismiss) button.
- **Performance.** `propose_merges` is O(n²) over payees with a
  bag-distance upper bound skipping most Levenshtein calls: ~0.6 s for 400
  payees on a laptop. Fine for a personal ledger; revisit (blocking by
  merchant key) if payee counts grow by an order of magnitude.
- **API** additions: `GET/POST /payees/{id}/identities`,
  `PUT/DELETE /payees/{id}/identities/{identity_id}` (409 `last_identity`
  on the last one), `GET /payees/merges/proposals`,
  `POST /payees/merges/proposals/dismiss`. Scan and undo are UI-only (the
  plan's API list does not include them).
- **Payees page.** The table uses a custom `body` slot: an "Identities (n)"
  toggle per row expands a panel (rendered with `v-if`, so collapsed rows
  add no duplicate text) listing spellings; edits and additions use
  `q-popup-edit` inline. Removing the last identity opens the delete-payee
  dialog with a dedicated message.

- **Settings.** Only the auto-merge threshold (0.80–0.99, default 0.92) is
  a control; the 0.75 proposal floor stays the fixed
  `PROPOSAL_THRESHOLD`: the plan's slider range starts at 0.80, so it only
  covers the auto-merge threshold. The controls live in
  `views/settings/payee_automerge.py` (settings is a package now, not the
  `views/settings.py` the touchpoints name), rendered in Features →
  Housekeeping.
- **Dismiss errors** in Housekeeping are caught by
  `PayeeMergeSuggestion._dismiss` (`handle_kaleta_error`).

- **Backfill on PostgreSQL** is not exercised by a test: KAL-PID-009 runs
  the migration chain on a SQLite file and is skipped under the Postgres
  test run, like the other SQLite-file migration tests. The backfill uses
  only portable SQL (`SELECT` + `bulk_insert`), with the key computed in
  Python.

### BDD
KAL-PID-004…013 `@automated` (integration + e2e), KAL-PID-014 (Settings scan
button) and KAL-PID-015 (proposals in Housekeeping) `@manual`.
