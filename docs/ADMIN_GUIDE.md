# Portal 8.0.0 — Admin Guide

## First Login

`./launch.sh up` creates `.env` from `.env.example` if absent, then `bootstrap_secrets` in scripts/lib/util.sh replaces every `CHANGEME` placeholder, printing a credentials box with the admin email and the generated `OPENWEBUI_ADMIN_PASSWORD` to the console. The account is `OPENWEBUI_ADMIN_EMAIL` (default `admin@portal.local`) and the password is written into `.env` for later retrieval. Log in at `http://localhost:8080`, or at the hostname printed when `ENABLE_REMOTE_ACCESS=true`.

## Why

First run has no UI to show credentials, so printing the generated password during bootstrap is the only channel that works before the stack is usable. Persisting the same value into `.env` means the operator can recover it later instead of losing it to scrollback, and the placeholder-repair loop regenerates any secret that was hand-broken or left at `CHANGEME`.

## User Management

### Approve Pending Users

Self-registration arrives with the `pending` role because `DEFAULT_USER_ROLE=pending` in `.env.example` is the shipped default, and a pending account has no access until an admin promotes it. Two promotion paths exist. The web path is Open WebUI's Admin Panel > Users: locate the pending account and change its role to `user`. The CLI path is `./launch.sh add-user <email> [name] [role]` with an explicit `pending` role, whose role values scripts/lib/users.sh documents as `user | admin | pending`. `ENABLE_SIGNUP=true` toggles whether self-registration exists at all.

## Why

Pending-by-default is the deliberate team-deployment posture: nobody gains access silently on a shared box, and every account is either approved or created by an operator. Both registration paths share the same role vocabulary, so the approval gate stays consistent whether a user self-signs or is provisioned from the shell.

### Create Users via CLI

`./launch.sh add-user <email> [name] [role]` invokes `_launch_add_user` in scripts/lib/users.sh, which signs in as the admin via `get_admin_token` (scripts/lib/util.sh), POSTs to Open WebUI's `/api/v1/auths/add`, and prints the generated temporary password once. Roles are `user` (default), `admin`, and `pending`. `./launch.sh list-users` calls `_launch_list_users`, GETs `/api/v1/users/`, and prints `[role] name <email>` per account. Both commands fail loudly when the stack is down.

```bash
./launch.sh add-user alice@team.local "Alice Smith"
./launch.sh add-user bob@team.local "Bob Jones" admin
./launch.sh list-users
```

## Why

The CLI exists so an operator can provision accounts without walking someone through the admin UI or sharing the admin password. Because a fresh temporary password is generated and printed per user, the invite path hands out per-account credentials rather than a single reused secret.

### User Roles

Accounts carry one of three roles. `pending` — no access until approved; this is the default for self-registration via `DEFAULT_USER_ROLE=pending` in `.env.example`. `user` — standard access to workspaces, tools, and chat. `admin` — full access including user management and settings. The CLI accepts exactly these values: `./launch.sh add-user <email> [name] [role]`, with role options `user | admin | pending` documented in scripts/lib/users.sh. `./launch.sh list-users` prints the role column per account.

## Why

Roles are the boundary between a single-operator home box and a team deployment, and pending-by-default keeps the approval gate on unless an operator explicitly relaxes it. The CLI and the signup default agree on the same three values, so a provisioned account can never silently carry a higher privilege than the operator intended.

## Model Management

### Pull Additional Models

# Pull additional models

Pull the Ollama model set for a fresh install or a re-sync of the model
registry.

```bash
./launch.sh pull-models
```

`pull-models` dispatches to `portal models pull`, which pulls every
non-retired entry in the `models:` block of `config/portal.yaml` into
Ollama. The broader default pull set — `xploiter`, `whiterabbitneo`,
`baronllm`, `tongyi`, `qwen3-coder`, `devstral`, and others — is declared
in `_DEFAULT_MODELS` in `portal/platform/inference/cli/update.py` and is
what `portal update` refreshes. A full pull takes 30-90 minutes depending
on connection speed, matching the help text in `launch.sh`.

## Why

Model acquisition is a long, interactive operation, so the CLI owns the
model list rather than this document: `config/portal.yaml` declares the
live registry that `models pull` walks, and `_DEFAULT_MODELS` in
`update.py` carries the named starter set. Grounding this unit to those
files means the documented list cannot drift from what the CLI actually
pulls — a hardcoded prose list would be stale by the next registry edit,
and an operator following it would pull a model the system no longer
serves.

### Add a Cluster Node

Cluster scaling is a config-only operation. Adding a node means appending a backend entry to `config/backends.yaml`: a unique `id`, a `type` (`ollama` or `openai_compatible`), the node's `url`, the routing `group`, and the model list it serves. The pipeline discovers new backends through `BackendRegistry` at startup and the auto-routing layer load-balances across healthy backends. After editing, restart the pipeline container so the registry re-reads the file. `./launch.sh status` confirms the new backend through the pipeline health block (`backends_healthy` / `backends_total`).

## Why

Scaling must never touch routing code, so the registry treats `config/backends.yaml` as the single operator-edited surface — a twelve-node fleet is still a YAML edit plus a restart. Keeping the scale-out path data-only is what lets a single-node install grow to a cluster without a fork, a feature flag, or a new code path.

## Routine Operations

Routine lifecycle is one command per operation. `./launch.sh status` runs `_cmd_status` in scripts/lib/util.sh — a per-service health table covering the Docker stack, native services, and the pipeline's `backends_healthy` counts. `./launch.sh logs` tails the portal-pipeline container by default; the default stack has no Ollama container (the compose `ollama` service sits behind the `docker-ollama` profile), so native Ollama logs come from `/opt/homebrew/var/log/ollama.log` (the `com.portal5.ollama` LaunchDaemon's configured log path, despite the `homebrew` directory prefix — not Homebrew-managed) or `~/.portal5/logs/ollama.log` on Linux, not from `logs ollama`. `./launch.sh seed` re-runs `openwebui-init` idempotently, `./launch.sh down` stops the stack via `_do_down` with data preserved, and `./launch.sh clean` removes only the `portal-5_open-webui-data` volume, keeping Ollama models.

## Why

Each verb carries an explicit data story — `down` preserves, `clean` wipes only Open WebUI data, `clean-all` wipes models — so an operator never reaches for `docker compose down -v` and accidentally deletes model weights. `logs` defaulting to the pipeline matches where the interesting decisions are logged.

## Security Notes

Secrets live in `.env`, which `.gitignore` excludes and `bootstrap_secrets` in scripts/lib/util.sh populates by replacing every `CHANGEME` placeholder on first run. `PIPELINE_API_KEY` authenticates callers of the pipeline API; `WEBUI_SECRET_KEY` encrypts Open WebUI session and tool state — rotating it invalidates stored OAuth tokens and forces re-login, per the `.env.example` note. `GRAFANA_PASSWORD` and `SEARXNG_SECRET_KEY` are generated the same way. Rotation is edit `.env`, then restart the stack; `./launch.sh up` auto-repairs any secret that reverted to a placeholder. Never commit `.env`.

