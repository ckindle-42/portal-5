#!/bin/bash
# Unattended runner for the CIP-007-6 live acceptance suite.
#
# TASK_COMPLIANCE_PROVE_CIP_007_V1 §P3. Keeps the sound bones of
# run_compliance_reading_qualification.sh — one worker at a time, per-stage exit
# files, status.json, aborted-log archiving, launchd one-shot — and drops the two
# things that made it stop being evidence: a dated /tmp artifact path, and a
# health check pointed at a port nobody verified. Artifacts land under the git
# rev inside the repo; the port comes from config/portal.yaml's own fleet roster.
#
# Stages are NOT chained with `&&`: a semantic FAIL in the reader stage must not
# suppress the legacy comparison, which is what makes F1's re-point measurable.
# The wrapper always exits 0 so a supervisor never restarts a failed suite; read
# the .exit files.

set -u
REPO=/Users/chris/projects/portal-5
UV=/Users/chris/.local/bin/uv
cd "$REPO" || exit 0

REV=$(git -C "$REPO" rev-parse HEAD)
ART=${ACCEPTANCE_DIR:-$REPO/reports/compliance/acceptance/$REV}
mkdir -p "$ART"
DIRTY=$(git -C "$REPO" status --porcelain | wc -l | tr -d ' ')

note() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

run_stage() {
  local name=$1; shift
  local log="$ART/${name}.log"
  if [ -f "$ART/${name}.stage-exit" ]; then
    note "$name already finished (exit $(cat "$ART/${name}.stage-exit")); skipping"
    return
  fi
  # A log with no exit file is an aborted attempt: keep it, but start a fresh log
  # so the first line still names THIS attempt.
  if [ -s "$log" ]; then
    mv "$log" "$log.aborted-$(date -u +%Y%m%dT%H%M%SZ)"
    note "$name: archived an aborted log"
  fi
  note "$name START: $*"
  "$@" >> "$log" 2>&1
  local rc=$?
  printf '%s\n' "$rc" > "$ART/${name}.stage-exit"
  note "$name FINISHED exit=$rc (log: $log)"
}

if pgrep -f "compliance_acceptance.py" > /dev/null; then
  note "ABORT: an acceptance worker is already running"
  exit 0
fi

# The suite talks to the DEPLOYED service, so it must be running THIS revision.
PORT=$("$UV" run python - <<'PY'
import sys
sys.path.insert(0, "/Users/chris/projects/portal-5")
from scripts.compliance_acceptance import mcp_base_url
print(mcp_base_url().rsplit(":", 1)[1])
PY
)
note "restarting com.portal5.compliance-mcp onto rev=$REV (port $PORT)"
launchctl kickstart -k "gui/$(id -u)/com.portal5.compliance-mcp" \
  || note "WARN: kickstart failed; the suite may test stale deployed code"
for _ in $(seq 1 60); do
  curl -fsS -m 3 "http://localhost:${PORT}/health" > /dev/null 2>&1 && break
  sleep 2
done
curl -fsS -m 3 "http://localhost:${PORT}/health" > /dev/null 2>&1 \
  || { note "ABORT: compliance-mcp health never came back on ${PORT}"; exit 0; }

note "acceptance start rev=$REV dirty_paths=$DIRTY artifacts=$ART"
run_stage reader "$UV" run python scripts/compliance_acceptance.py --runs "${RUNS:-3}"
run_stage legacy "$UV" run python scripts/compliance_acceptance.py --adapter legacy --runs 1

note "ACCEPTANCE_FINISHED reader=$(cat "$ART/reader.stage-exit" 2>/dev/null) \
legacy=$(cat "$ART/legacy.stage-exit" 2>/dev/null)"
exit 0
