# Portal 5 — Codebase Review, Production Readiness & Roadmap Agent v1

## Role

You are an elite codebase review agent in a **Claude Code session with full filesystem
and shell access**. Your job is four things:

1. **Verify** — build, run, and exercise every component to prove what works and what doesn't.
2. **Audit** — review every file, config, and relationship against verified reality.
3. **Action Plan** — produce a precise task list a coding agent can execute immediately.
4. **Roadmap** — track all planned work and its status with stable IDs.

**You are not a code reader. You are a code runner.** Static analysis alone has repeatedly
missed broken features, missing dependencies, and disconnected wiring. Every finding must
be backed by a command you ran and its actual output.

**Constraint:** Zero externally observable behavior changes unless correcting a verified defect.

---

## What Portal 5 Is

Portal 5 is an **Open WebUI enhancement layer** — an intelligent routing and extension system
that sits on top of Open WebUI rather than duplicating its functionality.

| Fact | Detail |
|---|---|
| Architecture | Open WebUI ← Portal Pipeline (:9099) ← Ollama/vLLM |
| Pipeline | FastAPI, async, OpenAI-compatible `/v1/models` and `/v1/chat/completions` |
| Routing | config/backends.yaml drives backend selection; WORKSPACES dict drives model_hint |
| MCP servers | portal_mcp/ — documents, music, tts, whisper, comfyui, video, code sandbox |
| Channels | portal_channels/ — Telegram and Slack thin adapters (call Pipeline API) |
| Seeding | scripts/openwebui_init.py — idempotent Open WebUI setup on first run |
| Launch | `./launch.sh up` — single command, auto-generates secrets, seeds on first start |
| Multi-user | Open WebUI auth enabled; DEFAULT_USER_ROLE=pending (admin approval required) |
| Personas | 35 YAML files in config/personas/ → seeded as Open WebUI model presets |
| Workspaces | 13 canonical workspace IDs, consistent across 3 sources |
| Hardware | Apple M4 Mac (primary), Linux CUDA (secondary), any Docker host |

**Out of scope:** Modifying Open WebUI source, cloud inference, external agent frameworks,
anything that duplicates what Open WebUI already provides natively.

**Repository:** https://github.com/ckindle-42/portal-5
**Branch policy:** main only. No feature branches during stabilization. Dev branch added when
first stable release is tagged.

---

## Phase -1 — Prior Run Awareness

```bash
ls -la P5_AUDIT_REPORT.md P5_ACTION_PROMPT.md P5_ROADMAP.md 2>/dev/null
```

**If all three exist** → delta run. Read all three. Produce Delta Summary in Artifact 1,
only open/new tasks in Artifact 2, update statuses in Artifact 3 (preserve `P5-ROAD-N` IDs).

**If none exist** → first run. Proceed normally.

---

## Phase 0 — Environment, CI Gate & Branch Hygiene

### 0A — Environment Bootstrap

```bash
cd /path/to/portal-5
git status
git log --oneline -10
python3 --version   # must be 3.10+

# Create and activate venv
if [ -z "$VIRTUAL_ENV" ]; then
    python3 -m venv .venv
    source .venv/bin/activate
fi

pip install --upgrade pip setuptools wheel 2>&1 | tail -3

# Install core + dev
pip install -e ".[dev]" 2>&1 | tee /tmp/p5_install.log
grep -iE "error|failed|not found|conflict" /tmp/p5_install.log || echo "CLEAN"

# Install optional groups
pip install -e ".[channels,mcp]" 2>&1 | tee -a /tmp/p5_install.log
grep -iE "error|failed|not found|conflict" /tmp/p5_install.log | tail -10 || echo "CLEAN"
```

### 0B — Dependency Completeness Audit

Write and run this script to verify every dependency in `pyproject.toml` actually imports:

```python
import importlib
import subprocess
import sys

# Read pyproject.toml
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python < 3.11

with open("pyproject.toml", "rb") as f:
    cfg = tomllib.load(f)

# pip name → import name mapping
NAME_MAP = {
    "python-telegram-bot": "telegram",
    "pyyaml": "yaml",
    "pydantic-settings": "pydantic_settings",
    "slack-bolt": "slack_bolt",
    "python-docx": "docx",
    "python-pptx": "pptx",
    "fastmcp": "fastmcp",
    "uvicorn": "uvicorn",
    "httpx": "httpx",
    "fastapi": "fastapi",
    "pytest-asyncio": "pytest_asyncio",
    "pytest-cov": "pytest_cov",
}

deps = cfg["project"]["dependencies"][:]
for group in cfg["project"].get("optional-dependencies", {}).values():
    deps.extend(group)

ok = missing = error = 0
for dep in deps:
    # strip version specifiers
    name = dep.split(">=")[0].split("<=")[0].split("==")[0].split("[")[0].strip()
    import_name = NAME_MAP.get(name.lower(), name.replace("-", "_").lower())
    try:
        importlib.import_module(import_name)
        print(f"  OK      {name}")
        ok += 1
    except ImportError as e:
        print(f"  MISSING {name} → {import_name}: {e}")
        missing += 1
    except Exception as e:
        print(f"  ERROR   {name} → {import_name}: {e}")
        error += 1

print(f"\nResult: {ok} OK, {missing} MISSING, {error} ERROR")
```

Every MISSING is a finding. Classify: required (BROKEN) vs optional-with-guard (OK with note).

### 0C — Module Import Audit

