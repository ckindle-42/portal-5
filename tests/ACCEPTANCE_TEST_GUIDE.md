# Portal 5 Acceptance Test Guide

This guide explains what every section of the acceptance tests does, in execution order. The main suite (`portal5_acceptance_v4.py`) covers the core platform (S0–S40). The ComfyUI suite (`portal5_acceptance_comfyui.py`) covers image/video generation separately (C0–C10).

## How to Run

```bash
# Full suite (runs in order, ~30-60 min)
python3 portal5_acceptance_v4.py

# Single section
python3 portal5_acceptance_v4.py --section S3

# Skip already-passing sections
python3 portal5_acceptance_v4.py --skip-passing

# Force rebuild before testing
python3 portal5_acceptance_v4.py --rebuild

# ComfyUI image/video tests (separate script)
python3 portal5_acceptance_comfyui.py
```

## Result Classification

| Status | Meaning |
|--------|---------|
| **PASS** | Test succeeded — the feature works correctly |
| **FAIL** | Test failed — a real bug or misconfiguration |
| **WARN** | Non-critical issue — degraded but functional (environmental, timeout, optional model missing) |
| **INFO** | Informational only — not a pass/fail (e.g., "skipped because model not installed") |
| **BLOCKED** | Cannot test because a prerequisite is broken — requires a code fix |

---

## Main Suite (`portal5_acceptance_v4.py`)

### S17 — Service Rebuild & Restart Verification

**Runs first.** Verifies that Docker containers are running the latest code.

| Test | What it checks |
|------|----------------|
| S17-00 | If `--rebuild` was passed: runs `git pull origin main` to ensure code is current |
| S17-01 | Compares each MCP container's image creation timestamp against the latest git commit touching `Dockerfile.mcp`, `portal_mcp/`, or `portal_channels/`. Flags stale images that need rebuilding |
| S17-02 | Checks if any portal-pipeline container is running stale code (image vs git commit comparison) |
| S17-03 | If `--rebuild`: runs `docker compose build --no-cache && up -d` to force a full rebuild |
| S17-04 | After rebuild: waits for portal-pipeline to become healthy (up to 180s) |
| S17-05 | After rebuild: waits for Open WebUI to become healthy (up to 120s) |

**Why it matters:** Catches the #1 operator pain point — forgetting to rebuild after a code change.

---

### S0 — Version & Codebase State

**Baseline sanity check.** Confirms you're testing the right code.

| Test | What it checks |
|------|----------------|
| S0-01 | Git repo is reachable and `HEAD` resolves to a commit SHA |
| S0-02 | Local `main` matches `origin/main` (WARN if behind — "run git pull") |
| S0-03 | Pipeline `/health` returns expected fields: `version`, `workspaces`, `backends_healthy` |
| S0-04 | `portal-5` package is installed via pip (or reads version from `pyproject.toml`) |

**What "good" looks like:** All PASS with a known SHA and version number.

---

### S1 — Static Config Consistency

**File-level cross-checks.** No HTTP calls — pure static analysis of config files.

| Test | What it checks |
|------|----------------|
| S1-01 | `router_pipe.py WORKSPACES` dict keys exactly match `config/backends.yaml workspace_routing` keys. Missing on either side = FAIL |
| S1-02 | Every persona YAML in `config/personas/` has all required fields: `name`, `slug`, `system_prompt`, `workspace_model` |
| S1-03 | `scripts/update_workspace_tools.py` lists all workspace IDs (catches missing tool registrations) |
| S1-04 | `docker-compose.yml` parses as valid YAML (`docker compose config --quiet`) |
| S1-05 | `imports/openwebui/mcp-servers.json` exists and has entries |
| S1-06 | MLX proxy script (`scripts/mlx-proxy.py`) lists Gemma and Magistral in both `ALL_MODELS` and `VLM_MODELS` (where appropriate) — prevents routing to models the proxy doesn't know about |
| S1-07 | Every MLX model referenced in `WORKSPACES` or personas appears in the proxy's model lists |

**What "good" looks like:** All PASS — the config files are internally consistent.

---

### S2 — Service Health

**HTTP health probes against every service.** The "is everything running?" check.

