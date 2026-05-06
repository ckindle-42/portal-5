# Known Limitations

Architectural and design constraints that cannot be resolved without significant tradeoffs. These are accepted as part of Portal 5's design.

---

## Memory and Persistence

### Cross-Session Memory Requires Model-Initiated Tool Calls
- **ID**: P5-MEM-001
- **Status**: ACTIVE — OWUI architectural limitation
- **Description**: UAT test A-08 (cross-session memory) expects a model to store a named fact in one OWUI chat and retrieve it in a separate fresh chat. The OWUI memory feature uses a tool-call model (`remember`/`recall`), but whether the model actually invokes these tools depends on the OWUI session's tool binding. In practice, the model sometimes acknowledges storage verbally without making the tool call, meaning the fact is never persisted to the memory backend. The retrieval chat then finds nothing.
- **Root cause**: Two compounding issues: (1) OWUI's per-session tool activation is not guaranteed across fresh chats opened by the UAT driver, and (2) some models respond verbally ("I'll remember that") instead of invoking the MCP tool.
- **Impact**: A-08 FAIL in UAT runs. Actual user-facing memory behavior in OWUI's own UI may differ (OWUI activates tools more reliably for human-initiated sessions).
- **Mitigation**: For reliable cross-session memory, use the memory MCP server directly via the API (`/tools/remember`) rather than relying on model-initiated tool calls through OWUI. The UAT driver cannot control OWUI's per-chat tool binding without changes to the seeding script.
- **Operator action**: None required. A-08 remains in the UAT suite as a canary for memory regression.
- **Last verified**: 2026-05-05

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

### supergemma4-26b-uncensored-mlx-4bit-v2 Removed from MLX Catalog
- **ID:** P5-MOD-REMOVED-001
- **Status:** REMOVED
- **Description:** `Jiunsong/supergemma4-26b-uncensored-mlx-4bit-v2` was added to the catalog for the `supergemma4researcher` persona but subsequently removed. The `supergemma4researcher` persona now routes via `auto-research` (mlx_model_hint: `mlx-community/gemma-4-31b-it-4bit`, Ollama fallback: `huihui_ai/tongyi-deepresearch-abliterated`).
- **Last verified:** 2026-05-04

### auto-math Workspace Has No Reasoning-Block Support
- **ID:** P5-MATH-001
- **Status:** ACTIVE
- **Description:** `Qwen2.5-Math-7B-Instruct` does not emit `reasoning_content` blocks — math reasoning appears in the regular content stream. The collapsible thinking panel will not show separately for `auto-math` traffic. This is a model property, not a pipeline issue. For extended thinking on math problems, `auto-reasoning` (Qwopus 27B) is an alternative.

### Asteroids Bench Lives/Loop Differences Are the Benchmark's Purpose
- **ID:** P5-BENCH-001
- **Status:** ACTIVE — by design
- **Description:** The CC-01 Asteroids bench (`bench-*` workspaces) measures real model differences in single-shot HTML game generation. Per UAT 2026-04-28: GPT-OSS and GLM-4.7-Flash deliver 5/5; Llama-3.3-70B and phi4 deliver 4/5 (lives system not explicitly named); Devstral, Dolphin-8B, Qwen3-Coder-30B, Qwen3-Coder-Next deliver 3/5 (also miss explicit canvas game loop keywords); phi4-reasoning delivers 2/5 (does not produce an HTML code block — phi4-reasoning is RL-trained for STEM/math, not code generation).
- **Why this is not a bug:** The bench personas all share an identical creative-coder system prompt by design (verified: `diff config/personas/bench_devstral.yaml config/personas/bench_glm.yaml` shows only header/slug differences). The point of the bench is to surface raw model capability on a fixed task. Broadening the assertion keywords would erase the signal the bench exists to capture.
- **Operator action:** None. Use the bench results as model-selection input. If a model scores ≤3/5 on CC-01 it is not a candidate for `auto-coding` HTML generation.
- **Last verified:** 2026-04-28

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
- **Next steps**: Replacement IN CATALOG as of 2026-04-26: `mlx-community/glm-4.7-flash-abliterated-8bit` (Apple-converted from huihui source, catalog-only pending security-tier MLX architecture). Standard non-abliterated `mlx-community/GLM-4.7-Flash-4bit` also added and pinned as `auto-coding` primary for general lineage diversity. The broken `huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit` remains registered for monitoring — remove if no upstream Linux fix appears within 60 days of replacement deployment.
- **Acceptance test**: S23-07 will FAIL or WARN on this model — expected until upstream fixes the conversion.
- **Last verified**: 2026-04-25

### Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit: Empty Content on Apple Metal
- **ID**: P5-MLX-008
- **Status**: **CONFIRMED BROKEN — produces empty content on Apple Metal**
- **Description**: UAT 2026-04-26 (M4 Pro, 64GB) WS-13 (auto-research, post-quantum cryptography prompt) returned `len=0` content. Same defect class as P5-MLX-006: Linux-converted MLX where the server emits tokens but they decode to empty string. Single-contributor repo (`Jiunsong`), no Apple Silicon validation in card. The "lighter MLX build" packaging note flagging Hub auto-inference as 5B/8B is a leading indicator of non-standard config that the Apple-side `mlx_vlm` runtime mis-handles. The sibling repo `Jiunsong/SuperGemma4-31b-abliterated-mlx-4bit` exhibits the same single-contributor / no-eval pattern and should be considered the same risk class.
- **Diagnosis**: Same pattern as P5-MLX-006 GLM-4.7. The multimodal MLX pipeline (`mlx_vlm`) is the most-fragile path for cross-platform tokenizer drift. Auto-research does not require vision (no `image_url` parts), so pinning a VLM there was a misallocation independent of the conversion bug.
- **Replacement**: Two-track. (1) For auto-research workspace: `mlx-community/gemma-4-31b-it-4bit` (already in catalog, proven working in auto-vision WS-14, co-locates auto-research + auto-vision on the same `mlx_vlm` server). (2) For the abliterated Gemma slot in the catalog and as the `auto-creative` MLX pin: `divinetribe/gemma-4-31b-it-abliterated-4bit-mlx` (MLX 4-bit quantization of null-space/gemma-4-31b-it-abliterated, 1857 downloads, no degeneration issues).
- **Acceptance test**: WS-13 acceptance prompt should produce non-zero substantive content after replacement.
- **Last verified**: 2026-04-26

### Laguna-XS.2-4bit: mlx-lm Architecture Plugin (Manual — Not Upstreamed)
- **ID**: P5-MLX-009
- **Status**: **RESOLVED via local plugin — mlx_lm 0.31.3 + laguna.py patch**
- **Description**: `mlx_lm 0.31.3` does not ship a Laguna model architecture (never upstreamed from the mlx-community conversion). Two files were installed manually into the mlx_lm package to fix this: `models/laguna.py` (MoE + sliding-window attention architecture) and `tool_parsers/laguna.py` (JSON tool call parser). Key bugs fixed during implementation: (1) gate.proj must be 8-bit (per config.json per-layer quantization, not the 4-bit default), (2) MoE routing weights must be normalized to sum=1 before applying `moe_routed_scaling_factor` to the aggregated output — skipping normalization caused 4-10x over-scaling and completely garbled output. Model now produces correct inference at ~92 tok/s on M4 Pro (18.97GB).
- **Impact**: If `mlx_lm` is upgraded, the two plugin files must be re-installed. `patch-mlx-threads.py` can be extended to handle this. The upstream Laguna architecture PR is still open as of 2026-04-30.
- **Next steps**: After any `mlx_lm` upgrade run: `cp /path/to/laguna.py $(python3 -c "import mlx_lm; import os; print(os.path.dirname(mlx_lm.__file__))")/models/laguna.py` and the tool_parsers equivalent.
- **Last verified**: 2026-04-30

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

## Shared Workspace + Auto-STT Disabled (TASK-WORKSPACE-001)

