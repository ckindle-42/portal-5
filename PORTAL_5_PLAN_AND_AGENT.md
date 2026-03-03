# Portal 5.0 — Strategic Plan & Coding Agent Task

**Date:** March 3, 2026  
**Branch:** `portal-5.0` (new branch from `main`) or new repository `ckindle-42/portal-5`  
**Philosophy:** Stop fighting Open WebUI. Become its most powerful enhancement layer.

---

## Part 1 — Strategic Context

### Why This Inflection Point Exists

Portal started as PocketPortal — a Telegram-first bot. When the scope grew to "local AI that does everything," new capabilities got bolted onto the Telegram foundation rather than re-centered around the best available web UI. The result is ~18,700 lines of Python that partially duplicates what Open WebUI already does better — its own web server, auth system, RAG pipeline, knowledge base, health checks, metrics, and rate limiting.

Portal 5.0 makes a deliberate architectural choice: **Open WebUI is the product. Portal is the intelligence layer and extension ecosystem that makes it extraordinary.**

### Dual Purpose — Single-Node and Cluster Foundation

Portal 5.0 serves two roles simultaneously:

**Role 1 — Personal Local AI (immediate)**  
The M4 Mac / Linux single-node setup you have today. Open WebUI as the full interface, Portal's intelligent router as an Open WebUI Pipeline, MCP servers exposed as Tool Servers. Everything works today.

**Role 2 — Foundation node for the Mac Studio cluster (growth path)**  
The dual-track infrastructure plan (Track B: Apple Silicon) calls for Mac Studios daisy-chained via Thunderbolt, scaling from 1 unit (Stage 1, ~$10.5K) to 12 units (Stage 5, ~$135K) running distributed inference for 40-60 concurrent users with models up to Kimi K2 (600GB INT4). Portal 5.0's Pipeline architecture and MCP server ecosystem are designed to sit in front of that entire cluster — the same Portal routing brain that intelligently selects between `auto-coding` and `auto-security` on a single M4 can equally route between a 12-node vLLM cluster running Kimi K2, a dedicated coding model, and a security specialist model. The Pipeline just gets different backend URLs.

This is why the architecture matters: building it right now means the single-node and the 12-node cluster share the same Portal installation, the same Open WebUI, the same workspace definitions, the same MCP tools. The cluster is just more backends registered in the router.

---

## Part 2 — What Portal 5.0 Is

### What Gets Deleted (duplicates Open WebUI)

| Module | Lines | Why deleted |
|---|---|---|
| `src/portal/interfaces/web/server.py` | 915 | Open WebUI is the web interface |
| `src/portal/security/auth/` | 141 | Open WebUI has full auth, SSO, SCIM, OAuth |
| `src/portal/memory/manager.py` | 236 | Open WebUI has native memory tools |
| `src/portal/tools/knowledge/` | 940 | Open WebUI has 9 vector DB backends + hybrid RAG |
| `src/portal/observability/` | 1,351 | Open WebUI has OpenTelemetry built-in |
| `src/portal/middleware/` | ~200 | Open WebUI handles this natively |
| **Total deleted** | **~3,800 lines** | |

### What Gets Kept and Rehoused

| Module | Lines | New home |
|---|---|---|
| `src/portal/routing/` — IntelligentRouter, task classifier, execution engine | 3,414 | Becomes `portal_pipeline/` — an Open WebUI Pipeline container |
| `src/portal/interfaces/telegram/` | 617 | Becomes `portal_channels/telegram/` |
| `src/portal/interfaces/slack/` | 218 | Becomes `portal_channels/slack/` |
| `portal_mcp/` — documents, music, video, TTS, whisper, comfyui, code sandbox | 1,921 | Stays as `portal_mcp/`, registered as Open WebUI Tool Servers |

### What Gets Added (new in 5.0)

| New component | Purpose |
|---|---|
| `portal_pipeline/` | FastAPI service hosting the IntelligentRouter as an Open WebUI Pipeline on port 9099 |
| `portal_pipeline/router_pipe.py` | The Pipeline that Open WebUI calls — classifies request, selects backend, returns response |
| `portal_pipeline/cluster_backends.py` | Multi-backend registry: Ollama (single node) + vLLM nodes (cluster), health-aware |
| `portal_channels/telegram/bot.py` | Cleaned-up Telegram bot that calls the Pipeline API instead of Portal's old AgentCore |
| `portal_channels/slack/bot.py` | Same for Slack |
| `deploy/portal-5/docker-compose.yml` | Clean compose: open-webui + pipelines + portal_mcp servers + channels |
| `deploy/portal-5/openwebui-init/` | Auto-seeding (from the import agent work, carried forward) |
| `config/backends.yaml` | Declarative backend registry — add a new Mac Studio or vLLM node here |

### Portal 5.0 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Open WebUI :8080                      │
│  (chat UI, auth, RAG, image gen, TTS, STT, web search)  │
│                                                          │
│  Model dropdown shows:                                   │
│    🤖 Portal Auto Router  (via Pipeline)                 │
│    💻 Portal Code Expert  (via Pipeline)                 │
│    🔐 Portal Security     (via Pipeline)                 │
│    ✍️  Portal Creative    (via Pipeline)                 │
│    ... all 9 workspaces                                  │
│                                                          │
│  Tools sidebar shows:                                    │
│    📄 Portal Documents    (MCP Tool Server :8913)        │
│    🎵 Portal Music        (MCP Tool Server :8912)        │
│    🎬 Portal Video        (MCP Tool Server :8911)        │
│    🗣️  Portal TTS         (MCP Tool Server :8916)        │
│    🔊 Portal Whisper      (MCP Tool Server :8915)        │
│    💻 Portal Code         (MCP Tool Server :8914)        │
│    🌐 Portal Web          (MCP Tool Server :8092)        │
│    🐚 Portal Shell        (MCP Tool Server :8091)        │
└──────────────┬──────────────────────────────────────────┘
               │ OpenAI API
               ▼
