# Portal 6.0.3 — How-To Guide

---

## 1. Quick Start

<!-- WIKI:GENERATED unit=unit-HOWTO-1-quick-start -->
Complete working examples for every feature. Each section shows: what it does, how to activate it, a working example, and how to verify.

**What:** Launch the entire platform with one command.

```bash
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
./launch.sh up
```

The `up` case in `launch.sh` copies `.env.example` to `.env` when it is missing, regenerates any secret still set to `CHANGEME` via `bootstrap_secrets` and the secret-repair loop, creates the shared workspace tree under `~/AI_Output`, pulls the Docker images, auto-starts the native services, checks hardware, and brings the compose stack up. A first run downloads images and model weights, so it takes tens of minutes rather than seconds; subsequent runs are near-instant.

When the stack is ready `launch.sh` prints the service URLs:

- Open WebUI: `http://localhost:8080`
- SearXNG: `http://localhost:8088`
- ComfyUI: `http://localhost:8188`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

`ENABLE_REMOTE_ACCESS=true` in `.env` makes Open WebUI bind to `0.0.0.0` instead of loopback, and `WEBUI_LISTEN_ADDR` is written back into `.env` so external restarts keep the same binding.

**Verify:**
```bash
./launch.sh status
```

## Why

First-run bootstrapping lives inside the `up` case rather than in a manual checklist so every post-clone dependency — env file, secrets, workspace tree, Docker images, model weights — is generated or fetched by one command and a fresh checkout converges to the same running stack as an old install. The secret-repair loop also makes an interrupted first run self-healing: re-running `up` regenerates whatever placeholder value is left over.
<!-- /WIKI:GENERATED -->

---

## 2. Chat with AI

<!-- WIKI:GENERATED unit=unit-HOWTO-2-chat-with-ai -->
**What:** Open WebUI connects to Portal Pipeline, which routes each request to the best-fit model.

**How:** Open `http://localhost:8080` and sign in with the admin credentials from `.env` — `OPENWEBUI_ADMIN_EMAIL` / `OPENWEBUI_ADMIN_PASSWORD`, the latter auto-generated on first run and printed by `launch.sh`. Open WebUI's `OPENAI_API_BASE_URL` points at the pipeline's `http://portal-pipeline:9099/v1` in `deploy/portal-5/docker-compose.yml`, so every chat flows through the router.

**Example — general chat:**
1. Select `Portal Auto Router` from the model dropdown
2. Type: `Explain how Docker networking works`
3. The `auto` workspace's `model_hint` (`huihui_ai/qwen3.5-abliterated:9b-ctx8k` in `config/portal.yaml`) selects the model served via Ollama

The `auto` workspace is special: when no explicit model is chosen, the LLM intent classifier (`_route_with_llm`, Layer 1 in `portal/platform/inference/router/routing.py`) picks the best-fit workspace, falling back to weighted keyword scoring (`_detect_workspace`, Layer 2) on low confidence or timeout. `DEFAULT_MODEL` in `.env.example` only sets Open WebUI's default picker selection.

**Verify routing:** run `./launch.sh status`, or `curl http://localhost:9099/v1/models` with `PIPELINE_API_KEY` as the bearer token.

## Why

Routing is deliberately split from serving: Open WebUI only knows one OpenAI-compatible endpoint, and the pipeline decides which workspace and model answer. Keeping the chat UI that thin means model selection, persona overrides, and tool grants can all evolve inside `config/portal.yaml` and `routing.py` without any Open WebUI change, and the two-layer classifier makes the router both accurate (LLM) and fast (keywords) without blocking the request on the classifier.
<!-- /WIKI:GENERATED -->

---

## 3. Workspaces

<!-- WIKI:GENERATED unit=unit-HOWTO-3-workspaces -->
**What:** Each workspace routes to a specialized model and activates the relevant tools.

**How:** Workspaces are defined in `config/portal.yaml` under the `workspaces:` block — each entry declares `module`, `name`, `model_hint`, `tools`, and `expose_to_owui`. Select one from the model dropdown; the exposed ones are exactly those with `expose_to_owui: true`. `./launch.sh sync-config` regenerates the derived artifacts (`workspace_routing` in `config/backends.yaml`, `.mcp.json`, and the Open WebUI workspace presets under `imports/openwebui/workspaces/`) so `config/portal.yaml` stays the single source of truth.

For the full live roster (production + eval workspaces, module, model hint) use `unit-fact-workspace-roster` — do not maintain a second handwritten table here. A few flagship examples verified against `config/portal.yaml`:

