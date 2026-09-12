# 🤖 Portal 5 — Local AI Platform

**Privacy-First, Fully Local AI Platform for Apple Silicon**

This is a **complete, running** platform containing everything needed to operate a production-grade private AI stack on your own hardware.

---

## 📦 What's in This Repository

```
portal-5/
├── 📄 README.md                          # This file - START HERE
├── 📄 CLAUDE.md                          # Agent entry point + ground rules
├── 📄 KNOWN_LIMITATIONS.md               # Where the honest answers live
├── 📄 P5_ROADMAP.md                      # Forward-looking only
├── 🚀 launch.sh                          # One command for everything
│
├── 📁 config/                            # Single source of truth
│   ├── portal.yaml                      # ✅ Workspaces + MCP fleet (authoritative)
│   ├── backends.yaml                    # ✅ Model catalog
│   ├── personas/                        # ✅ 122 persona definitions
│   └── modules.generated.yaml           # ⚠️ Generated - do not edit
│
├── 📁 portal/                            # The platform
│   ├── platform/                        # Contracts: agent loop, inference, wiki
│   │   ├── agent/                       # ✅ CapabilityProvider / Executor
│   │   ├── inference/                   # ✅ Pipeline + routing + CLI
│   │   ├── retrieval/                   # ✅ RAG composition
│   │   ├── memory/                      # ✅ Temporal knowledge graph
│   │   ├── mcp_host/                    # ✅ Fleet supervision
│   │   └── wiki/                        # ✅ Canonical docs engine
│   │
│   └── modules/                         # Implementations (16 domains)
│       ├── general/  coding/  security/  compliance/
│       ├── documents/  research/  media/  image/
│       ├── data/  cad/  icsot/  vulnintel/
│       ├── detection/  netforensics/
│       ├── eval/                        # ⚠️ OFF by default (bench apparatus)
│       └── video/                       # ⚠️ OFF by default (20-24GB, thermal)
│
├── 📁 portal_mcp/                        # 33 MCP tool servers (8910-8941)
├── 📁 portal_channels/                   # Telegram + Slack transports
├── 📁 portal_wiki/                       # Canonical documentation units
│
├── 📁 docs/                              # Operator documentation
│   ├── USER_GUIDE.md                    # Daily use
│   ├── HOWTO.md                         # Task recipes
│   ├── ADMIN_GUIDE.md                   # Operations
│   ├── PERFORMANCE.md                   # Benchmark harness
│   ├── ALERTS.md                        # Monitoring
│   └── BACKUP_RESTORE.md                # Snapshot + recovery
│
├── 📁 scripts/                           # Validation + tooling
│   ├── validate_system.py               # ✅ 213 checks
│   └── smoke_stream.sh                  # ✅ Live streaming gate
│
├── 📁 tests/                             # Unit + benchmark suites
└── 📁 deploy/                            # Compose stack + launchd plists
```

---

## 🎯 System Capabilities

### Capability Domains (16 modules)

#### Enabled by Default (14)
1. **general** — Everyday chat, math, routing fallback
2. **coding** — Code generation, repo work, sandboxed execution
3. **security** — Red/blue/purple lanes, MITRE, detections, Proxmox lab
4. **compliance** — NERC CIP reasoning, control registers
5. **documents** — Parsing, extraction, OCR, structured output
6. **research** — Retrieval, reranking, browser, web research
7. **media** — Speech, transcription, music
8. **image** — MFLUX image generation, MLX-native
9. **data** — Analytics, dataframes, charting
10. **cad** — Parametric CAD, FDM printability checks
11. **icsot** — ICS/OT protocol analysis
12. **vulnintel** — Vulnerability intelligence
13. **detection** — Detection-as-code
14. **netforensics** — Network forensics

#### Off by Default (2)
- ⚠️ **video** — LTX-2 MLX video generation (20-24GB working set, thermally punishing)
- ⚠️ **eval** — Benchmark and test apparatus (apparatus is not production capability)

Flip either: `portal module enable video`

### Routing Destinations (46 workspaces)

Every workspace pins a **model + toolset + context budget**. You pick an intent; it sets all three.

#### Functional — in your dropdown (25)
```
general      12   auto, auto-daily, auto-math, auto-council, auto-bigfix,
                  auto-nemotron, auto-general-uncensored …
media         3   auto-audio, auto-creative, auto-music
documents     2   auto-documents, auto-extract-uncensored
research      2   auto-data, auto-research
security      1   auto-security
coding        1   auto-coding
compliance    1   auto-compliance
image         1   auto-image
cad           1   auto-cad
video         1   auto-video
```

