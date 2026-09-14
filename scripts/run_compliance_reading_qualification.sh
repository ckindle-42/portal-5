#!/bin/zsh
# Offline qualification runner for the compliance reading architecture.
#
# Runs the three outstanding qualification stages (resume doc §5C–D) back to
# back on ONE fixed code revision, with no concurrent model acceptance workers:
#
#   stage1  live acceptance, all 26 cases, 1 run each
#   stage2  live acceptance, cases 01–05, 2 further runs each (3 observations)
#   stage3  deployed-HTTP scoped R2 route verification
#
# Stages are deliberately NOT chained with `&&`: a semantic FAIL in stage 1 must
# not suppress the required repetitions. Each stage writes its own log, its own
# child exit code, and a line in status.json. The wrapper always exits 0 so a
# supervisor never restarts a failed suite; read the .exit files instead.
#
# Normally launched detached via the one-shot launchd job installed by
# scripts/check_compliance_reading_qualification.sh --install.

set -u
REPO=/Users/chris/projects/portal-5
ART=${QUALIFICATION_DIR:-/tmp/compliance-reading-qualification-20260913}
UV=/Users/chris/.local/bin/uv
mkdir -p "$ART"
cd "$REPO" || exit 0

STATUS="$ART/status.json"
REV=$(git -C "$REPO" rev-parse HEAD)
DIRTY=$(git -C "$REPO" status --porcelain | wc -l | tr -d ' ')

note() { print -r -- "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

write_status() {
  python3 - "$STATUS" "$REV" "$DIRTY" "$@" <<'PY'
import json, sys, datetime
path, rev, dirty = sys.argv[1], sys.argv[2], sys.argv[3]
stages = {}
try:
    stages = json.load(open(path)).get("stages", {})
except Exception:
    pass
for entry in sys.argv[4:]:
    name, state, code = entry.split(":", 2)
    stages.setdefault(name, {})
    stages[name]["state"] = state
    if code != "-":
        stages[name]["exit"] = int(code)
    stages[name]["updated_at"] = datetime.datetime.now(datetime.UTC).isoformat()
json.dump(
    {"git_head": rev, "dirty_paths": int(dirty), "stages": stages},
    open(path, "w"),
    indent=2,
)
PY
}

run_stage() {
  local name=$1; shift
  local log="$ART/$name.log"
  if [ -f "$ART/$name.exit" ]; then
    note "$name already finished (exit $(cat "$ART/$name.exit")); skipping"
    return
  fi
  note "$name START: $*"
  write_status "$name:RUNNING:-"
  "$@" >> "$log" 2>&1
  local rc=$?
  print -r -- "$rc" > "$ART/$name.exit"
  write_status "$name:FINISHED:$rc"
  note "$name FINISHED exit=$rc (log: $log)"
}

# One acceptance worker at a time: a second live suite invalidates both.
if pgrep -f "verify_compliance_reading_acceptance.py --live" > /dev/null; then
  note "ABORT: a live acceptance worker is already running"
  exit 0
fi

note "qualification start rev=$REV dirty_paths=$DIRTY artifacts=$ART"
run_stage stage1 "$UV" run python scripts/verify_compliance_reading_acceptance.py --live --runs 1
run_stage stage2 "$UV" run python scripts/verify_compliance_reading_acceptance.py \
  --live --cases 01,02,03,04,05 --runs 2
# stage 3 talks to the DEPLOYED service, so restart it on the final code first.
if [ ! -f "$ART/stage3.exit" ]; then
  note "restarting com.portal5.compliance-mcp onto rev=$REV"
  launchctl kickstart -k "gui/$(id -u)/com.portal5.compliance-mcp" \
    || note "WARN: kickstart failed; stage3 may test stale deployed code"
  for _ in $(seq 1 60); do
    curl -fsS -m 3 http://localhost:8937/health > /dev/null 2>&1 && break
    sleep 2
  done
  curl -fsS -m 3 http://localhost:8937/health > /dev/null 2>&1 \
    || note "WARN: compliance-mcp health did not come back before stage3"
fi
run_stage stage3 "$UV" run python scripts/verify_compliance_reading_route.py

note "QUALIFICATION_FINISHED stage1=$(cat "$ART/stage1.exit" 2>/dev/null) \
stage2=$(cat "$ART/stage2.exit" 2>/dev/null) stage3=$(cat "$ART/stage3.exit" 2>/dev/null)"
exit 0