## Why

Secret hygiene is automated here because a shared default is the realistic failure: every secret starts as `CHANGEME` and is replaced at first run, so the residual risk is operator error — committing `.env` or hand-setting a weak value — which the gitignore and the placeholder-repair loop directly counter. Knowing which key guards what matters when a rotation is needed.

## Network Exposure

Bindings are per-service in `deploy/portal-5/docker-compose.yml`. Open WebUI publishes `${WEBUI_LISTEN_ADDR:-127.0.0.1}:8080` — localhost unless `ENABLE_REMOTE_ACCESS=true`, and the shipped `.env.example` sets that flag true, so a fresh install listens on `0.0.0.0`. The Docker MCP servers (8910-8926), SearXNG (8088), and Prometheus (9090) bind `127.0.0.1`. The pipeline API binds `0.0.0.0:9099` and Grafana binds `0.0.0.0:3000`. Host-native MCP servers default to `0.0.0.0` — `scripts/mlx-speech.py`, `scripts/mlx-transcribe.py`, `portal/platform/mcp_host/pipeline_mcp.py`, and the security/wiki MCPs. The external boundary is therefore the firewall plus the tunnel/proxy path, not a universal loopback guarantee.

## Why

"Everything is localhost" is a false comfort on this stack: compose services and host-native services bind differently, and the pipeline deliberately listens on all interfaces so the host MCPs and remote backends can reach it. Knowing exactly which surfaces are network-visible is what makes the recommended tunnel approach safe — it publishes only the media paths, not the full API plane.

### Recommended remote access: Cloudflare Tunnel

Recommended remote access is a Cloudflare Tunnel: `cloudflared` runs on the host and merges the reference ingress from `config/cloudflared/config.yml.example` into its own config. The rules route `/files/{music,tts}/*` to ports 8912/8916 and a ComfyUI hostname to 8188 before the catch-all to 8080. Remote media links need `ENABLE_REMOTE_ACCESS=true` and `PORTAL_PUBLIC_URL=https://portal.example.com`; `launch.sh` derives `MUSIC_PUBLIC_URL`, `TTS_PUBLIC_URL`, `VIDEO_PUBLIC_URL`, and `COMFYUI_PUBLIC_URL` from it and the MCPs emit those into chat. Without `PORTAL_PUBLIC_URL` the MCPs fall back to localhost URLs that a remote browser cannot resolve.

## Why

cloudflared on the host is the chosen remote path because it reaches host-loopback services without changing any bindings, and its ingress is path-scoped so only media files escape the machine. That keeps the tunnel as the single external surface instead of opening the full API plane, which is the security property the whole remote-access story is built on.

### Alternative: LAN reverse proxy (Caddy / nginx)

For deployments that skip Cloudflare Tunnel, a Caddy or nginx proxy on the same host plays the same role. Route only the media paths to the loopback services — `/files/{music,tts,video}/*` toward ports 8912/8916/8911 and a ComfyUI hostname toward 8188 — set `PORTAL_PUBLIC_URL` to the proxy's public address, and `launch.sh` derives `MUSIC_PUBLIC_URL`, `TTS_PUBLIC_URL`, `VIDEO_PUBLIC_URL`, and `COMFYUI_PUBLIC_URL` from it. Bindings are per-service in `docker-compose.yml`: the Docker MCP servers bind `127.0.0.1`, but the pipeline API binds `0.0.0.0:9099`, Grafana binds `0.0.0.0:3000`, and the host-native MCP servers (`scripts/mlx-speech.py`, `portal/platform/mcp_host/pipeline_mcp.py`) default to `0.0.0.0`. The proxy must therefore be the only path that exposes those surfaces; never proxy the bare MCP tool APIs.

## Why

The loopback-only posture is enforced per service, not globally, so an operator who assumes "everything is localhost" will misread the network map. The proxy's job is to publish exactly the media-file paths users click in chat and nothing else, which is why the ingress example is path-scoped rather than a blanket pass-through of the whole API plane.

## Backup

`./launch.sh backup [output-dir]` writes a timestamped directory (default under `./backups/`) via `_launch_backup` in scripts/lib/backup.sh. It tars the `portal-5_open-webui-data` volume into `openwebui-data.tar.gz` (accounts, chats, settings), tars `portal-5_grafana-data` into `grafana-data.tar.gz`, and copies `.env`, `config/`, and `imports/` alongside. Ollama weights in `portal-5_ollama-models` are intentionally excluded — they are re-pullable. `./launch.sh restore <path>` confirms interactively, stops the stack with a compose down, then restores the Open WebUI data, Grafana data, and `.env` from the same directory.

## Why

The backup is only as good as the volume inventory behind it. Personal data is confined to `open-webui-data` and `grafana-data` while model weights are disposable, so excluding `ollama-models` keeps backups small and deterministic. A directory-per-run layout plus a single `restore` argument makes recovery unambiguous and never touches `docker compose down -v`.

## Inference Health Monitoring

The inference tier is a single Ollama backend on port 11434, reached by the pipeline through `OLLAMA_URL` (default `http://host.docker.internal:11434`) and by the router through `LLM_ROUTER_OLLAMA_URL`. The MLX chat-inference proxy (ports 8081/18081/18082) was retired in commit 3a0c58e; its code remains only under `scripts/_archive/mlx-retired-3a0c58e/`. MLX survives strictly outside chat inference (speech, transcription, embeddings, reranking). Health monitoring is therefore `_cmd_status` in scripts/lib/util.sh: the `OLLAMA` row confirms the native server responds, and the pipeline block reports `backends_healthy` / `backends_total`.

## Why

With a single backend there is no proxy layer to supervise between the router and the models — health monitoring collapses to "is Ollama up and are the models resident." That simplification is exactly why the retired proxy's watchdog code was archived rather than maintained: supervision complexity scales with tier count, and the single-tier design removed the need for it.

### Debugging crashes

# Debugging crashes

When a service is down or a persona request fails, the first step is to
separate an inference-tier problem from a pipeline problem before touching
any containers.

## Ollama health and model list

Check that Ollama is up and list what is installed:

```bash
curl -s http://localhost:11434/api/tags | jq .
```

`/api/tags` is Ollama's model registry; a non-empty response proves the
inference tier is reachable and shows which GGUF models are present.

## Pipeline health

Check the Portal pipeline (the OpenAI-compatible router on :9099) and
every registered backend in one call:

```bash
curl -s http://localhost:9099/health/all | jq .
```

`/health/all` is mounted in `portal/platform/inference/router/app.py` and
returns per-backend status, so a healthy response means routing itself is
fine even when a specific model is not loaded.

## All services

```bash
./launch.sh status
```

`launch.sh status` reports the whole stack, so it is the broadest first
probe when the failure's origin is unknown.

## Why

