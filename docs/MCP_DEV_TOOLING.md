# MCP Dev Tooling — Claude Code & opencode Integration

Portal 5 ships two root-level configuration files that wire AI coding tools into the
stack. `.mcp.json` is the MCP server roster that Claude Code auto-discovers when it
opens the repo, covering the local transport servers and the remote portal-* HTTP
servers. `opencode.jsonc` is the opencode configuration: it declares the local
pipeline as the provider, the key plumbing for `PIPELINE_API_KEY`, the cloud-provider
guard, and its own `mcp` block — opencode reads tool servers from that block, not
from `.mcp.json`. Together they let both clients read the tree, run code, call Portal
tools, and, for opencode, use fully local models.

## Why

The two files exist because the two clients have different configuration surfaces:
Claude Code consumes `.mcp.json` natively, while opencode needs a provider block and
its own MCP roster. Keeping them separate but in lockstep means each tool reads the
format it expects and the integration stays declarative rather than scripted.

---

## MCP Servers (`.mcp.json`)

`.mcp.json` is the MCP server roster consumed by Claude Code. Four entries are
command-transport servers launched through `npx` or `uvx`: `filesystem`, `fetch`,
`git`, and `docker`. The rest are remote HTTP servers pointing at the reserved
portal-* ports — comfyui :8910, documents :8913, sandbox :8914, tts :8916,
security :8919, memory :8920, rag :8921, research :8922, browser :8923,
proxmox :8927, pipeline :8928, mitre :8929, wiki :8931, and detections :8932 among
them — so each tool set is available to the client without a local install.

## Why

The roster is the single place Claude Code learns which capabilities exist, and its
shape mirrors the project's port reservation table: every portal-* server is an HTTP
endpoint on a fixed port with no per-client packaging. That keeps tool delivery
cheap and makes the list auditable against `config/portal.yaml`'s fleet table.

---

### Prerequisites

The four command-transport servers in `.mcp.json` (`filesystem`, `fetch`, `git`,
`docker`) are spawned through `npx` or `uvx`, so those two runners must be on PATH.
`npx` ships with Node.js, and `uvx` ships with uv — both are single-install tools.
The remote portal-* servers need nothing beyond a running stack, and the 
`portal-sandbox` and `portal-pipeline` entries specifically require `./launch.sh up`
to have brought up the sandbox container and the host-native pipeline MCP.

## Why

Prerequisites are worth stating as a list because the failure they prevent is silent:
an MCP server that fails to spawn because `uvx` is missing looks exactly like a
server that crashed. Naming the two runners and the one stack command up front turns
that ambiguity into a two-minute check instead of a debugging session.

---

# Install if missing:

The four command-transport servers in `.mcp.json` — `filesystem`, `fetch`, `git`,
and `docker` — are launched via `npx` or `uvx`, so Node.js and uv must be installed
and on PATH before Claude Code or opencode can start them. The remote portal-*
servers have no such dependency: they are plain HTTP endpoints. The `portal-sandbox`
and `portal-pipeline` entries additionally require the stack to be running, because
`./launch.sh up` starts the sandbox container and the host-native pipeline MCP that
back them.

## Why

Splitting prerequisites between toolchain binaries and a live stack keeps the setup
diagnostic instead of magical. If an MCP server fails to load, the first question is
whether its transport depends on `npx` or `uvx` on PATH or on a service that only
exists after launch, and the answer is visible from how the server is declared in
`.mcp.json`.

---

## Portal Pipeline MCP (`portal-pipeline`, `:8928`)

The pipeline MCP is a host-native MCP SDK v2 server on port 8928 (overridable via
`PIPELINE_MCP_PORT`). `./launch.sh up` starts it through `_ensure_native_mcp_service`
in `scripts/lib/util.sh`, which on macOS registers a launchd agent that runs
`scripts/native-mcp-service.sh pipeline-mcp` — itself a thin exec of
`python -m portal.platform.mcp_host.pipeline_mcp`. The server runs its own
streamable-HTTP app and imports nothing from `portal.platform.inference`; every tool
reads live data by calling the pipeline's HTTP endpoints. It is registered in
`.mcp.json` so Claude Code and opencode pick it up automatically.

