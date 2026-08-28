# Portal 5 — Local AI Platform

Portal 5 is a complete, private AI platform that runs on your hardware: text,
code, security analysis, images, music, documents and voice — all local. It
connects to Open WebUI, Telegram and Slack, and routes each task automatically to
the workspace that carries the right model and toolset. The retained
video-generation code is shelved and not part of normal operation, documented in
`KNOWN_LIMITATIONS.md` and left unregistered in `config/portal.yaml`
(`mcp_fleet`), where the `video` fleet entry is intentionally removed.

Inference is fully local: prompts and responses never leave the machine. Model
downloads from HuggingFace or Ollama registries transmit standard HTTP metadata,
and if `HF_TOKEN` is configured for gated models, authentication requests are sent
to HuggingFace. No cloud accounts or usage fees are required.

## Why

The platform is scoped as an enhancement layer over Open WebUI rather than a
replacement web stack, which keeps authentication, chat history and RAG inside a
battle-tested frontend while the pipeline owns routing and model selection. The
video shelving is an honesty contract: code is retained for future work but is
neither advertised nor operated until the crash limitations are resolved.

---

## Prerequisites

The requirements `./launch.sh up` actually enforces are in `_check_hardware` in
`scripts/lib/util.sh`, run on every start:

| Requirement | Enforced minimum | Notes |
|---|---|---|
| **RAM** | 16 GB | warns below 32 GB (enough for core models; 32+ for the full catalog) |
| **Disk** | 20 GB free | warns below 50 GB; FLUX alone is about 12 GB |
| **Docker** | running daemon (5 s timeout) | a hung Docker Desktop is detected and the user is offered a process kill |
| **Ollama** | reachable on :11434 | auto-restarted by `_ensure_native_services` via `sudo -n launchctl kickstart -k system/com.portal5.ollama` if configured |

Apple Silicon is the recommended platform: `install-ollama` reports the pinned
native Ollama install's status (a system LaunchDaemon, `com.portal5.ollama` —
not Homebrew, which lags upstream releases below this project's minimum
version; disabled and uninstalled 2026-08-10), `install-comfyui` sets up
ComfyUI with an MPS venv, and the native MLX services run on the M-series
Metal path. On non-Apple-Silicon machines the installers print Linux/Docker
alternatives instead of failing.

## Why

The hardware gate runs before any pull or compose step so the stack fails fast
with a readable reason instead of dying mid-download or silently OOMing at first
inference. The thresholds come from the real working set: the router plus a pinned
model need 16 GB, and the FLUX checkpoint sets the floor for the disk check.

---

## Quick Start

```bash
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
./launch.sh up
```

The `up` case in `launch.sh` does the whole first boot: it copies `.env.example`
to `.env` if missing, generates any secrets still set to CHANGEME, initializes the
shared workspace directories, stops any previously running stack, pulls Docker
images, runs the hardware and port pre-flight checks, starts the compose stack
(profiles auto-selected from Telegram/Slack tokens), and launches the ARM64
embedding server on Apple Silicon. The `ollama-init` compose service pulls the
three core models (see the core-models unit).

When it finishes, the terminal prints the real endpoint list:

```
[portal-5] Stack started.
  Open WebUI:  http://localhost:8080
  SearXNG:     http://localhost:8088
  ComfyUI:     http://localhost:8188
  Grafana:     http://localhost:3000  (admin / check .env)
  Prometheus:  http://localhost:9090
```

Sign in at http://localhost:8080 with the admin credentials in `.env`
(`OPENWEBUI_ADMIN_EMAIL` defaults to `admin@portal.local`, password is the
auto-generated `OPENWEBUI_ADMIN_PASSWORD`). Do not commit `.env`.

## Why

The zero-setup contract is that a fresh machine reaches a usable stack from one
command: secret generation, workspace init, hardware checks and model bootstrap
all happen inside `up` so the operator never hand-edits a config to get started.
The printed endpoints are the actual compose service URLs, so the first login uses
credentials that already exist in `.env`.

---

## What Starts Automatically

`./launch.sh up` starts the core Docker stack (compose services plus profiles
auto-selected from Telegram/Slack tokens). Host-native Apple Silicon services
start when their launchd agent has been installed — `_ensure_native_services` in
`scripts/lib/util.sh` checks each registered launchd label (ComfyUI, both music backends,
MLX Speech, MLX Transcribe, embedding) and boots the service via `launchctl` or a
background `nohup` fallback.

| Service | What it does | URL/port |
|---|---|---|
| Open WebUI | Chat interface — main portal | http://localhost:8080 |
| Portal Pipeline | Routing, auth, metrics, MCP dispatch | :9099 |
| Ollama | Local GGUF models via Metal | :11434 |
| SearXNG | Private web search | :8088 |
| ComfyUI | Image generation (host-native; video shelved) | http://localhost:8188 |
| MCP fleet | ComfyUI :8910, Music-MiniMax :8912, Documents :8913, Sandbox :8914, Whisper :8915, TTS :8916, Security :8919, Memory :8920, RAG :8921, Research :8922, Browser :8923, CAD :8926, Proxmox :8927 | config/portal.yaml |
| Pipeline MCP | Stack introspection + FastContext explorer | :8928 |
| MITRE ATT&CK MCP | Technique lookup, data sources, detections | :8929 |
| Detections MCP | SPL library search, validate_syntax, explain | :8932 |
| Wiki MCP | Canonical knowledge layer — search, get_unit | :8931 |
| MLX Transcribe | Diarized transcription (Apple Silicon) | :8924 |
| MLX Speech | Kokoro TTS + Higgs Audio v2 voice clone + Qwen3-TTS/ASR (Apple Silicon) | :8918 |
| Embedding | Harrier-0.6B text embeddings | :8917 |
| Reranker | Qwen3-Reranker-0.6B two-stage RAG | :8925 |
| Prometheus | Metrics collection | http://localhost:9090 |
| Grafana | Metrics dashboard | http://localhost:3000 |

