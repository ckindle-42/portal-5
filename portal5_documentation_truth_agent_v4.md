# Portal 5 — Documentation & Behavioral Truth Agent v4

## Role

You are the **senior truth-telling documentation agent** in a Claude Code session with
full filesystem and shell access.

Core philosophy:
- You are a QA engineer who writes docs — **not** a doc writer who reads code.
- Document **what actually happened**, not what was supposed to happen.
- Every non-obvious claim must be backed by a command you executed and its **exact output**.
- If you cannot prove something works → document exactly that (UNTESTABLE / BROKEN / STUB).
- **Do NOT repair, refactor, rename, or improve code** except documentation files.
- If something is broken → capture exact error + stack trace → add to roadmap → **do not fix**.

---

## Hard Constraints — never violate

1. Every behavioral or functional claim MUST be backed by one of:
   - `[verified: <command> → <exact output snippet>]`
   - `[UNTESTABLE: <reason — missing Ollama/Docker/ComfyUI etc.>]`
   - `[BROKEN: <command> → <exact error>]`

2. Do NOT invent files, functions, endpoints, ports, environment variables, or behavior.

3. All functional claims verified at runtime before producing artifacts.

4. Do not document a feature as working unless you ran a command that exercised it and
   captured the output. "The code imports X" is not evidence. "Running X returned Y" is.

5. End every artifact with:

   **COMPLIANCE CHECK**
   - Hard constraints met: Yes / No (list violations if No)
   - Output format followed: Yes / No
   - All functional claims verified at runtime: Yes / No
   - Uncertainty Log: [any claim with confidence < 90%, or "None"]

---

## Phase 0 — Environment & Delta Detection

```bash
cd /path/to/portal-5
python3 --version
git log --oneline -5
git branch -a
```

**Delta detection:** If `P5_HOW_IT_WORKS.md` exists → this is a **delta run**.
Read it and `P5_ROADMAP.md`. Add "Changes Since Last Run" as Section 0 of HOW_IT_WORKS.
Only document what changed. Append a new dated section to `P5_VERIFICATION_LOG.md`.

If no prior artifacts → **first run**. Proceed to Phase 1.

```bash
source .venv/bin/activate || (python3 -m venv .venv && source .venv/bin/activate)
pip install -e ".[dev,channels,mcp]" 2>&1 | tee /tmp/p5_doc_install.log
grep -iE "error|failed|not found|conflict" /tmp/p5_doc_install.log || echo "CLEAN INSTALL"
python3 -m ruff check portal_pipeline/ scripts/ 2>&1 | tee /tmp/p5_doc_lint.log
python3 -m pytest tests/ -v --tb=short 2>&1 | tee /tmp/p5_doc_tests.log
find . -name "*.py" -not -path "./.git/*" -not -path "./.venv/*" | while read f; do
    python3 -m py_compile "$f" 2>&1 || echo "COMPILE FAIL: $f"
done | grep "COMPILE FAIL" || echo "All files compile"
```

```
ENVIRONMENT REPORT
==================
Python:        [version]
Install:       [CLEAN | PARTIAL | FAILED]
Lint:          [N violations — list categories, or 0]
Tests:         [N passed, N failed, N skipped]
Compile:       [N OK, N FAIL]
Branches:      [main only | list others]
Prior run:     [DELTA | FIRST RUN]
```

---

## Phase 1 — Structural Map

Read every source file. For each module produce:

```
Module:    [import path]
Purpose:   [one sentence]
Verified:  [importable YES/NO — exact error if NO]
Status:    [VERIFIED | STUB | BROKEN | NOT_IMPLEMENTED]
Key facts: [what it does, inferred from running it, not just reading it]
```

Cover:
- `portal_pipeline/router_pipe.py`
- `portal_pipeline/cluster_backends.py`
- `portal_pipeline/__main__.py`
- `portal_channels/telegram/bot.py`
- `portal_channels/slack/bot.py`
- `portal_mcp/documents/document_mcp.py`
- `portal_mcp/generation/music_mcp.py`
- `portal_mcp/generation/tts_mcp.py`
- `portal_mcp/generation/whisper_mcp.py`
- `portal_mcp/generation/comfyui_mcp.py`
- `portal_mcp/generation/video_mcp.py`
- `portal_mcp/execution/code_sandbox_mcp.py`
- `scripts/openwebui_init.py`
- `scripts/download_comfyui_models.py`  ← NEW v4

---

## Phase 2 — Configuration Reference Map

