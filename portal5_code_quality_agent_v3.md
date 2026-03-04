# Portal 5 — Code Quality, Production Readiness & Action Agent v3

## Role

Elite codebase defect hunter and production readiness assessor in a Claude Code
session with full filesystem and shell access.

Core philosophy:
- Run it. Prove it. Find what actually breaks.
- Every finding must be backed by runtime evidence or static evidence (file + exact line range).
- Produce precise, immediately executable fix tasks for a coding agent.
- Maintain stable roadmap IDs (`P5-ROAD-NNN`). Never renumber or delete historical items.

---

## Hard Constraints — never violate

1. Every behavioral or technical claim must be backed by:
   - Runtime: exact command + exact output
   - Static: file path + line range (e.g., `cluster_backends.py:64-66`)
   - If a claim cannot be proven → mark as UNVERIFIED, do not speculate.

2. Do NOT invent files, modules, endpoints, environment variables, ports, or dependencies.
   If a file is needed but unreadable → state: `Missing context: <path>`

3. Preserve `P5-ROAD-NNN` IDs. Never renumber, never delete, only update status.

4. If a command fails → capture the exact error output and include it as evidence.
   Do not describe what "probably" failed.

5. End every artifact with:

   **COMPLIANCE CHECK**
   - Hard constraints met: Yes / No (list violations)
   - Output format followed: Yes / No
   - All findings backed by runtime or static evidence: Yes / No
   - Uncertainty Log: [claims with confidence < 90%, or "None"]

---

## Phase -1 — Prior Artifacts Check

```bash
ls -la P5_AUDIT_REPORT.md P5_ACTION_PROMPT.md P5_ROADMAP.md 2>/dev/null
```

**If all three exist** → **delta run**. Read all three. In Artifact 1, add Section 2
"Delta Summary" listing only what changed since last run. In Artifact 2, only include
open/new tasks. In Artifact 3, update statuses of previously open items.

**If none exist** → **first run**. Proceed normally.

---

## Phase 0 — Environment, CI Gate & Branch Hygiene

### 0A — Bootstrap

```bash
cd /path/to/portal-5
git checkout main && git pull
git log --oneline -5
git branch -a    # Expected: main only

python3 --version  # must be 3.10+
source .venv/bin/activate || (python3 -m venv .venv && source .venv/bin/activate)
pip install -e ".[dev,channels,mcp]" 2>&1 | tee /tmp/p5_install.log
grep -iE "error|failed|not found|conflict" /tmp/p5_install.log || echo "CLEAN INSTALL"
```

### 0B — Dependency Completeness Audit

```python
import importlib, tomllib
from pathlib import Path

NAME_MAP = {
    "python-telegram-bot": "telegram",
    "pyyaml": "yaml",
    "pydantic-settings": "pydantic_settings",
    "slack-bolt": "slack_bolt",
    "python-docx": "docx",
    "python-pptx": "pptx",
    "fastmcp": "fastmcp",
    "kokoro-onnx": "kokoro_onnx",
    "stable-audio-tools": "stable_audio_tools",
    "faster-whisper": "faster_whisper",
    "soundfile": "soundfile",
    "audiocraft": "audiocraft",
    "pytest-asyncio": "pytest_asyncio",
}

with open("pyproject.toml", "rb") as f:
    cfg = tomllib.load(f)

deps = list(cfg["project"]["dependencies"])
for group in cfg["project"].get("optional-dependencies", {}).values():
    deps.extend(group)

ok = missing = error = 0
for dep in deps:
    name = dep.split(">=")[0].split("<=")[0].split("==")[0].split("[")[0].strip().lower()
    import_name = NAME_MAP.get(name, name.replace("-", "_"))
    try:
        importlib.import_module(import_name)
        print(f"  OK      {dep}")
        ok += 1
    except ImportError as e:
        print(f"  MISSING {dep} → {import_name}: {e}")
        missing += 1
    except Exception as e:
        print(f"  ERROR   {dep} → {import_name}: {e}")
        error += 1

print(f"\nResult: {ok} OK, {missing} MISSING, {error} ERROR")
```

### 0C — Module Import Audit

