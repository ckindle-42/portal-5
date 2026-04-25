# TASK_WATCHDOG_REWRITE_V1.md

**Source:** Standalone watchdog rewrite (not part of Phase 1/2/3 sequence).
**Prerequisite:** Operator places the new watchdog at `scripts/mlx-watchdog.py.new` before running this task. The new file is provided alongside this task document.
**Supersedes:** Phase 1 Task 1.16 (`recover_proxy` minor patch). Mark superseded by Task 5 below.
**Target version:** 6.0.4 (no project version bump required — single-file rewrite of a daemon).
**Estimated effort:** 30 min on the live system, 0 risk during install (full revert via single `git checkout` + restart).
**Risk:** Low. The new file is drop-in compatible with `start-mlx-watchdog` / `stop-mlx-watchdog`. No proxy or pipeline changes. Rollback restores byte-for-byte.

---

## Why this exists rather than copy/paste instructions

The standard project pattern is task-file-then-coding-agent. Manual swaps invite drift, missed steps (forgotten backup, forgotten env update, forgotten launch.sh restart, no metrics-endpoint verification). This file is executable by Claude Code — every step is verifiable, every revert is one command.

---

## Scope

The watchdog is being replaced wholesale. The new file:

1. Async throughout — `asyncio.gather` for concurrent probes, `asyncio.sleep` for waits. A 30s Metal GPU memory reclaim no longer blocks proxy /health probing.
2. Memory-aware zombie kills — escalates to immediate SIGKILL when proxy reports `memory_free_gb < MLX_MEMORY_CRITICAL_GB` (default 8).
3. Decaying recovery counter — `recovery_attempts` decrements after `MLX_RECOVERY_DECAY_S` (default 3600s) of sustained health. Flaky weekly crashes no longer accumulate to permanent giving-up.
4. `launchctl kickstart -k gui/<uid>/com.portal5.mlx-proxy` for proxy restart (preserves plist `EnvironmentVariables` — fixes REL-16 directly).
5. Forensic capture before recovery: `/tmp/mlx-watchdog-forensics-<ts>.json` containing last `/health`, last 100 proxy log lines, MLX process listing, `vm_stat`.
6. Notification debounce by event class (default 5 min cooldown). Recovery events use `force=True` so all-clears always go through.
7. Prometheus metrics endpoint on port `MLX_WATCHDOG_METRICS_PORT` (default 9101).
8. `fcntl.flock` singleton — atomic, no PID-file race window.

**Out of scope:** No changes to `mlx-proxy.py`. The in-proxy `_cleanup_zombie_servers` stays exactly as-is. The two recovery paths handle distinct failure modes by design.

---

## Pre-flight (run once before any task)

```bash
# Tag for rollback safety
git tag pre-watchdog-rewrite

# Confirm the new file exists at the expected staging path
test -f scripts/mlx-watchdog.py.new && echo "OK: new watchdog staged" || {
    echo "ERROR: scripts/mlx-watchdog.py.new not found — operator must place it there first"
    exit 1
}

# Capture current watchdog state for after-vs-before comparison
launchctl list 2>/dev/null | grep -E 'com.portal5.mlx-(proxy|watchdog)' > /tmp/launchctl_before_watchdog_swap.txt 2>&1 || true
[ -f /tmp/mlx-watchdog.pid ] && cat /tmp/mlx-watchdog.pid > /tmp/watchdog_pid_before.txt 2>&1 || true
```

---

## Task 1 — Validate the new watchdog in isolation

### Rationale
Run syntax + import + a no-op smoke test against the new file BEFORE swapping. Catches obvious regressions (missing import, typo) without touching the running watchdog.