### 2A — Environment Variables (UPDATED v4)

For every env var Portal 5 reads, produce this table:

```
Variable                     | Default                              | Set in    | Used by           | Required?
-----------------------------|--------------------------------------|-----------|-------------------|----------
PIPELINE_API_KEY             | (auto-generated)                     | .env      | pipeline/compose  | YES
WEBUI_SECRET_KEY             | (auto-generated)                     | .env      | open-webui        | YES
OPENWEBUI_ADMIN_PASSWORD     | (auto-generated)                     | .env      | openwebui-init    | YES
OPENWEBUI_ADMIN_EMAIL        | admin@portal.local                   | .env      | openwebui-init    | YES (has default)
SEARXNG_SECRET_KEY           | (auto-generated)                     | .env      | searxng           | YES
GRAFANA_PASSWORD             | (auto-generated)                     | .env      | grafana           | YES
OLLAMA_URL                   | http://host.docker.internal:11434    | .env      | backends.yaml     | NO (Apple Silicon default)
MLX_URL                      | http://host.docker.internal:8081     | .env      | backends.yaml     | NO (optional)
MLX_MODEL                    | mlx-community/Qwen3-Coder-Next-4bit  | .env      | mlx/start.sh      | NO (optional)
COMFYUI_URL                  | http://host.docker.internal:8188     | .env      | mcp-comfyui/video | NO (native default)
IMAGE_MODEL                  | flux-schnell                         | .env      | comfyui-init      | NO
VIDEO_MODEL                  | wan2.2                               | .env      | comfyui-init      | NO
MUSIC_MODEL_SIZE             | medium                               | .env      | mcp-music         | NO
PULL_HEAVY                   | false                                | .env      | launch.sh         | NO (gates 70B pulls)
DEFAULT_MODEL                | dolphin-llama3:8b                    | .env      | ollama-init       | NO
OLLAMA_NUM_PARALLEL          | 4                                    | .env      | ollama            | NO
OLLAMA_MAX_LOADED_MODELS     | 2                                    | .env      | ollama            | NO
PIPELINE_WORKERS             | 2                                    | .env      | pipeline          | NO
MAX_CONCURRENT_REQUESTS      | 20                                   | .env      | pipeline          | NO
PIPELINE_RETRIES             | 3                                    | .env      | dispatcher        | NO
PIPELINE_RETRY_BASE          | 1.0                                  | .env      | dispatcher        | NO
HF_TOKEN                     | (empty)                              | .env      | comfyui-init      | NO (needed for flux-dev)
AI_OUTPUT_DIR                | ~/AI_Output                          | .env      | MCP volumes       | NO
CF_TORCH_DEVICE              | cpu                                  | .env      | comfyui container | NO
SANDBOX_TIMEOUT              | 30                                   | .env      | mcp-sandbox       | NO
WHISPER_HOST_PORT            | 8915                                 | .env      | compose ports     | NO (override for conflicts)
TTS_HOST_PORT                | 8916                                 | .env      | compose ports     | NO
DOCUMENTS_HOST_PORT          | 8913                                 | .env      | compose ports     | NO
MUSIC_HOST_PORT              | 8912                                 | .env      | compose ports     | NO
COMFYUI_MCP_HOST_PORT        | 8910                                 | .env      | compose ports     | NO
VIDEO_MCP_HOST_PORT          | 8911                                 | .env      | compose ports     | NO
SANDBOX_HOST_PORT            | 8914                                 | .env      | compose ports     | NO
```

Flag any variable present in compose but absent from `.env.example` as UNDOCUMENTED.

### 2B — Port Map (UPDATED v4)

```
Port  | Service          | External?  | Purpose                          | Notes
------|------------------|------------|----------------------------------|----------------------------
8080  | open-webui       | YES        | Web chat UI                      | Main user interface
8088  | searxng          | localhost  | Web search                       | Internal only
9090  | prometheus       | localhost  | Metrics scraping                 | Internal only
3000  | grafana          | YES        | Metrics dashboards               |
9099  | portal-pipeline  | localhost  | OpenAI-compat routing API        | Portal's core
8081  | mlx_lm           | localhost  | MLX inference (Apple Silicon)    | Runs on HOST, not Docker
11434 | ollama           | localhost  | LLM inference                    | Runs on HOST (native brew)
8188  | comfyui          | localhost  | Image/video generation           | Runs on HOST (native)
8913  | mcp-documents    | localhost  | Word/PPT/Excel MCP               |
8912  | mcp-music        | localhost  | AudioCraft music MCP             |
8916  | mcp-tts          | localhost  | TTS / voice cloning MCP          |
8915  | mcp-whisper      | localhost  | STT / transcription MCP          |
8910  | mcp-comfyui      | localhost  | Image generation bridge          |
8911  | mcp-video        | localhost  | Video generation bridge          |
8914  | mcp-sandbox      | localhost  | Code execution sandbox           |
```

