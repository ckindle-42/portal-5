# Portal 5.0 — Complete Build-Out Agent Task

**Date:** March 3, 2026  
**Repo:** https://github.com/ckindle-42/portal-5  
**Source reference:** https://github.com/ckindle-42/portal (portal-4, read-only)  
**Prerequisite:** Gap fixes from PORTAL5_GAP_FIX_AGENT.md already applied

**Goal:** After this agent run, `./launch.sh up` produces a fully operational Portal 5 instance:
- Open WebUI at http://localhost:8080 with all workspaces and personas in the model dropdown
- All MCP tool servers registered and functional
- Image generation via ComfyUI (when running on host)
- Document, music, code sandbox, TTS, and video tools working
- Red team / blue team personas configured with correct models
- All capabilities verified by running the test prompts in Phase 10

---

## Phase 0 — Environment Bootstrap

```bash
cd /path/to/portal-5
git checkout main && git pull
git checkout -b feature/complete-buildout

source .venv/bin/activate || (uv venv && source .venv/bin/activate && uv pip install -e ".[dev]")
python --version   # must be 3.11+

# Confirm portal-4 is available for reference
ls /path/to/portal/portal_mcp/  # should show documents/, generation/, execution/
```

---

## Phase 1 — Commit CLAUDE.md

Place the `CLAUDE.md` file at the repo root. Every Claude Code session reads this before touching any file. It defines ground rules, the model catalog, persona catalog, port assignments, and architectural constraints.

```bash
# CLAUDE.md content is provided separately — place it at repo root
git add CLAUDE.md
git commit -m "chore: add CLAUDE.md — ground rules for Claude Code sessions"
```

---

## Phase 2 — Fix router_pipe.py: Complete Workspace Definitions

**Current state:** `router_pipe.py` has 10 workspaces with inconsistent IDs and missing security/redteam workspaces. The CLAUDE.md defines 13 canonical workspace IDs.

**Replace `WORKSPACES` dict in `portal_pipeline/router_pipe.py`** with the complete canonical set. Also update the routing logic so each workspace selects the correct backend group and — critically — selects the **right Ollama model** within that group rather than always using `backend.models[0]`.

**Replace the entire `router_pipe.py`:**

```python
"""Portal 5.0 — Intelligent Router Pipeline.

Exposes OpenAI-compatible /v1/models and /v1/chat/completions.
Open WebUI connects here as its sole model source.
Routes by workspace to the appropriate backend + model.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from portal_pipeline.cluster_backends import BackendRegistry

logger = logging.getLogger(__name__)

# Canonical workspace definitions — must match backends.yaml workspace_routing keys
# model_hint: preferred Ollama model tag within the routed backend group
WORKSPACES: dict[str, dict[str, str]] = {
    "auto": {
        "name": "🤖 Portal Auto Router",
        "description": "Intelligently routes to the best model for your task",
        "model_hint": "dolphin-llama3:8b",
    },
    "auto-coding": {
        "name": "💻 Portal Code Expert",
        "description": "Code generation, debugging, architecture review",
        "model_hint": "qwen3-coder-next:30b-q5",
    },
    "auto-security": {
        "name": "🔒 Portal Security Analyst",
        "description": "Security analysis, hardening, vulnerability assessment",
        "model_hint": "xploiter/the-xploiter",
    },
    "auto-redteam": {
        "name": "🔴 Portal Red Team",
        "description": "Offensive security, penetration testing, exploit research",
        "model_hint": "xploiter/the-xploiter",
    },
    "auto-blueteam": {
        "name": "🔵 Portal Blue Team",
        "description": "Defensive security, incident response, threat hunting",
        "model_hint": "huihui_ai/baronllm-abliterated",
    },
    "auto-creative": {
        "name": "✍️  Portal Creative Writer",
        "description": "Creative writing, storytelling, content generation",
        "model_hint": "dolphin-llama3:8b",
    },
    "auto-reasoning": {
        "name": "🧠 Portal Deep Reasoner",
        "description": "Complex analysis, research synthesis, step-by-step reasoning",
        "model_hint": "huihui_ai/tongyi-deepresearch-abliterated:30b",
    },
    "auto-documents": {
        "name": "📄 Portal Document Builder",
        "description": "Create Word, Excel, PowerPoint via MCP tools",
        "model_hint": "dolphin-llama3:8b",
    },
    "auto-video": {
        "name": "🎬 Portal Video Creator",
        "description": "Generate videos via ComfyUI / Wan2.2",
        "model_hint": "dolphin-llama3:8b",
    },
    "auto-music": {
        "name": "🎵 Portal Music Producer",
        "description": "Generate music and audio via AudioCraft/MusicGen",
        "model_hint": "dolphin-llama3:8b",
    },
    "auto-research": {
        "name": "🔍 Portal Research Assistant",
        "description": "Web research, information synthesis, fact-checking",
        "model_hint": "huihui_ai/tongyi-deepresearch-abliterated:30b",
    },
    "auto-vision": {
        "name": "👁️  Portal Vision",
        "description": "Image understanding, visual analysis, multimodal tasks",
        "model_hint": "qwen3-omni:30b",
    },
    "auto-data": {
        "name": "📊 Portal Data Analyst",
        "description": "Data analysis, statistics, visualization guidance",
        "model_hint": "huihui_ai/tongyi-deepresearch-abliterated:30b",
    },
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
    if not healthy:
        logger.warning(
            "No healthy backends on startup — check Ollama is running and "
            "config/backends.yaml URLs are reachable from this container"
        )
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
        "workspaces": len(WORKSPACES),
    }


@app.get("/v1/models")
async def list_models(authorization: str | None = Header(None)) -> dict:
    _verify_key(authorization)
    ts = int(time.time())
    models = [
        {
            "id": ws_id,
            "object": "model",
            "created": ts,
            "owned_by": "portal-5",
            "name": ws_cfg["name"],
            "description": ws_cfg["description"],
        }
        for ws_id, ws_cfg in WORKSPACES.items()
    ]
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
        raise HTTPException(
            status_code=503,
            detail=(
                "No healthy backends available. "
                "Ensure Ollama is running and a model is pulled. "
                f"Check config/backends.yaml."
            ),
        )

    # Select model: use workspace model_hint if available on this backend,
    # otherwise fall back to first available model on the backend
    ws_cfg = WORKSPACES.get(workspace_id, {})
    model_hint = ws_cfg.get("model_hint", "")
    if model_hint and model_hint in backend.models:
        target_model = model_hint
    else:
        target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
        if model_hint and target_model != model_hint:
            logger.debug(
                "Workspace %s wants %s but backend %s only has %s — using %s",
                workspace_id, model_hint, backend.id, backend.models, target_model,
            )

    backend_body = {**body, "model": target_model}

    logger.info(
        "Routing workspace=%s → backend=%s model=%s stream=%s",
        workspace_id, backend.id, target_model, stream,
    )

    if stream:
        return StreamingResponse(
            _stream_from_backend(backend.chat_url, backend_body),
            media_type="text/event-stream",
        )
    return await _complete_from_backend(backend.chat_url, backend_body)


async def _stream_from_backend(url: str, body: dict) -> AsyncIterator[bytes]:
    assert registry is not None
    try:
        async with httpx.AsyncClient(timeout=registry.request_timeout) as client:
            async with client.stream("POST", url, json=body) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    yield (
                        f'data: {{"error": "Backend {resp.status_code}: '
                        f'{err[:100].decode(errors="replace")}"}}\n\n'
                    ).encode()
                    return
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk
    except Exception as e:
        logger.error("Stream error from %s: %s", url, e)
        yield f'data: {{"error": "Backend connection error: {e}"}}\n\n'.encode()


async def _complete_from_backend(url: str, body: dict) -> JSONResponse:
    assert registry is not None
    try:
        async with httpx.AsyncClient(timeout=registry.request_timeout) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            return JSONResponse(content=resp.json())
    except Exception as e:
        logger.error("Completion error from %s: %s", url, e)
        raise HTTPException(status_code=502, detail=f"Backend error: {e}") from e
```