### Action
```bash
# Syntax + AST parse
python3 -c "import ast; ast.parse(open('scripts/mlx-watchdog.py.new').read()); print('syntax OK')"

# Import test (requires httpx — already a project dep)
python3 -c "
import sys
sys.path.insert(0, 'scripts')
import importlib.util
spec = importlib.util.spec_from_file_location('mlx_watchdog_new', 'scripts/mlx-watchdog.py.new')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
# Spot-check key symbols
assert hasattr(m, 'Config'), 'Config dataclass missing'
assert hasattr(m, 'classify_zombie'), 'classify_zombie missing'
assert hasattr(m, 'restart_proxy_via_launchctl'), 'launchctl restart missing'
assert hasattr(m, 'WatchdogMetrics'), 'metrics class missing'
assert hasattr(m, 'NotificationBus'), 'notification bus missing'
print('imports OK, key symbols present')
"
```

### Expected
Two `OK` lines. Any error means the file is broken; STOP and report.

### Rollback (if Task 1 fails)
```bash
rm scripts/mlx-watchdog.py.new
```
The repo is unchanged.

### No commit yet
Task 1 is verification only. No git changes.

---

## Task 2 — Stop the running watchdog

### Rationale
Stop cleanly before swapping the binary so we don't kill an in-progress recovery cycle. The current watchdog handles SIGTERM gracefully (notifies, removes PID file).

### Action
```bash
./launch.sh stop-mlx-watchdog

# Verify stopped
sleep 3
[ ! -f /tmp/mlx-watchdog.pid ] && echo "OK: watchdog stopped" || {
    echo "WARN: PID file still present — checking process"
    pgrep -f mlx-watchdog.py && {
        echo "ERROR: watchdog still running"
        exit 1
    } || echo "OK: process gone, stale PID file cleaned"
    rm -f /tmp/mlx-watchdog.pid
}
```

### Expected
`OK: watchdog stopped`.

### Rollback
The watchdog can be restarted with `./launch.sh start-mlx-watchdog`. Nothing destructive yet.

### No commit yet
This is a runtime action, not a code change.

---

## Task 3 — Swap the file (with backup)

### Rationale
Backup the current watchdog to a sibling file, then replace it. Keep the backup in-tree as `.bak` so it shows up in `git status` and the operator can see the diff explicitly. The backup is removed by Task 8 only after the new watchdog has proven healthy — until then it's recoverable.

### Action
```bash
# Backup current
cp scripts/mlx-watchdog.py scripts/mlx-watchdog.py.bak

# Swap
mv scripts/mlx-watchdog.py.new scripts/mlx-watchdog.py

# Verify swap
test -f scripts/mlx-watchdog.py.bak && echo "OK: backup at .bak"
test -f scripts/mlx-watchdog.py && echo "OK: new file in place"
test ! -f scripts/mlx-watchdog.py.new && echo "OK: staging file consumed"

# Diff size sanity (new is larger — async + metrics + forensics add ~600 lines)
old_lines=$(wc -l < scripts/mlx-watchdog.py.bak)
new_lines=$(wc -l < scripts/mlx-watchdog.py)
echo "Old: $old_lines lines, New: $new_lines lines"
[ "$new_lines" -gt "$old_lines" ] && echo "OK: new file is larger as expected" || \
    echo "WARN: new file is not larger — verify this is the rewrite, not the original"
```

### Verify
```bash
# File header confirms it's the rewrite (looks for "v2" in module docstring)
head -3 scripts/mlx-watchdog.py | grep -q 'v2' && echo "OK: rewrite confirmed by header"
```

### Rollback
```bash
mv scripts/mlx-watchdog.py.bak scripts/mlx-watchdog.py
```

### Commit (after Task 8 confirms healthy)
Defer commit to Task 8. The change is staged in the working tree until then.

---

## Task 4 — Document new env vars in `.env.example`

### Rationale
The rewrite introduces three new tunable env vars. Document defaults so operators discover them when reviewing `.env.example`.

### Before — append to `.env.example`

Find the existing MLX watchdog block (search for `MLX_WATCHDOG_ENABLED`), and add the new variables after it:

