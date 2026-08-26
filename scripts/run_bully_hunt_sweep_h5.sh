#!/usr/bin/env bash
# H.5 -- THE SWEEP RUN (TASK_BULLY_HUNT_SWEEP_V1.md).
#
# Runs the locate-plant-hunt loop across all 27 in-scope answer-key entries,
# at the span H.1's live calibration returned COMMIT for (10m). Live: reads
# the real corpus and plants real cousins via HEC. Progress is checkpointed
# and published per entry (H.3/H.4), so killing this script and re-running
# it resumes rather than restarts -- safe to Ctrl-C and come back to.
set -uo pipefail

cd /Users/chris/projects/portal-5

if [ -z "${LAB_SPLUNK_PASSWORD:-}" ] && [ -f .env ]; then
    set -a; source .env; set +a
fi

if [ -z "${LAB_SPLUNK_PASSWORD:-}" ]; then
    echo "LAB_SPLUNK_PASSWORD not set and not found in .env" >&2
    exit 1
fi

LOG_FILE="/tmp/bully_hunt_sweep_h5_$(date -u +%Y%m%dT%H%M%SZ).log"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) START H.5 sweep -- log: ${LOG_FILE}"

uv run python3 scripts/bully_full_assembly_run.py \
    --out-dir docs \
    --doc-stem BULLY_HUNT_SWEEP_RUN_H5_V1 \
    --hunt-span-seconds 600 \
    --batch-size 10000 \
    --per-sourcetype-cap 2000 \
    2>&1 | tee "${LOG_FILE}"

exit_code=${PIPESTATUS[0]}
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) DONE H.5 sweep exit=${exit_code}"
echo "results: docs/BULLY_HUNT_SWEEP_RUN_H5_V1.md / .json"
exit "${exit_code}"