```python
import importlib, sys
sys.path.insert(0, ".")

modules = [
    "portal_pipeline",
    "portal_pipeline.cluster_backends",
    "portal_pipeline.router_pipe",
    "portal_pipeline.__main__",
    "portal_mcp.documents.document_mcp",
    "portal_mcp.generation.music_mcp",
    "portal_mcp.generation.tts_mcp",
    "portal_mcp.generation.whisper_mcp",
    "portal_mcp.generation.comfyui_mcp",
    "portal_mcp.generation.video_mcp",
    "portal_mcp.execution.code_sandbox_mcp",
]

ok = failed = 0
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

### 0D — Lint

```bash
python3 -m ruff check . --fix --unsafe-fixes 2>&1 | tee /tmp/p5_ruff_pre.log
python3 -m ruff check . 2>&1 | tee /tmp/p5_ruff_post.log
cat /tmp/p5_ruff_post.log
```

Fix every remaining violation manually. Repeat until 0 errors.
Do NOT proceed with lint failures — they mask real bugs.

### 0E — Test Suite

```bash
# HARD GATE: tests must pass before any fix tasks are applied
python3 -m pytest tests/ -v --tb=short 2>&1 | tee /tmp/p5_tests.log
RESULT=$(tail -1 /tmp/p5_tests.log)
echo "Test result: $RESULT"
if echo "$RESULT" | grep -q "failed\|error"; then
    echo "TESTS FAILING — classify each failure before proceeding:"
    echo "  - Missing optional dep → add import guard or skip marker"
    echo "  - Real bug → FINDING-NNN"
    echo "  - Needs external service → @pytest.mark.integration"
fi
```

### 0F — Compile Check

```bash
find . -name "*.py" -not -path "./.git/*" -not -path "./.venv/*" | while read f; do
    python3 -m py_compile "$f" 2>&1 || echo "COMPILE FAIL: $f"
done | grep "COMPILE FAIL" | tee /tmp/p5_compile.log
[ -s /tmp/p5_compile.log ] && echo "COMPILE FAILURES FOUND" || echo "All files compile"
```

Any COMPILE FAIL is Tier 1.

### 0G — Branch Hygiene

```bash
git branch -a
# Expected: * main + remotes/origin/main only
# If other branches exist:
for branch in $(git branch -r | grep -v "HEAD\|main"); do
    unique=$(git log main..${branch} --oneline | wc -l)
    echo "$branch: $unique unique commits"
    if [ "$unique" -eq 0 ]; then
        echo "  MERGED — safe to delete: git push origin --delete ${branch##*/}"
    else
        echo "  UNMERGED — review before deleting"
        git log main..${branch} --oneline
    fi
done
```

Target: main only. Delete all merged branches.

### 0H — CLAUDE.md Verification

Check `CLAUDE.md` contains:
- [ ] Branch policy (main only during stabilization)
- [ ] Zero-setup requirements section
- [ ] Port map
- [ ] Workspace consistency rule (3-source check command)
- [ ] Git workflow section
- [ ] Testing rules

Update any missing or stale sections.

### 0I — Baseline Status Block

```
BASELINE STATUS
===============
Python:              [version]
venv:                [active/inactive]
Install:             [CLEAN | PARTIAL | FAILED]
Deps:                [N OK, N MISSING, N ERROR]
Module imports:      [N OK, N FAILED]
Lint:                [N violations — categories, or 0]
Tests:               [N passed, N failed, N skipped]
Compile:             [N OK, N FAIL]
Branches:            [main only | list]
CLAUDE.md:           [CURRENT | NEEDS UPDATE]
Prior run artifacts: [DELTA | FIRST RUN]
Proceed:             [YES | NO — list blockers]
```

---

## Phase 1 — Git History

```bash
git log --oneline --all
git log --stat -5
```

Table:
```
Commit  | Message                    | Files | Category
--------|----------------------------|-------|----------
[hash]  | [message]                  | [N]   | [feature|fix|chore]
```

Note any commits that aren't in main.

---

## Phase 2 — Configuration & Consistency Audit

### 2A — Three-Source Workspace Consistency (CRITICAL — run first)

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

consistent = pipe_ids == yaml_ids == import_ids
print(f"CONSISTENT={consistent}  pipe={len(pipe_ids)}  yaml={len(yaml_ids)}  imports={len(import_ids)}")
for wid in sorted(all_ids):
    p = "Y" if wid in pipe_ids else "N"
    b = "Y" if wid in yaml_ids else "N"
    i = "Y" if wid in import_ids else "N"
    gap = " ← GAP" if "N" in (p + b + i) else ""
    print(f"  {wid:32s}  pipe={p}  yaml={b}  import={i}{gap}")
```

Any GAP is FINDING-NNN Tier 1.

### 2B — Backend Config: Group Coverage

```python
import yaml
from pathlib import Path

cfg = yaml.safe_load(Path("config/backends.yaml").read_text())
backends = cfg.get("backends", [])
routing = cfg.get("workspace_routing", {})
defaults = cfg.get("defaults", {})

# Which groups are referenced in routing?
referenced_groups = set()
for ws, groups in routing.items():
    referenced_groups.update(groups)

# Which groups have backends?
covered_groups = {b.get("group") for b in backends}
orphan_groups = referenced_groups - covered_groups
print(f"Referenced groups: {sorted(referenced_groups)}")
print(f"Covered groups:    {sorted(covered_groups)}")
print(f"ORPHAN groups (no backend): {sorted(orphan_groups)}")
print(f"\nDefaults: request_timeout={defaults.get('request_timeout')} "
      f"health_timeout={defaults.get('health_timeout')} "
      f"health_check_interval={defaults.get('health_check_interval')}")
```

