# Portal 5 — Final Release Agent (Round 10)

**Date:** March 2026 | **Branch:** main only | **Target:** v5.0.0 release

---

## Current State

```
Tests:    67/72 pass — 5 failures (trivial: wrong mock patch targets after R9 dispatcher refactor)
Lint:     0 violations ✅
Compile:  All clean ✅
Branch:   main only ✅
```

**All 5 failures have the same root cause:** R9 moved httpx calls from `bot.py`
into `dispatcher.py`. Tests still patch `portal_channels.telegram.bot.httpx` and
`portal_channels.slack.bot.httpx` — modules that no longer import httpx directly.
Fix: patch `portal_channels.dispatcher.httpx` instead.

This is the only blocker to a clean `72/72` green suite and a v5.0.0 tag.

---

## Bootstrap (hard gate)

```bash
cd /path/to/portal-5
git checkout main && git pull
pip install -e ".[dev,mcp,channels]" --quiet

# Baseline — 5 known failures before fix
python3 -m pytest tests/ -q --tb=no 2>&1 | tail -2
python3 -m ruff check portal_pipeline/ scripts/ portal_mcp/ portal_channels/ --quiet
```

---

## TASK-001 — Fix 5 Failing Tests: Update Mock Patch Targets

**Root cause:** After R9 refactored both channel bots to delegate pipeline calls
through `portal_channels/dispatcher.py`, neither `telegram/bot.py` nor
`slack/bot.py` imports `httpx` directly any more. Tests that patch
`portal_channels.telegram.bot.httpx` or `portal_channels.slack.bot.httpx`
raise `AttributeError: module has no attribute 'httpx'`.

The correct patch target is now `portal_channels.dispatcher.httpx`.

**Action:** In `tests/unit/test_channels.py`, update all 5 affected patch targets:

**Lines 121, 171, 234 — Telegram tests:**
```python
# BEFORE (3 occurrences):
with patch("portal_channels.telegram.bot.httpx.AsyncClient") as mock_client:

# AFTER:
with patch("portal_channels.dispatcher.httpx.AsyncClient") as mock_client:
```

**Lines 312, 330 — Slack tests:**
```python
# BEFORE (2 occurrences):
with patch("portal_channels.slack.bot.httpx.Client") as mock_client:

# AFTER:
with patch("portal_channels.dispatcher.httpx.Client") as mock_client:
```

No logic changes — only the string passed to `patch()`.

**Verify:**
```bash
python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5
# Expected: 72 passed, 0 failed, 0 skipped
```

---

## TASK-002 — Replace README with Production-Ready Quickstart

**Finding:** The current README (414 words) has a Quick Start section that jumps
straight to `git clone` with no prerequisites. A user could spend an hour debugging
why nothing works because Docker isn't installed, or spend 45 minutes confused while
FLUX.1-schnell downloads with no progress indication. There are also no instructions
for enabling Telegram/Slack channels or pointing users to the full docs.

**Action:** Replace `README.md` entirely:

```markdown
# Portal 5 — Local AI Platform

A complete, private AI platform that runs on your hardware. Text, code, security
analysis, images, video, music, documents, and voice — all local, all yours.

Connects to Open WebUI, Telegram, and Slack. Routes automatically to the right
model for each task. No cloud accounts. No usage fees. No data leaving your machine.

---

## Prerequisites

| Requirement | Minimum | Recommended |
|---|---|---|
| **Docker** | Docker Desktop 4.x or Docker Engine 24+ with Compose v2 | Latest Docker Desktop |
| **RAM** | 16 GB | 32–64 GB (for large models) |
| **Disk** | 50 GB free | 200 GB (full model catalog) |
| **CPU** | Any modern x86-64 or Apple Silicon | Apple M-series or recent Intel/AMD |
| **GPU** | None required | NVIDIA GPU with 8GB+ VRAM (speeds inference) |
| **OS** | macOS 13+, Ubuntu 22.04+, or Windows 11 with WSL2 | macOS (Apple Silicon) |

> **Apple Silicon:** Portal 5 runs natively on M1/M2/M3/M4 via Ollama's Metal
> acceleration. No NVIDIA GPU required.

> **Linux:** Ensure your user is in the `docker` group:
> `sudo usermod -aG docker $USER && newgrp docker`

---

## Quick Start

```bash
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
./launch.sh up
```

**First run pulls ~16 GB of data and takes 10–45 minutes depending on your
connection.** You will see progress in the terminal. When it finishes:

```
[portal-5] ✅ Stack is ready
[portal-5] Web UI:     http://localhost:8080
[portal-5] Grafana:    http://localhost:3000
[portal-5] Admin creds saved to: .env (do not commit this file)
```

Open **http://localhost:8080** and sign in with the admin credentials printed to
your terminal.

---

## What Starts Automatically

Everything runs with a single command. No manual configuration.

| Service | What it does | URL |
|---|---|---|
| Open WebUI | Chat interface — your main portal | http://localhost:8080 |
| Portal Pipeline | Intelligent routing to models | (internal) |
| Ollama | Runs local language models | (internal) |
| SearXNG | Private web search for research | (internal) |
| ComfyUI | Image and video generation | http://localhost:8188 |
| 7 MCP Servers | Documents, music, voice, code, images | (internal) |
| Prometheus | Metrics collection | http://localhost:9090 |
| Grafana | Metrics dashboard | http://localhost:3000 |

---

## Workspaces

Select a workspace in the Open WebUI model dropdown to activate the right model
and tools automatically.

| Workspace | Purpose | Auto-activates |
|---|---|---|
| `auto` | General — routes to best model | — |
| `auto-coding` | Code generation and review | Code sandbox |
| `auto-security` | Security analysis and hardening | Code sandbox |
| `auto-redteam` | Offensive security research | Code sandbox |
| `auto-blueteam` | Defensive security, incident response | Code sandbox |
| `auto-documents` | Create Word, Excel, PowerPoint | Documents + Code |
| `auto-music` | Generate music via AudioCraft | Music + TTS |
| `auto-video` | Generate video via ComfyUI | Video + Image |
| `auto-vision` | Image understanding, visual tasks | Image generation |
| `auto-creative` | Creative writing | TTS voice |
| `auto-research` | Web research and synthesis | — |
| `auto-reasoning` | Deep reasoning, complex analysis | — |
| `auto-data` | Data analysis, statistics | Code + Documents |

---

## Common Commands

```bash
# Start / stop
./launch.sh up              # Start everything
./launch.sh down            # Stop (data preserved)
./launch.sh status          # Check service health

