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

As of `BUILD_PROGRAM_MODULARIZATION_ALL_V1` (M0-M8), the codebase is organized by discipline module under `portal/modules/`, with cross-cutting infrastructure under `portal/platform/`. `portal_mcp/` now holds only externally-vendored MCP servers that were never moved (`filesystem/`, `scrapling/`). `portal_wiki/` is the wiki's git-versioned data home (`canonical/`) plus its CLI/MCP-tool entrypoints; the wiki engine itself lives at `portal/platform/wiki/`.

```
portal-5/
├── portal/
│   ├── modules/                  # One dir per discipline — code + tools + tests together
│   │   ├── security/             # RBP (Red/Blue/Purple) bench engine — largest module
│   │   │   ├── core/             # RBP engine, capability graph, growth loop, intake
│   │   │   ├── tools/            # security_mcp.py, proxmox_mcp.py (MCP servers)
│   │   │   ├── knowledge/        # SPL library, scenario facades
│   │   │   ├── config/           # Security-specific config
│   │   │   ├── cli/              # `portal security ...` subcommands
│   │   │   ├── adapters/         # Wiki write-back adapters
│   │   │   ├── eval/             # Security-specific eval harness
│   │   │   └── tests/            # Mirrors this module's tree
│   │   ├── coding/tools/         # code_sandbox_mcp.py (:8914)
│   │   ├── media/tools/          # comfyui_mcp, video_mcp, music_mcp, tts_mcp, whisper_mcp
│   │   ├── cad/tools/            # cad_render_mcp.py (:8926)
│   │   ├── documents/tools/      # document_mcp.py (:8913)
│   │   ├── research/tools/       # web_search_mcp, rag_mcp, reranker_mcp, browser_mcp
│   │   ├── compliance/config/    # Config-only module (compliance personas + routing)
│   │   ├── general/               # Config-only module (vendored filesystem/fetch/git/docker)
│   │   └── eval/persona_matrix/  # Cross-cutting persona coverage sweep — off by default
│   └── platform/                  # Cross-cutting infra, not owned by any one discipline
│       ├── inference/             # FastAPI Pipeline server (:9099) — formerly portal_pipeline/
│       │   ├── cluster_backends.py  # BackendRegistry — Ollama (+ vLLM-compatible), health-aware
│       │   ├── router_pipe.py       # Backwards-compat facade — re-exports router/app.py's `app`
│       │   ├── sync_config.py       # Generates backends.yaml/.mcp.json/OWUI presets/modules manifest from portal.yaml
│       │   ├── tool_registry.py     # Tool discovery (polls MCP /tools), advertisement, dispatch
│       │   ├── router/              # Decomposed pipeline modules
│       │   │   ├── app.py           # FastAPI app + route decorators
│       │   │   ├── handlers.py      # Route handler bodies (incl. Gate 4 module-disabled 404)
│       │   │   ├── routing.py       # LLM router + keyword workspace detection
│       │   │   ├── streaming.py     # SSE streaming: tool loop, preamble
│       │   │   └── workspaces.py    # WORKSPACES dict, persona map, workspace tool helpers
│       │   ├── cli/                 # Typed operator CLI (portal config show, …) — entry: portal
│       │   └── notifications/       # Operational alerts + daily summaries
│       ├── wiki/                    # Wiki engine (schema, store, writeback, render, maintain)
│       │   └── adapters/            # Portal-specific wiki wiring (module toggle resolver, growth writeback)
│       ├── mcp_host/                 # Pipeline MCP (:8928) + shared MCP workspace helpers (workspace.py: resolve_upload_path, get_generated_dir, _VALID_CATEGORIES)
│       └── memory/                   # Cross-session memory store MCP (:8920)
├── portal_mcp/                   # Externally-vendored MCP servers only (never moved)
│   ├── filesystem/                # Vendored filesystem MCP server
│   └── scrapling/                 # Vendored scraping MCP server
├── portal_wiki/                  # Wiki data + CLI/MCP entrypoints (engine is portal/platform/wiki/)
│   └── canonical/                 # Git-versioned knowledge unit markdown files
├── config/
│   ├── backends.yaml             # OPERATOR EDITS THIS — adds cluster nodes here, no code changes
│   ├── portal.yaml               # Single source of truth for workspaces + mcp_fleet
│   ├── modules.generated.yaml    # Module enable/disable snapshot (generated by sync-config)
│   ├── personas/                 # Persona YAML files → Open WebUI model presets (see Rule 5)
│   ├── routing_descriptions.json # LLM router workspace descriptions
│   └── routing_examples.json     # LLM router few-shot examples
├── deploy/portal-5/
│   └── docker-compose.yml        # THE launch definition — all services
├── scripts/
│   ├── lib/                      # Shell function libraries sourced by launch.sh dispatcher
│   │   ├── util.sh               # Shared utilities (color, env, health checks)
│   │   ├── models.sh             # Model pull/refresh/import wrappers
│   │   ├── services.sh           # Service start/stop/status wrappers
│   │   ├── lab.sh                # Lab-exec wrappers
│   │   ├── backup.sh             # Backup/restore wrappers
│   │   └── users.sh              # User management wrappers
│   ├── ci/                       # Pre-commit CI guard scripts
│   │   ├── check_generated_fresh.py       # Fail if sync-config produces a diff
│   │   ├── check_no_identical_sources.py  # Warn on deploy/↔portal_mcp/ duplicates
│   │   └── check_pyproject_no_dup.py      # Fail on duplicate dep pins
│   ├── doc_ledger.py              # Doc-currency ledger CLI (status/check/stamp) — see Rule 12
│   ├── openwebui_init.py         # Auto-seeds Open WebUI on first fresh volume
│   ├── mlx-speech.py             # Host-native MLX speech server (TTS + ASR, port :8918)
│   ├── embedding-server.py       # Host-native ARM64 embedding server (fallback)
│   ├── pipeline-entrypoint.sh    # Docker entrypoint for portal-pipeline
│   ├── smoke_stream.sh           # Live streaming gate (also run by ./launch.sh test)
│   └── ...                       # See scripts/ for full list
├── tests/
│   ├── unit/                     # pytest unit tests — no Docker required
│   ├── acceptance/               # Acceptance test section modules (s*.py) + shared infra
│   ├── uat/                      # UAT driver modules (runner/cli/browser/grading/results)
│   └── benchmarks/               # Inference benchmarks (Ollama TPS, positional recall, coding shootout)
├── Dockerfile.pipeline           # Lean image for portal-pipeline service
├── Dockerfile.mcp                # Image for portal/modules/*/tools + portal_mcp services
├── launch.sh                     # Thin dispatcher — sources scripts/lib/*.sh, delegates to portal CLI
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
| **Type check** | `mypy portal/` | strict=true currently |
| **Tests** | `pytest tests/ -v --tb=short` | Must pass before any commit |
| **Python** | 3.10+ required | pyproject.toml requires-python >= 3.10 |
| **Framework** | FastAPI + Pydantic v2 | Async throughout |
| **Launch** | `./launch.sh up` | Never `docker compose up` directly |
| **Operator CLI** | `portal config show` | Typed CLI; `portal/platform/inference/cli/`; installed via `[project.scripts]` |

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

Each MCP server (`portal/modules/*/tools/*_mcp.py`, `portal/platform/{mcp_host,memory}/`, or a vendored server in `portal_mcp/{filesystem,scrapling}/`) is a standalone FastAPI+FastMCP app. They have zero imports from `portal.platform.inference` or `portal_channels/`. They are registered in Open WebUI as Tool Servers. They do not know about each other.

### 4 — The Pipeline Is Stateless (with metrics persistence)

`portal/platform/inference/router_pipe.py` (facade for `portal/platform/inference/router/app.py`'s `app`) is stateless for conversation routing — no database, no session state, no memory. Conversation history lives in Open WebUI's database. Cross-session memory uses Open WebUI's native memory feature.

The pipeline does persist operational metrics (request counts, TPS, errors) to `/app/data/metrics_state.json` for telemetry only — it does not affect routing decisions.

### 5 — Personas Live in config/personas/

Each `.yaml` in `config/personas/` becomes an Open WebUI model preset during seeding. The YAML defines: `name`, `slug`, `system_prompt`, `workspace_model`, `category`. The `openwebui_init.py` script reads these and creates model presets in Open WebUI. Adding a new persona = adding one YAML file. See `config/personas/` for the full catalog — currently 130 files (`ls config/personas/*.yaml | wc -l`).

### 6 — config/portal.yaml Is the Single Source of Truth for Workspaces and MCP Fleet

All workspaces and the MCP tool server fleet are defined in **`config/portal.yaml`**. Do not hand-edit these derived files:
- `config/backends.yaml` → `workspace_routing` block (auto-generated)
- `.mcp.json` → IDE MCP server list (auto-generated)
- `imports/openwebui/workspaces/workspace_*.json` → OWUI workspace presets (auto-generated)

After any change to `config/portal.yaml`, regenerate all derived files:
```bash
./launch.sh sync-config
# or directly:
python3 -m portal.platform.inference.sync_config
```

`sync-config` is idempotent — running it twice produces no diff. The test suite (`tests/unit/test_generated_artifacts_fresh.py`) verifies this. `sync-config` also regenerates `config/modules.generated.yaml`, a rendered snapshot of module enable/disable state (see Rule 12's sibling discipline for the module toggle layer — resolver at `portal/platform/wiki/adapters/modules.py`).

The `WORKSPACES` dict in `portal/platform/inference/router/workspaces.py` is loaded at import time from `portal.yaml` via `portal.platform.inference.config.get_workspace_dict()`. The `MCP_SERVERS` dict in `portal/platform/inference/tool_registry.py` is similarly derived from the fleet table via `get_pipeline_mcp_servers()`.

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
| 8929 | MCP MITRE ATT&CK (technique lookup, data sources, detections — deterministic, not RAG) |
| 8932 | MCP Detections (SPL library search, validate_syntax, explain_detection — bumped from 8930 to avoid an INCALMO_PORT collision, see `.env.example`) |
| 8931 | MCP Wiki (canonical knowledge layer — search, get_unit, explain — cited answers) |
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

Never add `transformers` or `torch` to `portal/platform/inference/` — it runs lean. Full model catalog with memory budgets is in `config/backends.yaml`.

### 9 — The Dockerfile Split Is Intentional

- `Dockerfile.pipeline` — minimal: fastapi, uvicorn, httpx, pyyaml only. Fast build, lean image.
- `Dockerfile.mcp` — heavier: adds python-docx, python-pptx, openpyxl, fastmcp, etc.

Do not merge them. The pipeline container must stay small for fast restarts.

### 10 — Git Discipline

Commit directly to `main` during stabilization. Run tests before every push: `pytest tests/ -q --tb=no`. Commit format: `type(scope): description`. Never force push. Never commit `.env` or cloud/external deps to `pyproject.toml`.

### 11 — Shared Workspace Is The Only Path For User Files

User-uploaded files and cross-MCP artifacts live at `${AI_OUTPUT_DIR}` (default `~/AI_Output/`), mounted into containers at `/workspace`. Never write user-facing artifacts to a container-local volume that other services cannot see.

- Reads of user uploads: `portal.platform.mcp_host.resolve_upload_path(file_id)` or `/workspace/uploads/<id>`.
- Writes of generated artifacts: `portal.platform.mcp_host.get_generated_dir(category)` or `/workspace/generated/<category>/`.
- Categories: `transcripts`, `documents`, `images`, `videos`, `music`, `speech`. Add a new category by editing `_VALID_CATEGORIES` in `portal/platform/mcp_host/workspace.py` (this is the source of truth — `launch.sh workspace-init` and the docker-compose mounts derive from this list).
- New Docker MCPs that touch user files: add `${AI_OUTPUT_DIR:-${HOME}/AI_Output}:/workspace` to the volumes block and `WORKSPACE_DIR=/workspace` to the environment block.
- `AUDIO_STT_ENGINE` is intentionally empty in the OWUI config — auto-transcription is disabled so audio uploads remain accessible to personas. Do not re-enable it without a migration plan for affected workflows.

### 12 — Docs Travel With The Work

Documentation is coupled to code the same way Rule 6 couples workspaces to `portal.yaml`: **mechanically, and CI-gated.** Every living doc is bound in `docs/.doc_ledger.yaml` to the source paths that determine its correctness, plus the commit it was last reconciled against. A doc is *stale* the moment a bound source changes past that commit.

**The rule:** when your change touches a subsystem, reconcile the docs bound to it **in the same task**, then re-stamp. Do not defer doc updates to "later" — later is how the docs rotted in the first place.

```bash
python3 scripts/doc_ledger.py status              # what drifted
# ...reconcile the stale docs against live code...
python3 scripts/doc_ledger.py stamp <doc>         # or stamp-all after a full pass
```

Enforcement: `scripts/validate_system.py` check **`AL. doc currency`** fails when any bound source changed since a doc's stamp. `bash scripts/ci_local.sh` will be red until docs are reconciled. The re-runnable remediation is `TASK_DOC_AUDIT_AGENT_V*.md` — the doc-side analogue of the validate/test harness.

**Never hardcode counts/ports/check-letters as prose** (persona counts, workspace counts, port tables, validate check letters). Derive them from an extractor at reconcile time; a hardcoded "130 personas" is drift waiting to happen.

---

## Testing Rules

- All tests in `tests/unit/` must pass with no network access (`pytest tests/unit/`)
- No test may call a real Ollama, real Open WebUI, or real Docker
- Use `tmp_path` fixtures for file I/O
- Mock `httpx.AsyncClient` for all HTTP calls
- Run before every commit: `pytest tests/unit/ -q && ruff check . && ruff format --check .`
- **The final verify step of any task is `bash scripts/ci_local.sh`**, not a narrow per-file pytest. This mirrors CI's `.github/workflows/unit-tests.yml` exactly (clean env, editable install, same pytest invocation) — it catches the "works locally, fails CI" gap before the push. A task isn't done until the ci-parity gate is green.
- Pre-commit hooks (`.pre-commit-config.yaml`) enforce: ruff lint+format, generated-artifact freshness (`sync-config` idempotent), no duplicate dep pins, **pytest unit suite**. Install once: `pip install pre-commit && pre-commit install`.
- Unit tests also run on every PR and push to `main` via `.github/workflows/unit-tests.yml`.
- **Any change touching `portal/platform/inference/router/streaming.py` or the streaming paths of `router_pipe.py` MUST run `./scripts/smoke_stream.sh` against the live stack before commit** — unit mocks cannot detect dependency-contract mismatches (FX1, `34be1eb`). Also runs as part of `./launch.sh test`.

### Pre-Testing: Always Verify Code Freshness

**Before any testing, troubleshooting, or benchmark run**, verify that Docker containers are running the latest code from HEAD. Stale images silently invalidate results and cause false failures.

Check image build times against recent git commits:
```bash
docker images --format "table {{.Repository}}\t{{.CreatedAt}}" | grep portal
git log --oneline --format="%h %ai %s" -5
```

If any portal image predates a relevant commit (pipeline: `portal/platform/`, `config/`; MCP: `portal/modules/*/tools/`, `portal_mcp/`), rebuild first:
```bash
./launch.sh rebuild    # rebuilds pipeline + all MCP containers
```

The UAT driver, acceptance test v6, and bench_tps all print a freshness warning automatically at startup — if you see that warning, stop and rebuild before proceeding. Do not explain away stale-image failures as model or routing issues.

### Checkpoint Backup Discipline — Non-Negotiable

**Multi-hour bench/sweep checkpoint files (e.g. `/tmp/agentic_blue_sweep.json`) must be backed up before they are ever cleared, deleted, or overwritten — no exceptions, not even "I already reported the numbers in chat."** A `cp checkpoint.json checkpoint_$(date +%Y%m%dT%H%M%S).json.bak` costs nothing; re-running a 20-scenario × 3-trial sweep across several models costs hours. This applies whenever you are about to:
- `rm`/overwrite a checkpoint to seed a fresh run
- Launch a new sweep that reuses the same output path as a just-completed one
- Any point where the next command could destroy data from a run that took more than a few minutes to produce

The failure mode this guards against: backing up *some* runs and not others out of momentum or urgency, then losing exactly the run you didn't back up. Treat the backup step as part of the launch sequence itself (write it into the same command block that clears the old checkpoint), not a separate judgment call to remember. If you skip it and then need to clear the checkpoint, back it up in that same moment before proceeding — never clear first and back up "after."

---

## Adding New Capabilities

### New MCP Tool Server
1. Create `portal/modules/<discipline>/tools/<name>_mcp.py` (or `portal/platform/<area>/` for a cross-cutting server — see Rule 6)
2. Add service to `deploy/portal-5/docker-compose.yml` on an unused port (Rule 7)
3. Add the server to `config/portal.yaml` under `mcp_fleet:` with the canonical `id`, `name`, `port`, and flags
4. Run `./launch.sh sync-config` — regenerates `.mcp.json` and OWUI tool preset stubs
5. Add tool JSON to `imports/openwebui/tools/portal_<name>.json`
6. `openwebui_init.py` picks up new tool servers automatically from the fleet
7. Reconcile bound docs and re-stamp: `python3 scripts/doc_ledger.py status` → fix → stamp

### New Persona
1. Create `config/personas/<slug>.yaml` with: `name`, `slug`, `system_prompt`, `workspace_model`, `category`
2. `openwebui_init.py` creates the Open WebUI model preset on next seed
3. No other changes needed
4. Reconcile bound docs and re-stamp: `python3 scripts/doc_ledger.py status` → fix → stamp

### New Workspace Routing Tier
1. Add the workspace entry to `config/portal.yaml` under `workspaces:`
2. Run `./launch.sh sync-config` — regenerates `backends.yaml workspace_routing`, OWUI preset JSON, and `.mcp.json`
3. Verify: `python3 -m pytest tests/unit/test_generated_artifacts_fresh.py -q`
4. Do NOT hand-edit `backends.yaml workspace_routing` or `imports/openwebui/workspaces/` — those are generated
5. Reconcile bound docs and re-stamp: `python3 scripts/doc_ledger.py status` → fix → stamp

### New Cluster Node
1. Edit `config/backends.yaml` — add backend entry, assign to group
2. `docker compose restart portal-pipeline`
3. Done. No code changes.
4. Reconcile bound docs and re-stamp: `python3 scripts/doc_ledger.py status` → fix → stamp

---

## Zero-Setup Requirements

Every feature must work from `./launch.sh up` without manual steps. Dependencies must be installable via pip/apt-get in the Dockerfile OR a Docker service. If a dependency may fail, degrade gracefully — never crash.

---

## Do Not

- Do NOT add `OLLAMA_BASE_URL` directly to Open WebUI's env — everything must go through `portal-pipeline`
- Do NOT import `portal.platform.inference` from an MCP module (`portal/modules/*/tools/`, `portal_mcp/`) or vice versa — they are independent
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
| Persona catalog (currently 130 — `ls config/personas/*.yaml \| wc -l`) | `config/personas/*.yaml` |
| Notification system setup | `docs/ALERTS.md` |
| ComfyUI image/video setup | `docs/COMFYUI_SETUP.md` |
| Speech pipeline (Kokoro + Qwen3-TTS/ASR) | `docs/HOWTO.md` (§ MLX Speech) |
| Voice cloning (fish-speech, optional) | `docs/FISH_SPEECH_SETUP.md` |
| Diarized transcription | `docs/HOWTO.md` (§ Transcription) |
| Claude Code / opencode integration + FastContext explorer | `docs/MCP_DEV_TOOLING.md` |
| Cluster scaling | `docs/CLUSTER_SCALE.md` |
| Admin guide | `docs/ADMIN_GUIDE.md` |

---

## Portal Wiki — Canonical Knowledge Layer

The project has a self-maintaining knowledge backbone (`portal_wiki/`) that agents can query for cited, grounded answers instead of re-reading source.

**For agents:** use `wiki.search`, `wiki.get_unit`, `wiki.explain` (via `portal_wiki.mcp`) to look up architecture decisions, technique signatures, subsystem overviews, and design rationale. Every answer cites its source — never trust a wiki claim without its citation.

**For operators:** `portal_wiki/canonical/` contains the source-of-truth knowledge units (markdown + frontmatter). Edit the canonical unit, not rendered views. Views are generated to `docs/generated/` and marked `<!-- GENERATED -->`.

**What lives where:**
- `portal/platform/wiki/` — engine: schema, store, maintenance, rendering (top-level files are stack-agnostic, zero Portal imports — this is the extraction-guarantee boundary CI enforces via `AK. wiki core backbone`)
- `portal/platform/wiki/adapters/` — Portal-specific wiring (Ollama inference, git source, security/intent/code seeders, module toggle resolver)
- `portal_wiki/canonical/` — the knowledge units themselves (git-versioned markdown, still at the repo-root data path — never moved)
- `portal_wiki/mcp.py` — agent-facing tools (search, get_unit, explain)
