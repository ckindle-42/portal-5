<!-- GENERATED FROM portal_wiki/canonical/ — edit the source unit, not this file -->

# Portal 5 Admin Guide

*Generated: 2026-07-26 04:37 UTC*

## Architecture Overview

### ADMIN_GUIDE — Accuracy across 36-query GOLDEN_SET
*Source: docs/ADMIN_GUIDE.md*

OLLAMA_URL=http://localhost:11434 python3 tests/benchmarks/bench_router.py

### ADMIN_GUIDE — Add a Cluster Node
*Source: docs/ADMIN_GUIDE.md*

Edit `config/backends.yaml` — see `docs/CLUSTER_SCALE.md`.

### ADMIN_GUIDE — Alternative: LAN reverse proxy (Caddy / nginx)
*Source: docs/ADMIN_GUIDE.md*

For deployments that don't use Cloudflare Tunnel, a Caddy or nginx reverse proxy on the same machine can serve the same role. Reverse-proxy `/files/{music,tts,video}/*` and `/comfyui/*` to the corresponding loopback ports, set `PORTAL_PUBLIC_URL` to the proxy's public address, and the same env-var derivation works. A first-class Caddy profile in `docker-compose.yml` is on the roadmap but not yet implemented.

**Never expose the MCP ports directly to the internet.** Routing only `/files/{kind}/*`

### ADMIN_GUIDE — Approve Pending Users
*Source: docs/ADMIN_GUIDE.md*

1. Admin Panel > Users
2. Find users with "pending" role
3. Click the user > set role to "user"

### ADMIN_GUIDE — Backup
*Source: docs/ADMIN_GUIDE.md*

Critical data is in Docker volumes:
- `portal-5_open-webui-data` — all user accounts, chat history, settings
- `portal-5_ollama-models` — downloaded model weights (replaceable, not personal data)

```bash
# Easiest: use the launch script (saves to ./backups/)
./launch.sh backup

# Or manually (Open WebUI):
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

### ADMIN_GUIDE — Changing the Router Model
*Source: docs/ADMIN_GUIDE.md*

All three variables live in `.env`:
```bash
LLM_ROUTER_MODEL=hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M
LLM_ROUTER_TIMEOUT_MS=1000   # 1000 for PRIMARY, 500 for STANDBY/FALLBACK
OLLAMA_MAX_LOADED_MODELS=5
```

Then restart the pipeline (not Ollama):
```bash
docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline
```

### ADMIN_GUIDE — Check pipeline logs for router decisions
*Source: docs/ADMIN_GUIDE.md*

./launch.sh logs | grep -E "LLM router|Routing workspace|keyword fallback" | tail -20

### ADMIN_GUIDE — Check which models Ollama currently has loaded
*Source: docs/ADMIN_GUIDE.md*

curl -s http://localhost:11434/api/ps | jq '.models[] | {name, size_vram}'

### ADMIN_GUIDE — Create Users via CLI
*Source: docs/ADMIN_GUIDE.md*

```bash
./launch.sh add-user alice@team.local "Alice Smith"
./launch.sh add-user bob@team.local "Bob Jones" admin
./launch.sh list-users
```

### ADMIN_GUIDE — Edit the plist, then:
*Source: docs/ADMIN_GUIDE.md*

launchctl unload ~/Library/LaunchAgents/homebrew.mxcl.ollama.plist
launchctl load  ~/Library/LaunchAgents/homebrew.mxcl.ollama.plist

## Components

- **10 security canonical variants**: 1 source(s)
- **115 MCP tools across 24 servers**: 1 source(s)
- **138 personas**: 6 source(s)
- **188 model ids, 6 backend groups**: 1 source(s)
- **23 production + 65 eval workspaces**: 1 source(s)
- **24 MCP fleet servers**: 1 source(s)
- **25/25 docs migrated (100.0%)**: 1 source(s)
- **ADMIN_GUIDE — Debugging crashes**: 1 source(s)
- **ADMIN_GUIDE — Pull Additional Models**: 1 source(s)
- **AGENT_LOOP — Agent Loop (platform core)**: 1 source(s)
- **AGENT_LOOP — Consumers**: 1 source(s)
- **AGENT_LOOP — Contracts (the "key" modules implement)**: 1 source(s)
- **AGENT_LOOP — Discipline (borrowed from the Campaign Supervisor)**: 1 source(s)
- **AGENT_LOOP — Operator surface**: 1 source(s)
- **AGENT_LOOP — Record path (writing enabled, CI-gated)**: 1 source(s)

---
*993 knowledge units referenced.*