| Test | What it checks |
|------|----------------|
| S2-01 to S2-10 | HTTP 200 from: Open WebUI, Pipeline, Grafana, MCP Documents, MCP Sandbox, MCP Music, MCP TTS, MCP Whisper, MCP Video, Prometheus |
| S2-12 | SearXNG container healthy (`/healthz` or `/search` endpoint) |
| S2-13 | Ollama responds with a list of pulled models (`/api/tags`) |
| S2-14 | Pipeline `/metrics` endpoint is unauthenticated (HOWTO §22 requirement) |

**What "good" looks like:** Everything PASS. A single FAIL here means that service is down — fix it before continuing.

---

### S8 — Text-to-Speech (kokoro-onnx, no LLM)

**Tests the TTS MCP server.** No model inference needed — uses kokoro-onnx locally.

| Test | What it checks |
|------|----------------|
| S8-01 | `list_voices` tool returns voices including `af_heart` (the default) |
| S8-02 | `speak` tool generates audio and returns a file path |
| S8-03 | REST endpoint `/v1/audio/speech` produces valid WAV for 4 different voices (US-F, British male, US male, British female). Validates WAV header, duration >= 1s |

---

### S9 — Speech-to-Text (Whisper, no LLM)

**Tests the Whisper MCP server.** Uses faster-whisper locally.

| Test | What it checks |
|------|----------------|
| S9-01 | Whisper health check via `docker exec` (HOWTO §12 exact command) |
| S9-02 | `transcribe_audio` tool is reachable (sends nonexistent file — expects a "not found" error, confirming connectivity) |
| S9-03 | Full round-trip: TTS generates a WAV → file copied into Whisper container → Whisper transcribes it → output contains expected text. Validates the STT→TTS pipeline end-to-end |

---

### S12 — Metrics & Monitoring (HOWTO §22)

**Verifies Prometheus metrics are being collected.**

| Test | What it checks |
|------|----------------|
| S12-01 | `portal_workspaces_total` gauge matches the actual workspace count in code |
| S12-02 | `portal_backends` gauge is present |
| S12-03 | `portal_requests` counter has incremented (expects traffic from earlier S3 tests) |
| S12-04 | `portal_tokens_per_second` histogram is being recorded |
| S12-05 | Prometheus is scraping the pipeline (`/targets` shows portal5 job as UP) |
| S12-06 | Grafana datasource points to Prometheus and can query data |

---

### S13 — GUI Validation (Playwright/Chromium)

**Browser-based smoke test of Open WebUI.** Uses Playwright to drive Chromium headless.

| Test | What it checks |
|------|----------------|
| S13-01 | Login page loads → credentials accepted → chat UI appears (screenshot saved) |
| S13-02 | Model/workspace selector dropdown is visible and contains expected workspace names |
| S13-03 | Sending a chat message in the GUI produces a response (validates the full GUI → pipeline path) |
| S13-04 | Settings page loads and shows MCP tool registrations |

**Skipped if:** `OPENWEBUI_ADMIN_PASSWORD` not set in `.env` or Playwright not installed.

---

### S14 — HOWTO Accuracy Audit

**Static file validation of `docs/HOWTO.md`.** No HTTP calls.

| Test | What it checks |
|------|----------------|
| S14-01 | No stale "Click **+** enable" instructions remain |
| S14-02 | Workspace table in §3 has exactly the same row count as the `WORKSPACES` dict |
| S14-03 | `auto-compliance` workspace is documented |
| S14-04 | Persona count claimed in HOWTO matches actual YAML file count |
| S14-05 | §16 Telegram workspace list includes all workspace IDs |
| S14-06 | Port table in HOWTO matches the actual port assignments in `docker-compose.yml` |
| S14-07 | All `./launch.sh` commands documented in HOWTO actually exist in `launch.sh` |

---

### S16 — CLI Commands

**Tests `launch.sh` subcommands.**

| Test | What it checks |
|------|----------------|
| S16-01 | `./launch.sh status` exits 0 and produces output |
| S16-02 | `./launch.sh list-users` exits 0 and produces output |

---

### S21 — Notifications & Alerts