#### Benchmark — behind the eval module (57)
Never in daily use. Same toolset and scaffolding as a functional lane, so a TPS or quality delta is attributable to model weights alone.

### Tool Servers (33 MCP servers, ports 8910-8941)

| Servers | Module | Pipeline | IDE |
|---|---|---|---|
| `documents` `execution` `rag` `research` `memory` | core | ✅ | ✅ |
| `security` `mitre` `detections` `vulnintel` `icsot` `detection` | security | ✅ | ✅ |
| `whisper` `tts` `mlx_transcribe` `music-minimax` | media | ✅ | ✅ |
| `mflux` `video_mlx` `cad_render` | generation | ✅ | ❌ |
| `wiki` `pipeline` `data` `netforensics` `compliance` | platform | ✅ | ✅ |
| `filesystem` `fetch` `git` `serena` `docker` `context7` | dev | ❌ | ✅ |
| `browser` `reranker` `proxmox` `binresearch` | specialist | ❌ | ✅ |

### Personas (122)
Voice and constraints layered over a workspace. The workspace picks the model; the persona shapes the answer.

### Channels (3)
- ✅ **Open WebUI** — browser, port 8080, the primary surface
- ✅ **Telegram** — set a token, one command
- ✅ **Slack** — Socket Mode, stays behind your firewall

### Total Capabilities
- **16 capability domains** (14 enabled)
- **46 workspaces** (25 functional, 21 benchmark)
- **33 MCP tool servers** (ports 8910-8941)
- **122 personas**
- **3 channels**
- **213 validation checks**
- **= everything runs on your hardware**

---

## ⚡ Quick Start

### Prerequisites
- macOS with Apple Silicon (M1/M2/M3/M4) — M4 Pro or better recommended
- 16GB+ RAM (64GB recommended, 128GB for concurrent large models)
- 100GB+ free disk (core models ~4GB, full catalog 60-100GB)
- Docker Desktop
- Ollama

### 1. Clone
```bash
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
```

### 2. Launch
```bash
./launch.sh up
```

This will:
- Generate `.env` secrets (API key, admin credentials)
- Run hardware checks (RAM, disk) — fails fast with a readable reason
- Start the compose stack (Open WebUI, pipeline, MCP fleet)
- Register host-native MLX services with launchd
- Pull core models (~4GB) in the init container

### 3. Sign In
```
http://localhost:8080
```
Credentials are already in `.env`. You never hand-edit a config to get started.

### 4. Pull the Full Catalog (optional)
```bash
./launch.sh pull-models          # 30-90 min, 60-100GB
```

### 5. Verify
```bash
uv run python scripts/validate_system.py
./scripts/smoke_stream.sh
```

**Total Time:** 10-15 minutes to a working stack. Add an hour for the full catalog.

---

## 📖 Full Documentation

### Operator Guides
1. **docs/USER_GUIDE.md** — Daily use, workspaces, personas (20 min)
2. **docs/HOWTO.md** — Task recipes (30 min)
3. **docs/ADMIN_GUIDE.md** — Operations, accounts, backup (45 min)
4. **docs/PERFORMANCE.md** — Benchmark harness (15 min)
5. **docs/ALERTS.md** — Monitoring and thresholds (15 min)
6. **docs/BACKUP_RESTORE.md** — Snapshot and recovery (20 min)

### Before You Change Anything
- **CLAUDE.md** — Agent entry point, 13 ground rules (20 min)
- **KNOWN_LIMITATIONS.md** — Where the honest answers live (long, on purpose)
- **P5_ROADMAP.md** — Forward-looking only (10 min)

---

## 🚀 Deployment Options

### Option 1: Core Only (15 min)
- Core models (~4GB)
- Open WebUI, pipeline, MCP fleet
- **Recommended for first run**

Run: `./launch.sh up`

### Option 2: Full Catalog (1-2 hours)
- Everything from Option 1
- Specialized models (60-100GB)
- All 25 functional workspaces live
- **Recommended for most operators**

Run: `./launch.sh up && ./launch.sh pull-models`

### Option 3: Complete (half a day)
- Everything from Option 2
- Telegram and/or Slack channels
- Speech services, image generation
- `video` and `eval` modules enabled
- **Recommended for power users**

