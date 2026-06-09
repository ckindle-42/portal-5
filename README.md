# Portal 5 — Local AI Platform

A complete, private AI platform that runs on your hardware. Text, code, security
analysis, images, video, music, documents, and voice — all local, all yours.

Connects to Open WebUI, Telegram, and Slack. Routes automatically to the right
model for each task. No cloud accounts. No usage fees. Inference is fully local —
your prompts and responses never leave your machine. Model downloads from HuggingFace
or Ollama registries transmit standard HTTP metadata; if `HF_TOKEN` is configured for
gated models, authentication requests are sent to HuggingFace.

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
| ComfyUI | Image and video generation (host-native) | http://localhost:8188 |
| 12 MCP Servers | Documents (:8913), Code sandbox (:8914), Security (:8919), Whisper (:8915), TTS (:8916), ComfyUI (:8910), Video (:8911), Music (:8912, host-native — requires `./launch.sh install-music`), Memory (:8920), RAG (:8921), Research (:8922), Browser (:8923) | (internal) |
| MLX Transcribe | Diarized transcription (mlx-whisper + pyannote speaker labeling, Apple Silicon only) | :8924 (internal) |
| MLX Speech | Kokoro TTS + Qwen3-TTS/ASR (host-native, Apple Silicon only) | :8918 (internal) |
| Embedding | Harrier-0.6B text embeddings for RAG | :8917 (internal) |
| Prometheus | Metrics collection | http://localhost:9090 |
| Grafana | Metrics dashboard | http://localhost:3000 |

---

## Workspaces

Select a workspace in the Open WebUI model dropdown to activate the right model
and tools automatically.

Portal 5 includes **19 functional workspaces** (plus 18 benchmark workspaces for performance comparison).

### Functional Workspaces

| Workspace | Purpose | Auto-activates |
|---|---|---|
| `auto` | General — routes to best model | — |
| `auto-daily` | Fast everyday assistant — chat, writing, summarization, planning (gemma-4-26b-a4b, 57.8 TPS) | Research + Memory |
| `auto-coding` | Code generation and review | Code sandbox |
| `auto-agentic` | Long-horizon multi-file agentic coding (Qwen3-Coder-Next 80B) | Code sandbox |
| `auto-security` | Security analysis and hardening | Code sandbox |
| `auto-redteam` | Offensive security research | Code sandbox |
| `auto-blueteam` | Defensive security, incident response | Code sandbox |
| `auto-documents` | Create Word, Excel, PowerPoint | Documents + Code |
| `auto-music` | Generate music via HuggingFace MusicGen | Music + TTS |
| `auto-video` | Generate video via ComfyUI | Video + Image |
| `auto-vision` | Image understanding, visual tasks | Image generation |
| `auto-creative` | Creative writing | TTS voice |
| `auto-research` | Web research and synthesis | — |
| `auto-reasoning` | Deep reasoning, complex analysis | — |
| `auto-data` | Data analysis, statistics | Code + Documents |
| `auto-math` | Mathematical problem solving, proofs, calculus | Code sandbox |
| `auto-spl` | Splunk SPL queries, pipeline explanation | — |
| `auto-compliance` | NERC CIP gap analysis, policy review, audit prep | — |
| `auto-mistral` | Strategic analysis, business reasoning | — |

### Benchmark Workspaces (user-selected only)

These pin a specific model for direct performance comparison. Not intended for daily use.