## Why

Being host-native rather than a container gives the pipeline MCP direct access to the
repo tree and the local pipeline without volume mounts or networking, and the
zero-import rule keeps the coding-tools surface decoupled from the inference stack.
The launchd wrapper makes it start and stop with the stack, so the IDE tools are
simply there when the project is up.

---

### Tools

The pipeline MCP exposes introspection and repository tools, all implemented as
`_impl_*` helpers in `portal/platform/mcp_host/pipeline_mcp.py`. `get_pipeline_status`
reports pipeline health, `list_workspaces` lists the model catalog with an optional
filter, `get_loaded_models` reads Ollama's loaded set, `get_metrics_summary` folds
the /metrics text into a summary, `get_workspace_recommendation` maps a task
description to a workspace, `trigger_backend_warmup` pre-loads one, and
`explore_repository` runs the FastContext subagent. File tools `read_text_file`,
`write_file`, `list_directory`, and `search_files` operate on the repo tree with
explicit allow-roots. The tools are reachable two ways: directly over MCP
streamable-HTTP from the IDE, or through the pipeline ToolRegistry, which discovers
them via GET /tools and dispatches POST /tools/{name} using the `pipeline` entry in
`MCP_SERVERS` (`MCP_PIPELINE_URL` overrides the base URL).

## Why

Two consumer paths exist because the same tools serve both an IDE and the in-pipeline
agentic workspaces, and sharing the `_impl_*` helpers guarantees identical behaviour
from both. That single-source-of-truth design is what keeps the tool contract from
diverging between a Claude Code session and a workspace tool call.

---

### FastContext Repository Explorer

`explore_repository` in `portal/platform/mcp_host/pipeline_mcp.py` runs the
FastContext model (`hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M`) as a
dedicated repository-exploration subagent. It issues parallel READ, GLOB, and GREP
tool calls across the repo, bounded by a default of six turns, and returns compact
citations carrying path plus line ranges. If the model has not been pulled into
Ollama the tool returns an explicit error telling the caller to run
`ollama pull` on the exact model name before retrying.

## Why

FastContext exists to stop the main coding model from burning its context window
scanning the tree. A small specialist that only finds files and line ranges keeps
the expensive reasoning model focused on the change itself, and the citation format
means the returned paths are directly actionable instead of being vague hints about
where something might live.

---

## opencode Integration (`opencode.jsonc`)

`opencode.jsonc` at the repo root tells opencode to use Portal 5 as its AI backend
instead of a cloud API. It declares a `portal` provider using the OpenAI wire format
with a base URL of :9099/v1, lists `PIPELINE_API_KEY` in the provider `env` block so the
key is passed as the bearer token, disables the built-in cloud providers, sets the
default model to `portal/codingagentic`, and carries an `mcp` block of remote HTTP
tool servers. Together these make a bare `opencode .` from the repo root a fully
local session.

## Why

opencode discovers configuration by working directory, so the project must assert
its own provider, key plumbing, and MCP roster or the client falls back to whatever
global config exists — potentially a cloud provider. Centralising the local
integration in one committed file makes the local-first posture the default for
anyone opening the repo.

---

### What opencode gets

Opening the repo with opencode delivers three things. First, fully local inference:
every completion goes through the `portal` provider in `opencode.jsonc` to the
pipeline on :9099 and then to Ollama, so no tokens leave the machine. Second, the
workspace and persona catalog as models: `GET /v1/models` advertises the base
workspaces plus the `ide_expose` personas, with a curated subset in the provider
`models` block and `portal/codingagentic` as the default. Third, the full MCP roster
declared in the opencode `mcp` block — the same HTTP servers the pipeline exposes.
Cloud providers are disabled in the same file to prevent accidental cloud use.

## Why