The MCP fleet and its ports are defined in `config/portal.yaml` (`mcp_fleet:`);
the compose container names and health checks are in
`deploy/portal-5/docker-compose.yml`.

## Why

The split into a compose stack and host-native launchers exists because Apple
Silicon runtimes (MLX, ComfyUI, embeddings) are faster and lighter outside Docker,
while the web services benefit from compose's networking, health checks and
restart policy. launchd registration makes the native services survive reboots and
crashes, so `up` only needs to confirm or start them rather than install them.

---

## Workspaces

<!-- WIKI:GENERATED unit=unit-readme-workspaces -->
Select a workspace in the Open WebUI model dropdown to activate the right model
and tools automatically. Each workspace carries a `model_hint:` (the served model)
and a `tools:` array (the tool grants), both defined in `config/portal.yaml` and
loaded at import time into `WORKSPACES` by `portal/platform/inference/router/workspaces.py`
via `get_workspace_dict()`.

Portal 5 includes **25 functional workspaces** (plus 52 benchmark workspaces for
performance comparison, gated off by default behind the `eval` module, which is
disabled unless `PORTAL_ENABLE_EVAL=1` is set; 77 total —
`python3 -c "import yaml; d=yaml.safe_load(open('config/portal.yaml')); print(len(d['workspaces']))"`).
Benchmark workspaces are excluded from routing when the eval module is off, so the
daily model dropdown stays limited to the functional set.

## Why

Routing against a config-declared workspace catalog rather than a hardcoded model
list keeps model and tool selection an operator-editable fact: adding a workspace
is one block in `config/portal.yaml`, and `sync-config` propagates it to routing,
the model registry and Open WebUI presets. The eval-module gate exists so
benchmark lanes never leak into normal use unless the operator explicitly opts in.
<!-- /WIKI:GENERATED -->

---

### Functional Workspaces

The functional workspaces are the everyday entries in the Open WebUI model
dropdown. Each is defined in `config/portal.yaml` under `workspaces:` with a
`model_hint:` that pins the served model and a `tools:` array that grants the
toolset. Selecting a workspace activates both at once. The current functional set,
with the pinned model, is:

| Workspace | Pinned model (`model_hint`) |
|---|---|
| `auto` | Qwen3.5-abliterated 9b (context 8k) |
| `auto-daily` | `gemma4:26b-a4b-it-qat` (web_search, documents, memory tools) |
| `auto-coding` | `qwen3-coder:30b-a3b-q4_K_M` (code sandbox tools) |
| `auto-reasoning` | DeepSeek-R1-0528-Qwen3-8B (context 64k) |
| `auto-council` | `qwen3.6:27b-q4_K_M` (no tools) |
| `auto-research` | `tongyi-deepresearch-abliterated` (web_search, web_fetch, kb_search) |
| `auto-vision` | `qwen3-vl:32b` |
| `auto-creative` | Qwen3.6-35B-A3B uncensored (HauhauCS) |
| `auto-documents` | `granite4.1:8b` (document create/read tools) |
| `auto-data` | `granite4.1:30b` (execute_python, create_excel) |
| `auto-math` | `phi4-mini-reasoning` |
| `auto-audio` | `gemma4:12b-it-qat` (transcribe tools) |
| `auto-music` | `lfm2.5:8b` (minimax_generate / minimax_status, speak, clone_voice, register_voice, transcribe) |
| `auto-video` | shelved — retained in config but not operated |
| `auto-image` | `granite4.1:8b` (generate_image, ComfyUI tools) |
| `auto-cad` | `qwen3-coder:30b-a3b-q4_K_M` (render_mesh, render_openscad, convert_cad) |
| `auto-spl` | Qwen3-Coder-Next abliterated (classify_vulnerability, kb_search) |
| `auto-compliance` | `granite4.1:8b` (NERC CIP gap analysis) |
| `auto-bigfix` | `qwen3-coder:30b-a3b-q4_K_M` (BigFix relevance scripting) |
| `auto-security` | VulnLLM-R-7B (web_search, classify_vulnerability, sandbox) |
| `auto-general-uncensored` | `huihui_ai/Qwen3.6-abliterated:27b` (uncensored generalist) |
| `auto-extract-uncensored` | LFM2.5-8B-A1B uncensored (extraction, no tool loop) |
| `tools-specialist` | `granite4.1:8b` (execute_python, remember, recall) |

The `auto-coding` and `auto-security` families express variants (for example
`laguna`, `uncensored`, `pentest`, `purpleteam`) as persona `variant:` fields
instead of sibling workspaces.

## Why

Mapping a dropdown entry to a (model, toolset) pair is what makes the platform
usable without prompt discipline: the user picks an intent, and the workspace
carries the model weight class and the capability grants. Keeping that mapping in
`config/portal.yaml` lets operators add or retune a lane without touching code,
and `sync-config` pushes it into routing and the Open WebUI presets.

---

### Benchmark Workspaces (user-selected only)

<!-- WIKI:GENERATED unit=unit-readme-benchmark-workspaces-user-selected-only -->
Benchmark workspaces pin a specific model for direct, side-by-side performance
comparison. They are not intended for daily use: the user must deliberately select
one from the model dropdown. Every entry is a `bench-*` workspace in
`config/portal.yaml` whose `model_hint:` names an exact catalog model from
`config/backends.yaml`, so a bench run measures that one model and nothing else.

