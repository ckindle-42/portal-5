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
| Portal Pipeline | Intelligent routing, auth, metrics | :9099 (internal) |
| Ollama | Runs local GGUF models via Metal | :11434 (internal) |
| SearXNG | Private web search for research | (internal) |
| ComfyUI | Image and video generation (host-native) | http://localhost:8188 |
| MCP Servers (14) | ComfyUI (:8910), Video (:8911), Music (:8912), Documents (:8913), Code sandbox (:8914), Whisper (:8915), TTS (:8916), Security (:8919), Memory (:8920), RAG (:8921), Research (:8922), Browser (:8923), CAD render (:8926), Proxmox (:8927) | (internal) |
| Pipeline MCP | Stack introspection + FastContext code explorer for Claude Code / opencode | :8928 (host-native) |
| MITRE ATT&CK MCP | Technique lookup, data sources, detections — deterministic, not RAG | :8929 (internal) |
| Detections MCP | SPL library search, validate_syntax, explain_detection | :8932 (internal) |
| Wiki MCP | Canonical knowledge layer — search, get_unit, explain, cited answers | :8931 (internal) |
| MLX Transcribe | Diarized transcription — mlx-whisper + pyannote (Apple Silicon) | :8924 (host-native) |
| MLX Speech | Kokoro TTS + Qwen3-TTS/ASR (Apple Silicon) | :8918 (host-native) |
| Embedding | Harrier-0.6B text embeddings for RAG | :8917 (host-native) |
| Reranker | Qwen3-Reranker-0.6B two-stage RAG | :8925 (host-native) |
| Prometheus | Metrics collection | http://localhost:9090 |
| Grafana | Metrics dashboard | http://localhost:3000 |

---

## Workspaces

Select a workspace in the Open WebUI model dropdown to activate the right model
and tools automatically.

Portal 5 includes **29 functional workspaces** (plus 60 benchmark workspaces for performance comparison, gated off by default behind the `eval` module — see `coding_task/BUILD_PROGRAM_COLLAPSE_V1.md`; 89 total — `python3 -c "import yaml; d=yaml.safe_load(open('config/portal.yaml')); print(len(d['workspaces']))"`).

### Functional Workspaces

| Workspace | Purpose | Auto-activates |
|---|---|---|
| `auto` | General — routes to best model for each task | — |
| `auto-daily` | Fast everyday assistant — chat, writing, summarization, planning | web_search, memory, documents |
| `auto-coding` | One-shot code generation and review (Qwen3-Coder-30B MoE). 7 former sibling workspaces (auto-coding-agentic, auto-coding-uncensored(-agentic), auto-agentic(-lite/-ornith), auto-coding-northmini) are now `?variant=` query params or a persona's `variant:` field — `laguna` (Laguna-XS.2, self-improvement agentic), `uncensored`, `uncensored-agentic`, `heavy` (Qwen3-Coder-Next 80B, long-horizon), `lite` (AgentWorld 35B), `ornith` (Ornith-1.0 35B), `northmini` (North-Mini-Code) | Code sandbox |
| `auto-reasoning` | Extended reasoning, complex analysis | — |
| `auto-research` | Web research and synthesis | web_search, web_fetch |
| `auto-vision` | Image understanding, visual Q&A (Qwen3-VL 32B) | — |
| `auto-gemma-vision` | Heavy vision analysis — Gemma 4 31B Dense QAT | — |
| `auto-gemma-fast` | Fast Gemma 4 E2B/E4B responses | — |
| `auto-gemma-e4b` | Gemma 4 E4B specialist (audio + vision + text) | — |
| `auto-creative` | Creative writing with voice output | TTS |
| `auto-documents` | Create Word, Excel, PowerPoint | Documents + Code |
| `auto-data` | Data analysis, statistics, charting (Granite 4.1 30B) | Code + Documents |
| `auto-math` | Mathematical problem solving, proofs, calculus | Code sandbox |
| `auto-audio` | Audio processing and transcription | Transcribe |
| `auto-music` | Generate music via MusicGen | Music |
| `auto-video` | Generate video via ComfyUI | Video |
| `auto-cad` | 3D CAD model generation — OpenSCAD, CadQuery | CAD render |
| `auto-spl` | Splunk SPL queries, YARA rules, detection search | — |
| `auto-compliance` | NERC CIP gap analysis, policy review, audit prep (Granite 4.1 30B) | — |
| `auto-mistral` | Strategic analysis, business reasoning — Magistral 24B | — |
| `auto-phi4` | Phi-4 specialist — math, science, structured reasoning | — |
| `auto-bigfix` | IBM BigFix relevance scripting | — |
| `auto-devstral` | Devstral-Small-2 agentic coding lane | execute_bash |
| `auto-glm` | GLM-4.7-Flash REAP — non-Meta/Qwen lineage diversity | — |
| `auto-glm-thinking` | GLM-Z1-Rumination 32B extended reasoning | — |
| `auto-security` | Security analysis, CVE triage, hardening. 8 former sibling workspaces (auto-security-uncensored, auto-pentest, auto-blueteam, auto-redteam(-deep), auto-purpleteam(-deep/-exec)) are now `?variant=` query params or a persona's `variant:` field — `uncensored`, `pentest` (JANG-CRACK 31B, live execution), `blueteam` (sylink:8b, threat hunting), `redteam`/`redteam-deep` (SuperGemma4-26B), `purpleteam`/`purpleteam-deep`/`purpleteam-exec` (2/4-hop red→blue chains, exec = live attack + detection + IR playbook) | web_search, kb_search (exec/pentest variants add execute_bash, execute_python) |
| `auto-general-uncensored` | General uncensored assistant | — |
| `auto-extract-uncensored` | Uncensored information extraction | — |
| `tools-specialist` | Tool-use specialist — structured output, function calling (Granite 4.1 8B) | — |

