#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KIT="$ROOT/scripts/seat_screen"
OUTPUT_DIR="${SEAT_SCREEN_OUTPUT_DIR:-$ROOT/results/seat_screen}"
DISPATCH="${SEAT_SCREEN_DISPATCH:-$HOME/.claude/orchestrate/bin/dispatch.py}"
BASE_COMMIT="${SEAT_SCREEN_BASE_COMMIT:-e75095ef}"
cd "$ROOT"
set -a
. ./.env
set +a
export PIPELINE_URL="${PIPELINE_URL:-http://localhost:9099}"

unload() {
  curl -s localhost:11434/api/ps |
    python3 -c "import sys,json;[print(m['name']) for m in json.load(sys.stdin)['models']]" |
    while read -r model; do
      case "$model" in
        *gemma-4-E4B*) ;;
        *) curl -s localhost:11434/api/generate -d "{\"model\":\"$model\",\"keep_alive\":0}" -o /dev/null ;;
      esac
    done
}

run_seat() {
  local variant="${1#auto-coding::}" slug="$2"
  unload
  echo "=== $(date +%T) $variant" >> "$OUTPUT_DIR/seat_gates.log"
  for think in true false; do
    "$KIT/probe_seat.py" "auto-coding::$variant" --think "$think" 2>&1 |
      grep -E '^phase|_ok=|seen=|darwin' >> "$OUTPUT_DIR/seat_gates.log" || true
  done
  if ! "$KIT/seat_screen2.sh" \
      --dispatch "$DISPATCH" \
      --output-dir "$OUTPUT_DIR" \
      --base-commit "$BASE_COMMIT" \
      "$slug" >> "$OUTPUT_DIR/seat_queue_run.log" 2>&1; then
    echo "$(date +%T) FAILED $slug" >> "$OUTPUT_DIR/seat_queue_run.log"
  fi
}

mkdir -p "$OUTPUT_DIR"
if [[ "${1:-}" == "--stdin" ]]; then
  if (($# != 1)); then
    echo "usage: seat_rescreen.sh [variant slug ...] | seat_rescreen.sh --stdin" >&2
    exit 2
  fi
  while read -r variant slug; do
    [[ -z "${variant:-}" || -z "${slug:-}" ]] && continue
    run_seat "$variant" "$slug"
  done
elif (($#)); then
  if (($# % 2)); then
    echo "seat arguments must be variant slug pairs" >&2
    exit 2
  fi
  while (($#)); do
    run_seat "$1" "$2"
    shift 2
  done
else
  while read -r variant slug; do
    run_seat "$variant" "$slug"
  done < "$KIT/kit/run_list.txt"
fi
echo RESCREEN-DONE >> "$OUTPUT_DIR/seat_queue_run.log"
