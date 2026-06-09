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

### Devstral 2509 Upgrade Blocked — Model Not Published
- **ID**: P5-BENCH-DEVSTRAL-2509
- **Description**: `lmstudio-community/Devstral-Small-2509-MLX-4bit` was not found on
  HuggingFace as of TASK_BENCH_COVERAGE_V1 (2026-05-21). bench-devstral remains pinned
  to the 2507 (July 2025) variant.
- **Operator action**: Re-run Change 0 verification when the 2509 card appears.

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

## MLX Inference Proxy — RETIRED (commit 3a0c58e)

The MLX inference proxy and all its limitations (single-model eviction,
cold-boot 503 windows, admission control, deploy staleness) no longer
apply. All chat inference runs through Ollama (:11434). MLX is retained
only for speech (:8918), transcription (:8924), embeddings (:8917), and
reranking (:8925) — those have their own sections.

## Model Parity — Specialist models lost in the MLX→Ollama migration

Two production specialist models were MLX-only safetensor builds with no
verified GGUF equivalent. The migration (3a0c58e) remapped their
workspaces to general-purpose GGUF substitutes:

| Workspace(s) | Original (MLX) | Now served (Ollama GGUF) | Gap |
|---|---|---|---|
| `auto-blueteam`, `bench-foundation-sec` | Foundation-Sec-8B-Reasoning (Cisco, purpose-trained defender cybersec: CVE→CWE, MITRE ATT&CK, SOC triage) | Apriel-Nemotron-15B-Thinker (general reasoner) | loss of domain-specialized defender behavior |
| `tools-specialist`, `bench-toolace25` | ToolACE-2.5-Llama-3.1-8B (Team-ACE, BFCL-topping tool-caller) | granite4.1:8b (general tool-tagged) | loss of purpose-trained tool-call accuracy |

**Status:** descriptions corrected for truth-in-labeling (P5-FUT-PARITY-001
in P5_ROADMAP.md). Whether to source/verify GGUF rebuilds of these exact
models, accept the substitutes permanently, or retire the specialist
workspaces is an OPERATOR DECISION — see roadmap item. No GGUF card for
Foundation-Sec-8B-Reasoning or ToolACE-2.5 was confirmable at audit; do
not add either to backends.yaml without verifying weight availability
from a primary HF source first (project rule: unconfirmable card = do not
recommend).

---

## Inference Performance

### Speculative Decoding Adds Memory Cost
- **ID**: P5-SPEC-001
- **Description**: Models with a draft assigned in `speculative_decoding.draft_models` load both target and draft simultaneously. Admission control accounts for this, but models with drafts require ~0.5–1GB more headroom.
- **Mitigation**: Remove the draft entry from `backends.yaml` and restart the proxy to disable spec decoding for a specific model.

### MTP Speculative Decoding Not Supported by MLX Proxy
- **ID**: P5-MTP-001
- **Severity**: MEDIUM — enhancement opportunity (promoted from LOW by TASK_MODEL_REFRESH_V8)
- **Description**: Multi-Token Prediction (3.94× speedup verified for Gemma 4 26B-A4B BF16) requires `--draft-model` and `--draft-kind mtp` flags. The proxy does not pass these. V8 supersedes the BF16-slower premise: 4-bit-trunk + INT4-MTP-sidecar (MTPLX) removes the BF16 cost, and the dense-27B no-MTP baseline (12.4 TPS) is exactly the case MTP rescues.
- **Resolution path**: TASK_MTP_PROXY_V1.md.

### MTP Speculative Decoding Is Bench-Only (V8)
- **ID**: P5-MTP-PATH
- **Description**: MTP speculative decoding is bench-only pending the `--spec-decoding-tag` A/B and sustained-load probe. The production MLX-proxy serving path does not yet enable MTP, and MTP requires a separate runtime (MTPLX for MLX, llama.cpp b9180+ for GGUF) rather than the existing `--draft-model` external-drafter wiring.
- **Operator action**: Re-run the A/B (`bench_tps.py --spec-decoding-tag mtp-on` vs `mtp-off` on `bench-qwen36-27b-mtp`) and TASK_OMLX_MTP_STABILITY_V1 before any production promotion.

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

---

## Models Out of M4 Pro 64 GB Budget

The following models were evaluated and explicitly **refused** from the Portal 5
catalog. They exceed the M4 Pro 64 GB unified memory ceiling at the lowest
quality-preserving quantization. Do not re-propose without a cluster scaling
plan (P5_ROADMAP Stage 3 vLLM node).

**Guardrail for future Claude sessions**: before recommending any MoE model
with total params > 100B on a 64 GB M4 Pro budget, compute the 4-bit weight
footprint. If > 50 GB, refuse and reference this section. Mac Studio 128 GB+
is the path for these models.

| Model | 4-bit MLX resident | Why refused |
|-------|--------------------|-------------|
| `mlx-community/MiniMax-M2-4bit` | ~129 GB | 230B-A10B MoE. 4-bit weight footprint alone exceeds 64 GB before any KV cache. |
| `mlx-community/MiniMax-M2.5-4bit` (and Uncensored variant) | ~129 GB | Same architecture as M2. |
| `mlx-community/MiniMax-M2.7-4bit-mxfp4` | ~129 GB | mxfp4 does not reduce the dense-weight component substantially. |
| `thetom-ai/MiniMax-M2.7-ConfigI-MLX` (mixed-precision) | ~87 GB | Aggressive Config-I 2-bit on expert MLPs, still over 64 GB. |
| `mlx-community/DeepSeek-V4-Flash` (community 4-bit) | ~142 GB | 284B-A13B MoE FP4+FP8 base. |
| `mlx-community/DeepSeek-V4-Pro` (community 4-bit) | ~800 GB | 1.6T total params. |
| `mlx-community/Kimi-K2-Instruct-0905-mlx-4bit` (Instruct + Thinking) | ~578 GB | 1T total MoE, 32B active. |
| `mlx-community/Kimi-K2-Instruct-0905-mlx-DQ3_K_M` | ~450 GB | Mixed 3-4 bit still over budget. |
| GLM-5 (Z.AI flagship) | 192+ GB at 4-bit | 744B params; not yet in MLX. |
| `huihui-ai/Huihui-GLM-5.1-abliterated` (754B) | 377+ GB at 4-bit | Same bucket as GLM-5 — abliterated variant, total params far exceed 64 GB. |

**P5-MODEL-64GB principle**: MoE active-parameter count governs decode *speed*, but total parameters govern *whether it fits* — 64 GB gates on total, not active. The April-2026 headline releases (DeepSeek-V4-Flash 284B/13B active, Kimi-K2.6 1T/32B active) are verified real but excluded on this basis. They become relevant only at the cluster Stage-3 / Mac-Studio tier on the roadmap.

*Last updated: 2026-05-28*
