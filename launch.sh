#!/bin/bash
set -euo pipefail
PORTAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$PORTAL_ROOT/deploy/portal-5"
ENV_FILE="$PORTAL_ROOT/.env"

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

    # Docker check
    if ! docker info &>/dev/null; then
        echo "  ❌ Docker: not running — start Docker Desktop and retry"
        exit 1
    else
        echo "  ✅ Docker: running"
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
        else
            echo "  ℹ️  ComfyUI not running (image/video generation unavailable)"
            echo "     Install: ./launch.sh install-comfyui"
            echo "     Start:   ~/ComfyUI/start.sh"
        fi
        # Check mlx_lm server
        local MLX_PORT_CHECK="${MLX_PORT:-8081}"
        if curl -s "http://localhost:${MLX_PORT_CHECK}/v1/models" &>/dev/null 2>&1; then
            MLX_ACTIVE=$(curl -s "http://localhost:${MLX_PORT_CHECK}/v1/models" 2>/dev/null | \
                python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data'][0]['id'].split('/')[-1] if d.get('data') else 'running')" 2>/dev/null || echo "running")
            echo "  ✅ mlx_lm: active ($MLX_ACTIVE) — native Apple Silicon inference"
        elif python3 -c "import mlx_lm" &>/dev/null 2>&1; then
            echo "  ℹ️  mlx_lm: installed, not running (Ollama will be used)"
            echo "     Start: MLX_MODEL=mlx-community/Qwen3-Coder-Next-4bit ~/.portal5/mlx/start.sh"
        else
            echo "  ℹ️  mlx_lm: not installed (optional, 20-40% faster than Ollama on M4)"
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
                nohup ollama serve > "$HOME/.portal5/logs/ollama.log" 2>&1 &
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
                    launchctl start com.portal5.comfyui 2>/dev/null || true
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

    # ── MLX inference server (Apple Silicon native only) ─────────────────────
    if [ "$ARCH" = "arm64" ]; then
        local MLX_PORT_VAL="${MLX_PORT:-8081}"
        local MLX_START_SCRIPT="$HOME/.portal5/mlx/start.sh"
        if [ -f "$MLX_START_SCRIPT" ]; then
            if ! curl -s "http://localhost:${MLX_PORT_VAL}/v1/models" &>/dev/null 2>&1; then
                echo "[portal-5]   MLX server installed but not running — starting..."
                mkdir -p "$HOME/.portal5/logs"
                if launchctl list com.portal5.mlx &>/dev/null 2>&1; then
                    launchctl start com.portal5.mlx 2>/dev/null || true
                else
                    MLX_PORT="$MLX_PORT_VAL" nohup "$MLX_START_SCRIPT" \
                        > "$HOME/.portal5/logs/mlx.log" 2>&1 &
                fi
                echo "[portal-5]   ⏳ MLX starting in background (first run downloads model ~18GB)"
                echo "[portal-5]      Logs: $HOME/.portal5/logs/mlx.log"
                echo "[portal-5]      API:  http://localhost:${MLX_PORT_VAL}/v1"
            else
                local MLX_MODEL_NAME
                MLX_MODEL_NAME=$(curl -s "http://localhost:${MLX_PORT_VAL}/v1/models" 2>/dev/null | \
                    python3 -c "import json,sys; d=json.load(sys.stdin); \
                    print(d['data'][0]['id'].split('/')[-1] if d.get('data') else 'running')" \
                    2>/dev/null || echo "running")
                echo "[portal-5]   ✅ MLX: running ($MLX_MODEL_NAME)"
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
    _port_check "${MUSIC_HOST_PORT:-8912}"      "MCP Music"
    _port_check "${TTS_HOST_PORT:-8916}"        "MCP TTS"
    _port_check "${WHISPER_HOST_PORT:-8915}"    "MCP Whisper"
    _port_check "${SANDBOX_HOST_PORT:-8914}"    "MCP Sandbox"
    _port_check "${COMFYUI_MCP_HOST_PORT:-8910}" "MCP ComfyUI Bridge"
    _port_check "${VIDEO_MCP_HOST_PORT:-8911}"  "MCP Video"

    # MLX inference server — only check if MLX is installed
    # Avoids false "port conflict" errors on Linux or Mac systems without MLX
    if [ -f "$HOME/.portal5/mlx/start.sh" ] || python3 -c "import mlx_lm" &>/dev/null 2>&1; then
        _port_check "${MLX_PORT:-8081}"   "MLX inference server"
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
        echo "     Note: 'down' also stops native MLX (:8081) and ComfyUI (:8188)"
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

    curl -s -X POST "$url/api/v1/auths/signin" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$email\",\"password\":\"$pass\"}" \
        2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('token',''))" \
        2>/dev/null
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

    # Check hardware requirements before starting
    _check_hardware

    # Auto-start native services if installed but not running
    _ensure_native_services

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

    echo "[portal-5] Starting stack..."
    cd "$COMPOSE_DIR"
    docker compose up -d
    echo "[portal-5] Stack started."
    echo "  Open WebUI:  http://localhost:8080"
    echo "  SearXNG:     http://localhost:8088"
    echo "  ComfyUI:     http://localhost:8188"
    echo "  Grafana:     http://localhost:3000  (admin / check .env)"
    echo "  Prometheus:  http://localhost:9090"
    ;;
  test)
    # Run end-to-end smoke tests against the live stack
    # Usage: ./launch.sh up && sleep 30 && ./launch.sh test
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
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
    STATUS=$(echo "$HEALTH_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
    BACKENDS=$(echo "$HEALTH_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('backends_healthy',0))" 2>/dev/null)

    # Pipeline is reachable if status is 'ok' or 'degraded' (either means it's running)
    [ "$STATUS" = "ok" ] || [ "$STATUS" = "degraded" ] \
        && { echo "  ✅ Pipeline reachable (status=$STATUS)"; PASS=$((PASS+1)); } \
        || { echo "  ❌ Pipeline not responding (status=$STATUS)"; FAIL=$((FAIL+1)); }

    # Ollama connectivity is informational — degraded is expected before models are pulled
    [ "$STATUS" = "ok" ] \
        && echo "  ✅ Ollama connected ($BACKENDS backends healthy)" && PASS=$((PASS+1)) \
        || echo "  ℹ️  Ollama: no backends healthy yet — run: ./launch.sh pull-models"

    WS_COUNT=$(curl -s -H "Authorization: Bearer ${PIPELINE_API_KEY}" "$PIPE/v1/models" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',[])))" 2>/dev/null)
    _check "all 13 workspaces exposed" "$WS_COUNT" "13"

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
    MODELS=$(curl -s http://localhost:11434/api/tags | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('models',[])))" 2>/dev/null)
    [ "$MODELS" -ge 1 ] && echo "  ✅ Ollama has $MODELS model(s) loaded" && PASS=$((PASS+1)) || { echo "  ❌ No Ollama models loaded — run: ./launch.sh pull-models"; FAIL=$((FAIL+1)); }

    # Live inference test
    REPLY=$(curl -s -X POST "$PIPE/v1/chat/completions" \
        -H "Authorization: Bearer ${PIPELINE_API_KEY}" \
        -H "Content-Type: application/json" \
        -d '{"model":"auto","messages":[{"role":"user","content":"Say PONG"}],"stream":false}' \
        | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('choices',[{}])[0].get('message',{}).get('content','FAIL')[:20])" 2>/dev/null)
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
    DOC_RESULT=$(curl -s -X POST "http://localhost:8913/mcp" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"create_word_document","arguments":{"title":"Smoke Test","content":"Portal 5 smoke test document"}},"id":1}' \
        2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('result',{}); print('OK' if r.get('success') or 'path' in str(r) else 'FAIL')" 2>/dev/null)
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
    SEARCH=$(curl -s "http://localhost:8088/search?q=portal+ai&format=json" \
        | python3 -c "import json,sys; d=json.load(sys.stdin); print('OK' if d.get('results') else 'EMPTY')" 2>/dev/null)
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

  down)
    # ── Stop Docker stack ─────────────────────────────────────────────────
    cd "$COMPOSE_DIR"
    docker compose down
    echo "[portal-5] Docker stack stopped."

    # ── Stop native macOS services (MLX, ComfyUI) ─────────────────────────
    # These run outside Docker and must be stopped explicitly.
    # Uses launchctl if the service is registered, falls back to pkill.
    if [ "$(uname -s)" = "Darwin" ]; then
        # MLX inference server (:8081)
        if launchctl list com.portal5.mlx &>/dev/null 2>&1; then
            launchctl stop com.portal5.mlx 2>/dev/null || true
            echo "[portal-5] MLX inference service stopped (launchd)."
        elif pgrep -f "mlx_lm.server" &>/dev/null 2>&1; then
            pkill -f "mlx_lm.server" 2>/dev/null || true
            echo "[portal-5] MLX inference process stopped (pkill)."
        else
            echo "[portal-5] MLX inference: not running (nothing to stop)."
        fi

        # ComfyUI (:8188)
        if launchctl list com.portal5.comfyui &>/dev/null 2>&1; then
            launchctl stop com.portal5.comfyui 2>/dev/null || true
            echo "[portal-5] ComfyUI service stopped (launchd)."
        elif pgrep -f "comfyui\|ComfyUI\|main.py.*comfy" &>/dev/null 2>&1; then
            pkill -f "comfyui\|ComfyUI\|main.py.*comfy" 2>/dev/null || true
            echo "[portal-5] ComfyUI process stopped (pkill)."
        else
            echo "[portal-5] ComfyUI: not running (nothing to stop)."
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
    set -a; source "$PORTAL_ROOT/.env"; set +a
    export OPENWEBUI_URL="${OPENWEBUI_URL:-http://localhost:8080}"
    python "$PORTAL_ROOT/scripts/openwebui_init.py"
    ;;
  logs)
    cd "$COMPOSE_DIR"
    docker compose logs -f "${2:-portal-pipeline}"
    ;;
  status)
    cd "$COMPOSE_DIR"
    docker compose ps
    echo ""
    echo "Pipeline health:"
    curl -s http://localhost:9099/health 2>/dev/null | python3 -m json.tool || echo "  Pipeline not reachable"
    echo ""
    echo "Open WebUI: http://localhost:8080"
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
        local _dl_dir="$HOME/.portal5/model_downloads/${actual_repo//\//_}"
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
        local _dl_dir="$HOME/.portal5/model_downloads/${actual_repo//\//_}"
        local _hf_err
        _hf_err=$(mktemp)
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
" 2>"$_hf_err")
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
" 2>"$_hf_err")
        fi

        if [ -z "$gguf_path" ] || [ ! -f "$gguf_path" ]; then
            echo "  ❌ Download failed for $actual_repo"
            # Show the actual Python error — critical for diagnosing auth/network/version issues
            if [ -s "$_hf_err" ]; then
                echo "  Error detail: $(cat "$_hf_err")"
            fi
            rm -f "$_hf_err"
            echo "     Retry manually:"
            echo "       huggingface-cli download $actual_repo ${filename:-} --local-dir ~/Downloads"
            echo "     Then import: ./launch.sh import-gguf ~/Downloads/${filename:-model.gguf} $ollama_name"
            return 1
        fi
        rm -f "$_hf_err"

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
        "llama3.2:3b-instruct-q4_K_M"
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
        "llama3.2:3b-instruct-q4_K_M"
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

  install-mlx)
    echo "=== Installing mlx_lm (Apple Silicon native inference) ==="
    ARCH=$(uname -m)

    if [ "$ARCH" != "arm64" ]; then
        echo "  ℹ️  mlx_lm is Apple Silicon only. On Linux, Ollama GGUF handles inference."
        exit 0
    fi

    if ! command -v python3 &>/dev/null; then
        echo "  ❌ python3 required. Install: brew install python"
        exit 1
    fi

    echo "  Installing mlx-lm (>=0.30.5 required for Qwen3-Coder-Next)..."
    pip3 install "mlx-lm>=0.30.5" --upgrade --quiet 2>/dev/null || \
        pip3 install "mlx-lm>=0.30.5" --upgrade --quiet --break-system-packages
    # ASK-05: Verify version pin — prevents silent downgrade breaking Qwen3-Coder-Next
    python3 -c "import mlx_lm; from packaging.version import Version; \
        v=mlx_lm.__version__; assert Version(v)>=Version('0.30.5'), \
        f'mlx-lm {v} < 0.30.5 — Qwen3-Coder-Next requires >=0.30.5'; \
        print(f'  ✅ mlx-lm {v}')"

    # Create start wrapper
    MLX_DIR="$HOME/.portal5/mlx"
    mkdir -p "$MLX_DIR" "$HOME/.portal5/logs"

    cat > "$MLX_DIR/start.sh" << 'MLXSTART'
