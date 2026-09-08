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
# PLAN overrides the workload map. Must reach EVERY campaign.py call including
# --list-arms, or the sweep would run the default plan's arms against the
# override's rows. Set it to rehearse the driver on a two-arm plan.
PLAN_FLAG=""
[ -n "${PLAN:-}" ] && PLAN_FLAG="--plan ${PLAN}"

mkdir -p "$LOG_DIR" "$DEBUG_DIR"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

echo "$(ts) CAMPAIGN ${CAMPAIGN_ID} repeats=${REPEATS} all_suites=${ALL_SUITES:-0}" | tee -a "$PROGRESS_LOG"

# Print the matrix, then materialise it. --dry-run only reports; --status is the
# call that actually creates/appends the manifest, so its output is kept: a
# materialisation failure here would otherwise be invisible for the whole sweep.
uv run python -m tests.wfe.campaign \
    --campaign-id "$CAMPAIGN_ID" --repeats "$REPEATS" $ALL_SUITES_FLAG $PLAN_FLAG \
    --append --dry-run "$@" 2>&1 | tee -a "$PROGRESS_LOG"
uv run python -m tests.wfe.campaign \
    --campaign-id "$CAMPAIGN_ID" --repeats "$REPEATS" $ALL_SUITES_FLAG $PLAN_FLAG \
    --append --status "$@" 2>&1 | tee -a "$PROGRESS_LOG"

# `mapfile`/`readarray` is bash 4+; macOS ships bash 3.2, so read into the array
# by hand or the whole sweep silently runs zero arms.
ARMS=()
if [ -n "${ARMS_FILE:-}" ]; then
    while IFS= read -r _line || [ -n "$_line" ]; do
        [ -n "$_line" ] && ARMS+=("$_line")
    done < "$ARMS_FILE"
else
    # Smallest model first. Two reasons on a 64GB box: the early arms finish fast
    # so a broken sweep shows itself in the first hour rather than the tenth, and
    # each eviction leaves a larger inactive pool for the arm that follows.
    while IFS= read -r _line || [ -n "$_line" ]; do
        [ -n "$_line" ] && ARMS+=("$_line")
    done < <(uv run python -m tests.wfe.campaign --list-arms $ALL_SUITES_FLAG $PLAN_FLAG \
        2>/dev/null | sed 's/^[[:space:]]*[0-9]*[[:space:]]*//' | grep -v '^$' \
        | uv run python -c "
import json, sys, urllib.request
try:
    with urllib.request.urlopen('${OLLAMA:-http://localhost:11434}/api/tags', timeout=10) as r:
        size = {m['name']: m['size'] for m in json.load(r)['models']}
except Exception:
    size = {}
arms = [ln.strip() for ln in sys.stdin if ln.strip()]
for a in sorted(arms, key=lambda a: (size.get(a, 0), a)):
    print(a)
")
fi

if [ "${#ARMS[@]}" -eq 0 ]; then
    echo "$(ts) ABORT: no arms resolved (ARMS_FILE=${ARMS_FILE:-<none>}, --list-arms empty?)" \
        | tee -a "$PROGRESS_LOG"
    exit 2
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
        $ALL_SUITES_FLAG $NOTIFY_FLAG $PLAN_FLAG "$@" \
        < /dev/null >> "${LOG_DIR}/${safe}.log" 2>&1
    exit_code=$?

    # execute_arm drains its own model and waits for /api/ps to confirm it. This
    # is the fallback for the path where it could not — a killed or crashed
    # process — and it is fire-and-forget by design: the next arm's drain_others()
    # is what actually waits. Without any release, OLLAMA_MAX_LOADED_MODELS (5
    # here) lets several ~20GB arms sit resident and the sweep measures memory
    # pressure instead of models.
    curl -s -m 30 "${OLLAMA:-http://localhost:11434}/api/generate" \
        -d "{\"model\":\"${arm}\",\"keep_alive\":0}" > /dev/null 2>&1

    echo "$(ts) DONE ${arm} exit=${exit_code}" | tee -a "$PROGRESS_LOG"
done

echo "$(ts) CAMPAIGN COMPLETE" | tee -a "$PROGRESS_LOG"
uv run python -m tests.wfe.campaign --campaign-id "$CAMPAIGN_ID" --status 2>&1 | tee -a "$PROGRESS_LOG"
echo "report: uv run python -m tests.wfe.report --campaign ${CAMPAIGN_ID}"
