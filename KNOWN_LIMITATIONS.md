# Known Limitations

Architectural and design constraints that cannot be resolved without significant tradeoffs. These are accepted as part of Portal 5's design.

---

## Security

### Code Sandbox Requires Privileged Container
- **ID**: P5-ROAD-SEC-001
- **Description**: The `dind` (Docker-in-Docker) service runs with `privileged: true`. Docker-in-Docker cannot function without host kernel capabilities.
- **Impact**: In hardened environments, a compromised sandbox container could potentially escape to host.
- **Mitigation**: Either disable the code sandbox by removing `mcp-sandbox` and `dind` services from `docker-compose.yml`, or apply host-level controls (AppArmor/seccomp profile on the Docker daemon).
- **Last verified**: 2026-03-30

### No Built-in Multi-User Rate Limiting
- **ID**: P5-ROAD-031
- **Description**: Open WebUI does not have per-user rate limiting. A single user in a multi-user deployment could exhaust server resources.
- **Mitigation**: Deploy behind a reverse proxy (nginx, Traefik) with rate limiting, or use Open WebUI's admin controls to set per-user quotas.
- **Last verified**: 2026-03-03

---

## Infrastructure

### ComfyUI Runs Outside Docker
- **Description**: ComfyUI runs on the host (not in Docker) to access GPU directly (MPS on Apple Silicon, CUDA on NVIDIA). This is required for image/video generation performance.
- **Impact**: Manual setup required outside the `./launch.sh up` flow. On first run after a fresh machine, ComfyUI must be installed separately.
- **Documentation**: See `docs/COMFYUI_SETUP.md`
- **Mitigation**: `./launch.sh install-comfyui` handles the setup on supported platforms.
- **Last verified**: 2026-03-03

### Voice Cloning (fish-speech) Requires Separate Installation
- **Description**: Voice cloning via `fish-speech` is not included in the Docker stack — it requires host-side installation.
- **Impact**: Voice cloning is unavailable; TTS still works via the included `kokoro-onnx` engine.
- **Documentation**: See `docs/FISH_SPEECH_SETUP.md`
- **Mitigation**: `kokoro-onnx` provides text-to-speech out of the box with no extra setup.
- **Last verified**: 2026-03-03

---

## Models

