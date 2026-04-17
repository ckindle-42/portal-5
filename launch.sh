#!/bin/bash
set -euo pipefail
PORTAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$PORTAL_ROOT/deploy/portal-5"
ENV_FILE="$PORTAL_ROOT/.env"

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
        # Check MLX proxy (auto-switches mlx_lm ↔ mlx_vlm on 8081)
        if curl -s "http://localhost:8081/health" &>/dev/null 2>&1; then
            MLX_ACTIVE=$(_json_get "$(curl -s "http://localhost:8081/health" 2>/dev/null)" \
                '.active_server // "?"' "d.get('active_server','?')" "?")
            echo "  ✅ MLX proxy: active (server=$MLX_ACTIVE) — dual-server Apple Silicon inference"
        elif pgrep -f "mlx-proxy|mlx_lm.server|mlx_vlm.server" &>/dev/null 2>&1; then
            echo "  ⏳ MLX: starting in background (Ollama used until ready)"
        elif python3 -c "import mlx_vlm" &>/dev/null 2>&1; then
            echo "  ℹ️  MLX proxy: installed, not running (Ollama will be used)"
            echo "     Start: ~/.portal5/mlx/mlx-proxy.py"
        else
            echo "  ℹ️  MLX: not installed (optional, 20-40% faster than Ollama on M4)"
            echo "     Install: ./launch.sh install-mlx"
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

    # ── MLX proxy (Apple Silicon native only) ────────────────────────────────
    if [ "$ARCH" = "arm64" ]; then
        local MLX_PROXY_SCRIPT="$HOME/.portal5/mlx/mlx-proxy.py"
        if [ -f "$MLX_PROXY_SCRIPT" ]; then
            if ! curl -s "http://localhost:8081/health" &>/dev/null 2>&1; then
                echo "[portal-5]   MLX proxy installed but not running — starting..."
                mkdir -p "$HOME/.portal5/logs"
                if launchctl list com.portal5.mlx-proxy &>/dev/null 2>&1; then
                    launchctl start com.portal5.mlx-proxy 2>>"$HOME/.portal5/logs/mlx-proxy-launchctl.log" || true
                else
                    nohup python3 "$MLX_PROXY_SCRIPT" \
                        > "$HOME/.portal5/logs/mlx-proxy.log" 2>&1 &
                fi
                echo "[portal-5]   ⏳ MLX proxy starting on :8081 (auto-switches mlx_lm ↔ mlx_vlm)"
                echo "[portal-5]      Logs: $HOME/.portal5/logs/mlx-proxy.log"
            else
                echo "[portal-5]   ✅ MLX proxy: running"
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
                    nohup "$MUSIC_VENV/bin/python" -m portal_mcp.generation.music_mcp \
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

    # ── MLX Watchdog (Apple Silicon native only) ─────────────────────────────
    if [ "$ARCH" = "arm64" ]; then
        if [ "${MLX_WATCHDOG_ENABLED:-true}" != "false" ]; then
            local WATCHDOG_SCRIPT="$PORTAL_ROOT/scripts/mlx-watchdog.py"
            if [ -f "$WATCHDOG_SCRIPT" ]; then
                if [ -f /tmp/mlx-watchdog.pid ] && kill -0 "$(cat /tmp/mlx-watchdog.pid)" 2>/dev/null; then
                    echo "[portal-5]   ✅ MLX watchdog: running (PID $(cat /tmp/mlx-watchdog.pid))"
                else
                    echo "[portal-5]   MLX watchdog not running — starting..."
                    mkdir -p "$HOME/.portal5/logs"
                    nohup python3 "$WATCHDOG_SCRIPT" \
                        > "$HOME/.portal5/logs/mlx-watchdog.log" 2>&1 &
                    echo $! > /tmp/mlx-watchdog.pid
                    sleep 2
                    if kill -0 "$!" 2>/dev/null; then
                        echo "[portal-5]   ✅ MLX watchdog started (PID $!)"
                    else
                        echo "[portal-5]   ⚠️  MLX watchdog failed to start — check: $HOME/.portal5/logs/mlx-watchdog.log"
                    fi
                fi
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
    _port_check "${COMFYUI_MCP_HOST_PORT:-8910}" "MCP ComfyUI Bridge"
    _port_check "${VIDEO_MCP_HOST_PORT:-8911}"  "MCP Video"

    # MLX proxy (port 8081) — only check if installed
    # Skip the check if proxy is already responding (started by _ensure_native_services)
    if [ -f "$HOME/.portal5/mlx/mlx-proxy.py" ] || python3 -c "import mlx_vlm" &>/dev/null 2>&1; then
        if curl -s "http://localhost:8081/health" &>/dev/null 2>&1; then
            echo "  ✅ Port 8081 (MLX proxy) — already responding"
        else
            _port_check 8081   "MLX proxy (mlx_lm/vlm auto-switch)"
        fi
    fi

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
        echo "     Note: 'down' also stops native MLX (:8081), Speech (:8918) and ComfyUI (:8188)"
        echo "  3. If it's a different service, override the port in .env:"
        echo "     e.g.:  DOCUMENTS_HOST_PORT=9013  (for MCP Documents)"
        echo "            MLX_PORT=8082             (for MLX inference server)"
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

    if grep -q "^WEBUI_SECRET_KEY=CHANGEME" "$tmp"; then
        local key; key=$(generate_secret)
        sed -i.bak "s|^WEBUI_SECRET_KEY=CHANGEME|WEBUI_SECRET_KEY=$key|" "$tmp"
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

        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8081/health', timeout=2)" &>/dev/null 2>&1; then
            _MX=$(python3 -c "
import urllib.request, json
d = json.loads(urllib.request.urlopen('http://localhost:8081/health', timeout=3).read())
print(d.get('active_server','?'))
" 2>/dev/null || echo "?")
            printf "    ✅  %-28s %s  (%s server)\n" "MLX proxy" ":8081" "${_MX:-?}"
        elif pgrep -f "mlx-proxy|mlx_lm.server|mlx_vlm.server" &>/dev/null 2>&1; then
            printf "    ⏳  %-28s %s\n" "MLX" "starting"
        elif python3 -c "import mlx_vlm" &>/dev/null 2>&1; then
            printf "    ❌  %-28s %s\n" "MLX" "installed but not running — ./launch.sh up"
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

        # Watchdog
        if [ -f /tmp/mlx-watchdog.pid ] && kill -0 "$(cat /tmp/mlx-watchdog.pid)" 2>/dev/null; then
            printf "    ✅  %-28s %s\n" "MLX Watchdog" "running (PID $(cat /tmp/mlx-watchdog.pid))"
        elif python3 -c "import mlx_vlm" &>/dev/null 2>&1; then
            printf "    ❌  %-28s %s\n" "MLX Watchdog" "not running — ./launch.sh start-mlx-watchdog"
        fi

        # MLX Speech
        if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8918/health', timeout=2)" &>/dev/null 2>&1; then
            printf "    ✅  %-28s %s\n" "MLX Speech" ":8918 (Qwen3-TTS + Qwen3-ASR)"
        elif [ -f /tmp/portal-mlx-speech.pid ] && kill -0 "$(cat /tmp/portal-mlx-speech.pid)" 2>/dev/null; then
            printf "    ⏳  %-28s %s\n" "MLX Speech" "starting"
        elif python3 -c "import mlx_audio" &>/dev/null 2>&1; then
            printf "    ❌  %-28s %s\n" "MLX Speech" "installed but not running — ./launch.sh start-speech"
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
    r = httpx.post('http://localhost:8080/api/v1/auths/signin',
        json={'email': '${_OW_EMAIL}', 'password': '${_OW_PASS}'}, timeout=5)
    token = r.json().get('token','')
    if not token:
        print('? ?')
    else:
        r2 = httpx.get('http://localhost:8080/api/v1/models/export',
            headers={'Authorization': 'Bearer ' + token}, timeout=5)
        items = r2.json() if isinstance(r2.json(), list) else r2.json().get('items', r2.json().get('data', []))
        ws = sum(1 for m in items if m['id'].startswith('auto'))
        ps = sum(1 for m in items if not m['id'].startswith('auto'))
        print(ws, ps)
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
}

