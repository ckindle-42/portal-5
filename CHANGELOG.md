# Changelog

All notable changes to Portal 5 will be documented in this file.

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