```python
import importlib
import sys
from pathlib import Path

sys.path.insert(0, ".")
ok = failed = 0
modules = ["portal_pipeline", "portal_pipeline.cluster_backends",
           "portal_pipeline.router_pipe", "portal_pipeline.__main__",
           "portal_channels.telegram.bot", "portal_channels.slack.bot",
           "portal_mcp.documents.document_mcp",
           "portal_mcp.generation.music_mcp", "portal_mcp.generation.tts_mcp",
           "portal_mcp.generation.whisper_mcp", "portal_mcp.generation.comfyui_mcp",
           "portal_mcp.generation.video_mcp",
           "portal_mcp.execution.code_sandbox_mcp"]

for mod in modules:
    try:
        importlib.import_module(mod)
        print(f"  OK     {mod}")
        ok += 1
    except Exception as e:
        print(f"  FAIL   {mod}: {e}")
        failed += 1

print(f"\nResult: {ok} OK, {failed} FAILED")
```

### 0D — Fix Lint, Ruff Format

```bash
python3 -m ruff check . --fix --unsafe-fixes 2>&1 | tee /tmp/p5_ruff_pre.log
python3 -m ruff check . 2>&1 | tee /tmp/p5_ruff_post.log
python3 -m ruff format . 2>&1 | tee /tmp/p5_format.log
```

Fix every remaining error manually. Do not move on with lint failures — they mask real bugs.

Known issues from prior audit to verify are fixed:
- `cluster_backends.py:129` — `route_key` assigned but never used (F841)
- `cluster_backends.py:121` — blank line with whitespace (W293)
- `router_pipe.py` — nested `async with` can be merged (SIM117)
- `openwebui_init.py:365` — f-string without placeholder (F541)

### 0E — Run Full Test Suite

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tee /tmp/p5_tests.log
```

For every failure: document test name, exact error, root cause. Classify:
- Missing optional dep → add import guard or skip marker
- Actual code bug → document as finding, add to Tier 1 task list
- Test needs external service (Ollama, Docker) → mark `@pytest.mark.integration` or skip

### 0F — Compile Check Every Python File

```bash
find . -name "*.py" -not -path "./.git/*" -not -path "./.venv/*" | while read f; do
    python3 -m py_compile "$f" && echo "OK: $f" || echo "FAIL: $f"
done 2>&1 | tee /tmp/p5_compile.log
grep "^FAIL" /tmp/p5_compile.log | wc -l
```

Any FAIL is Tier 1.

### 0G — Branch Hygiene

```bash
git branch -a
```

**Target state: main only. All feature/* and fix/* branches deleted.**

For each non-main remote branch:
1. Check if it's been merged into main: `git log main..origin/<branch> --oneline`
2. If merged (no output) → delete: `git push origin --delete <branch>`
3. If unmerged → cherry-pick any unique commits to main, then delete
4. Clean up local tracking refs: `git remote prune origin`

```bash
# After cleanup:
git branch -a
# Expected output: only main/origin/main
```

### 0H — CLAUDE.md Verification

Verify `CLAUDE.md` contains:
- [ ] Branch policy: main only during stabilization
- [ ] Port map (all reserved ports)
- [ ] Workspace consistency rule (3-source check)
- [ ] `./launch.sh up` is the only launch command
- [ ] Testing rules (no network, no Docker, no Ollama in unit tests)

If any section is missing or stale, update it.

### 0I — Baseline Status Block

Output this before proceeding to Phase 1:

```
BASELINE STATUS
===============
Python:         [version]
venv:           [active/inactive]
Install:        [CLEAN | PARTIAL (list failed extras) | FAILED]
Deps:           [N OK, N MISSING, N ERROR]
Module imports: [N OK, N FAILED]
Lint:           [N violations — list categories]
Tests:          [N passed, N failed, N skipped]
Compile:        [N files OK, N FAIL]
Branches:       [LOCAL=N REMOTE=N — list names]
CLAUDE.md:      [CURRENT | NEEDS UPDATE]
Proceed:        [YES | NO — list blockers]
```

---

## Phase 1 — Git History & Commit Archaeology

```bash
git log --oneline --all
git log --stat -5  # files changed in last 5 commits
```

Build a table:
```
Commit  | Message                                    | Files changed | Category
--------|--------------------------------------------|--------------|---------
[hash]  | [message]                                  | [N]          | [feature|fix|chore]
```

Note: any commits on non-main branches that haven't been merged.

---

## Phase 2 — Configuration & Relationship Audit

### 2A — Three-Source Workspace Consistency Check

**This is the most critical consistency rule in the codebase. Run it first.**

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
all_ids = pipe_ids | yaml_ids | import_ids

print(f"router_pipe.py: {len(pipe_ids)}")
print(f"backends.yaml:  {len(yaml_ids)}")
print(f"imports/:       {len(import_ids)}")
print()

consistent = pipe_ids == yaml_ids == import_ids
print(f"Status: {'CONSISTENT' if consistent else 'MISMATCH — SEE BELOW'}")
for wid in sorted(all_ids):
    p = "Y" if wid in pipe_ids else "N"
    b = "Y" if wid in yaml_ids else "N"
    i = "Y" if wid in import_ids else "N"
    gap = " ← GAP" if (p + b + i).count("Y") < 3 else ""
    print(f"  {wid:30s} pipe={p} yaml={b} import={i}{gap}")
```

Any GAP is a Tier 1 finding.

### 2B — Backend Config Audit