| Workspace | model_hint (Ollama) | Key tools |
|---|---|---|
| `auto` (Portal Auto Router) | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | LLM intent classifier routes onward |
| `auto-daily` | `gemma4:26b-a4b-it-qat-ctx8k` | web_search, create_word_document, execute_python |
| `auto-coding` | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | execute_python, execute_nodejs, execute_bash |
| `auto-security` | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k` | web_search, classify_vulnerability, execute_bash |
| `auto-documents` | `granite4.1:8b-ctx16k` | create_word_document, create_excel, create_powerpoint |
| `auto-music` | `lfm2.5:8b-ctx8k` | generate_music, speak, clone_voice |
| `auto-vision` | `qwen3-vl:32b-ctx8k` | transcribe_audio, generate_image |

`auto-video` is defined with `expose_to_owui: false` (shelved — see the Video Generation unit). Eval workspaces (the `bench-*` set) additionally require `PORTAL_ENABLE_EVAL=1` at pipeline startup.

**Example — coding:** select `Portal Code Expert` and ask a coding question; `auto-coding` answers with Qwen3-Coder-30B and its sandbox tools (`execute_bash`, `execute_python`, `sandbox_status`) run code on request.

## Why

Workspaces are pure configuration, not code. Putting name, model hint, tool grants, and OWUI exposure in one YAML block means adding or tuning a lane never requires a pipeline code change, and the module-toggle layer can hide an entire workspace family at sync time. Mechanically deriving the presets keeps the dropdown and routing in lockstep, which is why `sync-config` idempotence is enforced by the test suite.
<!-- /WIKI:GENERATED -->

---

## 4. Personas

<!-- WIKI:GENERATED unit=unit-HOWTO-4-personas -->
**What:** Pre-configured specialist prompts that shape the AI's behavior.

**How:** Personas live as one YAML file each under `config/personas/`. During seeding, `scripts/openwebui_init.py` reads them and creates model presets in Open WebUI, binding each persona to a `workspace_model` and an optional `variant`. Select a persona from the model dropdown alongside workspaces.

**Available personas:** use `unit-fact-persona-roster` for the generated live count, module ownership, workspace binding, and model pins. Do not maintain a second handwritten roster here.

To inspect the live module breakdown:

```bash
python3 -m portal.platform.inference.cli module list
```

**Example — red team:**

1. Select `Red Team Operator`.
2. Ask for an attack-surface analysis or lab-scoped exercise.
3. `config/personas/redteamoperator.yaml` declares `workspace_model: auto-security` and `variant: redteam`; the pipeline resolves the variant through `_resolve_workspace_variant` in `portal/platform/inference/router/preinject.py`, applying `auto-security`'s redteam variant model, prompt, and empty tool grant.

**Verify personas exposed by the pipeline:**

```bash
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer ${PIPELINE_API_KEY}" \
  | python3 -c "import sys,json; [print(m['name']) for m in json.load(sys.stdin)['data']]"
```

`PIPELINE_API_KEY` lives in `.env` (auto-generated on first `up`); the pipeline's `list_models` handler (`portal/platform/inference/router/handlers.py`) serves workspaces plus the IDE-curated persona entries so external pickers agree with Open WebUI.

## Why

Personas are data, not code: one YAML per persona means adding a specialist never touches the pipeline, and the workspace-model binding guarantees a persona is always served by the model family it was written for. Routing a persona through a workspace variant rather than a standalone workspace keeps model, prompt, tool grants, and guardrail posture in one place instead of duplicating them across near-identical workspaces.
<!-- /WIKI:GENERATED -->

---

## 5. Code Generation & Execution

<!-- WIKI:GENERATED unit=unit-HOWTO-5-code-generation-execution -->
**What:** Generate code with AI and execute it in an isolated Docker-in-Docker sandbox.

**Activate:** Select `Portal Code Expert` (`auto-coding`) from the model dropdown. Its `tools` list in `config/portal.yaml` grants `execute_python`, `execute_nodejs`, `execute_bash`, and `sandbox_status`, so the sandbox tools are available the moment the workspace is selected.

**How:** Execution runs through `portal/modules/coding/tools/code_sandbox_mcp.py`, the sandbox MCP server on the `portal5-sandbox` container. Each tool launches a throwaway container from an image (`python:3.11-slim`, `node:20-alpine`, `alpine:latest` by default) inside the Docker-in-Docker daemon, with a default `SANDBOX_TIMEOUT` of 30 seconds, no network (`SANDBOX_ALLOW_NETWORK=false`), and a small memory ceiling.

Environment knobs live in `.env`: `SANDBOX_TIMEOUT`, `SANDBOX_ALLOW_NETWORK`, and `SANDBOX_LAB_EXEC`. The last one swaps in the attack-image lab envelope used by the `-exec` security variants, widening the timeout and enabling a routable lab network (`$LAB_TARGET_*`). Pass an explicit `timeout` argument per call when a task may run long; the ceiling is enforced by the server, not the caller.

## Why

Code execution must never touch the host directly, so the sandbox MCP shells out to a Docker-in-Docker daemon with throwaway containers, a strict default timeout, and networking disabled by default. Because the isolation posture is expressed as env flags rather than hardcoded, the same tool surface serves both the locked-down default lane and the authorized lab-exec lane without duplicating handlers.
<!-- /WIKI:GENERATED -->

---

## 6. Security Analysis

<!-- WIKI:GENERATED unit=unit-HOWTO-6-security-analysis -->
**What:** One base workspace (`auto-security`) covering research, simulation, and execution tiers. The former sibling workspaces collapsed into `?variant=` query params (or a persona's `variant:` field) are resolved by `_resolve_workspace_variant` in `portal/platform/inference/router/preinject.py` instead of separate workspace ids. The complete variant catalog — including the newer `blueteam-orchestrated` and `blueteam-council` — is defined under `auto-security.variants` in `config/portal.yaml`; `unit-fact-security-variants` is the live index.

Verified variant summary from `config/portal.yaml`:

| Variant | Tier | Model hint | Tools |
|---|---|---|---|
| *(base)* | Research | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k` | web_search, web_fetch, classify_vulnerability, execute_python, execute_bash, kb_search, kb_list |
| `uncensored` | Research | `huihui_ai/baronllm-abliterated:latest-ctx8k` | execute_bash, execute_python, remember, recall |
| `redteam` | Simulation | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | none |
| `redteam-deep` | Simulation | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` | none |
| `blueteam` | Research | `granite4.1:8b-ctx8k` | web_search, web_fetch, classify_vulnerability, kb_search, kb_list |
| `pentest` | Execution | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4` | execute_bash, execute_python, web_search |
| `purpleteam` | Simulation, 2-hop | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` → `granite4.1:8b-ctx8k` | none |
| `purpleteam-deep` | Simulation, 4-hop | abliterated → granite → `qwen3-coder:30b-a3b-q4_K_M` → `qwen3.6:27b-q4_K_M` | none |
| `purpleteam-exec` | Execution, 4-hop | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` → same chain | execute_bash, execute_python, web_search |

