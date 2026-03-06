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
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from portal_pipeline.cluster_backends import BackendRegistry

logger = logging.getLogger(__name__)

# Basic Prometheus-compatible metrics counter
_request_count: dict[str, int] = {}
_request_errors: int = 0
_startup_time = time.time()

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
        "model_hint": "hf.co/Qwen/Qwen3-Coder-Next-GGUF",
    },
    "auto-security": {
        "name": "🔒 Portal Security Analyst",
        "description": "Security analysis, hardening, vulnerability assessment",
        "model_hint": "hf.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF",
    },
    "auto-redteam": {
        "name": "🔴 Portal Red Team",
        "description": "Offensive security, penetration testing, exploit research",
        "model_hint": "hf.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF",
    },
    "auto-blueteam": {
        "name": "🔵 Portal Blue Team",
        "description": "Defensive security, incident response, threat hunting",
        "model_hint": "hf.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF",
    },
    "auto-creative": {
        "name": "✍️  Portal Creative Writer",
        "description": "Creative writing, storytelling, content generation",
        "model_hint": "dolphin-llama3:8b",
    },
    "auto-reasoning": {
        "name": "🧠 Portal Deep Reasoner",
        "description": "Complex analysis, research synthesis, step-by-step reasoning",
        "model_hint": "hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF",
    },
    "auto-documents": {
        "name": "📄 Portal Document Builder",
        "description": "Create Word, Excel, PowerPoint via MCP tools",
        "model_hint": "hf.co/MiniMaxAI/MiniMax-M2.1-GGUF",
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
        "model_hint": "hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF",
    },
    "auto-vision": {
        "name": "👁️  Portal Vision",
        "description": "Image understanding, visual analysis, multimodal tasks",
        "model_hint": "qwen3-omni:30b",
    },
    "auto-data": {
        "name": "📊 Portal Data Analyst",
        "description": "Data analysis, statistics, visualization guidance",
        "model_hint": "hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF",
    },
}

PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "portal-pipeline")

# Concurrency limiter — prevents Ollama overload when all workers are busy
_MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT_REQUESTS", "20"))
_request_semaphore: asyncio.Semaphore | None = None

registry: BackendRegistry | None = None
_health_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global registry, _health_task, _request_semaphore
    _request_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
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


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    """Prometheus-compatible metrics endpoint.

    Note: request counters are per-worker when PIPELINE_WORKERS > 1.
    For aggregate counts, sum across scrape intervals or set PIPELINE_WORKERS=1.
    """
    uptime = time.time() - _startup_time
    lines = [
        "# HELP portal_requests_total Total requests by workspace (per-worker when workers>1)",
        "# TYPE portal_requests_total counter",
    ]
    for ws_id, count in _request_count.items():
        lines.append(f'portal_requests_total{{workspace="{ws_id}"}} {count}')

    assert registry is not None
    healthy = len(registry.list_healthy_backends())
    total = len(registry.list_backends())

    lines += [
        "# HELP portal_backends_healthy Number of healthy backends",
        "# TYPE portal_backends_healthy gauge",
        f"portal_backends_healthy {healthy}",
        "# HELP portal_backends_total Total registered backends",
        "# TYPE portal_backends_total gauge",
        f"portal_backends_total {total}",
        "# HELP portal_uptime_seconds Process uptime in seconds",
        "# TYPE portal_uptime_seconds gauge",
        f"portal_uptime_seconds {uptime:.1f}",
        "# HELP portal_workspaces_total Number of configured workspaces",
        "# TYPE portal_workspaces_total gauge",
        f"portal_workspaces_total {len(WORKSPACES)}",
    ]
    return PlainTextResponse("\n".join(lines) + "\n")


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

    # Concurrency check — return 503 if server is overloaded
    assert _request_semaphore is not None
    try:
        await asyncio.wait_for(_request_semaphore.acquire(), timeout=0.001)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Server busy — too many concurrent requests. Please retry.",
            headers={"Retry-After": "5"},
        ) from None
    try:
        assert registry is not None

        body = await request.json()
        workspace_id = body.get("model", "auto")
        stream = body.get("stream", True)

        # Increment request counter for this workspace
        _request_count[workspace_id] = _request_count.get(workspace_id, 0) + 1

        # Select backend
        backend = registry.get_backend_for_workspace(workspace_id)
        if not backend:
            raise HTTPException(
                status_code=503,
                detail=(
                    "No healthy backends available. "
                    "Ensure Ollama is running and a model is pulled. "
                    "Check config/backends.yaml."
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
                    workspace_id,
                    model_hint,
                    backend.id,
                    backend.models,
                    target_model,
                )

        backend_body = {**body, "model": target_model}

        logger.info(
            "Routing workspace=%s → backend=%s model=%s stream=%s",
            workspace_id,
            backend.id,
            target_model,
            stream,
        )

        if stream:
            return StreamingResponse(
                _stream_from_backend(backend.chat_url, backend_body),
                media_type="text/event-stream",
            )
        return await _complete_from_backend(backend.chat_url, backend_body)
    finally:
        _request_semaphore.release()


async def _stream_from_backend(url: str, body: dict) -> AsyncIterator[bytes]:
    assert registry is not None
    try:
        async with (
            httpx.AsyncClient(timeout=registry.request_timeout) as client,
            client.stream("POST", url, json=body) as resp,
        ):
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
