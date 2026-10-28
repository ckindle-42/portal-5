# Portal 8.0.0 — Admin Guide

## First Login

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-first-login -->
`./launch.sh up` creates `.env` from `.env.example` if absent, then `bootstrap_secrets` in scripts/lib/util.sh replaces every `CHANGEME` placeholder, printing a credentials box with the admin email and the generated `OPENWEBUI_ADMIN_PASSWORD` to the console. The account is `OPENWEBUI_ADMIN_EMAIL` (default `admin@portal.local`) and the password is written into `.env` for later retrieval. Log in at `http://localhost:8080`, or at the hostname printed when `ENABLE_REMOTE_ACCESS=true`.

### Why

First run has no UI to show credentials, so printing the generated password during bootstrap is the only channel that works before the stack is usable. Persisting the same value into `.env` means the operator can recover it later instead of losing it to scrollback, and the placeholder-repair loop regenerates any secret that was hand-broken or left at `CHANGEME`.
<!-- /WIKI:GENERATED -->

## User Management

### Approve Pending Users

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-approve-pending-users -->
Self-registration arrives with the `pending` role because `DEFAULT_USER_ROLE=pending` in `.env.example` is the shipped default, and a pending account has no access until an admin promotes it. Two promotion paths exist. The web path is Open WebUI's Admin Panel > Users: locate the pending account and change its role to `user`. The CLI path is `./launch.sh add-user <email> [name] [role]` with an explicit `pending` role, whose role values scripts/lib/users.sh documents as `user | admin | pending`. `ENABLE_SIGNUP=true` toggles whether self-registration exists at all.

#### Why

Pending-by-default is the deliberate team-deployment posture: nobody gains access silently on a shared box, and every account is either approved or created by an operator. Both registration paths share the same role vocabulary, so the approval gate stays consistent whether a user self-signs or is provisioned from the shell.
<!-- /WIKI:GENERATED -->

### Create Users via CLI

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-create-users-via-cli -->
`./launch.sh add-user <email> [name] [role]` invokes `_launch_add_user` in scripts/lib/users.sh, which signs in as the admin via `get_admin_token` (scripts/lib/util.sh), POSTs to Open WebUI's `/api/v1/auths/add`, and prints the generated temporary password once. Roles are `user` (default), `admin`, and `pending`. `./launch.sh list-users` calls `_launch_list_users`, GETs `/api/v1/users/`, and prints `[role] name <email>` per account. Both commands fail loudly when the stack is down.

```bash
./launch.sh add-user alice@team.local "Alice Smith"
./launch.sh add-user bob@team.local "Bob Jones" admin
./launch.sh list-users
```

#### Why

The CLI exists so an operator can provision accounts without walking someone through the admin UI or sharing the admin password. Because a fresh temporary password is generated and printed per user, the invite path hands out per-account credentials rather than a single reused secret.
<!-- /WIKI:GENERATED -->

### User Roles

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-user-roles -->
Accounts carry one of three roles. `pending` — no access until approved; this is the default for self-registration via `DEFAULT_USER_ROLE=pending` in `.env.example`. `user` — standard access to workspaces, tools, and chat. `admin` — full access including user management and settings. The CLI accepts exactly these values: `./launch.sh add-user <email> [name] [role]`, with role options `user | admin | pending` documented in scripts/lib/users.sh. `./launch.sh list-users` prints the role column per account.

#### Why

Roles are the boundary between a single-operator home box and a team deployment, and pending-by-default keeps the approval gate on unless an operator explicitly relaxes it. The CLI and the signup default agree on the same three values, so a provisioned account can never silently carry a higher privilege than the operator intended.
<!-- /WIKI:GENERATED -->

## Model Management

### Pull Additional Models

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-pull-additional-models -->
#### Pull additional models

Pull the Ollama model set for a fresh install or a re-sync of the model
registry.

```bash
./launch.sh pull-models
```

`pull-models` dispatches to `portal models pull`, which reads the `models:`
block of `config/portal.yaml`. A Hugging Face entry is imported only when it
pins `filename` and `sha256`: the CLI downloads that file, checks the digest,
and runs `ollama create` from a Modelfile that carries `FROM` and the entry's
`num_ctx`. After create, `ollama show --modelfile` must not contain a
`<think>` stop or any stop the entry does not list in `stops`. An entry
missing the pin is reported and skipped. `portal update` refreshes the model
ids on `type: ollama` backends in `config/backends.yaml`. A library tag is
`ollama pull`. A baked-context tag (`-ctxNk`, or `-ctxNk-agentic`) refreshes
its base, then `ollama create` writes `FROM` that base and `PARAMETER num_ctx`
— the same Modelfile as `portal models apply-params`. An entry `num_ctx` wins
over the suffix. An `hf.co/` base is created only when that base pins
`filename` and `sha256`; otherwise the derived tag is skipped. A `portal5/`
tag is skipped as a local tag with no upstream unless that entry has the pin.
A bare `hf.co/` id uses the same pin-and-create path.

##### Why

Model acquisition stays in config. `config/portal.yaml` holds the Hugging Face
pull registry and `config/backends.yaml` holds the fleet ids that `portal update`
refreshes. Pins live on those entries, so the pull set stays the fleet the
operator edited.
<!-- /WIKI:GENERATED -->

