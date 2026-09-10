# Portal 5 — Local AI Platform

<!-- WIKI:GENERATED unit=unit-readme-portal-5-local-ai-platform -->
Portal 5 is a complete, private AI platform that runs on your hardware: text,
code, security analysis, images, music, documents and voice — all local. It
connects to Open WebUI, Telegram and Slack, and routes each task automatically to
the workspace that carries the right model and toolset. Image and video
generation are MLX-native on Apple Silicon (MFLUX for images; `ltx-2-mlx` for
video, behind the `video` module — off by default, shipped enabled).

Inference is fully local: prompts and responses never leave the machine. Model
downloads from HuggingFace or Ollama registries transmit standard HTTP metadata,
and if `HF_TOKEN` is configured for gated models, authentication requests are sent
to HuggingFace. No cloud accounts or usage fees are required.

## Why

The platform is scoped as an enhancement layer over Open WebUI rather than a
replacement web stack, which keeps authentication, chat history and RAG inside a
battle-tested frontend while the pipeline owns routing and model selection. Image
and video generation moved to the host MLX layer (from a ComfyUI path that Metal's
lack of FP8 made unrunnable here); video is an M7 module that is disabled by
default but shipped enabled, so flipping it is a one-command toggle rather than
a rebuild.
<!-- /WIKI:GENERATED -->

---

## What this is for

<!-- WIKI:HUMAN-OWNED reason="founding commitments — the project's purpose, not a property of the code" -->
Portal 5 exists because the useful version of an AI assistant is the one you can tell the truth
to.

That rules out most of the market. Ask a hosted model about the control network you are
defending, the compliance gap you have not closed, or the code you have not shipped, and you
have filed all of it with a company whose retention policy is a link in a footer. So the
question this started from was narrow and testable: can a fully local, fully private assistant
be *good enough to actually use* — not as a demo, not as a principle, but as the thing you
reach for on a Tuesday afternoon?

It can. That is the whole claim, and everything here serves it:

- **Privacy-first.** Your prompts and your responses stay on this machine. Not "anonymized," not
  "not used for training." They do not leave.
- **Fully local.** Inference runs here, on your hardware. Downloading a model is the only thing
  that reaches out, and you can see exactly when it does.
- **Zero cloud dependencies.** No accounts, no API keys, no per-token meter, no vendor who can
  deprecate the model you built a workflow around.
- **One command.** A fresh machine reaches a working stack from `./launch.sh up`. If that stops
  being true it is a bug, not a documentation problem.

Every awkward decision downstream traces to one of those four being treated as non-negotiable
while something more convenient was given up. The convenient thing was usually a cloud call.
<!-- /WIKI:HUMAN-OWNED -->

## Why you'd choose this

<!-- WIKI:HUMAN-OWNED reason="comparative judgment — an argument about the alternatives, each with its real cost" -->
Portal 5 is not the easy choice. The honest comparison:

**Against a hosted assistant.** A frontier model in someone's cloud is smarter than anything you
will run at home, and it is ready in the time it takes to sign up. What you give up is
everything you type: it lands on hardware you do not control, under terms you did not write, and
"we don't train on your data" is a promise, not a mechanism. Portal 5 trades the smarter model
for the property that the sentence never leaves your machine.

**Against wiring your own local stack.** You can connect Ollama, a web UI, a search index and a
handful of tool servers yourself — a few weekends of integration and a standing maintenance cost
every time a component moves. Portal 5 is that assembly, already done and kept working, behind
one command. What you give up is the satisfaction of having made every wiring decision yourself.

**Against a bare Ollama install.** Ollama runs the models; it does not choose one, grant it the
right tools, or give it a system prompt shaped for the task. Portal 5 is the layer on top — you
pick an intent and the workspace behind it sets the model, the toolset and the context budget.
What you give up is little you will miss, unless you enjoy remembering which model was good at
what.

**Against a commercial on-prem product.** Those exist and are supported, for a licence fee and a
lock to someone's release schedule and roadmap. Portal 5 is a repository you own outright. What
you give up is a support contract and someone else's SLA.
<!-- /WIKI:HUMAN-OWNED -->

## What Portal 5 is not

<!-- WIKI:HUMAN-OWNED reason="scope boundary — the deliberate choices about what not to build, and the tradeoff they buy" -->
Portal 5 is an intelligence layer on top of Open WebUI, not a replacement for it. Some things it
deliberately is *not*:

- **Not a chat UI, auth system, knowledge base or metrics stack.** Open WebUI already does those
  well, so Portal 5 extends it through the Pipeline server and MCP tool servers rather than
  rebuilding a web frontend.
- **Not cloud inference with a local option.** There is no frontier fallback when a local model
  struggles. If a model you can run cannot do the task, the honest answer is that it cannot, and
  `KNOWN_LIMITATIONS.md` is where those answers are written down.
- **Not an agent framework.** No LangChain, no LlamaIndex — the abstraction layers cost more
  here than they saved.

The tradeoff, plainly: you give up a frontier model's ceiling and you take on running your own
hardware. What you get back is that nothing you type is somebody else's training data.
<!-- /WIKI:HUMAN-OWNED -->

## How much of this you get

<!-- WIKI:HUMAN-OWNED reason="orientation for a first-time reader — the kinds of capability, framed around a count that is generated rather than typed" -->
Capability in Portal 5 comes in a few kinds, and it helps to know them before the numbers:

- **Modules** are whole domains you can switch off wholesale — security, coding, compliance,
  documents, image, media and the rest.