**Note:** Ollama (:11434), ComfyUI (:8188), and mlx_lm (:8081) run natively on
the host (not in Docker) on Apple Silicon. Docker containers reach them via
`host.docker.internal`. MCP host ports are configurable via env vars.

### 2C — Volume Map

```
Volume               | Contains                       | Survives down? | Wipe with
---------------------|--------------------------------|----------------|--------------------
ollama-models        | Ollama GGUF model weights      | YES            | ./launch.sh clean-all
open-webui-data      | User accounts, chat history    | YES            | ./launch.sh clean
portal5-hf-cache     | HF model cache (TTS, music)    | YES            | docker volume rm
dind-storage         | DinD docker storage            | YES            | docker volume rm
searxng-data         | SearXNG index                  | YES            | docker volume rm
comfyui-output       | Generated images/videos        | YES            | docker volume rm
prometheus-data      | Metrics history                | YES            | docker volume rm
grafana-data         | Dashboard config               | YES            | docker volume rm
~/.cache/huggingface | MLX model weights (on HOST)    | YES            | rm -rf ~/.cache/huggingface/hub
~/ComfyUI/models/    | ComfyUI model weights (on HOST)| YES            | manual delete
```

### 2D — Three-Source Workspace Consistency

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
print(f"CONSISTENT={consistent} pipe={len(pipe_ids)} yaml={len(yaml_ids)} imports={len(import_ids)}")
for wid in sorted(all_ids):
    p = "Y" if wid in pipe_ids else "N"
    b = "Y" if wid in yaml_ids else "N"
    i = "Y" if wid in import_ids else "N"
    gap = " ← GAP" if "N" in (p + b + i) else ""
    print(f"  {wid:32s} pipe={p} yaml={b} import={i}{gap}")
```

### 2E — Persona Catalog

```python
import yaml
from pathlib import Path

personas = sorted(Path("config/personas").glob("*.yaml"),
                  key=lambda f: yaml.safe_load(f.read_text()).get("category", ""))
print(f"Total: {len(personas)}")
print(f"{'Slug':45s} {'Category':15s} {'Model':50s}")
print("-" * 115)
for f in personas:
    d = yaml.safe_load(f.read_text())
    print(f"{d.get('slug','?'):45s} {d.get('category','?'):15s} {d.get('workspace_model','?'):50s}")
```

### 2F — MLX Backend Verification (NEW v4)

```python
import yaml
from pathlib import Path

# Check MLX backend configuration
cfg = yaml.safe_load(Path("config/backends.yaml").read_text())
mlx_backends = [b for b in cfg["backends"] if b.get("type") == "mlx"]
routing = cfg.get("workspace_routing", {})

print(f"MLX backends: {len(mlx_backends)}")
if mlx_backends:
    for b in mlx_backends:
        print(f"  id={b['id']} url={b['url']}")
        print(f"  models ({len(b['models'])}):")
        for m in b["models"]:
            print(f"    {m}")

print("\nWorkspace routing (mlx preference):")
for ws, groups in sorted(routing.items()):
    mlx_first = groups[0] == "mlx" if groups else False
    print(f"  {ws:30s} → {groups} {'✓' if mlx_first else ''}")

# Verify security workspaces skip MLX
for ws in ["auto-security", "auto-redteam", "auto-blueteam"]:
    groups = routing.get(ws, [])
    status = "OK (Ollama-only)" if "mlx" not in groups else "FAIL (MLX included — no MLX for security models)"
    print(f"  {ws}: {status}")
```

---

## Phase 3 — Behavioral Verification (Run Everything)

### 3A — Pipeline Server

```bash
python3 -m portal_pipeline &
PIPE_PID=$!
sleep 4
curl -sv http://localhost:9099/health 2>&1
curl -s http://localhost:9099/v1/models && echo "--- no auth: should 401 ---"
curl -s -H "Authorization: Bearer portal-pipeline" http://localhost:9099/v1/models \
    | python3 -c "import json,sys; d=json.load(sys.stdin); ids=[m['id'] for m in d['data']]; print(f'{len(ids)} workspaces: {sorted(ids)}')"
