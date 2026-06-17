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

# Or manually (Open WebUI):
docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

## Inference Health Monitoring

Portal 5 runs a single inference backend: **Ollama** (:11434). The MLX inference proxy
(:8081/:18081/:18082) was retired in commit 3a0c58e.

### Debugging crashes

```bash
# Check Ollama health and model list
curl -s http://localhost:11434/api/tags | jq .

# Check pipeline health
curl -s http://localhost:9099/health/all | jq .

# Check all services
./launch.sh status
```

---

## Router Configuration

### How the LLM Router Works

The pipeline routes every `auto` workspace request through a **two-layer intent classifier**:

- **Layer 1 — LLM router** (`portal_pipeline/router/routing.py`): A small model classifies intent via Ollama `/api/generate` with grammar-enforced JSON output. Result: `{"workspace": "<id>", "confidence": 0.0–1.0}`. Fast, accurate.
- **Layer 2 — Keyword scoring** (`portal_pipeline/router/routing.py`): Weighted keyword match. Fires when LLM router times out, returns low confidence, or errors.

### Three-Tier Router Models

Three models are available; select via `LLM_ROUTER_MODEL` in `.env`:

| Tier | Model | Accuracy | p50 Latency | VRAM | When to use |
|------|-------|----------|-------------|------|-------------|
| **PRIMARY** | `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M` | 82.2% | ~840ms | 5.3GB | Default — best accuracy |
| **STANDBY** | `llama3.2:3b` | 75.3% | ~433ms | ~2GB | If PRIMARY is evicted frequently in your fleet |
| **FALLBACK** | `qwen2.5:1.5b` | 67.1% | ~339ms | 1GB | Extremely memory-constrained; stays hot under any fleet load |

Accuracy figures are from `tests/benchmarks/bench_router.py` (36-query GOLDEN_SET, 3 rounds).

### OLLAMA_MAX_LOADED_MODELS=3

The Ollama slot count is set to **3** (not 2) so the router model holds its own slot alongside two inference models. Without this, Ollama evicts the router to make room for inference models — the first request after eviction falls back to Layer 2 keyword scoring while the router cold-loads.

**Cold-load times** (after eviction): PRIMARY 4.2s · STANDBY 2.4s · FALLBACK 1.6s. All exceed the production `LLM_ROUTER_TIMEOUT_MS` limit, so the first post-eviction request always goes to Layer 2 — exactly one fallback, then the router reloads and stays warm.

### Changing the Router Model

All three variables live in `.env`:
```bash
LLM_ROUTER_MODEL=hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M
LLM_ROUTER_TIMEOUT_MS=1000   # 1000 for PRIMARY, 500 for STANDBY/FALLBACK
OLLAMA_MAX_LOADED_MODELS=3
```

Then restart the pipeline (not Ollama):
```bash
docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline
```

### Ollama is Native — Plist Is the Source of Truth

Ollama runs under launchd, not Docker. Docker-compose env vars pass through to the pipeline container but **do not affect Ollama itself**. The authoritative config is:

```
~/Library/LaunchAgents/homebrew.mxcl.ollama.plist
```

To change `OLLAMA_MAX_LOADED_MODELS` (or add `OLLAMA_MEMORY_LIMIT`), edit the plist and reload:

```bash
# Edit the plist, then:
launchctl unload ~/Library/LaunchAgents/homebrew.mxcl.ollama.plist
launchctl load  ~/Library/LaunchAgents/homebrew.mxcl.ollama.plist

# Verify the new value was picked up:
ps eww -p $(pgrep -f "ollama serve") | tr ' ' '\n' | grep OLLAMA_MAX_LOADED
```

### Runtime VRAM vs File Size Gap

Ollama allocates KV cache at model-load time. Runtime resident size is **significantly larger** than the model file:

| Model | File size | Runtime VRAM | Driver |
|-------|-----------|--------------|--------|
| devstral:24b | 14.3 GB | ~25.7 GB | Large default context window |
| granite4.1:8b | 5.3 GB | ~16.8 GB | Large context + KV q8_0 |
| OBLITERATED E4B | 5.3 GB | ~5.3 GB | Compact architecture |

**devstral:24b specifically**: its 25.7 GB runtime footprint can cause memory-pressure eviction of other models regardless of `MAX_LOADED_MODELS`. This is expected graceful behavior — Ollama offloads CPU layers rather than crashing (unlike MLX Metal OOM). If devstral evicts the router, Layer 2 keyword scoring handles that one request, then the router reloads. Not a bug.

### OLLAMA_MEMORY_LIMIT (deferred)

`OLLAMA_MEMORY_LIMIT` is currently **not set** (unlimited). On the M4 Pro 48GB, worst-case slot composition (router 5.3GB + devstral 25.7GB + granite 16.8GB) can hit ~47.8GB — very tight. Ollama gracefully offloads to CPU before crashing, but if kernel panics or Metal OOM errors appear under heavy multi-model loads, add to the plist:

```xml
<key>OLLAMA_MEMORY_LIMIT</key>
<string>42g</string>
```

42 GB leaves ~6 GB for macOS + pipeline + Open WebUI.

### Verifying Router Is Warm

```bash
# Check which models Ollama currently has loaded
curl -s http://localhost:11434/api/ps | jq '.models[] | {name, size_vram}'

# Check pipeline logs for router decisions
./launch.sh logs | grep -E "LLM router|Routing workspace|keyword fallback" | tail -20

# Pull router model if not yet downloaded
ollama pull hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M
```

### Router Benchmarks

To re-validate router accuracy after model changes:
```bash
# Accuracy across 36-query GOLDEN_SET
OLLAMA_URL=http://localhost:11434 python3 tests/benchmarks/bench_router.py

# VRAM eviction and cold-load conditions bench (3 router candidates × 4 scenarios)
OLLAMA_URL=http://localhost:11434 python3 tests/benchmarks/bench_router_conditions.py \
  --companions devstral:24b granite4.1:8b
```

Results are written to `tests/benchmarks/results/`.
