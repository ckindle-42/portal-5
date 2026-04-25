# Known Limitations

Architectural and design constraints that cannot be resolved without significant tradeoffs. These are accepted as part of Portal 5's design.

---

## Security

### Code Sandbox Requires Privileged Container
- **ID**: P5-ROAD-SEC-001
- **Description**: The `dind` (Docker-in-Docker) service runs with `privileged: true`. Docker-in-Docker cannot function without host kernel capabilities.
- **Impact**: In hardened environments, a compromised sandbox container could potentially escape to host.
- **Mitigation**: Either disable the code sandbox by removing `mcp-sandbox` and `dind` services from `docker-compose.yml`, or apply host-level controls (AppArmor/seccomp profile on the Docker daemon).
- **Last verified**: 2026-04-06

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

### auto-math Workspace Has No Reasoning-Block Support
- **ID:** P5-MATH-001
- **Status:** ACTIVE
- **Description:** `Qwen2.5-Math-7B-Instruct` does not emit `reasoning_content` blocks — math reasoning appears in the regular content stream. The collapsible thinking panel will not show separately for `auto-math` traffic. This is a model property, not a pipeline issue. For extended thinking on math problems, `auto-reasoning` (Qwopus 27B) is an alternative.

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

### DeepSeek-Coder-V2-Lite-Instruct-8bit Removed (Gibberish Output)
- **ID**: P5-MLX-005
- **Status**: **RESOLVED** — model removed from `config/backends.yaml` MLX list 2026-04-25
- **Description**: The MLX-converted `mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit` produced garbled Unicode output in V4 acceptance test S40 #229 (run dated 2026-04-10). Stale `backends.yaml` comment still claimed it as auto-spl primary; `router_pipe.py:404` had already swapped to `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit` due to "consistent 120s timeouts."
- **Replacement**: `huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit` added to MLX catalog. Selected for: GLM lineage (new to MLX tier), 59.2% SWE-bench, 79.5% τ²-Bench tool use, abliterated by trusted provider, ~18GB.
- **Last verified**: 2026-04-25

### Huihui-GLM-4.7-Flash-abliterated-mlx-4bit: Empty Output on Apple Silicon
- **ID**: P5-MLX-006
- **Status**: **CONFIRMED BROKEN — produces empty content on Apple Metal**
- **Description**: Benchmark on 2026-04-25 (M4 Pro, 64GB, mlx-lm 0.31.1) shows `Huihui-GLM-4.7-Flash-abliterated-mlx-4bit` loads and reports non-zero TPS (30.9 avg) but `choices[0].message.content` is always empty string across all 3 runs. The model generates `usage.completion_tokens=256` (max) but produces no readable text. This confirms the model card warning: *"This is just the MLX model we generated under Linux using mlx-lm version 0.30.3; it hasn't been tested in an Apple environment."*
- **Diagnosis**: Confirmed at the mlx_lm server level (port 18081, bypassing proxy): `usage.completion_tokens=20` but `content=""`. The server generates tokens but they all decode to empty string — a tokenizer vocabulary mapping defect in the Linux conversion. Not a proxy or test harness issue; other models produce text through identical code paths.
- **Impact**: Quality score = 0.00; TPS×Q = 0.0. The model is non-functional for inference.
- **Next steps**: Monitor huihui-ai HF discussions for Apple Metal fix; alternatively find an mlx-community conversion of GLM-4.7-Flash-abliterated. Model remains in `backends.yaml` and `ALL_MODELS` (registered) for when a fixed conversion becomes available — remove if no fix in 60 days.
- **Acceptance test**: S23-07 will FAIL or WARN on this model — expected until upstream fixes the conversion.
- **Last verified**: 2026-04-25

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

### mlx_vlm utils.py Patch Required for JANG Mixed-Precision Model
- **ID**: P5-ROAD-MLX-004
- **Status**: **ACTIVE**
- **Description**: `dealignai/Gemma-4-31B-JANG_4M-CRACK` uses mixed-precision quantization: embed/MLP layers are 4-bit (pack_factor=8), attention projections are 8-bit (pack_factor=4). mlx_vlm 0.4.4 (latest as of 2026-04-12) applies a single global `bits` value to all layers, causing shape mismatches on every attention weight.
- **Fix applied**: `/opt/homebrew/lib/python3.14/site-packages/mlx_vlm/utils.py` was patched to support `quantization_bits_per_layer_type` in config.json — a dict mapping layer-name substring to per-type bit depth. JANG's config.json has `{"self_attn": 8}` which triggers a two-pass `nn.quantize`: attention layers at 8-bit, embed/MLP at 4-bit (default). See `scripts/convert_jang_keys.py` for the full config patch logic.
- **Impact if mlx_vlm is upgraded**: The utils.py patch will be overwritten by the new install. Re-apply the two-pass quantization block from `scripts/convert_jang_keys.py`'s docstring, or re-run `scripts/convert_jang_keys.py` which will warn if the patch is missing (future improvement).
- **Workaround if patch is lost**: Run `brew upgrade mlx-vlm` then re-apply patch from git history (`git show d1d07af -- scripts/convert_jang_keys.py` explains the change; the utils.py diff is in the session that produced commit `d1d07af`).
- **Last verified**: 2026-04-12