**Tests the notification system modules.** Skipped entirely if `NOTIFICATIONS_ENABLED=false`.

| Test | What it checks |
|------|----------------|
| S21-01 | `NotificationDispatcher` module imports without errors |
| S21-02 | `AlertEvent` formats correctly for all channels (Slack, Telegram, Pushover, Email) |
| S21-03 | `SummaryEvent` formats correctly for all channels |
| S21-04 | `/notifications/test` endpoint accepts a POST and returns 200 |
| S21-05 | Event type enum covers all expected types (`BACKEND_DOWN`, `BACKEND_RECOVERED`, `ALL_BACKENDS_DOWN`, `DAILY_SUMMARY`) |

---

### S3 — Workspace Routing (Ollama workspaces)

**The core routing test.** Sends real prompts through each Ollama-backed workspace and checks for domain-relevant responses.

| Test | What it checks |
|------|----------------|
| S3-01 | `/v1/models` exposes all 15 workspace IDs |
| S3-02 to S3-16 | Each Ollama workspace gets a domain-specific prompt and the response is checked for signal words. Workspaces tested: `auto`, `auto-creative`, `auto-documents`, `auto-security`, `auto-redteam`, `auto-blueteam`, `auto-video`, `auto-music` |
| S3-17 | **Content-aware routing test:** sends "exploit vulnerability payload shellcode" to `auto` workspace — verifies the pipeline's keyword scorer routes it to `auto-redteam` (not general). Checks pipeline logs for security workspace selection |
| S3-18 | **LLM intent router test:** sends a coding prompt to `auto` — verifies the LLM router (Llama 3.2 3B Abliterated) classifies it as coding intent. Checks pipeline logs |

**Why it matters:** If S3 passes, the pipeline correctly routes every workspace to the right backend/model. This is the "does the whole system work?" test.

---

### S4 — Document Generation MCP (Word / PowerPoint / Excel)

**Tests the document MCP server.** Generates real Office files.

| Test | What it checks |
|------|----------------|
| S4-01 | `create_word_document` produces a `.docx` file |
| S4-01b | The `.docx` file exists on disk and contains expected keywords (validates Python-docx output) |
| S4-02 | `create_powerpoint` produces a `.pptx` file with slides |
| S4-02b | The `.pptx` exists on disk and contains expected slide content |
| S4-03 | `create_excel` produces a `.xlsx` file with sheets |
| S4-03b | The `.xlsx` exists on disk and contains expected data rows |
| S4-04 | Pipeline round-trip: `auto-documents` workspace generates a document via chat (model writes content → MCP creates the file) |

---

### S5 — Code Generation & Sandbox Execution

**Tests code generation through the pipeline and execution in the sandbox MCP.**