#!/bin/bash
# Portal 5 — mlx_lm inference server
# Usage: MLX_MODEL=mlx-community/Qwen3-Coder-Next-4bit ~/.portal5/mlx/start.sh
MODEL="${MLX_MODEL:-mlx-community/Qwen3-Coder-Next-4bit}"
PORT="${MLX_PORT:-8081}"
SPECULATIVE="${MLX_SPECULATIVE:-false}"
if [ "$SPECULATIVE" = "true" ]; then
    echo "[portal5-mlx] Speculative decoding: ENABLED"
    python3 -m mlx_lm.server --model "$MODEL" --port "$PORT" --host 0.0.0.0 \
        --speculative-decoding
else
    python3 -m mlx_lm.server --model "$MODEL" --port "$PORT" --host 0.0.0.0
fi
MLXSTART
    chmod +x "$MLX_DIR/start.sh"
    echo "  ✅ Start wrapper: $MLX_DIR/start.sh"

    # ── Register MLX as a launchd service (auto-start on login) ──────────────
    if [ "$(uname -s)" = "Darwin" ]; then
        PLIST_PATH="$HOME/Library/LaunchAgents/com.portal5.mlx.plist"
        # Find the Python that actually has mlx_lm installed
        # Falls back to system python3 if detection fails
        PYTHON_PATH=$(python3 -c "import mlx_lm, sys; print(sys.executable)" 2>/dev/null || which python3)
        if [ -z "$PYTHON_PATH" ]; then
            echo "  ❌ Cannot find Python with mlx_lm — install mlx-lm first"
            exit 1
        fi
        echo "  ✅ Using Python: $PYTHON_PATH"
        MLX_LOG_DIR="$HOME/.portal5/logs"
        mkdir -p "$MLX_LOG_DIR"

        cat > "$PLIST_PATH" << MLXPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.portal5.mlx</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>-m</string>
        <string>mlx_lm.server</string>
        <string>--model</string>
        <string>mlx-community/Qwen3-Coder-Next-4bit</string>
        <string>--port</string>
        <string>8081</string>
        <string>--host</string>
        <string>0.0.0.0</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${MLX_LOG_DIR}/mlx.log</string>
    <key>StandardErrorPath</key>
    <string>${MLX_LOG_DIR}/mlx-error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>${HOME}</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>MLX_SPECULATIVE</key>
        <string>${MLX_SPECULATIVE:-false}</string>
    </dict>
