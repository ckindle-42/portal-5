# CLAUDE.md — Claude Code Guidelines for Portal 5

**Project**: Portal 5 — Open WebUI Intelligence Layer  
**Repository**: https://github.com/ckindle-42/portal-5  
**Version**: 6.0.0
**Last Updated**: April 7, 2026

---

## What Portal 5 Is

Portal 5 is an **Open WebUI enhancement layer** — not a replacement web stack. It extends Open WebUI through its native extension points (Pipeline server, MCP Tool Servers) rather than duplicating what Open WebUI already does. The result is a complete local AI platform covering text, code, security, images, video, music, documents, and voice — all running on local hardware, all accessible through a single Open WebUI interface.

**This project has two roles:**
1. **Personal local AI** — single M4 Mac or Linux node, launch and use today
2. **Foundation node** for the Mac Studio cluster growth path (Stage 1→5, Track B Apple Silicon)

**Hardware targets**: Apple M4 Mac (primary), NVIDIA CUDA Linux (secondary), any Docker host  
**Architecture**: Open WebUI ← Portal Pipeline (:9099) ← MLX proxy (host:8081) → mlx_lm (18081) / mlx_vlm (18082) / Ollama (fallback, host:11434) ← local models  
**Inference strategy**: MLX-first on Apple Silicon (20-40% faster), Ollama GGUF fallback. Both run natively on host (not Docker).  
**MLX requirement**: The MLX proxy (`scripts/mlx-proxy.py`) is **always running** and **required** on Apple Silicon. It auto-switches between `mlx_lm` (text-only models) and `mlx_vlm` (VLM models including Qwen3.5 family) based on the requested model. Only one server runs at a time due to unified memory constraints. Coding workspaces and coding personas depend on MLX as their primary inference path. Ollama serves as fallback for non-MLX model groups and general routing.  
**Core values**: Privacy-first, fully local, zero cloud dependencies, launch in one command

---

## What Portal 5 Is NOT

Do not add these — they are explicitly out of scope:

- A web chat interface — Open WebUI handles that
- An auth system — Open WebUI handles that  
- A RAG/knowledge base — Open WebUI handles that
- A metrics/observability stack — Open WebUI handles that
- Cloud inference (OpenRouter, Anthropic API, etc.)
- External agent frameworks (LangChain, LlamaIndex, etc.)
- Anything requiring user accounts or API keys beyond what's in `.env.example`

---

## Project Layout

```
portal-5/
├── portal_pipeline/              # FastAPI Pipeline server (:9099)
│   ├── cluster_backends.py       # BackendRegistry — Ollama + vLLM + MLX, health-aware
│   ├── router_pipe.py            # /v1/models + /v1/chat/completions routing
│   ├── __main__.py               # Uvicorn entrypoint (multi-worker)
│   └── notifications/            # Operational alerts + daily summaries
│       ├── dispatcher.py         # Event bus: fans out to all configured channels
│       ├── events.py             # AlertEvent / SummaryEvent / EventType
│       ├── scheduler.py          # APScheduler daily summary
│       └── channels/             # Slack, Telegram, Email, Pushover, Webhook
├── portal_mcp/                   # MCP Tool Servers (registered in Open WebUI)
│   ├── documents/                # Word, PowerPoint, Excel generation (:8913)
│   ├── generation/               # Music (:8912), TTS (:8916), Video (:8911), Whisper (:8915), ComfyUI (:8910)
│   ├── execution/                # Code sandbox (:8914)
│   └── mcp_server/               # Vendored FastMCP implementation
├── portal_channels/              # Optional push interfaces
│   ├── telegram/bot.py           # Telegram → Pipeline adapter
│   └── slack/bot.py              # Slack → Pipeline adapter
├── config/
│   ├── backends.yaml             # OPERATOR EDITS THIS — adds cluster nodes here, no code changes
│   ├── personas/                 # 40 persona YAML files → Open WebUI model presets
│   ├── routing_descriptions.json # LLM router workspace descriptions
│   ├── routing_examples.json     # LLM router few-shot examples
│   ├── searxng/                  # SearXNG search engine config
│   ├── prometheus/               # Prometheus scrape config
│   └── grafana/                  # Grafana dashboards + datasources
├── deploy/portal-5/
│   └── docker-compose.yml        # THE launch definition — all services
├── scripts/
│   ├── openwebui_init.py         # Auto-seeds Open WebUI on first fresh volume
│   ├── mlx-proxy.py              # MLX dual-server proxy (auto-switches mlx_lm ↔ mlx_vlm, admission control)
│   ├── mlx-watchdog.py           # MLX component health monitor with auto-recovery
│   ├── mlx-switch-benchmark.py   # MLX model switch timing benchmark
│   ├── pipeline-entrypoint.sh    # Docker entrypoint for portal-pipeline
│   ├── download_comfyui_models.py # ComfyUI model download helper
│   └── update_workspace_tools.py # Workspace tool ID sync helper
├── imports/openwebui/            # Pre-built JSON files for Open WebUI GUI import
│   ├── tools/                    # MCP Tool Server registration JSONs
│   ├── workspaces/               # Workspace preset JSONs
│   └── functions/                # Open WebUI Function (pipe) JSONs
├── tests/
│   ├── unit/                     # pytest unit tests — no Docker required
│   └── benchmarks/               # MLX vs Ollama performance benchmarks
├── Dockerfile.pipeline           # Lean image for portal-pipeline service
├── Dockerfile.mcp                # Image for all portal_mcp services
├── launch.sh                     # Single entry point (30+ commands, see below)
└── .env.example                  # All configurable values with defaults
```

---

## Tech Stack & Tooling