# Test everything is working
./launch.sh test            # Run live smoke tests against running stack

# Pull specialized models (security, coding, reasoning — 30–90 min)
./launch.sh pull-models

# User management
./launch.sh add-user alice@example.com "Alice Smith"
./launch.sh list-users

# Enable messaging channels (requires tokens in .env)
./launch.sh up-telegram     # Start Telegram bot
./launch.sh up-slack        # Start Slack bot
./launch.sh up-channels     # Start both

# Backup and restore
./launch.sh backup          # Save all data to ./backups/
./launch.sh restore <file>  # Restore from backup

# Cleanup
./launch.sh clean           # Remove containers (keeps model weights)
./launch.sh clean-all       # Remove everything including models
```

---

## Enable Telegram Bot

1. Message **@BotFather** on Telegram → `/newbot` → copy the token
2. Get your Telegram user ID from **@userinfobot**
3. Add to `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=your-token-here
   TELEGRAM_USER_IDS=your-user-id
   ```
4. Start: `./launch.sh up-telegram`
5. Message your bot `/start` to verify

---

## Enable Slack Bot

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**
2. Under **OAuth & Permissions** → add bot scopes:
   `app_mentions:read`, `chat:write`, `channels:history`, `im:history`, `im:read`, `im:write`
3. Under **Socket Mode** → enable it → generate an **App-Level Token** (xapp-...)
4. Install app to your workspace
5. Add to `.env`:
   ```bash
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_SIGNING_SECRET=...
   ```
6. Start: `./launch.sh up-slack`
7. Mention `@portal` in any channel to verify

---

## Hardware & Model Guide

### Core models (pulled automatically on first run, ~4 GB)
- `dolphin-llama3:8b` — general purpose default
- `llama3.2:3b` — fast small model
- `nomic-embed-text` — document embeddings for RAG

### Specialized models (pulled with `./launch.sh pull-models`, ~60–100 GB total)
- **Security:** BaronLLM-18B, Lily-Cybersecurity-7B, WhiteRabbitNeo-33B
- **Coding:** Qwen3-Coder-30B, GLM-4.7-Flash, Devstral-24B
- **Reasoning:** DeepSeek-R1-32B, Tongyi-DeepResearch-30B
- **Vision:** Qwen3-Omni-30B, LLaVA-7B

### Image generation (downloaded automatically on first run, ~12 GB)
- FLUX.1-schnell — fast, high-quality image generation

To use a different image model: set `IMAGE_MODEL=sdxl` or `IMAGE_MODEL=flux-dev`
in `.env` (flux-dev requires a HuggingFace token).

---

## Troubleshooting

**Services not starting:**
```bash
./launch.sh status          # See which services failed
docker compose -f deploy/portal-5/docker-compose.yml logs <service-name>
```

**Out of disk space:**
```bash
docker system df            # See Docker disk usage
./launch.sh clean           # Remove containers
# Then free disk space and retry ./launch.sh up
```

**Models not loading (Ollama shows 0 backends):**
```bash
./launch.sh pull-models     # Ensure at least one model is pulled
# Wait for Ollama to finish loading, then try again
```

**First run taking too long:**
FLUX.1-schnell is ~12 GB. On a 100 Mbps connection this takes ~15 minutes.
On slower connections it may take longer. The download resumes if interrupted.

**Port already in use:**
```bash
lsof -i :8080               # Find what is using port 8080
# Stop the conflicting service, then ./launch.sh up
```

---

## Documentation

| Guide | Contents |
|---|---|
| [User Guide](docs/USER_GUIDE.md) | How to use workspaces, tools, personas |
| [Admin Guide](docs/ADMIN_GUIDE.md) | User management, configuration, security |
| [ComfyUI Setup](docs/COMFYUI_SETUP.md) | Advanced image/video model configuration |
| [Cluster Scaling](docs/CLUSTER_SCALE.md) | Running multiple Ollama instances |
| [Backup & Restore](docs/BACKUP_RESTORE.md) | Data backup procedures |
| [Known Issues](KNOWN_ISSUES.md) | Current limitations and workarounds |

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │         Open WebUI :8080         │
                    │   (chat, workspaces, personas)   │
                    └──────────┬──────────────────────┘
                               │
                    ┌──────────▼──────────────────────┐
                    │    Portal Pipeline :9099          │
                    │  (routing, auth, metrics, MCP)   │
                    └──┬───┬───┬───┬──────────────────┘
                       │   │   │   │
          ┌────────────┘   │   │   └─────────────┐
          │                │   │                 │
   ┌──────▼──────┐  ┌──────▼──┐  ┌──────────────▼──┐
   │  Ollama      │  │SearXNG  │  │  MCP Servers     │
   │  :11434      │  │  :8088  │  │  :8910–8916      │
   │  (LLMs)      │  │(search) │  │  (tools)         │
   └─────────────┘  └─────────┘  └─────────────────┘
                                          │
                         ┌────────────────┼──────────────────┐
                         │                │                  │
                   ┌─────▼────┐    ┌──────▼──────┐   ┌──────▼──────┐
                   │ Documents │    │  TTS/Whisper │   │  Code/DinD  │
                   │  :8913    │    │  :8916/:8915 │   │   :8914     │
                   └──────────┘    └─────────────┘   └────────────┘

   Telegram Bot ──► Portal Pipeline    Slack Bot ──► Portal Pipeline
   (profile: telegram)                 (profile: slack)

   Grafana :3000 ◄── Prometheus :9090 ◄── /metrics
```