The `pentest` variant runs inside the `portal5-attack` Kali image with `$LAB_TARGET_*` env vars pre-injected and a hard prompt constraint that it open with a live `execute_bash` call. Note the `pentest` model is the Qwen3.6-35B HauhauCS abliterated MoE, which replaced an earlier `gemma-4-abliterated:E2b-qat` pick after that model failed the tool-call reliability gate.

## Why

Collapsing the sibling workspaces into one base plus variants removed duplicate model registrations, prompt text, and tool grants that had drifted apart. The variant mechanism is a pure config transform applied at request time, so a tier change (an extra hop, a guardrail flip) is an edit to `config/portal.yaml`, not pipeline code, and the same resolution path serves both `?variant=` query params and persona `variant:` fields.
<!-- /WIKI:GENERATED -->

---

## 7. Document Generation

<!-- WIKI:GENERATED unit=unit-HOWTO-7-document-generation -->
**What:** Generate Word (.docx), Excel (.xlsx), and PowerPoint (.pptx) files from chat.

**Activate:** Select `Portal Document Builder` (`auto-documents`) from the model dropdown. Its `tools` list in `config/portal.yaml` grants `create_word_document`, `create_excel`, `create_powerpoint`, the matching `read_*` tools, and `transcribe_with_speakers`, so the Documents tool is available automatically in that workspace.

**How:** Documents are produced by the `portal-documents` MCP server (Docker container at port 8913, code under `portal/modules/documents/tools/`), which builds the bytes with `python-docx`, `openpyxl`, and `python-pptx`. Files are written to the shared workspace's `generated/documents/` directory and returned with a `download_url`. The `auto-documents` system prompt requires the model to include that link in its reply so the user can download the file from the chat.

## Why

Document output is a two-part contract: the MCP server owns the byte-level format work while the workspace prompt owns the chat behavior (always returning a download link). Keeping generation in a dedicated MCP means the same file-producing tools are available to any workspace that lists them, and writing into the shared workspace means files are immediately reachable by other services and by the host.
<!-- /WIKI:GENERATED -->

---

## 8. Image Generation

<!-- WIKI:GENERATED unit=unit-HOWTO-8-image-generation -->
**What:** Generate images using ComfyUI — FLUX, SDXL, and Qwen-Image checkpoints.

**Activate:** ComfyUI runs natively on the host (`./launch.sh install-comfyui`, installed into `COMFYUI_DIR`, served at `http://localhost:8188`) because a Docker container cannot reach the Metal GPU. The `mcp-comfyui` container (port 8910) exposes the `generate_image` / `start_image_generation` tools to models, and the `auto-image` workspace (`Portal Image Creator`) grants them, so selecting that workspace makes image generation available.

**How:** `portal/modules/media/tools/comfyui_mcp.py` drives ComfyUI's workflow API. The default `flux` model maps to the `comfyui:flux-schnell` checkpoint; `sdxl`, `qwen-image-2512`, and the `qwen-image-edit-*` editing models are selectable per call. Jobs can take minutes, so the tool surface splits into a blocking `generate_image` and the async `start_image_generation` + `get_image_status` pair. Outputs land in the shared workspace `generated/images/` and the MCP returns a URL. `.env` sets `COMFYUI_URL` and the `COMFYUI_TIMEOUT` ceiling. See `docs/COMFYUI_SETUP.md` for the full setup.

## Why

Image generation is split across two processes by hardware reality: ComfyUI must run on the host to use MPS, while the MCP bridge keeps the model-facing tool API uniform. The async job surface exists because diffusion jobs routinely outlast a chat request timeout, so models are taught to start a job, return the id, and poll rather than block.
<!-- /WIKI:GENERATED -->

---

## 9. Video Generation

<!-- WIKI:GENERATED unit=unit-HOWTO-9-video-generation -->
**Shelved (2026-07-29):** Video generation is not currently in operation.

Wan 2.2's `fp8_scaled` checkpoints (T2V-A14B, S2V-14B) crash on this host's Apple Silicon MPS stack — see `KNOWN_LIMITATIONS.md`, "Wan 2.2 fp8_scaled Checkpoints Crash on Apple Silicon MPS." TI2V-5B alone does work but was not judged worth exposing on its own. The `auto-video` workspace remains defined in `config/portal.yaml` with `expose_to_owui: false` so it stays hidden from the model dropdown, and the `mcp-video` container is profile-gated out of the default `./launch.sh up` set. Only image generation (`auto-image`, the ComfyUI MCP) is in operation.

The code path is left in place, not deleted, in case this becomes viable later — the `KNOWN_LIMITATIONS.md` entry lists what would need to change. `./launch.sh pull-wan22` still exists as an archival download command but must not be treated as enabling video operation.

## Why

