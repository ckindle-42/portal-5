# Portal 5 — Code Quality, Production Readiness & Action Agent v5

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

### 2B — MCP Tool Bidirectional Alignment

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
    miss_man = reg - man
    miss_reg = man - reg
    if miss_man or miss_reg:
        print(f"FAIL {name}: dead={miss_man} broken={miss_reg}")
        all_ok = False
    else:
        print(f"OK   {name}: {sorted(reg)}")
print("All aligned:", all_ok)
```

### 2C — Workspace toolIds

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

### 2D — Compose Profiles

```python
import yaml
dc = yaml.safe_load(open("deploy/portal-5/docker-compose.yml"))
svcs = dc["services"]

# Channel services in correct profiles
assert svcs.get("portal-telegram", {}).get("profiles") == ["telegram"], \
    "FAIL: portal-telegram not in telegram profile"
assert svcs.get("portal-slack", {}).get("profiles") == ["slack"], \
    "FAIL: portal-slack not in slack profile"
print("OK: channel services in correct profiles")

# Native services (Ollama + ComfyUI) must be profile-gated on Apple Silicon
for svc_name, expected_profile in [("ollama", "docker-ollama"),
                                    ("ollama-init", "docker-ollama"),
                                    ("comfyui", "docker-comfyui"),
                                    ("comfyui-model-init", "docker-comfyui")]:
    svc = svcs.get(svc_name, {})
    profiles = svc.get("profiles", [])
    if expected_profile in profiles:
        print(f"OK: {svc_name} behind profile [{expected_profile}]")
    else:
        print(f"FAIL: {svc_name} profiles={profiles} — should be [{expected_profile}]")
        print(f"      On Apple Silicon, {svc_name.split('-')[0]} runs natively (brew/git)")
        print(f"      Docker version causes port conflict on 11434/8188")

# MCP ports must be configurable (not hardcoded)
compose_str = open("deploy/portal-5/docker-compose.yml").read()
port_vars = ["WHISPER_HOST_PORT", "TTS_HOST_PORT", "DOCUMENTS_HOST_PORT",
             "MUSIC_HOST_PORT", "COMFYUI_MCP_HOST_PORT", "VIDEO_MCP_HOST_PORT",
             "SANDBOX_HOST_PORT"]
for var in port_vars:
    found = var in compose_str
    print(f"{'OK' if found else 'FAIL'}: {var} in docker-compose.yml")
```

### 2E — Dispatcher Coverage

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

for bot_file in ["portal_channels/telegram/bot.py", "portal_channels/slack/bot.py"]:
    src = open(bot_file).read()
    assert "import httpx" not in src, f"FAIL: {bot_file} imports httpx directly"
    assert "dispatcher" in src, f"FAIL: {bot_file} doesn't use dispatcher"
    print(f"OK: {bot_file} uses dispatcher")
```

### 2F — Sandbox Security Flags

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

### 2G — Launch Script Commands (UPDATED v5)

```bash
bash -n launch.sh && echo "PASS: syntax valid"

# Core operational commands
for cmd in up down clean clean-all seed logs status pull-models test \
           add-user list-users up-telegram up-slack up-channels \
           backup restore; do
    grep -q "^  ${cmd})" launch.sh && echo "PRESENT: $cmd" || echo "MISSING: $cmd"
done

# Native install commands (Apple Silicon — NEW in R20/R21/R23)
for cmd in install-ollama install-comfyui install-mlx \
           pull-mlx-models download-comfyui-models; do
    grep -q "${cmd}" launch.sh && echo "PRESENT: $cmd" || echo "MISSING: $cmd"
done

# 70B gate must exist
grep -q "PULL_HEAVY" launch.sh && echo "PRESENT: PULL_HEAVY gating" || echo "MISSING: PULL_HEAVY gating"
```

### 2H — Dockerfile Completeness and Channel Deployment Checks

```python
src = open("Dockerfile.mcp").read()

assert "COPY portal_mcp/ ./portal_mcp/" in src, \
    "FAIL: portal_mcp not copied into MCP image"
assert "COPY portal_channels/ ./portal_channels/" in src, \
    "FAIL: portal_channels not copied — portal-telegram/slack will crash"
mcp_pos = src.index("COPY portal_mcp/")
ch_pos  = src.index("COPY portal_channels/")
assert ch_pos > mcp_pos, "FAIL: COPY order wrong"
for pkg in ["python-telegram-bot", "slack-bolt"]:
    assert pkg in src, f"FAIL: {pkg} not installed in Dockerfile.mcp"
    print(f"OK: {pkg}")
print("OK: Dockerfile.mcp copies both portal_mcp/ and portal_channels/")
```