### Benchmark Workspaces (user-selected only)

These pin a specific model for direct performance comparison. Not intended for daily use.
Run `python3 -c "from portal.platform.inference.router.workspaces import WORKSPACES; [print(k) for k in sorted(WORKSPACES) if k.startswith('bench-')]"` for the current full list (currently 60 workspaces).

| Workspace | Pinned model |
|---|---|
| `bench-agentworld` | Qwen-AgentWorld-35B-A3B UD-Q4_K_XL |
| `bench-devstral` | Devstral-Small-2507 24B (GGUF) |
| `bench-devstral-small-2` | Devstral-Small-2 24B Dec 2025 (GGUF) |
| `bench-fastcontext` | FastContext-1.0-4B-SFT (repository explorer subagent) |
| `bench-gemma4-12b` | Gemma 4 12B Q4_K_M (ctx8k) |
| `bench-gemma4-26b-qat` | Gemma 4 26B-A4B QAT |
| `bench-gemma4-31b-crack` | Gemma-4-31B-JANG_4M-CRACK Q4_K_M |
| `bench-gemma4-e2b` | Gemma 4 E2B MoE |
| `bench-gemma4-e4b` | Gemma 4 E4B MoE Q4_K_M |
| `bench-gemma4-e4b-qat` | Gemma 4 E4B QAT |
| `bench-glm` | GLM-4.7-Flash Q4_K_M |
| `bench-glm-reap` | GLM-4.7-Flash REAP 23B-A3B UD-Q4_K_XL |
| `bench-glm-z1-rumination` | GLM-Z1-Rumination-32B Q4_K_M |
| `bench-gptoss` | GPT-OSS 20B (Ollama) |
| `bench-granite41-8b` | Granite 4.1 8B (Ollama) |
| `bench-granite41-30b` | Granite 4.1 30B (Ollama) |
| `bench-huihui-qwen36-27b` | Huihui Qwen3.6-27B abliterated |
| `bench-huihui-qwen36-35b-a3b` | Huihui Qwen3.6-35B-A3B abliterated Q4_K_M |
| `bench-laguna` | Laguna-XS.2 33B-A3B Q4_K_M (Poolside AI) |
| `bench-lfm25-8b` | LFM2.5-8B-A1B (Liquid AI hybrid architecture) |
| `bench-lfm25-8b-uncensored` | LFM2.5-8B uncensored |
| `bench-nex-n2-mini` | Nex-N2-mini UD-Q4_K_M (Nex AGI) |
| `bench-omnicoder2` | OmniCoder-2 9B Q4_K_M |
| `bench-qwable-35b` | Qwable-3.6-35B Q4_K_M |
| `bench-qwen35-abliterated` | Qwen3.5-9B abliterated (Ollama) |
| `bench-qwen36-27b` | Qwen3.6-27B Q4_K_M |
| `bench-qwen36-35b-a3b` | Qwen3.6-35B-A3B MoE Q4_K_M |
| `bench-qwen36-35b-a3b-ud` | Qwen3.6-35B-A3B UD-Q4_K_XL (Unsloth Dynamic) |
| `bench-qwen3-coder-30b` | Qwen3-Coder 30B MoE A3B Q4_K_M |
| `bench-qwen3-coder-next` | Qwen3-Coder-Next 80B MoE Q4_K_M |
| `bench-qwen3-coder-next-abliterated` | Huihui Qwen3-Coder-Next abliterated Q4_K_M |
| `bench-sylink` | sylink:8b (SOC triage, DFIR, ATT&CK) |
| `bench-vulnllm-r7b` | VulnLLM-R-7B Q4_K_M |
| *(+ 15 more)* | Security exec chain, LFM micro, MTP, security bench lanes |

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
- `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` — LLM router fallback/standby (uncensored 3B). Router primary is `gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M` (pulled with `pull-models`)
- `nomic-embed-text` — document embeddings for RAG