### Add a Cluster Node

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-add-a-cluster-node -->
Cluster scaling is a config-only operation. Adding a node means appending a backend entry to `config/backends.yaml`: a unique `id`, a `type` (`ollama` or `openai_compatible`), the node's `url`, the routing `group`, and the model list it serves. The pipeline discovers new backends through `BackendRegistry` at startup and the auto-routing layer load-balances across healthy backends. After editing, restart the pipeline container so the registry re-reads the file. `./launch.sh status` confirms the new backend through the pipeline health block (`backends_healthy` / `backends_total`).

#### Why

Scaling must never touch routing code, so the registry treats `config/backends.yaml` as the single operator-edited surface — a twelve-node fleet is still a YAML edit plus a restart. Keeping the scale-out path data-only is what lets a single-node install grow to a cluster without a fork, a feature flag, or a new code path.
<!-- /WIKI:GENERATED -->

### Load Guard (Model Memory Admission)

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-load-guard-model-memory -->
#### Load guard: model memory admission and tuning

The load guard (`portal/platform/inference/load_guard.py`) is the Pipeline's host-memory admission control for model loads on both engines. Ollama and oMLX draw from one unified-memory pool but each engine admits a load from its own view; the 2026-10-07 watchdog reset (`docs/reports/INCIDENT_20261007_WATCHDOG_RESET.md`) is what happens without a shared gate. Every Pipeline request to either engine reports through it, so it counts in-flight requests per (engine, model) and serialises cold loads across worker processes: each worker keeps its own asyncio lock, backed by a host-wide `cold-load.lock` file lock under `/tmp/portal-5-load-guard`, and per-model `flock` activity locks track busy models across workers — `admit_and_begin_ollama` leases that lock through request completion, reserving the model operation across workers so one worker's unload or load never collides with another's. It frees idle models rather than admitting a load that fits only by evicting a model that is serving a sibling request. An Ollama cold load that does not fit waits inside the caller's load budget: a free the guard issues stays pending until Ollama's `/api/ps` drops the model and headroom covers its bytes, and the request is refused HTTP 507 only when that budget runs out (the router cascades a 507 as a capacity rejection). When oMLX's status cannot be read the guard fails open and admits, logging loudly. Resident models — the router model, task routers, warm seats — never wait.

#### Knobs

`.env` values, passed into the Pipeline container by `deploy/portal-5/docker-compose.yml`; restart the pipeline container to apply.

- `LOAD_GUARD` (default 1): 0 disables admission entirely; in-flight tracking stays on. Change it only to confirm a refusal is the guard's.
- `LOAD_GUARD_FACTOR` (default 1.25): projected footprint = weights on disk × factor, because weights understate the loaded footprint (KV cache, compute buffers); a footprint observed the last time the model was resident overrides the projection. Raise it if large cold loads repeatedly stall near the limit; lower it only against measured footprints.
- `LOAD_GUARD_MARGIN_GB` (default 2): memory kept free after an admitted load, for everything on the host that is not a model. Raise it when non-model processes grow (bigger caches, parallel test workers).
- `LOAD_GUARD_CEILING_GB` (default 0): 0 budgets against oMLX's live `final_ceiling`, which the balanced tier derives from host free memory, so the same load's verdict can change through the night (P5-OMLX-CEILING-001). Set a fixed GiB budget to make the verdict a property of the model set rather than of the moment; the cap governs Ollama admission only — oMLX's own guard never sees it.
- `LOAD_GUARD_WAIT_S` (default 120): how long an interactive cold load waits for memory before HTTP 507. Batch callers override it per request with the header `X-Portal-Load-Wait: <seconds>` (capped at one hour); compliance's pipeline calls send their own larger budget via `COMPLIANCE_LOAD_WAIT_S`.
- `defaults.hot_seat_protect_s` in `config/backends.yaml` (shipped default 0 = off; production runs 900 — a 15-minute window — since 2026-10-22): seconds after an oMLX model's last request during which a *different* oMLX model's request is steered to another candidate instead of deep-resetting the seat's warm prefix cache (P5-OMLX-PREFIX-CACHE-001). Turn it on when two seats share the oMLX engine and one keeps re-paying a cold prefix; it never denies service, never reorders a pinned `::model=` request, and each Pipeline worker tracks its own seats.

#### Watching it work

Admissions, wait seconds, free settles, unloads, and refusals are Prometheus counters and histograms (`portal5_load_guard_admissions_total`, `portal5_load_guard_wait_seconds`, `portal5_load_guard_free_settle_seconds`, `portal5_load_guard_unloads_total`, `portal5_load_guard_refusals_total`), and the headroom and ceiling at the last decision are gauges (`portal5_load_guard_headroom_bytes`, `portal5_load_guard_ceiling_bytes`). The Grafana dashboard `config/grafana/dashboards/portal5_model_management.json` ("Portal 5 — Model Management (Load Guard)") charts them, and the Overview dashboard carries a load-guard row. `portal5_load_guard_wait_seconds` records each wait episode labelled `waited_on` (`in_flight`, `free_settle`, `engine_transition`, `model_operation`); `portal5_load_guard_free_settle_seconds{engine}` times how long a guard-issued free took to show as released (Ollama `/api/ps` drop, oMLX queued-unload counter drop). Refusals bucket by the reason their raise site records: `projected-exceeds` (the load will not fit), `free-settle` (a free the guard issued did not settle within the load wait), `transition-active` (oMLX mid-swap for the whole wait), `quiet` (nothing in flight could free the memory — waiting cannot help until something else changes), `deadline` (another cold load or model operation held the lock past the wait), and `coordination-unavailable` (the cross-process lock directory cannot be used). A turn no candidate could serve is counted separately in `portal5_no_answer_total`. Batch work can ask `POST /admin/load-plan` whether a set of models fits together right now, and run in fit-sized waves instead of discovering the answer as refusals.

