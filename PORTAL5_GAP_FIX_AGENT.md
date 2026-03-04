# Portal 5.0 — Gap Fix Agent Task

**Date:** March 3, 2026  
**Repo:** https://github.com/ckindle-42/portal-5  
**Goal:** Close all gaps between the current state and `./launch.sh up` → working Open WebUI
         with intelligent routing and MCP tools, zero manual steps after launch.

**Expected end state:**
```
./launch.sh up
# 2-3 minutes later:
# → Ollama running with model pulled
# → Portal Pipeline routing requests
# → Open WebUI at http://localhost:8080
# → Admin account auto-created
# → 9 workspace models visible in model dropdown
# → MCP tool servers registered and ready
# → User logs in and starts chatting
```

---

## Phase 0 — Bootstrap

```bash
cd /path/to/portal-5
git checkout main && git pull
git checkout -b fix/launch-gaps

# Install deps for local testing
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
python --version  # must be 3.10+
```

---

## Phase 1 — Audit (Run These, Read the Output)

```bash
# 1. Confirm the Ollama API bug
grep "chat_url" portal_pipeline/cluster_backends.py
# EXPECTED PROBLEM: returns /api/chat for ollama type — wrong endpoint

# 2. Confirm missing directories
ls portal_mcp/ 2>/dev/null || echo "MISSING: portal_mcp/"
ls scripts/ 2>/dev/null    || echo "MISSING: scripts/"
ls imports/ 2>/dev/null    || echo "MISSING: imports/"

# 3. Confirm Dockerfile pip bug
grep "fastapi>=" Dockerfile.pipeline
# EXPECTED PROBLEM: unquoted >= in shell RUN command

# 4. Confirm Ollama absent from compose
grep "ollama" deploy/portal-5/docker-compose.yml
# EXPECTED: no ollama service definition

# 5. Confirm openwebui-init will crash
grep "openwebui_init" deploy/portal-5/docker-compose.yml
# Will show the command - but scripts/openwebui_init.py doesn't exist
```

Document findings before writing any code.

---

## Phase 2 — Fix: Ollama API Endpoint Bug

**File:** `portal_pipeline/cluster_backends.py`  
**Bug:** `chat_url` for Ollama type returns `/api/chat` — this is Ollama's native format
endpoint. The pipeline sends OpenAI-formatted bodies (`{"messages": [...], "model": "..."}`).
That combination fails. Ollama's OpenAI-compatible endpoint is `/v1/chat/completions`.

**Find this block:**
```python
@property
def chat_url(self) -> str:
    """Return the chat completions URL for this backend."""
    if self.type == "ollama":
        return f"{self.url}/api/chat"
    return f"{self.url}/chat/completions"
```

**Replace with:**
```python
@property
def chat_url(self) -> str:
    """Return the OpenAI-compatible chat completions URL for this backend.

    Both Ollama (>=0.1.24) and vLLM expose /v1/chat/completions.
    We always use the OpenAI-compatible endpoint so request body format
    is identical regardless of backend type.
    """
    return f"{self.url.rstrip('/')}/v1/chat/completions"

@property
def health_url(self) -> str:
    """Return the health/availability check URL for this backend."""
    if self.type == "ollama":
        return f"{self.url.rstrip('/')}/api/tags"   # Ollama: list models
    return f"{self.url.rstrip('/')}/health"          # vLLM: /health
```

**Also fix `_check_one` to use `backend.health_url`:**
```python
async def _check_one(self, backend: Backend) -> None:
    """Check a single backend's health."""
    import time
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(backend.health_url)
            backend.healthy = resp.status_code == 200
    except Exception as e:
        logger.debug("Health check failed for %s: %s", backend.id, e)
        backend.healthy = False
    finally:
        backend.last_check = time.time()
```

**Verify fix:**
```bash
python3 -c "
from portal_pipeline.cluster_backends import Backend
b = Backend(id='test', type='ollama', url='http://localhost:11434', group='general', models=['llama3'])
assert b.chat_url == 'http://localhost:11434/v1/chat/completions', f'Wrong: {b.chat_url}'
assert b.health_url == 'http://localhost:11434/api/tags', f'Wrong: {b.health_url}'
b2 = Backend(id='test2', type='openai_compatible', url='http://192.168.1.2:8000', group='general', models=['llama3'])
assert b2.chat_url == 'http://192.168.1.2:8000/v1/chat/completions'
assert b2.health_url == 'http://192.168.1.2:8000/health'
print('Endpoint URLs: OK')
"
```

