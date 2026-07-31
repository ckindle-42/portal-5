# CLAUDE.md — Claude Code Guidelines for Portal 5

**Project**: Portal 5 — Open WebUI Intelligence Layer  
**Repository**: https://github.com/ckindle-42/portal-5  
**Version**: 8.0.0

---

## What Portal 5 Is

Portal 5 is an **Open WebUI enhancement layer** — not a replacement web stack. It extends Open WebUI through its Pipeline server (:9099) and MCP Tool Servers. Result: local AI platform for text, code, security, images, music, documents, voice — all on your hardware, one interface. Video-generation code is retained, but the service is shelved.

**Architecture**: Open WebUI → Portal Pipeline (:9099) → Ollama (:11434) → local models. MCP servers (:8910–8928) provide tools (documents, code sandbox, TTS, research, memory, RAG, browser, proxmox, pipeline introspection).

**Inference**: Single tier — **Ollama** (GGUF models, Ollama 0.32.4+ with native MLX Metal backend on Apple Silicon). The 0.32.4 floor carries the upstream Metal-residency fix that keeps pinned models resident across multi-model serving. The MLX inference proxy was retired in commit 3a0c58e; Ollama now matches or beats standalone mlx_lm throughput while removing the dual-stack operational overhead. Host-native, not Docker. NOTE: MLX is still used outside inference — for speech (mlx-speech :8918), diarized transcription (mlx-transcribe :8924), embeddings (:8917), and reranking (:8925). Those are audio/retrieval runtimes, not the chat inference tier.

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

## Working Style — How to Make Changes Here

These rules bias toward caution over speed. For trivial tasks, use judgment.

### Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations of the task exist, present them — don't pick one silently.
- If a simpler approach exists than what was asked for, say so. Push back when warranted.
- Before proposing new work: check `KNOWN_LIMITATIONS.md` (some "bugs" are documented limitations) and lead discovery from the wiki fact-units (Rule 13) rather than cold-grepping.

### Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked. No abstractions for single-use code. No unrequested "flexibility" or "configurability". No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- This is architectural here, not just stylistic: scope creep collides with "What Portal 5 Is NOT" at the feature level and with the lean-container rules (Rules 8–9) at the dependency level.

### Surgical Changes

**Touch only what you must. Clean up only your own mess.**

- Every changed line should trace directly to the task. Don't "improve" adjacent code, comments, or formatting; match existing style even where you'd choose differently.
- Remove imports/variables/functions that YOUR change made unused. Pre-existing dead code: mention it, don't delete it unless asked.
- Before staging, confirm the diff contains no ride-along artifacts (see Testing Rules on `field_journal/` write-through).

### Goal-Driven Execution

**Define success criteria. Loop until verified.**

- Transform tasks into verifiable goals before coding: "fix the bug" → "write a test that reproduces it, then make it pass"; "refactor X" → "tests pass before and after".
- For multi-step tasks, state a brief plan with a verification check per step.
- The verification ladder is already fixed by this project — per-commit gate (`pytest tests/unit/ -q && ruff check . && ruff format --check .`), final gate (`bash scripts/ci_local.sh`), live streaming gate where required (`./scripts/smoke_stream.sh`), and doc reconciliation (Rule 12). A task isn't done until the applicable gates are green.

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

Each MCP server (`portal/modules/*/tools/*_mcp.py`, `portal/platform/{mcp_host,memory}/`, or a vendored server in `portal_mcp/{filesystem,scrapling}/`) is a standalone service using the MCP SDK v2 `MCPServer` API (mounted in FastAPI where needed). They have zero imports from `portal.platform.inference` or `portal_channels/`. They are registered in Open WebUI as Tool Servers. They do not know about each other.

### 4 — The Pipeline Is Stateless (with metrics persistence)

