# Portal 5 — Local AI Platform

A complete, private AI platform that runs on your hardware. Text, code, security
analysis, images, video, music, documents, and voice — all local, all yours.

Connects to Open WebUI, Telegram, and Slack. Routes automatically to the right
model for each task. No cloud accounts. No usage fees. No data leaving your machine.

---

## Prerequisites

| Requirement | Minimum | Recommended |
|---|---|---|
| **Docker** | Docker Desktop 4.x or Docker Engine 24+ with Compose v2 | Latest Docker Desktop |
| **RAM** | 16 GB | 32–64 GB (for large models) |
| **Disk** | 50 GB free | 200 GB (full model catalog) |
| **CPU** | Any modern x86-64 or Apple Silicon | Apple M-series or recent Intel/AMD |
| **GPU** | None required | NVIDIA GPU with 8GB+ VRAM (speeds inference) |
| **OS** | macOS 13+, Ubuntu 22.04+, or Windows 11 with WSL2 | macOS (Apple Silicon) |

> **Apple Silicon:** Portal 5 runs natively on M1/M2/M3/M4 via Ollama's Metal
> acceleration. No NVIDIA GPU required.

> **Linux:** Ensure your user is in the `docker` group:
> `sudo usermod -aG docker $USER && newgrp docker`

---

## Quick Start

```bash
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
./launch.sh up
```

**First run pulls ~16 GB of data and takes 10–45 minutes depending on your
connection.** You will see progress in the terminal. When it finishes:

```
[portal-5] ✅ Stack is ready
[portal-5] Web UI:     http://localhost:8080
[portal-5] Grafana:    http://localhost:3000
[portal-5] Admin creds saved to: .env (do not commit this file)
```

Open **http://localhost:8080** and sign in with the admin credentials printed to
your terminal.

---

## What Starts Automatically

Everything runs with a single command. No manual configuration.

| Service | What it does | URL |
|---|---|---|
| Open WebUI | Chat interface — your main portal | http://localhost:8080 |
| Portal Pipeline | Intelligent routing to models | (internal) |
| Ollama | Runs local language models | (internal) |
| SearXNG | Private web search for research | (internal) |
| ComfyUI | Image and video generation | http://localhost:8188 |
| 7 MCP Servers | Documents, music, voice, code, images | (internal) |
| Prometheus | Metrics collection | http://localhost:9090 |
| Grafana | Metrics dashboard | http://localhost:3000 |

---

## Workspaces

Select a workspace in the Open WebUI model dropdown to activate the right model
and tools automatically.

| Workspace | Purpose | Auto-activates |
|---|---|---|
| `auto` | General — routes to best model | — |
| `auto-coding` | Code generation and review | Code sandbox |
| `auto-security` | Security analysis and hardening | Code sandbox |
| `auto-redteam` | Offensive security research | Code sandbox |
| `auto-blueteam` | Defensive security, incident response | Code sandbox |
| `auto-documents` | Create Word, Excel, PowerPoint | Documents + Code |
| `auto-music` | Generate music via AudioCraft | Music + TTS |
| `auto-video` | Generate video via ComfyUI | Video + Image |
| `auto-vision` | Image understanding, visual tasks | Image generation |
| `auto-creative` | Creative writing | TTS voice |
| `auto-research` | Web research and synthesis | — |
| `auto-reasoning` | Deep reasoning, complex analysis | — |
| `auto-data` | Data analysis, statistics | Code + Documents |
| `⚖️ auto-compliance` | NERC CIP gap analysis, policy review, audit prep | Qwen3.5-35B-A3B (MLX) |

---

## Common Commands

```bash
# Start / stop
./launch.sh up              # Start everything
./launch.sh down            # Stop (data preserved)
./launch.sh status          # Check service health

# Test everything is working
./launch.sh test            # Run live smoke tests against running stack

# Pull specialized models (security, coding, reasoning — 30–90 min)
./launch.sh pull-models

# User management
./launch.sh add-user alice@example.com "Alice Smith"
./launch.sh list-users

# Enable messaging channels (requires tokens in .env)
./launch.sh up-telegram     # Start Telegram bot
./launch.sh up-slack        # Start Slack bot
./launch.sh up-channels     # Start both

# Backup and restore
./launch.sh backup          # Save all data to ./backups/
./launch.sh restore <file>  # Restore from backup

# Cleanup
./launch.sh clean           # Remove containers (keeps model weights)
./launch.sh clean-all       # Remove everything including models
```

---

## Enable Telegram Bot

1. Message **@BotFather** on Telegram → `/newbot` → copy the token
2. Get your Telegram user ID from **@userinfobot**
3. Add to `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=your-token-here
   TELEGRAM_USER_IDS=your-user-id
   ```
4. Start: `./launch.sh up-telegram`
5. Message your bot `/start` to verify