### Deployed MLX Proxy Can Become Stale
- **ID**: P5-ROAD-MLX-002
- **Status**: **ACTIVE**
- **Description**: `./launch.sh up` starts the MLX proxy from `~/.portal5/mlx/mlx-proxy.py`, which is a copy deployed by `./launch.sh install-mlx`. If the repo version (`scripts/mlx-proxy.py`) is updated but `install-mlx` is not re-run, the deployed copy will be stale. The deployed proxy may have outdated model lists, missing health monitoring, or missing concurrency protection.
- **Impact**: MLX proxy may start but fail to serve requests (wrong model names, no watchdog, no thread safety). The test suite's crash remediation starts the proxy from `scripts/mlx-proxy.py` (repo version), which bypasses this issue.
- **Mitigation**: Run `./launch.sh install-mlx` after updating `scripts/mlx-proxy.py`. The test suite detects stale deployed proxy by comparing file sizes and falls back to using the repo version.
- **Last verified**: 2026-04-06

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
- **Status**: **RESOLVED** (2026-04-06)
- **Description**: The HunyuanVideo sharded model in `models/diffusion_models/hunyuan-video/` could not be loaded by ComfyUI's `UNETLoader`. The merged single-file version (`models/video/diffusion_pytorch_model_comfyui.safetensors`) existed but was in a non-standard path that `UNETLoader` does not scan.
- **Resolution**: Created symlink `models/diffusion_models/hunyuanvideo_comfyui.safetensors` → `../video/diffusion_pytorch_model_comfyui.safetensors`. Updated `VIDEO_MODEL_FILE` default in `video_mcp.py` and `docker-compose.yml` to `hunyuanvideo_comfyui.safetensors`. `UNETLoader` now discovers and loads the model.
- **Last verified**: 2026-04-06

### Video Generation — Missing HunyuanVideo Text Encoder and VAE
- **ID**: P5-VIDEO-002
- **Status**: **ACTIVE**
- **Description**: HunyuanVideo T2V requires three supporting models not currently present: (1) `llava_llama3_fp8_scaled.safetensors` (~8.9GB LLaVA LLaMA 3 text encoder), (2) `clip_l.safetensors` (~235MB CLIP-L), and (3) `hunyuan_video_vae_bf16.safetensors` (~200MB HunyuanVideo VAE). The FLUX CLIP-L and FLUX T5 XXL currently in `models/clip/` are incompatible — T5 XXL's output tensors do not match HunyuanVideo's expected conditioning shape, causing a dimension mismatch in `SamplerCustomAdvanced`.
- **Impact**: Video generation via `generate_video` MCP tool fails with a ComfyUI tensor mismatch error.
- **Resolution**: Download the missing models:
  ```
  huggingface-cli download Comfy-Org/HunyuanVideo_repackaged \
    --include "split_files/text_encoders/llava_llama3_fp8_scaled.safetensors" \
    --include "split_files/text_encoders/clip_l.safetensors" \
    --include "split_files/vae/hunyuan_video_vae_bf16.safetensors" \
    --local-dir ~/ComfyUI/models
  ```
  Then set the `HUNYUAN_*` env vars in `.env` to point to the downloaded files. The workflow node layout is already correct (P5-VIDEO-001 resolved).
- **Last verified**: 2026-04-06

### SDXL Image Generation — Slow on Apple Silicon MPS
- **ID**: P5-COMFY-001
- **Status**: **ACTIVE**
- **Description**: SDXL generation at 25 steps, 1024×1024 exceeds 5 minutes on Apple M4 MPS. The acceptance test C6 timeout (300s) fires before generation completes, and cascading C7 tests time out while SDXL is still running in the ComfyUI queue.
- **Impact**: C6-02 and C7-02/03/04 acceptance tests report WARN (timeout). The images ARE generated eventually; the issue is test timeout, not generation failure.
- **Mitigation**: FLUX schnell (4 steps) and SDXL with fewer steps work within timeout. Reduce SDXL steps to ≤8 in test parameters for faster validation.
- **Last verified**: 2026-04-06

---

## Inference Performance (M4)

### Speculative Decoding Adds Memory Cost
- **ID**: P5-SPEC-001
- **Status**: **ACTIVE**
- **Description**: When a target model has a draft assigned in `speculative_decoding.draft_models`, both the target and draft are loaded simultaneously by `mlx_lm.server`. Admission control accounts for this — draft memory is added to the target's MODEL_MEMORY entry pre-flight.
- **Impact**: Models with draft mappings require ~0.5-1GB more headroom than without. If memory is tight, removing the draft entry from `backends.yaml` and restarting the proxy falls back to non-spec-decoded inference.
- **Mitigation**: Draft models are small (0.5-1GB) — impact is minimal on 64GB machines. Remove from `speculative_decoding.draft_models` to disable.
- **Last verified**: 2026-04-24

### OMLX Evaluation Complete
- **ID**: P5-OMLX-001
- **Status**: **CLOSED — Not adopted. KV cache not working.** See OMLX_DECISION.md.
- **Description**: OMLX evaluated as replacement for mlx-proxy.py. Full bake-off shows KV cache persistence is NOT functioning — warm TTFT is 31% slower than cold (0.38s vs 0.29s). OMLX also failed to load 22GB Qwen3-Coder-30B model. Headline feature fails.
- **Impact**: No KV cache. mlx-proxy remains production inference.
- **Mitigation**: mlx-proxy ~equivalent TPS, more stable. Speculative decoding provides independent gains.
- **Last verified**: 2026-04-25

---

*Last updated: 2026-04-25*
