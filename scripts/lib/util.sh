#!/usr/bin/env bash
# util.sh — Portal 5 utility functions (sourced by launch.sh)
# shellcheck shell=bash

# ── JSON parsing helper ────────────────────────────────────────────────────────
# Prefer jq (faster), fall back to python3 if unavailable.
if command -v jq &>/dev/null; then
    _USE_JQ=true
else
    _USE_JQ=false
fi

# Usage: _jq_get <json_string> <jq_filter> <python_fallback_expr> [default]
# Example: _jq_get "$JSON" '.status // "?"' "d.get('status','?')"
_json_get() {
    local json="$1" jq_filter="$2" py_expr="$3" default="${4:-}"
    if $_USE_JQ; then
        echo "$json" | jq -r "$jq_filter" 2>/dev/null || echo "${default}"
    else
        echo "$json" | python3 -c "import json,sys; d=json.load(sys.stdin); print($py_expr)" 2>/dev/null || echo "${default}"
    fi
}

# ── Secret generation ─────────────────────────────────────────────────────────
generate_secret() {
    # Works on macOS (LibreSSL) and Linux (OpenSSL)
    openssl rand -base64 32 | tr -d '/+=' | head -c 43
}

# ── Hardware check ──────────────────────────────────────────────────────────
_check_hardware() {
    echo "[portal-5] Checking system requirements..."
    WARN=0

    # RAM check (need ≥16GB, warn below 32GB for full model catalog)
    # Cross-platform: /proc/meminfo on Linux, sysctl on macOS
    RAM_GB=0
    if [ "$(uname -s)" = "Darwin" ]; then
        # macOS
        MEM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
        RAM_GB=$(( MEM_BYTES / 1024 / 1024 / 1024 ))
    elif [ -f /proc/meminfo ]; then
        # Linux
        MEM_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
        RAM_GB=$(( MEM_KB / 1024 / 1024 ))
    fi

    if [ "$RAM_GB" -lt 16 ] 2>/dev/null; then
        echo "  ⚠️  RAM: ${RAM_GB}GB detected — 16GB minimum required"
        echo "     Portal 5 may crash or fail to load models"
        WARN=1
    elif [ "$RAM_GB" -lt 32 ] 2>/dev/null; then
        echo "  ℹ️  RAM: ${RAM_GB}GB — enough for core models (32GB+ for full catalog)"
    elif [ "$RAM_GB" -gt 0 ]; then
        echo "  ✅ RAM: ${RAM_GB}GB"
    fi

    # Disk check (need ≥20GB free; FLUX alone is ~12GB)
    # Check root filesystem "/" - more reliable than current directory on macOS
    DISK_FREE=$(python3 -c "import shutil; print(shutil.disk_usage('/').free // 1024**3)" 2>/dev/null || \
                df -k / 2>/dev/null | tail -1 | awk '{printf "%d\n", $4/1024/1024}' || \
                echo 0)
    if [ "$DISK_FREE" -lt 20 ] 2>/dev/null; then
        echo "  ⚠️  Disk: ${DISK_FREE}GB free — 20GB minimum (FLUX model is 12GB)"
        echo "     Free up disk space before continuing: docker system prune -a"
        WARN=1
    elif [ "$DISK_FREE" -lt 50 ] 2>/dev/null; then
        echo "  ℹ️  Disk: ${DISK_FREE}GB free — enough for core stack (50GB+ for all models)"
    else
        echo "  ✅ Disk: ${DISK_FREE}GB free"
    fi

    # Docker check (with timeout — Docker Desktop can hang in zombie state)
    local _docker_ok=0
    if command -v timeout &>/dev/null; then
        timeout 5 docker info &>/dev/null && _docker_ok=1
    else
        # macOS has no `timeout` — use bash background process with kill
        ( docker info &>/dev/null ) & local _dpid=$!
        ( sleep 5 && kill -9 $_dpid &>/dev/null ) & local _kpid=$!
        wait $_dpid 2>/dev/null && _docker_ok=1
        kill -9 $_kpid 2>/dev/null; wait $_kpid 2>/dev/null || true
    fi
    if [ "$_docker_ok" -eq 1 ]; then
        echo "  ✅ Docker: running"
    else
        # Check if Docker process exists but is unresponsive (zombie/hung state)
        if pgrep -f "com.docker.backend|Docker.app" &>/dev/null; then
            echo "  ❌ Docker: process running but unresponsive (hung daemon)"
            echo ""
            echo "  This happens when Docker Desktop enters a zombie state."
            echo "  Fix: kill Docker and restart from /Applications"
            echo ""
            printf "  Kill hung Docker processes now? [y/N] "
            read -r confirm
            if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
                echo "  Killing Docker processes..."
                pkill -f "com.docker.backend" 2>/dev/null || true
                pkill -f "com.docker.driver.amd" 2>/dev/null || true
                pkill -f "com.docker.qemu" 2>/dev/null || true
                pkill -f "com.docker.hyperkit" 2>/dev/null || true
                pkill -f "com.docker.vmnetd" 2>/dev/null || true
                pkill -f "Docker.app" 2>/dev/null || true
                echo "  ✅ Docker processes killed."
                echo ""
                echo "  Now open Docker Desktop from /Applications and wait for it to start."
                echo "  Then run: ./launch.sh up"
                exit 1
            else
                echo "  Aborted. Restart Docker Desktop manually and retry."
                exit 1
            fi
        else
            echo "  ❌ Docker: not running — start Docker Desktop and retry"
            exit 1
        fi
    fi

    # Apple Silicon detection (helpful context)
    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        echo "  ✅ Platform: Apple Silicon — Metal acceleration available"
        if command -v ollama &>/dev/null && curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
            OLLAMA_VER=$(ollama --version 2>/dev/null | head -1 || echo "installed")
            echo "  ✅ Ollama: native ($OLLAMA_VER) — Metal GPU active"
        elif command -v ollama &>/dev/null; then
            echo "  ⚠️  Ollama installed but not running — start it: brew services start ollama"
            WARN=1
        else
            echo "  ⚠️  Ollama not installed — run: ./launch.sh install-ollama"
            WARN=1
        fi
        # Check native ComfyUI is running
        if curl -s http://localhost:8188/system_stats &>/dev/null 2>&1; then
            echo "  ✅ ComfyUI: native — Metal GPU active (:8188)"
        elif pgrep -f "ComfyUI/main.py|comfyui" &>/dev/null 2>&1; then
            echo "  ⏳ ComfyUI: starting in background (may take 30-60s)"
        else
            echo "  ℹ️  ComfyUI not running (image/video generation unavailable)"
            echo "     Install: ./launch.sh install-comfyui"
            echo "     Start:   ~/ComfyUI/start.sh"
        fi
    elif [ "$ARCH" = "x86_64" ]; then
        # Check for NVIDIA GPU
        if command -v nvidia-smi &>/dev/null && nvidia-smi -L &>/dev/null 2>&1; then
            GPU=$(nvidia-smi -L 2>/dev/null | head -1 | sed 's/GPU 0: //' | cut -d'(' -f1)
            echo "  ✅ GPU: $GPU (CUDA acceleration available)"
        else
            echo "  ℹ️  GPU: No NVIDIA GPU detected — CPU inference (slower)"
        fi
    fi

    if [ "$WARN" -eq 1 ]; then
        echo ""
        echo "[portal-5] ⚠️  System requirements warning — see above"
        echo "           Press Enter to continue anyway, or Ctrl+C to abort"
        read -r _
    fi
}