The point of the integration is that an IDE session should inherit the project's
local-first posture without configuration: local provider, local models, local tools,
cloud locked out. Stating what opencode actually receives makes it possible to verify
that posture from the config alone, which is the difference between a claimed local
setup and a real one.

---

### Quick start

The quick start is three steps. First bring the stack up with `./launch.sh up`, which
starts the compose services and the host-native pipeline MCP. Second, make sure
`PIPELINE_API_KEY` is exported — the wrapper scripts do this automatically, and
`opencode.jsonc` declares it for opencode. Third, open the repo: `opencode .` for the
local-pipeline client, or `claude` via one of `scripts/cc-portal.sh`,
`scripts/cc-local.sh`, or `scripts/cc-stock.sh` depending on whether the intelligence
should be cloud, local, or stock.

## Why

A quick start exists to make the zero-setup claim testable: if these three steps do
not produce a working local session, the integration is broken. Each step maps to a
concrete file or command — `launch.sh`, the key plumbing, and the per-client entry
point — so the check stays mechanical instead of depending on tribal knowledge.

---

# 1. Ensure stack is running

Every Portal MCP tool is a thin client that proxies to live services, so the stack
must be up before anything works. `./launch.sh up` (the `up` case in `launch.sh`)
first pulls the Docker images, then calls `_ensure_native_services` from
`scripts/lib/util.sh` to start the host-native MCP servers — including
`pipeline-mcp` on :8928 — and finally brings up the compose stack with the pipeline
on :9099 and the sandbox container on :8914. Both the pipeline and Ollama on :11434
have to answer before portal tools can route a request.

## Why

The pipeline MCP and sandbox MCP hold no state of their own; they forward every call
to the pipeline, Ollama, or an isolated container. Treating `./launch.sh up` as a
mandatory first step keeps health checks from failing at the network layer, which is
exactly the failure the tooling workflow is designed to avoid.

---

# 2. Export the pipeline API key into the environment

The pipeline requires a bearer token on its authenticated endpoints. The key lives as
`PIPELINE_API_KEY` in `.env` (see `.env.example`), and every entry point that talks
to the pipeline must carry it. `scripts/cc-portal.sh` and `scripts/cc-local.sh`
grep the value out of `.env` and export it before launching `claude`, and
`opencode.jsonc` declares `PIPELINE_API_KEY` in its provider `env` block so opencode
passes it as the bearer token. The pipeline MCP reads the same variable through
`_pipeline_headers` in `portal/platform/mcp_host/pipeline_mcp.py` to authenticate
its own calls.

## Why

The API key is the only guard between localhost callers and the routing stack, and it
is deliberately kept out of source control. Centralising the export in the wrapper
scripts and the provider config means an operator never has to paste the secret into
a shell by hand, which is both a convenience and a way to avoid leaking it into a
history or a log.

---

# 3. Launch opencode (reads opencode.jsonc + .mcp.json automatically)

Opening the repo with bare `opencode .` picks up `opencode.jsonc` at the root, which
carries the whole IDE integration: the `portal` provider block (base URL
:9099/v1), the `env` list for `PIPELINE_API_KEY`, a cloud-provider guard,
the default model, and a dedicated `mcp` block of remote HTTP tool servers. Note that
opencode reads the `mcp` roster from `opencode.jsonc`, not from `.mcp.json` — the
latter is the Claude Code file. `scripts/oc-portal.sh` is the explicit wrapper that
sets the key and launches opencode from the repo root.

## Why

opencode merges configuration by working directory and has no strict-MCP bypass, so
the project's behaviour has to be declared in the project's own config file. Keeping
the provider, the key plumbing, and the MCP roster together in `opencode.jsonc` makes
a bare launch from the repo root fully local without any shell incantation.

---

### Workspace selection

opencode selects a model with `--model portal/<key>`, where the key is a base
workspace id or a curated persona slug from the `models` block in `opencode.jsonc`.
The default is `portal/codingagentic`, the Laguna agentic persona. Other curated
options include `agenticheavy` for long-horizon multi-file work, `agenticlite` for a
lighter load, `auto-coding` for one-shot generation, `auto-reasoning` for deep
reasoning, `auto-security` for defensive review, and the pentest-focused
`pentestlead` and `purpleteamexec`. The picker is keyed on the post-closeout persona
slugs — the retired alias ids no longer resolve. `opencode models` lists everything
advertised by `GET /v1/models` for full discovery.