---

## License

MIT — see [LICENSE](LICENSE)
```

**Verify:**
```bash
wc -w README.md
python3 -c "
src = open('README.md').read()
required = ['Prerequisites', 'Quick Start', 'Docker', 'RAM', 'Disk',
            'up-telegram', 'up-slack', 'Troubleshooting', 'pull-models',
            'Architecture']
missing = [r for r in required if r not in src]
print(f'Missing sections: {missing or \"NONE\"}')
assert not missing
print('OK: README has all required sections')
"
```

---

## TASK-003 — Update Code Quality Agent v4

The code quality agent v3 misses several checks that have caused real bugs across
rounds 5–9. Replace `portal5_code_quality_agent_v3.md` with the updated v4.

**What v3 was missing (proved by findings caught manually):**
- No TOOLS_MANIFEST ↔ registered tool bidirectional check
- No dispatcher.py check
- No workspace toolIds per JSON check
- No sandbox `--security-opt` / `--cap-drop` flag check
- No channel profile check in compose
- No `up-telegram` / `up-slack` launch.sh command check
- Test gate only installs `[dev]`, not `[dev,mcp,channels]`
- No check that test mock patches target the right module

Replace the file with a complete v4 that adds these to Phase 2 and Phase 3:

```markdown
# Portal 5 — Code Quality, Production Readiness & Action Agent v4

## Role
Elite codebase defect hunter and production readiness assessor in Claude Code
(full filesystem and shell access).

Core philosophy: Run it. Prove it. Find what actually breaks.
Every finding must be backed by runtime or static evidence.

## Hard Constraints
1. Every claim backed by: runtime output OR static file:line reference
2. Never invent files, modules, endpoints, or env vars
3. Preserve P5-ROAD-NNN IDs
4. Capture exact error output — no paraphrasing

End every artifact with:
**COMPLIANCE CHECK**
- Hard constraints met: Yes/No
- All findings backed by evidence: Yes/No
- Uncertainty Log: [<90% confidence items or "None"]

---

## Phase 0 — Bootstrap (hard gate)