List the current set with:

```bash
python3 -c "from portal.platform.inference.router.workspaces import WORKSPACES; [print(k) for k in sorted(WORKSPACES) if k.startswith('bench-')]"
```

The live count is currently 52 workspaces. Verified examples from `config/portal.yaml`:

| Workspace | Pinned model (`model_hint`) |
|---|---|
| `bench-glm` | `glm-4.7-flash:Q4_K_M` |
| `bench-granite41-30b` | `granite4.1:30b-ctx16k` |
| `bench-gemma4-26b-qat` | `gemma4:26b-a4b-it-qat` |
| `bench-laguna` | `laguna-xs.2:Q4_K_M` |
| `bench-qwen3-coder-30b` | `qwen3-coder:30b-a3b-q4_K_M` |
| `bench-vulnllm-r-7b` | VulnLLM-R-7B GGUF Q4_K_M |

The remaining lanes cover security exec chains, LFM micro models, MTP draft pairs
and additional coding, vision and security variants; the authoritative list is
`config/portal.yaml`, not this table.

## Why

A bench lane decouples model choice from workspace behavior: the same toolset,
prompt scaffolding and routing apply, so a TPS or quality delta is attributable to
the model weights alone. Keeping the lanes behind the eval module (disabled by
default, `PORTAL_ENABLE_EVAL=1` to opt in) stops them from cluttering the daily
model dropdown while leaving a documented harness path.
<!-- /WIKI:GENERATED -->

---

## Common Commands

The operator surface is one dispatcher: `./launch.sh <command>`. The `case`
statement in `launch.sh` routes every subcommand, and most delegate either to a
sourced library under `scripts/lib/` or to `portal.platform.inference.cli`. The
core lifecycle commands are `./launch.sh up` (build the stack, auto-generate
secrets, run port pre-flight), `./launch.sh down` (stop Docker services plus
native macOS services while preserving data) and `./launch.sh status` (health
table via `_cmd_status` in `scripts/lib/util.sh`).

Around that core sit the operational groups: `seed` / `reseed` for Open WebUI
presets (`scripts/openwebui_init.py`), `pull-models` / `refresh-models` /
`import-gguf` for Ollama models, `add-user` / `list-users` for accounts
(`scripts/lib/users.sh`), `backup` / `restore` for data (`scripts/lib/backup.sh`),
and `up-telegram` / `up-slack` / `up-channels` for messaging bots. Native Apple
Silicon services are managed with `start-speech` / `stop-speech`,
`start-transcribe` / `stop-transcribe` and the embedding service installers in
`scripts/lib/services.sh`. `sync-config` regenerates derived artifacts from
`config/portal.yaml`, and `./launch.sh test` runs live smoke tests.

## Why

A single entrypoint keeps every operational action deterministic and scriptable:
each subcommand either maps to a small shell library or to one typed CLI module,
so there is exactly one way to start, stop, seed or back up the stack. It also
means the Docker Compose project directory and the `.env` file are never touched
by hand, which keeps `docker compose up` and `launch.sh up` from diverging.

---

# Start / stop

# Test everything is working

```bash
./launch.sh test            # Run live smoke tests against running stack
```

The `test` subcommand in `launch.sh` executes `portal.platform.inference.cli test`,
implemented in `portal/platform/inference/cli/smoke.py`. `cmd_test` runs
end-to-end checks against the live stack: it probes the pipeline health endpoint
(`PIPELINE_URL`, default `http://localhost:9099`) with the configured
`PIPELINE_API_KEY`, the Open WebUI URL (`OPENWEBUI_URL`, default
`http://localhost:8080`), and prints a per-check pass/fail summary with a nonzero
exit on any failure. This is the quick post-`up` verification path, distinct from
the heavier acceptance suite.

## Why

A mock-only unit suite cannot prove the real services accept requests, so a
short live smoke test is the first thing an operator runs after `up`. Keeping it
inside the CLI (rather than a compose one-shot) means it uses the same environment
the operator has, and a nonzero exit makes it usable in a scripted health check
without parsing output.

---

# Pull specialized models (security, coding, reasoning — 30–90 min)

```bash
./launch.sh pull-models
```

`pull-models` delegates to `portal.platform.inference.cli models pull`
(`launch.sh` case block). That command loads the model registry from
`config/portal.yaml` (`models:` block), resolves pull targets via
`_select_pull_targets` (excluding `retired: true` entries and entries without an
`ollama_name`), and pulls each into Ollama — HuggingFace repos via `hf hub
download`, native registry models via `ollama pull`. It prints the estimate that
the full set takes 30–90 minutes depending on connection speed, and it skips
models already present in Ollama. Gated repositories require `HF_TOKEN` set in
`.env`; the pull reports a clear error otherwise.

## Why

The specialized catalog is large (security, coding, reasoning, vision, creative
lanes), so it is deliberately a separate, operator-initiated step after the three
core models have bootstrapped the stack. Keeping the pull set registry-driven
means a model added to `config/portal.yaml` is automatically pullable without
editing shell code, and retired entries stay documented but stop being fetched.

---

# MLX (Apple Silicon)

# User management

```bash
./launch.sh add-user alice@example.com "Alice Smith"
./launch.sh list-users
```