## Why

Model choice is a routing decision, not an aesthetic one: the coding tasks split
across agentic loop, one-shot generation, and long-horizon refactor, and each
workspace is tuned for one of them. Exposing the curated subset as named personas
keeps the picker legible while the full catalog stays reachable through discovery,
which is why the keys must match the pipeline's advertised ids exactly.

---

### Dual mode: Portal vs stock (no file renaming)

opencode runs in Portal mode by default inside the repo: bare `opencode .` reads
`opencode.jsonc` and gets the local pipeline backend plus the `mcp` roster.
`scripts/oc-portal.sh` is the explicit Portal wrapper; `scripts/oc-stock.sh` runs
stock opencode by exporting `OPENCODE_CONFIG` pointing at the global config, which
overrides the project provider without touching any file. If Portal models still
appear after that, the wrapper's own notes recommend running opencode from outside
the repo or setting `OC_GLOBAL_CONFIG`. Neither mode renames or edits
`opencode.jsonc`.

## Why

opencode has no strict-MCP flag and merges configs by working directory, so the only
clean way to get stock behaviour inside the repo is to force the global config into
play. Wrapping that in a script, and leaving the project config untouched, gives the
operator a reversible switch instead of a file edit they will have to undo later.

---

## Claude Code Integration

Claude Code has three operating modes with Portal 5, each a thin wrapper script
around the `claude` CLI. Mode A (`scripts/cc-portal.sh`) keeps Anthropic cloud as
the intelligence and adds Portal tools via `.mcp.json`. Mode B (`scripts/cc-local.sh`)
points `ANTHROPIC_BASE_URL` at the pipeline on :9099 so local models supply the
intelligence, and Mode C (`scripts/cc-stock.sh`) runs vanilla cloud Claude Code with
zero Portal MCP servers via the strict-mcp-config bypass. All three launch from the
repo root so `.mcp.json` and `CLAUDE.md` are discovered automatically unless
explicitly bypassed.

## Why

One tool, three intents: cloud with Portal tooling, fully local inference, and
pristine stock behaviour. Keeping each intent in its own script means the operator
picks a mode by name and never has to remember the environment variables or the
CLI flags that implement it, and none of the modes rename or delete the project's
config files to switch.

---

### Mode A — Cloud intelligence + Portal tools (default, `cc-portal.sh`)

Mode A is the default Claude Code posture: Anthropic cloud supplies the reasoning,
and Portal 5 supplies tools. `scripts/cc-portal.sh` runs `claude` from the repo
root so `.mcp.json` and `CLAUDE.md` are auto-discovered, and it exports
`PIPELINE_API_KEY` from `.env` so the portal tools that reach the pipeline are
authenticated. The equivalent manual launch is plain `claude` from the root. The
tool namespaces available come straight from `.mcp.json`: the filesystem, git,
docker, and fetch servers plus the portal-sandbox and portal-pipeline HTTP servers.

## Why

This mode exists to give the strongest available reasoning model access to Portal's
operational surface — the sandbox, the pipeline introspection tools, and the repo
filesystem — without any of that intelligence being replaced. It is the default
because it needs no model routing configuration; the tools are simply present and
the cloud model uses them.

---

### Mode B — Local model intelligence + Portal tools (`cc-local.sh`)

Mode B keeps the same Portal tool set as Mode A but moves the intelligence on-box.
`scripts/cc-local.sh` exports `ANTHROPIC_BASE_URL=http://localhost:9099` and
`ANTHROPIC_API_KEY=$PIPELINE_API_KEY`, verifies the pipeline answers on /health, and
then launches `claude`, defaulting the model to `agenticheavy` unless one is passed
with `--model`. The pipeline's `anthropic_messages` handler translates the
`/v1/messages` body via `anthropic_to_openai_body`, routes it through the normal
chat-completions stack, and returns Anthropic-format SSE — so Claude Code believes it
is talking to Anthropic while every token is generated locally.

