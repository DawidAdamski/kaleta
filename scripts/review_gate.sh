#!/usr/bin/env bash
# Independent critic for the current branch against its plan (ADR-39).
#
# Runs scripts/harness/critic.py: k fresh, read-only samples (Claude, plus one
# from another model family when required) answer the narrow questions in
# docs/harness/critic-questions.toml with yes/no/na and file:line evidence.
# The result — p_violation per question, never a verdict — goes to
# .claude/state/critic.json and to the run log; the Stop hook
# (.claude/hooks/dod-gate.sh) decides what it means.
#
#   scripts/review_gate.sh [plan_id] [--samples N] [--dry-run]
#
# Env:
#   KALETA_CRITIC_SAMPLES      samples per run              (default: profile, else 3)
#   KALETA_REVIEW_MODEL        model for the Claude samples (default: sonnet)
#   KALETA_CROSS_REVIEW=1      one sample from the Cursor CLI (needs `agent` / `cursor-agent`)
#   KALETA_CROSS_REVIEW_MODEL  Cursor model id              (default: gpt-5)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
# shellcheck source=harness/python.sh
. scripts/harness/python.sh
exec "${HARNESS_PY[@]}" scripts/harness/critic.py "$@"
