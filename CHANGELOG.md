# Changelog

All notable changes to Portal 5 will be documented in this file.

## [6.0.1] - 2026-04-11

### Security
- **CRITICAL**: Removed insecure default API key fallback — pipeline now fails closed when `PIPELINE_API_KEY` is unset (P5-SEC-001)
- **CRITICAL**: Removed `privileged: true` from DinD sandbox to prevent container escape; migrated to rootless `docker:27-dind-rootless` (P5-SEC-002)

### Fixed
- Removed global warning suppression in MCP server; exceptions now log full tracebacks (P5-OBS-001)
- Removed dead code: `_complete_from_backend()` in `router_pipe.py` (P5-MAINT-001)
- Fixed duplicate `_MLX_PROXY_HEALTH_URL` assignment in `dispatcher.py` (P5-MAINT-002)

### Changed
- Native service startup errors now logged to `~/.portal5/logs/` instead of `/dev/null` (P5-OBS-002)
- JSON parsing in `launch.sh` uses `jq` when available for faster status checks (P5-PERF-001)

### Documentation
- Fixed AudioCraft → HuggingFace MusicGen terminology in README (P5-DOCS-001)
- Fixed version drift: aligned all headers to 6.0.1 (P5-DOCS-002)
- Added network exposure security documentation with local-only override option (P5-DOCS-003)
- Clarified privacy claims regarding model download telemetry (P5-DOCS-004)
- Updated persona count in CLAUDE.md from 42 to 44 (P5-MAINT-003)

### Tests
- Added `TestCodeHygiene` regression prevention tests (P5-TEST-001)
- Fixed test suite to set `PIPELINE_API_KEY` via `conftest.py` for hard-fail API key enforcement
- Fixed `HEADERS` in `test_pipeline.py` to read from env rather than hardcoded default key

---

## [Unreleased]

### Added
- **Unified update command** (`launch.sh`)
  - `./launch.sh update`: Single command to update all components — git pull, Docker image pulls
    (ollama, open-webui, searxng), rebuild portal-pipeline + all MCP server images, refresh Ollama
    models, pull MLX models (Apple Silicon), update ComfyUI + VideoHelperSuite (if installed),
    upgrade Music MCP deps (if installed), force re-seed Open WebUI presets, and restart the stack.
  - `--skip-models`: Skip Ollama + MLX model refresh for faster updates.
  - `--models-only`: Only refresh models without touching Docker images or code.
  - `-y` / `--yes`: Skip confirmation prompts.
  - Non-destructive: models are refreshed (ollama pull / snapshot_download) — nothing is deleted.
    HuggingFace cache deduplicates, Ollama pulls only changed layers.
  - All existing update commands (`rebuild`, `refresh-models`, `pull-mlx-models`, `install-comfyui`,
    `install-music`, `seed`) remain available for granular control.

## [6.0.0] — 2026-04-07

### Breaking Changes
- None. All existing workspace IDs, personas, and API contracts are unchanged.

### Added
- **P5-FUT-006: LLM-based intent routing** (`portal_pipeline/router_pipe.py`)
  - `_route_with_llm()`: Uses `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` (uncensored abliterated) as
    primary semantic intent classifier for the `auto` workspace. Temperature=0, 40 tokens,
    512-token context, `keep_alive=-1` (always warm).
  - Falls back to existing `_detect_workspace()` keyword scoring on low confidence
    (`LLM_ROUTER_CONFIDENCE_THRESHOLD`, default 0.5) or timeout
    (`LLM_ROUTER_TIMEOUT_MS`, default 500ms).
  - Ollama grammar-enforced JSON schema guarantees parseable output.
  - Workspace ID validated against `_VALID_WORKSPACE_IDS` allowlist — unknown IDs
    trigger keyword fallback rather than routing errors.
  - `config/routing_descriptions.json`: Operator-editable workspace capability descriptions
    used as the LLM's grounding context.
  - `config/routing_examples.json`: Operator-editable few-shot examples (25 included;
    add domain-specific examples to improve accuracy for your use cases).
  - `tests/unit/test_routing.py`: 16 new unit tests (mock-only, no Ollama required).
  - Env vars: `LLM_ROUTER_ENABLED`, `LLM_ROUTER_MODEL`, `LLM_ROUTER_CONFIDENCE_THRESHOLD`,
    `LLM_ROUTER_TIMEOUT_MS`, `LLM_ROUTER_OLLAMA_URL`.
  - Expected accuracy: 93-94% (see P5_ROADMAP.md for workspace-level breakdown).

