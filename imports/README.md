# Portal Import Files

This directory contains importable configurations for various services used by Portal.

## Open WebUI

Located in `openwebui/`:

| File | Description |
|------|-------------|
| `mcp-servers.json` | MCP tool server configurations (for API-based setup) |
| `config.env` | Copy-paste friendly config values |
| `tools/` | Individual tool JSON files for GUI import |

### Option 1: Automated Setup (Recommended)

Run the setup script to automatically configure workspaces and MCP servers:

```bash
python scripts/setup_openwebui.py --url http://localhost:8080 --api-key YOUR_API_KEY
```

The script reads `imports/openwebui/mcp-servers.json` and pushes the configuration via Open WebUI's API.

### Option 2: GUI Import

For manual GUI-based import:

1. Open Open WebUI at http://localhost:8080
2. Go to **Workspace** > **Tools**
3. Click the **Import Tool** button
4. Select individual JSON files from `imports/openwebui/tools/`:

   - `portal_music.json` - Music generation
   - `portal_documents.json` - Document creation
   - `portal_code.json` - Code sandbox
   - `portal_tts.json` - Text-to-speech

### Option 3: Manual Entry

1. Open Open WebUI at http://localhost:8080
2. Go to **Admin Panel** > **Settings** > **Tools**
3. Click **Add Tool Server**
4. Enter values from `config.env`

### MCP Server Ports

| Service | Port | Description |
|---------|------|-------------|
| Music Generation | 8912 | AudioCraft/MusicGen |
| Document Creation | 8913 | Word/PowerPoint/Excel |
| Code Sandbox | 8914 | Python/Node/Bash execution |
| Text-to-Speech | 8916 | Fish Speech / CosyVoice |

Note: On macOS, use `host.docker.internal`. On Linux, use the host machine's IP address.