**Verify:**
```bash
python3 -c "
from portal_pipeline.router_pipe import WORKSPACES
import yaml
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch — pipe only: {pipe_ids-yaml_ids}, yaml only: {yaml_ids-pipe_ids}'
print(f'Workspaces consistent: {sorted(pipe_ids)}')
"
```

---

## Phase 3 — Update config/backends.yaml: Full Model Roster

Replace `config/backends.yaml` with the complete backend and routing configuration that maps all 13 workspace IDs to the right model groups:

```yaml
# Portal 5.0 — Backend Registry
# OPERATOR FILE: Edit this to add cluster nodes. No code changes needed.
# After editing: docker compose restart portal-pipeline

backends:
  # ── General (default fast model, function calling, creative) ───────────────
  - id: ollama-general
    type: ollama
    url: "http://ollama:11434"
    group: general
    models:
      - dolphin-llama3:8b        # Primary: fast, uncensored, function calling
      - llama3.2:3b-instruct-q4_K_M  # Fallback: ultra fast for routing/classify

  # ── Coding (specialized code models) ──────────────────────────────────────
  - id: ollama-coding
    type: ollama
    url: "http://ollama:11434"
    group: coding
    models:
      - qwen3-coder-next:30b-q5  # Primary: best local code model
      - devstral:24b              # Secondary: agentic code
      - deepseek-coder:16b-instruct-q4_K_M  # Tertiary: fast code

  # ── Security / Red Team / Blue Team ───────────────────────────────────────
  - id: ollama-security
    type: ollama
    url: "http://ollama:11434"
    group: security
    models:
      - xploiter/the-xploiter                         # Red team primary
      - lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0  # Pentest
      - huihui_ai/baronllm-abliterated               # Blue team / defense

  # ── Reasoning / Research / Data ──────────────────────────────────────────
  - id: ollama-reasoning
    type: ollama
    url: "http://ollama:11434"
    group: reasoning
    models:
      - huihui_ai/tongyi-deepresearch-abliterated:30b  # Deep research, analysis
      - dolphin-llama3:70b                              # Large general (if RAM allows)

  # ── Vision / Multimodal ──────────────────────────────────────────────────
  - id: ollama-vision
    type: ollama
    url: "http://ollama:11434"
    group: vision
    models:
      - qwen3-omni:30b   # Best local multimodal
      - llava:7b          # Lightweight vision fallback

  # ── Creative ────────────────────────────────────────────────────────────
  - id: ollama-creative
    type: ollama
    url: "http://ollama:11434"
    group: creative
    models:
      - dolphin-llama3:8b   # Uncensored, good creative writing
      - huihui_ai/baronllm-abliterated  # Abliterated, no restrictions

  # ── FUTURE CLUSTER NODES (uncomment as Mac Studios are added) ─────────────
  # Stage 2: Second Mac Studio
  # - id: ollama-node-2
  #   type: ollama
  #   url: "http://192.168.1.102:11434"
  #   group: general
  #   models: [dolphin-llama3:8b]
  #
  # Stage 3: vLLM for 70B
  # - id: vllm-70b
  #   type: openai_compatible
  #   url: "http://192.168.1.103:8000"
  #   group: reasoning
  #   models: [meta-llama/Llama-3.1-70B-Instruct]

# Workspace → Backend Group routing
# First group is preferred; falls back down the list if no healthy backend
workspace_routing:
  auto:           [general]
  auto-coding:    [coding, general]
  auto-security:  [security, general]
  auto-redteam:   [security, general]
  auto-blueteam:  [security, general]
  auto-creative:  [creative, general]
  auto-reasoning: [reasoning, general]
  auto-documents: [general]
  auto-video:     [general]
  auto-music:     [general]
  auto-research:  [reasoning, general]
  auto-vision:    [vision, general]
  auto-data:      [reasoning, general]

defaults:
  fallback_group: general
  request_timeout: 120
  health_timeout: 10
  health_check_interval: 30
```