---

## Enable Slack Bot

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**
2. Under **OAuth & Permissions** → add bot scopes:
   `app_mentions:read`, `chat:write`, `channels:history`, `im:history`, `im:read`, `im:write`
3. Under **Socket Mode** → enable it → generate an **App-Level Token** (xapp-...)
4. Install app to your workspace
5. Add to `.env`:
   ```bash
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_SIGNING_SECRET=...
   ```
6. Start: `./launch.sh up-slack`
7. Mention `@portal` in any channel to verify

---

## Hardware & Model Guide

### Core models (pulled automatically on first run, ~4 GB)
- `dolphin-llama3:8b` — general purpose default
- `llama3.2:3b` — fast small model
- `nomic-embed-text` — document embeddings for RAG

### Specialized models (pulled with `./launch.sh pull-models`, ~60–100 GB total)
- **Security:** BaronLLM-18B, Lily-Cybersecurity-7B, WhiteRabbitNeo-33B
- **Coding:** Qwen3-Coder-30B, GLM-4.7-Flash, Devstral-24B
- **Reasoning:** DeepSeek-R1-32B, Tongyi-DeepResearch-30B
- **Vision:** Qwen3-Omni-30B, LLaVA-7B

### Image generation (downloaded automatically on first run, ~12 GB)
- FLUX.1-schnell — fast, high-quality image generation

To use a different image model: set `IMAGE_MODEL=sdxl` or `IMAGE_MODEL=flux-dev`
in `.env` (flux-dev requires a HuggingFace token).

---

## Troubleshooting

**Services not starting:**
```bash
./launch.sh status          # See which services failed
docker compose -f deploy/portal-5/docker-compose.yml logs <service-name>
```

**Out of disk space:**
```bash
docker system df            # See Docker disk usage
./launch.sh clean           # Remove containers
# Then free disk space and retry ./launch.sh up
```

**Models not loading (Ollama shows 0 backends):**
```bash
./launch.sh pull-models     # Ensure at least one model is pulled
# Wait for Ollama to finish loading, then try again
```

**First run taking too long:**
FLUX.1-schnell is ~12 GB. On a 100 Mbps connection this takes ~15 minutes.
On slower connections it may take longer. The download resumes if interrupted.

**Port already in use:**
```bash
lsof -i :8080               # Find what is using port 8080
# Stop the conflicting service, then ./launch.sh up
```

---

## Documentation

| Guide | Contents |
|---|---|
| [How-To Guide](docs/HOWTO.md) | Complete guide with working examples for every feature |
| [User Guide](docs/USER_GUIDE.md) | How to use workspaces, tools, personas |
| [Admin Guide](docs/ADMIN_GUIDE.md) | User management, configuration, security |
| [Alerts & Notifications](docs/ALERTS.md) | Operational alerts and daily summaries |
| [ComfyUI Setup](docs/COMFYUI_SETUP.md) | Advanced image/video model configuration |
| [Fish Speech Setup](docs/FISH_SPEECH_SETUP.md) | Optional voice cloning TTS backend |
| [Cluster Scaling](docs/CLUSTER_SCALE.md) | Running multiple Ollama instances |
| [Backup & Restore](docs/BACKUP_RESTORE.md) | Data backup procedures |
| [Known Issues](KNOWN_ISSUES.md) | Current limitations and workarounds |

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │         Open WebUI :8080         │
                    │   (chat, workspaces, personas)   │
                    └──────────┬──────────────────────┘
                               │
                    ┌──────────▼──────────────────────┐
                    │    Portal Pipeline :9099          │
                    │  (routing, auth, metrics, MCP)   │
                    └──┬───┬───┬───┬──────────────────┘
                       │   │   │   │
          ┌────────────┘   │   │   └─────────────┐
          │                │   │                 │
   ┌──────▼──────┐  ┌──────▼──┐  ┌──────────────▼──┐
   │  Ollama      │  │SearXNG  │  │  MCP Servers     │
   │  :11434      │  │  :8088  │  │  :8910–8916      │
   │  (LLMs)      │  │(search) │  │  (tools)         │
   └─────────────┘  └─────────┘  └─────────────────┘
                                          │
                         ┌────────────────┼──────────────────┐
                         │                │                  │
                   ┌─────▼────┐    ┌──────▼──────┐   ┌──────▼──────┐
                   │ Documents │    │  TTS/Whisper │   │  Code/DinD  │
                   │  :8913    │    │  :8916/:8915 │   │   :8914     │
                   └──────────┘    └─────────────┘   └────────────┘

   Telegram Bot ──► Portal Pipeline    Slack Bot ──► Portal Pipeline
   (profile: telegram)                 (profile: slack)

   Grafana :3000 ◄── Prometheus :9090 ◄── /metrics
```

---

## License

MIT — see [LICENSE](LICENSE)
