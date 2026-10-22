# Portal 5 — Local AI Platform for Apple Silicon

Portal 5 is an enhancement layer over Open WebUI that turns a single Apple Silicon Mac
into a private, fully local AI platform: chat, documents, code, research, security,
compliance, media and more, launched with one command and running entirely on your
hardware. It is for operators and developers who want the capability of a hosted AI
stack — specialist workspaces, tools, memory, monitoring — without sending a byte to a
cloud provider or renting inference by the token.

The pipeline is the product. Talking to Ollama directly gives you a model; Portal's
Pipeline gives you a platform: it picks the model per workspace, admits loads onto a
shared memory pool, swaps models between two engines, wires in tool servers, and
surfaces all of it as metrics — so any workspace answers on one 64 GB machine and you
never think about what is resident.

## How it works

```
Open WebUI :8080  ──►  Portal Pipeline :9099  ──►  Ollama (GGUF)  ─┐
                                     │            oMLX (MLX/Metal) ┴─  one unified
                                     │                                 memory pool
                                     └─►  MCP tool servers (documents, code sandbox,
                                          research, memory, RAG, security, media …)
```

**Open WebUI** is the chat surface — accounts, history, retrieval, the model picker.
Every request it serves flows through the **Pipeline**, which owns the hard parts:

- **Workspaces and routing.** A workspace pins a model, a toolset and a context budget;
  you pick an intent and it sets all three. The `auto` workspace classifies intent with
  a local router model (weighted keywords as fallback) and hands specialist work to the
  lane that owns it.
- **The load guard.** One admission control for both engines over the single
  unified-memory pool: it counts in-flight requests per engine and model, serialises
  cold loads behind a host-wide lock, frees idle models before refusing, waits inside
  the request's own budget, and refuses with HTTP 507 only when waiting cannot help.
  Resident and warm models never wait. Tuning and internals:
  `docs/ADMIN_GUIDE.md` → *Inference Health Monitoring*.
- **Two engines, no dead ends.** Ollama and oMLX are one candidate ladder, not two
  stacks. A model an oMLX seat is not currently serving falls through to the next
  candidate — usually the Ollama tag of the same weights — and a turn no candidate can
  serve returns an explicit no-answer, never a dead error.
- **Hot-seat placement.** Before admitting a second model onto the oMLX engine, the
  router checks whether the seat holds a warm prefix cache and steers the request to an
  alternative candidate when one exists — protecting first-token latency without ever
  denying service.
- **Metrics and dashboards.** Routing decisions, load-guard admissions, waits, unloads
  and refusals are Prometheus counters and gauges, charted by the Grafana dashboards in
  `config/grafana/dashboards/` (including *Model Management (Load Guard)*).

Go deeper without leaving the authoritative sources: `docs/ADMIN_GUIDE.md` for router
configuration and load-guard tuning, `KNOWN_LIMITATIONS.md` for what does not work yet
and why, `CLAUDE.md` for the ground rules if you want to change the code.

## Modules at a glance

Capabilities are modules you can toggle (`portal module enable <name>`). The table is
generated from `config/portal.yaml` (`modules:` and `mcp_fleet:`) — ports and the
server list live there, not here.

| Module | Default | What it gives a chat | Pipeline-facing tool servers |
|---|---|---|---|
| general | on | Everyday chat, math, routing | — |
| coding | on | Code generation, repo work | `execution` code sandbox :8914 |
| documents | on | Parsing, extraction, OCR | `documents` :8913 |
| research | on | Retrieval, RAG, web research | `rag` :8921, `research` :8922 |
| media | on | Speech, transcription, TTS | `whisper` :8915, `tts` :8916 |
| security | on | Blue/red lanes, MITRE, detections | `security` :8919, `mitre` :8929, `detections` :8932, `review` :8943 |
| compliance | on | NERC CIP reasoning, control registers | `compliance` :8937 |
| data | on | Analytics, dataframes, charting | `data` :8939 |
| cad | on | Parametric CAD, printability checks | `cad_render` :8926 |
| icsot | on | ICS/OT protocol analysis | `icsot` :8936 |
| vulnintel | on | Vulnerability intelligence | `vulnintel` :8934 |
| detection | on | Detection-as-code | `detection` :8938 |
| netforensics | on | Network forensics | `netforensics` :8941 |
| image | off | MFLUX image generation (MLX) | `mflux` :8933 |
| music | off | Music generation (MiniMax) | `music-minimax` :8912 |
| video | off | LTX-2 video generation (MLX) | `video_mlx` :8935 |
| eval | off | Benchmark apparatus, bench workspaces | — |
| orchestration | off | Local verified task arm | — |
| security_redteam | off | Offensive-generation variants (campaign-scoped) | — |