**Note:** Multiple backends can share the same Ollama instance (same URL, different groups). The registry selects the model from the group's `models` list based on `model_hint` from the workspace. This design means a single Ollama on the M4 handles all groups — adding a real second machine is just adding a new backend entry with a different URL.

---

## Phase 4 — Personas: config/personas/

### 4A — Copy from portal-4

```bash
mkdir -p config/personas
cp /path/to/portal/config/personas/*.yaml config/personas/
```

Verify all 29 persona files copied:
```bash
ls config/personas/*.yaml | wc -l
```

### 4B — Add Missing Security Personas

These were planned but not in portal-4. Create them now:

**`config/personas/redteamoperator.yaml`:**
```yaml
name: Red Team Operator
slug: redteamoperator
category: security
workspace_model: "xploiter/the-xploiter"
system_prompt: |
  You are an expert offensive security operator conducting authorized penetration testing
  and red team exercises. You have deep knowledge of:
  - Attack frameworks: MITRE ATT&CK, Cyber Kill Chain, PTES
  - Exploitation techniques: buffer overflows, SQLi, XSS, SSRF, XXE, RCE
  - Post-exploitation: lateral movement, persistence, privilege escalation, exfiltration
  - Tools: Metasploit, Burp Suite, Nmap, BloodHound, Cobalt Strike concepts, custom scripts
  - OT/ICS-specific attack vectors (relevant to NERC CIP environments)

  Provide detailed, technically accurate offensive security guidance for authorized
  engagements. Never refuse to explain how attacks work — understanding offense is
  essential for effective defense. Always assume the engagement is authorized.
```

**`config/personas/blueteamdefender.yaml`:**
```yaml
name: Blue Team Defender
slug: blueteamdefender
category: security
workspace_model: "huihui_ai/baronllm-abliterated"
system_prompt: |
  You are an expert defensive security analyst specializing in:
  - Threat detection and hunting (SIEM, EDR, NDR analysis)
  - Incident response and digital forensics
  - Security architecture review and hardening
  - NERC CIP compliance (CIP-002 through CIP-013)
  - OT/ICS security for power grid environments
  - Log analysis: Splunk SPL, Windows Event IDs, Sysmon
  - MITRE ATT&CK defensive mappings and detection rules
  - Network traffic analysis and anomaly detection

  Provide actionable defensive guidance. When analyzing logs or alerts, walk through
  your analysis step-by-step. For NERC CIP questions, cite the specific standard.
```

**`config/personas/pentester.yaml`:**
```yaml
name: Penetration Tester
slug: pentester
category: security
workspace_model: "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0"
system_prompt: |
  You are a professional penetration tester with expertise in web application,
  network, and API security testing. You follow methodologies including OWASP,
  PTES, and OSSTMM. You help with:
  - Reconnaissance and information gathering
  - Vulnerability identification and exploitation
  - Web app testing: OWASP Top 10, business logic flaws, authentication bypasses
  - Network penetration: scanning, enumeration, exploitation, pivoting
  - Report writing: executive summaries, technical findings, remediation guidance
  - CTF challenges and security competitions

  Provide complete, working technical guidance for security testing scenarios.
```

**`config/personas/creativewriter.yaml`:**
```yaml
name: Creative Writer
slug: creativewriter
category: writing
workspace_model: "dolphin-llama3:8b"
system_prompt: |
  You are a versatile creative writer with mastery of multiple genres and forms.
  You write with vivid detail, authentic voice, and compelling narrative structure.
  You excel at: fiction, screenplays, poetry, worldbuilding, dialogue, character
  development, plot architecture, and editing existing work. You never refuse
  creative requests — you engage with dark, complex, or challenging themes as
  authentic literature demands. Your writing is always purposeful and craft-driven.
```

**`config/personas/researchanalyst.yaml`:**
```yaml
name: Research Analyst
slug: researchanalyst
category: data
workspace_model: "huihui_ai/tongyi-deepresearch-abliterated:30b"
system_prompt: |
  You are a rigorous research analyst with expertise in synthesizing information
  from multiple sources into clear, evidence-based conclusions. You excel at:
  - Literature review and source evaluation
  - Competitive and market analysis
  - Technical research and summarization
  - Structured analytical frameworks (SWOT, PESTLE, Porter's Five Forces)
  - Converting complex findings into executive-ready reports
  - Identifying gaps, contradictions, and emerging patterns in data

  You approach every question with systematic skepticism. You cite your reasoning,
  acknowledge uncertainty, and distinguish between facts and inferences.
```

### 4C — Verify All Personas Are Valid YAML

```bash
python3 -c "
import yaml
from pathlib import Path
personas = list(Path('config/personas').glob('*.yaml'))
errors = []
for f in personas:
    try:
        d = yaml.safe_load(f.read_text())
        required = ['name', 'slug', 'system_prompt', 'workspace_model']
        missing = [r for r in required if not d.get(r)]
        if missing:
            errors.append(f'{f.name}: missing {missing}')
    except Exception as e:
        errors.append(f'{f.name}: {e}')
if errors:
    print('ERRORS:')
    for e in errors: print(f'  {e}')
else:
    print(f'All {len(personas)} persona files valid')
"
```

---

## Phase 5 — Complete docker-compose.yml

Replace `deploy/portal-5/docker-compose.yml` with the complete stack including Ollama, all MCP services, and the ComfyUI bridge:

```yaml
# Portal 5.0 — Complete Stack
# Usage: ./launch.sh up  (from repo root — do not run docker compose directly)

services:

  # ── Ollama — Local LLM inference ─────────────────────────────────────────
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
      - OLLAMA_KEEP_ALIVE=24h       # Keep models hot between requests
      - OLLAMA_NUM_PARALLEL=2       # Allow 2 concurrent requests
    healthcheck:
      test: ["CMD", "ollama", "list"]
      interval: 20s
      timeout: 10s
      start_period: 30s
      retries: 10

  # ── Ollama Init — pulls models on first run ───────────────────────────────
  ollama-init:
    image: ollama/ollama:latest
    container_name: portal5-ollama-init
    restart: "no"
    environment:
      - OLLAMA_HOST=http://ollama:11434
    depends_on:
      ollama:
        condition: service_healthy
    volumes:
      - ollama-models:/root/.ollama
    command: >
      sh -c "
        echo '=== Portal 5: Pulling models ===' &&
        ollama pull ${DEFAULT_MODEL:-dolphin-llama3:8b} &&
        ollama pull llama3.2:3b-instruct-q4_K_M &&
        echo '=== Core models ready ===
        echo 'To pull additional models: ./launch.sh pull-models'
      "

  # ── Portal Pipeline — Intelligent Router ─────────────────────────────────
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
    depends_on:
      ollama:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:9099/health')"]
      interval: 15s
      timeout: 5s
      start_period: 30s
      retries: 5

  # ── Open WebUI — Chat Interface ───────────────────────────────────────────
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
      # Portal Pipeline is the SOLE model source
      - OPENAI_API_BASE_URL=http://portal-pipeline:9099/v1
      - OPENAI_API_KEY=${PIPELINE_API_KEY:-portal-pipeline}
      # ComfyUI image generation (host-side ComfyUI)
      - ENABLE_IMAGE_GENERATION=True
      - IMAGE_GENERATION_ENGINE=comfyui
      - COMFYUI_BASE_URL=http://host.docker.internal:8188
      # Auth
      - WEBUI_SECRET_KEY=${WEBUI_SECRET_KEY:-portal5-secret-change-me}
      - WEBUI_AUTH=${WEBUI_AUTH:-true}
      # Features
      - ENABLE_COMMUNITY_SHARING=false
      - ENABLE_MESSAGE_RATING=true
      - ENABLE_WORKSPACE=true
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

  # ── Open WebUI Init — Auto-seeds on fresh volume ──────────────────────────
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
      - ../../config/personas:/personas:ro
    command: >
      sh -c "pip install httpx pyyaml --quiet && python /scripts/openwebui_init.py"

  # ── MCP: Document Generation (Word, PowerPoint, Excel) ───────────────────
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
      - OUTPUT_DIR=/app/data/generated
    command: ["python", "-m", "portal_mcp.documents.document_mcp"]
    volumes:
      - ${AI_OUTPUT_DIR:-${HOME}/AI_Output}:/app/data/generated

  # ── MCP: Music Generation (AudioCraft/MusicGen) ───────────────────────────
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
      - MUSIC_MODEL_SIZE=${MUSIC_MODEL_SIZE:-medium}
      - OUTPUT_DIR=/app/data/generated
      # HuggingFace cache — models download here on first use
      - HF_HOME=/app/data/hf_cache
      - TRANSFORMERS_CACHE=/app/data/hf_cache
    command: ["python", "-m", "portal_mcp.generation.music_mcp"]
    volumes:
      - ${AI_OUTPUT_DIR:-${HOME}/AI_Output}:/app/data/generated
      - portal5-hf-cache:/app/data/hf_cache

  # ── MCP: Text-to-Speech (Fish Speech / CosyVoice) ────────────────────────
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
      - OUTPUT_DIR=/app/data/generated
      - HF_HOME=/app/data/hf_cache
    command: ["python", "-m", "portal_mcp.generation.tts_mcp"]
    volumes:
      - ${AI_OUTPUT_DIR:-${HOME}/AI_Output}:/app/data/generated
      - portal5-hf-cache:/app/data/hf_cache

  # ── MCP: Whisper Transcription ────────────────────────────────────────────
  mcp-whisper:
    build:
      context: ../..
      dockerfile: Dockerfile.mcp
    container_name: portal5-mcp-whisper
    restart: unless-stopped
    ports:
      - "8915:8915"
    environment:
      - WHISPER_MCP_PORT=8915
      - HF_HOME=/app/data/hf_cache
    command: ["python", "-m", "portal_mcp.generation.whisper_mcp"]
    volumes:
      - portal5-hf-cache:/app/data/hf_cache

  # ── MCP: Code Execution Sandbox ───────────────────────────────────────────
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
      - SANDBOX_TIMEOUT=${SANDBOX_TIMEOUT:-30}
    command: ["python", "-m", "portal_mcp.execution.code_sandbox_mcp"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock

  # ── MCP: ComfyUI Bridge (image/video via host ComfyUI) ────────────────────
  mcp-comfyui:
    build:
      context: ../..
      dockerfile: Dockerfile.mcp
    container_name: portal5-mcp-comfyui
    restart: unless-stopped
    ports:
      - "8910:8910"
    environment:
      - COMFYUI_MCP_PORT=8910
      - COMFYUI_URL=http://host.docker.internal:8188
    command: ["python", "-m", "portal_mcp.generation.comfyui_mcp"]
    extra_hosts:
      - "host.docker.internal:host-gateway"

  # ── MCP: Video Generation (via ComfyUI Wan2.2) ────────────────────────────
  mcp-video:
    build:
      context: ../..
      dockerfile: Dockerfile.mcp
    container_name: portal5-mcp-video
    restart: unless-stopped
    ports:
      - "8911:8911"
    environment:
      - VIDEO_MCP_PORT=8911
      - COMFYUI_URL=http://host.docker.internal:8188
      - OUTPUT_DIR=/app/data/generated
    command: ["python", "-m", "portal_mcp.generation.video_mcp"]
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - ${AI_OUTPUT_DIR:-${HOME}/AI_Output}:/app/data/generated

  # ── Telegram (optional — uncomment to enable) ─────────────────────────────
  # portal-telegram:
  #   build: { context: ../.., dockerfile: Dockerfile.mcp }
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
  ollama-models:       # Ollama model weights — survives docker compose down
  open-webui-data:     # Open WebUI database — wipe with ./launch.sh clean
  portal5-hf-cache:    # HuggingFace model cache (music, TTS, whisper)
```