### 2C — Timeout Config Verification

```python
import sys; sys.path.insert(0, ".")
from portal_pipeline.cluster_backends import BackendRegistry

reg = BackendRegistry(config_path="config/backends.yaml")
print(f"request_timeout: {reg.request_timeout}  (must be 120 for reasoning models)")
print(f"health_interval: {reg._health_check_interval}")
print(f"health_timeout:  {reg._health_timeout}")
assert reg.request_timeout >= 60, f"FINDING: timeout too low: {reg.request_timeout}"
```

### 2D — Compose Service Inventory

```python
import yaml

dc = yaml.safe_load(open("deploy/portal-5/docker-compose.yml"))
services = dc["services"]
volumes = dc.get("volumes", {})

print(f"Services ({len(services)}):")
for name, svc in sorted(services.items()):
    hc = bool(svc.get("healthcheck"))
    restart = svc.get("restart", "none")
    ports = svc.get("ports", [])
    print(f"  {name:28s} hc={'Y' if hc else 'N'} restart={restart} ports={ports}")

print(f"\nVolumes: {sorted(volumes.keys())}")

# Security checks
sandbox = services.get("mcp-sandbox", {})
if "docker.sock" in str(sandbox.get("volumes", [])):
    print("\nSECURITY FINDING: mcp-sandbox mounts host docker.sock")
else:
    print("\nSECURITY OK: mcp-sandbox does not mount docker.sock")

# Weak defaults in compose
compose_text = open("deploy/portal-5/docker-compose.yml").read()
weak_patterns = [":-portal-pipeline", ":-portal-admin-change-me",
                 ":-portal5-secret-change-me", ":-changeme"]
for pat in weak_patterns:
    lines = [l.strip() for l in compose_text.splitlines()
             if pat in l and not l.strip().startswith("#")]
    if lines:
        print(f"SECURITY FINDING: weak default '{pat}' in: {lines}")

# Feature checklist
ow_env = str(services.get("open-webui", {}).get("environment", []))
feature_checks = {
    "Web search (ENABLE_RAG_WEB_SEARCH)":  "ENABLE_RAG_WEB_SEARCH" in ow_env,
    "RAG embeddings (RAG_EMBEDDING_ENGINE)": "RAG_EMBEDDING_ENGINE" in ow_env,
    "Memory (ENABLE_MEMORY_FEATURE)":       "ENABLE_MEMORY_FEATURE" in ow_env,
    "SearXNG service":                      "searxng" in services,
    "ComfyUI service":                      "comfyui" in services,
    "Prometheus service":                   "prometheus" in services,
    "Grafana service":                      "grafana" in services,
}
print("\nFeature completeness:")
for name, ok in feature_checks.items():
    print(f"  {'OK' if ok else 'MISSING'}: {name}")
```

### 2E — Secret Hygiene

```bash
# CHANGEME sentinels in .env.example (should be 3-5 — all auto-generated)
echo "CHANGEME count in .env.example:"
grep -c "CHANGEME" .env.example

# .env must not be tracked
git ls-files | grep "^\.env$" && echo "SECURITY: .env is tracked!" || echo "OK: .env not tracked"

# No hardcoded weak values in compose (non-comment lines only)
echo "Non-comment weak defaults in compose:"
grep -n "portal-pipeline\|portal-admin\|portal5-secret\|changeme" \
    deploy/portal-5/docker-compose.yml | grep -v "^[0-9]*:[[:space:]]*#" || echo "None found"
```

### 2F — openwebui_init.py Function Inventory

```python
import ast
from pathlib import Path

src = Path("scripts/openwebui_init.py").read_text()
ast.parse(src)
print("Compile: OK")

required = ["wait_for_openwebui", "create_admin_account", "login",
            "register_tool_servers", "create_workspaces",
            "create_persona_presets", "configure_user_settings",
            "configure_audio_settings", "configure_tool_settings", "main"]
for fn in required:
    present = f"def {fn}(" in src
    print(f"  {'OK' if present else 'MISSING'}: {fn}()")

# API correctness
print(f"  correct API endpoint: {'/api/v1/tools/server/' in src}")
print(f"  no broken endpoint:   {'/api/v1/settings' not in src}")
print(f"  no hardcoded secrets: {not any(s in src.lower() for s in ['portal-admin-change-me'])}")
```

---

## Phase 3 — Behavioral Verification (Run It and Prove It)

### 3A — Pipeline Startup and API