| Test | What it checks |
|------|----------------|
| S5-01 | `auto-coding` workspace returns Python code when asked to write a Sieve of Eratosthenes. Checks for `def` or ` ```python` in the response |
| S5-02 | `execute_python` tool runs a prime sieve and returns correct count/sum |
| S5-03 | `execute_python` handles syntax errors gracefully (sends broken code — expects error message, not crash) |
| S5-04 | `execute_python` enforces timeout (sends infinite loop with 5s timeout — expects timeout error) |
| S5-05 | `execute_python` can import allowed packages (sends code using `math`, `json`, `collections`) |
| S5-06 | `execute_python` blocks dangerous operations (sends `import os; os.system('ls')` — expects rejection or sandboxed output) |

---

### S6 — Security Workspaces

**Tests the three security workspaces with domain-specific prompts.**

| Test | What it checks |
|------|----------------|
| S6-01 | `auto-security`: analyzes a misconfigured nginx config. Looks for signals like "autoindex", "security", "vulnerability" |
| S6-02 | `auto-redteam`: enumerates GraphQL injection vectors. Looks for "injection", "graphql", "introspection", "attack" |
| S6-03 | `auto-blueteam`: analyzes firewall logs for IoCs. Looks for "445", "smb", "lateral", "mitre", "attack" |

---

### S7 — Music Generation

**Tests the Music MCP server.** Uses MusicGen via transformers.

| Test | What it checks |
|------|----------------|
| S7-01 | `list_music_models` reports small/medium/large model sizes |
| S7-02 | `generate_music` produces a 5-second jazz WAV using musicgen-large |
| S7-02b | The WAV file exists on disk, has a valid RIFF header, and is >= 4.5 seconds long |
| S7-03 | Pipeline round-trip: `auto-music` workspace produces a music description when asked about a genre |

---

### S10 — Video MCP

**Tests the Video MCP server** (connectivity and routing — actual video generation is in the ComfyUI suite).

| Test | What it checks |
|------|----------------|
| S10-01 | Video MCP health endpoint returns 200 |
| S10-02 | `list_video_models` returns a model list |
| S10-03 | `auto-video` workspace: sends a cinematic shot description prompt — checks for video-domain signals ("wave", "camera", "lens", etc.) |

---

### S11 — All Personas (Ollama group)

**Tests every persona registered in `config/personas/`** through the pipeline. Grouped by model to minimize model loading.

| Test | What it checks |
|------|----------------|
| S11-01 | All personas are registered in Open WebUI's model list (via API) |
| S11-02+ | Each Ollama-backed persona receives a domain-specific prompt through its workspace. Response is checked for signal words. Example: `redteamoperator` gets a pentest prompt, `dataanalyst` gets a data analysis prompt |

**Personas are grouped by their `workspace_model`:**
- `dolphin-llama3:8b` → general personas (itexpert, techreviewer, techwriter, creativewriter)
- `deepseek-r1:32b-q4_k_m` → reasoning personas (dataanalyst, datascientist, statistician, etc.)
- Security models → security personas (cybersecurityspecialist, pentester, etc.)

MLX-backed personas are skipped here and tested in S30–S37.

---

### S30 — MLX: Qwen3-Coder-Next-4bit (Coding)

**Loads the Qwen3-Coder-Next model via the MLX proxy and tests the auto-coding workspace + 17 coding personas.**

| Test | What it checks |
|------|----------------|
| S30-ws | `auto-coding` workspace routes to MLX (not Ollama fallback). Sends a code generation prompt, checks for `def` or ` ```python` |
| S30-P:* | 17 coding personas tested sequentially: bugdiscoverycodeassistant, codebasewikidocumentationskill, codereviewassistant, codereviewer, devopsautomator, devopsengineer, ethereumdeveloper, githubexpert, javascriptconsole, kubernetesdockerrpglearningengine, linuxterminal, pythoncodegenerator, pythoninterpreter, seniorfrontenddeveloper, seniorsoftwareengineer, softwarequalityassurancetester, sqlterminal |

**Why a dedicated section:** This model is 46GB. By grouping all coding personas here, the model loads once and stays resident — no thrashing.

---

### S5 — Code Sandbox (runs after S30)

**Positioned after S30** so the MLX model is already loaded. Tests code generation + sandbox execution through `auto-coding`.

---

### S31 — MLX: Qwen3-Coder-30B-A3B-Instruct-8bit (SPL)

**Tests auto-spl workspace + 3 SPL/fullstack personas.** Model switch from Qwen3-Coder-Next.

| Test | What it checks |
|------|----------------|
| S31-ws | `auto-spl` workspace routes to MLX Qwen3-Coder-30B |
| S31-P:* | fullstacksoftwaredeveloper, splunksplgineer, ux-uideveloper |

---

### S32 — MLX: DeepSeek-R1-Distill-Qwen-32B (Reasoning)

**Tests reasoning/research/data workspaces.** Two model variants tested (abliterated-4bit for reasoning/research, MLX-8Bit for data).

| Test | What it checks |
|------|----------------|
| S32-ws | `auto-reasoning` and `auto-research` use the 4bit variant |
| S32-ws | `auto-data` uses the 8bit variant (separate model load) |

---

### S33 — MLX: Qwen3.5-35B-Claude-Opus (Compliance)

**Tests auto-compliance workspace + 2 compliance personas.**

| Test | What it checks |
|------|----------------|
| S33-ws | `auto-compliance` routes to MLX |
| S33-P:* | nerccipcomplianceanalyst, cippolicywriter |

---

### S34 — MLX: Magistral-Small (Mistral Reasoning)

**Tests auto-mistral workspace + 1 persona.**