#### Why

Two engines, one memory pool, and no engine that can see the other's view is exactly the shape that produced the watchdog reset: each engine admits from its own number, and both are right at the moment they ask. The guard makes admission a property of the host by serialising the loads and charging them against one measured budget, and it makes refusals rare by freeing idle memory and waiting inside the request's own budget first. That is why the knobs are memory figures and wait budgets rather than concurrency limits: the failure being prevented is running the machine out of swap, not overloading a server. The fixed ceiling exists because a verdict that moves with free memory cannot be reasoned about at all — an operator who wants the same answer for the same load all night buys that by fixing the budget, at the cost of also fixing what everything else on the host may use.
<!-- /WIKI:GENERATED -->

## Routine Operations

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-routine-operations -->
Routine lifecycle is one command per operation. `./launch.sh status` runs `_cmd_status` in scripts/lib/util.sh — a per-service health table covering the Docker stack, native services, and the pipeline's `backends_healthy` counts. `./launch.sh logs` tails the portal-pipeline container by default; the default stack has no Ollama container (the compose `ollama` service sits behind the `docker-ollama` profile), so native Ollama logs come from `/opt/homebrew/var/log/ollama.log` (the `com.portal5.ollama` LaunchDaemon's configured log path, despite the `homebrew` directory prefix — not Homebrew-managed) or `~/.portal5/logs/ollama.log` on Linux, not from `logs ollama`. On Apple Silicon, `up` installs the hourly `com.portal5.log-rotate` agent; preview its next pass with `.venv/bin/python scripts/rotate_logs.py --dry-run`. `./launch.sh seed` re-runs `openwebui-init` idempotently, `./launch.sh down` stops the stack via `_do_down` with data preserved, and `./launch.sh clean` removes only the `portal-5_open-webui-data` volume, keeping Ollama models.

### Why

Each verb carries an explicit data story — `down` preserves, `clean` wipes only Open WebUI data, `clean-all` wipes models — so an operator never reaches for `docker compose down -v` and accidentally deletes model weights. `logs` defaulting to the pipeline matches where the interesting decisions are logged.
<!-- /WIKI:GENERATED -->

## Security Notes

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-security-notes -->
Secrets live in `.env`, which `.gitignore` excludes and `bootstrap_secrets` in scripts/lib/util.sh populates by replacing every `CHANGEME` placeholder on first run. `PIPELINE_API_KEY` authenticates callers of the pipeline API; `WEBUI_SECRET_KEY` encrypts Open WebUI session and tool state — rotating it invalidates stored OAuth tokens and forces re-login, per the `.env.example` note. `GRAFANA_PASSWORD` and `SEARXNG_SECRET_KEY` are generated the same way. Rotation is edit `.env`, then restart the stack; `./launch.sh up` auto-repairs any secret that reverted to a placeholder. Never commit `.env`.

### Why

Secret hygiene is automated here because a shared default is the realistic failure: every secret starts as `CHANGEME` and is replaced at first run, so the residual risk is operator error — committing `.env` or hand-setting a weak value — which the gitignore and the placeholder-repair loop directly counter. Knowing which key guards what matters when a rotation is needed.
<!-- /WIKI:GENERATED -->

## Network Exposure

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-network-exposure -->
Bindings are per-service in `deploy/portal-5/docker-compose.yml`. Open WebUI publishes `${WEBUI_LISTEN_ADDR:-127.0.0.1}:8080` — localhost unless `ENABLE_REMOTE_ACCESS=true`, and the shipped `.env.example` sets that flag true, so a fresh install listens on `0.0.0.0`. The Docker MCP servers (8910-8926), SearXNG (8088), and Prometheus (9090) bind `127.0.0.1`. The pipeline API binds `0.0.0.0:9099` and Grafana binds `0.0.0.0:3000` (its `grafana-image-renderer` sidecar is compose-internal — no host binding). Host-native MCP servers default to `0.0.0.0` — `scripts/mlx-speech.py`, `scripts/mlx-transcribe.py`, `portal/platform/mcp_host/pipeline_mcp.py`, and the security/wiki MCPs. The external boundary is therefore the firewall plus the tunnel/proxy path, not a universal loopback guarantee.

### Why

"Everything is localhost" is a false comfort on this stack: compose services and host-native services bind differently, and the pipeline deliberately listens on all interfaces so the host MCPs and remote backends can reach it. Knowing exactly which surfaces are network-visible is what makes the recommended tunnel approach safe — it publishes only the media paths, not the full API plane.
<!-- /WIKI:GENERATED -->

### Recommended remote access: Cloudflare Tunnel

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-recommended-remote-access-cloudflare-tunnel -->
Recommended remote access is a Cloudflare Tunnel pointed only at Open WebUI on `:8080` — a single catch-all rule, no path routing (`config/cloudflared/config.yml.example`). Set three things in `.env`: `ENABLE_REMOTE_ACCESS=true`, `PORTAL_PUBLIC_URL=https://portal.example.com` (the address users type), and `OWUI_API_KEY` (an Open WebUI `sk-` key from Settings → Account → API Keys).

Every generator — speech, music, 3D, documents, spreadsheets, images, transcripts — writes its file locally, then publishes it through Open WebUI's files API via `portal.platform.mcp_host.owui_files.publish_file`. Chat gets one link shape, `${PORTAL_PUBLIC_URL}/api/v1/files/{id}/content/{name}`, served on `:8080` and authorised by the viewer's existing session cookie. No MCP serves files, no per-service ports, no ingress rules. The tunnel can run on any host. With `OWUI_API_KEY` unset a generator returns an error instead of a dead link.

