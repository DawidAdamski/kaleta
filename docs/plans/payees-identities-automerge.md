---
plan_id: payees-identities-automerge
title: Payees — multiple identities and automatic merge
area: payees
effort: medium
roadmap_ref: ../roadmap.md#cross-cutting-automatic-deduplication-suggestions
status: draft
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
_Filled in as work progresses._