| Test | What it checks |
|------|----------------|
| S34-ws | `auto-mistral` routes to MLX Magistral-Small |
| S34-P:* | magistralstrategist |

---

### S35 — MLX: Qwopus3.5-9B (Documents)

**Tests auto-documents workspace as a direct MLX test + pipeline workspace path.**

| Test | What it checks |
|------|----------------|
| S35-ws | `auto-documents` routes to MLX Qwopus3.5-9B |
| S35-direct | Direct MLX proxy inference (bypass pipeline) — confirms the proxy itself works |

---

### S36 — MLX: Dolphin3.0-Llama3.1-8B (Creative)

**Tests auto-creative workspace.** Lightweight model (~9GB).

| Test | What it checks |
|------|----------------|
| S36-ws | `auto-creative` routes to MLX Dolphin3.0 |

---

### S37 — MLX: gemma-4-31b-it-4bit (Vision, VLM)

**Tests auto-vision workspace + Gemma persona.** This is a VLM model — the MLX proxy switches to `mlx_vlm.server`.

| Test | What it checks |
|------|----------------|
| S37-ws | `auto-vision` routes through the VLM path. Tests both with and without images |
| S37-P:* | gemmaresearchanalyst |
| S37-vlm | Confirms the proxy switched to `mlx_vlm` server (not `mlx_lm`) |

---

### S38 — MLX: GLM-5.1 HEAVY (Frontier Agentic Coder)

**Optional HEAVY model (~38GB).** Only inference-tested if `TEST_HEAVY_MLX=true`. Without the env var, only config/static checks run. Missing model = WARN (cannot complete the test without it).

| Test | What it checks |
|------|----------------|
| S38-01 | GLM-5.1 model present in HuggingFace cache. **WARN** if not downloaded |
| S38-02 | Memory pre-check for ~38GB model |
| S38-03 | GLM-5.1 entry in `mlx-proxy.py` MODEL_MEMORY dict |
| S38-04 | Model load + inference (gated on `TEST_HEAVY_MLX=true`). **WARN** if skipped |
| S38-05 | Coding inference validation (Python linked-list reversal) |

---

### S39 — Ollama Model Direct Inference

**Tests every Ollama model in `backends.yaml` via direct API call.** Each model gets a domain-specific prompt with signal validation. Models not pulled return WARN (test cannot be completed). Covers models not exercised through workspace routing (S3) or persona tests (S11).

| Test | Model | Domain |
|------|-------|--------|
| S39-01/02 | dolphin-llama3:8b, dolphin-llama3:70b | General (Docker/containerization) |
| S39-03..08 | qwen3-coder:30b, qwen3.5:9b, devstral:24b, deepseek-coder-v2, deepseek-coder-v2-lite, glm-4.7-flash | Coding (Python functions) |
| S39-09 | llama3.3:70b-q4_k_m | Coding (binary search, PULL_HEAVY) |
| S39-10..12 | baronllm-abliterated, whiterabbitneo:33b, dolphin3-r1-mistral | Security (CORS, privilege escalation, OWASP) |
| S39-13 | tongyi-deepresearch-abliterated | Reasoning (architecture comparison) |
| S39-14/15 | qwen3-vl:32b, llava:7b | Vision (visual analysis capabilities) |

---

### S40 — MLX Model Direct Inference

**Tests MLX models in `backends.yaml` not already covered by S30-S38.** Each model is loaded into the MLX proxy and gets a direct inference test. Missing model = WARN. Heavy models (Llama-3.3-70B) gated on `TEST_HEAVY_MLX=true`.

| Test | Model | Domain |
|------|-------|--------|
| S40-01 | Qwen3-VL-32B-Instruct-8bit (VLM, 36GB) | Vision analysis |
| S40-02 | llava-1.5-7b-8bit (VLM, 8GB) | Vision analysis |
| S40-03 | GLM-OCR-bf16 (VLM, 2GB) | OCR capabilities |
| S40-04 | Devstral-Small-2507-MLX-4bit (18GB) | Coding (binary search tree) |
| S40-05 | DeepSeek-Coder-V2-Lite-Instruct-8bit (12GB) | Coding (LRU cache) |
| S40-06 | Llama-3.2-3B-Instruct-8bit (3GB) | Python data types |
| S40-07 | Llama-3.2-11B-Vision-Instruct-abliterated-4-bit (VLM, 7GB) | Vision capabilities |
| S40-08 | DeepSeek-R1-Distill-Qwen-32B-abliterated-8bit (34GB) | Reasoning (math) |
| S40-09 | Llama-3.3-70B-Instruct-4bit (HEAVY, 40GB) | Transformers architecture, gated |

