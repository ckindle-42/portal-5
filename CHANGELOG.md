# Changelog

All notable changes to Portal 5 will be documented in this file.

## [Unreleased] - 2026-03-03

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