# ── Auto-start native services if installed but not running ─────────────────
_ensure_native_services() {
    local ARCH
    ARCH=$(uname -m)
    echo "[portal-5] Checking native services..."

    # ── Ollama ───────────────────────────────────────────────────────────────
    if command -v ollama &>/dev/null; then
        if ! curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
            echo "[portal-5]   Ollama installed but not running — starting..."
            if command -v brew &>/dev/null; then
                brew services start ollama &>/dev/null || true
            else
                # Linux: start as background process
                mkdir -p "$HOME/.portal5/logs"
                OLLAMA_MODELS="${OLLAMA_MODELS:-$HOME/.ollama/models}" nohup ollama serve > "$HOME/.portal5/logs/ollama.log" 2>&1 &
            fi
            # Wait up to 10s for Ollama to respond
            local retries=10
            while [ "$retries" -gt 0 ]; do
                sleep 1
                if curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
                    echo "[portal-5]   ✅ Ollama started"
                    break
                fi
                retries=$((retries - 1))
            done
            if [ "$retries" -eq 0 ]; then
                echo "[portal-5]   ⚠️  Ollama did not respond after 10s — check: brew services info ollama"
            fi
        else
            echo "[portal-5]   ✅ Ollama: running"
        fi
    fi

    # ── ComfyUI (Apple Silicon native only) ──────────────────────────────────
    if [ "$ARCH" = "arm64" ]; then
        local COMFYUI_DIR="${COMFYUI_DIR:-$HOME/ComfyUI}"
        if [ -f "$COMFYUI_DIR/start.sh" ]; then
            if ! curl -s http://localhost:8188/system_stats &>/dev/null 2>&1; then
                echo "[portal-5]   ComfyUI installed but not running — starting..."
                mkdir -p "$HOME/.portal5/logs"
                if launchctl list com.portal5.comfyui &>/dev/null 2>&1; then
                    launchctl start com.portal5.comfyui 2>>"$HOME/.portal5/logs/comfyui-launchctl.log" || true
                else
                    nohup "$COMFYUI_DIR/start.sh" \
                        > "$HOME/.portal5/logs/comfyui.log" 2>&1 &
                fi
                echo "[portal-5]   ⏳ ComfyUI starting in background (may take 30-60s)"
                echo "[portal-5]      Logs: $HOME/.portal5/logs/comfyui.log"
                echo "[portal-5]      UI:   http://localhost:8188"
            else
                echo "[portal-5]   ✅ ComfyUI: running"
            fi
        fi
    fi

    # ── Music MCP (native on macOS for MPS; skip on non-arm64) ──────────────
    if [ "$ARCH" = "arm64" ]; then
        local MUSIC_VENV="$HOME/.portal5/music/.venv"
        if [ -f "$MUSIC_VENV/bin/python" ]; then
            if ! curl -s "http://localhost:${MUSIC_HOST_PORT:-8912}/health" &>/dev/null 2>&1; then
                echo "[portal-5]   Music MCP installed but not running — starting..."
                mkdir -p "$HOME/.portal5/logs"
                if launchctl list com.portal5.music-mcp &>/dev/null 2>&1; then
                    launchctl start com.portal5.music-mcp 2>>"$HOME/.portal5/logs/music-mcp-launchctl.log" || true
                else
                    PYTHONPATH="$PORTAL_ROOT" \
                    HF_HOME="${HF_HOME:-$HOME/.portal5/music/hf_cache}" \
                    TRANSFORMERS_CACHE="${HF_HOME:-$HOME/.portal5/music/hf_cache}" \
                    OUTPUT_DIR="${AI_OUTPUT_DIR:-$HOME/AI_Output}" \
                    MUSIC_MCP_PORT="${MUSIC_HOST_PORT:-8912}" \
                    nohup "$MUSIC_VENV/bin/python" -m portal.modules.media.tools.music_mcp \
                        > "$HOME/.portal5/logs/music-mcp.log" 2>&1 &
                    echo $! > /tmp/music-mcp.pid
                fi
                echo "[portal-5]   ⏳ Music MCP starting on :${MUSIC_HOST_PORT:-8912}"
                echo "[portal-5]      Logs: $HOME/.portal5/logs/music-mcp.log"
            else
                echo "[portal-5]   ✅ Music MCP: running"
            fi
        fi
    fi

    # ── MLX Speech (Apple Silicon native only) ──────────────────────────────
    if [ "$ARCH" = "arm64" ]; then
        if python3 -c "import mlx_audio" &>/dev/null 2>&1; then
            local SPEECH_PID_FILE="/tmp/portal-mlx-speech.pid"
            local SPEECH_SCRIPT="$PORTAL_ROOT/scripts/mlx-speech.py"
            if [ -f "$SPEECH_PID_FILE" ] && kill -0 "$(cat "$SPEECH_PID_FILE")" 2>/dev/null; then
                echo "[portal-5]   ✅ MLX Speech: running (PID $(cat "$SPEECH_PID_FILE"))"
            elif [ -f "$SPEECH_SCRIPT" ]; then
                echo "[portal-5]   MLX Speech installed but not running — starting..."
                mkdir -p "$HOME/.portal5/logs"
                nohup python3 "$SPEECH_SCRIPT" \
                    >> "$HOME/.portal5/logs/mlx-speech.log" 2>&1 &
                echo $! > "$SPEECH_PID_FILE"
                echo "[portal-5]   ✅ MLX Speech started on :${MLX_SPEECH_PORT:-8918}"
            fi
        fi
    fi

    # ── MLX Transcribe (Apple Silicon native only) ───────────────────────────
    if [ "$ARCH" = "arm64" ]; then
        local TRANSCRIBE_PID_FILE="/tmp/portal-mlx-transcribe.pid"
        local TRANSCRIBE_SCRIPT="$PORTAL_ROOT/scripts/mlx-transcribe.py"
        if [ -f "$TRANSCRIBE_PID_FILE" ] && kill -0 "$(cat "$TRANSCRIBE_PID_FILE")" 2>/dev/null; then
            echo "[portal-5]   ✅ MLX Transcribe: running (PID $(cat "$TRANSCRIBE_PID_FILE"))"
        elif [ -f "$TRANSCRIBE_SCRIPT" ]; then
            echo "[portal-5]   MLX Transcribe not running — starting..."
            mkdir -p "$HOME/.portal5/logs"
            nohup python3 "$TRANSCRIBE_SCRIPT" \
                >> "$HOME/.portal5/logs/mlx-transcribe.log" 2>&1 &
            echo $! > "$TRANSCRIBE_PID_FILE"
            echo "[portal-5]   ✅ MLX Transcribe started on :${MLX_TRANSCRIBE_PORT:-8924}"
        fi
    fi

    # ── Pipeline MCP (host-native, :8928) ────────────────────────────────────
    # Exposes get_pipeline_status, list_workspaces, get_loaded_models,
    # explore_repository (FastContext subagent), and get_metrics_summary
    # to coding tools (Claude Code, opencode) via .mcp.json.
    local PIPELINE_MCP_PID_FILE="/tmp/portal-pipeline-mcp.pid"
    local PIPELINE_MCP_MODULE="portal.platform.mcp_host.pipeline_mcp"
    if [ -f "$PIPELINE_MCP_PID_FILE" ] && kill -0 "$(cat "$PIPELINE_MCP_PID_FILE")" 2>/dev/null; then
        echo "[portal-5]   ✅ Pipeline MCP: running (PID $(cat "$PIPELINE_MCP_PID_FILE"))"
    else
        echo "[portal-5]   Pipeline MCP not running — starting..."
        mkdir -p "$HOME/.portal5/logs"
        PIPELINE_API_KEY="${PIPELINE_API_KEY:-}" \
        PIPELINE_URL="${PIPELINE_URL:-http://localhost:9099}" \
        OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}" \
        PIPELINE_MCP_REPO_ROOT="$PORTAL_ROOT" \
        PIPELINE_MCP_PORT="${PIPELINE_MCP_PORT:-8928}" \
        nohup python3 -m "$PIPELINE_MCP_MODULE" \
            >> "$HOME/.portal5/logs/pipeline-mcp.log" 2>&1 &
        echo $! > "$PIPELINE_MCP_PID_FILE"
        echo "[portal-5]   ✅ Pipeline MCP started on :${PIPELINE_MCP_PORT:-8928}"
    fi

    # ── MITRE ATT&CK MCP (host-native, :8929) ────────────────────────────────
    # Reads tests/benchmarks/bench_security/siem/spl_detections.py via a
    # repo-relative sys.path hack — not packaged into Dockerfile.mcp, so this
    # must run against the host checkout rather than as a container.
    local MITRE_MCP_PID_FILE="/tmp/portal-mitre-mcp.pid"
    if [ -f "$MITRE_MCP_PID_FILE" ] && kill -0 "$(cat "$MITRE_MCP_PID_FILE")" 2>/dev/null; then
        echo "[portal-5]   ✅ MITRE MCP: running (PID $(cat "$MITRE_MCP_PID_FILE"))"
    else
        echo "[portal-5]   MITRE MCP not running — starting..."
        mkdir -p "$HOME/.portal5/logs"
        MITRE_MCP_PORT="${MITRE_MCP_PORT:-8929}" \
        nohup python3 -m portal.modules.security.tools.mitre_mcp \
            >> "$HOME/.portal5/logs/mitre-mcp.log" 2>&1 &
        echo $! > "$MITRE_MCP_PID_FILE"
        echo "[portal-5]   ✅ MITRE MCP started on :${MITRE_MCP_PORT:-8929}"
    fi

    # ── Detections MCP (host-native, :8932) ──────────────────────────────────
    # Same tests/benchmarks/ dependency as MITRE MCP above.
    local DETECTIONS_MCP_PID_FILE="/tmp/portal-detections-mcp.pid"
    if [ -f "$DETECTIONS_MCP_PID_FILE" ] && kill -0 "$(cat "$DETECTIONS_MCP_PID_FILE")" 2>/dev/null; then
        echo "[portal-5]   ✅ Detections MCP: running (PID $(cat "$DETECTIONS_MCP_PID_FILE"))"
    else
        echo "[portal-5]   Detections MCP not running — starting..."
        mkdir -p "$HOME/.portal5/logs"
        DETECTIONS_MCP_PORT="${DETECTIONS_MCP_PORT:-8932}" \
        nohup python3 -m portal.modules.security.tools.detections_mcp \
            >> "$HOME/.portal5/logs/detections-mcp.log" 2>&1 &
        echo $! > "$DETECTIONS_MCP_PID_FILE"
        echo "[portal-5]   ✅ Detections MCP started on :${DETECTIONS_MCP_PORT:-8932}"
    fi

    # ── Wiki MCP (host-native, :8931) ─────────────────────────────────────────
    # Reads portal_wiki/canonical/ via a repo-relative path and calls Ollama
    # directly for wiki_explain — not packaged into Dockerfile.mcp.
    local WIKI_MCP_PID_FILE="/tmp/portal-wiki-mcp.pid"
    if [ -f "$WIKI_MCP_PID_FILE" ] && kill -0 "$(cat "$WIKI_MCP_PID_FILE")" 2>/dev/null; then
        echo "[portal-5]   ✅ Wiki MCP: running (PID $(cat "$WIKI_MCP_PID_FILE"))"
    else
        echo "[portal-5]   Wiki MCP not running — starting..."
        mkdir -p "$HOME/.portal5/logs"
        OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}" \
        WIKI_MCP_PORT="${WIKI_MCP_PORT:-8931}" \
        nohup python3 -m portal_wiki.wiki_mcp \
            >> "$HOME/.portal5/logs/wiki-mcp.log" 2>&1 &
        echo $! > "$WIKI_MCP_PID_FILE"
        echo "[portal-5]   ✅ Wiki MCP started on :${WIKI_MCP_PORT:-8931}"
    fi
}

