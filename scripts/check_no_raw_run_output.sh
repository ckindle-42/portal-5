#!/usr/bin/env bash
# Reject new raw run output in the tracked output directories. Summaries (Markdown)
# may stay; data lives under $PORTAL_DATA_ROOT. Pre-commit passes the staged paths.
set -euo pipefail
status=0
for f in "$@"; do
  [ -e "$f" ] || continue
  case "$f" in
    *.json|*.jsonl|*.csv)
      echo "raw run output belongs under \$PORTAL_DATA_ROOT, not main: $f" >&2
      status=1
      ;;
  esac
done
exit "$status"
