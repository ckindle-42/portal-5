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
#   ./scripts/wfe_campaign.sh wfe_s8 --plan tests/wfe/plans/s8_x.yaml --tier screen \
#       --engine pipeline                                  # job-friendly (no env needed)
#   ./scripts/wfe_campaign.sh wfe_s8 --canary ...          # live canary: one incumbent row
#       per workload into <id>_canary, classified SETUP vs MODEL; exit 0 only when no
#       row is SETUP. Gate a long campaign on it (job specs: a `canary: <step>` step).
# The final stdout line is `CAMPAIGN <id>: complete|stopped (<reason>) rows done/total`
# (printed by the --finish call, which is also the script's exit): 0 matrix complete
# (arm halts are a result, summarised on that line), 5 an arm stopped (instrument
# drift, seat loss) leaving rows PENDING, 8 rows left PENDING with no stop record,
# 10 nothing measured at all, 4 campaign gate refusal, 2/3 driver misuse or
# conformance findings. Incident realuse_s8_20261030: 3 of 68 rows, every arm
# STOPPED on instrument drift, and this script exited 0.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

CAMPAIGN_ID="${1:?usage: wfe_campaign.sh <campaign_id> [extra args...]}"
shift || true

# --plan/--engine are parsed here, not passed through: a job step has no env channel,
# and PLAN/WFE_ENGINE used to be settable only by one.
ARGS=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --plan)
            [ "$#" -ge 2 ] || { echo "wfe-campaign: --plan needs a path" >&2; exit 2; }
            PLAN="$2"; shift 2 ;;
        --plan=*)
            PLAN="${1#--plan=}"; shift ;;
        --engine)
            [ "$#" -ge 2 ] || { echo "wfe-campaign: --engine needs a name" >&2; exit 2; }
            WFE_ENGINE="$2"; shift 2 ;;
        --engine=*)
            WFE_ENGINE="${1#--engine=}"; shift ;;
        --canary)
            CANARY=1; shift ;;
        *)
            ARGS+=("$1"); shift ;;
    esac
done
set -- "${ARGS[@]+"${ARGS[@]}"}"
[ -n "${PLAN:-}" ] && export PLAN
[ -n "${WFE_ENGINE:-}" ] && export WFE_ENGINE
# Pipeline mode authenticates to :9099. Take ONLY the key from the repo .env: sourcing the
# whole file exports container hostnames/paths that break host-side runners.
if [ "${WFE_ENGINE:-}" = "pipeline" ] && [ -z "${PIPELINE_API_KEY:-}" ] \
    && [ -f "$REPO_ROOT/.env" ]; then
    PIPELINE_API_KEY="$(grep -E '^PIPELINE_API_KEY=' "$REPO_ROOT/.env" | tail -1 | cut -d= -f2- | tr -d "\"'")"
    [ -n "$PIPELINE_API_KEY" ] && export PIPELINE_API_KEY
fi

# Canary mode: tests/wfe/canary.py owns the whole path — fixture staging, the
# conformance gate, one live incumbent row per workload, SETUP/MODEL
# classification, and the exit. One repeat is implied; the sweeps' REPEATS
# policy does not apply.
if [ "${CANARY:-0}" = "1" ]; then
    PLAN_ARGS=()
    [ -n "${PLAN:-}" ] && PLAN_ARGS+=(--plan "$PLAN")
    exec uv run python -m tests.wfe.canary \
        --campaign-id "$CAMPAIGN_ID" ${PLAN_ARGS[@]+"${PLAN_ARGS[@]}"} "$@"
fi

# Unset REPEATS on --tier realuse omits --repeats (realuse_repeats: 1 draw, 2 only
# above temperature 0). A job step cannot export REPEATS. An explicit REPEATS still wins.
_realuse=0
_prev=""
for _arg in "$@"; do
    [ "$_prev" = "--tier" ] && [ "$_arg" = "realuse" ] && _realuse=1
    [ "$_arg" = "--tier=realuse" ] && _realuse=1
    _prev="$_arg"
done
if [ "$_realuse" = 1 ] && [ -z "${REPEATS+x}" ]; then
    REPEATS=policy
else
    REPEATS="${REPEATS:-3}"
fi
# REPEATS=policy leaves --repeats off, so a confirm takes the harness's repeats policy
# (1 when every arm in the cell served temperature 0, else 3 — campaign.repeats_policy).
REPEATS_FLAG="--repeats ${REPEATS}"
[ "$REPEATS" = "policy" ] && REPEATS_FLAG=""
BUDGET_S="${BUDGET_S:-1800}"
MAX_TURNS="${MAX_TURNS:-16}"
DATA_ROOT="${PORTAL_DATA_ROOT:-$HOME/AI_Output/portal-data}"
DEBUG_DIR="${DEBUG_DIR:-${DATA_ROOT}/tests/wfe/results/campaigns/${CAMPAIGN_ID}/debug}"
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
    --campaign-id "$CAMPAIGN_ID" $REPEATS_FLAG $ALL_SUITES_FLAG $PLAN_FLAG \
    --append --dry-run "$@" 2>&1 | tee -a "$PROGRESS_LOG"
DRY_RUN_RC=$?
if [ "$DRY_RUN_RC" -ne 0 ]; then
    exit "$DRY_RUN_RC"
fi
for arg in "$@"; do
    if [ "$arg" = "--dry-run" ]; then
        exit 0
    fi
done
# Prompt paths must already be readable; a missing fixture otherwise burns the sweep.
fixture_rc=0
fixture_gate=$(uv run python -m tests.wfe.realuse_paths --preflight \
    $PLAN_FLAG $ALL_SUITES_FLAG "$@" 2>&1) || fixture_rc=$?