| Workspace | Pinned model |
|---|---|
| `bench-devstral` | Devstral-Small-2507 (GGUF) |
| `bench-dolphin8b` | Dolphin 3.0 Llama 3.1 8B (GGUF) |
| `bench-glm` | GLM-4.7-Flash (Q4 GGUF) |
| `bench-gptoss` | GPT-OSS 20B (Ollama) |
| `bench-granite41-8b` | Granite 4.1 8B (Ollama) |
| `bench-granite41-30b` | Granite 4.1 30B (Ollama) |
| `bench-laguna` | Laguna-XS.2 33B-A3B (Q4 GGUF) |
| `bench-llama33-70b` | Llama 3.3 70B (Q4 GGUF) |
| `bench-negentropy` | Negentropy 9B (GGUF, Ollama) |
| `bench-olmo3-32b` | Olmo-3 32B (GGUF, Ollama) |
| `bench-omnicoder2` | OmniCoder-2 9B (Ollama) |
| `bench-phi4` | Phi-4 (Q8 GGUF) |
| `bench-phi4-reasoning` | Phi-4 reasoning plus (GGUF) |
| `bench-qwen35-abliterated` | Qwen3.5-9B abliterated (Ollama) |
| `bench-qwen36-27b` | Qwen3.6-27B (GGUF) |
| `bench-qwen36-35b-a3b` | Qwen3.6-35B-A3B MoE (GGUF) |
| `bench-qwen3-coder-30b` | Qwen3-Coder 30B MoE A3B (Q4 GGUF) |
| `bench-qwen3-coder-next` | Qwen3-Coder-Next 80B MoE (Q4 GGUF) |

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

# MLX (Apple Silicon)
./launch.sh start-speech    # Start MLX speech server (Apple Silicon)
./launch.sh stop-speech     # Stop MLX speech server
./launch.sh mlx-status      # Check MLX component status (includes speech)

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

# Seeding
./launch.sh seed            # Re-seed Open WebUI (workspaces + personas)
./launch.sh reseed          # Force-refresh all presets (delete + recreate)

# Update (single command: git pull + rebuild + model refresh + re-seed)
./launch.sh update                  # Full update of all components
./launch.sh update --skip-models    # Skip Ollama + MLX model refresh (faster)
./launch.sh update --models-only    # Only refresh models

# Cleanup
./launch.sh clean           # Remove containers (keeps model weights)
./launch.sh clean-all       # Remove everything including models
./launch.sh rebuild         # Rebuild portal-pipeline Docker image after git pull
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
- `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` — fast routing classifier (uncensored)
- `nomic-embed-text` — document embeddings for RAG

### Specialized models (pulled with `./launch.sh pull-models`, ~60–100 GB total)
- **Security:** BaronLLM-6B, Lily-Cybersecurity-7B, WhiteRabbitNeo-33B, The-Xploiter
- **Coding:** Qwen3-Coder-30B, GLM-4.7-Flash, Devstral-24B, DeepSeek-Coder-V2
- **Reasoning:** DeepSeek-R1-32B, Tongyi-DeepResearch-30B
- **Vision:** Qwen3-VL 32B, LLaVA-7B

### MLX models (Apple Silicon, retained for audio/embedding/reranker only — chat inference is Ollama-only)
- **Speech:** MLX speech server (:8918) — Kokoro + Qwen3-TTS/ASR, host-native
- **Transcription:** MLX Transcribe (:8924) — mlx-whisper + pyannote diarization, host-native
- **Embedding:** Harrier-0.6B TEI (:8917)
- **Reranker:** Qwen3-Reranker-0.6B-mxfp8 (:8925)
- Chat model inference runs exclusively through Ollama (:11434) — GGUF format, pulled via `ollama pull`

The MLX inference proxy (:8081/:18081/:18082) was retired in commit 3a0c58e.

### Image generation (downloaded automatically on first run, ~12 GB)
- FLUX.1-schnell — fast, high-quality image generation

To use a different image model: set `IMAGE_MODEL=sdxl` or `IMAGE_MODEL=flux-dev`
in `.env` (flux-dev requires a HuggingFace token).

---

## Speech (Text-to-Speech & Speech-to-Text)

Portal 5 includes a native MLX speech server on Apple Silicon with:
- **Kokoro TTS** — fast, high-quality English TTS (200+ voices)
- **Qwen3-TTS** — 10 languages, voice cloning, voice design, emotion control
- **Qwen3-ASR** — speech-to-text via MLX

```bash
./launch.sh start-speech    # Start MLX speech server (Apple Silicon)
./launch.sh stop-speech     # Stop MLX speech server
./launch.sh mlx-status      # Check MLX component status (includes speech)
```