## Why

The Anthropic compatibility endpoint is what makes Claude Code usable as a local-model
IDE without forking the CLI: the SDK's base URL and key are the only moving parts.
Keeping the wrapper responsible for those two variables, plus the default persona
selection, means local inference stays a one-command operation with the full tool set
intact.

---

### Mode C — Stock cloud (zero Portal MCP, `cc-stock.sh`)

Mode C runs vanilla cloud Claude Code inside the repo with none of Portal's MCP
servers. `scripts/cc-stock.sh` builds the argument list starting with
`--strict-mcp-config`, which tells Claude Code to load only command-line MCP servers
and ignore all file-based ones, so `.mcp.json` stays in place untouched. By default
the inline config is empty; setting `CC_STOCK_KEEP_GENERIC` adds back only the four
non-Portal servers (filesystem, fetch, git, docker), and setting
`CC_STOCK_IGNORE_SETTINGS` appends `--setting-sources user` to also skip project and
local settings.

## Why

Stock mode exists because occasionally the operator wants pristine cloud Claude Code
— no sandbox, no pipeline tools, no project config influence — without modifying the
repo. The strict-mcp-config flag delivers exactly that, and the two environment
switches give a graduated path from zero MCP to the generic-only subset without ever
touching a file.

---

## `auto-coding` Workspace — `laguna` Variant

The `laguna` variant of the `auto-coding` workspace is the default agentic coding lane
for opencode and Claude Code. `config/portal.yaml` pins its `model_hint` to
`laguna-xs.2:Q4_K_M-ctx64k`, sets `keep_alive` to 15 minutes and `context_limit` to
65536, and attaches a `system_prompt_append` that encodes the agentic loop: explore
with `explore_repository`, read with `read_text_file`, plan, edit with `write_file`,
verify with `execute_bash` running pytest, then report. The backing model id
`laguna-xs.2:Q4_K_M` is registered in `config/backends.yaml`, and the `codingagentic`
persona in `config/personas/codingagentic.yaml` binds this variant for the IDE
picker with `ide_expose` enabled.

## Why

A coding model is only as good as the loop it is told to run. Encoding read, plan,
edit, verify directly in the system prompt removes the guesswork about which tools
exist and which order to call them, and the persona indirection lets the picker
address the variant by a stable name rather than by an implementation detail of the
workspace config.

---

### Fixing a bug (Claude Code)

Fixing a routing bug with Claude Code in Portal mode follows the tool chain that
`.mcp.json` and the pipeline MCP provide. The session starts with
`explore_repository` to locate the routing and workspace-selection code, then reads
the exact ranges from `router/routing.py` or `router/workspaces.py`, makes the edit
through the filesystem server, verifies with `execute_bash` in the sandbox running
pytest, and finishes with the git server's diff and commit tools. Every step maps to
a concrete server in `.mcp.json`, so no manual checkout or terminal juggling is
required to take a fix from discovery to commit.

## Why

The walkthrough is really a contract between the tool roster and a debugging flow:
exploration, targeted read, edit, test, and version control are each owned by one
server. That separation keeps the expensive reasoning model focused on diagnosis
while the mechanical steps stay cheap and auditable, which is the whole point of
assembling the IDE tool set.

---

### Adding a feature (opencode with local Laguna)

Adding a new workspace with opencode and the local Laguna persona follows the
agentic loop that the `laguna` variant's `system_prompt_append` in `config/portal.yaml`
bakes into every turn. First call `explore_repository` (FastContext) to learn how
workspaces are defined and which files the routing touches, then use `read_text_file`
and `write_file` from `portal/platform/mcp_host/pipeline_mcp.py` to make the change,
and finally run the unit suite with `execute_bash` in the sandbox. The workspace
definition itself lands in `config/portal.yaml` and is consumed by the routing layer.

## Why