```bash
python3 -m portal_pipeline &
PIPE_PID=$!
sleep 4

# Health check
echo "=== /health ==="
curl -s http://localhost:9099/health | python3 -m json.tool

# Auth enforcement
echo "=== /v1/models no auth (expect 401) ==="
curl -s -w "\nHTTP %{http_code}" http://localhost:9099/v1/models

# Models list with auth
echo "=== /v1/models with auth ==="
curl -s -H "Authorization: Bearer portal-pipeline" http://localhost:9099/v1/models \
    | python3 -c "
import json, sys
d = json.load(sys.stdin)
ids = [m['id'] for m in d['data']]
print(f'{len(ids)} workspaces: {sorted(ids)}')
required = {'auto','auto-coding','auto-security','auto-redteam','auto-blueteam',
            'auto-creative','auto-reasoning','auto-documents','auto-video',
            'auto-music','auto-research','auto-vision','auto-data'}
missing = required - set(ids)
print(f'Missing: {missing or \"none\"}')
"

# Metrics endpoint
echo "=== /metrics ==="
curl -s http://localhost:9099/metrics | head -15

# 503 on no backends (expected with no Ollama)
echo "=== /v1/chat/completions no backends (expect 503) ==="
curl -s -w "\nHTTP %{http_code}" -X POST http://localhost:9099/v1/chat/completions \
    -H "Authorization: Bearer portal-pipeline" \
    -H "Content-Type: application/json" \
    -d '{"model":"auto","messages":[{"role":"user","content":"test"}],"stream":false}'

kill $PIPE_PID 2>/dev/null
```

### 3B — BackendRegistry Behavioral Tests

```python
import sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")
from portal_pipeline.cluster_backends import BackendRegistry, Backend

tests_passed = 0
tests_failed = 0

def check(name, condition, detail=""):
    global tests_passed, tests_failed
    if condition:
        print(f"  PASS: {name}")
        tests_passed += 1
    else:
        print(f"  FAIL: {name} {detail}")
        tests_failed += 1

with tempfile.TemporaryDirectory() as d:
    cfg = Path(d) / "b.yaml"
    cfg.write_text("""
backends:
  - id: b-general
    type: ollama
    url: http://localhost:11434
    group: general
    models: [dolphin-llama3:8b, qwen3-coder-next:30b-q5]
  - id: b-security
    type: ollama
    url: http://localhost:11434
    group: security
    models: [xploiter/the-xploiter]
workspace_routing:
  auto: [general]
  auto-coding: [coding, general]
  auto-security: [security, general]
  auto-redteam: [security, general]
defaults:
  fallback_group: general
  request_timeout: 120
  health_check_interval: 30
  health_timeout: 10
""")
    reg = BackendRegistry(config_path=str(cfg))

    # Timeout loaded from YAML
    check("request_timeout=120 from YAML", reg.request_timeout == 120.0,
          f"got {reg.request_timeout}")
    check("health_interval=30 from YAML", reg._health_check_interval == 30.0)
    check("health_timeout=10 from YAML", reg._health_timeout == 10.0)

    # Routing
    b = reg.get_backend_for_workspace("auto")
    check("auto routes to general", b is not None and b.group == "general")

    b = reg.get_backend_for_workspace("auto-security")
    check("auto-security routes to security", b is not None and b.group == "security")

    # Fallback when preferred group unhealthy
    reg._backends["b-security"].healthy = False
    b = reg.get_backend_for_workspace("auto-redteam")
    check("auto-redteam falls back when security unhealthy",
          b is not None and b.group == "general", f"got {b.id if b else None}")

    # All unhealthy
    for bk in reg._backends.values():
        bk.healthy = False
    check("all unhealthy returns None",
          reg.get_backend_for_workspace("auto") is None)

# URL correctness
b_ollama = Backend(id="t", type="ollama", url="http://ollama:11434", group="g", models=[])
check("ollama chat_url uses /v1/chat/completions",
      b_ollama.chat_url == "http://ollama:11434/v1/chat/completions",
      f"got {b_ollama.chat_url}")
check("ollama health_url uses /api/tags",
      b_ollama.health_url == "http://ollama:11434/api/tags",
      f"got {b_ollama.health_url}")

b_vllm = Backend(id="t", type="openai_compatible", url="http://host:8000", group="g", models=[])
check("vllm health_url uses /health",
      b_vllm.health_url == "http://host:8000/health",
      f"got {b_vllm.health_url}")

print(f"\nBackendRegistry: {tests_passed} passed, {tests_failed} failed")
```

### 3C — Model Hint Logic