- **Workspaces** are routing destinations: each pins a model to a toolset and a context budget,
  so choosing a workspace chooses all three.
- **Personas** layer a voice and a set of constraints on top of a workspace.
- **MCP tool servers** are the tools themselves — documents, code sandbox, research, browser,
  retrieval, CAD, and more.
- **Channels** are the ways in: the Open WebUI browser tab, plus Telegram and Slack.

The count itself is generated, so it cannot go stale between releases:
<!-- /WIKI:HUMAN-OWNED -->

<!-- WIKI:GENERATED unit=unit-readme-capability-rollup -->
Portal 5 is one platform assembled from a small set of switchable
parts. The headline figures below are derived from config on every
seed, never hand-written.

| Kind | Count | Source |
|---|---|---|
| Modules | 15 enabled of 16 | `config/modules.generated.yaml` |
| Functional workspaces | 25 | `config/portal.yaml` `workspaces` |
| Benchmark workspaces | 57 | `config/portal.yaml` `workspaces` (eval module) |
| Workspaces total | 82 | `config/portal.yaml` `workspaces` |
| Personas | 135 | `config/personas/` |
| MCP tool servers | 33 | `config/portal.yaml` `mcp_fleet` |

That is 15 modules enabled of 16 modules total, 25 functional workspaces (57 benchmark workspaces, 82 workspaces total), 135 personas and 33 MCP tool servers — plus the Telegram and Slack channels, which carry no count of their own.

### Why

A first-time reader needs one number before they need eighty-one, so the README opens its capability section on a single rollup. It has to be derived rather than typed because every figure here moves between releases as modules, workspaces and personas are added or retired, and a README that quotes a stale count is the fastest way to lose a new reader's trust in the rest of the page.
<!-- /WIKI:GENERATED -->

## What it does on this hardware

<!-- WIKI:HUMAN-OWNED reason="performance expectations — the shape of the answer by hand, with the numbers deferred to a real bench run" -->
The honest shape of it: a short question comes back in a couple of seconds. A larger model
trades tokens per second for judgment, so a hard reasoning task feels more like waiting for a
colleague to think than like a web search. Model size sets the memory floor, and when two large
models are asked for at once the router evicts one.

Concrete throughput belongs here, but it has to come from a bench run on your hardware, not from
a guess. `docs/PERFORMANCE.md` documents the `bench_tps.py` harness; results land in
`tests/benchmarks/results/` per run.

**honest-BLOCKED:** the tokens-per-second and memory-per-model table for this README is not
filled in yet. To produce it:

```bash
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace auto --runs 3
```

A wrong throughput figure in the one document a stranger uses to judge the project is worse than
an absent one, so this section stays blocked until a real bench lands.
<!-- /WIKI:HUMAN-OWNED -->

## Which path is yours

<!-- WIKI:HUMAN-OWNED reason="reader-type triage — an opinion about who should do what first, with the time each costs" -->
Three ways in, depending on why you are here.

**Just trying it** — about half an hour. Run `./launch.sh up`, let it pull the core models, and
use the browser tab. Do not pull the specialized catalog yet; it is large and you do not need it
to judge whether the basics work.

**Running it daily** — an evening. Pull the full catalog with `./launch.sh pull-models`, enable
a channel if you want the assistant in Telegram or Slack, and point retrieval at the material
you actually care about.

**Building on it** — a week before you commit code. Read `CLAUDE.md`, the classification guide
and the governance rules first. Portal 5 has opinions about where a new module, workspace or
tool server belongs, and the rules are enforced at commit time.
<!-- /WIKI:HUMAN-OWNED -->

## You know it worked when

<!-- WIKI:HUMAN-OWNED reason="acceptance judgment — what 'working' means to an operator, which no health probe defines" -->
`./launch.sh up` printing an endpoint list means the stack started. It does not mean it works.
You know it works when:

- you can sign in at `http://localhost:8080` with the credentials in `.env`;
- the model dropdown lists more than one preset;
- a plain question answers coherently within a few seconds;
- a question that needs a tool visibly uses one rather than describing what it would do;
- `./scripts/smoke_stream.sh` streams tokens instead of delivering one block at the end;
- `uv run python scripts/validate_system.py` exits zero;
- Grafana shows request metrics after you have had a conversation.

The useful diagnostic: if the last two pass and the first five do not, the stack is healthy and
the configuration is wrong — start at Troubleshooting, not at reinstalling.
<!-- /WIKI:HUMAN-OWNED -->

## What to do next

<!-- WIKI:HUMAN-OWNED reason="sequencing advice — an opinion about the order of the first week, not a system behaviour" -->
**First hour.** Have a real conversation, switch workspaces mid-task and watch the model change,
ask something that forces a tool call.

**First evening.** Pull the specialized catalog, wire up a channel, and point retrieval at a
folder of your own documents.

**First week.** Read `docs/USER_GUIDE.md` end to end, skim `P5_ROADMAP.md` for where this is
going, and read `KNOWN_LIMITATIONS.md` — it is long on purpose, and it is where the honest
answers about what does not work yet are kept.
<!-- /WIKI:HUMAN-OWNED -->

---

## Prerequisites

<!-- WIKI:HUMAN-OWNED reason="section framing — why the Prerequisites list is the enforced set, not an aspirational one" -->
This list is what `_check_hardware` actually enforces on every start, not a wishlist. The
numbers are floors for a working set that has to hold a router plus at least one resident model;
below them the stack stops rather than limping into a confusing failure. Apple Silicon is named
first because the native Metal inference and MLX runtimes are where the performance lives.
<!-- /WIKI:HUMAN-OWNED -->

