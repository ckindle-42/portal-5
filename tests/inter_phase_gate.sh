#!/bin/bash
# inter_phase_gate.sh — hard gate between UAT phases
# Sleeps/recovers until system safe; exits 0 on PASS, exits 1 on UNRECOVERABLE.
# Usage: bash tests/inter_phase_gate.sh <phase_num> <phase_test_count> [--keep-comfyui]
#   --keep-comfyui: don't kill ComfyUI even if memory is tight (use before Phase 6 media_heavy)

set -euo pipefail
PHASE_NUM="${1:?usage: $0 <phase_num> <phase_test_count> [--keep-comfyui]}"
PHASE_TESTS="${2:?usage: $0 <phase_num> <phase_test_count> [--keep-comfyui]}"
KEEP_COMFYUI=false
if [ "${3:-}" = "--keep-comfyui" ]; then
    KEEP_COMFYUI=true
fi
ELAPSED=0  # accumulated wait time across all gates, credited against 600s memory cap
FAIL_BEFORE=$(grep -c '| FAIL |' tests/UAT_RESULTS.md 2>/dev/null || echo 0)
PASS_BEFORE=$(grep -c '| PASS |' tests/UAT_RESULTS.md 2>/dev/null || echo 0)
WARN_BEFORE=$(grep -c '| WARN |' tests/UAT_RESULTS.md 2>/dev/null || echo 0)

# ---- Top-level utilities (must be defined before use) ----

# Ollama direct eviction. Proxy /unload?ollama=true sometimes reports success but
# models stay loaded (seen in Phase 5/6 start logs with retries). This hits
# Ollama's own API directly and is called from multiple gate levels.
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

# ---- Gate 1: pipeline health (unrecoverable) ----
if ! curl -sf --max-time 5 http://localhost:9099/health > /dev/null; then
    echo "[GATE:$PHASE_NUM] FATAL: pipeline DOWN — cannot proceed. Fix and re-run gate."
    echo "| $PHASE_NUM. gate | BLOCKED | $(date -u +%H:%MZ) | — | — | — | pipeline DOWN |" >> tests/UAT_RUN_LOG.md
    exit 1
fi
echo "[GATE:$PHASE_NUM] Pipeline healthy"

