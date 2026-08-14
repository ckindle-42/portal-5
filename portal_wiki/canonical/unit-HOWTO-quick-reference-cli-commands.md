---
id: unit-HOWTO-quick-reference-cli-commands
kind: what
title: 'HOWTO -- Quick Reference: All CLI Commands'
sources:
- type: code
  path: launch.sh
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1784944814.9461
updated_at: 1784944814.9461
---

All commands below are the actual `case` branches in `launch.sh` (or dispatch into `python3 -m portal.platform.inference.cli`).

# Start / stop
./launch.sh up              # Start everything (first run bootstraps .env + secrets + workspace)
./launch.sh down            # Stop (data preserved)
./launch.sh status          # Check service health

# Test everything is working
./launch.sh test            # Live smoke tests against the running stack (cli smoke)

# Pull specialized models (security, coding, reasoning -- 30-90 min)
./launch.sh pull-models     # cli models pull

# MLX native services (Apple Silicon)
./launch.sh start-speech    # Start MLX speech server (:8918) — idempotent, reports if running
./launch.sh stop-speech     # Stop MLX speech server
./launch.sh start-transcribe  # Start mlx-transcribe (:8924)
./launch.sh stop-transcribe   # Stop mlx-transcribe

# User management
./launch.sh add-user alice@example.com "Alice Smith"   # optional third arg: user|admin|pending role
./launch.sh list-users

# Enable messaging channels (requires tokens in .env)
./launch.sh up-telegram     # Start Telegram bot (compose --profile telegram)
./launch.sh up-slack        # Start Slack bot (requires SLACK_BOT_TOKEN + SLACK_APP_TOKEN)
./launch.sh up-channels     # Start both

# Backup and restore
./launch.sh backup          # Save to ./backups/portal5_backup_<timestamp>/
./launch.sh restore <dir>   # Restore from a backup directory (not a single file; prompts first)

# Seeding
./launch.sh seed            # Re-seed Open WebUI (workspaces + personas) — skips existing presets
./launch.sh reseed          # Force-refresh all presets (FORCE_RESEED=true)

# Update (single command: git pull + rebuild + model refresh + re-seed)
./launch.sh update                  # cli update — full pass
./launch.sh update --skip-models    # Skip the Ollama model refresh (faster)
./launch.sh update --models-only    # Only refresh models

# Cleanup
./launch.sh clean           # Stop + wipe Open WebUI data (keeps Ollama model weights)
./launch.sh clean-all       # Stop + wipe everything including models
./launch.sh rebuild         # Rebuild portal-pipeline + MCP images, restart

# Workspace
./launch.sh workspace-init     # Create shared workspace tree (uploads, generated/*)
./launch.sh workspace-status   # File counts and sizes per category
./launch.sh workspace-show     # Resolved paths (host vs container)

## Why

This surface is deliberately a thin shell over `launch.sh` cases and the typed CLI, so every command has one implementation and the usage text in the `*)` branch stays the reference. Commands that need real logic — `pull-models`, `update`, `test`, workspace — delegate to `portal.platform.inference.cli`, keeping the shell file declarative and testable instead of growing bespoke logic in bash.
