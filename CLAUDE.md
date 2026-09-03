# CLAUDE.md — Claude Code Guidelines for Portal 5

**Project:** Portal 5 — Open WebUI Intelligence Layer · **Repository:** https://github.com/ckindle-42/portal-5 · **Version:** 8.0.0

## What Portal 5 Is

An Open WebUI enhancement layer, not a replacement web stack. It extends Open WebUI through its Pipeline server (:9099) and MCP Tool Servers: a local AI platform for text, code, security, images, music, documents, voice — all on your hardware, one interface. Image generation is MLX-native (MFLUX, host layer); video generation is MLX-native (ltx-2-mlx) behind the `video` module, off by default and shipped enabled.

**Architecture:** Open WebUI → Portal Pipeline (:9099) → Ollama (:11434) → local models. MCP servers (:8912–8935) provide tools (documents, code sandbox, TTS, research, memory, RAG, browser, proxmox, pipeline introspection, MLX image/video generation).
**Inference:** Single tier — **Ollama** (GGUF, 0.32.4+ with native MLX Metal on Apple Silicon). MLX proxy retired (`3a0c58e`); MLX remains for speech (:8918), transcription (:8924), embeddings (:8917), reranking (:8925) — not chat. Host-native, not Docker.

**Core values:** Privacy-first, fully local, zero cloud dependencies, launch in one command.

## What Portal 5 Is NOT

- A web chat interface, auth system, RAG/knowledge base, or metrics stack — Open WebUI handles those
- Cloud inference (OpenRouter, Anthropic API, etc.) or external agent frameworks (LangChain, LlamaIndex)
- Anything requiring accounts/API keys beyond `.env.example`

## Working Style

**Think before coding.** State assumptions; surface tradeoffs; if uncertain, ask. Check `KNOWN_LIMITATIONS.md` and lead discovery from the wiki fact-units before cold-grepping.
**Simplicity first.** Minimum code that solves the problem. Nothing speculative, no unrequested flexibility.
**Surgical changes.** Touch only what you must. Every changed line traces to the task. Remove imports/variables your change made unused; mention pre-existing dead code, don't delete it.
**Goal-driven.** Define success criteria, loop until verified. Verification ladder: per-commit gate `uv run pytest tests/unit/ -q && uv run ruff check . && uv run ruff format --check .`, final gate `bash scripts/ci_local.sh`, live streaming gate `./scripts/smoke_stream.sh`, doc reconciliation (Rule 12).

## Tech Stack

`uv` (not pip); `uv pip install -e ".[dev]"`; `uv run ruff check . --fix` / `uv run ruff format .`; `uv run mypy portal/` (strict); `uv run pytest tests/ -v --tb=short`; Python 3.10+; FastAPI + Pydantic v2, async; `./launch.sh up`; operator CLI `portal config show`.

**Always prefix `pytest`/`ruff`/`mypy` with `uv run` (or activate `.venv` in the SAME shell command, not a prior one).** A bare `pytest` on PATH can resolve to an unrelated Homebrew/global install (`/opt/homebrew/bin/pytest` on this machine) instead of the project's `.venv`, silently running against the wrong Python/site-packages and producing bogus collection errors. `source .venv/bin/activate` does not persist across separate tool-call shell invocations — each is a fresh shell — so activation-then-run in two steps is unreliable here; `uv run <cmd>` is the one form that's always correct.

## Architectural Ground Rules
### 1 — config/backends.yaml Is Sacred
Only file an operator edits to scale from 1 to 12 nodes. Never hardcode backend URLs in Python; all discovery flows through `BackendRegistry`.
### 2 — Never Modify Open WebUI Source
Extend via the Pipeline server, MCP Tool Servers, and Open WebUI Functions only.
### 3 — MCP Servers Are Independent Services
Standalone MCP SDK v2 servers; zero imports from `portal.platform.inference` or `portal_channels/`. They don't know each other.
### 4 — The Pipeline Is Stateless
`router_pipe.py` holds no conversation state (Open WebUI owns that). It persists operational metrics to `metrics_state.json` for telemetry only — never for routing.
### 5 — Personas Live in config/personas/
One YAML per persona (`name`, `slug`, `module`, `workspace_model`, `category`, and `system_prompt` or `prompt_template`). `openwebui_init.py` seeds them. Catalog currently at `config/personas/` — currently 135 files (extractor-derived count — never hardcode it in prose).
### 6 — config/portal.yaml Is the Single Source of Truth
All workspaces and the MCP fleet live here. After any change run `./launch.sh sync-config` (idempotent). Never hand-edit the derived files: `config/backends.yaml` `workspace_routing`, `.mcp.json`, `imports/openwebui/workspaces/*.json`. Auto-routing: Layer 1 LLM intent classifier (default `gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`), Layer 2 weighted keyword fallback.
### 7 — All Ports Are Reserved
8080 OWUI · 9099 Pipeline · 8912 music · 8913 documents · 8914 sandbox · 8915 whisper · 8916 TTS · 8917 embedding (host MLX) · 8918 MLX speech (host) · 8919 security · 8920 memory · 8921 RAG · 8922 research · 8923 browser · 8924 MLX transcribe · 8925 reranker · 8926 CAD · 8927 proxmox · 8928 pipeline MCP · 8929 MITRE · 8930 binresearch · 8931 wiki · 8932 detections · 8933 MFLUX image · 8935 video-mlx · 8088 SearXNG · 11434 Ollama · 9090 Prometheus · 3000 Grafana. Enforced in `.env.example`. (Authoritative roster: `config/portal.yaml` `mcp_fleet`.)
### 8 — Single Inference Tier: Ollama
Never add `transformers` or `torch` to `portal/platform/inference/`. Model catalog + memory budgets in `config/backends.yaml`.
### 9 — The Dockerfile Split Is Intentional
`Dockerfile.pipeline` minimal (fastapi/uvicorn/httpx/pyyaml); `Dockerfile.mcp` heavier. Don't merge. Full image index (all 7 Dockerfiles, what each builds): `unit-fact-dockerfile-index`.
### 10 — Git Discipline
Commit to `main` during stabilization; `uv run pytest tests/ -q --tb=no` before every push; conventional commits; never force-push; never commit `.env`.
### 11 — Shared Workspace Is The Only Path For User Files
User files live at `${AI_OUTPUT_DIR}` (default `~/AI_Output/`), mounted at `/workspace`. Reads: `resolve_upload_path(file_id)`; writes: `get_generated_dir(category)` (categories: transcripts, documents, images, videos, music, speech). New Docker MCPs touching user files must mount `${AI_OUTPUT_DIR}:/workspace`.
### 12 — Docs Travel With The Work
Docs couple to code mechanically where mechanized: fact-unit currency is check `AW` (`scripts/validate_system.py`), drift census is `BS`, and generated views render from `portal_wiki/canonical/`. When a change touches a subsystem, update its fact-unit or authored unit in the same task. Never hardcode counts/ports/check-letters as prose — derive them at reconcile time.