</dict>
</plist>
MLXPLIST

        launchctl load "$PLIST_PATH" 2>/dev/null || true
        echo "  ✅ launchd service registered: com.portal5.mlx"
        echo "  ✅ Auto-starts on login (will start after pull-mlx-models completes)"
        echo "  ℹ️  Start now:  launchctl start com.portal5.mlx"
        echo "  ℹ️  Stop:       launchctl stop com.portal5.mlx"
        echo "  ℹ️  Logs:       $MLX_LOG_DIR/mlx.log"
    fi

    echo ""
    echo "Next steps:"
    echo "  1. Pull MLX models:  ./launch.sh pull-mlx-models"
    echo "  2. Start inference:  ~/.portal5/mlx/start.sh"
    echo "  3. Start Portal:     ./launch.sh up"
    echo ""
    echo "Speculative decoding (~1.5x throughput):"
    echo "  MLX_SPECULATIVE=true ~/.portal5/mlx/start.sh"
    echo "  Or set MLX_SPECULATIVE=true in .env and restart:"
    echo "    launchctl stop com.portal5.mlx && launchctl start com.portal5.mlx"
    echo ""
    echo "NOTE: mlx_lm serves ONE model at a time."
    echo "      Portal automatically falls back to Ollama when mlx_lm is not running."
    ;;

  switch-mlx-model)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    MODEL="${2:-}"
    if [ -z "$MODEL" ]; then
        echo "Usage: ./launch.sh switch-mlx-model <mlx-community/model-tag>"
        echo ""
        echo "Available MLX models (pull first with ./launch.sh pull-mlx-models):"
        echo "  mlx-community/Qwen3-Coder-Next-4bit          (~18GB — primary coder)"
        echo "  mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit  (~17GB)"
        echo "  mlx-community/DeepSeek-R1-0528-4bit         (~18GB — reasoning)"
        echo "  mlx-community/Llama-3.2-3B-Instruct-4bit    (~2GB — fast routing)"
        echo "  mlx-community/Llama-3.3-70B-Instruct-4bit   (~40GB — heavy, unload others first)"
        echo ""
        echo "Current: ${MLX_MODEL:-mlx-community/Qwen3-Coder-Next-4bit}"
        exit 1
    fi

    echo "Switching MLX model to: $MODEL"

    # Update MLX_MODEL in .env (backup original)
    if [ -f "$ENV_FILE" ]; then
        cp "$ENV_FILE" "$ENV_FILE.bak"
        if sed -i.bak "s|^MLX_MODEL=.*|MLX_MODEL=${MODEL}|" "$ENV_FILE" 2>/dev/null; then
            rm -f "$ENV_FILE.bak"
            echo "  ✅ Updated MLX_MODEL in .env"
        else
            mv "$ENV_FILE.bak" "$ENV_FILE"
            echo "  ❌ Failed to update .env — check MLX_MODEL=$MODEL is valid"
            exit 1
        fi
    else
        echo "  ⚠️  .env not found — MLX_MODEL env var only (session-scoped)"
    fi

    # Regenerate start.sh with new model
    MLX_DIR="$HOME/.portal5/mlx"
    if [ -f "$MLX_DIR/start.sh" ]; then
        sed -i.bak "s|^MODEL=.*|MODEL=\"${MODEL}\"|" "$MLX_DIR/start.sh" 2>/dev/null || \
            sed "s|^MODEL=.*|MODEL=\"${MODEL}\"|" "$MLX_DIR/start.sh" > "${MLX_DIR/start.sh}.new" && \
            mv "${MLX_DIR/start.sh}.new" "$MLX_DIR/start.sh"
        rm -f "$MLX_DIR/start.sh.bak"
        echo "  ✅ Updated $MLX_DIR/start.sh"
    fi

    # Regenerate and restart launchd service (macOS)
    if [ "$(uname -s)" = "Darwin" ]; then
        PLIST_PATH="$HOME/Library/LaunchAgents/com.portal5.mlx.plist"
        if [ -f "$PLIST_PATH" ]; then
            PYTHON_PATH=$(python3 -c "import mlx_lm, sys; print(sys.executable)" 2>/dev/null || which python3)
            MLX_LOG_DIR="$HOME/.portal5/logs"
            MLX_SPECULATIVE_VAL="${MLX_SPECULATIVE:-false}"
            cat > "$PLIST_PATH" << MLXPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.portal5.mlx</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>-m</string>
        <string>mlx_lm.server</string>
        <string>--model</string>
        <string>${MODEL}</string>
        <string>--port</string>
        <string>8081</string>
        <string>--host</string>
        <string>0.0.0.0</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${MLX_LOG_DIR}/mlx.log</string>
    <key>StandardErrorPath</key>
    <string>${MLX_LOG_DIR}/mlx-error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>${HOME}</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>MLX_SPECULATIVE</key>
        <string>${MLX_SPECULATIVE_VAL}</string>
    </dict>