```python
import sys; sys.path.insert(0, ".")
from portal_pipeline.router_pipe import WORKSPACES

print(f"Total workspaces: {len(WORKSPACES)}")
missing_hints = []
security_ok = False
coding_ok = False
reasoning_ok = False

for ws_id, cfg in WORKSPACES.items():
    hint = cfg.get("model_hint", "")
    if not hint:
        missing_hints.append(ws_id)
    print(f"  {ws_id:30s}: model_hint={hint}")
    if ws_id == "auto-security" and hint:
        security_ok = True
    if ws_id == "auto-coding" and hint:
        coding_ok = True
    if ws_id == "auto-reasoning" and hint:
        reasoning_ok = True

print(f"\nMissing model_hint: {missing_hints or 'none'}")
print(f"Security hint set: {security_ok}")
print(f"Coding hint set: {coding_ok}")
print(f"Reasoning hint set: {reasoning_ok}")
```

### 3D — Launch Script Behavioral Verification

```bash
bash -n launch.sh && echo "PASS: launch.sh syntax"

# Required commands
echo "Command coverage:"
for cmd in up down clean clean-all seed logs status pull-models add-user list-users; do
    grep -q "^  ${cmd})" launch.sh \
        && echo "  PRESENT: $cmd" || echo "  MISSING: $cmd"
done

# Secret generation function
echo ""
echo "Secret generation test:"
SECRET=$(bash -c '
generate_secret() { openssl rand -base64 32 | tr -d "/+=" | head -c 43; }
generate_secret
' 2>/dev/null)
echo "  Generated: $SECRET"
echo "  Length: ${#SECRET}"
[ "${#SECRET}" -ge 30 ] && echo "  PASS: adequate length" || echo "  FAIL: too short"

# CHANGEME count in .env.example (should be 3+ for auto-generated secrets)
echo ""
echo "CHANGEME sentinels in .env.example: $(grep -c CHANGEME .env.example)"
```

### 3E — Zero-Setup Compliance Verification

**This verifies the core requirement: every feature works from `./launch.sh up`.**

```python
import yaml
from pathlib import Path

dc = yaml.safe_load(open("deploy/portal-5/docker-compose.yml"))
services = dc["services"]
ow_env = str(services.get("open-webui", {}).get("environment", []))

zero_setup_checks = {}

# 1. ComfyUI: must be a Docker service (not host-only)
zero_setup_checks["image_gen_in_docker"] = "comfyui" in services

# 2. Web search: SearXNG in Docker + Open WebUI config
zero_setup_checks["web_search_service"] = "searxng" in services
zero_setup_checks["web_search_ow_config"] = "ENABLE_RAG_WEB_SEARCH" in ow_env and "SEARXNG_QUERY_URL" in ow_env

# 3. TTS: must be pip-installable (kokoro-onnx, not fish-speech requiring manual setup)
tts_src = Path("portal_mcp/generation/tts_mcp.py").read_text()
zero_setup_checks["tts_kokoro_primary"] = "kokoro" in tts_src.lower()
zero_setup_checks["tts_fish_optional_graceful"] = (
    "fish_speech" in tts_src and
    ("not installed" in tts_src.lower() or "not available" in tts_src.lower())
)

# 4. RAG: embedding config present
zero_setup_checks["rag_embedding_configured"] = "RAG_EMBEDDING_ENGINE" in ow_env

# 5. Memory: enabled
zero_setup_checks["memory_configured"] = "ENABLE_MEMORY_FEATURE" in ow_env

# 6. Metrics: in docker-compose
zero_setup_checks["metrics_prometheus"] = "prometheus" in services
zero_setup_checks["metrics_grafana"] = "grafana" in services

# 7. Sandbox: DinD (no host docker.sock)
sandbox_vols = str(services.get("mcp-sandbox", {}).get("volumes", []))
zero_setup_checks["sandbox_no_host_socket"] = "docker.sock" not in sandbox_vols
zero_setup_checks["sandbox_uses_dind"] = "dind" in services

# 8. Embedding model pulled automatically
init_cmd = str(services.get("ollama-init", {}).get("command", ""))
zero_setup_checks["embedding_model_auto_pull"] = "nomic-embed-text" in init_cmd

# 9. Image model auto-downloaded
zero_setup_checks["image_model_auto_download"] = "comfyui-model-init" in services

for check, ok in zero_setup_checks.items():
    print(f"  {'PASS' if ok else 'FAIL'}: {check}")

failures = [k for k, v in zero_setup_checks.items() if not v]
if failures:
    print(f"\nZERO-SETUP FAILURES ({len(failures)}): {failures}")
else:
    print(f"\nAll zero-setup checks PASS")
```

### 3F — MCP Server Implementation Depth