#### Why

One publish path through Open WebUI keeps the external surface a single hostname to a single port: nothing but `:8080` is ever exposed, file access rides the UI's own auth, and adding a new generator needs no tunnel or firewall change. Earlier builds served files from each MCP's own port behind per-path ingress rules; consolidating onto the files API removed that entirely.
<!-- /WIKI:GENERATED -->

### Alternative: LAN reverse proxy (Caddy / nginx)

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-alternative-lan-reverse-proxy-caddy-nginx -->
For deployments that skip Cloudflare Tunnel, a Caddy or nginx proxy on the same host plays the same role: proxy Open WebUI on `:8080`, set `PORTAL_PUBLIC_URL` to the proxy's public address and `OWUI_API_KEY` to an Open WebUI `sk-` key. Generated files then come back as `${PORTAL_PUBLIC_URL}/api/v1/files/{id}/content/{name}` on `:8080` — the same one-port story as the tunnel. Bindings are per-service in `docker-compose.yml`: the Docker MCP servers bind `127.0.0.1`, but the pipeline API binds `0.0.0.0:9099`, Grafana binds `0.0.0.0:3000`, and the host-native MCP servers (`scripts/mlx-speech.py`, `portal/platform/mcp_host/pipeline_mcp.py`) default to `0.0.0.0`. The proxy must be the only thing that exposes those surfaces; never proxy the bare MCP tool APIs or the `:8080`-adjacent ports.

#### Why

The loopback-only posture is enforced per service, not globally, so an operator who assumes "everything is localhost" will misread the network map. The proxy's job is to publish exactly the media-file paths users click in chat and nothing else, which is why the ingress example is path-scoped rather than a blanket pass-through of the whole API plane.
<!-- /WIKI:GENERATED -->

## Backup

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-backup -->
`./launch.sh backup [output-dir]` writes a timestamped directory (default under `./backups/`) via `_launch_backup` in scripts/lib/backup.sh. It tars the `portal-5_open-webui-data` volume into `openwebui-data.tar.gz` (accounts, chats, settings), tars `portal-5_grafana-data` into `grafana-data.tar.gz`, and copies `.env`, `config/`, and `imports/` alongside. Ollama weights in `portal-5_ollama-models` are intentionally excluded — they are re-pullable. `./launch.sh restore <path>` confirms interactively, stops the stack with a compose down, then restores the Open WebUI data, Grafana data, and `.env` from the same directory.

### Why

The backup is only as good as the volume inventory behind it. Personal data is confined to `open-webui-data` and `grafana-data` while model weights are disposable, so excluding `ollama-models` keeps backups small and deterministic. A directory-per-run layout plus a single `restore` argument makes recovery unambiguous and never touches `docker compose down -v`.
<!-- /WIKI:GENERATED -->

## Inference Health Monitoring

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-inference-health-monitoring -->
The inference tier is a single Ollama backend on port 11434, reached by the pipeline through `OLLAMA_URL` (default `http://host.docker.internal:11434`) and by the router through `LLM_ROUTER_OLLAMA_URL`. The MLX chat-inference proxy (ports 8081/18081/18082) was retired in commit 75c24a9; its code remains only under `scripts/_archive/mlx-retired-3a0c58e/`. MLX survives strictly outside chat inference (speech, transcription, embeddings, reranking). Health monitoring is therefore `_cmd_status` in scripts/lib/util.sh: the `OLLAMA` row confirms the native server responds, and the pipeline block reports `backends_healthy` / `backends_total`.

### Why

With a single backend there is no proxy layer to supervise between the router and the models — health monitoring collapses to "is Ollama up and are the models resident." That simplification is exactly why the retired proxy's watchdog code was archived rather than maintained: supervision complexity scales with tier count, and the single-tier design removed the need for it.
<!-- /WIKI:GENERATED -->

### Debugging crashes

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-debugging-crashes -->
#### Debugging crashes

When a service is down or a persona request fails, the first step is to
separate an inference-tier problem from a pipeline problem before touching
any containers.

##### Ollama health and model list

Check that Ollama is up and list what is installed:

```bash
curl -s http://localhost:11434/api/tags | jq .
```

`/api/tags` is Ollama's model registry; a non-empty response proves the
inference tier is reachable and shows which GGUF models are present.

##### Pipeline health

Check the Portal pipeline (the OpenAI-compatible router on :9099) and
every registered backend in one call:

```bash
curl -s http://localhost:9099/health/all | jq .
```

`/health/all` is mounted in `portal/platform/inference/router/app.py` and
returns per-backend status, so a healthy response means routing itself is
fine even when a specific model is not loaded.

**Which code is running.** The pipeline and the documents, data, memory, RAG and compliance MCPs
report `build_sha` and `build_dirty` on `/health`. Docker images take them from `./launch.sh`
build arguments, and host-native services from `scripts/native-mcp-service.sh` at launch (HEAD of
the checkout; `unknown` / -1 outside one). After a code change, a service whose `build_sha` is not
HEAD, or whose `build_dirty` is above 0, is running something else: rebuild it, or restart it with
`launchctl kickstart -k gui/$(id -u)/com.portal5.<service>`.

##### All services

```bash
./launch.sh status
```

`launch.sh status` reports the whole stack, so it is the broadest first
probe when the failure's origin is unknown.

##### Why