Run: add `up-telegram`, `up-slack`, `start-speech`, `install-mflux`, `portal module enable video`

---

## 🔧 Configuration

### Minimal (.env — auto-generated by `up`)
```bash
PIPELINE_API_KEY=<generated>            # gates pipeline, UI and bots
WEBUI_SECRET_KEY=<generated>
OLLAMA_BASE_URL=http://localhost:11434
```

### With Channels (.env additions)
```bash
TELEGRAM_BOT_TOKEN=your_token           # from @BotFather
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_APP_TOKEN=xapp-your-token         # Socket Mode
```

### With Gated Models (.env additions)
```bash
HF_TOKEN=hf_your_token                  # only for gated HuggingFace repos
```

### Remote Access (optional)
```bash
WEBUI_BIND=0.0.0.0                      # default is loopback - opt in deliberately
```

---

## 🎓 Architecture Overview

### Core Components
1. **Open WebUI** — Auth, chat history, RAG, the browser surface
2. **Portal Pipeline** — Routing, model selection, tool dispatch
3. **Ollama** — All chat inference, single tier
4. **MCP Fleet** — 33 independent tool servers, own ports, own lifecycles
5. **MLX Host Layer** — Speech, transcription, embeddings, reranking, image, video

### Data Flow
```
Open WebUI :8080  ─┐
Telegram          ─┼─►  Portal Pipeline :9099  ─►  Ollama :11434
Slack             ─┘            │
                                ├─►  MCP fleet :8910-8941
                                └─►  MLX host layer (Metal)
```

### The Five Kinds
- **Module** — a capability domain you can switch off wholesale
- **Workspace** — a routing destination: model + toolset + context budget
- **Persona** — voice and constraints over a workspace
- **MCP Server** — an independent tool-serving process
- **Channel** — a transport carrying messages to the pipeline

### Single Inference Tier
Ollama serves all chat. MLX survives only where Ollama has no equivalent — speech synthesis, diarized transcription, embeddings, reranking, image and video. One tier means one model catalog and one pull path.

### Source of Truth
`config/portal.yaml` declares workspaces and the MCP fleet. `sync_config` regenerates everything derived from it. Editing a generated file is a change that gets overwritten.

---

## 📊 Performance Expectations

### M4 Pro Mac Mini (64GB)
- **Simple queries:** 1-3s
- **Code generation:** 3-8s
- **Multi-step tool tasks:** 5-15s
- **Tokens/sec:** ⚠️ not benchmarked into this README yet

```bash
# Produce your own numbers:
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace auto --runs 3
```

### Memory Usage
- **Baseline:** 4-6GB (pipeline + MCP fleet + Open WebUI)
- **7B model:** +6GB
- **32B model:** +24GB
- **video module:** +20-24GB — off by default for a reason

### Concurrent Models
With 64GB, plan for one large model resident at a time. The router evicts when two large models are asked for at once.

---

## 🆘 Troubleshooting

### Common Issues

**"Container unhealthy"**
```bash
./launch.sh status              # names the specific offender
./launch.sh logs
```

**"No space left on device"**
```bash
./launch.sh clean               # scoped to data that is safe to lose
./launch.sh up
```

**"Connection refused" / model not loading**
```bash
ollama list                     # wait for Ollama to finish loading, then retry
```

**"Port already in use"**
```bash
./launch.sh status              # _check_ports names who has it
# Stop the conflicting service, then ./launch.sh up
```

**More help:** `docs/HOWTO.md` and `KNOWN_LIMITATIONS.md`

---

## 🔐 Security

### Privacy Guarantees
- ✅ 100% local inference — prompts and responses never leave
- ✅ Zero cloud API calls in the chat path
- ✅ No accounts, no per-token meter, no vendor lock
- ✅ Single credential (`PIPELINE_API_KEY`) gates pipeline, UI and bots
- ✅ Chat UI defaults to loopback; pipeline binds LAN behind the key

### What Does Reach Out
- ⚠️ Model downloads (HuggingFace / Ollama registries, standard HTTP metadata)
- ⚠️ `HF_TOKEN` authentication, if you configured gated models

Nothing else.

### Best Practices
1. Never commit `.env`
2. Keep `WEBUI_BIND` on loopback unless you need LAN access
3. Treat `PIPELINE_API_KEY` as the key to everything — it is
4. Run `validate_system.py` before trusting a change
5. Read `KNOWN_LIMITATIONS.md` before trusting a capability