- **Voice-input via microphone is disabled.** Setting `AUDIO_STT_ENGINE` to empty (the default after this task) prevents auto-transcription of both file uploads AND microphone recordings in Open WebUI. Operators who want voice-input back must either re-enable the global STT (which re-enables auto-transcribe-on-file-upload) or implement a custom OWUI Function that scopes STT to recording-only. The global toggle is currently OWUI's only knob.
- **Existing MCPs not migrated to /workspace.** `mcp-documents`, `mcp-tts`, and `mcp-comfyui` continue to write to `${AI_OUTPUT_DIR}` flat (their existing `OUTPUT_DIR=/app/data/generated` mount is unchanged). New MCPs and the helper module use `/workspace/generated/<category>/`. The two layouts coexist; migration is opportunistic, scheduled for whenever each MCP is next touched for unrelated reasons.
- **OWUI named volume retains historical uploads visibility.** The bind-mount overlay on `/app/backend/data/uploads` hides any pre-existing files in the named volume's `uploads/` subdirectory. Pre-flight migration (Phase 0) handles this for current state; new operators have empty uploads on first launch (correct behavior).
- **Permissions assume single-host deployment.** The 0775 mode on workspace directories assumes the operator's user owns the files and Docker containers run with compatible UIDs. On multi-tenant or hardened hosts, more careful UID mapping is required.
- **No retention policy.** `${AI_OUTPUT_DIR}` grows unbounded. Future task adds `./launch.sh workspace-clean --age=Nd` for time-based pruning.

---

## Diarized Transcription (TASK-TRANSCRIBE-001)

- **Pyannote model gating.** Diarization models (`pyannote/segmentation-3.0`, `pyannote/speaker-diarization-3.1`) require accepting their HuggingFace user agreements before download. Without `HF_TOKEN` in `.env` and licenses accepted, the service starts but diarization calls return 500. Upstream licensing, not a Portal 5 limitation.
- **Overlapping speech.** Pyannote 3.1 under-performs when multiple speakers talk simultaneously. The merge logic assigns each transcribed segment to a single speaker by maximum overlap; rapid alternation may surface as one merged turn.
- **Speaker count drift on long recordings.** For recordings >15–30 min, pyannote may register the same speaker as two separate IDs after long silence gaps. Pass `num_speakers=N` if the count is known. The `transcriptanalyst` persona surfaces suspicious counts and offers re-processing.
- **No hard length limit, but practical scaling.** 10 min ≈ 60–130s; 35 min ≈ 3.5–7.5 min; 1 hour ≈ 6–13 min. Memory comfortable up to multi-hour files on 64 GB.
- **OWUI tool-call timeout for long files.** OWUI's default MCP timeout is shorter than processing time for files >5 min. Operator must raise `TOOL_SERVER_REQUEST_TIMEOUT` (e.g., 1800s) or use the direct curl endpoint at `:8924`.
- **First-call latency.** Pyannote pipeline takes ~10–15s to load on first call. `/health` returns `diarization_loaded: false` until then. Subsequent calls reuse the loaded pipeline.
- **MLX path is macOS-only.** `scripts/mlx-transcribe.py` requires Apple Silicon. The Docker `whisper_mcp.py` fallback (faster-whisper + pyannote on CPU/CUDA) is the cross-platform alternative; significantly slower on Apple Silicon (CPU-bound).
- **First-run model download.** Whisper-large-v3-turbo (~1.5 GB) + pyannote weights (~36 MB) download on first transcription. Subsequent calls use cached weights in `~/.cache/huggingface/`.

---

## OWUI Audio Drop UX (TASK-OWUI-AUDIO-DROP-001)