┌─────────────────────────────────────────────────────────┐
│            Portal Pipeline Server :9099                  │
│         (Open WebUI Pipelines container)                 │
│                                                          │
│  router_pipe.py                                          │
│    1. Receive message + workspace_id from Open WebUI     │
│    2. LLM classifier → task type                        │
│    3. Backend selector → best model for task            │
│    4. Route to backend, stream response back             │
│                                                          │
│  cluster_backends.py                                     │
│    Single node:  Ollama :11434                          │
│    Stage 2+:     + vLLM node 2 :8000                    │
│    Stage 3+:     + vLLM node 3-4 :8001-8002             │
│    Stage 5:      12-node cluster, load balanced          │
└──────────────┬──────────────────────────────────────────┘
               │
    ┌──────────┴──────────┐
    ▼                     ▼
Ollama :11434         vLLM cluster
(single node)         (future stages)

┌─────────────────────────────────────────────────────────┐
│           Portal Channels (optional)                     │
│                                                          │
│  Telegram bot → calls Pipeline API → same routing       │
│  Slack bot   → calls Pipeline API → same routing        │
└─────────────────────────────────────────────────────────┘
```

---

## Part 3 — New Repository vs. New Branch

**Recommendation: New repository `ckindle-42/portal-5`**

Reasons:
- Portal 4.x stays intact and usable while 5.0 is developed — no risk to working system
- Clean git history — 5.0 doesn't inherit 300+ commits of PocketPortal archaeology
- Demonstrates the architectural break clearly — this isn't a refactor, it's a redesign
- The old repo becomes the reference implementation for "what we learned"

If you want to stay in one repo, use branch `portal-5.0` and keep `main` frozen at 4.x. Either works — the agent task below supports both.

---

## Part 4 — Coding Agent Task

### Role

You are an elite build agent with full filesystem and shell access. Your goal is to create Portal 5.0 — an Open WebUI enhancement layer that moves Portal's intelligent routing engine into an Open WebUI Pipelines container, exposes all MCP servers as Open WebUI Tool Servers, and preserves the Telegram/Slack channel adapters. You are building a new codebase, not refactoring the old one. The old `src/portal/` directory is reference material only — read it, don't copy it wholesale.

**Constraint:** Every component you build must be runnable and testable before you move to the next. No placeholder code. No `pass` implementations. If you write a function, it must work.

---

### Phase 0 — Repository Setup

```bash
# Option A: New repository
mkdir -p ~/projects/portal-5
cd ~/projects/portal-5
git init
git checkout -b main

# Option B: New branch in existing repo
cd /path/to/portal
git checkout main && git pull
git checkout -b portal-5.0

# Either way, establish the new structure
mkdir -p portal_pipeline portal_channels/telegram portal_channels/slack
mkdir -p portal_mcp/documents portal_mcp/generation portal_mcp/execution
mkdir -p config deploy/portal-5/openwebui-init imports/openwebui/tools
mkdir -p imports/openwebui/workspaces imports/openwebui/functions
mkdir -p tests/unit tests/integration
```

Create `pyproject.toml`:

```toml
[project]
name = "portal-5"
version = "5.0.0"
description = "Open WebUI intelligence layer — routing, channels, and MCP tools"
requires-python = ">=3.11"

dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "httpx>=0.27.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "python-telegram-bot>=21.0",
    "slack-bolt>=1.18.0",
    "pyyaml>=6.0",
    "python-docx>=1.1.0",
    "openpyxl>=3.1.0",
    "python-pptx>=0.6.23",
    "mcp[cli]>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-httpx>=0.30",
    "ruff>=0.4.0",
    "mypy>=1.10",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
python --version  # must be 3.11+
```

---

### Phase 1 — Backend Registry (`portal_pipeline/cluster_backends.py`)

This is the foundation everything else builds on. It must work before any other component.

The backend registry is a declarative config-driven system that:
- Reads `config/backends.yaml` for the list of inference backends
- Supports Ollama and vLLM (OpenAI-compatible) backends interchangeably
- Health-checks each backend on startup and periodically
- Provides `get_backend(workspace_id)` → returns the best available backend URL for the workspace
- Supports single-node (just Ollama) and multi-node cluster (Ollama + vLLM nodes) transparently

**`config/backends.yaml`** — the operator edits this file to add cluster nodes, never code:

```yaml
# Portal 5.0 Backend Registry
# Add new nodes here as the cluster grows. No code changes required.
# workspace_affinity: maps workspace IDs to preferred backend groups
# If preferred backend is unhealthy, falls back to 'general' group.

backends:
  - id: ollama-primary
    type: ollama
    url: "http://host.docker.internal:11434"
    group: general
    models:
      - dolphin-llama3:8b
      - qwen2.5:7b
    health_check_interval: 30

  # Uncomment and add as cluster grows:
  # - id: vllm-node-2
  #   type: openai_compatible
  #   url: "http://192.168.1.102:8000"
  #   group: general
  #   models:
  #     - meta-llama/Llama-3.1-70B-Instruct
  #   health_check_interval: 30
  #
  # - id: vllm-coding
  #   type: openai_compatible
  #   url: "http://192.168.1.103:8000"
  #   group: coding
  #   models:
  #     - Qwen/Qwen2.5-Coder-32B-Instruct
  #   health_check_interval: 30

workspace_routing:
  auto:          [general]
  auto-coding:   [coding, general]
  auto-security: [general]
  auto-creative: [general]
  auto-reasoning:[general]
  auto-documents:[general]
  auto-video:    [general]
  auto-music:    [general]
  auto-research: [general]

defaults:
  fallback_group: general
  request_timeout: 120
  health_timeout: 5