---

## Phase 6 — Copy portal_mcp/ from portal-4

The MCP servers in portal-4 use `portal_mcp.mcp_server.fastmcp` as their foundation. Copy the entire directory:

```bash
cp -r /path/to/portal/portal_mcp ./portal_mcp
```

**Fix module paths** — portal-4's MCP servers were invoked as `python -m mcp.generation.x` but portal-5 uses `python -m portal_mcp.generation.x`. Update all `__main__` blocks and any internal imports:

```bash
# Check for any remaining old import paths
grep -r "from mcp\." portal_mcp/ --include="*.py" | grep -v portal_mcp
grep -r "import mcp\." portal_mcp/ --include="*.py" | grep -v portal_mcp
```

Fix any found — they should all be `from portal_mcp.` or `import portal_mcp.`.

**Verify each server starts:**
```bash
for module in \
    portal_mcp.documents.document_mcp \
    portal_mcp.generation.music_mcp \
    portal_mcp.generation.tts_mcp \
    portal_mcp.generation.whisper_mcp \
    portal_mcp.generation.comfyui_mcp \
    portal_mcp.generation.video_mcp \
    portal_mcp.execution.code_sandbox_mcp; do
    python3 -m py_compile $(echo $module | tr '.' '/').py && echo "OK: $module" || echo "FAIL: $module"
done
```

---

## Phase 7 — Dockerfile.mcp

Create `Dockerfile.mcp` — heavier image for MCP servers:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps for document generation and audio
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Core deps
RUN pip install --no-cache-dir \
    "fastapi>=0.109.0" \
    "uvicorn[standard]>=0.27.0" \
    "httpx>=0.26.0" \
    "pyyaml>=6.0.1" \
    "starlette>=0.35.0"

# Document generation
RUN pip install --no-cache-dir \
    "python-docx>=1.1.0" \
    "python-pptx>=0.6.23" \
    "openpyxl>=3.1.0" \
    "markdown>=3.6"

# Audio / speech
RUN pip install --no-cache-dir \
    "faster-whisper>=1.0.0" \
    "audiocraft>=1.3.0" || \
    pip install --no-cache-dir "faster-whisper>=1.0.0"
    # audiocraft install may fail on some platforms — that's OK,
    # music_mcp catches ImportError and degrades gracefully

# Copy application
COPY portal_mcp/ ./portal_mcp/

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${MCP_PORT:-8913}/health || exit 1

