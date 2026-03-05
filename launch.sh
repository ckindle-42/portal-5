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
    if command -v python3 &>/dev/null; then
        RAM_GB=$(python3 -c "
import os
with open('/proc/meminfo') as f:
    for line in f:
        if 'MemTotal' in line:
            print(int(line.split()[1]) // 1024 // 1024)
            break
" 2>/dev/null || echo 0)
        if [ "$RAM_GB" -lt 16 ] 2>/dev/null; then
            echo "  ⚠️  RAM: ${RAM_GB}GB detected — 16GB minimum required"
            echo "     Portal 5 may crash or fail to load models"
            WARN=1
        elif [ "$RAM_GB" -lt 32 ] 2>/dev/null; then
            echo "  ℹ️  RAM: ${RAM_GB}GB — enough for core models (32GB+ for full catalog)"
        else
            echo "  ✅ RAM: ${RAM_GB}GB"
        fi
    fi

    # Disk check (need ≥20GB free; FLUX alone is ~12GB)
    DISK_FREE=$(df -BG . 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G' || echo 0)
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

    set -a; source "$ENV_FILE"; set +a

    # Validate required secrets are set and not placeholder values
    for var in PIPELINE_API_KEY WEBUI_SECRET_KEY OPENWEBUI_ADMIN_PASSWORD SEARXNG_SECRET_KEY GRAFANA_PASSWORD; do
        val="${!var:-}"
        if [ -z "$val" ] || [ "$val" = "CHANGEME" ]; then
            echo "ERROR: $var is not set or still CHANGEME in .env"
            echo "  Run: ./launch.sh up  (secrets are auto-generated)"
            exit 1
        fi
    done

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
    cd "$COMPOSE_DIR"
    docker compose --profile slack up -d
    echo "[portal-5] Stack + Slack started"
    echo "  Mention @portal in any channel to verify"
    ;;

  up-channels)
    # Start core stack + both Telegram and Slack
    set -a; source "$ENV_FILE"; set +a
    cd "$COMPOSE_DIR"
    docker compose --profile telegram --profile slack up -d
    echo "[portal-5] Stack + all channels started"
    ;;

  down)
    cd "$COMPOSE_DIR"
    docker compose down
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
    cd "$COMPOSE_DIR"

    # Verify ollama container is running
    if ! docker ps --format '{{.Names}}' | grep -q "portal5-ollama"; then
        echo "ERROR: portal5-ollama is not running. Start the stack first: ./launch.sh up"
        exit 1
    fi

    echo "=== Portal 5: Pulling additional models ==="
    echo "This may take 30-90 minutes depending on connection speed."
    echo "Pulled models survive docker compose down (stored in ollama-models volume)."
    echo ""

    # Add or remove models here — one per line
    MODELS=(
        # ── Security (priority — core use case) ───────────────────────────
        # BaronLLM Offensive Security (~18GB Q6_K — best for red team)
        "hf.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF"
        # Lily-Cybersecurity 7B — fast, balanced red/blue, zero refusals
        "hf.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF"
        # The-Xploiter — classic offensive security specialist
        "xploiter/the-xploiter"
        # WhiteRabbitNeo 8B — fast classic security
        "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0"
        # BaronLLM abliterated — uncensored general
        "huihui_ai/baronllm-abliterated"

        # ── Coding ──────────────────────────────────────────────────────
        # Qwen3-Coder 30B — best agentic coding, Splunk/BigFix/PPT
        "qwen3-coder-next:30b-q5"
        # GLM-4.7-Flash — fast MoE, strong PowerShell/C#/SQL
        "hf.co/unsloth/GLM-4.7-Flash-GGUF"
        # DeepSeek-Coder V2 16B — Splunk SPL specialist
        "deepseek-coder:16b-instruct-q4_K_M"
        # Devstral 24B — agentic development workflows
        "devstral:24b"

        # ── Reasoning / Research ────────────────────────────────────────
        # DeepSeek-R1 32B — deep reasoning + code (~16GB)
        "hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF"
        # Tongyi DeepResearch 30B — abliterated, research synthesis
        "huihui_ai/tongyi-deepresearch-abliterated:30b"

        # ── Vision ──────────────────────────────────────────────────────
        "qwen3-omni:30b"
        "llava:7b"

        # ── Large General (requires 48GB+ free RAM, commented by default) ─
        # "hf.co/cognitivecomputations/dolphin-3-llama3-70b-GGUF"
        # "hf.co/WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF"
    )

    total=${#MODELS[@]}
    count=0
    failed=0
    for model in "${MODELS[@]}"; do
        count=$((count + 1))
        echo "[$count/$total] Pulling: $model"
        if docker exec portal5-ollama ollama pull "$model"; then
            echo "  ✅ $model"
        else
            echo "  ❌ Failed: $model"
            failed=$((failed + 1))
        fi
        echo ""
    done

    echo "=== Pull complete: $((total - failed))/$total succeeded ==="
    if [ $failed -gt 0 ]; then
        echo "  $failed model(s) failed — check logs above"
    fi
    echo ""
    echo "Restart the pipeline to pick up new models:"
    echo "  docker compose -f $COMPOSE_DIR/docker-compose.yml restart portal-pipeline"
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

  *)
    echo "Usage: ./launch.sh [up|down|clean|clean-all|seed|logs|status|pull-models|test|add-user|list-users|backup|restore|up-telegram|up-slack|up-channels]"
    echo ""
    echo "  up           Start all services (first run auto-generates secrets)"
    echo "  up-telegram  Start core stack + Telegram bot (requires TELEGRAM_BOT_TOKEN in .env)"
    echo "  up-slack     Start core stack + Slack bot (requires SLACK_BOT_TOKEN + SLACK_APP_TOKEN in .env)"
    echo "  up-channels  Start core stack + both Telegram and Slack"
    echo "  test         Run end-to-end smoke tests against the live stack"
    echo "  down         Stop all services (data preserved)"
    echo "  clean        Stop + wipe Open WebUI data (Ollama models preserved)"
    echo "  clean-all    Stop + wipe everything including Ollama models"
    echo "  seed         Re-run Open WebUI seeding (workspaces + personas + tools)"
    echo "  logs [svc]   Tail logs (default: portal-pipeline)"
    echo "  status       Show service status and health"
    echo "  pull-models  Pull all Portal 5 Ollama models (30-90 min)"
    echo "  add-user <email> [name] [role]  Create a user account"
    echo "  list-users   List all registered users"
    echo "  backup       Back up all data to ./backups/ (or specified path)"
    echo "  restore      Restore data from a backup directory"
    ;;
esac