```bash
cd /path/to/portal-5
git checkout main && git pull
git log --oneline -5
git branch -a   # Expected: main only

# Install ALL optional groups — tests require channels and mcp
pip install -e ".[dev,mcp,channels]" 2>&1 | tee /tmp/p5_install.log
grep -iE "error|failed|conflict" /tmp/p5_install.log || echo "CLEAN INSTALL"

python3 -m ruff check portal_pipeline/ scripts/ portal_mcp/ portal_channels/ 2>&1
find . -name "*.py" -not -path "./.git/*" -not -path "./.venv/*" | \
    xargs -I{} python3 -m py_compile {} 2>&1 | grep "Error" || echo "All compile"

# HARD GATE: 0 failures before any work
python3 -m pytest tests/ -q --tb=short 2>&1 | tee /tmp/p5_tests.log
RESULT=$(tail -1 /tmp/p5_tests.log)
echo "Tests: $RESULT"
echo "$RESULT" | grep -q "passed" && echo "Gate passed" || echo "GATE FAILED — stop"
```

Produce baseline block:
```
BASELINE
Python: [version] | Install: [CLEAN/FAIL] | Lint: [N violations]
Tests: [N passed, N failed] | Compile: [OK/FAIL] | Branch: [main only/other]
```

---

## Phase 2 — Configuration & Consistency

### 2A — Three-Source Workspace Consistency

```python
import json, yaml, sys
from pathlib import Path
sys.path.insert(0, ".")
from portal_pipeline.router_pipe import WORKSPACES

cfg = yaml.safe_load(Path("config/backends.yaml").read_text())
yaml_ids = set(cfg.get("workspace_routing", {}).keys())
ws_files = list(Path("imports/openwebui/workspaces").glob("workspace_*.json"))
import_ids = {json.loads(f.read_text()).get("id", "") for f in ws_files}
pipe_ids = set(WORKSPACES.keys())
ok = pipe_ids == yaml_ids == import_ids
print(f"Consistent={ok}: pipe={len(pipe_ids)} yaml={len(yaml_ids)} imports={len(import_ids)}")
for wid in sorted(pipe_ids | yaml_ids | import_ids):
    p = "Y" if wid in pipe_ids else "N"
    b = "Y" if wid in yaml_ids else "N"
    i = "Y" if wid in import_ids else "N"
    gap = " ← GAP" if "N" in (p+b+i) else ""
    print(f"  {wid:32s} pipe={p} yaml={b} import={i}{gap}")
```

### 2B — MCP Tool Bidirectional Alignment (NEW — catches silent AI tool failures)

```python
import sys, importlib
sys.path.insert(0, ".")

servers = [
    ("documents", "portal_mcp.documents.document_mcp"),
    ("music",     "portal_mcp.generation.music_mcp"),
    ("tts",       "portal_mcp.generation.tts_mcp"),
    ("whisper",   "portal_mcp.generation.whisper_mcp"),
    ("comfyui",   "portal_mcp.generation.comfyui_mcp"),
    ("video",     "portal_mcp.generation.video_mcp"),
    ("sandbox",   "portal_mcp.execution.code_sandbox_mcp"),
]
all_ok = True
for name, path in servers:
    mod = importlib.import_module(path)
    reg = set(mod.mcp._tool_manager._tools.keys())
    man = {t["name"] for t in mod.TOOLS_MANIFEST}
    miss_man = reg - man   # registered but AI can't call it (dead)
    miss_reg = man - reg   # AI calls it but doesn't exist (silent fail)
    if miss_man or miss_reg:
        print(f"FAIL {name}: dead={miss_man} broken={miss_reg}")
        all_ok = False
    else:
        print(f"OK   {name}: {sorted(reg)}")
print("All aligned:", all_ok)
```

### 2C — Workspace toolIds (NEW — ensures tools auto-activate per workspace)

```python
import json
from pathlib import Path

EXPECTED = {
    "auto-coding":    ["portal_code"],
    "auto-documents": ["portal_documents", "portal_code"],
    "auto-music":     ["portal_music", "portal_tts"],
    "auto-video":     ["portal_video", "portal_comfyui"],
    "auto-security":  ["portal_code"],
    "auto-redteam":   ["portal_code"],
    "auto-blueteam":  ["portal_code"],
    "auto-creative":  ["portal_tts"],
    "auto-vision":    ["portal_comfyui"],
    "auto-data":      ["portal_code", "portal_documents"],
    "auto":           [],
    "auto-research":  [],
    "auto-reasoning": [],
}
all_ok = True
for f in sorted(Path("imports/openwebui/workspaces").glob("workspace_*.json")):
    d = json.loads(f.read_text())
    ws_id = d.get("id", "")
    got = sorted(d.get("meta", {}).get("toolIds", []))
    exp = sorted(EXPECTED.get(ws_id, []))
    ok = got == exp
    if not ok:
        print(f"FAIL {ws_id}: got={got} expected={exp}")
        all_ok = False
    else:
        print(f"OK   {ws_id}: {got}")
print("All toolIds correct:", all_ok)
```

### 2D — Compose Profiles (NEW — channels in correct profiles)

