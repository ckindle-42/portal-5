# Portal Open WebUI Import Files

This directory contains all importable configurations for Open WebUI. Two setup paths exist: fully automated (happens on first `docker compose up`) and manual GUI fallback.

## Automated Setup (happens automatically)

On first launch with a fresh volume, the `openwebui-init` container automatically:
1. Creates the admin account
2. Registers all 7 MCP tool servers
3. Creates all 13 workspace presets

Admin credentials are auto-generated on first launch and stored in `.env`:
- **Email:** `admin@portal.local` (default, overridable via `OPENWEBUI_ADMIN_EMAIL`)
- **Password:** randomly generated 16-char string (see `.env` after first run)

To re-run seeding manually:
```bash
bash launch.sh seed
```

## Clean Restart for Testing

To wipe the Open WebUI database (users, tool servers, workspaces, chat history) while preserving Ollama models and ComfyUI model files:
```bash
bash launch.sh clean
bash launch.sh up
```

To wipe everything including Ollama models:
```bash
bash launch.sh clean-all
bash launch.sh up
```

## GUI Fallback (if automation fails)

If automation fails, you can manually import files through the Open WebUI admin interface.

### Tool Servers
1. Go to **Admin Panel > Settings > Tools**
2. Click **Add Tool Server**
3. Import individual `tools/*.json` files one at a time

### Workspaces
1. Go to **Workspace > Models**
2. Click **Import**
3. Select individual `workspaces/workspace_*.json` files or the bulk `workspaces_all.json`

### Functions
1. Go to **Workspace > Functions**
2. Click **Import**
3. Select `functions/portal_router_pipe.json`

## Complete File Index

| File | Type | Import Location | Count |
|---|---|---|---|
| `tools/portal_comfyui.json` | MCP Tool Server | Admin > Settings > Tools | 1 of 7 |
| `tools/portal_video.json` | MCP Tool Server | Admin > Settings > Tools | 2 of 7 |
| `tools/portal_music.json` | MCP Tool Server | Admin > Settings > Tools | 3 of 7 |
| `tools/portal_documents.json` | MCP Tool Server | Admin > Settings > Tools | 4 of 7 |
| `tools/portal_code.json` | MCP Tool Server | Admin > Settings > Tools | 5 of 7 |
| `tools/portal_whisper.json` | MCP Tool Server | Admin > Settings > Tools | 6 of 7 |
| `tools/portal_tts.json` | MCP Tool Server | Admin > Settings > Tools | 7 of 7 |
| `workspaces/workspace_auto.json` | Workspace Preset | Workspace > Models > Import | 1 of 13 |
| `workspaces/workspace_auto_*.json` | Workspace Preset | Workspace > Models > Import | 2–13 of 13 |
| `workspaces/workspaces_all.json` | Bulk Workspace | Workspace > Models > Import | all 13 |
| `functions/portal_router_pipe.json` | Open WebUI Function | Workspace > Functions > Import | 1 of 1 |
| `mcp-servers.json` | Config source | Used by setup scripts | — |
| `portal_import_bundle.json` | Full bundle | Reference / tooling | — |

## macOS vs Linux

- **macOS with Docker Desktop:** Uses `host.docker.internal` — resolves automatically
- **Linux with Docker:** Replace `host.docker.internal` with your host IP:
  ```bash
  $(ip route | awk '/default/{print $3}')
  ```