- **P5-FUT-009: Model-size-aware admission control** (`scripts/mlx-proxy.py`)
  - `MODEL_MEMORY` dict: 16 entries mapping each MLX model → estimated peak GB.
  - `_check_memory_for_model()`: Pre-flight check in `ensure_server()` comparing
    `MODEL_MEMORY[model] + MEMORY_HEADROOM_GB` against `_get_available_memory_gb()`.
  - Rejects with HTTP 503 and operator-actionable message before evicting any loaded model,
    preventing OOM from conflicting model+ComfyUI loads.
  - Unknown models use `MEMORY_UNKNOWN_DEFAULT_GB` (default 20GB) — conservative but not blocking.
  - CLAUDE.md coexistence rules are now self-enforcing rather than documentation-only.
  - `tests/unit/test_mlx_proxy.py`: 9 new unit tests (mocked memory reads, no MLX runtime).
  - Env vars: `MLX_MEMORY_HEADROOM_GB` (default 10.0), `MLX_MEMORY_UNKNOWN_DEFAULT_GB` (default 20.0).

- **`auto-spl` workspace**: Splunk SPL query authoring, pipeline explanation, detection search
  - Routes `[mlx, coding, general]` — MLX Qwen3-Coder-30B-A3B-Instruct-8bit primary,
    deepseek-coder-v2:16b-lite-instruct-q4_K_M Ollama fallback
  - `_SPL_KEYWORDS` weighted dict + scoring for content-aware routing from `auto` workspace
  - New `splunksplgineer` persona with hardened SPL constraints
  - 16 new unit tests in `TestSPLWorkspace`
  - Workspace count: 15 → 16

- **`auto-agentic` workspace**: Long-horizon agentic coding via Qwen3-Coder-Next-4bit (80B MoE)
  - Routes `[mlx, coding, general]` — `mlx-community/Qwen3-Coder-Next-4bit` MLX primary
  - `context_limit: 32768` for KV cache suppression (P5-BIG-001)
  - Keyword triggers: agentic, swe-agent, openhands, multi-file, long-horizon
  - Workspace count: 16 → 17

- **`auto-compliance` workspace**: NERC CIP gap analysis and policy-to-standard mapping
  - Routes `[mlx, reasoning, general]` — MLX Qwen3.5-35B-A3B-8bit primary,
    DeepSeek-R1-32B Ollama fallback
  - `_COMPLIANCE_KEYWORDS` weighted dict + scoring for content-aware routing
  - System prompt: structured gap table output with CIP requirement citations
  - CIP-003-9 R1 Part 1.2.6 priority flagging built into prompt
  - Two new personas: `nerccipcomplianceanalyst`, `cippolicywriter`
  - 8 new unit tests in `TestComplianceWorkspace`
  - Workspace count: 14 → 15 (after SPL at 16, after agentic at 17)

- **`auto-mistral` workspace**: Strategic analysis, business reasoning
  - Routes `[mlx, reasoning, general]` — MLX Magistral-Small-2509-8bit primary
  - `_MISTRAL_KEYWORDS` weighted dict + scoring for content-aware routing
  - New `magistralstrategist` persona (category: reasoning)

- **`gemma-4-31b-it-4bit` MLX model**: Vision and research tasks
  - New `gemmaresearchanalyst` persona (category: research)
  - Replaces older `gemma-4-26B-A4B` reference

- **portal_pipeline/notifications/channels/webhook.py**: New `WebhookChannel` sends JSON POST
  to any user-defined `WEBHOOK_URL` on all operational alert and daily summary events.
  Configure via `WEBHOOK_URL` (required) and optional `WEBHOOK_HEADERS` (JSON object).

- **config/grafana/dashboards/portal5_overview.json** (v2→v3): Added 6 new Usage Analytics
  panels — Requests by Workspace Over Time, Tokens by Workspace, Top 10 Workspaces by Volume,
  Model Distribution per Workspace, Current Request Rate.

- **`auto-mistral` and `auto-compliance` keyword routing** (`router_pipe.py`):
  Added `_COMPLIANCE_KEYWORDS` and `_MISTRAL_KEYWORDS` to `_WORKSPACE_ROUTING` —
  previously these workspaces were only reachable via LLM router; keyword fallback now works.

### Acceptance Test Suite (v4)

- **5 new test sections** (S18-S22): image/video MCP tool calls, Telegram/Slack channel adapters,
  notifications/alerts, MLX proxy model switching
- **Execution order**: Reordered `ALL_ORDER` to group by backend (Ollama → MLX → ComfyUI → no-LLM)
  — reduces backend transitions from ~20 to 12
