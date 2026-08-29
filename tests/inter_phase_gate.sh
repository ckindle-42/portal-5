#!/bin/bash
# inter_phase_gate.sh — hard gate between UAT phases (Ollama-only)
# Sleeps/recovers until system safe; exits 0 on PASS, exits 1 on UNRECOVERABLE.
# Usage: bash tests/inter_phase_gate.sh <phase_num> <phase_test_count>
#
# OLLAMA-ONLY (rewritten after MLX inference-proxy retirement, commit 3a0c58e).
# Chat inference runs entirely through Ollama (:11434). The memory gate reclaims
# unified memory by evicting Ollama models (/api/ps + keep_alive:0) and reading
# pressure from vm_stat — no MLX proxy, no /health/wired, no mlx_lm/mlx_vlm servers.
# Retained MLX services (mlx-speech :8918, mflux :8933, video-mlx :8935) are
# detected only as memory-pressure sources, never killed.

set -euo pipefail
PHASE_NUM="${1:?usage: $0 <phase_num> <phase_test_count>}"
PHASE_TESTS="${2:?usage: $0 <phase_num> <phase_test_count>}"
ELAPSED=0  # accumulated wait time, credited against the 600s memory cap
FAIL_BEFORE=$(grep -c '| FAIL |' tests/UAT_RESULTS.md 2>/dev/null || true); FAIL_BEFORE=${FAIL_BEFORE:-0}
PASS_BEFORE=$(grep -c '| PASS |' tests/UAT_RESULTS.md 2>/dev/null || true); PASS_BEFORE=${PASS_BEFORE:-0}
WARN_BEFORE=$(grep -c '| WARN |' tests/UAT_RESULTS.md 2>/dev/null || true); WARN_BEFORE=${WARN_BEFORE:-0}

# ---- Top-level utilities ----