Shelving rather than deleting preserves an operational option at near-zero cost: the workspace, the ComfyUI workflows, and the pull commands are tested code that only lacks a viable MPS checkpoint. Keeping `expose_to_owui: false` and the compose profile gate means the shelf stays literal — nothing video-facing is advertised to users, so the documented posture cannot silently rot into a half-working feature.
<!-- /WIKI:GENERATED -->

---

## 10. Music Generation

<!-- WIKI:GENERATED unit=unit-HOWTO-10-music-generation -->
**What:** Generate music clips from text descriptions using HuggingFace MusicGen.

**Activate:** Select `Music Producer` (`auto-music`) from the model dropdown. The Music tools — `generate_music`, `generate_continuation`, `list_music_models`, plus the speech and transcription tools — are granted by `auto-music`'s `tools` list in `config/portal.yaml`, so they are available when that workspace is selected.

**How:** `portal/modules/media/tools/music_mcp.py` runs the MusicGen models through the `transformers` library, not AudioCraft — AudioCraft's `torchtext`/`xformers` dependencies have no aarch64 wheels. Model sizes `small`, `medium`, `large` download to the HuggingFace cache on first use. The server runs host-native on Apple Silicon (install with `./launch.sh install-music`, auto-started by `up` through `_ensure_native_services`); the port is 8912. Clips write to the shared workspace `generated/music/` and the tool returns a download URL. Duration is capped at 30 seconds per clip; `generate_continuation` extends an existing WAV using a melody as conditioning.

## Why

Music generation is a large, cold model that Docker would run on CPU, so it is a host-native service kept out of the container set and auto-started only when installed. Routing the tools through the `auto-music` workspace rather than globally keeps the heavy models out of everyday chat while still exposing them to any persona that binds to that workspace.
<!-- /WIKI:GENERATED -->

---

## 11. Text-to-Speech

<!-- WIKI:GENERATED unit=unit-HOWTO-11-text-to-speech -->
**What:** Convert text to spoken audio using MLX-native speech (Kokoro + Qwen3-TTS).

**Activate:** Select `Music Producer` (`auto-music`) from the model dropdown. The TTS tools (`speak`, `clone_voice`, `list_voices`) are granted by `auto-music`'s `tools` list in `config/portal.yaml` — they are not available in every workspace.

**How:** The host-native MLX speech server (`scripts/mlx-speech.py`, port 8918) provides TTS via Kokoro (default backend, `af_heart` default voice) and Qwen3-TTS (voice cloning, emotion control, 10 languages). Start it with `./launch.sh start-speech` — `_launch_start_speech` in `scripts/lib/services.sh` requires Apple Silicon and `mlx-audio`, and models load lazily on the first request. The Docker `mcp-tts` container (port 8916, `portal/modules/media/tools/tts_mcp.py`) is the fallback tool server, defaulting to the kokoro-onnx backend. Audio files land in `generated/speech/` and the tool returns a download URL.

## Why

Speech is an audio runtime, not part of the chat inference tier, so it runs outside Ollama entirely: a native server on Apple Silicon uses the Metal GPU for fast synthesis while the MCP tool layer keeps the model-facing call uniform. Lazy model loading keeps `start-speech` cheap to bring up — the first utterance pays the load cost, not the startup command.
<!-- /WIKI:GENERATED -->

---

## 12. Speech-to-Text (ASR)

<!-- WIKI:GENERATED unit=unit-HOWTO-12-speech-to-text-asr -->
**What:** Transcribe audio files to text — MLX-native ASR and a Docker Whisper fallback.

**Activate:** Transcription is available only in workspaces that grant the tools: `transcribe_audio` and `transcribe_with_speakers` appear in `auto-music`, `auto-daily`, `auto-audio`, `auto-vision`, and `auto-documents` (`config/portal.yaml`). It is not enabled in every workspace.

**How:** Two engines back the tools. The Docker `mcp-whisper` server (port 8915, `portal/modules/media/tools/whisper_mcp.py`) handles plain transcription. The host-native MLX speech server (`scripts/mlx-speech.py`, port 8918) includes Qwen3-ASR (MLX-native). For speaker-labeled transcripts use `./launch.sh start-transcribe` (mlx-transcribe, port 8924) — see the Diarized Transcription unit. The `auto-music` prompt tells the model to call `transcribe_audio` with no file argument so the most recently uploaded audio is auto-detected from the shared workspace `uploads/` directory.

## Why

Transcription availability is deliberately workspace-scoped because ASR is not free — each engine loads a model and takes GPU time, so granting it everywhere would add latency to chat lanes that never transcribe. Scoping by workspace tools means audio-heavy lanes (music, audio analysis, documents) carry the capability while general chat stays lean.
<!-- /WIKI:GENERATED -->

### Diarized Transcription (Speaker-Labeled Transcripts)

<!-- WIKI:GENERATED unit=unit-HOWTO-diarized-transcription-speaker-labeled-transcripts -->
**What:** Drop an audio file in OWUI chat, get back a transcript with speaker labels (SPEAKER_00, SPEAKER_01, ...). Outputs JSON + Markdown to the shared workspace at `~/AI_Output/generated/transcripts/`.

**Pre-flight (one-time):**

1. Accept the gated pyannote models on HuggingFace (`pyannote/speaker-diarization-3.1` — the pipeline pulls the segmentation model internally)
2. Generate a read token at https://huggingface.co/settings/tokens
3. Add to `.env`: `HF_TOKEN=hf_...` — without it, `scripts/mlx-transcribe.py` refuses to load the diarization pipeline

