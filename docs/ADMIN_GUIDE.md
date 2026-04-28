# Portal 6.0.7 — Admin Guide

## First Login

After `./launch.sh up`, credentials are printed to the console and saved in `.env`.
Log in at `http://localhost:8080` with the generated admin account.

## User Management

### Approve Pending Users
1. Admin Panel > Users
2. Find users with "pending" role
3. Click the user > set role to "user"

### Create Users via CLI
```bash
./launch.sh add-user alice@team.local "Alice Smith"
./launch.sh add-user bob@team.local "Bob Jones" admin
./launch.sh list-users
```

### User Roles
- `pending` — cannot use the system, waiting for approval
- `user` — standard access to workspaces, tools, chat
- `admin` — full access including user management and all settings

## Model Management

### Pull Additional Models
```bash
./launch.sh pull-models
# Pulls: xploiter, whiterabbitneo, baronllm, tongyi, qwen3-coder, devstral, etc.
# Takes 30-90 minutes depending on connection speed
```

### Add a Cluster Node
Edit `config/backends.yaml` — see `docs/CLUSTER_SCALE.md`.

## Routine Operations

```bash
./launch.sh status      # Check service health
./launch.sh logs        # Pipeline logs (default)
./launch.sh logs ollama # Ollama logs
./launch.sh seed        # Re-seed workspaces/personas (after config changes)
./launch.sh down        # Stop all services (data preserved)
./launch.sh clean       # Wipe Open WebUI data (fresh start, Ollama models kept)
```

## Security Notes

- Generated secrets are in `.env` — never commit this file
- PIPELINE_API_KEY protects the routing API — rotate if compromised
- WEBUI_SECRET_KEY secures user sessions — rotation requires all users to re-login
- To rotate secrets: edit `.env`, restart stack

## Network Exposure

Portal 5 is designed for single-machine local use. Open WebUI binds to `127.0.0.1` by default and is only reachable from `localhost`. All MCP servers (8910–8923) are always 127.0.0.1-bound and never reach the network directly.

### Recommended remote access: Cloudflare Tunnel

Run `cloudflared` on the host and configure ingress rules that route specific paths to the local services. The MCP servers stay loopback-only — cloudflared (running on the host, not in docker) reaches them through `127.0.0.1`. A reference ingress configuration is provided at `config/cloudflared/config.yml.example`.

To make generated media links work for remote browsers:

```
ENABLE_REMOTE_ACCESS=true
PORTAL_PUBLIC_URL=https://portal.example.com
```

`launch.sh` derives `MUSIC_PUBLIC_URL`, `TTS_PUBLIC_URL`, `VIDEO_PUBLIC_URL`, and `COMFYUI_PUBLIC_URL` from `PORTAL_PUBLIC_URL`, and the MCPs emit those into chat instead of `http://localhost:<port>/...`.

Without `PORTAL_PUBLIC_URL` set, every MCP falls back to localhost-only links — Open WebUI can still be reached remotely, but media download links inside chat won't resolve from a remote browser.

### Alternative: LAN reverse proxy (Caddy / nginx)

For deployments that don't use Cloudflare Tunnel, a Caddy or nginx reverse proxy on the same machine can serve the same role. Reverse-proxy `/files/{music,tts,video}/*` and `/comfyui/*` to the corresponding loopback ports, set `PORTAL_PUBLIC_URL` to the proxy's public address, and the same env-var derivation works. A first-class Caddy profile in `docker-compose.yml` is on the roadmap but not in v6.0.7.

**Never expose the MCP ports directly to the internet.** Routing only `/files/{kind}/*` keeps the rest of the MCP API surface private.

The pipeline API (port 9099) and all MCP servers (8910–8923) are always bound to 127.0.0.1 and are not reachable externally under any configuration. Cloudflare Tunnel reaches them via the host loopback only because cloudflared itself runs on the host.

> **Note:** Grafana (port 3000) binds to `0.0.0.0:3000` and **is** reachable from other machines on your network. Grafana requires login (`admin` / `GRAFANA_PASSWORD` from `.env`) and does not expose inference data — but if your LAN is untrusted, restrict it with a firewall rule or set `GF_SERVER_HTTP_ADDR=127.0.0.1` in `docker-compose.yml`.

## Backup

Critical data is in Docker volumes:
- `portal-5_open-webui-data` — all user accounts, chat history, settings
- `portal-5_ollama-models` — downloaded model weights (replaceable, not personal data)

```bash
# Easiest: use the launch script (saves to ./backups/)
./launch.sh backup

# Or manually:
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

## MLX Health Monitoring

The MLX subsystem uses two complementary health monitors with distinct responsibilities:

### 1. In-process probe (`mlx-proxy.py`)
Runs as a daemon thread inside `mlx-proxy.py` on a 15-second interval (configurable via `MLX_WATCHDOG_INTERVAL`).

**Responsibilities:**
- Keeps the proxy's `/health` endpoint accurate by probing `mlx_lm.server` and `mlx_vlm.server`
- Updates `mlx_state` (ready / switching / down) for accurate self-reporting
- Samples GPU memory every ~60 seconds for the `/health` `memory` field
- Recovers internal state if a server comes back healthy after a down period

**Does NOT:** kill processes, restart servers, or send notifications. One process killing another from two places caused race conditions and split the recovery logic.

### 2. External daemon (`mlx-watchdog.py` via launchd)
Runs as a standalone process managed by launchd, polling every 30 seconds.

**Responsibilities:**
- Owns zombie cleanup (SIGTERM → wait → SIGKILL for hung mlx_lm/mlx_vlm processes)
- Owns process restart (respawns crashed servers after cool-down)
- Sends operational notifications (Telegram/Slack/email) on crash and recovery
- Tracks consecutive failure counts and escalates as needed

**Configured via:** `~/.portal5/mlx/start.sh` (installed by `./launch.sh install-mlx`)

### Debugging crashes

```bash
# External watchdog logs (last 50 lines)
tail -50 ~/.portal5/mlx/logs/mlx-watchdog.log

# Proxy state via API
curl -s http://localhost:8081/health | jq .

# Check both watchdogs are running
./launch.sh status
```
