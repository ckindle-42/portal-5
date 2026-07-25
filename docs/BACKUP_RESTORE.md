# Portal 6.0.0 — Backup & Restore Guide

<!-- WIKI:GENERATED unit=unit-backup-restore-portal-6-0-0-backup-restore-guide -->
This guide covers backup and restore procedures for all Portal 5 data.
<!-- /WIKI:GENERATED -->

---

## What to Back Up

<!-- WIKI:GENERATED unit=unit-backup-restore-what-to-back-up -->
| Component | Volume | Critical? | Notes |
|-----------|--------|-----------|-------|
| Open WebUI data | `portal-5_open-webui-data` | YES | Users, chat history, settings, workspaces |
| Ollama models | `portal-5_ollama-models` | NO | Can be re-downloaded, large (10-100GB) |
| Configuration | `config/` | YES | backends.yaml, personas/ (if customized) |
| Environment | `.env` | YES | Secrets, API keys |
| Generated artifacts | `${AI_OUTPUT_DIR:-~/AI_Output}` (host dir, mounted `/workspace`) | MAYBE | Uploads + generated docs/images/videos/music/speech, if any (CLAUDE.md Rule 11) |
<!-- /WIKI:GENERATED -->

---

### 1. Open WebUI Data (Critical)

<!-- WIKI:GENERATED unit=unit-backup-restore-1-open-webui-data-critical -->
```bash
<!-- /WIKI:GENERATED -->

---

# Manual backup

<!-- WIKI:GENERATED unit=unit-backup-restore-manual-backup -->
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
<!-- /WIKI:GENERATED -->

---

# With compression (faster for large volumes)

<!-- WIKI:GENERATED unit=unit-backup-restore-with-compression-faster-for-large-volumes -->
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar -I 'gzip -9' -cf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```
<!-- /WIKI:GENERATED -->

---

### 2. Configuration Files

<!-- WIKI:GENERATED unit=unit-backup-restore-2-configuration-files -->
```bash
<!-- /WIKI:GENERATED -->

---

# Backup config directory

<!-- WIKI:GENERATED unit=unit-backup-restore-backup-config-directory -->
tar czf config-backup-$(date +%Y%m%d).tar.gz config/ .env
<!-- /WIKI:GENERATED -->

---

# Or just config (excluding .env for security)

<!-- WIKI:GENERATED unit=unit-backup-restore-or-just-config-excluding-env-for-security -->
tar czf config-backup-$(date +%Y%m%d).tar.gz config/
```
<!-- /WIKI:GENERATED -->

---

### 3. Generated Artifacts (if applicable)

<!-- WIKI:GENERATED unit=unit-backup-restore-3-mcp-data-if-applicable -->
```bash
tar czf mcp-backup-$(date +%Y%m%d).tar.gz -C "${AI_OUTPUT_DIR:-$HOME/AI_Output}" .
```
<!-- /WIKI:GENERATED -->

---

### 4. Full System Backup Script

<!-- WIKI:GENERATED unit=unit-backup-restore-4-full-system-backup-script -->
Create `scripts/backup-portal.sh`:

```bash
#!/bin/bash
<!-- /WIKI:GENERATED -->

---

# Backup Portal 5 data

<!-- WIKI:GENERATED unit=unit-backup-restore-backup-portal-5-data -->
set -e

BACKUP_DIR="${BACKUP_DIR:-.}"
DATE=$(date +%Y%m%d-%H%M%S)

echo "Backing up Portal 6.0.0..."
<!-- /WIKI:GENERATED -->

---

# Open WebUI data

<!-- WIKI:GENERATED unit=unit-backup-restore-open-webui-data -->
docker run --rm -v portal-5_open-webui-data:/data -v ${BACKUP_DIR}:/backup \
    alpine tar czf /backup/openwebui-${DATE}.tar.gz /data
<!-- /WIKI:GENERATED -->

---

# Config (excluding .env for security - back that up manually)

<!-- WIKI:GENERATED unit=unit-backup-restore-config-excluding-env-for-security-back-that-up-manually -->
tar czf ${BACKUP_DIR}/config-${DATE}.tar.gz config/
<!-- /WIKI:GENERATED -->

---

# Generated artifacts (if exists)

<!-- WIKI:GENERATED unit=unit-backup-restore-mcp-data-if-exists -->
AI_OUTPUT_DIR="${AI_OUTPUT_DIR:-$HOME/AI_Output}"
if [ -d "$AI_OUTPUT_DIR" ]; then
    tar czf ${BACKUP_DIR}/mcp-${DATE}.tar.gz -C "$AI_OUTPUT_DIR" .
fi

echo "Backup complete: ${DATE}"
ls -la ${BACKUP_DIR}/*-${DATE}.tar.gz
```
<!-- /WIKI:GENERATED -->

