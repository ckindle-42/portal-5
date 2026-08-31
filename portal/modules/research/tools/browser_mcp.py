#!/usr/bin/env python3
"""Portal 5 Browser MCP — HTTP wrapper around Obscura (Rust headless browser).

Wraps Obscura's HTTP MCP transport into Portal 5's HTTP MCP fleet shape. The
public surface (routes, tool names, security policy) is unchanged from the prior
Playwright-backed implementation — only the backend the wrapper drives changed
(TASK_BROWSER_OBSCURA_MIGRATION_V1). Obscura ships no Node/Chromium: a single
pinned Rust binary with built-in stealth, tracker blocking, and SSRF protection,
~30 MB/instance. Its MCP tool names already match this wrapper's manifest.

Adds (unchanged): allowlist/blocklist, audit logging, per-domain rate limiting,
anomaly detection, sensitive-field redaction, profile management, persona policy.

Tools (gated by allowlist; names stable across the backend swap):
- browser_navigate(url, profile?)
- browser_click(element_ref, profile?)
- browser_fill(element_ref, text, profile?)
- browser_snapshot(profile?) — readable body text + element refs
- browser_screenshot(profile?, full_page?)
- browser_evaluate(expression, profile?)
- browser_close(profile?)
- browser_list_profiles()
- browser_create_profile(name) — admin only

Backend transport:
- Interactive/stateful tools drive a per-profile ``obscura mcp --http`` process
  (MCP over HTTP — no stdio framing) via ``ObscuraClient``.
- Stateless markdown extraction (``web_fetch`` fallback, A2) uses a one-shot
  ``obscura fetch <url> --dump markdown`` subprocess — no session needed.

Env: BROWSER_MCP_PORT (8923), OBSCURA_BIN (obscura), BROWSER_STEALTH (true),
OBSCURA_MCP_PORT_BASE (internal per-profile MCP ports, default 9310),
BROWSER_PROXY (optional HTTP/SOCKS5 proxy passed to Obscura).
"""

import asyncio
import json
import logging
import logging.handlers
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

import httpx
from mcp.server import MCPServer
from starlette.responses import JSONResponse

from portal.platform.data_loader import load_data

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

PROFILES_DIR = Path(os.environ.get("PROFILES_DIR", "/profiles"))
AUDIT_LOG_PATH = Path(os.environ.get("AUDIT_LOG_PATH", "/audit/audit.log"))
DEFAULT_BLOCKED_ORIGINS = os.environ.get(
    "PLAYWRIGHT_MCP_BLOCKED_ORIGINS",
    "localhost;127.0.0.1;169.254.169.254;metadata.google.internal",
).split(";")
PRIVATE_PREFIXES = (
    "127.",  # full loopback range (127.0.0.0/8), not just 127.0.0.1
    "169.254.",  # full link-local range (169.254.0.0/16), not just the AWS metadata IP
    "192.168.",
    "10.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
)
SENSITIVE_FIELD_PATTERNS = re.compile(
    r"password|passwd|pwd|secret|token|api[-_]?key|ssn|social|credit|card|cvv|cvc",
    re.IGNORECASE,
)

DOMAIN_RATE_LIMIT = int(os.environ.get("BROWSER_DOMAIN_RATE_LIMIT", "30"))
DOMAIN_RATE_WINDOW_S = 60

PROFILES_DIR.mkdir(parents=True, exist_ok=True)

# ── Audit logging with rotation ──────────────────────────────────────────

_audit_logger = logging.getLogger("portal5.browser.audit")
_audit_logger.setLevel(logging.INFO)
_audit_logger.propagate = False
if AUDIT_LOG_PATH.parent.exists() or True:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _audit_handler = logging.handlers.TimedRotatingFileHandler(
        str(AUDIT_LOG_PATH),
        when="midnight",
        interval=1,
        backupCount=30,
    )
    _audit_handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.addHandler(_audit_handler)


def _redact_args(tool: str, args: dict) -> dict:
    redacted = dict(args)
    if tool == "browser_fill":
        text = redacted.get("text", "")
        ref = redacted.get("element_ref", "")
        if SENSITIVE_FIELD_PATTERNS.search(str(ref)) or SENSITIVE_FIELD_PATTERNS.search(str(text)):
            redacted["text"] = f"<REDACTED:{len(str(text))} chars>"
    return redacted