```python
import yaml
dc = yaml.safe_load(open("deploy/portal-5/docker-compose.yml"))
for svc_name in ["portal-telegram", "portal-slack"]:
    svc = dc["services"].get(svc_name, {})
    hc = svc.get("healthcheck")
    assert hc is not None, f"FAIL: {svc_name} has no healthcheck"
    assert hc.get("test"), f"FAIL: {svc_name} healthcheck has no test command"
    print(f"OK: {svc_name} healthcheck: {hc['test']}")
```

```bash
WRONG_PATTERN=$(grep -c '$(pwd)/${BACKUP_PATH}' launch.sh || echo 0)
[ "$WRONG_PATTERN" -eq 0 ] && echo "OK: backup uses realpath" \
    || echo "FAIL: backup still uses \$(pwd)/\${BACKUP_PATH}"
```

### 2I — Dispatcher Retry Test Coverage

```python
src = open("tests/unit/test_channels.py").read()
assert "test_call_pipeline_async_retries_on_500" in src, \
    "FAIL: async retry test missing"
assert "test_call_pipeline_sync_raises_after_exhausting_retries" in src, \
    "FAIL: sync retry exhaustion test missing"
print("OK: dispatcher retry tests present")
```

### 2J — Native Ollama + MLX Architecture (NEW v5)

```python
import yaml

# backends.yaml must NOT have hardcoded http://ollama:11434
backends_src = open("config/backends.yaml").read()
assert '"http://ollama:11434"' not in backends_src, \
    "FAIL: hardcoded http://ollama:11434 found — breaks native Ollama on macOS\n" \
    "      Must use: ${OLLAMA_URL:-http://host.docker.internal:11434}"
assert "OLLAMA_URL" in backends_src, \
    "FAIL: OLLAMA_URL env var not in backends.yaml"
print("OK: backends.yaml uses OLLAMA_URL env var")

# MLX backend must exist
cfg = yaml.safe_load(open("config/backends.yaml"))
mlx_backends = [b for b in cfg["backends"] if b.get("type") == "mlx"]
assert len(mlx_backends) >= 1, \
    "FAIL: No MLX backend in backends.yaml\n" \
    "      MLX inference is 20-40% faster than Ollama GGUF on Apple Silicon"
print(f"OK: {len(mlx_backends)} MLX backend(s) found")

# MLX models must be mlx-community tags
mlx_models = mlx_backends[0].get("models", [])
assert any("mlx-community" in m for m in mlx_models), \
    "FAIL: MLX backend has no mlx-community models"
assert any("Qwen3-Coder-Next" in m for m in mlx_models), \
    "FAIL: Qwen3-Coder-Next-4bit (primary coding model) missing from MLX backend"
print(f"OK: MLX backend has {len(mlx_models)} verified mlx-community models")

# MLX routing: key workspaces must prefer mlx group
routing = cfg.get("workspace_routing", {})
for ws in ["auto-coding", "auto-reasoning", "auto-research"]:
    groups = routing.get(ws, [])
    assert groups and groups[0] == "mlx", \
        f"FAIL: {ws} must list 'mlx' first — got {groups}"
    print(f"OK: {ws} → {groups}")

# Security workspaces must NOT use MLX (no MLX versions for BaronLLM etc)
for ws in ["auto-security", "auto-redteam", "auto-blueteam"]:
    groups = routing.get(ws, [])
    assert "mlx" not in groups, \
        f"FAIL: {ws} includes mlx — security models have no MLX versions"
    print(f"OK: {ws} Ollama-only → {groups}")

# MiniMax-M2-4bit must NOT be in MLX backend (129GB, too large for 64GB)
if mlx_backends:
    for m in mlx_backends[0].get("models", []):
        assert "MiniMax-M2-4bit" not in m, \
            f"FAIL: MiniMax-M2-4bit (129GB) in MLX backend — exceeds 64GB unified memory"
print("OK: MiniMax-M2-4bit correctly excluded from MLX backend")

# cluster_backends.py must handle mlx type
cb_src = open("portal_pipeline/cluster_backends.py").read()
assert "mlx" in cb_src, \
    "FAIL: cluster_backends.py does not handle 'mlx' backend type"
assert "v1/models" in cb_src, \
    "FAIL: MLX health URL must use /v1/models endpoint"
print("OK: cluster_backends.py handles mlx type")
```