```bash
# Append new env vars to .env.example
cat >> .env.example << 'EOF'

# ── MLX Watchdog v2 additions ──────────────────────────────────────────────
# Memory pressure threshold (GB). Below this, the watchdog skips SIGTERM
# grace and goes straight to SIGKILL on zombie servers — every byte counts
# when the system is starved.
# MLX_MEMORY_CRITICAL_GB=8

# After this many seconds of sustained component health, the watchdog
# decrements recovery_attempts by 1. A flaky service that crashes once a
# week earns its budget back rather than accumulating toward
# MLX_MAX_RECOVERY_ATTEMPTS forever.
# MLX_RECOVERY_DECAY_S=3600

# Skip zombie checks during proxy state=switching if state has lasted less
# than this many seconds. Above this, the model load is taking too long
# and a hung server should still be killed.
# MLX_ZOMBIE_MIN_AGE=120

# Watchdog Prometheus metrics endpoint
# MLX_WATCHDOG_METRICS_ENABLED=true
# MLX_WATCHDOG_METRICS_PORT=9101

# Notification debounce: same event class within this window is suppressed
# (recovery notifications bypass via force=True so all-clears always go through).
# MLX_NOTIFY_COOLDOWN_S=300

# Forensic capture path. Watchdog writes a JSON snapshot to this directory
# before attempting proxy recovery, capturing /health, log tail, ps, vm_stat.
# MLX_FORENSICS_DIR=/tmp
# MLX_FORENSICS_LOG_TAIL=100
# MLX_PROXY_LOG_PATH=$HOME/.portal5/logs/mlx-proxy.log
EOF
```

### Verify
```bash
grep -c 'MLX_MEMORY_CRITICAL_GB\|MLX_RECOVERY_DECAY_S\|MLX_WATCHDOG_METRICS_PORT' .env.example
# Expected: 3
```

### Rollback
```bash
git checkout .env.example
```

---

## Task 5 — Mark Phase 1 Task 1.16 superseded

### Rationale
Phase 1 Task 1.16 (`recover_proxy uses launchctl kickstart`) is now redundant — the rewrite implements this fix natively as part of `restart_proxy_via_launchctl`. Leaving Task 1.16 in the phase file would cause the coding agent to attempt a second, conflicting modification. Mark it explicitly superseded so the agent skips it.

### Edit
At the top of `## Task 1.16 — \`recover_proxy\` uses \`launchctl kickstart\` (REL-16)` in `TASK_REVIEW_FIXES_PHASE1_QUICK_WINS.md`, prepend a SUPERSEDED notice:

```bash
python3 << 'PYEOF'
from pathlib import Path
p = Path('TASK_REVIEW_FIXES_PHASE1_QUICK_WINS.md')
s = p.read_text()
old_header = '## Task 1.16 — `recover_proxy` uses `launchctl kickstart` (REL-16)'
new_header = '''## Task 1.16 — `recover_proxy` uses `launchctl kickstart` (REL-16) ⚠️ SUPERSEDED

> **SUPERSEDED by `TASK_WATCHDOG_REWRITE_V1.md`** — the watchdog rewrite implements
> launchctl-based proxy restart natively. Skip this task entirely. The full
> watchdog rewrite covers REL-16 plus several other improvements (async,
> memory-aware kills, decaying recovery counter, forensic capture, metrics
> endpoint). Effort below is preserved as historical context only.

---

(Original task content below — DO NOT execute)

## Original Task 1.16 — `recover_proxy` uses `launchctl kickstart` (REL-16)'''
assert old_header in s, 'Task 1.16 header not found exactly — manual edit required'
s = s.replace(old_header, new_header, 1)
p.write_text(s)
print('Task 1.16 marked SUPERSEDED')
PYEOF
```

### Verify
```bash
grep -A1 'Task 1.16' TASK_REVIEW_FIXES_PHASE1_QUICK_WINS.md | head -3
# Expected: SUPERSEDED notice on the next line
```

### Update Phase 1 totals
The Phase 1 commit count goes from 13 to 12 (Task 1.16 no longer commits). Update the totals table at the bottom:

```bash
python3 << 'PYEOF'
from pathlib import Path
p = Path('TASK_REVIEW_FIXES_PHASE1_QUICK_WINS.md')
s = p.read_text()
old = '**Total: ~5 hours of focused work, 13 commits, 16 verifiable changes.**'
new = '**Total: ~4.5 hours of focused work, 12 commits, 15 verifiable changes (Task 1.16 superseded by TASK_WATCHDOG_REWRITE_V1.md).**'
assert old in s, 'totals line not found'
s = s.replace(old, new)
p.write_text(s)
print('Phase 1 totals updated')
PYEOF
```

### Rollback
```bash
git checkout TASK_REVIEW_FIXES_PHASE1_QUICK_WINS.md
```

---

## Task 6 — Start the new watchdog

### Rationale
Launch the rewrite. `./launch.sh start-mlx-watchdog` is unchanged — it loads `com.portal5.mlx-watchdog` from the existing plist. The plist's `ProgramArguments` points to `scripts/mlx-watchdog.py`, which now contains the rewrite.

### Action
```bash
./launch.sh start-mlx-watchdog
sleep 5
```

### Verify
```bash
# 1. PID file exists
test -f /tmp/mlx-watchdog.pid && echo "OK: PID file present"

# 2. Process running and is the rewrite
PID=$(cat /tmp/mlx-watchdog.pid)
ps -p "$PID" -o command= | grep -q mlx-watchdog.py && echo "OK: process running PID=$PID"

# 3. Lock file held (rewrite-only feature)
test -f /tmp/mlx-watchdog.lock && echo "OK: flock singleton lock present"

# 4. Log shows rewrite startup banner
tail -20 ~/.portal5/logs/mlx-watchdog.log | grep -q 'MLX Watchdog v2 starting' && \
    echo "OK: log confirms v2 startup" || {
    echo "ERROR: log does not show v2 startup banner"
    tail -20 ~/.portal5/logs/mlx-watchdog.log
    exit 1
}

# 5. Singleton enforced — second start attempt exits cleanly with code 0
python3 scripts/mlx-watchdog.py &
SECOND_PID=$!
sleep 3
wait "$SECOND_PID" 2>/dev/null
SECOND_RC=$?
[ "$SECOND_RC" -eq 0 ] && echo "OK: second-instance attempt exited cleanly" || \
    echo "WARN: second instance returned code $SECOND_RC"
```

### Rollback (if Task 6 fails)
```bash
./launch.sh stop-mlx-watchdog
mv scripts/mlx-watchdog.py.bak scripts/mlx-watchdog.py
./launch.sh start-mlx-watchdog
```

---

## Task 7 — Validate the metrics endpoint

### Rationale
The metrics endpoint is the most visible new feature. Confirm it's reachable, returns valid Prometheus exposition, and shows live data.

### Action
```bash
# Wait for first cycle to complete (default cycle is 30s; allow up to 35)
sleep 35

# 1. Endpoint responds
curl -sf -o /tmp/watchdog_metrics.txt http://127.0.0.1:9101/metrics && \
    echo "OK: metrics endpoint responding"

# 2. Required metrics present
for metric in \
    mlx_watchdog_cycles_total \
    mlx_watchdog_zombie_kills_total \
    mlx_watchdog_proxy_restarts_total \
    mlx_watchdog_proxy_state \
    mlx_watchdog_memory_free_gb \
    mlx_watchdog_proxy_consecutive_failures \
    ; do
    grep -q "^${metric}" /tmp/watchdog_metrics.txt || grep -q "^${metric}{" /tmp/watchdog_metrics.txt && \
        echo "  ✓ $metric" || { echo "  ✗ MISSING: $metric"; exit 1; }
done

# 3. cycles_total > 0 (one cycle ran)
CYCLES=$(grep '^mlx_watchdog_cycles_total ' /tmp/watchdog_metrics.txt | awk '{print $2}')
[ "$CYCLES" -ge 1 ] && echo "OK: cycles_total = $CYCLES" || {
    echo "ERROR: cycles_total is $CYCLES — watchdog cycle did not complete"
    exit 1
}

# 4. proxy_state populated
grep '^mlx_watchdog_proxy_state{state=' /tmp/watchdog_metrics.txt && echo "OK: proxy_state populated"
```