Crash debugging needs a tier order: Ollama, then the pipeline, then the
full stack. Each command above is one cheap probe that names its tier, so
an operator can bisect a failure before restarting anything — the
pipeline cannot route to a backend that is down, and `launch.sh status`
is the catch-all when the symptom does not map to a single port. The
endpoints are grounded in the router app that mounts them and the
`launch.sh` dispatch that runs `status`.

---

## Router Configuration

### How the LLM Router Works

Every `auto` request goes through two layers in routing.py. Layer 1 `_route_with_llm` sends the last user message to Ollama `/api/generate` with `format: _ROUTER_JSON_SCHEMA` — grammar-enforced JSON returning `{"workspace": ..., "confidence": ...}` — and accepts the result only when confidence is at least `LLM_ROUTER_CONFIDENCE_THRESHOLD`. Layer 2 `_detect_workspace` runs weighted keyword scoring over `_WORKSPACE_ROUTING` and fires on timeout, low confidence, or error. Variant recovery (`_infer_variant`) exists only on Layer 1: with the router down, a defensive intent lands on the `auto-security` base rather than `auto-security::blueteam`, a coarser but not incorrect decision. lifespan.py pre-warms the router model with `keep_alive: -1`.

## Why

The keyword scorer exists so the router model is never a hard dependency of serving — it is the guaranteed-latency path while the LLM layer buys accuracy. The variant asymmetry is a direct consequence: variant vocabulary lives in `_SECURITY_VARIANT_SIGNALS`, which Layer 2's scorer has no entry for, so an outage degrades variant precision rather than correctness.

### Three-Tier Router Models

Three router tiers are documented in `.env.example` and the header of routing.py. PRIMARY is `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M` — 82.2% accuracy, about 840ms warm latency, roughly 5.3GB, and the default `LLM_ROUTER_MODEL`. STANDBY is `llama3.2:3b` (75.3%, about 433ms, roughly 2GB). FALLBACK is `qwen2.5:1.5b` (67.1%, about 339ms, roughly 1GB). Switch tiers by setting `LLM_ROUTER_MODEL` and dropping `LLM_ROUTER_TIMEOUT_MS` to 500 for standby/fallback. The accuracy figures trace to `tests/benchmarks/bench_router.py`'s `GOLDEN_SET`.

## Why

Three tiers exist because accuracy and latency trade against each other on shared unified memory: the primary maximizes routing quality, the fallback's tiny footprint stays resident alongside inference models, and the standby splits the difference. The timeout must track the tier's warm latency, or every request falls through to Layer 2 keyword scoring.

### OLLAMA_MAX_LOADED_MODELS

The slot count is `OLLAMA_MAX_LOADED_MODELS`: `.env.example` ships 5 (router model plus four inference models for chained and parallel bench work), while the compose `docker-ollama` profile still defaults to 3. The number must cover the router plus every concurrently-resident inference model — a multi-hop security chain needs each hop's model hot, or Ollama evicts and cold-reloads between hops. `run.py` reads the live value and emits a preflight warning when `--parallel-workspaces` is used with a count too low for the chain, and routing.py's header records the router model's own slot requirement. After changing it, verify the running server picked up the new value rather than assuming.

## Why

The slot count is a memory-versus-availability trade, not a throughput knob: each resident slot competes for unified memory, but a count below the chain length converts multi-hop workspaces into cold-load stalls. The 3-to-5 bump exists so the security bench can keep four distinct chain models resident during parallel dispatch.

### Changing the Router Model

The router model is chosen through `.env`: `LLM_ROUTER_MODEL` (default `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`), `LLM_ROUTER_TIMEOUT_MS` (1000 for the primary, 500 for standby/fallback), plus `LLM_ROUTER_CONFIDENCE_THRESHOLD` and `LLM_ROUTER_ENABLED`. routing.py reads these into `_LLM_ROUTER_MODEL` and `_LLM_ROUTER_TIMEOUT_MS` at startup, and lifespan.py's `_warmup_llm_router` pre-loads the configured model with `keep_alive: -1`. Apply a change by editing `.env` and restarting only the pipeline container:

```bash
docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline
```

Ollama needs no restart because the router model is an ordinary Ollama model.

## Why

The router is a classification model, not an inference tier, so swapping it is config plus a restart with no retraining and no backend rework. The model and its timeout are coupled — the timeout is tuned to the tier's warm latency, so changing one without the other silently pushes requests into Layer 2 fallback instead of giving the new model a chance.

### Ollama is Native — Plist Is the Source of Truth