```python
import yaml
dc = yaml.safe_load(open("deploy/portal-5/docker-compose.yml"))
svcs = dc["services"]

# Channel services must be in profiles, not in core stack
assert svcs.get("portal-telegram", {}).get("profiles") == ["telegram"], \
    "FAIL: portal-telegram not in telegram profile"
assert svcs.get("portal-slack", {}).get("profiles") == ["slack"], \
    "FAIL: portal-slack not in slack profile"
print("OK: channel services in correct profiles")

# Core services must NOT be in profiles
core = ["ollama", "portal-pipeline", "open-webui", "mcp-tts", "mcp-whisper",
        "mcp-documents", "mcp-music", "mcp-sandbox", "mcp-comfyui", "mcp-video",
        "searxng", "comfyui", "prometheus", "grafana", "dind"]
for svc in core:
    prof = svcs.get(svc, {}).get("profiles", [])
    assert prof == [], f"FAIL: {svc} has profiles={prof} (should be always-on)"
    print(f"OK: {svc} always-on")
```

### 2E — Dispatcher Coverage (NEW)

```python
import sys; sys.path.insert(0, ".")
from portal_channels.dispatcher import VALID_WORKSPACES
from portal_pipeline.router_pipe import WORKSPACES

pipe_ids = set(WORKSPACES.keys())
disp_ids = set(VALID_WORKSPACES)
missing = pipe_ids - disp_ids
extra = disp_ids - pipe_ids
print(f"Pipeline: {len(pipe_ids)} workspaces")
print(f"Dispatcher: {len(disp_ids)} workspaces")
assert not missing, f"FAIL: dispatcher missing {missing}"
assert not extra, f"FAIL: dispatcher has unknown {extra}"
print("OK: dispatcher covers all workspaces")

# Bots must NOT import httpx directly (uses dispatcher)
for bot_file in ["portal_channels/telegram/bot.py", "portal_channels/slack/bot.py"]:
    src = open(bot_file).read()
    assert "import httpx" not in src, f"FAIL: {bot_file} imports httpx directly"
    assert "dispatcher" in src, f"FAIL: {bot_file} doesn't use dispatcher"
    print(f"OK: {bot_file} uses dispatcher")
```

### 2F — Sandbox Security Flags (NEW)

```python
src = open("portal_mcp/execution/code_sandbox_mcp.py").read()
required_flags = [
    "--network", "none", "--cpus", "0.5", "--memory", "256m",
    "--pids-limit", "--security-opt", "no-new-privileges",
    "--cap-drop", "ALL", "--read-only", "--tmpfs",
]
for flag in required_flags:
    assert flag in src, f"FAIL: docker flag missing: {flag}"
    print(f"OK: {flag}")
assert "wait_for" in src, "FAIL: asyncio timeout missing"
assert "MAX_OUTPUT_BYTES" in src, "FAIL: output cap missing"
print("OK: all sandbox security flags present")
```

### 2G — Launch Script Commands (NEW)

```bash
bash -n launch.sh && echo "PASS: syntax valid"
for cmd in up down clean clean-all seed logs status pull-models test \
           add-user list-users up-telegram up-slack up-channels; do
    grep -q "^  ${cmd})" launch.sh && echo "PRESENT: $cmd" || echo "MISSING: $cmd"
done
```

---

## Phase 3 — Behavioral Verification

### 3A — Pipeline Startup

```bash
python3 -m portal_pipeline &
PIPE_PID=$!
for i in $(seq 1 15); do
    sleep 1
    curl -s http://localhost:9099/health 2>/dev/null | grep -q '"status"' && \
        echo "Ready after ${i}s" && break
done
curl -s http://localhost:9099/health | python3 -m json.tool
curl -s -H "Authorization: Bearer portal-pipeline" http://localhost:9099/v1/models | \
    python3 -c "import json,sys; d=json.load(sys.stdin); ids=[m['id'] for m in d['data']]; \
    print(f'{len(ids)} workspaces'); [print(f'  {i}') for i in sorted(ids)]"
curl -s http://localhost:9099/metrics | grep "^portal_"
# Auth enforcement
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9099/v1/models)
echo "No-auth → $STATUS (expect 401)"
kill $PIPE_PID 2>/dev/null; wait $PIPE_PID 2>/dev/null
```

### 3B — BackendRegistry

```python
import sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")
from portal_pipeline.cluster_backends import BackendRegistry

# Load from real config
reg = BackendRegistry(config_path="config/backends.yaml")
print(f"timeout={reg.request_timeout} interval={reg._health_check_interval}")
assert reg.request_timeout >= 60, f"FAIL: timeout too low: {reg.request_timeout}"

# Fallback behavior
for b in reg._backends.values():
    b.healthy = False
result = reg.get_backend_for_workspace("auto")
print(f"All unhealthy → {result} (expect None)")
assert result is None
print("OK: BackendRegistry")
```

### 3C — MCP Server Endpoints (all 7)