<!-- WIKI:GENERATED unit=unit-readme-prerequisites -->
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
version; disabled and uninstalled 2026-08-10), `install-mflux` sets up
the MLX-native image generator, and the other native MLX services run on the
M-series Metal path. On non-Apple-Silicon machines the installers print
Linux/Docker alternatives instead of failing.

### Why

The hardware gate runs before any pull or compose step so the stack fails fast
with a readable reason instead of dying mid-download or silently OOMing at first
inference. The thresholds come from the real working set: the router plus a pinned
model need 16 GB, and the FLUX checkpoint sets the floor for the disk check.
<!-- /WIKI:GENERATED -->

---

## Quick Start

<!-- WIKI:HUMAN-OWNED reason="section framing — why first boot is one command that does a lot" -->
The whole of first boot sits behind `./launch.sh up` on purpose: secret generation, workspace
init, hardware checks and the core model pull all happen inside it, so there is nothing to
hand-edit before the stack is usable. If a fresh machine cannot reach a working stack this way,
that is the bug to file.
<!-- /WIKI:HUMAN-OWNED -->

<!-- WIKI:GENERATED unit=unit-readme-quick-start -->
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
  Grafana:     http://localhost:3000  (admin / check .env)
  Prometheus:  http://localhost:9090
```

Sign in at http://localhost:8080 with the admin credentials in `.env`
(`OPENWEBUI_ADMIN_EMAIL` defaults to `admin@portal.local`, password is the
auto-generated `OPENWEBUI_ADMIN_PASSWORD`). Do not commit `.env`.

### Why

The zero-setup contract is that a fresh machine reaches a usable stack from one
command: secret generation, workspace init, hardware checks and model bootstrap
all happen inside `up` so the operator never hand-edits a config to get started.
The printed endpoints are the actual compose service URLs, so the first login uses
credentials that already exist in `.env`.
<!-- /WIKI:GENERATED -->

---

## What Starts Automatically

<!-- WIKI:HUMAN-OWNED reason="section framing — why the stack is split between Docker and host-native services" -->
Two runtimes, deliberately. The web services live in Docker for its networking, health checks
and restart policy; the Apple Silicon runtimes — generation, embeddings, speech — run
host-native because Metal is faster and lighter outside a container. `up` confirms or starts
them; it does not install them, so the first run of each installer is a separate step.
<!-- /WIKI:HUMAN-OWNED -->

<!-- WIKI:GENERATED unit=unit-readme-what-starts-automatically -->
`./launch.sh up` starts the core Docker stack (compose services plus profiles
auto-selected from Telegram/Slack tokens). Host-native Apple Silicon services
start when their launchd agent has been installed — `_ensure_native_services` in
`scripts/lib/util.sh` checks each registered launchd label (MFLUX image, music backend,
MLX Speech, MLX Transcribe, embedding) and boots the service via `launchctl` or a
background `nohup` fallback.

| Service | What it does | URL/port |
|---|---|---|
| Open WebUI | Chat interface — main portal | http://localhost:8080 |
| Portal Pipeline | Routing, auth, metrics, MCP dispatch | :9099 |
| Ollama | Local GGUF models via Metal | :11434 |
| SearXNG | Private web search | :8088 |
| MCP fleet | MFLUX image :8933, video-mlx :8935, Music-MiniMax :8912, Documents :8913, Sandbox :8914, Whisper :8915, TTS :8916, Security :8919, Memory :8920, RAG :8921, Research :8922, Browser :8923, MLX Transcribe :8924, Reranker :8925, CAD :8926, Proxmox :8927, Pipeline MCP :8928, MITRE ATT&CK :8929, BinResearch :8930, Wiki :8931, Detections :8932 | config/portal.yaml |
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

### Why

The split into a compose stack and host-native launchers exists because Apple
Silicon runtimes (MLX generation, embeddings) are faster and lighter outside Docker,
while the web services benefit from compose's networking, health checks and
restart policy. launchd registration makes the native services survive reboots and
crashes, so `up` only needs to confirm or start them rather than install them.
<!-- /WIKI:GENERATED -->

---

## Workspaces

<!-- WIKI:HUMAN-OWNED reason="section framing — why routing goes through a config catalog rather than a raw model list" -->
A workspace is the unit of "pick the right setup for this task": it names a model, a toolset and
a context budget together, so you choose an intent and get all three. Keeping the catalog in
`config/portal.yaml` rather than in code makes adding one an operator edit, and the benchmark
workspaces stay walled off from daily routing unless the eval module is switched on.
<!-- /WIKI:HUMAN-OWNED -->

<!-- WIKI:GENERATED unit=unit-readme-workspaces -->
Select a workspace in the Open WebUI model dropdown to activate the right model
and tools automatically. Each workspace carries a `model_hint:` (the served model)
and a `tools:` array (the tool grants), both defined in `config/portal.yaml` and
loaded at import time into `WORKSPACES` by `portal/platform/inference/router/workspaces.py`
via `get_workspace_dict()`.

Portal 5 includes **25 functional workspaces** (plus 57 benchmark workspaces for
performance comparison, gated off by default behind the `eval` module, which is
disabled unless `PORTAL_ENABLE_EVAL=1` is set; 82 total —
`python3 -c "import yaml; d=yaml.safe_load(open('config/portal.yaml')); print(len(d['workspaces']))"`).
Benchmark workspaces are excluded from routing when the eval module is off, so the
daily model dropdown stays limited to the functional set.

### Why

Routing against a config-declared workspace catalog rather than a hardcoded model
list keeps model and tool selection an operator-editable fact: adding a workspace
is one block in `config/portal.yaml`, and `sync-config` propagates it to routing,
the model registry and Open WebUI presets. The eval-module gate exists so
benchmark lanes never leak into normal use unless the operator explicitly opts in.
<!-- /WIKI:GENERATED -->

---

### Functional Workspaces

<!-- WIKI:GENERATED unit=unit-readme-functional-workspaces -->
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
| `auto-video` | `granite4.1:8b-ctx16k` (generate_video / animate_image, MLX LTX-2.3; shipped enabled) |
| `auto-image` | `granite4.1:8b` (generate_image / edit_image, MFLUX) |
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

#### Why

Mapping a dropdown entry to a (model, toolset) pair is what makes the platform
usable without prompt discipline: the user picks an intent, and the workspace
carries the model weight class and the capability grants. Keeping that mapping in
`config/portal.yaml` lets operators add or retune a lane without touching code,
and `sync-config` pushes it into routing and the Open WebUI presets.
<!-- /WIKI:GENERATED -->

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

The live count is currently 57 workspaces. Verified examples from `config/portal.yaml`:

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

#### Why

A bench lane decouples model choice from workspace behavior: the same toolset,
prompt scaffolding and routing apply, so a TPS or quality delta is attributable to
the model weights alone. Keeping the lanes behind the eval module (disabled by
default, `PORTAL_ENABLE_EVAL=1` to opt in) stops them from cluttering the daily
model dropdown while leaving a documented harness path.
<!-- /WIKI:GENERATED -->

---

## Common Commands

<!-- WIKI:HUMAN-OWNED reason="section framing — how to read this section and what it is not" -->
This is not the full command surface — `./launch.sh` with no argument prints that. It is the
handful you actually reach for after a fresh install, in roughly the order you meet them. If a
command here does something surprising, the fix is almost always in the small shell library it
delegates to under `scripts/lib/`, not in `launch.sh` itself.
<!-- /WIKI:HUMAN-OWNED -->

<!-- WIKI:GENERATED unit=unit-readme-common-commands -->
The operator surface is one dispatcher: `./launch.sh <command>`. The `case`
statement in `launch.sh` routes every subcommand, and most delegate either to a
sourced library under `scripts/lib/` or to `portal.platform.inference.cli`. The
core lifecycle commands are `./launch.sh up` (build the stack, auto-generate
secrets, run port pre-flight), `./launch.sh down` (stop Docker services plus
native macOS services while preserving data) and `./launch.sh status` (health
table via `_cmd_status` in `scripts/lib/util.sh`). Around that core sit the
operational groups below; `sync-config` regenerates derived artifacts from
`config/portal.yaml`, and the native Apple Silicon services are handled with the
`start-speech` / `start-transcribe` pairs and the embedding installers in
`scripts/lib/services.sh`.

### Test everything is working

```bash
# Test everything is working
./launch.sh test            # Run live smoke tests against running stack
```

The `test` subcommand executes `portal.platform.inference.cli test`, implemented
in `portal/platform/inference/cli/smoke.py`. `cmd_test` runs end-to-end checks
against the live stack: it probes the pipeline health endpoint (`PIPELINE_URL`,
default `http://localhost:9099`) with the configured `PIPELINE_API_KEY`, then the
Open WebUI URL (`OPENWEBUI_URL`), and prints a per-check pass/fail summary that
exits nonzero on any failure. It is the quick post-`up` check, separate from the
heavier acceptance suite.

