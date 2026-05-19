# Known Limitations

Architectural and design constraints that are currently unresolved. Resolved items are not listed here — see git log for history.

---

## Security

### Code Sandbox Requires Privileged Container
- **ID**: P5-ROAD-SEC-001
- **Description**: The `dind` (Docker-in-Docker) service runs with `privileged: true`. Docker-in-Docker cannot function without host kernel capabilities.
- **Impact**: In hardened environments, a compromised sandbox container could potentially escape to host.
- **Mitigation**: Disable the code sandbox by removing `mcp-sandbox` and `dind` from `docker-compose.yml`, or apply host-level controls (AppArmor/seccomp on the Docker daemon).

### No Built-in Multi-User Rate Limiting
- **ID**: P5-ROAD-031
- **Description**: Open WebUI has no per-user rate limiting. A single user in a multi-user deployment can exhaust server resources.
- **Mitigation**: Deploy behind a reverse proxy (nginx, Traefik) with rate limiting, or use Open WebUI's admin controls for per-user quotas.

---

## Infrastructure

### ComfyUI Runs Outside Docker
- **Description**: ComfyUI runs on the host (not in Docker) to access MPS/CUDA directly. Required for image/video generation performance.
- **Impact**: Manual setup required outside `./launch.sh up`. On a fresh machine, ComfyUI must be installed separately.
- **Mitigation**: `./launch.sh install-comfyui` handles setup on supported platforms. See `docs/COMFYUI_SETUP.md`.

### Voice Cloning (fish-speech) Requires Separate Installation
- **Description**: Voice cloning via `fish-speech` is not in the Docker stack — requires host-side installation.
- **Impact**: Voice cloning unavailable; TTS works via the included `kokoro-onnx` engine.
- **Mitigation**: `kokoro-onnx` provides TTS out of the box. See `docs/FISH_SPEECH_SETUP.md` for fish-speech.

---

## Models

### auto-math Workspace Has No Reasoning-Block Support
- **ID**: P5-MATH-001
- **Description**: `Qwen2.5-Math-7B-Instruct` does not emit `reasoning_content` blocks — math reasoning appears in the regular content stream. The collapsible thinking panel will not show separately for `auto-math` traffic. This is a model property, not a pipeline issue.
- **Alternative**: For extended thinking on math problems, `auto-reasoning` (Qwopus 27B) separates reasoning content.

### Asteroids Bench Score Variance Is the Benchmark's Purpose
- **ID**: P5-BENCH-001
- **Description**: The CC-01 Asteroids bench (`bench-*` workspaces) intentionally surfaces raw model differences on a fixed task. All bench personas share an identical creative-coder system prompt — score variance reflects model capability, not a test harness defect.
- **Operator action**: Use bench scores as model-selection signal. A model scoring ≤3/5 on CC-01 is not a candidate for `auto-coding` HTML generation tasks.

---

## MLX Proxy

### Single-Model Constraint: Concurrent Sessions Using Different MLX Models Cause Eviction Cycles
- **ID**: P5-MLX-010
- **Affects**: All frontends (Open WebUI, LibreChat) — any concurrent usage
- **Description**: The MLX proxy holds exactly one model in GPU memory at a time. When two browser tabs (or two conversations in the same frontend) target different MLX-backed models simultaneously, every request switch evicts the current model and loads the requested one. Each eviction+reload takes **30–90s for ≤26B models, 90–180s for 32–70B models**.
- **Trigger patterns**:
  - OWUI: switching between two open tabs that use different workspaces (e.g., `auto-daily` → `auto-reasoning`) while both are generating
  - LibreChat: navigating to a new conversation with `?endpoint=Portal+5&model=<workspace>` — the URL params cause background pipeline requests that can switch the loaded model even before the user sends a message
  - Any API client making concurrent requests to two different MLX workspaces
