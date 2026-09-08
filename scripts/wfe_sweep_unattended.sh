#!/usr/bin/env bash
# wfe_sweep_unattended.sh — kick off the multi-day WFE fitness sweep and walk away.
#
# WHY THE STACK GOES DOWN — the sweep does not need it. The harness talks
# straight to Ollama (:11434) and brings its OWN six tools, implemented in
# process in tests/wfe/runner.py: file_read / file_write / file_list over a
# per-run sandbox, repo_search over `git grep`, pytest_run as a subprocess, and
# http_get straight out to the internet. Not one of them is an MCP server, so
# :8912-8935 and the pipeline on :9099 are irrelevant to a run. That is
# deliberate — a model's tool use has to be measurable and offline-re-gradable,
# which it would not be through a fleet of moving services.
#
# So the stack is not a dependency, it is a competitor for memory: ~10-15GB of
# containers, plus the pipeline pinning its intent classifier at keep_alive=-1.
# On a 64GB box against ~20GB arms that is the difference between measuring a
# model and measuring swap. Taking it down is the default; --no-down is
# supported and safe, because campaign.py evicts on model change either way.
#
# What it does, in order:
#   1. preconditions      Ollama up, config/ clean, every arm tag installed, disk
#                         headroom — all checked BEFORE anything is stopped
#   2. ./launch.sh down   frees the Docker VM (no -v; models are never touched)
#   3. evict Ollama       releases every resident model, the pinned classifier
#                         included, so arm 1 starts on a clean machine
#   4. --preflight        probes all arms smallest-first (~11 min for 17). An arm
#                         the harness cannot talk to produces NO rows, and
#                         unattended that is found at hour forty, not hour zero
#   5. the sweep          scripts/wfe_campaign.sh — one arm per process,
#                         resumable. Each arm drains every model that is not its
#                         own before its first row and gives its own back after
#                         the last, waiting on /api/ps rather than assuming
#   6. the report         tests.wfe.report, written next to the campaign
#   7. ./launch.sh up     restored via trap, whatever happened in 4-6
#
# Usage:
#   ./scripts/wfe_sweep_unattended.sh --detach                  # the normal one
#   ./scripts/wfe_sweep_unattended.sh                           # foreground
#   ./scripts/wfe_sweep_unattended.sh wfe_deep --detach         # named campaign
#   ./scripts/wfe_sweep_unattended.sh --check                   # preconditions only
#   ./scripts/wfe_sweep_unattended.sh --paths                   # just say where output goes
#   ./scripts/wfe_sweep_unattended.sh --no-down                 # leave the stack alone
#   ./scripts/wfe_sweep_unattended.sh --leave-down              # don't restore at the end
#   ./scripts/wfe_sweep_unattended.sh --strict-preflight        # abort if any arm needs review
#
# Watching it: the detach banner prints every path, but the one worth knowing is
#   uv run python -m tests.wfe.campaign --campaign-id <id> --watch
# a live per-arm view with row counts and an ETA, read-only, Ctrl-C safe. Raw
# logs are under /tmp/wfe_<id>/ and the evidence under the campaign directory.
#
# Resumable: re-run the same campaign id and it continues from the manifest.
# Env: REPEATS (3) BUDGET_S (1800) MAX_TURNS (16) ALL_SUITES (0)
#      NOTIFICATIONS_ENABLED (true here — the whole point is to be told)
#      PLAN — override tests/wfe/workloads.yaml. Use it to rehearse the whole
#      driver on a two-arm plan before committing the machine for two days.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
: "${NOTIFICATIONS_ENABLED:=true}"
export NOTIFICATIONS_ENABLED
# Exported so scripts/wfe_campaign.sh resolves the same arms this script checked.
PLAN_FLAG=""
if [ -n "${PLAN:-}" ]; then PLAN_FLAG="--plan ${PLAN}"; export PLAN; fi

CAMPAIGN_ID=""
DETACH=0
NO_DOWN=0
LEAVE_DOWN=0
CHECK_ONLY=0
PATHS_ONLY=0
STRICT_PREFLIGHT=0
for arg in "$@"; do
  case "$arg" in
    --detach)            DETACH=1 ;;
    --no-down)           NO_DOWN=1 ;;
    --leave-down)        LEAVE_DOWN=1 ;;
    --check)             CHECK_ONLY=1 ;;
    --paths)             PATHS_ONLY=1 ;;
    --strict-preflight)  STRICT_PREFLIGHT=1 ;;
    # Print the header comment block by SHAPE, not by line number: a hardcoded
    # range silently truncates the moment the header grows, which it just did.
    -h|--help)           awk 'NR>1 && /^#/ {sub(/^# ?/,""); print; next} NR>1 {exit}' \
                             "${BASH_SOURCE[0]}"; exit 0 ;;
    -*)                  echo "wfe-sweep: unknown flag '$arg'" >&2; exit 2 ;;
    *)                   CAMPAIGN_ID="$arg" ;;
  esac