| Tool | Command | Notes |
|---|---|---|
| **Package manager** | `uv` | NOT pip directly. Lock file: `uv.lock` |
| **Install** | `uv pip install -e ".[dev]"` | Installs all extras + dev deps |
| **Linter** | `ruff check . --fix` | Ruff handles lint AND format |
| **Formatter** | `ruff format .` | NOT Black |
| **Type check** | `mypy portal_pipeline/ portal_mcp/` | strict=true currently |
| **Tests** | `pytest tests/ -v --tb=short` | Must pass before any commit |
| **Python** | 3.10+ required | pyproject.toml requires-python >= 3.10 |
| **Framework** | FastAPI + Pydantic v2 | Async throughout |
| **Launch** | `./launch.sh up` | Never `docker compose up` directly. 30+ commands (see below) |

---

## Architectural Ground Rules

### 1 — config/backends.yaml Is Sacred

This is the ONLY file an operator edits to scale from 1 node to 12. Never hardcode backend URLs in Python. All backend discovery flows through `BackendRegistry`. Adding a Mac Studio cluster node means adding 6 lines of YAML, nothing else.

### 2 — Never Modify Open WebUI Source

Portal 5 extends Open WebUI through documented extension points only:
- **Pipeline server** (`portal-pipeline` at :9099) — registered as an OpenAI API connection
- **MCP Tool Servers** — registered in Admin > Settings > Tools
- **Open WebUI Functions** — installed via Workspace > Functions > Import

If something seems to require modifying Open WebUI internals, find the extension point instead.

### 3 — MCP Servers Are Independent Services

Each `portal_mcp/` server is a standalone FastAPI+FastMCP app. They have zero imports from `portal_pipeline/` or `portal_channels/`. They are registered in Open WebUI as Tool Servers. They do not know about each other.

### 4 — The Pipeline Is Stateless (with metrics persistence)

`portal_pipeline/router_pipe.py` is stateless for conversation routing — no database, no session state, no memory. Conversation history lives in Open WebUI's database. Cross-session memory uses Open WebUI's native memory feature.

However, the pipeline **does persist operational metrics** to a JSON state file (`/app/data/metrics_state.json`) that survives restarts. This includes request counts, token totals, TPS aggregates, error counts, and persona usage. The state is written every 60 seconds and merged atomically across multiple uvicorn workers. This is operational telemetry only — it does not affect routing decisions.

### 5 — Personas Live in config/personas/

Each `.yaml` in `config/personas/` becomes an Open WebUI model preset during seeding. The YAML defines: `name`, `slug`, `system_prompt`, `workspace_model` (which Ollama model to use), `category`. The `openwebui_init.py` script reads these and creates model presets in Open WebUI. Adding a new persona = adding one YAML file.

### 6 — Workspace Routing Must Stay Consistent

`WORKSPACES` dict in `router_pipe.py` and `workspace_routing` in `backends.yaml` must define **identical keys**. The `scripts/openwebui_init.py` seeding must create a model preset for each key. After any change, run:
```bash
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print('Workspace IDs consistent')
"
```

### 7 — All Ports Are Reserved

| Port | Service |
|---|---|
| 8080 | Open WebUI |
| 9099 | Portal Pipeline |
| 8081 | MLX proxy (auto-switches mlx_lm ↔ mlx_vlm) |
| 18081 | mlx_lm server (text-only, managed by proxy) |
| 18082 | mlx_vlm server (VLM, managed by proxy) |
| 8910 | MCP: ComfyUI |
| 8911 | MCP: Video |
| 8912 | MCP: Music |
| 8913 | MCP: Documents |
| 8914 | MCP: Code Sandbox |
| 8915 | MCP: Whisper |
| 8916 | MCP: TTS |
| 8917 | Embedding (Harrier-0.6B TEI) |
| 8188 | ComfyUI |
| 8088 | SearXNG |
| 11434 | Ollama |
| 9090 | Prometheus |
| 3000 | Grafana |

Do not reassign these. Do not add new services on overlapping ports without updating this table.

### 8 — Models Pull From Ollama or HuggingFace GGUF Imports