> **Kokoro TTS dependencies:** The Kokoro backend requires additional Python
> packages that are not installed automatically. Install them before using Kokoro:
> ```bash
> pip install misaki num2words spacy phonemizer
> python3 -m spacy download en_core_web_sm
> ```
> Qwen3-TTS and Qwen3-ASR work without these dependencies.

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

## Security

### Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PIPELINE_API_KEY` | **Yes** | API key for pipeline authentication. Generate with: `openssl rand -hex 32`. Pipeline will not start without this. |

### Network Exposure

By default, the Portal Pipeline binds to all interfaces (`0.0.0.0:9099`) to allow LAN access from other applications. This is intentional for multi-device setups.

**Security Considerations**:
- The pipeline is protected by `PIPELINE_API_KEY` authentication
- Ensure your LAN is trusted or use firewall rules to restrict access
- For local-only deployments, set in `.env`: `PIPELINE_LISTEN_ADDR=127.0.0.1`

---

## Documentation

| Guide | Contents |
|---|---|
| [How-To Guide](docs/HOWTO.md) | Complete guide with working examples for every feature, including remote API access |
| [User Guide](docs/USER_GUIDE.md) | How to use workspaces, tools, personas |
| [Admin Guide](docs/ADMIN_GUIDE.md) | User management, configuration, security |
| [Alerts & Notifications](docs/ALERTS.md) | Operational alerts and daily summaries |
| [ComfyUI Setup](docs/COMFYUI_SETUP.md) | Advanced image/video model configuration |
| [Fish Speech Setup](docs/FISH_SPEECH_SETUP.md) | Optional voice cloning TTS backend |
| [Cluster Scaling](docs/CLUSTER_SCALE.md) | Running multiple Ollama instances |
| [Backup & Restore](docs/BACKUP_RESTORE.md) | Data backup procedures |
| [Known Issues](KNOWN_ISSUES.md) | Current limitations and workarounds |

### Acceptance Testing

The full acceptance test suite (`tests/portal5_acceptance_v6.py`) runs
~250 checks across 30 sections. Run with:

```bash
python3 tests/portal5_acceptance_v6.py        # full suite
python3 tests/portal5_acceptance_v6.py --section S70  # one section
```

Latest run summary is in [ACCEPTANCE_RESULTS.md](ACCEPTANCE_RESULTS.md).

---

## Architecture

```
┌──────────────┐
│  Open WebUI  │
│    :8080     │
└──────┬───────┘
                │
                     ┌────────────▼───────────────────┐
                     │    Portal Pipeline :9099         │
                     │  (routing, auth, metrics, MCP)  │
                     └──┬───┬───┬───┬─────────────────┘
                        │   │   │   │
           ┌────────────┘   │   │   └─────────────┐
           │                │   │                 │
    ┌──────▼──────┐  ┌──────▼──┐  ┌──────────────────▼──┐
    │  Ollama      │  │ Ollama  │  │  MCP Servers          │
    │  :11434      │  │ :11434  │  │  :8910–8916 (tools)   │
    │  (LLMs)      │  │ (LLMs)  │  │  :8917 (embedding)    │
    └─────────────┘  └─────────┘  │  :8918 (speech)       │
                                  │  :8924 (transcribe)   │
    Ollama is the single          │  :8925 (reranker)     │
    inference tier (:11434).      └─────────────────────┘
    MLX speech/transcription/
    embedding/reranker are
    retained for non-chat use.

    Telegram Bot ──► Portal Pipeline    Slack Bot ──► Portal Pipeline
    (profile: telegram)                 (profile: slack)

    Grafana :3000 ◄── Prometheus :9090 ◄── /metrics
```

All chat inference runs through Ollama (:11434) with its native MLX Metal backend on
Apple Silicon. The MLX inference proxy (:8081/:18081/:18082) was retired in commit 3a0c58e.
MLX is retained for speech (:8918), transcription (:8924), embeddings (:8917),
and reranking (:8925) — non-chat-inference runtimes only.

---

## License

MIT — see [LICENSE](LICENSE)