---

### S22 — MLX Proxy Model Switching

**Intentionally forces model switches to verify the proxy handles them correctly.** Runs after all model-grouped sections.

| Test | What it checks |
|------|----------------|
| S22-01 | MLX proxy health — reports `state` and `active_server` (ready/none/switching are valid) |
| S22-02 | `/v1/models` lists available models |
| S22-03 | Sends a request to `auto-coding` that forces a model switch (e.g., from VLM back to text). Verifies the switch completes within the pipeline timeout |
| S22-04 | After switch: proxy is in `ready` state with the correct model loaded |
| S22-05 | **Crash recovery:** if proxy is in `down` state, test restarts it and verifies recovery |
| S22-06 | **Admission control:** attempts to load a model that would OOM — verifies the proxy rejects with HTTP 503 and an actionable message |

---

### S23 — Fallback Chain Verification

**The destructive test.** Kills backends one at a time and verifies the pipeline falls back gracefully.

| Test | What it checks |
|------|----------------|
| S23-00 | MLX watchdog is disabled (killed at startup to prevent auto-recovery during kill tests) |
| S23-01 | `/health` shows all backends and their healthy/unhealthy counts |
| S23-02 | Response includes model identity (which model actually answered) |
| S23-03 | **Primary path (MLX):** `auto-coding` with MLX loaded — confirms MLX is the primary responder |
| S23-04 | **Kill MLX → Ollama fallback:** stops MLX proxy, sends to `auto-coding` — verifies Ollama coding model answers instead. Checks pipeline logs for "fallback" |
| S23-05 | **Restore MLX:** restarts MLX proxy — verifies `auto-coding` routes back to MLX |
| S23-06 | **Kill Ollama → general fallback:** stops Ollama — verifies pipeline returns 503 or routes to remaining healthy backend |
| S23-07 | **Restore Ollama:** restarts Ollama — verifies normal routing resumes |
| S23-08 | **Kill watchdog restore:** verifies the MLX watchdog is restarted after the fallback tests complete |

**Why it matters:** This proves the system degrades gracefully when components fail, rather than returning cryptic errors.

---

## ComfyUI Suite (`portal5_acceptance_comfyui.py`)

Run separately: `python3 portal5_acceptance_comfyui.py`

### C0 — Prerequisites

| Test | What it checks |
|------|----------------|
| C0-01 | Python deps available (httpx, mcp, yaml) |
| C0-02 | Portal pipeline reachable |
| C0-03 | ComfyUI process running on host (`pgrep`) |
| C0-04 | ComfyUI API reachable (`http://host.docker.internal:8188/system_stats`) |

---

### C1 — ComfyUI Direct API

| Test | What it checks |
|------|----------------|
| C1-01 | `/system_stats` returns Python version and ComfyUI version |
| C1-02 | `/queue` is reachable (running/pending counts) |
| C1-03 | `/object_info` returns node catalogue — checks for required nodes (KSampler, CLIPTextEncode, VAEDecode, SaveImage) |
| C1-04 | Checkpoint models discovered via `/object_info` — lists available checkpoints |

---

### C2 — MCP Bridge Health

| Test | What it checks |
|------|----------------|
| C2-01 | ComfyUI MCP bridge health (:8910) |
| C2-02 | Video MCP bridge health (:8911) |
| C2-03 | Docker compose lists ComfyUI/video containers (INFO only — ComfyUI may run natively) |

---

### C3 — Model Discovery via MCP

| Test | What it checks |
|------|----------------|
| C3-01 | `list_workflows` returns checkpoint list via ComfyUI MCP |
| C3-02 | `list_video_models` returns model list via Video MCP |
| C3-03 | `list_samplers` returns sampler list (if supported) |