### Pull specialized models (security, coding, reasoning — 30–90 min)

```bash
# Pull specialized models (security, coding, reasoning — 30–90 min)
./launch.sh pull-models
```

`pull-models` delegates to `portal.platform.inference.cli models pull`, which
reads the model registry from `config/portal.yaml` (`models:` block), resolves
targets with `_select_pull_targets` (skipping `retired: true` entries and entries
with no `ollama_name`), and fetches each into Ollama — HuggingFace repos through
`hf download`, native registry tags through `ollama pull`. Anything already
present is skipped, and gated repos need `HF_TOKEN` set in `.env`.

### User management

```bash
# User management
./launch.sh add-user alice@example.com "Alice Smith"
./launch.sh list-users
```

Both wrap the Open WebUI admin API from `scripts/lib/users.sh`. `add-user` posts
to `/api/v1/auths/add` with an admin token from `get_admin_token`, mints a
temporary password, and prints the new account's credentials; the role defaults
to `user` and also accepts `admin` or `pending`. `list-users` reads
`/api/v1/users/`. Both need the stack running and an admin token resolvable.

### Seeding

```bash
# Seeding
./launch.sh seed            # Re-seed Open WebUI (workspaces + personas)
./launch.sh reseed          # Force-refresh all presets (delete + recreate)
```

Both run the `openwebui-init` compose service, which executes
`scripts/openwebui_init.py` against the Open WebUI API. `seed` is idempotent —
`FORCE_RESEED` is false, so existing presets are left alone — while `reseed` sets
`FORCE_RESEED=true` and deletes then recreates every workspace, persona and tool
preset. `./launch.sh up` also runs an incremental seed in the background whenever
`open-webui` is already healthy.

### Why