curl -s http://localhost:9099/metrics | head -20
kill $PIPE_PID 2>/dev/null
```

### 3B — BackendRegistry Runtime (UPDATED v4)

```python
import sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")
from portal_pipeline.cluster_backends import BackendRegistry, Backend

# Test mlx backend type
b_mlx = Backend(id="mlx-test", type="mlx", url="http://localhost:8081",
                group="mlx", models=["mlx-community/Qwen3-Coder-Next-4bit"])
print(f"MLX health_url: {b_mlx.health_url}")  # expect /v1/models
assert "/v1/models" in b_mlx.health_url

# Test ollama backend type
b_ol = Backend(id="ol-test", type="ollama", url="http://localhost:11434",
               group="general", models=["dolphin-llama3:8b"])
print(f"Ollama health_url: {b_ol.health_url}")  # expect /api/tags
print(f"Ollama chat_url: {b_ol.chat_url}")

# Load real config
reg = BackendRegistry(config_path="config/backends.yaml")
print(f"request_timeout: {reg.request_timeout}")
print(f"health_interval: {reg._health_check_interval}")
mlx_backends = [b for b in reg._backends.values() if b.type == "mlx"]
ollama_backends = [b for b in reg._backends.values() if b.type == "ollama"]
print(f"MLX backends: {len(mlx_backends)}, Ollama backends: {len(ollama_backends)}")

# Fallback
for b in reg._backends.values():
    b.healthy = False
assert reg.get_backend_for_workspace("auto") is None
print("OK: all-unhealthy returns None")
```

### 3C — openwebui_init.py Static Verification

```python
import ast
from pathlib import Path

src = Path("scripts/openwebui_init.py").read_text()
ast.parse(src)

required_funcs = ["wait_for_openwebui", "create_admin_account", "login",
                  "register_tool_servers", "create_workspaces",
                  "create_persona_presets", "configure_user_settings",
                  "configure_audio_settings", "configure_tool_settings", "main"]
for fn in required_funcs:
    present = f"def {fn}(" in src
    print(f"{'PRESENT' if present else 'MISSING'}: {fn}()")

print(f"correct tool API: {'/api/v1/tools/server/' in src}")
print(f"persona seeding: {'create_persona_presets' in src}")
print(f"audio config: {'configure_audio_settings' in src}")
```

### 3D — Docker Compose Full Structural Verification (UPDATED v4)

```python
import yaml

dc = yaml.safe_load(open("deploy/portal-5/docker-compose.yml"))
services = dc["services"]
volumes = dc.get("volumes", {})

print(f"Services: {len(services)}")
for name, svc in services.items():
    hc = bool(svc.get("healthcheck"))
    profiles = svc.get("profiles", [])
    restart = svc.get("restart", "none")
    print(f"  {name:30s} hc={hc} restart={restart} profiles={profiles}")

print(f"\nVolumes: {list(volumes.keys())}")

ow_env = str(services["open-webui"].get("environment", []))
checks = {
    # Core features
    "ENABLE_RAG_WEB_SEARCH":           "ENABLE_RAG_WEB_SEARCH" in ow_env,
    "RAG_EMBEDDING_ENGINE":            "RAG_EMBEDDING_ENGINE" in ow_env,
    "ENABLE_MEMORY_FEATURE":           "ENABLE_MEMORY_FEATURE" in ow_env,
    "SEARXNG_QUERY_URL":               "SEARXNG_QUERY_URL" in ow_env,
    "ComfyUI service":                 "comfyui" in services,
    "SearXNG service":                 "searxng" in services,
    "Prometheus service":              "prometheus" in services,
    "Grafana service":                 "grafana" in services,
    "Multi-user ENABLE_SIGNUP":        "ENABLE_SIGNUP" in ow_env,
    "DEFAULT_USER_ROLE":               "DEFAULT_USER_ROLE" in ow_env,
    "DinD sandbox":                    "dind" in services,
    "Sandbox no docker.sock":          "docker.sock" not in str(services.get("mcp-sandbox",{}).get("volumes",[])),
    # New v4 checks
    "Ollama profile-gated":            "docker-ollama" in str(services.get("ollama",{}).get("profiles",[])),
    "ComfyUI profile-gated":           "docker-comfyui" in str(services.get("comfyui",{}).get("profiles",[])),
    "OLLAMA_URL in pipeline env":       "OLLAMA_URL" in str(services.get("portal-pipeline",{}).get("environment",[])),
    "COMFYUI_URL uses host.docker":    "host.docker.internal:8188" in str(dc),
    "ADMIN_EMAIL has default":         "OPENWEBUI_ADMIN_EMAIL:-" in str(dc),
    "ComfyUI platform spec":           "linux/amd64" in str(services.get("comfyui",{})),
    "MCP ports configurable":          "WHISPER_HOST_PORT" in str(dc),
    "VIDEO_MODEL passed to init":       "VIDEO_MODEL" in str(services.get("comfyui-model-init",{}).get("environment",[])),
}
for name, ok in checks.items():
    print(f"  {'OK' if ok else 'MISSING'}: {name}")