**Start the service (Apple Silicon primary):**
```bash
./launch.sh start-transcribe
```
`_launch_start_transcribe` in `scripts/lib/services.sh` warns when `HF_TOKEN` is missing, then registers the server (port 8924, `MLX_TRANSCRIBE_PORT`) as a native service. The engine is `mlx-whisper` (large-v3-turbo) for transcription plus pyannote.audio 3.1 diarization on MPS; the `voxtral-mini-3b` engine is available for multilingual files. OWUI chats reach it through the workspace that grants `transcribe_with_speakers` (e.g. `auto-documents`), and the generated files are served as download URLs on port 8924.

## Why

Diarization is gated HuggingFace content, so the token requirement is enforced at load time rather than silently skipped — a transcript that claims speaker labels without pyannote would be wrong in a hard-to-notice way. Outputting both canonical JSON and a Markdown sidecar into the shared workspace means the transcript is immediately available to any other service, not just the chat thread that requested it.
<!-- /WIKI:GENERATED -->

---

## 13. Web Search

<!-- WIKI:GENERATED unit=unit-HOWTO-13-web-search -->
**What:** Web search via a self-hosted SearXNG instance.

**Activate:** Workspaces opt in with `enable_web_search: true` in `config/portal.yaml` (for example `auto-daily`, `auto-research`, `auto-compliance`); the model then sees `web_search` / `news_search` in its tool grant. `auto-research` even forces `tool_choice: required` because it once narrated a search without completing it.

**How:** The `web_search` tool lives in `portal/modules/research/tools/web_search_mcp.py` and queries the SearXNG container (port 8088) at `SEARXNG_URL`. SearXNG is self-hosted — no third-party AI provider sees queries — but the engines configured in `config/searxng/settings.yml` are public ones (google, duckduckgo, bing, github, stackoverflow), so query strings do reach those engines. If `BRAVE_API_KEY` is set, the tool switches to the Brave backend instead.

## Why

Self-hosting the aggregator keeps the search control plane (which engine, what formatting, what rate limits) under Portal's config rather than inside a model call, while the workspace-level `enable_web_search` flag keeps the capability out of lanes that do not need it. The privacy claim is accurate only about AI providers, which is why the engine list is the grounding for what actually leaves the host.
<!-- /WIKI:GENERATED -->

---

## 14. Document RAG (Knowledge Base)

<!-- WIKI:GENERATED unit=unit-HOWTO-14-document-rag-knowledge-base -->
**What:** Upload documents in Open WebUI and have conversations grounded in their content.

**How:** Two layers provide this. Open WebUI owns the knowledge base itself — chat uploads become a searchable collection through its native RAG, which is out of Portal 5's scope by design. On the pipeline side, workspaces with `auto_rag: true` in `config/portal.yaml` (e.g. `auto-daily`) get automatic knowledge-base context: before answering, the router dispatches a `kb_search` against the `portal-rag` MCP (port 8921) and injects the top snippets into the prompt (`inject_retrieved_context` in `portal/platform/inference/router/context_inject.py`). Workspaces can also grant the explicit `kb_search` / `kb_list` tools for the model to call on demand.

## Why

Document grounding is deliberately split: Open WebUI keeps the uploaded corpus and search index — the durable knowledge store — while the pipeline only reads it at request time through tool dispatch. That separation means a knowledge base works without Portal touching Open WebUI internals, and auto-injection is an opt-in workspace flag so RAG latency only affects lanes that opt into it.
<!-- /WIKI:GENERATED -->

---

## 15. User Management

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-approve-pending-users -->
Self-registration arrives with the `pending` role because `DEFAULT_USER_ROLE=pending` in `.env.example` is the shipped default, and a pending account has no access until an admin promotes it. Two promotion paths exist. The web path is Open WebUI's Admin Panel > Users: locate the pending account and change its role to `user`. The CLI path is `./launch.sh add-user <email> [name] [role]` with an explicit `pending` role, whose role values scripts/lib/users.sh documents as `user | admin | pending`. `ENABLE_SIGNUP=true` toggles whether self-registration exists at all.

## Why

Pending-by-default is the deliberate team-deployment posture: nobody gains access silently on a shared box, and every account is either approved or created by an operator. Both registration paths share the same role vocabulary, so the approval gate stays consistent whether a user self-signs or is provisioned from the shell.
<!-- /WIKI:GENERATED -->

---

## 16. Telegram Bot

<!-- WIKI:GENERATED unit=unit-HOWTO-16-telegram-bot -->
1. Message **@BotFather** on Telegram -> `/newbot` -> copy the token
2. Get your Telegram user ID from **@userinfobot**
3. Add to `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=your-token-here
   TELEGRAM_USER_IDS=your-user-id
   ```
4. Start: `./launch.sh up-telegram` — the `up-telegram` case in `launch.sh` refuses to start when `TELEGRAM_BOT_TOKEN` is unset, then runs `docker compose --profile telegram up -d`
5. Message your bot `/start` to verify — the bot's `/start` handler in `portal_channels/telegram/bot.py` replies

The bot container (`portal-telegram` in `deploy/portal-5/docker-compose.yml`) is profile-gated: plain `./launch.sh up` auto-detects the token and includes the telegram profile, while `up-telegram` forces it. The bot relays messages to the pipeline via `PIPELINE_URL` with `PIPELINE_API_KEY`, `TELEGRAM_USER_IDS` (comma-separated) controls which Telegram users may talk to it, and `TELEGRAM_DEFAULT_WORKSPACE` selects the routing workspace when the user has not set one with `/workspace`.

