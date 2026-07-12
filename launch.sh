#!/bin/bash
set -euo pipefail
PORTAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$PORTAL_ROOT/deploy/portal-5"
ENV_FILE="$PORTAL_ROOT/.env"


# ── Sourced libraries ─────────────────────────────────────────────────────────
# shellcheck source=scripts/lib/util.sh
source "$PORTAL_ROOT/scripts/lib/util.sh"
# shellcheck source=scripts/lib/services.sh
source "$PORTAL_ROOT/scripts/lib/services.sh"
# shellcheck source=scripts/lib/lab.sh
source "$PORTAL_ROOT/scripts/lib/lab.sh"
# shellcheck source=scripts/lib/backup.sh
source "$PORTAL_ROOT/scripts/lib/backup.sh"
# shellcheck source=scripts/lib/users.sh
source "$PORTAL_ROOT/scripts/lib/users.sh"

case "${1:-up}" in
  up)
    # Copy example if .env doesn't exist
    if [ ! -f "$ENV_FILE" ]; then
        cp "$PORTAL_ROOT/.env.example" "$ENV_FILE"
        echo "[portal-5] Created .env from .env.example"
    fi

    # Generate any secrets still set to CHANGEME
    bootstrap_secrets "$ENV_FILE"

    # TASK-WORKSPACE-001: ensure workspace exists before bind mounts go live
    WS="${AI_OUTPUT_DIR:-${HOME}/AI_Output}"
    if [ ! -d "${WS}/uploads" ] || [ ! -d "${WS}/generated/transcripts" ]; then
      echo "Initializing workspace structure..."
      mkdir -p "${WS}"/{uploads,generated/transcripts,generated/documents,generated/images,generated/videos,generated/music,generated/speech}
      chmod -R 0775 "${WS}" 2>/dev/null || true
    fi

    # Tear down any previously running stack so ports are clean before we start
    echo "[portal-5] Stopping any existing Portal 5 services..."
    _do_down

    # Pull latest Docker images before bringing the stack up
    echo "[portal-5] Pulling latest Docker images..."
    cd "$COMPOSE_DIR"
    docker compose pull || echo "[portal-5] ⚠️  Some images could not be pulled — using cached versions."

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

    if [ -n "${PORTAL_PUBLIC_URL:-}" ]; then
        _BASE="${PORTAL_PUBLIC_URL%/}"
        export MUSIC_PUBLIC_URL="${_BASE}/files/music"
        export TTS_PUBLIC_URL="${_BASE}/files/tts"
        export VIDEO_PUBLIC_URL="${_BASE}/files/video"
        export COMFYUI_PUBLIC_URL="${_BASE}/comfyui"
        echo "[portal-5] Public media URLs derived from PORTAL_PUBLIC_URL=${_BASE}"
        echo "[portal-5]   For Cloudflare Tunnel, see config/cloudflared/config.yml.example"
    fi

    # Auto-detect channel profiles from .env tokens
    _PROFILES=""
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
        _PROFILES="$_PROFILES --profile telegram"
        echo "[portal-5] Telegram token configured — including Telegram bot"
    fi
    if [ -n "${SLACK_BOT_TOKEN:-}" ] && [ -n "${SLACK_APP_TOKEN:-}" ]; then
        _PROFILES="$_PROFILES --profile slack"
        echo "[portal-5] Slack tokens configured — including Slack bot"
    fi
    echo "[portal-5] Starting stack..."
    cd "$COMPOSE_DIR"
    docker compose $_PROFILES up -d


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
    exec python3 -m portal.platform.inference.cli test "${@:2}"
    ;;

  promptfoo)
    # Run LLM quality evaluations via Promptfoo against Portal 5 Ollama models
    # Usage: ./launch.sh promptfoo [area]   (area: coding|daily|reasoning|security|document|media|strategic|all)
    # Grading (llm-rubric) runs locally on ollama:chat:gemma4:26b-a4b-it-qat — no cloud API keys needed.
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    if command -v promptfoo >/dev/null 2>&1; then
        PF="promptfoo"
    elif command -v npx >/dev/null 2>&1; then
        PF="npx --yes promptfoo@latest"
    else
        echo "ERROR: promptfoo not found. Install: pip install promptfoo   (or: npm install -g promptfoo)"
        exit 1
    fi
    AREA="${2:-all}"
    echo "=== Portal 5 — Promptfoo LLM Quality Evaluations ($PF) ==="
    echo ""
    if [ "$AREA" = "all" ]; then
        for cfg in config/promptfoo/*_quality.yaml; do
            echo "--- Running: $cfg ---"
            $PF eval -c "$cfg" --no-cache -j 1
            echo ""
        done
    else
        CFG="config/promptfoo/${AREA}_quality.yaml"
        if [ -f "$CFG" ]; then
            $PF eval -c "$CFG" --no-cache -j 1
        else
            echo "ERROR: config not found: $CFG"
            echo "Available: coding, daily, reasoning, security, document, media, strategic, all"
            exit 1
        fi
    fi
    echo "=== Done. Run '$PF view' for interactive results ==="
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


  lab-up)
    _launch_lab_up
    ;;

  lab-up-wazuh)
    _launch_lab_up_wazuh
    ;;

  lab-down)
    _launch_lab_down
    ;;

  lab-status)
    _launch_lab_status
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
    _do_down
    ;;

  backup)
    _launch_backup "$@"
    ;;

  restore)
    _launch_restore "$@"
    ;;

  build-lab-attack)
    _launch_build_lab_attack
    ;;

  rebuild)
    # Rebuild and restart all Docker images (pipeline + MCP servers)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    cd "$COMPOSE_DIR"
    MCP_SERVICES="mcp-documents mcp-tts mcp-whisper mcp-sandbox mcp-security mcp-research mcp-memory mcp-rag playwright-mcp mcp-cad-render mcp-proxmox mcp-reranker"
    [ -d "${COMFYUI_DIR:-$HOME/ComfyUI}" ] && MCP_SERVICES="$MCP_SERVICES mcp-comfyui mcp-video"
    echo "[portal-5] Rebuilding portal-pipeline..."
    docker compose build portal-pipeline
    echo "[portal-5] Rebuilding MCP images..."
    docker compose build $MCP_SERVICES
    echo "[portal-5] Building native arm64 PowerShell sandbox image..."
    docker build -t portal5-pwsh:latest -f "$PORTAL_ROOT/Dockerfile.pwsh" "$PORTAL_ROOT"
    echo "[portal-5] Loading pwsh image into DinD..."
    docker save portal5-pwsh:latest | docker exec -i portal5-dind docker load
    echo "[portal-5] Restarting all rebuilt containers..."
    docker compose up -d --no-deps portal-pipeline $MCP_SERVICES
    echo "[portal-5] Done. Check status: ./launch.sh status"
    ;;

  rebuild-mcp)
    # Rebuild and restart all MCP containers (e.g. after a docker-compose.yml or Dockerfile.mcp change)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    cd "$COMPOSE_DIR"
    MCP_SERVICES="mcp-documents mcp-tts mcp-whisper mcp-sandbox mcp-security mcp-research mcp-memory mcp-rag playwright-mcp mcp-cad-render mcp-proxmox mcp-reranker"
    [ -d "${COMFYUI_DIR:-$HOME/ComfyUI}" ] && MCP_SERVICES="$MCP_SERVICES mcp-comfyui mcp-video"
    echo "[portal-5] Rebuilding MCP images..."
    docker compose build $MCP_SERVICES
    echo "[portal-5] Building native arm64 PowerShell sandbox image..."
    docker build -t portal5-pwsh:latest -f "$PORTAL_ROOT/Dockerfile.pwsh" "$PORTAL_ROOT"
    echo "[portal-5] Loading pwsh image into DinD..."
    docker save portal5-pwsh:latest | docker exec -i portal5-dind docker load
    echo "[portal-5] Restarting MCP containers..."
    docker compose up -d --no-deps $MCP_SERVICES
    echo "[portal-5] Done. Check status: ./launch.sh status"
    ;;

  restart-mcp)
    # Restart all MCP containers without rebuilding (e.g. after a config or env change)
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    cd "$COMPOSE_DIR"
    MCP_SERVICES="mcp-documents mcp-tts mcp-whisper mcp-sandbox mcp-security mcp-research mcp-memory mcp-rag playwright-mcp mcp-cad-render"
    [ -d "${COMFYUI_DIR:-$HOME/ComfyUI}" ] && MCP_SERVICES="$MCP_SERVICES mcp-comfyui mcp-video"
    echo "[portal-5] Restarting MCP containers..."
    docker compose restart $MCP_SERVICES
    echo "[portal-5] Done. Check status: ./launch.sh status"
    ;;

  update)
    exec python3 -m portal.platform.inference.cli update "${@:2}"
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
  sync-readme)
    if [ ! -f "${PORTAL_ROOT}/ACCEPTANCE_RESULTS.md" ]; then
      echo "No ACCEPTANCE_RESULTS.md to sync from. Run acceptance tests first:"
      echo "  python3 tests/portal5_acceptance_v6.py"
      exit 1
    fi
    python3 << 'PYEOF'
import re
from pathlib import Path

root = Path(__file__).parent if '__file__' in dir() else Path('.')
results = (root / "ACCEPTANCE_RESULTS.md").read_text()
readme = (root / "README.md").read_text()

# Extract Summary block from ACCEPTANCE_RESULTS.md (between ## Summary and ## Results)
summary_match = re.search(r'(## Summary.*?)(?=## Results)', results, re.DOTALL)
summary_block = summary_match.group(1).strip() if summary_match else "*(see ACCEPTANCE_RESULTS.md)*"

# Extract date line
date_match = re.search(r'\*\*Date:\*\*\s*([^\n]+)', results)
date_str = date_match.group(1).strip() if date_match else "unknown"

new_block = f"""### Acceptance Testing

The full acceptance test suite (`tests/portal5_acceptance_v6.py`) runs
~250 checks across 30 sections. Run with:

```bash
python3 tests/portal5_acceptance_v6.py
python3 tests/portal5_acceptance_v6.py --section S70
```

Latest run ({date_str}):

{summary_block}

See [ACCEPTANCE_RESULTS.md](ACCEPTANCE_RESULTS.md) for full results.
"""

new_readme = re.sub(
    r'### Acceptance Testing.*?(?=\n## |\n### |\Z)',
    new_block,
    readme,
    count=1,
    flags=re.DOTALL,
)

if new_readme == readme:
    print("README.md: no '### Acceptance Testing' section found — nothing to update.")
else:
    (root / "README.md").write_text(new_readme)
    print("README.md acceptance section refreshed.")
PYEOF
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
    exec python3 -m portal.platform.inference.cli models pull "${@:2}"
    ;;

  refresh-models)
    exec python3 -m portal.platform.inference.cli models refresh "${@:2}"
    ;;

  add-user)
    _launch_add_user "$@"
    ;;

  list-users)
    _launch_list_users
    ;;

  install-ollama)
    _launch_install_ollama
    ;;

  install-comfyui)
    _launch_install_comfyui
    ;;

  install-music)
    _launch_install_music
    ;;

  start-speech)
    _launch_start_speech
    ;;

  start-embedding-cpu-arm)
    _launch_start_embedding_cpu_arm
    ;;

  stop-embedding-cpu-arm)
    _launch_stop_embedding_cpu_arm
    ;;

  install-embedding-service)
    _launch_install_embedding_service
    ;;

  uninstall-embedding-service)
    _launch_uninstall_embedding_service
    ;;

  install-powermetrics)
    _launch_install_powermetrics
    ;;

  uninstall-powermetrics)
    _launch_uninstall_powermetrics
    ;;

  stop-speech)
    _launch_stop_speech
    ;;

  workspace-init)
    exec python3 -m portal.platform.inference.cli workspace init "${@:2}"
    ;;

  workspace-status)
    exec python3 -m portal.platform.inference.cli workspace status "${@:2}"
    ;;

  workspace-show)
    exec python3 -m portal.platform.inference.cli workspace show "${@:2}"
    ;;

  start-transcribe)
    _launch_start_transcribe
    ;;

  stop-transcribe)
    _launch_stop_transcribe
    ;;

  apply-model-params)
    exec python3 -m portal.platform.inference.cli models apply-params "${@:2}"
    ;;

  import-gguf)
    exec python3 -m portal.platform.inference.cli models import-gguf "${@:2}"
    ;;

  download-comfyui-models)
    _launch_download_comfyui_models
    ;;

  apply-mtp-drafts)
    exec python3 -m portal.platform.inference.cli models apply-mtp-drafts "${@:2}"
    ;;

  sync-config)
    exec python3 -m portal.platform.inference.cli sync-config "${@:2}"
    ;;


    *)
    echo "Usage: ./launch.sh [up|down|clean|clean-all|seed|reseed|logs|status|sync-config|update|pull-models|refresh-models|import-gguf|test|promptfoo|add-user|list-users|backup|restore|up-telegram|up-slack|up-channels|install-ollama|install-comfyui|install-music|download-comfyui-models|start-speech|stop-speech|start-transcribe|stop-transcribe|start-embedding-cpu-arm|stop-embedding-cpu-arm|install-embedding-service|uninstall-embedding-service|install-powermetrics|uninstall-powermetrics|rebuild|workspace-init|workspace-status|workspace-show|pull-wan22|pull-qwen-image|apply-mtp-drafts|build-lab-attack]"
    echo ""
    echo "  up                    Start all services (first run auto-generates secrets)"
    echo "  install-ollama        Install Ollama natively via brew (Apple Silicon recommended)"
    echo "  install-comfyui       Install ComfyUI natively via git+pip (Apple Silicon)"
    echo "  install-music         Install Music MCP natively via venv (Apple Silicon / MPS)"
    echo "  download-comfyui-models  Download image/video models to ~/ComfyUI/models/"
  echo "  pull-wan22            Pull Wan 2.2 ComfyUI models (T2V-A14B/TI2V-5B/Animate-14B/S2V-14B, ~80 GB)"
  echo "  pull-qwen-image       Pull Qwen-Image-2512 family (2512/Edit-2511/Lightning, ~30 GB)"
    echo "  start-speech          Start MLX Speech server (Qwen3-TTS + Qwen3-ASR)"
    echo "  stop-speech           Stop MLX Speech server"
    echo "  start-transcribe      Start MLX Transcribe server (mlx-whisper + pyannote diarization, :8924)"
    echo "  stop-transcribe       Stop MLX Transcribe server"
    echo ""
    echo "  workspace-init        Create shared workspace directory structure (uploads, generated/*)"
    echo "  workspace-status      Show file counts and disk usage per category"
    echo "  workspace-show        Print resolved paths for the current configuration"
    echo "  start-embedding-cpu-arm  Start native ARM64 embedding server (Apple Silicon, no Rosetta)"
    echo "  stop-embedding-cpu-arm   Stop ARM64 embedding server"
    echo "  install-embedding-service   Install launchd agent — embedding starts at login, auto-restarts on crash"
    echo "  uninstall-embedding-service Remove launchd agent"
    echo "  install-powermetrics        Install powermetrics daemon (sudo) — power telemetry for cost tracking"
    echo "  uninstall-powermetrics      Remove powermetrics daemon (sudo)"
    echo "  rebuild               Rebuild all Docker images (pipeline + MCP) + restart (after git pull)"
    echo "  build-lab-attack      Build the arm64 attack image (portal5-attack) for the lab-exec lane + load into DinD"
    echo "  update                Full update: git pull, Docker images, rebuilds, model refresh, re-seed"
    echo "                          --skip-models   Skip Ollama model refresh"
    echo "                          --models-only   Only refresh models (Ollama)"
    echo "                          --yes / -y      Skip confirmation prompts"
      echo "  up-telegram           Force-start Telegram bot (auto-detected by 'up' when TELEGRAM_BOT_TOKEN is set)"
    echo "  up-slack              Force-start Slack bot (auto-detected by 'up' when SLACK_BOT_TOKEN + SLACK_APP_TOKEN are set)"
    echo "  up-channels           Force-start both Telegram and Slack bots"
    echo "  lab-up                Start Incalmo C2 + Talon SOC analyst (lab profile, no Wazuh)"
    echo "  lab-up-wazuh          Start Incalmo + Talon + full Wazuh SIEM stack (~6GB extra RAM)"
    echo "  lab-down              Stop all lab services"
    echo "  lab-status            Show lab container status"
    echo "  test                  Run end-to-end smoke tests against the live stack"
    echo "  promptfoo [area]      Run LLM quality evals (coding|daily|reasoning|security|document|media|strategic|all)"
    echo "  down                  Stop all services (data preserved)"
    echo "  clean                 Stop + wipe Open WebUI data (Ollama models preserved)"
    echo "  clean-all             Stop + wipe everything including Ollama models"
    echo "  sync-config           Regenerate derived artifacts from config/portal.yaml"
    echo "                          (workspace_routing in backends.yaml, .mcp.json, OWUI presets)"
    echo "  seed                  Re-run Open WebUI seeding (workspaces + personas + tools)"
    echo "  logs [svc]            Tail logs (default: portal-pipeline; also: open-webui, searxng)"
    echo "  status                Show service status and health"
    echo "  pull-models           Pull all Portal 5 Ollama models (30-90 min)"
    echo "  refresh-models        Check all models for updates (skips unchanged models)"
    echo "  apply-model-params        Create Ollama ctx-tagged variants (e.g. qwen3-coder:480b-...-ctx32k)"
    echo "  apply-mtp-drafts          Wire Qwen3.6-27B MTP A/B pair (q8_0 base + mtp-q4 draft → portal5/... tag)"
    echo "  import-gguf <path> [name]  Import a locally downloaded GGUF file into Ollama"
    echo "  add-user <email> [name] [role]  Create a user account"
    echo "  list-users            List all registered users"
    echo "  backup                Back up all data to ./backups/ (or specified path)"
    echo "  restore               Restore data from a backup directory"
    ;;
esac