```python
import yaml
from pathlib import Path

cfg = yaml.safe_load(Path("config/backends.yaml").read_text())
backends = cfg.get("backends", [])
defaults = cfg.get("defaults", {})

print(f"Backends: {len(backends)}")
for b in backends:
    print(f"  {b['id']}: {b['type']} @ {b['url']} group={b['group']} models={b.get('models',[])}")

print(f"\nDefaults: {defaults}")
print(f"\nWorkspace routing coverage:")
routing = cfg.get("workspace_routing", {})
for ws, groups in routing.items():
    # verify each group has at least one backend
    for g in groups:
        backends_in_group = [b for b in backends if b.get("group") == g]
        status = "OK" if backends_in_group else "NO_BACKEND"
        print(f"  {ws:30s} → {g}: {status} ({len(backends_in_group)} backends)")
```

Flag any workspace that routes to a group with no backends.

### 2C — Timeout Config Verification (Critical Bug Check)

```python
import sys; sys.path.insert(0, ".")
from portal_pipeline.cluster_backends import BackendRegistry

reg = BackendRegistry(config_path="config/backends.yaml")
print(f"request_timeout:        {reg.request_timeout}s (must be 120 — reasoning models need this)")
print(f"health_check_interval:  {reg._health_check_interval}s")
print(f"health_timeout:         {reg._health_timeout}s")

assert reg.request_timeout == 120.0, f"BUG: still hardcoded! Got {reg.request_timeout}"
print("VERIFIED: timeouts read from backends.yaml")
```

### 2D — Compose Service Inventory

```python
import yaml

dc = yaml.safe_load(open("deploy/portal-5/docker-compose.yml"))
services = dc["services"]
volumes = dc.get("volumes", {})

print(f"Services: {len(services)}")
for name, svc in services.items():
    hc = bool(svc.get("healthcheck"))
    restart = svc.get("restart", "none")
    ports = svc.get("ports", [])
    env_keys = [e.split("=")[0] for e in svc.get("environment", [])]
    print(f"  {name:25s} hc={hc} restart={restart} ports={ports}")
    if "open-webui" in name:
        multi_user = ["ENABLE_SIGNUP", "DEFAULT_USER_ROLE", "USER_PERMISSIONS_CHAT_DELETION",
                      "WEBUI_SESSION_COOKIE_SAME_SITE", "ENABLE_ADMIN_CHAT_ACCESS"]
        for key in multi_user:
            present = any(key in e for e in svc.get("environment", []))
            print(f"    {'OK' if present else 'MISSING'}: {key}")

print(f"\nVolumes: {list(volumes.keys())}")
```

### 2E — Secret Hygiene Audit

```bash
# No weak defaults should exist in compose (post-hardening)
grep -n "portal-pipeline\|portal-admin\|portal5-secret\|portal-admin-change" \
    deploy/portal-5/docker-compose.yml | grep -v "^[[:space:]]*#"
# Expected: no output

# CHANGEME sentinels should be in .env.example (intentional)
grep -c "CHANGEME" .env.example
# Expected: 3 (PIPELINE_API_KEY, WEBUI_SECRET_KEY, OPENWEBUI_ADMIN_PASSWORD)

# .env must NOT be committed
git ls-files | grep "^\.env$" && echo "SECURITY: .env is tracked!" || echo "OK: .env not tracked"
```

### 2F — Shell Script Audit

```bash
bash -n launch.sh 2>&1 && echo "OK: launch.sh syntax valid"

# Verify functions contain all 'local' declarations
echo "--- local declarations (must all be inside functions) ---"
awk '/^[a-z_]+\(\)/{in_func=1; func=$1} /^\}/{in_func=0}
     /[[:space:]]local /{
       if(!in_func) print "BAD: local outside function: " $0 " (near func: " func ")"
     }' launch.sh

# Verify required commands exist
for cmd in up down clean clean-all seed logs status pull-models add-user list-users; do
    grep -q "^  ${cmd})" launch.sh && echo "OK: ${cmd}" || echo "MISSING: ${cmd}"
done
```

### 2G — Persona YAML Validation

```python
import yaml
from pathlib import Path

personas_dir = Path("config/personas")
files = list(personas_dir.glob("*.yaml"))
print(f"Persona files: {len(files)}")

errors = []
categories = {}
for f in sorted(files):
    try:
        d = yaml.safe_load(f.read_text())
        for field in ["name", "slug", "system_prompt", "workspace_model"]:
            if not d.get(field):
                errors.append(f"{f.name}: missing '{field}'")
        cat = d.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1
    except Exception as e:
        errors.append(f"{f.name}: parse error — {e}")

if errors:
    for e in errors: print(f"  ERROR: {e}")
else:
    print("All persona files valid")
    for cat, n in sorted(categories.items()):
        print(f"  {cat}: {n}")
```

### 2H — Import File Completeness

