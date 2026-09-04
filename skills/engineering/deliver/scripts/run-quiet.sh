#!/usr/bin/env bash

set -u

if [ "$#" -lt 2 ]; then
  printf 'Usage: %s <label> <command> [args...]\n' "$0" >&2
  exit 64
fi

label=$1
shift

log_file=$(mktemp "${TMPDIR:-/tmp}/claude-quiet.XXXXXX") || exit 1

"$@" >"$log_file" 2>&1
status=$?

line_count=$(wc -l <"$log_file" | tr -d ' ')
byte_count=$(wc -c <"$log_file" | tr -d ' ')

if [ "$status" -eq 0 ]; then
  printf 'PASS %s (%s lines, %s bytes captured)\n' "$label" "$line_count" "$byte_count"
  rm -f "$log_file"
  exit 0
fi

tail_lines=${CLAUDE_QUIET_TAIL_LINES:-80}
line_chars=${CLAUDE_QUIET_LINE_CHARS:-1000}

printf 'FAIL %s (exit %s; %s lines, %s bytes). Full log: %s\n' \
  "$label" "$status" "$line_count" "$byte_count" "$log_file" >&2
printf 'Last %s lines, capped at %s characters each:\n' "$tail_lines" "$line_chars" >&2
tail -n "$tail_lines" "$log_file" | awk -v max="$line_chars" '{ print substr($0, 1, max) }' >&2

exit "$status"