```python
import sys, importlib, os
sys.path.insert(0, ".")
os.environ.setdefault("COMFYUI_URL", "http://localhost:8188")
from fastapi.testclient import TestClient

servers = {
    "documents": "portal_mcp.documents.document_mcp",
    "music":     "portal_mcp.generation.music_mcp",
    "tts":       "portal_mcp.generation.tts_mcp",
    "whisper":   "portal_mcp.generation.whisper_mcp",
    "comfyui":   "portal_mcp.generation.comfyui_mcp",
    "video":     "portal_mcp.generation.video_mcp",
    "sandbox":   "portal_mcp.execution.code_sandbox_mcp",
}
for name, path in servers.items():
    mod = importlib.import_module(path)
    app = mod.mcp.streamable_http_app()
    client = TestClient(app)
    r = client.get("/health")
    r2 = client.get("/tools")
    tools = [t["name"] for t in r2.json().get("tools", [])]
    print(f"  {name}: health={r.status_code} tools={tools}")
    assert r.status_code == 200, f"FAIL: {name} /health"
    assert tools, f"FAIL: {name} no tools"
```

### 3D — Channel Adapter Logic

```python
import sys, os
sys.path.insert(0, ".")

# Dispatcher
from portal_channels.dispatcher import is_valid_workspace, VALID_WORKSPACES
from portal_pipeline.router_pipe import WORKSPACES
assert set(VALID_WORKSPACES) == set(WORKSPACES.keys()), "FAIL: dispatcher out of sync"
assert is_valid_workspace("auto-coding")
assert not is_valid_workspace("auto-nonexistent")
print("OK: dispatcher correct")

# Bots importable without tokens
for key in ("TELEGRAM_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
    os.environ.pop(key, None)
import importlib
for mod in ("portal_channels.telegram.bot", "portal_channels.slack.bot"):
    if mod in sys.modules: del sys.modules[mod]
    m = importlib.import_module(mod)
    assert hasattr(m, "build_app")
    print(f"OK: {mod} importable without token")
```

### 3E — Behavioral Verification Matrix

```
CHECK                                     | RESULT | SOURCE
------------------------------------------|--------|-------
Pipeline /health 200                      |        | 3A
Pipeline /v1/models 401 without auth      |        | 3A
Pipeline returns 13 workspaces            |        | 3A
Pipeline /metrics has 4+ gauges           |        | 3A
timeout=120 from YAML                     |        | 3B
all-unhealthy returns None                |        | 3B
All 7 MCP /health return 200              |        | 3C
All 7 MCP tools non-empty                 |        | 3C
MCP TOOLS_MANIFEST bidirectional (7/7)    |        | 2B
workspace toolIds correct (13/13)         |        | 2C
Dispatcher covers all 13 workspaces       |        | 2E
Bots don't import httpx directly          |        | 2E
Sandbox has 10 security flags             |        | 2F
Channel services in correct profiles      |        | 2D
launch.sh has up-telegram/slack/channels  |        | 2G
3-source workspace consistency            |        | 2A
```

---

## Output Artifacts

### P5_AUDIT_REPORT.md
1. Executive Summary (score, top issues)
2. Baseline Status
3. Behavioral Verification Matrix (3E)
4. Configuration Audit
5. Code Findings Register (file:line, severity, evidence, fix)
6. Test Coverage
7. Production Readiness Score /100

Dimensions: Security / Sandbox / Multi-user / Routing / Capacity /
Zero-setup / Model catalog / Ops tooling / Test coverage / Code quality /
Docs / Deploy / Channel integrity / MCP alignment

### P5_ACTION_PROMPT.md
Bootstrap block (installs `[dev,mcp,channels]`) + TASK-NNN items.

### P5_ROADMAP.md
Preserve P5-ROAD-NNN IDs. Add new items for BROKEN/STUB findings.

**COMPLIANCE CHECK**
- Hard constraints met: Yes/No
- All findings backed by evidence: Yes/No
- Uncertainty Log: [<90% confidence or "None"]
```

---

## TASK-004 — Update Documentation Agent v4

The doc agent v3 misses verification of: the dispatcher, workspace toolIds per file,
channel adapter test coverage, and the live stack smoke test. Replace
`portal5_documentation_truth_agent_v3.md` with v4 that adds these to Phase 3.

Add the following to **Phase 3 — Behavioral Verification** in the doc agent:

**3H (new) — Channel Adapter Verification:**
```python
import sys, os
sys.path.insert(0, ".")

# Dispatcher exists and is correct
from portal_channels.dispatcher import VALID_WORKSPACES, call_pipeline_async, call_pipeline_sync
from portal_pipeline.router_pipe import WORKSPACES
assert set(VALID_WORKSPACES) == set(WORKSPACES.keys())
print(f"OK: dispatcher.py — {len(VALID_WORKSPACES)} workspaces")