# ── Teardown helper (shared by 'down' and the pre-start phase of 'up') ────────
_do_down() {
    # ── Stop Docker stack ─────────────────────────────────────────────────
    cd "$COMPOSE_DIR"
    docker compose down
    echo "[portal-5] Docker stack stopped."

    # ── Stop native macOS services (ComfyUI, Music MCP, Speech) ──────────────
    # These run outside Docker and must be stopped explicitly.
    # Uses launchctl if the service is registered, falls back to pkill.
    if [ "$(uname -s)" = "Darwin" ]; then
        # ComfyUI (:8188)
        if launchctl list com.portal5.comfyui &>/dev/null 2>&1; then
            launchctl stop com.portal5.comfyui 2>/dev/null || true
            echo "[portal-5] ComfyUI service stopped (launchd)."
        elif pgrep -f "comfyui|ComfyUI|main.py.*comfy" &>/dev/null 2>&1; then
            pkill -f "comfyui|ComfyUI|main.py.*comfy" 2>/dev/null || true
            echo "[portal-5] ComfyUI process stopped (pkill)."
        else
            echo "[portal-5] ComfyUI: not running (nothing to stop)."
        fi

        # Music MCP (:8912)
        if launchctl list com.portal5.music-mcp &>/dev/null 2>&1; then
            launchctl stop com.portal5.music-mcp 2>/dev/null || true
            echo "[portal-5] Music MCP service stopped (launchd)."
        elif [ -f /tmp/music-mcp.pid ] && kill -0 "$(cat /tmp/music-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/music-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/music-mcp.pid
            echo "[portal-5] Music MCP process stopped."
        elif pgrep -f "music_mcp|music-mcp" &>/dev/null 2>&1; then
            pkill -f "music_mcp|music-mcp" 2>/dev/null || true
            echo "[portal-5] Music MCP process stopped (pkill)."
        else
            echo "[portal-5] Music MCP: not running (nothing to stop)."
        fi

        # MLX Speech (:8918)
        if [ -f /tmp/portal-mlx-speech.pid ] && kill -0 "$(cat /tmp/portal-mlx-speech.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-mlx-speech.pid)" 2>/dev/null || true
            rm -f /tmp/portal-mlx-speech.pid
            echo "[portal-5] MLX Speech stopped."
        else
            echo "[portal-5] MLX Speech: not running (nothing to stop)."
        fi

        # MLX Transcribe (:8924)
        if [ -f /tmp/portal-mlx-transcribe.pid ] && kill -0 "$(cat /tmp/portal-mlx-transcribe.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-mlx-transcribe.pid)" 2>/dev/null || true
            rm -f /tmp/portal-mlx-transcribe.pid
            echo "[portal-5] MLX Transcribe stopped."
        else
            echo "[portal-5] MLX Transcribe: not running (nothing to stop)."
        fi

        # Pipeline MCP (:8928)
        if [ -f /tmp/portal-pipeline-mcp.pid ] && kill -0 "$(cat /tmp/portal-pipeline-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-pipeline-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-pipeline-mcp.pid
            echo "[portal-5] Pipeline MCP stopped."
        else
            echo "[portal-5] Pipeline MCP: not running (nothing to stop)."
        fi

        # MITRE MCP (:8929)
        if [ -f /tmp/portal-mitre-mcp.pid ] && kill -0 "$(cat /tmp/portal-mitre-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-mitre-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-mitre-mcp.pid
            echo "[portal-5] MITRE MCP stopped."
        else
            echo "[portal-5] MITRE MCP: not running (nothing to stop)."
        fi

        # Detections MCP (:8932)
        if [ -f /tmp/portal-detections-mcp.pid ] && kill -0 "$(cat /tmp/portal-detections-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-detections-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-detections-mcp.pid
            echo "[portal-5] Detections MCP stopped."
        else
            echo "[portal-5] Detections MCP: not running (nothing to stop)."
        fi

        # Wiki MCP (:8931)
        if [ -f /tmp/portal-wiki-mcp.pid ] && kill -0 "$(cat /tmp/portal-wiki-mcp.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-wiki-mcp.pid)" 2>/dev/null || true
            rm -f /tmp/portal-wiki-mcp.pid
            echo "[portal-5] Wiki MCP stopped."
        else
            echo "[portal-5] Wiki MCP: not running (nothing to stop)."
        fi

        # ARM64 embedding server (:8917)
        # launchd-managed: leave the service running (it manages its own lifecycle),
        # just print a note so the operator knows it's still up.
        if launchctl list com.portal5.embedding 2>/dev/null | grep -q '"PID"'; then
            echo "[portal-5] Embedding server: still running (launchd-managed — use './launch.sh uninstall-embedding-service' to stop permanently)."
        elif [ -f /tmp/portal-embedding-arm.pid ] && kill -0 "$(cat /tmp/portal-embedding-arm.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-embedding-arm.pid)" 2>/dev/null || true
            rm -f /tmp/portal-embedding-arm.pid
            echo "[portal-5] ARM64 embedding server stopped."
        else
            echo "[portal-5] Embedding server: not running (nothing to stop)."
        fi
    fi
}