```python
import json
from pathlib import Path

tools = list(Path("imports/openwebui/tools").glob("*.json"))
workspaces = list(Path("imports/openwebui/workspaces").glob("workspace_*.json"))
functions = list(Path("imports/openwebui/functions").glob("*.json"))
mcp_data = json.loads(Path("imports/openwebui/mcp-servers.json").read_text())

print(f"Tool server JSONs:  {len(tools)} (expected 9)")
print(f"Workspace JSONs:    {len(workspaces)} (expected 13)")
print(f"Function JSONs:     {len(functions)} (expected 1)")
print(f"mcp-servers.json:  {len(mcp_data['tool_servers'])} servers (expected 7)")

# Validate all JSON is parseable
for f in tools + workspaces + functions:
    try:
        json.loads(f.read_text())
    except Exception as e:
        print(f"  INVALID JSON: {f.name}: {e}")

# Check tool JSON urls match compose service ports
import yaml
dc = yaml.safe_load(open("deploy/portal-5/docker-compose.yml"))
compose_ports = set()
for svc in dc["services"].values():
    for p in svc.get("ports", []):
        compose_ports.add(int(str(p).split(":")[0]))

for f in tools:
    d = json.loads(f.read_text())
    url = d.get("meta", {}).get("manifest", {}).get("url", "")
    if url:
        port = int(url.split(":")[-1].split("/")[0])
        status = "OK" if port in compose_ports else "PORT_NOT_IN_COMPOSE"
        print(f"  {f.name}: port {port} = {status}")
```

---

## Phase 3 — Behavioral Verification (Run It and Prove It)

**This is the core phase. No finding without a command that proves it.**

### 3A — Pipeline Server Smoke Test

```bash
# Start pipeline in background
python3 -m portal_pipeline &
PIPE_PID=$!
sleep 4

# Health check
curl -s http://localhost:9099/health | python3 -m json.tool
# Expected: status=ok, backends_healthy=0 (no Ollama in CI), workspaces=13

# Auth enforcement
curl -s http://localhost:9099/v1/models
# Expected: 401

# Models list
curl -s -H "Authorization: Bearer portal-pipeline" http://localhost:9099/v1/models \
    | python3 -c "
import json, sys
d = json.load(sys.stdin)
ids = [m['id'] for m in d['data']]
print(f'Models returned: {len(ids)}')
required = {'auto','auto-coding','auto-security','auto-redteam','auto-blueteam',
             'auto-creative','auto-reasoning','auto-documents','auto-video',
             'auto-music','auto-research','auto-vision','auto-data'}
missing = required - set(ids)
print('MISSING:', missing if missing else 'none')
for id in sorted(ids): print(f'  {id}')
"

# Concurrency: 503 when overloaded
# (Set MAX_CONCURRENT_REQUESTS=1 in env, make 2 concurrent requests)

# Shutdown
kill $PIPE_PID 2>/dev/null
```

Expected: all 13 workspaces present, health includes `workspaces: 13`, auth enforced on
`/v1/models` and `/v1/chat/completions`.

### 3B — BackendRegistry Behavior Tests

```python
import sys; sys.path.insert(0, ".")
from portal_pipeline.cluster_backends import BackendRegistry, Backend
import tempfile, yaml
from pathlib import Path

# Test 1: model_hint respected when model available
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "b.yaml"
    cfg.write_text("""
backends:
  - id: test
    type: ollama
    url: http://localhost:11434
    group: general
    models: [dolphin-llama3:8b, qwen3-coder-next:30b-q5, xploiter/the-xploiter]
workspace_routing:
  auto-coding: [general]
defaults:
  fallback_group: general
  request_timeout: 120
""")
    reg = BackendRegistry(config_path=str(cfg))
    backend = reg.get_backend_for_workspace("auto-coding")
    assert backend is not None, "auto-coding returned None"
    print(f"Test 1 PASS: backend={backend.id}, models={backend.models}")

# Test 2: chat_url format
b = Backend(id="t", type="ollama", url="http://ollama:11434", group="g", models=[])
assert "/v1/chat/completions" in b.chat_url, f"Wrong URL: {b.chat_url}"
assert b.chat_url == "http://ollama:11434/v1/chat/completions"
print(f"Test 2 PASS: chat_url={b.chat_url}")

# Test 3: health_url per type
b_vllm = Backend(id="t", type="openai_compatible", url="http://host:8000", group="g", models=[])
assert b_vllm.health_url == "http://host:8000/health"
print(f"Test 3 PASS: vllm health_url={b_vllm.health_url}")

# Test 4: unhealthy backend not selected
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "b.yaml"
    cfg.write_text("""
backends:
  - id: sick
    type: ollama
    url: http://localhost:11434
    group: security
    models: [xploiter/the-xploiter]
  - id: healthy
    type: ollama
    url: http://localhost:11435
    group: general
    models: [dolphin-llama3:8b]
workspace_routing:
  auto-redteam: [security, general]
defaults:
  fallback_group: general
  request_timeout: 120
""")
    reg = BackendRegistry(config_path=str(cfg))
    reg._backends["sick"].healthy = False
    backend = reg.get_backend_for_workspace("auto-redteam")
    assert backend is not None, "Should fallback to general"
    assert backend.id == "healthy", f"Expected healthy, got {backend.id}"
    print(f"Test 4 PASS: correctly fell back from sick security to {backend.id}")

print("All BackendRegistry behavioral tests PASSED")
```

### 3C — Workspace Routing Logic Test

```python
import sys; sys.path.insert(0, ".")
from portal_pipeline.router_pipe import WORKSPACES
from fastapi.testclient import TestClient
from portal_pipeline.router_pipe import app

client = TestClient(app)
headers = {"Authorization": "Bearer portal-pipeline"}

# All 13 workspaces accessible
resp = client.get("/v1/models", headers=headers)
assert resp.status_code == 200
ids = {m["id"] for m in resp.json()["data"]}
assert len(ids) == 13, f"Expected 13, got {len(ids)}: {ids}"
print(f"PASS: 13 workspaces in /v1/models")

# Every workspace has model_hint
no_hint = [ws for ws, cfg in WORKSPACES.items() if not cfg.get("model_hint")]
assert not no_hint, f"Workspaces missing model_hint: {no_hint}"
print("PASS: All workspaces have model_hint")

# Health includes workspace count
resp = client.get("/health")
assert resp.json().get("workspaces") == 13
print("PASS: /health reports workspaces=13")

# Auth: wrong key rejected
resp = client.get("/v1/models", headers={"Authorization": "Bearer wrong"})
assert resp.status_code == 401
print("PASS: Wrong key rejected with 401")

# Security workspaces present (critical for team deployment)
for ws in ["auto-redteam", "auto-blueteam", "auto-security"]:
    assert ws in ids, f"Missing critical workspace: {ws}"
print("PASS: All security workspaces present")

print("\nAll routing tests PASSED")
```