# Ollama direct eviction via /api/ps + keep_alive:0. Called from the memory gate.
_evict_ollama_direct() {
    local loaded_count
    loaded_count=$(curl -s --max-time 5 http://localhost:11434/api/ps 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('models',[])))" 2>/dev/null || echo 0)
    if [ "$loaded_count" -gt 0 ]; then
        echo "[GATE:$PHASE_NUM]       Ollama has ${loaded_count} model(s) loaded — evicting directly..."
        curl -s --max-time 5 http://localhost:11434/api/ps 2>/dev/null | python3 -c "
import sys,json,httpx
models = json.load(sys.stdin).get('models',[])
for m in models:
    name = m.get('name','')
    print(f'         unloading: {name}')
    try:
        r = httpx.post('http://localhost:11434/api/generate', json={'model': name, 'keep_alive': 0}, timeout=10)
        print(f'         -> {name}: done' if r.status_code == 200 else f'         -> {name}: HTTP {r.status_code}')
    except Exception as e:
        print(f'         -> {name}: error {e}')
" 2>/dev/null || echo "[GATE:$PHASE_NUM]       Ollama direct eviction failed (API error)"
        sleep 5
    fi
}

# Unified-memory snapshot from vm_stat. Echoes "used_pct free_gb wired_gb inactive_gb".
_mem_snapshot() {
    vm_stat 2>/dev/null | python3 -c "
import sys
free=active=inactive=spec=wired=0
for line in sys.stdin:
    if 'Pages free:' in line: free=int(line.split(':')[1].strip().rstrip('.'))
    elif 'Pages active:' in line: active=int(line.split(':')[1].strip().rstrip('.'))
    elif 'Pages inactive:' in line: inactive=int(line.split(':')[1].strip().rstrip('.'))
    elif 'Pages speculative:' in line: spec=int(line.split(':')[1].strip().rstrip('.'))
    elif 'Pages wired down:' in line: wired=int(line.split(':')[1].strip().rstrip('.'))
pg=16384  # M-series page size
total=free+active+inactive+spec+wired
used_pct=round((active+wired+spec)/total*100,1) if total else 99.0
to_gb=lambda p:round(p*pg/1024/1024/1024,1)
print(f'{used_pct} {to_gb(free)} {to_gb(wired)} {to_gb(inactive)}')
" 2>/dev/null || echo "99.0 0 99 99"
}

_ollama_loaded_count() {
    curl -s --max-time 5 http://localhost:11434/api/ps 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('models',[])))" 2>/dev/null || echo 0
}

# ---- Gate 1: pipeline health (auto-restart attempt before hard stop) ----
if ! curl -sf --max-time 5 http://localhost:9099/health > /dev/null; then
    echo "[GATE:$PHASE_NUM] Pipeline DOWN — attempting Docker restart (one attempt)..."
    docker restart portal5-pipeline 2>/dev/null || true
    echo "[GATE:$PHASE_NUM] Waiting 30s for pipeline to come up..."
    sleep 30
    if ! curl -sf --max-time 5 http://localhost:9099/health > /dev/null; then
        echo "[GATE:$PHASE_NUM] FATAL: pipeline still DOWN after restart — cannot proceed."
        echo "| $PHASE_NUM. gate | BLOCKED | $(date -u +%H:%MZ) | — | — | — | pipeline DOWN (restart failed) |" >> tests/UAT_RUN_LOG.md
        exit 1
    fi
    echo "[GATE:$PHASE_NUM] Pipeline recovered after restart"
fi
echo "[GATE:$PHASE_NUM] Pipeline healthy"

# ---- Gate 2: Ollama health (unrecoverable after 3 attempts) ----
OLLAMA_OK=false
for attempt in 1 2 3; do
    if curl -sf --max-time 5 http://localhost:11434/api/tags > /dev/null 2>&1; then
        OLLAMA_OK=true
        break
    fi
    echo "[GATE:$PHASE_NUM] Ollama unreachable (attempt ${attempt}/3) — waiting 30s..."
    sleep 30
done
if [ "$OLLAMA_OK" != true ]; then
    echo "[GATE:$PHASE_NUM] FATAL: Ollama (:11434) DOWN after 3 attempts — cannot proceed."
    echo "| $PHASE_NUM. gate | BLOCKED | $(date -u +%H:%MZ) | — | — | — | Ollama DOWN (3 attempts) |" >> tests/UAT_RUN_LOG.md
    exit 1
fi
echo "[GATE:$PHASE_NUM] Ollama healthy"

# ---- Gate 2.5: detect OTHER memory-pressure sources (retained MLX services) ----
# These share the unified-memory pool. The MLX image/video MCPs (mflux :8933,
# video-mlx :8935) are launchd-supervised and release memory between jobs — only
# reported here, never killed. Retained MLX audio (mlx-speech) likewise.
PRESSURE_SOURCES=""
SPEECH_PID=$(pgrep -f "mlx-speech" 2>/dev/null | head -1 || true)
if [ -n "$SPEECH_PID" ]; then
    PRESSURE_SOURCES="$PRESSURE_SOURCES mlx-speech(PID=$SPEECH_PID,retained)"
fi
if [ -n "$PRESSURE_SOURCES" ]; then
    echo "[GATE:$PHASE_NUM] Memory-pressure sources (not killed):$PRESSURE_SOURCES"
fi

# ---- Gate 3: unified memory MUST come down (THE KEY GATE) ----
# Blocks until used_pct < 80% AND no Ollama model is resident, or 600s pass.
# Recovery: evict Ollama models (/api/ps keep_alive:0). Unlike the old MLX gate
# there is no proxy to restart and no mlx_lm/mlx_vlm servers to kill — Ollama owns
# its own memory and releases it on keep_alive:0.
MEM_CAP_S=600
UNLOAD_COUNT=0
read -r USED_PCT FREE_GB WIRED_GB INACTIVE_GB <<< "$(_mem_snapshot)"
while :; do
    LOADED=$(_ollama_loaded_count)
    read -r USED_PCT FREE_GB WIRED_GB INACTIVE_GB <<< "$(_mem_snapshot)"
    echo "  [GATE:$PHASE_NUM +${ELAPSED}s] used=${USED_PCT}% free=${FREE_GB}GB wired=${WIRED_GB}GB inactive=${INACTIVE_GB}GB ollama_loaded=${LOADED}"

    # Safe condition: low pressure AND nothing resident in Ollama.
    if python3 -c "import sys; sys.exit(0 if float('${USED_PCT}') < 80.0 else 1)" && [ "$LOADED" -eq 0 ]; then
        echo "[GATE:$PHASE_NUM] Memory safe (used=${USED_PCT}% < 80%, ollama_loaded=0) after ${ELAPSED}s"
        break
    fi

    if [ "$ELAPSED" -ge "$MEM_CAP_S" ]; then
        echo "[GATE:$PHASE_NUM] WARNING: memory cap (${MEM_CAP_S}s) reached at used=${USED_PCT}% loaded=${LOADED} — proceeding with caution"
        echo "| $PHASE_NUM. gate | WARN | $(date -u +%H:%MZ) | — | — | — | mem cap: used=${USED_PCT}% loaded=${LOADED} |" >> tests/UAT_RUN_LOG.md
        break
    fi

    # Recovery: evict resident Ollama models, then wait for the pager to settle.
    if [ "$LOADED" -gt 0 ]; then
        echo "[GATE:$PHASE_NUM]  --> ${LOADED} Ollama model(s) resident — evicting (attempt $((UNLOAD_COUNT+1)))"
        _evict_ollama_direct
        UNLOAD_COUNT=$((UNLOAD_COUNT+1))
    else
        echo "[GATE:$PHASE_NUM]  --> no model resident but used=${USED_PCT}% — waiting for VM pager to reclaim"
    fi
    sleep 15
    ELAPSED=$((ELAPSED+15))
done

# ---- Gate 4: FAIL delta check ----
FAIL_AFTER=$(grep -c '| FAIL |' tests/UAT_RESULTS.md 2>/dev/null || true); FAIL_AFTER=${FAIL_AFTER:-0}
FAIL_DELTA=$((FAIL_AFTER - FAIL_BEFORE))
FAIL_PCT=0
if [ "$PHASE_TESTS" -gt 0 ]; then
    FAIL_PCT=$((FAIL_DELTA * 100 / PHASE_TESTS))
fi
echo "[GATE:$PHASE_NUM] FAIL delta: +${FAIL_DELTA}/${PHASE_TESTS} (${FAIL_PCT}%)"
if [ "$FAIL_PCT" -gt 30 ] && [ "$PHASE_TESTS" -gt 3 ]; then
    echo "[GATE:$PHASE_NUM] WARNING: >30% of phase tests FAILED — investigate before proceeding."
    echo "[GATE:$PHASE_NUM] Check tests/UAT_RESULTS.md for the new FAIL rows."
    echo "[GATE:$PHASE_NUM] Common cause: memory pressure causing empty responses (check used% above)."
    echo "[GATE:$PHASE_NUM] If FAILs are all empty-response cascades, proceed. If behavioral, pause and diagnose."
    echo "| $PHASE_NUM. gate | WARN | $(date -u +%H:%MZ) | — | — | — | FAIL delta ${FAIL_PCT}% (${FAIL_DELTA}/${PHASE_TESTS}) |" >> tests/UAT_RUN_LOG.md
fi

echo ""
echo "============================================"
echo " GATE $PHASE_NUM PASSED — safe to proceed"
echo " Cumulative: $(grep -c '| PASS |' tests/UAT_RESULTS.md)P / $(grep -c '| WARN |' tests/UAT_RESULTS.md)W / $(grep -c '| FAIL |' tests/UAT_RESULTS.md)F"
echo " Used: ${USED_PCT}%  Free: ${FREE_GB}GB  Wired: ${WIRED_GB}GB  Inactive: ${INACTIVE_GB}GB  Ollama_loaded: $(_ollama_loaded_count)"
echo "============================================"