# ── Port pre-flight check ───────────────────────────────────────────────────
_check_ports() {
    echo "[portal-5] Checking for port conflicts..."
    local FAILED=0

    # Check if a port is in use. Prints owning process if found.
    # Usage: _port_check <port> <service_name> [skip_if_profile_absent]
    _port_check() {
        local port="$1"
        local name="$2"
        local in_use=0

        # Primary check: try connecting
        if command -v nc &>/dev/null; then
            nc -z 127.0.0.1 "$port" 2>/dev/null && in_use=1
        else
            # bash built-in /dev/tcp fallback — works without nc
            (echo >/dev/tcp/127.0.0.1/"$port") 2>/dev/null && in_use=1 || true
        fi

        if [ "$in_use" -eq 1 ]; then
            echo "  ❌ Port $port ($name) is already in use"
            # Show which process owns it
            if command -v lsof &>/dev/null; then
                local owner
                owner=$(lsof -ti :"$port" 2>/dev/null | head -1)
                if [ -n "$owner" ]; then
                    local proc
                    proc=$(ps -p "$owner" -o comm= 2>/dev/null || echo "PID $owner")
                    echo "     └─ Owned by: $proc (PID $owner)"
                    echo "     └─ To free:  kill $owner"
                fi
            elif command -v ss &>/dev/null; then
                ss -tlnp "sport = :$port" 2>/dev/null | tail -1 | awk '{print "     └─ " $0}'
            fi
            FAILED=1
        else
            echo "  ✅ Port $port ($name) is free"
        fi
    }

    # Core services — always checked
    _port_check 8080  "Open WebUI"
    _port_check 9099  "Portal Pipeline"
    _port_check 8088  "SearXNG"
    _port_check 9090  "Prometheus"
    _port_check 3000  "Grafana"

    # MCP servers — use env overrides if set
    _port_check "${DOCUMENTS_HOST_PORT:-8913}"  "MCP Documents"
    # Music MCP runs natively on macOS — skip Docker port conflict check
    if [ "$(uname -m)" != "arm64" ]; then
        _port_check "${MUSIC_HOST_PORT:-8912}"  "MCP Music"
    fi
    _port_check "${TTS_HOST_PORT:-8916}"        "MCP TTS"
    _port_check "${WHISPER_HOST_PORT:-8915}"    "MCP Whisper"
    _port_check "${SANDBOX_HOST_PORT:-8914}"    "MCP Sandbox"
    # ComfyUI / Video MCP only run when ComfyUI is installed — skip check otherwise
    if [ -d "${COMFYUI_DIR:-$HOME/ComfyUI}" ]; then
        _port_check "${COMFYUI_MCP_HOST_PORT:-8910}" "MCP ComfyUI Bridge"
        _port_check "${VIDEO_MCP_HOST_PORT:-8911}"  "MCP Video"
    fi
    # On ARM64 the native embedding server is launchd-managed and intentionally
    # owns this port — skip the conflict check when it's our own service.
    if [ "$(uname -m)" = "arm64" ] && launchctl list com.portal5.embedding 2>/dev/null | grep -q '"PID"'; then
        echo "  ✅ Port ${EMBEDDING_HOST_PORT:-8917} (MCP Embedding) — launchd-managed native server"
    else
        _port_check "${EMBEDDING_HOST_PORT:-8917}"  "MCP Embedding"
    fi
    _port_check "${SECURITY_HOST_PORT:-8919}"   "MCP Security"

    # MLX Speech (port 8918) — only check if installed
    if python3 -c "import mlx_audio" &>/dev/null 2>&1; then
        if curl -s "http://localhost:8918/health" &>/dev/null 2>&1; then
            echo "  ✅ Port 8918 (MLX Speech) — already responding"
        else
            _port_check 8918   "MLX Speech (Qwen3-TTS + Qwen3-ASR)"
        fi
    fi

    # Ollama (Docker profile) — only check if explicitly using docker-ollama
    # Native Ollama on 11434 is expected and correct for the default setup
    if echo "${COMPOSE_PROFILES:-}" | grep -q "docker-ollama"; then
        _port_check 11434 "Ollama (Docker profile — conflicts with native Ollama)"
    fi

    if [ "$FAILED" -eq 1 ]; then
        echo ""
        echo "[portal-5] ❌ Port conflict(s) detected — cannot start safely."
        echo ""
        echo "  Options:"
        echo "  1. Stop the conflicting process (see 'kill <PID>' above)"
        echo "  2. If it's a previous Portal 5 stack:  ./launch.sh down"
        echo "     Note: 'down' also stops native Speech (:8918) and ComfyUI (:8188)"
        echo "  3. If it's a different service, override the port in .env:"
        echo "     e.g.:  DOCUMENTS_HOST_PORT=9013  (for MCP Documents)"
        echo "     All overrideable ports are documented in .env.example"
        echo ""
        exit 1
    fi

    echo "[portal-5] ✅ All ports are free."
}