### Rollback (if Task 7 fails)
Same as Task 6 rollback — restore `.bak`, restart watchdog.

### Optional: Add to Prometheus scrape config
Out of scope for this task. If your existing `prometheus.yml` has a generic
`mlx_watchdog_*` scrape job, restart Prometheus and the metrics will flow
into Grafana automatically. If not, add this block (separate task):

```yaml
scrape_configs:
  - job_name: 'mlx-watchdog'
    scrape_interval: 30s
    static_configs:
      - targets: ['host.docker.internal:9101']
```

---

## Task 8 — Smoke test, remove backup, commit

### Rationale
Final validation before committing. Confirm the watchdog responds to a deliberate but non-destructive trigger (we read the proxy state to make sure the watchdog is observing it correctly), then remove the .bak file and commit the change.

### Action
```bash
# 1. Confirm proxy state is being observed by the new watchdog
PROXY_STATE=$(curl -sf http://127.0.0.1:9101/metrics | grep '^mlx_watchdog_proxy_state{state=' | sed 's/.*state="\([^"]*\)".*/\1/')
echo "Watchdog reports proxy state: $PROXY_STATE"
[ -n "$PROXY_STATE" ] && [ "$PROXY_STATE" != "unknown" ] && \
    echo "OK: watchdog is observing the proxy" || {
    echo "ERROR: watchdog reports proxy state '$PROXY_STATE' — not observing correctly"
    exit 1
}

# 2. Notification bus initialized (look for the startup banner notification)
grep -q 'watchdog_started' ~/.portal5/logs/mlx-watchdog.log && \
    echo "OK: startup notification dispatched" || \
    echo "INFO: startup notification not dispatched (may indicate no channels configured)"

# 3. No errors in the watchdog log
ERR_COUNT=$(grep -c '^.*ERROR' ~/.portal5/logs/mlx-watchdog.log | tail -1)
[ "$ERR_COUNT" -eq 0 ] && echo "OK: no errors in log" || {
    echo "WARN: $ERR_COUNT ERROR lines in log — review:"
    grep ERROR ~/.portal5/logs/mlx-watchdog.log | tail -10
}

# 4. Remove backup
rm scripts/mlx-watchdog.py.bak
echo "OK: backup removed"

# 5. Lockfile sanity (singleton works)
test -f /tmp/mlx-watchdog.lock && echo "OK: lock file present"
```

### Verify
```bash
# Final state check before commit
git status --short
# Expected:
#   M  scripts/mlx-watchdog.py
#   M  .env.example
#   M  TASK_REVIEW_FIXES_PHASE1_QUICK_WINS.md
```