## Why

A messaging bot is just a thin channel adapter: all the intelligence stays in the pipeline, so the bot container only relays text between Telegram and the OpenAI-compatible router. Making it a compose profile rather than a default service keeps the token-less install clean, and the token auto-detection in `up` means turning the channel on is a one-line `.env` change with no extra command.
<!-- /WIKI:GENERATED -->

---

## 17. Slack Bot

<!-- WIKI:GENERATED unit=unit-HOWTO-17-slack-bot -->
1. Go to https://api.slack.com/apps -> **Create New App** -> **From scratch**
2. Under **OAuth & Permissions** -> add bot scopes:
   `app_mentions:read`, `chat:write`, `channels:history`, `im:history`, `im:read`, `im:write` (Slack-side app configuration)
3. Under **Socket Mode** -> enable it -> generate an **App-Level Token** (xapp-...)
4. Install app to your workspace
5. Add to `.env`:
   ```bash
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_SIGNING_SECRET=...
   ```
6. Start: `./launch.sh up-slack` — the `up-slack` case in `launch.sh` requires both `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` before running `docker compose --profile slack up -d`
7. Mention `@portal` in any channel to verify — `portal_channels/slack/bot.py` registers an `app_mention` event handler

The bot container (`portal-slack` in the compose file) receives the three tokens as env vars and runs `python -m portal_channels.slack.bot`. It connects via Socket Mode, so no public webhook or ingress is required. `SLACK_DEFAULT_WORKSPACE` sets the routing workspace for DMs and unmapped channels.

## Why

Slack integration uses Socket Mode precisely because it needs no public endpoint: the app-level token establishes an outbound WebSocket from the bot container, which keeps the whole deployment firewalled. The two-token requirement (bot token for the app, app token for the socket) is why `up-slack` validates both before starting — a half-configured bot fails loudly instead of silently ignoring mentions.
<!-- /WIKI:GENERATED -->

---

## 18. Notifications & Alerts

<!-- WIKI:GENERATED unit=unit-HOWTO-18-notifications-alerts -->
**What:** Get operational alerts and daily usage summaries via Slack, Telegram, Email, Pushover, or a generic webhook.

**How:** The pipeline's notification dispatcher (`portal/platform/inference/notifications/`) fires `AlertEvent` and `SummaryEvent` messages to every configured channel. Enable it with `NOTIFICATIONS_ENABLED=true` in `.env` (default `false`). Each channel is configured by its env var in `.env.example`:

- Slack: `SLACK_ALERT_WEBHOOK_URL` / `SLACK_ALERT_CHANNEL`
- Telegram: `TELEGRAM_ALERT_BOT_TOKEN` / `TELEGRAM_ALERT_CHANNEL_ID`
- Email: `SMTP_HOST` plus the `EMAIL_ALERT_TO` recipient
- Pushover: `PUSHOVER_API_TOKEN` + `PUSHOVER_USER_KEY`
- Generic: `WEBHOOK_URL`

The daily summary is scheduled by `ALERT_SUMMARY_ENABLED` (default true), `ALERT_SUMMARY_HOUR`, and `ALERT_SUMMARY_TIMEZONE`.

**Verify:** `POST /notifications/test` on the pipeline (`portal/platform/inference/router/handlers.py`) fires a real test alert plus a summary with live request counts, and reports the per-channel configured state. It answers 503 when the dispatcher is disabled.

## Why

Alerting lives in the pipeline process rather than a separate daemon so it shares the request telemetry it reports on — the daily summary needs live counters, so it reads them from the same memory the router writes. Channel configuration is pure env plumbing, which keeps notification support out of Open WebUI and lets an operator add a channel without a rebuild.
<!-- /WIKI:GENERATED -->

---

## Shared Workspace

<!-- WIKI:GENERATED unit=unit-HOWTO-shared-workspace -->
**What:** A single host directory that all Portal 5 services read from and write to. Files dropped in OWUI chat, MCP-generated outputs, and host-native script outputs all live here, eliminating cross-service file-bridging friction.

**Where:** `AI_OUTPUT_DIR` in `.env` (default `~/AI_Output`). Containers see it mounted at `/workspace` with `WORKSPACE_DIR=/workspace` (docker-compose volumes), and Open WebUI's uploads bind-mount `${AI_OUTPUT_DIR}/uploads` to `/app/backend/data/uploads`. Path resolution lives in `portal/platform/mcp_host/workspace.py`: `WORKSPACE_DIR` → `AI_OUTPUT_DIR` → `/workspace` → `~/AI_Output`.

**Layout:**
```
~/AI_Output/
├── uploads/                ← Files dropped in OWUI chat
└── generated/
    ├── transcripts/        ← Diarized transcripts (mlx-transcribe, whisper)
    ├── documents/          ← Word/Excel/PowerPoint (documents MCP)
    ├── images/             ← ComfyUI outputs
    ├── videos/             ← Retained archival video-output category
    ├── music/              ← Music MCP outputs
    └── speech/             ← TTS outputs
```
`_VALID_CATEGORIES` in `workspace.py` also admits `models3d` (CAD render output).

**Initialize:**
```bash
./launch.sh workspace-init
```
(Run automatically on first `./launch.sh up` — the `up` case creates the tree.)