---

### C4 — Image Generation: FLUX Schnell (fast, 4 steps)

| Test | What it checks |
|------|----------------|
| C4-01 | FLUX schnell checkpoint is installed in ComfyUI |
| C4-02 | `generate_image` via MCP produces output (4 steps, seed=42) |
| C4-03 | Output image is accessible via ComfyUI `/view` endpoint (validates file exists) |

---

### C5 — Image Generation: FLUX Dev (high quality, optional)

| Test | What it checks |
|------|----------------|
| C5-01 | FLUX dev checkpoint installed (INFO if missing — optional) |
| C5-02 | `generate_image` with 20 steps, cfg=3.5 (higher quality) |

---

### C6 — Image Generation: SDXL (optional)

| Test | What it checks |
|------|----------------|
| C6-01 | SDXL checkpoint installed (INFO if missing) |
| C6-02 | `generate_image` with 25 steps, cfg=7, 1024x1024, negative prompt |

**Known issue:** SDXL on Apple M4 MPS often exceeds the 300s timeout → WARN. This is a test timeout, not a generation failure.

---

### C7 — Image Generation: Parameter Sweep

**Tests that different parameters produce valid results.** Uses the fastest available checkpoint.

| Test | What it checks |
|------|----------------|
| C7-01 | Identifies which checkpoint to use (prefers schnell) |
| C7-02 | Seed determinism run 1 (seed=1234, 4 steps) |
| C7-03 | Step variation (seed=1234, 8 steps) — different steps should still produce valid output |
| C7-04 | Negative prompt support (portrait with "cartoon, anime, sketch, blurry" exclusions) |

---

### C8 — Video Generation: Wan2.2 T2V

| Test | What it checks |
|------|----------------|
| C8-01 | `list_video_models` returns available models |
| C8-02 | Wan2.2 generates a 16-frame, 832x480, 4-step video clip (ocean waves at sunset) |
| C8-03 | Longer clip: 32 frames, 8 steps (time-lapse clouds) — only runs if C8-02 passed |

---

### C9 — Pipeline Round-Trips

**Tests the auto-video workspace through the pipeline** (not direct MCP).

| Test | What it checks |
|------|----------------|
| C9-01 | `auto-video` workspace: sends a cinematic shot description prompt — checks for 3+ video-domain signals |
| C9-02 | `auto-video` workspace: asks about ComfyUI workflow parameters — checks for workflow-specific terms |

---

### C10 — Output Validation

**Checks that ComfyUI output files actually exist and are valid.**

| Test | What it checks |
|------|----------------|
| C10-01 | ComfyUI `/history` has recent outputs (images or videos) |
| C10-02 | Most recent image: fetched via `/view`, size > 1KB, content-type is image |
| C10-03 | Most recent video: fetched via `/view`, size > 50KB, content-type is video |

---

## Execution Order (why this order?)

The sections run in a specific order to minimize model switching and maximize reliability:

1. **S17** — Rebuild first (ensures fresh code)
2. **S0, S1, S2** — Baseline checks (no LLM needed)
3. **S8, S9, S12, S13, S14, S16, S21** — Non-LLM tests (no model loading)
4. **S3, S4, S6, S7, S10, S15, S20, S11, S39** — Ollama workspaces + personas + direct model tests
5. **S30, S5, S31–S38, S40** — MLX models, one model per section (minimizes switching)
6. **S22** — Intentional model switch stress test
7. **S23** — Destructive fallback chain (kills/restores backends)

The ComfyUI suite runs independently because ComfyUI is a separate process with its own model management.

## Interpreting Results

- **All PASS** = ship it
- **WARN on optional models** (FLUX dev, SDXL, WhiteRabbitNeo 33B) = normal — those models aren't installed
- **WARN on MLX 503** = MLX proxy couldn't load the model (likely memory pressure) — Ollama fallback should work
- **FAIL on S1** = config drift — fix the YAML/code mismatch before anything else
- **FAIL on S2** = a service is down — check `docker compose ps` and `./launch.sh status`
- **BLOCKED on S23** = pipeline response missing `model` field — needs code fix in `router_pipe.py`
