#!/usr/bin/env bash
# Y23 driver — one (variant, seat) probe per process, resumable.
#
# The first attempt ran all 15 pairs inside one long-lived process and was
# killed partway (low memory, mid-seat), losing the whole sweep. Each pair is
# now its own process writing its own debug file, and a pair whose debug file
# already has the full 31 lines (1 preflight + 30 cases) is skipped. Re-running
# this script after a kill resumes where it stopped.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

RUN=coding_task/v9_compliance/private/runs/D0_20260906T185401Z
DBG="$RUN/y23_debug"
LOG=${Y23_LOG:-/tmp/y23_run.log}

SEATS=(
  "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"
  "granite4.1:30b-ctx16k"
  "mistral-small3.2:24b-instruct-2506-q4_K_M"
)
VARIANTS=(shipped terse verbose reordered outdated_rule)

echo "=== Y23 sweep starting $(date -u +%FT%TZ) ===" >> "$LOG"
for v in "${VARIANTS[@]}"; do
  for s in "${SEATS[@]}"; do
    safe="${s//\//_}"
    f="$DBG/$v/${safe}.debug.jsonl"
    if [ -f "$f" ] && [ "$(wc -l < "$f")" -ge 31 ]; then
      echo "[skip] $v / $s (complete)" >> "$LOG"
      continue
    fi
    echo "[run ] $v / $s  $(date -u +%FT%TZ)" >> "$LOG"
    uv run python tests/benchmarks/bench_judgment_probe_v6.py \
      --models "$s" --prompt-variant "$v" --debug-dir "$DBG/$v" >> "$LOG" 2>&1
    echo "[done] $v / $s rc=$? lines=$( [ -f "$f" ] && wc -l < "$f" || echo 0)" >> "$LOG"
  done
done
echo "Y23_SWEEP_COMPLETE $(date -u +%FT%TZ)" >> "$LOG"