- **7 prompt/signal fixes**: Fixed signal words that wouldn't appear in valid responses
- **Removed** `portal5_acceptance_v3.py` (orphaned, not referenced anywhere)

### Changed

## [5.2.1] - 2026-03-30

### Fixed
- **launch.sh**: Docker Compose no longer starts with empty `PIPELINE_API_KEY` — `launch.sh up`
  now symlinks `.env` into `deploy/portal-5/` so docker compose auto-loads it.
  Previously the pipeline fell back to the insecure default key on every restart.
- **launch.sh + config/searxng/settings.yml**: SearXNG no longer crashes on restart with
  "server.secret_key is not changed" — `launch.sh up` now injects `SEARXNG_SECRET_KEY`
  from `.env` directly into `settings.yml` before starting the container.
  (SearXNG reads `secret_key` from settings.yml, not from env vars.)

### Changed
- **launch.sh**: Added symlink step for `.env` to `deploy/portal-5/` in `up`, `up-telegram`,
  `up-slack`, and `up-channels` commands.
- Version bumped 5.2.0 → 5.2.1 across `pyproject.toml`, `portal_pipeline/__init__.py`,
  `portal_mcp/__init__.py`, `portal_channels/__init__.py`, and `CLAUDE.md`.

## [5.2.0] - 2026-03-30

### Fixed
- **router_pipe.py**: Replaced all `assert` statements in HTTP handlers with proper
  `HTTPException(503)` raises — assertions are silently elided by Python `-O` flag,
  which would cause AssertionError in optimised deployments (lines 517, 542, 605, 617, 713, 761)
- **router_pipe.py**: Sanitised backend error messages returned to clients — internal
  URLs, stack traces, and backend response bodies are now logged server-side only;
  clients receive generic "Backend returned HTTP NNN" / "check server logs" messages
- **router_pipe.py**: Version string now reads from `importlib.metadata` (single
  source of truth: `pyproject.toml`) instead of a hardcoded literal
- **router_pipe.py**: Added `BackendRegistry.close_health_client()` call in lifespan
  shutdown — previously the shared health-check connection pool was never drained
- **cluster_backends.py**: `yaml.safe_load()` now wrapped in `try/except yaml.YAMLError`
  — a malformed backends.yaml previously crashed silently; now logs a clear error and
  returns an empty registry (all requests return 503 with an actionable message)
- **cluster_backends.py**: Added `close_health_client()` classmethod — cleans up the
  shared httpx client on shutdown to prevent connection pool leaks
- **tts_mcp.py**: Fish Speech backend device detection now auto-selects mps/cuda/cpu
  instead of hardcoding `device="mps"` (broke on Linux CUDA and CPU-only systems)
- **music_mcp.py**: Stable Audio backend device detection now auto-selects mps/cuda/cpu
  using the same priority order (was hardcoded `cuda or cpu`, missing Apple Silicon MPS)
- **test_mcp_endpoints.py**: Added module-level `pytest.importorskip` guards for
  `fastmcp` and `portal_mcp.generation.tts_mcp` — MCP endpoint tests now SKIP cleanly
  instead of ERROR when MCP dependencies are not installed (resolves P5-ROAD-107)
- **docker-compose.yml**: Added `cpus: "4.0"` limit to DinD service — previously only
  memory was bounded; an unterminated container process could consume all host CPU

### Added
- **.env.example**: Documented 8 previously undocumented environment variables used by
  Python code: `OPENWEBUI_ADMIN_NAME`, `PIPELINE_PORT`, `PIPELINE_URL`,
  `PIPELINE_TIMEOUT`, `BACKEND_CONFIG_PATH`, `PROMETHEUS_MULTIPROC_DIR`, `MODELS_DIR`
  (resolves P5-ROAD-146)

### Changed
- Version bumped 5.1.0 → 5.2.0 across `pyproject.toml`, `portal_pipeline/__init__.py`,
  `portal_channels/__init__.py`, `CLAUDE.md`

---

## [5.1.0] - 2026-03-06

### Fixed
- Content-aware routing: removed false-positive keywords ("go ", "apt", "attack")
- Melody conditioning in generate_continuation() was silently dropped — now
  uses AudioCraft generate_with_chroma() for actual melody conditioning
- FastAPI app version string: 5.0.0 → 5.1.0
- CLAUDE.md workspace routing table: 9 stale model_hints updated
- CLAUDE.md architecture line: MLX port 8080 → 8081
- BackendRegistry._health_timeout: added defensive default in __init__