Both commands are implemented in `scripts/lib/users.sh` and wrap the Open WebUI
admin API. `add-user` calls `POST /api/v1/auths/add` on `OPENWEBUI_URL` (default
`http://localhost:8080`) with an admin bearer token from `get_admin_token`,
generates a temporary password, and prints the credentials for the new account
(email, password, role). The role defaults to `user` and accepts `admin` or
`pending`. `list-users` calls `GET /api/v1/users/` and prints each account with
its role, name and email. Both require the stack to be running and an admin
token to be resolvable.

## Why

User accounts are owned by Open WebUI, so the CLI does not invent its own user
store — it shells out to the same admin endpoints the UI uses, which keeps roles
and password handling consistent. Wrapping them in `launch.sh` gives an operator a
scriptable path to provision accounts without clicking through the admin panel.

---

# Enable messaging channels (requires tokens in .env)

# Backup and restore

# Seeding

```bash
./launch.sh seed            # Re-seed Open WebUI (workspaces + personas)
./launch.sh reseed          # Force-refresh all presets (delete + recreate)
```

Both commands run the `openwebui-init` compose service, which executes
`scripts/openwebui_init.py` against the Open WebUI API. `seed` runs it idempotently:
`FORCE_RESEED` is false, so existing presets are skipped and only new ones are
created. `reseed` sets `FORCE_RESEED=true`, and the script deletes and re-creates
all workspaces, personas and tool presets, so updated persona prompts, workspace
tool ids and model presets are pushed into Open WebUI.

`./launch.sh up` also performs an incremental seed: if `open-webui` is already
healthy, it runs `openwebui-init` in the background to pick up any personas or
workspaces added since the last boot.

## Why

Seeding exists because the workspace and persona catalog is generated from
`config/portal.yaml` and `config/personas/`, not entered by hand in Open WebUI.
The idempotent default makes `up` converge safely on every boot, while `reseed`
is the explicit escape hatch to repair a drifted or partially edited preset set
without touching Open WebUI's database by hand.

---

# Update (single command: git pull + rebuild + model refresh + re-seed)

# Cleanup

## Enable Telegram Bot

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

---

## Enable Slack Bot

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

---

### Core models (pulled automatically on first run, ~4 GB)

Three core models are pulled automatically on the first `./launch.sh up` by the
`ollama-init` service in `deploy/portal-5/docker-compose.yml`. Its command runs
three `ollama pull` calls before reporting that core models are ready:

- `dolphin-llama3:8b` — the general-purpose default, set by `DEFAULT_MODEL` in
  `.env.example` (default `dolphin-llama3:8b`).
- `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` — the standby LLM
  router fallback. The router primary is `gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`,
  which is the default of `_LLM_ROUTER_MODEL` in
  `portal/platform/inference/router/routing.py` and the value of
  `LLM_ROUTER_MODEL` in `.env.example`.
- `nomic-embed-text:latest` — pulled as part of the core set. RAG embeddings are
  now served by the :8917 embedding server: `rag_mcp.py` and `memory_mcp.py` read
  `MLX_EMBEDDING_URL`, defaulting to `http://localhost:8917/v1/embeddings`.

The init service is the Docker-compose equivalent of the `_DEFAULT_MODELS` list in
`portal/platform/inference/cli/update.py`, which also opens with
`${DEFAULT_MODEL:-dolphin-llama3:8b}`, the abliterated Llama-3.2 GGUF and
`nomic-embed-text:latest`.

## Why

A fresh machine must reach a working minimum before any operator-time download
runs: a general chat model, a router standby and an embedding model guarantee
that routing, conversation and RAG all function on first boot. Pulling them in the
compose init container keeps the first-run pull inside the normal `up` path so the
stack is never brought up half-configured.

---

### Specialized models (pulled with `./launch.sh pull-models`, ~60–100 GB total)

The specialized model catalog lives in `config/backends.yaml`, grouped by routing
group, and is what the workspaces' `model_hint:` values reference. Verified
members per group:

- **Security:** JANG-CRACK 31B (pentest, `gemma-4-31b-jang-crack-Q4_K_M.gguf`),
  SuperGemma4-26B (red team), BaronLLM (security analyst, `huihui_ai/baronllm-abliterated`),
  sylink:8b (blue team — SOC triage, DFIR, ATT&CK); Foundation-Sec-8B sits in the
  reasoning group for analytical blue-team work.
- **Coding:** Qwen3-Coder-30B MoE, Laguna-XS.2 33B-A3B (`laguna-xs.2:Q4_K_M`, the
  `auto-coding` laguna variant), Devstral-Small-2, GLM-4.7-Flash REAP.
- **Reasoning:** DeepSeek-R1-0528-Qwen3-8B (auto-reasoning), GLM-Z1-Rumination-32B,
  GPT-OSS 20B, Tongyi-DeepResearch-abliterated.
- **Vision:** Qwen3-VL 32B (auto-vision), Gemma 4 31B dense QAT (`gemma4:31b-it-qat`),
  Gemma 4 E4B QAT (`gemma4:e4b-it-qat`).

Pull mechanics are registry-driven: `./launch.sh pull-models` pulls the active
(non-retired) entries from the `models:` block of `config/portal.yaml`, while the
`./launch.sh update` flow's default pull list in
`portal/platform/inference/cli/update.py` (`_DEFAULT_MODELS`) covers a broader
set that also includes `deepseek-coder-v2:16b-lite-instruct-q4_K_M`.

## Why

Cataloging specialized models in `config/backends.yaml` rather than hardcoding
them in the router keeps one authoritative list for routing, admission and pull
targets, so adding or retiring a lane is a config change, not a code change. The
split between the pull-models registry and the update default set reflects two
workflows: a deliberate operator pull versus a full upgrade that refreshes the
whole fleet.

