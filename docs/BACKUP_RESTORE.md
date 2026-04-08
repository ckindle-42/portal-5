# Portal 6.0.0 — Backup & Restore Guide

This guide covers backup and restore procedures for all Portal 5 data.

## What to Back Up

| Component | Volume | Critical? | Notes |
|-----------|--------|-----------|-------|
| Open WebUI data | `portal-5_open-webui-data` | YES | Users, chat history, settings, workspaces |
| Ollama models | `portal-5_ollama-models` | NO | Can be re-downloaded, large (10-100GB) |
| Configuration | `config/` | YES | backends.yaml, personas/ (if customized) |
| Environment | `.env` | YES | Secrets, API keys |
| MCP data | `portal-5_mcp-data` | MAYBE | Generated documents, if any |

## Backup Commands

### 1. Open WebUI Data (Critical)

```bash
# Manual backup
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data

# With compression (faster for large volumes)
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar -I 'gzip -9' -cf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

### 2. Configuration Files

```bash
# Backup config directory
tar czf config-backup-$(date +%Y%m%d).tar.gz config/ .env

# Or just config (excluding .env for security)
tar czf config-backup-$(date +%Y%m%d).tar.gz config/
```

### 3. MCP Data (if applicable)

```bash
docker run --rm -v portal-5_mcp-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/mcp-backup-$(date +%Y%m%d).tar.gz /data
```

### 4. Full System Backup Script

Create `scripts/backup-portal.sh`:

```bash
#!/bin/bash
# Backup Portal 5 data
set -e

BACKUP_DIR="${BACKUP_DIR:-.}"
DATE=$(date +%Y%m%d-%H%M%S)

echo "Backing up Portal 6.0.0..."

# Open WebUI data
docker run --rm -v portal-5_open-webui-data:/data -v ${BACKUP_DIR}:/backup \
    alpine tar czf /backup/openwebui-${DATE}.tar.gz /data

# Config (excluding .env for security - back that up manually)
tar czf ${BACKUP_DIR}/config-${DATE}.tar.gz config/

# MCP data (if exists)
if docker volume ls -q | grep -q "portal-5_mcp-data"; then
    docker run --rm -v portal-5_mcp-data:/data -v ${BACKUP_DIR}:/backup \
        alpine tar czf /backup/mcp-${DATE}.tar.gz /data
fi

echo "Backup complete: ${DATE}"
ls -la ${BACKUP_DIR}/*-${DATE}.tar.gz
```

## Restore Commands

### 1. Open WebUI Data

**WARNING**: This overwrites all existing data.

```bash
# Stop services first
./launch.sh down

# Restore from backup
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar xzf /backup/openwebui-backup-20260303.tar.gz -C /

# Restart services
./launch.sh up
```

### 2. Configuration

```bash
# Extract config (careful - may overwrite current settings)
tar xzf config-backup-20260303.tar.gz

# After config changes, re-seed
./launch.sh seed
```

## Automated Backups

### Daily Backup with Cron

```bash
# Add to crontab (crontab -e)
0 2 * * * cd /path/to/portal-5 && ./scripts/backup-portal.sh
```

### Backup Retention

Keep:
- Daily backups for 7 days
- Weekly backups for 4 weeks
- Monthly backups for 12 months

```bash
# Cleanup old backups (run daily)
find . -name "openwebui-*.tar.gz" -mtime +7 -delete
find . -name "config-*.tar.gz" -mtime +30 -delete
```

## Disaster Recovery

### Complete System Recovery

1. **Reinstall Portal 5** (fresh clone or restore from git backup)
2. **Restore `.env`** (from your secure backup)
3. **Restore configuration**: `tar xzf config-backup-*.tar.gz`
4. **Restore Open WebUI**: `docker volume rm portal-5_open-webui-data` then restore
5. **Restart**: `./launch.sh up`

### Model Weights Recovery

If `ollama-models` volume is lost:

```bash
# Pull default model
./launch.sh pull-models

# Or manually
docker exec ollama ollama pull dolphin-llama3:8b
```

## Migration to New Host

1. Backup from source:
   ```bash
   docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
       alpine tar czf /backup/openwebui-migration.tar.gz /data
   ```

2. Transfer backup file to new host

3. On new host:
   ```bash
   # Fresh Portal 5 install
   git clone https://github.com/ckindle-42/portal-5
   cd portal-5

   # Copy your .env (from backup or recreate from .env.example)
   cp .env.example .env
   # Edit .env with your settings

   # Stop services
   ./launch.sh down

   # Restore data
   docker volume create portal-5_open-webui-data
   docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
       alpine tar xzf /backup/openwebui-migration.tar.gz -C /

   # Start
   ./launch.sh up
   ```

## What NOT to Back Up

- `ollama-models` volume — can be 50-100GB, easily re-downloaded
- Docker images — can be rebuilt with `docker compose build`
- `.venv/` — rebuild with `uv pip install -e ".[dev]"`

## Security Notes

- Store backups encrypted at rest (use gpg or similar)
- Offsite backup recommended (S3, external drive)
- `.env` contains secrets — back up separately, store securely
- Test restore procedure periodically