done
CAMPAIGN_ID="${CAMPAIGN_ID:-wfe_full_$(date -u +%Y%m%d)}"

# Exported: scripts/wfe_campaign.sh derives the same default independently, so
# without this an operator LOG_DIR override would send the child somewhere the
# banner above does not name — a monitoring path that quietly lies.
LOG_DIR="${LOG_DIR:-/tmp/wfe_${CAMPAIGN_ID}}"
export LOG_DIR
CAMPAIGN_DIR_REL="tests/wfe/results/campaigns/${CAMPAIGN_ID}"
KICKOFF_LOG="${LOG_DIR}/kickoff.log"
mkdir -p "$LOG_DIR"

say()  { printf '\033[1;36m[wfe-sweep]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[wfe-sweep]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[wfe-sweep] BLOCKED:\033[0m %s\n' "$*" >&2; exit 1; }

# Where everything lands. Printed on detach, on --check and at the end of a
# foreground run, because a sweep whose output the operator cannot find is a
# sweep they cannot use. --paths prints it alone, which is also what makes it
# testable without committing the machine to 30 hours.
print_paths() {
  cat <<EOF

  WATCH     uv run python -m tests.wfe.campaign --campaign-id ${CAMPAIGN_ID} --watch
            Live per-arm progress, row counts and an ETA from what rows have
            actually cost. Read-only; Ctrl-C leaves the sweep running.

  status    uv run python -m tests.wfe.campaign --campaign-id ${CAMPAIGN_ID} --status
  health    uv run python -m tests.wfe.campaign --campaign-id ${CAMPAIGN_ID} --health
            One verdict + exit code (0 OK, 1 DONE, 2 STALLED, 3 DEGRADED).
            This is what a scheduled check-in should call.
  report    uv run python -m tests.wfe.report --campaign ${CAMPAIGN_ID}

  kickoff   tail -f ${KICKOFF_LOG}
              stack down/up, preflight, report
  progress  tail -f ${LOG_DIR}/progress.log
              arm START / DONE + exit codes
  per-arm   tail -f ${LOG_DIR}/*.log
              one line per row as it finishes ('/' and ':' in a tag become '_')
  rows      ${CAMPAIGN_DIR_REL}/manifest.json
              every row and its state; rewritten after each one
  evidence  ${CAMPAIGN_DIR_REL}/debug/*.debug.jsonl
              full request, response, tool calls and sandbox tree per run
EOF
}

if [ "$PATHS_ONLY" -eq 1 ]; then
  say "Campaign: ${CAMPAIGN_ID} — where its output goes:"
  print_paths
  exit 0
fi

# ── 1. preconditions — all of them before anything is stopped ────────────────
say "Campaign: ${CAMPAIGN_ID}"

curl -sf -m 10 "$OLLAMA_URL/api/version" >/dev/null 2>&1 \
  || die "Ollama not answering on $OLLAMA_URL — 'sudo launchctl kickstart -k system/com.portal5.ollama'"

dirty="$(git -C "$REPO" status --porcelain -- config/ | head -5)"
if [ -n "$dirty" ]; then
  die "config/ has uncommitted changes — a fitness sweep must measure committed config, not a draft:
$dirty"
fi

free_gb=$(df -g "$REPO" | awk 'NR==2 {print $4}')
[ "${free_gb:-0}" -ge 20 ] || die "only ${free_gb}GB free — the debug capture needs headroom"

# Every arm tag must be installed. A missing tag is 39 rows of HARNESS_ERROR.
missing="$(uv run python -m tests.wfe.campaign --list-arms $PLAN_FLAG 2>/dev/null \
  | sed 's/^[[:space:]]*[0-9]*[[:space:]]*//' | grep -v '^$' \
  | uv run python -c "
import json, sys, urllib.request
with urllib.request.urlopen('${OLLAMA_URL}/api/tags', timeout=10) as r:
    have = {m['name'] for m in json.load(r)['models']}
arms = [ln.strip() for ln in sys.stdin if ln.strip()]
if not arms:
    print('__NO_ARMS__')
for a in arms:
    if a not in have:
        print(a)
")"
[ "$missing" != "__NO_ARMS__" ] || die "the plan resolved zero arms — check tests/wfe/workloads.yaml"
[ -z "$missing" ] || die "arm tags not installed in Ollama:
$missing"

say "Preconditions OK (Ollama up, config/ clean, ${free_gb}GB free, all arms installed)."
uv run python -m tests.wfe.campaign --campaign-id "$CAMPAIGN_ID" $PLAN_FLAG \
    --repeats "${REPEATS:-3}" --append --dry-run

if [ "$CHECK_ONLY" -eq 1 ]; then
  say "--check: stopping here. Nothing was stopped or started."
  print_paths
  exit 0
fi

# ── 2. detach ────────────────────────────────────────────────────────────────
# caffeinate so a multi-day sweep is not ended by the display going to sleep;
# nohup so it is not ended by this terminal closing.
if [ "$DETACH" -eq 1 ]; then
  args=()
  for arg in "$@"; do [ "$arg" = "--detach" ] || args+=("$arg"); done
  say "Detaching under nohup + caffeinate…"
  nohup caffeinate -ims "${BASH_SOURCE[0]}" "${args[@]+"${args[@]}"}" \
      > "$KICKOFF_LOG" 2>&1 &
  pid=$!
  sleep 2
  echo
  echo "  started   pid ${pid}"
  print_paths
  echo
  echo "  stop      kill ${pid}     (safe — the campaign resumes from its manifest)"
  echo
  exit 0
fi

# ── 3. stack down, with restoration guaranteed ───────────────────────────────
STACK_WAS_UP=0
docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^portal5-pipeline$' && STACK_WAS_UP=1

restore() {
  rc=$?
  trap - EXIT INT TERM
  if [ "$STACK_WAS_UP" -eq 1 ] && [ "$LEAVE_DOWN" -eq 0 ] && [ "$NO_DOWN" -eq 0 ]; then
    say "Restoring the Portal stack (./launch.sh up)…"
    ./launch.sh up || warn "./launch.sh up failed — bring it up by hand."
  fi
  say "Exit ${rc}. Campaign ${CAMPAIGN_ID}."
  exit "$rc"
}
trap restore EXIT INT TERM

if [ "$NO_DOWN" -eq 0 ] && [ "$STACK_WAS_UP" -eq 1 ]; then
  say "Stopping the Portal stack for the duration (it competes for memory; the sweep does not use it)…"
  ./launch.sh down || die "./launch.sh down failed — refusing to sweep against a half-stopped stack"
else
  say "Stack already down (or --no-down) — skipping."
fi

# Ollama is a system LaunchDaemon and `launch.sh down` does not touch it; make
# sure of that before committing the next 40 hours to it.
curl -sf -m 10 "$OLLAMA_URL/api/version" >/dev/null 2>&1 \
  || die "Ollama went away with the stack — it should be independent of it"

# ── 4. evict everything Ollama still holds ───────────────────────────────────
loaded="$(curl -sf "$OLLAMA_URL/api/ps" 2>/dev/null | sed -n 's/.*"name":"\([^"]*\)".*/\1/p' || true)"
if [ -n "$loaded" ]; then
  while IFS= read -r m; do
    [ -n "$m" ] || continue
    say "Evicting resident model: $m"
    curl -sf "$OLLAMA_URL/api/generate" -d "{\"model\":\"$m\",\"keep_alive\":0}" >/dev/null 2>&1 || true
  done <<< "$loaded"
  sleep 3
fi

# ── 5. preflight the whole roster ────────────────────────────────────────────
say "Preflighting every arm (smallest first) — the cheap way to learn an arm is unreachable…"
uv run python -m tests.wfe.campaign --campaign-id "$CAMPAIGN_ID" $PLAN_FLAG \
    --repeats "${REPEATS:-3}" --append --preflight 2>&1 | tee "${LOG_DIR}/preflight.log"
pf_rc="${PIPESTATUS[0]}"
if [ "$pf_rc" -ne 0 ]; then
  if [ "$STRICT_PREFLIGHT" -eq 1 ]; then
    die "preflight flagged an arm and --strict-preflight is set — see ${LOG_DIR}/preflight.log"
  fi
  warn "Some arms need review — they will be BLOCKED, the rest of the sweep proceeds."
  warn "See ${LOG_DIR}/preflight.log. Fix and re-run this script: blocked rows are re-offered."
fi

# ── 6. the sweep ─────────────────────────────────────────────────────────────
say "Starting the sweep. Per-arm logs in ${LOG_DIR}/."
./scripts/wfe_campaign.sh "$CAMPAIGN_ID"
sweep_rc=$?

# ── 7. the report ────────────────────────────────────────────────────────────
say "Compiling the report…"
uv run python -m tests.wfe.report --campaign "$CAMPAIGN_ID" 2>&1 \
    | tee "${LOG_DIR}/report.txt" || warn "report failed — the rows are intact, re-run the report"

say "Sweep finished (exit ${sweep_rc}). Report: ${LOG_DIR}/report.txt"
print_paths
exit "$sweep_rc"