---

## 🎯 Success Criteria

Your install succeeds when:
- ✅ You sign in at `http://localhost:8080`
- ✅ The model dropdown lists more than one preset
- ✅ A plain question answers coherently in a few seconds
- ✅ A question needing a tool **visibly uses one** — not describes one
- ✅ `./scripts/smoke_stream.sh` streams tokens rather than one block
- ✅ `uv run python scripts/validate_system.py` exits zero
- ✅ Grafana at `http://localhost:3000` shows request metrics

**If the last two pass and the first five don't:** the stack is healthy and the config is wrong. Go to Troubleshooting — don't reinstall.

---

## 🌟 What Makes This Special

### vs Cloud AI Assistants
- ❌ **Them:** Your control network, your compliance gaps, your unshipped code — on their servers
- ✅ **You:** It never leaves the machine

### vs Other Open Source Stacks
- ❌ **Them:** Ollama + a UI + an index + tool servers, wired by hand, maintained forever
- ✅ **You:** The assembly is done and kept working, behind one command

### vs Bare Ollama
- ❌ **Them:** Runs the model. Doesn't pick one, grant it tools, or shape the prompt.
- ✅ **You:** Pick an intent — the workspace sets model, toolset and context budget

### vs Commercial On-Prem
- ❌ **Them:** Licence fee, someone else's roadmap
- ✅ **You:** A repository you own outright

**What you give up:** a frontier model's ceiling, and a support contract. That's the trade, and it's real.

### What This Is Not
- ❌ Not a chat UI, auth system or metrics stack — Open WebUI does those, Portal 5 extends it
- ❌ Not cloud inference with a local option — there is no frontier fallback
- ❌ Not an agent framework — no LangChain, no LlamaIndex

---

## 🚀 Next Steps

### Today
1. `./launch.sh up`
2. Sign in, ask a few real questions
3. Find which presets you actually reach for
4. **Don't** pull the full catalog yet

### This Week
1. `./launch.sh pull-models`, walk away
2. Read `docs/USER_GUIDE.md`
3. Point retrieval at documents you care about
4. Turn on a channel if you want it on your phone

### This Month
1. Read `CLAUDE.md` before adding anything
2. Add a workspace or persona for work you actually do
3. Run the benchmark lanes against your own tasks
4. Read `KNOWN_LIMITATIONS.md` before trusting anything

---

## 📞 Support & Resources

### Documentation
- All guides in `docs/`
- Start with `docs/USER_GUIDE.md`
- Check `KNOWN_LIMITATIONS.md` for anything that surprises you

### Resources
- **Ollama:** https://ollama.ai
- **Open WebUI:** https://github.com/open-webui/open-webui
- **MCP:** https://github.com/modelcontextprotocol/
- **MLX:** https://github.com/ml-explore/mlx

---

## 🎉 You're Ready!

This repository contains **everything** needed to run a production-grade, privacy-first AI platform:

- ✅ **16 capability domains** (14 enabled out of the box)
- ✅ **46 workspaces** (25 functional, 21 benchmark)
- ✅ **33 MCP tool servers** (ports 8910-8941)
- ✅ **122 personas**
- ✅ **3 channels** (browser, Telegram, Slack)
- ✅ **213 validation checks**
- ✅ **No cloud dependencies** (100% local inference)

**Start with `./launch.sh up` and sign in at localhost:8080!**

---

## 🎓 Why This Exists

This started as a Telegram bot on a Mac Mini, routing between a 270M model and a 32B one, built to settle whether local models were a hobby or a tool.

They were a tool. The bot became PocketPortal. PocketPortal became Portal 5. The interface moved to Open WebUI because writing a worse chat UI is not a good use of an evening. The wager never moved: **local, private, one command, no subscription.**

Nearly everything added since arrived because a real job demanded it — OT/ICS security work, NERC CIP compliance reasoning, Splunk queries, documents, voice, CAD. Nothing was added to make a feature list longer, and a fair amount has been retired for not earning its keep.

The bet is that owning the whole stack beats renting a better one.

---

**Platform:** Apple Silicon (M-series)
**Inference:** Ollama (chat) + MLX (speech, embeddings, generation)
**License:** MIT

**Built with ❤️ for privacy, autonomy, and control**