**Inspect:**
```bash
./launch.sh workspace-status     # File counts and sizes per category (cli workspace status)
./launch.sh workspace-show       # Resolved paths (host vs container)
```

**Use from MCP code (new modules):**
```python
from portal.platform.mcp_host import get_uploads_dir, get_generated_dir, resolve_upload_path
```

## Why

A single shared root with category subdirectories is the interface contract between services that otherwise have no shared filesystem understanding: a document MCP writes `generated/documents/`, the host user finds it in `~/AI_Output/`, and OWUI uploads land in `uploads/` for every service to read. Centralizing the paths in `mcp_host/workspace.py` means a future remap — a different mount point or drive — is one configuration change instead of a repo-wide search-and-replace.
<!-- /WIKI:GENERATED -->

---

## 19. Backup & Restore

<!-- WIKI:GENERATED unit=unit-HOWTO-19-backup-restore -->
Backup and restore are implemented in `scripts/lib/backup.sh`.

```bash
./launch.sh backup                # Save all data to ./backups/ (or pass an output dir)
./launch.sh restore <backup-dir>  # Restore from a backup directory
```

`_launch_backup` creates a timestamped directory `portal5_backup_<timestamp>` under `./backups/` and fills it with `openwebui-data.tar.gz` (the Open WebUI data volume — users, chat history, settings), `grafana-data.tar.gz` (Grafana dashboards/datasources), a copy of `.env`, and copies of `config/` and `imports/`. `_launch_restore` prompts for confirmation, stops the stack, wipes and restores the two volumes from the tarballs, and copies `.env` back. Ollama model weights are NOT included — they live in the `ollama-models` volume, which neither backup nor restore touches; re-download them with `./launch.sh pull-models`.

## Why

Backup is scoped to small, generated state — OWUI data, Grafana, env, config — and deliberately excludes the large, reproducible Ollama weights that `pull-models` can always rebuild. A timestamped directory instead of a single tarball makes restores auditable and safe, and the confirmation prompt plus stack teardown in `_launch_restore` prevents restoring onto a live database.
<!-- /WIKI:GENERATED -->

---

## 20. Cluster Scaling

<!-- WIKI:GENERATED unit=unit-HOWTO-20-cluster-scaling -->
**What:** Add more machines to increase throughput — no pipeline code changes needed.

**How:** Cluster scaling is a `config/backends.yaml` edit (CLAUDE.md Rule 1). The file's `backends:` block lists backend groups (general, coding, security, reasoning, vision, creative); each backend declares a `type` (ollama) and a `url` — e.g. `http://192.168.1.102:11434` for a second Mac Studio running Ollama. `BackendRegistry` in `portal/platform/inference/cluster_backends.py` loads this file at startup (resolving the path across container `/app/config/backends.yaml`, local dev, and CI), expands `${OLLAMA_URL}`-style env refs, and health-checks each backend. After editing, restart the pipeline container so the registry re-reads the file. Never edit the generated `workspace_routing` block — `sync-config` owns it.

The full scale-out walkthrough is `docs/CLUSTER_SCALE.md` (single Mac through a 12-node cluster).

## Why

Capacity is treated as data, not architecture: because the router only knows backends through the registry, adding a node is a YAML edit plus a restart. Keeping `workspace_routing` generated while `backends:` stays hand-edited preserves the two jobs — routing intent belongs to the workspaces, hardware topology belongs to the operator — so the scaling surface is exactly the file the operator already owns.
<!-- /WIKI:GENERATED -->

---

## 21. Remote API Access (Pipeline at :9099)

<!-- WIKI:GENERATED unit=unit-HOWTO-21-remote-api-access-pipeline-at-9099 -->
**What:** The Portal Pipeline exposes an OpenAI-compatible HTTP API on port 9099. Any tool that accepts a custom OpenAI base URL can connect directly — no Open WebUI required.

**Endpoints** (`portal/platform/inference/router/app.py`):

- `GET /v1/models` — `list_models`, workspaces + IDE-curated persona entries
- `POST /v1/chat/completions` — `chat_completions`, streaming included
- `POST /v1/messages` — Anthropic-compatible message passthrough
- `GET /v1/backends` — registry health
- `GET /health` — liveness

**Auth:** requests need `Authorization: Bearer ${PIPELINE_API_KEY}`; `PIPELINE_API_KEY` is in `.env` (auto-generated on first `./launch.sh up`). Open WebUI itself connects this way: `OPENAI_API_BASE_URL=http://portal-pipeline:9099/v1` in `deploy/portal-5/docker-compose.yml`. The port maps to `0.0.0.0:9099:9099`, so remote clients can reach it if the host is reachable.

**Verify:**
```bash
curl http://localhost:9099/health
curl http://localhost:9099/v1/models -H "Authorization: Bearer ${PIPELINE_API_KEY}"
```

## Why

Exposing the same router as a plain HTTP API is what lets Open WebUI, the Telegram and Slack bots, IDE pickers, and arbitrary scripts all share one routing brain. Because auth is a single shared bearer key rather than per-client state, any consumer can point its OpenAI client at the pipeline and inherit workspace routing, persona handling, and tool dispatch without knowing any of it.
<!-- /WIKI:GENERATED -->

---

## 22. MLX Acceleration (Apple Silicon) — RETIRED