A single entrypoint keeps every operational action deterministic and scriptable:
each subcommand maps to one small shell library or one typed CLI module, so there
is exactly one way to start, stop, seed, verify or back up the stack, and the
Docker Compose project directory and `.env` are never hand-edited — which keeps
`docker compose up` and `launch.sh up` from diverging. The groups above are kept
separate from the lifecycle core because each is an occasional, operator-initiated
step — pulling the large specialized catalog, provisioning an account, repairing a
drifted preset set — that has no business running on every boot.
<!-- /WIKI:GENERATED -->

---

## Enable Telegram Bot

<!-- WIKI:GENERATED unit=unit-readme-telegram-bot-setup -->
To enable the Telegram channel, create a bot in Telegram and add its token to
`.env`:

1. Open a chat with **@BotFather** and send `/newbot`; copy the token it returns.
2. Ask **@userinfobot** for your numeric Telegram user ID.
3. In `.env` set:
   ```bash
   TELEGRAM_BOT_TOKEN=your-token-here
   TELEGRAM_USER_IDS=your-user-id
   ```
4. Run `./launch.sh up-telegram` — `launch.sh` aborts the start when
   `TELEGRAM_BOT_TOKEN` is empty, otherwise it runs
   `docker compose --profile telegram up -d`.
5. Send `/start` to the bot; the handler in `portal_channels/telegram/bot.py`
   confirms the relay works.

The `portal-telegram` service in `deploy/portal-5/docker-compose.yml` is gated
behind the `telegram` compose profile. A plain `./launch.sh up` enables the
profile automatically when the token is present, so adding the channel is just a
`.env` edit; `up-telegram` is the explicit variant that forces the profile on.
The container relays user messages to the pipeline with `PIPELINE_URL` and
`PIPELINE_API_KEY`. `TELEGRAM_USER_IDS` accepts a comma-separated list of the
only Telegram accounts allowed to talk to the bot, and
`TELEGRAM_DEFAULT_WORKSPACE` picks the routing workspace for any user who has not
chosen one with `/workspace`.

### Why

Keeping the bot behind a compose profile, rather than a default service, keeps a
token-less first install free of an always-on relay container. The token check in
`up-telegram` fails loudly instead of booting a bot with no credentials, and the
auto-detection in `up` means the whole channel can be switched on by setting one
`.env` value — the bot itself stays a thin transport that passes text to the
pipeline and returns its answer.
<!-- /WIKI:GENERATED -->

---

## Enable Slack Bot

<!-- WIKI:GENERATED unit=unit-readme-slack-bot-setup -->
To enable the Slack channel, create a Slack app with Socket Mode and add its
tokens to `.env`:

1. Create a new app at https://api.slack.com/apps (**Create New App** -> **From scratch**).
2. Under **OAuth & Permissions**, add the bot scopes:
   `app_mentions:read`, `chat:write`, `channels:history`, `im:history`, `im:read`, `im:write`
   (Slack-side app configuration).
3. Enable **Socket Mode** and generate an **App-Level Token** (xapp-...).
4. Install the app to your workspace.
5. In `.env` set:
   ```bash
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_SIGNING_SECRET=...
   ```
6. Run `./launch.sh up-slack` — `launch.sh` refuses to start unless both
   `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` are set, then runs
   `docker compose --profile slack up -d`.
7. Mention `@portal` in a channel; the `app_mention` event handler in
   `portal_channels/slack/bot.py` answers.

The `portal-slack` service (defined in `deploy/portal-5/docker-compose.yml`) gets
the three tokens as environment variables and launches
`python -m portal_channels.slack.bot`. Because the app connects over Socket Mode,
the bot opens an outbound WebSocket and needs no public webhook or ingress.
`SLACK_DEFAULT_WORKSPACE` selects the routing workspace for direct messages and
for channels that have no explicit mapping.

### Why

Socket Mode is what lets the whole integration stay behind the firewall: the
app-level token drives an outbound WebSocket from the container, so no inbound
path has to be exposed. The two-token design — bot token for the app, app token
for the socket — is why `up-slack` validates both before launching: a bot that
is only half-configured fails immediately instead of silently dropping every
mention.
<!-- /WIKI:GENERATED -->

---

### Core models (pulled automatically on first run, ~4 GB)

<!-- WIKI:GENERATED unit=unit-readme-core-models-pulled-automatically-on-first-run-4-gb -->
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

#### Why

A fresh machine must reach a working minimum before any operator-time download
runs: a general chat model, a router standby and an embedding model guarantee
that routing, conversation and RAG all function on first boot. Pulling them in the
compose init container keeps the first-run pull inside the normal `up` path so the
stack is never brought up half-configured.
<!-- /WIKI:GENERATED -->

---

### Specialized models (pulled with `./launch.sh pull-models`, ~60–100 GB total)

<!-- WIKI:GENERATED unit=unit-readme-specialized-models-pulled-with-launch-sh-pull-models-60-100-gb-total -->
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

#### Why

Cataloging specialized models in `config/backends.yaml` rather than hardcoding
them in the router keeps one authoritative list for routing, admission and pull
targets, so adding or retiring a lane is a config change, not a code change. The
split between the pull-models registry and the update default set reflects two
workflows: a deliberate operator pull versus a full upgrade that refreshes the
whole fleet.
<!-- /WIKI:GENERATED -->

---

### MLX models (Apple Silicon, retained for audio/embedding/reranker only — chat inference is Ollama-only)

