#!/usr/bin/env python3
"""Portal 5 Browser MCP — HTTP wrapper around Microsoft @playwright/mcp.

Wraps the stdio-only @playwright/mcp into Portal 5's HTTP MCP fleet shape.
Adds: allowlist/blocklist, audit logging, profile management, persona policy.

Tools (subset of MS Playwright MCP, gated by allowlist):
- browser_navigate(url, profile?)
- browser_click(element_ref, profile?)
- browser_fill(element_ref, text, profile?)
- browser_snapshot(profile?) — accessibility tree
- browser_screenshot(profile?, full_page?)
- browser_evaluate(expression, profile?)
- browser_close(profile?)
- browser_list_profiles()
- browser_create_profile(name) — admin only

Port: 8923 (BROWSER_MCP_PORT env override).
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
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

PROFILES_DIR = Path(os.environ.get("PROFILES_DIR", "/profiles"))
AUDIT_LOG_PATH = Path(os.environ.get("AUDIT_LOG_PATH", "/audit/audit.log"))
DEFAULT_BLOCKED_ORIGINS = os.environ.get(
    "PLAYWRIGHT_MCP_BLOCKED_ORIGINS",
    "localhost;127.0.0.1;169.254.169.254;metadata.google.internal",
).split(";")
PRIVATE_PREFIXES = (
    "192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
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
        str(AUDIT_LOG_PATH), when="midnight", interval=1, backupCount=30,
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


def _audit_log(persona: str, profile: str, tool: str,
               args: dict, result_status: str, duration_ms: float):
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
        _recent_actions.append({
            "ts": now, "persona": persona, "profile": profile,
            "tool": tool, "args": args,
        })
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

def _validate_url(url: str, allowed_domains: list[str] | None = None,
                  blocked_domains: list[str] | None = None) -> tuple[bool, str]:
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


# ── Microsoft Playwright MCP stdio bridge ────────────────────────────────

class PlaywrightStdioClient:
    def __init__(self, profile: str = "_isolated"):
        self.profile = profile
        self.proc: subprocess.Popen | None = None
        self._req_id = 0
        self._lock = asyncio.Lock()
        self._last_used = time.time()

    async def start(self):
        if self.proc is not None and self.proc.poll() is None:
            return
        cmd = ["npx", "@playwright/mcp@latest", "--browser", "chromium"]
        if self.profile == "_isolated":
            cmd.append("--isolated")
        else:
            profile_path = PROFILES_DIR / self.profile
            profile_path.mkdir(parents=True, exist_ok=True)
            cmd.extend(["--user-data-dir", str(profile_path)])
        if os.environ.get("BROWSER_HEADLESS", "true").lower() != "false":
            cmd.append("--headless")
        cmd.extend(["--blocked-origins", ";".join(DEFAULT_BLOCKED_ORIGINS)])
        logger.info("Starting Playwright MCP for profile=%s", self.profile)
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            bufsize=0,
        )

    async def request(self, method: str, params: dict) -> dict:
        async with self._lock:
            await self.start()
            self._req_id += 1
            req = {"jsonrpc": "2.0", "id": self._req_id, "method": method, "params": params}
            line = (json.dumps(req) + "\n").encode()
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
            resp_line = await asyncio.get_event_loop().run_in_executor(
                None, self.proc.stdout.readline
            )
            self._last_used = time.time()
            return json.loads(resp_line.decode())

    async def close(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


_clients: dict[str, PlaywrightStdioClient] = {}
_clients_lock = asyncio.Lock()


async def _get_client(profile: str) -> PlaywrightStdioClient:
    async with _clients_lock:
        client = _clients.get(profile)
        if client is None:
            client = PlaywrightStdioClient(profile=profile)
            _clients[profile] = client
        return client


async def _idle_reaper():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        async with _clients_lock:
            stale = [p for p, c in _clients.items()
                     if c.proc is not None and now - c._last_used > 300]
            for p in stale:
                logger.info("Reaping idle browser client: %s", p)
                await _clients[p].close()
                del _clients[p]


# ── HTTP API ─────────────────────────────────────────────────────────────

async def health(request):
    return JSONResponse({
        "status": "ok",
        "service": "browser-mcp",
        "active_clients": len(_clients),
        "profiles": [p.name for p in PROFILES_DIR.iterdir() if p.is_dir()],
    })


TOOLS_MANIFEST = [
    {
        "name": "browser_navigate",
        "description": "Navigate to a URL in a browser tab. Returns the page accessibility tree.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL with http/https scheme"},
                "profile": {"type": "string", "default": "_isolated"},
                "wait_for": {"type": "string", "default": ""},
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_snapshot",
        "description": "Return the current page's accessibility tree (structured DOM data).",
        "parameters": {
            "type": "object",
            "properties": {"profile": {"type": "string", "default": "_isolated"}},
        },
    },
    {
        "name": "browser_click",
        "description": "Click an element identified by its accessibility ref.",
        "parameters": {
            "type": "object",
            "properties": {
                "element_ref": {"type": "string"},
                "profile": {"type": "string", "default": "_isolated"},
            },
            "required": ["element_ref"],
        },
    },
    {
        "name": "browser_fill",
        "description": "Type text into a form field. Sensitive fields are redacted in logs.",
        "parameters": {
            "type": "object",
            "properties": {
                "element_ref": {"type": "string"},
                "text": {"type": "string"},
                "profile": {"type": "string", "default": "_isolated"},
            },
            "required": ["element_ref", "text"],
        },
    },
    {
        "name": "browser_screenshot",
        "description": "Capture a PNG screenshot. Returns base64.",
        "parameters": {
            "type": "object",
            "properties": {
                "profile": {"type": "string", "default": "_isolated"},
                "full_page": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "browser_evaluate",
        "description": "Execute a JavaScript expression in the page context.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"},
                "profile": {"type": "string", "default": "_isolated"},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "browser_close",
        "description": "Close the browser session for a profile. Releases memory.",
        "parameters": {
            "type": "object",
            "properties": {"profile": {"type": "string", "default": "_isolated"}},
        },
    },
    {
        "name": "browser_list_profiles",
        "description": "List the named browser profiles available on this host.",
        "parameters": {"type": "object", "properties": {}},
    },
]


async def list_tools(request):
    return JSONResponse(TOOLS_MANIFEST)


async def _proxy_tool(request, tool_name: str):
    body = await request.json()
    args = body.get("arguments", {})
    persona = body.get("persona", "")
    allowed = body.get("allowed_domains")
    blocked = body.get("blocked_domains")
    profile = args.get("profile", "_isolated")
    t0 = time.monotonic()

    if tool_name == "browser_navigate":
        ok, why = _validate_url(args.get("url", ""), allowed, blocked)
        if not ok:
            duration = (time.monotonic() - t0) * 1000
            _audit_log(persona, profile, tool_name, args, f"denied: {why}", duration)
            return JSONResponse({"error": why}, status_code=403)
        host = (urlparse(args.get("url", "")).hostname or "").lower()
        rate_ok, rate_why = _check_domain_rate(host)
        if not rate_ok:
            duration = (time.monotonic() - t0) * 1000
            _audit_log(persona, profile, tool_name, args, f"rate_limited: {rate_why}", duration)
            return JSONResponse({"error": rate_why}, status_code=429)

    if tool_name == "browser_fill":
        ref = args.get("element_ref", "")
        text = args.get("text", "")
        if (SENSITIVE_FIELD_PATTERNS.search(str(ref)) and
                not body.get("force_credential_fill", False)):
            duration = (time.monotonic() - t0) * 1000
            _audit_log(persona, profile, tool_name, args, "denied: sensitive field", duration)
            return JSONResponse({
                "error": "sensitive field detected; persona does not have force_credential_fill"
            }, status_code=403)

    # Anomaly check
    anomaly = _check_anomaly(persona, profile, tool_name, args)
    if anomaly:
        logger.warning("Browser anomaly: %s", anomaly)

    client = await _get_client(profile)
    try:
        result = await asyncio.wait_for(
            client.request(tool_name, args), timeout=120
        )
        duration = (time.monotonic() - t0) * 1000
        status = "ok" if "error" not in result else "error"
        _audit_log(persona, profile, tool_name, args, status, duration)
        return JSONResponse(result.get("result", result))
    except asyncio.TimeoutError:
        duration = (time.monotonic() - t0) * 1000
        _audit_log(persona, profile, tool_name, args, "timeout", duration)
        return JSONResponse({"error": "tool timed out after 120s"}, status_code=504)
    except Exception as e:
        duration = (time.monotonic() - t0) * 1000
        _audit_log(persona, profile, tool_name, args, f"exception: {e}", duration)
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


def _make_route(tool_name):
    async def handler(request):
        return await _proxy_tool(request, tool_name)
    return Route(f"/tools/{tool_name}", handler, methods=["POST"])


async def list_profiles_handler(request):
    profiles = sorted([p.name for p in PROFILES_DIR.iterdir() if p.is_dir()])
    return JSONResponse({"profiles": profiles})


# ── Admin endpoints (profile management) ─────────────────────────────────

async def admin_create_profile(request):
    body = await request.json()
    name = body.get("arguments", {}).get("name", "")
    if not re.match(r"^[a-z0-9_]+$", name):
        return JSONResponse({"error": "name must be lowercase alphanumeric + underscore"}, status_code=400)
    profile_path = PROFILES_DIR / name
    if profile_path.exists():
        return JSONResponse({"error": f"profile '{name}' already exists"}, status_code=409)
    profile_path.mkdir(parents=True)
    return JSONResponse({
        "profile": name, "created": True,
        "next_step": f"call /admin/browser_login_session with profile='{name}' to log in",
    })


async def admin_login_session(request):
    body = await request.json()
    args = body.get("arguments", {})
    profile = args.get("profile", "")
    url = args.get("starting_url", "")
    if not profile or not url:
        return JSONResponse({"error": "profile and starting_url required"}, status_code=400)
    profile_path = PROFILES_DIR / profile
    if not profile_path.exists():
        return JSONResponse({"error": f"profile '{profile}' not found — create first"}, status_code=404)
    cmd = [
        "npx", "@playwright/mcp@latest",
        "--browser", "chromium",
        "--user-data-dir", str(profile_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    init = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "browser_navigate",
                        "params": {"url": url}}).encode() + b"\n"
    proc.stdin.write(init)
    proc.stdin.flush()
    return JSONResponse({
        "profile": profile, "session_pid": proc.pid,
        "instructions": "Browser window opened. Complete login, then kill the process to persist cookies.",
    })


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


# ── App assembly ─────────────────────────────────────────────────────────

routes = [
    Route("/health", health, methods=["GET"]),
    Route("/tools", list_tools, methods=["GET"]),
    Route("/tools/browser_list_profiles", list_profiles_handler, methods=["POST"]),
    Route("/admin/browser_create_profile", admin_create_profile, methods=["POST"]),
    Route("/admin/browser_login_session", admin_login_session, methods=["POST"]),
    Route("/admin/browser_delete_profile", admin_delete_profile, methods=["POST"]),
] + [_make_route(t["name"]) for t in TOOLS_MANIFEST if t["name"] != "browser_list_profiles"]


@asynccontextmanager
async def _lifespan(app):
    asyncio.create_task(_idle_reaper())
    yield


app = Starlette(routes=routes, lifespan=_lifespan)


def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("BROWSER_MCP_PORT", "8923")))


if __name__ == "__main__":
    main()