---

### MLX models (Apple Silicon, retained for audio/embedding/reranker only — chat inference is Ollama-only)

MLX survives in four non-chat runtimes, each started by its own launcher:

- **Speech:** the host-native MLX speech server on port 8918 (`scripts/mlx-speech.py`,
  started by `start-speech` in `scripts/lib/services.sh`) — Kokoro + Higgs Audio v2 voice clone + Qwen3-TTS/ASR.
- **Transcription:** MLX Transcribe on port 8924 (`scripts/mlx-transcribe.py`) —
  Parakeet-TDT-v3 (transcript + word timestamps); `transcribe_with_speakers` adds
  Sortformer speaker diarization merged at the word level (up to 4 speakers, no HF
  token), host-native.
- **Embedding:** Harrier-0.6B on port 8917 (`scripts/embedding-server.py`, default
  `EMBEDDING_MODEL=microsoft/harrier-oss-v1-0.6b`) — the RAG/memory embedding
  endpoint (`MLX_EMBEDDING_URL` in `rag_mcp.py`).
- **Reranker:** Qwen3-Reranker-0.6B on port 8925 (`RERANKER_MODEL` in `.env.example`,
  `mlx-community/Qwen3-Reranker-0.6B-mxfp8`) for two-stage RAG.

Chat model inference runs exclusively through Ollama on port 11434 — GGUF format,
pulled via `ollama pull` and cataloged in `config/backends.yaml`. The MLX
inference proxy that previously served ports 8081/18081/18082 was retired in
commit 3a0c58e, so no MLX runtime participates in conversation routing.

## Why

Retiring the MLX proxy removed a second chat-serving stack while keeping MLX where
Ollama has no equivalent: Ollama does not host Kokoro/Qwen3 TTS, diarized
transcription, sentence embeddings or reranking. Those four runtimes stay host-native on
Apple Silicon because the MPS path is substantially faster than the equivalent
Docker images, and none of them touch the router.

---

### Image generation (downloaded automatically on first run, ~12 GB)

Image generation runs through ComfyUI, and the default checkpoint is FLUX.1-schnell,
set by `IMAGE_MODEL=flux-schnell` in `.env.example`. The same file documents the
alternatives: `flux-dev` (about 24 GB, requires `HF_TOKEN`), `flux-uncensored`,
`sdxl`, `juggernaut-xl`, `pony-diffusion` and `epicrealism-xl`.

`IMAGE_MODEL` is consumed in `deploy/portal-5/docker-compose.yml` by the opt-in
`comfyui-model-init` service (`IMAGE_MODEL=${IMAGE_MODEL:-flux-schnell}`), which
downloads checkpoints on first start under the `docker-comfyui` profile. On the
default Apple Silicon path ComfyUI runs natively on the host, and checkpoints are
fetched with `./launch.sh pull-qwen-image` / `./launch.sh pull-wan22`
(`scripts/lib/services.sh`), which download ComfyUI-flat model files via `hf
download`. The MCP tool `generate_image` in
`portal/modules/media/tools/comfyui_mcp.py` selects the checkpoint per workflow,
and `scripts/gen-image.py` is the standalone CLI wrapper with a `--model` override.

## Why

Image checkpoints are large enough (the FLUX schnell default is roughly 12 GB)
that bundling every option into the base install would waste disk and slow first
boot. `IMAGE_MODEL` picks the default while the `pull-qwen-image` / `pull-wan22`
commands fetch specific checkpoints on demand, so the operator pays the download
cost only for the models actually used.

---

## Speech (Text-to-Speech & Speech-to-Text)

Portal 5 includes a native MLX speech server on Apple Silicon
(`scripts/mlx-speech.py`, port `MLX_SPEECH_PORT` default 8918) with three
backends:

- **Kokoro TTS** — the `mlx-community/Kokoro-82M-bf16` model via mlx-audio; voices
  are selected by the Kokoro naming prefix (`af_`, `am_`, `bf_`, `bm_`, `jf_`,
  `jm_`, `zf_`, `zm_`), e.g. `af_heart`, `bm_george`.
- **Higgs Audio v2** — voice cloning (one-off `clone:` clips or persisted `trainer:<name>`
  profiles registered via `register_voice`); no provenance watermark. `MLX_CLONE_MODEL`
  swaps the engine (e.g. to `mlx-community/chatterbox-fp16`).
- **Qwen3-TTS CustomVoice / VoiceDesign** — preset speakers + voice-from-description (retained).
- **Qwen3-ASR** — speech-to-text via `mlx_audio.stt`.

Manage it with the `start-speech` and `stop-speech` subcommands of `launch.sh`
(`scripts/lib/services.sh`): `start-speech` verifies `mlx_audio` is installed,
checks the PID file at `/tmp/portal-mlx-speech.pid`, and launches
`scripts/mlx-speech.py` with nohup, logging to `~/.portal5/logs/mlx-speech.log`;
`stop-speech` kills the recorded PID. Models load lazily on the first TTS or ASR
request.

## Why

TTS and ASR are latency-sensitive and run continuously, so the speech server is a
host-native process on Metal rather than a Docker container: the MPS path keeps
synthesis fast and the models are loaded once and reused. The PID-file plus
`start-speech`/`stop-speech` pairing gives an operator lifecycle control without a
container orchestrator, and Kokoro voices are addressed by the same prefix scheme
the Kokoro model uses.

---

## Troubleshooting

**Services not starting:**
```bash
./launch.sh status          # See which services failed
docker compose -f deploy/portal-5/docker-compose.yml logs <service-name>
```