Crash debugging needs a tier order: Ollama, then the pipeline, then the
full stack. Each command above is one cheap probe that names its tier, so
an operator can bisect a failure before restarting anything — the
pipeline cannot route to a backend that is down, and `launch.sh status`
is the catch-all when the symptom does not map to a single port. The
endpoints are grounded in the router app that mounts them and the
`launch.sh` dispatch that runs `status`.
<!-- /WIKI:GENERATED -->

---

## Router Configuration

### How the LLM Router Works

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-how-the-llm-router-works -->
Every `auto` request goes through two layers in routing.py. Layer 1 `_route_with_llm` sends the last user message to Ollama `/api/generate` with `format: _ROUTER_JSON_SCHEMA` — grammar-enforced JSON returning `{"workspace": ..., "confidence": ...}` — and accepts the result only when confidence is at least `LLM_ROUTER_CONFIDENCE_THRESHOLD`. Layer 2 `_detect_workspace` runs weighted keyword scoring over `_WORKSPACE_ROUTING` and fires on timeout, low confidence, or error. Ahead of both layers sits the `router: false` hand-off gate (`detect_router_handoff`): a workspace the operator selects explicitly is never chosen by either layer, and a request that is plainly its work goes to the workspace's `router_fallback` lane, which declines and names the workspace to select — see [[unit-routing-security-operator-selected]]. Variant recovery (`_infer_variant`) exists only on Layer 1 and covers `auto-coding`. lifespan.py pre-warms the router model with `keep_alive: -1`.

#### Why

The keyword scorer exists so the router model is never a hard dependency of serving — it is the guaranteed-latency path while the LLM layer buys accuracy. The variant asymmetry is a direct consequence: variant vocabulary lives in `_SECURITY_VARIANT_SIGNALS`, which Layer 2's scorer has no entry for, so an outage degrades variant precision rather than correctness.
<!-- /WIKI:GENERATED -->

### Three-Tier Router Models

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-three-tier-router-models -->
Three router tiers are documented in `.env.example` and the header of routing.py. PRIMARY is `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M` — 82.2% accuracy, about 840ms warm latency, roughly 5.3GB, and the default `LLM_ROUTER_MODEL`. STANDBY is `llama3.2:3b` (75.3%, about 433ms, roughly 2GB). FALLBACK is `qwen2.5:1.5b` (67.1%, about 339ms, roughly 1GB). Switch tiers by setting `LLM_ROUTER_MODEL` and dropping `LLM_ROUTER_TIMEOUT_MS` to 500 for standby/fallback. The accuracy figures trace to `tests/benchmarks/bench_router.py`'s `GOLDEN_SET`.

#### Why

Three tiers exist because accuracy and latency trade against each other on shared unified memory: the primary maximizes routing quality, the fallback's tiny footprint stays resident alongside inference models, and the standby splits the difference. The timeout must track the tier's warm latency, or every request falls through to Layer 2 keyword scoring.
<!-- /WIKI:GENERATED -->

### OLLAMA_MAX_LOADED_MODELS

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-ollama-max-loaded-models-3 -->
The slot count is `OLLAMA_MAX_LOADED_MODELS`: `.env.example` ships 5 (router model plus four inference models for chained and parallel bench work), while the compose `docker-ollama` profile still defaults to 3. The number must cover the router plus every concurrently-resident inference model — a multi-hop security chain needs each hop's model hot, or Ollama evicts and cold-reloads between hops. `run.py` reads the live value and emits a preflight warning when `--parallel-workspaces` is used with a count too low for the chain, and routing.py's header records the router model's own slot requirement. After changing it, verify the running server picked up the new value rather than assuming.

#### Why

The slot count is a memory-versus-availability trade, not a throughput knob: each resident slot competes for unified memory, but a count below the chain length converts multi-hop workspaces into cold-load stalls. The 3-to-5 bump exists so the security bench can keep four distinct chain models resident during parallel dispatch.
<!-- /WIKI:GENERATED -->

### Changing the Router Model

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-changing-the-router-model -->
The router model is chosen through `.env`: `LLM_ROUTER_MODEL` (default `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`), `LLM_ROUTER_TIMEOUT_MS` (1000 for the primary, 500 for standby/fallback), plus `LLM_ROUTER_CONFIDENCE_THRESHOLD` and `LLM_ROUTER_ENABLED`. routing.py reads these into `_LLM_ROUTER_MODEL` and `_LLM_ROUTER_TIMEOUT_MS` at startup, and lifespan.py's `_warmup_llm_router` pre-loads the configured model with `keep_alive: -1`. Apply a change by editing `.env` and restarting only the pipeline container:

```bash
docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline
```

Ollama needs no restart because the router model is an ordinary Ollama model.

#### Why

The router is a classification model, not an inference tier, so swapping it is config plus a restart with no retraining and no backend rework. The model and its timeout are coupled — the timeout is tuned to the tier's warm latency, so changing one without the other silently pushes requests into Layer 2 fallback instead of giving the new model a chance.
<!-- /WIKI:GENERATED -->