# Bots importable without tokens
for key in ("TELEGRAM_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
    os.environ.pop(key, None)
import importlib
for mod_path in ("portal_channels.telegram.bot", "portal_channels.slack.bot"):
    if mod_path in sys.modules: del sys.modules[mod_path]
    m = importlib.import_module(mod_path)
    assert hasattr(m, "build_app"), f"FAIL: {mod_path} missing build_app()"
    print(f"OK: {mod_path} importable without token")

# Slack: correct SocketModeHandler token
slack_src = open("portal_channels/slack/bot.py").read()
assert "app_token" in slack_src and "SLACK_APP_TOKEN" in slack_src
assert "SocketModeHandler(slack_app, app_token)" in slack_src
print("OK: Slack uses SLACK_APP_TOKEN for SocketModeHandler")

# Neither bot imports httpx (uses dispatcher)
for f in ["portal_channels/telegram/bot.py", "portal_channels/slack/bot.py"]:
    src = open(f).read()
    assert "import httpx" not in src, f"FAIL: {f} imports httpx directly"
    print(f"OK: {f} delegates to dispatcher")
```

**3I (new) — Workspace toolIds Verification:**
```python
import json
from pathlib import Path

EXPECTED = {
    "auto-coding": ["portal_code"], "auto-documents": ["portal_documents","portal_code"],
    "auto-music": ["portal_music","portal_tts"], "auto-video": ["portal_video","portal_comfyui"],
    "auto-security": ["portal_code"], "auto-redteam": ["portal_code"],
    "auto-blueteam": ["portal_code"], "auto-creative": ["portal_tts"],
    "auto-vision": ["portal_comfyui"], "auto-data": ["portal_code","portal_documents"],
    "auto": [], "auto-research": [], "auto-reasoning": [],
}
for f in sorted(Path("imports/openwebui/workspaces").glob("workspace_*.json")):
    d = json.loads(f.read_text())
    ws_id = d.get("id", "")
    got = sorted(d.get("meta", {}).get("toolIds", []))
    exp = sorted(EXPECTED.get(ws_id, []))
    status = "VERIFIED" if got == exp else "BROKEN"
    print(f"  {status}: {ws_id}: toolIds={got}")
```

Also update the feature status matrix in Phase 3H to include:
- `Dispatcher covers all 13 workspaces | [status] | 3H`
- `Channel bots use dispatcher not direct httpx | [status] | 3H`
- `Workspace toolIds seeded (10/13 non-empty) | [status] | 3I`

And update the docs sections list to add:
- **Section 5b: Channel Dispatcher** — `portal_channels/dispatcher.py`,
  `VALID_WORKSPACES`, `call_pipeline_async`, `call_pipeline_sync`
- **Section 9b: Live Smoke Test** — `./launch.sh test` commands and what each checks

---

## Final Verification — All Tasks Complete

```bash
echo "=== 0. Install ==="
pip install -e ".[dev,mcp,channels]" --quiet && echo "OK"

echo ""
echo "=== 1. Tests: 72/72 ==="
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -10

echo ""
echo "=== 2. Lint ==="
python3 -m ruff check portal_pipeline/ scripts/ portal_mcp/ portal_channels/ \
    && echo "OK: 0 violations"

echo ""
echo "=== 3. Mock patch targets correct ==="
python3 -c "
src = open('tests/unit/test_channels.py').read()
bad = src.count('telegram.bot.httpx') + src.count('slack.bot.httpx')
good = src.count('dispatcher.httpx')
print(f'Wrong patches (telegram/slack.bot.httpx): {bad} (expect 0)')
print(f'Correct patches (dispatcher.httpx): {good} (expect 5)')
assert bad == 0, 'FAIL: still patching bot modules'
assert good == 5, f'FAIL: expected 5 dispatcher patches, found {good}'
print('OK: all patches target dispatcher')
"

echo ""
echo "=== 4. README has prerequisites ==="
python3 -c "
src = open('README.md').read()
required = ['Prerequisites','Docker','RAM','Disk','up-telegram','up-slack',
            'Troubleshooting','pull-models','Architecture']
for r in required:
    print(f'  {\"OK\" if r in src else \"MISSING\"}: {r}')
assert all(r in src for r in required)
print('OK: README complete')
"

echo ""
echo "=== 5. Review agents updated ==="
python3 -c "
for f, checks in [
    ('portal5_code_quality_agent_v3.md', ['TOOLS_MANIFEST', 'dispatcher', 'toolIds', 'no-new-privileges', 'up-telegram', 'mcp,channels']),
    ('portal5_documentation_truth_agent_v3.md', ['dispatcher', 'toolIds', 'SocketModeHandler', 'launch.sh test']),
]:
    src = open(f).read()
    for check in checks:
        print(f'  {\"OK\" if check in src else \"MISSING\"}: {f.split(\"/\")[-1]} has {check!r}')
"

echo ""
echo "=== 6. Full MCP alignment ==="
python3 -c "
import sys, importlib; sys.path.insert(0,'.')
servers = [
    ('documents','portal_mcp.documents.document_mcp'),
    ('music','portal_mcp.generation.music_mcp'),
    ('tts','portal_mcp.generation.tts_mcp'),
    ('whisper','portal_mcp.generation.whisper_mcp'),
    ('comfyui','portal_mcp.generation.comfyui_mcp'),
    ('video','portal_mcp.generation.video_mcp'),
    ('sandbox','portal_mcp.execution.code_sandbox_mcp'),
]
all_ok = True
for name, path in servers:
    mod = importlib.import_module(path)
    reg = set(mod.mcp._tool_manager._tools.keys())
    man = {t['name'] for t in mod.TOOLS_MANIFEST}
    ok = reg == man
    if not ok: all_ok = False
    print(f'  {\"OK\" if ok else \"FAIL\"}: {name}')
print('All aligned:', all_ok)
"

echo ""
echo "=== 7. Tag v5.0.0 ready? ==="
FAIL_COUNT=$(python3 -m pytest tests/ -q --tb=no 2>&1 | grep -c "failed" || echo 0)
LINT_COUNT=$(python3 -m ruff check portal_pipeline/ scripts/ portal_mcp/ portal_channels/ --quiet 2>&1 | grep -c "error" || echo 0)
echo "Test failures: $FAIL_COUNT (need 0)"
echo "Lint errors: $LINT_COUNT (need 0)"
if [ "$FAIL_COUNT" -eq 0 ] && [ "$LINT_COUNT" -eq 0 ]; then
    echo ""
    echo "✅ READY TO TAG v5.0.0"
    echo "  git tag -a v5.0.0 -m 'Portal 5.0.0 — feature-complete release'"
    echo "  git push origin v5.0.0"
else
    echo "❌ NOT READY — fix failures first"
fi
```

---

## Git Commit

```bash
git add .
git commit -m "release(v5.0.0): fix 5 test failures, complete README, update review agents

Test fixes (TASK-001):
- Fix 5 test failures in test_channels.py caused by R9 dispatcher refactor
  Tests patched portal_channels.telegram.bot.httpx and slack.bot.httpx
  After R9 those modules no longer import httpx — calls go through dispatcher
  Fixed: patch portal_channels.dispatcher.httpx (5 occurrences)
  Result: 72/72 tests pass, 0 failed, 0 skipped

README (TASK-002):
- Full rewrite: 414 words → production-grade quickstart guide
  Added: Prerequisites table (Docker, RAM, Disk, CPU, GPU, OS)
  Added: Platform notes (Apple Silicon, Linux docker group)
  Added: First-run timing expectations (10-45 min, 16GB download)
  Added: Complete commands reference with descriptions
  Added: Step-by-step Telegram and Slack setup instructions
  Added: Hardware and model guide (core/specialized/image)
  Added: Troubleshooting section (5 common issues with fixes)
  Added: Architecture diagram (ASCII, accurate port references)
  Updated: Workspace table with tool auto-activation column

Code quality agent v4 (TASK-003):
- Bootstrap: install [dev,mcp,channels] (was [dev] only)
- Phase 2B: TOOLS_MANIFEST ↔ registered bidirectional alignment (all 7 servers)
- Phase 2C: workspace toolIds per JSON (13 workspaces)
- Phase 2D: compose profiles (telegram/slack in profiles, core always-on)
- Phase 2E: dispatcher.py coverage and bot httpx import check
- Phase 2F: sandbox 10-flag security check
- Phase 2G: launch.sh up-telegram, up-slack, up-channels command check
- Phase 3E matrix: expanded to 16 checks

Documentation agent v4 (TASK-004):
- Phase 3H: channel adapter verification (dispatcher, imports, Slack token)
- Phase 3I: workspace toolIds verification per JSON file
- Feature matrix: 3 new rows (dispatcher, httpx delegation, toolIds)
- Docs sections: dispatcher.py section, live smoke test section"

git tag -a v5.0.0 -m "Portal 5.0.0 — feature-complete release

72/72 tests passing. 0 lint violations. Full feature set verified:
- 13 workspaces with model routing and auto-activated tools
- 35 AI personas
- 7 MCP servers: documents, music, TTS, STT, images, video, code sandbox
- Web search via SearXNG
- RAG with nomic-embed-text embeddings
- Cross-session memory
- Telegram and Slack channel adapters
- Prometheus + Grafana metrics
- Zero-setup: ./launch.sh up"

git push origin main
git push origin v5.0.0
```

---

## Release Checklist

Before pushing the tag, verify:

```
[ ] python3 -m pytest tests/ -q  → 72 passed, 0 failed
[ ] ruff check ...               → All checks passed
[ ] README has Prerequisites, Quickstart, Troubleshooting
[ ] Review agents updated (portal5_code_quality_agent_v3.md, portal5_documentation_truth_agent_v3.md)
[ ] git tag -a v5.0.0 pushed
[ ] .env not in git ls-files
[ ] data/ not in git ls-files
```