</dict>
</plist>
MLXPLIST
            launchctl unload "$PLIST_PATH" 2>/dev/null || true
            launchctl load "$PLIST_PATH" 2>/dev/null || true
            echo "  ✅ Restarted com.portal5.mlx service"
        fi
    fi

    echo ""
    echo "✅ MLX model switched to: $MODEL"
    echo "   Allow ~30s for model to load before querying."
    echo "   Verify: curl -s http://localhost:8081/v1/models | python3 -m json.tool"
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
    echo "Models download to: ~/.cache/huggingface/hub/"
    echo ""

    # Standard MLX models (confirmed on mlx-community)
    MLX_MODELS=(
        # Coding — primary workspace models
        "mlx-community/Qwen3-Coder-Next-4bit"              # ~18GB active
        "mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit"  # ~17GB
        "mlx-community/Qwen3.5-35B-A3B-4bit"               # ~20GB
        "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-4bit-mlx"  # ~9GB
        "mlx-community/Devstral-Small-2505-4bit"            # ~13GB
        # Reasoning
        "mlx-community/DeepSeek-R1-0528-4bit"              # ~18GB
        "mlx-community/Qwen3.5-27B-4bit"                   # ~15GB
        # General / fast routing
        "mlx-community/Llama-3.2-3B-Instruct-4bit"         # ~2GB — ultra-fast
    )

    # Heavy models — gated behind PULL_HEAVY=true
    HEAVY_MLX_MODELS=(
        "mlx-community/Llama-3.3-70B-Instruct-4bit"        # ~40GB — unload others first
    )

    total=${#MLX_MODELS[@]}
    count=0
    failed=0

    for model in "${MLX_MODELS[@]}"; do
        count=$((count + 1))
        echo "[$count/$total] $model"
        _mlx_err=$(mktemp)
        if python3 -W ignore -c "
import warnings; warnings.filterwarnings('ignore')
from huggingface_hub import snapshot_download
snapshot_download('$model', ignore_patterns=['*.md','*.txt','*.safetensors.index.json'])
" 2>"$_mlx_err"; then
            echo "  ✅ Downloaded"
        else
            echo "  ❌ Failed"
            [ -s "$_mlx_err" ] && echo "  Error: $(cat "$_mlx_err" | tail -1)"
            echo "  Retry: huggingface-cli download $model"
            failed=$((failed + 1))
        fi
        rm -f "$_mlx_err"
        echo ""
    done

    if [ "${PULL_HEAVY:-false}" = "true" ]; then
        echo "Pulling heavy MLX models (PULL_HEAVY=true) — ensure <24GB RAM is free..."
        for model in "${HEAVY_MLX_MODELS[@]}"; do
            echo "  Downloading: $model (~40GB)"
            _mlx_err=$(mktemp)
            if python3 -W ignore -c "
import warnings; warnings.filterwarnings('ignore')
from huggingface_hub import snapshot_download
snapshot_download('$model', ignore_patterns=['*.md','*.txt','*.safetensors.index.json'])
" 2>"$_mlx_err"; then
                echo "  ✅ Done"
            else
                echo "  ❌ Failed"
                [ -s "$_mlx_err" ] && echo "  Error: $(cat "$_mlx_err" | tail -1)"
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
    # Qwen3.5-35B-A3B-4bit and Qwen3.5-27B-4bit are now UNCOMMENTED in backends.yaml
    # — this block watches for future model publishes only.
    echo ""
    echo "=== Checking Qwen3.5 MLX watch (future publishes) ==="
    echo "  ℹ️  Qwen3.5-35B-A3B-4bit and Qwen3.5-27B-4bit: enabled (see backends.yaml)"
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
    echo "Usage: ./launch.sh [up|down|clean|clean-all|seed|logs|status|pull-models|refresh-models|import-gguf|test|add-user|list-users|backup|restore|up-telegram|up-slack|up-channels|install-ollama|install-comfyui|install-mlx|download-comfyui-models|pull-mlx-models|switch-mlx-model|rebuild]"
    echo ""
    echo "  up                    Start all services (first run auto-generates secrets)"
    echo "  install-ollama        Install Ollama natively via brew (Apple Silicon recommended)"
    echo "  install-comfyui       Install ComfyUI natively via git+pip (Apple Silicon)"
    echo "  install-mlx           Install mlx_lm for native Apple Silicon inference"
    echo "  download-comfyui-models  Download image/video models to ~/ComfyUI/models/"
    echo "  pull-mlx-models       Download MLX model weights to HF cache"
    echo "  switch-mlx-model <tag>  Hot-swap MLX inference model (updates .env + restarts service)"
    echo "  rebuild               Rebuild portal-pipeline Docker image + restart (after git pull)"
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