Always-on platform services ride alongside these: `memory` :8920 (temporal knowledge
graph), `pipeline` :8928 (stack introspection), `wiki` :8931 (canonical knowledge),
`mlx_transcribe` :8924, plus host-native embedding and reranking services. A second set
of servers — filesystem, fetch, git, serena, docker, context7, browser, proxmox,
binresearch — serves coding agents over IDE integrations rather than the chat pipeline.

## Quick start

Requirements:

- macOS on Apple Silicon (M-series)
- Docker Desktop, running
- Ollama (`./launch.sh install-ollama` installs it natively under launchd)
- 16 GB RAM minimum (32 GB+ for the full catalog; the design target is one
  64 GB machine)
- 20 GB free disk minimum for the core stack; model catalog grows from there

```bash
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
./launch.sh up
```

`./launch.sh` with no arguments means `up`. The first run creates `.env` from
`.env.example`, generates secrets, checks hardware and fails fast with a readable
reason if something is missing, starts the compose stack and the host-native services,
and pulls the core models. Then:

1. Open `http://localhost:8080` and sign in — credentials are in `.env`.
2. Pick a workspace and ask a real question.
3. Optional, later: `./launch.sh pull-models` fetches the full model catalog.

To verify an install:

```bash
uv run python scripts/validate_system.py    # full check suite; exits zero when healthy
./scripts/smoke_stream.sh                   # live streaming check against the running stack
```

Everyday operations: `./launch.sh status`, `./launch.sh logs`, `./launch.sh down`,
`./launch.sh backup`. The full command list is in the `case` block of `launch.sh`.

## Configuration

- `.env.example` — every environment knob, commented. `up` copies it to `.env` and
  fills in secrets; never commit `.env`.
- `config/portal.yaml` — the source of truth: workspaces, modules and the MCP fleet.
- `config/backends.yaml` — the model catalog and memory budgets. Only file an operator
  edits to scale beyond one machine.
- `config/personas/` — one YAML per persona: voice and constraints layered over a
  workspace.
- Derived files (`workspace_routing` in `config/backends.yaml`, Open WebUI imports,
  `config/modules.generated.yaml`) are regenerated — edit the sources, then run
  `portal sync-config`.

The operator CLI inspects and drives all of it: `portal config show` for the current
runtime inventory, `portal module enable <name>`, `portal workspace status`,
`portal models pull`, `portal docs build` when a release needs generated docs refreshed.

## Privacy and security

- Inference, memory and tools run locally; the chat path has no cloud calls. The only
  outbound traffic is model downloads from the Ollama and Hugging Face registries (and
  `HF_TOKEN` authentication if you use gated repos).
- One generated key (`PIPELINE_API_KEY`) gates the pipeline, UI and bots. The chat UI
  binds to loopback unless you opt into LAN exposure.
- Security and offensive-capability workspaces exist but are user-selected: the `auto`
  router declines security work and names the workspace to pick rather than routing it
  silently.
- Read `KNOWN_LIMITATIONS.md` before trusting a capability, and
  `docs/ADMIN_GUIDE.md` → *Security Notes* before exposing anything beyond loopback.

MIT licensed — see `LICENSE`.

## Documentation

| Doc | What it covers |
|---|---|
| `docs/USER_GUIDE.md` | Daily use: workspaces, personas, channels |
| `docs/HOWTO.md` | Task recipes |
| `docs/ADMIN_GUIDE.md` | Accounts, model management, load guard, router config, backup |
| `docs/ALERTS.md` | Monitoring and thresholds |
| `docs/BACKUP_RESTORE.md` | Snapshot and recovery |
| `docs/CLUSTER_SCALE.md` | Scaling beyond one node |
| `docs/MCP_DEV_TOOLING.md` | Developing and debugging MCP tool servers |
| `KNOWN_LIMITATIONS.md` | The honest answers: open limitations and refused models |
| `CLAUDE.md` | Ground rules for changing the code |
| `ROADMAP.md` | Forward-looking only |