- **Impact**: The in-flight request on the first model is left waiting (or times out) while the proxy loads the second model. The first model reloads when that tab becomes active again. On a busy system this creates a thrashing loop where neither conversation makes progress.
- **This is a GPU memory constraint, not a software defect.** Apple Silicon M-series chips have a single unified memory pool; MLX loads the full model into it. There is no way to partially share GPU memory across two large models simultaneously.
- **Mitigation**:
  1. **Use the same workspace across open tabs.** Sessions sharing one MLX model (e.g., all tabs on `auto-daily`) never trigger eviction — the model stays loaded.
  2. **Prefer Ollama-backed workspaces for short, parallel tasks.** Ollama (GGUF models on port 11434) can hold multiple models in its cache and round-robins requests without full eviction. Good for `auto-coding`, `auto-security`, and other workspaces where conversational depth is short.
  3. **Avoid model-switching URL params in LibreChat.** Navigate to the conversation list (`:8082`) rather than `/c/new?endpoint=Portal+5&model=<name>` bookmarks — the latter fires background prefetch requests that switch the proxy before you type.
  4. **Single-user, sequential workflow.** The system is designed for one active MLX conversation at a time. Finishing one conversation before starting another in a different workspace avoids all eviction overhead.

### MLX Proxy Has Slow Startup (Cold Boot)
- **ID**: P5-ROAD-MLX-001
- **Description**: On cold boot or restart, the MLX proxy takes 60–300+ seconds to become ready while `mlx_lm.server` or `mlx_vlm.server` loads the model. The proxy returns HTTP 503 during this window — this is normal, not a crash.
- **Detection signals** (in order of reliability):
  1. `/health` returns `state: "ready"` with `loaded_model` set
  2. Server log `/tmp/mlx-proxy-logs/mlx_lm.log` contains "Starting httpd"
  3. `pgrep -f mlx_lm.server` or `mlx_vlm.server` returns a PID
- **Mitigation**: Test suite waits up to 300s. Only classify as crashed if no processes exist and no server logs are present.

### Laguna-XS.2 Requires Manual mlx_lm Plugin Files
- **ID**: P5-MLX-009
- **Description**: `mlx_lm` does not ship a Laguna architecture. Two plugin files are manually installed: `models/laguna.py` and `tool_parsers/laguna.py`. These are overwritten by any `mlx_lm` upgrade.
- **Mitigation**: After any `mlx_lm` upgrade, run `scripts/patch-mlx-threads.py` — it reinstalls the Laguna plugin files alongside the thread-local stream fix. Do not upgrade `mlx_lm` without re-running the patch.

### Deployed MLX Proxy Can Become Stale
- **ID**: P5-ROAD-MLX-002
- **Description**: `./launch.sh up` starts the MLX proxy from `~/.portal5/mlx/mlx-proxy.py`, a copy deployed by `./launch.sh install-mlx`. If `scripts/mlx-proxy.py` is updated but `install-mlx` is not re-run, the deployed copy is stale.
- **Impact**: Stale proxy may start but fail to serve requests (wrong model names, missing concurrency protection).
- **Mitigation**: Run `./launch.sh install-mlx` after any change to `scripts/mlx-proxy.py`.

### MLX Proxy Kill/Restart Causes Memory Churn
- **ID**: P5-ROAD-MLX-003
- **Description**: `stop_all()` uses `kill -9`, which does not allow graceful GPU memory release. Metal may take 15–30s to fully reclaim memory after a kill.
- **Impact**: Killing and restarting too quickly can cause the new server to fail GPU memory allocation.
- **Mitigation**: Wait 15s after killing MLX processes before restarting. The test suite enforces this wait automatically.

---

## Inference Performance

### Speculative Decoding Adds Memory Cost
- **ID**: P5-SPEC-001
- **Description**: Models with a draft assigned in `speculative_decoding.draft_models` load both target and draft simultaneously. Admission control accounts for this, but models with drafts require ~0.5–1GB more headroom.
- **Mitigation**: Remove the draft entry from `backends.yaml` and restart the proxy to disable spec decoding for a specific model.

