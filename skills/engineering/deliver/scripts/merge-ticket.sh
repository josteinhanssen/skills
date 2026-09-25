#!/usr/bin/env bash
# Merge a ticket branch into the batch branch, verify, and push.
#
# Usage: merge-ticket.sh --scratch <worktree> --ticket-branch <branch> --ticket <id> --title <title>
#                         [--check "<command>"]... [--remote origin]
#
# Runs inside <worktree>, which must already be checked out on the batch branch. Records the
# batch head H before merging. If H is already an ancestor of the ticket branch (merge-base of
# the two equals H), the batch head has not moved since the ticket branched: the fast path.
# Otherwise: the slow path.
#
#   1. `git merge --no-ff <ticket-branch> -m "<id>: <title>"`. On conflict: `git merge --abort`,
#      exit 10.
#   2. `verify-head.sh HEAD`, resolved next to this script. On the slow path, every --check also
#      runs, through run-quiet.sh, in <worktree>.
#   3. Any failure in step 2: `git reset --hard H`, exit 11, and the failing check is named.
#   4. Success: push HEAD to the batch branch on --remote (default origin) and print one line:
#      merged <id> <new head sha> (fast path|checks ran)
set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
VERIFY_HEAD="$SCRIPT_DIR/verify-head.sh"
RUN_QUIET="$SCRIPT_DIR/run-quiet.sh"

WORKTREE=""
TICKET_BRANCH=""
TICKET=""
TITLE=""
REMOTE="origin"
CHECKS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --scratch) WORKTREE="$2"; shift 2;;
    --ticket-branch) TICKET_BRANCH="$2"; shift 2;;
    --ticket) TICKET="$2"; shift 2;;
    --title) TITLE="$2"; shift 2;;
    --check) CHECKS+=("$2"); shift 2;;
    --remote) REMOTE="$2"; shift 2;;
    *) echo "unknown option $1" >&2; exit 99;;
  esac
done

if [ -z "$WORKTREE" ]; then echo "--scratch is required" >&2; exit 99; fi
if [ -z "$TICKET_BRANCH" ]; then echo "--ticket-branch is required" >&2; exit 99; fi
if [ -z "$TICKET" ]; then echo "--ticket is required" >&2; exit 99; fi
if [ -z "$TITLE" ]; then echo "--title is required" >&2; exit 99; fi
if [ ! -x "$VERIFY_HEAD" ]; then echo "$VERIFY_HEAD not found or not executable" >&2; exit 99; fi
if [ ! -x "$RUN_QUIET" ]; then echo "$RUN_QUIET not found or not executable" >&2; exit 99; fi

cd "$WORKTREE" || { echo "cannot cd to $WORKTREE" >&2; exit 98; }

H=$(git rev-parse HEAD) || { echo "cannot resolve HEAD in $WORKTREE" >&2; exit 98; }
BATCH_BRANCH=$(git symbolic-ref --short HEAD) || { echo "$WORKTREE is not checked out on a branch" >&2; exit 98; }

MERGE_BASE=$(git merge-base "$TICKET_BRANCH" "$H") || { echo "cannot compute merge-base of $TICKET_BRANCH and $H" >&2; exit 98; }
FAST=0
[ "$MERGE_BASE" = "$H" ] && FAST=1

MERGE_LOG=$(mktemp "${TMPDIR:-/tmp}/claude-merge-ticket.XXXXXX")
if ! git merge --no-ff "$TICKET_BRANCH" -m "$TICKET: $TITLE" >"$MERGE_LOG" 2>&1; then
  git merge --abort >/dev/null 2>&1
  echo "conflict merging $TICKET_BRANCH into $BATCH_BRANCH:" >&2
  tail -20 "$MERGE_LOG" >&2
  rm -f "$MERGE_LOG"
  exit 10
fi
rm -f "$MERGE_LOG"

FAILED=""
if ! "$VERIFY_HEAD" HEAD; then
  FAILED="verify-head.sh"
fi

if [ -z "$FAILED" ] && [ "$FAST" = "0" ] && [ ${#CHECKS[@]} -gt 0 ]; then
  for cmd in "${CHECKS[@]}"; do
    if ! "$RUN_QUIET" "$cmd" bash -c "$cmd"; then
      FAILED="$cmd"
      break
    fi
  done
fi

if [ -n "$FAILED" ]; then
  git reset --hard "$H" >/dev/null
  echo "check failed, batch head reset to $H: $FAILED" >&2
  exit 11
fi

NEW_HEAD=$(git rev-parse --short HEAD)
if ! git push "$REMOTE" "HEAD:$BATCH_BRANCH"; then
  echo "push of $NEW_HEAD to $REMOTE/$BATCH_BRANCH failed" >&2
  exit 12
fi

MODE="fast path"
[ "$FAST" = "0" ] && MODE="checks ran"
echo "merged $TICKET $NEW_HEAD ($MODE)"
