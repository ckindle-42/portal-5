#!/usr/bin/env bash
# V5 quantization ladder bench orchestrator.
# Per TASK_MODEL_REFRESH_V5 §E.
#
# Memory management mirrors portal5_uat_driver.py _restart_proxy_for_reclaim():
#   1. SIGTERM the proxy (graceful shutdown — stops current mlx_lm/vlm server).
#   2. SIGTERM any residual mlx_lm/vlm server processes.
#   3. Start a fresh proxy — a new process forces the VM pager to release
#      stale Metal allocations left in the inactive pool by smoke test runs.
#   4. Wait 60s for the proxy's MemoryMonitor to complete its first sample.
#   5. Verify free_gb >= 4 before proceeding to bench.
#
# Then bench each smoke-PASSed model one at a time through bench_tps.py's
# built-in load→test→evict→reclaim→cooldown cycle. bench_tps.py resume
# support (runs_success>0) skips models already successfully benched.
#
# Output: tests/benchmarks/results/bench_tps_v5_ladders.json

set -euo pipefail

cd "$(dirname "$0")/.."

# Smoke test must have been run first
test -f tests/results/smoke_test_v5.json || {
  echo "ERROR: tests/results/smoke_test_v5.json not found. Run scripts/smoke_test_mlx.py first."
  exit 1
}

# Identify smoke-PASSed models — only bench those
PASSED_MODELS=$(python3 -c "
import json
with open('tests/results/smoke_test_v5.json') as f:
    results = json.load(f)
for r in results:
    if r.get('status') == 'PASS':
        print(r['model'])
")

if [ -z "$PASSED_MODELS" ]; then
  echo "ERROR: No models passed smoke test. Aborting bench."
  exit 1
fi

echo "=== V5 Ladder Bench ==="
echo "Smoke-PASSed models to bench:"
echo "$PASSED_MODELS"
echo

# ── Pause mlx-watchdog for the duration of this bench ────────────────────────
# The watchdog's zombie-kill and proxy-restart actions conflict with the bench's
# own controlled restart sequence below. The sentinel puts it in passive (monitor-
# only) mode. Removed in the EXIT trap so it's always cleaned up, even on error.
WATCHDOG_SENTINEL="/tmp/mlx-watchdog-paused"
touch "$WATCHDOG_SENTINEL" 2>/dev/null || true
trap 'rm -f "$WATCHDOG_SENTINEL"' EXIT
echo "  Watchdog passive mode: $WATCHDOG_SENTINEL created (removed on exit)"
echo

# ── Step 1: Proxy restart to clear Metal inactive pages ───────────────────────
# smoke_test_mlx.py calls mlx_lm generate / mlx_vlm generate as subprocesses,
# bypassing the proxy. Each subprocess loads a model into Metal then exits,
# leaving pages in the kernel "inactive" pool. These are NOT released by a
# simple proxy unload — only a fresh proxy process forces the VM pager to
# reclaim stale Metal allocations (same logic as UAT _restart_proxy_for_reclaim).
echo "=== Restarting MLX proxy to reclaim Metal inactive pages ==="

# 1. SIGTERM the proxy (graceful: proxy sends SIGTERM to mlx_lm/vlm server)
if launchctl list com.portal5.mlx-proxy &>/dev/null 2>&1; then
    launchctl stop com.portal5.mlx-proxy 2>/dev/null || true
    echo "  Proxy stopped via launchd."
elif pgrep -f "mlx-proxy.py" &>/dev/null 2>&1; then
    pkill -TERM -f "mlx-proxy.py" 2>/dev/null || true
    echo "  Proxy SIGTERM sent."
fi
sleep 5

# 2. SIGTERM any residual mlx server processes
pkill -TERM -f "mlx_lm.server" 2>/dev/null || true
pkill -TERM -f "mlx_vlm.server" 2>/dev/null || true
sleep 5

# 3. Start fresh proxy (new process → VM pager releases stale Metal pages)
if launchctl list com.portal5.mlx-proxy &>/dev/null 2>&1; then
    launchctl start com.portal5.mlx-proxy 2>/dev/null || true
    echo "  Fresh proxy started via launchd."
elif [ -f "$HOME/.portal5/mlx/mlx-proxy.py" ]; then
    python3 "$HOME/.portal5/mlx/mlx-proxy.py" \
        > "$HOME/.portal5/logs/mlx-proxy.log" 2>&1 &
    echo "  Fresh proxy started (PID $!)."
fi

# 4. Wait 60s for proxy MemoryMonitor to complete first sample (mirrors UAT driver)
echo "  Waiting 60s for proxy + Metal to stabilize..."
sleep 60

# 5. Verify proxy is up and free_gb >= 4
echo -n "  Proxy health check: "
proxy_check=$(python3 -c "
import urllib.request, json, sys
try:
    resp = urllib.request.urlopen('http://localhost:8081/health/wired', timeout=5)
    d = json.load(resp)
    free = d.get('free_gb', 0)
    inactive = d.get('inactive_gb', 0)
    state = d.get('state', 'err')
    print(f'state={state} free={free:.1f}GB inactive={inactive:.1f}GB')
    sys.exit(0 if free >= 4 else 1)
except Exception as e:
    print(f'unreachable ({e})')
    sys.exit(2)
" 2>&1 || true)

if echo "$proxy_check" | grep -q "state="; then
    echo "$proxy_check"
    if ! echo "$proxy_check" | grep -qE "free=[4-9][0-9]*\.|free=[1-9][0-9]+\."; then
        echo "  WARNING: free_gb < 4 — bench may fail on large models. Continuing anyway."
    fi
else
    echo "$proxy_check"
    echo "  WARNING: proxy not reachable — bench will attempt anyway (proxy may start on first request)."
fi
echo

OUTPUT="tests/benchmarks/results/bench_tps_v5_ladders.json"

# ── Step 2: Bench each smoke-PASSed model through proxy memory cycle ──────────
# bench_tps.py's load→test→evict→reclaim→cooldown cycle runs one model at a
# time through the proxy's admission gates. Each invocation exits with Metal
# fully reclaimed (canary push + poll), so the next model starts from a clean
# state. Resume support skips models with runs_success>0 (already succeeded).
echo "=== Benching V5 smoke-passed candidates (one model at a time) ==="
TOTAL=$(echo "$PASSED_MODELS" | grep -c . || true)
I=0
while IFS= read -r model_id; do
    [ -z "$model_id" ] && continue
    I=$((I + 1))
    echo ""
    echo "--- [$I/$TOTAL] $model_id ---"
    python3 tests/benchmarks/bench_tps.py \
        --mode direct \
        --runs 5 \
        --cooldown 10 \
        --order size \
        --model "$model_id" \
        --output "$OUTPUT"
done <<< "$PASSED_MODELS"

echo
echo "=== Bench complete. Results: $OUTPUT ==="
echo "Run: python3 scripts/analyze_bench_v5.py"
