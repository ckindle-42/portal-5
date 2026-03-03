"""Portal 5.0 — Open WebUI Pipeline Filter (_portal_router.py compatible).

Exposes OpenAI-compatible /v1/models and /v1/chat/completions.
Routes by workspace ID to appropriate backend via BackendRegistry.
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

# Static workspace definitions (exposed as OpenAI "models")
WORKSPACES = {
    "auto": {"name": "🤖 Portal Router", "description": "Smart routing based on request context"},
    "auto-coding": {"name": "💻 Coding Assistant", "description": "Optimized for software development tasks"},
    "auto-security": {"name": "🔒 Security Analyst", "description": "Security analysis and hardening"},
    "auto-creative": {"name": "✨ Creative Writer", "description": "Creative writing and storytelling"},
    "auto-documents": {"name": "📄 Portal Document Builder", "description": "Create Word, Excel, PowerPoint via MCP tools"},
    "auto-video": {"name": "🎬 Portal Video Creator", "description": "Generate video clips via ComfyUI/Wan2.1"},
    "auto-music": {"name": "🎵 Portal Music Producer", "description": "Generate music and audio via AudioCraft"},
    "auto-research": {"name": "🔍 Portal Research Assistant", "description": "Web research, information synthesis, fact-checking"},
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