# ── First-run bootstrap ───────────────────────────────────────────────────────
bootstrap_secrets() {
    local env_file="$1"
    local changed=0

    # Replace CHANGEME placeholders with generated secrets
    local tmp
    tmp=$(mktemp)
    cp "$env_file" "$tmp"

    if grep -q "^PIPELINE_API_KEY=CHANGEME" "$tmp"; then
        local key; key=$(generate_secret)
        sed -i.bak "s|^PIPELINE_API_KEY=CHANGEME|PIPELINE_API_KEY=$key|" "$tmp"
        echo "[portal-5] Generated PIPELINE_API_KEY"
        changed=1
    fi

    if grep -qE "^WEBUI_SECRET_KEY=CHANGEME(-AUTOGEN)?$" "$tmp"; then
        local key; key=$(generate_secret)
        sed -i.bak "s|^WEBUI_SECRET_KEY=CHANGEME.*|WEBUI_SECRET_KEY=$key|" "$tmp"
        echo "[portal-5] Generated WEBUI_SECRET_KEY"
        changed=1
    fi

    if grep -q "^OPENWEBUI_ADMIN_PASSWORD=CHANGEME" "$tmp"; then
        local pass; pass=$(generate_secret)
        sed -i.bak "s|^OPENWEBUI_ADMIN_PASSWORD=CHANGEME|OPENWEBUI_ADMIN_PASSWORD=$pass|" "$tmp"
        echo "[portal-5] Generated OPENWEBUI_ADMIN_PASSWORD"
        echo ""
        echo "  ╔══════════════════════════════════════════════════════╗"
        echo "  ║  First-run credentials (save these now)              ║"
        echo "  ║                                                      ║"
        echo "  ║  Open WebUI: http://localhost:8080                   ║"
        printf "  ║  Email:    %-41s ║\n" "$(grep "^OPENWEBUI_ADMIN_EMAIL=" "$tmp" | cut -d= -f2)"
        printf "  ║  Password: %-41s ║\n" "$pass"
        echo "  ╚══════════════════════════════════════════════════════╝"
        echo ""
        changed=1
    fi

    if grep -q "^SEARXNG_SECRET_KEY=CHANGEME" "$tmp"; then
        local key; key=$(generate_secret)
        sed -i.bak "s|^SEARXNG_SECRET_KEY=CHANGEME|SEARXNG_SECRET_KEY=$key|" "$tmp"
        echo "[portal-5] Generated SEARXNG_SECRET_KEY"
        changed=1
    fi

    if grep -q "^GRAFANA_PASSWORD=CHANGEME" "$tmp"; then
        local key; key=$(generate_secret | head -c 20)
        sed -i.bak "s|^GRAFANA_PASSWORD=CHANGEME|GRAFANA_PASSWORD=$key|" "$tmp"
        echo "[portal-5] Generated GRAFANA_PASSWORD"
        changed=1
    fi

    # Clean up sed backup files
    rm -f "${tmp}.bak"

    if [ $changed -eq 1 ]; then
        cp "$tmp" "$env_file"
        echo "[portal-5] Secrets written to .env"
    fi
    rm -f "$tmp"
}