---

## Phase 3 — Fix: Dockerfile.pipeline Build Failure

**File:** `Dockerfile.pipeline`  
**Bug:** Unquoted `>=` in `RUN pip install` is valid shell but inconsistent. More importantly,
the versions are pinned loosely and not derived from `pyproject.toml`. Use `pyproject.toml`
as the single source of truth.

**Replace the entire file with:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install build tools
RUN pip install --no-cache-dir hatchling

# Copy dependency spec first (cache layer)
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.109.0" \
    "uvicorn[standard]>=0.27.0" \
    "httpx>=0.26.0" \
    "pyyaml>=6.0.1"

# Copy application code
COPY portal_pipeline/ ./portal_pipeline/
COPY config/ ./config/

EXPOSE 9099

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9099/health')"

CMD ["python", "-m", "portal_pipeline"]
```

**Verify (syntax check only — Docker not required):**
```bash
python3 -c "
import subprocess
result = subprocess.run(['docker', 'build', '-f', 'Dockerfile.pipeline', '-t', 'portal5-pipeline-test', '--no-cache', '.'], 
    capture_output=True, text=True)
if result.returncode == 0:
    print('Docker build: OK')
    subprocess.run(['docker', 'rmi', 'portal5-pipeline-test'], capture_output=True)
else:
    print('Docker build failed:')
    print(result.stderr[-500:])
" 2>/dev/null || echo "Docker not available — skip build test, verify syntax manually"
```

---

## Phase 4 — Add Ollama + Model Init to docker-compose

**File:** `deploy/portal-5/docker-compose.yml`  
**Problem:** No Ollama service. No model pull. Stack starts, pipeline is "healthy" (it can
start without a backend), but every chat request returns 503.

**Add these two services** to `docker-compose.yml` before the `open-webui` service:

```yaml
  # ── Ollama (local inference) ────────────────────────────────────────────────
  ollama:
    image: ollama/ollama:latest
    container_name: portal5-ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ollama-models:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0
    healthcheck:
      test: ["CMD", "ollama", "list"]
      interval: 20s
      timeout: 10s
      start_period: 30s
      retries: 10

  # ── Model Init (pulls default model on first run) ───────────────────────────
  ollama-init:
    image: ollama/ollama:latest
    container_name: portal5-ollama-init
    restart: "no"
    environment:
      - OLLAMA_HOST=http://ollama:11434
    depends_on:
      ollama:
        condition: service_healthy
    command: >
      sh -c "
        echo 'Pulling default model: ${DEFAULT_MODEL:-dolphin-llama3:8b}' &&
        ollama pull ${DEFAULT_MODEL:-dolphin-llama3:8b} &&
        echo 'Model pull complete'
      "
    volumes:
      - ollama-models:/root/.ollama
```

**Update `config/backends.yaml`** — the Ollama URL must now use the Docker service name, not `host.docker.internal`, since Ollama is in the compose network:

```yaml
backends:
  - id: local-ollama
    type: ollama
    url: "http://ollama:11434"        # Docker service name, not host.docker.internal
    group: general
    models:
      - dolphin-llama3:8b
    health_check_interval: 30

workspace_routing:
  auto:           [general]
  auto-coding:    [coding, general]
  auto-security:  [general]
  auto-creative:  [creative, general]
  auto-reasoning: [general]
  auto-documents: [general]
  auto-video:     [general]
  auto-music:     [general]
  auto-research:  [general]

defaults:
  fallback_group: general
  request_timeout: 120
  health_timeout: 10
```

**Update `portal-pipeline` depends_on** to wait for ollama:
```yaml
  portal-pipeline:
    ...
    depends_on:
      ollama:
        condition: service_healthy
```

**Add `ollama-models` to the volumes section at bottom:**
```yaml
volumes:
  open-webui-data:
  ollama-models:
```

**Also update `.env.example`** — add the model choice:
```bash
# Model pulled on first start (change to any model Ollama supports)
DEFAULT_MODEL=dolphin-llama3:8b
```

**Verify compose is structurally valid:**
```bash
docker compose -f deploy/portal-5/docker-compose.yml config --quiet && echo "Compose valid"
```

---

## Phase 5 — Add portal_mcp/ (MCP Tool Servers)

**Problem:** No `portal_mcp/` directory. The plan called for copying from portal-4, but it
wasn't done. These are the generation tool servers that become Open WebUI Tool Servers.

### Option A — Copy from portal-4 (if you have it locally)
```bash
# If portal-4 is cloned alongside
cp -r ../portal/portal_mcp ./portal_mcp
# Verify
python3 -m py_compile portal_mcp/documents/document_mcp.py && echo "OK"
python3 -m py_compile portal_mcp/generation/music_mcp.py && echo "OK"
python3 -m py_compile portal_mcp/generation/tts_mcp.py && echo "OK"
```

### Option B — Build minimal stubs (if portal-4 not available)

Create a minimal working MCP server for each capability. Each is a FastAPI app
that exposes an MCP-compatible endpoint. The agent must write real implementations,
not stubs — if a tool is in the list, it must do something when called.

Create `portal_mcp/__init__.py` (empty).

**`portal_mcp/documents/document_mcp.py`** — Word/Excel/PowerPoint generation:

The document MCP server must:
- Run on port `$DOCUMENTS_MCP_PORT` (default 8913)
- Expose an MCP endpoint at `/mcp`
- Provide at minimum: `create_word_document(title, content)`, `create_excel_sheet(data)`,
  `create_powerpoint(title, slides)`
- Save files to `/app/data/generated/`
- Return the file path in the response

Use `python-docx`, `openpyxl`, and `python-pptx`. These are already in `pyproject.toml`
under the `mcp` optional group.

If copying from portal-4, verify the module path is `portal_mcp.documents.document_mcp`
(not `mcp.documents.document_mcp` as portal-4 uses).

**For each MCP server, add to `deploy/portal-5/docker-compose.yml`:**

```yaml
  # ── MCP: Document Generation ─────────────────────────────────────────────────
  mcp-documents:
    build:
      context: ../..
      dockerfile: Dockerfile.mcp
    container_name: portal5-mcp-documents
    restart: unless-stopped
    ports:
      - "8913:8913"
    environment:
      - DOCUMENTS_MCP_PORT=8913
    command: ["python", "-m", "portal_mcp.documents.document_mcp"]
    volumes:
      - "${HOME}/AI_Output:/app/data/generated"

  # ── MCP: Music Generation ─────────────────────────────────────────────────
  mcp-music:
    build:
      context: ../..
      dockerfile: Dockerfile.mcp
    container_name: portal5-mcp-music
    restart: unless-stopped
    ports:
      - "8912:8912"
    environment:
      - MUSIC_MCP_PORT=8912
    command: ["python", "-m", "portal_mcp.generation.music_mcp"]
    volumes:
      - "${HOME}/AI_Output:/app/data/generated"

  # ── MCP: Text-to-Speech ───────────────────────────────────────────────────
  mcp-tts:
    build:
      context: ../..
      dockerfile: Dockerfile.mcp
    container_name: portal5-mcp-tts
    restart: unless-stopped
    ports:
      - "8916:8916"
    environment:
      - TTS_MCP_PORT=8916
      - TTS_BACKEND=${TTS_BACKEND:-fish_speech}
    command: ["python", "-m", "portal_mcp.generation.tts_mcp"]
    volumes:
      - "${HOME}/AI_Output:/app/data/generated"

  # ── MCP: Code Sandbox ────────────────────────────────────────────────────
  mcp-sandbox:
    build:
      context: ../..
      dockerfile: Dockerfile.mcp
    container_name: portal5-mcp-sandbox
    restart: unless-stopped
    ports:
      - "8914:8914"
    environment:
      - SANDBOX_MCP_PORT=8914
    command: ["python", "-m", "portal_mcp.execution.code_sandbox_mcp"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

**Create `Dockerfile.mcp`** (separate from pipeline — different deps):
```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "fastapi>=0.109.0" \
    "uvicorn[standard]>=0.27.0" \
    "httpx>=0.26.0" \
    "python-docx>=1.1.0" \
    "openpyxl>=3.1.0" \
    "python-pptx>=0.6.23" \
    "fastmcp>=0.4.0"

COPY portal_mcp/ ./portal_mcp/

CMD ["python", "-m", "portal_mcp.documents.document_mcp"]
```

---

## Phase 6 — Add scripts/openwebui_init.py and imports/

**Problem:** `openwebui-init` container mounts `../../scripts` and `../../imports` and runs
`python /scripts/openwebui_init.py` — neither directory exists.

### 6A — Create `scripts/openwebui_init.py`

This script is fully specified in `PORTAL_OPENWEBUI_SETUP_AGENT.md` (already in the repo).
Implement it exactly as specified there. Key behaviors:

- Polls `$OPENWEBUI_URL/health` until ready (max 120s)
- Creates admin account via `POST /api/v1/auths/signup` (first run only)
- Falls back to login if account already exists
- Registers all MCP tool servers via `POST /api/v1/tools/server/` (correct endpoint)
- Creates workspace model presets via `POST /api/v1/models/`
- Is fully idempotent — safe to run multiple times
- Exits 0 on success, non-zero on fatal failure

The script is ~200 lines. Write it completely. Do not stub it.

### 6B — Create `imports/openwebui/` directory structure

```
imports/
└── openwebui/
    ├── mcp-servers.json
    ├── tools/
    │   ├── portal_documents.json
    │   ├── portal_music.json
    │   ├── portal_tts.json
    │   ├── portal_sandbox.json
    │   └── portal_comfyui.json   (optional — if ComfyUI running)
    └── workspaces/
        ├── workspace_auto.json
        ├── workspace_auto_coding.json
        ├── workspace_auto_security.json
        ├── workspace_auto_creative.json
        ├── workspace_auto_reasoning.json
        ├── workspace_auto_documents.json
        ├── workspace_auto_video.json
        ├── workspace_auto_music.json
        ├── workspace_auto_research.json
        └── workspaces_all.json
```

**`imports/openwebui/mcp-servers.json`:**
```json
{
  "version": "1.1",
  "description": "Portal 5.0 MCP Tool Server configurations",
  "tool_servers": [
    { "name": "Portal Documents", "url": "http://host.docker.internal:8913/mcp", "api_key": "" },
    { "name": "Portal Music",     "url": "http://host.docker.internal:8912/mcp", "api_key": "" },
    { "name": "Portal TTS",       "url": "http://host.docker.internal:8916/mcp", "api_key": "" },
    { "name": "Portal Code",      "url": "http://host.docker.internal:8914/mcp", "api_key": "" }
  ]
}
```

Each workspace JSON follows this format:
```json
{
  "id": "auto-coding",
  "name": "💻 Portal Code Expert",
  "meta": {
    "description": "Code generation, debugging, architecture"
  },
  "params": {
    "system": "You are an expert programmer. Generate clean, well-documented code. Always prefer idiomatic solutions.",
    "model": "auto-coding"
  }
}
```

Generate all 9 workspace files. Pull system prompts from `WORKSPACES` dict in
`portal_pipeline/router_pipe.py` — do not invent new ones.

**Verify:**
```bash
python3 -c "
import json
from pathlib import Path
tools = list(Path('imports/openwebui/tools').glob('*.json'))
workspaces = list(Path('imports/openwebui/workspaces').glob('workspace_*.json'))
print(f'Tool files: {len(tools)}')
print(f'Workspace files: {len(workspaces)}')
for f in tools + workspaces:
    json.loads(f.read_text())  # validates JSON
print('All import files: valid JSON')
"
```

---

## Phase 7 — Update launch.sh

The current `launch.sh` is good but missing two things:

**1. The `clean` command uses a hardcoded volume name** that may not match the actual
Docker Compose project name. Fix to derive from compose:

```bash
  clean)
    cd "$PORTAL_ROOT/deploy/portal-5"
    docker compose down
    # Remove named volumes (preserves ollama-models by default)
    docker compose down -v --remove-orphans 2>/dev/null || true
    echo "[portal-5] Clean complete (Open WebUI data wiped, Ollama models preserved)."
    echo "Run ./launch.sh up for fresh start."
    ;;

  clean-all)
    cd "$PORTAL_ROOT/deploy/portal-5"
    docker compose down -v --remove-orphans 2>/dev/null || true
    docker volume rm portal-5_ollama-models 2>/dev/null || true
    echo "[portal-5] Full clean complete (all volumes removed including Ollama models)."
    echo "WARNING: Models will re-download on next up (several GB)."
    ;;
```

**2. Add `status` command:**
```bash
  status)
    cd "$PORTAL_ROOT/deploy/portal-5"
    docker compose ps
    echo ""
    echo "Pipeline health:"
    curl -s http://localhost:9099/health 2>/dev/null | python3 -m json.tool || echo "  Pipeline not reachable"
    echo ""
    echo "Open WebUI: http://localhost:8080"
    ;;
```

**Update help:**
```bash
  *)
    echo "Usage: ./launch.sh [up|down|clean|clean-all|seed|logs|status]"
    echo ""
    echo "  up         Start all services (first run pulls model)"
    echo "  down       Stop all services (data preserved)"
    echo "  clean      Stop + wipe Open WebUI data (Ollama models preserved)"
    echo "  clean-all  Stop + wipe everything including Ollama models"
    echo "  seed       Re-run Open WebUI seeding (workspaces + tool servers)"
    echo "  logs [svc] Tail logs (default: portal-pipeline)"
    echo "  status     Show service status and health"
    ;;
```

---

## Phase 8 — Sync WORKSPACES Between router_pipe.py and workspace_routing in backends.yaml

**Current mismatch:** `router_pipe.py` defines these workspace IDs:
```
auto, auto-coding, auto-document, auto-security, auto-images, auto-creative,
auto-documents, auto-video, auto-music, auto-research
```

`backends.yaml` `workspace_routing` has:
```
auto, auto-coding, auto-document, auto-security, auto-images, auto-creative,
auto-documents, auto-video, auto-music, auto-research
```

These need to be identical. There are also two near-duplicates: `auto-document` and
`auto-documents`. Pick one and be consistent everywhere. **Standardize on the set
in the plan: `auto-documents` (plural) only.** Remove `auto-document` and `auto-images`
from `WORKSPACES` in `router_pipe.py` (or keep them — just make them match `backends.yaml`).

After editing, run:
```bash
python3 -c "
import yaml, json
from pathlib import Path

# Get workspace IDs from router
import sys; sys.path.insert(0, '.')
from portal_pipeline.router_pipe import WORKSPACES
pipe_ids = set(WORKSPACES.keys())

# Get workspace IDs from backends.yaml
cfg = yaml.safe_load(Path('config/backends.yaml').read_text())
yaml_ids = set(cfg.get('workspace_routing', {}).keys())

print(f'Pipeline workspaces: {sorted(pipe_ids)}')
print(f'YAML routing keys:   {sorted(yaml_ids)}')
missing_from_yaml = pipe_ids - yaml_ids
missing_from_pipe = yaml_ids - pipe_ids
if missing_from_yaml:
    print(f'WARNING: In pipeline but not in YAML: {missing_from_yaml}')
if missing_from_pipe:
    print(f'WARNING: In YAML but not in pipeline: {missing_from_pipe}')
if not missing_from_yaml and not missing_from_pipe:
    print('Workspace IDs: CONSISTENT')
"
```

---

## Phase 9 — Full Test

```bash
# ── Unit tests ─────────────────────────────────────────────────────────────
pytest tests/ -v
# All must pass

# ── Compile check: every Python file ───────────────────────────────────────
find . -name "*.py" -not -path "./.git/*" -not -path "./.venv/*" | while read f; do
    python3 -m py_compile "$f" && echo "OK: $f" || echo "FAIL: $f"
done

# ── Pipeline smoke test ────────────────────────────────────────────────────
python -m portal_pipeline &
PIPE_PID=$!
sleep 3

curl -s http://localhost:9099/health | python3 -m json.tool
curl -s -H "Authorization: Bearer portal-pipeline" http://localhost:9099/v1/models \
    | python3 -c "
import json, sys
d = json.load(sys.stdin)
ids = [m['id'] for m in d['data']]
print(f'Models: {ids}')
assert len(ids) >= 9
"

kill $PIPE_PID

# ── Compose validates ───────────────────────────────────────────────────────
docker compose -f deploy/portal-5/docker-compose.yml config --quiet && echo "Compose: valid"

# ── Import files complete ───────────────────────────────────────────────────
python3 -c "
import json
from pathlib import Path
tools = list(Path('imports/openwebui/tools').glob('*.json'))
ws = list(Path('imports/openwebui/workspaces').glob('workspace_*.json'))
assert len(tools) >= 4, f'Expected 4+ tools, got {len(tools)}'
assert len(ws) == 9, f'Expected 9 workspaces, got {len(ws)}'
assert Path('scripts/openwebui_init.py').exists(), 'Missing openwebui_init.py'
print(f'Tools: {len(tools)}, Workspaces: {len(ws)}, Init script: present')
print('All import artifacts: OK')
"

# ── Endpoint URL fix confirmed ──────────────────────────────────────────────
python3 -c "
from portal_pipeline.cluster_backends import Backend
b = Backend(id='t', type='ollama', url='http://localhost:11434', group='g', models=[])
assert '/v1/chat/completions' in b.chat_url, f'Still wrong: {b.chat_url}'
print(f'Ollama chat URL: {b.chat_url}')
print('Endpoint fix: confirmed')
"
```

---

## Phase 10 — End-to-End Smoke Test (If Docker Available)

```bash
# Full stack up
./launch.sh up

# Wait for model pull (can take 3-5 min on first run)
echo "Waiting for stack to be ready..."
sleep 30

# Check all services
./launch.sh status

# Test pipeline directly
curl -s -H "Authorization: Bearer portal-pipeline" \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello"}],"stream":false}' \
  http://localhost:9099/v1/chat/completions | python3 -m json.tool | head -20

# Verify Open WebUI is seeded
curl -s http://localhost:8080/health
echo ""
echo "Login at: http://localhost:8080"
echo "Email:    admin@portal.local"
echo "Password: portal-admin-change-me"
echo "(change these in .env before any real use)"
```

---

## Phase 11 — Git

```bash
git add .
git commit -m "fix: close all launch gaps — working stack on first up

Fixes:
- CRITICAL: Ollama API endpoint was /api/chat (wrong format)
  Now uses /v1/chat/completions (OpenAI-compatible) for all backend types
- CRITICAL: Ollama not in docker-compose — added ollama + ollama-init services
  ollama-init pulls DEFAULT_MODEL on first run (default: dolphin-llama3:8b)
- CRITICAL: scripts/openwebui_init.py missing — implemented fully
  Creates admin account, registers MCP tool servers, creates workspace presets
- CRITICAL: imports/ directory missing — added all tool JSONs + workspace presets
- MAJOR: portal_mcp/ missing — added document/music/tts/sandbox MCP servers
- BUG: Dockerfile.pipeline pip install syntax — quoted version specs
- BUG: Workspace ID mismatch between router_pipe.py and backends.yaml — synced
- IMPROVEMENT: Added ollama-models named volume (models survive docker compose down)
- IMPROVEMENT: Added status, clean-all commands to launch.sh

First-run flow after this fix:
  ./launch.sh up
  # Ollama starts, model pulls (~2-5 min)
  # Pipeline starts, connects to Ollama
  # Open WebUI starts, depends on pipeline health
  # openwebui-init creates admin, registers tools, creates workspaces
  # Login at http://localhost:8080 with admin@portal.local"

git push origin fix/launch-gaps
```

Then open a PR from `fix/launch-gaps` → `main`.

---

## Gap Summary

| # | Gap | Fix Location | Status After Task |
|---|---|---|---|
| 1 | Ollama `/api/chat` wrong endpoint | `cluster_backends.py` | Fixed → `/v1/chat/completions` |
| 2 | Ollama not in compose | `docker-compose.yml` | Fixed → service + health check |
| 3 | No model pull | `docker-compose.yml` | Fixed → `ollama-init` service |
| 4 | `portal_mcp/` missing | New directory | Fixed → 4 MCP servers |
| 5 | `scripts/openwebui_init.py` missing | New file | Fixed → full implementation |
| 6 | `imports/` missing | New directory | Fixed → tools + workspaces |
| 7 | Dockerfile.pipeline syntax | `Dockerfile.pipeline` | Fixed → quoted versions |
| 8 | Workspace ID mismatch | `router_pipe.py` + `backends.yaml` | Fixed → synced |