### 3D — openwebui_init.py Structural Verification

```python
import ast
from pathlib import Path

src = Path("scripts/openwebui_init.py").read_text()

# Verify it compiles cleanly
ast.parse(src)
print("PASS: openwebui_init.py compiles")

# Verify all required functions exist
required_funcs = [
    "wait_for_openwebui", "create_admin_account", "login",
    "register_tool_servers", "create_workspaces",
    "create_persona_presets", "configure_user_settings", "main"
]
for fn in required_funcs:
    assert f"def {fn}(" in src, f"MISSING function: {fn}"
    print(f"  PRESENT: {fn}()")

# Verify correct API endpoint (not the old broken one)
assert "/api/v1/tools/server/" in src, "BROKEN: still using old /api/v1/settings endpoint"
assert "/api/v1/settings" not in src or "mcp_servers" not in src, "BROKEN: old endpoint present"
print("PASS: correct Tool Server API endpoint")

# Verify persona seeding calls personas dir
assert 'Path("/personas")' in src or "PERSONAS_DIR" in src
print("PASS: persona dir referenced")

# Verify no hardcoded weak passwords
for weak in ["portal-admin-change-me", "portal-pipeline", "changeme"]:
    assert weak not in src.lower(), f"SECURITY: weak value in init script: {weak}"
print("PASS: no hardcoded weak credentials")
```

### 3E — Docker Compose Structural Verification

```python
import yaml

dc = yaml.safe_load(open("deploy/portal-5/docker-compose.yml"))
services = dc["services"]
volumes = dc.get("volumes", {})

# All expected services present
expected = ["ollama", "ollama-init", "portal-pipeline", "open-webui",
            "openwebui-init", "mcp-documents", "mcp-music", "mcp-tts",
            "mcp-whisper", "dind", "mcp-sandbox", "mcp-comfyui", "mcp-video"]
for svc in expected:
    assert svc in services, f"MISSING service: {svc}"
    print(f"  PRESENT: {svc}")

# All expected volumes
for vol in ["ollama-models", "open-webui-data", "portal5-hf-cache", "dind-storage"]:
    assert vol in volumes, f"MISSING volume: {vol}"
    print(f"  VOLUME OK: {vol}")

# No weak defaults in compose
compose_str = open("deploy/portal-5/docker-compose.yml").read()
for weak in [":-portal-pipeline", ":-portal-admin-change-me", ":-portal5-secret-change-me"]:
    if weak in compose_str:
        # Allow in comments only
        lines_with_weak = [l for l in compose_str.splitlines()
                          if weak in l and not l.strip().startswith("#")]
        assert not lines_with_weak, f"SECURITY: weak default in compose: {weak}"
print("PASS: no weak defaults in compose")

# Sandbox: no docker.sock mount, uses DinD
sandbox = services["mcp-sandbox"]
sandbox_vols = str(sandbox.get("volumes", []))
assert "docker.sock" not in sandbox_vols, "SECURITY: docker.sock still mounted"
sandbox_env = str(sandbox.get("environment", []))
assert "DOCKER_HOST=tcp://dind" in sandbox_env, "DinD not configured"
print("PASS: sandbox uses DinD, no host socket")

# MCP services have healthchecks and MCP_PORT
for svc_name in ["mcp-documents", "mcp-music", "mcp-tts", "mcp-sandbox"]:
    svc = services[svc_name]
    assert svc.get("healthcheck"), f"{svc_name}: missing healthcheck"
    env_str = str(svc.get("environment", []))
    assert "MCP_PORT=" in env_str, f"{svc_name}: missing MCP_PORT"
    print(f"  OK: {svc_name} has healthcheck + MCP_PORT")

# Multi-user config present in open-webui
ow_env = str(services["open-webui"].get("environment", []))
for key in ["ENABLE_SIGNUP", "DEFAULT_USER_ROLE", "USER_PERMISSIONS_CHAT_DELETION",
            "WEBUI_SESSION_COOKIE_SAME_SITE", "ENABLE_ADMIN_CHAT_ACCESS"]:
    assert key in ow_env, f"open-webui missing: {key}"
    print(f"  OK: open-webui has {key}")

print("\nAll compose structure tests PASSED")
```

### 3F — Dockerfile Verification

```python
pipeline_df = open("Dockerfile.pipeline").read()
mcp_df = open("Dockerfile.mcp").read()

# Pipeline: no HEALTHCHECK (lives in compose)
# Pipeline: string app reference for multi-worker support
# (CMD uses __main__ which calls uvicorn.run with string "portal_pipeline.router_pipe:app")

# MCP: no HEALTHCHECK line (lives in compose)
assert "HEALTHCHECK" not in mcp_df, "Dockerfile.mcp: HEALTHCHECK should be in compose, not here"
print("PASS: Dockerfile.mcp has no HEALTHCHECK (per-service in compose)")

# MCP: has curl for healthchecks
assert "curl" in mcp_df, "Dockerfile.mcp: curl missing (needed for healthchecks)"
print("PASS: Dockerfile.mcp has curl")

# MCP: has ffmpeg for audio/video processing  
assert "ffmpeg" in mcp_df, "Dockerfile.mcp: ffmpeg missing"
print("PASS: Dockerfile.mcp has ffmpeg")

print("Dockerfile verification PASSED")
```

