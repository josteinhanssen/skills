#!/bin/zsh
# Content verification of a head before and after a merge.
#
# Usage: verify-head.sh <ref> [--invariant "<command>"]... [--ledger-row "<regex>"]
#   <ref>            the commit, branch or remote ref to verify (checked out read-only via git show/grep)
#   --invariant CMD  a command that must exit 0 on a checkout of <ref>; run in the current worktree
#                    after `git checkout --detach <ref>` (the caller decides which worktree)
#   --ledger-row RE  a line regex that must occur exactly once in the file named by --ledger-file
#   --ledger-file F  the ledger file for --ledger-row
#
# Exit code is the number of failed checks. Every check prints one line.
set -u
REF="${1:?ref required}"; shift
INVARIANTS=(); LEDGER_ROW=""; LEDGER_FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --invariant) INVARIANTS+=("$2"); shift 2;;
    --ledger-row) LEDGER_ROW="$2"; shift 2;;
    --ledger-file) LEDGER_FILE="$2"; shift 2;;
    *) echo "unknown option $1" >&2; exit 99;;
  esac
done
fail=0
sha=$(git rev-parse --short "$REF") || exit 98
echo "== head $sha ($REF)"

markers=$(git grep -n -E '^(\|\|\|\|\|\|\||<<<<<<<|=======|>>>>>>>)' "$REF" -- . | wc -l | tr -d ' ')
if [ "$markers" = "0" ]; then echo "conflict markers: none"; else echo "conflict markers: $markers FOUND"; git grep -n -E '^(\|\|\|\|\|\|\||<<<<<<<|=======|>>>>>>>)' "$REF" -- . | head -5; fail=$((fail+1)); fi

only=$(git grep -n -E '\.only\(' "$REF" -- '*.spec.*' '*.test.*' 2>/dev/null | wc -l | tr -d ' ')
if [ "$only" = "0" ]; then echo ".only: none"; else echo ".only: $only FOUND"; fail=$((fail+1)); fi

if [ -n "$LEDGER_ROW" ] && [ -n "$LEDGER_FILE" ]; then
  rows=$(git show "${REF}:${LEDGER_FILE}" | grep -c -E "$LEDGER_ROW")
  if [ "$rows" = "1" ]; then echo "ledger row: exactly one"; else echo "ledger row: $rows FOUND"; fail=$((fail+1)); fi
fi

if [ ${#INVARIANTS[@]} -gt 0 ]; then
  git checkout -q --detach "$REF" || { echo "checkout failed"; exit 97; }
  for cmd in "${INVARIANTS[@]}"; do
    if eval "$cmd" >/tmp/deliver-invariant.log 2>&1; then echo "invariant ok: $cmd"; else echo "invariant FAILED: $cmd"; tail -5 /tmp/deliver-invariant.log; fail=$((fail+1)); fi
  done
fi
echo "== failed checks: $fail"
exit $fail