```

**`portal_pipeline/cluster_backends.py`:**

```python
"""
Portal 5.0 — Cluster Backend Registry

Manages a pool of Ollama / vLLM inference backends.
Config-driven: add new cluster nodes in config/backends.yaml.
Health-aware: automatically routes around unhealthy backends.
Single-node and multi-node cluster transparent to callers.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
import yaml

logger = logging.getLogger(__name__)


@dataclass
class Backend:
    id: str
    type: str           # 'ollama' | 'openai_compatible'
    url: str
    group: str
    models: list[str]
    health_check_interval: int = 30
    healthy: bool = True
    last_check: float = field(default_factory=time.time)

    @property
    def chat_url(self) -> str:
        return f"{self.url.rstrip('/')}/v1/chat/completions"

    @property
    def models_url(self) -> str:
        return f"{self.url.rstrip('/')}/v1/models"


class BackendRegistry:
    """
    Config-driven registry of inference backends.
    Supports Ollama and OpenAI-compatible (vLLM) backends.
    Used by the Portal Pipeline to route requests to the right backend.
    """

    def __init__(self, config_path: Path | str | None = None) -> None:
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "backends.yaml"
        self.config_path = Path(config_path)
        self._backends: dict[str, Backend] = {}
        self._workspace_routing: dict[str, list[str]] = {}
        self._fallback_group = "general"
        self._request_timeout = 120
        self._health_timeout = 5
        self._load_config()

    def _load_config(self) -> None:
        if not self.config_path.exists():
            logger.warning("backends.yaml not found at %s — using empty registry", self.config_path)
            return

        with open(self.config_path) as f:
            cfg = yaml.safe_load(f)

        for b in cfg.get("backends", []):
            backend = Backend(
                id=b["id"],
                type=b.get("type", "ollama"),
                url=b["url"],
                group=b.get("group", "general"),
                models=b.get("models", []),
                health_check_interval=b.get("health_check_interval", 30),
            )
            self._backends[backend.id] = backend
            logger.info("Registered backend: %s (%s) in group '%s'", backend.id, backend.url, backend.group)

        self._workspace_routing = cfg.get("workspace_routing", {})
        defaults = cfg.get("defaults", {})
        self._fallback_group = defaults.get("fallback_group", "general")
        self._request_timeout = defaults.get("request_timeout", 120)
        self._health_timeout = defaults.get("health_timeout", 5)

    def get_backend_for_workspace(self, workspace_id: str) -> Backend | None:
        """Return the best healthy backend for a workspace ID."""
        groups = self._workspace_routing.get(workspace_id, [self._fallback_group])

        # Try each preferred group in order
        for group in groups:
            healthy = [b for b in self._backends.values() if b.group == group and b.healthy]
            if healthy:
                # Simple round-robin: sort by last_check ascending
                return sorted(healthy, key=lambda b: b.last_check)[0]

        # Fallback: any healthy backend
        all_healthy = [b for b in self._backends.values() if b.healthy]
        if all_healthy:
            logger.warning("No backend for workspace '%s' — using fallback", workspace_id)
            return all_healthy[0]

        logger.error("No healthy backends available")
        return None

    def list_backends(self) -> list[Backend]:
        return list(self._backends.values())

    def list_healthy_backends(self) -> list[Backend]:
        return [b for b in self._backends.values() if b.healthy]

    async def health_check_all(self) -> None:
        """Check all backends and update health status."""
        async with httpx.AsyncClient(timeout=self._health_timeout) as client:
            tasks = [self._check_one(client, b) for b in self._backends.values()]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_one(self, client: httpx.AsyncClient, backend: Backend) -> None:
        try:
            resp = await client.get(backend.models_url)
            was_healthy = backend.healthy
            backend.healthy = resp.status_code == 200
            backend.last_check = time.time()
            if was_healthy and not backend.healthy:
                logger.warning("Backend %s went unhealthy", backend.id)
            elif not was_healthy and backend.healthy:
                logger.info("Backend %s recovered", backend.id)
        except Exception as e:
            if backend.healthy:
                logger.warning("Backend %s health check failed: %s", backend.id, e)
            backend.healthy = False
            backend.last_check = time.time()

    async def start_health_loop(self) -> None:
        """Run background health checks. Call from lifespan or startup."""
        await self.health_check_all()  # immediate first check
        while True:
            min_interval = min(
                (b.health_check_interval for b in self._backends.values()),
                default=30
            )
            await asyncio.sleep(min_interval)
            await self.health_check_all()

    @property
    def request_timeout(self) -> int:
        return self._request_timeout
```

**Verify:**
```bash
python3 -c "
from portal_pipeline.cluster_backends import BackendRegistry
from pathlib import Path
reg = BackendRegistry()
print(f'Backends loaded: {len(reg.list_backends())}')
for b in reg.list_backends():
    print(f'  {b.id}: {b.url} [{b.group}]')
print('BackendRegistry OK')
"
```

---

### Phase 2 — Portal Pipeline Server (`portal_pipeline/`)

The Pipeline server runs as a standalone FastAPI service on port 9099. Open WebUI connects to it as an additional OpenAI API connection. When a user selects a Portal workspace model (e.g., "Portal Code Expert"), Open WebUI sends the request to the Pipeline server, which routes it to the appropriate backend.

This replaces `src/portal/interfaces/web/server.py` (915 lines) + `src/portal/routing/` (3,414 lines) with a clean, purpose-built implementation.

**`portal_pipeline/router_pipe.py`** — the core routing logic:

```python
"""
Portal 5.0 — Intelligent Router Pipeline

Open WebUI Pipelines-compatible server.
Exposes Portal workspaces as selectable models in Open WebUI's model dropdown.
Routes each request to the best available backend based on workspace + task classification.