### 2K — Boot Reliability Checks (NEW v5)

```bash
# Disk check must use python3, not df -BG (Linux-only flag)
grep "df -BG" launch.sh && echo "FAIL: df -BG is Linux-only, breaks on macOS" \
    || echo "OK: df -BG not present"
grep "shutil.disk_usage\|python3.*shutil" launch.sh && echo "OK: macOS-compatible disk check" \
    || echo "FAIL: disk check may not work on macOS"

# CHANGEME repair — validation must not hard-exit on CHANGEME
REPAIR_PATTERN=$(grep -c "_repair=0\|_new_secret" launch.sh || echo 0)
[ "$REPAIR_PATTERN" -ge 2 ] && echo "OK: inline CHANGEME repair present" \
    || echo "FAIL: missing inline secret repair — will loop on interrupted first run"

# local keyword must NOT appear outside functions in case blocks
bash -n launch.sh && echo "OK: launch.sh syntax valid" || echo "FAIL: launch.sh syntax error"

# OPENWEBUI_ADMIN_EMAIL must have default in compose
grep "OPENWEBUI_ADMIN_EMAIL:-" deploy/portal-5/docker-compose.yml \
    && echo "OK: OPENWEBUI_ADMIN_EMAIL has default" \
    || echo "FAIL: OPENWEBUI_ADMIN_EMAIL has no default — blank string warning on boot"

# ComfyUI must have platform spec (silences ARM warning)
grep "platform: linux/amd64" deploy/portal-5/docker-compose.yml \
    && echo "OK: ComfyUI platform spec present" \
    || echo "FAIL: ComfyUI missing platform: linux/amd64 — ARM mismatch warning on M4"
```

### 2L — MLX Backend Model Compatibility

```python
# Verify no mlx-vlm (vision) models are active in MLX backend
# mlx_lm.server cannot load mlx-vlm conversions

import yaml
cfg = yaml.safe_load(open("config/backends.yaml"))
mlx_backends = [b for b in cfg["backends"] if b.get("type") == "mlx"]
for b in mlx_backends:
    for model in b.get("models", []):
        # Check if model was commented out (shouldn't be here if active)
        if "Qwen3.5" in model:
            print(f"  ⚠️  {model} — verify this is an mlx-lm conversion, not mlx-vlm")
            print(f"     mlx-vlm models will fail to load in mlx_lm.server")
print("MLX model compatibility check complete")
```

### 2M — Melody Conditioning Implementation

```python
# Verify generate_continuation actually uses melody conditioning
music_src = open("portal_mcp/generation/music_mcp.py").read()
assert "generate_with_chroma" in music_src, \
    "FAIL: generate_continuation does not use AudioCraft melody conditioning"
assert "_generate_with_melody_sync" in music_src, \
    "FAIL: _generate_with_melody_sync function missing"
print("OK: Melody conditioning implemented")
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
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9099/v1/models)
echo "No-auth → $STATUS (expect 401)"
kill $PIPE_PID 2>/dev/null; wait $PIPE_PID 2>/dev/null
```

### 3B — BackendRegistry (UPDATED v5 — includes MLX backend test)