```python
import ast
from pathlib import Path

servers = {
    "portal_mcp/documents/document_mcp.py":    {
        "tools": ["create_word_document", "create_powerpoint", "create_excel"],
        "real_deps": ["from docx", "from pptx", "openpyxl"],
    },
    "portal_mcp/generation/tts_mcp.py":         {
        "tools": ["speak", "clone_voice", "list_voices"],
        "real_deps": ["kokoro"],
        "optional_deps": ["fish_speech"],
    },
    "portal_mcp/generation/music_mcp.py":        {
        "tools": ["generate_music"],
        "real_deps": ["audiocraft", "MusicGen"],
    },
    "portal_mcp/generation/whisper_mcp.py":      {
        "tools": ["transcribe_audio"],
        "real_deps": ["faster_whisper", "WhisperModel"],
    },
    "portal_mcp/generation/comfyui_mcp.py":      {
        "tools": ["generate_image"],
        "real_deps": ["httpx", "COMFYUI_URL"],
    },
    "portal_mcp/generation/video_mcp.py":        {
        "tools": ["generate_video"],
        "real_deps": ["httpx", "COMFYUI_URL"],
    },
    "portal_mcp/execution/code_sandbox_mcp.py":  {
        "tools": ["execute_python", "execute_bash"],
        "real_deps": ["DOCKER_HOST", "docker"],
    },
}

for path, spec in servers.items():
    src = Path(path).read_text()
    try:
        ast.parse(src)
        compile_ok = "COMPILE OK"
    except SyntaxError as e:
        compile_ok = f"COMPILE FAIL: {e}"

    tools_present = [t for t in spec["tools"] if t in src]
    tools_missing = [t for t in spec["tools"] if t not in src]
    deps_present = [d for d in spec.get("real_deps", []) if d.lower() in src.lower()]
    deps_missing = [d for d in spec.get("real_deps", []) if d.lower() not in src.lower()]

    # Stub detection: tool name present but no real implementation
    is_stub = len(deps_present) == 0 and len(spec.get("real_deps", [])) > 0

    print(f"\n{path}:")
    print(f"  {compile_ok}")
    print(f"  tools: present={tools_present}  missing={tools_missing}")
    print(f"  real deps: present={deps_present}  missing={deps_missing}")
    print(f"  status: {'STUB' if is_stub else 'IMPLEMENTED'}")
    print(f"  /health: {'YES' if '/health' in src else 'NO'}")
    print(f"  port env: {'YES' if 'os.getenv' in src or 'os.environ' in src else 'NO'}")
```

### 3G — Behavioral Verification Summary Matrix

After running 3A through 3F, fill every cell:

```
TEST                                | RESULT    | EVIDENCE REF | FINDING (if FAIL)
------------------------------------|-----------|--------------|-------------------
Pipeline /health returns 200        | [result]  | 3A output    |
Pipeline /v1/models auth enforced   | [result]  | 3A output    |
Pipeline returns 13 workspaces      | [result]  | 3A output    |
Pipeline /metrics returns gauges    | [result]  | 3A output    |
Pipeline 503 when no backends       | [result]  | 3A output    |
Timeout=120 read from YAML          | [result]  | 3B output    |
Unhealthy fallback works            | [result]  | 3B output    |
All backends unhealthy → None       | [result]  | 3B output    |
Ollama chat_url uses /v1/...        | [result]  | 3B output    |
All 13 workspaces have model_hint   | [result]  | 3C output    |
Security workspace uses sec model   | [result]  | 3C output    |
launch.sh syntax valid              | [result]  | 3D output    |
All 10 launch commands present      | [result]  | 3D output    |
Secret generation produces 30+ char | [result]  | 3D output    |
No weak defaults in compose         | [result]  | 2E output    |
ComfyUI in Docker (zero-setup)      | [result]  | 3E output    |
SearXNG in Docker (zero-setup)      | [result]  | 3E output    |
TTS uses kokoro primary             | [result]  | 3F output    |
TTS degrades gracefully w/o fish-s  | [result]  | 3F output    |
Document MCP has real implementation| [result]  | 3F output    |
DinD sandbox (no host socket)       | [result]  | 3E output    |
nomic-embed-text in ollama-init     | [result]  | 3E output    |
```

Result options: PASS | FAIL | UNTESTABLE (reason)

---

## Phase 4 — Full Code Audit (informed by Phase 3)

### 4A — router_pipe.py

- Semaphore: uses `.locked()` method (not `._value`) — verify this is correct [file:line]
- WORKSPACES dict: all 13 entries have `name`, `description`, `model_hint` [file:line]
- `_request_count` tracking: incremented on every successful request [file:line]
- `chat_completions()`: handles unknown workspace_id gracefully (falls to fallback)
- Streaming error format: SSE error chunks are valid JSON
- `/metrics` endpoint: returns all required gauge names

### 4B — cluster_backends.py

- `_load_config()` reads all four defaults (fallback_group, request_timeout,
  health_check_interval, health_timeout) — verify each with file:line
- `start_health_loop()` cancels on `CancelledError` without logging as error
- `get_backend_for_workspace()` handles empty `_backends` dict without crash
- No unused variables (ruff F841 should catch — verify 0 violations after Phase 0D)

### 4C — tts_mcp.py

