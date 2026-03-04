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
    echo "Usage: ./launch.sh [up|down|clean|clean-all|seed|logs|status|pull-models|add-user|list-users]"
    echo ""
    echo "  up           Start all services (first run auto-generates secrets)"
    echo "  down         Stop all services (data preserved)"
    echo "  clean        Stop + wipe Open WebUI data (Ollama models preserved)"
    echo "  clean-all    Stop + wipe everything including Ollama models"
    echo "  seed         Re-run Open WebUI seeding (workspaces + personas + tools)"
    echo "  logs [svc]   Tail logs (default: portal-pipeline)"
    echo "  status       Show service status and health"
    echo "  pull-models  Pull all Portal 5 Ollama models (30-90 min)"
    echo "  add-user <email> [name] [role]  Create a user account"
    echo "  list-users   List all registered users"
    ;;
esac
