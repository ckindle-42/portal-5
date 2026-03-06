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
_startup_time = time.time()

# Canonical workspace definitions — must match backends.yaml workspace_routing keys
# model_hint: preferred Ollama model tag within the routed backend group
WORKSPACES: dict[str, dict[str, str]] = {
    "auto": {
        "name": "🤖 Portal Auto Router",
        "description": (
            "Intelligently routes to the best specialist model based on your question. "
            "Security/redteam topics → BaronLLM. Coding → Qwen3-Coder. "
            "Reasoning/research → DeepSeek-R1. Other → general."
        ),
        "model_hint": "dolphin-llama3:8b",
    },
    "auto-coding": {
        "name": "💻 Portal Code Expert",
        "description": "Code generation, debugging, architecture review",
        "model_hint": "mlx-community/Qwen3-Coder-Next-4bit",
    },
    "auto-security": {
        "name": "🔒 Portal Security Analyst",
        "description": "Security analysis, hardening, vulnerability assessment",
        "model_hint": "baronllm:q6_k",
    },
    "auto-redteam": {
        "name": "🔴 Portal Red Team",
        "description": "Offensive security, penetration testing, exploit research",
        "model_hint": "baronllm:q6_k",
    },
    "auto-blueteam": {
        "name": "🔵 Portal Blue Team",
        "description": "Defensive security, incident response, threat hunting",
        "model_hint": "lily-cybersecurity:q4_k_m",
    },
    "auto-creative": {
        "name": "✍️  Portal Creative Writer",
        "description": "Creative writing, storytelling, content generation",
        "model_hint": "dolphin-llama3:8b",
    },
    "auto-reasoning": {
        "name": "🧠 Portal Deep Reasoner",
        "description": "Complex analysis, research synthesis, step-by-step reasoning",
        "model_hint": "deepseek-r1:32b-q4_k_m",
    },
    "auto-documents": {
        "name": "📄 Portal Document Builder",
        "description": "Create Word, Excel, PowerPoint via MCP tools",
        "model_hint": "minimax-m2:q4_k_m",
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
        "model_hint": "deepseek-r1:32b-q4_k_m",
    },
    "auto-vision": {
        "name": "👁️  Portal Vision",
        "description": "Image understanding, visual analysis, multimodal tasks",
        "model_hint": "qwen3-vl:32b",
    },
    "auto-data": {
        "name": "📊 Portal Data Analyst",
        "description": "Data analysis, statistics, visualization guidance",
        "model_hint": "deepseek-r1:32b-q4_k_m",
    },
}

# ── Content-aware routing keyword sets ───────────────────────────────────────
# Applied only when the user selects the 'auto' workspace.
# Each set maps to a workspace. Order matters — security before coding
# so "write an exploit in Python" routes to security, not coding.

_SECURITY_KEYWORDS: frozenset[str] = frozenset(
    {
        # Offensive / redteam
        "exploit",
        "payload",
        "shellcode",
        "privilege escalation",
        "privesc",
        "reverse shell",
        "bind shell",
        "command injection",
        "sql injection",
        "sqli",
        "xss",
        "csrf",
        "buffer overflow",
        "rop chain",
        "heap spray",
        "use after free",
        "uaf",
        "zero day",
        "0day",
        "cve-",
        "metasploit",
        "msfvenom",
        "meterpreter",
        "cobalt strike",
        "c2 server",
        "c&c",
        "lateral movement",
        "persistence mechanism",
        "evasion",
        "obfuscation",
        "antivirus bypass",
        "edr bypass",
        "av evasion",
        "defense evasion",
        "exfiltration",
        "data exfiltration",
        "lolbas",
        "living off the land",
        "pentesting",
        "pentest",
        "penetration test",
        "red team",
        "redteam",
        "offensive security",
        "bug bounty",
        "ctf",
        "capture the flag",
        "nmap",
        "masscan",
        "gobuster",
        "nikto",
        "burp suite",
        "sqlmap",
        "hydra",
        "hashcat",
        "mimikatz",
        "bloodhound",
        "crackmapexec",
        "pass the hash",
        "pass the ticket",
        "kerberoasting",
        "asreproasting",
        "golden ticket",
        "silver ticket",
        "dcsync",
        # Defensive / blue team
        "incident response",
        "threat hunting",
        "threat intelligence",
        "ioc",
        "indicator of compromise",
        "malware analysis",
        "reverse engineering",
        "yara rule",
        "sigma rule",
        "siem alert",
        "splunk detection",
        "ids rule",
        "snort rule",
        "suricata",
        "network forensics",
        "memory forensics",
        "volatility",
        "malware",
        "ransomware",
        "trojan",
        "rootkit",
        "backdoor",
        "botnet",
        "apt",
        "threat actor",
        "vulnerability assessment",
        "vulnerability scan",
        "nessus",
        "openvas",
        "security audit",
        "hardening",
        "cis benchmark",
        "mitre att&ck",
        "attack framework",
        "kill chain",
        "diamond model",
    }
)