### Persona workspace_model Values Fixed
- **ID**: P5-ROAD-MOD-001
- **Status**: **RESOLVED**
- **Description**: 9 persona YAMLs had `workspace_model` values that were either invalid Ollama identifiers or referenced HuggingFace paths that don't exist.
- **Root cause**: Ollama's `hf.co/` prefix imports models from HuggingFace under local Ollama names. The persona YAMLs were using HuggingFace paths directly (e.g., `hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF`) which don't exist — the correct path is `bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF` and it's imported as `deepseek-r1:32b-q4_k_m`.
- **Resolution**:
  - `redteamoperator` → `baronllm:q6_k` (imported from `hf.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF`); alternative: `xploiter/the-xploiter`
  - `blueteamdefender` → `lily-cybersecurity:7b-q4_k_m` (imported from `hf.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF`); alternative: `huihui_ai/baronllm-abliterated`
  - `dataanalyst`, `datascientist`, `machinelearningengineer`, `statistician`, `itarchitect`, `researchanalyst`, `excelsheet` → `deepseek-r1:32b-q4_k_m` (the HF path `hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF` doesn't exist; correct import is via `bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF`); alternative: `huihui_ai/tongyi-deepresearch-abliterated`
- **Last verified**: 2026-04-01

---

## Seeding / Init

### `openwebui-init` Skips Existing Personas and Workspaces on Re-Seed
- **ID**: P5-ROAD-INIT-001
- **Status**: **RESOLVED** — `./launch.sh reseed` now force-deletes and recreates all presets.
- **Description**: `scripts/openwebui_init.py` detects existing model presets and skips them on subsequent runs. The upsert path (PUT/POST to update) returns HTTP 405 against Open WebUI v0.6.5.
- **Resolution**: 
  - Discovered correct OW v0.6.5 API: `POST /api/v1/models/create` (create), `DELETE /api/v1/models/model/delete?id=` (delete), `POST /api/v1/models/model/update?id=` (update)
  - Added `FORCE_RESEED` env var to `openwebui_init.py` — deletes then recreates every preset
  - `./launch.sh reseed` invokes this path: delete all → recreate all with current YAML content
  - Also fixed: `base_model_id` must be set in all presets — OW v0.6.5 `get_models()` filters `WHERE base_model_id IS NOT NULL`, so presets without it are invisible to users
- **Usage**: After editing persona YAMLs or workspace JSONs, run `./launch.sh reseed` to push changes live.
- **Last verified**: 2026-04-01

---

## MLX Proxy

### MLX Proxy Has Slow Startup (Cold Boot)
- **ID**: P5-ROAD-MLX-001
- **Status**: **ACTIVE**
- **Description**: The MLX proxy (`scripts/mlx-proxy.py`) runs host-native on Apple Silicon. On cold boot or restart, it takes 60-300+ seconds to become ready, depending on the model being loaded. During startup, the proxy returns HTTP 503. This is normal — the proxy process is up but the underlying `mlx_lm.server` or `mlx_vlm.server` is still loading the model into GPU memory.
- **Impact**: Any test or user request sent to the MLX proxy before it finishes loading will receive HTTP 503. The test suite must WAIT for MLX to become ready rather than classifying 503 as a crash.
- **Detection signals** (in order of reliability):
  1. Server log: `/tmp/mlx-proxy-logs/mlx_lm.log` or `mlx_vlm.log` contains "Starting httpd" when ready
  2. `/health` endpoint returns `state: "ready"` with `loaded_model` set
  3. `pgrep -f mlx-proxy.py` returns a PID (proxy process is running)
  4. `pgrep -f mlx_lm.server` or `mlx_vlm.server` returns a PID (server process is running)
- **Mitigation**: Test suite waits up to 300s for MLX readiness. If processes exist but proxy isn't ready, it's STARTING (not crashed). Only classify as crashed if no processes exist and no server logs are present.
- **Last verified**: 2026-04-05

### Deployed MLX Proxy Can Become Stale
- **ID**: P5-ROAD-MLX-002
- **Status**: **ACTIVE**
- **Description**: `./launch.sh up` starts the MLX proxy from `~/.portal5/mlx/mlx-proxy.py`, which is a copy deployed by `./launch.sh install-mlx`. If the repo version (`scripts/mlx-proxy.py`) is updated but `install-mlx` is not re-run, the deployed copy will be stale. The deployed proxy may have outdated model lists, missing health monitoring, or missing concurrency protection.
- **Impact**: MLX proxy may start but fail to serve requests (wrong model names, no watchdog, no thread safety). The test suite's crash remediation starts the proxy from `scripts/mlx-proxy.py` (repo version), which bypasses this issue.
- **Mitigation**: Run `./launch.sh install-mlx` after updating `scripts/mlx-proxy.py`. The test suite detects stale deployed proxy by comparing file sizes and falls back to using the repo version.
- **Last verified**: 2026-04-05

### MLX Proxy Kill/Restart Causes Memory Churn
- **ID**: P5-ROAD-MLX-003
- **Status**: **ACTIVE**
- **Description**: The MLX proxy's `stop_all()` uses `kill -9` which doesn't allow graceful GPU memory release. Rapid model switching (e.g., testing 5 workspaces routing to 4 different MLX models) creates massive memory churn. After kill, Metal GPU memory may take 15-30s to fully reclaim.
- **Impact**: If the proxy is killed and restarted too quickly, the new server process may fail to allocate GPU memory, resulting in crashes or degraded performance.
- **Mitigation**: Test suite waits 15s after killing MLX processes for memory reclamation. The test suite also avoids killing MLX when it's in "starting" state — it waits for startup to complete instead.
- **Last verified**: 2026-04-05

---

### Video Generation — HunyuanVideo Model Loading Unsupported
- **ID**: P5-VIDEO-001
- **Status**: **ACTIVE**
- **Description**: The HunyuanVideo sharded model in `models/diffusion_models/hunyuan-video/` cannot be loaded by ComfyUI's `UNETLoader` — it returns "Could not detect model type". The `DiffusersLoader` (deprecated) also fails on the HunyuanVideo diffusers-format directory. End-to-end video generation via `portal_mcp/generation/video_mcp.py` is blocked until ComfyUI adds native HunyuanVideo support or the required custom nodes are installed.
- **Impact**: C8 acceptance tests (video generation via MCP) submit workflows that execute and complete but produce no video output. The MCP tool returns `success: false, error: "Generation completed but no video output found"`.
- **Mitigation**: Video generation workflows (auto-video workspace, `generate_video` MCP tool) gracefully degrade to returning descriptive failure messages. Pipeline round-trips (C9) remain fully functional for video description and planning tasks. To enable video generation, install the HunyuanVideo ComfyUI custom nodes package.
- **Last verified**: 2026-04-06

### SDXL Image Generation — Slow on Apple Silicon MPS
- **ID**: P5-COMFY-001
- **Status**: **ACTIVE**
- **Description**: SDXL generation at 25 steps, 1024×1024 exceeds 5 minutes on Apple M4 MPS. The acceptance test C6 timeout (300s) fires before generation completes, and cascading C7 tests time out while SDXL is still running in the ComfyUI queue.
- **Impact**: C6-02 and C7-02/03/04 acceptance tests report WARN (timeout). The images ARE generated eventually; the issue is test timeout, not generation failure.
- **Mitigation**: FLUX schnell (4 steps) and SDXL with fewer steps work within timeout. Reduce SDXL steps to ≤8 in test parameters for faster validation.
- **Last verified**: 2026-04-06

---

*Last updated: 2026-04-06*