---

### 1. Open WebUI Data

<!-- WIKI:GENERATED unit=unit-backup-restore-1-open-webui-data -->
**WARNING**: This overwrites all existing data.

```bash
<!-- /WIKI:GENERATED -->

---

# Stop services first

<!-- WIKI:GENERATED unit=unit-backup-restore-stop-services-first -->
./launch.sh down
<!-- /WIKI:GENERATED -->

---

# Restore from backup

<!-- WIKI:GENERATED unit=unit-backup-restore-restore-from-backup -->
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar xzf /backup/openwebui-backup-20260303.tar.gz -C /
<!-- /WIKI:GENERATED -->

---

# Restart services

<!-- WIKI:GENERATED unit=unit-backup-restore-restart-services -->
./launch.sh up
```
<!-- /WIKI:GENERATED -->

---

### 2. Configuration

<!-- WIKI:GENERATED unit=unit-backup-restore-2-configuration -->
```bash
<!-- /WIKI:GENERATED -->

---

# Extract config (careful - may overwrite current settings)

<!-- WIKI:GENERATED unit=unit-backup-restore-extract-config-careful-may-overwrite-current-settings -->
tar xzf config-backup-20260303.tar.gz
<!-- /WIKI:GENERATED -->

---

# After config changes, re-seed

<!-- WIKI:GENERATED unit=unit-backup-restore-after-config-changes-re-seed -->
./launch.sh seed
```
<!-- /WIKI:GENERATED -->

---

### Daily Backup with Cron

<!-- WIKI:GENERATED unit=unit-backup-restore-daily-backup-with-cron -->
```bash
<!-- /WIKI:GENERATED -->

---

# Add to crontab (crontab -e)

<!-- WIKI:GENERATED unit=unit-backup-restore-add-to-crontab-crontab-e -->
0 2 * * * cd /path/to/portal-5 && ./scripts/backup-portal.sh
```
<!-- /WIKI:GENERATED -->

---

### Backup Retention

<!-- WIKI:GENERATED unit=unit-backup-restore-backup-retention -->
Keep:
- Daily backups for 7 days
- Weekly backups for 4 weeks
- Monthly backups for 12 months

```bash
<!-- /WIKI:GENERATED -->

---

# Cleanup old backups (run daily)

<!-- WIKI:GENERATED unit=unit-backup-restore-cleanup-old-backups-run-daily -->
find . -name "openwebui-*.tar.gz" -mtime +7 -delete
find . -name "config-*.tar.gz" -mtime +30 -delete
```
<!-- /WIKI:GENERATED -->

---

### Complete System Recovery

<!-- WIKI:GENERATED unit=unit-backup-restore-complete-system-recovery -->
1. **Reinstall Portal 5** (fresh clone or restore from git backup)
2. **Restore `.env`** (from your secure backup)
3. **Restore configuration**: `tar xzf config-backup-*.tar.gz`
4. **Restore Open WebUI**: `docker volume rm portal-5_open-webui-data` then restore
5. **Restart**: `./launch.sh up`
<!-- /WIKI:GENERATED -->

---

### Model Weights Recovery

<!-- WIKI:GENERATED unit=unit-backup-restore-model-weights-recovery -->
If `ollama-models` volume is lost:

```bash
<!-- /WIKI:GENERATED -->

---

# Pull default model

<!-- WIKI:GENERATED unit=unit-backup-restore-pull-default-model -->
./launch.sh pull-models
<!-- /WIKI:GENERATED -->

---

# Or manually

<!-- WIKI:GENERATED unit=unit-backup-restore-or-manually -->
docker exec ollama ollama pull dolphin-llama3:8b
```
<!-- /WIKI:GENERATED -->

---

## Migration to New Host

<!-- WIKI:GENERATED unit=unit-backup-restore-migration-to-new-host -->
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
<!-- /WIKI:GENERATED -->

---

## What NOT to Back Up

<!-- WIKI:GENERATED unit=unit-backup-restore-what-not-to-back-up -->
- `ollama-models` volume — can be 50-100GB, easily re-downloaded
- Docker images — can be rebuilt with `docker compose build`
- `.venv/` — rebuild with `uv pip install -e ".[dev]"`
<!-- /WIKI:GENERATED -->

---

## Security Notes

<!-- WIKI:GENERATED unit=unit-backup-restore-security-notes -->
- Store backups encrypted at rest (use gpg or similar)
- Offsite backup recommended (S3, external drive)
- `.env` contains secrets — back up separately, store securely
- Test restore procedure periodically
<!-- /WIKI:GENERATED -->

---
