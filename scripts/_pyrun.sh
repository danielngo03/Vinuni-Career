#!/usr/bin/env bash
set -u

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "$@"
elif command -v py >/dev/null 2>&1; then
  exec py -3 "$@"
fi

echo "AI log hook skipped: Python was not found on PATH." >&2
exit 0
