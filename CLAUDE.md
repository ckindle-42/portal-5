# CLAUDE.md — Claude Code Guidelines for Portal 5

**Project**: Portal 5 — Open WebUI Intelligence Layer  
**Repository**: https://github.com/ckindle-42/portal-5  
**Version**: 6.0.3

---

## What Portal 5 Is

Portal 5 is an **Open WebUI enhancement layer** — not a replacement web stack. It extends Open WebUI through its Pipeline server (:9099) and MCP Tool Servers. Result: local AI platform for text, code, security, images, video, music, documents, voice — all on your hardware, one interface.

**Architecture**: Open WebUI → Portal Pipeline (:9099) → [MLX proxy (:8081) + Ollama (:11434)] → local models. MCP servers (:8910–8916) provide tools (documents, code sandbox, TTS, etc.).

**Inference**: Two tiers on Apple Silicon — **Tier 1 MLX proxy** (safetensor models, faster ~20-30% for <14B) and **Tier 2 Ollama** (GGUF models, simpler management). Both host-native, not Docker.

**Core values**: Privacy-first, fully local, zero cloud dependencies, launch in one command.

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
│   ├── generation/               # Music (:8912 host-native), TTS (:8916), Video (:8911), Whisper (:8915), ComfyUI (:8910)
│   ├── execution/                # Code sandbox (:8914)
│   ├── security/                 # Vulnerability classification (:8919)
│   ├── core/                     # Shared MCP utilities
│   └── mcp_server/               # Vendored FastMCP implementation
├── config/
│   ├── backends.yaml             # OPERATOR EDITS THIS — adds cluster nodes here, no code changes
│   ├── personas/                 # 57 persona YAML files → Open WebUI model presets
│   ├── routing_descriptions.json # LLM router workspace descriptions
│   └── routing_examples.json     # LLM router few-shot examples
├── deploy/portal-5/
│   └── docker-compose.yml        # THE launch definition — all services
├── scripts/
│   ├── openwebui_init.py         # Auto-seeds Open WebUI on first fresh volume
│   ├── mlx-proxy.py              # MLX dual-server proxy (auto-switches mlx_lm ↔ mlx_vlm, admission control)
│   ├── mlx-speech.py             # Host-native MLX speech server (TTS + ASR, port :8918)
│   ├── mlx-watchdog.py           # MLX component health monitor with auto-recovery
│   ├── mlx-switch-benchmark.py   # MLX model switch timing benchmark
│   ├── embedding-server.py       # Host-native ARM64 embedding server (fallback)
│   ├── pipeline-entrypoint.sh    # Docker entrypoint for portal-pipeline
│   └── ...                       # See scripts/ for full list
├── tests/
│   ├── unit/                     # pytest unit tests — no Docker required
│   └── benchmarks/               # Inference tier benchmarks (mlx_lm/mlx_vlm vs Ollama MLX)
├── Dockerfile.pipeline           # Lean image for portal-pipeline service
├── Dockerfile.mcp                # Image for all portal_mcp services
├── launch.sh                     # Single entry point (30+ commands)
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

### 4 — The Pipeline Is Stateless (with metrics persistence)

`portal_pipeline/router_pipe.py` is stateless for conversation routing — no database, no session state, no memory. Conversation history lives in Open WebUI's database. Cross-session memory uses Open WebUI's native memory feature.

The pipeline does persist operational metrics (request counts, TPS, errors) to `/app/data/metrics_state.json` for telemetry only — it does not affect routing decisions.

### 5 — Personas Live in config/personas/

Each `.yaml` in `config/personas/` becomes an Open WebUI model preset during seeding. The YAML defines: `name`, `slug`, `system_prompt`, `workspace_model`, `category`. The `openwebui_init.py` script reads these and creates model presets in Open WebUI. Adding a new persona = adding one YAML file. See `config/personas/` for the full catalog (57 personas).

### 6 — Workspace Routing Must Stay Consistent