`status` runs `_cmd_status` (`scripts/lib/util.sh`), which reads container health
from `docker compose ps --format json` and renders a table covering Open WebUI,
the pipeline, SearXNG, Prometheus, Grafana and the MCP servers, marking each
healthy, running, starting or failed. `logs` in `launch.sh` tails
`docker compose logs -f <service>` (default `portal-pipeline`).

**Out of disk space:**
```bash
docker system df            # See Docker disk usage
./launch.sh clean           # Stop services and remove the Open WebUI data volume
```

`clean` in `launch.sh` stops the stack and removes only the `open-webui-data`
volume, explicitly preserving the Ollama models volume — so a clean wipes chat
history and settings but does not force the model weights to re-download.

## Why

Most boot failures are container health or disk exhaustion, so the troubleshooting
surface is deliberately two commands. `status` resolves the question of which
container is not healthy without parsing compose output, and `clean` is scoped to
remove exactly the data that is safe to lose, because nuking the Ollama volume
would force hours of model re-downloads.

---

# Then free disk space and retry ./launch.sh up

The disk check in `_check_hardware` (`scripts/lib/util.sh`) is the first-run
gating constraint: below 20 GB free it warns and suggests `docker system prune -a`
before continuing, and below 50 GB it notes that more is needed for the full
model catalog. Because the core models plus the FLUX checkpoint (~12 GB) are the
bulk of a first download, a tight disk makes `up` or the model pulls fail
mid-transfer, so the remediation is to free space and re-run `./launch.sh up`.

If models are not loading and Ollama reports zero backends, ensure at least one
model is pulled:

```bash
./launch.sh pull-models     # Ensure at least one model is pulled
```

## Why

Disk is checked before any pull because a failed multi-gigabyte download is the
most wasteful failure mode — the download restarts or half-completes, and the
stack comes up without usable models. Gating on free space up front, and offering
the exact prune command, turns a storage shortfall into a quick fix rather than a
confusing mid-boot error.

---

# Wait for Ollama to finish loading, then try again

"Wait for Ollama to finish loading, then try again" is the guidance for a cold
start. During `up`, `_ensure_native_services` (`scripts/lib/util.sh`) restarts
Ollama via `sudo -n launchctl kickstart -k system/com.portal5.ollama` on Apple
Silicon (the pinned native install, `com.portal5.ollama` — not Homebrew, which
was uninstalled 2026-08-10) when it is configured but not responding, or via
`nohup ollama serve` on Linux, then polls `http://localhost:11434/api/tags` up
to 10 seconds before reporting success or warning. The router only sees healthy
backends once models finish loading, so an immediate request right after boot
can hit an empty backend list — retrying after Ollama responds is the intended
fix.

**First run taking too long:** the FLUX.1-schnell checkpoint is about 12 GB, so on
a slower connection the download dominates boot time; the `hf download` based
pull commands resume interrupted transfers.

**Port already in use:** find the owner with `lsof -i :8080` — the same tool
`_check_ports` uses to print the conflicting PID and its `kill` hint when `up`
aborts.

## Why

Ollama loads models lazily and the checkpoint downloads are large, so "wait and
retry" is not a workaround but the documented behavior of the loader: the stack
can be up before every model is resident. The 10-second readiness poll in
`_ensure_native_services` draws the line between a service that is starting and
one that is actually broken.

---

# Stop the conflicting service, then ./launch.sh up

"Stop the conflicting service, then `./launch.sh up`" is the resolution for a
port-conflict abort. The `up` case in `launch.sh` runs `_check_ports`
(`scripts/lib/util.sh`) as a pre-flight: it probes each reserved port with `nc`
or a `/dev/tcp` fallback and, for a busy port, prints the owning process (via
`lsof` or `ss`) with a `kill` hint. If any port is taken the stack refuses to
start and exits 1.

The printed options are the actual remediation paths: stop the conflicting
process, run `./launch.sh down` if the owner is a previous Portal 5 stack (it also
stops native Speech and ComfyUI), or override the port in `.env` (for example
`DOCUMENTS_HOST_PORT=9013` for MCP Documents). After freeing the port, re-run
`./launch.sh up`.

## Why

Ports are reserved in this project, so silent collisions would produce confusing
half-started services and cross-talk between Open WebUI, the pipeline and the MCP
fleet. A hard pre-flight that names the offender and offers both stop and override
escapes turns the most common first-run failure into a one-line fix instead of a
log dig.

---

### Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PIPELINE_API_KEY` | **Yes** | API key for pipeline authentication. Generate with: `openssl rand -hex 32`. Pipeline will not start without this. |

`PIPELINE_API_KEY` is the one variable every authenticated path depends on:
`portal/platform/inference/router/auth.py` compares every request's `Authorization`
Bearer token against it (constant-time via `hmac.compare_digest`), and
`deploy/portal-5/docker-compose.yml` passes it to the pipeline, Open WebUI
(`OPENAI_API_KEY`) and the Telegram/Slack bots. The pipeline refuses requests that
do not carry a matching token.

`./launch.sh up` removes the setup burden: the `up` case in `launch.sh` calls
`bootstrap_secrets` and a repair loop over `PIPELINE_API_KEY`, `WEBUI_SECRET_KEY`,
`OPENWEBUI_ADMIN_PASSWORD`, `SEARXNG_SECRET_KEY` and `GRAFANA_PASSWORD`, so a key
left at `CHANGEME` or missing is replaced with a generated secret before the stack
starts.

## Why