### Changed
- Broken mlx-vlm models (Qwen3.5-35B-A3B-4bit, Qwen3.5-27B-4bit) commented
  out from MLX backend — only mlx-vlm conversions exist, incompatible with
  mlx_lm.server. Will uncomment when mlx-lm community quants are published.
- Added qwen3-coder:30b to Ollama coding group (correct tag, replaces
  nonexistent qwen3-coder:32b)
- Added deepseek-r1:32b-q4_k_m to Ollama security group for threat modeling
- install-mlx now pins mlx-lm>=0.30.5 (required for Qwen3-Coder-Next support)
- Version bump to 5.1.0 across pyproject.toml, __init__.py files, CLAUDE.md

### Improved
- Agent prompt v5: added mlx-vlm compatibility check and melody conditioning test
- Agent prompt v4: corrected all stale port/model references
- P5_AUDIT_REPORT.md updated for v5.1.0

## [5.0.2] - 2026-03-05

### Fixed
- SearXNG: removed literal `${SEARXNG_SECRET_KEY}` from settings.yml — was never
  interpolated; SearXNG now reads `SEARXNG_SECRET_KEY` env var directly
- Prometheus: removed scrape job for `open-webui/metrics` (endpoint doesn't exist)
- Audio TTS/STT: moved config from broken `/api/v1/configs/audio` API call to
  compose environment variables (`AUDIO_TTS_ENGINE`, `AUDIO_STT_ENGINE`)
- Dockerfile.mcp: added `espeak-ng` and `libespeak-ng1` required by kokoro-onnx
- backends.yaml: corrected `unsloth/GLM-4.7-Flash` → `hf.co/unsloth/GLM-4.7-Flash-GGUF`
- Grafana: added datasource `uid: prometheus` required for dashboard panel wiring
- Grafana: created `portal5_overview.json` dashboard (was missing despite provisioning config)
- SearXNG healthcheck: `/healthz` → `/` (correct endpoint)
- configure_tool_settings: removed call to non-existent `/api/v1/configs/features`
- pyproject.toml: `stable-audio_tools` → `stable-audio-tools` (underscore typo)
- comfyui-model-init: extracted one-liner to `scripts/download_comfyui_models.py`
- cluster_backends.py: auto-detects config path for local dev (no more startup error)
- mcp-tts: added `/v1/audio/speech` OpenAI-compatible endpoint for Open WebUI TTS
- mcp-whisper: added `/v1/audio/transcriptions` OpenAI-compatible endpoint for STT
- test_semaphore.py: fixed failing test by using lifespan context manager
- wan2.2 download: use `snapshot_download` instead of `hf_hub_download` with `None` filename
- Port bindings: restricted internal services to `127.0.0.1` (Ollama, MCP servers,
  Prometheus, SearXNG, ComfyUI) to prevent unintended LAN exposure
- tts_mcp.py: consolidated 6 redundant in-function `JSONResponse` imports to top-level
- Added `TTS_DEFAULT_VOICE` to `.env.example`

### Added
- OpenAI-compatible `/v1/models` endpoint on mcp-tts and mcp-whisper
- Test coverage for TTS/STT endpoints, model hint routing, workspace routing completeness
- `scripts/download_comfyui_models.py` supporting flux-schnell, flux-dev, sdxl, wan2.2

## [5.0.0] - 2026-03-03

### Added
- Zero-setup web search via SearXNG integration
- Zero-setup image generation via ComfyUI in Docker
- Zero-setup TTS via kokoro-onnx (with optional fish-speech)
- Zero-setup metrics via Prometheus + Grafana
- 13 workspace routing configurations (auto, auto-coding, auto-security, etc.)
- Model hint routing for security, coding, reasoning, vision workspaces
- Health-aware backend registry with automatic fallback
- Concurrency limiting via semaphore with 503 + Retry-After
- MCP Tool Servers: Documents, Music, TTS, Whisper, ComfyUI, Video, Sandbox
- Telegram bot channel adapter
- Slack bot channel adapter
- Backup/restore documentation
- Comprehensive CLAUDE.md for AI-assisted development

### Changed
- Updated model catalog with DeepSeek-R1, Qwen3-Coder, BaronLLM variants
- Test coverage improved to 72%
- Production readiness score: 92/100

### Security
- Auto-generated secrets via openssl
- DinD sandbox (no host docker.sock)
- API key authentication on all Pipeline endpoints

### Infrastructure
- Docker Compose with 18 services
- Healthchecks on all critical services
- Volume management for persistence

---

**Portal 5** is an Open WebUI intelligence layer that provides a complete local AI platform covering text, code, security, images, video, music, documents, and voice — all running on local hardware.