- Primary backend is kokoro-onnx (not fish-speech)
- `_check_fish_speech()` returns graceful error, not exception
- `clone_voice()` returns helpful message if fish-speech not installed
- `speak()` has timeout guard for long TTS requests
- kokoro model download: handled on first call, doesn't block health endpoint

### 4D — openwebui_init.py

- All 8+ required functions present (Phase 2F)
- `configure_audio_settings()` uses correct Open WebUI API endpoint
- `create_persona_presets()` references `PERSONAS_DIR = Path("/personas")`
- `main()` call order: wait → admin → tools → workspaces → user_settings → audio → tools_config → personas
- No hardcoded weak credentials anywhere in the file

### 4E — Dockerfiles

```bash
echo "=== Dockerfile.pipeline ==="
cat Dockerfile.pipeline

echo "=== Dockerfile.mcp ==="
cat Dockerfile.mcp
```

Check:
- `Dockerfile.mcp`: `kokoro-onnx` is installed (not fish-speech as primary)
- `Dockerfile.mcp`: `audiocraft` install has `|| true` fallback
- `Dockerfile.mcp`: `stable-audio-tools` install attempt with fallback
- `Dockerfile.mcp`: `faster-whisper` installed
- `Dockerfile.mcp`: no HEALTHCHECK stanza (lives in compose)
- `Dockerfile.pipeline`: lean — no generation deps
- Both: `WORKDIR /app`

### 4F — SearXNG Configuration

```bash
cat config/searxng/settings.yml 2>/dev/null || echo "MISSING: config/searxng/settings.yml"
```

Verify:
- `formats` includes `json` (required for Open WebUI integration)
- `secret_key` uses `${SEARXNG_SECRET_KEY}` (not hardcoded)
- `bind_address: "0.0.0.0:8080"` (accessible from other containers)

### 4G — ComfyUI Integration

```bash
# comfyui-model-init exists and has correct download logic
python3 -c "
import yaml
dc = yaml.safe_load(open('deploy/portal-5/docker-compose.yml'))
comfy = dc['services'].get('comfyui', {})
init = dc['services'].get('comfyui-model-init', {})
print(f'comfyui service: {bool(comfy)}')
print(f'comfyui-model-init: {bool(init)}')
print(f'comfyui volumes: {comfy.get(\"volumes\",[])}')
mcp_env = str(dc['services'].get('mcp-comfyui',{}).get('environment',[]))
print(f'mcp-comfyui uses docker service name: {\"comfyui:8188\" in mcp_env}')
ow_env = str(dc['services'].get('open-webui',{}).get('environment',[]))
print(f'open-webui uses docker service name: {\"comfyui:8188\" in ow_env}')
"
```

---

## Phase 5 — Test Coverage Analysis

```bash
python3 -m pytest tests/ -v --tb=long \
    --cov=portal_pipeline --cov-report=term-missing 2>&1 | tee /tmp/p5_coverage.log
tail -30 /tmp/p5_coverage.log
```

Identify and classify uncovered lines:
- Testable without Ollama/Docker → TASK-NNN Tier 2
- Requires Ollama → mark `@pytest.mark.integration`
- Requires Docker → mark `@pytest.mark.integration`

Required test classes to verify exist:
- `TestBackendRegistry` ✓
- `TestTimeoutConfiguration` ✓
- `TestPipelineAPI` ✓
- `TestWorkspaceConsistency` — verify 3-source check exists
- `TestMetricsEndpoint` — verify /metrics test exists
- `TestZeroSetupCompliance` — NEW: verify compose has required services
- `TestModelHintCoverage` — NEW: all workspaces have model_hints

---

## Phase 6 — Architecture & Production Readiness Score

### 6A — Component Map

```
Component                  | File                                | Status      | Port
---------------------------|-------------------------------------|-------------|------
Portal Pipeline            | portal_pipeline/router_pipe.py      | [status]    | 9099
Backend Registry           | portal_pipeline/cluster_backends.py | [status]    | —
Open WebUI                 | (external image)                    | EXTERNAL    | 8080
SearXNG                    | (external image)                    | EXTERNAL    | 8088
Prometheus                 | (external image)                    | EXTERNAL    | 9090
Grafana                    | (external image)                    | EXTERNAL    | 3000
Ollama                     | (external image)                    | EXTERNAL    | 11434
ComfyUI                    | (external image)                    | EXTERNAL    | 8188
MCP: Documents             | portal_mcp/documents/               | [status]    | 8913
MCP: Music                 | portal_mcp/generation/music_mcp     | [status]    | 8912
MCP: TTS (kokoro primary)  | portal_mcp/generation/tts_mcp       | [status]    | 8916
MCP: Whisper               | portal_mcp/generation/whisper_mcp   | [status]    | 8915
MCP: ComfyUI bridge        | portal_mcp/generation/comfyui_mcp   | [status]    | 8910
MCP: Video bridge          | portal_mcp/generation/video_mcp     | [status]    | 8911
MCP: Sandbox (DinD)        | portal_mcp/execution/               | [status]    | 8914
DinD                       | (external image)                    | EXTERNAL    | —
Telegram Adapter           | portal_channels/telegram/bot.py     | [status]    | —
Slack Adapter              | portal_channels/slack/bot.py        | [status]    | —
openwebui_init.py          | scripts/openwebui_init.py           | [status]    | —
```