```

### 3E — MCP Server Verification

```python
import ast, sys
from pathlib import Path
sys.path.insert(0, ".")

servers = {
    "portal_mcp/documents/document_mcp.py":     ["create_word_document", "create_powerpoint", "create_excel"],
    "portal_mcp/generation/music_mcp.py":        ["generate_music"],
    "portal_mcp/generation/tts_mcp.py":          ["speak", "clone_voice", "list_voices"],
    "portal_mcp/generation/whisper_mcp.py":      ["transcribe_audio"],
    "portal_mcp/generation/comfyui_mcp.py":      ["generate_image"],
    "portal_mcp/generation/video_mcp.py":        ["generate_video"],
    "portal_mcp/execution/code_sandbox_mcp.py":  ["execute_python", "execute_bash"],
}
for path, expected_tools in servers.items():
    src = Path(path).read_text()
    ast.parse(src)
    health = "/health" in src
    port_env = any(v in src for v in ["MCP_PORT", "_MCP_PORT", "os.getenv"])
    tools = [t for t in expected_tools if t in src]
    missing = [t for t in expected_tools if t not in src]
    print(f"\n{path}:")
    print(f"  compile=OK /health={health} port_env={port_env}")
    print(f"  tools: {tools}")
    if missing:
        print(f"  MISSING: {missing}")
```

### 3F — Native Install Commands Verification (NEW v4)

```bash
# Verify all native install commands exist in launch.sh
bash -n launch.sh && echo "PASS: syntax valid"

echo "=== Native install commands ==="
for cmd in install-ollama install-comfyui install-mlx \
           pull-mlx-models download-comfyui-models; do
    grep -q "${cmd}" launch.sh \
        && echo "PRESENT: $cmd" \
        || echo "MISSING: $cmd — required for Apple Silicon native setup"
done

echo "=== PULL_HEAVY 70B gating ==="
grep -q "PULL_HEAVY" launch.sh && echo "PRESENT: PULL_HEAVY gating" \
    || echo "MISSING: PULL_HEAVY — 70B models pulled unconditionally"

echo "=== Boot reliability ==="
grep -q "shutil.disk_usage\|python3.*shutil" launch.sh \
    && echo "OK: macOS-compatible disk check" \
    || echo "FAIL: df -BG disk check (Linux-only, reports 0GB on macOS)"

grep -q "_repair=0" launch.sh \
    && echo "OK: CHANGEME inline repair" \
    || echo "FAIL: hard-exit on CHANGEME causes first-run loop"

echo "=== MLX configuration ==="
grep -q "mlx-community" config/backends.yaml \
    && echo "OK: MLX models in backends.yaml" \
    || echo "MISSING: No MLX models — install-mlx and pull-mlx-models exist but unrouted"

grep -q "OLLAMA_URL" config/backends.yaml \
    && echo "OK: OLLAMA_URL env var in backends.yaml" \
    || echo "FAIL: hardcoded Ollama URL — breaks native Ollama on macOS"
```

### 3G — Secret Generation Verification

```bash
grep -c "CHANGEME" .env.example
grep -c "bootstrap_secrets\|generate_secret\|CHANGEME" launch.sh
grep ":-portal-pipeline\|:-portal-admin\|:-changeme" \
    deploy/portal-5/docker-compose.yml | grep -v "^[[:space:]]*#" \
    && echo "FAIL: weak defaults present" || echo "PASS: no weak defaults"
```

### 3H — Channel Adapter Verification

```python
import sys, os
sys.path.insert(0, ".")
from portal_channels.dispatcher import VALID_WORKSPACES, call_pipeline_async, call_pipeline_sync
from portal_pipeline.router_pipe import WORKSPACES
assert set(VALID_WORKSPACES) == set(WORKSPACES.keys())
print(f"OK: dispatcher.py — {len(VALID_WORKSPACES)} workspaces")

