# CLAUDE.md — Claude Code Guidelines for Portal 5

**Project**: Portal 5 — Open WebUI Intelligence Layer  
**Repository**: https://github.com/ckindle-42/portal-5  
**Version**: 5.0.0  
**Last Updated**: March 3, 2026

---

## What Portal 5 Is

Portal 5 is an **Open WebUI enhancement layer** — not a replacement web stack. It extends Open WebUI through its native extension points (Pipeline server, MCP Tool Servers) rather than duplicating what Open WebUI already does. The result is a complete local AI platform covering text, code, security, images, video, music, documents, and voice — all running on local hardware, all accessible through a single Open WebUI interface.

**This project has two roles:**
1. **Personal local AI** — single M4 Mac or Linux node, launch and use today
2. **Foundation node** for the Mac Studio cluster growth path (Stage 1→5, Track B Apple Silicon)

**Hardware targets**: Apple M4 Mac (primary), NVIDIA CUDA Linux (secondary), any Docker host  
**Architecture**: Open WebUI ← Portal Pipeline (:9099) ← Ollama/vLLM ← local models  
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
├── portal_pipeline/          # FastAPI Pipeline server (:9099)
│   ├── cluster_backends.py   # BackendRegistry — Ollama + vLLM, health-aware
│   └── router_pipe.py        # /v1/models + /v1/chat/completions routing
├── portal_mcp/               # MCP Tool Servers (registered in Open WebUI)
│   ├── documents/            # Word, PowerPoint, Excel generation (:8913)
│   ├── generation/           # Music (:8912), TTS (:8916), Video (:8911), Whisper (:8915), ComfyUI (:8910)
│   └── execution/            # Code sandbox (:8914)
├── portal_channels/          # Optional push interfaces
│   ├── telegram/bot.py       # Telegram → Pipeline adapter
│   └── slack/bot.py          # Slack → Pipeline adapter
├── config/
│   ├── backends.yaml         # OPERATOR EDITS THIS — adds cluster nodes here, no code changes
│   └── personas/             # Persona YAML files → Open WebUI model presets
├── deploy/portal-5/
│   └── docker-compose.yml    # THE launch definition — all services
├── scripts/
│   └── openwebui_init.py     # Auto-seeds Open WebUI on first fresh volume
├── imports/openwebui/        # Pre-built JSON files for Open WebUI GUI import
│   ├── tools/                # MCP Tool Server registration JSONs
│   ├── workspaces/           # Workspace preset JSONs
│   └── functions/            # Open WebUI Function (pipe) JSONs
├── tests/
│   └── unit/                 # pytest unit tests — no Docker required
├── Dockerfile.pipeline       # Lean image for portal-pipeline service
├── Dockerfile.mcp            # Image for all portal_mcp services
├── launch.sh                 # Single entry point: up/down/clean/seed/status/logs
└── .env.example              # All configurable values with defaults
```

---

## Tech Stack & Tooling

| Tool | Command | Notes |
|---|---|---|
| **Package manager** | `uv` | NOT pip directly. Lock file: `uv.lock` |
| **Install** | `uv pip install -e ".[dev]"` | Installs all extras + dev deps |
| **Linter** | `ruff check . --fix` | Ruff handles lint AND format |
| **Formatter** | `ruff format .` | NOT Black |
| **Type check** | `mypy portal_pipeline/ portal_mcp/` | strict=false currently |
| **Tests** | `pytest tests/ -v --tb=short` | Must pass before any commit |
| **Python** | 3.11+ required | |
| **Framework** | FastAPI + Pydantic v2 | Async throughout |
| **Launch** | `./launch.sh up` | Never `docker compose up` directly |

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

### 4 — The Pipeline Is Stateless

`portal_pipeline/router_pipe.py` is stateless. It reads `backends.yaml`, routes requests, streams responses. No database, no session state, no memory. Conversation history lives in Open WebUI's database. Cross-session memory uses Open WebUI's native memory feature.

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
| 8910 | MCP: ComfyUI |
| 8911 | MCP: Video |
| 8912 | MCP: Music |
| 8913 | MCP: Documents |
| 8914 | MCP: Code Sandbox |
| 8915 | MCP: Whisper |
| 8916 | MCP: TTS |
| 8188 | ComfyUI |
| 11434 | Ollama |

Do not reassign these. Do not add new services on overlapping ports without updating this table.

### 8 — Models Pull From Ollama, Not HuggingFace Directly

All text models run through Ollama. HuggingFace is only used for:
- ComfyUI image/video model weights (downloaded into ComfyUI's `models/` directory)
- Music generation models (downloaded by AudioCraft on first use)
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

These are the Ollama models Portal 5 is designed around. All pulled via `ollama pull`. The `DEFAULT_MODEL` in `.env` is pulled automatically on `./launch.sh up`. Others are pulled on demand or via `./launch.sh pull-models`.

### Text Models (Ollama)

| Model | Ollama Tag | Purpose | RAM |
|---|---|---|---|
| Dolphin Llama3 8B | `dolphin-llama3:8b` | Default, general, function calling | 8GB |
| Dolphin Llama3 70B | `dolphin-llama3:70b` | High-quality general (needs 48GB+) | 48GB |
| The-Xploiter | `xploiter/the-xploiter` | Red team / security offense | 12GB |
| WhiteRabbitNeo 8B | `lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0` | Security research | 6GB |
| BaronLLM Abliterated | `huihui_ai/baronllm-abliterated` | Uncensored general | 6GB |
| Tongyi DeepResearch 30B | `huihui_ai/tongyi-deepresearch-abliterated:30b` | Reasoning, research, analysis | 22GB |
| Qwen3 Coder 30B | `qwen3-coder-next:30b-q5` | Code generation, review | 24GB |
| Devstral 24B | `devstral:24b` | Code, agentic development | 20GB |
| DeepSeek Coder 16B | `deepseek-coder:16b-instruct-q4_K_M` | Code, math | 16GB |
| Qwen3 Omni 30B | `qwen3-omni:30b` | Multimodal, vision, audio | 30GB |
| LLaVA 7B | `llava:7b` | Vision / image understanding | 8GB |
| Llama 3.2 3B | `llama3.2:3b-instruct-q4_K_M` | Fast routing classifier | 3GB |

### Generation Models (ComfyUI / HuggingFace)

| Model | Source | Purpose |
|---|---|---|
| FLUX.1-schnell | `black-forest-labs/FLUX.1-schnell` | Fast image generation |
| FLUX.1-dev | `black-forest-labs/FLUX.1-dev` | High-quality image generation |
| SDXL Base 1.0 | `stabilityai/stable-diffusion-xl-base-1.0` | Image generation alternative |
| Wan2.2 T2V 5B | `Wan-AI/Wan2.2-T2V-5B` | Text-to-video generation |
| MusicGen Small/Medium/Large | HuggingFace (auto via AudioCraft) | Music generation |
| Fish Speech | GitHub (fish-speech repo) | Text-to-speech |
| Faster-Whisper | HuggingFace (auto via faster-whisper) | Speech-to-text |

---

## Persona Catalog

Personas live in `config/personas/*.yaml`. Each becomes a model preset in Open WebUI.

### Development
- `bugdiscoverycodeassistant` → `qwen3-coder-next:30b-q5`
- `codebasewikidocumentation` → `qwen3-coder-next:30b-q5`
- `codereviewassistant` → `qwen3-coder-next:30b-q5`
- `codereviewer` → `qwen3-coder-next:30b-q5`
- `devopsautomator` → `qwen3-coder-next:30b-q5`
- `devopsengineer` → `qwen3-coder-next:30b-q5`
- `ethereumdeveloper` → `qwen3-coder-next:30b-q5`
- `fullstacksoftwaredeveloper` → `qwen3-coder-next:30b-q5`
- `githubexpert` → `qwen3-coder-next:30b-q5`
- `javascriptconsole` → `qwen3-coder-next:30b-q5`
- `kubernetesdockerlearning` → `qwen3-coder-next:30b-q5`
- `pythoncodegenerator` → `qwen3-coder-next:30b-q5`
- `pythoninterpreter` → `qwen3-coder-next:30b-q5`
- `seniorfrontenddeveloper` → `qwen3-coder-next:30b-q5`
- `seniorsoftwareengineer` → `qwen3-coder-next:30b-q5`
- `softwareqatester` → `qwen3-coder-next:30b-q5`
- `ux-uideveloper` → `qwen3-coder-next:30b-q5`

### Security
- `cybersecurityspecialist` → `xploiter/the-xploiter`
- `networkengineer` → `xploiter/the-xploiter`
- `redteamoperator` → `xploiter/the-xploiter`
- `blueteamdefender` → `huihui_ai/baronllm-abliterated`
- `pentester` → `lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0`

### Data / Research
- `dataanalyst` → `huihui_ai/tongyi-deepresearch-abliterated:30b`
- `datascientist` → `huihui_ai/tongyi-deepresearch-abliterated:30b`
- `machinelearningengineer` → `huihui_ai/tongyi-deepresearch-abliterated:30b`
- `statistician` → `huihui_ai/tongyi-deepresearch-abliterated:30b`
- `itarchitect` → `huihui_ai/tongyi-deepresearch-abliterated:30b`
- `researchanalyst` → `huihui_ai/tongyi-deepresearch-abliterated:30b`

### Systems
- `linuxterminal` → `qwen3-coder-next:30b-q5`
- `sqlterminal` → `qwen3-coder-next:30b-q5`

### General / Writing
- `itexpert` → `dolphin-llama3:8b`
- `techreviewer` → `dolphin-llama3:8b`
- `techwriter` → `dolphin-llama3:8b`
- `creativewriter` → `dolphin-llama3:8b`
- `excelsheet` → `huihui_ai/tongyi-deepresearch-abliterated:30b`

---

## Workspace Routing

These are the routing workspace IDs exposed by the Pipeline. Every key here must exist in both `router_pipe.py WORKSPACES` and `config/backends.yaml workspace_routing`.

| Workspace ID | Preferred Backend Group | Default Model |
|---|---|---|
| `auto` | general | dolphin-llama3:8b |
| `auto-coding` | coding → general | qwen3-coder-next:30b-q5 |
| `auto-security` | security → general | xploiter/the-xploiter |
| `auto-redteam` | security → general | xploiter/the-xploiter |
| `auto-blueteam` | security → general | huihui_ai/baronllm-abliterated |
| `auto-creative` | creative → general | dolphin-llama3:8b |
| `auto-reasoning` | reasoning → general | huihui_ai/tongyi-deepresearch-abliterated:30b |
| `auto-documents` | general | dolphin-llama3:8b |
| `auto-video` | general | dolphin-llama3:8b |
| `auto-music` | general | dolphin-llama3:8b |
| `auto-research` | reasoning → general | huihui_ai/tongyi-deepresearch-abliterated:30b |
| `auto-vision` | vision → general | qwen3-omni:30b |
| `auto-data` | reasoning → general | huihui_ai/tongyi-deepresearch-abliterated:30b |

---

## What `./launch.sh up` Does

```
1. Copy .env.example → .env (if .env doesn't exist)
2. Source .env
3. docker compose up -d (from deploy/portal-5/)
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
   ├── mcp-music starts (:8912)
   ├── mcp-tts starts (:8916)
   ├── mcp-sandbox starts (:8914)
   └── [ComfyUI: run separately, see docs/COMFYUI_SETUP.md]
4. Print access URLs
```

**First run time**: 5-15 min depending on model size and internet speed.  
**Subsequent runs**: ~30 seconds.

---

## ComfyUI Setup (Image/Video Generation)

ComfyUI runs **outside Docker** on the host (Mac bare-metal for MPS, or with GPU passthrough for CUDA). This is intentional — GPU access from Docker is complex and ComfyUI already handles its own model management.

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

### During Stabilization (now)
- **Work in main only** — no branches until v5.0 stable tag
- Every commit directly to main via push
- Run tests before every push: `pytest tests/ -q --tb=no`
- Commit format: `type(scope): description`

### After v5.0 Tagged
- main = stable releases only (PRs from dev)
- dev = active work (default branch)
- feature/* = individual features (PRs to dev)

### Never
- Never force push
- Never commit .env
- Never commit pyproject.toml changes that add cloud/external deps
- Never modify Open WebUI source code