Status from Phase 3 evidence only.

### 6B — Production Readiness Score

Score each dimension 0-10 with evidence from Phase 3:

```
PRODUCTION READINESS SCORE
==========================
Dimension                    Score  Evidence ref
---------------------------  -----  --------
Security (secrets)            /10   [3D + 2E]
Security (sandbox DinD)       /10   [3E zero-setup check]
Multi-user readiness          /10   [3D compose check]
Routing correctness           /10   [3A + 3B + 3C]
Capacity (25 users)           /10   [compose: OLLAMA_NUM_PARALLEL, PIPELINE_WORKERS]
Zero-setup compliance         /10   [3E all checks pass/fail]
Model catalog accuracy        /10   [2B group coverage + hf.co/ format]
Operational tooling           /10   [3D launch commands]
Test coverage                 /10   [Phase 5 coverage %]
Code quality                  /10   [Phase 0D violation count]
Documentation                 /10   [docs/ files verified]
Deployment cleanliness        /10   [healthchecks, volumes, restart policies]
---------------------------  -----
TOTAL                          /120

Normalized (out of 100):      /100
```

Score ≥ 80 = Release Candidate. 70-79 = Close, list blockers. < 70 = Not ready, list blockers.

---

## Output Artifacts

Produce all three in full.

### ARTIFACT 1: `P5_AUDIT_REPORT.md`

Sections:
1. Executive Summary (score, verdict, top 5 issues)
2. Delta Summary (delta runs only)
3. Baseline Status (Phase 0I block)
4. Behavioral Verification Summary (Phase 3G matrix — fully populated)
5. Configuration Audit (Phase 2 findings)
6. Code Findings Register

```
FINDING-NNN
File:           path:line-range OR function name
Severity:       Blocker / High / Medium / Low / Nit
Category:       Correctness / Security / Performance / Maintainability / Tests / Docs
Observation:    what the code or output shows (with exact evidence)
Impact:         why it matters
Recommendation: specific change with file:line if possible
Effort:         S / M / L
Risk of fix:    Low / Med / High
Verified by:    <exact command that produced this finding>
```

7. Test Coverage & Gaps
8. Architecture & Component Map (Phase 6A)
9. Zero-Setup Compliance (Phase 3E)
10. Production Readiness Score (Phase 6B)

### ARTIFACT 2: `P5_ACTION_PROMPT.md`

**Bootstrap block (copy-paste ready, hard gate):**
```bash
cd /path/to/portal-5
source .venv/bin/activate || (uv venv && source .venv/bin/activate && uv pip install -e ".[dev]")
git checkout main && git pull

# HARD GATE — must pass before touching any code
python3 -m pytest tests/ -q --tb=no || { echo "TESTS FAILING — classify failures first"; exit 1; }
python3 -m ruff check portal_pipeline/ scripts/ --quiet || { echo "LINT VIOLATIONS — fix first"; exit 1; }
echo "Gates passed — safe to proceed"
```

Task format:
```
TASK-NNN
Tier:         1 (fix now) / 2 (fix soon) / 3 (backlog)
File(s):      path(s) with line range(s) where possible
Category:     Correctness / Security / ZeroSetup / Tests / Docs / Performance
Finding:      one sentence — ref FINDING-NNN
Action:       specific change with exact line ranges
Risk:         Low / Med / High
Acceptance:   command that proves the fix worked
```

Tier definitions:
- **Tier 1:** Anything that prevents `./launch.sh up` from working, any security finding,
  any test failure, any zero-setup compliance failure
- **Tier 2:** Code quality issues, missing tests, degraded features, STUB features
- **Tier 3:** Backlog items, optimizations, docs improvements

### ARTIFACT 3: `P5_ROADMAP.md`

Preserve all existing `P5-ROAD-NNN` IDs. Add new entries for every Phase 3G FAIL.

New entry format:
```
P5-ROAD-NNN | P1/P2/P3-SEVERITY | Title | OPEN | Source: review-agent-v3 [date]
Description: one sentence
Evidence:    <command + output>
```

---

**COMPLIANCE CHECK**
- Hard constraints met: Yes / No (list violations)
- Output format followed: Yes / No
- All findings backed by runtime or static evidence: Yes / No
- Uncertainty Log: [claims with confidence < 90%, or "None"]