<!-- WIKI:GENERATED unit=unit-readme-mlx-models-apple-silicon-retained-for-audio-embedding-reranker-only-chat-inference-is-ollama-only -->
MLX survives in four non-chat runtimes, each started by its own launcher:

- **Speech:** the host-native MLX speech server on port 8918 (`scripts/mlx-speech.py`,
  started by `start-speech` in `scripts/lib/services.sh`) — Kokoro + Higgs Audio v2
  voice clone + Qwen3-TTS/ASR.
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

#### Why

Retiring the MLX proxy removed a second chat-serving stack while keeping MLX where
Ollama has no equivalent: Ollama does not host Kokoro/Qwen3 TTS, diarized
transcription, sentence embeddings or reranking. Those four runtimes stay host-native on
Apple Silicon because the MPS path is substantially faster than the equivalent
Docker images, and none of them touch the router.
<!-- /WIKI:GENERATED -->

---

### Image / video generation (MLX-native, host layer)

<!-- WIKI:GENERATED unit=unit-readme-image-video-generation-mlx-native-host-layer -->
Image generation is the **MFLUX MCP** (`portal/modules/media/tools/mflux_mcp.py`,
port 8933) — a headless wrapper over the `mflux-generate` CLI (MLX-native FLUX
for Apple Silicon). `./launch.sh install-mflux` sets it up as a launchd service;
`./launch.sh pull-mflux-models` pre-pulls the weights (FLUX.1-schnell full
weights are ~34 GB one-time). The `generate_image` tool takes a `model` arg:
`schnell` (fast default), `klein` (FLUX.2, higher quality), `qwen-image` (best
for legible text in the image), `dev`. `edit_image` does instruction editing
(`qwen-image-edit`) or img2img. Measured MLX peaks: `schnell` ~14.5 GB, `klein`
~18 GB.

Video generation is the **video-mlx MCP** (`video_mlx_mcp.py`, port 8935), a
wrapper over `ltx-2-mlx` (pure-MLX LTX-2.3). It is behind the `video` M7 module
— **off by default, shipped enabled** — installed with
`./launch.sh install-video-mlx` (and toggled with `portal module enable` /
`disable video`). Clips are preview-grade and practically capped at
~4–6 seconds on this hardware.

Both replaced a ComfyUI-based path removed in `TASK_IMAGE_VIDEO_OVERHAUL_V1`:
Metal has no FP8, so ComfyUI's standard quantized checkpoints never ran here.

#### Why

Image and video generation run on the host MLX layer alongside
speech/transcription/embeddings — one accelerator path, no Docker-to-Metal
bridge, and each is its own toggleable module so a tight-footprint box can
disable the heavy `video` surface (or image generation) without losing the
audio media. Weights download on demand via `install-*` / `pull-*` so the
operator pays the cost only for the models actually used.
<!-- /WIKI:GENERATED -->

---

## Speech (Text-to-Speech & Speech-to-Text)

<!-- WIKI:GENERATED unit=unit-readme-speech-text-to-speech-speech-to-text -->
Portal 5 includes a native MLX speech server on Apple Silicon
(`scripts/mlx-speech.py`, port `MLX_SPEECH_PORT` default 8918) with three
backends:

- **Kokoro TTS** — the `mlx-community/Kokoro-82M-bf16` model via mlx-audio; voices
  are selected by the Kokoro naming prefix (`af_`, `am_`, `bf_`, `bm_`, `jf_`,
  `jm_`, `zf_`, `zm_`), e.g. `af_heart`, `bm_george`.
- **Higgs Audio v2** (`mlx-community/higgs-audio-v2-3B-mlx-q8`, Boson AI) — voice cloning.
  One-off via `voice="clone:/path/to/ref.wav"`, or register a reusable trainer voice with
  the `register_voice` tool / `POST /v1/voices` (name + reference clip + transcript) and then
  use `voice="trainer:<name>"`. Zero-shot from a 10-15s clip; not a fine-tune, so fidelity
  tracks reference-clip quality. No provenance watermark. `MLX_CLONE_MODEL` swaps the engine
  (e.g. `mlx-community/chatterbox-fp16`).
- **Qwen3-TTS CustomVoice / VoiceDesign** — preset speakers and voice-from-description
  (retained; not used for cloning).
- **Qwen3-ASR** — speech-to-text via `mlx_audio.stt`.

Manage it with the `start-speech` and `stop-speech` subcommands of `launch.sh`
(`scripts/lib/services.sh`): `start-speech` verifies `mlx_audio` is installed,
checks the PID file at `/tmp/portal-mlx-speech.pid`, and launches
`scripts/mlx-speech.py` with nohup, logging to `~/.portal5/logs/mlx-speech.log`;
`stop-speech` kills the recorded PID. Models load lazily on the first TTS or ASR
request.

### Why

TTS and ASR are latency-sensitive and run continuously, so the speech server is a
host-native process on Metal rather than a Docker container: the MPS path keeps
synthesis fast and the models are loaded once and reused. The PID-file plus
`start-speech`/`stop-speech` pairing gives an operator lifecycle control without a
container orchestrator, and Kokoro voices are addressed by the same prefix scheme
the Kokoro model uses.
<!-- /WIKI:GENERATED -->

---

## Troubleshooting