### Ollama is Native — Plist Is the Source of Truth

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-ollama-is-native-plist-is-the-source-of-truth -->
On Apple Silicon the default Ollama is native under launchd, not a container — but **not** via Homebrew. `homebrew.mxcl.ollama` was disabled and fully uninstalled 2026-08-10: Homebrew's formula lags upstream releases and shipped below this project's minimum version (`OLLAMA_MIN_VERSION` in `scripts/lib/util.sh`), and a stale Homebrew reinstall had silently taken over `:11434` at one point, running an outdated build undetected. The supported native install is a pinned binary release run as `com.portal5.ollama`, a **system** LaunchDaemon (deliberately system-domain rather than a per-user LaunchAgent, so it's up before any user is logged in). `_launch_install_ollama` in scripts/lib/services.sh reports its status (it does not install — that's a deliberate one-time manual step, see the function's own guidance); `_ensure_native_services` in scripts/lib/util.sh restarts it via `sudo -n launchctl kickstart -k system/com.portal5.ollama` whenever `up` finds it installed but not responding — passwordless sudoers rules under `/etc/sudoers.d/` (`portal5-ollama`, `portal5-claude`) cover `launchctl` and `plutil` invocations on this box (kickstart, unload/load, and in-place plist edits all run without a password prompt; plain file operations like `cp` do not — the exact per-file grant boundary is root-readable only, not verified from an unprivileged shell). The compose `ollama` service is gated behind the `docker-ollama` profile, so compose env vars (e.g. `OLLAMA_MAX_LOADED_MODELS`) do not reach the native server. The authoritative config for native is the launchd plist:

```
/Library/LaunchDaemons/com.portal5.ollama.plist
```

Root-owned — edit with `sudo`. `ProgramArguments` points at `/Users/chris/ollama-current/ollama`; since 2026-09-25 `~/ollama-current` is a symlink to `~/ollama-live/`, a **fixed real path** whose contents are the active release (its version in `~/ollama-live/VERSION`), with the previous release archived as `~/.portal5/engines/ollama-<version>/` for rollback (older ones pruned). The path is fixed because macOS keys an unbundled binary's permission to read the external `data01` volume (where `OLLAMA_MODELS` lives) to its path plus its Developer ID requirement, which is identical across Ollama releases — a new path per version meant a new approval popup per upgrade. **Upgrades are automatic:** `scripts/engine_autoupdate.py` (daily launchd job `com.portal5.engine-update`, installed by `./launch.sh up`) installs the newest non-pre-release weekly — sooner when a release in the gap carries a security fix, or on `--now` — kickstarts the daemon, waits for the model count to return (asking via Pushover for the data01 popup if it does not), and runs `scripts/engine_contract_check.py`. A contract failure rolls back to the previous release and records the rejected version in `~/.portal5/engine_update.json`; an unanswered popup rolls back and retries the next day. A plist edit still needs the full unload/load (a `kickstart -k` restarts the process but does not re-read the plist).

On 2026-10-22 that updater moved this host from Ollama 0.40.5 to 0.40.8. The run is recorded in `~/.portal5/engine_update.json` with `contract_rc` 0 and result `updated`, and `~/ollama-live/VERSION` reads 0.40.8. The library tag `flint:40b-a2b-qat-int4` is installed. Flint's bench registration is still absent from `config/backends.yaml` and `config/bench_workspaces.yaml`; the tag being on disk is not a catalog entry.

#### Why

Native and container Ollama are two separate config surfaces, and the compose file documents only the container one. An operator who tunes the container's env block while running native (the default) has made a change that never takes effect — the plist is the only lever that does, so the source of truth must be stated explicitly. The Homebrew-vs-pinned-install distinction is called out explicitly because the failure mode is silent: both bind the same port, so a stale Homebrew reinstall serving an outdated Ollama version produces no error, just quietly-wrong behavior (a whole 3-hour benchmark leg ran against it undetected) until someone thinks to check `/api/version` against the live server instead of trusting `command -v ollama`, which resolves whatever is first on PATH. The `ollama-current` symlink indirection exists because the direct-path scheme required editing the plist's `ProgramArguments` and the `/opt/homebrew/bin/ollama` PATH symlink separately on every upgrade — two places that could silently disagree after a future upgrade if only one got updated.

##### oMLX fixed-path LaunchAgent

Since 2026-10-22 this host runs oMLX as LaunchAgent `com.portal5.omlx` from the fixed venv `~/omlx-live/venv`, so access to the external `data01` volume survives wheel upgrades. The interpreter is a python.org ARM64 framework build signed with Developer ID. macOS associates external-volume access with the executable path and signing identity; Homebrew's ad-hoc Python changes identity when Homebrew installs a new Python build, while package upgrades in the fixed venv retain the signed framework interpreter. `scripts/omlx_venv_install.py` selects Python 3.11, 3.12, or 3.13, verifies `platform.machine() == "arm64"` and `codesign -dv` output, downloads the matching macOS 15 universal2 wheel from the GitHub release, and stages the venv before swapping it into place. It does not install Python. Set `OMLX_VENV_PATH` in the repo `.env` when choosing a non-default location, and render the plist with that same path. If no eligible interpreter is present, install a universal2 framework build from [python.org](https://www.python.org/downloads/macos/) and rerun the installer.

The LaunchAgent template is `deploy/launchd/com.portal5.omlx.plist`. It runs `python -m omlx.cli serve`, uses the existing `/opt/homebrew/var/log/omlx.log` stdout and stderr paths, and preserves the Homebrew PATH. Render and lint the plist when installing the agent:

```bash
VENV="$HOME/omlx-live/venv"
PLIST="$HOME/Library/LaunchAgents/com.portal5.omlx.plist"
mkdir -p "$HOME/Library/LaunchAgents"
sed -e "s#__OMLX_VENV__#$VENV#g" -e "s#__HOME__#$HOME#g" \
  deploy/launchd/com.portal5.omlx.plist > "$PLIST"
plutil -lint "$PLIST"
```

Numbered host cutover checklist:

1. Run `uv run python scripts/omlx_venv_install.py` and confirm the installer reports the fixed `~/omlx-live/venv` path.
2. Render and lint the plist using the commands above.
3. Stop the Homebrew formula with `brew services stop jundot/omlx/omlx`.
4. Boot out any remaining Homebrew LaunchAgent with `launchctl bootout "gui/$(id -u)/sh.brew.omlx"` (ignore the error only if the label is already unloaded).
5. Bootstrap the new LaunchAgent with `launchctl bootstrap "gui/$(id -u)" "$PLIST"`.
6. Verify `launchctl print "gui/$(id -u)/com.portal5.omlx"`, `curl -fsS http://127.0.0.1:8085/health`, and the expected model count. Keep the Homebrew formula installed until all three checks pass.

Rollback: boot out `com.portal5.omlx`, restart the Homebrew formula with `brew services start jundot/omlx/omlx`, and verify `/health` plus the expected model count. Keep `~/.omlx/settings.json` and `model_settings.json` in place; the engine updater makes timestamped copies before a package switch and restores them after rollback. Do not uninstall the formula until the venv service has passed its live check.

The daily engine updater obtains oMLX versions from GitHub releases, upgrades the venv from a staged copy, restarts the loaded service label, waits for model visibility, and runs `scripts/engine_contract_check.py`. A failed contract reinstalls the previous release wheel and restores the settings backup. When `com.portal5.omlx` is not loaded, the existing Homebrew update path remains the fallback.
<!-- /WIKI:GENERATED -->

### Runtime VRAM vs File Size Gap

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-runtime-vram-vs-file-size-gap -->
Ollama allocates the KV cache when a model loads, so a resident model's footprint is routinely larger than its GGUF file size; the gap grows with context length, KV quantization, and `OLLAMA_NUM_BATCH`. `devstral:24b` and `granite4.1:8b` are registered in `config/backends.yaml` (general group), and under large contexts a resident big model can push others — including the router — out of memory. Ollama offloads CPU layers rather than crashing; the evicted model cold-loads on its next request, so the first post-eviction `auto` request falls through to Layer 2 keyword scoring in routing.py. `OLLAMA_KEEP_ALIVE_REQUEST` (default `-1`) and `OLLAMA_MAX_LOADED_MODELS` bound residency, and lifespan.py's `_warmup_llm_router` re-pins the router after eviction.

#### Why

File size is the wrong planning number because the KV cache is what actually competes for unified memory, making runtime residency diverge from size. Fleet and slot planning must budget resident footprint, and the graceful offload behavior is what makes an eviction a latency event rather than a crash.
<!-- /WIKI:GENERATED -->

### OLLAMA_MEMORY_LIMIT (deferred)

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-ollama-memory-limit-deferred -->
Native Ollama runs with no memory cap by default. `OLLAMA_MEMORY_LIMIT=0` in `.env.example` means "unlimited", and in the compose `docker-ollama` profile the value becomes the container's `deploy.resources.limits.memory`; a native install ignores it entirely, so the plist is the only lever there. Ollama handles memory pressure by offloading layers to CPU rather than crashing. If Metal OOM errors or kernel panics appear under heavy multi-model load, the escalation path is an `OLLAMA_MEMORY_LIMIT` entry in the launchd plist's `EnvironmentVariables` block (reloaded via `launchctl`), or trimming `OLLAMA_MAX_LOADED_MODELS` instead of adding a cap.

#### Why

The absent cap is a deliberate default, not an oversight — the reference slot/memory mix fits the target hardware, so a hard limit would only add an artificial ceiling. Capping is reserved as the escalation move for actual OOM symptoms, which keeps the common case simpler and leaves the tuning lever available when it is genuinely needed.
<!-- /WIKI:GENERATED -->

### Verifying Router Is Warm

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-check-which-models-ollama-currently-has-loaded -->
Ollama reports resident models through its `/api/ps` endpoint. The shell check is:

```bash
curl -s http://localhost:11434/api/ps | jq '.models[] | {name, size_vram}'
```

The port and host come from `OLLAMA_URL` (default `http://host.docker.internal:11434`). The same endpoint powers the `get_loaded_models` tool in `portal/platform/mcp_host/pipeline_mcp.py`, which returns each model's name and `vram_size_gb` — the tool is what an agent sees as `portal-pipeline get_loaded_models`.

#### Why

"Which models are resident" answers the two most common operational questions at once: is the router model warm (if not, the next `auto` request cold-loads it and falls through to Layer 2), and is a large inference model squatting on unified memory at the expense of everything else. The same query is exposed to both shell and agent so operators and automation read identical state.
<!-- /WIKI:GENERATED -->

### Checking Router Decisions in Pipeline Logs

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-check-pipeline-logs-for-router-decisions -->
Router decisions are logged by the pipeline. The LLM layer logs each confident classification from `_route_with_llm` in routing.py as `LLM router: '<text>' → workspace='<id>' confidence=<n>`, and every timeout, low-confidence result, or error logs "falling back to keywords". The dispatch layer logs `Routing workspace=<id>` in handlers.py when a request is sent to a backend. `./launch.sh logs` tails the portal-pipeline container by default (the `logs` case runs `docker compose logs -f portal-pipeline`). A practical filter is:

```bash
./launch.sh logs | grep -E "LLM router|Routing workspace|falling back to keywords"
```

#### Why

Misrouted requests are decided at a single point, so the router logs are the first place to look when a user reports the wrong workspace. The `confidence` field distinguishes a genuinely low-confidence classification from a timeout, which separates a model-quality problem from a latency problem before any deeper debugging starts.
<!-- /WIKI:GENERATED -->

### Read a Turn Trace

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-read-a-turn-trace -->
Every chat response carries an `X-Correlation-ID` header. Hand that value to
`GET /v1/trace/{correlation_id}` on the pipeline and the reply is the whole
turn: which workspace the request resolved to from whatever the client asked
for, how many backend candidates were available, and each tool the model
reached for with the verdict on whether its persona was allowed to. `GET
/v1/trace` lists recent turns newest first when the header was not kept.

Both need the pipeline key:

```
curl -s -H "Authorization: Bearer $PIPELINE_API_KEY" \
  http://localhost:9099/v1/trace | jq .
curl -s -H "Authorization: Bearer $PIPELINE_API_KEY" \
  "http://localhost:9099/v1/trace/p5-abc123def456" | jq .
```

A `404` means the turn aged out of the bounded store, predates the container
restart, or capture is off. Nothing is persisted across a restart by design.

#### Why

The header was already being minted and stamped on log lines, so the shortest
path from a turn that misbehaved to the reason was a container log grep
against an id. Serving the record over the same port the client already talks
to removes that step, and keeping it key-authenticated matters because a
summary names the workspace, persona and model a turn resolved to.
<!-- /WIKI:GENERATED -->

### Pulling the Router Model

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-pull-router-model-if-not-yet-downloaded -->
The router model is an Ollama-native HuggingFace pull. The recommended path is `./launch.sh pull-models`, which runs `models_pull` in `portal/platform/inference/cli/models.py` and pulls the whole catalog via `_pull_native`; the CLI locates the `ollama` binary through `_detect_ollama_cmd` in cli/_common.py. A lone model can be pulled directly:

```bash
ollama pull hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M
```

That is the value of `LLM_ROUTER_MODEL` in `.env.example`. Until it is present, the first `auto` request after startup cold-loads it and Layer 2 keyword scoring covers the interim.

#### Why

A missing router model is a warm-up cost, not an outage — the pipeline degrades to keyword scoring rather than failing, so a fresh install still serves. Pulling through the CLI matters because it keeps the installed set in sync with the catalog, so the router model and the workspace pool are provisioned together rather than piecemeal.
<!-- /WIKI:GENERATED -->

### Router Benchmarks

<!-- WIKI:GENERATED unit=unit-ADMIN_GUIDE-router-benchmarks -->
Router accuracy is re-measurable after any model or fleet change. `tests/benchmarks/bench_router.py` scores candidate models against the `GOLDEN_SET` of 73 test cases and writes a results JSON; `tests/benchmarks/bench_router_conditions.py` measures the companion-model cold-load conditions that affect warm latency. A typical invocation is:

```bash
OLLAMA_URL=http://localhost:11434 python3 tests/benchmarks/bench_router.py
```

Results land in `tests/benchmarks/results/`, and the published PRIMARY/STANDBY/FALLBACK accuracy figures in `.env.example` trace back to this bench.

#### Why

Router quality is a measured property, not an assumption — the bench pins the accuracy numbers that justify the default model choice, so a swap can be validated against a fixed corpus before it is trusted in production routing. Keeping the corpus and the runner in the repo means the figures stay reproducible instead of remembered.
<!-- /WIKI:GENERATED -->

---

## CAD (auto-cad)

`mcp-cad-render` (:8926) builds from its own image, `Dockerfile.cad`, native `linux/arm64`
(compose pins `platform: linux/arm64`). `curl localhost:8926/capabilities` is the health view:
`engine: true` (the in-container build123d engine is up), `arch: aarch64`, `openscad_backend:
manifold`, `build123d: true`. If `engine` is false, `cad_*` calls return `engine unreachable` while
`generate_scad`/`render_*` keep working; check the container logs and `CAD_B3D_*` in `.env`
(`.env.example` has the knobs). Rebuild after any CAD code or `config/` change:
`cd deploy/portal-5 && docker compose build mcp-cad-render && docker compose up -d --no-deps
mcp-cad-render`. Evaluate CAD changes with `tests/benchmarks/bench_cad_gauntlet_v2.py --arm
key=workspace` (sealed grader; run one at a time). Details: `portal/modules/cad/PLATFORM.md`.

## Live Config References

### Personas

Current persona details are computed from `config/personas/` on demand. Query `unit-fact-persona-roster` through the wiki MCP.

### Workspaces

Use `portal config show` for the current workspace and MCP summary. Query `unit-fact-workspace-roster` through the wiki MCP for module and model-hint detail.

### Model Bindings (reachability-resolved)

Model reachability is computed from live workspace and backend configuration. Query `unit-fact-model-bindings` through the wiki MCP.

### MCP Fleet

Use `portal config show` for the current MCP fleet summary. The editable source is `config/portal.yaml`.

### Model Catalog

The live model catalog is derived from `config/backends.yaml`. Query `unit-fact-model-catalog` through the wiki MCP.

## Optional read and ingest roots

By default the documents tools read only inside the output directory (`AI_OUTPUT_DIR`,
including uploads) and `kb_ingest` reads only the knowledge-base sources directory
(`PORTAL5_KB_SOURCES_DIR`). To widen either, set `DOCUMENTS_READ_ROOTS` or
`PORTAL5_KB_INGEST_ROOTS` to an `os.pathsep`-separated list of folders in `.env`. Leave them
unset unless a folder outside those defaults must be readable by the model's tools.
`compliance_ingest` reads only the compliance data directory and the operator profile's
`corpus_dirs`.