A single shared API key keeps the pipeline, the chat UI and the channel bots
authenticated against one credential instead of several hand-managed secrets, and
generating it automatically in `up` means a first-time operator never has to
produce or paste a random value. The remaining secrets are likewise auto-generated
so `.env` is usable the moment it is created.

---

### Network Exposure

By default the Portal Pipeline binds to all interfaces. `deploy/portal-5/docker-compose.yml`
maps `0.0.0.0:9099:9099`, so other machines on the LAN can reach it — intentional
for multi-device setups. Requests are protected by `PIPELINE_API_KEY` authentication:
`portal/platform/inference/router/auth.py` compares the `Authorization` Bearer
token against the key with `hmac.compare_digest` and rejects mismatches, so an
exposed port does not mean an open API.

Open WebUI is the component that defaults to loopback: `launch.sh` derives
`WEBUI_LISTEN_ADDR` from `ENABLE_REMOTE_ACCESS` in `.env` and writes it into the
compose mapping (`${WEBUI_LISTEN_ADDR:-127.0.0.1}:8080:8080`). Set
`ENABLE_REMOTE_ACCESS=true` in `.env` to bind Open WebUI on all interfaces.

## Why

The asymmetry is deliberate: the pipeline must be reachable from LAN clients and
channel bots, so it exposes 0.0.0.0 and leans on the API key; the chat UI has no
key of its own and should not be silently world-visible, so it defaults to
loopback unless the operator opts into remote access. Firewall guidance applies to
a LAN, not the public internet.

---

## Coding Tool Integration (Claude Code / opencode)

<!-- WIKI:GENERATED unit=unit-readme-coding-tool-integration-claude-code-opencode -->
Portal 5 ships first-class support for AI coding assistants. Two repo-root config
files activate automatically when either tool opens this project:

- **`.mcp.json`** — currently 22 MCP servers (count with `python3 -c "import json; print(len(json.load(open('.mcp.json'))['mcpServers']))"`): filesystem, git, docker, fetch, portal-sandbox (execute_bash), portal-pipeline (FastContext code explorer + stack introspection), plus the other portal-* tool servers.
- **`opencode.jsonc`** — points opencode at the pipeline (`http://localhost:9099/v1`) as a fully local AI backend; a curated 20-entry model picker whose default is `model: portal/codingagentic`; the cloud providers (anthropic, openai, google, bedrock, vertex) are disabled in its disabled_providers list.

The `codingagentic` persona (`config/personas/codingagentic.yaml`) binds the
`auto-coding` workspace with `variant: laguna` — Laguna-XS.2 33B-A3B running an
agentic read-edit-verify loop, with FastContext-4B as its exploration subagent.

**Claude Code** (Anthropic client, Portal 5 as tool provider):
```bash
claude .    # .mcp.json picked up automatically — portal-sandbox + pipeline tools
```

**opencode** (uses Portal 5 models locally, zero cloud):
```bash
export $(grep PIPELINE_API_KEY .env | xargs)
opencode .  # default model: portal/codingagentic
```

Secret hygiene: install the pre-commit hook once with `pip install pre-commit && pre-commit install`.
The gitleaks hook blocks committed secrets on every commit; real secrets live only
in `.env` (gitignored, auto-generated by `./launch.sh`).

See [MCP Dev Tooling](docs/MCP_DEV_TOOLING.md) for the full guide.

## Why

Coding assistants that default to cloud APIs would stream the repository's source
and the operator's key budget off the machine, defeating the local-first contract.
Shipping `.mcp.json` and `opencode.jsonc` in the repo makes both tools adopt the
pipeline as their tool and model endpoint with zero setup, and the same
`PIPELINE_API_KEY` that gates the chat pipeline also gates the agents, so a single
credential controls the whole surface.
<!-- /WIKI:GENERATED -->

---

## Documentation

The operator-facing manual is a set of reference docs at the repo root and under
`docs/`, all of which exist as tracked files:

| Guide | Contents |
|---|---|
| [MCP Dev Tooling](docs/MCP_DEV_TOOLING.md) | Claude Code & opencode integration, FastContext explorer, workflow examples |
| [How-To Guide](docs/HOWTO.md) | Working examples for every feature, including remote API access |
| [User Guide](docs/USER_GUIDE.md) | How to use workspaces, tools, personas |
| [Admin Guide](docs/ADMIN_GUIDE.md) | User management, configuration, security |
| [Alerts & Notifications](docs/ALERTS.md) | Operational alerts and daily summaries |
| [ComfyUI Setup](docs/COMFYUI_SETUP.md) | Image-model configuration and archived video status |
| [Cluster Scaling](docs/CLUSTER_SCALE.md) | Running multiple Ollama instances |
| [Agent Loop](docs/AGENT_LOOP.md) | Platform-core bounded agent loop (`portal/platform/agent/`), the `portal agent` CLI |
| [Backup & Restore](docs/BACKUP_RESTORE.md) | Data backup procedures |
| [Known Issues](KNOWN_ISSUES.md) | Current limitations and workarounds |

Most of these guides are generated shells whose substance lives in
`portal_wiki/canonical/` fact-units and is rendered into `<!-- WIKI:GENERATED -->`
blocks, so the docs stay current through `./launch.sh sync-config` rather than
hand edits.

## Why

The documentation is the operator contract, not a summary after the fact: the
guides cover exactly the surfaces the platform exposes (tooling, accounts, alerts,
media, clustering), so a new operator can find the answer for a feature without
reading source. Coupling the generated guides to wiki units means a doc cannot
silently drift from the config that produces it.

---

### Acceptance Testing