<!-- WIKI:HUMAN-OWNED reason="section framing — why the list is short and which failure it does not cover" -->
This covers first-run failures, which are nearly always one of four things: an unhealthy
container, a full disk, a backend still loading, or a taken port. A model that answers badly is
a different problem — that is a workspace or model-fit question, and `docs/USER_GUIDE.md` and
`KNOWN_LIMITATIONS.md` are the places for it.
<!-- /WIKI:HUMAN-OWNED -->

<!-- WIKI:GENERATED unit=unit-readme-troubleshooting -->
**Services not starting:**
```bash
./launch.sh status          # See which services failed
docker compose -f deploy/portal-5/docker-compose.yml logs <service-name>
```

`status` runs `_cmd_status` (`scripts/lib/util.sh`), which reads container health
from `docker compose ps --format json` and renders a table over Open WebUI, the
pipeline, SearXNG, Prometheus, Grafana and the MCP servers, marking each healthy,
running, starting or failed. `logs` tails `docker compose logs -f <service>`
(default `portal-pipeline`).

**Out of disk space:**
```bash
docker system df            # See Docker disk usage
./launch.sh clean           # Stop services and remove the Open WebUI data volume
```

`clean` stops the stack and removes only the `open-webui-data` volume, explicitly
keeping the Ollama models volume — a clean wipes chat history and settings but
does not force the weights to re-download. The disk check in `_check_hardware`
warns below 20 GB free and suggests `docker system prune -a`; below 50 GB it
notes more is needed for the full catalog. Because the core models plus the FLUX
checkpoint (~12 GB) dominate a first download, a tight disk makes `up` or the
pulls fail mid-transfer — free space, then re-run `./launch.sh up`.

**Ollama still loading:**
```bash
./launch.sh pull-models     # Ensure at least one model is pulled
```

On a cold start `_ensure_native_services` restarts Ollama — `launchctl kickstart
-k system/com.portal5.ollama` on Apple Silicon (the pinned `com.portal5.ollama`
install, not Homebrew), `nohup ollama serve` on Linux — then polls
`http://localhost:11434/api/tags` for up to 10 seconds. The router only sees a
backend once its models finish loading, so a request fired immediately after boot
can hit an empty list; wait for Ollama to answer and retry.

**Port already in use:** `_check_ports` probes every reserved port before `up`
and, for a busy one, prints the owning process and a `kill` hint before exiting
1. Stop the conflicting process, run `./launch.sh down` if the owner is an old
Portal 5 stack, or override the port in `.env` (for example
`DOCUMENTS_HOST_PORT=9013`), then re-run `./launch.sh up`.

### Why

Nearly every first-run failure is one of four things — an unhealthy container, an
exhausted disk, a backend that has not finished loading, or a reserved port
already taken — so the troubleshooting surface is deliberately small and each
entry pairs the diagnostic command with the one safe remediation. `status` and
`_check_ports` name the specific offender rather than making the operator read
compose output, and `clean` is scoped to the data that is safe to lose because
nuking the Ollama volume would cost hours of re-downloads.
<!-- /WIKI:GENERATED -->

---

### Required Environment Variables

<!-- WIKI:GENERATED unit=unit-readme-required-environment-variables -->
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

#### Why

A single shared API key keeps the pipeline, the chat UI and the channel bots
authenticated against one credential instead of several hand-managed secrets, and
generating it automatically in `up` means a first-time operator never has to
produce or paste a random value. The remaining secrets are likewise auto-generated
so `.env` is usable the moment it is created.
<!-- /WIKI:GENERATED -->

---

### Network Exposure

<!-- WIKI:GENERATED unit=unit-readme-network-exposure -->
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

#### Why

The asymmetry is deliberate: the pipeline must be reachable from LAN clients and
channel bots, so it exposes 0.0.0.0 and leans on the API key; the chat UI has no
key of its own and should not be silently world-visible, so it defaults to
loopback unless the operator opts into remote access. Firewall guidance applies to
a LAN, not the public internet.
<!-- /WIKI:GENERATED -->

---

## Coding Tool Integration (Claude Code / opencode)

<!-- WIKI:HUMAN-OWNED reason="section framing — why a local stack bothers to speak the coding-agent protocols" -->
Claude Code and opencode expect an OpenAI-compatible endpoint, and the Pipeline is one, so a
local model can back an agentic coding harness with no cloud key. It is the same routing and the
same toolset the browser tab uses, addressed from a terminal instead.
<!-- /WIKI:HUMAN-OWNED -->

<!-- WIKI:GENERATED unit=unit-readme-coding-tool-integration-claude-code-opencode -->
Portal 5 ships first-class support for AI coding assistants. Two repo-root config
files activate automatically when either tool opens this project:

- **`.mcp.json`** — currently 29 MCP servers (count with `python3 -c "import json; print(len(json.load(open('.mcp.json'))['mcpServers']))"`): filesystem, git, docker, fetch, portal-sandbox (execute_bash), portal-pipeline (FastContext code explorer + stack introspection), plus the other portal-* tool servers.
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

### Why

Coding assistants that default to cloud APIs would stream the repository's source
and the operator's key budget off the machine, defeating the local-first contract.
Shipping `.mcp.json` and `opencode.jsonc` in the repo makes both tools adopt the
pipeline as their tool and model endpoint with zero setup, and the same
`PIPELINE_API_KEY` that gates the chat pipeline also gates the agents, so a single
credential controls the whole surface.
<!-- /WIKI:GENERATED -->

---

## Documentation

<!-- WIKI:GENERATED unit=unit-readme-documentation -->
The operator-facing manual is a set of reference docs at the repo root and under
`docs/`, all of which exist as tracked files:

| Guide | Contents |
|---|---|
| [MCP Dev Tooling](docs/MCP_DEV_TOOLING.md) | Claude Code & opencode integration, FastContext explorer, workflow examples |
| [How-To Guide](docs/HOWTO.md) | Working examples for every feature, including remote API access |
| [User Guide](docs/USER_GUIDE.md) | How to use workspaces, tools, personas |
| [Admin Guide](docs/ADMIN_GUIDE.md) | User management, configuration, security |
| [Alerts & Notifications](docs/ALERTS.md) | Operational alerts and daily summaries |
| [Cluster Scaling](docs/CLUSTER_SCALE.md) | Running multiple Ollama instances |
| [Agent Loop](docs/AGENT_LOOP.md) | Platform-core bounded agent loop (`portal/platform/agent/`), the `portal agent` CLI |
| [Backup & Restore](docs/BACKUP_RESTORE.md) | Data backup procedures |
| [Known Issues](KNOWN_ISSUES.md) | Current limitations and workarounds |

Most of these guides are generated shells whose substance lives in
`portal_wiki/canonical/` fact-units and is rendered into `<!-- WIKI:GENERATED -->`
blocks, so the docs stay current through `./launch.sh sync-config` rather than
hand edits.

### Why

The documentation is the operator contract, not a summary after the fact: the
guides cover exactly the surfaces the platform exposes (tooling, accounts, alerts,
media, clustering), so a new operator can find the answer for a feature without
reading source. Coupling the generated guides to wiki units means a doc cannot
silently drift from the config that produces it.
<!-- /WIKI:GENERATED -->

---

### Acceptance Testing

<!-- WIKI:GENERATED unit=unit-readme-acceptance-testing -->
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

#### Why

The acceptance gate exists because unit tests deliberately mock Ollama and the HTTP
surface, so a mocked suite can pass while the deployed stack rejects requests,
tools are missing, or container ports are wrong. Running against the live stack
catches those contract breaks before a push. The section-per-file layout keeps each
area (services, routing, personas, security MCP) independently re-runnable during
debugging instead of forcing one monolithic run.
<!-- /WIKI:GENERATED -->

---

### Unit Test CI

<!-- WIKI:GENERATED unit=unit-readme-unit-test-ci -->
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

#### Why

Unit tests must pass with no network and no live services, so the CI gate runs in
a clean environment where local state cannot mask a broken import. The
pre-commit hooks move the same checks earlier, catching style, freshness and
test failures before the commit is made, while the heavier system validation stays
at push time to keep the per-commit cost low.
<!-- /WIKI:GENERATED -->

---

## Architecture

<!-- WIKI:HUMAN-OWNED reason="section framing — the one load-bearing idea in the diagram below" -->
One thing to take from the diagram: the Pipeline is the only OpenAI-compatible endpoint Open
WebUI ever sees, it holds no conversation state, and inference is a single tier. That is what
lets there be one model catalog and one GPU-memory budget to reason about, rather than two
model-serving stacks competing for the same RAM.
<!-- /WIKI:HUMAN-OWNED -->

<!-- WIKI:GENERATED unit=unit-readme-architecture -->
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
                        │ :11434  │ │ :8912–:8935      │
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

### Why

Keeping a single inference tier on Ollama avoids running a second model-serving
stack against the same GPU memory; MLX survives only where Ollama has no
equivalent runtime — audio synthesis, diarization, embeddings and reranking. One
tier also means one model catalog (`config/backends.yaml`) and one pull path for
operators, which is why the retained MLX runtimes are explicitly non-chat.
<!-- /WIKI:GENERATED -->

---

## Why this exists

<!-- WIKI:HUMAN-OWNED reason="ancestry and intent — the project's own account of where it came from, which no unit can derive" -->
Portal 5 began as `pocketportal`, a Telegram bot: one private front door to a set of local
models, with a routing table that ran from a tiny SmallThinker-270M classifier up to a Qwen-32B,
aimed at an Apple Silicon Mac Mini. The interface later moved to Open WebUI and the model tiers
were replaced, but the shape held — one door, many local models, the right one chosen for you.

`[OPERATOR: verify or replace]` Why it started: the motive — a specific task a hosted assistant
could not be trusted with, or a standing objection to filing your work with someone else's
cloud.

`[OPERATOR: verify or replace]` How it grew: a task showed up that the local stack could not do,
so the stack grew a capability for it — security work, then compliance, then documents, voice,
CAD — which is why the module list looks the way it does.

`[OPERATOR: verify or replace]` What was retired: the things removed for not earning their keep
— name them if the claim should land (for example the MLX inference proxy, or the ComfyUI
generation path).

Built for privacy, autonomy, and control — and to be good enough that choosing them costs you
nothing.
<!-- /WIKI:HUMAN-OWNED -->

---

## License

<!-- WIKI:GENERATED unit=unit-readme-license -->
Portal 5 is released under the MIT License — see [LICENSE](LICENSE) at the repo
root for the full text. MIT grants permission to use, copy, modify and distribute
the code for any purpose, including commercial use, subject to preserving the
copyright and permission notice.

### Why

MIT was chosen because the project is a local-first enhancement layer on top of
Open WebUI, and permissive licensing removes friction for operators who want to
fork or vendor it internally. The individual GGUF models and runtimes it
orchestrates carry their own licenses (for example gated HuggingFace repos
require `HF_TOKEN`), which are separate from the project license.
<!-- /WIKI:GENERATED -->

---