All text models run through Ollama. HuggingFace is used for:
- **GGUF model imports** via Ollama's `hf.co/` pull format (e.g., `hf.co/org/repo-GGUF`) — used for Llama 3.2 3B Abliterated (router), BaronLLM, Lily Cybersecurity, Dolphin3 R1 Mistral, WhiteRabbitNeo, GLM 4.7 Flash, DeepSeek Coder V2 Lite, DeepSeek R1 32B, Llama 3.3 70B, Dolphin Llama3 70B
- ComfyUI image/video model weights (downloaded into ComfyUI's `models/` directory)
- MLX model weights (downloaded by `huggingface_hub.snapshot_download` via `./launch.sh pull-mlx-models`)
- Music generation models (downloaded by HuggingFace `transformers` MusicGen on first use)
- Whisper models (downloaded by faster-whisper on first use)

Never add `transformers` or `torch` to `portal_pipeline/` — it runs lean.

### 9 — The Dockerfile Split Is Intentional

- `Dockerfile.pipeline` — minimal: fastapi, uvicorn, httpx, pyyaml only. Fast build, lean image.
- `Dockerfile.mcp` — heavier: adds python-docx, python-pptx, openpyxl, fastmcp, etc.

Do not merge them. The pipeline container must stay small for fast restarts.

### 10 — Git Discipline

```bash
git checkout main && git pull
git checkout -b feature/your-thing
# do work, tests pass
git commit -m "type(scope): description"
git push origin feature/your-thing
# open PR → merge → delete branch
```

**Never commit directly to main.** Never force push. Branch names: `feature/`, `fix/`, `chore/`.

---

## Model Catalog

These are the models Portal 5 is designed around. MLX models run via `mlx_vlm` (always on). Ollama models are pulled via `ollama pull`. The `DEFAULT_MODEL` in `.env` is pulled automatically on `./launch.sh up`. Others are pulled on demand or via `./launch.sh pull-models`.

**HuggingFace GGUF imports**: Some models use Ollama's `hf.co/` pull format (e.g., `hf.co/org/repo-GGUF`) — this is Ollama's native mechanism for importing GGUF models directly from HuggingFace. These are valid Ollama model identifiers, not URLs, and are part of the intentional Apple Silicon setup.

### Text Models (Ollama)

**General**

| Model | Ollama Tag | Purpose | RAM |
|---|---|---|---|
| Dolphin Llama3 8B | `dolphin-llama3:8b` | Default, general, function calling | 8GB |
| Dolphin Llama3 70B | `dolphin-llama3:70b-q4_k_m` | High-quality general (needs 48GB+) | 48GB |
| Llama 3.2 3B Abliterated | `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` | Fast routing classifier, uncensored | 3GB |

**Coding** (Ollama fallback — MLX is primary for coding workspaces)

| Model | Ollama Tag | Purpose | RAM |
|---|---|---|---|
| Qwen3 Coder Next 30B | `qwen3-coder-next:30b-q5` | Code generation, review (persona model) | 24GB |
| Qwen3 Coder 30B MoE | `qwen3-coder:30b` | Primary Ollama coding fallback (3B active) | 19GB |
| Qwen3.5 9B | `qwen3.5:9b` | Fast coding / documents | 6GB |
| Devstral 24B | `devstral:24b` | Code, agentic development | 20GB |
| DeepSeek Coder V2 16B | `deepseek-coder-v2:16b-lite-instruct-q4_K_M` | Code, math | 11GB |
| DeepSeek Coder V2 Lite | `deepseek-coder-v2-lite:q4_k_m` | Fast code fallback | 9GB |
| GLM 4.7 Flash | `glm-4.7-flash:q4_k_m` | Coding, fast reasoning | 5GB |
| Llama 3.3 70B | `llama3.3:70b-q4_k_m` | Heavy coding (PULL_HEAVY) | 43GB |

**Security**

| Model | Ollama Tag | Purpose | RAM |
|---|---|---|---|
| The-Xploiter | `xploiter/the-xploiter` | Red team / security offense | 12GB |
| WhiteRabbitNeo 8B | `lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0` | Security research | 6GB |
| WhiteRabbitNeo 33B | `whiterabbitneo:33b-v1.5-q4_k_m` | Security research, heavy | 22GB |
| BaronLLM Abliterated | `huihui_ai/baronllm-abliterated` | Uncensored general / creative | 6GB |
| BaronLLM Q6K (imported) | `baronllm:q6_k` | Security offensive, higher quality | 8GB |
| Lily Cybersecurity 7B (imported) | `lily-cybersecurity:7b-q4_k_m` | Blue team defense | 5GB |
| Dolphin3 R1 Mistral 24B | `dolphin3-r1-mistral:24b-q4_k_m` | Security research with reasoning | 16GB |
| Dolphin Llama3 70B | `dolphin-llama3:70b-q4_k_m` | Heavy uncensored (PULL_HEAVY) | 48GB |

**Reasoning / Research**

| Model | Ollama Tag | Purpose | RAM |
|---|---|---|---|
| DeepSeek R1 32B | `deepseek-r1:32b-q4_k_m` | Primary reasoning + chain-of-thought | 20GB |
| Tongyi DeepResearch 30B | `huihui_ai/tongyi-deepresearch-abliterated` | Research, analysis | 19GB |

**Vision**

| Model | Ollama Tag | Purpose | RAM |
|---|---|---|---|
| Qwen3 VL 32B | `qwen3-vl:32b` | Multimodal, vision, audio | 32GB |
| LLaVA 7B | `llava:7b` | Vision / image understanding | 8GB |

### MLX Models (Apple Silicon) — Always Running, Required

The MLX proxy (`scripts/mlx-proxy.py` at `:8081`) is **always on** and **required** — it is not optional on Apple Silicon. Coding workspaces (`auto-coding`) and all coding personas route through MLX as their primary inference path. If MLX is not running, coding workspaces fall back to Ollama coding group, but this is degraded operation.

The proxy auto-switches between two servers based on the requested model:
- **`mlx_lm.server`** (port 18081) — text-only models (Qwen3-Coder-Next, DeepSeek-R1, Devstral, Llama)
- **`mlx_vlm.server`** (port 18082) — VLM models (Qwen3.5 family with vision tower)

Only one server runs at a time due to unified memory constraints. Switching takes ~30s on first request after a switch.

Install: `./launch.sh install-mlx`. Pre-warm a model: `./launch.sh switch-mlx-model <tag>`.

| Model | Memory | Server | Safe Concurrent With |
|---|---|---|---|
| `mlx-community/Qwen3-Coder-Next-4bit` | ~46GB | mlx_lm | No concurrent ComfyUI — 46GB + 8GB OS = 54GB |
| `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit` | ~22GB | mlx_lm | ComfyUI (CPU) + Ollama general (3B) |
| `mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit` | ~12GB | mlx_lm | ComfyUI (CPU) + Ollama general (3B) |
| `lmstudio-community/Devstral-Small-2507-MLX-4bit` | ~15GB | mlx_lm | ComfyUI (CPU) + Ollama general (3B) |
| `Jackrong/MLX-Qwopus3.5-27B-v3-8bit` | ~22GB | mlx_lm | ComfyUI (CPU) + Ollama general (3B) |
| `Jackrong/MLX-Qwopus3.5-9B-v3-8bit` | ~9GB | mlx_lm | Everything — safe baseline |
| `Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit` | ~14GB | mlx_lm | ComfyUI (CPU) + Ollama general (3B) |
| `Jackrong/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit` | ~9GB | mlx_lm | Everything — safe baseline |
| `Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit` | ~28GB | mlx_lm | ComfyUI (CPU) + Ollama general (3B) |
| `mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit` | ~34GB | mlx_lm | ComfyUI (CPU) + Ollama general (3B) |
| `mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit` | ~18GB | mlx_lm | ComfyUI (CPU) + Ollama general (3B) |
| `mlx-community/Dolphin3.0-Llama3.1-8B-8bit` | ~9GB | mlx_lm | Everything — safe baseline |
| `mlx-community/Llama-3.2-3B-Instruct-8bit` | ~3GB | mlx_lm | Everything — safe baseline |
| `mlx-community/phi-4-8bit` | ~14GB | mlx_lm | ComfyUI (CPU) + Ollama general (3B) |
| `mlx-community/gemma-4-31b-it-4bit` | ~18GB | mlx_vlm | ComfyUI (CPU) + Ollama general (~5GB) |
| `lmstudio-community/Magistral-Small-2509-MLX-8bit` | ~24GB | mlx_lm | ComfyUI (CPU) + Ollama general (~5GB) |
| `mlx-community/Llama-3.3-70B-Instruct-4bit` | ~40GB | mlx_lm | Ollama only (3B) — unload others first |
| `mlx-community/Qwen3-VL-32B-Instruct-8bit` | ~36GB | mlx_vlm | ComfyUI (CPU) + Ollama general (3B) |
| `mlx-community/llava-1.5-7b-8bit` | ~8GB | mlx_vlm | ComfyUI + Ollama + Wan2.2 video |
| `mlx-community/Llama-3.2-11B-Vision-Instruct-abliterated-4-bit` | ~7GB | mlx_vlm | ComfyUI + Ollama + Wan2.2 video |
| `mlx-community/GLM-OCR-bf16` | ~2GB | mlx_vlm | Everything — OCR specialist for document ingestion |

**64GB systems**: Qwen3-Coder-Next-4bit (~46GB) + Ollama (~5GB) + OS (~8GB) = 59GB — no concurrent ComfyUI/Wan2.2.
**64GB systems**: Qwen3-Coder-30B-8bit (~32GB) + Ollama (~5GB) + OS (~8GB) = 45GB — no ComfyUI headroom; Ollama routing only.
**64GB systems**: Llama-3.3-70B (~40GB) + anything else is tight — set `OLLAMA_MAX_LOADED_MODELS=1`.
**64GB systems**: Gemma-4-31B (~18GB) + Magistral-Small (~24GB) = 42GB combined — coexist safely.
**64GB systems**: Qwen3.5-35B-A3B-Claude (~28GB) + Wan2.2 (~18GB) + Ollama (~5GB) = 51GB — feasible.
**32GB systems**: Use Llama-3.2-3B (~3GB) or Devstral-Small (~22GB). Heavy models (70B, Qwen3-Coder-Next, Qwen3-Coder-30B-8bit) will OOM.

### MLX Memory Coexistence

Unified memory is shared across all workloads. The proxy ensures only one MLX server runs at a time.

| System RAM | MLX Model | Simultaneously Safe |
|---|---|---|
| 32GB | Llama-3.2-3B (~3GB) | ComfyUI flux-schnell + Ollama general |
| 32GB | DeepSeek-Coder-Lite (~14GB) | Ollama routing only |
| 32GB | Qwen3-Coder-30B-8bit (~32GB) | Will OOM on 32GB — use 4-bit variant instead |
| 64GB | Qwen3-Coder-Next-4bit (~46GB) | Ollama general only — unload before ComfyUI |
| 64GB | Jackrong-27B-v2-4bit (~14GB) | ComfyUI flux-schnell + Ollama general |
| 64GB | Phi-4-8bit (~14GB) | ComfyUI flux-schnell + Ollama general |
| 64GB | Gemma-4-31B (~18GB) | ComfyUI Wan2.2 + Ollama general |
| 64GB | Magistral-Small-8bit (~24GB) | ComfyUI flux-schnell + Ollama general |
| 64GB | Llama-3.3-70B (~40GB) | Nothing else heavy — stop ComfyUI first |

Pre-warm a model: `./launch.sh switch-mlx-model <tag>`

> **Note (v6.0.0):** Memory coexistence rules are now self-enforcing via MLX proxy admission control (P5-FUT-009). See `MODEL_MEMORY` dict in `scripts/mlx-proxy.py`. The proxy will reject model loads with HTTP 503 and an actionable message if available memory is insufficient.

### Embedding & Retrieval Models

| Model | Served By | Purpose | RAM |
|---|---|---|---|
| Harrier-OSS-v1-0.6B | portal5-embedding (TEI, :8917) | RAG embedding, 32K ctx, SOTA MTEB-v2, Microsoft lineage | ~1.2GB |
| bge-reranker-v2-m3 | Open WebUI internal (sentence-transformers) | Cross-encoder reranker for RAG result scoring | ~0.6GB |
| nomic-embed-text:latest | Ollama (fallback) | Legacy embedding fallback if embedding service is down | ~0.3GB |

### OCR Models

| Model | Server | Purpose | RAM |
|---|---|---|---|
| `mlx-community/GLM-OCR-bf16` | Host-side mlx_vlm | Scanned document OCR for compliance doc ingestion | ~2GB |

### Generation Models (ComfyUI / HuggingFace)

| Model | Source | Purpose |
|---|---|---|
| FLUX.1-schnell | `black-forest-labs/FLUX.1-schnell` | Fast image generation |
| FLUX.1-dev | `black-forest-labs/FLUX.1-dev` | High-quality image generation |
| SDXL Base 1.0 | `stabilityai/stable-diffusion-xl-base-1.0` | Image generation alternative |
| Wan2.2 T2V 5B | `Wan-AI/Wan2.2-T2V-5B` | Text-to-video generation |
| MusicGen Small/Medium/Large | HuggingFace (auto via transformers) | Music generation |
| Fish Speech | GitHub (fish-speech repo) | Text-to-speech |
| Faster-Whisper | HuggingFace (auto via faster-whisper) | Speech-to-text |

---

## Persona Catalog

Personas live in `config/personas/*.yaml`. Each becomes a model preset in Open WebUI.

### Development
- `bugdiscoverycodeassistant` → `qwen3-coder-next:30b-q5`
- `codebasewikidocumentationskill` → `qwen3-coder-next:30b-q5`
- `codereviewassistant` → `qwen3-coder-next:30b-q5`
- `codereviewer` → `qwen3-coder-next:30b-q5`
- `devopsautomator` → `qwen3-coder-next:30b-q5`
- `devopsengineer` → `qwen3-coder-next:30b-q5`
- `ethereumdeveloper` → `qwen3-coder-next:30b-q5`
- `fullstacksoftwaredeveloper` → `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit`
- `githubexpert` → `qwen3-coder-next:30b-q5`
- `javascriptconsole` → `qwen3-coder-next:30b-q5`
- `kubernetesdockerrpglearningengine` → `qwen3-coder-next:30b-q5`
- `pythoncodegeneratorcleanoptimizedproduction-ready` → `qwen3-coder-next:30b-q5`
- `pythoninterpreter` → `qwen3-coder-next:30b-q5`
- `seniorfrontenddeveloper` → `qwen3-coder-next:30b-q5`
- `seniorsoftwareengineersoftwarearchitectrules` → `qwen3-coder-next:30b-q5`
- `softwarequalityassurancetester` → `qwen3-coder-next:30b-q5`
- `ux-uideveloper` → `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit`

### Security
- `cybersecurityspecialist` → `xploiter/the-xploiter`
- `networkengineer` → `xploiter/the-xploiter`
- `redteamoperator` → `baronllm:q6_k` (imported from `hf.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF`); alt: `xploiter/the-xploiter`
- `blueteamdefender` → `lily-cybersecurity:7b-q4_k_m` (imported from `hf.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF`); alt: `huihui_ai/baronllm-abliterated`
- `pentester` → `lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0`
- `splunksplgineer` → `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit`

### Data / Research
- `dataanalyst` → `deepseek-r1:32b-q4_k_m`; alt: `huihui_ai/tongyi-deepresearch-abliterated`
- `datascientist` → `deepseek-r1:32b-q4_k_m`; alt: `huihui_ai/tongyi-deepresearch-abliterated`
- `machinelearningengineer` → `deepseek-r1:32b-q4_k_m`; alt: `huihui_ai/tongyi-deepresearch-abliterated`
- `statistician` → `deepseek-r1:32b-q4_k_m`; alt: `huihui_ai/tongyi-deepresearch-abliterated`
- `itarchitect` → `deepseek-r1:32b-q4_k_m`; alt: `huihui_ai/tongyi-deepresearch-abliterated`
- `researchanalyst` → `deepseek-r1:32b-q4_k_m`; alt: `huihui_ai/tongyi-deepresearch-abliterated`
- `gemmaresearchanalyst` → `mlx-community/gemma-4-31b-it-4bit` (Google Gemma 4, vision-capable)

### Compliance
- `nerccipcomplianceanalyst` → `Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit`
- `cippolicywriter` → `Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit`

### Reasoning
- `magistralstrategist` → `lmstudio-community/Magistral-Small-2509-MLX-8bit` (Mistral reasoning)

### Systems
- `linuxterminal` → `qwen3-coder-next:30b-q5`
- `sqlterminal` → `qwen3-coder-next:30b-q5`

### General / Writing
- `itexpert` → `dolphin-llama3:8b`
- `techreviewer` → `dolphin-llama3:8b`
- `techwriter` → `dolphin-llama3:8b`
- `creativewriter` → `dolphin-llama3:8b`
- `excelsheet` → `deepseek-r1:32b-q4_k_m`; alt: `huihui_ai/tongyi-deepresearch-abliterated`

---

## Workspace Routing

These are the routing workspace IDs exposed by the Pipeline. Every key here must exist in both `router_pipe.py WORKSPACES` and `config/backends.yaml workspace_routing`.

| Workspace ID | Preferred Backend Group | Default Model |
|---|---|---|
| `auto` | general | dolphin-llama3:8b |
| `auto-coding` | mlx → coding → general | mlx-community/Qwen3-Coder-Next-4bit |
| `auto-security` | security → general | baronllm:q6_k |
| `auto-redteam` | security → general | baronllm:q6_k |
| `auto-blueteam` | security → general | lily-cybersecurity:7b-q4_k_m |
| `auto-creative` | mlx → creative → general | mlx-community/Dolphin3.0-Llama3.1-8B-8bit |
| `auto-reasoning` | mlx → reasoning → general | Jackrong/MLX-Qwopus3.5-27B-v3-8bit |
| `auto-documents` | coding → general | mlx-community/phi-4-8bit |
| `auto-video` | general | dolphin-llama3:8b |
| `auto-music` | general | dolphin-llama3:8b |
| `auto-research` | mlx → reasoning → general | mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit |
| `auto-vision` | mlx → vision → general | mlx-community/gemma-4-31b-it-4bit |
| `auto-data` | mlx → reasoning → general | mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit |
| `auto-compliance` | mlx → reasoning → general | Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit |
| `auto-spl` | mlx → coding → general | mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit |
| `auto-mistral` | mlx → reasoning → general | lmstudio-community/Magistral-Small-2509-MLX-8bit |

### Auto-Routing (Content-Aware Intent Detection)

When a user selects the `auto` workspace, the Pipeline automatically routes to the best specialist workspace based on message content. This is a two-layer system:

**Layer 1: LLM-Based Intent Router** — Uses `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` as a fast semantic classifier (~100ms). Abliterated (surgical refusal removal) so red-team/security queries are never refused by the router. Configured in `router_pipe.py` via env vars:
- `LLM_ROUTER_ENABLED=true` (default)
- `LLM_ROUTER_CONFIDENCE_THRESHOLD=0.5`
- `LLM_ROUTER_TIMEOUT_MS=500`
- JSON schema enforced via Ollama grammar decoding (guaranteed parseable output)
- Falls back to Layer 2 on low confidence or timeout

**Layer 2: Weighted Keyword Scoring** — Deterministic, zero-latency. Each workspace defines weighted keywords (1=weak, 2=medium, 3=strong) and an activation threshold. The workspace with the highest score above its threshold wins. Tuned so a single strong signal or a combination of medium signals triggers routing.

Workspace descriptions for the LLM router are loaded from `config/routing_descriptions.json` and few-shot examples from `config/routing_examples.json`.

### vision Text-Only Fallback

When `auto-vision` is selected but no `image_url` content parts are present in the messages, the Pipeline automatically reroutes to `auto-reasoning` with a vision-domain system context injected. This prevents empty responses from vision-language models when given text-only queries.

---

## What `./launch.sh up` Does

```
1. Copy .env.example → .env (if .env doesn't exist)
2. Source .env
3. Auto-start native services (Ollama, ComfyUI, MLX proxy)
4. docker compose up -d (from deploy/portal-5/)
   ├── ollama starts, healthchecked on /api/tags
   ├── ollama-init pulls DEFAULT_MODEL (skips if already present)
   ├── portal-pipeline builds + starts (depends on ollama healthy)
   ├── open-webui starts (depends on portal-pipeline healthy)
   ├── openwebui-init runs once:
   │   ├── Creates admin account (admin@portal.local / from .env)
   │   ├── Registers all MCP Tool Servers
   │   ├── Creates all workspace model presets
   │   └── Creates persona model presets from config/personas/
   ├── mcp-documents starts (:8913)
   ├── mcp-comfyui starts (:8910)
   ├── mcp-video starts (:8911)
   ├── mcp-tts starts (:8916)
   ├── mcp-whisper starts (:8915)
   ├── mcp-sandbox starts (:8914)
   └── [ComfyUI: run separately, see docs/COMFYUI_SETUP.md]
   └── [Music MCP: runs natively on host — ./launch.sh install-music first]
5. Print access URLs
```

**First run time**: 5-15 min depending on model size and internet speed.  
**Subsequent runs**: ~30 seconds.

---

## ComfyUI Setup (Image/Video Generation)

ComfyUI runs **outside Docker** on the host (Mac bare-metal for MPS, or with GPU passthrough for CUDA). This is intentional — GPU access from Docker is complex and ComfyUI already handles its own model management.
**Linux with NVIDIA GPU:** use `./launch.sh up --profile docker-comfyui` instead (ComfyUI runs in Docker with CUDA passthrough).

**Mac (MPS):**
```bash
git clone https://github.com/comfyanonymous/ComfyUI
cd ComfyUI
pip install -r requirements.txt
python main.py --listen 0.0.0.0 --port 8188
```

**Required model downloads** (place in ComfyUI's `models/checkpoints/`):
- FLUX.1-schnell: `huggingface-cli download black-forest-labs/FLUX.1-schnell --local-dir models/checkpoints`
- SDXL: `huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0 --local-dir models/checkpoints`
- Wan2.2 (video): `huggingface-cli download Wan-AI/Wan2.2-T2V-5B --local-dir models/checkpoints`

Open WebUI points to ComfyUI at `http://host.docker.internal:8188` by default.

---

## Speech Pipeline (MLX-native, Apple Silicon)

Portal 5 v6.1+ uses `mlx-audio` for speech on Apple Silicon, replacing the Docker-based `kokoro-onnx` + `faster-whisper` services.

**Architecture**: Open WebUI → `scripts/mlx-speech.py` (host:8918) → mlx-audio → MLX (Metal GPU)

| Feature | Old (Docker) | New (MLX-native) |
|---|---|---|
| TTS engine | kokoro-onnx (82M, ONNX) | Kokoro (82M, MLX) + Qwen3-TTS (1.7B, MLX) |
| Voice cloning | fish-speech (manual install) | Qwen3-TTS Base (3s reference audio, zero setup) |
| Voice design | Not available | Qwen3-TTS VoiceDesign (describe a voice in text) |
| Emotion control | Not available | Qwen3-TTS CustomVoice (style instructions) |
| Languages | English only (kokoro) | 10 languages (Qwen3-TTS) + EN/JP/ZH (Kokoro) |
| ASR engine | faster-whisper (CPU, Docker) | Qwen3-ASR (MLX Metal, host-native) |
| Streaming | No | Yes (Qwen3-TTS streaming generation) |

**Startup**: `./launch.sh start-speech` (or automatically via `./launch.sh up` on Apple Silicon)

**Voice routing** (automatic based on voice name):
- `af_heart`, `bm_george`, etc. → Kokoro (fast, backward-compatible)
- `Chelsie`, `Ryan`, `Vivian`, etc. → Qwen3-TTS CustomVoice (style-controllable)
- `design:A warm female British voice` → Qwen3-TTS VoiceDesign (creates voice from description)
- `clone:/path/to/reference.wav` → Qwen3-TTS Base (voice cloning)

**Memory**: Models load lazily. Kokoro: ~0.2GB. Each Qwen3-TTS variant: ~0.8GB (8-bit). Qwen3-ASR: ~0.8GB. Only the requested model is loaded.

**Fallback**: Docker `mcp-tts` (:8916) and `mcp-whisper` (:8915) still run. Set `MLX_SPEECH_URL=http://mcp-tts:8916` in `.env` to bypass the MLX speech server.

---

## Notification System

The pipeline includes an operational alerting and daily summary system. It is **opt-in** — disabled by default via `NOTIFICATIONS_ENABLED=false`.

### Features
- **Backend health alerts**: Fires when a backend crosses a consecutive failure threshold (`ALERT_BACKEND_DOWN_THRESHOLD`, default 3)
- **All-backends-down alert**: Fires immediately when no healthy backends remain
- **Backend recovery alert**: Fires when a previously-down backend recovers
- **Daily usage summary**: Scheduled report (configurable hour/timezone) with request counts, token totals, TPS averages, per-model breakdown, and persona usage

### Configuration (env vars)

| Variable | Purpose | Default |
|---|---|---|
| `NOTIFICATIONS_ENABLED` | Master switch | `false` |
| `SLACK_ALERT_WEBHOOK_URL` | Slack Incoming Webhook URL | (empty) |
| `TELEGRAM_ALERT_BOT_TOKEN` | Dedicated alert bot token | (empty) |
| `TELEGRAM_ALERT_CHANNEL_ID` | Target channel/group ID | (empty) |
| `SMTP_HOST` | Email SMTP server | (empty) |
| `PUSHOVER_API_TOKEN` | Pushover application token | (empty) |
| `PUSHOVER_USER_KEY` | Pushover user key | (empty) |
| `WEBHOOK_URL` | Generic webhook POST endpoint | (empty) |
| `ALERT_BACKEND_DOWN_THRESHOLD` | Consecutive failures before alert | `3` |
| `ALERT_NO_HEALTHY_BACKENDS` | Alert when all backends fail | `true` |
| `ALERT_SUMMARY_ENABLED` | Enable daily summary | `true` |
| `ALERT_SUMMARY_HOUR` | Summary hour (0-23) | `8` |
| `ALERT_SUMMARY_TIMEZONE` | Summary timezone | `America/Chicago` |

Each channel is independently optional — configure only the ones you want. All channels share the pipeline's HTTP connection pool.

Test notifications: `curl -X POST http://localhost:9099/notifications/test -H "Authorization: Bearer $PIPELINE_API_KEY"`

### Architecture

```
router_pipe.py  →  NotificationDispatcher  →  SlackChannel
               →  NotificationScheduler     →  TelegramChannel
                                              →  EmailChannel
                                              →  PushoverChannel
                                              →  WebhookChannel
```

Events are dispatched asynchronously. The scheduler runs as a background task inside the pipeline process, reading metrics from the pipeline's in-memory counters.

---

## Testing Rules

- All tests in `tests/unit/` must pass with no network access (`pytest tests/unit/`)
- No test may call a real Ollama, real Open WebUI, or real Docker
- Use `tmp_path` fixtures for file I/O
- Mock `httpx.AsyncClient` for all HTTP calls
- Run before every commit: `pytest tests/ -v --tb=short && ruff check . && ruff format --check .`

---

## Adding New Capabilities

### New MCP Tool Server
1. Create `portal_mcp/<category>/<name>_mcp.py`
2. Add service to `deploy/portal-5/docker-compose.yml` on an unused port
3. Add tool JSON to `imports/openwebui/tools/portal_<name>.json`
4. Add to `imports/openwebui/mcp-servers.json`
5. `openwebui_init.py` picks up new tool servers automatically from `mcp-servers.json`

### New Persona
1. Create `config/personas/<slug>.yaml` with: `name`, `slug`, `system_prompt`, `workspace_model`, `category`
2. `openwebui_init.py` creates the Open WebUI model preset on next seed
3. No other changes needed

### New Workspace Routing Tier
1. Add to `WORKSPACES` in `portal_pipeline/router_pipe.py`
2. Add same key to `workspace_routing` in `config/backends.yaml`
3. Add workspace JSON to `imports/openwebui/workspaces/`
4. Run workspace consistency check (see Rule 6 above)

### New Cluster Node
1. Edit `config/backends.yaml` — add backend entry, assign to group
2. `docker compose restart portal-pipeline`
3. Done. No code changes.

---

## Zero-Setup Requirements

Every feature must work from `./launch.sh up` without manual steps.

| Feature | How it achieves zero-setup |
|---|---|
| Image generation | ComfyUI runs natively on host (MPS/CUDA); models auto-downloaded. Optional Docker profile: `./launch.sh up --profile docker-comfyui` |
| Music generation | MusicGen via `transformers`, runs natively (host) for MPS; `./launch.sh install-music` |
| Voice TTS | kokoro-onnx in Dockerfile.mcp; models auto-downloaded on first call |
| Voice cloning | fish-speech is OPTIONAL; degrade gracefully with helpful message |
| Web search | SearXNG in Docker; configured automatically via Open WebUI env vars |
| RAG | Open WebUI native; embedding model pulled by ollama-init |
| Memory | Open WebUI native; enabled via env var |
| Metrics | Prometheus + Grafana in Docker; start with ./launch.sh up |

### Adding a New Feature

If a new feature requires a new dependency:
1. It MUST be installable via pip or apt-get in the relevant Dockerfile
2. OR it MUST be a Docker service in docker-compose.yml
3. It MUST NOT require any manual user steps
4. If a dependency may fail (e.g., GPU-only, large download) — handle it with a
   graceful degradation + helpful error message, not a crash

### Model Downloads

Models that are downloaded on first use (auto, via HuggingFace):
- nomic-embed-text (RAG embeddings) — pulled by ollama-init
- FLUX.1-schnell (images) — pulled by comfyui-model-init
- faster-whisper base (transcription) — downloaded on first use
- kokoro-onnx voices (~200MB) — downloaded on first call
- MusicGen (via transformers) — downloaded on first call, cached in `~/.portal5/music/hf_cache`

Models that require `./launch.sh pull-models` (large, optional):
- All specialized LLM models (security, coding, reasoning, vision)

---

## Do Not

- Do NOT add `OLLAMA_BASE_URL` directly to Open WebUI's env — everything must go through `portal-pipeline`
- Do NOT import `portal_pipeline` from `portal_mcp` or vice versa — they are independent
- Do NOT store conversation state in the Pipeline — Open WebUI owns that
- Do NOT add system Python packages to `Dockerfile.pipeline` — keep it lean
- Do NOT hardcode model names in Python — they come from `backends.yaml` or persona YAMLs
- Do NOT use `docker compose down -v` in scripts (nukes Ollama models) — use targeted volume removal
- Do NOT commit `.env` — it is in `.gitignore`
- Do NOT skip tests — they protect the routing logic that everything depends on

---

## Git Workflow

**All work is done directly on `main` during stabilization. Do not create feature branches unless explicitly instructed.**

- **Commit directly to `main`** — no branches, no PRs, until v5.0 stable tag
- Run tests before every push: `pytest tests/ -q --tb=no`
- Commit format: `type(scope): description`

### Never
- Never force push
- Never commit .env
- Never commit pyproject.toml changes that add cloud/external deps
- Never modify Open WebUI source code

## Known Limitations

Before adding new tasks or filing issues, check `KNOWN_ISSUES.md` — some items are documented known limitations rather than bugs to fix. AI agents should read this file before proposing new work.

---

## MCP Dev Tooling (Claude Code / opencode)

The `.mcp.json` at the repo root provisions four MCP servers automatically when Claude Code or
opencode opens this project. These are **development tools only** — they have no relation to
the Portal 5 MCP Tool Servers in `portal_mcp/` that Open WebUI consumes.

### Servers

| Server | Install | Purpose |
|---|---|---|
| `filesystem` | `@modelcontextprotocol/server-filesystem` (npx) | Read/write repo source tree and `~/.portal5/logs` without shell |
| `fetch` | `mcp-fetch` (uvx) | Fetch Prometheus metrics API, Open WebUI API, Grafana API, docs |
| `git` | `mcp-git` (uvx) | Walk commit history, diff, blame — critical for regression bisect |
| `docker` | `@modelcontextprotocol/server-docker` (npx) | Container logs, status, exec — debug MCP server health live |

> **sqlite server omitted**: Open WebUI's `webui.db` lives in a pure Docker volume
> (`portal-5_open-webui-data`) not bind-mounted to the host. To re-enable sqlite MCP,
> add a bind mount in `docker-compose.yml` and add the entry back to `.mcp.json`.

### Prerequisites

These servers use `npx` and `uvx` — both must be available on PATH:

```bash
# npx ships with Node.js (>=18 recommended)
node --version && npx --version

# uvx ships with uv
uv --version && uvx --version
```

If either is missing:
- Node.js: `brew install node` (Mac) or `apt install nodejs npm` (Linux)
- uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Prometheus Fetch Pattern

The `fetch` MCP server can query Prometheus directly. Useful patterns:

```
# Current pipeline request rate
http://localhost:9090/api/v1/query?query=portal5_requests_total

# MCP server health over last 5 minutes
http://localhost:9090/api/v1/query_range?query=up{job="portal5"}&start=[5m ago]&end=now&step=30s

# Grafana dashboard (read-only API)
http://localhost:3000/api/dashboards/home
```

### git MCP — Regression Bisect Pattern

For commit-range regressions (e.g., video gen bug across two commits):

1. Use `git` MCP tool: `git_log` to list commits in range
2. Use `git` MCP tool: `git_diff` between suspect commits on affected files
3. Correlate with `portal_mcp/generation/` and `portal_mcp/mcp_server/` changes
4. No terminal copy-paste required

### docker MCP — MCP Server Debug Pattern

When an acceptance test fails against a portal MCP server:

1. `docker_list` — confirm `portal5-mcp-<name>` container is running
2. `docker_logs` — tail last 50 lines for startup errors or import failures
3. `docker_exec` — run `curl http://localhost:<port>/health` inside container if needed
4. Avoids blind `docker logs` copy-paste cycles during test iteration

### Scope Boundaries

- `filesystem` MCP is scoped to the repo dirs and `~/.portal5/logs` only. It cannot reach outside
  these paths — by design. Do not widen the scope.
- `docker` MCP uses the Docker socket. On a single-user local machine this is acceptable.
  Do not add this to any multi-user or production deployment.
- Do not use `fetch` MCP to POST to the Open WebUI admin API — read-only observation only.
