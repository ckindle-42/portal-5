# Known Limitations

Architectural and design constraints that are currently unresolved. Resolved items are not listed here — see git log for history.

---

## CAD / 3D Printing

### CadQuery and build123d Unusable on linux/arm64
- **ID**: P5-CAD-ARM64-001
- **Description**: CadQuery ≥2.4 and build123d both require `cadquery-ocp` / `ocp` (OpenCASCADE Python bindings), which has no pre-built wheels for `linux/arm64`. Installing either package in `Dockerfile.mcp` on Apple Silicon fails at build time.
- **Impact**: Python-native parametric CAD (`.box()`, `.extrude()` style) is unavailable inside the MCP containers. The `auto-cad` workspace uses OpenSCAD instead, which runs headlessly and has no platform restriction.
- **Mitigation**: Use OpenSCAD via the `render_openscad` tool for parametric geometry. Use `trimesh` (installed) for procedural mesh manipulation. If CadQuery is required in future, it must be built from source (multi-hour OCP compile) or sourced from a community arm64 wheel when one becomes available.
- **Do not re-add** `cadquery` or `build123d` to `Dockerfile.mcp` without first verifying an arm64 wheel exists — the build will silently succeed on x86 CI and fail on this hardware.

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

### baronllm text_only tool output — auto-security MCP tools non-functional
- **ID**: P5-TOOL-001
- **Description**: `huihui_ai/baronllm-abliterated` (auto-security primary) outputs tool-call JSON embedded in the `content` field of Ollama's `/v1/chat/completions` response rather than in the structured `tool_calls` field. Ollama's llama.cpp backend does not parse this as a function-call delta. Result: the pipeline's `_dispatch_tool_call` path is never triggered for auto-security requests that attempt MCP tool use.
- **Evidence**: `audit-tools 2026-06-18` probe — outcome `text_only`, content: `{"name":"get_current_time","parameters}:{ "city": "Paris" }`. UAT TV-02 (execute_python proof) and TV-03 (classify_vulnerability) both show tool not dispatched. Previous `supports_tools: true` marking (TASK_TOOL_AUDIT_V2) was a false positive from Ollama template header inspection, not a live response probe.
- **Impact**: Auto-security cannot use `execute_bash`, `execute_python`, `classify_vulnerability`, or any pipeline-dispatched MCP tool. TV-02 grades as WARN (non-critical assertion). Prose security analysis and code audits still work (text generation is unaffected).
- **Resolution path**: (a) Fix baronllm's Ollama chat template to emit proper `tool_calls` structure — this requires inspecting the model's tokenizer_config and Ollama template to align with llama.cpp's tool-call parsing; OR (b) Replace baronllm with a model in the auto-security chain that passes the live probe (e.g., qwen3.5-abliterated:9b was confirmed tool_call in a prior audit).
- **Do not re-enable** `supports_tools: true` for baronllm without running `python3 tests/portal5_persona_matrix.py --audit-tools --workspace auto-security` or the direct Ollama probe and confirming outcome=`tool_call`.

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
| `auto-blueteam`, `bench-foundation-sec` | Foundation-Sec-8B-Reasoning (Cisco, purpose-trained defender cybersec: CVE→CWE, MITRE ATT&CK, SOC triage) | Foundation-Sec-8B-Reasoning Q8_0 GGUF (Cisco fdtn-ai, first-party, ~8.5GB) | RESTORED (P5-FUT-PARITY-001) |
| `tools-specialist`, `bench-toolace25` | ToolACE-2.5-Llama-3.1-8B (Team-ACE, BFCL-topping tool-caller) | granite4.1:8b (general tool-tagged, BFCL V3 68.27, first-party IBM) | ACCEPTED — granite4.1:8b adopted; ToolACE-2.5 dropped (P5-FUT-PARITY-001 closed) |

**Status — Foundation-Sec:** RESTORED to the auto-blueteam production primary
via the first-party Cisco GGUF `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`
(TASK_PARITY_FOUNDATION_SEC_V1, direct swap, no bench gate — consistent with how
the original MLX→Ollama migration set models by assumption; this restores the
pre-migration primary).

**Status — ToolACE:** RESOLVED (accepted). granite4.1:8b adopted as the
tools-specialist model by operator decision; ToolACE-2.5 evaluated and dropped
(no verified ToolACE-2.5 GGUF confirmed; self-quant + Ollama tool-template risk
not justified). P5-FUT-PARITY-001 is CLOSED/DONE — both specialists dispositioned
(Foundation-Sec restored, ToolACE substitute accepted).

---

## Inference Performance