- **OWUI internal 60s tool-call ceiling.** Some OWUI builds enforce an additional internal timeout on tool execution that the documented `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` env var does not affect (see open-webui/open-webui#16902). When this bites, the tool actually completes server-side — the persona just never sees the result. Mitigation: use `scripts/transcribe_and_complete.sh` for files where transcription wall time exceeds 60s. The runner script is unaffected because it goes around OWUI's tool-call layer entirely.
- **WEBUI_SECRET_KEY rotation invalidates stored OAuth tokens.** If `.env` is regenerated and the secret key changes, all MCP tools using OAuth (Notion, GitHub, etc.) need re-authentication. The launch.sh auto-generation only runs when the value is unset or the placeholder; do not regenerate manually unless the operator accepts re-auth.
- **Microphone voice input remains disabled.** The TASK-WORKSPACE-001 trade-off is unchanged. This task does not address it.

---

*Last updated: 2026-04-29*

---

## P5-MATRIX-001 — Persona matrix methodology under remediation

**Status**: Active limitation — under remediation
**Filed**: 2026-05-04
**Affected**: `tests/portal5_persona_matrix.py`, `tests/portal5_acceptance_v6.py` S10c, `.github/workflows/persona_matrix_nightly.yml`, `docs/COMPLIANCE_FALLBACK_POLICY.md` thresholds

### Symptom

After commit `a50fda7` (TASK 001-009), large-scale evaluation runs produced
non-actionable failure rates:

- Acceptance V6 S10c (2026-05-02): 85 PASS / 177 FAIL / 56 WARN against the
  auto-compliance MLX primary
- Persona matrix MLX sweep: 25 models, every cell 0/35 PASS
- Persona matrix Ollama sweep: best model `granite4.1:8b` at 36.9% — below
  the 60% reject threshold in `docs/COMPLIANCE_FALLBACK_POLICY.md`

### Root cause (verified)

1. Matrix driver truncated persona system prompts at 1600 chars; 5 of 7
   compliance personas exceed that cap. Assertion-required structural
   instructions were never reaching the model.
2. Several compliance personas did not mandate the literal phrases the
   assertion library tests for (`Full|Partial|None|Ambiguous`,
   `"Insufficient context — needed:"`, etc.). The persona/assertion
   contract was implicit and inconsistent.
3. The matrix driver hits backends directly (bypassing pipeline); the
   acceptance suite hits the pipeline. They measure different systems but
   were treated as comparable.

### Remediation

`TASK_MATRIX_DRIVER_REMEDIATION_V1` (this task):

- Lifted truncation cap to 8000 chars with explicit guard
- Added response_preview + http_status capture for triage
- Added explicit OUTPUT CONTRACT to all 7 compliance personas
- Froze nightly CI as continue-on-error during remediation
- Archived pre-fix matrix result files

### Acceptance criteria

This entry remains in `KNOWN_LIMITATIONS.md` until:

1. A post-remediation matrix sweep is recorded as the new baseline
2. The auto-compliance routing chain has at least one model above the
   60% MUST-pass threshold per `docs/COMPLIANCE_FALLBACK_POLICY.md`
3. Acceptance V6 S10c PASS rate recovers to ≥75% on the live primary
4. Nightly CI is restored to a hard gate (continue-on-error removed)

### Operator next steps (manual)

After this task lands and is rebuilt, operator runs:

```bash
# Quick sanity — confirm response_preview captures real content
python3 tests/portal5_persona_matrix.py \
    --workspace auto-compliance \
    --backend ollama \
    --persona complianceanalyst \
    --max-scenarios 2 \
    --output tests/benchmarks/results/_smoke_post_remediation.json

# Inspect a cell — response_preview should now be populated, not absent
python3 -c "
import json
d = json.load(open('tests/benchmarks/results/_smoke_post_remediation.json'))
sc = d['cells'][0]['scenarios'][0]
assert 'response_preview' in sc, 'response_preview missing — Phase 1 not applied'
assert sc.get('http_status') == 200, f'unexpected http_status: {sc.get(\"http_status\")}'
print('smoke OK — response_preview length:', len(sc['response_preview']))
"

# Full re-baseline (90+ minutes)
python3 tests/portal5_persona_matrix.py \
    --workspace auto-compliance \
    --output tests/benchmarks/results/persona_matrix_$(date -u +%Y%m%dT%H%M%SZ).json
```

The MLX 0% across-the-board pattern from the pre-fix sweep should not
recur. If it does, captured response_preview values are the next data
source — pull a representative MLX cell and inspect.

---

## P5-TOOL-001 — Ollama tool-support catalog audit + per-model verification cycle

**Status**: Active limitation — under managed verification
**Filed**: 2026-05-04
**Affected**: `config/backends.yaml`, `portal_pipeline/router_pipe.py`, `portal_pipeline/cluster_backends.py`

### Symptom

Commit `de96984` (auto-video model swap) surfaced a systemic defect:
`dolphin-llama3:8b` does not support Ollama tool calling — sending a
request with a `tools` array returns an explicit Ollama API error. The
router previously trusted every Ollama model unconditionally for tool
support (`router_pipe.py:2420`), which propagated the dolphin defect to
14 workspaces whose chains fell through to `ollama-general` (where
dolphin sat at line 1) when their primary groups failed health checks.

### Root cause

1. Ollama determines tool support per-model by checking the model's
   template for the `.Tools` template variable. Dolphin's stock Ollama
   package does not include this variable. Other Ollama models in the
   catalog have varying tool support that was never verified.
2. `_model_supports_tools()` in `router_pipe.py` only consulted MLX
   metadata. For Ollama, the router took it on faith.
3. Six hardcoded `else "dolphin-llama3:8b"` defensive defaults
   compounded the risk by routing tool-using requests to dolphin
   whenever a backend's `models` list was empty.
4. Pre-existing gap: `granite4.1:8b` and `granite4.1:30b` were added to
   `config/backends.yaml` around the time of `de96984` but never
   registered in `launch.sh` model pull arrays.

### Remediation (`TASK_TOOL_SUPPORT_AUDIT_V1`)

- Schema change: Ollama `models:` accepts list-of-dicts with per-model
  metadata, parallel to existing MLX `mlx_models:`.
- Catalog audit: `supports_tools` flag added to every Ollama model
  entry. Verified-true for tools-tagged models; fail-safe-false for
  unverified.
- Router fix: `_model_supports_tools` reads both metadata sources;
  default for unflagged models is False.
- Hardcoded fallbacks removed: 6 sites now log and skip-this-backend.
- Catalog reorder: `ollama-general` line 1 is now
  `huihui_ai/qwen3.5-abliterated:9b` (uncensored + tool-tagged).
- AUTO + auto-music model_hints swap to qwen3.5-abliterated.
  auto-creative untouched.
- Matrix driver gains `--audit-tools` mode for per-model verification.
- launch.sh pull arrays register the new model + backfill granite4.1.
- bench_tps + UAT + acceptance v6 register the new model in fixture maps.
- New `bench-qwen35-abliterated` workspace + CC-01 fixture follows the
  per-significant-model bench-* pattern.

### Acceptance criteria

This entry remains until:

1. Operator runs `tests/portal5_persona_matrix.py --audit-tools` against
   every Ollama backend group at least once.
2. Every entry with `supports_tools: false` has been either:
   - Confirmed false by audit, OR
   - Flipped to `true` after audit confirmation, OR
   - Documented as intentionally false.
3. The matrix `--audit-tools` mode is wired into nightly CI.
4. Acceptance V6 S10c PASS rate against the auto-compliance MLX primary
   returns to ≥75%.

### Operator next steps

```bash
for ws in auto auto-coding auto-compliance auto-research auto-security; do
  python3 tests/portal5_persona_matrix.py --audit-tools \
    --workspace "$ws" --backend ollama \
    --output "tests/benchmarks/results/audit_tools_${ws}_$(date -u +%Y%m%dT%H%M%SZ).json"
done

jq '.results[] | select(.outcome == "tool_call") | .model' \
   tests/benchmarks/results/audit_tools_*.json | sort -u
```

### Out of scope

- Path 2 (OWUI MCP) tool dispatch verification.
- Auto-creative re-evaluation (intentionally untouched).
- vLLM tool-support metadata (schema is extensible; future task).