_REDTEAM_KEYWORDS: frozenset[str] = frozenset(
    {
        # Clearly offensive intent — route to redteam (more permissive model)
        "exploit",
        "payload",
        "shellcode",
        "bypass",
        "evasion",
        "obfuscate",
        "reverse shell",
        "bind shell",
        "privilege escalation",
        "privesc",
        "c2",
        "c2 server",
        "command and control",
        "metasploit",
        "msfvenom",
        "cobalt strike",
        "offensive",
        "red team",
        "redteam",
        "pentest",
        "penetration test",
        "attack",
        "hack",
        "hacking",
        "ctf",
        "lolbas",
        "living off",
        "lateral movement",
        "mimikatz",
        "bloodhound",
        "dcsync",
        "kerberoast",
        "pass the hash",
        "golden ticket",
        "edr bypass",
        "av evasion",
        "antivirus bypass",
    }
)

_CODING_KEYWORDS: frozenset[str] = frozenset(
    {
        "write a function",
        "write a script",
        "write a program",
        "write code",
        "debug this",
        "fix this code",
        "fix the bug",
        "code review",
        "refactor",
        "implement",
        "class definition",
        "api endpoint",
        "unit test",
        "pytest",
        "unittest",
        "docker",
        "kubernetes",
        "ci/cd",
        "sql query",
        "regex",
        "algorithm",
        "data structure",
        "python",
        "javascript",
        "typescript",
        "rust",
        "go ",
        "golang",
        "bash script",
        "powershell",
        "ansible",
        "terraform",
        "splunk",
        "spl query",
        "bigfix",
        "bes xml",
        "relevance",
    }
)

_REASONING_KEYWORDS: frozenset[str] = frozenset(
    {
        "analyze",
        "compare",
        "evaluate",
        "pros and cons",
        "trade-off",
        "research",
        "summarize",
        "explain in depth",
        "step by step",
        "break down",
        "how does",
        "why does",
        "what is the difference",
        "deep dive",
        "comprehensive",
        "thorough",
        "detailed analysis",
    }
)


def _detect_workspace(messages: list[dict]) -> str | None:
    """Detect the most appropriate workspace from the last user message.

    Returns a workspace ID string, or None if no strong signal found
    (caller should use the default 'auto' routing in that case).

    Routing priority (highest to lowest):
    1. Redteam keywords → auto-redteam (most permissive security model)
    2. Security keywords → auto-security (defensive + offensive analysis)
    3. Coding keywords → auto-coding (Qwen3-Coder-Next via MLX)
    4. Reasoning keywords → auto-reasoning (DeepSeek-R1)
    """
    # Find the last user message
    last_user_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_content = str(msg.get("content", "")).lower()
            break

    if not last_user_content:
        return None

    # Redteam check first — more specific than security
    redteam_hits = sum(1 for kw in _REDTEAM_KEYWORDS if kw in last_user_content)
    if redteam_hits >= 2:
        return "auto-redteam"

    # Security check (broader — includes defensive topics)
    security_hits = sum(1 for kw in _SECURITY_KEYWORDS if kw in last_user_content)
    if security_hits >= 1:
        return "auto-security"

    # Coding check
    coding_hits = sum(1 for kw in _CODING_KEYWORDS if kw in last_user_content)
    if coding_hits >= 1:
        return "auto-coding"

    # Reasoning check (requires 2+ signals to avoid false positives)
    reasoning_hits = sum(1 for kw in _REASONING_KEYWORDS if kw in last_user_content)
    if reasoning_hits >= 2:
        return "auto-reasoning"

    return None


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

    assert _request_semaphore is not None
    try:
        await asyncio.wait_for(_request_semaphore.acquire(), timeout=0.001)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Server busy — too many concurrent requests. Please retry.",
            headers={"Retry-After": "5"},
        ) from None

    _is_streaming = False
    try:
        assert registry is not None

        body = await request.json()
        workspace_id = body.get("model", "auto")
        stream = body.get("stream", True)

        # Content-aware routing for 'auto' workspace
        # Inspect message content to pick the most specialized backend.
        # This lets users ask security/coding/reasoning questions through 'auto'
        # and get the right specialist model without manually switching workspaces.
        if workspace_id == "auto":
            messages = body.get("messages", [])
            detected = _detect_workspace(messages)
            if detected:
                logger.info("Auto-routing: detected workspace '%s' from message content", detected)
                workspace_id = detected

        _request_count[workspace_id] = _request_count.get(workspace_id, 0) + 1

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
            # Construct first, mark streaming only after success
            # If StreamingResponse() raises, finally block correctly releases semaphore
            _streaming_response = StreamingResponse(
                _stream_from_backend_guarded(backend.chat_url, backend_body, _request_semaphore),
                media_type="text/event-stream",
            )
            _is_streaming = True  # Only set AFTER successful construction
            return _streaming_response
        return await _complete_from_backend(backend.chat_url, backend_body)
    finally:
        if not _is_streaming:
            # Non-streaming: response fully awaited above, safe to release here
            # Streaming: generator releases after stream completes
            _request_semaphore.release()


async def _stream_from_backend_guarded(
    url: str, body: dict, sem: asyncio.Semaphore
) -> AsyncIterator[bytes]:
    """Stream from backend and release semaphore only when stream is complete.

    This is required because StreamingResponse returns immediately (before the
    generator runs), so the normal finally-block release fires too early.
    """
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
    finally:
        sem.release()  # Release AFTER generator is fully exhausted


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