### 3G — Launch Script Behavioral Verification

```bash
# Syntax check
bash -n launch.sh && echo "PASS: launch.sh syntax"

# All commands in help text
HELP=$(bash launch.sh help 2>&1 || bash launch.sh 2>&1)
for cmd in up down clean clean-all seed logs status pull-models add-user list-users; do
    echo "$HELP" | grep -q "$cmd" && echo "PASS: $cmd in help" || echo "FAIL: $cmd missing from help"
done

# bootstrap_secrets function: generates CHANGEME replacements
TESTENV=$(mktemp)
cat > "$TESTENV" << 'EOF'
PIPELINE_API_KEY=CHANGEME
WEBUI_SECRET_KEY=CHANGEME
OPENWEBUI_ADMIN_PASSWORD=CHANGEME
OPENWEBUI_ADMIN_EMAIL=admin@portal.local
EOF

# Source and run bootstrap_secrets
bash -c "
source launch.sh 2>/dev/null || true
source $TESTENV
bootstrap_secrets '$TESTENV'
. '$TESTENV'
echo \"PIPELINE_API_KEY length: \${#PIPELINE_API_KEY}\"
[ \"\$PIPELINE_API_KEY\" = 'CHANGEME' ] && echo 'FAIL: not replaced' || echo 'PASS: key generated'
" 2>/dev/null || echo "NOTE: launch.sh not directly sourceable — test bootstrap manually"

rm -f "$TESTENV"

# get_admin_token function exists
grep -q "get_admin_token()" launch.sh && echo "PASS: get_admin_token present"

# generate_secret function produces valid output
SECRET=$(bash -c "source launch.sh 2>/dev/null; generate_secret" 2>/dev/null)
echo "Generated secret: $SECRET (len ${#SECRET})"
[ "${#SECRET}" -ge 30 ] && echo "PASS: secret generated" || echo "FAIL: secret too short"
```

### 3H — Persona Seeding Verification

```python
import yaml
from pathlib import Path

personas_dir = Path("config/personas")
personas = list(personas_dir.glob("*.yaml"))

print(f"Total personas: {len(personas)}")

# Verify persona-to-model mapping against known models
KNOWN_MODELS = {
    "dolphin-llama3:8b", "qwen3-coder-next:30b-q5", "devstral:24b",
    "xploiter/the-xploiter", "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0",
    "huihui_ai/baronllm-abliterated", "huihui_ai/tongyi-deepresearch-abliterated:30b",
    "qwen3-omni:30b", "llava:7b",
    "deepseek-coder:16b-instruct-q4_K_M",
}

unknown_models = []
for f in sorted(personas):
    d = yaml.safe_load(f.read_text())
    model = d.get("workspace_model", "")
    if model and model not in KNOWN_MODELS:
        unknown_models.append(f"{f.stem}: {model}")

if unknown_models:
    print("WARNING: Personas reference models not in known catalog:")
    for m in unknown_models: print(f"  {m}")
else:
    print("PASS: All persona models are in known catalog")

# Verify the 5 new security/creative personas are present
required_new = ["redteamoperator", "blueteamdefender", "pentester",
                "creativewriter", "researchanalyst"]
slugs = set()
for f in personas:
    d = yaml.safe_load(f.read_text())
    slugs.add(d.get("slug", f.stem))

for slug in required_new:
    status = "PRESENT" if slug in slugs else "MISSING"
    print(f"  {status}: {slug}")
```

### 3I — Behavioral Verification Summary

After running 3A through 3H, fill in this matrix:

```
BEHAVIORAL VERIFICATION SUMMARY
================================
Pipeline startup:        [PASS|FAIL|UNTESTABLE]
Auth enforcement:        [PASS|FAIL]
Workspace exposure (13): [PASS|FAIL]
model_hint routing:      [PASS|FAIL]
Timeout from YAML:       [PASS|FAIL]
Unhealthy fallback:      [PASS|FAIL]
Semaphore concurrency:   [PASS|FAIL]
Compose structure:       [PASS|FAIL]
DinD sandbox:            [PASS|FAIL]
MCP healthchecks:        [PASS|FAIL]
Multi-user env vars:     [PASS|FAIL]
Secret hygiene:          [PASS|FAIL]
Launch script syntax:    [PASS|FAIL]
Branch hygiene:          [PASS|FAIL — list branches if FAIL]
Lint clean:              [PASS|FAIL — N violations if FAIL]
All tests pass:          [PASS|FAIL — N failures if FAIL]
Persona coverage (35+):  [PASS|FAIL]
Import file counts:      tools=N workspaces=N functions=N
README accuracy:         [CURRENT|STALE]
```

---

## Phase 4 — Full Code Audit (informed by Phase 3)

### 4A — router_pipe.py

Read every line. Check:
- `_request_semaphore._value` — private attribute access (fragile across Python versions).
  Use `asyncio.BoundedSemaphore` or wrap in a try/acquire-nowait pattern instead.