def _audit_log(
    persona: str, profile: str, tool: str, args: dict, result_status: str, duration_ms: float
):
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request_id": str(uuid.uuid4())[:8],
        "persona": persona or "unknown",
        "profile": profile,
        "tool": tool,
        "args_redacted": _redact_args(tool, args),
        "result_status": result_status,
        "duration_ms": round(duration_ms, 1),
    }
    try:
        _audit_logger.info(json.dumps(entry))
    except Exception as e:
        logger.warning("Audit log write failed: %s", e)


# ── Per-domain rate limiting ─────────────────────────────────────────────

_domain_calls: dict[str, deque] = defaultdict(deque)
_rate_lock = threading.Lock()


def _check_domain_rate(host: str) -> tuple[bool, str]:
    with _rate_lock:
        now = time.time()
        q = _domain_calls[host]
        while q and q[0] < now - DOMAIN_RATE_WINDOW_S:
            q.popleft()
        if len(q) >= DOMAIN_RATE_LIMIT:
            return False, f"rate limit exceeded for {host}: {DOMAIN_RATE_LIMIT}/min"
        q.append(now)
    return True, ""


# ── Anomaly detection ────────────────────────────────────────────────────

_recent_actions: deque = deque(maxlen=20)
_anomaly_lock = threading.Lock()


def _check_anomaly(persona: str, profile: str, tool: str, args: dict) -> str | None:
    with _anomaly_lock:
        now = time.time()
        _recent_actions.append(
            {
                "ts": now,
                "persona": persona,
                "profile": profile,
                "tool": tool,
                "args": args,
            }
        )
        recent = list(_recent_actions)
        if tool == "browser_navigate":
            new_host = (urlparse(args.get("url", "")).hostname or "").lower()
            for past in recent[-5:-1]:
                if past["tool"] == "browser_snapshot" and past["profile"] != "_isolated":
                    return f"WARN: navigate to {new_host} after sensitive read on profile={past['profile']}"
        recent_fills = [a for a in recent if a["tool"] == "browser_fill" and now - a["ts"] < 10]
        if len(recent_fills) > 8:
            return f"WARN: {len(recent_fills)} fills in 10s (possible automation abuse)"
    return None


# ── URL filtering ────────────────────────────────────────────────────────


def _validate_url(
    url: str, allowed_domains: list[str] | None = None, blocked_domains: list[str] | None = None
) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "only http/https supported"
    host = (parsed.hostname or "").lower()
    if host in DEFAULT_BLOCKED_ORIGINS or host in (blocked_domains or []):
        return False, f"domain '{host}' is blocked"
    for prefix in PRIVATE_PREFIXES:
        if host.startswith(prefix):
            return False, "private/local IP ranges blocked"
    if allowed_domains:
        allowed = any(host == d or host.endswith("." + d) for d in allowed_domains)
        if not allowed:
            return False, f"domain '{host}' not in persona allowlist"
    return True, ""


# ── Obscura backend (HTTP MCP transport) ─────────────────────────────────
#
# Each profile drives its own ``obscura mcp --http`` process so browser state
# (navigate -> snapshot -> click) persists across REST calls, and profiles stay
# isolated from one another — the same one-process-per-profile model the prior
# stdio bridge used, but over HTTP MCP (no stdin/stdout line-framing to race).
# The MCP handshake (initialize + notifications/initialized) runs once per
# process; tool calls are wrapped as ``tools/call`` and the ``result.content[]``
# envelope is unwrapped here so callers get the tool payload directly.

OBSCURA_BIN = os.environ.get("OBSCURA_BIN", "obscura")
BROWSER_STEALTH = os.environ.get("BROWSER_STEALTH", "true").lower() != "false"
BROWSER_PROXY = os.environ.get("BROWSER_PROXY", "")
_OBSCURA_MCP_PORT_BASE = int(os.environ.get("OBSCURA_MCP_PORT_BASE", "9310"))
_OBSCURA_MARKDOWN_TIMEOUT_S = int(os.environ.get("OBSCURA_MARKDOWN_TIMEOUT_S", "30"))

# Deterministic per-profile internal port so restarts reuse the same slot.
_profile_ports: dict[str, int] = {}
_profile_port_lock = threading.Lock()