`portal/platform/inference/router_pipe.py` (facade for `portal/platform/inference/router/app.py`'s `app`) is stateless for conversation routing — no database, no session state, no memory. Conversation history lives in Open WebUI's database. Cross-session memory uses Open WebUI's native memory feature.

The pipeline does persist operational metrics (request counts, TPS, errors) to `/app/data/metrics_state.json` for telemetry only — it does not affect routing decisions.

### 5 — Personas Live in config/personas/

Each `.yaml` in `config/personas/` becomes an Open WebUI model preset during seeding. The YAML defines: `name`, `slug`, `module`, `workspace_model`, `category`, and either `system_prompt` (inline) or `prompt_template` (a shared body under `portal/modules/eval/persona_matrix/prompts/<name>.txt` — exactly one of the two is required, see BUILD_PROGRAM_COLLAPSE_V1.md Phase 8). Optional `variant` selects a named override on a factored workspace (e.g. `auto-coding` + `variant: laguna`). Optional `model_pin` is an exact `config/backends.yaml` model id that **is consumed** — applied in the handler via `_resolve_model_override` (the same bounded, catalog-checked mechanism the `?model=<hint>` query param uses) — for a persona whose identity is tied to one specific model rather than its workspace's pool primary (see `DESIGN_PERSONA_INTENT_REMEDIATION_V1.md`). Optional `preferred_models` is an ordered model-fallback chain that is **NOT consumed anywhere in the serving path** — advisory metadata only, roadmapped for a future live chain-walk (`P5-FUT-MODEL-CHAINWALK`); do not treat it as selecting the served model, and do not set it alongside `model_pin` on the same persona (the pin is authoritative — two competing model-intent fields is how a persona can silently be served the wrong model, see `scripts/persona_intent_audit.py` Check 2/4). The `openwebui_init.py` script reads these and creates model presets in Open WebUI. Adding a new persona = adding one YAML file. See `config/personas/` for the full catalog — currently 138 files (`ls config/personas/*.yaml | wc -l`).

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

The `WORKSPACES` dict in `portal/platform/inference/router/workspaces.py` is loaded at import time from `portal.yaml` via `portal.platform.inference.config.get_workspace_dict()`, which excludes every workspace whose `module:` is currently disabled (per `portal.platform.wiki.adapters.modules.enabled_modules()`) — the `eval` module additionally honors the `PORTAL_ENABLE_EVAL=1` bench-harness opt-in. The `MCP_SERVERS` dict in `portal/platform/inference/tool_registry.py` is similarly derived from the fleet table via `get_pipeline_mcp_servers()` (not module-gated — MCP servers are independent services per Rule 3; disabling a module hides its workspaces/routing, not its container).

Toggle a module's enabled state with `python3 -m portal.platform.inference.cli module {list,status,enable,disable}` — confirm-gated by default (writes a `proposed` wiki unit under `portal_wiki/proposed/`), pass `--yes` to apply immediately. A confirmed change re-runs `sync-config` automatically.

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

Portal 5 runs one inference backend: **Ollama** (port 11434, Ollama 0.32.4+ with native MLX Metal backend on Apple Silicon). The minimum includes the upstream Metal-residency fix needed for pinned router and inference models to remain loaded together. GGUF models, pulled via `ollama pull` or `hf.co/`, registered in `config/backends.yaml` under backend groups (general / coding / security / reasoning / vision / creative).

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

Documentation is coupled to code the same way Rule 6 couples workspaces to `portal.yaml`: **mechanically, where mechanization exists.** The old commit-stamp ledger (`docs/.doc_ledger.yaml`, check **`AK. doc currency`**) is retired — the ledger is empty and AK is a no-op now. Doc currency for *generated* content lives in check **`AW. wiki facts current`** (`scripts/validate_system.py`): it diffs each fact-unit (`kind: what`) against live config and every `WIKI:GENERATED` block against its unit, so a fact-unit or rendered block can't silently drift.

Authored knowledge (`kind: why` / HOWTO units) is **not** auto-checked against source by design (`portal/platform/wiki/maintain.py`: "advancing HEAD alone does not make an authored canonical unit stale") — staleness there is caught by reading, not tooling.

**The rule:** when your change touches a subsystem, update the fact-unit or authored unit that covers it **in the same task** — don't defer it. For a fact-unit, just re-run `./launch.sh sync-config` (Rule 6) and AW will catch anything you missed. For an authored WHY/HOWTO unit, edit `portal_wiki/canonical/unit-*.md` directly; there is no stamp step.

**Never hardcode counts/ports/check-letters as prose** (persona counts, workspace counts, port tables, validate check letters). Derive them from an extractor at reconcile time; a hardcoded persona count written from memory is drift waiting to happen.

Note: `scripts/validate_system.py` (all 73 checks, including AW) runs at **push** time via the `validate-system` pre-commit hook, scoped to commits touching `portal/`, `config/`, `portal_wiki/`, `scripts/`, `deploy/`, or `tests/` — it is **not** part of `scripts/ci_local.sh`, which stays narrow (ruff + pytest only, per Testing Rules).

### 13 — Fact-Units Are the Discovery Index

Before grepping, query the wiki: `wiki_search` / `wiki_get_unit` / `wiki_explain`. Fact-units
(`unit-fact-*`, gated by validate check AW) are the trusted index for workspaces, models, MCP fleet,
personas, tool authorizations, and the MCP tool registry. Lead discovery from them; still verify every
edit anchor `count==1` against HEAD before editing. See `unit-HOWTO-discovery-with-fact-units`.

---

## Testing Rules

- All tests in `tests/unit/` must pass with no network access (`pytest tests/unit/`)
- No test may call a real Ollama, real Open WebUI, or real Docker
- Use `tmp_path` fixtures for file I/O
- Mock `httpx.AsyncClient` for all HTTP calls
- **`pytest portal` (the module-tree suite under `portal/modules/*/tests/`) is known to leave real write-through artifacts** in `portal/modules/security/core/field_journal/` (dated entries + `_index.json`) and `portal/modules/security/core/results/checkpoints/` — some security-module tests write through the real goal/playbook journal path instead of a `tmp_path`-redirected one. `results/checkpoints/` is gitignored; `field_journal/` holds real committed history so it is **not** gitignored — after running `pytest portal` locally, run `git status` and `git checkout -- portal/modules/security/core/field_journal/_index.json` (plus `git clean` any new dated entry files) before staging a commit, so test side effects never ride along with real changes. Fixing this at the source (route the journal writer through a fixture-injected path in the offending tests) is open, tracked in `KNOWN_LIMITATIONS.md`.
- Run before every commit: `pytest tests/unit/ -q && ruff check . && ruff format --check .`
- **The final verify step of any task is `bash scripts/ci_local.sh`**, not a narrow per-file pytest. This mirrors CI's `.github/workflows/unit-tests.yml` exactly (clean env, editable install, same pytest invocation) — it catches the "works locally, fails CI" gap before the push. A task isn't done until the ci-parity gate is green.
- Pre-commit hooks (`.pre-commit-config.yaml`) enforce on every commit: ruff lint+format, generated-artifact freshness (`sync-config` idempotent), no duplicate dep pins, **pytest unit suite**. A separate, heavier hook — `validate-system` (`scripts/validate_system.py`, all 73 lettered checks, ~60s) — runs at **push** time, scoped to commits that touch `portal/`, `config/`, `portal_wiki/`, `scripts/`, `deploy/`, or `tests/`. Install once: `pip install pre-commit && pre-commit install && pre-commit install --hook-type pre-push` (the second install call is required for the pre-push stage hook to actually fire — `pre-commit install` alone only wires up the pre-commit stage).
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
| Persona catalog (currently 138 — `ls config/personas/*.yaml \| wc -l`) | `config/personas/*.yaml` |
| Notification system setup | `docs/ALERTS.md` |
| ComfyUI image setup and archived video status | `docs/COMFYUI_SETUP.md` |
| Speech pipeline (Kokoro + Qwen3-TTS/ASR) | `docs/HOWTO.md` (§ MLX Speech) |
| Voice cloning (fish-speech, optional) | `docs/FISH_SPEECH_SETUP.md` |
| Diarized transcription | `docs/HOWTO.md` (§ Transcription) |
| Claude Code / opencode integration + FastContext explorer | `docs/MCP_DEV_TOOLING.md` |
| Cluster scaling | `docs/CLUSTER_SCALE.md` |
| Admin guide | `docs/ADMIN_GUIDE.md` |

---

## Portal Wiki — Canonical Knowledge Layer

The project has a self-maintaining knowledge backbone (`portal_wiki/`) that agents can query for cited, grounded answers instead of re-reading source.

**For agents:** use `wiki.search`, `wiki.get_unit`, `wiki.explain` (via `portal_wiki.mcp`) to look up architecture decisions, technique signatures, subsystem overviews, and design rationale. Every answer cites its source — never trust a wiki claim without its citation. Task-specific "how do I add X" checklists (new MCP server, persona, workspace tier, cluster node) live in `unit-HOWTO-adding-new-capabilities` — query it rather than looking here.

**For operators:** `portal_wiki/canonical/` contains the source-of-truth knowledge units (markdown + frontmatter). Edit the canonical unit, not rendered views. Views are generated to `docs/generated/` and marked `<!-- GENERATED -->`.

**CLAUDE.md is the one intentional exception.** As of `TASK_WIKI_SPINE_DOC_GENERATION_V3`, nearly every other doc in this repo (`README.md`, `docs/*.md`, `config/MODEL_CATALOG.md`, the test-execution prompts, etc.) is a shell whose substance is `<!-- WIKI:GENERATED unit=<id> -->` blocks rendered from `portal_wiki/canonical/` — see `docs/DESIGN_WIKI_GENERATION_LOOP_V1.md` for the mechanism. CLAUDE.md alone stays hand-authored (it is hard-excluded from migration in `portal/platform/wiki/migration.py`) because it is the agent entry point, not a reference doc. When a change at HEAD affects a fact recorded in a spine unit, update that unit (and re-run `./launch.sh sync-config`) in the same change — a stale unit is a stale doc across the whole surface it feeds, not just one file.

**What lives where:**
- `portal/platform/wiki/` — engine: schema, store, maintenance, rendering (top-level files are stack-agnostic, zero Portal imports — this is the extraction-guarantee boundary CI enforces via `AJ. wiki core backbone`)
- `portal/platform/wiki/adapters/` — Portal-specific wiring (Ollama inference, git source, security/intent/code seeders, module toggle resolver)
- `portal_wiki/canonical/` — the knowledge units themselves (git-versioned markdown, still at the repo-root data path — never moved)
- `portal_wiki/mcp.py` — agent-facing tools (search, get_unit, explain)
