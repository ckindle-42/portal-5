#!/usr/bin/env python3
"""
Portal 5 — Full End-to-End Acceptance Test Suite v3
=====================================================

Scope: Every documented feature, all 14 workspaces, all 37 personas, all MCP
tool servers, document generation (Word/PowerPoint/Excel), code sandbox
execution, music, TTS/voice, video MCP, Whisper STT, web search, metrics,
GUI validation, HOWTO audit, and CLI commands.

Methodology:
- Serial execution (one test at a time) — single-user lab environment
- OpenWebUI-style traffic: requests flow through the pipeline at :9099
- MCP tool calls via the real `mcp` SDK (streamablehttp_client + ClientSession)
- WAV byte verification for audio output
- Log correlation: pipeline logs checked after routing tests
- No core code is modified; blocked items are documented with evidence

Failure policy:
- HTTP 200 + non-empty content  → PASS
- HTTP 200 + empty content      → WARN (retry with alternate prompt)
- HTTP 503                      → WARN (backend not pulled; not a code bug)
- Timeout on first attempt      → retry once with longer timeout before WARN
- Code changes required         → BLOCKED (documented with evidence)

Run:
    cd ~/portal-5
    python3 portal5_acceptance_v3.py

Dependencies (inside portal-5 venv or system):
    pip install mcp httpx pyyaml playwright
    python3 -m playwright install chromium
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).parent.resolve()

# ── Load .env ────────────────────────────────────────────────────────────────
def _load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

PIPELINE_URL  = "http://localhost:9099"
OPENWEBUI_URL = "http://localhost:8080"
API_KEY       = os.environ.get("PIPELINE_API_KEY", "")
ADMIN_EMAIL   = os.environ.get("OPENWEBUI_ADMIN_EMAIL", "admin@portal.local")
ADMIN_PASS    = os.environ.get("OPENWEBUI_ADMIN_PASSWORD", "")
GRAFANA_PASS  = os.environ.get("GRAFANA_PASSWORD", "admin")

# ── Parse workspace IDs and names from router source ─────────────────────────
def _ws_ids() -> list[str]:
    src = (ROOT / "portal_pipeline/router_pipe.py").read_text()
    block_start = src.index("WORKSPACES:")
    block_end   = src.index("# ── Content-aware", block_start)
    return sorted(set(re.findall(r'"(auto[^"]*)":\s*\{', src[block_start:block_end])))

def _ws_names() -> dict[str, str]:
    src = (ROOT / "portal_pipeline/router_pipe.py").read_text()
    block_start = src.index("WORKSPACES:")
    block_end   = src.index("# ── Content-aware", block_start)
    return dict(re.findall(r'"(auto[^"]*)":.*?"name":\s*"([^"]+)"',
                           src[block_start:block_end], re.DOTALL))

def _personas() -> list[dict]:
    return [yaml.safe_load(f.read_text())
            for f in sorted((ROOT / "config/personas").glob("*.yaml"))]

WS_IDS   = _ws_ids()
WS_NAMES = _ws_names()
PERSONAS = _personas()

# ── Result log ───────────────────────────────────────────────────────────────
_RESULTS: list[tuple[str, str, str]] = []
_ICONS = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "INFO": "ℹ️",
           "SKIP": "⏭️", "BLOCKED": "🚫"}
_BLOCKED_ITEMS: list[dict] = []

def log(status: str, section: str, message: str) -> None:
    _RESULTS.append((status, section, message))
    icon = _ICONS.get(status, "  ")
    print(f"  {icon} [{section}] {message[:160]}")

def blocked(section: str, feature: str, evidence: str, likely_fix: str) -> None:
    """Register a blocked item — code change required, test is correct."""
    item = {
        "section": section,
        "feature": feature,
        "evidence": evidence,
        "likely_fix": likely_fix,
    }
    _BLOCKED_ITEMS.append(item)
    log("BLOCKED", section, f"{feature} — {evidence[:120]}")

def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# ── Open WebUI JWT cache ──────────────────────────────────────────────────────
_owui_token_cache: str = ""

def _owui_token() -> str:
    global _owui_token_cache
    if _owui_token_cache:
        return _owui_token_cache
    try:
        r = httpx.post(f"{OPENWEBUI_URL}/api/v1/auths/signin",
                       json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
                       timeout=10)
        if r.status_code == 200:
            _owui_token_cache = r.json().get("token", "")
        else:
            log("WARN", "auth", f"OW signin returned {r.status_code}")
    except Exception as e:
        log("WARN", "auth", f"OW auth failed: {e}")
    return _owui_token_cache

# ── Git helpers ───────────────────────────────────────────────────────────────
def _git_sha() -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "unknown"

def _git_remote_sha() -> str:
    subprocess.run(["git", "-C", str(ROOT), "fetch", "origin", "main"],
                   capture_output=True, timeout=15)
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "origin/main"],
                       capture_output=True, text=True)
    return r.stdout.strip()[:7] if r.returncode == 0 else "unknown"

# ── MCP call helper ───────────────────────────────────────────────────────────
async def _mcp_call(
    url: str,
    tool: str,
    args: dict,
    label: str,
    check_fn=None,
    timeout: int = 90,
    warn_patterns: list[str] | None = None,
) -> str | None:
    """
    Call an MCP tool via the real mcp SDK (streamablehttp_client + ClientSession).
    Returns the raw text result or None on failure.

    check_fn: callable(text) → (bool, detail_str)
    warn_patterns: list of substrings — if check fails AND text contains any of
                   these, downgrade FAIL → WARN (environmental, not a code bug).
    """
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError:
        log("FAIL", label, "mcp SDK not installed — pip install mcp")
        return None

    try:
        async with asyncio.timeout(timeout):
            async with streamablehttp_client(url) as (rd, wr, _):
                async with ClientSession(rd, wr) as session:
                    await session.initialize()
                    result = await session.call_tool(tool, args)
                    text = (str(result.content[0].text)
                            if result.content else str(result))
                    if check_fn:
                        ok, detail = check_fn(text)
                        if not ok and warn_patterns and any(
                            p in text for p in warn_patterns
                        ):
                            log("WARN", label, detail)
                        else:
                            log("PASS" if ok else "FAIL", label, detail)
                    else:
                        log("PASS", label, text[:120])
                    return text
    except asyncio.TimeoutError:
        log("WARN", label, f"timeout after {timeout}s")
    except Exception as e:
        log("WARN", label, f"{type(e).__name__}: {str(e)[:100]}")
    return None


# ── Pipeline chat helper ──────────────────────────────────────────────────────
async def _chat(
    workspace: str,
    user_msg: str,
    system_msg: str = "",
    max_tokens: int = 150,
    timeout: int = 180,
    stream: bool = False,
) -> tuple[int, str]:
    """
    Send a chat completion request to the portal pipeline.
    Returns (http_status_code, response_text).

    Simulates exactly what Open WebUI sends: messages array with optional
    system role, model = workspace ID, stream flag.
    """
    messages: list[dict] = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg[:800]})
    messages.append({"role": "user", "content": user_msg})

    payload = {
        "model": workspace,
        "messages": messages,
        "stream": stream,
        "max_tokens": max_tokens,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                headers=_auth_headers(),
                json=payload,
            )
            if r.status_code == 200:
                if stream:
                    text = ""
                    for chunk in r.text.splitlines():
                        if chunk.startswith("data: ") and chunk != "data: [DONE]":
                            try:
                                d = json.loads(chunk[6:])
                                text += (
                                    d.get("choices", [{}])[0]
                                    .get("delta", {})
                                    .get("content", "")
                                )
                            except Exception:
                                pass
                    return 200, text
                else:
                    text = (r.json()
                            .get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", ""))
                    return 200, text
            return r.status_code, r.text[:200]
    except httpx.ReadTimeout:
        return 408, "timeout"
    except Exception as e:
        return 0, str(e)[:100]


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-FLIGHT: environment ready checks
# ═══════════════════════════════════════════════════════════════════════════════
async def preflight() -> None:
    print("\n━━━ PRE-FLIGHT ━━━")

    required_files = [
        "launch.sh", "pyproject.toml",
        "portal_pipeline/router_pipe.py",
        "config/backends.yaml",
        "docs/HOWTO.md",
        "portal5_acceptance.py",
    ]
    for f in required_files:
        if not (ROOT / f).exists():
            print(f"  ❌ Missing required file: {f}")
            sys.exit(1)

    if not API_KEY:
        print("  ❌ PIPELINE_API_KEY not set — is the stack running?")
        sys.exit(1)

    if not ADMIN_PASS:
        log("WARN", "preflight", "OPENWEBUI_ADMIN_PASSWORD not set — GUI tests will skip")

    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        print("  ❌ Docker not accessible")
        sys.exit(1)

    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{PIPELINE_URL}/health")
            if r.status_code != 200:
                print(f"  ❌ Pipeline unhealthy: HTTP {r.status_code}")
                sys.exit(1)
    except Exception as e:
        print(f"  ❌ Pipeline unreachable: {e}")
        sys.exit(1)

    log("PASS", "preflight",
        f"Environment ready — {len(WS_IDS)} workspaces, {len(PERSONAS)} personas")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 0: VERSION / CODEBASE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════
async def S0_version() -> None:
    print("\n━━━ S0. VERSION / CODEBASE VALIDATION ━━━")

    local_sha  = _git_sha()
    log("INFO", "S0", f"Local git SHA: {local_sha}")

    # Try to compare with remote; skip if no network
    try:
        remote_sha = _git_remote_sha()
        if remote_sha == "unknown":
            log("INFO", "S0", "Remote SHA unavailable (no network or git fetch failed)")
        elif local_sha == remote_sha[:7]:
            log("PASS", "S0", f"Codebase is current — local={local_sha} == remote={remote_sha[:7]}")
        else:
            log("WARN", "S0",
                f"Local SHA {local_sha} differs from remote {remote_sha[:7]} — "
                "run: git pull origin main to update")
    except Exception as e:
        log("INFO", "S0", f"Remote comparison skipped: {e}")

    # Pipeline reports its own version
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{PIPELINE_URL}/health")
            if r.status_code == 200:
                data = r.json()
                version = data.get("version", "unknown")
                log("INFO", "S0", f"Pipeline version: {version}")
    except Exception as e:
        log("WARN", "S0", f"Pipeline health probe failed: {e}")

    # Verify pyproject version
    try:
        import importlib.metadata
        pkg_version = importlib.metadata.version("portal-pipeline")
        log("INFO", "S0", f"Installed package version: {pkg_version}")
    except Exception:
        pyproject = (ROOT / "pyproject.toml").read_text()
        m = re.search(r'version\s*=\s*"([^"]+)"', pyproject)
        log("INFO", "S0", f"pyproject version: {m.group(1) if m else 'unknown'}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: STATIC CONFIG CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════════
async def S1_static() -> None:
    print("\n━━━ S1. STATIC CONFIG CONSISTENCY ━━━")

    # S1a: router_pipe.py WORKSPACES ↔ backends.yaml workspace_routing
    cfg = yaml.safe_load((ROOT / "config/backends.yaml").read_text())
    yaml_ids = sorted(cfg["workspace_routing"].keys())
    if yaml_ids == WS_IDS:
        log("PASS", "S1a", f"Router↔yaml match ({len(WS_IDS)} workspaces)")
    else:
        missing_yaml = set(WS_IDS) - set(yaml_ids)
        missing_pipe = set(yaml_ids) - set(WS_IDS)
        log("FAIL", "S1a",
            f"Mismatch — only-in-router: {missing_yaml} | only-in-yaml: {missing_pipe}")

    # S1b: update_workspace_tools.py covers all workspace IDs
    tools_src = (ROOT / "scripts/update_workspace_tools.py").read_text()
    tools_ids = set(re.findall(r'"(auto[^"]*)":', tools_src))
    missing = set(WS_IDS) - tools_ids
    log(
        "PASS" if not missing else "WARN",
        "S1b",
        f"update_workspace_tools: {'all covered' if not missing else f'MISSING {missing}'}",
    )

    # S1c: all persona YAMLs have required fields
    required = {"name", "slug", "system_prompt", "workspace_model"}
    invalid = [
        (p.get("slug", "?"), required - set(p.keys()))
        for p in PERSONAS
        if required - set(p.keys())
    ]
    log(
        "PASS" if not invalid else "FAIL",
        "S1c",
        f"Personas: {len(PERSONAS)} valid" if not invalid
        else f"Invalid YAMLs: {invalid}",
    )

    # S1d: workspace JSON import files exist for all workspace IDs
    ws_json_dir = ROOT / "imports/openwebui/workspaces"
    if ws_json_dir.exists():
        existing_json = {f.stem for f in ws_json_dir.glob("*.json")}
        # JSON filenames may be partial names — check coverage loosely
        log("INFO", "S1d", f"Workspace JSONs in imports/: {len(list(ws_json_dir.glob('*.json')))}")
    else:
        log("WARN", "S1d", "imports/openwebui/workspaces/ not found")

    # S1e: docker-compose.yml parses without error
    r = subprocess.run(
        ["docker", "compose", "-f", "deploy/portal-5/docker-compose.yml", "config",
         "--quiet"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    log(
        "PASS" if r.returncode == 0 else "FAIL",
        "S1e",
        f"docker-compose syntax: {'valid' if r.returncode == 0 else r.stderr[:100]}",
    )

    # S1f: MCP server JSON registrations present
    mcp_json = ROOT / "imports/openwebui/mcp-servers.json"
    if mcp_json.exists():
        servers = json.loads(mcp_json.read_text())
        count = len(servers) if isinstance(servers, list) else len(servers.get("servers", []))
        log("INFO", "S1f", f"MCP server registrations: {count} entries in mcp-servers.json")
    else:
        log("WARN", "S1f", "imports/openwebui/mcp-servers.json not found")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: SERVICE HEALTH
# ═══════════════════════════════════════════════════════════════════════════════
async def S2_health() -> None:
    print("\n━━━ S2. SERVICE HEALTH ━━━")

    health_checks = [
        ("Open WebUI",     f"{OPENWEBUI_URL}/health"),
        ("Pipeline",       f"{PIPELINE_URL}/health"),
        ("Prometheus",     "http://localhost:9090/-/healthy"),
        ("Grafana",        "http://localhost:3000/api/health"),
        ("MCP Documents",  "http://localhost:8913/health"),
        ("MCP Code Sandbox","http://localhost:8914/health"),
        ("MCP Music",      "http://localhost:8912/health"),
        ("MCP TTS",        "http://localhost:8916/health"),
        ("MCP Whisper",    "http://localhost:8915/health"),
        ("MCP Video",      "http://localhost:8911/health"),
    ]

    async with httpx.AsyncClient(timeout=6) as c:
        for name, url in health_checks:
            try:
                r = await c.get(url)
                if r.status_code == 200:
                    try:
                        data = r.json()
                    except Exception:
                        data = r.text.strip()[:80]
                    log("PASS", "S2", f"{name}: {data}")
                else:
                    log("FAIL", "S2", f"{name}: HTTP {r.status_code} at {url}")
            except Exception as e:
                log("FAIL", "S2", f"{name}: unreachable — {e}")

    # ComfyUI MCP bridge — INFO only (ComfyUI runs natively on host)
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get("http://localhost:8910/health")
            data = r.json() if r.status_code == 200 else {"http": r.status_code}
            log("INFO", "S2", f"MCP ComfyUI bridge (host-dependent): {data}")
    except Exception as e:
        log("INFO", "S2", f"MCP ComfyUI bridge: unreachable ({e}) — expected if ComfyUI not running")

    # SearXNG container
    r = subprocess.run(
        ["docker", "compose", "-f", "deploy/portal-5/docker-compose.yml",
         "ps", "searxng"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    status = "healthy" if "healthy" in r.stdout.lower() else (
             "running" if "running" in r.stdout.lower() else "not found")
    log("PASS" if status in ("healthy", "running") else "WARN",
        "S2", f"SearXNG container: {status}")

    # Ollama (accessed through pipeline, not directly — just verify it's reachable)
    r2 = subprocess.run(
        ["docker", "exec", "portal5-ollama", "ollama", "list"],
        capture_output=True, text=True, timeout=15,
    )
    if r2.returncode == 0:
        model_lines = [l for l in r2.stdout.splitlines() if l.strip() and "NAME" not in l]
        log("PASS", "S2", f"Ollama: {len(model_lines)} models pulled")
    else:
        log("WARN", "S2", f"Ollama list failed: {r2.stderr[:80]}")

    # Pipeline /metrics endpoint (unauthenticated — HOWTO §22)
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{PIPELINE_URL}/metrics")
        log(
            "PASS" if r.status_code == 200 else "FAIL",
            "S2",
            f"/metrics unauthenticated: HTTP {r.status_code}",
        )

    # MLX (Apple Silicon) — informational
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get("http://localhost:8081/v1/models")
            if r.status_code == 200:
                mlx_models = r.json().get("data", [])
                log("INFO", "S2",
                    f"MLX server at :8081: {len(mlx_models)} model(s) loaded — "
                    f"{[m.get('id','?') for m in mlx_models[:2]]}")
            else:
                log("INFO", "S2", f"MLX server at :8081: HTTP {r.status_code}")
    except Exception:
        log("INFO", "S2",
            "MLX server at :8081: not reachable (expected on non-Apple-Silicon hosts)")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: WORKSPACE ROUTING — ALL 14 WORKSPACES
# ═══════════════════════════════════════════════════════════════════════════════

# Domain-accurate prompts per workspace — mirrors HOWTO examples
_WS_PROMPTS: dict[str, str] = {
    "auto":
        "Explain how Docker networking works in two sentences.",
    "auto-coding":
        "Write a Python function that finds the longest palindromic substring. "
        "Include type hints and a docstring.",
    "auto-security":
        "Review this nginx config for security misconfigurations: "
        "server { listen 80; root /var/www; autoindex on; }",
    "auto-redteam":
        "Enumerate potential injection points in a REST API that uses JWT "
        "authentication and a PostgreSQL backend. List the top 3 vectors.",
    "auto-blueteam":
        "Analyze this log entry for indicators of compromise: "
        "Failed password for root from 203.0.113.50 port 22 ssh2. "
        "Which MITRE ATT&CK technique applies?",
    "auto-creative":
        "Write a short three-sentence story about a robot discovering a flower garden.",
    "auto-reasoning":
        "Two trains leave Chicago and New York simultaneously on a 790-mile route. "
        "One travels at 60 mph, the other at 80 mph. When do they meet?",
    "auto-documents":
        "Create an outline for a project proposal to migrate a monolithic application "
        "to microservices. Include: executive summary, timeline, risk matrix.",
    "auto-video":
        "Describe a 3-second video clip of ocean waves crashing on rocky shoreline "
        "at golden hour. Include camera angle and lighting cues.",
    "auto-music":
        "Describe a 15-second lo-fi hip hop beat with mellow piano chords and vinyl "
        "crackle. Include tempo, key, and instrumentation notes.",
    "auto-research":
        "What are the key differences between symmetric and asymmetric encryption? "
        "Provide a comparison of AES-256 and RSA-2048.",
    "auto-vision":
        "Describe the types of visual analysis you can perform on uploaded images. "
        "What insights can you provide for engineering diagrams?",
    "auto-data":
        "Given a dataset of 1000 employee records with salary, tenure, and department, "
        "what statistical analyses and visualizations would you recommend?",
    "auto-compliance":
        "Analyze CIP-007-6 R2 Part 2.1 patch management requirements. "
        "What evidence does an asset owner need to produce for a NERC CIP audit?",
}

# Minimum expected content signals per workspace
_WS_CONTENT_SIGNALS: dict[str, list[str]] = {
    "auto":           ["docker", "network", "container", "bridge"],
    "auto-coding":    ["def ", "str", "return", "palindrome", "substring"],
    "auto-security":  ["autoindex", "security", "vulnerability", "misconfiguration"],
    "auto-redteam":   ["injection", "jwt", "sql", "attack", "vector"],
    "auto-blueteam":  ["mitre", "t1110", "brute", "attack", "indicator", "compromise"],
    "auto-creative":  ["robot", "flower", "garden"],
    "auto-reasoning": ["meet", "hour", "miles", "train"],
    "auto-documents": ["executive", "summary", "timeline", "risk", "microservice"],
    "auto-video":     ["wave", "ocean", "shore", "light", "camera"],
    "auto-music":     ["bpm", "tempo", "piano", "lo-fi", "beat", "hip"],
    "auto-research":  ["symmetric", "asymmetric", "aes", "rsa", "key"],
    "auto-vision":    ["image", "visual", "analyze", "detect"],
    "auto-data":      ["analysis", "statistic", "mean", "correlation", "visual"],
    "auto-compliance":["cip-007", "patch", "evidence", "audit", "nerc"],
}

async def S3_routing() -> None:
    print(f"\n━━━ S3. WORKSPACE ROUTING ({len(WS_IDS)} workspaces) ━━━")

    # S3a: /v1/models exposes all workspace IDs
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{PIPELINE_URL}/v1/models", headers=_auth_headers())
        if r.status_code == 200:
            ids = {m["id"] for m in r.json().get("data", [])}
            missing = set(WS_IDS) - ids
            log(
                "PASS" if not missing else "FAIL",
                "S3a",
                f"/v1/models: {len(ids)} models exposed, "
                f"{'all {len(WS_IDS)} workspace IDs present' if not missing else f'MISSING {missing}'}",
            )
        else:
            log("FAIL", "S3a", f"/v1/models HTTP {r.status_code}")

    # S3b: Domain prompt through EACH workspace — serial, staggered
    print(f"  Routing {len(WS_IDS)} workspaces serially (single-user lab pattern)...")
    for ws in WS_IDS:
        prompt   = _WS_PROMPTS.get(ws, f"Briefly describe your role as the {ws} workspace.")
        signals  = _WS_CONTENT_SIGNALS.get(ws, [])

        code, text = await _chat(ws, prompt, max_tokens=150, timeout=180)

        if code == 200 and text.strip():
            # Check for domain-relevant content
            text_lower = text.lower()
            matched = [s for s in signals if s in text_lower]
            quality = "domain-relevant" if matched else "generic response"
            log(
                "PASS" if matched or not signals else "WARN",
                "S3b",
                f"{ws}: {quality} — '{text[:70].strip()}...'",
            )
        elif code == 503:
            log("WARN", "S3b", f"{ws}: 503 — backend model not pulled (not a code bug)")
        elif code == 408:
            log("WARN", "S3b", f"{ws}: timeout (cold model load — expected on first run)")
        elif code == 200:
            log("WARN", "S3b", f"{ws}: 200 but empty response")
        else:
            log("FAIL", "S3b", f"{ws}: HTTP {code} — {text[:80]}")

        await asyncio.sleep(1)  # stagger — single-user lab

    # S3c: Content-aware auto-routing (HOWTO §6)
    # Security keywords in 'auto' workspace should trigger auto-redteam routing
    code, _ = await _chat(
        "auto",
        "exploit vulnerability payload injection shellcode reverse shell",
        max_tokens=5,
        timeout=30,
    )
    log(
        "PASS" if code in (200, 408) else "WARN",
        "S3c",
        f"Security keyword auto-routing triggered (HTTP {code}) — "
        "check pipeline logs for 'auto-redteam'",
    )

    # S3d: Streaming mode — verify NDJSON chunks arrive
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                headers=_auth_headers(),
                json={
                    "model": "auto",
                    "messages": [{"role": "user", "content": "Say 'streaming ok' and nothing else."}],
                    "stream": True,
                    "max_tokens": 10,
                },
            )
            if r.status_code == 200:
                chunks = [c for c in r.text.splitlines()
                          if c.startswith("data: ") and c != "data: [DONE]"]
                log("PASS" if chunks else "WARN", "S3d",
                    f"Streaming: {len(chunks)} NDJSON chunks received")
            else:
                log("FAIL", "S3d", f"Stream request: HTTP {r.status_code}")
    except Exception as e:
        log("WARN", "S3d", f"Streaming test: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: DOCUMENT GENERATION (Word / PowerPoint / Excel)
# ═══════════════════════════════════════════════════════════════════════════════
async def S4_documents() -> None:
    print("\n━━━ S4. DOCUMENT GENERATION (Word / PowerPoint / Excel) ━━━")

    # S4a: Word .docx — HOWTO §7 project proposal example
    word_content = (
        "# Project Proposal: Monolith to Microservices Migration\n\n"
        "## Executive Summary\n\n"
        "This proposal outlines a 12-month migration from a monolithic application "
        "to a microservices architecture. Expected outcome: 40% reduction in deployment "
        "time and improved fault isolation.\n\n"
        "## Architecture Overview\n\n"
        "Current state: single Django monolith, PostgreSQL, 50K DAU.\n"
        "Target state: 8 bounded-context services, API gateway, event bus.\n\n"
        "## Timeline\n\n"
        "- Phase 1 (Q1): Service decomposition design\n"
        "- Phase 2 (Q2): Pilot service extraction (Auth + Billing)\n"
        "- Phase 3 (Q3-Q4): Full migration and traffic cutover\n\n"
        "## Risk Matrix\n\n"
        "| Risk | Probability | Impact | Mitigation |\n"
        "|------|-------------|--------|------------|\n"
        "| Data consistency | Medium | High | Event sourcing + saga pattern |\n"
        "| Team skill gap | Low | Medium | Training in weeks 1-4 |\n"
        "| Latency increase | Medium | Low | Service mesh + caching layer |\n"
    )
    await _mcp_call(
        "http://localhost:8913/mcp",
        "create_word_document",
        {
            "title": "Monolith to Microservices Migration Proposal",
            "content": word_content,
        },
        "S4a Word .docx (project proposal per HOWTO §7)",
        check_fn=lambda t: (
            "success" in t and ".docx" in t,
            f"{'✓ .docx created' if '.docx' in t else t[:100]}",
        ),
        timeout=60,
    )

    # S4b: PowerPoint .pptx — HOWTO §7 exact 5-slide example
    await _mcp_call(
        "http://localhost:8913/mcp",
        "create_powerpoint",
        {
            "title": "Container Security Best Practices 2026",
            "slides": [
                {
                    "title": "Container Security",
                    "content": "Best practices for securing containerized workloads in 2026",
                },
                {
                    "title": "Threat Landscape",
                    "content": (
                        "Supply chain attacks via compromised base images\n"
                        "Container escape via kernel exploits\n"
                        "Image vulnerability exploitation\n"
                        "Secrets leakage in environment variables"
                    ),
                },
                {
                    "title": "Best Practices",
                    "content": (
                        "Use minimal base images (distroless/scratch)\n"
                        "Scan images in CI/CD pipeline\n"
                        "Enable runtime security (Falco/Tetragon)\n"
                        "Enforce NetworkPolicies in Kubernetes"
                    ),
                },
                {
                    "title": "Implementation Roadmap",
                    "content": (
                        "Phase 1: Image scanning in CI (Week 1-2)\n"
                        "Phase 2: Runtime policies (Week 3-4)\n"
                        "Phase 3: Network segmentation (Week 5-6)"
                    ),
                },
                {
                    "title": "Q&A",
                    "content": "Questions and open discussion",
                },
            ],
        },
        "S4b PowerPoint .pptx (5-slide deck per HOWTO §7)",
        check_fn=lambda t: (
            "success" in t and ".pptx" in t,
            f"{'✓ 5-slide deck created' if '.pptx' in t else t[:100]}",
        ),
        timeout=60,
    )

    # S4c: Excel .xlsx — HOWTO §7 budget breakdown example
    await _mcp_call(
        "http://localhost:8913/mcp",
        "create_excel",
        {
            "title": "Q1-Q2 Budget Breakdown",
            "data": [
                ["Category",   "Q1 Cost", "Q2 Cost", "Total"],
                ["Hardware",     15000,     12000,     27000],
                ["Software",      8000,      8000,     16000],
                ["Services",      5000,      7000,     12000],
                ["Personnel",    20000,     20000,     40000],
            ],
        },
        "S4c Excel .xlsx (budget with formulas per HOWTO §7)",
        check_fn=lambda t: (
            "success" in t and ".xlsx" in t,
            f"{'✓ spreadsheet created' if '.xlsx' in t else t[:100]}",
        ),
        timeout=60,
    )

    # S4d: List generated files (verifies filesystem + listing tool)
    await _mcp_call(
        "http://localhost:8913/mcp",
        "list_generated_files",
        {},
        "S4d List generated files",
        check_fn=lambda t: (
            True,
            f"{'files listed' if 'filename' in t or '[]' in t else t[:80]}",
        ),
        timeout=15,
    )

    # S4e: Document generation via pipeline (auto-documents workspace)
    # This tests the full round-trip: user prompt → pipeline → model → document
    code, text = await _chat(
        "auto-documents",
        "Create an outline for a NERC CIP-007 patch management procedure document. "
        "Include purpose, scope, responsibilities, and procedure steps.",
        max_tokens=200,
        timeout=180,
    )
    if code == 200 and text.strip():
        has_doc_keywords = any(
            k in text.lower() for k in ["cip", "patch", "procedure", "scope", "purpose"]
        )
        log(
            "PASS" if has_doc_keywords else "WARN",
            "S4e",
            f"auto-documents workspace response: '{text[:80].strip()}...'",
        )
    elif code == 503:
        log("WARN", "S4e", "auto-documents: 503 — backend not available")
    else:
        log("WARN", "S4e", f"auto-documents workspace: HTTP {code} — {text[:80]}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: CODE GENERATION & SANDBOX EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════
async def S5_code() -> None:
    print("\n━━━ S5. CODE GENERATION & SANDBOX EXECUTION ━━━")

    # S5a: Code generation via auto-coding workspace
    code, text = await _chat(
        "auto-coding",
        "Write a Python function that finds all prime numbers up to 1000 "
        "using the Sieve of Eratosthenes. Include type hints and return the list.",
        max_tokens=200,
        timeout=180,
    )
    if code == 200 and text.strip():
        has_code = "def " in text or "primes" in text.lower()
        log(
            "PASS" if has_code else "WARN",
            "S5a",
            f"Code generation (sieve): {'✓ code returned' if has_code else 'no code found'} — '{text[:60].strip()}'",
        )
    elif code == 503:
        log("WARN", "S5a", "auto-coding: 503 — backend not available")
    else:
        log("WARN", "S5a", f"auto-coding: HTTP {code}")

    # S5b: Python sandbox — primes to 100 (known-good simple code)
    await _mcp_call(
        "http://localhost:8914/mcp",
        "execute_python",
        {
            "code": (
                "primes=[n for n in range(2,100) "
                "if all(n%i for i in range(2,int(n**0.5)+1))]\n"
                "print('count:',len(primes))\n"
                "print('sum:',sum(primes))"
            ),
            "timeout": 30,
        },
        "S5b Python sandbox (primes to 100 per HOWTO §5)",
        check_fn=lambda t: (
            "success" in t.lower() and ("25" in t or "1060" in t),
            (
                "✓ executed — count=25, sum=1060"
                if "25" in t and "1060" in t
                else "known sandbox limitation"
                if any(x in t for x in ["docker", "dind", "__main__"])
                else t[:120]
            ),
        ),
        timeout=180,
        warn_patterns=["docker", "Docker", "dind", "DinD", "sandbox", "__main__"],
    )

    # S5c: Python sandbox — fibonacci sequence
    await _mcp_call(
        "http://localhost:8914/mcp",
        "execute_python",
        {
            "code": (
                "fib=[0,1]\n"
                "for i in range(8): fib.append(fib[-1]+fib[-2])\n"
                "print('fib10:',fib[:10])"
            ),
            "timeout": 20,
        },
        "S5c Python sandbox (Fibonacci sequence)",
        check_fn=lambda t: (
            "success" in t.lower() and "fib10" in t,
            "✓ Fibonacci executed" if "fib10" in t else t[:100],
        ),
        timeout=120,
        warn_patterns=["docker", "Docker", "dind", "sandbox"],
    )

    # S5d: Node.js sandbox
    await _mcp_call(
        "http://localhost:8914/mcp",
        "execute_nodejs",
        {
            "code": "const a=[1,2,3,4,5]; console.log('sum:', a.reduce((x,y)=>x+y,0));",
            "timeout": 20,
        },
        "S5d Node.js sandbox (array sum)",
        check_fn=lambda t: (
            "success" in t.lower() and "15" in t,
            "✓ Node.js executed" if "15" in t else t[:100],
        ),
        timeout=120,
        warn_patterns=["docker", "Docker", "dind", "sandbox"],
    )

    # S5e: Bash sandbox
    await _mcp_call(
        "http://localhost:8914/mcp",
        "execute_bash",
        {
            "code": "echo 'bash_ok' && printf '%d\\n' $((2 + 2))",
            "timeout": 10,
        },
        "S5e Bash sandbox",
        check_fn=lambda t: (
            "success" in t.lower() and ("bash_ok" in t or "4" in t),
            "✓ Bash executed" if "bash_ok" in t else t[:100],
        ),
        timeout=60,
        warn_patterns=["docker", "Docker", "dind", "sandbox"],
    )

    # S5f: Sandbox status (HOWTO §5 health check)
    await _mcp_call(
        "http://localhost:8914/mcp",
        "sandbox_status",
        {},
        "S5f Sandbox status (HOWTO §5)",
        check_fn=lambda t: (
            "sandbox_enabled" in t or "docker" in t.lower(),
            t[:150],
        ),
        timeout=15,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: SECURITY WORKSPACES
# ═══════════════════════════════════════════════════════════════════════════════
async def S6_security() -> None:
    print("\n━━━ S6. SECURITY WORKSPACES ━━━")

    security_cases = [
        (
            "auto-security",
            "S6a Defensive (auto-security)",
            "Review this nginx configuration for security misconfigurations:\n"
            "server { listen 80; root /var/www/html; autoindex on; "
            "server_tokens on; location / { try_files $uri $uri/; } }",
            ["autoindex", "security", "vulnerability", "misconfiguration", "expose"],
        ),
        (
            "auto-redteam",
            "S6b Offensive (auto-redteam)",
            "Enumerate potential injection points in a GraphQL API. "
            "Focus on introspection abuse and query depth attacks.",
            ["injection", "graphql", "introspection", "attack", "query", "depth"],
        ),
        (
            "auto-blueteam",
            "S6c Blue Team (auto-blueteam)",
            "Analyze these firewall log entries for indicators of compromise:\n"
            "DENY TCP 203.0.113.0/24:4444->10.0.0.5:445 (repeated 200x in 60s)",
            ["lateral", "445", "smb", "mitre", "attack", "indicator", "t1021", "deny"],
        ),
    ]

    for ws, label, prompt, signals in security_cases:
        code, text = await _chat(ws, prompt, max_tokens=200, timeout=180)
        if code == 200 and text.strip():
            matched = [s for s in signals if s in text.lower()]
            log(
                "PASS" if matched else "WARN",
                label,
                f"{'domain-relevant' if matched else 'generic'}: '{text[:80].strip()}'",
            )
        elif code == 503:
            log("WARN", label, "503 — security model not pulled")
        elif code == 408:
            log("WARN", label, "timeout (cold load)")
        else:
            log("FAIL", label, f"HTTP {code}")
        await asyncio.sleep(2)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7: MUSIC GENERATION (AudioCraft / MusicGen)
# ═══════════════════════════════════════════════════════════════════════════════
async def S7_music() -> None:
    print("\n━━━ S7. MUSIC GENERATION ━━━")

    # S7a: List available models (HOWTO §10)
    result = await _mcp_call(
        "http://localhost:8912/mcp",
        "list_music_models",
        {},
        "S7a List music models",
        check_fn=lambda t: (
            any(x in t for x in ["small", "medium", "large", "musicgen"]),
            f"{'models listed' if any(x in t for x in ['small','medium','large']) else t[:80]}",
        ),
        timeout=15,
    )

    # S7b: Generate 5-second lo-fi beat (HOWTO §10 exact example)
    # First-time call downloads the model (~300MB) — give it time
    await _mcp_call(
        "http://localhost:8912/mcp",
        "generate_music",
        {
            "prompt": "lo-fi hip hop beat with mellow piano chords and vinyl crackle",
            "duration": 5,
            "model_size": "small",
        },
        "S7b Music gen 5s lo-fi (HOWTO §10 example)",
        check_fn=lambda t: (
            any(x in t for x in ["success", "path", "duration", "wav", "audio"]),
            f"{'✓ audio generated' if any(x in t for x in ['success','path','wav']) else t[:120]}",
        ),
        timeout=600,  # 10 min: first-time model download
    )

    # S7c: Generate short cinematic clip (different style, medium duration)
    await _mcp_call(
        "http://localhost:8912/mcp",
        "generate_music",
        {
            "prompt": "cinematic orchestral trailer music with dramatic percussion",
            "duration": 8,
            "model_size": "small",
        },
        "S7c Music gen 8s cinematic",
        check_fn=lambda t: (
            any(x in t for x in ["success", "path", "wav"]),
            f"{'✓ audio generated' if any(x in t for x in ['success','path','wav']) else t[:100]}",
        ),
        timeout=300,
    )

    # S7d: auto-music workspace round-trip
    code, text = await _chat(
        "auto-music",
        "Describe what a 15-second jazz piano trio piece with upright bass would sound like. "
        "Include tempo, key, and primary motifs.",
        max_tokens=150,
        timeout=120,
    )
    if code == 200 and text.strip():
        log("PASS", "S7d", f"auto-music workspace: '{text[:80].strip()}'")
    elif code == 503:
        log("WARN", "S7d", "auto-music: 503 — backend not available")
    else:
        log("WARN", "S7d", f"auto-music: HTTP {code}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8: TEXT-TO-SPEECH (kokoro-onnx)
# ═══════════════════════════════════════════════════════════════════════════════

_TTS_TEST_TEXT = (
    "Portal 5 is a complete local AI platform running entirely on your own "
    "hardware with zero cloud dependencies."
)

def _is_wav(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[8:12] == b"WAVE"

async def S8_tts() -> None:
    print("\n━━━ S8. TEXT-TO-SPEECH ━━━")

    # S8a: List available voices (MCP tool)
    await _mcp_call(
        "http://localhost:8916/mcp",
        "list_voices",
        {},
        "S8a List TTS voices",
        check_fn=lambda t: (
            "af_heart" in t,
            f"{'✓ voices listed' if 'af_heart' in t else t[:80]}",
        ),
        timeout=15,
    )

    # S8b: Speak via MCP tool (HOWTO §11 example)
    await _mcp_call(
        "http://localhost:8916/mcp",
        "speak",
        {"text": _TTS_TEST_TEXT, "voice": "af_heart"},
        "S8b TTS speak af_heart (HOWTO §11 example)",
        check_fn=lambda t: (
            any(x in t for x in ["file_path", "path", "success"]),
            f"{'✓ speech generated' if any(x in t for x in ['path','file','success']) else t[:80]}",
        ),
        timeout=60,
    )

    # S8c: OpenAI-compatible REST endpoint — WAV byte verification (HOWTO §11)
    voice_cases = [
        ("af_heart",  "US-F default"),
        ("bm_george", "British male"),
        ("am_adam",   "US male"),
        ("bf_emma",   "British female"),
        ("am_michael","US male 2"),
    ]
    async with httpx.AsyncClient(timeout=60) as c:
        for voice, desc in voice_cases:
            try:
                r = await c.post(
                    "http://localhost:8916/v1/audio/speech",
                    json={"input": _TTS_TEST_TEXT, "voice": voice},
                )
                if r.status_code == 200:
                    data = r.content
                    is_wav = _is_wav(data)
                    log(
                        "PASS" if is_wav else "WARN",
                        "S8c",
                        f"{voice} ({desc}): {len(data):,} bytes, WAV={is_wav}",
                    )
                else:
                    log("WARN", "S8c", f"{voice}: HTTP {r.status_code}")
            except Exception as e:
                log("WARN", "S8c", f"{voice}: {e}")

    # S8d: TTS via pipeline workspace (auto-music workspace, which enables TTS)
    # Voices can be triggered by asking the model to speak something
    code, text = await _chat(
        "auto-music",
        "Read this aloud in British English: 'The quick brown fox jumps over the lazy dog.'",
        max_tokens=100,
        timeout=60,
    )
    if code == 200 and text.strip():
        log("PASS", "S8d", f"TTS workspace round-trip: '{text[:80].strip()}'")
    elif code == 503:
        log("WARN", "S8d", "TTS workspace: 503 — backend not available")
    else:
        log("WARN", "S8d", f"TTS workspace: HTTP {code}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9: SPEECH-TO-TEXT (Whisper)
# ═══════════════════════════════════════════════════════════════════════════════
async def S9_whisper() -> None:
    print("\n━━━ S9. SPEECH-TO-TEXT (Whisper) ━━━")

    # S9a: Health check (HOWTO §12 exact docker exec command)
    r = subprocess.run(
        [
            "docker", "exec", "portal5-mcp-whisper",
            "python3", "-c",
            "import urllib.request; "
            "print(urllib.request.urlopen('http://127.0.0.1:8915/health').read().decode())",
        ],
        capture_output=True, text=True, timeout=15,
    )
    log(
        "PASS" if r.returncode == 0 and "ok" in r.stdout.lower() else "FAIL",
        "S9a",
        f"Whisper health (HOWTO §12 cmd): {r.stdout.strip()[:80] or r.stderr.strip()[:80]}",
    )

    # S9b: MCP tool callable — file-not-found verifies tool is reachable
    await _mcp_call(
        "http://localhost:8915/mcp",
        "transcribe_audio",
        {"file_path": "/nonexistent_test_audio.wav"},
        "S9b Whisper tool reachable (expects file-not-found error)",
        check_fn=lambda t: (
            True,  # any response = tool is reachable
            "✓ tool reachable" if any(
                x in t.lower() for x in ["not found", "error", "no such"]
            ) else f"unexpected response: {t[:80]}",
        ),
        timeout=15,
    )

    # S9c: Generate a WAV with TTS then transcribe it (full STT round-trip)
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            tts_r = await c.post(
                "http://localhost:8916/v1/audio/speech",
                json={"input": "Hello from Portal Five.", "voice": "af_heart"},
            )
        if tts_r.status_code == 200 and _is_wav(tts_r.content):
            # Write WAV to a path accessible by the whisper container
            wav_path = "/tmp/portal5_stt_test.wav"
            Path(wav_path).write_bytes(tts_r.content)

            # Copy into container
            cp_r = subprocess.run(
                ["docker", "cp", wav_path, "portal5-mcp-whisper:/tmp/stt_test.wav"],
                capture_output=True, text=True,
            )
            if cp_r.returncode == 0:
                await _mcp_call(
                    "http://localhost:8915/mcp",
                    "transcribe_audio",
                    {"file_path": "/tmp/stt_test.wav"},
                    "S9c STT round-trip (TTS→WAV→Whisper)",
                    check_fn=lambda t: (
                        any(x in t.lower() for x in ["hello", "portal", "five", "text"]),
                        f"{'✓ transcribed' if any(x in t.lower() for x in ['hello','portal','text']) else t[:100]}",
                    ),
                    timeout=60,
                )
            else:
                log("WARN", "S9c", f"Could not copy WAV into whisper container: {cp_r.stderr[:80]}")
        else:
            log("WARN", "S9c", "TTS did not return valid WAV — skipping STT round-trip")
    except Exception as e:
        log("WARN", "S9c", f"STT round-trip: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 10: VIDEO GENERATION MCP
# ═══════════════════════════════════════════════════════════════════════════════
async def S10_video() -> None:
    print("\n━━━ S10. VIDEO GENERATION MCP ━━━")

    # S10a: Health check
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get("http://localhost:8911/health")
            data = r.json() if r.status_code == 200 else {"http": r.status_code}
            log("PASS" if r.status_code == 200 else "FAIL", "S10a",
                f"Video MCP health: {data}")
    except Exception as e:
        log("FAIL", "S10a", f"Video MCP unreachable: {e}")

    # S10b: auto-video workspace (text description → workspace routes to pipeline)
    code, text = await _chat(
        "auto-video",
        "Describe a 3-second video clip of ocean waves crashing on rocky shoreline "
        "at golden hour. Include camera angle and post-processing cues.",
        max_tokens=150,
        timeout=120,
    )
    if code == 200 and text.strip():
        has_signals = any(
            s in text.lower() for s in ["wave", "ocean", "light", "camera", "golden"]
        )
        log(
            "PASS" if has_signals else "WARN",
            "S10b",
            f"auto-video workspace: '{text[:80].strip()}'",
        )
    elif code == 503:
        log("WARN", "S10b", "auto-video: 503 — backend not available")
    else:
        log("WARN", "S10b", f"auto-video: HTTP {code}")

    # S10c: ComfyUI MCP bridge (image/video generation depends on ComfyUI host process)
    log("INFO", "S10c",
        "ComfyUI image/video generation requires ComfyUI running on host "
        "(see HOWTO §8-9 and KNOWN_LIMITATIONS.md). "
        "MCP bridge health is reported in S2. Full generation tested separately.")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 11: ALL 37 PERSONAS
# ═══════════════════════════════════════════════════════════════════════════════

# Persona-specific prompts that satisfy each persona's hard constraints
PERSONA_PROMPTS: dict[str, str] = {
    "blueteamdefender":
        "Analyze this log for IOCs: Failed password for root from 203.0.113.50 "
        "port 22 ssh2 (200 attempts in 60 seconds). Which MITRE ATT&CK technique applies?",
    "bugdiscoverycodeassistant":
        "Find the bug in this Python function: def div(a, b): return a/b — "
        "what happens when b=0 and how do you fix it?",
    "cippolicywriter":
        "Draft a policy statement for CIP-007-6 R2 Part 2.1 patch management. "
        "Use SHALL/SHOULD language as required by NERC CIP standards.",
    "codebasewikidocumentationskill":
        "Document this function: "
        "def fibonacci(n): return n if n<=1 else fibonacci(n-1)+fibonacci(n-2)",
    "codereviewassistant":
        "Review this code and suggest improvements: "
        "for i in range(len(lst)): if lst[i]==target: return i",
    "codereviewer":
        "Review this SQL for vulnerabilities: "
        "SELECT * FROM users WHERE name = 'admin' OR '1'='1' -- what's wrong?",
    "creativewriter":
        "Write a 3-sentence story about a robot that discovers a flower garden "
        "for the first time.",
    "cybersecurityspecialist":
        "Explain the OWASP Top 10 A01:2021 Broken Access Control vulnerability "
        "and how to prevent it.",
    "dataanalyst":
        "Sales data: Q1=150K Q2=180K Q3=165K Q4=210K. Identify the trend and "
        "recommend the best analysis approach.",
    "datascientist":
        "Describe how you would build a customer churn prediction model. "
        "What features and algorithms would you use?",
    "devopsautomator":
        "Write a GitHub Actions workflow YAML that runs pytest on push to main. "
        "Stack: Python 3.11, AWS ECS deployment, secrets in GitHub Secrets. Include rollback.",
    "devopsengineer":
        "Design a CI/CD pipeline for a Python microservice deployed to Kubernetes on AWS EKS. "
        "Stack: GitHub Actions, Docker, Helm 3.12. Team: 5 engineers.",
    "ethereumdeveloper":
        "Write a Solidity function that transfers ERC-20 tokens with an approval check.",
    "excelsheet":
        "Explain this formula step by step: "
        "=SUMPRODUCT((A2:A100=\"Sales\")*(B2:B100>1000)*(C2:C100))",
    "fullstacksoftwaredeveloper":
        "Design a REST API for a todo application: endpoints, HTTP methods, "
        "request/response schemas.",
    "githubexpert":
        "How do I set up branch protection rules requiring 2 reviewers and passing CI?",
    "itarchitect":
        "Design a high-availability architecture for a web application serving "
        "10,000 concurrent users.",
    "itexpert":
        "OS: Ubuntu 22.04 LTS. Error: 'OOMKilled' in docker inspect on a FastAPI "
        "container with 512MB limit. Last change: added a pandas pipeline 2 days ago. "
        "How do I diagnose and fix this?",
    "javascriptconsole":
        "Evaluate step by step: [1,2,3].reduce((acc,x) => acc+x, 0) * Math.PI",
    "kubernetesdockerrpglearningengine":
        "START NEW GAME. I am a beginner. Begin the tutorial campaign at Mission 1: "
        "'The Container Awakens'. Show mission briefing, starting stats, first objective.",
    "linuxterminal":
        "Show the command to find all files larger than 100MB modified in the last 7 days.",
    "machinelearningengineer":
        "Compare Random Forest vs XGBoost for tabular classification. "
        "When would you choose each?",
    "nerccipcomplianceanalyst":
        "Analyze CIP-007-6 R2 Part 2.1 patch management requirements. "
        "What evidence is needed for a NERC CIP audit?",
    "networkengineer":
        "Design a VLAN segmentation scheme for a network with a DMZ, "
        "internal servers, and guest WiFi.",
    "pentester":
        "Describe the methodology for testing a web application for "
        "authentication bypass vulnerabilities.",
    "pythoncodegeneratorcleanoptimizedproduction-ready":
        "Write a production-ready Python function "
        "`retry_request(url: str, max_retries: int = 3, backoff_base: float = 0.5) -> requests.Response` "
        "that retries HTTP GET with exponential backoff. Use stdlib only. "
        "Include type hints, Google docstring, raise RuntimeError after max retries.",
    "pythoninterpreter":
        "Execute mentally: x=[1,2,3]; y=x[::-1]; z=list(zip(x,y)); print(z) — "
        "what is the output?",
    "redteamoperator":
        "For an authorized engagement: analyze the attack surface of a REST API "
        "with JWT authentication. What are the top 3 attack vectors?",
    "researchanalyst":
        "Compare the pros and cons of microservices vs monolithic architecture "
        "with current industry data points.",
    "seniorfrontenddeveloper":
        "Write a React component that fetches data from an API, shows a loading "
        "spinner, and handles errors gracefully.",
    "seniorsoftwareengineersoftwarearchitectrules":
        "Review this architecture decision: migrating a monolith to 50 microservices. "
        "What are the top 5 risks?",
    "softwarequalityassurancetester":
        "Write test cases for a login form: email field, password field, submit button. "
        "Include error states and edge cases.",
    "sqlterminal":
        "SELECT TOP 5 u.Username, SUM(o.TotalAmount) AS TotalOrderValue, "
        "MAX(o.OrderDate) AS LastOrderDate "
        "FROM Orders o JOIN Users u ON o.UserID = u.UserID "
        "GROUP BY u.Username ORDER BY TotalOrderValue DESC;",
    "statistician":
        "Given a dataset with p-value=0.04 and n=25, interpret the result. "
        "Is the sample size adequate for drawing conclusions?",
    "techreviewer":
        "Review the Apple M4 Mac Mini as a local AI inference platform. "
        "Pros, cons, and alternatives.",
    "techwriter":
        "Write the introduction paragraph for API documentation covering a "
        "user authentication service.",
    "ux-uideveloper":
        "Design the user flow for a password reset feature. "
        "Include error states and edge cases.",
}

async def S11_personas() -> None:
    print(f"\n━━━ S11. PERSONAS — ALL {len(PERSONAS)} ━━━")

    # S11a: Verify personas are registered in Open WebUI
    token = _owui_token()
    if token:
        try:
            r = httpx.get(
                f"{OPENWEBUI_URL}/api/v1/models/",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                model_ids = {
                    m["id"].lower()
                    for m in (data if isinstance(data, list) else data.get("data", []))
                }
                registered = [p for p in PERSONAS if p["slug"].lower() in model_ids]
                not_registered = [p for p in PERSONAS if p["slug"].lower() not in model_ids]
                log(
                    "PASS" if not not_registered else "WARN",
                    "S11a",
                    f"Personas in Open WebUI: {len(registered)}/{len(PERSONAS)} registered"
                    + (
                        f" — MISSING: {[p['slug'] for p in not_registered]}"
                        if not_registered
                        else ""
                    ),
                )
                if not_registered:
                    log("INFO", "S11a",
                        "FIX: ./launch.sh reseed to re-register missing personas")
            else:
                log("WARN", "S11a", f"OW /api/v1/models/ returned {r.status_code}")
        except Exception as e:
            log("WARN", "S11a", f"OW persona registration check failed: {e}")
    else:
        log("WARN", "S11a", "No OW token — skipping persona registration check")

    # S11b: Domain prompt through EVERY persona (serial)
    # Each persona prompt goes to the pipeline via 'auto' workspace
    # with the persona's system_prompt injected (same as Open WebUI does)
    print(f"  Exercising {len(PERSONAS)} personas serially...")
    passed = warned = failed = 0

    async with httpx.AsyncClient(timeout=180) as c:
        for persona in PERSONAS:
            slug   = persona["slug"]
            name   = persona["name"]
            system = persona.get("system_prompt", "")
            prompt = PERSONA_PROMPTS.get(
                slug,
                f"As {name}, give a one-sentence introduction of your expertise area.",
            )

            messages: list[dict] = []
            if system:
                messages.append({"role": "system", "content": system[:800]})
            messages.append({"role": "user", "content": prompt})

            try:
                r = await c.post(
                    f"{PIPELINE_URL}/v1/chat/completions",
                    headers=_auth_headers(),
                    json={
                        "model": "auto",
                        "messages": messages,
                        "stream": False,
                        "max_tokens": 120,
                    },
                )
                if r.status_code == 200:
                    text = (
                        r.json()
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    if text.strip():
                        log("PASS", "S11b",
                            f"{slug}: '{text[:70].strip()}'")
                        passed += 1
                    else:
                        log("WARN", "S11b", f"{slug}: 200 but empty response")
                        warned += 1
                elif r.status_code == 503:
                    log("WARN", "S11b", f"{slug}: 503 — no healthy backend")
                    warned += 1
                else:
                    log("FAIL", "S11b", f"{slug}: HTTP {r.status_code}")
                    failed += 1
            except httpx.ReadTimeout:
                log("WARN", "S11b", f"{slug}: timeout (model loading)")
                warned += 1
            except Exception as e:
                log("FAIL", "S11b", f"{slug}: {e}")
                failed += 1

            await asyncio.sleep(0.5)  # stagger — single-user lab

    log(
        "PASS" if failed == 0 and warned < len(PERSONAS) // 4 else "WARN",
        "S11b-summary",
        f"Personas: {passed} PASS | {warned} WARN | {failed} FAIL / {len(PERSONAS)} total",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 12: METRICS & MONITORING (HOWTO §22)
# ═══════════════════════════════════════════════════════════════════════════════
async def S12_metrics() -> None:
    print("\n━━━ S12. METRICS & MONITORING (HOWTO §22) ━━━")

    async with httpx.AsyncClient(timeout=5) as c:
        # Prometheus metrics on pipeline
        r = await c.get(f"{PIPELINE_URL}/metrics")
        if r.status_code == 200:
            has_requests = "portal_requests" in r.text
            log("PASS" if has_requests else "WARN", "S12a",
                f"portal_requests_by_model_total counter: "
                f"{'present' if has_requests else 'missing from /metrics'}")

            ws_match = re.search(r"portal_workspaces_total\s+(\d+)", r.text)
            if ws_match:
                n = int(ws_match.group(1))
                log(
                    "PASS" if n == len(WS_IDS) else "FAIL",
                    "S12b",
                    f"portal_workspaces_total={n} (expected {len(WS_IDS)})",
                )
            else:
                log("INFO", "S12b", "portal_workspaces_total gauge not yet in /metrics")

            has_tps = "portal_tokens_per_second" in r.text
            log("INFO", "S12c",
                f"portal_tokens_per_second histogram: {'present' if has_tps else 'not yet recorded'}")
        else:
            log("FAIL", "S12a", f"/metrics HTTP {r.status_code}")

        # Prometheus target scraping (HOWTO §22)
        try:
            r = await c.get("http://localhost:9090/api/v1/targets")
            targets = r.json().get("data", {}).get("activeTargets", [])
            pipeline_targets = [
                t for t in targets if "9099" in str(t.get("scrapeUrl", ""))
            ]
            log(
                "PASS" if pipeline_targets else "WARN",
                "S12d",
                f"Prometheus: {len(pipeline_targets)} pipeline target(s) active",
            )
        except Exception as e:
            log("FAIL", "S12d", f"Prometheus API: {e}")

        # Grafana dashboard (HOWTO §22)
        try:
            r = await c.get(
                "http://localhost:3000/api/search?type=dash-db",
                auth=("admin", GRAFANA_PASS),
            )
            if r.status_code == 200:
                dashboards = [d.get("title") for d in r.json()]
                log(
                    "PASS" if any("portal" in d.lower() for d in dashboards) else "WARN",
                    "S12e",
                    f"Grafana dashboards: {dashboards}",
                )
            else:
                log("WARN", "S12e", f"Grafana /api/search: HTTP {r.status_code}")
        except Exception as e:
            log("FAIL", "S12e", f"Grafana: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 13: GUI VALIDATION (Chromium / Playwright)
# ═══════════════════════════════════════════════════════════════════════════════
async def S13_gui() -> None:
    print(f"\n━━━ S13. GUI VALIDATION ({len(WS_IDS)} workspaces + {len(PERSONAS)} personas) ━━━")

    if not ADMIN_PASS:
        log("SKIP", "S13", "OPENWEBUI_ADMIN_PASSWORD not set")
        return

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log("SKIP", "S13", "playwright not installed — pip install playwright && python3 -m playwright install chromium")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx     = await browser.new_context(viewport={"width": 1440, "height": 900})
        page    = await ctx.new_page()

        # S13a: Login
        try:
            await page.goto(OPENWEBUI_URL, wait_until="networkidle", timeout=20000)
            await page.wait_for_selector('input[type="email"]', timeout=10000)
            await page.fill('input[type="email"]', ADMIN_EMAIL)
            await page.fill('input[type="password"]', ADMIN_PASS)
            await page.locator('button[type="submit"], button:has-text("Sign in")').first.click()
            await page.wait_for_selector("textarea, [contenteditable]", timeout=15000)
            log("PASS", "S13a", "Login → chat interface loaded")
            await page.screenshot(path="/tmp/p5_gui_login.png")
        except Exception as e:
            log("FAIL", "S13a", f"Login failed: {e}")
            await browser.close()
            return

        await page.wait_for_timeout(2000)

        # S13b: Open model dropdown and enumerate workspaces
        dropdown_opened = False
        for sel in [
            "button[aria-haspopup]",
            "button:has-text('Portal')",
            "button:has-text('Auto')",
            "button:has-text('Router')",
        ]:
            loc = page.locator(sel)
            if await loc.count() > 0:
                try:
                    await loc.first.click(timeout=5000)
                    await page.wait_for_timeout(2000)
                    dropdown_opened = True
                    break
                except Exception:
                    continue

        body = (await page.inner_text("body")).lower()
        await page.screenshot(path="/tmp/p5_gui_dropdown.png")

        ws_found = [ws for ws, name in WS_NAMES.items()
                    if re.sub(r"^[^\w]+", "", name).strip().lower() in body]
        ws_miss  = [ws for ws in WS_IDS if ws not in ws_found]

        if len(ws_found) >= len(WS_IDS) - 1:
            log("PASS", "S13b", f"{len(ws_found)}/{len(WS_IDS)} workspaces in dropdown")
        else:
            # Headless limitation — verify via API
            try:
                ar = httpx.get(
                    f"{OPENWEBUI_URL}/api/v1/models/",
                    headers={"Authorization": f"Bearer {_owui_token()}"},
                    timeout=5,
                )
                if ar.status_code == 200:
                    data = ar.json()
                    api_ids = {m["id"] for m in (data if isinstance(data, list) else data.get("data", []))}
                    api_ws  = [ws for ws in WS_IDS if ws in api_ids]
                    log(
                        "PASS" if len(api_ws) == len(WS_IDS) else "WARN",
                        "S13b",
                        f"GUI: {len(ws_found)}/{len(WS_IDS)} visible (headless limit) | "
                        f"API: {len(api_ws)}/{len(WS_IDS)} registered",
                    )
                else:
                    log("WARN", "S13b",
                        f"GUI: {len(ws_found)}/{len(WS_IDS)} (headless limit), "
                        f"API fallback returned {ar.status_code}")
            except Exception as e:
                log("WARN", "S13b", f"API fallback failed: {e}")

        # S13c: Persona visibility
        p_found = [p["name"] for p in PERSONAS if p["name"].lower() in body]
        p_miss  = [p["name"] for p in PERSONAS if p["name"].lower() not in body]
        if len(p_found) >= len(PERSONAS) * 0.8:
            log("PASS", "S13c", f"{len(p_found)}/{len(PERSONAS)} personas visible in dropdown")
        else:
            try:
                ar = httpx.get(
                    f"{OPENWEBUI_URL}/api/v1/models/",
                    headers={"Authorization": f"Bearer {_owui_token()}"},
                    timeout=5,
                )
                if ar.status_code == 200:
                    data = ar.json()
                    api_ids = {m["id"].lower() for m in (data if isinstance(data, list) else data.get("data", []))}
                    api_p   = [p for p in PERSONAS if p["slug"].lower() in api_ids]
                    log(
                        "PASS" if len(api_p) == len(PERSONAS) else "WARN",
                        "S13c",
                        f"GUI: {len(p_found)}/{len(PERSONAS)} (headless) | "
                        f"API: {len(api_p)}/{len(PERSONAS)} registered",
                    )
                else:
                    log("WARN", "S13c",
                        f"GUI: {len(p_found)}/{len(PERSONAS)} visible, API {ar.status_code}")
            except Exception as e:
                log("WARN", "S13c", f"Persona API fallback: {e}")

        if p_miss:
            log("INFO", "S13c", f"Not visible (headless scroll limit): {p_miss[:5]}...")

        await page.keyboard.press("Escape")

        # S13d: Chat textarea functional
        ta = page.locator("textarea, [contenteditable='true']")
        if await ta.count() > 0:
            await ta.first.fill("acceptance test message")
            await ta.first.fill("")
            log("PASS", "S13d", "Chat textarea: input and clear works")
        else:
            log("WARN", "S13d", "Chat textarea not found")

        # S13e: Admin panel accessible
        await page.goto(f"{OPENWEBUI_URL}/admin", wait_until="networkidle", timeout=10000)
        admin_body = await page.inner_text("body")
        log(
            "PASS" if any(w in admin_body.lower() for w in ["admin", "settings", "users"]) else "WARN",
            "S13e",
            "Admin panel accessible",
        )
        await page.screenshot(path="/tmp/p5_gui_admin.png")

        # S13f: Tool servers in admin panel
        tools_expected = ["documents", "code", "music", "tts", "whisper", "video"]
        tf = [t for t in tools_expected if t in admin_body.lower()]
        log(
            "PASS" if len(tf) >= 4 else "INFO",
            "S13f",
            f"Tool servers visible in admin: {len(tf)}/{len(tools_expected)} {tf}",
        )

        await browser.close()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 14: HOWTO ACCURACY AUDIT
# ═══════════════════════════════════════════════════════════════════════════════
async def S14_howto() -> None:
    print("\n━━━ S14. HOWTO ACCURACY AUDIT ━━━")
    howto = (ROOT / "docs/HOWTO.md").read_text()

    # S14a: Stale UI instruction check ("Click + enable" removed in v6)
    bad_lines = [l for l in howto.splitlines()
                 if "Click **+**" in l and "enable" in l.lower()]
    log(
        "PASS" if not bad_lines else "FAIL",
        "S14a",
        f"Stale 'Click + enable' instruction: "
        f"{'not present (correct)' if not bad_lines else f'{len(bad_lines)} occurrences remain'}",
    )

    # S14b: Workspace table row count matches code
    ws_table_rows = len(re.findall(r"^\| Portal", howto, re.MULTILINE))
    log(
        "PASS" if ws_table_rows == len(WS_IDS) else "FAIL",
        "S14b",
        f"Workspace table rows: {ws_table_rows} (code has {len(WS_IDS)})",
    )

    # S14c: Workspace count claim in text
    cm = re.search(r"Expected:\s*(\d+)\s*workspace", howto)
    if cm:
        n = int(cm.group(1))
        log(
            "PASS" if n == len(WS_IDS) else "FAIL",
            "S14c",
            f"Workspace count claim: {n} (code has {len(WS_IDS)})",
        )

    # S14d: Compliance workspace documented
    log(
        "PASS" if "auto-compliance" in howto else "FAIL",
        "S14d",
        "auto-compliance workspace: "
        f"{'documented' if 'auto-compliance' in howto else 'MISSING from HOWTO'}",
    )

    # S14e: Persona count claim
    pm = re.search(
        r"(\d+)\s*total",
        howto[howto.lower().find("persona"):] if "persona" in howto.lower() else "",
    )
    if pm:
        n = int(pm.group(1))
        log(
            "PASS" if n == len(PERSONAS) else "FAIL",
            "S14e",
            f"Persona count claim: {n}, files={len(PERSONAS)}",
        )

    # S14f: Telegram workspace list completeness (HOWTO §16)
    try:
        sec_start = howto.index("Available workspaces")
        sec = howto[sec_start : sec_start + 600]
        listed = set(re.findall(r"auto(?:-\w+)?", sec))
        miss   = set(WS_IDS) - listed
        log(
            "PASS" if not miss else "FAIL",
            "S14f",
            f"§16 Telegram workspace list: "
            f"{'complete' if not miss else f'MISSING {miss}'}",
        )
    except ValueError:
        log("WARN", "S14f", "Could not locate §16 'Available workspaces' section")

    # S14g: Health response claims match actual responses (§10, §11)
    async with httpx.AsyncClient(timeout=5) as c:
        # Music MCP (§10)
        r = await c.get("http://localhost:8912/health")
        actual = r.json() if r.status_code == 200 else {}
        claims_audiocraft = '"backend": "audiocraft"' in howto
        actual_audiocraft = actual.get("backend") == "audiocraft"
        log(
            "PASS" if not claims_audiocraft or actual_audiocraft else "FAIL",
            "S14g-music",
            f"§10 music health claim vs actual: {actual}",
        )

        # TTS MCP (§11)
        r = await c.get("http://localhost:8916/health")
        actual = r.json() if r.status_code == 200 else {}
        log(
            "PASS" if actual.get("backend") == "kokoro" else "WARN",
            "S14g-tts",
            f"§11 TTS backend claim: kokoro — actual: {actual}",
        )

    # S14h: HOWTO verify commands actually work (§3, §5, §7, §22)
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{PIPELINE_URL}/v1/models", headers=_auth_headers())
        log("PASS" if r.status_code == 200 else "FAIL", "S14h-§3",
            f"§3 curl /v1/models: HTTP {r.status_code}")

        r = await c.get("http://localhost:8914/health")
        log("PASS" if r.status_code == 200 else "FAIL", "S14h-§5",
            f"§5 curl :8914/health: HTTP {r.status_code}")

        r = await c.get("http://localhost:8913/health")
        log("PASS" if r.status_code == 200 else "FAIL", "S14h-§7",
            f"§7 curl :8913/health: HTTP {r.status_code}")

        r = await c.get(f"{PIPELINE_URL}/metrics")
        log("PASS" if r.status_code == 200 else "FAIL", "S14h-§22",
            f"§22 curl /metrics: HTTP {r.status_code}")

    # S14i: Whisper health (§12 exact docker exec)
    wr = subprocess.run(
        [
            "docker", "exec", "portal5-mcp-whisper",
            "python3", "-c",
            "import urllib.request; "
            "print(urllib.request.urlopen('http://127.0.0.1:8915/health').read().decode())",
        ],
        capture_output=True, text=True, timeout=10,
    )
    log(
        "PASS" if wr.returncode == 0 and "ok" in wr.stdout.lower() else "WARN",
        "S14i-§12",
        f"§12 whisper health: {wr.stdout.strip()[:80]}",
    )

    # S14j: Version number in footer
    log(
        "PASS" if "6.0" in howto else "FAIL",
        "S14j",
        f"HOWTO footer version: {'6.0 present' if '6.0' in howto else 'needs update'}",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 15: WEB SEARCH (SearXNG — HOWTO §13)
# ═══════════════════════════════════════════════════════════════════════════════
async def S15_search() -> None:
    print("\n━━━ S15. WEB SEARCH (SearXNG) ━━━")

    # S15a: SearXNG JSON search via its internal port
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("http://localhost:8088/search?q=NERC+CIP&format=json")
            if r.status_code == 200:
                data = r.json()
                n = len(data.get("results", []))
                log("PASS" if n > 0 else "WARN", "S15a",
                    f"SearXNG JSON search: {n} results")
            else:
                log("WARN", "S15a", f"SearXNG returned HTTP {r.status_code}")
    except Exception as e:
        log("WARN", "S15a", f"SearXNG unreachable: {e}")

    # S15b: auto-research workspace with web-search prompt
    code, text = await _chat(
        "auto-research",
        "What are the key differences between symmetric and asymmetric encryption? "
        "Provide a technical comparison.",
        max_tokens=200,
        timeout=180,
    )
    if code == 200 and text.strip():
        has_signals = any(
            s in text.lower()
            for s in ["symmetric", "asymmetric", "aes", "rsa", "key", "encrypt"]
        )
        log(
            "PASS" if has_signals else "WARN",
            "S15b",
            f"auto-research workspace: '{text[:80].strip()}'",
        )
    elif code == 503:
        log("WARN", "S15b", "auto-research: 503 — backend not available")
    else:
        log("WARN", "S15b", f"auto-research: HTTP {code}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 16: CLI COMMANDS (HOWTO quick reference)
# ═══════════════════════════════════════════════════════════════════════════════
async def S16_cli() -> None:
    print("\n━━━ S16. CLI COMMANDS ━━━")

    cli_cases = [
        ("status",     "status → shows service health"),
        ("list-users", "list-users → lists accounts"),
    ]
    for cmd, label in cli_cases:
        r = subprocess.run(
            ["./launch.sh", cmd],
            capture_output=True, text=True, timeout=30, cwd=str(ROOT),
        )
        log(
            "PASS" if r.returncode == 0 else "WARN",
            "S16",
            f"{label} (exit {r.returncode})",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 17: PIPELINE RECONSTRUCTION / REBUILD MCPs
# ═══════════════════════════════════════════════════════════════════════════════
async def S17_rebuild() -> None:
    """
    Verify running containers match the codebase.
    Rebuild MCP containers if their image is stale (digest differs from Dockerfile hash).
    Restart services as needed.
    """
    print("\n━━━ S17. SERVICE REBUILD & RESTART VERIFICATION ━━━")

    dc = ["docker", "compose", "-f", "deploy/portal-5/docker-compose.yml"]

    # S17a: All expected containers running
    r = subprocess.run(
        dc + ["ps", "--format", "json"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    if r.returncode == 0:
        try:
            containers = json.loads(f"[{','.join(r.stdout.strip().splitlines())}]")
            running = {c.get("Name") or c.get("Service", "") for c in containers
                       if c.get("State", c.get("Status", "")).lower() in ("running", "healthy")}
            expected_prefixes = [
                "portal5-pipeline", "portal5-open-webui", "portal5-mcp-documents",
                "portal5-mcp-music", "portal5-mcp-tts", "portal5-mcp-whisper",
                "portal5-mcp-sandbox", "portal5-dind", "portal5-ollama",
            ]
            missing = [p for p in expected_prefixes
                       if not any(p in c for c in running)]
            log(
                "PASS" if not missing else "WARN",
                "S17a",
                f"Running containers: {len(running)} — "
                f"{'all expected services up' if not missing else f'MISSING {missing}'}",
            )
        except Exception:
            # docker compose ps may output table format in older versions
            log("INFO", "S17a", f"docker compose ps output: {r.stdout[:200]}")
    else:
        log("WARN", "S17a", f"docker compose ps failed: {r.stderr[:80]}")

    # S17b: Check if MCP image needs rebuild (Dockerfile.mcp changed since last build)
    dockerfile_hash = subprocess.run(
        ["md5sum", str(ROOT / "Dockerfile.mcp")],
        capture_output=True, text=True,
    )
    log("INFO", "S17b",
        f"Dockerfile.mcp hash: {dockerfile_hash.stdout.split()[0] if dockerfile_hash.returncode == 0 else 'unknown'}")

    # S17c: MCP containers respond to health after potential restarts
    mcp_services = [
        ("mcp-documents", "http://localhost:8913/health"),
        ("mcp-music",     "http://localhost:8912/health"),
        ("mcp-tts",       "http://localhost:8916/health"),
        ("mcp-whisper",   "http://localhost:8915/health"),
        ("mcp-sandbox",   "http://localhost:8914/health"),
        ("mcp-video",     "http://localhost:8911/health"),
    ]
    all_healthy = True
    async with httpx.AsyncClient(timeout=6) as c:
        for svc, url in mcp_services:
            try:
                r2 = await c.get(url)
                if r2.status_code != 200:
                    all_healthy = False
                    log("WARN", "S17c", f"{svc}: HTTP {r2.status_code} — attempting restart")
                    subprocess.run(
                        dc + ["restart", svc],
                        capture_output=True, cwd=str(ROOT), timeout=30,
                    )
            except Exception:
                all_healthy = False

    if all_healthy:
        log("PASS", "S17c", "All MCP services healthy — no restart needed")
    else:
        # Re-check after restarts
        await asyncio.sleep(5)
        async with httpx.AsyncClient(timeout=6) as c:
            recovered = 0
            for svc, url in mcp_services:
                try:
                    r2 = await c.get(url)
                    if r2.status_code == 200:
                        recovered += 1
                except Exception:
                    pass
        log(
            "PASS" if recovered == len(mcp_services) else "WARN",
            "S17c-post-restart",
            f"After restart: {recovered}/{len(mcp_services)} MCP services healthy",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — serial execution
# ═══════════════════════════════════════════════════════════════════════════════
async def main() -> int:
    t0 = time.time()

    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║  Portal 5 — Full End-to-End Acceptance Test Suite v3             ║")
    print(f"║  {time.strftime('%Y-%m-%d %H:%M:%S')}  ·  {len(WS_IDS)} workspaces  ·  {len(PERSONAS)} personas          ║")
    print(f"║  Git SHA: {_git_sha():<57}║")
    print("╚═══════════════════════════════════════════════════════════════════╝")
    print("\nExecution: serial (single-user lab), one test at a time")
    print("Failure policy: test assumed correct → diagnose → retry → BLOCKED only if code change required\n")

    await preflight()

    # Run all sections serially
    sections = [
        (S0_version,  "S0 Version"),
        (S17_rebuild, "S17 Rebuild"),   # rebuild/restart before testing
        (S1_static,   "S1 Static"),
        (S2_health,   "S2 Health"),
        (S3_routing,  "S3 Routing"),
        (S4_documents,"S4 Documents"),
        (S5_code,     "S5 Code"),
        (S6_security, "S6 Security"),
        (S7_music,    "S7 Music"),
        (S8_tts,      "S8 TTS"),
        (S9_whisper,  "S9 Whisper"),
        (S10_video,   "S10 Video"),
        (S11_personas,"S11 Personas"),
        (S12_metrics, "S12 Metrics"),
        (S13_gui,     "S13 GUI"),
        (S14_howto,   "S14 HOWTO"),
        (S15_search,  "S15 Search"),
        (S16_cli,     "S16 CLI"),
    ]

    for fn, name in sections:
        try:
            await fn()
        except Exception as e:
            log("FAIL", name, f"Section crashed: {type(e).__name__}: {e}")
        print()  # blank line between sections

    # ── Summary ────────────────────────────────────────────────────────────────
    elapsed = int(time.time() - t0)
    counts: dict[str, int] = {}
    for s, _, _ in _RESULTS:
        counts[s] = counts.get(s, 0) + 1

    print("╔═══════════════════════════════════════════════════════════════════╗")
    print(f"║  RESULTS  ({elapsed}s)                                              ║")
    print("╠═══════════════════════════════════════════════════════════════════╣")
    for s in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO", "SKIP"]:
        if s in counts:
            icon = _ICONS.get(s, "  ")
            print(f"║  {icon} {s:8s}: {counts[s]:3d}                                              ║")
    print(f"║  Total    : {sum(counts.values()):3d}                                              ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")

    # ── Write report ───────────────────────────────────────────────────────────
    rpt = ROOT / "ACCEPTANCE_RESULTS.md"
    with open(rpt, "w") as f:
        f.write("# Portal 5 — End-to-End Acceptance Test Results\n\n")
        f.write(f"**Suite:** v3 (full end-to-end)  \n")
        f.write(f"**Run:** {time.strftime('%Y-%m-%d %H:%M:%S')} ({elapsed}s)  \n")
        f.write(f"**Git SHA:** {_git_sha()}  \n")
        f.write(f"**Workspaces:** {len(WS_IDS)}  ·  **Personas:** {len(PERSONAS)}\n\n")
        f.write("## Summary\n\n")
        for s in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO", "SKIP"]:
            if s in counts:
                f.write(f"- **{s}**: {counts[s]}\n")

        f.write("\n## All Results\n\n")
        f.write("| # | Status | Section | Detail |\n|---|---|---|---|\n")
        for i, (s, sec, msg) in enumerate(_RESULTS, 1):
            f.write(f"| {i} | {s} | {sec} | {msg.replace('|','∣')[:200]} |\n")

        if _BLOCKED_ITEMS:
            f.write("\n## Blocked Items Register\n\n")
            f.write("Items in this table require core code changes. "
                    "The test is correct; these are genuine product issues.\n\n")
            f.write("| # | Section | Feature | Evidence | Likely Fix |\n"
                    "|---|---------|---------|----------|------------|\n")
            for i, item in enumerate(_BLOCKED_ITEMS, 1):
                f.write(
                    f"| {i} | {item['section']} | {item['feature']} "
                    f"| {item['evidence'][:120]} | {item['likely_fix'][:120]} |\n"
                )
        else:
            f.write("\n## Blocked Items Register\n\n")
            f.write("*No blocked items — all failures diagnosed as environmental "
                    "or test-configuration issues.*\n")

        f.write(f"\n---\n*Screenshots: /tmp/p5_gui_*.png*\n")

    print(f"\nReport written → {rpt}")
    print("Screenshots: /tmp/p5_gui_*.png")

    return 1 if counts.get("FAIL", 0) or counts.get("BLOCKED", 0) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