The loop exists because a new workspace is a real configuration change: it must match
the shape the router expects or every request for it mis-routes. Making exploration,
edit, and verification explicit steps forces the model to confirm the exact definition
shape before writing anything, which keeps a one-file addition from becoming a
routing incident.

---

### Debugging a failing MCP server (Claude Code)

When a Portal MCP tool errors, the containerised servers and the pipeline MCP expose
enough surface to diagnose without leaving Claude Code. The sandbox runs as the
`mcp-sandbox` compose service bound to :8914 (see `deploy/portal-5/docker-compose.yml`);
its logs and health endpoint answer the usual questions. The `filesystem`, `git`,
`docker`, and `fetch` servers in `.mcp.json` give the client container listing, log
reading, and an HTTP probe path, and the failing tool can be invoked directly to
reproduce the error. Health handlers like the one in `code_sandbox_mcp.py` report
sandbox posture at a glance.

## Why

MCP failure debugging is mostly localisation: is the container up, is the HTTP
endpoint answering, or is the tool's own logic throwing? The tool roster in
`.mcp.json` was assembled so each of those questions has a server to answer it,
turning a black-box tool failure into a short read of logs, health, and one direct
call.

---

### Checking what's in VRAM before a long task

Before a long coding session, check whether the model you need is already resident in
memory so the first request is not a cold load. The `get_loaded_models` tool in
`portal/platform/mcp_host/pipeline_mcp.py` asks Ollama's `/api/ps` endpoint and
returns each loaded model's name, `size_gb`, `vram_size_gb`, and `expires_at`. A
model listed there is warm and will answer immediately; one that is absent will cost
a load before it can produce tokens. The `trigger_backend_warmup` tool exists for the
opposite case — pre-loading a workspace before you start.

## Why

Warm-model awareness is what turns a long agentic task from a sequence of
ten-second stalls into a continuous flow. Checking residency once at the start, and
optionally warming the workspace you plan to use, lets the model plan around cold
starts instead of being surprised by them mid-task.

---

## Prometheus Fetch Patterns

The pipeline exposes Prometheus text on /metrics from `portal/platform/inference/router/handlers.py`.
Hand-rolled gauges report `portal_backends_healthy`, `portal_backends_total`,
`portal_uptime_seconds`, and `portal_workspaces_total`, while the registry adds the
labelled request counter `portal_requests_total`, the error counter
`portal_errors_total`, and the `portal5_*` family such as `portal5_tool_calls_total`.
Prometheus runs on :9090 scraping the pipeline (see the job in
`config/prometheus/prometheus.yml`), and Grafana on :3000 provisions dashboards from
`config/grafana/dashboards`. The pipeline MCP's `get_metrics_summary` reads the same
text endpoint and collapses it into a summary.

## Why

The patterns exist so an operator can verify behaviour end to end — request counts,
tool dispatch, errors — without guessing. Metric names are the contract between the
exposition and any consumer, so they are stated here as they are defined in the
code, and the dashboard and MCP consumers all read from the one /metrics endpoint
rather than maintaining their own instrumentation.

---

## Security Boundaries

Each MCP server in `.mcp.json` has an explicit boundary. `filesystem` is launched
with `${HOME}/projects` and `/tmp` as its allowed roots. `docker` reaches the Docker
socket, which is acceptable only on a single-user machine. `fetch` performs HTTP
requests and should not be pointed at administrative APIs. `portal-sandbox` runs code
in an isolated container (`code_sandbox_mcp.py`) whose posture widens only when
`SANDBOX_LAB_EXEC` is set. `portal-pipeline` binds localhost and authenticates with
`PIPELINE_API_KEY`. There is deliberately no sqlite server: the Open WebUI database
lives in the `open-webui-data` named volume rather than a host bind mount.

## Why

The boundaries are the trust model for a local, single-operator setup, and they are
stated explicitly because each server is a different kind of surface. Reading them
together shows which servers are sandboxed, which inherit host trust, and which are
read-only — the information an operator needs before granting a coding agent broader
access or exposing a port.

---
