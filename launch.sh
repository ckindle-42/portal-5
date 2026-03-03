#!/bin/bash
set -euo pipefail
PORTAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-up}" in
  up)
    cp -n "$PORTAL_ROOT/.env.example" "$PORTAL_ROOT/.env" 2>/dev/null || true
    set -a; source "$PORTAL_ROOT/.env"; set +a
    echo "[portal-5] Starting stack..."
    cd "$PORTAL_ROOT/deploy/portal-5"
    docker compose up -d
    echo "[portal-5] Stack started. Open WebUI: http://localhost:8080"
    ;;
  down)
    cd "$PORTAL_ROOT/deploy/portal-5"
    docker compose down
    ;;
  clean)
    cd "$PORTAL_ROOT/deploy/portal-5"
    docker compose down
    # Remove named volumes (preserves ollama-models by default)
    docker compose down -v --remove-orphans 2>/dev/null || true
    echo "[portal-5] Clean complete (Open WebUI data wiped, Ollama models preserved)."
    echo "Run ./launch.sh up for fresh start."
    ;;
  clean-all)
    cd "$PORTAL_ROOT/deploy/portal-5"
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
    cd "$PORTAL_ROOT/deploy/portal-5"
    docker compose logs -f "${2:-portal-pipeline}"
    ;;
  status)
    cd "$PORTAL_ROOT/deploy/portal-5"
    docker compose ps
    echo ""
    echo "Pipeline health:"
    curl -s http://localhost:9099/health 2>/dev/null | python3 -m json.tool || echo "  Pipeline not reachable"
    echo ""
    echo "Open WebUI: http://localhost:8080"
    ;;
  pull-models)
    echo "=== Pulling additional Portal 5 models ==="
    echo "This may take 30-90 minutes depending on your connection."
    echo ""
    # Security models
    docker exec portal5-ollama ollama pull xploiter/the-xploiter || true
    docker exec portal5-ollama ollama pull "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0" || true
    docker exec portal5-ollama ollama pull huihui_ai/baronllm-abliterated || true
    # Reasoning / research
    docker exec portal5-ollama ollama pull "huihui_ai/tongyi-deepresearch-abliterated:30b" || true
    # Coding
    docker exec portal5-ollama ollama pull "qwen3-coder-next:30b-q5" || true
    docker exec portal5-ollama ollama pull "devstral:24b" || true
    docker exec portal5-ollama ollama pull "deepseek-coder:16b-instruct-q4_K_M" || true
    # Vision
    docker exec portal5-ollama ollama pull "qwen3-omni:30b" || true
    docker exec portal5-ollama ollama pull "llava:7b" || true
    echo ""
    echo "=== All models pulled. Restart pipeline to pick up new models: ==="
    echo "    docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline"
    ;;
  *)
    echo "Usage: ./launch.sh [up|down|clean|clean-all|seed|logs|status|pull-models]"
    echo ""
    echo "  up         Start all services (first run pulls model)"
    echo "  down       Stop all services (data preserved)"
    echo "  clean      Stop + wipe Open WebUI data (Ollama models preserved)"
    echo "  clean-all  Stop + wipe everything including Ollama models"
    echo "  seed       Re-run Open WebUI seeding (workspaces + tool servers)"
    echo "  logs [svc] Tail logs (default: portal-pipeline)"
    echo "  status     Show service status and health"
    echo "  pull-models Pull all Portal 5 Ollama models (30-90 min)"
    ;;
esac