<!-- WIKI:GENERATED unit=unit-HOWTO-22-mlx-acceleration-apple-silicon-retired -->
**Retired (commit 3a0c58e).** The MLX inference proxy was removed; all chat inference now runs through Ollama (port 11434) with its native MLX Metal backend on Apple Silicon. This is a standing decision, not a gap: Ollama 0.32.4+ carries the Metal-residency fix that keeps pinned router and inference models loaded together, reaching parity with standalone `mlx_lm` throughput while removing the dual-stack operational overhead. The Ollama-only inference tier is recorded in `config/backends.yaml` (every backend is `type: ollama`) and enforced as a project rule; see the MLX notes in `KNOWN_LIMITATIONS.md`.

The MLX speech (port 8918), transcription (port 8924), embedding (port 8917), and reranker (port 8925) servers documented elsewhere in this guide are unaffected and remain in use — MLX is not gone from the project, only from chat inference. `COMPUTE_BACKEND=mps` in `.env.example` records the Apple Silicon Metal target.

## Why

Retiring the proxy kept one inference tier instead of two, which removed a whole class of admission-control and thread-patch maintenance at the cost of a hardware-accelerated fallback that no longer outperformed the native path. The distinction matters for future work: a regression in Ollama Metal performance is a reason to revisit, not evidence that the retired proxy should return, and the audio and retrieval runtimes legitimately keep using MLX.
<!-- /WIKI:GENERATED -->

---

## 23. Metrics & Monitoring

<!-- WIKI:GENERATED unit=unit-HOWTO-23-metrics-monitoring -->
**What:** Prometheus metrics collection and Grafana dashboards for the pipeline.

**How:** The pipeline exposes Prometheus-compatible metrics at `GET /metrics` (`metrics` in `portal/platform/inference/router/handlers.py` — intentionally unauthenticated so Prometheus can scrape it). The `prometheus` service scrapes on port 9090 using `config/prometheus/prometheus.yml`, and the `grafana` service serves on port 3000 with dashboards and datasources provisioned from `config/grafana/dashboards` and `config/grafana/datasources` (both defined in `deploy/portal-5/docker-compose.yml`). Grafana login is `admin` / `GRAFANA_PASSWORD` from `.env`. Both are part of the default `./launch.sh up` stack.

**Inspect:**
```bash
./launch.sh status
curl http://localhost:9090/-/healthy
curl http://localhost:9099/metrics
```

## Why

Observability is kept out of Open WebUI and out of the pipeline's code: the router only emits Prometheus text, and dashboards live as provisioned files under `config/grafana/`. That makes metrics reproducible from git — there are no click-configured panels to lose — and lets an operator point any Prometheus-compatible stack at the pipeline without changing Portal itself.
<!-- /WIKI:GENERATED -->

---

## Quick Reference: All CLI Commands

<!-- WIKI:GENERATED unit=unit-HOWTO-quick-reference-cli-commands -->
All commands below are the actual `case` branches in `launch.sh` (or dispatch into `python3 -m portal.platform.inference.cli`).

# Start / stop
./launch.sh up              # Start everything (first run bootstraps .env + secrets + workspace)
./launch.sh down            # Stop (data preserved)
./launch.sh status          # Check service health

# Test everything is working
./launch.sh test            # Live smoke tests against the running stack (cli smoke)

# Pull specialized models (security, coding, reasoning -- 30-90 min)
./launch.sh pull-models     # cli models pull

# MLX native services (Apple Silicon)
./launch.sh start-speech    # Start MLX speech server (:8918) — idempotent, reports if running
./launch.sh stop-speech     # Stop MLX speech server
./launch.sh start-transcribe  # Start mlx-transcribe (:8924)
./launch.sh stop-transcribe   # Stop mlx-transcribe

# User management
./launch.sh add-user alice@example.com "Alice Smith"   # optional third arg: user|admin|pending role
./launch.sh list-users

# Enable messaging channels (requires tokens in .env)
./launch.sh up-telegram     # Start Telegram bot (compose --profile telegram)
./launch.sh up-slack        # Start Slack bot (requires SLACK_BOT_TOKEN + SLACK_APP_TOKEN)
./launch.sh up-channels     # Start both

# Backup and restore
./launch.sh backup          # Save to ./backups/portal5_backup_<timestamp>/
./launch.sh restore <dir>   # Restore from a backup directory (not a single file; prompts first)

# Seeding
./launch.sh seed            # Re-seed Open WebUI (workspaces + personas) — skips existing presets
./launch.sh reseed          # Force-refresh all presets (FORCE_RESEED=true)

# Update (single command: git pull + rebuild + model refresh + re-seed)
./launch.sh update                  # cli update — full pass
./launch.sh update --skip-models    # Skip the Ollama model refresh (faster)
./launch.sh update --models-only    # Only refresh models

# Cleanup
./launch.sh clean           # Stop + wipe Open WebUI data (keeps Ollama model weights)
./launch.sh clean-all       # Stop + wipe everything including models
./launch.sh rebuild         # Rebuild portal-pipeline + MCP images, restart

# Workspace
./launch.sh workspace-init     # Create shared workspace tree (uploads, generated/*)
./launch.sh workspace-status   # File counts and sizes per category
./launch.sh workspace-show     # Resolved paths (host vs container)

## Why

This surface is deliberately a thin shell over `launch.sh` cases and the typed CLI, so every command has one implementation and the usage text in the `*)` branch stays the reference. Commands that need real logic — `pull-models`, `update`, `test`, workspace — delegate to `portal.platform.inference.cli`, keeping the shell file declarative and testable instead of growing bespoke logic in bash.
<!-- /WIKI:GENERATED -->