### MTP Speculative Decoding Not Supported by MLX Proxy
- **ID**: P5-MTP-001
- **Severity**: LOW — enhancement opportunity
- **Description**: Multi-Token Prediction (3.94× speedup verified for Gemma 4 26B-A4B BF16) requires `--draft-model` and `--draft-kind mtp` flags. The proxy does not pass these. Deprioritized because even with MTP, the BF16 path (~12 TPS) is slower than current 4-bit MoE alternatives (25–40 TPS).
- **Resolution path**: TASK_MTP_PROXY_V1.md.

### 70B Dense Models Unusable for Daily Routing on M4 Pro 64GB
- **ID**: P5-SPEED-001
- **Description**: Llama-3.3-70B-Instruct-4bit and DeepSeek-R1-Distill-Llama-70B-4bit measure ~3.5 TPS warm — too slow for interactive use. 3-bit quantization (~28GB) is theoretically viable at ~9.7 TPS but not yet bench-validated.
- **Mitigation**: All daily-routed workspaces use ≤33B models. 70B variants are bench-tier only.

---

## Shared Workspace + Auto-STT Disabled (TASK-WORKSPACE-001)

- **Voice-input via microphone is disabled.** `AUDIO_STT_ENGINE` is empty by default, which disables auto-transcription of both file uploads and microphone recordings. Re-enabling it re-enables auto-transcribe-on-upload. The global toggle is OWUI's only knob.
- **Existing MCPs not migrated to /workspace.** `mcp-documents`, `mcp-tts`, and `mcp-comfyui` still write to `${AI_OUTPUT_DIR}` flat. New MCPs use `/workspace/generated/<category>/`. Both layouts coexist; migration is opportunistic.
- **Permissions assume single-host deployment.** 0775 mode on workspace directories assumes operator-owned files and compatible Docker UIDs. Multi-tenant or hardened hosts need explicit UID mapping.
- **No retention policy.** `${AI_OUTPUT_DIR}` grows unbounded. `./launch.sh workspace-clean --age=Nd` is a planned but not yet implemented command.

---

## Diarized Transcription (TASK-TRANSCRIBE-001)

- **Pyannote model gating.** Diarization requires accepting HuggingFace user agreements for `pyannote/segmentation-3.0` and `pyannote/speaker-diarization-3.1`. Without `HF_TOKEN` in `.env` and licenses accepted, diarization calls return 500.
- **Overlapping speech.** Pyannote 3.1 underperforms when multiple speakers talk simultaneously. Segments are assigned to a single speaker by maximum overlap.
- **Speaker count drift on long recordings.** For recordings >15–30 min, pyannote may split one speaker into two IDs after long silence gaps. Pass `num_speakers=N` if known.
- **OWUI tool-call timeout for long files.** OWUI's default MCP timeout is shorter than processing time for files >5 min. Raise `TOOL_SERVER_REQUEST_TIMEOUT` (e.g., 1800s) or use the direct endpoint at `:8924`.
- **MLX path is macOS-only.** `scripts/mlx-transcribe.py` requires Apple Silicon. The Docker `whisper_mcp.py` fallback (faster-whisper + pyannote on CPU/CUDA) is the cross-platform alternative.

---

## OWUI Audio Drop UX (TASK-OWUI-AUDIO-DROP-001)

- **OWUI internal 60s tool-call ceiling.** Some OWUI builds enforce a hard internal timeout on tool execution that `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` does not affect (open-webui/open-webui#16902). When this fires, the tool completes server-side but the persona never sees the result. Use `scripts/transcribe_and_complete.sh` for files with wall time >60s.
- **WEBUI_SECRET_KEY rotation invalidates OAuth tokens.** If `.env` is regenerated and the secret key changes, all MCP OAuth tools need re-authentication.
- **Microphone voice input remains disabled.** Unchanged from TASK-WORKSPACE-001 trade-off.

---

*Last updated: 2026-05-19*
