#!/usr/bin/env bash
# lab.sh — Portal 5 lab environment commands (sourced by launch.sh)
# shellcheck shell=bash

_launch_lab_up() {
    # Start Incalmo C2 + Talon SOC analyst (lab profile).
    # Does NOT start Wazuh — use lab-up-wazuh for that.
    # Requires VMs on LAB_TARGET_NETWORK (see docs/LAB_SETUP.md).
    set -a; source "$ENV_FILE"; set +a
    if [ ! -f "$COMPOSE_DIR/.env" ]; then
        ln -s "$ENV_FILE" "$COMPOSE_DIR/.env"
    fi
    cd "$COMPOSE_DIR"
    docker compose -f docker-compose.yml -f docker-compose.lab.yml --profile lab up -d
    echo "[portal-5] Lab services started:"
    echo "  Incalmo C2  → http://localhost:${INCALMO_PORT:-8930}"
    echo "  Talon SOC   → http://localhost:${TALON_PORT:-8931}"
    echo ""
    echo "  LLM routing: Incalmo → auto-security (redteam, via alias shim) | Talon → auto-security (blueteam)"
    echo "  Set LAB_TARGET_NETWORK, LAB_TARGET_DC, LAB_TARGET_WS in .env"
    echo "  See: docs/LAB_SETUP.md"
}

_launch_lab_up_wazuh() {
    # Start Incalmo + Talon + full Wazuh SIEM stack.
    # Requires ~6GB extra RAM for Wazuh manager + indexer.
    # Set LAB_OPENSEARCH_PASSWORD in .env before running.
    set -a; source "$ENV_FILE"; set +a
    if [ -z "${LAB_OPENSEARCH_PASSWORD:-}" ]; then
        echo "[portal-5] ERROR: LAB_OPENSEARCH_PASSWORD not set in .env"
        echo "  Set a strong password (min 8 chars, 1 upper, 1 digit, 1 special)"
        exit 1
    fi
    if [ ! -f "$COMPOSE_DIR/.env" ]; then
        ln -s "$ENV_FILE" "$COMPOSE_DIR/.env"
    fi
    cd "$COMPOSE_DIR"
    docker compose -f docker-compose.yml -f docker-compose.lab.yml \
        --profile lab --profile lab-wazuh up -d
    echo "[portal-5] Lab + Wazuh started:"
    echo "  Incalmo C2       → http://localhost:${INCALMO_PORT:-8930}"
    echo "  Talon SOC        → http://localhost:${TALON_PORT:-8931}"
    echo "  Wazuh Manager    → enrolled agents on :1515, syslog on :1514/udp"
    echo "  OpenSearch API   → http://localhost:9201"
    echo "  Wazuh REST API   → https://localhost:55000"
    echo ""
    echo "  Deploy Wazuh agents on VMs: see docs/LAB_SETUP.md"
}

_launch_lab_down() {
    # Stop all lab services (Incalmo, Talon, Wazuh).
    set -a; source "$ENV_FILE"; set +a
    if [ ! -f "$COMPOSE_DIR/.env" ]; then
        ln -s "$ENV_FILE" "$COMPOSE_DIR/.env"
    fi
    cd "$COMPOSE_DIR"
    docker compose -f docker-compose.yml -f docker-compose.lab.yml \
        --profile lab --profile lab-wazuh --profile lab-wazuh-ui down
    echo "[portal-5] Lab services stopped"
}

_launch_lab_status() {
    # Show status of all lab containers.
    echo "[portal-5] Lab service status:"
    docker ps --filter "name=portal5-lab" \
        --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true
}

_launch_build_lab_attack() {
    # Build the native arm64 attack image for the lab-exec lane and load it
    # into DinD. Opt-in / lab-only — NOT part of `rebuild` (heavy image, only
    # needed by operators running live lab sessions). Mirrors the pwsh
    # build->save->DinD-load pattern.
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    echo "[portal-5] Building native arm64 attack image (portal5-attack:latest)..."
    docker build -t portal5-attack:latest -f "$PORTAL_ROOT/Dockerfile.attack" "$PORTAL_ROOT"
    echo "[portal-5] Loading attack image into DinD..."
    if ! docker ps --format '{{.Names}}' | grep -q '^portal5-dind$'; then
      echo "[portal-5] ERROR: portal5-dind is not running. Start the stack first (./launch.sh up)."
      exit 1
    fi
    docker save portal5-attack:latest | docker exec -i portal5-dind docker load
    echo "[portal-5] Done. Set SANDBOX_LAB_IMAGE=portal5-attack:latest and SANDBOX_LAB_EXEC=true"
    echo "[portal-5] in .env, then: ./launch.sh restart-mcp   (see docs/LAB_SETUP.md)"
}

