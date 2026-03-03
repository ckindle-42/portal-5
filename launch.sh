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
    docker volume rm portal-5_open-webui-data 2>/dev/null || true
    echo "[portal-5] Clean complete. Run ./launch.sh up for fresh start."
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
  *)
    echo "Usage: ./launch.sh [up|down|clean|seed|logs]"
    ;;
esac