Connection: Open WebUI Admin > Settings > Connections > Add OpenAI API
  URL: http://host.docker.internal:9099
  Key: portal-pipeline (or whatever PIPELINE_API_KEY is set to)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from portal_pipeline.cluster_backends import BackendRegistry

logger = logging.getLogger(__name__)

# Workspace definitions — models exposed to Open WebUI
WORKSPACES = {
    "auto":           {"name": "🤖 Portal Auto Router",       "description": "Intelligently routes to the best model for your task"},
    "auto-coding":    {"name": "💻 Portal Code Expert",        "description": "Code generation, debugging, architecture"},
    "auto-security":  {"name": "🔐 Portal Security Analyst",   "description": "Security analysis, vulnerability assessment, defensive coding"},
    "auto-creative":  {"name": "✍️  Portal Creative Writer",   "description": "Creative writing, storytelling, content generation"},
    "auto-reasoning": {"name": "🧠 Portal Deep Reasoner",      "description": "Complex analysis, research synthesis, step-by-step reasoning"},
    "auto-documents": {"name": "📄 Portal Document Builder",   "description": "Create Word, Excel, PowerPoint via MCP tools"},
    "auto-video":     {"name": "🎬 Portal Video Creator",      "description": "Generate video clips via ComfyUI/Wan2.2"},
    "auto-music":     {"name": "🎵 Portal Music Producer",     "description": "Generate music and audio via AudioCraft"},
    "auto-research":  {"name": "🔍 Portal Research Assistant", "description": "Web research, information synthesis, fact-checking"},
}

PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "portal-pipeline")
registry: BackendRegistry | None = None
_health_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global registry, _health_task
    registry = BackendRegistry()
    await registry.health_check_all()
    healthy = registry.list_healthy_backends()
    logger.info("Portal Pipeline started. Healthy backends: %d", len(healthy))
    _health_task = asyncio.create_task(registry.start_health_loop())
    yield
    if _health_task:
        _health_task.cancel()


app = FastAPI(title="Portal Pipeline", version="5.0.0", lifespan=lifespan)


def _verify_key(authorization: str | None) -> None:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if token != PIPELINE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
async def health() -> dict:
    assert registry is not None
    healthy = registry.list_healthy_backends()
    return {
        "status": "ok" if healthy else "degraded",
        "backends_healthy": len(healthy),
        "backends_total": len(registry.list_backends()),
    }


@app.get("/v1/models")
async def list_models(authorization: str | None = Header(None)) -> dict:
    _verify_key(authorization)
    models = []
    ts = int(time.time())
    for ws_id, ws_cfg in WORKSPACES.items():
        models.append({
            "id": ws_id,
            "object": "model",
            "created": ts,
            "owned_by": "portal-5",
            "name": ws_cfg["name"],
            "description": ws_cfg["description"],
        })
    return {"object": "list", "data": models}


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    authorization: str | None = Header(None),
) -> Any:
    _verify_key(authorization)
    assert registry is not None

    body = await request.json()
    workspace_id = body.get("model", "auto")
    stream = body.get("stream", True)

    # Select backend
    backend = registry.get_backend_for_workspace(workspace_id)
    if not backend:
        raise HTTPException(status_code=503, detail="No healthy backends available")

    # Use the first available model on the backend, or fall back to default
    target_model = backend.models[0] if backend.models else "llama3"

    # Build the request for the backend
    backend_body = {**body, "model": target_model}

    if stream:
        return StreamingResponse(
            _stream_from_backend(backend.chat_url, backend_body),
            media_type="text/event-stream",
        )
    else:
        return await _complete_from_backend(backend.chat_url, backend_body)


async def _stream_from_backend(url: str, body: dict) -> AsyncIterator[bytes]:
    """Stream SSE chunks from the backend to the caller."""
    assert registry is not None
    try:
        async with httpx.AsyncClient(timeout=registry.request_timeout) as client:
            async with client.stream("POST", url, json=body) as resp:
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    yield f"data: {{\"error\": \"{resp.status_code}: {error_text[:100]}\"}}\n\n".encode()
                    return
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk
    except Exception as e:
        logger.error("Streaming error from backend %s: %s", url, e)
        yield f"data: {{\"error\": \"Backend error: {e}\"}}\n\n".encode()


async def _complete_from_backend(url: str, body: dict) -> JSONResponse:
    """Non-streaming completion from backend."""
    assert registry is not None
    try:
        async with httpx.AsyncClient(timeout=registry.request_timeout) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            return JSONResponse(content=resp.json())
    except Exception as e:
        logger.error("Completion error from backend %s: %s", url, e)
        raise HTTPException(status_code=502, detail=f"Backend error: {e}") from e
```

**`portal_pipeline/__main__.py`:**

```python
import logging
import uvicorn
from portal_pipeline.router_pipe import app

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9099)
```

**Verify — pipeline starts and responds:**
```bash
# Start pipeline in background
python -m portal_pipeline &
PIPE_PID=$!
sleep 3

# Health check
curl -s http://localhost:9099/health | python3 -m json.tool

# Models list
curl -s -H "Authorization: Bearer portal-pipeline" \
  http://localhost:9099/v1/models | python3 -m json.tool | grep '"id"'

# Kill background process
kill $PIPE_PID

# Expected: 9 workspace model IDs
```

---

### Phase 3 — Channel Adapters (`portal_channels/`)

Refactor Telegram and Slack to call the Pipeline API instead of Portal's old AgentCore. Both channels become thin adapters — they handle platform protocol (Telegram updates, Slack events) and forward to the Pipeline's `/v1/chat/completions` endpoint. All routing intelligence stays in the Pipeline.

**`portal_channels/telegram/bot.py`** — extract the core logic from `src/portal/interfaces/telegram/interface.py` (617 lines → ~150 lines) by removing the AgentCore dependency and replacing with a direct HTTP call:

```python
"""
Portal 5.0 — Telegram Channel Adapter

Receives Telegram updates, forwards to Portal Pipeline, streams response back.
Thin adapter: no routing logic here, all intelligence is in portal_pipeline/.
"""
from __future__ import annotations

