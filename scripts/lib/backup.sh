#!/usr/bin/env bash
# backup.sh — Portal 5 backup/restore commands (sourced by launch.sh)
# shellcheck shell=bash

_launch_backup() {
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
}

_launch_restore() {
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
}