printf '%s\n' "$fixture_gate" | tee -a "$PROGRESS_LOG"
if [ "$fixture_rc" -ne 0 ]; then
    echo "$(ts) ABORT: realuse fixture preflight refused" | tee -a "$PROGRESS_LOG"
    exit 4
fi
uv run python -m tests.wfe.campaign \
    --campaign-id "$CAMPAIGN_ID" $REPEATS_FLAG $ALL_SUITES_FLAG $PLAN_FLAG \
    --append --status "$@" 2>&1 | tee -a "$PROGRESS_LOG"

# `mapfile`/`readarray` is bash 4+; macOS ships bash 3.2, so read into the array
# by hand or the whole sweep silently runs zero arms.
ARMS=()
if [ -n "${ARMS_FILE:-}" ]; then
    while IFS= read -r _line || [ -n "$_line" ]; do
        [ -n "$_line" ] && ARMS+=("$_line")
    done < "$ARMS_FILE"
else
    # Incumbent first, then smallest model first. Confirm curtailment compares each
    # challenger against a COMPLETE incumbent, so the incumbent must run before any
    # challenger (size order put phi4, the auto-math incumbent, last). Smallest-first
    # for the rest: the early arms finish fast, so a broken sweep shows itself in the
    # first hour, and each eviction leaves a larger inactive pool for the next arm.
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
try:
    with open('${DATA_ROOT}/tests/wfe/results/campaigns/${CAMPAIGN_ID}/manifest.json') as f:
        rows = json.load(f)['rows']
    incumbents = {r.get('model') or r['arm'] for r in rows if r.get('arm_role') == 'incumbent'}
except Exception:
    incumbents = set()
arms = [ln.strip() for ln in sys.stdin if ln.strip()]
for a in sorted(arms, key=lambda a: (a not in incumbents, size.get(a, 0), a)):
    print(a)
")
fi

if [ "${#ARMS[@]}" -eq 0 ]; then
    echo "$(ts) ABORT: no arms resolved (ARMS_FILE=${ARMS_FILE:-<none>}, --list-arms empty?)" \
        | tee -a "$PROGRESS_LOG"
    exit 2
fi
echo "$(ts) ARMS ${#ARMS[@]}" | tee -a "$PROGRESS_LOG"

# Serving conformance gate: refuse to spend hours measuring a misconfigured path. The
# campaign's workspace(s) must audit clean on the engine that serves them, and every arm's
# Ollama tag must carry its library template and clean stops (tests/wfe/settings_audit.py;
# the same audit is validate_system check HQ). WFE_SKIP_CONFORMANCE=1 is the escape hatch.
if [ "${WFE_SKIP_CONFORMANCE:-0}" != "1" ]; then
    printf '%s\n' "${ARMS[@]}" > "${LOG_DIR}/arms.txt"
    gate=$(uv run python -c "
import sys
from tests.wfe import settings_audit as audit
args = sys.argv[1:]
spaces = {args[i + 1] for i, a in enumerate(args[:-1]) if a == '--workspace'}
arms = sorted({ln.strip().split('@card-')[0] for ln in open('${LOG_DIR}/arms.txt') if ln.strip()})
seats = audit.run_audit()
tags = audit.audit_tags(arms)
renderer = audit.audit_renderer_gate(arms)
bad = [v for v in seats['violations'] if v['severity'] in ('WARN', 'FAIL') and (not spaces or v['workspace'].split('::')[0] in spaces)]
bad += [v for v in tags['violations'] if v['severity'] in ('WARN', 'FAIL')]
bad += [v for v in renderer['violations'] if v['severity'] in ('WARN', 'FAIL')]
for v in bad:
    print(f\"  {v['severity']} {v['workspace']}: {v['kind']} — {v['detail'][:200]}\")
print('CONFORMANCE', 'CLEAN' if not bad else f'{len(bad)} finding(s)')
" "$@" 2>&1)
    echo "$gate" | tee -a "$PROGRESS_LOG"
    if ! echo "$gate" | grep -q "CONFORMANCE CLEAN"; then
        echo "$(ts) ABORT: serving conformance findings above (fix them, or WFE_SKIP_CONFORMANCE=1)" \
            | tee -a "$PROGRESS_LOG"
        exit 3
    fi
fi

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
        # Record the stop so the finish verdict reports stopped, not complete.
        uv run python -c "
import sys
from tests.wfe.campaign import record_arm_stop
record_arm_stop(*sys.argv[1:])
" "${DATA_ROOT}/tests/wfe/results/campaigns/${CAMPAIGN_ID}" "$arm" "Ollama unreachable" \
            >> "$PROGRESS_LOG" 2>&1
        break
    fi

    echo "$(ts) START ${arm}" | tee -a "$PROGRESS_LOG"
    uv run python -m tests.wfe.campaign \
        --campaign-id "$CAMPAIGN_ID" \
        --arm "$arm" \
        $REPEATS_FLAG \
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

echo "$(ts) CAMPAIGN FINISH" | tee -a "$PROGRESS_LOG"
uv run python -m tests.wfe.campaign --campaign-id "$CAMPAIGN_ID" --status 2>&1 | tee -a "$PROGRESS_LOG"
echo "report: uv run python -m tests.wfe.report --campaign ${CAMPAIGN_ID}" | tee -a "$PROGRESS_LOG"
# --finish is the last call so its single CAMPAIGN line is the script's final stdout
# line and its code is the script's: a stopped campaign must not ride home as 0.
uv run python -m tests.wfe.campaign --campaign-id "$CAMPAIGN_ID" --finish 2>&1 | tee -a "$PROGRESS_LOG"
finish_rc=${PIPESTATUS[0]}
exit "$finish_rc"