```python
import sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")
from portal_pipeline.cluster_backends import BackendRegistry, Backend

# Test mlx backend type health URL
b_mlx = Backend(id="t-mlx", type="mlx", url="http://localhost:8081", group="mlx",
                models=["mlx-community/Qwen3-Coder-Next-4bit"])
assert "/v1/models" in b_mlx.health_url, \
    f"FAIL: MLX health_url should use /v1/models, got: {b_mlx.health_url}"
print(f"OK: mlx health_url = {b_mlx.health_url}")

# Test ollama backend health URL
b_ol = Backend(id="t-ol", type="ollama", url="http://localhost:11434", group="g", models=[])
assert "/api/tags" in b_ol.health_url
print(f"OK: ollama health_url = {b_ol.health_url}")

# Test real config loads
reg = BackendRegistry(config_path="config/backends.yaml")
print(f"timeout={reg.request_timeout} interval={reg._health_check_interval}")
assert reg.request_timeout >= 60, f"FAIL: timeout too low: {reg.request_timeout}"

# Test MLX backend present in loaded config
mlx_backends = [b for b in reg._backends.values() if b.type == "mlx"]
print(f"MLX backends loaded: {len(mlx_backends)}")
assert len(mlx_backends) >= 1, "FAIL: No MLX backend loaded from backends.yaml"

# Test unhealthy fallback
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
from portal_channels.dispatcher import is_valid_workspace, VALID_WORKSPACES
from portal_pipeline.router_pipe import WORKSPACES
assert set(VALID_WORKSPACES) == set(WORKSPACES.keys()), "FAIL: dispatcher out of sync"
assert is_valid_workspace("auto-coding")
assert not is_valid_workspace("auto-nonexistent")
print("OK: dispatcher correct")

for key in ("TELEGRAM_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
    os.environ.pop(key, None)
import importlib
for mod in ("portal_channels.telegram.bot", "portal_channels.slack.bot"):
    if mod in sys.modules: del sys.modules[mod]
    m = importlib.import_module(mod)
    assert hasattr(m, "build_app")
    print(f"OK: {mod} importable without token")
```

### 3E — Verification Matrix

```
CHECK                                           | RESULT | SOURCE
------------------------------------------------|--------|-------
Pipeline /health 200                            |        | 3A
Pipeline /v1/models 401 without auth            |        | 3A
Pipeline returns 13 workspaces                  |        | 3A
Pipeline /metrics has 4+ gauges                 |        | 3A
MLX backend type loads from backends.yaml       |        | 3B
MLX health_url uses /v1/models                  |        | 3B
Ollama health_url uses /api/tags                |        | 3B
timeout=120 from YAML                           |        | 3B
all-unhealthy returns None                      |        | 3B
All 7 MCP /health return 200                    |        | 3C
All 7 MCP tools non-empty                       |        | 3C
MCP TOOLS_MANIFEST bidirectional (7/7)          |        | 2B
workspace toolIds correct (13/13)               |        | 2C
Dispatcher covers all 13 workspaces             |        | 2D/2E
Bots don't import httpx directly                |        | 2E
Sandbox has 10 security flags                   |        | 2F
Channel services in correct profiles            |        | 2D
Ollama behind docker-ollama profile             |        | 2D
ComfyUI behind docker-comfyui profile           |        | 2D
MCP ports use env var overrides (7 vars)        |        | 2D
backends.yaml uses OLLAMA_URL env var           |        | 2J
No hardcoded http://ollama:11434                |        | 2J
MLX backend present in backends.yaml            |        | 2J
mlx-community/Qwen3-Coder-Next-4bit in MLX     |        | 2J
auto-coding routes to mlx first                 |        | 2J
auto-security skips MLX (Ollama-only)           |        | 2J
MiniMax-M2-4bit excluded from MLX (129GB)       |        | 2J
cluster_backends.py handles mlx type            |        | 2J
launch.sh has install-ollama                    |        | 2G
launch.sh has install-comfyui                   |        | 2G
launch.sh has install-mlx                       |        | 2G
launch.sh has pull-mlx-models                   |        | 2G
launch.sh has download-comfyui-models           |        | 2G
launch.sh has PULL_HEAVY gating                 |        | 2G
Disk check uses python3 shutil (not df -BG)     |        | 2K
CHANGEME inline repair present                  |        | 2K
OPENWEBUI_ADMIN_EMAIL has default               |        | 2K
ComfyUI platform: linux/amd64                   |        | 2K
3-source workspace consistency                  |        | 2A
Dispatcher retry tests present (2/2)            |        | 2I
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

Dimensions: Security / Sandbox / Multi-user / Routing / MLX inference /
Native install / Capacity / Zero-setup / Model catalog / Ops tooling /
Test coverage / Code quality / Docs / Deploy / Channel integrity / MCP alignment

### P5_ACTION_PROMPT.md
Bootstrap block (installs `[dev,mcp,channels]`) + TASK-NNN items.

### P5_ROADMAP.md
Preserve P5-ROAD-NNN IDs. Add new items for BROKEN/STUB findings.

**COMPLIANCE CHECK**
- Hard constraints met: Yes/No
- All findings backed by evidence: Yes/No
- Uncertainty Log: [<90% confidence or "None"]
