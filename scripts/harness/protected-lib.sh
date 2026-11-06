#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Shared matcher for docs/harness/protected-paths.txt (sourced, not executed).
#
#   harness_protected <rel-path> edit   -> exit 0 when an Edit/Write must be blocked
#   harness_protected <rel-path> diff   -> exit 0 when a changed path vetoes the diff
#
# Python twin: scripts/harness/protected.py (the tests hold both to the same cases).
# Needs: HARNESS_ROOT (repo root). For `diff`, HARNESS_BASE (merge-base) decides
# whether a `tracked:` path already existed.

harness_protected() {
  local rel=$1 mode=$2 list="${HARNESS_ROOT:?}/docs/harness/protected-paths.txt" line glob kind
  [ -f "$list" ] || return 1
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line%%#*}
    line=${line#"${line%%[![:space:]]*}"}
    line=${line%"${line##*[![:space:]]}"}
    [ -z "$line" ] && continue
    kind=plain; glob=$line
    case "$line" in
      tracked:*) kind=tracked; glob=${line#tracked:} ;;
      written-by-harness:*) kind=harness; glob=${line#written-by-harness:} ;;
    esac
    # shellcheck disable=SC2053  # the right-hand side is a glob on purpose
    [[ $rel == $glob ]] || continue
    case "$kind" in
      plain) return 0 ;;
      harness) [ "$mode" = edit ] && return 0; return 1 ;;
      tracked)
        if [ "$mode" = edit ]; then
          git -C "$HARNESS_ROOT" ls-files --error-unmatch "$rel" >/dev/null 2>&1 && return 0
        else
          git -C "$HARNESS_ROOT" cat-file -e "${HARNESS_BASE:?}:$rel" 2>/dev/null && return 0
        fi
        ;;
    esac
  done < "$list"
  return 1
}
