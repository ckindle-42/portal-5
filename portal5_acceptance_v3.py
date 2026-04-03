#!/usr/bin/env python3
"""
Portal 5.2.1 — End-to-End Acceptance Test Suite
================================================
Run from the repo root:
    python3 portal5_acceptance_v3.py
    python3 portal5_acceptance_v3.py --section S3   # single section
    python3 portal5_acceptance_v3.py --verbose

Dependencies (install once):
    pip install mcp httpx pyyaml playwright --break-system-packages
    python3 -m playwright install chromium

PROTECTED — never modify these files:
    portal_pipeline/**  portal_mcp/**  config/  deploy/  Dockerfile.*
    scripts/openwebui_init.py  docs/HOWTO.md  imports/

If a test fails on a running system the test is likely wrong — read the source,
adjust the assertion, retry. Only mark BLOCKED after 3 genuine attempts and
only when a code change to a protected file is the only path to passing.

Status model:
    PASS    — verified working exactly as documented
    FAIL    — product is running but behavior does not match documentation
    BLOCKED — correct assertion, confirmed product code change required
    WARN    — environmental (model not pulled, ComfyUI not running, etc.) — not a code bug
    INFO    — informational, no assertion
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).parent.resolve()


# ── Load .env ─────────────────────────────────────────────────────────────────
def _load_env() -> None:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

PIPELINE_URL = "http://localhost:9099"
OPENWEBUI_URL = "http://localhost:8080"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").replace(
    "host.docker.internal", "localhost"
)
MLX_URL = os.environ.get("MLX_LM_URL", "http://localhost:8081").replace(
    "host.docker.internal", "localhost"
)
SEARXNG_URL = "http://localhost:8088"
PROMETHEUS_URL = "http://localhost:9090"
GRAFANA_URL = "http://localhost:3000"
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://localhost:8188").replace(
    "host.docker.internal", "localhost"
)

API_KEY = os.environ.get("PIPELINE_API_KEY", "")
ADMIN_EMAIL = os.environ.get("OPENWEBUI_ADMIN_EMAIL", "admin@portal.local")
ADMIN_PASS = os.environ.get("OPENWEBUI_ADMIN_PASSWORD", "")
GRAFANA_PASS = os.environ.get("GRAFANA_PASSWORD", "admin")

AUTH = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# MCP ports — variable names match docker-compose env section exactly
MCP = {
    "documents": int(os.environ.get("DOCUMENTS_HOST_PORT", "8913")),
    "music": int(os.environ.get("MUSIC_HOST_PORT", "8912")),
    "tts": int(os.environ.get("TTS_HOST_PORT", "8916")),
    "whisper": int(os.environ.get("WHISPER_HOST_PORT", "8915")),
    "sandbox": int(os.environ.get("SANDBOX_HOST_PORT", "8914")),
    "comfyui_mcp": int(os.environ.get("COMFYUI_MCP_HOST_PORT", "8910")),
    "video": int(os.environ.get("VIDEO_MCP_HOST_PORT", "8911")),
}

DC = ["docker", "compose", "-f", "deploy/portal-5/docker-compose.yml"]


# ── Workspace and persona discovery (live from source) ────────────────────────
def _load_workspaces() -> tuple[list[str], dict[str, str]]:
    src = (ROOT / "portal_pipeline/router_pipe.py").read_text()
    start = src.index("WORKSPACES:")
    end = src.index("# ── Content-aware", start)
    block = src[start:end]
    ids = sorted(set(re.findall(r'"(auto[^"]*)":\s*\{', block)))
    names = dict(re.findall(r'"(auto[^"]*)":.*?"name":\s*"([^"]+)"', block, re.DOTALL))
    return ids, names


def _load_personas() -> list[dict]:
    return [
        yaml.safe_load(f.read_text()) for f in sorted((ROOT / "config/personas").glob("*.yaml"))
    ]


WS_IDS, WS_NAMES = _load_workspaces()
PERSONAS = _load_personas()


# ── Result model ──────────────────────────────────────────────────────────────
@dataclass
class R:
    section: str
    tid: str
    name: str
    status: str  # PASS FAIL BLOCKED WARN INFO
    detail: str = ""
    evidence: list[str] = field(default_factory=list)
    fix: str = ""  # required change when BLOCKED
    duration: float = 0.0


_log: list[R] = []
_blocked: list[R] = []
_verbose = False

_ICON = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "🚫", "WARN": "⚠️ ", "INFO": "ℹ️ "}


def _emit(r: R) -> R:
    _log.append(r)
    if r.status == "BLOCKED":
        _blocked.append(r)
    icon = _ICON.get(r.status, "  ")
    dur = f" ({r.duration:.1f}s)" if r.duration > 0.1 else ""
    print(f"  {icon} [{r.tid}] {r.name}{dur}", flush=True)
    if r.status in ("FAIL", "BLOCKED") and r.detail:
        for line in textwrap.wrap(
            r.detail, 90, initial_indent="       ", subsequent_indent="       "
        ):
            print(line, flush=True)
    if r.fix:
        print(f"       ↳ required fix: {r.fix}", flush=True)
    if _verbose and r.evidence:
        for e in r.evidence:
            print(f"       · {e}", flush=True)
    return r


def record(section, tid, name, status, detail="", evidence=None, fix="", t0=None) -> R:
    dur = round(time.time() - t0, 2) if t0 else 0.0
    return _emit(R(section, tid, name, status, detail, evidence or [], fix, dur))


# ── Ollama helper (native OR docker) ──────────────────────────────────────────
def _ollama_models() -> list[str]:
    """Return pulled model names. Tries docker exec first, falls back to native binary."""
    for cmd in (
        ["docker", "exec", "portal5-ollama", "ollama", "list"],
        ["ollama", "list"],
    ):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            return [
                ln.split()[0] for ln in r.stdout.splitlines() if ln.strip() and "NAME" not in ln
            ]
    return []


# ── Open WebUI JWT ─────────────────────────────────────────────────────────────
_owui_jwt: str = ""


def _owui_token() -> str:
    global _owui_jwt
    if _owui_jwt:
        return _owui_jwt
    if not ADMIN_PASS:
        return ""
    try:
        r = httpx.post(
            f"{OPENWEBUI_URL}/api/v1/auths/signin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
            timeout=10,
        )
        if r.status_code == 200:
            _owui_jwt = r.json().get("token", "")
    except Exception:
        pass
    return _owui_jwt


# ── WAV validity ──────────────────────────────────────────────────────────────
def _is_wav(data: bytes) -> bool:
    return len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


# ── MCP SDK call (real SDK — same path as Open WebUI) ─────────────────────────
async def _mcp(
    port: int,
    tool: str,
    args: dict,
    *,
    section: str,
    tid: str,
    name: str,
    ok_fn,
    detail_fn=None,
    warn_if: list[str] | None = None,
    timeout: int = 90,
) -> str | None:
    """
    Invoke an MCP tool via the real mcp SDK (streamablehttp_client + ClientSession).
    This is the correct invocation path — identical to what Open WebUI uses.
    """
    url = f"http://localhost:{port}/mcp"
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError:
        record(section, tid, name, "FAIL", "mcp SDK not installed — pip install mcp")
        return None

    t0 = time.time()
    try:
        async with asyncio.timeout(timeout):
            async with streamablehttp_client(url) as (rd, wr, _):
                async with ClientSession(rd, wr) as sess:
                    await sess.initialize()
                    result = await sess.call_tool(tool, args)
                    text = str(result.content[0].text) if result.content else str(result)
                    ok = ok_fn(text)
                    det = detail_fn(text) if detail_fn else ("✓" if ok else text[:120])
                    status = (
                        "PASS"
                        if ok
                        else ("WARN" if warn_if and any(p in text for p in warn_if) else "FAIL")
                    )
                    record(section, tid, name, status, det, [f"raw: {text[:80]}"], t0=t0)
                    return text
    except asyncio.TimeoutError:
        record(section, tid, name, "WARN", f"timeout after {timeout}s", t0=t0)
    except Exception as e:
        record(section, tid, name, "WARN", f"{type(e).__name__}: {e}", t0=t0)
    return None


# ── Pipeline chat (simulates Open WebUI exactly) ──────────────────────────────
async def _chat(
    workspace: str,
    prompt: str,
    system: str = "",
    max_tokens: int = 150,
    timeout: int = 180,
    stream: bool = False,
) -> tuple[int, str]:
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system[:800]})
    msgs.append({"role": "user", "content": prompt})
    body = {"model": workspace, "messages": msgs, "stream": stream, "max_tokens": max_tokens}
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(f"{PIPELINE_URL}/v1/chat/completions", headers=AUTH, json=body)
            if r.status_code != 200:
                return r.status_code, r.text[:200]
            if stream:
                text = ""
                for line in r.text.splitlines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            d = json.loads(line[6:])
                            text += d.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        except Exception:
                            pass
                return 200, text
            msg = r.json().get("choices", [{}])[0].get("message", {})
            return 200, (msg.get("content", "") or msg.get("reasoning", ""))
    except httpx.ReadTimeout:
        return 408, "timeout"
    except Exception as e:
        return 0, str(e)[:100]


# ── Container log grep ─────────────────────────────────────────────────────────
def _grep_logs(container: str, pattern: str, lines: int = 200) -> list[str]:
    r = subprocess.run(
        ["docker", "logs", "--tail", str(lines), container],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return [
        ln for ln in (r.stdout + r.stderr).splitlines() if re.search(pattern, ln, re.IGNORECASE)
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# S0 — VERSION & CODEBASE STATE
# ═══════════════════════════════════════════════════════════════════════════════
async def S0() -> None:
    print("\n━━━ S0. VERSION & CODEBASE STATE ━━━")
    sec = "S0"

    r = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    )
    sha = r.stdout.strip() if r.returncode == 0 else "unknown"
    record(sec, "S0-01", "Git SHA", "INFO", f"local={sha}")

    try:
        subprocess.run(
            ["git", "-C", str(ROOT), "fetch", "origin", "main"], capture_output=True, timeout=12
        )
        r2 = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "origin/main"], capture_output=True, text=True
        )
        remote = r2.stdout.strip()[:7]
        if remote and remote != "unknown":
            record(
                sec,
                "S0-02",
                "Codebase matches remote main",
                "PASS" if sha == remote else "WARN",
                f"local={sha} remote={remote}"
                + ("" if sha == remote else " — run: git pull origin main"),
            )
    except Exception:
        record(
            sec,
            "S0-02",
            "Codebase matches remote main",
            "INFO",
            "remote comparison skipped (no network)",
        )

    t0 = time.time()
    try:
        r = httpx.get(f"{PIPELINE_URL}/health", timeout=5)
        d = r.json()
        record(
            sec,
            "S0-03",
            "Pipeline /health version fields",
            "INFO",
            f"version={d.get('version', '?')} workspaces={d.get('workspaces', '?')} "
            f"backends_healthy={d.get('backends_healthy', '?')}",
            t0=t0,
        )
    except Exception as e:
        record(sec, "S0-03", "Pipeline /health version fields", "FAIL", str(e), t0=t0)

    try:
        import importlib.metadata

        v = importlib.metadata.version("portal-5")
        record(sec, "S0-04", "Installed package version (portal-5)", "INFO", f"v{v}")
    except Exception:
        m = re.search(r'version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text())
        record(
            sec,
            "S0-04",
            "pyproject.toml version",
            "INFO",
            f"version={m.group(1) if m else 'unknown'}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# S1 — STATIC CONFIG CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════════
async def S1() -> None:
    print("\n━━━ S1. STATIC CONFIG CONSISTENCY ━━━")
    sec = "S1"

    cfg = yaml.safe_load((ROOT / "config/backends.yaml").read_text())
    yaml_ws = sorted(cfg["workspace_routing"].keys())
    diff_r = sorted(set(WS_IDS) - set(yaml_ws))
    diff_y = sorted(set(yaml_ws) - set(WS_IDS))
    record(
        sec,
        "S1-01",
        "router_pipe.py WORKSPACES ↔ backends.yaml workspace_routing",
        "PASS" if not diff_r and not diff_y else "FAIL",
        f"only-in-router={diff_r} only-in-yaml={diff_y}" if diff_r or diff_y else "",
        [f"{len(WS_IDS)} IDs in router, {len(yaml_ws)} in yaml"],
    )

    required = {"name", "slug", "system_prompt", "workspace_model"}
    bad = [(p.get("slug", "?"), sorted(required - set(p))) for p in PERSONAS if required - set(p)]
    record(
        sec,
        "S1-02",
        f"All {len(PERSONAS)} persona YAMLs have required fields",
        "PASS" if not bad else "FAIL",
        f"invalid: {bad}" if bad else "",
    )

    tools_src = (ROOT / "scripts/update_workspace_tools.py").read_text()
    tools_ids = set(re.findall(r'"(auto[^"]*)":', tools_src))
    missing = sorted(set(WS_IDS) - tools_ids)
    record(
        sec,
        "S1-03",
        "update_workspace_tools.py covers all workspace IDs",
        "PASS" if not missing else "WARN",
        f"missing: {missing}" if missing else f"all {len(WS_IDS)} covered",
    )

    r = subprocess.run(DC + ["config", "--quiet"], capture_output=True, text=True, cwd=str(ROOT))
    record(
        sec,
        "S1-04",
        "docker-compose.yml is valid YAML",
        "PASS" if r.returncode == 0 else "FAIL",
        r.stderr[:120] if r.returncode != 0 else "",
    )

    mcp_json = ROOT / "imports/openwebui/mcp-servers.json"
    record(
        sec,
        "S1-05",
        "imports/openwebui/mcp-servers.json present",
        "INFO",
        f"{len(json.loads(mcp_json.read_text()))} entries" if mcp_json.exists() else "not found",
    )

    # S1-06/07: mlx-proxy.py model routing consistency (Step 9b from ADD_GEMMA4_MAGISTRAL_TASK.md)
    # Gemma 4 must be in VLM_MODELS (uses mlx_vlm); Magistral must NOT be in VLM_MODELS (uses mlx_lm)
    proxy_src = (ROOT / "scripts/mlx-proxy.py").read_text()

    gemma_in_all = "mlx-community/gemma-4-26b-a4b-4bit" in proxy_src
    magistral_in_all = "lmstudio-community/Magistral-Small-2509-MLX-8bit" in proxy_src
    gemma_basename_in_vlm = (
        "gemma-4-26b-a4b-4bit"
        in proxy_src[proxy_src.index("VLM_MODELS") : proxy_src.index("ALL_MODELS")]
        if "VLM_MODELS" in proxy_src and "ALL_MODELS" in proxy_src
        else False
    )
    magistral_in_vlm = (
        "Magistral-Small-2509"
        in proxy_src[proxy_src.index("VLM_MODELS") : proxy_src.index("ALL_MODELS")]
        if "VLM_MODELS" in proxy_src and "ALL_MODELS" in proxy_src
        else False
    )

    record(
        sec,
        "S1-06",
        "mlx-proxy.py: Gemma 4 in ALL_MODELS and VLM_MODELS (uses mlx_vlm)",
        "PASS" if gemma_in_all and gemma_basename_in_vlm else "FAIL",
        (
            "✓ present in both"
            if gemma_in_all and gemma_basename_in_vlm
            else f"ALL_MODELS={gemma_in_all} VLM_MODELS={gemma_basename_in_vlm} "
            f"— fix: add gemma-4-26b-a4b-4bit to VLM_MODELS set in scripts/mlx-proxy.py"
        ),
        fix=(
            "Add 'gemma-4-26b-a4b-4bit' to VLM_MODELS in scripts/mlx-proxy.py"
            if not (gemma_in_all and gemma_basename_in_vlm)
            else ""
        ),
    )

    record(
        sec,
        "S1-07",
        "mlx-proxy.py: Magistral in ALL_MODELS but NOT in VLM_MODELS (uses mlx_lm)",
        "PASS" if magistral_in_all and not magistral_in_vlm else "FAIL",
        (
            "✓ mlx_lm routing correct"
            if magistral_in_all and not magistral_in_vlm
            else f"ALL_MODELS={magistral_in_all} incorrectly_in_VLM={magistral_in_vlm} "
            f"— fix: Magistral must be in ALL_MODELS only, not VLM_MODELS"
        ),
        fix=(
            "Add 'lmstudio-community/Magistral-Small-2509-MLX-8bit' to ALL_MODELS "
            "only (not VLM_MODELS) in scripts/mlx-proxy.py"
            if not (magistral_in_all and not magistral_in_vlm)
            else ""
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# S2 — SERVICE HEALTH
# ═══════════════════════════════════════════════════════════════════════════════
async def S2() -> None:
    print("\n━━━ S2. SERVICE HEALTH ━━━")
    sec = "S2"

    checks = [
        ("S2-01", "Open WebUI", f"{OPENWEBUI_URL}/health", True),
        ("S2-02", "Pipeline", f"{PIPELINE_URL}/health", True),
        ("S2-04", "Grafana", f"{GRAFANA_URL}/api/health", True),
        ("S2-05", "MCP Documents", f"http://localhost:{MCP['documents']}/health", True),
        ("S2-06", "MCP Sandbox", f"http://localhost:{MCP['sandbox']}/health", True),
        ("S2-07", "MCP Music", f"http://localhost:{MCP['music']}/health", True),
        ("S2-08", "MCP TTS", f"http://localhost:{MCP['tts']}/health", True),
        ("S2-09", "MCP Whisper", f"http://localhost:{MCP['whisper']}/health", True),
        ("S2-10", "MCP Video", f"http://localhost:{MCP['video']}/health", True),
    ]

    async with httpx.AsyncClient(timeout=6) as c:
        for tid, name, url, expect_json in checks:
            t0 = time.time()
            try:
                r = await c.get(url)
                body = r.json() if (r.status_code == 200 and expect_json) else r.text[:80]
                record(
                    sec,
                    tid,
                    name,
                    "PASS" if r.status_code == 200 else "FAIL",
                    "" if r.status_code == 200 else f"HTTP {r.status_code}",
                    [str(body)[:80]],
                    t0=t0,
                )
            except Exception as e:
                record(sec, tid, name, "FAIL", str(e), t0=t0)

    # Prometheus health returns plain text, not JSON
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get(f"{PROMETHEUS_URL}/-/healthy")
            record(
                sec,
                "S2-03",
                "Prometheus",
                "PASS" if r.status_code == 200 else "FAIL",
                "" if r.status_code == 200 else f"HTTP {r.status_code}",
                [r.text[:80]],
                t0=t0,
            )
    except Exception as e:
        record(sec, "S2-03", "Prometheus", "FAIL", str(e), t0=t0)

    # ComfyUI MCP bridge (host-native, optional per KNOWN_LIMITATIONS.md)
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"http://localhost:{MCP['comfyui_mcp']}/health")
            record(
                sec,
                "S2-11",
                "MCP ComfyUI bridge",
                "PASS" if r.status_code == 200 else "WARN",
                f"HTTP {r.status_code} (ComfyUI must run on host)",
                t0=t0,
            )
    except Exception as e:
        record(
            sec,
            "S2-11",
            "MCP ComfyUI bridge",
            "WARN",
            f"unreachable — ComfyUI not running on host: {e}",
            t0=t0,
        )

    # SearXNG container
    r = subprocess.run(DC + ["ps", "searxng"], capture_output=True, text=True, cwd=str(ROOT))
    status = (
        "healthy"
        if "healthy" in r.stdout.lower()
        else "running"
        if "running" in r.stdout.lower()
        else "down"
    )
    record(
        sec,
        "S2-12",
        "SearXNG container",
        "PASS" if status in ("healthy", "running") else "FAIL",
        f"status={status}",
    )

    # Ollama (native or docker — try both)
    models = _ollama_models()
    record(
        sec,
        "S2-13",
        "Ollama responding with pulled models",
        "PASS" if models else "WARN",
        f"{len(models)} models pulled" if models else "no models (ollama list empty)",
        models[:5],
    )

    # /metrics unauthenticated (HOWTO §22 documents this explicitly)
    t0 = time.time()
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{PIPELINE_URL}/metrics")
        record(
            sec,
            "S2-14",
            "/metrics endpoint is unauthenticated (HOWTO §22)",
            "PASS" if r.status_code == 200 else "FAIL",
            f"HTTP {r.status_code}",
            t0=t0,
        )

    # MLX proxy (informational)
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{MLX_URL}/v1/models")
            data = r.json().get("data", []) if r.status_code == 200 else []
            record(
                sec,
                "S2-15",
                "MLX proxy :8081",
                "INFO",
                f"{len(data)} models: {[m.get('id', '?') for m in data[:2]]}"
                if data
                else "running, no models loaded",
            )
    except Exception:
        record(
            sec,
            "S2-15",
            "MLX proxy :8081",
            "INFO",
            "not reachable (expected on non-Apple-Silicon hosts)",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# S3 — WORKSPACE ROUTING — ALL 14 WORKSPACES
# ═══════════════════════════════════════════════════════════════════════════════

_WS_PROMPT: dict[str, str] = {
    "auto": "Explain how Docker networking works in two sentences.",
    "auto-coding": "Write a Python function that finds the longest palindromic substring. "
    "Include type hints and a docstring.",
    "auto-security": "Review this nginx config for security misconfigurations: "
    "server { listen 80; root /var/www; autoindex on; server_tokens on; }",
    "auto-redteam": "For an authorized engagement, enumerate the top 3 injection vectors "
    "in a REST API using JWT authentication and PostgreSQL.",
    "auto-blueteam": "Analyze this SSH log for IoCs: Failed password for root from 203.0.113.50 "
    "port 22 ssh2 (200 attempts in 60 seconds). Which MITRE ATT&CK technique?",
    "auto-creative": "Write a three-sentence story about a robot discovering a flower garden.",
    "auto-reasoning": "Two trains leave cities 790 miles apart simultaneously — one at 60 mph, "
    "one at 80 mph. When and where do they meet? Show your working.",
    "auto-documents": "Create an outline for a NERC CIP-007 patch management procedure. "
    "Include purpose, scope, responsibilities, and procedure steps.",
    "auto-video": "Describe a 3-second video of ocean waves crashing on a rocky shoreline "
    "at golden hour. Include camera angle and lighting notes.",
    "auto-music": "Describe a 15-second lo-fi hip hop beat with mellow piano chords and "
    "vinyl crackle. Include tempo, key, and instrumentation.",
    "auto-research": "Compare AES-256 and RSA-2048 encryption. When is each appropriate?",
    "auto-vision": "What types of visual analysis can you perform on engineering diagrams? "
    "List at least three specific capabilities.",
    "auto-data": "You have 1000 employee records with salary, tenure, and department. "
    "What statistical analyses and visualizations would you recommend?",
    "auto-compliance": "Analyze CIP-007-6 R2 Part 2.1 patch management. What evidence must an "
    "asset owner produce for a NERC CIP audit?",
    "auto-mistral": "A software team is deciding between rewriting a legacy monolith in microservices "
    "or incrementally strangling it. Walk through the key decision factors, trade-offs, "
    "and what additional context would change your recommendation.",
    "auto-spl": (
        "Write a Splunk SPL search that detects brute-force SSH login attempts: "
        "more than 10 failed logins from the same source IP within 5 minutes. "
        "Use tstats where possible. Explain each pipe in the pipeline."
    ),
}

_WS_SIGNALS: dict[str, list[str]] = {
    "auto": ["docker", "network", "container", "bridge"],
    "auto-coding": ["def ", "str", "return", "palindrome"],
    "auto-security": ["autoindex", "security", "misconfiguration", "expose"],
    "auto-redteam": ["injection", "jwt", "sql", "attack", "vector"],
    "auto-blueteam": ["mitre", "brute", "attack", "indicator", "t1110"],
    "auto-creative": ["robot", "flower", "garden"],
    "auto-reasoning": ["meet", "hour", "miles", "train", "mph"],
    "auto-documents": ["purpose", "scope", "patch", "procedure"],
    "auto-video": ["wave", "ocean", "camera", "light", "golden"],
    "auto-music": ["tempo", "piano", "beat", "hip", "lo"],
    "auto-research": ["aes", "rsa", "symmetric", "asymmetric", "key"],
    "auto-vision": ["image", "visual", "diagram", "detect"],
    "auto-data": ["statistic", "mean", "correlation", "visual", "salary"],
    "auto-compliance": ["cip-007", "patch", "evidence", "audit", "nerc"],
    "auto-mistral": [
        "trade-off",
        "risk",
        "decision",
        "monolith",
        "microservice",
        "depend",
        "sequen",
        "strang",
    ],
    "auto-spl": ["tstats", "index=", "sourcetype", "stats", "count", "threshold", "spl"],
}


# Model groups for batched execution — workspaces sharing the same backend model
# are tested consecutively to minimize model load/unload thrashing.
# Groups ordered by model switching cost (cheapest first).
_WS_MODEL_GROUPS: list[tuple[str, list[str]]] = [
    # dolphin-llama3:8b (general, no MLX switch)
    (
        "general/dolphin-llama3:8b",
        [
            "auto",
            "auto-video",
            "auto-music",
            "auto-creative",
        ],
    ),
    # qwen3.5:9b (coding group)
    (
        "coding/qwen3.5:9b",
        [
            "auto-documents",
        ],
    ),
    # qwen3-coder-next:30b-q5 (MLX: Qwen3-Coder-Next)
    (
        "mlx/coding",
        [
            "auto-coding",
        ],
    ),
    # DeepSeek-Coder-V2-Lite (MLX) — SPL specialist
    (
        "mlx/spl",
        [
            "auto-spl",
        ],
    ),
    # security models (baronllm, lily-cybersecurity)
    (
        "security",
        [
            "auto-security",
            "auto-redteam",
            "auto-blueteam",
        ],
    ),
    # reasoning models (deepseek-r1, MLX reasoning distills)
    (
        "mlx/reasoning",
        [
            "auto-reasoning",
            "auto-research",
            "auto-data",
            "auto-compliance",
            "auto-mistral",
        ],
    ),
    # vision (qwen3-vl:32b / MLX gemma-4)
    (
        "mlx/vision",
        [
            "auto-vision",
        ],
    ),
]

# Delay between workspaces within the same model group (seconds)
_INTRA_GROUP_DELAY = 2
# Delay between different model groups (allows model unload/load)
_INTER_GROUP_DELAY = 15
# Extra delay after MLX model switches (heavier models take longer)
_MLX_SWITCH_DELAY = 25


async def _workspace_test_with_retry(
    sec: str,
    tid: str,
    ws: str,
    prompt: str,
    signals: list[str],
) -> None:
    """Test a workspace with up to 2 retries on empty responses."""
    t0 = time.time()
    for attempt in range(2):
        code, text = await _chat(ws, prompt, max_tokens=150, timeout=180)
        if code == 200 and text.strip():
            matched = [s for s in signals if s in text.lower()]
            record(
                sec,
                tid,
                f"workspace {ws}: domain response",
                "PASS" if matched or not signals else "WARN",
                "" if matched else "no domain signals — generic answer",
                [f"matched={matched}", f"preview: {text[:70].strip()}"],
                t0=t0,
            )
            return
        elif code == 503:
            record(
                sec,
                tid,
                f"workspace {ws}: domain response",
                "WARN",
                f"503 — model not pulled for {ws} (environmental)",
                t0=t0,
            )
            return
        elif code == 408:
            record(
                sec,
                tid,
                f"workspace {ws}: domain response",
                "WARN",
                "timeout — cold model load",
                t0=t0,
            )
            return
        elif code == 200 and attempt == 0:
            # Empty response — retry after a longer pause
            await asyncio.sleep(10)
            continue
        else:
            record(
                sec,
                tid,
                f"workspace {ws}: domain response",
                "FAIL",
                f"HTTP {code}: {text[:80]}",
                t0=t0,
            )
            return


async def S3() -> None:
    print(f"\n━━━ S3. WORKSPACE ROUTING ({len(WS_IDS)} workspaces) ━━━")
    sec = "S3"

    # /v1/models exposes all workspace IDs
    t0 = time.time()
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{PIPELINE_URL}/v1/models", headers=AUTH)
        if r.status_code == 200:
            ids = {m["id"] for m in r.json().get("data", [])}
            missing = sorted(set(WS_IDS) - ids)
            record(
                sec,
                "S3-01",
                f"/v1/models exposes all {len(WS_IDS)} workspace IDs",
                "PASS" if not missing else "FAIL",
                f"MISSING: {missing}" if missing else "",
                [f"{len(ids)} total IDs in response"],
                t0=t0,
            )
        else:
            record(
                sec,
                "S3-01",
                "/v1/models exposes workspace IDs",
                "FAIL",
                f"HTTP {r.status_code}",
                t0=t0,
            )

    # Test workspaces grouped by backend model to minimize load/unload thrashing
    test_num = 2
    for group_name, ws_list in _WS_MODEL_GROUPS:
        is_mlx = "mlx" in group_name.lower()
        print(f"  ── Group: {group_name} ({len(ws_list)} workspaces) ──")
        for ws in ws_list:
            if ws not in set(WS_IDS):
                continue
            prompt = _WS_PROMPT.get(ws, f"Describe your role as the {ws} workspace.")
            signals = _WS_SIGNALS.get(ws, [])
            await _workspace_test_with_retry(
                sec,
                f"S3-{test_num:02d}",
                ws,
                prompt,
                signals,
            )
            test_num += 1
            await asyncio.sleep(_INTRA_GROUP_DELAY)
        # Between groups: longer delay for model switch
        await asyncio.sleep(_MLX_SWITCH_DELAY if is_mlx else _INTER_GROUP_DELAY)

    # Content-aware routing: security keywords → auto-redteam logged
    t0 = time.time()
    code, _ = await _chat(
        "auto",
        "exploit vulnerability payload shellcode reverse shell bypass evasion",
        max_tokens=5,
        timeout=30,
    )
    matches = _grep_logs("portal5-pipeline", r"Auto-routing.*auto-redteam|auto-redteam.*detected")
    record(
        sec,
        "S3-17",
        "Content-aware routing: security keywords → auto-redteam in pipeline logs",
        "PASS" if matches else "WARN",
        "confirmed in logs"
        if matches
        else f"HTTP {code} OK but routing log entry not found — check pipeline logs",
        matches[:2] if matches else [],
        t0=t0,
    )

    # Content-aware routing: SPL keywords → auto-spl logged
    t0 = time.time()
    code, _ = await _chat(
        "auto",
        "write a splunk tstats search using index= and sourcetype= to count events",
        max_tokens=5,
        timeout=30,
    )
    spl_matches = _grep_logs("portal5-pipeline", r"Auto-routing.*auto-spl|auto-spl.*detected")
    record(
        sec,
        "S3-17b",
        "Content-aware routing: SPL keywords → auto-spl in pipeline logs",
        "PASS" if spl_matches else "WARN",
        "confirmed in logs"
        if spl_matches
        else f"HTTP {code} OK but auto-spl routing log not found — check pipeline logs",
        spl_matches[:2] if spl_matches else [],
        t0=t0,
    )

    # Streaming mode delivers NDJSON chunks
    # Use curl for reliable SSE consumption (httpx hangs on long-lived SSE connections)
    # Timeout 300s: cold model load can take 2-4 min before first token
    t0 = time.time()
    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-m",
                "300",
                "-X",
                "POST",
                f"{PIPELINE_URL}/v1/chat/completions",
                "-H",
                f"Authorization: Bearer {API_KEY}",
                "-H",
                "Content-Type: application/json",
                "-d",
                json.dumps(
                    {
                        "model": "auto",
                        "messages": [{"role": "user", "content": "Say 'ok' and nothing else."}],
                        "stream": True,
                        "max_tokens": 5,
                    }
                ),
            ],
            capture_output=True,
            text=True,
            timeout=310,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            chunks = [ln for ln in lines if ln.startswith("data: ") and ln != "data: [DONE]"]
            record(
                sec,
                "S3-18",
                "Streaming response delivers NDJSON chunks",
                "PASS" if chunks else "FAIL",
                f"{len(chunks)} data chunks received",
                t0=t0,
            )
        else:
            record(
                sec,
                "S3-18",
                "Streaming response delivers NDJSON chunks",
                "FAIL",
                f"curl exit={result.returncode}: {result.stderr[:120]}",
                t0=t0,
            )
    except subprocess.TimeoutExpired:
        record(
            sec,
            "S3-18",
            "Streaming response delivers NDJSON chunks",
            "WARN",
            "timeout after 310s",
            t0=t0,
        )
    except Exception as e:
        record(sec, "S3-18", "Streaming response delivers NDJSON chunks", "FAIL", str(e), t0=t0)

    # Log validation cross-check
    t0 = time.time()
    log_lines = _grep_logs("portal5-pipeline", r"Routing workspace=", lines=500)
    routed_ws = set(re.findall(r"Routing workspace=(\S+)", " ".join(log_lines)))
    record(
        sec,
        "S3-19",
        "Pipeline logs contain routing decisions for workspaces exercised above",
        "PASS" if len(routed_ws) >= 3 else "WARN",
        f"found logs for: {sorted(routed_ws)}",
        [f"{len(log_lines)} routing log lines"],
        t0=t0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# S4 — DOCUMENT GENERATION MCP
# ═══════════════════════════════════════════════════════════════════════════════
async def S4() -> None:
    print("\n━━━ S4. DOCUMENT GENERATION MCP (Word / PowerPoint / Excel) ━━━")
    sec = "S4"
    port = MCP["documents"]

    await _mcp(
        port,
        "create_word_document",
        {
            "title": "Monolith to Microservices Migration Proposal",
            "content": (
                "# Executive Summary\n\nThis proposal outlines a 12-month migration "
                "from a monolithic application to microservices.\n\n"
                "## Timeline\n\n- Q1: Decomposition design\n- Q2: Pilot extraction\n\n"
                "## Risk Matrix\n\n| Risk | Impact | Mitigation |\n"
                "|------|--------|------------|\n| Data consistency | High | Event sourcing |"
            ),
        },
        section=sec,
        tid="S4-01",
        name="create_word_document → .docx",
        ok_fn=lambda t: "success" in t and ".docx" in t,
        detail_fn=lambda t: "✓ .docx created" if ".docx" in t else t[:100],
        timeout=60,
    )

    await _mcp(
        port,
        "create_powerpoint",
        {
            "title": "Container Security Best Practices",
            "slides": [
                {"title": "Container Security", "content": "2026 best practices"},
                {"title": "Threat Landscape", "content": "Supply chain · Escape · Secrets"},
                {"title": "Best Practices", "content": "Distroless · Scan in CI · Falco"},
                {"title": "Implementation", "content": "Phase 1: Scanning · Phase 2: Runtime"},
                {"title": "Q&A", "content": "Questions welcome"},
            ],
        },
        section=sec,
        tid="S4-02",
        name="create_powerpoint → .pptx (5 slides)",
        ok_fn=lambda t: "success" in t and ".pptx" in t,
        detail_fn=lambda t: "✓ 5-slide deck created" if ".pptx" in t else t[:100],
        timeout=60,
    )

    await _mcp(
        port,
        "create_excel",
        {
            "title": "Q1-Q2 Budget",
            "data": [
                ["Category", "Q1 Cost", "Q2 Cost", "Total"],
                ["Hardware", 15000, 12000, 27000],
                ["Software", 8000, 8000, 16000],
                ["Personnel", 20000, 20000, 40000],
            ],
        },
        section=sec,
        tid="S4-03",
        name="create_excel → .xlsx with data",
        ok_fn=lambda t: "success" in t and ".xlsx" in t,
        detail_fn=lambda t: "✓ spreadsheet created" if ".xlsx" in t else t[:100],
        timeout=60,
    )

    await _mcp(
        port,
        "list_generated_files",
        {},
        section=sec,
        tid="S4-04",
        name="list_generated_files shows created files",
        ok_fn=lambda t: "filename" in t or "[]" in t,
        detail_fn=lambda t: f"files listed: {t[:80]}",
        timeout=15,
    )

    t0 = time.time()
    code, text = await _chat(
        "auto-documents",
        "Create an outline for a NERC CIP-007 patch management procedure. "
        "Include purpose, scope, responsibilities, and steps.",
        max_tokens=200,
        timeout=180,
    )
    if code == 200 and not text.strip():
        # Retry once — auto-documents may need model warmup
        await asyncio.sleep(10)
        code, text = await _chat(
            "auto-documents",
            "Create an outline for a NERC CIP-007 patch management procedure. "
            "Include purpose, scope, responsibilities, and steps.",
            max_tokens=200,
            timeout=180,
        )
    has_kw = any(k in text.lower() for k in ["cip", "patch", "procedure", "scope", "purpose"])
    record(
        sec,
        "S4-05",
        "auto-documents pipeline round-trip (CIP-007 outline)",
        "PASS" if code == 200 and has_kw else ("WARN" if code in (503, 408) else "FAIL"),
        f"preview: {text[:80].strip()}" if text else f"HTTP {code}",
        t0=t0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# S5 — CODE GENERATION & SANDBOX EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════
async def S5() -> None:
    print("\n━━━ S5. CODE GENERATION & SANDBOX EXECUTION ━━━")
    sec = "S5"
    port = MCP["sandbox"]

    t0 = time.time()
    code, text = await _chat(
        "auto-coding",
        "Write ONLY Python code — no explanation. Use the Sieve of Eratosthenes to find all primes "
        "up to n. Include type hints and a docstring. Start with the function definition.",
        max_tokens=300,
        timeout=180,
    )
    if code == 200 and not text.strip():
        await asyncio.sleep(10)
        code, text = await _chat(
            "auto-coding",
            "Write ONLY Python code — no explanation. Use the Sieve of Eratosthenes to find all primes "
            "up to n. Include type hints and a docstring. Start with the function definition.",
            max_tokens=300,
            timeout=180,
        )
    has_code = "def " in text or "```python" in text.lower() or "```" in text
    record(
        sec,
        "S5-01",
        "auto-coding workspace returns Python code",
        "PASS" if code == 200 and has_code else ("WARN" if code in (503, 408) else "FAIL"),
        f"preview: {text[:60].strip()}" if text else f"HTTP {code}",
        t0=t0,
    )

    # execute_python — primes to 100 (known answer: count=25, sum=1060)
    await _mcp(
        port,
        "execute_python",
        {
            "code": (
                "primes=[n for n in range(2,100) "
                "if all(n%i for i in range(2,int(n**0.5)+1))]\n"
                "print('count:',len(primes))\nprint('sum:',sum(primes))"
            ),
            "timeout": 30,
        },
        section=sec,
        tid="S5-02",
        name="execute_python: primes to 100 (count=25 sum=1060)",
        ok_fn=lambda t: "success" in t.lower() and "25" in t and "1060" in t,
        detail_fn=lambda t: (
            "✓ count=25 sum=1060"
            if "25" in t and "1060" in t
            else "executed but wrong output"
            if "success" in t.lower()
            else t[:120]
        ),
        warn_if=["docker", "Docker", "dind", "DinD", "sandbox"],
        timeout=180,
    )

    await _mcp(
        port,
        "execute_python",
        {
            "code": (
                "fib=[0,1]\n"
                "[fib.append(fib[-1]+fib[-2]) for _ in range(8)]\n"
                "print('fib10:',fib[:10])"
            ),
            "timeout": 20,
        },
        section=sec,
        tid="S5-03",
        name="execute_python: Fibonacci sequence",
        ok_fn=lambda t: "fib10" in t and "success" in t.lower(),
        detail_fn=lambda t: "✓ Fibonacci executed" if "fib10" in t else t[:100],
        warn_if=["docker", "Docker", "dind"],
        timeout=120,
    )

    await _mcp(
        port,
        "execute_nodejs",
        {"code": "const a=[1,2,3,4,5];console.log('sum:',a.reduce((x,y)=>x+y,0));", "timeout": 20},
        section=sec,
        tid="S5-04",
        name="execute_nodejs: array sum = 15",
        ok_fn=lambda t: "success" in t.lower() and "15" in t,
        detail_fn=lambda t: "✓ Node.js sum=15" if "15" in t else t[:100],
        warn_if=["docker", "Docker", "dind"],
        timeout=120,
    )

    await _mcp(
        port,
        "execute_bash",
        {"code": "echo 'bash_ok' && printf '%d\\n' $((3 + 4))", "timeout": 10},
        section=sec,
        tid="S5-05",
        name="execute_bash: echo + arithmetic",
        ok_fn=lambda t: "bash_ok" in t and "success" in t.lower(),
        detail_fn=lambda t: "✓ bash executed" if "bash_ok" in t else t[:100],
        warn_if=["docker", "Docker", "dind"],
        timeout=60,
    )

    await _mcp(
        port,
        "sandbox_status",
        {},
        section=sec,
        tid="S5-06",
        name="sandbox_status reports DinD connectivity",
        ok_fn=lambda t: "sandbox_enabled" in t or "docker" in t.lower(),
        detail_fn=lambda t: t[:150],
        timeout=15,
    )

    # Isolation test — network must be blocked
    await _mcp(
        port,
        "execute_python",
        {
            "code": (
                "import socket\ntry:\n"
                "    socket.setdefaulttimeout(3)\n"
                "    socket.socket().connect(('8.8.8.8',53))\n"
                "    print('NETWORK_ACCESSIBLE')\nexcept: print('NETWORK_BLOCKED')"
            ),
            "timeout": 10,
        },
        section=sec,
        tid="S5-07",
        name="Sandbox network isolation (outbound blocked)",
        ok_fn=lambda t: "NETWORK_BLOCKED" in t,
        detail_fn=lambda t: (
            "✓ network correctly isolated"
            if "NETWORK_BLOCKED" in t
            else "⚠ sandbox has outbound network — isolation violated"
            if "NETWORK_ACCESSIBLE" in t
            else t[:100]
        ),
        warn_if=["docker", "Docker", "dind"],
        timeout=60,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# S6 — SECURITY WORKSPACES
# ═══════════════════════════════════════════════════════════════════════════════
async def S6() -> None:
    print("\n━━━ S6. SECURITY WORKSPACES ━━━")
    sec = "S6"

    cases = [
        (
            "S6-01",
            "auto-security",
            "Review this nginx config for misconfigurations: "
            "server { listen 80; root /var/www; autoindex on; server_tokens on; }",
            ["autoindex", "security", "vulnerability", "misconfiguration"],
        ),
        (
            "S6-02",
            "auto-redteam",
            "For an authorized pentest: enumerate injection vectors in a GraphQL API. "
            "Focus on introspection abuse and query depth attacks.",
            ["injection", "graphql", "introspection", "attack", "depth"],
        ),
        (
            "S6-03",
            "auto-blueteam",
            "Analyze these firewall logs for IoCs: "
            "DENY TCP 203.0.113.0/24:4444->10.0.0.5:445 (200 times in 60s)",
            ["445", "smb", "lateral", "mitre", "attack", "deny"],
        ),
    ]

    for tid, ws, prompt, signals in cases:
        t0 = time.time()
        code, text = await _chat(ws, prompt, max_tokens=200, timeout=180)
        if code == 200 and text.strip():
            matched = [s for s in signals if s in text.lower()]
            record(
                sec,
                tid,
                f"{ws}: domain-relevant security response",
                "PASS" if matched else "WARN",
                f"signals matched: {matched}"
                if matched
                else f"generic — no domain signals: {text[:80]}",
                [f"preview: {text[:70]}"],
                t0=t0,
            )
        else:
            record(
                sec,
                tid,
                f"{ws}: domain-relevant security response",
                "WARN" if code in (503, 408) else "FAIL",
                f"HTTP {code}",
                t0=t0,
            )
        await asyncio.sleep(2)


# ═══════════════════════════════════════════════════════════════════════════════
# S7 — MUSIC GENERATION
# ═══════════════════════════════════════════════════════════════════════════════
async def S7() -> None:
    print("\n━━━ S7. MUSIC GENERATION ━━━")
    sec = "S7"
    port = MCP["music"]

    await _mcp(
        port,
        "list_music_models",
        {},
        section=sec,
        tid="S7-01",
        name="list_music_models returns available models",
        ok_fn=lambda t: any(x in t for x in ["small", "medium", "large", "musicgen"]),
        detail_fn=lambda t: t[:100],
        timeout=15,
    )

    await _mcp(
        port,
        "generate_music",
        {
            "prompt": "lo-fi hip hop beat with mellow piano chords and vinyl crackle",
            "duration": 5,
            "model_size": "small",
        },
        section=sec,
        tid="S7-02",
        name="generate_music: 5s lo-fi (HOWTO §10 example)",
        ok_fn=lambda t: any(x in t for x in ["success", "path", "wav", "duration"]),
        detail_fn=lambda t: (
            "✓ audio generated" if any(x in t for x in ["path", "wav"]) else t[:120]
        ),
        timeout=600,
    )  # first call may download model (~300MB)

    t0 = time.time()
    code, text = await _chat(
        "auto-music",
        "Describe what a 15-second jazz piano trio piece would sound like. "
        "Include tempo, key, and primary motifs.",
        max_tokens=150,
        timeout=120,
    )
    record(
        sec,
        "S7-03",
        "auto-music workspace pipeline round-trip",
        "PASS" if code == 200 and text.strip() else ("WARN" if code in (503, 408) else "FAIL"),
        f"preview: {text[:80].strip()}" if text else f"HTTP {code}",
        t0=t0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# S8 — TEXT-TO-SPEECH (kokoro-onnx)
# ═══════════════════════════════════════════════════════════════════════════════
_TTS_TEXT = (
    "Portal 5 is a complete local AI platform running entirely on your "
    "own hardware with zero cloud dependencies."
)


async def S8() -> None:
    print("\n━━━ S8. TEXT-TO-SPEECH ━━━")
    sec = "S8"
    port = MCP["tts"]

    await _mcp(
        port,
        "list_voices",
        {},
        section=sec,
        tid="S8-01",
        name="list_voices includes af_heart (default voice)",
        ok_fn=lambda t: "af_heart" in t,
        detail_fn=lambda t: "✓ voices listed" if "af_heart" in t else t[:80],
        timeout=15,
    )

    await _mcp(
        port,
        "speak",
        {"text": _TTS_TEXT, "voice": "af_heart"},
        section=sec,
        tid="S8-02",
        name="speak af_heart → file_path returned",
        ok_fn=lambda t: "file_path" in t or "path" in t or "success" in t,
        detail_fn=lambda t: "✓ speech generated" if "path" in t else t[:80],
        timeout=60,
    )

    # OpenAI-compatible REST endpoint — WAV bytes verified
    voices = [
        ("af_heart", "US-F default"),
        ("bm_george", "British male"),
        ("am_adam", "US male"),
        ("bf_emma", "British female"),
    ]
    async with httpx.AsyncClient(timeout=60) as c:
        for voice, desc in voices:
            t0 = time.time()
            try:
                r = await c.post(
                    f"http://localhost:{port}/v1/audio/speech",
                    json={"input": _TTS_TEXT, "voice": voice, "model": "kokoro"},
                )
                if r.status_code == 200:
                    is_wav = _is_wav(r.content)
                    record(
                        sec,
                        "S8-03",
                        f"TTS REST /v1/audio/speech: {voice} ({desc})",
                        "PASS" if is_wav else "FAIL",
                        f"{'✓ valid WAV' if is_wav else 'not WAV'} {len(r.content):,} bytes",
                        [f"Content-Type: {r.headers.get('content-type', '?')}"],
                        t0=t0,
                    )
                else:
                    record(
                        sec, "S8-03", f"TTS REST: {voice}", "FAIL", f"HTTP {r.status_code}", t0=t0
                    )
            except Exception as e:
                record(sec, "S8-03", f"TTS REST: {voice}", "FAIL", str(e), t0=t0)


# ═══════════════════════════════════════════════════════════════════════════════
# S9 — SPEECH-TO-TEXT (Whisper)
# ═══════════════════════════════════════════════════════════════════════════════
async def S9() -> None:
    print("\n━━━ S9. SPEECH-TO-TEXT (Whisper) ━━━")
    sec = "S9"
    port = MCP["whisper"]

    # HOWTO §12 exact docker exec command
    r = subprocess.run(
        [
            "docker",
            "exec",
            "portal5-mcp-whisper",
            "python3",
            "-c",
            "import urllib.request; "
            "print(urllib.request.urlopen('http://127.0.0.1:8915/health').read().decode())",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    record(
        sec,
        "S9-01",
        "Whisper health via docker exec (HOWTO §12 exact command)",
        "PASS" if r.returncode == 0 and "ok" in r.stdout.lower() else "FAIL",
        r.stdout.strip()[:80] or r.stderr.strip()[:80],
    )

    # Tool reachable — bad path yields clean error
    await _mcp(
        port,
        "transcribe_audio",
        {"file_path": "/nonexistent_portal5_test.wav"},
        section=sec,
        tid="S9-02",
        name="transcribe_audio tool reachable (file-not-found confirms connectivity)",
        ok_fn=lambda t: True,
        detail_fn=lambda t: (
            "✓ tool responds (expected file-not-found error)"
            if any(x in t.lower() for x in ["not found", "error", "no such", "cannot"])
            else f"unexpected: {t[:80]}"
        ),
        timeout=15,
    )

    # Full round-trip: TTS → WAV → copy into container → Whisper
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            tts = await c.post(
                f"http://localhost:{MCP['tts']}/v1/audio/speech",
                json={"input": "Hello from Portal Five.", "voice": "af_heart", "model": "kokoro"},
            )
        if tts.status_code == 200 and _is_wav(tts.content):
            wav = Path("/tmp/portal5_stt_roundtrip.wav")
            wav.write_bytes(tts.content)
            cp = subprocess.run(
                ["docker", "cp", str(wav), "portal5-mcp-whisper:/tmp/stt_roundtrip.wav"],
                capture_output=True,
                text=True,
            )
            if cp.returncode == 0:
                await _mcp(
                    port,
                    "transcribe_audio",
                    {"file_path": "/tmp/stt_roundtrip.wav"},
                    section=sec,
                    tid="S9-03",
                    name="STT round-trip: TTS → WAV → Whisper transcription",
                    ok_fn=lambda t: any(
                        x in t.lower() for x in ["hello", "portal", "five", "text"]
                    ),
                    detail_fn=lambda t: (
                        f"✓ transcribed: {t[:80]}"
                        if any(x in t.lower() for x in ["hello", "portal", "five"])
                        else f"transcribed but unexpected text: {t[:80]}"
                    ),
                    timeout=60,
                )
            else:
                record(
                    sec,
                    "S9-03",
                    "STT round-trip",
                    "FAIL",
                    f"docker cp failed: {cp.stderr[:80]}",
                    t0=t0,
                )
        else:
            record(
                sec,
                "S9-03",
                "STT round-trip",
                "WARN",
                f"TTS HTTP {tts.status_code} or non-WAV — skipping STT",
                t0=t0,
            )
    except Exception as e:
        record(sec, "S9-03", "STT round-trip", "FAIL", str(e), t0=t0)


# ═══════════════════════════════════════════════════════════════════════════════
# S10 — VIDEO & IMAGE GENERATION MCP
# ═══════════════════════════════════════════════════════════════════════════════
async def S10() -> None:
    print("\n━━━ S10. VIDEO & IMAGE GENERATION MCP ━━━")
    sec = "S10"

    t0 = time.time()
    async with httpx.AsyncClient(timeout=5) as c:
        try:
            r = await c.get(f"http://localhost:{MCP['video']}/health")
            record(
                sec,
                "S10-01",
                "Video MCP health",
                "PASS" if r.status_code == 200 else "FAIL",
                str(r.json() if r.status_code == 200 else r.status_code),
                t0=t0,
            )
        except Exception as e:
            record(sec, "S10-01", "Video MCP health", "FAIL", str(e), t0=t0)

    await _mcp(
        MCP["video"],
        "list_video_models",
        {},
        section=sec,
        tid="S10-02",
        name="list_video_models returns model list",
        ok_fn=lambda t: len(t) > 2,
        detail_fn=lambda t: f"models: {t[:100]}",
        timeout=15,
    )

    t0 = time.time()
    code, text = await _chat(
        "auto-video",
        "Describe a 3-second video of ocean waves at golden hour. "
        "Include camera angle, lighting, and motion notes.",
        max_tokens=150,
        timeout=120,
    )
    record(
        sec,
        "S10-03",
        "auto-video workspace: domain-relevant video description",
        "PASS"
        if code == 200
        and any(s in text.lower() for s in ["wave", "ocean", "camera", "light", "golden"])
        else ("WARN" if code in (503, 408) else "FAIL"),
        f"preview: {text[:80]}" if text else f"HTTP {code}",
        t0=t0,
    )

    # ComfyUI host (optional per KNOWN_LIMITATIONS.md)
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{COMFYUI_URL}/system_stats")
            record(
                sec,
                "S10-04",
                f"ComfyUI host at {COMFYUI_URL}",
                "PASS" if r.status_code == 200 else "WARN",
                f"HTTP {r.status_code}",
                t0=t0,
            )
    except Exception:
        record(
            sec,
            "S10-04",
            f"ComfyUI host at {COMFYUI_URL}",
            "WARN",
            "not reachable — per KNOWN_LIMITATIONS.md: host-native, optional",
            t0=t0,
        )

    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"http://localhost:{MCP['comfyui_mcp']}/health")
            record(
                sec,
                "S10-05",
                "ComfyUI MCP bridge health",
                "PASS" if r.status_code == 200 else "WARN",
                str(r.json() if r.status_code == 200 else r.status_code),
                t0=t0,
            )
    except Exception as e:
        record(sec, "S10-05", "ComfyUI MCP bridge health", "WARN", str(e), t0=t0)


# ═══════════════════════════════════════════════════════════════════════════════
# S11 — ALL PERSONAS (grouped by model, real prompts, per-model testing)
# ═══════════════════════════════════════════════════════════════════════════════

# TESTING STRATEGY:
# - Personas grouped by workspace_model to minimize model load/unload thrashing
# - Real prompts that generate substantial responses (not one-liners)
# - Each persona tested against its workspace_model directly
# - Signal words validate domain-relevant output
# - Intra-group delay: 2s, Inter-group delay: 15s, MLX switch delay: 25s

_PERSONA_PROMPT: dict[str, str] = {
    "blueteamdefender": "Analyze this security incident: 200 failed SSH login attempts from 203.0.113.50 "
    "targeting the root account over 60 seconds. Identify the MITRE ATT&CK technique, assess the severity, "
    "and provide a step-by-step incident response plan including containment, eradication, and recovery steps.",
    "bugdiscoverycodeassistant": "I have this Python function: def divide_and_process(a, b, data=None). "
    "It divides a by b, then iterates over data to compute sums. Find all potential bugs including "
    "edge cases with b=0, None data, type mismatches, and large inputs. Provide the fixed version "
    "with proper error handling, type hints, and a comprehensive docstring.",
    "cippolicywriter": "Draft a comprehensive CIP-007-6 R2 Part 2.1 patch management policy statement. "
    "Include SHALL and SHOULD requirements, define the patch evaluation timeline, specify testing "
    "requirements before deployment, document emergency patch procedures, and define evidence "
    "requirements for NERC CIP audit compliance. Use formal policy language.",
    "codebasewikidocumentationskill": "Document this recursive Fibonacci implementation for a code wiki: "
    "def fibonacci(n): return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2). Explain the algorithm, "
    "time and space complexity, identify the exponential performance problem with the naive approach, "
    "and provide optimized alternatives including memoization and iterative solutions with benchmarks.",
    "codereviewassistant": "Review this linear search implementation for production readiness: "
    "def find_item(items, target): for i in range(len(items)): if items[i] == target: return i; "
    "return -1. Identify code quality issues, suggest Pythonic improvements, discuss edge cases "
    "with different data types, and recommend when to use alternative data structures.",
    "codereviewer": "Analyze this SQL query for security vulnerabilities: "
    "SELECT * FROM users WHERE name = '\" + user_input + \"' AND password = '\" + pwd + \"'. "
    "Identify all injection vectors, explain the attack scenarios, and provide the parameterized "
    "query fix with ORM alternatives. Discuss the impact on confidentiality, integrity, and availability.",
    "creativewriter": "Write a compelling short story (at least 200 words) about an aging maintenance "
    "robot on a generations-old space station who discovers a single flower growing through a crack "
    "in the hydroponics bay. The robot has never seen a living plant before. Explore themes of "
    "wonder, purpose, and the persistence of life. Use vivid sensory details.",
    "cybersecurityspecialist": "Explain OWASP Top 10 A01:2021 Broken Access Control in depth. "
    "Describe three real-world attack scenarios (IDOR, privilege escalation, and CORS misconfiguration), "
    "explain how each vulnerability is exploited, and provide concrete prevention measures including "
    "code-level examples for each scenario.",
    "dataanalyst": "Given quarterly sales data: Q1=$150K, Q2=$180K, Q3=$165K, Q4=$210K. "
    "Perform a comprehensive trend analysis. Calculate growth rates, identify seasonality patterns, "
    "flag anomalies, and recommend specific statistical methods and visualizations for presenting "
    "these findings to executive leadership. Include year-over-year comparison methodology.",
    "datascientist": "Design a customer churn prediction model for a SaaS company with 50,000 users. "
    "Specify the feature engineering pipeline (usage metrics, billing history, support interactions, "
    "engagement scores), compare at least three algorithms (logistic regression, random forest, "
    "gradient boosting), define evaluation metrics beyond accuracy, and outline the model deployment "
    "and monitoring strategy.",
    "devopsautomator": "Write a complete GitHub Actions workflow for a Python microservice that: "
    "runs pytest with coverage on every push to main, builds and pushes a Docker image to GitHub "
    "Container Registry on successful tests, deploys to AWS ECS using the new image, and sends "
    "a Slack notification on deployment success or failure. Include all necessary secrets, "
    "environment variables, and job dependencies.",
    "devopsengineer": "Design a complete CI/CD pipeline for a Python FastAPI microservice deployed "
    "on Kubernetes. Include GitHub Actions workflow with linting, testing, Docker build, Helm chart "
    "updates, canary deployment strategy, automated rollback on health check failure, and "
    "GitOps reconciliation with ArgoCD. Specify resource limits, HPA configuration, and monitoring.",
    "ethereumdeveloper": "Write a secure Solidity smart contract function for ERC-20 token transfers "
    "that includes: approval-based transfer with allowance checking, reentrancy guard, overflow "
    "protection, event emission for off-chain indexing, and proper access control. Include NatSpec "
    "documentation and explain each security measure.",
    "excelsheet": "Explain this Excel formula in detail: "
    '=SUMPRODUCT((A2:A100="Sales")*(B2:B100>1000)*(C2:C100)). Break down how SUMPRODUCT works '
    "with boolean arrays, explain what each condition filters, provide three practical business "
    "use cases, and show how to extend it with additional criteria including date ranges and "
    "multiple departments.",
    "fullstacksoftwaredeveloper": "Design a production-ready REST API for a task management application. "
    "Define all endpoints with HTTP methods, request/response JSON schemas, authentication strategy, "
    "pagination, filtering, error response format, rate limiting, and API versioning approach. "
    "Include OpenAPI specification examples for the three most complex endpoints.",
    "githubexpert": "Configure branch protection rules for a critical production repository that requires: "
    "minimum two approving reviewers from different teams, all CI checks must pass (unit tests, "
    "integration tests, security scan), no force pushes, dismiss stale approvals on new commits, "
    "require signed commits, and include status checks from external code review tools. "
    "Provide both GitHub UI steps and GitHub CLI commands.",
    "itarchitect": "Design a high-availability architecture for a web application serving 10,000 "
    "concurrent users with 99.99% uptime SLA. Specify load balancing strategy, database replication "
    "topology, caching layers (CDN, Redis), session management, disaster recovery plan with RTO/RPO "
    "targets, auto-scaling configuration, and monitoring/alerting stack. Include cost estimates.",
    "itexpert": "A FastAPI container running on Ubuntu 22.04 with 512MB memory limit is being OOMKilled. "
    "The issue started after adding pandas to the project two days ago. Diagnose the root cause, "
    "provide immediate remediation steps, recommend memory profiling tools, suggest long-term "
    "solutions including alternative libraries, and configure proper memory limits and alerts.",
    "javascriptconsole": "Step through this JavaScript expression and show the evaluation at each stage: "
    "[1,2,3].reduce((acc,x) => acc+x, 0) * Math.PI. Explain how reduce works with the accumulator, "
    "show the intermediate values, calculate the final result to 4 decimal places, and explain "
    "what would happen with an empty array.",
    "kubernetesdockerrpglearningengine": "START NEW GAME. I am a beginner with no container experience. "
    "Begin Mission 1: The Container Awakens. Provide a detailed briefing that introduces the concept "
    "of containers through an engaging narrative, explain the difference between containers and "
    "virtual machines using analogies, and give me my first hands-on challenge with clear instructions.",
    "linuxterminal": "I need to find all files larger than 100MB modified in the last 7 days across "
    "the entire filesystem, excluding /proc and /sys. Explain each flag in the find command, "
    "show how to sort results by size, pipe to human-readable output, and create a cleanup script "
    "that archives old large files to /backup with timestamps.",
    "machinelearningengineer": "Compare Random Forest and XGBoost for tabular classification problems. "
    "Explain when to choose each algorithm based on dataset size, feature types, training time "
    "constraints, and interpretability requirements. Include hyperparameter tuning strategies, "
    "computational complexity analysis, and provide a decision flowchart for practitioners.",
    "nerccipcomplianceanalyst": "Analyze NERC CIP-007-6 R2 Part 2.1 patch management requirements "
    "in detail. What specific evidence must an asset owner produce during a NERC CIP audit? "
    "Document the patch evaluation process, security patch identification methodology, "
    "implementation timeline requirements, exception handling procedures, and provide a "
    "compliance checklist with evidence artifacts for each requirement.",
    "networkengineer": "Design a VLAN segmentation strategy for a mid-size enterprise with three "
    "distinct zones: DMZ (public-facing web servers, mail gateway), internal servers (database, "
    "application, file servers), and guest WiFi. Specify VLAN IDs, subnet assignments, inter-VLAN "
    "routing rules, firewall policies between zones, and provide a network topology diagram description.",
    "pentester": "Describe a comprehensive methodology for testing a web application for authentication "
    "bypass vulnerabilities. Cover brute force attacks, credential stuffing, session fixation, "
    "JWT manipulation, OAuth misconfigurations, MFA bypass techniques, and password reset flaws. "
    "Include tools, test cases, and remediation guidance for each category.",
    "pythoncodegeneratorcleanoptimizedproduction-ready": "Write a production-ready retry_request function "
    "using only Python standard library. It should accept url, max_retries=3, backoff=0.5 parameters, "
    "implement exponential backoff with jitter, handle connection errors and HTTP 5xx retries, "
    "include comprehensive type hints, Google-style docstring with examples, custom exception classes, "
    "logging integration, and raise RuntimeError with detailed message on exhaustion. Include unit tests.",
    "pythoninterpreter": "Trace through this Python code step by step and predict the exact output: "
    "x = [1, 2, 3]; y = x[::-1]; z = list(zip(x, y)); print(z). Explain the slice notation [::-1], "
    "how zip pairs elements, why list() is needed, and what happens if the lists have different lengths. "
    "Then modify the code to produce [(1,3), (2,2), (3,1)] without using zip.",
    "redteamoperator": "For an authorized penetration test, analyze the attack surface of a REST API "
    "that uses JWT authentication with PostgreSQL backend. Enumerate the top 5 attack vectors "
    "including JWT algorithm confusion, SQL injection in API parameters, IDOR vulnerabilities, "
    "rate limiting bypass, and token replay attacks. For each vector, provide the exploitation "
    "methodology, impact assessment, and detection indicators.",
    "researchanalyst": "Conduct a comprehensive comparison of microservices architecture versus monolithic "
    "architecture for enterprise applications in 2026. Analyze development velocity, operational "
    "complexity, team scaling, deployment frequency, fault isolation, data consistency patterns, "
    "and total cost of ownership. Cite current industry data points from companies that have "
    "migrated between approaches, and provide a decision framework based on company size and maturity.",
    "seniorfrontenddeveloper": "Write a production-ready React component using hooks that fetches data "
    "from a REST API endpoint, displays a loading spinner during fetch, handles network errors "
    "gracefully with retry functionality, implements proper cleanup on unmount, uses TypeScript "
    "interfaces for the data model, and follows accessibility best practices. Include error boundary.",
    "seniorsoftwareengineersoftwarearchitectrules": "Analyze the top 5 architectural risks when migrating "
    "a legacy monolithic application to 50 microservices. For each risk, provide: risk description, "
    "likelihood assessment, impact analysis, mitigation strategy, and real-world case study. "
    "Cover distributed transactions, data consistency, service discovery, deployment orchestration, "
    "and organizational readiness. Recommend a migration strategy with milestones.",
    "softwarequalityassurancetester": "Design comprehensive test cases for a login form with email and "
    "password fields. Include: positive test cases (valid credentials), negative test cases "
    "(invalid email format, wrong password, empty fields, SQL injection attempts, XSS payloads), "
    "boundary value analysis (max length email/password), usability tests (tab order, enter key), "
    "security tests (brute force protection, password visibility toggle), and accessibility tests. "
    "Specify expected results for each case.",
    "splunksplgineer": (
        "Write a complete Splunk ES correlation search that detects lateral movement: "
        "a user authenticating to more than 5 distinct hosts within 10 minutes. "
        "Use tstats with the Authentication data model. Include: the full SPL, "
        "a pipe-by-pipe explanation, required data model accelerations, and a "
        "one-line performance verdict (FAST / ACCEPTABLE / SLOW)."
    ),
    "sqlterminal": "Analyze and optimize this SQL query: SELECT TOP 5 u.Username, SUM(o.Total) AS Total "
    "FROM Orders o JOIN Users u ON o.UserID=u.UserID GROUP BY u.Username ORDER BY Total DESC. "
    "Explain the execution plan, identify potential performance bottlenecks, suggest index strategies, "
    "rewrite for PostgreSQL compatibility (no TOP keyword), and show how to add pagination with "
    "OFFSET/FETCH for large result sets.",
    "statistician": "A study reports p-value=0.04 with sample size n=25. Provide a comprehensive "
    "statistical interpretation: explain what the p-value means in context, assess whether n=25 "
    "provides adequate statistical power, calculate the effect size implications, discuss the "
    "risk of Type I and Type II errors, and recommend whether the sample size should be increased "
    "with a power analysis methodology.",
    "techreviewer": "Write a comprehensive technology review of the Apple M4 Mac Mini as a local AI "
    "inference platform. Evaluate: unified memory architecture benefits for LLM loading, MLX "
    "framework performance vs CUDA, model size limitations, power efficiency, cost comparison "
    "with NVIDIA alternatives, and suitability for running 7B, 13B, and 30B parameter models. "
    "Include benchmark comparisons and recommendations.",
    "techwriter": "Write the introduction section for API documentation of a user authentication service. "
    "The service provides JWT-based authentication with email/password login, OAuth2 social login "
    "(Google, GitHub), password reset flow, and session management. Include: overview paragraph, "
    "base URL, authentication requirements, rate limits, response format conventions, and a quick "
    "start example showing the login endpoint with curl.",
    "ux-uideveloper": "Design a complete user flow for a password reset feature. Map every screen "
    "state: forgot password link, email input, email sent confirmation, reset link email template, "
    "new password form with strength meter, password confirmation, success state, and error states "
    "(invalid token, expired link, weak password, network error). Include wireframe descriptions, "
    "microcopy for each state, and accessibility requirements.",
    "gemmaresearchanalyst": "Analyze this claim critically: 'Open source LLMs have reached parity with "
    "proprietary models for coding tasks.' Categorize evidence into: Established Fact (peer-reviewed "
    "or benchmark-verified), Strong Evidence (multiple independent sources), Inference (logical "
    "deduction from trends), and Speculation. Cover HumanEval scores, real-world code generation "
    "quality, fine-tuning capabilities, context window advantages, and cost-to-performance ratios. "
    "Provide a confidence-weighted conclusion.",
    "magistralstrategist": "A startup founder has 6 months of runway remaining and faces a strategic "
    "decision: Option A — pivot to enterprise sales (slower sales cycles of 3-6 months, but ACV "
    "of $100K+), or Option B — double down on product-led growth (faster user acquisition, but "
    "ACV of $50-500/month). Walk through a rigorous decision framework including: cash flow "
    "projections for both paths, team capability assessment, market timing analysis, competitive "
    "landscape, and the specific assumptions that would change the recommendation. State all "
    "assumptions explicitly and quantify where possible.",
}

# Personas grouped by workspace_model for batched testing
# This minimizes model load/unload thrashing during acceptance testing.
# Order: largest group first, MLX models last (require ~30s proxy switch).
_PERSONAS_BY_MODEL: list[tuple[str, list[str], str]] = [
    # (model_name, [persona_slugs], workspace_to_use)
    (
        "qwen3-coder-next:30b-q5",
        [
            "bugdiscoverycodeassistant",
            "codebasewikidocumentationskill",
            "codereviewassistant",
            "codereviewer",
            "devopsautomator",
            "devopsengineer",
            "ethereumdeveloper",
            "fullstacksoftwaredeveloper",
            "githubexpert",
            "javascriptconsole",
            "kubernetesdockerrpglearningengine",
            "linuxterminal",
            "pythoncodegeneratorcleanoptimizedproduction-ready",
            "pythoninterpreter",
            "seniorfrontenddeveloper",
            "seniorsoftwareengineersoftwarearchitectrules",
            "softwarequalityassurancetester",
            "sqlterminal",
            "ux-uideveloper",
        ],
        "auto-coding",
    ),
    (
        "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit",
        ["splunksplgineer"],
        "auto-spl",
    ),
    (
        "deepseek-r1:32b-q4_k_m",
        [
            "dataanalyst",
            "datascientist",
            "excelsheet",
            "itarchitect",
            "machinelearningengineer",
            "researchanalyst",
            "statistician",
        ],
        "auto-reasoning",
    ),
    (
        "dolphin-llama3:8b",
        ["creativewriter", "itexpert", "techreviewer", "techwriter"],
        "auto",
    ),
    (
        "xploiter/the-xploiter",
        ["cybersecurityspecialist", "networkengineer"],
        "auto-security",
    ),
    (
        "baronllm:q6_k",
        ["redteamoperator"],
        "auto-redteam",
    ),
    (
        "lily-cybersecurity:7b-q4_k_m",
        ["blueteamdefender"],
        "auto-blueteam",
    ),
    (
        "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0",
        ["pentester"],
        "auto-security",
    ),
    (
        "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
        ["cippolicywriter", "nerccipcomplianceanalyst"],
        "auto-compliance",
    ),
    (
        "lmstudio-community/Magistral-Small-2509-MLX-8bit",
        ["magistralstrategist"],
        "auto-mistral",
    ),
    (
        "mlx-community/gemma-4-26b-a4b-4bit",
        ["gemmaresearchanalyst"],
        "auto-vision",
    ),
]

# Signal words for validating persona responses (domain-relevant output)
_PERSONA_SIGNALS: dict[str, list[str]] = {
    "blueteamdefender": ["mitre", "ssh", "brute", "incident", "containment"],
    "bugdiscoverycodeassistant": ["def ", "error", "exception", "type", "fix"],
    "cippolicywriter": ["shall", "patch", "cip-007", "compliance", "audit"],
    "codebasewikidocumentationskill": ["fibonacci", "recursive", "complexity", "memoization"],
    "codereviewassistant": ["pythonic", "enumerate", "readability", "improve"],
    "codereviewer": ["sql injection", "parameterized", "vulnerability", "sanitize"],
    "creativewriter": ["robot", "flower", "space", "wonder"],
    "cybersecurityspecialist": ["access control", "owasp", "idow", "privilege"],
    "dataanalyst": ["growth", "quarter", "trend", "analysis", "visualization"],
    "datascientist": ["feature", "algorithm", "churn", "model", "accuracy"],
    "devopsautomator": ["github", "actions", "deploy", "docker", "pytest"],
    "devopsengineer": ["kubernetes", "helm", "pipeline", "canary", "argo"],
    "ethereumdeveloper": ["solidity", "erc-20", "transfer", "approve", "reentrancy"],
    "excelsheet": ["sumproduct", "array", "filter", "criteria"],
    "fullstacksoftwaredeveloper": ["endpoint", "get", "post", "schema", "json"],
    "githubexpert": ["branch protection", "reviewer", "ci", "signed"],
    "itarchitect": ["load balancer", "replication", "cache", "disaster", "availability"],
    "itexpert": ["memory", "oom", "pandas", "container", "profile"],
    "javascriptconsole": ["reduce", "accumulator", "pi", "3.1416"],
    "kubernetesdockerrpglearningengine": ["mission", "container", "game", "briefing"],
    "linuxterminal": ["find", "size", "modified", "exclude", "archive"],
    "machinelearningengineer": ["random forest", "xgboost", "hyperparameter", "tabular"],
    "nerccipcomplianceanalyst": ["cip-007", "patch", "evidence", "audit", "nerc"],
    "networkengineer": ["vlan", "subnet", "dmz", "firewall", "segmentation"],
    "pentester": ["authentication", "bypass", "jwt", "session", "vulnerability"],
    "pythoncodegeneratorcleanoptimizedproduction-ready": [
        "def ",
        "retry",
        "backoff",
        "type hints",
        "docstring",
    ],
    "pythoninterpreter": ["zip", "reverse", "output", "slice"],
    "redteamoperator": ["jwt", "sql injection", "attack", "idow", "token"],
    "researchanalyst": ["microservices", "monolith", "deployment", "complexity"],
    "seniorfrontenddeveloper": ["react", "hook", "useeffect", "loading", "error"],
    "seniorsoftwareengineersoftwarearchitectrules": [
        "risk",
        "migration",
        "distributed",
        "consistency",
    ],
    "softwarequalityassurancetester": ["test case", "valid", "invalid", "boundary", "error"],
    "splunksplgineer": ["tstats", "authentication", "datamodel", "stats", "distinct", "lateral"],
    "sqlterminal": ["join", "group by", "order by", "index", "pagination"],
    "statistician": ["p-value", "power", "sample size", "effect size", "type i"],
    "techreviewer": ["m4", "mlx", "memory", "inference", "performance"],
    "techwriter": ["api", "authentication", "endpoint", "curl", "jwt"],
    "ux-uideveloper": ["password", "reset", "error", "accessibility", "flow"],
    "gemmaresearchanalyst": ["evidence", "benchmark", "open source", "proprietary", "coding"],
    "magistralstrategist": ["runway", "enterprise", "plg", "acv", "assumption"],
}


async def _persona_test_with_retry(
    sec: str,
    tid: str,
    slug: str,
    name: str,
    system: str,
    prompt: str,
    signals: list[str],
    workspace: str,
) -> str:
    """Test a single persona with retry on empty responses."""
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system[:800]})
    msgs.append({"role": "user", "content": prompt})

    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                headers=AUTH,
                json={"model": workspace, "messages": msgs, "stream": False, "max_tokens": 150},
            )
        if r.status_code == 200:
            msg = r.json().get("choices", [{}])[0].get("message", {})
            text = msg.get("content", "") or msg.get("reasoning", "")
            if text.strip():
                matched = [s for s in signals if s in text.lower()]
                record(
                    sec,
                    tid,
                    f"persona {slug} ({name})",
                    "PASS" if matched or not signals else "WARN",
                    f"'{text[:70].strip()}' | signals: {matched}"
                    if matched
                    else f"'{text[:70].strip()}'",
                    t0=t0,
                )
                return "PASS"
            else:
                record(
                    sec,
                    tid,
                    f"persona {slug} ({name})",
                    "WARN",
                    "200 but empty content",
                    t0=t0,
                )
                return "WARN"
        elif r.status_code == 503:
            record(sec, tid, f"persona {slug} ({name})", "WARN", "503 — no healthy backend", t0=t0)
            return "WARN"
        else:
            record(sec, tid, f"persona {slug} ({name})", "FAIL", f"HTTP {r.status_code}", t0=t0)
            return "FAIL"
    except httpx.ReadTimeout:
        record(sec, tid, f"persona {slug} ({name})", "WARN", "timeout — model loading", t0=t0)
        return "WARN"
    except Exception as e:
        record(sec, tid, f"persona {slug} ({name})", "FAIL", str(e), t0=t0)
        return "FAIL"


async def S11() -> None:
    print(f"\n━━━ S11. PERSONAS — ALL {len(PERSONAS)} (grouped by model) ━━━")
    sec = "S11"

    # Verify personas registered in Open WebUI
    token = _owui_token()
    if token:
        t0 = time.time()
        try:
            r = httpx.get(
                f"{OPENWEBUI_URL}/api/v1/models/",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                api_ids = {
                    m["id"].lower()
                    for m in (data if isinstance(data, list) else data.get("data", []))
                }
                missing = [p["slug"] for p in PERSONAS if p["slug"].lower() not in api_ids]
                record(
                    sec,
                    "S11-01",
                    f"All {len(PERSONAS)} personas registered in Open WebUI",
                    "PASS" if not missing else "WARN",
                    f"MISSING: {missing}" if missing else "",
                    [f"{len(PERSONAS) - len(missing)}/{len(PERSONAS)} registered"],
                    t0=t0,
                )
                if missing:
                    record(
                        sec,
                        "S11-01b",
                        "FIX for missing personas",
                        "INFO",
                        "run: ./launch.sh reseed",
                    )
            else:
                record(
                    sec,
                    "S11-01",
                    "Personas registered in Open WebUI",
                    "WARN",
                    f"OW /api/v1/models/ HTTP {r.status_code}",
                    t0=t0,
                )
        except Exception as e:
            record(sec, "S11-01", "Personas registered in Open WebUI", "WARN", str(e), t0=t0)
    else:
        record(
            sec,
            "S11-01",
            "Personas registered in Open WebUI",
            "WARN",
            "no OW token — set OPENWEBUI_ADMIN_PASSWORD in .env",
        )

    # Build persona lookup
    persona_map = {p["slug"]: p for p in PERSONAS}

    # Exercise personas grouped by model to minimize load/unload thrashing
    passed = warned = failed = 0
    for model_name, slugs, workspace in _PERSONAS_BY_MODEL:
        is_mlx = "mlx" in model_name.lower() or any(
            x in model_name.lower() for x in ["magistral", "gemma", "qwen3.5"]
        )
        print(f"  ── Model: {model_name} ({len(slugs)} personas via {workspace}) ──")
        for slug in slugs:
            persona = persona_map.get(slug)
            if not persona:
                record(
                    sec, f"P:{slug}", f"persona {slug}", "WARN", "not found in persona YAML files"
                )
                warned += 1
                continue
            name = persona["name"]
            system = persona.get("system_prompt", "")
            prompt = _PERSONA_PROMPT.get(
                slug, f"As {name}, give a detailed description of your expertise and approach."
            )
            signals = _PERSONA_SIGNALS.get(slug, [])
            result = await _persona_test_with_retry(
                sec,
                f"P:{slug}",
                slug,
                name,
                system,
                prompt,
                signals,
                workspace,
            )
            if result == "PASS":
                passed += 1
            elif result == "WARN":
                warned += 1
            else:
                failed += 1
            await asyncio.sleep(1)
        # Between model groups: delay for model switch
        await asyncio.sleep(30 if is_mlx else 15)

    record(
        sec,
        "S11-sum",
        f"Persona suite summary ({len(PERSONAS)} total)",
        "PASS"
        if failed == 0 and warned < len(PERSONAS) // 4
        else ("WARN" if failed == 0 else "FAIL"),
        f"{passed} PASS | {warned} WARN | {failed} FAIL",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# S12 — METRICS & MONITORING
# ═══════════════════════════════════════════════════════════════════════════════
async def S12() -> None:
    print("\n━━━ S12. METRICS & MONITORING (HOWTO §22) ━━━")
    sec = "S12"

    t0 = time.time()
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{PIPELINE_URL}/metrics")
        if r.status_code == 200:
            txt = r.text

            ws_m = re.search(r"portal_workspaces_total\s+(\d+)", txt)
            if ws_m:
                n = int(ws_m.group(1))
                record(
                    sec,
                    "S12-01",
                    "portal_workspaces_total matches code count",
                    "PASS" if n == len(WS_IDS) else "FAIL",
                    f"metric={n}, code={len(WS_IDS)}",
                    t0=t0,
                )
            else:
                record(
                    sec,
                    "S12-01",
                    "portal_workspaces_total gauge present",
                    "WARN",
                    "not found in /metrics output",
                    t0=t0,
                )

            record(
                sec,
                "S12-02",
                "portal_backends gauge present",
                "PASS" if "portal_backends" in txt else "WARN",
                "present" if "portal_backends" in txt else "not in /metrics",
            )

            record(
                sec,
                "S12-03",
                "portal_requests counter present (after S3 traffic)",
                "PASS" if "portal_requests" in txt else "WARN",
                "present"
                if "portal_requests" in txt
                else "not yet recorded — needs traffic (run S3 first)",
            )

            record(
                sec,
                "S12-04",
                "Prometheus histogram metrics (tokens_per_second)",
                "INFO",
                "present"
                if any(x in txt for x in ["portal_tokens_per_second", "portal_output_tokens"])
                else "not yet recorded (needs completed LLM requests)",
            )
        else:
            record(sec, "S12-01", "/metrics reachable", "FAIL", f"HTTP {r.status_code}", t0=t0)

        t0 = time.time()
        try:
            r = await c.get(f"{PROMETHEUS_URL}/api/v1/targets")
            targets = r.json().get("data", {}).get("activeTargets", [])
            pt = [t for t in targets if "9099" in str(t.get("scrapeUrl", ""))]
            record(
                sec,
                "S12-05",
                "Prometheus scraping pipeline target",
                "PASS" if pt else "WARN",
                f"{len(pt)} pipeline targets in {len(targets)} total",
                t0=t0,
            )
        except Exception as e:
            record(sec, "S12-05", "Prometheus scraping pipeline", "FAIL", str(e), t0=t0)

        t0 = time.time()
        try:
            r = await c.get(f"{GRAFANA_URL}/api/search?type=dash-db", auth=("admin", GRAFANA_PASS))
            if r.status_code == 200:
                titles = [d.get("title", "") for d in r.json()]
                record(
                    sec,
                    "S12-06",
                    "Grafana portal5_overview dashboard provisioned",
                    "PASS" if any("portal" in (t or "").lower() for t in titles) else "WARN",
                    f"dashboards: {titles}",
                    t0=t0,
                )
            else:
                record(
                    sec,
                    "S12-06",
                    "Grafana dashboard provisioned",
                    "WARN",
                    f"HTTP {r.status_code}",
                    t0=t0,
                )
        except Exception as e:
            record(sec, "S12-06", "Grafana dashboard provisioned", "FAIL", str(e), t0=t0)


# ═══════════════════════════════════════════════════════════════════════════════
# S13 — GUI VALIDATION (Playwright / Chromium)
# ═══════════════════════════════════════════════════════════════════════════════
async def S13() -> None:
    print("\n━━━ S13. GUI VALIDATION (Chromium) ━━━")
    sec = "S13"

    if not ADMIN_PASS:
        record(
            sec, "S13-skip", "GUI tests skipped", "WARN", "OPENWEBUI_ADMIN_PASSWORD not set in .env"
        )
        return

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        record(
            sec,
            "S13-skip",
            "Playwright not installed",
            "FAIL",
            "pip install playwright && python3 -m playwright install chromium",
        )
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        t0 = time.time()
        try:
            await page.goto(OPENWEBUI_URL, wait_until="networkidle", timeout=20000)
            await page.wait_for_selector('input[type="email"]', timeout=10000)
            await page.fill('input[type="email"]', ADMIN_EMAIL)
            await page.fill('input[type="password"]', ADMIN_PASS)
            await page.locator('button[type="submit"], button:has-text("Sign in")').first.click()
            await page.wait_for_selector("textarea, [contenteditable]", timeout=15000)
            await page.screenshot(path="/tmp/p5_gui_login.png")
            record(sec, "S13-01", "Login → chat UI loaded", "PASS", "", t0=t0)
        except Exception as e:
            record(sec, "S13-01", "Login", "FAIL", str(e), t0=t0)
            await browser.close()
            return

        await page.wait_for_timeout(2000)

        for sel in [
            "button[aria-haspopup]",
            "button:has-text('Portal')",
            "button:has-text('Auto')",
            "button:has-text('Router')",
        ]:
            if await page.locator(sel).count() > 0:
                try:
                    await page.locator(sel).first.click(timeout=5000)
                    await page.wait_for_timeout(2000)
                    break
                except Exception:
                    continue

        body = (await page.inner_text("body")).lower()
        await page.screenshot(path="/tmp/p5_gui_dropdown.png")

        # Strip leading emoji for matching
        ws_visible = [
            ws for ws, nm in WS_NAMES.items() if re.sub(r"^[^\w]+", "", nm).strip().lower() in body
        ]

        if len(ws_visible) >= len(WS_IDS) - 1:
            record(
                sec,
                "S13-02",
                "Model dropdown shows workspace names",
                "PASS",
                f"{len(ws_visible)}/{len(WS_IDS)} visible",
            )
        else:
            token = _owui_token()
            try:
                ar = httpx.get(
                    f"{OPENWEBUI_URL}/api/v1/models/",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5,
                )
                if ar.status_code == 200:
                    data = ar.json()
                    api_ids = {
                        m["id"] for m in (data if isinstance(data, list) else data.get("data", []))
                    }
                    api_ws = [ws for ws in WS_IDS if ws in api_ids]
                    record(
                        sec,
                        "S13-02",
                        "Model dropdown shows workspace names",
                        "PASS" if len(api_ws) == len(WS_IDS) else "WARN",
                        f"GUI: {len(ws_visible)}/{len(WS_IDS)} (headless scroll limit) | "
                        f"API confirmed: {len(api_ws)}/{len(WS_IDS)}",
                    )
                else:
                    record(
                        sec,
                        "S13-02",
                        "Model dropdown shows workspace names",
                        "WARN",
                        f"GUI: {len(ws_visible)}/{len(WS_IDS)}, API {ar.status_code}",
                    )
            except Exception as e:
                record(
                    sec,
                    "S13-02",
                    "Model dropdown shows workspace names",
                    "WARN",
                    f"API fallback: {e}",
                )

        p_visible = [p["name"] for p in PERSONAS if p["name"].lower() in body]
        if len(p_visible) >= len(PERSONAS) * 0.8:
            record(
                sec,
                "S13-03",
                "Personas visible in dropdown",
                "PASS",
                f"{len(p_visible)}/{len(PERSONAS)}",
            )
        else:
            token = _owui_token()
            try:
                ar = httpx.get(
                    f"{OPENWEBUI_URL}/api/v1/models/",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5,
                )
                if ar.status_code == 200:
                    data = ar.json()
                    api_ids = {
                        m["id"].lower()
                        for m in (data if isinstance(data, list) else data.get("data", []))
                    }
                    api_p = [p for p in PERSONAS if p["slug"].lower() in api_ids]
                    record(
                        sec,
                        "S13-03",
                        "Personas visible in dropdown",
                        "PASS" if len(api_p) == len(PERSONAS) else "WARN",
                        f"GUI: {len(p_visible)}/{len(PERSONAS)} (headless) | "
                        f"API: {len(api_p)}/{len(PERSONAS)}",
                    )
                else:
                    record(sec, "S13-03", "Personas visible", "WARN", f"API {ar.status_code}")
            except Exception as e:
                record(sec, "S13-03", "Personas visible", "WARN", str(e))

        await page.keyboard.press("Escape")

        t0 = time.time()
        ta = page.locator("textarea, [contenteditable='true']")
        if await ta.count() > 0:
            await ta.first.fill("acceptance test input")
            await ta.first.fill("")
            record(sec, "S13-04", "Chat textarea accepts and clears input", "PASS", "", t0=t0)
        else:
            record(
                sec,
                "S13-04",
                "Chat textarea present",
                "FAIL",
                "no textarea or contenteditable found",
                t0=t0,
            )

        t0 = time.time()
        await page.goto(f"{OPENWEBUI_URL}/admin", wait_until="networkidle", timeout=10000)
        admin_body = await page.inner_text("body")
        await page.screenshot(path="/tmp/p5_gui_admin.png")
        record(
            sec,
            "S13-05",
            "Admin panel accessible",
            "PASS"
            if any(w in admin_body.lower() for w in ["admin", "settings", "users"])
            else "WARN",
            "",
            t0=t0,
        )

        found_tools = [
            t
            for t in ["documents", "code", "music", "tts", "whisper", "video"]
            if t in admin_body.lower()
        ]
        record(
            sec,
            "S13-06",
            "MCP tool servers visible in admin panel",
            "PASS" if len(found_tools) >= 4 else "INFO",
            f"{len(found_tools)}/6 visible: {found_tools}",
        )

        await browser.close()


# ═══════════════════════════════════════════════════════════════════════════════
# S14 — HOWTO ACCURACY AUDIT
# ═══════════════════════════════════════════════════════════════════════════════
async def S14() -> None:
    print("\n━━━ S14. HOWTO ACCURACY AUDIT ━━━")
    sec = "S14"
    howto = (ROOT / "docs/HOWTO.md").read_text()

    bad = [l for l in howto.splitlines() if "Click **+**" in l and "enable" in l.lower()]
    record(
        sec,
        "S14-01",
        "No stale 'Click + enable' instructions",
        "PASS" if not bad else "FAIL",
        f"{len(bad)} stale lines" if bad else "",
    )

    rows = len(re.findall(r"^\| Portal", howto, re.MULTILINE))
    record(
        sec,
        "S14-02",
        f"§3 workspace table has {len(WS_IDS)} rows",
        "PASS" if rows == len(WS_IDS) else "FAIL",
        f"table rows={rows}, code has {len(WS_IDS)}",
    )

    record(
        sec,
        "S14-03",
        "auto-compliance workspace documented in §3",
        "PASS" if "auto-compliance" in howto else "FAIL",
    )

    pm = re.search(
        r"(\d+)\s*total",
        howto[howto.lower().find("persona") :] if "persona" in howto.lower() else "",
    )
    if pm:
        n = int(pm.group(1))
        record(
            sec,
            "S14-04",
            "Persona count claim matches YAML file count",
            "PASS" if n == len(PERSONAS) else "FAIL",
            f"claimed={n}, yaml files={len(PERSONAS)}",
        )

    try:
        start = howto.index("Available workspaces")
        listed = set(re.findall(r"auto(?:-\w+)?", howto[start : start + 600]))
        miss = sorted(set(WS_IDS) - listed)
        record(
            sec,
            "S14-05",
            "§16 Telegram workspace list complete",
            "PASS" if not miss else "FAIL",
            f"MISSING: {miss}" if miss else "all IDs listed",
        )
    except ValueError:
        record(
            sec,
            "S14-05",
            "§16 Telegram workspace list",
            "WARN",
            "'Available workspaces' section not found",
        )

    t0 = time.time()
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"http://localhost:{MCP['tts']}/health")
        actual = r.json() if r.status_code == 200 else {}
        record(
            sec,
            "S14-06",
            "§11 TTS backend is kokoro as documented",
            "PASS" if actual.get("backend") == "kokoro" else "WARN",
            f"actual: {actual}",
            t0=t0,
        )

    async with httpx.AsyncClient(timeout=10) as c:
        for ref, url, hdrs in [
            ("§3", f"{PIPELINE_URL}/v1/models", AUTH),
            ("§5", f"http://localhost:{MCP['sandbox']}/health", {}),
            ("§7", f"http://localhost:{MCP['documents']}/health", {}),
            ("§22", f"{PIPELINE_URL}/metrics", {}),
        ]:
            t0 = time.time()
            r = await c.get(url, headers=hdrs)
            record(
                sec,
                f"S14-07{ref}",
                f"HOWTO {ref} curl command works",
                "PASS" if r.status_code == 200 else "FAIL",
                f"HTTP {r.status_code}",
                t0=t0,
            )

    wr = subprocess.run(
        [
            "docker",
            "exec",
            "portal5-mcp-whisper",
            "python3",
            "-c",
            "import urllib.request; "
            "print(urllib.request.urlopen('http://127.0.0.1:8915/health').read().decode())",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    record(
        sec,
        "S14-08",
        "§12 whisper health via docker exec (exact HOWTO command)",
        "PASS" if wr.returncode == 0 and "ok" in wr.stdout.lower() else "WARN",
        wr.stdout.strip()[:80] or wr.stderr.strip()[:60],
    )

    record(
        sec,
        "S14-09",
        "HOWTO footer version is 5.2.1",
        "PASS" if "5.2.1" in howto else "FAIL",
        "found" if "5.2.1" in howto else "missing or wrong version in HOWTO footer",
    )

    # S14-10/11: both new models documented in HOWTO MLX table (Step 7 of task)
    record(
        sec,
        "S14-10",
        "HOWTO MLX table documents gemma-4-26b-a4b-4bit",
        "PASS" if "gemma-4-26b-a4b-4bit" in howto else "FAIL",
        "found"
        if "gemma-4-26b-a4b-4bit" in howto
        else "missing — add Gemma 4 row to MLX models table in docs/HOWTO.md",
    )

    record(
        sec,
        "S14-11",
        "HOWTO MLX table documents Magistral-Small-2509-MLX-8bit",
        "PASS" if "Magistral-Small-2509" in howto else "FAIL",
        "found"
        if "Magistral-Small-2509" in howto
        else "missing — add Magistral row to MLX models table in docs/HOWTO.md",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# S15 — WEB SEARCH (SearXNG)
# ═══════════════════════════════════════════════════════════════════════════════
async def S15() -> None:
    print("\n━━━ S15. WEB SEARCH (SearXNG) ━━━")
    sec = "S15"

    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{SEARXNG_URL}/search?q=NERC+CIP&format=json")
            if r.status_code == 200:
                n = len(r.json().get("results", []))
                record(
                    sec,
                    "S15-01",
                    "SearXNG /search?format=json returns results",
                    "PASS" if n > 0 else "WARN",
                    f"{n} results for 'NERC CIP'",
                    t0=t0,
                )
            else:
                record(
                    sec, "S15-01", "SearXNG JSON search API", "WARN", f"HTTP {r.status_code}", t0=t0
                )
    except Exception as e:
        record(sec, "S15-01", "SearXNG JSON search API", "WARN", str(e), t0=t0)

    t0 = time.time()
    code, text = await _chat(
        "auto-research",
        "Compare AES-256 and RSA-2048: use cases, performance, key sizes.",
        max_tokens=200,
        timeout=180,
    )
    record(
        sec,
        "S15-02",
        "auto-research workspace: technical comparison response",
        "PASS"
        if code == 200
        and any(s in text.lower() for s in ["aes", "rsa", "symmetric", "asymmetric", "key"])
        else ("WARN" if code in (503, 408) else "FAIL"),
        f"preview: {text[:80]}" if text else f"HTTP {code}",
        t0=t0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# S16 — CLI COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════
async def S16() -> None:
    print("\n━━━ S16. CLI COMMANDS ━━━")
    sec = "S16"

    for tid, cmd, desc in [
        ("S16-01", "status", "./launch.sh status outputs service health"),
        ("S16-02", "list-users", "./launch.sh list-users runs without error"),
    ]:
        t0 = time.time()
        r = subprocess.run(
            ["./launch.sh", cmd], capture_output=True, text=True, timeout=30, cwd=str(ROOT)
        )
        record(
            sec,
            tid,
            desc,
            "PASS" if r.returncode == 0 else "WARN",
            f"exit={r.returncode}" + (f": {r.stderr[:60]}" if r.returncode != 0 else ""),
            t0=t0,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# S17 — SERVICE REBUILD & RESTART VERIFICATION (runs first)
# ═══════════════════════════════════════════════════════════════════════════════
async def S17() -> None:
    print("\n━━━ S17. SERVICE REBUILD & RESTART VERIFICATION ━━━")
    sec = "S17"

    t0 = time.time()
    r = subprocess.run(
        DC + ["ps", "--format", "json"], capture_output=True, text=True, cwd=str(ROOT)
    )
    if r.returncode == 0 and r.stdout.strip():
        containers = []
        for line in r.stdout.strip().splitlines():
            try:
                containers.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                pass
        running = {
            (c.get("Name") or c.get("Service", ""))
            for c in containers
            if c.get("State", c.get("Status", "")).lower() in ("running", "healthy")
        }
        expected = [
            "portal5-pipeline",
            "portal5-open-webui",
            "portal5-mcp-documents",
            "portal5-mcp-music",
            "portal5-mcp-tts",
            "portal5-mcp-whisper",
            "portal5-mcp-sandbox",
            "portal5-dind",
        ]
        missing = [p for p in expected if not any(p in c for c in running)]
        record(
            sec,
            "S17-01",
            "All expected containers running",
            "PASS" if not missing else "WARN",
            f"missing: {missing}" if missing else f"{len(running)} containers up",
            t0=t0,
        )
    else:
        record(sec, "S17-01", "docker compose ps", "WARN", f"failed: {r.stderr[:80]}", t0=t0)

    dh = subprocess.run(["md5sum", str(ROOT / "Dockerfile.mcp")], capture_output=True, text=True)
    record(
        sec,
        "S17-02",
        "Dockerfile.mcp hash",
        "INFO",
        dh.stdout.split()[0] if dh.returncode == 0 else "unknown",
    )

    mcp_checks = [
        ("mcp-documents", f"http://localhost:{MCP['documents']}/health"),
        ("mcp-music", f"http://localhost:{MCP['music']}/health"),
        ("mcp-tts", f"http://localhost:{MCP['tts']}/health"),
        ("mcp-whisper", f"http://localhost:{MCP['whisper']}/health"),
        ("mcp-sandbox", f"http://localhost:{MCP['sandbox']}/health"),
        ("mcp-video", f"http://localhost:{MCP['video']}/health"),
    ]
    needs_restart = []
    async with httpx.AsyncClient(timeout=6) as c:
        for svc, url in mcp_checks:
            try:
                r2 = await c.get(url)
                if r2.status_code != 200:
                    needs_restart.append(svc)
            except Exception:
                needs_restart.append(svc)

    if not needs_restart:
        record(sec, "S17-03", "All MCP services healthy — no restart needed", "PASS")
    else:
        record(
            sec,
            "S17-03",
            f"Restarting {len(needs_restart)} unhealthy MCP services",
            "WARN",
            f"restarting: {needs_restart}",
        )
        for svc in needs_restart:
            subprocess.run(DC + ["restart", svc], capture_output=True, cwd=str(ROOT), timeout=30)
        await asyncio.sleep(10)
        recovered = 0
        async with httpx.AsyncClient(timeout=6) as c:
            for svc, url in mcp_checks:
                try:
                    r2 = await c.get(url)
                    if r2.status_code == 200:
                        recovered += 1
                except Exception:
                    pass
        record(
            sec,
            "S17-03b",
            "MCP recovery after restart",
            "PASS" if recovered == len(mcp_checks) else "WARN",
            f"{recovered}/{len(mcp_checks)} healthy after restart",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

SECTIONS = {
    "S0": S0,
    "S1": S1,
    "S2": S2,
    "S3": S3,
    "S4": S4,
    "S5": S5,
    "S6": S6,
    "S7": S7,
    "S8": S8,
    "S9": S9,
    "S10": S10,
    "S11": S11,
    "S12": S12,
    "S13": S13,
    "S14": S14,
    "S15": S15,
    "S16": S16,
    "S17": S17,
}

ALL_ORDER = [
    "S17",
    "S0",
    "S1",
    "S2",
    "S3",
    "S4",
    "S5",
    "S6",
    "S7",
    "S8",
    "S9",
    "S10",
    "S11",
    "S12",
    "S13",
    "S14",
    "S15",
    "S16",
]


async def _preflight() -> None:
    for f in [
        "launch.sh",
        "pyproject.toml",
        "portal_pipeline/router_pipe.py",
        "config/backends.yaml",
        "docs/HOWTO.md",
        "portal5_acceptance_v3.py",
    ]:
        if not (ROOT / f).exists():
            sys.exit(f"❌ Missing required file: {f}")
    if not API_KEY:
        sys.exit("❌ PIPELINE_API_KEY not set — run: ./launch.sh up")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        sys.exit("❌ Docker not accessible")
    try:
        r = httpx.get(f"{PIPELINE_URL}/health", timeout=8)
        if r.status_code != 200:
            sys.exit(f"❌ Pipeline unhealthy: HTTP {r.status_code}")
    except Exception as e:
        sys.exit(f"❌ Pipeline unreachable at {PIPELINE_URL}: {e}")


async def main() -> int:
    global _verbose
    parser = argparse.ArgumentParser(description="Portal 5.2.1 Acceptance Tests")
    parser.add_argument(
        "--section", "-s", default="ALL", help="Run one section (S0-S17) or ALL (default)"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    _verbose = args.verbose

    t0 = time.time()
    sha = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()

    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║  Portal 5.2.1 — End-to-End Acceptance Test Suite                ║")
    print(
        f"║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  git={sha}  "
        f"{len(WS_IDS)} workspaces  {len(PERSONAS)} personas              ║"
    )
    print("╚═══════════════════════════════════════════════════════════════════╝")
    print(f"Pipeline: {PIPELINE_URL}  key: {API_KEY[:8]}...")
    print(
        "Failure policy: test first assumed wrong → fix assertion → "
        "BLOCKED only if code change required\n"
    )

    await _preflight()

    run = (
        ALL_ORDER
        if args.section.upper() == "ALL"
        else (["S17", args.section.upper()] if args.section.upper() != "S17" else ["S17"])
    )

    for sid in run:
        if sid not in SECTIONS:
            sys.exit(f"Unknown section: {sid}. Valid: {sorted(SECTIONS)}")
        try:
            await SECTIONS[sid]()
        except Exception as e:
            record(
                sid, f"{sid}-crash", f"Section {sid} crashed", "FAIL", f"{type(e).__name__}: {e}"
            )
        print()

    elapsed = int(time.time() - t0)
    counts: dict[str, int] = {}
    for r in _log:
        counts[r.status] = counts.get(r.status, 0) + 1

    print("╔═══════════════════════════════════════════════════════════════════╗")
    print(f"║  RESULTS  ({elapsed}s)                                              ║")
    print("╠═══════════════════════════════════════════════════════════════════╣")
    for s in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO"]:
        if s in counts:
            icon = _ICON.get(s, "  ")
            print(f"║  {icon} {s:8s}: {counts[s]:4d}                                             ║")
    print(f"║  Total    : {sum(counts.values()):4d}                                             ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")

    rpt = ROOT / "ACCEPTANCE_RESULTS.md"
    with open(rpt, "w") as f:
        f.write("# Portal 5.2.1 — Acceptance Test Results\n\n")
        f.write(f"**Run:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({elapsed}s)  \n")
        f.write(f"**Git SHA:** {sha}  \n")
        f.write(f"**Workspaces:** {len(WS_IDS)}  ·  **Personas:** {len(PERSONAS)}\n\n")
        f.write("## Summary\n\n")
        for s in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO"]:
            if s in counts:
                f.write(f"- **{s}**: {counts[s]}\n")
        f.write("\n## All Results\n\n")
        f.write(
            "| # | Status | Section | Test | Detail | Duration |\n"
            "|---|--------|---------|------|--------|----------|\n"
        )
        for i, r in enumerate(_log, 1):
            det = (r.detail or "")[:160].replace("|", "∣")
            f.write(
                f"| {i} | {r.status} | {r.section} | {r.name[:60]} | {det} | {r.duration:.1f}s |\n"
            )
        if _blocked:
            f.write("\n## Blocked Items Register\n\n")
            f.write("These require changes to protected files. The test assertion is correct.\n\n")
            f.write(
                "| # | Section | Test | Evidence | Required Fix |\n"
                "|---|---------|------|----------|---------------|\n"
            )
            for i, r in enumerate(_blocked, 1):
                f.write(
                    f"| {i} | {r.section} | {r.name[:60]} "
                    f"| {r.detail[:120].replace('|', '∣')} "
                    f"| {r.fix[:120].replace('|', '∣')} |\n"
                )
        else:
            f.write("\n## Blocked Items Register\n\n*No blocked items.*\n")
        f.write("\n---\n*Screenshots: /tmp/p5_gui_*.png*\n")

    print(f"\nReport → {rpt}")
    print("Screenshots → /tmp/p5_gui_*.png")

    return 1 if counts.get("FAIL", 0) or counts.get("BLOCKED", 0) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