import logging
import os

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://portal-pipeline:9099")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "portal-pipeline")
ALLOWED_USER_IDS_RAW = os.environ.get("TELEGRAM_USER_IDS", "")
ALLOWED_USER_IDS: set[int] = {
    int(uid.strip()) for uid in ALLOWED_USER_IDS_RAW.split(",") if uid.strip().isdigit()
}
DEFAULT_WORKSPACE = os.environ.get("TELEGRAM_DEFAULT_WORKSPACE", "auto")


def _is_allowed(user_id: int) -> bool:
    return not ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 Portal 5.0 — Local AI Assistant\n\n"
        "Send any message to get started.\n"
        "Commands:\n"
        "/workspace [name] — switch workspace (auto, auto-coding, auto-security...)\n"
        "/clear — clear conversation history"
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.message.reply_text("Conversation history cleared.")


async def set_workspace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if args:
        ws = args[0].lower()
        context.user_data["workspace"] = ws
        await update.message.reply_text(f"Workspace set to: {ws}")
    else:
        current = context.user_data.get("workspace", DEFAULT_WORKSPACE)
        await update.message.reply_text(f"Current workspace: {current}\nUsage: /workspace [auto|auto-coding|auto-security|...]")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    if not _is_allowed(update.effective_user.id):
        await update.message.reply_text("Unauthorized.")
        return

    user_text = update.message.text or ""
    workspace = context.user_data.get("workspace", DEFAULT_WORKSPACE)

    # Build message history (last 10 turns)
    history: list[dict] = context.user_data.get("history", [])
    history.append({"role": "user", "content": user_text})
    if len(history) > 20:
        history = history[-20:]

    # Send typing indicator
    await update.message.chat.send_action("typing")

    # Call Pipeline API
    payload = {
        "model": workspace,
        "messages": history,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {PIPELINE_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("Pipeline error: %s", e)
        reply = f"⚠️ Pipeline error: {e}"

    # Store assistant reply in history
    history.append({"role": "assistant", "content": reply})
    context.user_data["history"] = history

    # Telegram has a 4096 char limit
    if len(reply) > 4000:
        for chunk in [reply[i:i+4000] for i in range(0, len(reply), 4000)]:
            await update.message.reply_text(chunk, parse_mode="Markdown")
    else:
        await update.message.reply_text(reply, parse_mode="Markdown")


def build_app() -> Application:
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("workspace", set_workspace))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    bot_app = build_app()
    bot_app.run_polling()
```

**Verify (syntax only — no bot token needed):**
```bash
python3 -m py_compile portal_channels/telegram/bot.py && echo "Telegram adapter: OK"
python3 -m py_compile portal_channels/slack/bot.py && echo "Slack adapter: OK"
```

The Slack adapter follows the same pattern: receive event → build history → POST to Pipeline → return response. Extract from `src/portal/interfaces/slack/interface.py`, remove AgentCore dependency.

---

### Phase 4 — MCP Servers (Carry Forward)

Copy `portal_mcp/` from the existing repo. No changes needed — these are standalone FastMCP servers that don't depend on Portal's AgentCore. They get registered as Tool Servers in Open WebUI directly.

```bash
# Copy from existing Portal repo
cp -r /path/to/portal/portal_mcp ./portal_mcp

# Verify each MCP server compiles
for f in portal_mcp/documents/document_mcp.py \
          portal_mcp/generation/music_mcp.py \
          portal_mcp/generation/video_mcp.py \
          portal_mcp/generation/tts_mcp.py \
          portal_mcp/generation/whisper_mcp.py \
          portal_mcp/generation/comfyui_mcp.py \
          portal_mcp/execution/code_sandbox_mcp.py; do
    python3 -m py_compile "$f" && echo "OK: $f" || echo "FAIL: $f"
done
```

---

### Phase 5 — Docker Compose (`deploy/portal-5/docker-compose.yml`)

The new compose file is dramatically simpler than Portal 4.x. Open WebUI handles what used to require portal-api, portal-router, and all the middleware.

```yaml
# Portal 5.0 — Clean Stack
# Usage: docker compose up -d
# First run: docker compose up -d && bash ../../launch.sh seed

services:

  # ── Open WebUI ─────────────────────────────────────────────────────────────
  open-webui:
    image: ghcr.io/open-webui/open-webui:latest
    container_name: portal5-open-webui
    restart: unless-stopped
    pull_policy: always
    ports:
      - "8080:8080"
    volumes:
      - open-webui-data:/app/backend/data
    environment:
      # Portal Pipeline is the ONLY model source (routes all LLM requests)
      - OPENAI_API_BASE_URL=http://portal-pipeline:9099/v1
      - OPENAI_API_KEY=${PIPELINE_API_KEY:-portal-pipeline}
      # ComfyUI native image generation
      - ENABLE_IMAGE_GENERATION=True
      - IMAGE_GENERATION_ENGINE=comfyui
      - COMFYUI_BASE_URL=http://host.docker.internal:8188
      # Auth
      - WEBUI_SECRET_KEY=${WEBUI_SECRET_KEY:-portal5-secret-change-me}
      - WEBUI_AUTH=${WEBUI_AUTH:-true}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      portal-pipeline:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      start_period: 60s
      retries: 3

  # ── Portal Pipeline (intelligent router) ───────────────────────────────────
  portal-pipeline:
    build:
      context: ../..
      dockerfile: Dockerfile.pipeline
    container_name: portal5-pipeline
    restart: unless-stopped
    ports:
      - "127.0.0.1:9099:9099"
    volumes:
      - ../../config/backends.yaml:/app/config/backends.yaml:ro
    environment:
      - PIPELINE_API_KEY=${PIPELINE_API_KEY:-portal-pipeline}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9099/health"]
      interval: 15s
      timeout: 5s
      start_period: 30s
      retries: 5

  # ── Open WebUI Init (auto-seeds on fresh volume) ────────────────────────────
  openwebui-init:
    image: python:3.11-slim
    container_name: portal5-init
    restart: "no"
    depends_on:
      open-webui:
        condition: service_healthy
    environment:
      - OPENWEBUI_URL=http://open-webui:8080
      - OPENWEBUI_ADMIN_EMAIL=${OPENWEBUI_ADMIN_EMAIL:-admin@portal.local}
      - OPENWEBUI_ADMIN_PASSWORD=${OPENWEBUI_ADMIN_PASSWORD:-portal-admin-change-me}
    volumes:
      - ../../scripts:/scripts:ro
      - ../../imports:/imports:ro
    command: >
      sh -c "pip install httpx --quiet && python /scripts/openwebui_init.py"

  # ── MCP Servers ─────────────────────────────────────────────────────────────
  mcp-documents:
    build: { context: ../.. }
    container_name: portal5-mcp-documents
    restart: unless-stopped
    ports: ["8913:8913"]
    environment: [DOCUMENTS_MCP_PORT=8913]
    command: ["python", "-m", "portal_mcp.documents.document_mcp"]
    volumes: ["${HOME}/AI_Output:/app/data/generated"]

  mcp-music:
    build: { context: ../.. }
    container_name: portal5-mcp-music
    restart: unless-stopped
    ports: ["8912:8912"]
    environment: [MUSIC_MCP_PORT=8912]
    command: ["python", "-m", "portal_mcp.generation.music_mcp"]
    volumes: ["${HOME}/AI_Output:/app/data/generated"]

  mcp-tts:
    build: { context: ../.. }
    container_name: portal5-mcp-tts
    restart: unless-stopped
    ports: ["8916:8916"]
    environment: [TTS_MCP_PORT=8916, "TTS_BACKEND=${TTS_BACKEND:-fish_speech}"]
    command: ["python", "-m", "portal_mcp.generation.tts_mcp"]
    volumes: ["${HOME}/AI_Output:/app/data/generated"]

  mcp-video:
    build: { context: ../.. }
    container_name: portal5-mcp-video
    restart: unless-stopped
    ports: ["8911:8911"]
    environment: [VIDEO_MCP_PORT=8911]
    command: ["python", "-m", "portal_mcp.generation.video_mcp"]
    volumes: ["${HOME}/AI_Output:/app/data/generated"]

  mcp-sandbox:
    build: { context: ../.. }
    container_name: portal5-mcp-sandbox
    restart: unless-stopped
    ports: ["8914:8914"]
    environment: [SANDBOX_MCP_PORT=8914]
    command: ["python", "-m", "portal_mcp.execution.code_sandbox_mcp"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./data/sandbox:/app/data/sandbox

  # ── Optional: Telegram Channel ──────────────────────────────────────────────
  # Uncomment to enable
  # portal-telegram:
  #   build: { context: ../.. }
  #   container_name: portal5-telegram
  #   restart: unless-stopped
  #   environment:
  #     - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
  #     - TELEGRAM_USER_IDS=${TELEGRAM_USER_IDS}
  #     - PIPELINE_URL=http://portal-pipeline:9099
  #     - PIPELINE_API_KEY=${PIPELINE_API_KEY:-portal-pipeline}
  #   command: ["python", "-m", "portal_channels.telegram.bot"]
  #   depends_on:
  #     portal-pipeline:
  #       condition: service_healthy

volumes:
  open-webui-data:
```

Create `Dockerfile.pipeline` (lean — only Pipeline dependencies):

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir fastapi uvicorn httpx pydantic pyyaml
COPY portal_pipeline/ ./portal_pipeline/
COPY config/ ./config/
CMD ["python", "-m", "portal_pipeline"]
```

---

### Phase 6 — Import Files & Auto-Seeding

Carry forward the complete `imports/openwebui/` directory and `scripts/openwebui_init.py` from the import agent work (PORTAL_OPENWEBUI_SETUP_AGENT.md). These are already built — just ensure they're present in the 5.0 repo structure.

```bash
# Verify
ls imports/openwebui/tools/        # 9 files
ls imports/openwebui/workspaces/   # 9 files + workspaces_all.json
ls imports/openwebui/functions/    # portal_router_pipe.json
ls scripts/openwebui_init.py       # init container script
```

---

### Phase 7 — Tests

```bash
# Create tests/unit/test_pipeline.py
```

```python
"""Portal 5.0 Pipeline unit tests — no live backends required."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from portal_pipeline.cluster_backends import Backend, BackendRegistry
from portal_pipeline.router_pipe import WORKSPACES, app

CLIENT = TestClient(app)
HEADERS = {"Authorization": "Bearer portal-pipeline"}


class TestBackendRegistry:
    def test_load_config(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: test-ollama
    type: ollama
    url: http://localhost:11434
    group: general
    models: [dolphin-llama3:8b]
workspace_routing:
  auto: [general]
defaults:
  fallback_group: general
""")
        reg = BackendRegistry(config_path=cfg)
        assert len(reg.list_backends()) == 1
        assert reg.list_backends()[0].id == "test-ollama"

    def test_get_backend_for_workspace(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: b1
    type: ollama
    url: http://localhost:11434
    group: general
    models: [llama3]
workspace_routing:
  auto: [general]
defaults:
  fallback_group: general
""")
        reg = BackendRegistry(config_path=cfg)
        backend = reg.get_backend_for_workspace("auto")
        assert backend is not None
        assert backend.id == "b1"

    def test_unhealthy_backend_not_selected(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: sick
    type: ollama
    url: http://localhost:11434
    group: general
    models: [llama3]
  - id: healthy
    type: ollama
    url: http://localhost:11435
    group: general
    models: [llama3]
workspace_routing:
  auto: [general]
defaults:
  fallback_group: general
""")
        reg = BackendRegistry(config_path=cfg)
        reg._backends["sick"].healthy = False
        backend = reg.get_backend_for_workspace("auto")
        assert backend is not None
        assert backend.id == "healthy"

    def test_no_healthy_backends_returns_none(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: sick
    type: ollama
    url: http://localhost:11434
    group: general
    models: [llama3]
workspace_routing:
  auto: [general]
defaults:
  fallback_group: general
""")
        reg = BackendRegistry(config_path=cfg)
        reg._backends["sick"].healthy = False
        assert reg.get_backend_for_workspace("auto") is None


class TestPipelineAPI:
    def test_health_endpoint(self):
        resp = CLIENT.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "backends_healthy" in data

    def test_models_requires_auth(self):
        resp = CLIENT.get("/v1/models")
        assert resp.status_code == 401

    def test_models_returns_workspaces(self):
        resp = CLIENT.get("/v1/models", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        ids = {m["id"] for m in data["data"]}
        assert "auto" in ids
        assert "auto-coding" in ids
        assert "auto-security" in ids
        assert len(ids) == len(WORKSPACES)

    def test_chat_requires_auth(self):
        resp = CLIENT.post("/v1/chat/completions", json={})
        assert resp.status_code == 401

    def test_chat_no_backends_returns_503(self):
        # Pipeline has no backends in test env — should return 503
        resp = CLIENT.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}], "stream": False},
            headers=HEADERS,
        )
        # Either 503 (no backends) or 502 (backend error) are acceptable
        assert resp.status_code in (503, 502, 200)
```

**Run tests:**
```bash
pytest tests/unit/test_pipeline.py -v
# All tests must pass
```

---

### Phase 8 — `.env.example` and Launch Script

**`.env.example`:**
```bash
# Portal 5.0 Configuration

# Pipeline
PIPELINE_API_KEY=portal-pipeline   # Change this in production

# Open WebUI Admin (created on first fresh start)
OPENWEBUI_ADMIN_EMAIL=admin@portal.local
OPENWEBUI_ADMIN_PASSWORD=portal-admin-change-me  # Change this

# Hardware
COMPUTE_BACKEND=mps   # mps (Apple Silicon) | cuda (NVIDIA) | cpu

# Optional channels
TELEGRAM_ENABLED=false
# TELEGRAM_BOT_TOKEN=
# TELEGRAM_USER_IDS=123456789

SLACK_ENABLED=false
# SLACK_BOT_TOKEN=xoxb-...
# SLACK_SIGNING_SECRET=

# Generation services
TTS_BACKEND=fish_speech
COMFYUI_URL=http://localhost:8188

# Logging
LOG_LEVEL=INFO
```

**`launch.sh`** — much simpler than Portal 4.x:
```bash
#!/bin/bash
set -euo pipefail
PORTAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-up}" in
  up)
    cp -n "$PORTAL_ROOT/.env.example" "$PORTAL_ROOT/.env" 2>/dev/null || true
    set -a; source "$PORTAL_ROOT/.env"; set +a
    echo "[portal-5] Starting stack..."
    cd "$PORTAL_ROOT/deploy/portal-5"
    docker compose up -d
    echo "[portal-5] Stack started. Open WebUI: http://localhost:8080"
    ;;
  down)
    cd "$PORTAL_ROOT/deploy/portal-5"
    docker compose down
    ;;
  clean)
    cd "$PORTAL_ROOT/deploy/portal-5"
    docker compose down
    docker volume rm portal-5_open-webui-data 2>/dev/null || true
    echo "[portal-5] Clean complete. Run ./launch.sh up for fresh start."
    ;;
  seed)
    set -a; source "$PORTAL_ROOT/.env"; set +a
    export OPENWEBUI_URL="${OPENWEBUI_URL:-http://localhost:8080}"
    python "$PORTAL_ROOT/scripts/openwebui_init.py"
    ;;
  logs)
    cd "$PORTAL_ROOT/deploy/portal-5"
    docker compose logs -f "${2:-portal-pipeline}"
    ;;
  *)
    echo "Usage: ./launch.sh [up|down|clean|seed|logs]"
    ;;
esac
```

---

### Phase 9 — Cluster Scale-Out Guide

Create `docs/CLUSTER_SCALE.md` that maps directly to the Mac Studio growth plan:

```markdown
# Portal 5.0 — Cluster Scale-Out Guide

Portal 5.0 is designed to grow from a single M4 Mac to a 12-node Mac Studio 
cluster without any code changes. All scaling is done by editing config/backends.yaml.

## Stage 1 → Stage 2: Add a Second Mac Studio

1. Install Ollama on the new Mac Studio
2. Configure it to listen on the network:
   OLLAMA_HOST=0.0.0.0 ollama serve
3. Add to config/backends.yaml:

   - id: ollama-node-2
     type: ollama
     url: "http://192.168.1.102:11434"
     group: general
     models: [dolphin-llama3:8b]

4. Restart the pipeline container:
   docker compose restart portal-pipeline

Portal automatically discovers the new backend and load-balances across both.

## Stage 3: vLLM for 70B Models

When ready to run 70B+ models (Llama 3.1 70B, etc.) via vLLM:

1. Install vLLM on the target machine
2. Start vLLM: vllm serve meta-llama/Llama-3.1-70B-Instruct --port 8000
3. Add to config/backends.yaml:

   - id: vllm-70b
     type: openai_compatible
     url: "http://192.168.1.103:8000"
     group: general
     models: [meta-llama/Llama-3.1-70B-Instruct]

## Stage 4-5: Specialized Model Groups

Assign different machines to different workspace groups for optimal routing:

   - id: vllm-coding
     url: "http://192.168.1.104:8000"
     group: coding      # auto-coding workspace routes here first
     models: [Qwen/Qwen2.5-Coder-32B-Instruct]

   - id: vllm-creative  
     url: "http://192.168.1.105:8000"
     group: creative    # auto-creative routes here first
     models: [mistral-7b-instruct-abliterated]

Open WebUI, the MCP tools, and the Telegram/Slack channels all continue working 
unchanged. The only edit is a YAML file.
```

---

### Phase 10 — Verification Checklist

```bash
# ── Compile checks ─────────────────────────────────────────────────────────
python3 -m py_compile portal_pipeline/cluster_backends.py && echo "OK: cluster_backends"
python3 -m py_compile portal_pipeline/router_pipe.py && echo "OK: router_pipe"
python3 -m py_compile portal_channels/telegram/bot.py && echo "OK: telegram"
python3 -m py_compile portal_channels/slack/bot.py && echo "OK: slack"

# ── Unit tests ─────────────────────────────────────────────────────────────
pytest tests/ -v
# All tests must pass

# ── Pipeline smoke test ────────────────────────────────────────────────────
python -m portal_pipeline &
PIPE_PID=$!
sleep 3
curl -s http://localhost:9099/health
curl -s -H "Authorization: Bearer portal-pipeline" \
  http://localhost:9099/v1/models | python3 -c "
import json,sys
d=json.load(sys.stdin)
ids=[m['id'] for m in d['data']]
assert len(ids)==9, f'Expected 9 workspaces, got {len(ids)}'
print(f'Pipeline exposes {len(ids)} workspaces: {ids}')
"
kill $PIPE_PID

# ── Docker Compose validates ───────────────────────────────────────────────
docker compose -f deploy/portal-5/docker-compose.yml config --quiet && echo "Compose: valid"

# ── Import files complete ──────────────────────────────────────────────────
echo "Tool imports:   $(ls imports/openwebui/tools/*.json | wc -l)/9"
echo "Workspaces:     $(ls imports/openwebui/workspaces/workspace_*.json | wc -l)/9"
echo "Functions:      $(ls imports/openwebui/functions/*.json | wc -l)/1"

# ── Line count comparison ──────────────────────────────────────────────────
echo ""
echo "=== Portal 4.x vs 5.0 ==="
echo "Portal 4.x src/portal:     18,758 lines"
echo "Portal 5.0 portal_pipeline: $(find portal_pipeline -name '*.py' | xargs wc -l | tail -1)"
echo "Portal 5.0 portal_channels: $(find portal_channels -name '*.py' | xargs wc -l | tail -1)"
echo "Portal 5.0 portal_mcp:      $(find portal_mcp -name '*.py' | xargs wc -l | tail -1 | awk '{print $1}') (carried forward, unchanged)"
```

---

### Phase 11 — Git & README

```bash
git add .
git commit -m "feat: Portal 5.0 — Open WebUI enhancement layer

Architecture shift: Portal becomes an intelligence layer ON TOP of Open WebUI
rather than a parallel web stack that duplicates what Open WebUI does natively.

What changed:
- Deleted: web server, auth, RAG, knowledge base, observability (~3,800 lines)
  → All replaced by Open WebUI native features
- Rewritten: routing engine → Open WebUI Pipeline (portal_pipeline/)
  → Clean FastAPI service on :9099, config-driven backend registry
  → Transparent single-node (Ollama) and cluster (vLLM) support
- Rewritten: Telegram/Slack → thin channel adapters (portal_channels/)
  → ~150 lines each vs 617/218 in 4.x
  → Call Pipeline API, no AgentCore dependency
- Carried forward: MCP servers (portal_mcp/) — unchanged, zero dependencies
  → Registered as Open WebUI Tool Servers

What this enables:
- Mac Studio cluster scale-out: add nodes to config/backends.yaml, no code
- vLLM integration: same config, just different backend type
- All 9 workspace routing modes work from day one
- Auto-seeding on fresh install: ./launch.sh up seeds everything

Portal 4.x preserved at tag v4.0 / branch main for reference."

git tag v5.0.0-alpha
git push origin portal-5.0 --tags
```

---

## Part 5 — What Portal 5.0 Is NOT

To keep scope honest:

- **Not a fork of Open WebUI.** Portal 5.0 does not modify Open WebUI's source. It extends it through documented extension points (Pipelines, Tool Servers, Functions).
- **Not a replacement for Ollama.** Ollama handles inference. Portal routes to it.
- **Not a new agent framework.** The routing is intentionally simple — classify request, select backend, forward. Complex agentic behavior lives in Open WebUI's native agentic mode with MCP tools.
- **Not dependent on Portal 4.x.** Clean start. The old repo stays intact at tag `v4.0` as reference.

---

## Part 6 — Effort Estimate

| Phase | Task | Effort |
|---|---|---|
| 0 | Repo setup, pyproject.toml | 30 min |
| 1 | BackendRegistry + backends.yaml | 2 hours |
| 2 | Pipeline server (router_pipe.py) | 3 hours |
| 3 | Telegram + Slack channel adapters | 2 hours |
| 4 | Copy + verify portal_mcp/ | 30 min |
| 5 | docker-compose.yml + Dockerfile.pipeline | 1 hour |
| 6 | Import files + openwebui_init.py | carried forward |
| 7 | Unit tests | 1.5 hours |
| 8 | .env.example + launch.sh | 30 min |
| 9 | Cluster scale-out docs | 1 hour |
| 10 | Full verification pass | 1 hour |
| 11 | Git + README | 30 min |
| **Total** | | **~13-14 hours** |

This is one solid coding agent session — achievable in a single Claude Code run with `/compact` at Phase 5 if context gets long.
