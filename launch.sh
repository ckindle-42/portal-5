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

    # Clean up sed backup files
    rm -f "${tmp}.bak"

    if [ $changed -eq 1 ]; then
        cp "$tmp" "$env_file"
        echo "[portal-5] Secrets written to .env"
    fi
    rm -f "$tmp"
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

    set -a; source "$ENV_FILE"; set +a

    # Validate required secrets are set and not placeholder values
    for var in PIPELINE_API_KEY WEBUI_SECRET_KEY OPENWEBUI_ADMIN_PASSWORD; do
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
    echo "[portal-5] Stack started. Open WebUI: http://localhost:8080"
    ;;
  down)
    cd "$COMPOSE_DIR"
    docker compose down
    ;;
  clean)
    cd "$COMPOSE_DIR"
    echo "[portal-5] Stopping services..."
    docker compose down

    echo "[portal-5] Removing Open WebUI data volume..."
    # Remove only the open-webui-data volume — NOT ollama-models
    # Docker Compose prefixes volumes with the project directory name
    local project_name
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
        # Security / Red Team / Blue Team
        "xploiter/the-xploiter"
        "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0"
        "huihui_ai/baronllm-abliterated"
        # Deep reasoning / research / data
        "huihui_ai/tongyi-deepresearch-abliterated:30b"
        # Coding
        "qwen3-coder-next:30b-q5"
        "devstral:24b"
        "deepseek-coder:16b-instruct-q4_K_M"
        # Vision / multimodal
        "qwen3-omni:30b"
        "llava:7b"
        # Large general (requires 48GB+ RAM)
        # "dolphin-llama3:70b"
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
  *)
    echo "Usage: ./launch.sh [up|down|clean|clean-all|seed|logs|status|pull-models]"
    echo ""
    echo "  up           Start all services (first run auto-generates secrets)"
    echo "  down         Stop all services (data preserved)"
    echo "  clean        Stop + wipe Open WebUI data (Ollama models preserved)"
    echo "  clean-all    Stop + wipe everything including Ollama models"
    echo "  seed         Re-run Open WebUI seeding (workspaces + personas + tools)"
    echo "  logs [svc]   Tail logs (default: portal-pipeline)"
    echo "  status       Show service status and health"
    echo "  pull-models  Pull all Portal 5 Ollama models (30-90 min)"
    ;;
esac