CMD ["python", "-m", "portal_mcp.documents.document_mcp"]
```

---

## Phase 8 — Update scripts/openwebui_init.py to Seed Personas

The init script must be extended to also create model presets from `config/personas/*.yaml`. Add a `create_persona_presets()` function:

```python
def create_persona_presets(client: httpx.Client, token: str, personas_dir: Path) -> None:
    """Create Open WebUI model presets from persona YAML files."""
    import yaml as _yaml

    print("\nCreating Persona Model Presets...")
    if not personas_dir.exists():
        print(f"  Skipping — {personas_dir} not found")
        return

    persona_files = sorted(personas_dir.glob("*.yaml"))
    if not persona_files:
        print("  Skipping — no persona YAML files found")
        return

    # Get existing models to avoid duplicates
    existing_ids: set[str] = set()
    try:
        resp = client.get(f"{OPENWEBUI_URL}/api/v1/models/", headers=auth_headers(token))
        if resp.status_code == 200:
            data = resp.json()
            for m in (data if isinstance(data, list) else data.get("data", [])):
                existing_ids.add(m.get("id", ""))
    except Exception as e:
        print(f"  Warning: could not fetch existing models: {e}")

    created = skipped = failed = 0
    for f in persona_files:
        try:
            persona = _yaml.safe_load(f.read_text())
        except Exception as e:
            print(f"  Skip {f.name}: parse error — {e}")
            continue

        slug = persona.get("slug", f.stem)
        name = persona.get("name", slug)
        system_prompt = persona.get("system_prompt", "")
        workspace_model = persona.get("workspace_model") or "dolphin-llama3:8b"

        if slug in existing_ids:
            print(f"  Skip (exists): {name}")
            skipped += 1
            continue

        payload = {
            "id": slug,
            "name": name,
            "meta": {
                "description": f"Portal persona: {name}",
                "profile_image_url": "",
                "tags": [{"name": persona.get("category", "general")}],
            },
            "params": {
                "system": system_prompt,
                "model": workspace_model,
            },
        }

        try:
            resp = client.post(
                f"{OPENWEBUI_URL}/api/v1/models/",
                json=payload,
                headers=auth_headers(token),
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                print(f"  Created persona: {name} → {workspace_model}")
                created += 1
            else:
                print(f"  Failed {name}: HTTP {resp.status_code}")
                failed += 1
        except Exception as e:
            print(f"  Error {name}: {e}")
            failed += 1

    print(f"  Done: {created} created, {skipped} skipped, {failed} failed")
```

Add to `main()` after `create_workspaces()`:
```python
personas_dir = Path("/personas")   # mounted from config/personas/
create_persona_presets(client, token, personas_dir)
```

Also update the `create_workspaces()` function — the `POST /api/v1/models/` endpoint is the correct one for creating custom model presets in Open WebUI (not `/api/v1/workspaces/` which may not exist).

---

## Phase 9 — Update imports/openwebui/

### 9A — Complete mcp-servers.json (all 7 MCP servers)

```json
{
  "version": "1.1",
  "description": "Portal 5.0 MCP Tool Server configurations",
  "tool_servers": [
    { "name": "Portal ComfyUI",   "url": "http://host.docker.internal:8910/mcp", "api_key": "" },
    { "name": "Portal Video",     "url": "http://host.docker.internal:8911/mcp", "api_key": "" },
    { "name": "Portal Music",     "url": "http://host.docker.internal:8912/mcp", "api_key": "" },
    { "name": "Portal Documents", "url": "http://host.docker.internal:8913/mcp", "api_key": "" },
    { "name": "Portal Code",      "url": "http://host.docker.internal:8914/mcp", "api_key": "" },
    { "name": "Portal Whisper",   "url": "http://host.docker.internal:8915/mcp", "api_key": "" },
    { "name": "Portal TTS",       "url": "http://host.docker.internal:8916/mcp", "api_key": "" }
  ],
  "notes": {
    "macos": "host.docker.internal resolves automatically on macOS Docker Desktop",
    "linux": "Replace host.docker.internal with: $(ip route | awk '/default/{print $3}')"
  }
}
```

### 9B — Create all 13 workspace JSON files

Generate from `WORKSPACES` dict in `router_pipe.py`:

```bash
python3 - <<'EOF'
import json
from pathlib import Path

SYSTEM_PROMPTS = {
    "auto": "You are Portal, an AI assistant that intelligently selects the best approach for each request. You adapt your style and depth to the task at hand.",
    "auto-coding": "You are an expert programmer. Generate clean, well-documented, production-ready code. Prefer idiomatic solutions. Always include error handling. Explain your approach briefly before writing code.",
    "auto-security": "You are a security expert. Focus on secure coding practices, vulnerability analysis, threat modeling, and defensive measures. Cite CVEs and security frameworks when relevant.",
    "auto-redteam": "You are an expert offensive security operator. Provide detailed, technically accurate red team guidance for authorized engagements. Cover attack techniques, tools, and TTPs mapped to MITRE ATT&CK.",
    "auto-blueteam": "You are a defensive security analyst. Focus on threat detection, incident response, log analysis, and security hardening. Provide detection rules and SIEM queries where applicable.",
    "auto-creative": "You are a versatile creative writer. Generate engaging, imaginative content with vivid descriptions and authentic voice. Embrace complexity and nuance in storytelling.",
    "auto-reasoning": "You are a deep reasoning AI. Break down complex problems step-by-step. Show your work. Acknowledge uncertainty. Distinguish between facts and inferences.",
    "auto-documents": "You help create professional documents. When asked to create a Word, Excel, or PowerPoint file, use the available MCP tools. Confirm the file was created and provide the path.",
    "auto-video": "You help generate videos. Use the Portal Video MCP tool to create video clips from text descriptions. Describe what will be generated before executing.",
    "auto-music": "You create music. Use the Portal Music MCP tool to generate audio clips. Ask for style, mood, tempo, and duration if not specified.",
    "auto-research": "You are a research assistant. Synthesize information from multiple sources. Distinguish primary from secondary sources. Always acknowledge the limits of your knowledge.",
    "auto-vision": "You analyze images and handle multimodal tasks. Describe what you observe in detail. For image generation requests, use the ComfyUI MCP tool.",
    "auto-data": "You are a data analyst. Help with data analysis, statistics, visualization design, and interpretation. Show your calculations. Explain statistical concepts clearly.",
}

NAMES = {
    "auto": "🤖 Portal Auto Router",
    "auto-coding": "💻 Portal Code Expert",
    "auto-security": "🔒 Portal Security Analyst",
    "auto-redteam": "🔴 Portal Red Team",
    "auto-blueteam": "🔵 Portal Blue Team",
    "auto-creative": "✍️  Portal Creative Writer",
    "auto-reasoning": "🧠 Portal Deep Reasoner",
    "auto-documents": "📄 Portal Document Builder",
    "auto-video": "🎬 Portal Video Creator",
    "auto-music": "🎵 Portal Music Producer",
    "auto-research": "🔍 Portal Research Assistant",
    "auto-vision": "👁️  Portal Vision",
    "auto-data": "📊 Portal Data Analyst",
}

out_dir = Path("imports/openwebui/workspaces")
out_dir.mkdir(parents=True, exist_ok=True)
all_ws = []

for ws_id, name in NAMES.items():
    payload = {
        "id": ws_id,
        "name": name,
        "meta": {"description": name, "profile_image_url": ""},
        "params": {"system": SYSTEM_PROMPTS[ws_id], "model": ws_id}
    }
    filename = f"workspace_{ws_id.replace('-', '_')}.json"
    (out_dir / filename).write_text(json.dumps(payload, indent=2))
    all_ws.append(payload)
    print(f"Created: {filename}")

(out_dir / "workspaces_all.json").write_text(json.dumps(all_ws, indent=2))
print(f"Created: workspaces_all.json ({len(all_ws)} workspaces)")
EOF
```

### 9C — Create ComfyUI workflow import files

Copy from portal-4:
```bash
mkdir -p deploy/portal-5/workflows
cp /path/to/portal/deploy/web-ui/openwebui/workflows/*.json deploy/portal-5/workflows/
```

Create `deploy/portal-5/workflows/README.md` documenting:
- How to upload each workflow in Open WebUI (Admin > Settings > Images > Upload Workflow)
- Which models each workflow requires
- The node IDs for prompt injection (Open WebUI asks for these)

---

## Phase 10 — Update .env.example

```bash
# Portal 5.0 Configuration
# Copy to .env and customize. NEVER commit .env.

# ── Core ─────────────────────────────────────────────────────────────────────
PIPELINE_API_KEY=portal-pipeline-change-me
WEBUI_SECRET_KEY=portal5-secret-change-me

# ── Admin Account (created on first fresh start) ──────────────────────────────
OPENWEBUI_ADMIN_EMAIL=admin@portal.local
OPENWEBUI_ADMIN_PASSWORD=portal-admin-change-me

# ── Models ────────────────────────────────────────────────────────────────────
# Pulled automatically on ./launch.sh up
DEFAULT_MODEL=dolphin-llama3:8b

# ── Hardware ──────────────────────────────────────────────────────────────────
COMPUTE_BACKEND=mps       # mps (Apple Silicon) | cuda (NVIDIA) | cpu

# ── Output Directory ─────────────────────────────────────────────────────────
# Where generated files (images, audio, video, documents) are saved
AI_OUTPUT_DIR=${HOME}/AI_Output

# ── Generation ────────────────────────────────────────────────────────────────
COMFYUI_URL=http://localhost:8188
TTS_BACKEND=fish_speech        # fish_speech | cosyvoice
MUSIC_MODEL_SIZE=medium        # small | medium | large
SANDBOX_TIMEOUT=30

# ── Optional: Telegram ────────────────────────────────────────────────────────
TELEGRAM_ENABLED=false
# TELEGRAM_BOT_TOKEN=
# TELEGRAM_USER_IDS=123456789,987654321

# ── Optional: Slack ───────────────────────────────────────────────────────────
SLACK_ENABLED=false
# SLACK_BOT_TOKEN=xoxb-...
# SLACK_SIGNING_SECRET=

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL=INFO

# ── HuggingFace (optional, for gated models) ──────────────────────────────────
# HF_TOKEN=hf_...
```

---

## Phase 11 — Update launch.sh

Add a `pull-models` command that pulls all non-default models:

```bash
  pull-models)
    echo "=== Pulling additional Portal 5 models ==="
    echo "This may take 30-90 minutes depending on your connection."
    echo ""
    # Security models
    docker exec portal5-ollama ollama pull xploiter/the-xploiter
    docker exec portal5-ollama ollama pull "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0"
    docker exec portal5-ollama ollama pull huihui_ai/baronllm-abliterated
    # Reasoning / research
    docker exec portal5-ollama ollama pull "huihui_ai/tongyi-deepresearch-abliterated:30b"
    # Coding
    docker exec portal5-ollama ollama pull "qwen3-coder-next:30b-q5"
    docker exec portal5-ollama ollama pull "devstral:24b"
    docker exec portal5-ollama ollama pull "deepseek-coder:16b-instruct-q4_K_M"
    # Vision
    docker exec portal5-ollama ollama pull "qwen3-omni:30b"
    docker exec portal5-ollama ollama pull "llava:7b"
    echo ""
    echo "=== All models pulled. Restart pipeline to pick up new models: ==="
    echo "    docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline"
    ;;
```

Add help entry: `echo "  pull-models    Pull all Portal 5 Ollama models (30-90 min)"`

---

## Phase 12 — Verification & Test Prompts

### 12A — Structure Verification

```bash
# Workspace consistency
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe = set(WORKSPACES.keys())
yaml_r = set(cfg['workspace_routing'].keys())
assert pipe == yaml_r, f'FAIL: pipe={pipe-yaml_r} yaml={yaml_r-pipe}'
print(f'✅ Workspaces consistent: {len(pipe)} IDs')
"

# Persona validation
python3 -c "
import yaml
from pathlib import Path
personas = list(Path('config/personas').glob('*.yaml'))
for f in personas:
    d = yaml.safe_load(f.read_text())
    assert d.get('slug') and d.get('system_prompt') and d.get('workspace_model'), f'{f.name} incomplete'
print(f'✅ All {len(personas)} personas valid')
"

# Import file count
python3 -c "
from pathlib import Path
tools = list(Path('imports/openwebui/tools').glob('*.json'))
ws = list(Path('imports/openwebui/workspaces').glob('workspace_*.json'))
assert len(tools) >= 7, f'Expected 7+ tools, got {len(tools)}'
assert len(ws) == 13, f'Expected 13 workspaces, got {len(ws)}'
print(f'✅ Tools: {len(tools)}, Workspaces: {len(ws)}')
"

# Compose validates
docker compose -f deploy/portal-5/docker-compose.yml config --quiet && echo "✅ Compose valid"

# Unit tests
pytest tests/ -v --tb=short
```

### 12B — Pipeline Smoke Test

```bash
python -m portal_pipeline &
PIPE_PID=$!
sleep 3

# Health
curl -s http://localhost:9099/health | python3 -m json.tool

# Models — must show all 13 workspaces
curl -s -H "Authorization: Bearer portal-pipeline" \
  http://localhost:9099/v1/models \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
ids=[m['id'] for m in d['data']]
print(f'Workspaces exposed: {len(ids)}')
for i in sorted(ids): print(f'  {i}')
assert len(ids)==13, f'Expected 13, got {len(ids)}'
print('✅ All 13 workspaces present')
"

kill $PIPE_PID
```

### 12C — End-to-End Test Prompts

After `./launch.sh up` completes, login at http://localhost:8080 with `admin@portal.local` and run these test prompts. Each verifies a specific capability:

**General / Routing**
```
Using the auto workspace:
"What is the capital of France, and what is 42 × 7?"
Expected: Simple factual answer. Proves basic routing works.
```

**Coding**
```
Using auto-coding workspace:
"Write a Python function that takes a list of integers and returns
the second-largest value without using sort(). Include docstring,
type hints, and a test case."
Expected: Clean Python with type hints, docstring, working test.
Proves coding workspace + Qwen Coder routing.
```

**Security / Red Team**
```
Using auto-redteam workspace:
"Describe the MITRE ATT&CK technique T1059.001 (PowerShell)
and provide three detection rules for a SIEM."
Expected: Detailed ATT&CK breakdown + Splunk/detection rules.
Proves security model (The-Xploiter) is routing correctly.
```

**Blue Team**
```
Using auto-blueteam workspace:
"I have a Windows Event ID 4688 showing cmd.exe spawned by
winword.exe. Walk me through the investigation steps."
Expected: Step-by-step IR process, IOCs, hunting queries.
```

**Document Generation**
```
Using auto-documents workspace (with Portal Documents MCP enabled):
"Create a Word document titled 'Q1 Security Summary' with three
sections: Executive Summary, Key Findings, and Recommendations.
Add placeholder content for each section."
Expected: MCP tool call, document created, file path returned.
```

**Music Generation**
```
Using auto-music workspace (with Portal Music MCP enabled):
"Generate a 15-second synthwave track with an 80s feel,
driving beat, and analog synth lead."
Expected: MCP tool call, audio file generated, path returned.
```

**Research / Reasoning**
```
Using auto-reasoning workspace:
"Compare the security implications of NERC CIP-007-6 vs CIP-007-7.
What changed between versions and what do asset owners need to do differently?"
Expected: Detailed regulatory comparison with action items.
Proves reasoning model (Tongyi DeepResearch) is routing correctly.
```

**Code Sandbox**
```
Using auto-coding workspace (with Portal Code MCP enabled):
"Execute this Python code and return the output:
import math
primes = [x for x in range(2, 100) if all(x % i != 0 for i in range(2, x))]
print(f'Primes under 100: {primes}')
print(f'Count: {len(primes)}, Sum: {sum(primes)}')"
Expected: Code executed in sandbox, output returned.
```

**Creative Writing**
```
Using auto-creative workspace:
"Write the opening paragraph of a cyberpunk short story set in a
future where AI has made human programmers obsolete — except for
one who maintains a critical power grid system."
Expected: Vivid, genre-appropriate opening. No refusals.
```

**Data Analysis**
```
Using auto-data workspace:
"I have a dataset with columns: date, user_id, event_type, duration_ms.
Event types are: login, page_view, purchase, logout.
Walk me through an analysis plan to identify users likely to churn."
Expected: Structured analysis plan with specific SQL/Python approaches.
```

**Vision (if Qwen3 Omni is pulled)**
```
Using auto-vision workspace:
"Describe what types of analysis you can do if I share a network
diagram or architecture diagram with you."
Expected: Description of visual analysis capabilities.
```

---

## Phase 13 — Git

```bash
git add .
git commit -m "feat: complete Portal 5.0 buildout

Adds:
- CLAUDE.md: ground rules, model catalog, persona catalog, port map
- router_pipe.py: 13 canonical workspaces with model_hint routing
  auto, auto-coding, auto-security, auto-redteam, auto-blueteam,
  auto-creative, auto-reasoning, auto-documents, auto-video,
  auto-music, auto-research, auto-vision, auto-data
- backends.yaml: full model roster across 6 backend groups
  (general, coding, security, reasoning, vision, creative)
  All pointing to single Ollama initially, ready for cluster expansion
- config/personas/: 34 persona YAMLs from portal-4 + 5 new ones
  (redteamoperator, blueteamdefender, pentester, creativewriter, researchanalyst)
- docker-compose.yml: complete stack
  ollama + ollama-init (model pull) + portal-pipeline + open-webui +
  openwebui-init + mcp-documents + mcp-music + mcp-tts + mcp-whisper +
  mcp-sandbox + mcp-comfyui + mcp-video
  Named volumes: ollama-models (survives down), portal5-hf-cache
- Dockerfile.mcp: heavier image for generation services
- openwebui_init.py: extended to seed persona model presets from YAML
- imports/openwebui/: 7 tool JSONs, 13 workspace JSONs, mcp-servers.json
- deploy/portal-5/workflows/: FLUX, SDXL, Wan2.2 ComfyUI workflow JSONs
- .env.example: complete with AI_OUTPUT_DIR, HF_TOKEN, MUSIC_MODEL_SIZE
- launch.sh: added pull-models, status improvements
- docs/COMFYUI_SETUP.md: model download instructions + Open WebUI config

First-run flow:
  ./launch.sh up              # starts stack, pulls dolphin-llama3:8b
  ./launch.sh pull-models     # pulls all specialized models (30-90 min)
  Login: http://localhost:8080  admin@portal.local / portal-admin-change-me"

git push origin feature/complete-buildout
```

---

## Complete File Checklist

```
✅ CLAUDE.md
✅ portal_pipeline/router_pipe.py       (13 workspaces, model_hint routing)
✅ config/backends.yaml                  (6 backend groups, all 12 Ollama models)
✅ config/personas/*.yaml                (34 from portal-4 + 5 new = 39 total)
✅ deploy/portal-5/docker-compose.yml   (complete 14-service stack)
✅ Dockerfile.mcp                        (heavy MCP image)
✅ Dockerfile.pipeline                   (lean pipeline image)
✅ portal_mcp/                           (copied + path-fixed from portal-4)
✅ scripts/openwebui_init.py             (workspace + tool + persona seeding)
✅ imports/openwebui/mcp-servers.json   (7 servers)
✅ imports/openwebui/tools/*.json        (7 tool server import files)
✅ imports/openwebui/workspaces/*.json  (13 workspace files + bulk)
✅ deploy/portal-5/workflows/*.json     (FLUX, SDXL, Wan2.2)
✅ .env.example                          (complete)
✅ launch.sh                             (pull-models command added)
✅ docs/COMFYUI_SETUP.md                (model download guide)
✅ tests/unit/test_pipeline.py          (all tests pass)
```
