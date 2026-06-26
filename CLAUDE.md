# CLAUDE.md — Claude Code Guidelines for Portal 5

**Project**: Portal 5 — Open WebUI Intelligence Layer  
**Repository**: https://github.com/ckindle-42/portal-5  
**Version**: 7.6.0

---

## What Portal 5 Is

Portal 5 is an **Open WebUI enhancement layer** — not a replacement web stack. It extends Open WebUI through its Pipeline server (:9099) and MCP Tool Servers. Result: local AI platform for text, code, security, images, video, music, documents, voice — all on your hardware, one interface.

**Architecture**: Open WebUI → Portal Pipeline (:9099) → Ollama (:11434) → local models. MCP servers (:8910–8928) provide tools (documents, code sandbox, TTS, research, memory, RAG, browser, proxmox, pipeline introspection).

**Inference**: Single tier — **Ollama** (GGUF models, Ollama 0.30.7+ with native MLX Metal backend on Apple Silicon). The MLX inference proxy was retired in commit 3a0c58e; Ollama now matches or beats standalone mlx_lm throughput while removing the dual-stack operational overhead. Host-native, not Docker. NOTE: MLX is still used outside inference — for speech (mlx-speech :8918), diarized transcription (mlx-transcribe :8924), embeddings (:8917), and reranking (:8925). Those are audio/retrieval runtimes, not the chat inference tier.

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
│   ├── cluster_backends.py       # BackendRegistry — Ollama (+ vLLM-compatible), health-aware
│   ├── router_pipe.py            # FastAPI app, @app routes, lifespan, auth, option injection
│   ├── __main__.py               # Uvicorn entrypoint (multi-worker)
│   ├── router/                   # Decomposed pipeline modules (facade-exported by router_pipe.py)
│   │   ├── anthropic_compat.py  # /v1/messages ↔ OpenAI format bridge (Claude Code local mode)
│   │   ├── concurrency.py        # 3 semaphores + RequestSlot (single-owner lifecycle)
│   │   ├── metrics.py            # CollectorRegistry + all Prometheus collectors
│   │   ├── monitor.py            # Metal GPU memory + Ollama model state primitives
│   │   ├── power.py              # powermetrics polling, energy/cost, usage recording
│   │   ├── routing.py            # LLM router + keyword workspace detection
│   │   ├── state.py              # State persistence + per-event recorders
│   │   ├── streaming.py          # SSE streaming: _stream_from_backend_guarded, tool loop, preamble
│   │   ├── thinking.py           # Shared <think>…</think> strip + reasoning passthrough
│   │   ├── tools.py              # MCP tool dispatch (_dispatch_tool_call)
│   │   └── workspaces.py         # WORKSPACES dict, persona map, workspace tool helpers
│   ├── tool_registry.py          # Tool discovery (polls MCP /tools), advertisement, dispatch
│   └── notifications/            # Operational alerts + daily summaries
│       ├── dispatcher.py         # Event bus: fans out to all configured channels
│       ├── events.py             # AlertEvent / SummaryEvent / EventType
│       ├── scheduler.py          # APScheduler daily summary
│       └── channels/             # Slack, Telegram, Email, Pushover, Webhook
├── portal_mcp/                   # MCP Tool Servers (registered in Open WebUI)
│   ├── documents/                # Word, PowerPoint, Excel generation (:8913)
│   ├── generation/               # Music (:8912 host-native), TTS (:8916), Video (:8911), Whisper (:8915), ComfyUI (:8910), CAD render (:8926)
│   ├── execution/                # Code sandbox (:8914)
│   ├── security/                 # Vulnerability classification (:8919)
│   ├── memory/                   # Cross-session memory store (:8920)
│   ├── rag/                      # LanceDB RAG + reranker (:8921, :8925)
│   ├── research/                 # Web search + SearXNG (:8922)
│   ├── browser/                  # Playwright browser automation (:8923)
│   ├── proxmox/                  # Lab VM control via Proxmox API (:8927)
│   ├── platform/                 # Pipeline MCP — stack introspection + FastContext (:8928)
│   ├── core/                     # Shared MCP utilities (workspace helpers, path resolution)
│   └── mcp_server/               # Vendored FastMCP implementation
├── config/
│   ├── backends.yaml             # OPERATOR EDITS THIS — adds cluster nodes here, no code changes
│   ├── personas/                 # 150 persona YAML files → Open WebUI model presets
│   ├── routing_descriptions.json # LLM router workspace descriptions
│   └── routing_examples.json     # LLM router few-shot examples
├── deploy/portal-5/
│   └── docker-compose.yml        # THE launch definition — all services
├── scripts/
│   ├── openwebui_init.py         # Auto-seeds Open WebUI on first fresh volume
│   ├── mlx-speech.py             # Host-native MLX speech server (TTS + ASR, port :8918)
│   ├── embedding-server.py       # Host-native ARM64 embedding server (fallback)
│   ├── pipeline-entrypoint.sh    # Docker entrypoint for portal-pipeline
│   ├── smoke_stream.sh           # Live streaming gate (also run by ./launch.sh test)
│   └── ...                       # See scripts/ for full list
├── tests/
│   ├── unit/                     # pytest unit tests — no Docker required
│   └── benchmarks/               # Inference benchmarks (Ollama TPS, positional recall, coding shootout)
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