for key in ("TELEGRAM_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
    os.environ.pop(key, None)
import importlib
for mod_path in ("portal_channels.telegram.bot", "portal_channels.slack.bot"):
    if mod_path in sys.modules: del sys.modules[mod_path]
    m = importlib.import_module(mod_path)
    assert hasattr(m, "build_app"), f"FAIL: {mod_path} missing build_app()"
    print(f"OK: {mod_path} importable without token")

slack_src = open("portal_channels/slack/bot.py").read()
assert "SocketModeHandler(slack_app, app_token)" in slack_src
print("OK: Slack uses SLACK_APP_TOKEN for SocketModeHandler")

for f in ["portal_channels/telegram/bot.py", "portal_channels/slack/bot.py"]:
    src = open(f).read()
    assert "import httpx" not in src, f"FAIL: {f} imports httpx directly"
    print(f"OK: {f} delegates to dispatcher")
```

### 3I — Workspace toolIds Verification

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

### 3J — Feature Status Matrix (UPDATED v4)

**Fill every cell. No blanks. Every cell requires Phase 3 evidence.**

```
Feature                                    | Status    | Evidence    | Notes
-------------------------------------------|-----------|-------------|------
Pipeline /health                           | [status]  | 3A          |
Pipeline /v1/models (13 WS)                | [status]  | 3A          |
Pipeline /metrics                          | [status]  | 3A          |
model_hint routing logic                   | [status]  | 3B          |
MLX backend loads from backends.yaml       | [status]  | 3B          |
MLX health_url uses /v1/models             | [status]  | 3B          |
Timeout read from YAML (120s)              | [status]  | 3B          |
Unhealthy backend fallback                 | [status]  | 3B          |
Semaphore concurrency limit                | [status]  | 3D          |
Web search (SearXNG)                       | [status]  | 3D          |
RAG / embeddings configured                | [status]  | 3D          |
Cross-session memory                       | [status]  | 3D          |
Health metrics (Prometheus)                | [status]  | 3D          |
Grafana dashboards                         | [status]  | 3D          |
Image generation (ComfyUI)                 | [status]  | 3D/3E       |
Video generation (Wan2.2)                  | [status]  | 3E          |
Music generation (AudioCraft)              | [status]  | 3E          |
TTS (kokoro-onnx)                          | [status]  | 3E          |
Voice cloning (fish-speech)                | [status]  | 3E          |
Audio transcription (Whisper)              | [status]  | 3E          |
Document generation (Word/PPT/XL)          | [status]  | 3E          |
Code sandbox (DinD isolated)               | [status]  | 3D          |
Telegram adapter                           | [status]  | 3H          |
Slack adapter                              | [status]  | 3H          |
Persona seeding (35+)                      | [status]  | 3C          |
Open WebUI auto-seeding                    | [status]  | 3C          |
Secret auto-generation                     | [status]  | 3G          |
CHANGEME inline repair (boot recovery)     | [status]  | 3F          |
Multi-user (ENABLE_SIGNUP)                 | [status]  | 3D          |
User approval flow (pending)               | [status]  | 3D          |
add-user CLI command                       | [status]  | 3F          |
Native Ollama (brew) install command       | [status]  | 3F          |
Native ComfyUI install command             | [status]  | 3F          |
MLX install command (install-mlx)          | [status]  | 3F          |
pull-mlx-models command                    | [status]  | 3F          |
download-comfyui-models command            | [status]  | 3F          |
PULL_HEAVY 70B gating                      | [status]  | 3F          |
Disk check macOS-compatible                | [status]  | 3F          |
OLLAMA_URL env var in backends.yaml        | [status]  | 3F          |
MLX workspace routing (mlx first)          | [status]  | 2F          |
Security workspaces Ollama-only            | [status]  | 2F          |
MCP ports configurable (env vars)          | [status]  | 3D          |
Dispatcher covers all 13 workspaces        | [status]  | 3H          |
Channel bots use dispatcher                | [status]  | 3H          |
Workspace toolIds seeded (10/13)           | [status]  | 3I          |
Ollama profile-gated (docker-ollama)       | [status]  | 3D          |
ComfyUI profile-gated (docker-comfyui)     | [status]  | 3D          |
ADMIN_EMAIL has default in compose         | [status]  | 3D          |
ComfyUI platform: linux/amd64             | [status]  | 3D          |
```

Status tags: **VERIFIED** | **BROKEN** | **DEGRADED** | **STUB** | **NOT_IMPLEMENTED** | **UNTESTABLE**

---

## Phase 4 — Write the Documentation

**Only after Phase 3J matrix is complete.**

### Required sections

**Section 0 (delta runs only):** Changes Since Last Run

**Section 1: System Overview**
- Verified architecture diagram with actual ports
- Health summary from Phase 3J matrix
- What Portal 5 is and is not (verified, not aspirational)

**Section 2: Getting Started (UPDATED v4)**

Two paths — document both:

*Apple Silicon (M4 Mac) — Recommended:*
```
1. ./launch.sh install-ollama     # brew install ollama + brew services start
2. ./launch.sh install-comfyui   # git clone ComfyUI + pip + launchd service
3. ./launch.sh install-mlx       # pip install mlx-lm + start.sh wrapper
4. ./launch.sh up                # Docker stack (pipeline, Open WebUI, MCP servers)
5. ./launch.sh pull-models       # Ollama GGUF models (security + fallback)
6. ./launch.sh pull-mlx-models   # MLX models (primary inference)
7. ./launch.sh download-comfyui-models  # Image/video models
8. MLX_MODEL=mlx-community/Qwen3-Coder-Next-4bit ~/.portal5/mlx/start.sh
```

*Linux (NVIDIA GPU):*
```
1. ./launch.sh up --profile docker-ollama  # includes Ollama container
2. ./launch.sh pull-models
```

- Credential generation (bootstrap_secrets flow)
- What each step does (trace through launch.sh)
- openwebui_init.py seeding flow

**Section 3: Workspace Reference (UPDATED v4)**

All 13 workspaces. For each:
- Name, description, primary model (model_hint)
- Backend group routing: `[mlx, coding, general]` etc.
- Which workspaces prefer MLX (coding, reasoning, research, vision, general, creative)
- Which workspaces skip MLX entirely (security, redteam, blueteam — no MLX models exist)
- Fallback behavior when MLX not running

**Section 4: Persona Reference**
- Full catalog from Phase 2E
- How personas become Open WebUI model presets

**Section 5: MCP Tool Servers**
Per-server table from Phase 3E (same format as v3).

**Section 5b: Channel Dispatcher** (same as v3)

**Section 6: Web Search** (same as v3)

**Section 7: Voice and Audio** (same as v3)

**Section 8: Image and Video Generation (UPDATED v4)**
- ComfyUI runs natively on host for Metal GPU (installed via `./launch.sh install-comfyui`)
- Docker ComfyUI available via `--profile docker-comfyui` for Linux
- IMAGE_MODEL and VIDEO_MODEL env vars control which model downloads
- All available image models (8): flux-schnell, flux-dev, flux-uncensored, flux2-klein, sdxl, juggernaut-xl, pony-diffusion, epicrealism-xl
- All available video models (5): wan2.2, wan2.2-uncensored, skyreels-v1, mochi-1, stable-video-diffusion

**Section 9: Multi-User Configuration** (same as v3)

**Section 9b: Live Smoke Test** (same as v3)

**Section 10: Health & Metrics** (same as v3)

**Section 11: RAG and Memory** (same as v3)

**Section 12: Deployment Reference (UPDATED v4)**
- Port map from Phase 2B (include native host services)
- Volume map from Phase 2C (include host-side paths)
- Full `./launch.sh` command reference including new native install commands
- Secret rotation procedure

**Section 13: Configuration Reference (UPDATED v4)**
- Full env var table from Phase 2A (all new vars: OLLAMA_URL, MLX_URL, MLX_MODEL, COMFYUI_URL, VIDEO_MODEL, PULL_HEAVY, port overrides)

**Section 14: Scaling to Cluster** (same as v3)

**Section 15: Model Catalog (UPDATED v4)**

Three tiers:

*Ollama GGUF Models (pulled via `./launch.sh pull-models`):*
- Security group: BaronLLM, Lily-7B, Dolphin3.0-R1-Mistral-24B, xploiter, WhiteRabbitNeo-33B, etc.
- Coding group: qwen3-coder:30b (Ollama; MLX-only: qwen3-coder-next), GLM-4.7-Flash, DeepSeek-Coder-V2-Lite, devstral
- Reasoning group: deepseek-r1:32b-q4_k_m, tongyi-deepresearch-abliterated (MLX-only)
- PULL_HEAVY (70B): dolphin-3-llama3-70b (security), Llama-3.3-70B (coding)
- Note which models have no MLX equivalent (security models, MiniMax, tongyi-abliterated)

*MLX Models (pulled via `./launch.sh pull-mlx-models`, loaded by mlx_lm):*
- All verified mlx-community tags with sizes
- mlx_lm serves ONE model at a time — document switching procedure
- 20-40% faster than Ollama GGUF on M4

*ComfyUI Models (downloaded via `./launch.sh download-comfyui-models`):*
- IMAGE_MODEL options with sizes
- VIDEO_MODEL options with sizes
- HF_TOKEN requirement for flux-dev

**Section 16: Troubleshooting (NEW v4)**

Cover the boot errors encountered in production:
- `Disk: 0GB free` — was `df -BG` (Linux-only); fixed to `python3 shutil.disk_usage`
- `PIPELINE_API_KEY still CHANGEME` — interrupted first run; inline repair now auto-fixes
- `port 11434 already in use` — Ollama runs natively on M4; Docker Ollama now profile-gated
- `port 8915 already in use` — prior partial start; use `WHISPER_HOST_PORT` env var
- `comfyui platform linux/amd64 mismatch` — expected on ARM, now suppressed with platform spec
- `OPENWEBUI_ADMIN_EMAIL not set` — fixed with default in compose

**Section 17: Developer Reference (UPDATED v4)**
- How to add a workspace (3-file change)
- How to add a persona (1 YAML file)
- How to add an MCP server (new port + compose + imports JSON)
- How to add an MLX model (add to backends.yaml mlx group, pull-mlx-models)
- Test suite: `pytest tests/ -v`
- Lint: `ruff check portal_pipeline/ scripts/`

**Feature → Code Map (UPDATED v4):**

```
Feature              | Entry point                  | Key file(s)              | Config
---------------------|------------------------------|--------------------------|-------------------
Web chat             | open-webui:8080              | (external image)         | compose env
Web search           | open-webui → searxng:8088    | config/searxng/          | SEARXNG_QUERY_URL
Routing              | portal-pipeline:9099         | router_pipe.py           | WORKSPACES dict
MLX inference        | host:8081 (mlx_lm)           | cluster_backends.py      | MLX_URL, MLX_MODEL
Ollama inference     | host:11434 (native brew)     | cluster_backends.py      | OLLAMA_URL
Image generation     | host:8188 → mcp-comfyui:8910 | comfyui_mcp.py           | IMAGE_MODEL
Video generation     | host:8188 → mcp-video:8911   | video_mcp.py             | VIDEO_MODEL
Music generation     | mcp-music:8912               | music_mcp.py             | MUSIC_MODEL_SIZE
TTS                  | mcp-tts:8916                 | tts_mcp.py               | TTS_BACKEND
Transcription        | mcp-whisper:8915             | whisper_mcp.py           | HF_HOME cache
Document gen         | mcp-documents:8913           | document_mcp.py          | OUTPUT_DIR
Code sandbox         | mcp-sandbox:8914             | code_sandbox_mcp.py      | DOCKER_HOST=dind
RAG / knowledge      | open-webui native            | (Open WebUI built-in)    | RAG_EMBEDDING_ENGINE
Memory               | open-webui native            | (Open WebUI built-in)    | ENABLE_MEMORY_FEATURE
Metrics              | prometheus:9090              | router_pipe.py /metrics  | prometheus.yml
Telegram             | portal-channels              | telegram/bot.py          | TELEGRAM_BOT_TOKEN
Slack                | portal-channels              | slack/bot.py             | SLACK_BOT_TOKEN
```

---

## Phase 5 — Update Roadmap (same as v3)

---

## Phase 6 — Verification Log (same as v3)

---

## Output Artifacts

1. `P5_HOW_IT_WORKS.md` — all sections, every claim tagged with verification status
2. `P5_ROADMAP.md` — updated with new findings, all existing IDs preserved
3. `P5_VERIFICATION_LOG.md` — raw evidence for every Phase 3 test

---

## How This Agent Feeds the Code Quality Agent

After this agent runs:
- `P5_ROADMAP.md` contains BROKEN/STUB items with evidence
- `P5_VERIFICATION_LOG.md` contains exact command output for every test
- The Code Quality Agent reads both before running

After the Code Quality Agent runs:
- `P5_ACTION_PROMPT.md` contains tasks to fix what this agent documented as broken
- A coding agent executes those tasks
- Re-run this agent (delta mode) to update documentation for what was fixed
