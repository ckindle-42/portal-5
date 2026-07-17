#!/usr/bin/env bash
# Per-scenario driver for the HauhauCS full red-capture sweep.
#
# The two --all-scenarios attempts (one long-lived process running all 89
# scenarios sequentially) both failed catastrophically partway through with
# instant "[Errno 61] Connection refused" on every subsequent scenario, while
# every single-scenario invocation this session succeeded. Looping scenarios
# as separate process invocations avoids whatever resource exhaustion/leak
# hits a long-lived process, at the cost of per-process startup overhead.
set -uo pipefail

cd /Users/chris/projects/portal-5

MODEL="fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4"
SCENARIO_LIST="/tmp/hauhaucs_scenario_list.txt"
OUT_DIR="/tmp/hauhaucs_per_scenario"
PROGRESS_LOG="/tmp/hauhaucs_sweep_progress.log"

mkdir -p "$OUT_DIR"

while IFS= read -r scenario; do
    [ -z "$scenario" ] && continue
    out_file="${OUT_DIR}/${scenario}.json"
    if [ -f "$out_file" ]; then
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) SKIP (already done) ${scenario}" >> "$PROGRESS_LOG"
        continue
    fi

    # Re-verify lab reachability before each scenario — cheap, catches a dead
    # lab/sandbox before burning a scenario's worth of inference time on it.
    reachable=$(python3 -c "
from portal.modules.security.core.lab import verify_lab_targets_reachable
print(verify_lab_targets_reachable())
" < /dev/null 2>/dev/null | tail -1)

    if [ "$reachable" != "True" ]; then
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ABORT (lab unreachable before ${scenario})" >> "$PROGRESS_LOG"
        break
    fi

    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) START ${scenario}" >> "$PROGRESS_LOG"

    python3 -m portal.modules.security.core \
        --scenario "$scenario" \
        --chain-models "$MODEL" \
        --lab-exec \
        --skip-workspace-bench \
        --output "$out_file" \
        < /dev/null > "${OUT_DIR}/${scenario}.log" 2>&1

    exit_code=$?
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) DONE ${scenario} exit=${exit_code}" >> "$PROGRESS_LOG"
done < "$SCENARIO_LIST"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) SWEEP COMPLETE" >> "$PROGRESS_LOG"