On Apple Silicon the default Ollama is native under launchd, not a container — but **not** via Homebrew. `homebrew.mxcl.ollama` was disabled and fully uninstalled 2026-08-10: Homebrew's formula lags upstream releases and shipped below this project's minimum version (`OLLAMA_MIN_VERSION` in `scripts/lib/util.sh`), and a stale Homebrew reinstall had silently taken over `:11434` at one point, running an outdated build undetected. The supported native install is a pinned binary release run as `com.portal5.ollama`, a **system** LaunchDaemon (deliberately system-domain rather than a per-user LaunchAgent, so it's up before any user is logged in). `_launch_install_ollama` in scripts/lib/services.sh reports its status (it does not install — that's a deliberate one-time manual step, see the function's own guidance); `_ensure_native_services` in scripts/lib/util.sh restarts it via `sudo -n launchctl kickstart -k system/com.portal5.ollama` whenever `up` finds it installed but not responding — passwordless sudoers rules under `/etc/sudoers.d/` (`portal5-ollama`, `portal5-claude`) cover `launchctl` and `plutil` invocations on this box (kickstart, unload/load, and in-place plist edits all run without a password prompt; plain file operations like `cp` do not — the exact per-file grant boundary is root-readable only, not verified from an unprivileged shell). The compose `ollama` service is gated behind the `docker-ollama` profile, so compose env vars (e.g. `OLLAMA_MAX_LOADED_MODELS`) do not reach the native server. The authoritative config for native is the launchd plist:

```
/Library/LaunchDaemons/com.portal5.ollama.plist
```

Root-owned — edit with `sudo`. Since the 2026-08-13 upgrade to v0.32.9, `ProgramArguments` points at `/Users/chris/ollama-current/ollama`, a symlink to the active versioned install directory (currently `ollama-0.32.14`, upgraded 2026-08-16), not a hardcoded version path — this was a deliberate fix after the previous scheme (editing the plist's binary path on every upgrade) left the PATH symlink and the plist able to drift out of sync. **A version upgrade is now just:** unpack the new release to `~/ollama-<version>/`, flip the symlink (`ln -sfn ~/ollama-<version> ~/ollama-current`), then reload the daemon — no plist edit needed. Reload with `sudo launchctl unload /Library/LaunchDaemons/com.portal5.ollama.plist && sudo launchctl load /Library/LaunchDaemons/com.portal5.ollama.plist` (equivalent to `bootout`/`bootstrap` — both fully remove and re-register the service, re-reading the plist from disk; a mere `kickstart -k` restarts the process but does **not** re-read the plist, so it only picks up env var or `ProgramArguments` changes via the full unload/load or bootout/bootstrap cycle). Retaining the previous version directory after an upgrade makes rollback one more symlink flip with no reinstall; the 2026-08-14 upgrade pruned all prior versioned directories (0.32.7/0.32.9/0.32.11/0.32.12) by explicit operator choice, and `ollama-0.32.13` remains on disk after the 2026-08-16 upgrade to 0.32.14, so a rollback from 0.32.14 is a symlink flip.

## Why

Native and container Ollama are two separate config surfaces, and the compose file documents only the container one. An operator who tunes the container's env block while running native (the default) has made a change that never takes effect — the plist is the only lever that does, so the source of truth must be stated explicitly. The Homebrew-vs-pinned-install distinction is called out explicitly because the failure mode is silent: both bind the same port, so a stale Homebrew reinstall serving an outdated Ollama version produces no error, just quietly-wrong behavior (a whole 3-hour benchmark leg ran against it undetected) until someone thinks to check `/api/version` against the live server instead of trusting `command -v ollama`, which resolves whatever is first on PATH. The `ollama-current` symlink indirection exists because the direct-path scheme required editing the plist's `ProgramArguments` and the `/opt/homebrew/bin/ollama` PATH symlink separately on every upgrade — two places that could silently disagree after a future upgrade if only one got updated.

### Runtime VRAM vs File Size Gap

Ollama allocates the KV cache when a model loads, so a resident model's footprint is routinely larger than its GGUF file size; the gap grows with context length, KV quantization, and `OLLAMA_NUM_BATCH`. `devstral:24b` and `granite4.1:8b` are registered in `config/backends.yaml` (general group), and under large contexts a resident big model can push others — including the router — out of memory. Ollama offloads CPU layers rather than crashing; the evicted model cold-loads on its next request, so the first post-eviction `auto` request falls through to Layer 2 keyword scoring in routing.py. `OLLAMA_KEEP_ALIVE_REQUEST` (default `-1`) and `OLLAMA_MAX_LOADED_MODELS` bound residency, and lifespan.py's `_warmup_llm_router` re-pins the router after eviction.

## Why

File size is the wrong planning number because the KV cache is what actually competes for unified memory, making runtime residency diverge from size. Fleet and slot planning must budget resident footprint, and the graceful offload behavior is what makes an eviction a latency event rather than a crash.

### OLLAMA_MEMORY_LIMIT (deferred)

Native Ollama runs with no memory cap by default. `OLLAMA_MEMORY_LIMIT=0` in `.env.example` means "unlimited", and in the compose `docker-ollama` profile the value becomes the container's `deploy.resources.limits.memory`; a native install ignores it entirely, so the plist is the only lever there. Ollama handles memory pressure by offloading layers to CPU rather than crashing. If Metal OOM errors or kernel panics appear under heavy multi-model load, the escalation path is an `OLLAMA_MEMORY_LIMIT` entry in the launchd plist's `EnvironmentVariables` block (reloaded via `launchctl`), or trimming `OLLAMA_MAX_LOADED_MODELS` instead of adding a cap.

## Why

The absent cap is a deliberate default, not an oversight — the reference slot/memory mix fits the target hardware, so a hard limit would only add an artificial ceiling. Capping is reserved as the escalation move for actual OOM symptoms, which keeps the common case simpler and leaves the tuning lever available when it is genuinely needed.

### Verifying Router Is Warm

Ollama reports resident models through its `/api/ps` endpoint. The shell check is:

```bash
curl -s http://localhost:11434/api/ps | jq '.models[] | {name, size_vram}'
```

The port and host come from `OLLAMA_URL` (default `http://host.docker.internal:11434`). The same endpoint powers the `get_loaded_models` tool in `portal/platform/mcp_host/pipeline_mcp.py`, which returns each model's name and `vram_size_gb` — the tool is what an agent sees as `portal-pipeline get_loaded_models`.

## Why

"Which models are resident" answers the two most common operational questions at once: is the router model warm (if not, the next `auto` request cold-loads it and falls through to Layer 2), and is a large inference model squatting on unified memory at the expense of everything else. The same query is exposed to both shell and agent so operators and automation read identical state.

Router decisions are logged by the pipeline. The LLM layer logs each confident classification from `_route_with_llm` in routing.py as `LLM router: '<text>' → workspace='<id>' confidence=<n>`, and every timeout, low-confidence result, or error logs "falling back to keywords". The dispatch layer logs `Routing workspace=<id>` in handlers.py when a request is sent to a backend. `./launch.sh logs` tails the portal-pipeline container by default (the `logs` case runs `docker compose logs -f portal-pipeline`). A practical filter is:

```bash
./launch.sh logs | grep -E "LLM router|Routing workspace|falling back to keywords"
```

## Why

Misrouted requests are decided at a single point, so the router logs are the first place to look when a user reports the wrong workspace. The `confidence` field distinguishes a genuinely low-confidence classification from a timeout, which separates a model-quality problem from a latency problem before any deeper debugging starts.

The router model is an Ollama-native HuggingFace pull. The recommended path is `./launch.sh pull-models`, which runs `models_pull` in `portal/platform/inference/cli/models.py` and pulls the whole catalog via `_pull_native`; the CLI locates the `ollama` binary through `_detect_ollama_cmd` in cli/_common.py. A lone model can be pulled directly:

```bash
ollama pull hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M
```

That is the value of `LLM_ROUTER_MODEL` in `.env.example`. Until it is present, the first `auto` request after startup cold-loads it and Layer 2 keyword scoring covers the interim.

## Why

A missing router model is a warm-up cost, not an outage — the pipeline degrades to keyword scoring rather than failing, so a fresh install still serves. Pulling through the CLI matters because it keeps the installed set in sync with the catalog, so the router model and the workspace pool are provisioned together rather than piecemeal.

### Router Benchmarks

Router accuracy is re-measurable after any model or fleet change. `tests/benchmarks/bench_router.py` scores candidate models against the `GOLDEN_SET` of 73 test cases and writes a results JSON; `tests/benchmarks/bench_router_conditions.py` measures the companion-model cold-load conditions that affect warm latency. A typical invocation is:

```bash
OLLAMA_URL=http://localhost:11434 python3 tests/benchmarks/bench_router.py
```

Results land in `tests/benchmarks/results/`, and the published PRIMARY/STANDBY/FALLBACK accuracy figures in `.env.example` trace back to this bench.

## Why

Router quality is a measured property, not an assumption — the bench pins the accuracy numbers that justify the default model choice, so a swap can be validated against a fixed corpus before it is trusted in production routing. Keeping the corpus and the runner in the repo means the figures stay reproducible instead of remembered.

---

## Live Facts (Generated)

### Personas

<!-- WIKI:GENERATED unit=unit-fact-persona-roster -->
# Persona roster (132 personas)

| Slug | Module | Workspace | Model Pin |
|---|---|---|---|
| `adversarysimulator` | security | `auto-security` | — |
| `agenticheavy` | coding | `auto-coding` | — |
| `agenticlite` | coding | `auto-coding` | — |
| `agentorchestrator` | coding | `auto-coding` | — |
| `bench-gemma4-12b` | eval | `bench-gemma4-12b` | — |
| `bench-gemma4-26b-optiq` | eval | `bench-gemma4-26b-optiq` | — |
| `bench-gemma4-26b-qat` | eval | `bench-gemma4-26b-qat` | — |
| `bench-gemma4-31b-qat` | eval | `bench-gemma4-31b-qat` | — |
| `bench-gemma4-e2b` | eval | `bench-gemma4-e2b` | — |
| `bench-gemma4-e4b` | eval | `bench-gemma4-e4b` | — |
| `bench-gemma4-e4b-qat` | eval | `bench-gemma4-e4b-qat` | — |
| `bench-glm` | eval | `bench-glm` | — |
| `bench-granite41-30b` | eval | `bench-granite41-30b` | — |
| `bench-granite41-8b` | eval | `bench-granite41-8b` | — |
| `bench-huihui-qwen36-27b` | eval | `bench-huihui-qwen36-27b` | — |
| `bench-huihui-qwen36-35b-a3b` | eval | `bench-huihui-qwen36-35b-a3b` | — |
| `bench-laguna` | eval | `bench-laguna` | — |
| `bench-lfm25-8b` | eval | `bench-lfm25-8b` | — |
| `bench-lfm25-8b-uncensored` | eval | `bench-lfm25-8b-uncensored` | — |
| `bench-nex-n2-mini` | eval | `bench-nex-n2-mini` | — |
| `bench-omnicoder2` | eval | `bench-omnicoder2` | — |
| `bench-qwen35-abliterated` | eval | `bench-qwen35-abliterated` | — |
| `bench-qwen36-27b-optiq` | eval | `bench-qwen36-27b-optiq` | — |
| `bench-qwen36-35b-a3b-ud` | eval | `bench-qwen36-35b-a3b-ud` | — |
| `bench-qwen36-abl-27b` | eval | `bench-huihui-qwen36-27b` | — |
| `bench-qwen36-hauhaucs` | eval | `bench-qwen36-hauhaucs` | — |
| `bench-qwen3-coder-30b` | eval | `bench-qwen3-coder-30b` | — |
| `bench-qwen3-coder-next` | eval | `bench-qwen3-coder-next` | — |
| `bench-qwen3-coder-next-abliterated` | eval | `bench-qwen3-coder-next-abliterated` | — |
| `blueteamdefender` | security | `auto-security` | — |
| `bugdiscoverycodeassistant` | coding | `auto-coding` | — |
| `businessanalyst` | general | `auto-reasoning` | — |
| `cadquerydesigner` | cad | `auto-cad` | — |
| `chartanalyst` | general | `auto-vision` | — |
| `cippolicywriter` | compliance | `auto-compliance` | — |
| `codebasewikidocumentationskill` | coding | `auto-coding` | — |
| `codereviewassistant` | coding | `auto-coding` | — |
| `codereviewer` | coding | `auto-coding` | — |
| `codescreenshotreader` | general | `auto-vision` | — |
| `codingagentic` | coding | `auto-coding` | — |
| `codinguncensored` | coding | `auto-coding` | — |
| `codinguncensoredagentic` | coding | `auto-coding` | — |
| `complianceanalyst` | compliance | `auto-compliance` | — |
| `creativecoder` | coding | `auto-coding` | — |
| `creativewriter` | media | `auto-creative` | — |
| `cybersecurityspecialist` | security | `auto-security` | — |
| `dailydriver` | general | `auto-daily` | — |
| `dashboardarchitect` | research | `auto-data` | — |
| `dataanalyst` | research | `auto-data` | — |
| `databasearchitect` | research | `auto-data` | — |
| `dataextractor` | research | `auto-data` | — |
| `datascientist` | research | `auto-data` | — |
| `devopsautomator` | coding | `auto-coding` | — |
| `devopsengineer` | general | `auto-reasoning` | — |
| `devstral_coder` | coding | `auto-coding` | `devstral-small-2:latest-ctx8k` |
| `diagramreader` | general | `auto-vision` | — |
| `documentationarchitect` | documents | `auto-documents` | — |
| `e2edebugger` | coding | `auto-coding` | — |
| `e2etestauthor` | coding | `auto-coding` | — |
| `ethereumdeveloper` | coding | `auto-coding` | — |
| `excelsheet` | coding | `auto-coding` | — |
| `factchecker` | research | `auto-research` | — |
| `formfiller` | coding | `auto-coding` | — |
| `fullstacksoftwaredeveloper` | coding | `auto-coding` | — |
| `gdprdpoadvisor` | compliance | `auto-compliance` | — |
| `gemma4e4bvision` | general | `auto-vision` | — |
| `gemma4jangvision` | general | `auto-vision` | `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` |
| `gemma_e4b` | general | `auto-daily` | — |
| `gemma_fast` | general | `auto-daily` | — |
| `gemma_vision` | general | `auto-vision` | `gemma4:31b-it-qat-ctx8k` |
| `gemmaresearchanalyst` | research | `auto-research` | — |
| `githubexpert` | coding | `auto-coding` | — |
| `glm-coder` | coding | `auto-coding` | `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` |
| `glm-thinker` | general | `auto-reasoning` | `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k` |
| `goengineer` | coding | `auto-coding` | — |
| `gptossanalyst` | general | `auto-reasoning` | — |
| `hermes3writer` | media | `auto-creative` | — |
| `hipaaprivacyofficer` | compliance | `auto-compliance` | — |
| `interviewcoach` | media | `auto-creative` | — |
| `itarchitect` | general | `auto-reasoning` | — |
| `itexpert` | general | `auto` | — |
| `javascriptconsole` | coding | `auto-coding` | — |
| `kbnavigator` | research | `auto-research` | — |
| `kubernetesdockerrpglearningengine` | coding | `auto-coding` | — |
| `linuxterminal` | coding | `auto-coding` | — |
| `machinelearningengineer` | research | `auto-data` | — |
| `magistralstrategist` | general | `auto-reasoning` | `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` |
| `marketanalyst` | research | `auto-research` | — |
| `mathreasoner` | general | `auto-math` | — |
| `nemotronlightning` | general | `auto-nemotron` | — |
| `nerccipcomplianceanalyst` | compliance | `auto-compliance` | — |
| `networkengineer` | security | `auto-security` | — |
| `ocrspecialist` | general | `auto-vision` | — |
| `paywalledresearcher` | research | `auto-research` | — |
| `pcidssassessor` | compliance | `auto-compliance` | — |
| `pentester` | security | `auto-security` | — |
| `pentestlead` | security | `auto-security` | — |
| `personalassistant` | general | `auto-daily` | — |
| `phi4specialist` | documents | `auto-documents` | — |
| `phi4stemanalyst` | general | `auto-reasoning` | — |
| `printabilityengineer` | cad | `auto-cad` | — |
| `productmanager` | general | `auto-reasoning` | — |
| `proofreader` | media | `auto-creative` | — |
| `purpleteamexec` | security | `auto-security` | — |
| `purpleteamlead` | security | `auto-security` | — |
| `pythoncodegeneratorcleanoptimizedproduction-ready` | coding | `auto-coding` | — |
| `pythoninterpreter` | coding | `auto-coding` | — |
| `qwen38coder` | coding | `auto-coding` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` |
| `qwen38coder-dflash` | coding | `auto-coding` | `Qwen3.8-27B-4bit` |
| `redteamoperator` | security | `auto-security` | — |
| `researchanalyst` | research | `auto-research` | — |
| `rustengineer` | coding | `auto-coding` | — |
| `securityuncensored` | security | `auto-security` | — |
| `seniorfrontenddeveloper` | coding | `auto-coding` | — |
| `seniorsoftwareengineersoftwarearchitectrules` | general | `auto-reasoning` | — |
| `soc2auditor` | compliance | `auto-compliance` | — |
| `softwarequalityassurancetester` | coding | `auto-coding` | — |
| `splunkdetectionauthor` | general | `auto-spl` | — |
| `splunksplgineer` | general | `auto-spl` | — |
| `sqlterminal` | coding | `auto-coding` | — |
| `statistician` | research | `auto-data` | — |
| `supergemma4researcher` | research | `auto-research` | — |
| `techreviewer` | general | `auto` | — |
| `techwriter` | documents | `auto-documents` | — |
| `terraformwriter` | coding | `auto-coding` | — |
| `toolcomposer` | general | `tools-specialist` | — |
| `transcriptanalyst` | documents | `auto-documents` | — |
| `typescriptengineer` | coding | `auto-coding` | — |
| `ux-uideveloper` | coding | `auto-coding` | — |
| `webnavigator` | general | `auto` | — |
| `webresearcher` | research | `auto-research` | — |
| `whiteboardconverter` | general | `auto-vision` | — |

## Why

The roster is derived from the persona YAML files under `config/personas/`, one per specialist, so the count and the slug/module/workspace bindings always reflect what the pipeline can actually route to. Personas are seeded into Open WebUI as model presets by the same files, so the wiki roster and the served roster cannot drift apart.
<!-- /WIKI:GENERATED -->

### Workspaces

<!-- WIKI:GENERATED unit=unit-fact-workspace-roster -->
# Workspace roster (24 production, 46 eval, 70 total)

## Production workspaces (acceptance/UAT scope, eval OFF)

| Workspace | Module | Model Hint |
|---|---|---|
| `auto` | general | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` |
| `auto-audio` | media | `gemma4:12b-it-qat-ctx8k` |
| `auto-bigfix` | general | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` |
| `auto-cad` | cad | `qwen3-coder:30b-a3b-q4_K_M-ctx8k` |
| `auto-coding` | coding | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` |
| `auto-compliance` | compliance | `granite4.1:8b-ctx16k` |
| `auto-council` | general | `qwen3.6:27b-q4_K_M-ctx16k` |
| `auto-creative` | media | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` |
| `auto-daily` | general | `gemma4:26b-a4b-it-qat-ctx8k` |
| `auto-data` | research | `granite4.1:30b-ctx64k` |
| `auto-documents` | documents | `granite4.1:8b-ctx16k` |
| `auto-extract-uncensored` | documents | `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:q4_K_M-ctx8k` |
| `auto-general-uncensored` | general | `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` |
| `auto-image` | media | `granite4.1:8b-ctx16k` |
| `auto-math` | general | `phi4-mini-reasoning:latest-ctx24k` |
| `auto-music` | media | `lfm2.5:8b-ctx8k` |
| `auto-nemotron` | general | `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx8k` |
| `auto-reasoning` | general | `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` |
| `auto-research` | research | `portal5/xyz-aquila-mini:q4_k_m-ctx16k` |
| `auto-security` | security | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k` |
| `auto-spl` | general | `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k` |
| `auto-video` | media | `granite4.1:8b-ctx16k` |
| `auto-vision` | general | `qwen3-vl:32b-ctx8k` |
| `tools-specialist` | general | `granite4.1:8b-ctx8k` |

## Eval/bench workspaces (need PORTAL_ENABLE_EVAL=1)

- `bench-agentworld`
- `bench-baronllm-q6k`
- `bench-e2b-pentest`
- `bench-exec-exploit`
- `bench-exec-reasoning`
- `bench-exec-recon`
- `bench-foundation-sec-8b-reasoning`
- `bench-gemma4-12b`
- `bench-gemma4-12b-agentic`
- `bench-gemma4-26b-heretic`
- `bench-gemma4-26b-optiq`
- `bench-gemma4-26b-qat`
- `bench-gemma4-31b-qat`
- `bench-gemma4-e2b`
- `bench-gemma4-e4b`
- `bench-gemma4-e4b-qat`
- `bench-glm`
- `bench-granite41-30b`
- `bench-granite41-8b`
- `bench-hermes3`
- `bench-huihui-qwen36-27b`
- `bench-huihui-qwen36-35b-a3b`
- `bench-laguna`
- `bench-lfm25-8b`
- `bench-lfm25-8b-uncensored`
- `bench-llama32-3b-abliterated`
- `bench-magistral-small`
- `bench-mistral-small-3-2`
- `bench-nex-n2-mini`
- `bench-north-mini-code`
- `bench-omnicoder2`
- `bench-ornith-35b`
- `bench-qwable-35b`
- `bench-qwen3-14b-abliterated`
- `bench-qwen3-coder-30b`
- `bench-qwen3-coder-next`
- `bench-qwen3-coder-next-abliterated`
- `bench-qwen35-9b-heretic-vision`
- `bench-qwen35-abliterated`
- `bench-qwen36-27b-optiq`
- `bench-qwen36-35b-a3b-ud`
- `bench-qwen36-hauhaucs`
- `bench-qwen38-27b`
- `bench-supergemma4-sec`
- `bench-vulnllm-r-7b`
- `bench-vulnllm-r7b`

## Why

The roster is the workspace mapping in `config/portal.yaml`, split into the production workspaces that acceptance/UAT exercises and the eval/bench workspaces gated behind `PORTAL_ENABLE_EVAL=1`. The counts and the per-workspace model hints come straight from that file, so the roster cannot disagree with what routing serves.
<!-- /WIKI:GENERATED -->

### Model Bindings (reachability-resolved)

<!-- WIKI:GENERATED unit=unit-fact-model-bindings -->
# Model bindings (reachability-resolved)

What each production workspace/persona actually SERVES, not what it
claims. A row marked GAP means the intended model is unreachable via
the workspace's routing groups and silently falls back to the pool
default.

## Workspace model_hint reachability

| Workspace | model_hint | Reachable |
|---|---|---|
| `auto` | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | yes |
| `auto-audio` | `gemma4:12b-it-qat-ctx8k` | yes |
| `auto-bigfix` | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | yes |
| `auto-cad` | `qwen3-coder:30b-a3b-q4_K_M-ctx8k` | yes |
| `auto-coding` | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | yes |
| `auto-compliance` | `granite4.1:8b-ctx16k` | yes |
| `auto-council` | `qwen3.6:27b-q4_K_M-ctx16k` | yes |
| `auto-creative` | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` | yes |
| `auto-daily` | `gemma4:26b-a4b-it-qat-ctx8k` | yes |
| `auto-data` | `granite4.1:30b-ctx64k` | yes |
| `auto-documents` | `granite4.1:8b-ctx16k` | yes |
| `auto-extract-uncensored` | `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:q4_K_M-ctx8k` | yes |
| `auto-general-uncensored` | `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` | yes |
| `auto-image` | `granite4.1:8b-ctx16k` | yes |
| `auto-math` | `phi4-mini-reasoning:latest-ctx24k` | yes |
| `auto-music` | `lfm2.5:8b-ctx8k` | yes |
| `auto-nemotron` | `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx8k` | yes |
| `auto-reasoning` | `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` | yes |
| `auto-research` | `portal5/xyz-aquila-mini:q4_k_m-ctx16k` | yes |
| `auto-security` | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k` | yes |
| `auto-spl` | `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k` | yes |
| `auto-video` | `granite4.1:8b-ctx16k` | yes |
| `auto-vision` | `qwen3-vl:32b-ctx8k` | yes |
| `tools-specialist` | `granite4.1:8b-ctx8k` | yes |

## Persona model_pin reachability

| Persona | Workspace | model_pin | Reachable |
|---|---|---|---|
| `devstral_coder` | `auto-coding` | `devstral-small-2:latest-ctx8k` | yes |
| `gemma4jangvision` | `auto-vision` | `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` | yes |
| `gemma_vision` | `auto-vision` | `gemma4:31b-it-qat-ctx8k` | yes |
| `glm-coder` | `auto-coding` | `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` | yes |
| `glm-thinker` | `auto-reasoning` | `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k` | yes |
| `magistralstrategist` | `auto-reasoning` | `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` | yes |
| `qwen38coder` | `auto-coding` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` | yes |
| `qwen38coder-dflash` | `auto-coding` | `Qwen3.8-27B-4bit` | yes |

**0 reachability gap(s)** — clean.

## Why

Model bindings are the reachability-resolved view of what each workspace `model_hint` and persona `model_pin` actually serve: a hint is reachable only when the workspace's routing groups in `config/backends.yaml` contain the model. The gap count is the live measure of how many bindings silently fall back to the pool default, and is regenerated from the same config the router reads.
<!-- /WIKI:GENERATED -->

### MCP Fleet

<!-- WIKI:GENERATED unit=unit-fact-mcp-fleet -->
# MCP fleet (24 servers)

| ID | Name | Port |
|---|---|---|
| `filesystem` | filesystem |  |
| `fetch` | fetch |  |
| `git` | git |  |
| `serena` | serena |  |
| `docker` | docker |  |
| `comfyui` | portal-comfyui | 8910 |
| `music` | portal-music | 8912 |
| `documents` | portal-documents | 8913 |
| `execution` | portal-sandbox | 8914 |
| `whisper` | portal-whisper | 8915 |
| `tts` | portal-tts | 8916 |
| `security` | portal-security | 8919 |
| `memory` | portal-memory | 8920 |
| `rag` | portal-rag | 8921 |
| `research` | portal-research | 8922 |
| `browser` | portal-browser | 8923 |
| `mlx_transcribe` | portal-mlx-transcribe | 8924 |
| `reranker` | portal-reranker | 8925 |
| `cad_render` | portal-cad-render | 8926 |
| `proxmox` | portal-proxmox | 8927 |
| `pipeline` | portal-pipeline | 8928 |
| `mitre` | portal-mitre | 8929 |
| `wiki` | portal-wiki | 8931 |
| `detections` | portal-detections | 8932 |

## Why

The fleet table is the `mcp_fleet` list in `config/portal.yaml`, the single source for every MCP tool server the pipeline can dispatch to. Each entry carries the server id, display name, and reserved port, so the wiki fleet roster is the same list the tool registry and the Open WebUI tool-server wiring are built from.
<!-- /WIKI:GENERATED -->

### Model Catalog

<!-- WIKI:GENERATED unit=unit-fact-model-catalog -->
# Model catalog (225 model ids across 7 backend groups)

## coding (44)

- `Laguna-XS.2-4bit`
- `Qwen3-Coder-30B-A3B-Instruct-4bit`
- `Qwen3.8-27B-4bit`
- `Qwen3.8-27B-oQ4e-mtp`
- `devstral-small-2`
- `devstral-small-2:latest-ctx8k`
- `devstral:24b`
- `glm-4.7-flash:Q4_K_M`
- `gpt-oss:20b`
- `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M`
- `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M`
- `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf`
- `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M`
- `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf`
- `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k`
- `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M`
- `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k`
- `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4`
- `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4-ctx8k`
- `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M`
- `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M-ctx64k`
- `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M`
- `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M`
- `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k`
- `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx64k`
- `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M`
- `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M`
- `huihui_ai/qwen3-abliterated:14b-v2`
- `laguna-xs.2:Q4_K_M`
- `laguna-xs.2:Q4_K_M-ctx64k`
- `omnicoder2:9b-q4_k_m`
- `omnicoder2:9b-q4_k_m-ctx8k`
- `phi4-reasoning:plus`
- `phi4-reasoning:plus-ctx32k`
- `qwen3-coder-next:latest`
- `qwen3-coder-next:latest-ctx64k`
- `qwen3-coder:30b-a3b-q4_K_M`
- `qwen3-coder:30b-a3b-q4_K_M-ctx16k`
- `qwen3-coder:30b-a3b-q4_K_M-ctx8k`
- `qwen3.6:27b-q4_K_M`
- `qwen3.6:35b-a3b-q4_K_M`

## creative (11)

- `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit`
- `dolphin-llama3:8b`
- `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4`
- `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k`
- `hermes3:8b`
- `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M`
- `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:q4_K_M-ctx8k`
- `huihui_ai/Qwen3.6-abliterated:27b`
- `huihui_ai/Qwen3.6-abliterated:27b-ctx8k`
- `huihui_ai/baronllm-abliterated`
- `huihui_ai/baronllm-abliterated:latest-ctx8k`

## general (93)

- `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp`
- `cybersecqwen-4b-toolfix:latest`
- `deepseek-r1:32b-q4_k_m`
- `devstral-small-2:latest`
- `devstral:24b`
- `dolphin-llama3:8b`
- `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4`
- `gemma-4-26b-a4b-it-QAT-4bit`
- `gemma4:12b-it-qat`
- `gemma4:26b-a4b-it-q4_K_M`
- `gemma4:26b-a4b-it-qat`
- `gemma4:26b-a4b-it-qat-ctx8k`
- `gemma4:31b-it-qat`
- `gemma4:e2b-it-qat`
- `gemma4:e4b-it-q4_K_M`
- `gemma4:e4b-it-qat`
- `glm-4.7-flash:Q4_K_M`
- `gpt-oss:20b`
- `granite4.1:30b`
- `granite4.1:30b-ctx16k`
- `granite4.1:8b`
- `granite4.1:8b-ctx16k`
- `granite4.1:8b-ctx8k`
- `hermes3:8b`
- `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M`
- `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M`
- `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K`
- `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M`
- `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M`
- `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf`
- `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M`
- `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M`
- `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M`
- `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M`
- `hf.co/Nguuma/security-slm-unsloth-1.5b:latest`
- `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF`
- `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF:latest`
- `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx8k`
- `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M`
- `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf`
- `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M`
- `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4`
- `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M`
- `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf`
- `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M`
- `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M`
- `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M`
- `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M`
- `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M`
- `hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF:gemma-4-26B-A4B-it-uncensored-heretic.Q4_K_M.gguf`
- `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M`
- `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k`
- `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0`
- `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k`
- `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx64k`
- `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`
- `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M`
- `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M`
- `huihui_ai/Qwen3.6-abliterated:27b`
- `huihui_ai/Qwen3.6-abliterated:27b-ctx8k`
- `huihui_ai/baronllm-abliterated:latest`
- `huihui_ai/gemma-4-abliterated:E2b-qat`
- `huihui_ai/qwen3-abliterated:14b-v2`
- `huihui_ai/qwen3.5-abliterated:9b`
- `huihui_ai/qwen3.5-abliterated:9b-ctx64k`
- `huihui_ai/qwen3.5-abliterated:9b-ctx8k`
- `laguna-xs.2:Q4_K_M`
- `lfm2.5:8b`
- `lfm2.5:8b-ctx8k`
- `llama3.2:3b`
- `llama3.2:3b-instruct-q8_0-ctx8k`
- `meta-secalign-8b-q4_k_m:latest`
- `mistral-small3.2:24b`
- `muse-glimmer:30b-mlx`
- `omnicoder2:9b-q4_k_m`
- `phi4-mini`
- `phi4:14b-q8_0`
- `portal5/deepwen-3.6:q4.5-moq`
- `portal5/deepwen-3.6:q4.5-moq-ctx32k`
- `portal5/gemma4-12b:q4_K_M-ctx8k`
- `portal5/qwen3.6-27b-mtp:q8_0-drafted`
- `portal5/xyz-aquila-mini:Q4_K_M`
- `portal5/xyz-aquila-mini:q4_k_m-ctx16k`
- `qwen3-coder-next:latest`
- `qwen3-coder:30b-a3b-q4_K_M`
- `qwen3.6:27b-q4_K_M`
- `qwen3.6:27b-q4_K_M-ctx16k`
- `qwen3.6:27b-q8_0`
- `qwen3.6:35b-a3b-q4_K_M`
- `supergemma4-26b-uncensored:Q4_K_M`
- `sylink/sylink:8b`

## omlx (2)

- `Laguna-XS.2-4bit`
- `Qwen3-Coder-30B-A3B-Instruct-4bit`

## reasoning (27)

- `DeepSeek-R1-0528-Qwen3-8B-4bit`
- `Tongyi-DeepResearch-30B-A3B-abliterated-4bit`
- `deepseek-r1:32b-q4_k_m`
- `gpt-oss:20b`
- `granite-4.1-30b-4bit`
- `granite-4.1-8b-mxfp8`
- `granite4.1:30b`
- `granite4.1:30b-ctx16k`
- `granite4.1:30b-ctx64k`
- `granite4.1:8b`
- `granite4.1:8b-ctx16k`
- `granite4.1:8b-ctx8k`
- `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf`
- `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf`
- `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k`
- `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`
- `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL`
- `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k`
- `huihui_ai/tongyi-deepresearch-abliterated`
- `huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k`
- `phi4-mini-reasoning`
- `phi4-mini-reasoning:latest-ctx24k`
- `portal5/qwen3.6-27b-mtp:q8_0-drafted`
- `qwen3.6:27b-mtp-q4_K_M`
- `qwen3.6:27b-q8_0`
- `supergemma4-26b-uncensored:Q4_K_M`
- `supergemma4-26b-uncensored:Q4_K_M-ctx64k`

## security (32)

- `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit`
- `VulnLLM-R-7B-4bit`
- `baronllm:q6_k`
- `cybersecqwen-4b-toolfix:latest`
- `devstral-small-2:latest`
- `devstral-small-2:latest-ctx8k`
- `glm-4.7-flash:Q4_K_M`
- `granite-4.1-8b-mxfp8`
- `granite4.1:8b`
- `granite4.1:8b-ctx16k`
- `granite4.1:8b-ctx8k`
- `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K`
- `hf.co/Nguuma/security-slm-unsloth-1.5b:latest`
- `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf`
- `hf.co/mradermacher/CyberSecQwen-4B-GGUF:Q4_K_M`
- `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M`
- `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k`
- `huihui-ai--Huihui-Qwen3.5-9B-abliterated-mlx-4bit`
- `huihui_ai/baronllm-abliterated`
- `huihui_ai/baronllm-abliterated:latest-ctx8k`
- `huihui_ai/gemma-4-abliterated:E2b-qat`
- `huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k`
- `huihui_ai/qwen3.5-abliterated:9b`
- `huihui_ai/qwen3.5-abliterated:9b-ctx64k`
- `huihui_ai/qwen3.5-abliterated:9b-ctx8k`
- `lfm2.5:8b`
- `lfm2.5:8b-ctx8k`
- `meta-secalign-8b-q4_k_m`
- `supergemma4-26b-uncensored:Q4_K_M`
- `supergemma4-26b-uncensored:Q4_K_M-ctx64k`
- `sylink/sylink:8b`
- `sylink/sylink:8b-ctx8k`

## vision (16)

- `gemma4:12b-it-qat`
- `gemma4:12b-it-qat-ctx8k`
- `gemma4:26b-a4b-it-q4_K_M`
- `gemma4:26b-a4b-it-qat`
- `gemma4:26b-a4b-it-qat-ctx8k`
- `gemma4:31b-it-qat`
- `gemma4:31b-it-qat-ctx8k`
- `gemma4:e2b-it-qat`
- `gemma4:e2b-it-qat-ctx8k`
- `gemma4:e4b-it-q4_K_M`
- `gemma4:e4b-it-qat`
- `gemma4:e4b-it-qat-ctx8k`
- `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf`
- `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M`
- `qwen3-vl:32b`
- `qwen3-vl:32b-ctx8k`

## Why

The catalog groups every model id registered in `config/backends.yaml` by its routing group, which is the same grouping `workspace_routing` uses to resolve which backends a workspace can draw from. Deriving the catalog from the backend file keeps the documented model inventory and the actually-served pool identical.
<!-- /WIKI:GENERATED -->