### Commit
```bash
git add scripts/mlx-watchdog.py .env.example TASK_REVIEW_FIXES_PHASE1_QUICK_WINS.md
git commit -m "$(cat <<'COMMIT_EOF'
refactor(watchdog): full rewrite with async, metrics, decaying recovery

Replaces scripts/mlx-watchdog.py wholesale. The new file is a drop-in
replacement: same launchctl plist, same env vars (plus several new
optional ones), same start/stop launch.sh commands.

Key changes:

  * Async throughout. asyncio.gather for concurrent probes, asyncio.sleep
    for waits. A 30s Metal GPU memory reclaim no longer blocks proxy
    health probing.
  * Memory-aware zombie kills. When proxy reports memory_free_gb <
    MLX_MEMORY_CRITICAL_GB (default 8), kills escalate to immediate
    SIGKILL skipping the SIGTERM grace.
  * Decaying recovery counter. recovery_attempts decrements by 1 after
    MLX_RECOVERY_DECAY_S (default 3600s) of sustained health. A flaky
    service that crashes once a week no longer accumulates toward
    MLX_MAX_RECOVERY_ATTEMPTS forever.
  * launchctl kickstart -k for proxy restart preserves the plist's
    EnvironmentVariables block (HF_HOME, HF_HUB_CACHE, HF_TOKEN) and
    keeps the new process under launchd's KeepAlive. Falls back to
    subprocess.Popen on Linux dev environments.
  * Forensic capture before recovery: /tmp/mlx-watchdog-forensics-<ts>.json
    with last /health response, last 100 proxy log lines, MLX process
    listing, and vm_stat. Operators have something to debug from after
    auto-recovery.
  * Notification debounce by event class. Same event within
    MLX_NOTIFY_COOLDOWN_S (default 5min) is suppressed; recovery
    notifications bypass via force=True so all-clears always go through.
  * Prometheus metrics endpoint on MLX_WATCHDOG_METRICS_PORT (9101).
    Counters and gauges feed the existing Grafana dashboard.
  * fcntl.flock singleton replaces the PID-file race-prone check.

Resolves: REL-16 (supersedes Phase 1 Task 1.16 — recover_proxy now uses
launchctl kickstart natively).

No changes to mlx-proxy.py. The in-process _cleanup_zombie_servers stays
exactly as-is — the two recovery layers remain by-design separate.
COMMIT_EOF
)"
```

---

## Phase verification (run after all tasks land)

```bash
set -e

echo "── Watchdog process running ──"
test -f /tmp/mlx-watchdog.pid && pgrep -f mlx-watchdog.py >/dev/null && echo "OK"

echo "── Metrics endpoint responding ──"
curl -sf http://127.0.0.1:9101/metrics > /dev/null && echo "OK"

echo "── Cycles incrementing ──"
C1=$(curl -sf http://127.0.0.1:9101/metrics | grep '^mlx_watchdog_cycles_total ' | awk '{print $2}')
sleep 35
C2=$(curl -sf http://127.0.0.1:9101/metrics | grep '^mlx_watchdog_cycles_total ' | awk '{print $2}')
[ "$C2" -gt "$C1" ] && echo "OK: cycles $C1 → $C2"

echo "── Proxy still healthy ──"
curl -sf http://127.0.0.1:8081/health | jq -r .state | grep -qE '^(ready|none|down)$' && echo "OK"

echo "── Singleton enforced ──"
python3 scripts/mlx-watchdog.py &
SECOND=$!
sleep 3
wait "$SECOND" 2>/dev/null
[ "$?" -eq 0 ] && echo "OK"

echo "── No proxy.py changes (rewrite is watchdog-only) ──"
git diff --quiet HEAD scripts/mlx-proxy.py && echo "OK"

echo "── Phase verification PASSED ──"
```

---

## Rollback (full)

If anything goes wrong at any stage after Task 3:

```bash
# 1. Stop the new watchdog
./launch.sh stop-mlx-watchdog

# 2. Restore old file
git reset --hard pre-watchdog-rewrite

# 3. Restart
./launch.sh start-mlx-watchdog

# 4. Verify old behavior restored
sleep 5
tail -5 ~/.portal5/logs/mlx-watchdog.log | grep -v 'v2 starting' && echo "OK: old watchdog running"

# 5. Clean up
git tag -d pre-watchdog-rewrite
```

---

## Total scope

| Task | Action | Lines / Effort |
|---|---|---|
| 1 | Validate new file in isolation | 0 / 2 min |
| 2 | Stop running watchdog | 0 / 1 min |
| 3 | Backup + swap file | ±2 / 1 min |
| 4 | Document new env vars | +25 to .env.example / 5 min |
| 5 | Mark Phase 1 Task 1.16 superseded | 2 edits / 3 min |
| 6 | Start new watchdog | 0 / 2 min |
| 7 | Validate metrics endpoint | 0 / 2 min |
| 8 | Smoke test + commit | 0 / 5 min |

**Total: ~30 min, 1 commit, full rollback via `git reset --hard pre-watchdog-rewrite`.**

— end of task —