### devstral:24b Runtime VRAM Footprint (25.7 GB)
- **ID**: P5-VRAM-DEVSTRAL-001
- **Description**: devstral:24b file size is 14.3 GB but runtime Ollama resident size is ~25.7 GB due to large default context window and KV cache allocation (q8_0). This is nearly 2× the file size and will cause memory-pressure eviction of other loaded models on 48 GB hardware.
- **Impact**: When devstral is active, it may evict the LLM router model from VRAM. The first post-eviction routing request falls back to Layer 2 keyword scoring (correct behavior), then the router cold-loads in ~4.2s and stays warm. Subsequent requests use the LLM router normally.
- **This is graceful, not a crash**: Ollama offloads CPU layers under memory pressure rather than failing. Unlike the former MLX Metal OOM, no kernel panic occurs.
- **Mitigation**: `OLLAMA_MAX_LOADED_MODELS=3` (current default) reserves a slot for the router + 2 inference models. If devstral:24b is loading as an inference peer, its runtime footprint is the limiting factor — not the slot count. Setting `OLLAMA_MEMORY_LIMIT=42g` in the Ollama plist caps worst-case pressure; see Admin Guide → Router Configuration.

### Request-Size Cap Relies on Content-Length Only
- **ID**: P5-REQ-SIZE-001
- **Description**: The pipeline caps requests at 4 MB via `Content-Length` header check. Chunked transfer-encoded requests bypass this cap entirely — Starlette middleware is the proper fix.
- **Mitigation**: Until Starlette body-size middleware is added, operators should configure upstream proxies (nginx, OWUI) to enforce request-size limits.

### Speculative Decoding / MTP — RETIRED with the MLX proxy (commit 3a0c58e)
- **IDs**: P5-SPEC-001, P5-MTP-001, P5-MTP-PATH (all moot)
- **Status**: The MLX inference proxy that hosted `--draft-model` speculative decoding and the `speculative_decoding.draft_models` map was retired; chat inference is Ollama-only. These limitations no longer apply because the infrastructure they described no longer exists.
- **If revisited**: any future speculative-decoding / MTP work targets Ollama's native path (llama.cpp b9180+), not MLX. The bench-only MTP GGUF candidates remain in the catalog as bench entries; there is no production MLX serving path to enable.
- **P5-FUT**: evaluate `/api/chat` as `chat_url` — `/api/chat` would allow full `options` passthrough but requires changing payload/response shapes.

### 70B Dense Models Unusable for Daily Routing on M4 Pro 64GB
- **ID**: P5-SPEED-001
- **Description**: Llama-3.3-70B-Instruct-4bit and DeepSeek-R1-Distill-Llama-70B-4bit measure ~3.5 TPS warm — too slow for interactive use. 3-bit quantization (~28GB) is theoretically viable at ~9.7 TPS but not yet bench-validated.
- **Mitigation**: All daily-routed workspaces use ≤33B models. 70B variants are bench-tier only.

### Ollama /v1 ignores options.num_ctx and options.num_batch
- **ID**: P5-OLLAMA-OPTIONS-001
- **Description**: Ollama's OpenAI-compatible `/v1/chat/completions` endpoint ignores the `options` sub-object entirely (VERIFY-1 probes, 2026-06). The pipeline still injects `options.num_ctx`, `options.num_batch`, and `options.num_predict` (the latter mapped to `max_tokens` at top level per Branch I) because a future Ollama version may honor them. Currently:
  - `context_limit` per workspace (e.g. `auto-agentic: 32768`) is **not enforced** — set PARAMETER num_ctx in the model's Modelfile or OLLAMA_CONTEXT_LENGTH
  - `num_batch` injection is inert — set PARAMETER num_batch in Modelfiles for prefill tuning
  - `predict_limit` is mapped to OpenAI `max_tokens` (top-level, honored) as a workaround
- **Roadmap note:** P5-FUT: evaluate `/api/chat` as `chat_url` — it honors the Ollama-native parameter set but requires changing all payload/response shapes.

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

### V8 Catalog Deferred (insufficient hardware)

| Model | Est Size | Reason Deferred |
|-------|----------|-----------------|
| `sjakek/Nex-N2-Pro` | ~230GB | 397B total, 17B active — far exceeds 64 GB even at Q1. |
| `DeepSeek-R1-0528` (full) | ~400GB | 671B full model. 8B distill variant added (V8 bench-r1-0528-qwen3-8b). |
| `Harness-1` (full capability) | n/a | Requires Chroma vector DB + external search state harness. Standalone model (gpt-oss-20B fine-tune) added to V8 bench-harness1. |

*Last updated: 2026-06-10*
