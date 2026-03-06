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
           add-user list-users up-telegram up-slack up-channels \
           backup restore; do
    grep -q "^  ${cmd})" launch.sh && echo "PRESENT: $cmd" || echo "MISSING: $cmd"
done
```

### 2H — Dockerfile Completeness and Channel Deployment Checks (NEW)

**Verify Dockerfile.mcp copies all required modules:**
```python
src = open("Dockerfile.mcp").read()

# Critical: channel containers run portal_channels — must be copied
assert "COPY portal_mcp/ ./portal_mcp/" in src, \
    "FAIL: portal_mcp not copied into MCP image"
assert "COPY portal_channels/ ./portal_channels/" in src, \
    "FAIL: portal_channels not copied — portal-telegram/slack will crash with " \
    "ModuleNotFoundError on every startup"

# Verify order: portal_mcp before portal_channels
mcp_pos = src.index("COPY portal_mcp/")
ch_pos  = src.index("COPY portal_channels/")
assert ch_pos > mcp_pos, "FAIL: COPY order wrong — portal_channels before portal_mcp"

# Verify all channel deps installed
for pkg in ["python-telegram-bot", "slack-bolt"]:
    assert pkg in src, f"FAIL: {pkg} not installed in Dockerfile.mcp"
    print(f"OK: {pkg}")

print("OK: Dockerfile.mcp copies both portal_mcp/ and portal_channels/")
```

**Verify channel services have healthchecks:**
```python
import yaml
dc = yaml.safe_load(open("deploy/portal-5/docker-compose.yml"))

for svc_name in ["portal-telegram", "portal-slack"]:
    svc = dc["services"].get(svc_name, {})
    hc = svc.get("healthcheck")
    assert hc is not None, \
        f"FAIL: {svc_name} has no healthcheck — crashes go undetected and restart never triggers"
    assert hc.get("test"), f"FAIL: {svc_name} healthcheck has no test command"
    assert hc.get("interval"), f"FAIL: {svc_name} healthcheck has no interval"
    print(f"OK: {svc_name} healthcheck: {hc['test']}")
```

**Verify backup uses realpath (not $(pwd)/):**
```bash
# $(pwd)/${BACKUP_PATH} breaks for absolute paths like /mnt/nas/backup
WRONG_PATTERN=$(grep -c '$(pwd)/${BACKUP_PATH}' launch.sh || echo 0)
echo "Wrong pattern count: $WRONG_PATTERN (expect 0)"
[ "$WRONG_PATTERN" -eq 0 ] && echo "OK: backup uses realpath" \
    || echo "FAIL: backup still uses \$(pwd)/\${BACKUP_PATH}"
```

### 2I — Dispatcher Retry Test Coverage (NEW)

**Verify dispatcher retry tests exist:**
```python
import re
src = open("tests/unit/test_channels.py").read()

assert "test_call_pipeline_async_retries_on_500" in src, (
    "FAIL: dispatcher retry test missing.\n"
    "  The retry logic in dispatcher.py (PIPELINE_RETRIES, exponential backoff)\n"
    "  has no test coverage. Add:\n"
    "  - TestDispatcher::test_call_pipeline_async_retries_on_500\n"
    "  - TestDispatcher::test_call_pipeline_sync_raises_after_exhausting_retries"
)
assert "test_call_pipeline_sync_raises_after_exhausting_retries" in src, \
    "FAIL: sync retry exhaustion test missing"

print("OK: dispatcher retry tests present")
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
