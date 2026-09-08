#!/usr/bin/env bash
# WFE fitness campaign — unattended multi-day driver.
#
# One arm per PROCESS, in sequence. Per scripts/run_hauhaucs_full_sweep.sh: a
# persistent connection failure or a leaked handle in one model must not poison
# every remaining arm in a 30-60 hour sweep. This trades process startup
# overhead for failure isolation, which is the right trade at this duration.
#
# Resume-safe: an arm with no PENDING rows is skipped, so killing this script
# and re-running it continues rather than restarts. Safe to Ctrl-C.
#
#   ./scripts/wfe_campaign.sh wfe_full_20260908            # all arms, n=3
#   ARMS_FILE=/tmp/arms.txt ./scripts/wfe_campaign.sh wfe_full_20260908
#   REPEATS=5 ALL_SUITES=1 ./scripts/wfe_campaign.sh wfe_deep --arm <tag>
set -uo pipefail

cd /Users/chris/projects/portal-5

CAMPAIGN_ID="${1:?usage: wfe_campaign.sh <campaign_id> [extra args...]}"
shift || true

REPEATS="${REPEATS:-3}"
BUDGET_S="${BUDGET_S:-1800}"
MAX_TURNS="${MAX_TURNS:-16}"
DEBUG_DIR="${DEBUG_DIR:-tests/wfe/results/campaigns/${CAMPAIGN_ID}/debug}"
LOG_DIR="${LOG_DIR:-/tmp/wfe_${CAMPAIGN_ID}}"
PROGRESS_LOG="${LOG_DIR}/progress.log"
ALL_SUITES_FLAG=""
[ "${ALL_SUITES:-0}" = "1" ] && ALL_SUITES_FLAG="--all-suites"
NOTIFY_FLAG=""
[ "${NOTIFICATIONS_ENABLED:-false}" = "true" ] && NOTIFY_FLAG="--notify"

mkdir -p "$LOG_DIR" "$DEBUG_DIR"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

echo "$(ts) CAMPAIGN ${CAMPAIGN_ID} repeats=${REPEATS} all_suites=${ALL_SUITES:-0}" | tee -a "$PROGRESS_LOG"

# Materialise the matrix once. Idempotent: re-running only appends new rows.
uv run python -m tests.wfe.campaign \
    --campaign-id "$CAMPAIGN_ID" --repeats "$REPEATS" $ALL_SUITES_FLAG \
    --append --dry-run "$@" 2>&1 | tee -a "$PROGRESS_LOG"
uv run python -m tests.wfe.campaign \
    --campaign-id "$CAMPAIGN_ID" --repeats "$REPEATS" $ALL_SUITES_FLAG \
    --append --status "$@" > /dev/null 2>&1

if [ -n "${ARMS_FILE:-}" ]; then
    mapfile -t ARMS < "$ARMS_FILE"
else
    mapfile -t ARMS < <(uv run python -m tests.wfe.campaign --list-arms $ALL_SUITES_FLAG \
        2>/dev/null | sed 's/^[[:space:]]*[0-9]*[[:space:]]*//' | grep -v '^$')
fi

echo "$(ts) ARMS ${#ARMS[@]}" | tee -a "$PROGRESS_LOG"

for arm in "${ARMS[@]}"; do
    [ -z "$arm" ] && continue
    safe=$(echo "$arm" | tr '/:' '__')

    # Cheap reachability check before each arm — catches a dead Ollama before
    # burning an arm's worth of wall clock on connection errors.
    reachable=$(uv run python -c "
from tests.wfe.campaign import ollama_reachable
print(ollama_reachable())
" < /dev/null 2>/dev/null | tail -1)
    if [ "$reachable" != "True" ]; then
        echo "$(ts) ABORT (Ollama unreachable before ${arm})" | tee -a "$PROGRESS_LOG"
        break
    fi

    echo "$(ts) START ${arm}" | tee -a "$PROGRESS_LOG"
    uv run python -m tests.wfe.campaign \
        --campaign-id "$CAMPAIGN_ID" \
        --arm "$arm" \
        --repeats "$REPEATS" \
        --budget-s "$BUDGET_S" \
        --max-turns "$MAX_TURNS" \
        --debug-dir "$DEBUG_DIR" \
        $ALL_SUITES_FLAG $NOTIFY_FLAG "$@" \
        < /dev/null > "${LOG_DIR}/${safe}.log" 2>&1
    exit_code=$?
    echo "$(ts) DONE ${arm} exit=${exit_code}" | tee -a "$PROGRESS_LOG"
done

echo "$(ts) CAMPAIGN COMPLETE" | tee -a "$PROGRESS_LOG"
uv run python -m tests.wfe.campaign --campaign-id "$CAMPAIGN_ID" --status 2>&1 | tee -a "$PROGRESS_LOG"
echo "report: uv run python -m tests.wfe.report --campaign ${CAMPAIGN_ID}"
