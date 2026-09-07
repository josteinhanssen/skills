#!/bin/zsh
# Wait for a grant file naming this agent.
# Usage: wait-grant.sh <resource> <agent-id> [timeout-minutes, default 45]
# Polls .deliver/grants/<resource> (written by `state.py grant`) every 30 s from the repository root.
# Exit 0 when the grant names the agent, 2 on timeout, 3 when the grant names someone else for the whole wait.
set -u
RES="${1:?resource}"; AGENT="${2:?agent id}"; LIMIT="${3:-45}"
SAFE=$(printf '%s' "$RES" | sed 's/[^A-Za-z0-9_-]/_/g')
FILE=".deliver/grants/$SAFE"
deadline=$(( $(date +%s) + LIMIT * 60 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if [ -f "$FILE" ]; then
    if grep -q "\"agent\": *\"$AGENT\"" "$FILE"; then echo "grant for $RES: $(cat "$FILE")"; exit 0; fi
  fi
  sleep 30
done
[ -f "$FILE" ] && { echo "grant for $RES is held by another agent: $(cat "$FILE")"; exit 3; }
echo "no grant for $RES after $LIMIT minutes"; exit 2