The acceptance suite is a live-stack gate, deliberately separate from the mocked
pytest unit suite. The entrypoint `tests/portal5_acceptance_v6.py` is a thin shim:
it re-exports the signal dictionaries from `tests/acceptance/_common.py` and calls
`acceptance.cli.main()`. `cli.py` parses `--section` and delegates each section to
one file under `tests/acceptance/` — for example `s02_services.py`, `s03_routing.py`,
`s10_personas_ollama.py`, `s16_security_mcp.py`, `s60_tool_calling.py` and
`s70_information_access.py`. Each section records named checks via `record(...)`,
and `cli.py` tallies PASS/FAIL/BLOCKED/WARN counts and writes the summary to
`ACCEPTANCE_RESULTS.md`.

Run the whole suite, or a single section:

```bash
python3 tests/portal5_acceptance_v6.py          # all sections
python3 tests/portal5_acceptance_v6.py --section S70
```

`--skip-passing` skips sections that passed in a prior run, and `--append` merges a
targeted re-run into the saved results. `tests/acceptance/runner.py` maps section
names such as S0, S2, S3a and S70 to their `async` section functions, so the suite
fails the run whenever any recorded check FAILs or BLOCKs.

## Why

The acceptance gate exists because unit tests deliberately mock Ollama and the HTTP
surface, so a mocked suite can pass while the deployed stack rejects requests,
tools are missing, or container ports are wrong. Running against the live stack
catches those contract breaks before a push. The section-per-file layout keeps each
area (services, routing, personas, security MCP) independently re-runnable during
debugging instead of forcing one monolithic run.

---

### Unit Test CI

The unit test suite runs on every PR and push to `main` via GitHub Actions. The
workflow `.github/workflows/unit-tests.yml` runs `pytest` on `tests/unit` (with
`-n auto -x --tb=short -v`) in a clean environment, so a change that breaks
import-only unit tests blocks the merge.

For local pre-commit feedback, install the hooks once:

```bash
pip install pre-commit && pre-commit install
```

The hook config (`.pre-commit-config.yaml`) defines the per-commit gate: gitleaks
(block committed secrets), ruff lint and format, the generated-artifacts-fresh
check (sync-config idempotent), a portal config validation, and a `pytest-unit`
hook running `pytest tests/unit -n auto -x --tb=short -q`. A heavier
`validate-system` hook (`scripts/validate_system.py --skip-pytest`) runs at push
time when the change touches `portal/`, `config/`, `portal_wiki/`, `scripts/`,
`deploy/` or `tests/`.

## Why

Unit tests must pass with no network and no live services, so the CI gate runs in
a clean environment where local state cannot mask a broken import. The
pre-commit hooks move the same checks earlier, catching style, freshness and
test failures before the commit is made, while the heavier system validation stays
at push time to keep the per-commit cost low.

---

## Architecture

The deployment is a Docker compose stack plus host-native runtimes, orchestrated
by `launch.sh`. Open WebUI (port 8080) is the user-facing chat surface and the
only component a human normally opens. It talks to the Portal Pipeline (port
9099), which performs routing, `PIPELINE_API_KEY` authentication, metrics
collection and MCP tool dispatch. The pipeline is the OpenAI-API-compatible
endpoint registered in Open WebUI; it is stateless for conversation routing and
forwards to Ollama (port 11434), the single inference tier, which runs GGUF
models through its Metal backend on Apple Silicon.

```
┌──────────────┐        ┌──────────────────────────┐
│  Open WebUI  │ ─────► │  Portal Pipeline :9099   │
│     :8080    │        │  routing / auth / MCP    │
└──────────────┘        └──────┬───────┬───────────┘
                               │       │
                        ┌──────▼──┐ ┌──▼───────────────┐
                        │ Ollama  │ │ MCP fleet        │
                        │ :11434  │ │ :8910–:8932      │
                        └─────────┘ └──────────────────┘
Telegram Bot ──► Pipeline    Slack Bot ──► Pipeline
(profile telegram)           (profile slack)
Grafana :3000 ◄── Prometheus :9090 ◄── /metrics
```

The MCP fleet, defined in the `mcp_fleet:` block of `config/portal.yaml`, exposes
tool servers for documents, code sandboxing, TTS, research, memory, RAG, browser
automation, CAD, Proxmox and the canonical wiki. Host-native MLX runtimes serve
speech (`scripts/mlx-speech.py`, port 8918), diarized transcription
(`scripts/mlx-transcribe.py`, port 8924), embeddings
(`scripts/embedding-server.py`, port 8917) and retrieval reranking (port 8925).
Chat inference is Ollama-only: the MLX inference proxy that once listened on
ports 8081/18081/18082 was retired in commit 3a0c58e.

## Why

Keeping a single inference tier on Ollama avoids running a second model-serving
stack against the same GPU memory; MLX survives only where Ollama has no
equivalent runtime — audio synthesis, diarization, embeddings and reranking. One
tier also means one model catalog (`config/backends.yaml`) and one pull path for
operators, which is why the retained MLX runtimes are explicitly non-chat.

---

## License

Portal 5 is released under the MIT License — see [LICENSE](LICENSE) at the repo
root for the full text. MIT grants permission to use, copy, modify and distribute
the code for any purpose, including commercial use, subject to preserving the
copyright and permission notice.

## Why

MIT was chosen because the project is a local-first enhancement layer on top of
Open WebUI, and permissive licensing removes friction for operators who want to
fork or vendor it internally. The individual GGUF models and runtimes it
orchestrates carry their own licenses (for example gated HuggingFace repos
require `HF_TOKEN`), which are separate from the project license.

---