case "${1:-up}" in
  up)
    # Copy example if .env doesn't exist
    if [ ! -f "$ENV_FILE" ]; then
        cp "$PORTAL_ROOT/.env.example" "$ENV_FILE"
        echo "[portal-5] Created .env from .env.example"
    fi

    # Generate any secrets still set to CHANGEME
    bootstrap_secrets "$ENV_FILE"

    # Auto-start native services first so _check_hardware sees them as running
    _ensure_native_services

    # Check hardware requirements (runs after native services are up)
    _check_hardware

    set -a; source "$ENV_FILE"; set +a

    # Validate required secrets — auto-repair any still set to CHANGEME
    # (handles interrupted first-run or manual .env edits that left placeholders)
    _repair=0
    for var in PIPELINE_API_KEY WEBUI_SECRET_KEY OPENWEBUI_ADMIN_PASSWORD SEARXNG_SECRET_KEY GRAFANA_PASSWORD; do
        val="${!var:-}"
        if [ -z "$val" ] || [ "$val" = "CHANGEME" ]; then
            _new_secret=$(generate_secret)
            # Write the new value directly into .env
            if grep -q "^${var}=" "$ENV_FILE"; then
                sed -i.bak "s|^${var}=.*|${var}=${_new_secret}|" "$ENV_FILE"
                rm -f "${ENV_FILE}.bak"
            else
                echo "${var}=${_new_secret}" >> "$ENV_FILE"
            fi
            echo "[portal-5] Repaired missing secret: $var"
            _repair=1
        fi
    done
    if [ "$_repair" -eq 1 ]; then
        # Re-source .env so the newly written values are in scope
        set -a; source "$ENV_FILE"; set +a
        echo "[portal-5] Secrets repaired. Continuing..."
    fi

    # Port pre-flight check (uses sourced env for port overrides)
    _check_ports

    # Ensure .env is in the compose directory (docker compose auto-loads .env from
    # the compose file's directory; symlink if not already there)
    if [ ! -f "$COMPOSE_DIR/.env" ]; then
        ln -s "$ENV_FILE" "$COMPOSE_DIR/.env"
        echo "[portal-5] Linked .env into compose directory"
    fi

    # Inject SEARXNG_SECRET_KEY into searxng settings.yml (SearXNG reads secret_key
    # from settings.yml, NOT from env vars — the env var comment in settings.yml was wrong)
    if [ -n "${SEARXNG_SECRET_KEY:-}" ] && [ -f "$PORTAL_ROOT/config/searxng/settings.yml" ]; then
        if grep -q "^  secret_key: REPLACE_ME_WITH_SEARXNG_SECRET_KEY" "$PORTAL_ROOT/config/searxng/settings.yml"; then
            sed -i.bak "s|^  secret_key: REPLACE_ME_WITH_SEARXNG_SECRET_KEY|  secret_key: ${SEARXNG_SECRET_KEY}|" \
                "$PORTAL_ROOT/config/searxng/settings.yml"
            rm -f "$PORTAL_ROOT/config/searxng/settings.yml.bak"
            echo "[portal-5] Injected SEARXNG_SECRET_KEY into settings.yml"
        fi
    fi

    # Derive WEBUI_LISTEN_ADDR from ENABLE_REMOTE_ACCESS (set in .env).
    # Default: localhost-only. Set ENABLE_REMOTE_ACCESS=true to expose on all interfaces.
    if [ "${ENABLE_REMOTE_ACCESS:-false}" = "true" ]; then
        export WEBUI_LISTEN_ADDR="0.0.0.0"
        echo "[portal-5] Remote access enabled — Open WebUI will listen on 0.0.0.0:8080"
    else
        export WEBUI_LISTEN_ADDR="127.0.0.1"
    fi

    # Persist WEBUI_LISTEN_ADDR to .env so that `docker compose up -d` and
    # `docker restart` invoked outside of launch.sh always pick up the correct
    # binding address.  Without this, any restart falls back to 127.0.0.1.
    if grep -q "^WEBUI_LISTEN_ADDR=" "$ENV_FILE" 2>/dev/null; then
        sed -i.bak "s|^WEBUI_LISTEN_ADDR=.*|WEBUI_LISTEN_ADDR=${WEBUI_LISTEN_ADDR}|" "$ENV_FILE"
        rm -f "${ENV_FILE}.bak"
    else
        echo "WEBUI_LISTEN_ADDR=${WEBUI_LISTEN_ADDR}" >> "$ENV_FILE"
    fi

    echo "[portal-5] Starting stack..."
    cd "$COMPOSE_DIR"
    docker compose up -d

    # Auto-start ARM64 native embedding server on Apple Silicon (TEI image is x86-only)
    if [ "$(uname -m)" = "arm64" ]; then
        # If the launchd service is installed it manages the server — don't double-start.
        if launchctl list com.portal5.embedding 2>/dev/null | grep -q '"PID"'; then
            echo "[portal-5]   ✅ ARM64 embedding server managed by launchd (auto-restart on crash)"
        else
            _PID_FILE="/tmp/portal-embedding-arm.pid"
            if [ -f "$_PID_FILE" ] && kill -0 "$(cat "$_PID_FILE")" 2>/dev/null; then
                echo "[portal-5]   ✅ ARM64 embedding server already running (PID $(cat "$_PID_FILE"))"
                echo "[portal-5]   💡 Tip: run './launch.sh install-embedding-service' to start at login automatically"
            else
                # Use a dedicated venv so packages don't collide with the project venv
                # or the Homebrew-managed system Python (PEP 668).
                _EM_VENV="${HOME}/.portal5/embedding-venv"
                _EM_PY="${_EM_VENV}/bin/python3"
                if [ ! -x "$_EM_PY" ]; then
                    python3 -m venv "$_EM_VENV" --without-pip 2>/dev/null || python3 -m venv "$_EM_VENV"
                    "$_EM_PY" -m ensurepip --upgrade &>/dev/null || true
                fi
                if ! "$_EM_PY" -c "import sentence_transformers, fastapi, uvicorn" &>/dev/null 2>&1; then
                    echo "[portal-5]   Installing ARM64 embedding server deps..."
                    "$_EM_PY" -m pip install --quiet sentence-transformers fastapi uvicorn 2>&1 | tail -1 || true
                fi
                if "$_EM_PY" -c "import sentence_transformers, fastapi, uvicorn" &>/dev/null 2>&1; then
                    echo "[portal-5]   Starting ARM64 native embedding server (port 8917)..."
                    _EM_MODEL="${EMBEDDING_MODEL:-microsoft/harrier-oss-v1-0.6b}"
                    _EM_PORT="${EMBEDDING_HOST_PORT:-8917}"
                    _EM_LOG="${HOME}/.portal5/logs/embedding-server.log"
                    mkdir -p "$(dirname "$_EM_LOG")"
                    nohup "$_EM_PY" "$PORTAL_ROOT/scripts/embedding-server.py" \
                        --model "$_EM_MODEL" \
                        --port "$_EM_PORT" \
                        > "$_EM_LOG" 2>&1 &
                    echo $! > "$_PID_FILE"
                    echo "[portal-5]   ✅ ARM64 embedding server started (PID $!)"
                    echo "[portal-5]   💡 Tip: run './launch.sh install-embedding-service' to start at login automatically"
                else
                    echo "[portal-5]   ⚠️  ARM64 embedding server deps install failed — skipping"
                fi
            fi
        fi
    fi

    # Re-run openwebui-init in the background to pick up any new personas/workspaces
    # added since the last run (idempotent — skips existing, only creates new ones).
    # Only runs if open-webui is already healthy (first-run init is handled by depends_on).
    if docker compose ps open-webui 2>/dev/null | grep -q "(healthy)"; then
        echo "[portal-5] Syncing new personas/workspaces (incremental)..."
        docker compose run --rm openwebui-init >/dev/null 2>&1 &
    fi

    # Prune dangling images left behind by image pulls (untagged build layers).
    # Safe: only removes images with no tag and no running container referencing them.
    # Does NOT remove images used by other projects on this machine.
    _PRUNED=$(docker image prune -f 2>/dev/null | grep "Total reclaimed" || true)
    if [ -n "$_PRUNED" ] && ! echo "$_PRUNED" | grep -qE "0 ?B$"; then
        echo "[portal-5] 🧹 $_PRUNED"
    fi

    echo "[portal-5] Stack started."
    if [ "${ENABLE_REMOTE_ACCESS:-false}" = "true" ]; then
        echo "  Open WebUI:  http://$(hostname -f 2>/dev/null || hostname):8080  (remote access enabled)"
    else
        echo "  Open WebUI:  http://localhost:8080"
    fi
    echo "  SearXNG:     http://localhost:8088"
    echo "  ComfyUI:     http://localhost:8188"
    echo "  Grafana:     http://localhost:3000  (admin / check .env)"
    echo "  Prometheus:  http://localhost:9090"
    ;;
  test)
    # Run end-to-end smoke tests against the live stack
    # Usage: ./launch.sh up && sleep 30 && ./launch.sh test
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    export MLX_WATCHDOG_ENABLED=false
    OWUI="${OPENWEBUI_URL:-http://localhost:8080}"
    PIPE="http://localhost:9099"
    PASS=0; FAIL=0

    _check() {
        local name="$1" result="$2" expect="$3"
        if [ "$result" = "$expect" ]; then
            echo "  ✅ $name"
            PASS=$((PASS+1))
        else
            echo "  ❌ $name (got: $result, expected: $expect)"
            FAIL=$((FAIL+1))
        fi
    }

    echo "=== Portal 5 Live Stack Smoke Test ==="
    echo ""

    # ── Pipeline ──────────────────────────────────────────────────────────────
    echo "Pipeline:"
    HEALTH_JSON=$(curl -s "$PIPE/health" 2>/dev/null)
    STATUS=$(_json_get "$HEALTH_JSON" '.status // "?"' "json.load(sys.stdin).get('status','?')" "?")
    BACKENDS=$(_json_get "$HEALTH_JSON" '.backends_healthy // 0' "json.load(sys.stdin).get('backends_healthy',0)" "0")

    # Pipeline is reachable if status is 'ok' or 'degraded' (either means it's running)
    [ "$STATUS" = "ok" ] || [ "$STATUS" = "degraded" ] \
        && { echo "  ✅ Pipeline reachable (status=$STATUS)"; PASS=$((PASS+1)); } \
        || { echo "  ❌ Pipeline not responding (status=$STATUS)"; FAIL=$((FAIL+1)); }

    # Ollama connectivity is informational — degraded is expected before models are pulled
    [ "$STATUS" = "ok" ] \
        && echo "  ✅ Ollama connected ($BACKENDS backends healthy)" && PASS=$((PASS+1)) \
        || echo "  ℹ️  Ollama: no backends healthy yet — run: ./launch.sh pull-models"

    WS_COUNT=$(_json_get "$(curl -s -H "Authorization: Bearer ${PIPELINE_API_KEY}" "$PIPE/v1/models" 2>/dev/null)" \
        '(.data // []) | length' "d=json.load(sys.stdin); print(len(d.get('data',[])))" "0")
    _check "all 15 workspaces exposed" "$WS_COUNT" "15"

    METRICS=$(curl -s "$PIPE/metrics" | grep -c "^portal_")
    [ "$METRICS" -ge 4 ] && echo "  ✅ Prometheus metrics ($METRICS gauges)" && PASS=$((PASS+1)) || { echo "  ❌ Metrics missing"; FAIL=$((FAIL+1)); }

    # ── Open WebUI ────────────────────────────────────────────────────────────
    echo ""
    echo "Open WebUI:"
    OW_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$OWUI/health")
    _check "Open WebUI responds" "$OW_STATUS" "200"

    # ── Ollama inference ──────────────────────────────────────────────────────
    echo ""
    echo "Ollama:"
    MODELS=$(_json_get "$(curl -s http://localhost:11434/api/tags 2>/dev/null)" \
        '(.models // []) | length' "d=json.load(sys.stdin); print(len(d.get('models',[])))" "0")
    [ "$MODELS" -ge 1 ] && echo "  ✅ Ollama has $MODELS model(s) loaded" && PASS=$((PASS+1)) || { echo "  ❌ No Ollama models loaded — run: ./launch.sh pull-models"; FAIL=$((FAIL+1)); }

    # Live inference test
    _infer_json=$(curl -s -X POST "$PIPE/v1/chat/completions" \
        -H "Authorization: Bearer ${PIPELINE_API_KEY}" \
        -H "Content-Type: application/json" \
        -d '{"model":"auto","messages":[{"role":"user","content":"Say PONG"}],"stream":false}' \
        2>/dev/null)
    REPLY=$(_json_get "$_infer_json" \
        '(.choices[0].message.content // "FAIL")[:20]' \
        "d=json.load(sys.stdin); print(d.get('choices',[{}])[0].get('message',{}).get('content','FAIL')[:20])" "FAIL")
    [ -n "$REPLY" ] && [ "$REPLY" != "FAIL" ] && echo "  ✅ Live inference: got reply" && PASS=$((PASS+1)) || { echo "  ❌ Live inference failed — check Ollama has a model"; FAIL=$((FAIL+1)); }

    # ── MCP Servers ───────────────────────────────────────────────────────────
    echo ""
    echo "MCP Servers:"
    for port_name in "8913:Documents" "8912:Music" "8916:TTS" "8915:Whisper" \
                     "8910:ComfyUI" "8911:Video" "8914:Sandbox"; do
        PORT="${port_name%%:*}"
        NAME="${port_name##*:}"
        HC=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/health" 2>/dev/null)
        _check "$NAME MCP (:$PORT)" "$HC" "200"
    done

    # ── Document generation ───────────────────────────────────────────────────
    echo ""
    echo "Document Generation:"
    _doc_json=$(curl -s -X POST "http://localhost:8913/mcp" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"create_word_document","arguments":{"title":"Smoke Test","content":"Portal 5 smoke test document"}},"id":1}' \
        2>/dev/null)
    DOC_RESULT=$(_json_get "$_doc_json" \
        'if (.result.success // false) or (.result | tostring | test("path")) then "OK" else "FAIL" end' \
        "d=json.load(sys.stdin); r=d.get('result',{}); print('OK' if r.get('success') or 'path' in str(r) else 'FAIL')" "FAIL")
    _check "Word document created" "$DOC_RESULT" "OK"

    # ── TTS ───────────────────────────────────────────────────────────────────
    echo ""
    echo "TTS / Voice:"
    TTS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://localhost:8916/v1/audio/speech" \
        -H "Content-Type: application/json" \
        -d '{"input":"Hello from Portal 5","voice":"af_heart"}' 2>/dev/null)
    # 200 = works, 503 = model downloading, both acceptable
    [ "$TTS_STATUS" = "200" ] && echo "  ✅ TTS generates audio" && PASS=$((PASS+1)) || \
    [ "$TTS_STATUS" = "503" ] && echo "  ⚠️  TTS: kokoro model downloading (first run — try again in 60s)" || \
    { echo "  ❌ TTS error (HTTP $TTS_STATUS)"; FAIL=$((FAIL+1)); }

    # ── SearXNG ───────────────────────────────────────────────────────────────
    echo ""
    echo "Web Search:"
    SEARCH=$(_json_get "$(curl -s "http://localhost:8088/search?q=portal+ai&format=json" 2>/dev/null)" \
        'if (.results // [] | length) > 0 then "OK" else "EMPTY" end' \
        "d=json.load(sys.stdin); print('OK' if d.get('results') else 'EMPTY')" "EMPTY")
    _check "SearXNG returns results" "$SEARCH" "OK"

    # ── Prometheus + Grafana ──────────────────────────────────────────────────
    echo ""
    echo "Metrics:"
    PROM=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:9090/-/healthy" 2>/dev/null)
    _check "Prometheus healthy" "$PROM" "200"
    GRAF=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:3000/api/health" 2>/dev/null)
    _check "Grafana healthy" "$GRAF" "200"

    # ── Channels (if running) ─────────────────────────────────────────────────
    echo ""
    echo "Channels:"
    TG=$(docker ps --format "{{.Names}}" 2>/dev/null | grep -c "portal5-telegram" || echo 0)
    [ "$TG" -ge 1 ] && echo "  ✅ Telegram container running" && PASS=$((PASS+1)) || echo "  ℹ️  Telegram not running (./launch.sh up-telegram to start)"
    SL=$(docker ps --format "{{.Names}}" 2>/dev/null | grep -c "portal5-slack" || echo 0)
    [ "$SL" -ge 1 ] && echo "  ✅ Slack container running" && PASS=$((PASS+1)) || echo "  ℹ️  Slack not running (./launch.sh up-slack to start)"

    # ── Summary ───────────────────────────────────────────────────────────────
    echo ""
    echo "=================================================="
    echo "  Results: $PASS passed, $FAIL failed"
    echo "=================================================="
    [ "$FAIL" -eq 0 ] && echo "  ✅ All checks passed — Portal 5 is fully operational" || \
        echo "  ❌ $FAIL check(s) failed — review output above"
    [ "$FAIL" -gt 0 ] && exit 1 || exit 0
    ;;

  up-telegram)
    # Start core stack + Telegram bot
    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
        source "$ENV_FILE"
    fi
    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
        echo "ERROR: TELEGRAM_BOT_TOKEN not set in .env"
        echo "  Get a token from @BotFather: https://t.me/BotFather"
        echo "  Then set TELEGRAM_BOT_TOKEN=... in .env"
        exit 1
    fi
    set -a; source "$ENV_FILE"; set +a
    if [ ! -f "$COMPOSE_DIR/.env" ]; then
        ln -s "$ENV_FILE" "$COMPOSE_DIR/.env"
    fi
    cd "$COMPOSE_DIR"
    docker compose --profile telegram up -d
    echo "[portal-5] Stack + Telegram started"
    echo "  Send /start to your bot to verify it's working"
    ;;

  up-slack)
    # Start core stack + Slack bot
    source "$ENV_FILE" 2>/dev/null || true
    set -a; source "$ENV_FILE"; set +a
    for var in SLACK_BOT_TOKEN SLACK_APP_TOKEN; do
        val="${!var:-}"
        if [ -z "$val" ]; then
            echo "ERROR: $var not set in .env"
            echo "  Create at: https://api.slack.com/apps"
            echo "  Enable Socket Mode and create an App-Level Token (xapp-...)"
            exit 1
        fi
    done
    if [ ! -f "$COMPOSE_DIR/.env" ]; then
        ln -s "$ENV_FILE" "$COMPOSE_DIR/.env"
    fi
    cd "$COMPOSE_DIR"
    docker compose --profile slack up -d
    echo "[portal-5] Stack + Slack started"
    echo "  Mention @portal in any channel to verify"
    ;;

  up-channels)
    # Start core stack + both Telegram and Slack
    set -a; source "$ENV_FILE"; set +a
    if [ ! -f "$COMPOSE_DIR/.env" ]; then
        ln -s "$ENV_FILE" "$COMPOSE_DIR/.env"
    fi
    cd "$COMPOSE_DIR"
    docker compose --profile telegram --profile slack up -d
    echo "[portal-5] Stack + all channels started"
    ;;

  prune)
    # Remove unused Docker resources to reclaim disk space.
    # Removes: dangling images, stopped containers, unused networks.
    # Does NOT remove: named volumes (model weights, OW data), images in use.
    echo "[portal-5] Pruning unused Docker resources..."
    docker system prune -f
    echo ""
    echo "[portal-5] Current Docker disk usage:"
    docker system df
    ;;
  down)
    # ── Stop Docker stack ─────────────────────────────────────────────────
    cd "$COMPOSE_DIR"
    docker compose down
    echo "[portal-5] Docker stack stopped."

    # ── Stop native macOS services (MLX, ComfyUI) ─────────────────────────
    # These run outside Docker and must be stopped explicitly.
    # Uses launchctl if the service is registered, falls back to pkill.
    if [ "$(uname -s)" = "Darwin" ]; then
        # MLX proxy (:8081) + underlying servers (:18081, :18082)
        if launchctl list com.portal5.mlx-proxy &>/dev/null 2>&1; then
            launchctl stop com.portal5.mlx-proxy 2>/dev/null || true
            echo "[portal-5] MLX proxy service stopped (launchd)."
        elif pgrep -f "mlx-proxy|mlx_lm.server|mlx_vlm.server" &>/dev/null 2>&1; then
            pkill -f "mlx-proxy" 2>/dev/null || true
            pkill -f "mlx_lm.server" 2>/dev/null || true
            pkill -f "mlx_vlm.server" 2>/dev/null || true
            echo "[portal-5] MLX processes stopped (pkill)."
        else
            echo "[portal-5] MLX proxy: not running (nothing to stop)."
        fi

        # Remove stale single-server plist if present
        if [ -f "$HOME/Library/LaunchAgents/com.portal5.mlx.plist" ]; then
            launchctl unload "$HOME/Library/LaunchAgents/com.portal5.mlx.plist" 2>/dev/null || true
            rm -f "$HOME/Library/LaunchAgents/com.portal5.mlx.plist"
            echo "[portal-5] Removed stale com.portal5.mlx plist."
        fi

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

        # MLX Watchdog
        if [ -f /tmp/mlx-watchdog.pid ] && kill -0 "$(cat /tmp/mlx-watchdog.pid)" 2>/dev/null; then
            kill "$(cat /tmp/mlx-watchdog.pid)" 2>/dev/null || true
            rm -f /tmp/mlx-watchdog.pid
            echo "[portal-5] MLX watchdog stopped."
        else
            echo "[portal-5] MLX watchdog: not running (nothing to stop)."
        fi

        # MLX Speech (:8918)
        if [ -f /tmp/portal-mlx-speech.pid ] && kill -0 "$(cat /tmp/portal-mlx-speech.pid)" 2>/dev/null; then
            kill "$(cat /tmp/portal-mlx-speech.pid)" 2>/dev/null || true
            rm -f /tmp/portal-mlx-speech.pid
            echo "[portal-5] MLX Speech stopped."
        else
            echo "[portal-5] MLX Speech: not running (nothing to stop)."
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
    ;;
  backup)
    # Back up all critical Portal 5 data
    # Usage: ./launch.sh backup [output-dir]
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    BACKUP_DIR="${2:-./backups}"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_PATH="${BACKUP_DIR}/portal5_backup_${TIMESTAMP}"
    mkdir -p "$BACKUP_PATH"

    echo "[portal-5] Backing up to: $BACKUP_PATH"

    # Open WebUI data (users, chat history, workspaces, settings)
    echo "[portal-5] Backing up Open WebUI data..."
    docker run --rm \
        -v portal-5_open-webui-data:/data \
        -v "$(realpath "$BACKUP_PATH"):/backup" \
        alpine sh -c "tar czf /backup/openwebui-data.tar.gz /data 2>/dev/null && echo 'Done'" \
        && echo "  ✅ openwebui-data.tar.gz" \
        || echo "  ⚠️  Open WebUI backup failed (is the stack running?)"

    # Grafana dashboards and datasources
    echo "[portal-5] Backing up Grafana data..."
    docker run --rm \
        -v portal-5_grafana-data:/data \
        -v "$(realpath "$BACKUP_PATH"):/backup" \
        alpine sh -c "tar czf /backup/grafana-data.tar.gz /data 2>/dev/null && echo 'Done'" \
        && echo "  ✅ grafana-data.tar.gz" \
        || echo "  ⚠️  Grafana backup skipped"

    # .env (secrets and config)
    if [ -f "$ENV_FILE" ]; then
        cp "$ENV_FILE" "${BACKUP_PATH}/.env"
        echo "  ✅ .env"
    fi

    # Configuration files
    cp -r config/ "${BACKUP_PATH}/config" 2>/dev/null && echo "  ✅ config/"
    cp -r imports/ "${BACKUP_PATH}/imports" 2>/dev/null && echo "  ✅ imports/"

    echo "[portal-5] Backup complete: $BACKUP_PATH"
    echo "  To restore: ./launch.sh restore $BACKUP_PATH"
    ;;
  restore)
    # Restore Portal 5 data from a backup
    # Usage: ./launch.sh restore <backup-path>
    BACKUP_PATH="${2:-}"
    if [ -z "$BACKUP_PATH" ] || [ ! -d "$BACKUP_PATH" ]; then
        echo "Usage: ./launch.sh restore <backup-path>"
        echo "  e.g.: ./launch.sh restore ./backups/portal5_backup_20260301_120000"
        exit 1
    fi

    echo "[portal-5] WARNING: This will OVERWRITE current data with backup from:"
    echo "  $BACKUP_PATH"
    printf "Continue? [y/N] "
    read -r confirm
    [ "$confirm" = "y" ] || [ "$confirm" = "Y" ] || { echo "Aborted."; exit 0; }

    # Stop stack before restore
    cd "$COMPOSE_DIR" && docker compose down 2>/dev/null; cd - > /dev/null

    # Restore Open WebUI data
    if [ -f "${BACKUP_PATH}/openwebui-data.tar.gz" ]; then
        echo "[portal-5] Restoring Open WebUI data..."
        docker run --rm \
            -v portal-5_open-webui-data:/data \
            -v "$(realpath "$BACKUP_PATH"):/backup" \
            alpine sh -c "rm -rf /data/* && tar xzf /backup/openwebui-data.tar.gz -C / 2>/dev/null"
        echo "  ✅ Open WebUI data restored"
    fi

    # Restore Grafana
    if [ -f "${BACKUP_PATH}/grafana-data.tar.gz" ]; then
        echo "[portal-5] Restoring Grafana data..."
        docker run --rm \
            -v portal-5_grafana-data:/data \
            -v "$(realpath "$BACKUP_PATH"):/backup" \
            alpine sh -c "rm -rf /data/* && tar xzf /backup/grafana-data.tar.gz -C / 2>/dev/null"
        echo "  ✅ Grafana data restored"
    fi

    # Restore .env
    if [ -f "${BACKUP_PATH}/.env" ]; then
        cp "${BACKUP_PATH}/.env" "$ENV_FILE"
        echo "  ✅ .env restored"
    fi

    echo "[portal-5] Restore complete. Run: ./launch.sh up"
    ;;
  rebuild)
    # Rebuild and restart portal-pipeline (e.g. after a code update via git pull)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    cd "$COMPOSE_DIR"
    echo "[portal-5] Rebuilding portal-pipeline..."
    docker compose build portal-pipeline
    echo "[portal-5] Restarting portal-pipeline..."
    docker compose up -d --no-deps portal-pipeline
    echo "[portal-5] Done. Check status: ./launch.sh status"
    ;;

  update)
    # Full update: git pull, Docker images, rebuilds, model refresh, re-seed, restart
    # Usage: ./launch.sh update [--skip-models|--models-only] [--yes|-y]
    _UPDATE_SKIP_MODELS=false
    _UPDATE_MODELS_ONLY=false
    _UPDATE_YES=false
    for _arg in "${@:2}"; do
        case "$_arg" in
            --skip-models) _UPDATE_SKIP_MODELS=true ;;
            --models-only) _UPDATE_MODELS_ONLY=true ;;
            --yes|-y)      _UPDATE_YES=true ;;
            *)
                echo "Unknown option: $_arg"
                echo "Usage: ./launch.sh update [--skip-models|--models-only] [--yes|-y]"
                exit 1
                ;;
        esac
    done

    ARCH=$(uname -m)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    echo ""
    echo "  Portal 5 — Update"
    echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # ── Step 1: Git pull ───────────────────────────────────────────────────
    if [ "$_UPDATE_MODELS_ONLY" = "false" ]; then
        echo "[1/8] Updating portal-5 source..."
        if [ -d "$PORTAL_ROOT/.git" ]; then
            _BEFORE_SHA=$(git -C "$PORTAL_ROOT" rev-parse HEAD 2>/dev/null)
            git -C "$PORTAL_ROOT" pull --ff-only 2>/dev/null
            _AFTER_SHA=$(git -C "$PORTAL_ROOT" rev-parse HEAD 2>/dev/null)
            if [ "$_BEFORE_SHA" != "$_AFTER_SHA" ]; then
                echo "  ✅ Updated ($_BEFORE_SHA → $_AFTER_SHA)"
            else
                echo "  ✅ Already up to date"
            fi
        else
            echo "  ⚠️  Not a git repo — skipping source update"
        fi
        echo ""
    fi

    # ── Step 2: Pull Docker images ────────────────────────────────────────
    if [ "$_UPDATE_MODELS_ONLY" = "false" ]; then
        echo "[2/8] Pulling latest Docker images..."
        cd "$COMPOSE_DIR"
        # pull_policy: always services get pulled automatically, but explicit pull
        # also catches prometheus/grafana (pinned but we check for patch updates)
        docker compose pull ollama open-webui searxng 2>/dev/null || true
        echo "  ✅ Docker images pulled"
        echo ""
    fi

    # ── Step 3: Rebuild portal-pipeline + MCP servers ─────────────────────
    if [ "$_UPDATE_MODELS_ONLY" = "false" ]; then
        echo "[3/8] Rebuilding portal-pipeline + MCP servers..."
        cd "$COMPOSE_DIR"
        docker compose build portal-pipeline mcp-documents mcp-comfyui mcp-video mcp-tts mcp-whisper mcp-sandbox 2>/dev/null || \
            docker compose build portal-pipeline 2>/dev/null || true
        echo "  ✅ Images rebuilt"
        echo ""
    fi

    # ── Step 4: Refresh Ollama models ─────────────────────────────────────
    if [ "$_UPDATE_SKIP_MODELS" = "false" ]; then
        echo "[4/8] Refreshing Ollama models (checks for newer versions)..."
        _ollama_cmd() {
            if command -v ollama &>/dev/null && curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
                echo "ollama"
            elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^portal5-ollama$"; then
                echo "docker exec portal5-ollama ollama"
            else
                echo ""
            fi
        }
        _OCMD=$(_ollama_cmd)
        if [ -n "$_OCMD" ]; then
            _MODELS=(
                "${DEFAULT_MODEL:-dolphin-llama3:8b}"
                "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF"
                "nomic-embed-text:latest"
        # Note: Harrier-0.6B is served by portal5-embedding container (TEI), not Ollama.
        # nomic-embed-text kept as fallback if embedding service is down.
                "hf.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF"
                "hf.co/cognitivecomputations/Dolphin3.0-R1-Mistral-24B-GGUF"
                "xploiter/the-xploiter"
                "hf.co/WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF"
                "huihui_ai/baronllm-abliterated"
                "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0"
                "qwen3.5:9b"
                "qwen3-coder:30b"
                "hf.co/unsloth/GLM-4.7-Flash-GGUF"
                "hf.co/deepseek-ai/DeepSeek-Coder-V2-Lite-Base-GGUF"
                "deepseek-coder-v2:16b-lite-instruct-q4_K_M"
                "devstral:24b"
                "hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF"
                "huihui_ai/tongyi-deepresearch-abliterated"
                "qwen3-vl:32b"
                "llava:7b"
            )
            if [ "${PULL_HEAVY:-false}" = "true" ]; then
                _MODELS+=(
                    "hf.co/cognitivecomputations/dolphin-3-llama3-70b-GGUF"
                    "hf.co/meta-llama/Meta-Llama-3.3-70B-GGUF"
                )
            fi
            _TOTAL=${#_MODELS[@]}
            _COUNT=0
            _FAILED=0
            for _model in "${_MODELS[@]}"; do
                _COUNT=$((_COUNT + 1))
                echo "  [$_COUNT/$_TOTAL] $_model"
                $_OCMD pull "$_model" 2>/dev/null && echo "  ✅ Done" || _FAILED=$((_FAILED + 1))
            done
            echo "  Ollama: $((_TOTAL - _FAILED))/$_TOTAL succeeded"
        else
            echo "  ⚠️  Ollama not running — skipping model refresh"
            echo "     Start Ollama and run: ./launch.sh refresh-models"
        fi
        echo ""
    fi

    # ── Step 5: Pull MLX models (Apple Silicon only) ──────────────────────
    if [ "$_UPDATE_SKIP_MODELS" = "false" ] && [ "$ARCH" = "arm64" ]; then
        echo "[5/8] Refreshing MLX models (Apple Silicon)..."
        if python3 -c "import mlx_lm" &>/dev/null 2>&1; then
            _MLX_MODELS=(
                "mlx-community/Qwen3-Coder-Next-4bit"
                "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit"
                "Jackrong/MLX-Qwopus3.5-9B-v3-8bit"
                "Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit"
                "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit"
                "lmstudio-community/Devstral-Small-2507-MLX-4bit"
                "Jackrong/MLX-Qwopus3.5-27B-v3-8bit"
                "Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit"
                "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit"
                "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit"
                "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit"
                "mlx-community/Dolphin3.0-Llama3.1-8B-8bit"
                "mlx-community/Llama-3.2-3B-Instruct-8bit"
                "mlx-community/gemma-4-31b-it-4bit"
                "lmstudio-community/Magistral-Small-2509-MLX-8bit"
                "mlx-community/Qwen3-VL-32B-Instruct-8bit"
                "mlx-community/gemma-4-e4b-it-4bit"            # ~5GB — Gemma 4 E4B vision+audio (replaces LLaVA)
                "mlx-community/gemma-4-26b-a4b-it-4bit"        # ~15GB — Gemma 4 26B A4B MoE research VLM
                "lmstudio-community/Phi-4-reasoning-plus-MLX-4bit" # ~7GB — Phi-4-reasoning-plus STEM/math
                # OCR (document ingestion)
                "mlx-community/GLM-OCR-bf16"                        # ~2GB — Zhipu GLM-OCR for scanned document ingestion
            )
            if [ "${PULL_HEAVY:-false}" = "true" ]; then
                _MLX_MODELS+=("mlx-community/Llama-3.3-70B-Instruct-4bit")
            fi
            _MTOTAL=${#_MLX_MODELS[@]}
            _MCOUNT=0
            _MFAILED=0
            for _model in "${_MLX_MODELS[@]}"; do
                _MCOUNT=$((_MCOUNT + 1))
                echo "  [$_MCOUNT/$_MTOTAL] $_model"
                if python3 -W ignore -c "
import warnings; warnings.filterwarnings('ignore')
from huggingface_hub import snapshot_download
snapshot_download('$_model', ignore_patterns=['*.md','*.txt','*.safetensors.index.json'])
" 2>/dev/null; then
                    echo "  ✅ Done"
                else
                    echo "  ⚠️  Failed (may not have new version)"
                    _MFAILED=$((_MFAILED + 1))
                fi
            done
            echo "  MLX: $((_MTOTAL - _MFAILED))/$_MTOTAL succeeded"
        else
            echo "  ⚠️  mlx-lm not installed — skipping MLX models"
            echo "     Install with: ./launch.sh install-mlx"
        fi
        echo ""
    elif [ "$_UPDATE_SKIP_MODELS" = "false" ]; then
        echo "[5/8] Skipping MLX models (not Apple Silicon)"
        echo ""
    fi

    # ── Step 6: Update ComfyUI (if installed) ────────────────────────────
    if [ "$_UPDATE_MODELS_ONLY" = "false" ]; then
        echo "[6/8] Checking ComfyUI..."
        _COMFYUI_DIR="${COMFYUI_DIR:-$HOME/ComfyUI}"
        if [ -d "$_COMFYUI_DIR/.git" ]; then
            echo "  Updating ComfyUI..."
            git -C "$_COMFYUI_DIR" pull --quiet 2>/dev/null && \
                echo "  ✅ ComfyUI updated" || echo "  ⚠️  ComfyUI pull failed"
            # Update VHS plugin
            _VHS_DIR="$_COMFYUI_DIR/custom_nodes/ComfyUI-VideoHelperSuite"
            if [ -d "$_VHS_DIR/.git" ]; then
                git -C "$_VHS_DIR" pull --quiet 2>/dev/null && \
                    echo "  ✅ VideoHelperSuite updated" || true
            fi
            # Upgrade ComfyUI deps
            if [ -f "$_COMFYUI_DIR/.venv/bin/pip" ]; then
                "$_COMFYUI_DIR/.venv/bin/pip" install --quiet --upgrade -r "$_COMFYUI_DIR/requirements.txt" 2>/dev/null || true
                echo "  ✅ ComfyUI dependencies upgraded"
            fi
        else
            echo "  ℹ️  ComfyUI not installed — skipping"
        fi
        echo ""
    fi

    # ── Step 7: Update Music MCP (if installed) ───────────────────────────
    if [ "$_UPDATE_MODELS_ONLY" = "false" ]; then
        echo "[7/8] Checking Music MCP..."
        _MUSIC_VENV="$HOME/.portal5/music/.venv"
        if [ -d "$_MUSIC_VENV" ]; then
            echo "  Upgrading Music MCP dependencies..."
            "$_MUSIC_VENV/bin/pip" install --quiet --upgrade \
                "torch>=2.1.0" \
                "torchaudio>=2.1.0" \
                "transformers>=4.40.0" \
                "scipy>=1.11.0" \
                "fastapi>=0.109.0" \
                "uvicorn[standard]>=0.27.0" \
                "httpx>=0.26.0" \
                "pyyaml>=6.0.1" \
                "starlette>=0.35.0" \
                "mcp>=1.0.0" \
                "fastmcp>=0.4.0" 2>/dev/null || true
            echo "  ✅ Music MCP dependencies upgraded"
            # Restart the service if running
            if [ "$(uname -s)" = "Darwin" ]; then
                launchctl stop com.portal5.music-mcp 2>/dev/null || true
                launchctl start com.portal5.music-mcp 2>/dev/null || true
            fi
        else
            echo "  ℹ️  Music MCP not installed — skipping"
        fi
        echo ""
    fi

    # ── Step 8: Re-seed Open WebUI + restart stack ────────────────────────
    if [ "$_UPDATE_MODELS_ONLY" = "false" ]; then
        echo "[8/8] Re-seeding Open WebUI + restarting stack..."
        cd "$COMPOSE_DIR"
        # Rebuild and restart all services with updated images
        docker compose up -d 2>/dev/null
        # Re-seed (force to pick up any new workspaces/personas)
        docker compose run --rm -e FORCE_RESEED=true openwebui-init 2>/dev/null || true
        echo "  ✅ Stack restarted + re-seeded"
        echo ""
    fi

    # ── Summary ───────────────────────────────────────────────────────────
    echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Update complete."
    echo ""
    if [ "$_UPDATE_MODELS_ONLY" = "false" ]; then
        echo "  Updated:"
        echo "    ✅ Portal 5 source (git pull)"
        echo "    ✅ Docker images (ollama, open-webui, searxng)"
        echo "    ✅ portal-pipeline + MCP server images (rebuild)"
    fi
    if [ "$_UPDATE_SKIP_MODELS" = "false" ]; then
        echo "    ✅ Ollama models (checked for updates)"
        if [ "$ARCH" = "arm64" ]; then
            echo "    ✅ MLX models (HuggingFace cache refreshed)"
        fi
    fi
    if [ "$_UPDATE_MODELS_ONLY" = "false" ]; then
        echo "    ✅ ComfyUI (if installed)"
        echo "    ✅ Music MCP (if installed)"
        echo "    ✅ Open WebUI presets (re-seeded)"
    fi
    echo ""
    echo "  Check status: ./launch.sh status"
    ;;

  clean)
    cd "$COMPOSE_DIR"
    echo "[portal-5] Stopping services..."
    docker compose down

    echo "[portal-5] Removing Open WebUI data volume..."
    # Remove only the open-webui-data volume — NOT ollama-models
    # Docker Compose prefixes volumes with the project directory name
    project_name=$(basename "$COMPOSE_DIR")
    docker volume rm "${project_name}_open-webui-data" 2>/dev/null \
        || docker volume rm "open-webui-data" 2>/dev/null \
        || echo "  Note: volume may not exist yet (first clean)"

    echo "[portal-5] Clean complete."
    echo "  Ollama models preserved (use clean-all to wipe everything)."
    echo "  Run ./launch.sh up for a fresh Open WebUI."
    ;;
  clean-all)
    cd "$COMPOSE_DIR"
    docker compose down -v --remove-orphans 2>/dev/null || true
    docker volume rm portal-5_ollama-models 2>/dev/null || true
    echo "[portal-5] Full clean complete (all volumes removed including Ollama models)."
    echo "WARNING: Models will re-download on next up (several GB)."
    ;;
  seed)
    cd "$COMPOSE_DIR"
    echo "[portal-5] Seeding Open WebUI (skips existing presets)..."
    docker compose run --rm openwebui-init
    echo "[portal-5] Seed complete. To force-refresh all presets: ./launch.sh reseed"
    ;;
  reseed)
    cd "$COMPOSE_DIR"
    echo "[portal-5] Force-reseeding Open WebUI (deletes and recreates all presets)..."
    echo "[portal-5] This updates persona prompts, workspace toolIds, and all model presets."
    FORCE_RESEED=true docker compose run --rm -e FORCE_RESEED=true openwebui-init
    echo "[portal-5] Reseed complete."
    ;;
  logs)
    cd "$COMPOSE_DIR"
    docker compose logs -f "${2:-portal-pipeline}"
    ;;
  status)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    _cmd_status
    ;;
  pull-models)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    # ── Ollama availability check ─────────────────────────────────────────────
    _ollama_cmd() {
        # Returns the ollama command prefix to use (native or docker exec)
        if command -v ollama &>/dev/null && curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
            echo "ollama"
        elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^portal5-ollama$"; then
            echo "docker exec portal5-ollama ollama"
        else
            echo ""
        fi
    }

    # ── Check if model is already loaded in Ollama ────────────────────────────
    _model_exists() {
        local model_name="$1"
        local ollama_cmd
        ollama_cmd=$(_ollama_cmd)
        [ -n "$ollama_cmd" ] && $ollama_cmd list 2>/dev/null | grep -q "^${model_name}"
    }

    # ── Refresh model (force re-pull even if present) ─────────────────────────
    _refresh_model() {
        local model="$1"
        local ollama_cmd
        ollama_cmd=$(_ollama_cmd)

        if [ -z "$ollama_cmd" ]; then
            echo "  ❌ No Ollama available. Run: ./launch.sh install-ollama"
            return 1
        fi

        # ── Native Ollama registry (no hf.co/ prefix) ────────────────────────
        if [[ "$model" != hf.co/* ]]; then
            echo "  Checking: $model"
            $ollama_cmd pull --force "$model"
            return $?
        fi

        # ── HuggingFace model ───────────────────────────────────────────────
        local repo_id="${model#hf.co/}"
        local actual_repo=""
        local filename=""
        local glob_pattern=""
        local ollama_name=""
        local gated="false"

        case "$repo_id" in
            AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF)
                actual_repo="AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF"
                filename="baronllm-llama3.1-v1-q6_k.gguf"
                ollama_name="baronllm:q6_k"
                gated="true"
                ;;
            segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF)
                actual_repo="segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF"
                filename="Lily-7B-Instruct-v0.2.Q4_K_M.gguf"
                ollama_name="lily-cybersecurity:7b-q4_k_m"
                ;;
            cognitivecomputations/Dolphin3.0-R1-Mistral-24B-GGUF)
                actual_repo="bartowski/cognitivecomputations_Dolphin3.0-R1-Mistral-24B-GGUF"
                filename="cognitivecomputations_Dolphin3.0-R1-Mistral-24B-Q4_K_M.gguf"
                ollama_name="dolphin3-r1-mistral:24b-q4_k_m"
                ;;
            WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF)
                actual_repo="dranger003/WhiteRabbitNeo-33B-v1.5-iMat.GGUF"
                filename="ggml-whiterabbitneo-33b-v1.5-q4_k_m.gguf"
                ollama_name="whiterabbitneo:33b-v1.5-q4_k_m"
                ;;
            unsloth/GLM-4.7-Flash-GGUF)
                actual_repo="unsloth/GLM-4.7-Flash-GGUF"
                filename="GLM-4.7-Flash-Q4_K_M.gguf"
                ollama_name="glm-4.7-flash:q4_k_m"
                ;;
            deepseek-ai/DeepSeek-Coder-V2-Lite-Base-GGUF)
                actual_repo="bartowski/DeepSeek-Coder-V2-Lite-Base-GGUF"
                filename="DeepSeek-Coder-V2-Lite-Base-Q4_K_M.gguf"
                ollama_name="deepseek-coder-v2-lite:q4_k_m"
                ;;
            deepseek-ai/DeepSeek-R1-32B-GGUF)
                actual_repo="bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF"
                filename="DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf"
                ollama_name="deepseek-r1:32b-q4_k_m"
                ;;
            cognitivecomputations/dolphin-3-llama3-70b-GGUF)
                actual_repo="bartowski/dolphin-2.9.1-llama3-70b-GGUF"
                filename="dolphin-2.9.1-llama3-70b-Q4_K_M.gguf"
                ollama_name="dolphin-llama3:70b-q4_k_m"
                ;;
            meta-llama/Meta-Llama-3.3-70B-GGUF)
                actual_repo="bartowski/Llama-3.3-70B-Instruct-GGUF"
                filename="Llama-3.3-70B-Instruct-Q4_K_M.gguf"
                ollama_name="llama3.3:70b-q4_k_m"
                ;;
            *)
                echo "  ⚠️  No verified spec for $repo_id — attempting direct ollama pull"
                $ollama_cmd pull --force "$model"
                return $?
                ;;
        esac

        if [ "$gated" = "true" ] && [ -z "${HF_TOKEN:-}" ]; then
            echo "  ❌ $actual_repo requires HF_TOKEN (gated repo)"
            return 1
        fi

        _ensure_hf_cli

        echo "  Re-downloading: https://huggingface.co/$actual_repo"
        local _dl_dir="${OLLAMA_MODELS:-$HOME/.ollama/models}/../model_imports/${actual_repo//\//_}"
        local _hf_err
        _hf_err=$(mktemp)
        local gguf_path=""
        if [ -n "$filename" ]; then
            mkdir -p "$_dl_dir"
            gguf_path=$(HF_TOKEN="${HF_TOKEN:-}" \
                DL_REPO="$actual_repo" \
                DL_FILE="$filename" \
                DL_DIR="$_dl_dir" \
                python3 -W ignore -c "
import os, sys, warnings
warnings.filterwarnings('ignore')
from huggingface_hub import hf_hub_download
token = os.environ.get('HF_TOKEN') or None
try:
    path = hf_hub_download(
        repo_id=os.environ['DL_REPO'],
        filename=os.environ['DL_FILE'],
        token=token,
        local_dir=os.environ['DL_DIR'],
    )
    print(path)
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}', file=sys.stderr)
    sys.exit(1)
" 2>"$_hf_err")
        fi

        if [ -z "$gguf_path" ] || [ ! -f "$gguf_path" ]; then
            echo "  ❌ Download failed for $actual_repo"
            [ -s "$_hf_err" ] && echo "  Error detail: $(cat "$_hf_err")"
            rm -f "$_hf_err"
            return 1
        fi
        rm -f "$_hf_err"
        echo "  ✅ Downloaded: $(basename "$gguf_path")"
        echo "  Re-importing as: $ollama_name"

        local modelfile
        modelfile=$(mktemp)
        printf 'FROM %s\nPARAMETER temperature 0.7\nPARAMETER num_ctx 8192\n' "$gguf_path" > "$modelfile"

        if $ollama_cmd create --force "$ollama_name" -f "$modelfile"; then
            echo "  ✅ Refreshed: $ollama_name"
            rm -f "$modelfile"
            [ -d "${_dl_dir:-}" ] && rm -rf "$_dl_dir"
            return 0
        else
            echo "  ❌ ollama create --force failed"
            rm -f "$modelfile"
            return 1
        fi
    }

    # ── HuggingFace CLI availability ──────────────────────────────────────────
    _ensure_hf_cli() {
        # Check importability via python3 — avoids PATH issues with the binary
        if ! python3 -c "import huggingface_hub" &>/dev/null 2>&1; then
            echo "  Installing huggingface_hub..."
            pip3 install huggingface_hub --quiet --break-system-packages 2>/dev/null || \
            pip3 install huggingface_hub --quiet
        fi
        # Authenticate if token provided — use python API (no binary PATH needed)
        if [ -n "${HF_TOKEN:-}" ]; then
            python3 -W ignore -c "
from huggingface_hub import login
import warnings; warnings.filterwarnings('ignore')
try:
    login(token='${HF_TOKEN}', add_to_git_credential=False)
except Exception:
    pass
" 2>/dev/null || true
        fi
    }

    # ── Main model pull function ──────────────────────────────────────────────
    # Routes hf.co/ models through huggingface-cli + ollama create (bypasses
    # Ollama's broken cross-host auth redirect for HuggingFace models).
    # Native Ollama registry models use ollama pull directly.
    _pull_model() {
        local model="$1"
        local ollama_cmd
        ollama_cmd=$(_ollama_cmd)

        if [ -z "$ollama_cmd" ]; then
            echo "  ❌ No Ollama available. Run: ./launch.sh install-ollama"
            return 1
        fi

        # ── Native Ollama registry (no hf.co/ prefix) ────────────────────────
        if [[ "$model" != hf.co/* ]]; then
            if _model_exists "$model"; then
                echo "  ✅ Already pulled: $model — skipping"
                return 0
            fi
            $ollama_cmd pull "$model"
            return $?
        fi

        # ── HuggingFace model: download via Python huggingface_hub + import ──
        # This bypasses Ollama's broken cross-host auth redirect.
        # Uses snapshot_download() which correctly returns the actual cache path
        # regardless of ~/.cache vs --local-dir quirks.

        local repo_id="${model#hf.co/}"

        # ── Per-model spec: actual_repo, filename (or glob), ollama_name ─────
        local actual_repo=""
        local filename=""       # exact filename — preferred
        local glob_pattern=""   # fallback when exact name unverifiable
        local ollama_name=""
        local gated="false"

        case "$repo_id" in
            # ── Security models ──────────────────────────────────────────────
            AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF)
                # Gated: accept terms at https://huggingface.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF
                actual_repo="AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF"
                filename="baronllm-llama3.1-v1-q6_k.gguf"
                ollama_name="baronllm:q6_k"
                gated="true"
                ;;
            segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF)
                # Source: https://huggingface.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF
                actual_repo="segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF"
                filename="Lily-7B-Instruct-v0.2.Q4_K_M.gguf"
                ollama_name="lily-cybersecurity:7b-q4_k_m"
                ;;
            cognitivecomputations/Dolphin3.0-R1-Mistral-24B-GGUF)
                # Source: https://huggingface.co/bartowski/cognitivecomputations_Dolphin3.0-R1-Mistral-24B-GGUF/tree/main
                actual_repo="bartowski/cognitivecomputations_Dolphin3.0-R1-Mistral-24B-GGUF"
                filename="cognitivecomputations_Dolphin3.0-R1-Mistral-24B-Q4_K_M.gguf"
                ollama_name="dolphin3-r1-mistral:24b-q4_k_m"
                ;;
            WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF)
                # Source: https://huggingface.co/dranger003/WhiteRabbitNeo-33B-v1.5-iMat.GGUF
                # Q4_K_M imatrix quant — 19.9 GB
                actual_repo="dranger003/WhiteRabbitNeo-33B-v1.5-iMat.GGUF"
                filename="ggml-whiterabbitneo-33b-v1.5-q4_k_m.gguf"
                ollama_name="whiterabbitneo:33b-v1.5-q4_k_m"
                ;;

            # ── Coding models ────────────────────────────────────────────────
            unsloth/GLM-4.7-Flash-GGUF)
                # Source: https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/blob/main/GLM-4.7-Flash-Q4_K_M.gguf
                actual_repo="unsloth/GLM-4.7-Flash-GGUF"
                filename="GLM-4.7-Flash-Q4_K_M.gguf"
                ollama_name="glm-4.7-flash:q4_k_m"
                ;;
            deepseek-ai/DeepSeek-Coder-V2-Lite-Base-GGUF)
                # Source: https://huggingface.co/bartowski/DeepSeek-Coder-V2-Lite-Base-GGUF
                actual_repo="bartowski/DeepSeek-Coder-V2-Lite-Base-GGUF"
                filename="DeepSeek-Coder-V2-Lite-Base-Q4_K_M.gguf"
                ollama_name="deepseek-coder-v2-lite:q4_k_m"
                ;;
            MiniMaxAI/MiniMax-M2.1-GGUF)
                # Q4_K_M = 138 GB — does not fit in 48 GB unified memory
                echo "  ⚠️  Skipping MiniMax-M2.1: smallest useful quant is 138 GB (requires ~160 GB RAM)"
                echo "     To pull manually if you have sufficient RAM:"
                echo "     huggingface-cli download bartowski/MiniMaxAI_MiniMax-M2.1-GGUF --include 'MiniMaxAI_MiniMax-M2.1-Q4_K_M.gguf'"
                return 0
                ;;

            # ── Reasoning models ─────────────────────────────────────────────
            deepseek-ai/DeepSeek-R1-32B-GGUF)
                # NOTE: deepseek-ai/DeepSeek-R1-32B-GGUF does NOT exist on HuggingFace.
                # The actual model is DeepSeek-R1-Distill-Qwen-32B.
                # Source: https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF
                actual_repo="bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF"
                filename="DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf"
                ollama_name="deepseek-r1:32b-q4_k_m"
                ;;

            # ── Heavy 70B models (PULL_HEAVY=true) ───────────────────────────
            cognitivecomputations/dolphin-3-llama3-70b-GGUF)
                # No reliable GGUF hosting for this exact repo.
                # Source: https://huggingface.co/bartowski/dolphin-2.9.1-llama-3-70b-GGUF
                actual_repo="bartowski/dolphin-2.9.1-llama-3-70b-GGUF"
                filename="dolphin-2.9.1-llama-3-70b-Q4_K_M.gguf"
                ollama_name="dolphin-llama3:70b-q4_k_m"
                ;;
            meta-llama/Meta-Llama-3.3-70B-GGUF)
                # Gated at meta-llama; use bartowski's public rehost.
                # Source: https://huggingface.co/bartowski/Llama-3.3-70B-Instruct-GGUF
                actual_repo="bartowski/Llama-3.3-70B-Instruct-GGUF"
                filename="Llama-3.3-70B-Instruct-Q4_K_M.gguf"
                ollama_name="llama3.3:70b-q4_k_m"
                ;;

            *)
                echo "  ⚠️  No verified spec for $repo_id — attempting direct ollama pull"
                echo "     (May fail due to Ollama hf.co auth redirect issue)"
                $ollama_cmd pull "$model"
                return $?
                ;;
        esac

        # ── Skip if already registered in Ollama ─────────────────────────────
        if _model_exists "$ollama_name"; then
            echo "  ✅ Already in Ollama as $ollama_name — skipping"
            return 0
        fi

        # ── Token check for gated repos ───────────────────────────────────────
        if [ "$gated" = "true" ] && [ -z "${HF_TOKEN:-}" ]; then
            echo "  ❌ $actual_repo requires HF_TOKEN (gated repo)"
            echo "     1. Accept terms: https://huggingface.co/$actual_repo"
            echo "     2. Create token: https://huggingface.co/settings/tokens (Read scope)"
            echo "     3. Add to .env:  HF_TOKEN=hf_..."
            return 1
        fi

        # ── Ensure huggingface_hub is installed ───────────────────────────────
        _ensure_hf_cli

        # ── Download via Python snapshot_download ─────────────────────────────
        # snapshot_download returns the actual cached path — works correctly
        # whether files end up in --local-dir or ~/.cache/huggingface.
        # This also handles the case where --include glob ignores --local-dir.

        echo "  Downloading from: https://huggingface.co/$actual_repo"

        local gguf_path=""
        local _dl_dir="${OLLAMA_MODELS:-$HOME/.ollama/models}/../model_imports/${actual_repo//\//_}"
        if [ -n "$filename" ]; then
            echo "  File: $filename"
            mkdir -p "$_dl_dir"
            gguf_path=$(HF_TOKEN="${HF_TOKEN:-}" \
                DL_REPO="$actual_repo" \
                DL_FILE="$filename" \
                DL_DIR="$_dl_dir" \
                python3 -W ignore -c "
import os, sys, warnings
warnings.filterwarnings('ignore')
from huggingface_hub import hf_hub_download
token = os.environ.get('HF_TOKEN') or None
try:
    path = hf_hub_download(
        repo_id=os.environ['DL_REPO'],
        filename=os.environ['DL_FILE'],
        token=token,
        local_dir=os.environ['DL_DIR'],
    )
    print(path)
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}', file=sys.stderr)
    sys.exit(1)
")
        elif [ -n "$glob_pattern" ]; then
            echo "  Pattern: $glob_pattern (listing repo to find file)"
            mkdir -p "$_dl_dir"
            gguf_path=$(HF_TOKEN="${HF_TOKEN:-}" \
                DL_REPO="$actual_repo" \
                DL_GLOB="$glob_pattern" \
                DL_DIR="$_dl_dir" \
                python3 -W ignore -c "
import os, sys, fnmatch, warnings
warnings.filterwarnings('ignore')
from huggingface_hub import hf_hub_download, list_repo_files
token = os.environ.get('HF_TOKEN') or None
try:
    files = list(list_repo_files(os.environ['DL_REPO'], token=token))
    pat = os.environ['DL_GLOB']
    # Case-insensitive match to handle repos that use lowercase quant names
    matches = [f for f in files if fnmatch.fnmatch(f.lower(), pat.lower()) and f.endswith('.gguf')]
    if not matches:
        print(f'ERROR: no .gguf files matching {pat} in repo. Available: {[f for f in files if f.endswith(\".gguf\")]}', file=sys.stderr)
        sys.exit(1)
    target = next((f for f in matches if 'q4_k_m.gguf' in f.lower()), matches[0])
    path = hf_hub_download(
        repo_id=os.environ['DL_REPO'],
        filename=target,
        token=token,
        local_dir=os.environ['DL_DIR'],
    )
    print(path)
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}', file=sys.stderr)
    sys.exit(1)
")
        fi

        if [ -z "$gguf_path" ] || [ ! -f "$gguf_path" ]; then
            echo "  ❌ Download failed for $actual_repo"
            echo "     Retry manually:"
            echo "       huggingface-cli download $actual_repo ${filename:-} --local-dir ~/Downloads"
            echo "     Then import: ./launch.sh import-gguf ~/Downloads/${filename:-model.gguf} $ollama_name"
            return 1
        fi

        echo "  ✅ Downloaded: $(basename "$gguf_path")"
        echo "  Importing as: $ollama_name"

        local modelfile
        modelfile=$(mktemp)
        printf 'FROM %s\nPARAMETER temperature 0.7\nPARAMETER num_ctx 8192\n' "$gguf_path" > "$modelfile"

        # Bug C fix: use _ollama_cmd not bare 'ollama'
        if $ollama_cmd create "$ollama_name" -f "$modelfile"; then
            echo "  ✅ Imported: $ollama_name"
            rm -f "$modelfile"
            # Clean download cache — Ollama has its own copy in blob store
            [ -d "${_dl_dir:-}" ] && rm -rf "$_dl_dir" && echo "  ℹ️  Freed download cache"
            return 0
        else
            echo "  ❌ ollama create failed — GGUF kept at: $gguf_path"
            rm -f "$modelfile"
            return 1
        fi
    }

    echo "=== Portal 5: Pulling AI models ==="
    echo "This may take 30-90 minutes depending on connection speed."
    echo ""

    # ── HuggingFace authentication — required for hf.co/ models ─────────────
    echo "[portal-5] ℹ️  HuggingFace models: using huggingface-cli download (bypasses Ollama auth issues)"
    echo "   For gated models (BaronLLM etc.), you must first accept terms at huggingface.co"
    echo "   then set HF_TOKEN in .env:"
    echo "     1. https://huggingface.co/<repo> → Accept conditions"
    echo "     2. https://huggingface.co/settings/tokens → Create token (read scope)"
    echo "     3. Add to .env:  HF_TOKEN=hf_..."
    echo ""

    MODELS=(
        # ── Core ──────────────────────────────────────────────────────────
        "${DEFAULT_MODEL:-dolphin-llama3:8b}"
        "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF"
        "nomic-embed-text:latest"
        # ── Security ─────────────────────────────────────────────────────
        "hf.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF"
        "hf.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF"
        "hf.co/cognitivecomputations/Dolphin3.0-R1-Mistral-24B-GGUF"
        "xploiter/the-xploiter"
        "hf.co/WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF"
        "huihui_ai/baronllm-abliterated"
        "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0"
        # ── Coding ───────────────────────────────────────────────────────
        # NOTE: Qwen3-Coder-Next GGUF removed — sharded GGUF incompatible with Ollama
        # Use MLX backend instead: ./launch.sh install-mlx && ./launch.sh pull-mlx-models
        "qwen3.5:9b"                   # Fast dense: 8-12GB, ~30-50 t/s on M4
        "qwen3-coder:30b"              # 30B-A3B MoE (3B active), 19GB
        "hf.co/unsloth/GLM-4.7-Flash-GGUF"
        "hf.co/deepseek-ai/DeepSeek-Coder-V2-Lite-Base-GGUF"
        "deepseek-coder-v2:16b-lite-instruct-q4_K_M"
        "devstral:24b"
        # ── Reasoning / Research ──────────────────────────────────────────
        "hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF"
        "huihui_ai/tongyi-deepresearch-abliterated"
        # ── Vision ───────────────────────────────────────────────────────
        "qwen3-vl:32b"
        "llava:7b"
    )

    total=${#MODELS[@]}
    count=0
    failed=0
    for model in "${MODELS[@]}"; do
        count=$((count + 1))
        echo "[$count/$total] $model"
        if _pull_model "$model"; then
            echo "  ✅ Done"
        else
            failed=$((failed + 1))
        fi
        echo ""
    done

    # Heavy 70B models — gated behind PULL_HEAVY=true
    if [ "${PULL_HEAVY:-false}" = "true" ]; then
        echo "Pulling heavy 70B models (PULL_HEAVY=true)..."
        for model in \
            "hf.co/cognitivecomputations/dolphin-3-llama3-70b-GGUF" \
            "hf.co/meta-llama/Meta-Llama-3.3-70B-GGUF"; do
            echo "  Pulling: $model (~35GB)"
            _pull_model "$model" && echo "  ✅ Done" || { echo "  ❌ Failed"; failed=$((failed + 1)); }
        done
    else
        echo "Skipping 70B models (set PULL_HEAVY=true in .env to pull ~35GB models)"
        echo "  - hf.co/cognitivecomputations/dolphin-3-llama3-70b-GGUF"
        echo "  - hf.co/meta-llama/Meta-Llama-3.3-70B-GGUF"
    fi

    echo ""
    echo "=== Pull complete: $((total - failed))/$total succeeded ==="
    ;;

  refresh-models)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    _ollama_cmd() {
        if command -v ollama &>/dev/null && curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
            echo "ollama"
        elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^portal5-ollama$"; then
            echo "docker exec portal5-ollama ollama"
        else
            echo ""
        fi
    }

    _ensure_hf_cli() {
        if ! python3 -c "import huggingface_hub" &>/dev/null 2>&1; then
            echo "  Installing huggingface_hub..."
            pip3 install huggingface_hub --quiet --break-system-packages 2>/dev/null || \
            pip3 install huggingface_hub --quiet
        fi
        if [ -n "${HF_TOKEN:-}" ]; then
            python3 -W ignore -c "
from huggingface_hub import login
import warnings; warnings.filterwarnings('ignore')
try:
    login(token='${HF_TOKEN}', add_to_git_credential=False)
except Exception:
    pass
" 2>/dev/null || true
        fi
    }

    echo "=== Portal 5: Refreshing models (only downloads changes) ==="
    echo "Each model will be checked — unchanged models will say 'up to date'."
    echo ""

    MODELS=(
        "${DEFAULT_MODEL:-dolphin-llama3:8b}"
        "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF"
        "nomic-embed-text:latest"
        "hf.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF"
        "hf.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF"
        "hf.co/cognitivecomputations/Dolphin3.0-R1-Mistral-24B-GGUF"
        "xploiter/the-xploiter"
        "hf.co/WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF"
        "huihui_ai/baronllm-abliterated"
        "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0"
        "qwen3.5:9b"
        "qwen3-coder:30b"
        "hf.co/unsloth/GLM-4.7-Flash-GGUF"
        "hf.co/deepseek-ai/DeepSeek-Coder-V2-Lite-Base-GGUF"
        "deepseek-coder-v2:16b-lite-instruct-q4_K_M"
        "devstral:24b"
        "hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF"
        "huihui_ai/tongyi-deepresearch-abliterated"
        "qwen3-vl:32b"
        "llava:7b"
    )

    if [ "${PULL_HEAVY:-false}" = "true" ]; then
        MODELS+=(
            "hf.co/cognitivecomputations/dolphin-3-llama3-70b-GGUF"
            "hf.co/meta-llama/Meta-Llama-3.3-70B-GGUF"
        )
    fi

    total=${#MODELS[@]}
    count=0
    failed=0
    for model in "${MODELS[@]}"; do
        count=$((count + 1))
        echo "[$count/$total] $model"
        if _refresh_model "$model"; then
            echo "  ✅ Done"
        else
            failed=$((failed + 1))
        fi
        echo ""
    done

    echo "=== Refresh complete: $((total - failed))/$total succeeded ==="
    ;;

  add-user)
    # Usage: ./launch.sh add-user <email> [name] [role]
    # role: user (default) | admin | pending
    local_email="${2:-}"
    local_name="${3:-New User}"
    local_role="${4:-user}"

    if [ -z "$local_email" ]; then
        echo "Usage: ./launch.sh add-user <email> [name] [role]"
        echo ""
        echo "  email   Required. User's email address."
        echo "  name    Display name (default: 'New User')"
        echo "  role    user | admin | pending (default: user)"
        echo ""
        echo "Examples:"
        echo "  ./launch.sh add-user alice@team.local 'Alice Smith'"
        echo "  ./launch.sh add-user bob@team.local 'Bob Jones' admin"
        exit 1
    fi

    set -a; source "$ENV_FILE"; set +a

    # Generate a temporary password for the user
    temp_pass=$(generate_secret | head -c 16)

    echo "[portal-5] Creating user: $local_email ($local_role)"

    response=$(curl -s -X POST \
        "${OPENWEBUI_URL:-http://localhost:8080}/api/v1/auths/add" \
        -H "Authorization: Bearer $(get_admin_token)" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"$local_name\",\"email\":\"$local_email\",\"password\":\"$temp_pass\",\"role\":\"$local_role\"}" \
        2>&1)

    if echo "$response" | grep -q '"id"'; then
        echo ""
        echo "  ╔══════════════════════════════════════════════════════╗"
        echo "  ║  User created — share these credentials              ║"
        echo "  ║                                                      ║"
        echo "  ║  Open WebUI: http://localhost:8080                   ║"
        printf "  ║  Email:    %-41s ║\n" "$local_email"
        printf "  ║  Password: %-41s ║\n" "$temp_pass"
        echo "  ║  Role:     $local_role                                           ║"
        echo "  ╚══════════════════════════════════════════════════════╝"
        echo ""
        echo "  User must change their password on first login."
    else
        echo "  Failed to create user."
        echo "  Response: $response"
        echo ""
        echo "  Is the stack running? ./launch.sh status"
        exit 1
    fi
    ;;

  list-users)
    set -a; source "$ENV_FILE"; set +a
    echo "[portal-5] Registered users:"
    curl -s \
        "${OPENWEBUI_URL:-http://localhost:8080}/api/v1/users/" \
        -H "Authorization: Bearer $(get_admin_token)" \
        2>/dev/null | python3 -c "
import json, sys
users = json.load(sys.stdin)
users = users if isinstance(users, list) else users.get('data', [])
print(f'  {len(users)} user(s):')
for u in users:
    role = u.get('role','?')
    name = u.get('name','?')
    email = u.get('email','?')
    print(f'  [{role:8s}] {name} <{email}>')
" 2>/dev/null || echo "  Could not fetch users — is stack running?"
    ;;

  install-ollama)
    echo "=== Installing Ollama natively (Apple Silicon / Metal GPU) ==="
    ARCH=$(uname -m)

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  Non-Apple-Silicon detected ($ARCH)."
        echo "  For Linux: curl -fsSL https://ollama.com/install.sh | sh"
        echo "  Then run:  ./launch.sh up --profile docker-ollama"
        exit 0
    fi

    if ! command -v brew &>/dev/null; then
        echo "  ❌ Homebrew not found. Install it first:"
        echo '     /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        echo "  Then re-run: ./launch.sh install-ollama"
        exit 1
    fi

    if command -v ollama &>/dev/null; then
        echo "  ✅ Ollama already installed: $(ollama --version 2>/dev/null | head -1 || echo 'installed')"
    else
        echo "  Installing Ollama via brew..."
        brew install ollama
        echo "  ✅ Ollama installed"
    fi

    echo "  Starting Ollama service (auto-starts on login)..."
    brew services start ollama
    sleep 3

    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        echo "  ✅ Ollama is running at http://localhost:11434"
        echo "  ✅ Will auto-start on login via brew services"
    else
        echo "  ⚠️  Ollama installed but not yet responding — wait a moment then check:"
        echo "     curl http://localhost:11434/api/tags"
    fi

    echo ""
    echo "Next steps:"
    echo "  ./launch.sh up           — start Portal 5 stack"
    echo "  ./launch.sh pull-models  — pull AI models (30-90 min)"
    ;;

  install-comfyui)
    echo "=== Installing ComfyUI natively (Apple Silicon / Metal GPU) ==="
    ARCH=$(uname -m)
    COMFYUI_DIR="${COMFYUI_DIR:-$HOME/ComfyUI}"

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  Non-Apple-Silicon detected ($ARCH)."
        echo "  For Linux with NVIDIA: use Docker ComfyUI via --profile docker-comfyui"
        echo "  Or install manually: https://github.com/comfyanonymous/ComfyUI"
        exit 0
    fi

    # ── Install Python dependency manager ────────────────────────────────────
    if ! command -v python3 &>/dev/null; then
        echo "  ❌ python3 not found. Install via brew: brew install python"
        exit 1
    fi

    # ── Clone ComfyUI ─────────────────────────────────────────────────────────
    if [ -d "$COMFYUI_DIR" ]; then
        echo "  ✅ ComfyUI already cloned at $COMFYUI_DIR"
        echo "  Updating..."
        git -C "$COMFYUI_DIR" pull --quiet
    else
        echo "  Cloning ComfyUI to $COMFYUI_DIR..."
        git clone https://github.com/comfyanonymous/ComfyUI "$COMFYUI_DIR"
        echo "  ✅ ComfyUI cloned"
    fi

    # ── Install Python dependencies ───────────────────────────────────────────
    echo "  Installing Python dependencies (this may take a few minutes)..."
    cd "$COMFYUI_DIR"

    # Use a venv to avoid system Python conflicts
    if [ ! -d "$COMFYUI_DIR/.venv" ]; then
        python3 -m venv "$COMFYUI_DIR/.venv"
    fi

    "$COMFYUI_DIR/.venv/bin/pip" install --quiet --upgrade pip
    "$COMFYUI_DIR/.venv/bin/pip" install --quiet -r requirements.txt
    # PyTorch for Apple Silicon (MPS)
    "$COMFYUI_DIR/.venv/bin/pip" install --quiet \
        torch torchvision torchaudio
    echo "  ✅ Dependencies installed"

    # ── Create model directories ──────────────────────────────────────────────
    mkdir -p "$COMFYUI_DIR/models/checkpoints"
    mkdir -p "$COMFYUI_DIR/models/video"
    mkdir -p "$COMFYUI_DIR/output"
    echo "  ✅ Model directories created"

    # ── Create a launch script for ComfyUI ───────────────────────────────────
    cat > "$COMFYUI_DIR/start.sh" << 'COMFY_START'
#!/bin/bash
# Start ComfyUI with Metal (MPS) acceleration for Apple Silicon
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
.venv/bin/python main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --force-fp16
COMFY_START
    chmod +x "$COMFYUI_DIR/start.sh"

    # ── Register as a launchd service (auto-start on login) ──────────────────
    PLIST_PATH="$HOME/Library/LaunchAgents/com.portal5.comfyui.plist"
    cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.portal5.comfyui</string>
    <key>ProgramArguments</key>
    <array>
        <string>$COMFYUI_DIR/.venv/bin/python</string>
        <string>$COMFYUI_DIR/main.py</string>
        <string>--listen</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8188</string>
        <string>--force-fp16</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$COMFYUI_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/.portal5/logs/comfyui.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.portal5/logs/comfyui-error.log</string>
</dict>
</plist>
PLIST

    mkdir -p "$HOME/.portal5/logs"

    # ── Install ComfyUI-VideoHelperSuite (required for VHS_VideoCombine video output) ──
    echo "  Installing ComfyUI-VideoHelperSuite (video output node)..."
    VHS_DIR="$COMFYUI_DIR/custom_nodes/ComfyUI-VideoHelperSuite"
    if [ -d "$VHS_DIR" ]; then
        echo "  ✅ ComfyUI-VideoHelperSuite already installed — updating"
        git -C "$VHS_DIR" pull --quiet
    else
        git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git "$VHS_DIR"
        echo "  ✅ ComfyUI-VideoHelperSuite installed"
    fi
    if [ -f "$VHS_DIR/requirements.txt" ]; then
        "$COMFYUI_DIR/.venv/bin/pip" install --quiet -r "$VHS_DIR/requirements.txt"
    fi

    # Load the service
    launchctl load "$PLIST_PATH" 2>/dev/null || true
    launchctl start com.portal5.comfyui 2>/dev/null || true
    sleep 5

    if curl -s http://localhost:8188/system_stats &>/dev/null; then
        echo "  ✅ ComfyUI is running at http://localhost:8188"
        echo "  ✅ Auto-starts on login via launchd"
    else
        echo "  ⚠️  ComfyUI installed but not yet responding."
        echo "  Logs: $HOME/.portal5/logs/comfyui.log"
        echo "  Or start manually: $COMFYUI_DIR/start.sh"
    fi

    echo ""
    echo "Next steps:"
    echo "  ./launch.sh download-comfyui-models   — download image/video models"
    echo "  ./launch.sh up                        — start Portal 5 stack"
    ;;

  install-music)
    echo "=== Installing Music MCP natively (Apple Silicon / MPS) ==="
    ARCH=$(uname -m)
    MUSIC_DIR="$HOME/.portal5/music"
    MUSIC_VENV="$MUSIC_DIR/.venv"
    MUSIC_LOG="$HOME/.portal5/logs/music-mcp.log"
    MUSIC_PORT="${MUSIC_HOST_PORT:-8912}"

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  Non-Apple-Silicon detected ($ARCH)."
        echo "  Music MCP is designed for native macOS/MPS. On x86_64+CUDA, it can"
        echo "  still run natively but Docker is also an option."
        echo "  Continuing anyway..."
    fi

    if ! command -v python3 &>/dev/null; then
        echo "  ❌ python3 not found. Install via brew: brew install python"
        exit 1
    fi

    # ── Create venv ───────────────────────────────────────────────────────────
    mkdir -p "$MUSIC_DIR"
    mkdir -p "$HOME/.portal5/logs"
    if [ ! -d "$MUSIC_VENV" ]; then
        echo "  Creating Python venv at $MUSIC_VENV..."
        python3 -m venv "$MUSIC_VENV"
    else
        echo "  ✅ Venv already exists at $MUSIC_VENV"
    fi

    # ── Install dependencies ──────────────────────────────────────────────────
    echo "  Installing dependencies (torch, transformers, mcp — this may take a few minutes)..."
    "$MUSIC_VENV/bin/pip" install --quiet --upgrade pip
    "$MUSIC_VENV/bin/pip" install --quiet \
        "torch>=2.1.0" \
        "torchaudio>=2.1.0" \
        "transformers>=4.40.0" \
        "scipy>=1.11.0" \
        "fastapi>=0.109.0" \
        "uvicorn[standard]>=0.27.0" \
        "httpx>=0.26.0" \
        "pyyaml>=6.0.1" \
        "starlette>=0.35.0" \
        "mcp>=1.0.0" \
        "fastmcp>=0.4.0"
    echo "  ✅ Dependencies installed"

    # ── HuggingFace cache dir ─────────────────────────────────────────────────
    HF_CACHE="${HF_HOME:-$MUSIC_DIR/hf_cache}"
    mkdir -p "$HF_CACHE"
    echo "  HuggingFace cache: $HF_CACHE"
    echo "  (MusicGen models download here on first generate_music call)"

    # ── Create start script ───────────────────────────────────────────────────
    cat > "$MUSIC_DIR/start.sh" << MUSIC_START
#!/bin/bash
# Start Music MCP natively for MPS acceleration on Apple Silicon
PORTAL_ROOT="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")/../../projects/portal-5" 2>/dev/null && pwd)"
# Fallback: walk up to find portal_mcp
if [ ! -d "\$PORTAL_ROOT/portal_mcp" ]; then
    PORTAL_ROOT="\$(python3 -c "import subprocess, os; r=subprocess.run(['git','-C',os.path.dirname(os.path.abspath('\$0')),  'rev-parse','--show-toplevel'],capture_output=True,text=True); print(r.stdout.strip())" 2>/dev/null)"
fi
export PYTHONPATH="\$PORTAL_ROOT"
export HF_HOME="${HF_CACHE}"
export TRANSFORMERS_CACHE="${HF_CACHE}"
export OUTPUT_DIR="\${AI_OUTPUT_DIR:-\$HOME/AI_Output}"
export MUSIC_MCP_PORT="${MUSIC_PORT}"
mkdir -p "\$OUTPUT_DIR"
exec "$MUSIC_VENV/bin/python" -m portal_mcp.generation.music_mcp
MUSIC_START
    chmod +x "$MUSIC_DIR/start.sh"
    echo "  ✅ Start script: $MUSIC_DIR/start.sh"

    # ── Register launchd plist (auto-start on login) ──────────────────────────
    PLIST_PATH="$HOME/Library/LaunchAgents/com.portal5.music-mcp.plist"
    cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.portal5.music-mcp</string>
    <key>ProgramArguments</key>
    <array>
        <string>$MUSIC_DIR/start.sh</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>$PORTAL_ROOT</string>
        <key>HF_HOME</key>
        <string>$HF_CACHE</string>
        <key>TRANSFORMERS_CACHE</key>
        <string>$HF_CACHE</string>
        <key>OUTPUT_DIR</key>
        <string>${AI_OUTPUT_DIR:-$HOME/AI_Output}</string>
        <key>MUSIC_MCP_PORT</key>
        <string>$MUSIC_PORT</string>
    </dict>
    <key>WorkingDirectory</key>
    <string>$PORTAL_ROOT</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$MUSIC_LOG</string>
    <key>StandardErrorPath</key>
    <string>$MUSIC_LOG</string>
</dict>
</plist>
PLIST
    launchctl load "$PLIST_PATH" 2>/dev/null || true
    echo "  ✅ Registered as launchd service: com.portal5.music-mcp"

    echo ""
    echo "=== Music MCP installed ==="
    echo "  Port:    :$MUSIC_PORT"
    echo "  Venv:    $MUSIC_VENV"
    echo "  Cache:   $HF_CACHE"
    echo "  Log:     $MUSIC_LOG"
    echo "  Start:   ./launch.sh up  (auto-started)"
    echo "  Models download on first call (~300MB small, ~1.5GB medium)"
    echo ""
    echo "Next steps:"
    echo "  ./launch.sh up   — start Portal 5 (Music MCP starts automatically)"
    ;;

  install-mlx)
    echo "=== Installing MLX dual-server (Apple Silicon native inference) ==="
    ARCH=$(uname -m)

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  MLX is Apple Silicon only. On Linux, Ollama GGUF handles inference."
        exit 0
    fi

    if ! command -v python3 &>/dev/null; then
        echo "  ❌ python3 required. Install: brew install python"
        exit 1
    fi

    echo "  Installing mlx-vlm (supports Qwen3.5 VLM + vision models)..."
    pip3 install "mlx-vlm" --upgrade --quiet 2>/dev/null || \
        pip3 install "mlx-vlm" --upgrade --quiet --break-system-packages
    # mlx-lm is pulled as a dependency of mlx-vlm and mlx-audio — no explicit pin needed.
    # mlx-vlm 0.4.4 requires mlx-lm>=0.31.0; mlx-audio 0.4.2 pins mlx-lm==0.31.1.
    python3 -c "import mlx_lm; print(f'  ✅ mlx-lm {mlx_lm.__version__}')" 2>/dev/null || \
        echo "  ❌ mlx-lm not installed (should be pulled by mlx-vlm)"
    python3 -c "import mlx_vlm; print(f'  ✅ mlx-vlm {mlx_vlm.__version__}')" 2>/dev/null || \
        echo "  ✅ mlx-vlm installed"

    echo "  Installing mlx-audio (unified TTS + ASR via mlx-audio)..."
    pip3 install "mlx-audio>=0.3.0" --upgrade --quiet 2>/dev/null || \
        pip3 install "mlx-audio>=0.3.0" --upgrade --quiet --break-system-packages
    python3 -c "import mlx_audio; print(f'  ✅ mlx-audio {mlx_audio.__version__}')" 2>/dev/null || \
        echo "  ✅ mlx-audio installed"

    # ── Kokoro TTS dependencies (required by mlx-audio Kokoro backend) ──────
    echo "  Installing Kokoro TTS dependencies (misaki, num2words, spacy, phonemizer)..."
    pip3 install "misaki" "num2words" "spacy" "phonemizer" --upgrade --quiet 2>/dev/null || \
        pip3 install "misaki" "num2words" "spacy" "phonemizer" --upgrade --quiet --break-system-packages
    echo "  Downloading en_core_web_sm (spaCy English model)..."
    python3 -m spacy download en_core_web_sm --quiet 2>/dev/null || \
        python3 -m spacy download en_core_web_sm --quiet --break-system-packages 2>/dev/null || \
        echo "  ⚠️  en_core_web_sm download failed — Kokoro TTS may not work"
    echo "  ✅ Kokoro TTS dependencies installed"

    # Deploy MLX proxy (auto-switches mlx_lm ↔ mlx_vlm on port 8081)
    MLX_DIR="$HOME/.portal5/mlx"
    mkdir -p "$MLX_DIR" "$HOME/.portal5/logs"

    # Copy proxy from repo to local runtime directory
    if [ -f "$PORTAL_ROOT/scripts/mlx-proxy.py" ]; then
        cp "$PORTAL_ROOT/scripts/mlx-proxy.py" "$MLX_DIR/mlx-proxy.py"
        chmod +x "$MLX_DIR/mlx-proxy.py"
        echo "  ✅ Proxy deployed: $MLX_DIR/mlx-proxy.py"
    else
        echo "  ⚠️  scripts/mlx-proxy.py not found — proxy not deployed"
        echo "     Run from the portal-5 repo directory, or copy manually."
    fi

    # Remove stale single-server scripts
    [ -f "$MLX_DIR/start.sh" ] && rm -f "$MLX_DIR/start.sh" && echo "  🧹 Removed stale start.sh"
    [ -f "$MLX_DIR/start-lm.sh" ] && rm -f "$MLX_DIR/start-lm.sh" && echo "  🧹 Removed stale start-lm.sh"
    [ -f "$MLX_DIR/start-vlm.sh" ] && rm -f "$MLX_DIR/start-vlm.sh" && echo "  🧹 Removed stale start-vlm.sh"

    # ── Register mlx-proxy as a launchd service (auto-start on login) ────────
    if [ "$(uname -s)" = "Darwin" ]; then
        # Remove stale single-server plist
        if [ -f "$HOME/Library/LaunchAgents/com.portal5.mlx.plist" ]; then
            launchctl unload "$HOME/Library/LaunchAgents/com.portal5.mlx.plist" 2>/dev/null || true
            rm -f "$HOME/Library/LaunchAgents/com.portal5.mlx.plist"
            echo "  🧹 Removed stale com.portal5.mlx plist"
        fi

        PLIST_PATH="$HOME/Library/LaunchAgents/com.portal5.mlx-proxy.plist"
        PYTHON_PATH=$(python3 -c "import sys; print(sys.executable)" 2>/dev/null || which python3)
        MLX_LOG_DIR="$HOME/.portal5/logs"
        mkdir -p "$MLX_LOG_DIR"

        cat > "$PLIST_PATH" << MLXPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.portal5.mlx-proxy</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${MLX_DIR}/mlx-proxy.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${MLX_LOG_DIR}/mlx-proxy.log</string>
    <key>StandardErrorPath</key>
    <string>${MLX_LOG_DIR}/mlx-proxy-error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>${HOME}</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
MLXPLIST

        launchctl load "$PLIST_PATH" 2>/dev/null || true
        launchctl start com.portal5.mlx-proxy 2>/dev/null || true
        sleep 3
        if curl -s "http://localhost:8081/health" &>/dev/null 2>&1; then
            echo "  ✅ launchd service registered: com.portal5.mlx-proxy"
            echo "  ✅ MLX proxy running on :8081 (auto-switches mlx_lm :18081 ↔ mlx_vlm :18082)"
        else
            echo "  ✅ launchd service registered: com.portal5.mlx-proxy"
            echo "  ⚠️  Proxy not yet responding — logs: $MLX_LOG_DIR/mlx-proxy.log"
        fi
    fi

    echo ""
    echo "Next steps:"
    echo "  1. Pull MLX models:  ./launch.sh pull-mlx-models"
    echo "  2. Start Portal:     ./launch.sh up"
    echo ""
    echo "The proxy auto-switches between mlx_lm (text-only, port 18081) and mlx_vlm"
    echo "(VLM models including Qwen3.5, port 18082) based on the requested model."
    echo "Only one server runs at a time — switching takes ~30s on first request."
    echo "Portal automatically falls back to Ollama during MLX model switches."
    ;;

  switch-mlx-model)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    MODEL="${2:-}"
    if [ -z "$MODEL" ]; then
        echo "Usage: ./launch.sh switch-mlx-model <mlx-community/model-tag>"
        echo ""
        echo "The MLX proxy auto-switches between mlx_lm (text-only) and mlx_vlm (VLM)"
        echo "based on the model in each request. This command forces a pre-warm switch."
        echo ""
        echo "Available MLX models (pull first with ./launch.sh pull-mlx-models):"
        echo "  Text-only (mlx_lm, port 18081):"
        echo "    mlx-community/Qwen3-Coder-Next-4bit              (~46GB — primary coder, 80B MoE)"
        echo "    mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit  (~22GB)"
        echo "    mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit  (~12GB)"
        echo "    lmstudio-community/Devstral-Small-2507-MLX-4bit      (~15GB — Devstral v1.1, 53.6% SWE-bench, Mistral lineage)"
        echo "    mlx-community/Dolphin3.0-Llama3.1-8B-8bit        (~9GB — creative)"
        echo "    mlx-community/Llama-3.2-3B-Instruct-8bit         (~3GB — fast routing)"
        echo "  Model Diversity (Microsoft / Google / Mistral):"
        echo "    mlx-community/phi-4-8bit                           (~14GB — Microsoft Phi-4 14B, synthetic data, MIT)"
        echo "    mlx-community/gemma-4-31b-it-4bit                  (~18GB — Google Gemma 4 dense 31B, thinking+vision, VLM)"
        echo "    lmstudio-community/Magistral-Small-2509-MLX-8bit  (~24GB — Mistral reasoning, [THINK] mode)"
        echo "    mlx-community/Llama-3.3-70B-Instruct-4bit        (~40GB — heavy, 4bit only)"
        echo "  Jackrong Reasoning Distills:"
        echo "    Jackrong/MLX-Qwopus3.5-27B-v3-8bit                                    (~22GB, primary auto-reasoning)"
        echo "    Jackrong/MLX-Qwopus3.5-9B-v3-8bit                                     (~9GB)"
        echo "    Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit  (~14GB, Claude-4.6-Opus v2)"
        echo "    Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit      (~9GB, Claude-4.6-Opus)"
        echo "    Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit (~28GB)"
        echo "    mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit           (~18GB — uncensored)"
        echo "  Microsoft:"
        echo "    mlx-community/phi-4-8bit                                              (~14GB)"
        echo "  VLM models (mlx_vlm, port 18082):"
        echo "    mlx-community/gemma-4-31b-it-4bit                 (~18GB — Google Gemma 4 dense 31B, thinking+vision)"
        echo "    mlx-community/Qwen3-VL-32B-Instruct-8bit         (~36GB — vision)"
        echo "    mlx-community/gemma-4-e4b-it-4bit                 (~5GB — Gemma 4 E4B vision+audio fallback)"
        echo "    mlx-community/gemma-4-26b-a4b-it-4bit            (~15GB — Gemma 4 26B A4B MoE, 256K ctx)"
        echo "    mlx-community/Llama-3.2-11B-Vision-Instruct-abliterated-4-bit  (~7GB — uncensored VLM)"
        echo "    dealignai/Gemma-4-31B-JANG_4M-CRACK              (~23GB — abliterated Gemma 4 31B, uncensored VLM)"
        echo ""
        echo "Current status:"
        curl -s "http://localhost:8081/health" 2>/dev/null | python3 -m json.tool 2>/dev/null || \
            echo "  MLX proxy not running"
        exit 0
    fi

    echo "Pre-warming MLX server for: $MODEL"

    # Send a dummy request to the proxy — it will switch servers if needed
    MLX_PROXY="$HOME/.portal5/mlx/mlx-proxy.py"
    if [ ! -f "$MLX_PROXY" ]; then
        echo "  ❌ MLX proxy not found at $MLX_PROXY"
        echo "     Run: ./launch.sh install-mlx"
        exit 1
    fi

    # Start proxy if not running
    if ! curl -s "http://localhost:8081/health" &>/dev/null 2>&1; then
        echo "  Starting MLX proxy..."
        mkdir -p "$HOME/.portal5/logs"
        nohup python3 "$MLX_PROXY" > "$HOME/.portal5/logs/mlx-proxy.log" 2>&1 &
        sleep 3
    fi

    # Send a minimal request to trigger server switch
    echo "  Triggering server switch (this may take ~30s)..."
    RESP=$(curl -s -X POST "http://localhost:8081/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":false}" \
        --max-time 120 2>/dev/null)

    if [ "$(_json_get "$RESP" 'if .choices then "yes" else "no" end' "d=json.load(sys.stdin); print('yes' if 'choices' in d else 'no')" "no")" = "yes" ]; then
        echo "  ✅ Server switched and responding for $MODEL"
    else
        echo "  ⚠️  Request completed (may have fallen back to Ollama)"
        echo "     Response: $(echo "$RESP" | head -c 200)"
    fi
    ;;

  start-mlx-watchdog)
    ARCH=$(uname -m)
    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  MLX watchdog is Apple Silicon only."
        exit 0
    fi
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    WATCHDOG_SCRIPT="$PORTAL_ROOT/scripts/mlx-watchdog.py"
    if [ ! -f "$WATCHDOG_SCRIPT" ]; then
        echo "  ❌ mlx-watchdog.py not found at $WATCHDOG_SCRIPT"
        exit 1
    fi

    if [ -f /tmp/mlx-watchdog.pid ] && kill -0 "$(cat /tmp/mlx-watchdog.pid)" 2>/dev/null; then
        echo "  ℹ️  MLX watchdog already running (PID $(cat /tmp/mlx-watchdog.pid))"
        exit 0
    fi

    mkdir -p "$HOME/.portal5/logs"
    echo "  Starting MLX watchdog..."
    nohup python3 "$WATCHDOG_SCRIPT" > "$HOME/.portal5/logs/mlx-watchdog.log" 2>&1 &
    echo $! > /tmp/mlx-watchdog.pid
    sleep 2
    if kill -0 "$!" 2>/dev/null; then
        echo "  ✅ MLX watchdog started (PID $!)"
        echo "     Logs: $HOME/.portal5/logs/mlx-watchdog.log"
    else
        echo "  ❌ MLX watchdog failed to start"
        exit 1
    fi
    ;;

  stop-mlx-watchdog)
    if [ -f /tmp/mlx-watchdog.pid ] && kill -0 "$(cat /tmp/mlx-watchdog.pid)" 2>/dev/null; then
        kill "$(cat /tmp/mlx-watchdog.pid)"
        rm -f /tmp/mlx-watchdog.pid
        echo "  ✅ MLX watchdog stopped"
    else
        echo "  ℹ️  MLX watchdog not running"
    fi
    ;;

  mlx-status)
    ARCH=$(uname -m)
    echo "=== MLX Component Status ==="
    echo ""

    # Proxy
    echo -n "  MLX Proxy (:8081):     "
    if curl -s --connect-timeout 3 http://localhost:8081/health &>/dev/null; then
        echo "✅ healthy"
        curl -s http://localhost:8081/health 2>/dev/null | python3 -m json.tool 2>/dev/null | sed 's/^/    /'
    else
        echo "❌ down"
    fi

    # mlx_lm
    echo -n "  mlx_lm server (:18081): "
    if curl -s --connect-timeout 3 http://localhost:18081/health &>/dev/null; then
        echo "✅ healthy"
        curl -s http://localhost:18081/health 2>/dev/null | python3 -m json.tool 2>/dev/null | sed 's/^/    /'
    else
        echo "❌ down"
    fi

    # mlx_vlm
    echo -n "  mlx_vlm server (:18082): "
    if curl -s --connect-timeout 3 http://localhost:18082/health &>/dev/null; then
        echo "✅ healthy"
        curl -s http://localhost:18082/health 2>/dev/null | python3 -m json.tool 2>/dev/null | sed 's/^/    /'
    else
        echo "❌ down"
    fi

    # Watchdog
    echo -n "  MLX Watchdog:          "
    if [ -f /tmp/mlx-watchdog.pid ] && kill -0 "$(cat /tmp/mlx-watchdog.pid)" 2>/dev/null; then
        echo "✅ running (PID $(cat /tmp/mlx-watchdog.pid))"
    else
        echo "❌ not running (start with: ./launch.sh start-mlx-watchdog)"
    fi

    # MLX Speech
    echo -n "  MLX Speech (:8918):    "
    if curl -s --connect-timeout 3 http://localhost:8918/health &>/dev/null; then
        echo "✅ healthy"
    elif [ -f /tmp/portal-mlx-speech.pid ] && kill -0 "$(cat /tmp/portal-mlx-speech.pid)" 2>/dev/null; then
        echo "⏳ starting (PID $(cat /tmp/portal-mlx-speech.pid))"
    else
        echo "❌ not running (start with: ./launch.sh start-speech)"
    fi

    echo ""
    echo "=== Pipeline Backend Health ==="
    curl -s http://localhost:9099/health 2>/dev/null | python3 -m json.tool 2>/dev/null | sed 's/^/  /' || echo "  Pipeline not responding"
    ;;

  start-speech)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

    if [ "$(uname -m)" != "arm64" ]; then
        echo "  ℹ️  MLX Speech requires Apple Silicon. Docker TTS/ASR services are available as fallback."
        exit 0
    fi

    if ! python3 -c "import mlx_audio" &>/dev/null 2>&1; then
        echo "  ❌ mlx-audio not installed. Run: ./launch.sh install-mlx"
        exit 1
    fi

    PID_FILE="/tmp/portal-mlx-speech.pid"
    LOG_FILE="$HOME/.portal5/logs/mlx-speech.log"
    mkdir -p "$(dirname "$LOG_FILE")"

    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "  ℹ️  MLX Speech already running (PID $(cat "$PID_FILE"))"
        exit 0
    fi

    echo "Starting MLX Speech Server (Qwen3-TTS + Qwen3-ASR + Kokoro)..."
    nohup python3 "$PORTAL_ROOT/scripts/mlx-speech.py" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "  ✅ MLX Speech started (PID $!, port ${MLX_SPEECH_PORT:-8918})"
    echo "  📋 Log: $LOG_FILE"
    echo "  💡 Models load lazily on first TTS/ASR request."
    ;;

  start-embedding-cpu-arm)
    # Start the native ARM64 embedding server (Python/sentence-transformers + MPS).
    # Replaces the TEI Docker service on Apple Silicon where the x86-only TEI image
    # has no ARM64 manifest. Binds to port 8917 — same as the Docker service.

    # Source .env so EMBEDDING_MODEL, EMBEDDING_HOST_PORT, and ENABLE_REMOTE_ACCESS
    # overrides are respected when this command is run standalone (not via `up`).
    if [ -f "$ENV_FILE" ]; then set -a; source "$ENV_FILE"; set +a; fi

    ARCH=$(uname -m)
    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  This command is for Apple Silicon (arm64). On x86, the Docker TEI service works directly."
        echo "  Run: ./launch.sh up  (embedding starts automatically)"
        exit 0
    fi

    PID_FILE="/tmp/portal-embedding-arm.pid"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "  ✅ ARM64 embedding server already running (PID $(cat "$PID_FILE"))"
        echo "  Test: curl http://localhost:8917/health"
        exit 0
    fi

    # Use a dedicated venv (avoids conflicts with project venv and PEP 668 Homebrew Python)
    EM_VENV="${HOME}/.portal5/embedding-venv"
    EM_PY="${EM_VENV}/bin/python3"
    if [ ! -x "$EM_PY" ]; then
        echo "  Creating embedding venv at $EM_VENV..."
        python3 -m venv "$EM_VENV" --without-pip 2>/dev/null || python3 -m venv "$EM_VENV"
        "$EM_PY" -m ensurepip --upgrade &>/dev/null || true
    fi
    if ! "$EM_PY" -c "import sentence_transformers, fastapi, uvicorn" &>/dev/null 2>&1; then
        echo "  Installing deps into embedding venv..."
        "$EM_PY" -m pip install --quiet sentence-transformers fastapi uvicorn || {
            echo "  ❌ Failed to install deps into $EM_VENV"
            exit 1
        }
    fi

    # Stop the TEI Docker container if running (port conflict)
    docker stop portal5-embedding 2>/dev/null && echo "  Stopped Docker TEI container (port conflict)" || true

    MODEL="${EMBEDDING_MODEL:-microsoft/harrier-oss-v1-0.6b}"
    PORT="${EMBEDDING_HOST_PORT:-8917}"
    LOG_FILE="${HOME}/.portal5/logs/embedding-server.log"
    mkdir -p "$(dirname "$LOG_FILE")"

    echo "[portal-5] Starting ARM64 native embedding server..."
    echo "  Model: $MODEL"
    echo "  Port:  $PORT"
    echo "  Log:   $LOG_FILE"

    nohup "$EM_PY" "$PORTAL_ROOT/scripts/embedding-server.py" \
        --model "$MODEL" \
        --port "$PORT" \
        --host 0.0.0.0 \
        >"$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "[portal-5] ARM64 embedding server started (PID $!)"
    echo "  Health (ready in ~30s): curl http://localhost:8917/health"
    ;;

  stop-embedding-cpu-arm)
    PID_FILE="/tmp/portal-embedding-arm.pid"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        kill "$(cat "$PID_FILE")"
        rm -f "$PID_FILE"
        echo "  ✅ ARM64 embedding server stopped"
    else
        echo "  ℹ️  ARM64 embedding server not running"
    fi
    ;;

  install-embedding-service)
    # Install a macOS launchd agent so the ARM64 embedding server starts at login
    # and auto-restarts on crash — no dependency on launch.sh being run first.
    if [ "$(uname)" != "Darwin" ]; then
        echo "  ❌ launchd services are macOS-only"
        exit 1
    fi
    if [ "$(uname -m)" != "arm64" ]; then
        echo "  ℹ️  ARM64 embedding server is for Apple Silicon only."
        echo "  On x86, the portal5-embedding Docker service (TEI) handles embeddings."
        exit 0
    fi

    PLIST_DIR="${HOME}/Library/LaunchAgents"
    PLIST_FILE="${PLIST_DIR}/com.portal5.embedding.plist"
    LOG_DIR="${HOME}/.portal5/logs"
    WRAPPER="${PORTAL_ROOT}/scripts/embedding-launchd-wrapper.sh"

    mkdir -p "$PLIST_DIR" "$LOG_DIR"
    chmod +x "$WRAPPER"

    # Ensure venv + deps are installed before registering the service
    _EM_VENV="${HOME}/.portal5/embedding-venv"
    _EM_PY="${_EM_VENV}/bin/python3"
    if [ ! -x "$_EM_PY" ]; then
        echo "[portal-5] Creating embedding venv at $_EM_VENV..."
        python3 -m venv "$_EM_VENV" --without-pip 2>/dev/null || python3 -m venv "$_EM_VENV"
        "$_EM_PY" -m ensurepip --upgrade &>/dev/null || true
    fi
    if ! "$_EM_PY" -c "import sentence_transformers, fastapi, uvicorn" &>/dev/null 2>&1; then
        echo "[portal-5] Installing embedding server deps..."
        "$_EM_PY" -m pip install --quiet sentence-transformers fastapi uvicorn || {
            echo "  ❌ Failed to install deps — aborting"
            exit 1
        }
    fi

    # Stop any existing nohup instance so there's no port conflict
    _PID_FILE="/tmp/portal-embedding-arm.pid"
    if [ -f "$_PID_FILE" ] && kill -0 "$(cat "$_PID_FILE")" 2>/dev/null; then
        kill "$(cat "$_PID_FILE")" 2>/dev/null || true
        rm -f "$_PID_FILE"
        echo "[portal-5] Stopped existing nohup embedding instance"
    fi

    # Write the plist (paths must be absolute — launchd does not expand ~)
    cat > "$PLIST_FILE" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.portal5.embedding</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${WRAPPER}</string>
    </array>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>30</integer>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/embedding-server.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/embedding-server-err.log</string>
    <key>WorkingDirectory</key>
    <string>${PORTAL_ROOT}</string>
</dict>
</plist>
PLIST

    # Unload any existing registration, then register the updated plist
    launchctl bootout "gui/$(id -u)/com.portal5.embedding" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST_FILE"

    echo "[portal-5] ✅ Embedding service installed and started"
    echo "  Plist:    $PLIST_FILE"
    echo "  Log:      ${LOG_DIR}/embedding-server.log"
    echo "  Status:   launchctl list com.portal5.embedding"
    echo "  Uninstall: ./launch.sh uninstall-embedding-service"
    ;;

  uninstall-embedding-service)
    PLIST_FILE="${HOME}/Library/LaunchAgents/com.portal5.embedding.plist"
    if launchctl list com.portal5.embedding 2>/dev/null | grep -q '"PID"'; then
        launchctl bootout "gui/$(id -u)/com.portal5.embedding" 2>/dev/null || true
        echo "[portal-5] ✅ Embedding service stopped and unregistered"
    else
        launchctl bootout "gui/$(id -u)/com.portal5.embedding" 2>/dev/null || true
    fi
    if [ -f "$PLIST_FILE" ]; then
        rm -f "$PLIST_FILE"
        echo "[portal-5] Plist removed: $PLIST_FILE"
    else
        echo "[portal-5] ℹ️  No plist found at $PLIST_FILE"
    fi
    ;;

  stop-speech)
    PID_FILE="/tmp/portal-mlx-speech.pid"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        kill "$(cat "$PID_FILE")"
        rm -f "$PID_FILE"
        echo "  ✅ MLX Speech stopped"
    else
        echo "  ℹ️  MLX Speech not running"
    fi
    ;;

  pull-mlx-models)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    ARCH=$(uname -m)

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  MLX models are Apple Silicon only. Use: ./launch.sh pull-models for Ollama."
        exit 0
    fi

    if ! python3 -c "import mlx_lm" &>/dev/null 2>&1; then
        echo "  ❌ mlx-lm not installed. Run: ./launch.sh install-mlx"
        exit 1
    fi

    echo "=== Downloading MLX models to HuggingFace cache ==="
    echo "Models download to: ${HF_HOME:-~/.cache/huggingface/hub/}"
    echo ""

    # Standard MLX models (8bit quants for 64GB M4 Mac — one at a time)
    MLX_MODELS=(
        # Coding — primary workspace models
        "mlx-community/Qwen3-Coder-Next-4bit"              # ~46GB — 80B MoE, 4bit required (8bit ~85GB exceeds 64GB)
        "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit"  # ~22GB
        "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit"  # ~12GB
        "lmstudio-community/Devstral-Small-2507-MLX-4bit"        # ~15GB — Devstral v1.1, 53.6% SWE-bench
        # Jackrong Reasoning (Qwopus3.5-v3 primary + Claude-4.6-Opus variants)
        "Jackrong/MLX-Qwopus3.5-27B-v3-8bit"                                    # ~22GB — primary auto-reasoning
        "Jackrong/MLX-Qwopus3.5-9B-v3-8bit"                                     # ~9GB
        "Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit"  # ~14GB — v2: efficient CoT
        "Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit"      # ~9GB — Claude-4.6-Opus 9B distill
        "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit" # ~28GB
        "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit"                   # ~34GB
        "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit"           # ~18GB (uncensored)
        # Creative / general (uncensored)
        "mlx-community/Dolphin3.0-Llama3.1-8B-8bit"        # ~9GB
        # General / fast routing
        "mlx-community/Llama-3.2-3B-Instruct-8bit"         # ~3GB — ultra-fast
        # Model diversity (non-Qwen/non-DeepSeek families)
        "mlx-community/phi-4-8bit"                          # ~14GB — Microsoft Phi-4 14B, synthetic data training, MIT
        "mlx-community/gemma-4-31b-it-4bit"                  # ~18GB — Google Gemma 4 dense 31B, thinking+vision
        "lmstudio-community/Magistral-Small-2509-MLX-8bit"  # ~24GB — Mistral reasoning, [THINK] mode
        # Vision
        "mlx-community/Qwen3-VL-32B-Instruct-8bit"         # ~36GB
        "mlx-community/gemma-4-e4b-it-4bit"                # ~5GB — Gemma 4 E4B vision+audio VLM (replaces LLaVA 1.5-7B)
        "mlx-community/gemma-4-26b-a4b-it-4bit"            # ~15GB — Gemma 4 26B A4B MoE VLM, 256K ctx
        "lmstudio-community/Phi-4-reasoning-plus-MLX-4bit" # ~7GB — Phi-4-reasoning-plus, STEM/math RL-trained
        "dealignai/Gemma-4-31B-JANG_4M-CRACK"              # ~23GB — Abliterated Gemma 4 31B JANG v2 5.1-bit, uncensored VLM
        # OCR (document ingestion)
        "mlx-community/GLM-OCR-bf16"                        # ~2GB — Zhipu GLM-OCR for scanned document ingestion
        # Speech (mlx-audio — TTS + ASR, host-native)
        "mlx-community/Kokoro-82M-bf16"                        # ~0.2GB — Kokoro TTS via mlx-audio
        "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit"  # ~0.8GB — voice cloning + style control
        "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit"  # ~0.8GB — create voices from descriptions
        "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"         # ~0.8GB — voice cloning from reference audio
        "mlx-community/Qwen3-ASR-1.7B-8bit"                    # ~0.8GB — speech recognition (replaces faster-whisper)
    )

    # Heavy models — gated behind PULL_HEAVY=true
    HEAVY_MLX_MODELS=(
        "mlx-community/Llama-3.3-70B-Instruct-4bit"        # ~40GB — unload others first (BIG_MODEL)
        # GLM-5.1 removed: tested on 64GB M4 Mac — both MXFP4-Q8 (49GB) and DQ4plus variants exceed safe headroom
    )

    total=${#MLX_MODELS[@]}
    count=0
    failed=0

    for model in "${MLX_MODELS[@]}"; do
        count=$((count + 1))
        echo "[$count/$total] $model"
        if python3 -W ignore -c "
import warnings; warnings.filterwarnings('ignore')
from huggingface_hub import snapshot_download
snapshot_download('$model', ignore_patterns=['*.md','*.txt','*.safetensors.index.json'])
"; then
            echo "  ✅ Downloaded"
        else
            echo "  ❌ Failed"
            echo "  Retry: huggingface-cli download $model"
            failed=$((failed + 1))
        fi
        echo ""
    done

    if [ "${PULL_HEAVY:-false}" = "true" ]; then
        echo "Pulling heavy MLX models (PULL_HEAVY=true) — ensure <24GB RAM is free..."
        for model in "${HEAVY_MLX_MODELS[@]}"; do
            echo "  Downloading: $model (~40GB)"
            if python3 -W ignore -c "
import warnings; warnings.filterwarnings('ignore')
from huggingface_hub import snapshot_download
snapshot_download('$model', ignore_patterns=['*.md','*.txt','*.safetensors.index.json'])
"; then
                echo "  ✅ Done"
            else
                echo "  ❌ Failed"
                failed=$((failed + 1))
            fi
            rm -f "$_mlx_err"
        done
    else
        echo "Skipping Llama-3.3-70B MLX (~40GB) — set PULL_HEAVY=true to include"
    fi

    echo ""
    echo "=== MLX download complete: $((total - failed))/$total succeeded ==="
    echo ""
    echo "Start inference with:"
    echo "  MLX_MODEL=mlx-community/Qwen3-Coder-Next-4bit ~/.portal5/mlx/start.sh"

    # ASK-04: Check availability of other Qwen3.5 MLX models that may publish later
    # Claude-distilled models are now in backends.yaml — this block watches for future publishes.
    echo ""
    echo "=== Checking Qwen3.5 MLX watch (future publishes) ==="
    echo "  ℹ️  Claude-distilled models: enabled (see backends.yaml)"
    echo ""
    ;;

  import-gguf)
    # Import a locally downloaded GGUF file into Ollama
    # Usage: ./launch.sh import-gguf /path/to-model.gguf [ollama-name]
    _gguf_path="${2:-}"
    _model_name="${3:-}"

    # Expand ~ manually since this runs at script level, not inside a function
    _gguf_path="${_gguf_path/#\~/$HOME}"

    if [ -z "$_gguf_path" ] || [ ! -f "$_gguf_path" ]; then
        echo "Usage: ./launch.sh import-gguf <path-to-gguf> [model-name]"
        echo ""
        echo "  path-to-gguf   Full path to a .gguf file"
        echo "  model-name     Name to register in Ollama (default: filename without extension)"
        echo ""
        echo "Example:"
        echo "  ./launch.sh import-gguf ~/Downloads/baronllm-q6_k.gguf baronllm:q6_k"
        echo "  ./launch.sh import-gguf ~/Downloads/WhiteRabbitNeo-33B-v1.5-Q4_K_M.gguf whiterabbitneo:33b-v1.5-q4_k_m"
        exit 1
    fi

    if [ -z "$_model_name" ]; then
        _model_name=$(basename "$_gguf_path" .gguf | tr '[:upper:]' '[:lower:]' | tr '_' '-')
    fi

    # Detect Ollama (native or Docker)
    if command -v ollama &>/dev/null && curl -s http://localhost:11434/api/tags &>/dev/null 2>&1; then
        _ollama_import_cmd="ollama"
    elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^portal5-ollama$"; then
        _ollama_import_cmd="docker exec portal5-ollama ollama"
    else
        echo "[portal-5] ❌ No Ollama available. Run: ./launch.sh install-ollama"
        exit 1
    fi

    echo "[portal-5] Importing GGUF: $_gguf_path"
    echo "           Ollama name:   $_model_name"

    _tmp_dir=$(mktemp -d)
    cat > "$_tmp_dir/Modelfile" << MEOF
FROM $_gguf_path
PARAMETER temperature 0.7
PARAMETER num_ctx 8192
MEOF

    if $_ollama_import_cmd create "$_model_name" -f "$_tmp_dir/Modelfile"; then
        echo "[portal-5] ✅ Imported: $_model_name"
        echo "  Run it: ollama run $_model_name"
    else
        echo "[portal-5] ❌ Import failed. Check Ollama is running: brew services info ollama"
        rm -rf "$_tmp_dir"
        exit 1
    fi
    rm -rf "$_tmp_dir"
    ;;

  download-comfyui-models)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    COMFYUI_DIR="${COMFYUI_DIR:-$HOME/ComfyUI}"
    IMAGE_MODEL="${IMAGE_MODEL:-flux-schnell}"
    VIDEO_MODEL="${VIDEO_MODEL:-wan2.2}"
    HF_TOKEN="${HF_TOKEN:-}"

    echo "=== Downloading ComfyUI models ==="
    echo "  Image model: $IMAGE_MODEL"
    echo "  Video model: $VIDEO_MODEL"
    echo "  Models dir:  $COMFYUI_DIR/models/checkpoints"
    echo ""

    # Ensure huggingface_hub is available
    if ! python3 -c "import huggingface_hub" &>/dev/null; then
        echo "  Installing huggingface_hub..."
        pip install huggingface_hub --quiet --break-system-packages 2>/dev/null || \
            python3 -m pip install huggingface_hub --quiet
    fi

    IMAGE_MODEL="$IMAGE_MODEL" \
    VIDEO_MODEL="$VIDEO_MODEL" \
    HF_TOKEN="$HF_TOKEN" \
    MODELS_DIR="$COMFYUI_DIR/models/checkpoints" \
    python3 "$PORTAL_ROOT/scripts/download_comfyui_models.py"
    ;;

    *)
    echo "Usage: ./launch.sh [up|down|clean|clean-all|seed|logs|status|update|pull-models|refresh-models|import-gguf|test|add-user|list-users|backup|restore|up-telegram|up-slack|up-channels|install-ollama|install-comfyui|install-music|install-mlx|download-comfyui-models|pull-mlx-models|switch-mlx-model|start-mlx-watchdog|stop-mlx-watchdog|mlx-status|start-speech|stop-speech|start-embedding-cpu-arm|stop-embedding-cpu-arm|install-embedding-service|uninstall-embedding-service|rebuild]"
    echo ""
    echo "  up                    Start all services (first run auto-generates secrets)"
    echo "  install-ollama        Install Ollama natively via brew (Apple Silicon recommended)"
    echo "  install-comfyui       Install ComfyUI natively via git+pip (Apple Silicon)"
    echo "  install-music         Install Music MCP natively via venv (Apple Silicon / MPS)"
    echo "  install-mlx           Install MLX dual-server proxy (mlx_lm + mlx_vlm + mlx-audio) for Apple Silicon"
    echo "  download-comfyui-models  Download image/video models to ~/ComfyUI/models/"
    echo "  pull-mlx-models       Download MLX model weights to HF cache"
    echo "  switch-mlx-model <tag>  Pre-warm MLX server for a specific model (triggers auto-switch)"
    echo "  start-mlx-watchdog      Start MLX health watchdog daemon (auto-recover + notifications)"
    echo "  stop-mlx-watchdog       Stop MLX watchdog daemon"
    echo "  mlx-status              Show status of all MLX components (proxy, mlx_lm, mlx_vlm, speech)"
    echo "  start-speech          Start MLX Speech server (Qwen3-TTS + Qwen3-ASR)"
    echo "  stop-speech           Stop MLX Speech server"
    echo "  start-embedding-cpu-arm  Start native ARM64 embedding server (Apple Silicon, no Rosetta)"
    echo "  stop-embedding-cpu-arm   Stop ARM64 embedding server"
    echo "  install-embedding-service   Install launchd agent — embedding starts at login, auto-restarts on crash"
    echo "  uninstall-embedding-service Remove launchd agent"
    echo "  rebuild               Rebuild portal-pipeline Docker image + restart (after git pull)"
    echo "  update                Full update: git pull, Docker images, rebuilds, model refresh, re-seed"
    echo "                          --skip-models   Skip Ollama + MLX model refresh"
    echo "                          --models-only   Only refresh models (Ollama + MLX)"
    echo "                          --yes / -y      Skip confirmation prompts"
    echo "  up-telegram           Start core stack + Telegram bot (requires TELEGRAM_BOT_TOKEN in .env)"
    echo "  up-slack              Start core stack + Slack bot (requires SLACK_BOT_TOKEN + SLACK_APP_TOKEN in .env)"
    echo "  up-channels           Start core stack + both Telegram and Slack"
    echo "  test                  Run end-to-end smoke tests against the live stack"
    echo "  down                  Stop all services (data preserved)"
    echo "  clean                 Stop + wipe Open WebUI data (Ollama models preserved)"
    echo "  clean-all             Stop + wipe everything including Ollama models"
    echo "  seed                  Re-run Open WebUI seeding (workspaces + personas + tools)"
    echo "  logs [svc]            Tail logs (default: portal-pipeline)"
    echo "  status                Show service status and health"
    echo "  pull-models           Pull all Portal 5 Ollama models (30-90 min)"
    echo "  refresh-models        Check all models for updates (skips unchanged models)"
    echo "  import-gguf <path> [name]  Import a locally downloaded GGUF file into Ollama"
    echo "  add-user <email> [name] [role]  Create a user account"
    echo "  list-users            List all registered users"
    echo "  backup                Back up all data to ./backups/ (or specified path)"
    echo "  restore               Restore data from a backup directory"
    ;;
esac