Each `.yaml` in `config/personas/` becomes an Open WebUI model preset during seeding. The YAML defines: `name`, `slug`, `system_prompt`, `workspace_model`, `category`. The `openwebui_init.py` script reads these and creates model presets in Open WebUI. Adding a new persona = adding one YAML file. See `config/personas/` for the full catalog (150 personas).

### 6 — config/portal.yaml Is the Single Source of Truth for Workspaces and MCP Fleet

All workspaces and the MCP tool server fleet are defined in **`config/portal.yaml`**. Do not hand-edit these derived files:
- `config/backends.yaml` → `workspace_routing` block (auto-generated)
- `.mcp.json` → IDE MCP server list (auto-generated)
- `imports/openwebui/workspaces/workspace_*.json` → OWUI workspace presets (auto-generated)

After any change to `config/portal.yaml`, regenerate all derived files:
```bash
./launch.sh sync-config
# or directly:
python3 -m portal_pipeline.sync_config
```

`sync-config` is idempotent — running it twice produces no diff. The test suite (`tests/unit/test_generated_artifacts_fresh.py`) verifies this.

The `WORKSPACES` dict in `portal_pipeline/router/workspaces.py` is loaded at import time from `portal.yaml` via `portal_pipeline.config.get_workspace_dict()`. The `MCP_SERVERS` dict in `portal_pipeline/tool_registry.py` is similarly derived from the fleet table via `get_pipeline_mcp_servers()`.

After any workspace change, verify consistency:
```bash
python3 -m pytest tests/unit/test_generated_artifacts_fresh.py tests/unit/test_mcp_fleet_single_source.py -q
```

Auto-routing uses two layers: **Layer 1** — LLM-based intent classifier (default: `gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`, ~840ms warm, 82.2% accuracy; switchable via `LLM_ROUTER_MODEL` in `.env`). **Layer 2** — weighted keyword scoring (fallback on confidence < 0.5 or timeout). Vision text-only fallback: `auto-vision` with no image parts reroutes to `auto-reasoning`.

### 7 — All Ports Are Reserved