`BS` (pre-push, not pre-commit) HARD-FAILs when a unit's declared `claims` no longer hold against a live probe, or a Tier-1 doc names a repo-relative path that no longer exists. A fact change is **one commit**: edit the fact-unit (or run `sync-config` to re-derive it) and commit — there is no pin, so there is nothing to re-stamp in a second commit. (Pre-P0 this required a `last_generated_commit` pin re-stamp as a mandatory second commit; `TASK_BULLY_P0_SPINE_REDUCTION_V1` A1 deleted that mechanism outright — see `docs/SPINE_THIN_CONTRACT_V1.md`.)
### 13 — Fact-Units Are the Discovery Index
Before grepping, query the wiki: `wiki_search` / `wiki_get_unit` / `wiki_explain`. Verify every edit anchor `count==1` against HEAD before editing.

## Testing Rules

- `tests/unit/` must pass with no network, no real Ollama/OWUI/Docker; `tmp_path` for I/O; mock `httpx.AsyncClient`.
- `pytest portal` (module-tree suite) leaves real write-through artifacts in `portal/modules/security/core/field_journal/` and `results/checkpoints/` — after running it, `git checkout -- portal/modules/security/core/field_journal/_index.json` and `git clean` new dated entries before staging.
- Pre-commit hooks: ruff lint+format, generated-artifact freshness, no duplicate dep pins, pytest unit suite. The `validate-system` hook runs the full lettered check suite (current count: `python3 scripts/validate_system.py`; registry under `scripts/validation/`) at **push** time. Install: `pip install pre-commit && pre-commit install && pre-commit install --hook-type pre-push`.
- **Before any testing/benchmark:** verify Docker images aren't stale vs HEAD (`docker images` vs `git log`); rebuild with `./launch.sh rebuild` if any portal image predates a relevant commit. Stale images invalidate results.
- **Checkpoint backup — non-negotiable:** multi-hour bench/sweep checkpoints (e.g. `/tmp/agentic_blue_sweep.json`) must be `cp`-backed-up before ever being cleared or overwritten.
- **Streaming changes MUST run `./scripts/smoke_stream.sh` against the live stack** before commit — unit mocks can't catch dependency-contract mismatches.

## Zero-Setup Requirements

Every feature works from `./launch.sh up`. Dependencies installable via pip/apt in the Dockerfile or a Docker service; degrade gracefully, never crash.

## Do Not

- Add `OLLAMA_BASE_URL` directly to OWUI env (everything goes through portal-pipeline)
- Import `portal.platform.inference` from an MCP module or vice versa
- Store conversation state in the Pipeline
- Add system Python packages to `Dockerfile.pipeline`
- Hardcode model names in Python (they come from backends.yaml / persona YAMLs)
- Use `docker compose down -v` in scripts (nukes Ollama models)
- Commit `.env`; skip tests

## Known Limitations

See `KNOWN_LIMITATIONS.md` before adding tasks or filing issues — some items are documented limitations, not bugs.

## Reference Docs

`config/backends.yaml` · `config/personas/` · `docs/HOWTO.md` (speech, transcription) · `docs/MCP_DEV_TOOLING.md` · `docs/CLUSTER_SCALE.md` · `docs/ADMIN_GUIDE.md` · `docs/ALERTS.md` · `config/PENDING_MODEL_VERDICTS.md` (bench-evaluated models awaiting a promote/decline decision — regenerate via `scripts/model_cleanup_audit.py`, `- [x]` lines persist across reruns).

## Portal Wiki — Canonical Knowledge Layer

`portal_wiki/canonical/` holds source-of-truth knowledge units. Agents query via `wiki.search`/`get_unit`/`explain`; operators edit canonical units directly — rendered views are generated. CLAUDE.md is the one intentional hand-authored exception to the generated-doc shell pattern.