# ── Admin API token helper ────────────────────────────────────────────────────
get_admin_token() {
    # Returns a JWT token for the admin account
    # Reads credentials from .env
    local url="${OPENWEBUI_URL:-http://localhost:8080}"
    local email="${OPENWEBUI_ADMIN_EMAIL:-admin@portal.local}"
    local pass="${OPENWEBUI_ADMIN_PASSWORD:-}"

    if [ -z "$pass" ]; then
        echo "ERROR: OPENWEBUI_ADMIN_PASSWORD not set in .env" >&2
        exit 1
    fi

    local _auth_json
    _auth_json=$(curl -s -X POST "$url/api/v1/auths/signin" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$email\",\"password\":\"$pass\"}" \
        2>/dev/null)
    _json_get "$_auth_json" '.token // ""' "d.get('token','')" ""
}

# ── Status display ─────────────────────────────────────────────────────────
_cmd_status() {
    local ARCH
    ARCH=$(uname -m)

    _svc_icon() {
        case "$1" in
            healthy)  echo "✅" ;;
            running)  echo "✅" ;;
            starting) echo "⏳" ;;
            *)        echo "❌" ;;
        esac
    }

    echo ""
    echo "  Portal 5 — System Status"
    echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # ── Stack services ────────────────────────────────────────────────────────
    echo "  STACK SERVICES"
    # Build status table: python3 looks up health per container name
    _stack_status() {
        cd "$COMPOSE_DIR" && docker compose ps --format json 2>/dev/null | python3 -c "
import json, sys
health = {}
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        d = json.loads(line)
        h = d.get('Health','') or ('running' if 'Up' in d.get('Status','') else 'stopped')
        health[d['Name']] = h
    except: pass

rows = [
    ('portal5-open-webui',    'Open WebUI',           'http://localhost:8080'),
    ('portal5-pipeline',      'Portal Pipeline',      'http://localhost:9099'),
    ('portal5-searxng',       'SearXNG',              'http://localhost:8088'),
    ('portal5-prometheus',    'Prometheus',           'http://localhost:9090'),
    ('portal5-grafana',       'Grafana',              'http://localhost:3000'),
    ('portal5-mcp-documents', 'MCP Documents',        ':8913'),
    ('portal5-mcp-tts',       'MCP TTS',              ':8916'),
    ('portal5-mcp-whisper',   'MCP Whisper',          ':8915'),
    ('portal5-mcp-sandbox',   'MCP Code Sandbox',     ':8914'),
    ('portal5-mcp-comfyui',   'MCP ComfyUI Bridge',   ':8910'),
    ('portal5-mcp-video',     'MCP Video',            ':8911'),
    ('portal5-mcp-security',  'MCP Security',         ':8919'),
    ('portal5-playwright',    'MCP Browser (Playwright)', ':8923'),
    ('portal5-mcp-research',  'MCP Research',         ':8922'),
    ('portal5-mcp-memory',    'MCP Memory',           ':8920'),
    ('portal5-mcp-rag',       'MCP RAG',              ':8921'),
    ('portal5-mcp-cad-render','MCP CAD Render',       ':8926'),
]
icons = {'healthy': '✅', 'running': '✅', 'starting': '⏳'}
for key, label, url in rows:
    h = health.get(key, 'stopped')
    icon = icons.get(h, '❌')
    print(f'    {icon}  {label:<28} {url}')
" 2>/dev/null
    }
    _stack_status
    echo ""

    # ── Native services ───────────────────────────────────────────────────────
    if [ "$ARCH" = "arm64" ]; then
        echo "  NATIVE SERVICES (host)"

        if command -v ollama &>/dev/null && python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=2)" &>/dev/null 2>&1; then
            _OV=$(ollama --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
            printf "    ✅  %-28s %s\n" "Ollama" ":11434  (v${_OV:-?})"
        else
            printf "    ❌  %-28s %s\n" "Ollama" "not running — brew services start ollama"
        fi

        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8188/system_stats', timeout=2)" &>/dev/null 2>&1; then
            _CV=$(python3 -c "
import urllib.request, json
d = json.loads(urllib.request.urlopen('http://localhost:8188/system_stats', timeout=3).read())
print(d.get('system',{}).get('comfyui_version','?'))
" 2>/dev/null || echo "?")
            printf "    ✅  %-28s %s\n" "ComfyUI (v${_CV})" ":8188"
        elif pgrep -f "ComfyUI/main.py|comfyui" &>/dev/null 2>&1; then
            printf "    ⏳  %-28s %s\n" "ComfyUI" "starting"
        else
            printf "    ❌  %-28s %s\n" "ComfyUI" "not running — ~/ComfyUI/start.sh"
        fi

        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${MUSIC_HOST_PORT:-8912}/health', timeout=2)" &>/dev/null 2>&1; then
            printf "    ✅  %-28s %s\n" "Music MCP" ":${MUSIC_HOST_PORT:-8912}"
        elif [ -f "$HOME/.portal5/music/.venv/bin/python" ]; then
            printf "    ❌  %-28s %s\n" "Music MCP" "installed but not running — ./launch.sh up"
        else
            printf "    ℹ️   %-28s %s\n" "Music MCP" "not installed — ./launch.sh install-music"
        fi

        # MLX Speech
        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8918/health', timeout=2)" &>/dev/null 2>&1; then
            printf "    ✅  %-28s %s\n" "MLX Speech" ":8918 (Qwen3-TTS + Qwen3-ASR)"
        elif [ -f /tmp/portal-mlx-speech.pid ] && kill -0 "$(cat /tmp/portal-mlx-speech.pid)" 2>/dev/null; then
            printf "    ⏳  %-28s %s\n" "MLX Speech" "starting"
        elif python3 -c "import mlx_audio" &>/dev/null 2>&1; then
            printf "    ❌  %-28s %s\n" "MLX Speech" "installed but not running — ./launch.sh start-speech"
        fi

        # MLX Transcribe service status
        if [ -f /tmp/portal-mlx-transcribe.pid ] && kill -0 "$(cat /tmp/portal-mlx-transcribe.pid)" 2>/dev/null; then
            printf "    ✅  %-28s %s\n" "MLX Transcribe" "running (PID $(cat /tmp/portal-mlx-transcribe.pid), :8924)"
        elif [ -f scripts/mlx-transcribe.py ]; then
            printf "    ❌  %-28s %s\n" "MLX Transcribe" "installed but not running — ./launch.sh start-transcribe"
        fi

        # Embedding server
        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${EMBEDDING_HOST_PORT:-8917}/health', timeout=2)" &>/dev/null 2>&1; then
            printf "    ✅  %-28s %s\n" "Embedding" ":${EMBEDDING_HOST_PORT:-8917}"
        elif launchctl list com.portal5.embedding 2>/dev/null | grep -q '"PID"'; then
            printf "    ⏳  %-28s %s\n" "Embedding" "starting (launchd-managed)"
        else
            printf "    ❌  %-28s %s\n" "Embedding" "not running — ./launch.sh up"
        fi

        # Powermetrics daemon
        if [ -S /tmp/portal5-powermetrics.sock ] && python3 -c "import socket; s=socket.socket(socket.AF_UNIX); s.connect('/tmp/portal5-powermetrics.sock'); s.close()" &>/dev/null 2>&1; then
            printf "    ✅  %-28s %s\n" "Powermetrics" "/tmp/portal5-powermetrics.sock"
        elif launchctl list com.portal5.powermetrics 2>/dev/null | grep -q '"PID"'; then
            printf "    ⏳  %-28s %s\n" "Powermetrics" "starting (launchd)"
        else
            printf "    ❌  %-28s %s\n" "Powermetrics" "not running — ./launch.sh install-powermetrics"
        fi

        echo ""
    fi

    # ── Pipeline summary ──────────────────────────────────────────────────────
    echo "  PIPELINE"
    _PH=$(python3 -c "
import urllib.request, json
d = json.loads(urllib.request.urlopen('http://localhost:9099/health', timeout=3).read())
print(f\"{d.get('backends_healthy','?')}/{d.get('backends_total','?')} backends healthy, {d.get('workspaces','?')} workspaces\")
" 2>/dev/null)
    if [ -n "$_PH" ]; then
        printf "    ✅  %s\n" "$_PH"
    else
        printf "    ❌  Pipeline unreachable\n"
    fi
    echo ""

    # ── Model counts ─────────────────────────────────────────────────────────
    echo "  MODELS"
    local _OW_EMAIL="${OPENWEBUI_ADMIN_EMAIL:-admin@portal.local}"
    local _OW_PASS="${OPENWEBUI_ADMIN_PASSWORD:-}"
    _OW_COUNTS=$(python3 -c "
import httpx
try:
    # Workspace count from pipeline
    ws_count = '?'
    try:
        pr = httpx.get('http://localhost:9099/health', timeout=3)
        ws_count = str(pr.json().get('workspaces', '?'))
    except: pass
    # Persona count from OWUI
    ps_count = '?'
    r = httpx.post('http://localhost:8080/api/v1/auths/signin',
        json={'email': '${_OW_EMAIL}', 'password': '${_OW_PASS}'}, timeout=5)
    token = r.json().get('token','')
    if token:
        r2 = httpx.get('http://localhost:8080/api/v1/models/export',
            headers={'Authorization': 'Bearer ' + token}, timeout=5)
        items = r2.json() if isinstance(r2.json(), list) else r2.json().get('items', r2.json().get('data', []))
        ps_count = str(len(items))
    print(ws_count, ps_count)
except Exception as e:
    print('? ?')
" 2>/dev/null || echo "? ?")
    read -r _WS_COUNT _PERSONA_COUNT <<< "$_OW_COUNTS"
    if [ "$_WS_COUNT" != "?" ]; then
        printf "    ✅  Workspaces: %-4s  Personas: %s\n" "${_WS_COUNT}" "${_PERSONA_COUNT}"
    else
        printf "    ❌  Open WebUI not reachable (model counts unavailable)\n"
    fi
    echo ""

    # ── Channels (only shown when tokens are configured) ─────────────────────
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] || [ -n "${SLACK_BOT_TOKEN:-}" ]; then
        echo "  CHANNELS"
        if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
            _TG=$(docker ps --format "{{.Names}}" 2>/dev/null | grep -c "portal5-telegram")
            if [ "$_TG" -ge 1 ]; then
                printf "    ✅  %-28s %s\n" "Telegram Bot" "running"
            else
                printf "    ❌  %-28s %s\n" "Telegram Bot" "configured but not running — ./launch.sh up"
            fi
        fi
        if [ -n "${SLACK_BOT_TOKEN:-}" ] && [ -n "${SLACK_APP_TOKEN:-}" ]; then
            _SL=$(docker ps --format "{{.Names}}" 2>/dev/null | grep -c "portal5-slack")
            if [ "$_SL" -ge 1 ]; then
                printf "    ✅  %-28s %s\n" "Slack Bot" "running"
            else
                printf "    ❌  %-28s %s\n" "Slack Bot" "configured but not running — ./launch.sh up"
            fi
        fi
        echo ""
    fi

}