| Port | Service |
|---|---|
| 8080 | Open WebUI |
| 9099 | Portal Pipeline |
| 8910-8916 | MCP: ComfyUI, Video, Music, Documents, Sandbox, Whisper, TTS |
| 8917 | Embedding (Harrier-0.6B TEI) |
| 8918 | MLX speech (Kokoro + Qwen3-TTS/ASR) |
| 8919 | MCP Security |
| 8920 | MCP Memory |
| 8921 | MCP RAG |
| 8922 | MCP Research |
| 8923 | MCP Browser (Playwright) |
| 8924 | MLX Transcribe (mlx-whisper + pyannote diarization, host-native) |
| 8925 | MCP Reranker (Qwen3-Reranker-0.6B-mxfp8, MLX-native, two-stage RAG) |
| 8926 | MCP CAD Render (OpenSCAD / CadQuery 3D model generation) |
| 8928 | Pipeline MCP (host-native; exposes explore_repository + stack introspection for Claude Code / opencode) |
| 8188 | ComfyUI |
| 8088 | SearXNG |
| 11434 | Ollama |
| 9090 | Prometheus |
| 3000 | Grafana |

Port assignments are enforced in `.env.example`. Do not reassign without updating both.

### 8 — Single Inference Tier: Ollama

Portal 5 runs one inference backend: **Ollama** (port 11434, Ollama 0.30.7+ with native MLX Metal backend on Apple Silicon). GGUF models, pulled via `ollama pull` or `hf.co/`, registered in `config/backends.yaml` under backend groups (general / coding / security / reasoning / vision / creative).

The MLX inference proxy (formerly :8081/:18081/:18082) was retired in commit `3a0c58e` — Ollama's MLX Metal backend reaches parity on this hardware without the thread-patch maintenance, admission-control complexity, and dual-stack overhead.

**MLX is NOT gone from the project — only from chat inference.** It still serves: speech/TTS+ASR (`scripts/mlx-speech.py`, :8918), diarized transcription (`scripts/mlx-transcribe.py`, :8924), embeddings (:8917), and the RAG reranker (:8925, `mlx-community/Qwen3-Reranker-0.6B-mxfp8`). Do not remove those when "cleaning up MLX."

Never add `transformers` or `torch` to `portal_pipeline/` — it runs lean. Full model catalog with memory budgets is in `config/backends.yaml`.

### 9 — The Dockerfile Split Is Intentional

- `Dockerfile.pipeline` — minimal: fastapi, uvicorn, httpx, pyyaml only. Fast build, lean image.
- `Dockerfile.mcp` — heavier: adds python-docx, python-pptx, openpyxl, fastmcp, etc.

Do not merge them. The pipeline container must stay small for fast restarts.

### 10 — Git Discipline

Commit directly to `main` during stabilization. Run tests before every push: `pytest tests/ -q --tb=no`. Commit format: `type(scope): description`. Never force push. Never commit `.env` or cloud/external deps to `pyproject.toml`.

### 11 — Shared Workspace Is The Only Path For User Files

User-uploaded files and cross-MCP artifacts live at `${AI_OUTPUT_DIR}` (default `~/AI_Output/`), mounted into containers at `/workspace`. Never write user-facing artifacts to a container-local volume that other services cannot see.

- Reads of user uploads: `portal_mcp.core.resolve_upload_path(file_id)` or `/workspace/uploads/<id>`.
- Writes of generated artifacts: `portal_mcp.core.get_generated_dir(category)` or `/workspace/generated/<category>/`.
- Categories: `transcripts`, `documents`, `images`, `videos`, `music`, `speech`. Add a new category by editing `_VALID_CATEGORIES` in `portal_mcp/core/workspace.py` (this is the source of truth — `launch.sh workspace-init` and the docker-compose mounts derive from this list).
- New Docker MCPs that touch user files: add `${AI_OUTPUT_DIR:-${HOME}/AI_Output}:/workspace` to the volumes block and `WORKSPACE_DIR=/workspace` to the environment block.
- `AUDIO_STT_ENGINE` is intentionally empty in the OWUI config — auto-transcription is disabled so audio uploads remain accessible to personas. Do not re-enable it without a migration plan for affected workflows.

---

## Testing Rules

