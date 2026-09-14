#!/bin/bash
# Install / inspect / stop the offline compliance-reading qualification job.
#
#   --install   write the one-shot launchd plist and bootstrap it (starts now)
#   --status    default; print stage states, progress and receipt directories
#   --stop      bootout the job (a partial suite is NOT a qualification)
#
# The job is one-shot (KeepAlive=false). Its wrapper always exits 0, so never
# infer success from launchd; read the per-stage .exit files and each suite's
# summary.json "complete": true.

set -u
ART=${QUALIFICATION_DIR:-/tmp/compliance-reading-qualification-20260913}
LABEL=com.portal5.compliance.reading.qualification.20260913
REPO=/Users/chris/projects/portal-5
PLIST="$ART/qualification.plist"
MODE=${1:---status}

install_job() {
  mkdir -p "$ART"
  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>EnvironmentVariables</key>
	<dict>
		<key>PATH</key>
		<string>/Users/chris/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
		<key>PYTHONUNBUFFERED</key>
		<string>1</string>
		<key>QUALIFICATION_DIR</key>
		<string>$ART</string>
	</dict>
	<key>KeepAlive</key>
	<false/>
	<key>Label</key>
	<string>$LABEL</string>
	<key>ProgramArguments</key>
	<array>
		<string>/bin/bash</string>
		<string>$REPO/scripts/run_compliance_reading_qualification.sh</string>
	</array>
	<key>RunAtLoad</key>
	<true/>
	<key>StandardErrorPath</key>
	<string>$ART/qualification.log</string>
	<key>StandardOutPath</key>
	<string>$ART/qualification.log</string>
	<key>WorkingDirectory</key>
	<string>$REPO</string>
</dict>
</plist>
PLIST
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
  launchctl bootstrap "gui/$(id -u)" "$PLIST" || { echo "bootstrap failed"; exit 1; }
  echo "installed and started: $LABEL"
  echo "artifacts: $ART"
}

status_job() {
  echo "label:    $LABEL"
  echo "launchd:  $(launchctl list | grep -F "$LABEL" || echo 'not loaded')"
  echo "artifacts: $ART"
  [ -f "$ART/status.json" ] && { echo '--- status.json ---'; cat "$ART/status.json"; }
  for stage in stage1 stage2 stage3; do
    log="$ART/$stage.log"
    [ -f "$log" ] || continue
    echo "--- $stage ---"
    echo "exit: $(cat "$ART/$stage.exit" 2>/dev/null || echo 'still running')"
    echo "receipts: $(head -1 "$log" | sed -n 's/^receipts: //p')"
    grep -E '^(case |PASS |FAIL |run_id=.* status=)' "$log" | tail -5
  done
  # A suite is only qualified when its own summary says so.
  python3 - "$ART" <<'PY'
import json, pathlib, sys
art = pathlib.Path(sys.argv[1])
for stage in ("stage1", "stage2", "stage3"):
    log = art / f"{stage}.log"
    if not log.exists():
        continue
    first = log.read_text(errors="replace").splitlines()[:1]
    if not first or not first[0].startswith("receipts: "):
        continue
    summary = pathlib.Path(first[0][len("receipts: "):]) / "summary.json"
    if not summary.exists():
        print(f"{stage}: no summary.json yet")
        continue
    data = json.loads(summary.read_text())
    rows = data.get("rows", [])
    counts: dict[str, int] = {}
    for row in rows:
        counts[row[1]] = counts.get(row[1], 0) + 1
    print(f"{stage}: complete={data.get('complete')} rows={len(rows)} {counts}")
PY
}

case "$MODE" in
  --install) install_job ;;
  --stop)    launchctl bootout "gui/$(id -u)/$LABEL" && echo "stopped $LABEL" ;;
  *)         status_job ;;
esac