- `WORKSPACES` dict — verify all 13 entries have `name`, `description`, `model_hint`
- Streaming error format — verify SSE error chunks are valid JSON
- `chat_completions` — verify `ws_cfg` lookup handles unknown workspace IDs gracefully

### 4B — cluster_backends.py

- Verify `route_key` unused variable is removed (F841)
- Verify `_load_config` reads all four defaults: `fallback_group`, `request_timeout`,
  `health_check_interval`, `health_timeout`
- Verify `start_health_loop` handles `CancelledError` gracefully (doesn't log as error)
- Verify `health_check_all` uses `asyncio.gather(return_exceptions=True)` — it does, confirm

### 4C — openwebui_init.py

- Verify `create_persona_presets` has the `PERSONAS_DIR = Path("/personas")` constant
- Verify `configure_user_settings` calls the correct Open WebUI API endpoint
- Verify all functions have docstrings
- Verify the main flow order: wait → admin account → login fallback → tool servers →
  workspaces → user settings → personas

### 4D — launch.sh

- Verify `local` keyword only inside functions (0G already checked, confirm)
- Verify `add-user` uses `local_email` (not `local email`) to avoid `local` outside function
- Verify `get_admin_token` handles empty password gracefully
- Verify `pull-models` array loop exits cleanly on container-not-found
- Verify `clean` targets `portal-5_open-webui-data` but falls back to `open-webui-data`

### 4E — Dockerfile.pipeline and Dockerfile.mcp

- `Dockerfile.pipeline`: verify CMD is `["python", "-m", "portal_pipeline"]` not direct python call
- `Dockerfile.mcp`: verify no HEALTHCHECK stanza (moved to compose)
- `Dockerfile.mcp`: verify pip installs use quoted version specs
- Both: verify WORKDIR is `/app`

### 4F — MCP Server Implementations

For each of `portal_mcp/documents/document_mcp.py`,
`portal_mcp/generation/music_mcp.py`, `portal_mcp/generation/tts_mcp.py`,
`portal_mcp/generation/whisper_mcp.py`, `portal_mcp/generation/comfyui_mcp.py`,
`portal_mcp/generation/video_mcp.py`, `portal_mcp/execution/code_sandbox_mcp.py`:

- Does it compile? (`python3 -m py_compile`)
- Does it have a `/health` endpoint that returns `{"status": "ok"}`?
- Does it read its port from the right env var?
- Does it use `portal_mcp.mcp_server.fastmcp` (not a bare import)?
- Output dir: does it use `OUTPUT_DIR` env var or hardcode a path?

### 4G — Channel Adapters

```python
import ast
from pathlib import Path

for adapter in ["portal_channels/telegram/bot.py", "portal_channels/slack/bot.py"]:
    src = Path(adapter).read_text()
    ast.parse(src)  # verify compiles
    
    # Verify it calls Pipeline API, not old AgentCore
    assert "portal_pipeline" not in src or "PIPELINE_URL" in src, \
        f"{adapter}: may still have AgentCore dependency"
    assert "PIPELINE_URL" in src, f"{adapter}: missing PIPELINE_URL"
    assert "/v1/chat/completions" in src, f"{adapter}: not calling Pipeline API"
    print(f"PASS: {adapter}")
```

---

## Phase 5 — Test Suite Analysis

```bash
python3 -m pytest tests/ -v --tb=long --cov=portal_pipeline \
    --cov-report=term-missing 2>&1 | tee /tmp/p5_tests_final.log
```

For the coverage report, identify:
1. Lines covered by current tests
2. Lines NOT covered — classify each as: testable without Ollama / requires Ollama / requires Docker
3. Missing test classes based on Phase 3 findings

Required test coverage (verify each exists):
- `TestBackendRegistry` — load_config, workspace routing, unhealthy fallback, no-backend 503
- `TestTimeoutConfiguration` — timeout read from YAML (120s), health_interval, health_timeout
- `TestPipelineAPI` — health=200, models auth, 13 workspaces, wrong key 401, all security workspaces
- `TestWorkspaceConsistency` — 3-source match (router/yaml/imports), all 13 IDs, model_hints

Missing and needed:
- `TestRouterPipeLogic` — model_hint respected when model in backend.models, falls back correctly
- `TestSemaphore` — 503 + Retry-After when semaphore exhausted
- `TestPersonaFiles` — all 35 personas valid YAML, required fields, known models

---

## Phase 6 — Architecture Assessment

### 6A — Component Map

Produce a verified table:

```
Component                  | File                              | Status  | Port
---------------------------|-----------------------------------|---------|------
Portal Pipeline            | portal_pipeline/router_pipe.py    | [status]| 9099
Backend Registry           | portal_pipeline/cluster_backends.py| [status]|  —
Open WebUI                 | (external image)                  | EXTERNAL| 8080
Ollama                     | (external image)                  | EXTERNAL|11434
MCP: Documents             | portal_mcp/documents/             | [status]| 8913
MCP: Music                 | portal_mcp/generation/music_mcp   | [status]| 8912
MCP: TTS                   | portal_mcp/generation/tts_mcp     | [status]| 8916
MCP: Whisper               | portal_mcp/generation/whisper_mcp | [status]| 8915
MCP: ComfyUI               | portal_mcp/generation/comfyui_mcp | [status]| 8910
MCP: Video                 | portal_mcp/generation/video_mcp   | [status]| 8911
MCP: Sandbox               | portal_mcp/execution/             | [status]| 8914
DinD (sandbox runtime)     | (external image)                  | EXTERNAL|  —
Telegram Adapter           | portal_channels/telegram/bot.py   | [status]|  —
Slack Adapter              | portal_channels/slack/bot.py      | [status]|  —
openwebui_init.py          | scripts/openwebui_init.py         | [status]|  —
```

Status options: VERIFIED, STUB (compiles but not fully functional), BROKEN, UNTESTABLE

### 6B — Evolution Gaps

Identify genuine gaps — things that are architecturally missing, not just bugs:
1. Does the Pipeline expose `/v1/chat/completions` with streaming? Verify SSE works.
2. Does `configure_user_settings` actually set `DEFAULT_USER_ROLE` or only signup enabled?
   (The Open WebUI API for setting default role may be undocumented — verify.)
3. Is there any rate limiting at the Open WebUI layer for multi-user fairness?
4. Is the Telegram bot's conversation history bounded (max turns) to prevent memory growth?

---

## Phase 7 — Production Readiness Score

Score each dimension 1-10, with evidence:

```
PRODUCTION READINESS SCORE
==========================
Dimension               Score  Evidence
----------------------  -----  --------
Security (secrets)        /10  [evidence from 2E + 3E]
Security (sandbox)        /10  [evidence from 3E DinD check]
Multi-user readiness      /10  [evidence from 3E compose check]
Routing correctness       /10  [evidence from 3C + 3B]
Capacity (25 users)       /10  [OLLAMA_NUM_PARALLEL, workers, semaphore]
Operational tooling       /10  [launch.sh commands, add-user, pull-models]
Test coverage             /10  [Phase 5 coverage %]
Code quality (lint)       /10  [Phase 0D violation count]
Documentation             /10  [docs/ files present + accurate]
Deployment cleanliness    /10  [healthchecks, volumes, compose structure]
----------------------  -----
TOTAL                     /100
```

Score of 75+ = Release Candidate. Below 75 = list blockers.

---

## Output — Three Artifacts

Produce all three in full after completing all phases.

### ARTIFACT 1: `P5_AUDIT_REPORT.md`

Sections:
1. **Executive Summary** — overall score, top 5 findings, release-ready verdict
2. **Delta Summary** *(delta runs only)* — what changed since last run
3. **Baseline Status** — Phase 0I block
4. **Behavioral Verification Summary** — Phase 3I matrix, fully populated
5. **Branch Status** — result of 0G
6. **Configuration Audit** — Phase 2 findings
7. **Code Findings Register** — every finding with file:line, severity, category
8. **Test Coverage Map** — covered vs uncovered
9. **Architecture Blueprint** — Phase 6A table
10. **Evolution Gap Register** — Phase 6B
11. **Production Readiness Score** — Phase 7 scorecard with evidence

Format each finding:

```
FINDING-[N]
File:       [path:line]
Severity:   [CRITICAL|HIGH|MEDIUM|LOW]
Category:   [LINT|SECURITY|CORRECTNESS|MISSING_FEATURE|PERF|DOC_DRIFT]
Finding:    [one sentence]
Evidence:   [command run + output]
Task ref:   [TASK-N in Artifact 2]
```

### ARTIFACT 2: `P5_ACTION_PROMPT.md`

Session bootstrap block at top:
```bash
cd /path/to/portal-5
source .venv/bin/activate || (uv venv && source .venv/bin/activate && uv pip install -e ".[dev]")
git checkout main && git pull
python3 -m pytest tests/ -q --tb=no && echo "Tests OK" || echo "Tests BROKEN — fix before proceeding"
python3 -m ruff check portal_pipeline/ scripts/ --quiet && echo "Lint OK" || echo "Lint violations present"
```

Task format:
```
TASK-[N]
Tier:       [1 = fix now, 2 = fix soon, 3 = backlog]
File(s):    [paths]
Category:   [LINT|SECURITY|CORRECTNESS|TEST_GAP|PERF|DOC_DRIFT|MISSING_FEATURE]
Finding:    [one sentence — reference FINDING-N]
Action:     [specific change with exact line numbers where possible]
Risk:       [LOW|MEDIUM|HIGH]
Acceptance: [runnable command that proves the fix worked]
```

Tier 1 includes: CORRECTNESS bugs proven by Phase 3, SECURITY issues, LINT errors that
mask bugs (F841 unused var, SIM117 readability), any test that fails.

### ARTIFACT 3: `P5_ROADMAP.md`

```
Portal 5.0 Roadmap
==================
Last updated: [date]
Source: codebase-review-[date]

LEGEND: P1=Critical, P2=High, P3=Medium
STATUS: OPEN, IN_PROGRESS, DONE, BLOCKED

P5-ROAD-001 | P[N] | [title] | [status] | [source]
```

Organize by:
- **Stability** (bugs, broken features, test failures)
- **Security** (hardening, audit items)
- **Capacity** (multi-user, concurrent request handling)
- **Features** (planned capabilities not yet implemented)
- **Documentation** (gaps, drift, missing guides)
- **Operations** (tooling, monitoring, backup)

---

## Begin

Start with Phase -1 (prior artifacts check). Then Phase 0 (build, lint, test, branch hygiene).
Then Phase 1 (git history). Phase 2 (configuration audit). **Phase 3 (behavioral verification
— run every test).**  Phase 4 (code audit informed by Phase 3). Phase 5 (test analysis).
Phase 6 (architecture). Phase 7 (score). Then produce all three artifacts.

**Do not produce artifacts until all phases complete. Every finding requires a command you
ran and its actual output.**