- All tests in `tests/unit/` must pass with no network access (`pytest tests/unit/`)
- No test may call a real Ollama, real Open WebUI, or real Docker
- Use `tmp_path` fixtures for file I/O
- Mock `httpx.AsyncClient` for all HTTP calls
- Run before every commit: `pytest tests/ -v --tb=short && ruff check . && ruff format --check .`
- **Any change touching `portal_pipeline/router/streaming.py` or the streaming paths of `router_pipe.py` MUST run `./scripts/smoke_stream.sh` against the live stack before commit** — unit mocks cannot detect dependency-contract mismatches (FX1, `34be1eb`). Also runs as part of `./launch.sh test`.

### Pre-Testing: Always Verify Code Freshness

**Before any testing, troubleshooting, or benchmark run**, verify that Docker containers are running the latest code from HEAD. Stale images silently invalidate results and cause false failures.

Check image build times against recent git commits:
```bash
docker images --format "table {{.Repository}}\t{{.CreatedAt}}" | grep portal
git log --oneline --format="%h %ai %s" -5
```

If any portal image predates a relevant commit (pipeline: `portal_pipeline/`, `config/`; MCP: `portal_mcp/`), rebuild first:
```bash
./launch.sh rebuild    # rebuilds pipeline + all MCP containers
```

The UAT driver, acceptance test v6, and bench_tps all print a freshness warning automatically at startup — if you see that warning, stop and rebuild before proceeding. Do not explain away stale-image failures as model or routing issues.

---

## Adding New Capabilities

### New MCP Tool Server
1. Create `portal_mcp/<category>/<name>_mcp.py`
2. Add service to `deploy/portal-5/docker-compose.yml` on an unused port (Rule 7)
3. Add the server to `config/portal.yaml` under `mcp_fleet:` with the canonical `id`, `name`, `port`, and flags
4. Run `./launch.sh sync-config` — regenerates `.mcp.json` and OWUI tool preset stubs
5. Add tool JSON to `imports/openwebui/tools/portal_<name>.json`
6. `openwebui_init.py` picks up new tool servers automatically from the fleet

### New Persona
1. Create `config/personas/<slug>.yaml` with: `name`, `slug`, `system_prompt`, `workspace_model`, `category`
2. `openwebui_init.py` creates the Open WebUI model preset on next seed
3. No other changes needed

### New Workspace Routing Tier
1. Add the workspace entry to `config/portal.yaml` under `workspaces:`
2. Run `./launch.sh sync-config` — regenerates `backends.yaml workspace_routing`, OWUI preset JSON, and `.mcp.json`
3. Verify: `python3 -m pytest tests/unit/test_generated_artifacts_fresh.py -q`
4. Do NOT hand-edit `backends.yaml workspace_routing` or `imports/openwebui/workspaces/` — those are generated

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

Before adding new tasks or filing issues, check `KNOWN_LIMITATIONS.md` — some items are documented known limitations rather than bugs to fix. AI agents should read this file before proposing new work.

---

## Reference Docs

| Topic | Location |
|---|---|
| Model catalog + memory budgets | `config/backends.yaml` (annotated YAML comments) |
| Persona catalog (150 personas) | `config/personas/*.yaml` |
| Notification system setup | `docs/ALERTS.md` |
| ComfyUI image/video setup | `docs/COMFYUI_SETUP.md` |
| Speech pipeline (Kokoro + Qwen3-TTS/ASR) | `docs/HOWTO.md` (§ MLX Speech) |
| Voice cloning (fish-speech, optional) | `docs/FISH_SPEECH_SETUP.md` |
| Diarized transcription | `docs/HOWTO.md` (§ Transcription) |
| Claude Code / opencode integration + FastContext explorer | `docs/MCP_DEV_TOOLING.md` |
| Cluster scaling | `docs/CLUSTER_SCALE.md` |
| Admin guide | `docs/ADMIN_GUIDE.md` |