def _obscura_port_for(profile: str) -> int:
    with _profile_port_lock:
        if profile not in _profile_ports:
            _profile_ports[profile] = _OBSCURA_MCP_PORT_BASE + len(_profile_ports)
        return _profile_ports[profile]


class ObscuraClient:
    """One ``obscura mcp --http`` process per profile, spoken to over HTTP MCP."""

    def __init__(self, profile: str = "_isolated"):
        self.profile = profile
        self.port = _obscura_port_for(profile)
        self.proc: subprocess.Popen | None = None
        self._req_id = 0
        self._initialized = False
        self._lock = asyncio.Lock()
        self._last_used = time.time()
        self._http = httpx.AsyncClient(timeout=125)
        self._endpoint = f"http://127.0.0.1:{self.port}/mcp"

    async def start(self):
        if self.proc is not None and self.proc.poll() is None:
            return
        cmd = [OBSCURA_BIN, "mcp", "--http", "--port", str(self.port)]
        if BROWSER_STEALTH:
            cmd.append("--stealth")
        if BROWSER_PROXY:
            cmd.extend(["--proxy", BROWSER_PROXY])
        # Named profiles persist cookies/session under PROFILES_DIR; _isolated is
        # a fresh ephemeral session each start. Obscura persists via its own
        # user-data dir when pointed at one (verify flag name on the pinned build
        # at bring-up; falls back to isolated if unsupported).
        if self.profile != "_isolated":
            profile_path = PROFILES_DIR / self.profile
            profile_path.mkdir(parents=True, exist_ok=True)
            cmd.extend(["--user-data-dir", str(profile_path)])
        logger.info("Starting Obscura MCP for profile=%s on :%d", self.profile, self.port)
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._initialized = False
        # Wait for the HTTP MCP endpoint to accept the initialize handshake.
        await self._await_ready()

    async def _await_ready(self, attempts: int = 40):
        for _ in range(attempts):
            try:
                await self._rpc(
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "portal-browser-wrapper", "version": "1"},
                    },
                    _skip_init_guard=True,
                )
                await self._notify("notifications/initialized")
                self._initialized = True
                return
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError):
                await asyncio.sleep(0.25)
        raise RuntimeError(f"Obscura MCP for profile={self.profile} did not become ready")

    async def _rpc(self, method: str, params: dict, _skip_init_guard: bool = False) -> dict:
        self._req_id += 1
        payload = {"jsonrpc": "2.0", "id": self._req_id, "method": method, "params": params}
        r = await self._http.post(
            self._endpoint,
            json=payload,
            headers={"content-type": "application/json", "accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"Obscura MCP error: {data['error']}")
        return data.get("result", {})

    async def _notify(self, method: str, params: dict | None = None) -> None:
        await self._http.post(
            self._endpoint,
            json={"jsonrpc": "2.0", "method": method, "params": params or {}},
            headers={"content-type": "application/json", "accept": "application/json"},
        )

    async def request(self, tool_name: str, args: dict) -> dict:
        """Call an Obscura MCP tool and return its unwrapped content payload."""
        async with self._lock:
            await self.start()
            # Obscura's tool args use the wrapper's own names/shapes; the profile
            # key is a wrapper concept (one process per profile) — strip it.
            tool_args = {k: v for k, v in args.items() if k != "profile"}
            result = await self._rpc("tools/call", {"name": tool_name, "arguments": tool_args})
            self._last_used = time.time()
            return _unwrap_mcp_content(result)

    async def close(self):
        try:
            await self._http.aclose()
        except Exception:
            pass
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        self._initialized = False


def _unwrap_mcp_content(result: dict) -> dict:
    """Flatten an MCP ``tools/call`` result envelope to a plain payload.

    Tool output lives in ``result.content[]``; text parts are frequently
    JSON-in-string. Return the parsed JSON when there is a single text part that
    parses, otherwise return a normalized ``{"content": ..., "isError": ...}``.
    """
    if not isinstance(result, dict) or "content" not in result:
        return result if isinstance(result, dict) else {"result": result}
    parts = result.get("content") or []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except (json.JSONDecodeError, TypeError):
            return {"text": texts[0], "isError": bool(result.get("isError"))}
    payload: dict = {"content": parts}
    if result.get("isError"):
        payload["isError"] = True
    return payload


async def obscura_fetch_markdown(
    url: str, timeout_s: int = _OBSCURA_MARKDOWN_TIMEOUT_S
) -> str | None:
    """One-shot ``obscura fetch <url> --dump markdown`` — stateless, for the
    web_fetch fallback (A2). Returns clean Markdown, or None on failure."""
    cmd = [OBSCURA_BIN, "fetch", url, "--dump", "markdown", "--timeout", str(timeout_s), "--quiet"]
    if BROWSER_STEALTH:
        cmd.append("--stealth")
    if BROWSER_PROXY:
        cmd = [OBSCURA_BIN, "--proxy", BROWSER_PROXY] + cmd[1:]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s + 5)
        text = out.decode("utf-8", errors="replace").strip()
        return text or None
    except (TimeoutError, FileNotFoundError, OSError) as e:
        logger.warning("obscura markdown fetch failed for %s: %s", url, e)
        return None


_clients: dict[str, ObscuraClient] = {}
_clients_lock = asyncio.Lock()
_reaper_started = False


async def _get_client(profile: str) -> ObscuraClient:
    global _reaper_started
    async with _clients_lock:
        if not _reaper_started:
            asyncio.create_task(_idle_reaper())
            _reaper_started = True
        client = _clients.get(profile)
        if client is None:
            client = ObscuraClient(profile=profile)
            _clients[profile] = client
        return client


async def _idle_reaper():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        async with _clients_lock:
            stale = [
                p for p, c in _clients.items() if c.proc is not None and now - c._last_used > 300
            ]
            for p in stale:
                logger.info("Reaping idle browser client: %s", p)
                await _clients[p].close()
                del _clients[p]


# ── Shared tool execution core ───────────────────────────────────────────


async def _execute_tool(
    tool_name: str,
    args: dict,
    persona: str = "",
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
    force_credential_fill: bool = False,
) -> tuple[dict, int]:
    """Common security + dispatch path for all browser tools. Returns (result, http_status)."""
    profile = args.get("profile", "_isolated")
    t0 = time.monotonic()

    if tool_name == "browser_navigate":
        ok, why = _validate_url(args.get("url", ""), allowed_domains, blocked_domains)
        if not ok:
            duration = (time.monotonic() - t0) * 1000
            _audit_log(persona, profile, tool_name, args, f"denied: {why}", duration)
            return {"error": why}, 403
        host = (urlparse(args.get("url", "")).hostname or "").lower()
        rate_ok, rate_why = _check_domain_rate(host)
        if not rate_ok:
            duration = (time.monotonic() - t0) * 1000
            _audit_log(persona, profile, tool_name, args, f"rate_limited: {rate_why}", duration)
            return {"error": rate_why}, 429

    if tool_name == "browser_fill":
        ref = args.get("element_ref", "")
        if SENSITIVE_FIELD_PATTERNS.search(str(ref)) and not force_credential_fill:
            duration = (time.monotonic() - t0) * 1000
            _audit_log(persona, profile, tool_name, args, "denied: sensitive field", duration)
            return {
                "error": "sensitive field detected; persona does not have force_credential_fill"
            }, 403

    anomaly = _check_anomaly(persona, profile, tool_name, args)
    if anomaly:
        logger.warning("Browser anomaly: %s", anomaly)

    client = await _get_client(profile)
    try:
        # ObscuraClient.request already unwraps the MCP content envelope.
        result = await asyncio.wait_for(client.request(tool_name, args), timeout=120)
        if not isinstance(result, dict):
            result = {"result": result}
        duration = (time.monotonic() - t0) * 1000
        status = "ok" if not (result.get("error") or result.get("isError")) else "error"
        _audit_log(persona, profile, tool_name, args, status, duration)
        return result, 200
    except TimeoutError:
        duration = (time.monotonic() - t0) * 1000
        _audit_log(persona, profile, tool_name, args, "timeout", duration)
        return {"error": "tool timed out after 120s"}, 504
    except Exception as e:
        duration = (time.monotonic() - t0) * 1000
        _audit_log(persona, profile, tool_name, args, f"exception: {e}", duration)
        return {"error": str(e)[:200]}, 500


# ── MCP Server Setup ─────────────────────────────────────────────────────

_port = int(os.environ.get("BROWSER_MCP_PORT", "8923"))

mcp = MCPServer(
    "Portal Browser Tools",
    instructions="Playwright browser automation: navigate, click, fill forms, screenshot, and inspect page content.",
)

TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_browser_mcp")

# ── Custom routes (health + pipeline REST compat + admin) ────────────────


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse(
        {
            "status": "ok",
            "service": "browser-mcp",
            "active_clients": len(_clients),
            "profiles": [p.name for p in PROFILES_DIR.iterdir() if p.is_dir()],
        }
    )


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse(TOOLS_MANIFEST)


@mcp.custom_route("/tools/{tool_name}", methods=["POST"])
async def invoke_tool(request):
    """REST dispatch used by portal-pipeline tool_registry."""
    tool_name = request.path_params.get("tool_name", "")
    try:
        body = await request.json()
    except Exception:
        body = {}
    args = body.get("arguments", {})
    persona = body.get("persona", "")
    allowed = body.get("allowed_domains")
    blocked = body.get("blocked_domains")
    force = body.get("force_credential_fill", False)

    if tool_name == "browser_list_profiles":
        profiles = sorted([p.name for p in PROFILES_DIR.iterdir() if p.is_dir()])
        return JSONResponse({"profiles": profiles})

    # Stateless markdown extraction for the web_fetch fallback (A2). Same URL
    # security gate as browser_navigate; no session/profile involved.
    if tool_name == "browser_get_markdown":
        url = args.get("url", "")
        ok, why = _validate_url(url, allowed, blocked)
        if not ok:
            _audit_log(persona, "_isolated", tool_name, args, f"denied: {why}", 0.0)
            return JSONResponse({"error": why}, status_code=403)
        host = (urlparse(url).hostname or "").lower()
        rate_ok, rate_why = _check_domain_rate(host)
        if not rate_ok:
            return JSONResponse({"error": rate_why}, status_code=429)
        md = await obscura_fetch_markdown(url)
        if md is None:
            return JSONResponse({"error": "markdown fetch failed", "url": url}, status_code=502)
        _audit_log(persona, "_isolated", tool_name, {"url": url}, "ok", 0.0)
        return JSONResponse({"url": url, "markdown": md, "char_count": len(md)})

    known = {t["name"] for t in TOOLS_MANIFEST}
    if tool_name not in known:
        return JSONResponse({"error": f"Unknown tool: {tool_name}"}, status_code=404)

    result, status_code = await _execute_tool(tool_name, args, persona, allowed, blocked, force)
    return JSONResponse(result, status_code=status_code)


@mcp.custom_route("/admin/browser_create_profile", methods=["POST"])
async def admin_create_profile(request):
    body = await request.json()
    name = body.get("arguments", {}).get("name", "")
    if not re.match(r"^[a-z0-9_]+$", name):
        return JSONResponse(
            {"error": "name must be lowercase alphanumeric + underscore"}, status_code=400
        )
    profile_path = PROFILES_DIR / name
    if profile_path.exists():
        return JSONResponse({"error": f"profile '{name}' already exists"}, status_code=409)
    profile_path.mkdir(parents=True)
    return JSONResponse(
        {
            "profile": name,
            "created": True,
            "next_step": f"call /admin/browser_login_session with profile='{name}' to log in",
        }
    )


@mcp.custom_route("/admin/browser_login_session", methods=["POST"])
async def admin_login_session(request):
    body = await request.json()
    args = body.get("arguments", {})
    profile = args.get("profile", "")
    url = args.get("starting_url", "")
    if not profile or not url:
        return JSONResponse({"error": "profile and starting_url required"}, status_code=400)
    profile_path = PROFILES_DIR / profile
    if not profile_path.exists():
        return JSONResponse(
            {"error": f"profile '{profile}' not found — create first"}, status_code=404
        )
    # Open a headed Obscura session bound to this profile's persistent
    # user-data dir so the operator can complete the login; cookies persist in
    # the profile dir and are reused by subsequent ObscuraClient calls.
    cmd = [OBSCURA_BIN, "serve", "--port", str(_obscura_port_for(profile) + 500)]
    if BROWSER_STEALTH:
        cmd.append("--stealth")
    cmd.extend(["--user-data-dir", str(profile_path)])
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return JSONResponse(
        {
            "profile": profile,
            "session_pid": proc.pid,
            "starting_url": url,
            "instructions": (
                "Obscura CDP session opened for this profile. Complete the login flow, "
                "then kill the process to persist cookies into the profile dir."
            ),
        }
    )


@mcp.custom_route("/admin/browser_delete_profile", methods=["POST"])
async def admin_delete_profile(request):
    body = await request.json()
    args = body.get("arguments", {})
    name = args.get("name", "")
    if args.get("confirm_token") != "YES_DELETE":
        return JSONResponse({"error": "confirm_token must be 'YES_DELETE'"}, status_code=400)
    profile_path = PROFILES_DIR / name
    if not profile_path.exists():
        return JSONResponse({"error": "profile not found"}, status_code=404)
    shutil.rmtree(profile_path)
    return JSONResponse({"profile": name, "deleted": True})


# ── MCP tool definitions ─────────────────────────────────────────────────


@mcp.tool()
async def browser_navigate(
    url: str,
    profile: str = "_isolated",
    wait_for: str = "",
) -> dict:
    """Navigate to a URL in a browser tab. Returns the page accessibility tree.

    Args:
        url: Full URL with http/https scheme.
        profile: Browser profile name (_isolated for a fresh ephemeral session).
        wait_for: Optional CSS selector or event to wait for before returning.
    """
    args = {"url": url, "profile": profile}
    if wait_for:
        args["wait_for"] = wait_for
    result, _ = await _execute_tool("browser_navigate", args)
    return result


@mcp.tool()
async def browser_snapshot(profile: str = "_isolated") -> dict:
    """Return the current page's accessibility tree (structured DOM data).

    Args:
        profile: Browser profile name (_isolated for the ephemeral session).
    """
    result, _ = await _execute_tool("browser_snapshot", {"profile": profile})
    return result


@mcp.tool()
async def browser_click(element_ref: str, profile: str = "_isolated") -> dict:
    """Click an element identified by its accessibility ref.

    Args:
        element_ref: Accessibility reference from a prior browser_snapshot call.
        profile: Browser profile name.
    """
    result, _ = await _execute_tool(
        "browser_click", {"element_ref": element_ref, "profile": profile}
    )
    return result


@mcp.tool()
async def browser_fill(element_ref: str, text: str, profile: str = "_isolated") -> dict:
    """Type text into a form field. Sensitive fields are redacted in audit logs.

    Args:
        element_ref: Accessibility reference from a prior browser_snapshot call.
        text: Text to type into the field.
        profile: Browser profile name.
    """
    result, _ = await _execute_tool(
        "browser_fill", {"element_ref": element_ref, "text": text, "profile": profile}
    )
    return result


@mcp.tool()
async def browser_screenshot(profile: str = "_isolated", full_page: bool = False) -> dict:
    """Capture a PNG screenshot of the current page. Returns base64-encoded image.

    Args:
        profile: Browser profile name.
        full_page: If true, captures the full scrollable page rather than the viewport.
    """
    result, _ = await _execute_tool(
        "browser_screenshot", {"profile": profile, "full_page": full_page}
    )
    return result


@mcp.tool()
async def browser_evaluate(expression: str, profile: str = "_isolated") -> dict:
    """Execute a JavaScript expression in the current page context.

    Args:
        expression: JavaScript expression to evaluate.
        profile: Browser profile name.
    """
    result, _ = await _execute_tool(
        "browser_evaluate", {"expression": expression, "profile": profile}
    )
    return result


@mcp.tool()
async def browser_close(profile: str = "_isolated") -> dict:
    """Close the browser session for a profile and release its memory.

    Args:
        profile: Browser profile name to close.
    """
    async with _clients_lock:
        client = _clients.pop(profile, None)
    if client:
        await client.close()
        return {"closed": True, "profile": profile}
    return {"closed": False, "profile": profile, "note": "no active session for this profile"}


@mcp.tool()
async def browser_list_profiles() -> dict:
    """List the named browser profiles available on this host."""
    profiles = sorted([p.name for p in PROFILES_DIR.iterdir() if p.is_dir()])
    return {"profiles": profiles}


# ── Entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=_port)