### Specialized models (pulled with `./launch.sh pull-models`, ~60–100 GB total)
- **Security:** JANG-CRACK 31B (pentest), SuperGemma4-26B (red team), BaronLLM-9B (security analyst), sylink:8b (blue team primary — SOC triage, DFIR, ATT&CK); Foundation-Sec-8B in reasoning group for analytical blue-team work
- **Coding:** Qwen3-Coder-30B MoE, Laguna-XS.2 33B-A3B (auto-coding-agentic), Devstral-Small-2, GLM-4.7-Flash REAP, DeepSeek-Coder-V2
- **Reasoning:** DeepSeek-R1-0528-Qwen3-8B (auto-reasoning), GLM-Z1-Rumination-32B, GPT-OSS 20B, Tongyi-DeepResearch-abliterated
- **Vision:** Qwen3-VL 32B (auto-vision), Gemma4-31B dense QAT (auto-gemma-vision), Gemma4-E4B (auto-gemma-e4b)

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

## Coding Tool Integration (Claude Code / opencode)

Portal 5 ships first-class support for AI coding assistants. Two config files at the repo root
activate automatically when either tool opens this project:

- **`.mcp.json`** — currently 22 MCP servers (`python3 -c "import json; print(len(json.load(open('.mcp.json'))['mcpServers']))"`): filesystem, git, docker, fetch, portal-sandbox (execute_bash),
  portal-pipeline (FastContext code explorer + stack introspection), plus the other portal-* tool servers
- **`opencode.jsonc`** — points opencode at portal-pipeline (:9099) as a fully local AI backend;
  all 104 workspaces available as models; cloud providers disabled

**Claude Code** (uses Anthropic AI, Portal 5 as tool provider):
```bash
claude .    # .mcp.json picked up automatically — portal-sandbox + pipeline tools available
```

**opencode** (uses Portal 5 models locally, zero cloud):
```bash
export $(grep PIPELINE_API_KEY .env | xargs)
opencode .  # default model: portal/auto-coding-agentic (Laguna-XS.2 33B-A3B)
```

The `auto-coding-agentic` workspace uses **FastContext-4B** as an exploration subagent — it finds
exact file paths and line ranges before Devstral edits anything, reducing wasted token budget by
~50-60% compared to unguided file scanning.

See [MCP Dev Tooling](docs/MCP_DEV_TOOLING.md) for the full guide, workflow examples, and tool reference.

> **Secret scanning:** install the pre-commit hook once with
> `pip install pre-commit && pre-commit install`. It runs gitleaks on every commit to
> block accidental secret leaks. Real secrets live only in `.env` (gitignored,
> auto-generated by `./launch.sh`).

---

## Documentation

| Guide | Contents |
|---|---|
| [MCP Dev Tooling](docs/MCP_DEV_TOOLING.md) | Claude Code & opencode integration, FastContext explorer, workflow examples |
| [How-To Guide](docs/HOWTO.md) | Complete guide with working examples for every feature, including remote API access |
| [User Guide](docs/USER_GUIDE.md) | How to use workspaces, tools, personas |
| [Admin Guide](docs/ADMIN_GUIDE.md) | User management, configuration, security |
| [Alerts & Notifications](docs/ALERTS.md) | Operational alerts and daily summaries |
| [ComfyUI Setup](docs/COMFYUI_SETUP.md) | Advanced image/video model configuration |
| [Fish Speech Setup](docs/FISH_SPEECH_SETUP.md) | Optional voice cloning TTS backend |
| [Cluster Scaling](docs/CLUSTER_SCALE.md) | Running multiple Ollama instances |
| [Agent Loop](docs/AGENT_LOOP.md) | Platform-core bounded agent loop (`portal/platform/agent/`) — contracts, discipline, `portal agent` CLI |
| [Backup & Restore](docs/BACKUP_RESTORE.md) | Data backup procedures |
| [Known Issues](KNOWN_ISSUES.md) | Current limitations and workarounds |

### Acceptance Testing

The full acceptance test suite (`tests/portal5_acceptance_v6.py`) runs
~300 tests across ~27 sections. Run with:

```bash
python3 tests/portal5_acceptance_v6.py        # full suite
python3 tests/portal5_acceptance_v6.py --section S70  # one section
```

Latest run summary is in [ACCEPTANCE_RESULTS.md](ACCEPTANCE_RESULTS.md).

### Unit Test CI

The unit test suite (`pytest tests/unit -x`) runs on every PR and push to
`main` via GitHub Actions (`.github/workflows/unit-tests.yml`). For local
pre-commit feedback, install the hooks:

```bash
pip install pre-commit && pre-commit install
```

This adds a `pytest-unit` hook that runs before each commit.

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