# ---- Gate 2: proxy health (unrecoverable after 3 attempts) ----
PROXY_DOWN_COUNT=0
while true; do
    PROXY_RESP=$(curl -s --max-time 5 http://localhost:8081/health 2>/dev/null || echo '{"state":"down"}')
    PROXY_STATE=$(echo "$PROXY_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state','down'))" 2>/dev/null || echo "down")
    if [ "$PROXY_STATE" = "down" ]; then
        PROXY_DOWN_COUNT=$((PROXY_DOWN_COUNT + 1))
        if [ $PROXY_DOWN_COUNT -ge 3 ]; then
            echo "[GATE:$PHASE_NUM] FATAL: MLX proxy DOWN after 3 attempts — cannot proceed."
            echo "| $PHASE_NUM. gate | BLOCKED | $(date -u +%H:%MZ) | — | — | — | proxy DOWN (3 attempts) |" >> tests/UAT_RUN_LOG.md
            exit 1
        fi
        echo "[GATE:$PHASE_NUM] Proxy DOWN (attempt $PROXY_DOWN_COUNT/3) — waiting 30s..."
        sleep 30
    else
        break
    fi
done
echo "[GATE:$PHASE_NUM] Proxy healthy (state=$PROXY_STATE)"

# ---- Gate 2.5: detect OTHER memory pressure sources (ComfyUI, Ollama, embedding, speech) ----
# These run host-native outside Docker and compete for the same unified memory pool.
# The Gate 3 recovery ladder only touches MLX. If ComfyUI is loaded with FLUX (12-22GB),
# the gate will never reach wired < 12 and must warn/act on this source specifically.
echo "[GATE:$PHASE_NUM] Scanning for non-MLX memory pressure sources..."

COMFY_PID=$(pgrep -f "ComfyUI/main.py" 2>/dev/null | head -1 || true)
COMFY_PORT_UP=false
curl -sf --max-time 3 http://localhost:8188/ > /dev/null 2>&1 && COMFY_PORT_UP=true || true

OLLAMA_MODELS=$(curl -s --max-time 5 http://localhost:11434/api/ps 2>/dev/null | python3 -c "import sys,json; models=json.load(sys.stdin).get('models',[]); print(len(models))" 2>/dev/null || echo 0)
EMBED_PID=$(pgrep -f "embedding-server" 2>/dev/null | head -1 || true)
SPEECH_PID=$(pgrep -f "mlx-speech" 2>/dev/null | head -1 || true)

PRESSURE_SOURCES=""
if [ -n "$COMFY_PID" ] || [ "$COMFY_PORT_UP" = "true" ]; then
    COMFY_RSS_GB=0
    if [ -n "$COMFY_PID" ]; then
        COMFY_RSS_KB=$(ps -p "$COMFY_PID" -o rss= 2>/dev/null | tr -d ' ' || echo 0)
        COMFY_RSS_GB=$((COMFY_RSS_KB / 1024 / 1024))
    fi
    PRESSURE_SOURCES="$PRESSURE_SOURCES ComfyUI(~${COMFY_RSS_GB}GB_RSS)"

    if [ "$KEEP_COMFYUI" = "true" ]; then
        echo "[GATE:$PHASE_NUM] ComfyUI running (PID=$COMFY_PID, RSS~${COMFY_RSS_GB}GB) — keeping (--keep-comfyui)"
        echo "[GATE:$PHASE_NUM] Expect elevated wired memory. Media-heavy tests need ComfyUI."
    else
        echo "[GATE:$PHASE_NUM] ComfyUI running (PID=$COMFY_PID, RSS~${COMFY_RSS_GB}GB) — phase doesn't need it, unloading GPU memory"
        echo "[GATE:$PHASE_NUM] ComfyUI shares the unified memory pool via MPS. Never kill -9 a Metal process —"
        echo "[GATE:$PHASE_NUM] the driver may not reclaim buffers. Use API unload first, SIGTERM second."
        # Step 1: Try ComfyUI API to free loaded model (preserves process, releases GPU)
        echo "[GATE:$PHASE_NUM]  --> Step 1: ComfyUI API /free to unload model (keeps process, frees Metal)..."
        COMFY_FREE_RESP=$(curl -s --max-time 10 -X POST http://localhost:8188/api/free 2>/dev/null || echo '{"error":"api unavailable"}')
        echo "[GATE:$PHASE_NUM]       API /free response: $(echo "$COMFY_FREE_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message',d.get('error','?')))" 2>/dev/null || echo 'parse error')"
        sleep 10
        ELAPSED=$((ELAPSED + 10))
        # Step 2: SIGTERM for graceful Metal cleanup (process releases its own buffers)
        if [ -n "$COMFY_PID" ] && kill -0 "$COMFY_PID" 2>/dev/null; then
            echo "[GATE:$PHASE_NUM]  --> Step 2: SIGTERM to ComfyUI (graceful Metal cleanup)..."
            kill -TERM "$COMFY_PID" 2>/dev/null || true
            for i in $(seq 1 6); do
                sleep 5
                kill -0 "$COMFY_PID" 2>/dev/null || break
            done
            ELAPSED=$((ELAPSED + 30))
            # Step 3: Only if SIGTERM failed, try SIGKILL (risk of unreclaimable Metal)
            if kill -0 "$COMFY_PID" 2>/dev/null; then
                echo "[GATE:$PHASE_NUM]  --> Step 3: SIGTERM didn't work — SIGKILL as last resort (Metal may leak)"
                echo "[GATE:$PHASE_NUM]       If wired memory stays elevated, Metal buffer leak is likely. Reboot needed."
                kill -9 "$COMFY_PID" 2>/dev/null || true
                sleep 5
            fi
        fi
        pkill -f "ComfyUI" 2>/dev/null || true
        echo "[GATE:$PHASE_NUM] ComfyUI shutdown complete. Waiting 30s for Metal buffer release..."
        sleep 30
        ELAPSED=$((ELAPSED + 30))
    fi
fi
if [ "$OLLAMA_MODELS" -gt 0 ]; then
    PRESSURE_SOURCES="$PRESSURE_SOURCES Ollama(${OLLAMA_MODELS}_models)"
    echo "[GATE:$PHASE_NUM] Ollama has ${OLLAMA_MODELS} model(s) loaded — evicting (fast reload, frees Metal)"
    _evict_ollama_direct
fi
if [ -n "$EMBED_PID" ]; then
    PRESSURE_SOURCES="$PRESSURE_SOURCES Embedding(PID=$EMBED_PID)"
    echo "[GATE:$PHASE_NUM] Embedding server running (PID=$EMBED_PID)"
fi
if [ -n "$SPEECH_PID" ]; then
    PRESSURE_SOURCES="$PRESSURE_SOURCES MLX-Speech(PID=$SPEECH_PID)"
    echo "[GATE:$PHASE_NUM] MLX Speech server running (PID=$SPEECH_PID)"
fi

if [ -n "$PRESSURE_SOURCES" ]; then
    echo "[GATE:$PHASE_NUM] Non-MLX memory consumers detected:$PRESSURE_SOURCES"
    echo "[GATE:$PHASE_NUM] These share the unified memory pool with MLX."
    if [ "$KEEP_COMFYUI" != "true" ]; then
        echo "[GATE:$PHASE_NUM] ComfyUI was auto-killed above. Remaining sources should be small."
    fi
else
    echo "[GATE:$PHASE_NUM] No non-MLX memory pressure sources detected"
fi

# ---- Gate 3: wired memory MUST come down (THE KEY GATE) ----
# This gate blocks until wired_gb < 12 or 10 minutes pass.
# Every polling cycle it prints a full snapshot so the operator can monitor in real time.
# The agent MUST NOT proceed to the next phase until this gate passes or times out.

MAX_WAIT_SEC=600
UNLOAD_COUNT=0
while [ $ELAPSED -lt $MAX_WAIT_SEC ]; do
    WIRED_RESP=$(curl -s --max-time 5 http://localhost:8081/health/wired 2>/dev/null || echo '{"wired_gb":99,"free_gb":0,"state":"?"}')
    WIRED_GB=$(echo "$WIRED_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('wired_gb',99))" 2>/dev/null || echo 99)
    FREE_GB=$(echo "$WIRED_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('free_gb',0))" 2>/dev/null || echo 0)
    STATE=$(echo "$WIRED_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state','?'))" 2>/dev/null || echo "?")
    LOADED=$(echo "$WIRED_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('loaded_model','-'))" 2>/dev/null || echo "-")
    ACTIVE_GB=$(echo "$WIRED_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('active_gb','?'))" 2>/dev/null || echo "?")

    # Real-time snapshot for operator monitoring
    echo "  [GATE:$PHASE_NUM +${ELAPSED}s] wired=${WIRED_GB}GB free=${FREE_GB}GB active=${ACTIVE_GB}GB state=${STATE} model=${LOADED}"

    if [ "$(echo "$WIRED_GB < 12" | bc -l 2>/dev/null || echo 0)" = "1" ]; then
        echo "[GATE:$PHASE_NUM] Memory safe (wired=${WIRED_GB}GB < 12GB) after ${ELAPSED}s"
        break
    fi

    # ---- Recovery escalation ladder ----
    # Level 0: model loaded? /unload it.
    # Level 1: state=none but wired high? /unload to force Metal reclaim.
    # Level 2: /unload returned freed=0 three times? Kill orphaned mlx servers holding GPU buffers.
    # Level 3: wired still >30 after killing orphans? Restart the proxy (cleanest reclaim).

    if [ "$STATE" = "ready" ] && [ "$LOADED" != "-" ] && [ "$LOADED" != "null" ]; then
        # Level 0: normal eviction
        echo "[GATE:$PHASE_NUM]  --> Level 0: state=ready with ${LOADED} — /unload"
        curl -s -X POST 'http://localhost:8081/unload?ollama=true' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'       result: wired {d.get(\"wired_before_gb\",\"?\")}->{d.get(\"wired_after_gb\",\"?\")}GB freed={d.get(\"wired_freed_gb\",\"?\")}GB ollama_evicted={d.get(\"ollama_evicted\",\"?\")}')" 2>/dev/null || echo "       request sent"
        # Also directly evict any Ollama models (proxy /unload?ollama=true sometimes fails)
        _evict_ollama_direct
        sleep 10
        ELAPSED=$((ELAPSED + 10))

    elif [ "$STATE" = "none" ] && [ "$UNLOAD_COUNT" -lt 3 ]; then
        # Level 1: force-reclaim Metal buffers
        echo "[GATE:$PHASE_NUM]  --> Level 1: state=none, wired=${WIRED_GB}GB — /unload to force reclaim ($((UNLOAD_COUNT+1))/3)"
        BEFORE=$WIRED_GB
        curl -s -X POST 'http://localhost:8081/unload?ollama=true' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'       result: wired {d.get(\"wired_before_gb\",\"?\")}->{d.get(\"wired_after_gb\",\"?\")}GB freed={d.get(\"wired_freed_gb\",\"?\")}GB')" 2>/dev/null || echo "       request sent"
        _evict_ollama_direct
        UNLOAD_COUNT=$((UNLOAD_COUNT + 1))

    elif [ "$STATE" = "none" ] && [ "$UNLOAD_COUNT" -ge 3 ] && [ "$UNLOAD_COUNT" -lt 5 ]; then
        # Level 2: /unload returned freed=0 three times — kill orphaned mlx servers
        # IMPORTANT: Never kill -9 a Metal process without trying SIGTERM first.
        # Metal GPU driver can't reclaim buffers from a force-killed process.
        # SIGTERM allows mlx_lm.server to run its own cleanup.
        ORPHANS=$(pgrep -f "mlx_lm.server|mlx_vlm.server" 2>/dev/null || true)
        if [ -n "$ORPHANS" ]; then
            echo "[GATE:$PHASE_NUM]  --> Level 2: /unload freed 0GB 3x — orphaned mlx servers: $ORPHANS"
            for pid in $ORPHANS; do
                CMD=$(ps -p $pid -o comm= 2>/dev/null || echo '?')
                echo "[GATE:$PHASE_NUM]       SIGTERM to $CMD (PID=$pid) — graceful Metal cleanup..."
                kill -TERM "$pid" 2>/dev/null || true
            done
            sleep 5
            # Check if they're still alive after SIGTERM
            STILL_ALIVE=$(pgrep -f "mlx_lm.server|mlx_vlm.server" 2>/dev/null || true)
            if [ -n "$STILL_ALIVE" ]; then
                echo "[GATE:$PHASE_NUM]       Servers survived SIGTERM — SIGKILL (risk: Metal may leak)"
                for pid in $STILL_ALIVE; do
                    kill -9 "$pid" 2>/dev/null || true
                done
            else
                echo "[GATE:$PHASE_NUM]       Servers shut down gracefully via SIGTERM"
            fi
            echo "[GATE:$PHASE_NUM]       Waiting 30s for Metal buffer release..."
            sleep 30
            ELAPSED=$((ELAPSED + 35))
            UNLOAD_COUNT=$((UNLOAD_COUNT + 1))
        else
            echo "[GATE:$PHASE_NUM]  --> Level 2: no orphaned mlx servers found — escalating to Level 3"
            UNLOAD_COUNT=5
        fi

    elif [ "$STATE" = "none" ] && [ "$UNLOAD_COUNT" -ge 5 ]; then
        # Level 3: restart the MLX proxy (cleanest Metal reclaim)
        # SIGTERM first — proxy handles graceful shutdown of child mlx servers.
        # SIGKILL only if SIGTERM fails, and only after logging the Metal leak risk.
        PROXY_PID=$(pgrep -f "mlx-proxy.py" 2>/dev/null || true)
        if [ -n "$PROXY_PID" ]; then
            echo "[GATE:$PHASE_NUM]  --> Level 3: wired=${WIRED_GB}GB after Level 0-2 — restarting MLX proxy"
            echo "[GATE:$PHASE_NUM]       SIGTERM to proxy (PID=$PROXY_PID) — allows graceful child cleanup..."
            kill -TERM "$PROXY_PID" 2>/dev/null || true
            sleep 10
            # Kill any remaining children after proxy down
            for pid in $(pgrep -f "mlx_lm.server|mlx_vlm.server" 2>/dev/null || true); do
                echo "[GATE:$PHASE_NUM]       SIGTERM to lingering child $pid..."
                kill -TERM "$pid" 2>/dev/null || true
            done
            sleep 5
            # Only SIGKILL if still alive
            for pid in $(pgrep -f "mlx_lm.server|mlx_vlm.server|mlx-proxy.py" 2>/dev/null || true); do
                echo "[GATE:$PHASE_NUM]       SIGKILL $pid (last resort — Metal may leak)"
                kill -9 "$pid" 2>/dev/null || true
            done
            # Restart from deployed copy
            echo "[GATE:$PHASE_NUM]       Restarting proxy from ~/.portal5/mlx/mlx-proxy.py..."
            nohup python3 ~/.portal5/mlx/mlx-proxy.py > /tmp/mlx-proxy-restart.log 2>&1 &
            echo "[GATE:$PHASE_NUM]       Proxy restarted (PID=$!). Waiting 45s for startup..."
            sleep 45
            ELAPSED=$((ELAPSED + 60))
            UNLOAD_COUNT=99
        else
            echo "[GATE:$PHASE_NUM]  --> Level 3: no proxy PID found — cannot restart"
            UNLOAD_COUNT=99
        fi

    elif [ "$STATE" != "none" ] && [ "$STATE" != "ready" ]; then
        echo "[GATE:$PHASE_NUM]  --> Wait: proxy in transition (${STATE}) — allowing settle time"
    else
        echo "[GATE:$PHASE_NUM]  --> Wait: recovering (unload=${UNLOAD_COUNT}, state=${STATE})"
    fi

    sleep 30
    ELAPSED=$((ELAPSED + 30))
done

if [ "$(echo "$WIRED_GB < 12" | bc -l 2>/dev/null || echo 0)" != "1" ]; then
    echo "[GATE:$PHASE_NUM] Memory gate timed out after ${MAX_WAIT_SEC}s (wired=${WIRED_GB}GB)."
    echo "[GATE:$PHASE_NUM] WARNING: proceeding with elevated memory — expect potential empty responses."
    echo "| $PHASE_NUM. gate | WARN | $(date -u +%H:%MZ) | — | — | — | wired=${WIRED_GB}GB after ${MAX_WAIT_SEC}s timeout |" >> tests/UAT_RUN_LOG.md
else
    echo "| $PHASE_NUM. gate | PASS | $(date -u +%H:%MZ) | $(date -u +%H:%MZ) | — | — | wired=${WIRED_GB}GB after ${ELAPSED}s |" >> tests/UAT_RUN_LOG.md
fi

# ---- Gate 4: FAIL delta check ----
FAIL_AFTER=$(grep -c '| FAIL |' tests/UAT_RESULTS.md 2>/dev/null || echo 0)
FAIL_DELTA=$((FAIL_AFTER - FAIL_BEFORE))
FAIL_PCT=0
if [ "$PHASE_TESTS" -gt 0 ]; then
    FAIL_PCT=$((FAIL_DELTA * 100 / PHASE_TESTS))
fi
echo "[GATE:$PHASE_NUM] FAIL delta: +${FAIL_DELTA}/${PHASE_TESTS} (${FAIL_PCT}%)"
if [ "$FAIL_PCT" -gt 30 ] && [ "$PHASE_TESTS" -gt 3 ]; then
    echo "[GATE:$PHASE_NUM] WARNING: >30% of phase tests FAILED — investigate before proceeding."
    echo "[GATE:$PHASE_NUM] Check tests/UAT_RESULTS.md for the new FAIL rows."
    echo "[GATE:$PHASE_NUM] Common cause: memory pressure causing empty responses (check wired_gb above)."
    echo "[GATE:$PHASE_NUM] If FAILs are all empty-response cascades, proceed. If behavioral, pause and diagnose."
    echo "| $PHASE_NUM. gate | WARN | $(date -u +%H:%MZ) | — | — | — | FAIL delta ${FAIL_PCT}% (${FAIL_DELTA}/${PHASE_TESTS}) |" >> tests/UAT_RUN_LOG.md
fi

echo ""
echo "============================================"
echo " GATE $PHASE_NUM PASSED — safe to proceed"
echo " Cumulative: $(grep -c '| PASS |' tests/UAT_RESULTS.md)P / $(grep -c '| WARN |' tests/UAT_RESULTS.md)W / $(grep -c '| FAIL |' tests/UAT_RESULTS.md)F"
echo " Wired: ${WIRED_GB}GB  Free: ${FREE_GB}GB  Proxy: ${PROXY_STATE}"
echo "============================================"
