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
  *)
    echo "Usage: ./launch.sh [up|down|clean|clean-all|seed|logs|status]"
    echo ""
    echo "  up         Start all services (first run pulls model)"
    echo "  down       Stop all services (data preserved)"
    echo "  clean      Stop + wipe Open WebUI data (Ollama models preserved)"
    echo "  clean-all  Stop + wipe everything including Ollama models"
    echo "  seed       Re-run Open WebUI seeding (workspaces + tool servers)"
    echo "  logs [svc] Tail logs (default: portal-pipeline)"
    echo "  status     Show service status and health"
    ;;
esac