Workspace routing is defined in `config/backends.yaml` `workspace_routing` block and the `WORKSPACES` dict in `router_pipe.py`. They must define **identical keys**. The `openwebui_init.py` seeding must create a model preset for each key. After any change, run:
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

Auto-routing uses two layers: **Layer 1** — LLM-based intent classifier (`Llama-3.2-3B-Instruct-abliterated-GGUF`, ~100ms, grammar-enforced JSON). **Layer 2** — weighted keyword scoring (fallback on low confidence or timeout). Vision text-only fallback: `auto-vision` with no image parts reroutes to `auto-reasoning`.

### 7 — All Ports Are Reserved

| Port | Service |
|---|---|
| 8080 | Open WebUI |
| 9099 | Portal Pipeline |
| 8081 | MLX proxy (auto-switches mlx_lm ↔ mlx_vlm) |
| 18081 | mlx_lm server (text-only, managed by proxy) |
| 18082 | mlx_vlm server (VLM, managed by proxy) |
| 8910-8916 | MCP: ComfyUI, Video, Music, Documents, Sandbox, Whisper, TTS |
| 8917 | Embedding (Harrier-0.6B TEI) |
| 8188 | ComfyUI |
| 8088 | SearXNG |
| 11434 | Ollama |
| 9090 | Prometheus |
| 3000 | Grafana |

Port assignments are enforced in `.env.example`. Do not reassign without updating both.

### 8 — Two Inference Tiers: MLX Proxy and Ollama

Portal 5 runs two inference backends concurrently on the host. Each model belongs to exactly one tier.

**Tier 1 — MLX proxy** (`scripts/mlx-proxy.py`, ports 8081 / 18081 / 18082)
- Safetensor/MLX format models, downloaded via `huggingface-cli download`
- Served by `mlx_lm.server` (text) or `mlx_vlm.server` (vision + audio)
- Use when: no GGUF available, needs mlx_vlm audio, or model >20GB (admission control)

**Tier 2 — Ollama** (port 11434, Ollama 0.20.5+ MLX backend)
- GGUF format models, pulled via `ollama pull` or `hf.co/`
- Registered in `config/backends.yaml` under ollama backend groups
- Use when: stable GGUF exists, no audio input needed, simpler management preferred

Never add `transformers` or `torch` to `portal_pipeline/` — it runs lean.
Full model catalog with memory budgets is in `config/backends.yaml`.

### 9 — The Dockerfile Split Is Intentional

- `Dockerfile.pipeline` — minimal: fastapi, uvicorn, httpx, pyyaml only. Fast build, lean image.
- `Dockerfile.mcp` — heavier: adds python-docx, python-pptx, openpyxl, fastmcp, etc.

Do not merge them. The pipeline container must stay small for fast restarts.

### 10 — Git Discipline

Commit directly to `main` during stabilization. Run tests before every push: `pytest tests/ -q --tb=no`. Commit format: `type(scope): description`. Never force push. Never commit `.env` or cloud/external deps to `pyproject.toml`.

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

Every feature must work from `./launch.sh up` without manual steps. Dependencies must be installable via pip/apt-get in the Dockerfile OR a Docker service. If a dependency may fail, degrade gracefully — never crash.

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

## Known Limitations

Before adding new tasks or filing issues, check `KNOWN_ISSUES.md` — some items are documented known limitations rather than bugs to fix. AI agents should read this file before proposing new work.

---

## Reference Docs

| Topic | Location |
|---|---|
| Model catalog + memory budgets | `config/backends.yaml` (annotated YAML comments) |
| Persona catalog (57 personas) | `config/personas/*.yaml` |
| Notification system setup | `docs/ALERTS.md` |
| ComfyUI image/video setup | `docs/COMFYUI_SETUP.md` |
| Speech pipeline (MLX-native TTS) | `docs/FISH_SPEECH_SETUP.md` |
| IDE MCP tooling (filesystem, fetch, git, docker) | `docs/MCP_DEV_TOOLING.md` |
| Cluster scaling | `docs/CLUSTER_SCALE.md` |
| Admin guide | `docs/ADMIN_GUIDE.md` |
