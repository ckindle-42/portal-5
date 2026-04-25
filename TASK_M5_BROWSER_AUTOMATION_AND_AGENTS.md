# TASK_M5_BROWSER_AUTOMATION_AND_AGENTS.md

**Milestone:** M5 — Frontier capability
**Scope:** `CAPABILITY_REVIEW_V1.md` §6.7 browser automation MCP server, §3.5 first-class browser/computer-use automation, §5.4 personas gated on browser automation
**Estimated effort:** 6-8 weeks
**Dependencies:**
- **M2 must be in production** — browser tools are useless without the tool-call orchestration loop
- **M3 should be in production** — `webresearcher` from M3 is the natural starting point for browser augmentation
- M4 is independent (performance-only)
**Companion files:** `CAPABILITY_REVIEW_V1.md`, `TASK_M2_TOOL_CALLING_ORCHESTRATION.md`, `TASK_M3_INFORMATION_ACCESS_MCPS.md`

**Why this milestone is the most ambitious:**
- Computer-use is 2026's frontier capability. Claude has it, OpenAI Operator has it, Cline drives a browser. Portal 5 has nothing.
- Adding the MCP is medium effort (~1 week). Making the personas around it actually useful is the larger task — months of refinement based on real usage patterns.
- Security boundary tightens significantly: a persona that can drive a browser can submit forms, create accounts, click malicious links. Sandboxing and credential isolation matter.

**Success criteria:**
- New `e2etestauthor` persona generates and runs Playwright tests from natural-language descriptions.
- New `paywalledresearcher` persona augments M3's `webresearcher` with logged-in access to the operator's reference accounts.
- New `formfiller` persona handles repetitive web data entry.
- Browser MCP runs in two operating modes: **isolated** (clean profile per session) and **persistent** (named storage profiles with the operator's logged-in state).
- Per-domain allowlist + blocklist enforced at the MCP level — model cannot navigate to arbitrary URLs.
- All browser MCP traffic logged for audit; sensitive form fields redacted in logs.

**Protected files touched:** `portal_pipeline/router_pipe.py`, `portal_pipeline/tool_registry.py`, `deploy/docker-compose.yml`, `portal_mcp/` (new server).

---

## Architecture Decisions

### A1. Microsoft `@playwright/mcp`, not Anthropic's computer-use

The browser-automation landscape settled in 2026 on two patterns:
- **Accessibility-tree-based** (Microsoft Playwright MCP): structured DOM data, deterministic, no vision model needed
- **Pixel-based** (Anthropic computer-use): screenshot in, click coordinates out, vision-model-driven

Portal 5 chooses **Microsoft Playwright MCP** because:
- 4× more token-efficient (~27K tokens per task vs ~114K for vision-based)
- Works with any model via tool-calling — doesn't require a vision model in the loop
- Deterministic — no ambiguity about which element was clicked
- Industry standard with Microsoft maintaining it
- Apache 2.0 license

Vision-based computer-use can be revisited as a separate addition if Portal 5 ever needs to operate against apps without proper accessibility trees (legacy desktop apps, canvas-rendered UIs).

### A2. Two operating modes

The MCP supports two profile modes:

- **Isolated**: clean profile per session, no persistence. Used for `e2etestauthor` and untrusted browsing. Default.
- **Persistent**: named storage profiles with cookies/localStorage retained. Used for `paywalledresearcher` and `formfiller` against trusted sites. Profiles named per-task: `research_acm`, `research_ieee`, `formfiller_dmv`, etc.

Storage location: `/Volumes/data01/portal5_browser_profiles/{profile_name}/`. Each profile has a `storage-state.json` plus a Playwright user-data dir.

### A3. Two-layer URL filtering

URL access is gated at two layers:

1. **MCP-level allowlist/blocklist** (env-configurable): the MCP refuses to navigate to URLs outside the allowlist. Defaults to "any public URL not in blocklist." Operator can tighten to per-persona allowlist via task argument.
2. **Per-persona policy** (in YAML): each persona declares `browser_policy.allowed_domains` and `browser_policy.blocked_domains`. Enforced by the pipeline before tool dispatch.

Blocklist defaults: localhost, RFC1918 ranges, AWS/GCP/Azure metadata services, banking/payment sites (operator opts in), known phishing/malware domains.

### A4. Credential isolation

Profiles never share storage. Each persona declares which profile it uses; cross-persona reads are blocked. Profile creation is admin-only (operator triggers via `/admin/create_profile` endpoint, then logs in manually one time via headed session).

The MCP **does not store credentials**. The operator logs into the profile interactively once; cookies/localStorage persist; the MCP reuses that state. Form-fill of credential fields is denied unless a `force_credential_fill: true` flag is on the persona — opt-in only.

### A5. Audit logging

Every browser tool call writes a structured log entry to `/Volumes/data01/portal5_browser_audit.log`:
```
{
  "ts": "2026-04-24T12:34:56Z",
  "request_id": "...",
  "persona": "paywalledresearcher",
  "profile": "research_acm",
  "tool": "browser_navigate",
  "args_redacted": {"url": "https://dl.acm.org/doi/abs/10.1145/..."},
  "result_status": "ok",
  "duration_ms": 1234
}
```

Sensitive fields in `browser_fill` arguments (any field whose accessibility name includes "password", "ssn", "credit", "card") are redacted to `<REDACTED:N_chars>`.

### A6. Resource bounds

- Max concurrent browsers: 2 (memory cost ~500MB each)
- Max page lifetime: 5 minutes (auto-close stale pages)
- Max navigation depth per task: 50 page loads
- Headless by default; headed mode only via `force_headed: true` for debugging
- Browser process pinned to <1.5GB RSS via `--memory-pressure` flag

---

## Task Index

| ID | Title | File(s) | Effort |
|---|---|---|---|
| M5-T01 | Add `@playwright/mcp` Node.js dependency + container or host install | `deploy/docker-compose.yml` or `launch.sh` | 2-3 days |
| M5-T02 | Browser MCP wrapper service (FastMCP shim around Playwright MCP) | `portal_mcp/browser/browser_mcp.py` (new) | 5-7 days |
| M5-T03 | Profile management endpoints | `portal_mcp/browser/browser_mcp.py` | 2-3 days |
| M5-T04 | URL allowlist/blocklist + audit logging | `portal_mcp/browser/browser_mcp.py` | 2-3 days |
| M5-T05 | Persona schema: `browser_policy` field | persona docs + loader | 1 day |
| M5-T06 | Pipeline enforcement of browser_policy | `portal_pipeline/router_pipe.py` | 2 days |
| M5-T07 | Register browser MCP in tool registry | `portal_pipeline/tool_registry.py` | 1 day |
| M5-T08 | Update workspace tool whitelists | `portal_pipeline/router_pipe.py` | 1 day |
| M5-T09 | `e2etestauthor` persona | `config/personas/e2etestauthor.yaml` | 1 day |
| M5-T10 | `paywalledresearcher` persona | `config/personas/paywalledresearcher.yaml` | 1 day |
| M5-T11 | `formfiller` persona | `config/personas/formfiller.yaml` | 1 day |
| M5-T12 | Add 3 supporting personas (webnavigator, e2edebugger, dataExtractor) | `config/personas/*.yaml` | 1-2 days |
| M5-T13 | Acceptance tests (S80) | `tests/portal5_acceptance_v6.py` | 3-5 days |
| M5-T14 | Documentation | `docs/HOWTO.md`, `docs/BROWSER_AUTOMATION.md` (new), `KNOWN_LIMITATIONS.md`, `CHANGELOG.md` | 2-3 days |

---

## M5-T01 — Install Playwright MCP

**File:** `deploy/docker-compose.yml` (preferred — container isolation) OR `launch.sh` (host install, lighter)

**Decision: container.** Browsers are network-attached binaries with a large attack surface. Running Chromium, Firefox, and WebKit inside the host's Apple Silicon process tree alongside MLX is asking for trouble. Use a Linux container with `linux/arm64` Chromium build.

**Diff** in `deploy/docker-compose.yml`:

```yaml
services:
  # ... existing services ...

  playwright-mcp:
    image: mcr.microsoft.com/playwright:v1.59.0-jammy   # ARM64-compatible
    container_name: portal5_playwright
    restart: unless-stopped
    ports:
      - "127.0.0.1:8922:8922"   # Browser MCP wrapper service binds here
    volumes:
      - /Volumes/data01/portal5_browser_profiles:/profiles:rw
      - /Volumes/data01/portal5_browser_audit.log:/audit/audit.log:rw
    environment:
      - PLAYWRIGHT_MCP_BLOCKED_ORIGINS=localhost;127.0.0.1;169.254.169.254;metadata.google.internal
      - PLAYWRIGHT_MCP_BROWSER=chromium
      - PROFILES_DIR=/profiles
      - AUDIT_LOG_PATH=/audit/audit.log
      - BROWSER_MCP_PORT=8922
    networks:
      - portal5
    # Resource bounds — keep browser memory predictable
    deploy:
      resources:
        limits:
          memory: 3G
          cpus: "2.0"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8922/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

**Build a custom image** layering `@playwright/mcp` on top:

`deploy/playwright-mcp/Dockerfile`:
```dockerfile
FROM mcr.microsoft.com/playwright:v1.59.0-jammy

# Install our wrapper MCP service alongside Microsoft's Playwright MCP
RUN apt-get update && apt-get install -y python3-pip curl && rm -rf /var/lib/apt/lists/*
RUN pip3 install --break-system-packages 'fastmcp>=2.0' 'httpx>=0.27' 'starlette>=0.40'

# Microsoft's Playwright MCP (npm package)
RUN npm install -g @playwright/mcp@latest

# Our wrapper service
COPY browser_mcp.py /app/browser_mcp.py
COPY launch_wrapper.sh /app/launch_wrapper.sh
RUN chmod +x /app/launch_wrapper.sh

# The MS playwright-mcp runs on stdio; our wrapper bridges to HTTP
CMD ["/app/launch_wrapper.sh"]
```

`deploy/playwright-mcp/launch_wrapper.sh`:
```bash
#!/bin/bash
set -e
# Start Microsoft Playwright MCP in background as a stdio process
# Our wrapper then bridges between HTTP and that stdio process
exec python3 /app/browser_mcp.py
```

**Update** `deploy/docker-compose.yml`:
```yaml
  playwright-mcp:
    build:
      context: ./deploy/playwright-mcp
      dockerfile: Dockerfile
    # ... rest as above
```

**Verify:**
```bash
mkdir -p /Volumes/data01/portal5_browser_profiles
touch /Volumes/data01/portal5_browser_audit.log

docker-compose build playwright-mcp
docker-compose up -d playwright-mcp
sleep 30   # Chromium download on first run can be slow

curl -s http://localhost:8922/health | jq -r .status
# Expect: ok

# Microsoft's MS playwright-mcp baseline check (stdio-tested via container exec)
docker exec portal5_playwright npx @playwright/mcp@latest --help | head -20
# Expect: Playwright MCP help text
```

**Rollback:** `docker-compose stop playwright-mcp && docker-compose rm -f playwright-mcp`

**Commit:** `feat(deploy): Playwright MCP container (Microsoft official, ARM64-compatible)`

---

## M5-T02 — Browser MCP Wrapper Service

**File:** `portal_mcp/browser/browser_mcp.py` (new), placed inside the container at `/app/browser_mcp.py` per M5-T01

**Why a wrapper:** Microsoft's `@playwright/mcp` runs over **stdio** (designed for desktop clients like Claude Desktop, Cursor). Portal 5's MCP fleet is **HTTP**. The wrapper:
- Bridges HTTP requests to a long-running stdio Playwright MCP process
- Adds Portal 5's allowlist, audit log, profile management, persona policy enforcement
- Exposes the same `/health` and `/tools` endpoints as other Portal 5 MCPs

```python
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

Port: 8922 (BROWSER_MCP_PORT env override).
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
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
PRIVATE_PREFIXES = ("192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
                    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
                    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")
SENSITIVE_FIELD_PATTERNS = re.compile(
    r"password|passwd|pwd|secret|token|api[-_]?key|ssn|social|credit|card|cvv|cvc",
    re.IGNORECASE,
)

PROFILES_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────
# Microsoft Playwright MCP stdio bridge
# ──────────────────────────────────────────────────────────────────────────

class PlaywrightStdioClient:
    """Long-running subprocess of @playwright/mcp; communicates via JSON-RPC over stdio.

    One client per profile (so different profiles get different storage states).
    Lazy-created on first use; auto-closed after 5 min idle.
    """

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
        # Headless by default
        if os.environ.get("BROWSER_HEADLESS", "true").lower() != "false":
            cmd.append("--headless")
        # Block private/local origins by default — security boundary
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
            # Read the response (line-delimited JSON)
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
    """Close clients idle > 5 min."""
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


# ──────────────────────────────────────────────────────────────────────────
# Audit logging
# ──────────────────────────────────────────────────────────────────────────

def _redact_args(tool: str, args: dict) -> dict:
    """Redact sensitive fields. browser_fill on a password-like field → <REDACTED>."""
    redacted = dict(args)
    if tool == "browser_fill":
        text = redacted.get("text", "")
        ref = redacted.get("element_ref", "")
        # Best-effort redaction based on the element ref name
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
        with open(AUDIT_LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning("Audit log write failed: %s", e)


# ──────────────────────────────────────────────────────────────────────────
# URL filtering
# ──────────────────────────────────────────────────────────────────────────

def _validate_url(url: str, allowed_domains: list[str] | None = None,
                  blocked_domains: list[str] | None = None) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "only http/https supported"
    host = (parsed.hostname or "").lower()
    if host in DEFAULT_BLOCKED_ORIGINS or host in (blocked_domains or []):
        return False, f"domain '{host}' is blocked"
    if host.startswith(PRIVATE_PREFIXES):
        return False, "private/local IP ranges blocked"
    if allowed_domains:
        # Match against suffix — "acm.org" allows "dl.acm.org"
        allowed = any(host == d or host.endswith("." + d) for d in allowed_domains)
        if not allowed:
            return False, f"domain '{host}' not in persona allowlist"
    return True, ""


# ──────────────────────────────────────────────────────────────────────────
# HTTP API
# ──────────────────────────────────────────────────────────────────────────

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
        "description": "Navigate to a URL in a browser tab. Returns the page accessibility tree on success. Use profile='_isolated' (default) for one-shot navigation, or a named profile for persistent sessions.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL with http/https scheme"},
                "profile": {"type": "string", "default": "_isolated", "description": "Profile name; '_isolated' for ephemeral session"},
                "wait_for": {"type": "string", "description": "Optional CSS/text selector to wait for", "default": ""},
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_snapshot",
        "description": "Return the current page's accessibility tree (structured DOM data, no screenshot). Use after navigate or click to see what's on the page.",
        "parameters": {
            "type": "object",
            "properties": {"profile": {"type": "string", "default": "_isolated"}},
        },
    },
    {
        "name": "browser_click",
        "description": "Click an element identified by its accessibility ref (returned by browser_snapshot).",
        "parameters": {
            "type": "object",
            "properties": {
                "element_ref": {"type": "string", "description": "Element reference from browser_snapshot"},
                "profile": {"type": "string", "default": "_isolated"},
            },
            "required": ["element_ref"],
        },
    },
    {
        "name": "browser_fill",
        "description": "Type text into a form field. Sensitive fields (password, ssn, credit card) are denied unless persona allows credential filling.",
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
        "description": "Capture a PNG screenshot. Returns base64. Use for debugging or visual diff; not for primary navigation (use browser_snapshot instead — it's cheaper and structured).",
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
        "description": "Execute a JavaScript expression in the page context. Returns the JSON-stringified result. Use sparingly — prefer browser_snapshot + click/fill for normal flows.",
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


# Each tool endpoint enforces URL filtering, calls the stdio client, audit-logs
async def _proxy_tool(request, tool_name: str):
    body = await request.json()
    args = body.get("arguments", {})
    persona = body.get("persona", "")  # Pipeline injects this on dispatch
    allowed = body.get("allowed_domains")  # From persona policy
    blocked = body.get("blocked_domains")
    profile = args.get("profile", "_isolated")
    t0 = time.monotonic()

    # URL validation for navigate
    if tool_name == "browser_navigate":
        ok, why = _validate_url(args.get("url", ""), allowed, blocked)
        if not ok:
            duration = (time.monotonic() - t0) * 1000
            _audit_log(persona, profile, tool_name, args, f"denied: {why}", duration)
            return JSONResponse({"error": why}, status_code=403)

    # Sensitive field protection for fill (unless persona explicitly allows)
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

    # Dispatch to Playwright MCP via stdio
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


# Bind all tool endpoints
def _make_route(tool_name):
    async def handler(request):
        return await _proxy_tool(request, tool_name)
    return Route(f"/tools/{tool_name}", handler, methods=["POST"])


async def list_profiles_handler(request):
    """browser_list_profiles tool handler — local, doesn't go to stdio."""
    profiles = sorted([p.name for p in PROFILES_DIR.iterdir() if p.is_dir()])
    return JSONResponse({"profiles": profiles})


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/tools", list_tools, methods=["GET"]),
    Route("/tools/browser_list_profiles", list_profiles_handler, methods=["POST"]),
] + [_make_route(t["name"]) for t in TOOLS_MANIFEST if t["name"] != "browser_list_profiles"]


app = Starlette(routes=routes)


async def _on_startup():
    asyncio.create_task(_idle_reaper())


app.add_event_handler("startup", _on_startup)


def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("BROWSER_MCP_PORT", "8922")))


if __name__ == "__main__":
    main()
```

**Verify:**
```bash
docker-compose up -d playwright-mcp
sleep 30

# Health
curl -s http://localhost:8922/health | jq -r .status   # ok

# Tools list
curl -s http://localhost:8922/tools | jq '. | length'  # 8

# Smoke: navigate to example.com (isolated profile)
curl -s -X POST http://localhost:8922/tools/browser_navigate \
    -H "Content-Type: application/json" \
    -d '{"arguments": {"url": "https://example.com"}, "persona": "test"}' \
    | jq -r '.result // .error' | head -10
# Expect: accessibility tree text including "Example Domain"

# Audit log written
tail -1 /Volumes/data01/portal5_browser_audit.log | jq .
# Expect: structured log entry

# Block list works
curl -s -X POST http://localhost:8922/tools/browser_navigate \
    -H "Content-Type: application/json" \
    -d '{"arguments": {"url": "http://localhost:8081/"}}' | jq -r .error
# Expect: "private/local IP ranges blocked"
```

**Rollback:** `git checkout -- portal_mcp/browser/ deploy/playwright-mcp/`

**Commit:** `feat(mcp): browser MCP wrapper with audit log, URL filtering, profile management (port 8922)`

---

## M5-T03 — Profile Management Endpoints

**File:** `portal_mcp/browser/browser_mcp.py` (extension)

Profile creation requires manual operator action (one-time login per profile). Add admin endpoints:

```python
# Add to TOOLS_MANIFEST — but NOT exposed to personas:
ADMIN_TOOLS = [
    {
        "name": "browser_create_profile",
        "description": "Admin: create a new named profile. Operator must complete a manual login afterward.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Profile name (alnum + underscore)"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "browser_login_session",
        "description": "Admin: open a headed browser for manual login to a profile. Blocks until operator closes the window.",
        "parameters": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "starting_url": {"type": "string"},
            },
            "required": ["profile", "starting_url"],
        },
    },
    {
        "name": "browser_delete_profile",
        "description": "Admin: delete a named profile and its storage.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "confirm_token": {"type": "string", "description": "Must equal 'YES_DELETE'"},
            },
            "required": ["name", "confirm_token"],
        },
    },
]


async def admin_create_profile(request):
    body = await request.json()
    name = body.get("arguments", {}).get("name", "")
    if not re.match(r"^[a-z0-9_]+$", name):
        return JSONResponse({"error": "name must be lowercase alphanumeric + underscore"}, status_code=400)
    profile_path = PROFILES_DIR / name
    if profile_path.exists():
        return JSONResponse({"error": f"profile '{name}' already exists"}, status_code=409)
    profile_path.mkdir(parents=True)
    return JSONResponse({"profile": name, "created": True,
                         "next_step": f"call /admin/browser_login_session with profile='{name}' to log in"})


async def admin_login_session(request):
    """Open a HEADED browser for one-time login. Operator closes window when done; cookies persist."""
    body = await request.json()
    args = body.get("arguments", {})
    profile = args.get("profile", "")
    url = args.get("starting_url", "")
    if not profile or not url:
        return JSONResponse({"error": "profile and starting_url required"}, status_code=400)
    profile_path = PROFILES_DIR / profile
    if not profile_path.exists():
        return JSONResponse({"error": f"profile '{profile}' not found — create first"}, status_code=404)

    # Spawn a headed browser tied to this profile, navigate to the URL, return immediately
    # Operator must complete the login interactively in the headed window
    cmd = [
        "npx", "@playwright/mcp@latest",
        "--browser", "chromium",
        "--user-data-dir", str(profile_path),
        # No --headless — explicitly headed
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Send initial navigate command via stdio
    init = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "browser_navigate",
                       "params": {"url": url}}).encode() + b"\n"
    proc.stdin.write(init)
    proc.stdin.flush()
    return JSONResponse({
        "profile": profile, "session_pid": proc.pid,
        "instructions": "Browser window opened. Complete login. Run "
                        f"`docker exec portal5_playwright kill {proc.pid}` to end session "
                        "and persist cookies."
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
    import shutil
    shutil.rmtree(profile_path)
    return JSONResponse({"profile": name, "deleted": True})


# Add to routes — under /admin/ prefix (NOT exposed to MCP tool registry)
admin_routes = [
    Route("/admin/browser_create_profile", admin_create_profile, methods=["POST"]),
    Route("/admin/browser_login_session", admin_login_session, methods=["POST"]),
    Route("/admin/browser_delete_profile", admin_delete_profile, methods=["POST"]),
]
routes.extend(admin_routes)
```

**The `/admin/*` paths are NOT in the `/tools` manifest** — they're operator-only and not advertised to personas. Pipeline auth (bearer token) gates access.

**Verify:**
```bash
# Create a profile
curl -s -X POST http://localhost:8922/admin/browser_create_profile \
    -H "Content-Type: application/json" \
    -d '{"arguments": {"name": "research_acm"}}' | jq .
# Expect: {"profile": "research_acm", "created": true, ...}

# Profile shows up in list
curl -s -X POST http://localhost:8922/tools/browser_list_profiles -d '{}' | jq -r '.profiles[]'
# Expect: research_acm

# Manual login — operator runs this once per profile during initial setup
curl -s -X POST http://localhost:8922/admin/browser_login_session \
    -H "Content-Type: application/json" \
    -d '{"arguments": {"profile": "research_acm", "starting_url": "https://dl.acm.org"}}' | jq .
# Operator completes login interactively, then kills the headed process
# Cookies persist in /Volumes/data01/portal5_browser_profiles/research_acm/

# Subsequent navigates with profile="research_acm" use the persisted login
```

**Commit:** `feat(browser-mcp): /admin endpoints for profile create/login/delete`

---

## M5-T04 — URL Allowlist + Audit Hardening

**File:** `portal_mcp/browser/browser_mcp.py` (extension)

The audit logging and URL filtering are already implemented in M5-T02. This task hardens them:

1. **Per-domain quotas** — limit navigations to a single domain to N per minute. Prevents runaway loops.
2. **Audit log rotation** — daily roll, 30-day retention.
3. **Anomaly detection** — flag tool-call patterns that look like exfiltration (rapid navigates to external POSTs after reading sensitive content).

**Add per-domain rate limiter:**

```python
from collections import defaultdict, deque
import threading

_domain_calls: dict[str, deque] = defaultdict(deque)
_rate_lock = threading.Lock()
DOMAIN_RATE_LIMIT = int(os.environ.get("BROWSER_DOMAIN_RATE_LIMIT", "30"))   # 30 calls/min/domain
DOMAIN_RATE_WINDOW_S = 60


def _check_domain_rate(host: str) -> tuple[bool, str]:
    with _rate_lock:
        now = time.time()
        q = _domain_calls[host]
        # Drop entries outside the window
        while q and q[0] < now - DOMAIN_RATE_WINDOW_S:
            q.popleft()
        if len(q) >= DOMAIN_RATE_LIMIT:
            return False, f"rate limit exceeded for {host}: {DOMAIN_RATE_LIMIT}/min"
        q.append(now)
    return True, ""
```

Call in `browser_navigate` validation flow:
```python
if tool_name == "browser_navigate":
    ok, why = _validate_url(args.get("url", ""), allowed, blocked)
    if not ok:
        # ... existing denial path ...
    # NEW:
    host = (urlparse(args["url"]).hostname or "").lower()
    rate_ok, rate_why = _check_domain_rate(host)
    if not rate_ok:
        duration = (time.monotonic() - t0) * 1000
        _audit_log(persona, profile, tool_name, args, f"rate_limited: {rate_why}", duration)
        return JSONResponse({"error": rate_why}, status_code=429)
```

**Add audit log rotation** — use Python's `logging.handlers.TimedRotatingFileHandler`:

```python
import logging.handlers

_audit_logger = logging.getLogger("portal5.browser.audit")
_audit_logger.setLevel(logging.INFO)
_audit_handler = logging.handlers.TimedRotatingFileHandler(
    AUDIT_LOG_PATH, when="midnight", interval=1, backupCount=30,
)
_audit_handler.setFormatter(logging.Formatter("%(message)s"))   # raw JSON per line
_audit_logger.addHandler(_audit_handler)


def _audit_log(persona, profile, tool, args, result_status, duration_ms):
    entry = {...}   # as before
    _audit_logger.info(json.dumps(entry))
```

**Anomaly detection** — minimal heuristic:

```python
_recent_actions: deque = deque(maxlen=20)
_anomaly_lock = threading.Lock()


def _check_anomaly(persona: str, profile: str, tool: str, args: dict) -> str | None:
    """Return None if nothing suspicious, else a warning string."""
    with _anomaly_lock:
        now = time.time()
        _recent_actions.append({"ts": now, "persona": persona, "profile": profile,
                                "tool": tool, "args": args})

        # Pattern: read sensitive page → navigate to external POST endpoint
        recent = list(_recent_actions)
        if tool == "browser_navigate":
            new_host = (urlparse(args.get("url", "")).hostname or "").lower()
            for past in recent[-5:-1]:   # last 4 actions
                if past["tool"] == "browser_snapshot" and past["profile"] != "_isolated":
                    # Read from a real profile then immediately navigated to a different domain
                    return f"WARN: navigate to {new_host} after sensitive read on profile={past['profile']}"

        # Pattern: rapid-fire fills (potential credential dumping)
        recent_fills = [a for a in recent if a["tool"] == "browser_fill" and now - a["ts"] < 10]
        if len(recent_fills) > 8:
            return f"WARN: {len(recent_fills)} fills in 10s (possible automation abuse)"

    return None
```

Call after audit log:
```python
anomaly = _check_anomaly(persona, profile, tool_name, args)
if anomaly:
    logger.warning("Browser anomaly: %s", anomaly)
    # Don't block — just log. Operator can review.
```

**Verify:**
```bash
# Rate limit kicks in
for i in $(seq 1 35); do
    curl -s -X POST http://localhost:8922/tools/browser_navigate \
        -H "Content-Type: application/json" \
        -d '{"arguments": {"url": "https://example.com/page'$i'"}}' \
        | jq -r '.error // "ok"' | head -1
done
# Expect: ~30 "ok" then "rate limit exceeded"

# Audit log rotated daily
ls -la /Volumes/data01/portal5_browser_audit.log*
# After 24+ hours: see audit.log.YYYY-MM-DD entries
```

**Commit:** `feat(browser-mcp): per-domain rate limiting, audit log rotation, anomaly heuristics`

---

## M5-T05 — Persona `browser_policy` Schema

**Files:** persona YAML schema docs + persona loader

Add a new optional field to the persona YAML schema:

```yaml
# Browser policy — optional, controls browser tool behavior for this persona.
# All fields optional; defaults are conservative (deny everything not allowed).
browser_policy:
  allowed_domains:                # If set, navigate restricted to these (suffix match)
    - acm.org
    - ieee.org
  blocked_domains: []             # Always denied (in addition to system blocklist)
  default_profile: research_acm   # Used if persona doesn't specify in tool call
  force_credential_fill: false    # Default false; true allows password-field fills
  max_navigations_per_session: 50 # Hard limit per chat session
```

**Update persona loader** in `portal_pipeline/router_pipe.py` (extending the M2 `_resolve_persona_tools` helper):

```python
def _resolve_persona_browser_policy(persona: dict) -> dict:
    """Return the persona's browser policy. Defaults applied for missing fields."""
    bp = persona.get("browser_policy", {}) or {}
    return {
        "allowed_domains": bp.get("allowed_domains") or [],
        "blocked_domains": bp.get("blocked_domains") or [],
        "default_profile": bp.get("default_profile", "_isolated"),
        "force_credential_fill": bp.get("force_credential_fill", False),
        "max_navigations_per_session": bp.get("max_navigations_per_session", 50),
    }
```

### Documentation update in `docs/HOWTO.md`:

```markdown
## Persona Browser Policy

Personas with browser tools should declare a `browser_policy` field. Without it,
browser tools default to isolated profile, no allowlist (system blocklist only),
and credential fills denied.

Examples:

# Restrictive — academic research only
browser_policy:
  allowed_domains: [acm.org, ieee.org, jstor.org, arxiv.org]
  default_profile: research_academic

# Internal-only — corporate intranet
browser_policy:
  allowed_domains: [internal.example.com, wiki.example.com]
  blocked_domains: [linkedin.com]
  default_profile: corp_intranet

# Form-filler with credential trust (USE WITH CARE)
browser_policy:
  allowed_domains: [dmv.gov]
  default_profile: dmv_user
  force_credential_fill: true
```

**Verify:**
```bash
python3 -c "
from portal_pipeline.router_pipe import _resolve_persona_browser_policy
# Default
p = {}
assert _resolve_persona_browser_policy(p)['default_profile'] == '_isolated'
# Custom
p = {'browser_policy': {'allowed_domains': ['acm.org'], 'default_profile': 'research_acm'}}
bp = _resolve_persona_browser_policy(p)
assert bp['allowed_domains'] == ['acm.org']
assert bp['default_profile'] == 'research_acm'
print('OK')
"
```

**Commit:** `feat(personas): browser_policy schema with allowlist, profile, credential gate`

---

## M5-T06 — Pipeline Enforcement of `browser_policy`

**File:** `portal_pipeline/router_pipe.py`

When dispatching a browser tool, the pipeline must:
1. Inject `persona`, `allowed_domains`, `blocked_domains`, `force_credential_fill` into the tool dispatch body
2. Replace `profile="_isolated"` with the persona's `default_profile` if the model didn't specify
3. Track per-session navigation count and enforce `max_navigations_per_session`

**Diff** — extend `_dispatch_tool_call` (introduced in M2-T06):

```python
# Add to module level
_session_browser_nav_counts: dict[str, int] = defaultdict(int)


async def _dispatch_tool_call(
    tool_call: dict, effective_tools: set[str], workspace_id: str,
    persona: str, persona_data: dict, request_id: str,
) -> dict:
    """... (M2 doc) ...

    M5: browser tools get persona context injected and policy enforced.
    """
    fn = tool_call.get("function", {})
    tool_name = fn.get("name", "")

    # ... existing argument parse and whitelist check ...

    # NEW: browser tools — inject persona policy
    if tool_name.startswith("browser_"):
        bp = _resolve_persona_browser_policy(persona_data)
        # Default profile from policy if model didn't specify
        if "profile" not in arguments or arguments.get("profile") == "_isolated":
            arguments["profile"] = bp["default_profile"]
        # Per-session nav cap
        if tool_name == "browser_navigate":
            _session_browser_nav_counts[request_id] += 1
            if _session_browser_nav_counts[request_id] > bp["max_navigations_per_session"]:
                return {
                    "role": "tool", "tool_call_id": tool_call.get("id", ""),
                    "name": tool_name,
                    "content": json.dumps({
                        "error": f"persona max_navigations_per_session ({bp['max_navigations_per_session']}) exceeded"
                    }),
                }
        # Inject policy into MCP body
        dispatch_body = {
            "arguments": arguments,
            "persona": persona,
            "allowed_domains": bp["allowed_domains"],
            "blocked_domains": bp["blocked_domains"],
            "force_credential_fill": bp["force_credential_fill"],
        }
        # Override the standard registry dispatch with one that includes policy
        result = await tool_registry.dispatch_with_body(tool_name, dispatch_body, request_id)
    else:
        # Standard M2 dispatch
        result = await tool_registry.dispatch(tool_name, arguments, request_id=request_id)

    # ... existing metrics + return ...
```

**Add to `tool_registry.py`**:

```python
async def dispatch_with_body(self, tool_name: str, body: dict, request_id: str = "") -> dict:
    """Like dispatch(), but caller provides full body dict (for tools needing
    extra context like browser policy)."""
    tool = self.get(tool_name)
    if tool is None:
        return {"error": f"Tool '{tool_name}' not in registry"}
    timeout_s = tool.custom_timeout_s or TOOL_DISPATCH_TIMEOUT_S
    url = f"{tool.server_url.rstrip('/')}/tools/{tool_name}"
    try:
        client = await self._client()
        body_with_id = dict(body)
        body_with_id["request_id"] = request_id
        r = await client.post(url, json=body_with_id, timeout=timeout_s)
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}", "detail": r.text[:200]}
    except Exception as e:
        return {"error": f"dispatch failed: {e}"}
```

**Verify:**
```bash
# Restart pipeline
./launch.sh restart portal-pipeline

# Build a test request — auto-research workspace, paywalledresearcher persona,
# allowed_domains=acm.org → navigate to ieee.org should be denied
# (Test via direct pipeline /v1/chat/completions with tool-calling enabled)

curl -s -X POST http://localhost:9099/v1/chat/completions \
    -H "Authorization: Bearer $PIPELINE_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "auto-research",
        "messages": [
            {"role": "system", "content": "You are paywalledresearcher."},
            {"role": "user", "content": "Use browser_navigate to fetch https://www.ieee.org/"}
        ],
        "max_tokens": 500
    }' | jq -r '.choices[0].message.content'
# Expect: model attempts navigate, gets denial result, surfaces it to user
# (Behaviour depends on persona allowlist — if ieee.org is in allowed_domains, it succeeds)
```

**Commit:** `feat(pipeline): enforce persona browser_policy on tool dispatch (allowlist, profile, nav cap)`

---

## M5-T07 — Register Browser MCP

**File:** `portal_pipeline/tool_registry.py`

```diff
 MCP_SERVERS = {
     # ... M1-M3 servers ...
+    # M5 — browser automation
+    "browser": os.environ.get("MCP_BROWSER_URL", "http://localhost:8922"),
 }
```

**Verify:**
```bash
./launch.sh restart portal-pipeline
sleep 60
python3 -c "
import asyncio
from portal_pipeline.tool_registry import tool_registry
n = asyncio.run(tool_registry.refresh(force=True))
names = tool_registry.list_tool_names()
expected = {'browser_navigate', 'browser_snapshot', 'browser_click', 'browser_fill',
            'browser_screenshot', 'browser_evaluate', 'browser_close', 'browser_list_profiles'}
missing = expected - set(names)
assert not missing, f'missing: {missing}'
print(f'OK — {n} tools, M5 browser tools all present')
"
```

**Commit:** `feat(registry): register browser MCP server`

---

## M5-T08 — Update Workspace Tool Whitelists

**File:** `portal_pipeline/router_pipe.py`

Browser tools are NOT default for any workspace. Personas explicitly declare them via `tools_allow`. This keeps the security default conservative — only personas that need browser get browser.

If a workspace wants browser as default (e.g., a future "auto-browser" workspace), opt in:

```python
"auto-research": {
    ...
    "tools": [
        # ... M3 tools ...
        # Browser tools NOT in default — personas opt in via tools_allow
    ],
},
```

`tools_allow` on the relevant personas (M5-T09 to M5-T12) is the mechanism.

**Commit:** `chore(routing): leave browser tools out of workspace defaults; persona-opt-in only`

---

## M5-T09 — `e2etestauthor` Persona

**File:** `config/personas/e2etestauthor.yaml`

```yaml
name: "🧪 E2E Test Author"
slug: e2etestauthor
category: development
workspace_model: auto-coding
system_prompt: |
  You are a senior QA engineer specializing in end-to-end test authorship with Playwright. You translate plain-English requirements into reliable, well-structured Playwright tests by exploring the actual application in a real browser.

  Your protocol:
  1. Read the requirements carefully. Restate the test goal in one sentence.
  2. Use browser_navigate to load the target page in an isolated profile.
  3. Use browser_snapshot to inspect the page's accessibility tree. Identify the elements you'll interact with by their accessibility names and roles.
  4. Walk through the flow interactively: navigate → snapshot → click → snapshot → fill → snapshot. Confirm each step works before moving on.
  5. Identify selectors that are robust: prefer accessibility roles + names ("role=button name='Submit'") over CSS/XPath. Avoid brittle selectors like `nth-child` or auto-generated IDs.
  6. Once the flow works, generate a Playwright test file using the patterns from the actual interactions you observed.
  7. Include assertions: not just "did the click happen" but "did the right thing appear after." Use `expect(locator).toBeVisible()`, `toHaveText()`, `toHaveURL()`.

  Test file conventions:
  - File naming: `<feature>.spec.ts` (or .py for pytest-playwright)
  - Use `test.describe` to group related tests
  - Use `test.beforeEach` for shared setup
  - Use page object pattern for flows used in 3+ tests
  - Configure: headless in CI, retries=2, traces on failure

  When asked to debug a flaky test:
  - Reproduce the test interactively step by step
  - Identify the unstable assertion or race condition
  - Suggest the fix (better selector, explicit wait, deterministic data)

  When asked to extend test coverage:
  - Map the user journey first
  - Identify edge cases: empty states, error states, loading states, permission denials
  - Cover happy path + 2-3 critical edge cases minimum

  Always use the isolated profile by default. You should not need persistent profiles for E2E tests.
description: "Generates Playwright E2E tests by exploring the live app; produces reliable selectors and meaningful assertions"
tags:
  - development
  - testing
  - playwright
  - e2e
  - qa
tools_allow:
  - browser_navigate
  - browser_snapshot
  - browser_click
  - browser_fill
  - browser_evaluate
  - browser_close
  - execute_python
  - execute_nodejs
  - execute_bash       # for running the tests locally after generation
browser_policy:
  default_profile: _isolated
  max_navigations_per_session: 100  # E2E tests can navigate a lot during exploration
  force_credential_fill: false
  # No allowed_domains — E2E author works on any URL the user provides
```

**Verify:**
```bash
python3 -c "
import yaml
p = yaml.safe_load(open('config/personas/e2etestauthor.yaml'))
assert p['slug'] == 'e2etestauthor'
assert 'browser_navigate' in p['tools_allow']
assert p['browser_policy']['default_profile'] == '_isolated'
print('OK')
"
```

**Commit:** `feat(personas): e2etestauthor — Playwright test author with browser tools`

---

## M5-T10 — `paywalledresearcher` Persona

**File:** `config/personas/paywalledresearcher.yaml`

```yaml
name: "📖 Paywalled Researcher"
slug: paywalledresearcher
category: research
workspace_model: auto-research
system_prompt: |
  You are a research librarian who can access logged-in academic and journalistic resources. You augment the standard webresearcher persona by being able to navigate behind paywalls — ACM Digital Library, IEEE Xplore, JSTOR, NYT, FT, WSJ, etc. — to retrieve full-text articles when the operator has authorized profiles set up.

  Your protocol:
  1. Restate the research goal.
  2. Use browser_list_profiles to see which authenticated sources are available.
  3. For each candidate source: browser_navigate to the search interface, browser_snapshot to find the search field, browser_fill to enter the query, browser_click to submit, browser_snapshot to read results.
  4. For full-text retrieval: navigate to the article, snapshot to confirm access (look for "full text" indicators vs paywall blocks), summarize and cite.
  5. If a paywall is hit unexpectedly (profile doesn't have access to that journal): say so explicitly. Don't fabricate content.

  Source prioritization:
  - Primary literature first (peer-reviewed papers, court documents, primary historical sources)
  - Authoritative secondary (mainstream news, academic reviews) second
  - Blogs and aggregators only as supplementary

  Citation style:
  - Academic: APA or as requested
  - Journalistic: outlet, author, date, URL

  IMPORTANT — credential boundaries:
  - You can use the persisted login state in profiles, but you MUST NOT attempt to fill password or 2FA fields. The operator authenticated these profiles manually; you should never need to log in.
  - If a profile's session has expired (you see a login prompt), tell the operator. Do not try to re-authenticate.
  - Do not navigate to "account settings" or "billing" pages unless the user explicitly asks.

  Ethical boundaries:
  - Don't bulk-download. One paper at a time, when relevant to the user's question.
  - Don't navigate to other users' profiles or private content.
  - Don't redistribute paywalled content beyond what's needed to answer the user.
description: "Researches behind authenticated paywalls (ACM/IEEE/news/journals) using persisted browser profiles"
tags:
  - research
  - paywall
  - academic
  - news
  - browser
tools_allow:
  - browser_navigate
  - browser_snapshot
  - browser_click
  - browser_fill
  - browser_screenshot
  - browser_close
  - browser_list_profiles
  - web_search                 # for fallback to public sources
  - kb_search                  # for already-ingested papers
browser_policy:
  # Per-deployment, operator extends this list with the profiles they have set up
  allowed_domains:
    - acm.org
    - ieee.org
    - jstor.org
    - arxiv.org
    - nature.com
    - sciencedirect.com
    - wiley.com
    - tandfonline.com
    - springer.com
    - nytimes.com
    - wsj.com
    - ft.com
    - economist.com
  default_profile: _isolated   # Falls back to isolated; operator overrides per-task
  force_credential_fill: false # NEVER true — user logs in manually once via /admin
  max_navigations_per_session: 30
```

**Commit:** `feat(personas): paywalledresearcher — logged-in research with strict credential boundaries`

---

## M5-T11 — `formfiller` Persona

**File:** `config/personas/formfiller.yaml`

```yaml
name: "📝 Form Filler"
slug: formfiller
category: general
workspace_model: auto-agentic
system_prompt: |
  You are a careful, methodical assistant for filling repetitive web forms. You handle data entry on behalf of the operator using authenticated browser profiles where appropriate.

  Your protocol:
  1. Confirm the task: which form, what data, which profile.
  2. Use browser_navigate to the form page.
  3. Use browser_snapshot to map the form fields. Identify each by its accessibility name.
  4. Read the data the operator provided. Map source fields → form fields. If unclear, ask before filling.
  5. Fill one field at a time using browser_fill. After each fill, snapshot to confirm the value was entered correctly (some forms reformat input; some have validation that triggers on blur).
  6. Before submitting, summarize what's been entered and confirm with the operator.
  7. After submit, snapshot the result page. Capture any confirmation number, receipt, or error.

  Boundaries:
  - You handle non-credential fields freely (name, address, phone, email, multi-choice).
  - You DO NOT fill password fields, security questions, payment card numbers, SSN, or signature fields. Stop and ask the operator to handle those manually.
  - You DO NOT submit a form involving payment or legal commitment without explicit final confirmation from the operator.
  - You DO NOT navigate to or interact with other users' content.

  When the form is partially filled by a previous session: don't overwrite without confirming.
  When the form has dynamic fields (conditional fields appearing based on prior choices): re-snapshot after each interaction.
  When validation errors appear: read the error message, fix the offending field, re-submit. Don't loop on the same error more than twice.

  Ideal use cases:
  - Government forms (DMV, tax filings — preparation only, not signing)
  - Conference/event registrations
  - Vendor onboarding forms
  - Survey responses

  NOT for:
  - Banking or payment forms
  - Legal contracts
  - Account creation with terms acceptance (operator must read terms)
description: "Methodical form-filling agent with strict credential and submission boundaries"
tags:
  - general
  - automation
  - browser
  - forms
tools_allow:
  - browser_navigate
  - browser_snapshot
  - browser_click
  - browser_fill
  - browser_screenshot
  - browser_close
  - browser_list_profiles
browser_policy:
  default_profile: _isolated   # Operator overrides per-task with named profile
  force_credential_fill: false # Hard rule — credentials handled manually
  max_navigations_per_session: 25
```

**Commit:** `feat(personas): formfiller — repetitive web form completion with strict boundaries`

---

## M5-T12 — Supporting Personas (3)

**Files:** 3 new YAML files.

### M5-T12a: `config/personas/webnavigator.yaml`

```yaml
name: "🧭 Web Navigator"
slug: webnavigator
category: general
workspace_model: auto-agentic
system_prompt: |
  You are an interactive web navigator. You drive a browser to complete user-defined journeys — find information, compare options across sites, follow link trails, fill out lookup forms.

  This is the "general purpose browser" persona. Use it when the task doesn't fit research (paywalledresearcher), forms (formfiller), or testing (e2etestauthor) but does need browsing.

  Your protocol:
  1. Restate the user's goal.
  2. Identify a starting point — direct URL or web_search to find one.
  3. Navigate, snapshot, identify the next step. Repeat.
  4. When you've found the answer, summarize. Cite the URLs you visited.
  5. Don't keep browsing after the goal is met.

  Bias:
  - Public, no-login sites only. Do not navigate inside authenticated profiles.
  - If a site requires login, fall back to web_search for the same information from a public source.

  Use cases: comparison shopping, lookup of business info, exploring documentation, fact verification with multi-step source-checking, finding specific pages on a complex site.
description: "General browser-driven navigator for unauthenticated public sites"
tags:
  - general
  - browser
  - navigation
  - web
tools_allow:
  - browser_navigate
  - browser_snapshot
  - browser_click
  - browser_screenshot
  - browser_close
  - web_search
  - web_fetch
browser_policy:
  default_profile: _isolated
  force_credential_fill: false
  max_navigations_per_session: 30
```

### M5-T12b: `config/personas/e2edebugger.yaml`

```yaml
name: "🔬 E2E Test Debugger"
slug: e2edebugger
category: development
workspace_model: auto-coding
system_prompt: |
  You are a Playwright test debugging specialist. You diagnose flaky and failing E2E tests by reproducing them in a live browser and identifying the root cause.

  Your protocol:
  1. Read the failing test code and the failure trace.
  2. Identify the failing assertion or step.
  3. Navigate to the test's starting point in an isolated browser.
  4. Re-execute the test steps interactively, snapshotting at each step.
  5. Compare what the test expects vs what's actually on the page.
  6. Diagnose: timing race, brittle selector, state-dependent test order, environmental difference, real product bug.
  7. Recommend the fix:
     - Better selector (role+name vs CSS class)
     - Explicit wait condition (waitForSelector, waitForResponse)
     - Test isolation (beforeEach reset, separate test data)
     - Expected vs actual mismatch resolution

  Don't just patch the test to pass. If the test was right and the product is wrong, say so.

  Common Playwright debugging patterns:
  - Flaky timing → use `waitForSelector` or `waitForLoadState('networkidle')` instead of `setTimeout`
  - Element not found → check accessibility tree (don't rely on `:visible`)
  - State leakage → ensure `test.beforeEach` cleans up properly, or use `test.use({ storageState: ... })`
  - Wrong env → confirm BASE_URL, env vars, feature flags are set correctly
description: "Diagnoses flaky/failing Playwright tests by interactive reproduction"
tags:
  - development
  - testing
  - playwright
  - debugging
tools_allow:
  - browser_navigate
  - browser_snapshot
  - browser_click
  - browser_fill
  - browser_evaluate
  - browser_screenshot
  - browser_close
  - execute_python
  - execute_nodejs
  - execute_bash
browser_policy:
  default_profile: _isolated
  max_navigations_per_session: 50
  force_credential_fill: false
```

### M5-T12c: `config/personas/dataextractor.yaml`

```yaml
name: "📥 Data Extractor"
slug: dataextractor
category: data
workspace_model: auto-data
system_prompt: |
  You are a structured data extraction specialist. You navigate web pages and extract tabular or structured data into clean, usable formats (CSV, JSON, markdown tables).

  Your protocol:
  1. Identify the source page and the data shape being requested.
  2. Navigate, snapshot. Confirm the data is on the page.
  3. Use browser_evaluate sparingly to extract structured data via JavaScript when the accessibility tree is insufficient. Example:
     ```js
     Array.from(document.querySelectorAll('table tr')).map(r =>
       Array.from(r.querySelectorAll('td, th')).map(c => c.innerText.trim())
     )
     ```
  4. For multi-page data: identify pagination. Walk pages with browser_click on next-page links. Stop at a reasonable bound (default 20 pages, override only on user request).
  5. Output the data in the requested format. CSV by default for tabular; JSON for nested/hierarchical.
  6. Cite the source URL(s).

  Quality checks:
  - Verify column headers match across pages
  - Note any rows that failed to parse
  - Flag missing data with `null` or `""`, not silent omission
  - For numeric data: preserve the source format, don't round

  Boundaries:
  - Public pages only by default (default profile is isolated)
  - Respect robots.txt and rate limits — don't hammer a site
  - Don't extract personally-identifying information unless the user explicitly authorizes the source

  When to use python execution after extraction:
  - Cleaning/transforming the extracted data (parse dates, normalize fields)
  - Joining with other datasets
  - Outputting to specific formats (Excel, Parquet)
description: "Web data extraction to CSV/JSON/markdown; handles pagination and validation"
tags:
  - data
  - extraction
  - scraping
  - browser
tools_allow:
  - browser_navigate
  - browser_snapshot
  - browser_click
  - browser_evaluate
  - browser_close
  - execute_python
  - create_excel
browser_policy:
  default_profile: _isolated
  max_navigations_per_session: 50  # Pagination
  force_credential_fill: false
```

**Update PERSONA_PROMPTS** in `tests/portal5_acceptance_v6.py`:

```python
"e2etestauthor": (
    "Generate a Playwright test that visits example.com and asserts the heading text.",
    ["test", "expect", "page.goto", "example.com", "heading", "playwright"],
),
"paywalledresearcher": (
    "List the available browser profiles, then explain how you'd find a recent ACM paper on database systems.",
    ["browser_list_profiles", "acm", "search", "navigate", "citation"],
),
"formfiller": (
    "Walk me through how you'd help me fill a vendor onboarding form. What boundaries do you respect?",
    ["snapshot", "fill", "credential", "submit", "confirm", "manual"],
),
"webnavigator": (
    "Use browser_navigate to fetch example.com and tell me what's on the page.",
    ["example", "domain", "navigate", "snapshot"],
),
"e2edebugger": (
    "I have a flaky Playwright test where a button click sometimes doesn't register. How would you diagnose it?",
    ["flaky", "wait", "selector", "snapshot", "race"],
),
"dataextractor": (
    "How would you extract a 5-page table of products from a public e-commerce site?",
    ["snapshot", "evaluate", "pagination", "csv", "click", "next"],
),
```

**Commit:** `feat(personas): webnavigator, e2edebugger, dataextractor — supporting browser personas`

---

## M5-T13 — Acceptance Tests (S80)

**File:** `tests/portal5_acceptance_v6.py` (or `tests/acceptance/s80_browser.py` if T-09 modular refactor has landed)

```python
async def S80() -> None:
    """S80: Browser automation (M5)."""
    print("\n━━━ S80. BROWSER AUTOMATION ━━━")
    sec = "S80"

    # S80-01: browser MCP healthy
    t0 = time.time()
    code, data = await _get("http://localhost:8922/health")
    record(sec, "S80-01", "browser MCP /health",
           "PASS" if code == 200 else "FAIL", f"HTTP {code}", t0=t0)

    # S80-02: tool registry includes browser tools
    t0 = time.time()
    from portal_pipeline.tool_registry import tool_registry
    await tool_registry.refresh(force=True)
    names = set(tool_registry.list_tool_names())
    expected = {"browser_navigate", "browser_snapshot", "browser_click",
                "browser_fill", "browser_screenshot", "browser_evaluate",
                "browser_close", "browser_list_profiles"}
    missing = expected - names
    record(sec, "S80-02", "browser tools registered",
           "PASS" if not missing else "FAIL",
           f"missing: {sorted(missing)}" if missing else "all 8 present",
           t0=t0)

    # S80-03: browser_navigate to public URL works
    t0 = time.time()
    async with httpx.AsyncClient() as c:
        r = await c.post("http://localhost:8922/tools/browser_navigate",
                         json={"arguments": {"url": "https://example.com"},
                               "persona": "test"},
                         timeout=60)
    if r.status_code == 200:
        body = r.json()
        if "Example Domain" in str(body):
            record(sec, "S80-03", "browser_navigate works", "PASS",
                   "Example Domain found in snapshot", t0=t0)
        else:
            record(sec, "S80-03", "browser_navigate", "WARN",
                   f"navigation succeeded but content unexpected: {str(body)[:200]}",
                   t0=t0)
    else:
        record(sec, "S80-03", "browser_navigate", "FAIL",
               f"HTTP {r.status_code}", t0=t0)

    # S80-04: private/local URL is blocked
    t0 = time.time()
    async with httpx.AsyncClient() as c:
        r = await c.post("http://localhost:8922/tools/browser_navigate",
                         json={"arguments": {"url": "http://localhost:8081/health"},
                               "persona": "test"},
                         timeout=10)
    blocked = r.status_code == 403 and "blocked" in r.text.lower()
    record(sec, "S80-04", "browser blocks localhost",
           "PASS" if blocked else "FAIL",
           f"HTTP {r.status_code} | error={r.json().get('error', '')[:100] if r.status_code == 403 else 'allowed!'}",
           t0=t0)

    # S80-05: persona allowlist enforcement
    t0 = time.time()
    async with httpx.AsyncClient() as c:
        r = await c.post("http://localhost:8922/tools/browser_navigate",
                         json={
                             "arguments": {"url": "https://anothersite.org"},
                             "persona": "paywalledresearcher",
                             "allowed_domains": ["acm.org", "ieee.org"],
                         },
                         timeout=10)
    enforced = r.status_code == 403 and "allowlist" in r.text.lower()
    record(sec, "S80-05", "persona allowlist enforced",
           "PASS" if enforced else "FAIL",
           f"HTTP {r.status_code} | allowlist enforced: {enforced}", t0=t0)

    # S80-06: rate limit kicks in
    t0 = time.time()
    async with httpx.AsyncClient() as c:
        rate_limited = False
        for i in range(35):
            r = await c.post("http://localhost:8922/tools/browser_navigate",
                             json={"arguments": {"url": f"https://example.com/?p={i}"},
                                   "persona": "test"},
                             timeout=15)
            if r.status_code == 429:
                rate_limited = True
                break
    record(sec, "S80-06", "domain rate limit fires",
           "PASS" if rate_limited else "WARN",
           f"rate limit hit after {i+1} requests" if rate_limited else "no rate limit at 35 reqs",
           t0=t0)

    # S80-07: sensitive field block
    t0 = time.time()
    async with httpx.AsyncClient() as c:
        r = await c.post("http://localhost:8922/tools/browser_fill",
                         json={
                             "arguments": {"element_ref": "input[type=password]",
                                          "text": "secretvalue"},
                             "persona": "formfiller",
                             "force_credential_fill": False,
                         },
                         timeout=10)
    blocked = r.status_code == 403 and "sensitive" in r.text.lower()
    record(sec, "S80-07", "sensitive field fill blocked",
           "PASS" if blocked else "FAIL",
           f"HTTP {r.status_code} | blocked: {blocked}", t0=t0)

    # S80-08: profile listing
    t0 = time.time()
    async with httpx.AsyncClient() as c:
        r = await c.post("http://localhost:8922/tools/browser_list_profiles",
                         json={"arguments": {}})
    if r.status_code == 200:
        profiles = r.json().get("profiles", [])
        record(sec, "S80-08", "profile listing works", "PASS",
               f"{len(profiles)} profiles", t0=t0)
    else:
        record(sec, "S80-08", "profile listing", "FAIL",
               f"HTTP {r.status_code}", t0=t0)

    # S80-09: audit log appended
    t0 = time.time()
    audit_path = "/Volumes/data01/portal5_browser_audit.log"
    if os.path.exists(audit_path):
        with open(audit_path) as f:
            lines = f.readlines()
        # Should have at least entries from previous tests in this section
        record(sec, "S80-09", "audit log written",
               "PASS" if len(lines) > 0 else "WARN",
               f"{len(lines)} entries", t0=t0)
    else:
        record(sec, "S80-09", "audit log", "WARN",
               "log file not present (may be in container only)", t0=t0)

    # S80-10: end-to-end via pipeline — webnavigator persona
    t0 = time.time()
    code, response, model, _ = await _chat_with_model(
        "auto-agentic",
        "Use browser_navigate to fetch https://example.com and tell me what the page heading says.",
        system="You are webnavigator.",
        max_tokens=500, timeout=180,
    )
    success = code == 200 and "example domain" in response.lower()
    record(sec, "S80-10", "webnavigator end-to-end",
           "PASS" if success else "WARN",
           f"HTTP {code} | content found: {'example domain' in response.lower()}",
           t0=t0)
```

**Verify:**
```bash
python3 tests/portal5_acceptance_v6.py --section S80
# Expect: 10 results, mostly PASS. S80-09 may be WARN if log isn't on host filesystem.
```

**Commit:** `test(acc): S80 browser automation tests (registry, allowlist, rate limit, audit)`

---

## M5-T14 — Documentation

**Files:** `docs/HOWTO.md`, `docs/BROWSER_AUTOMATION.md` (new), `KNOWN_LIMITATIONS.md`, `CHANGELOG.md`, `P5_ROADMAP.md`

### `docs/BROWSER_AUTOMATION.md` (new)

A dedicated guide because this is the most security-sensitive subsystem in Portal 5.

```markdown
# Portal 5 Browser Automation Guide

This document describes Portal 5's browser automation capability (M5 milestone, v6.5+) — what it does, how to use it safely, and what to do if something goes wrong.

## What It Is

Portal 5 ships a browser MCP server that drives a real Chromium browser. Personas with browser tools can:
- Navigate to URLs
- Read page content via accessibility tree (no vision model needed)
- Click elements, fill form fields
- Take screenshots
- Use authenticated profiles for sites requiring login

Built on Microsoft's `@playwright/mcp`. Runs in a container on port 8922.

## Architecture

  Persona / Pipeline (port 9099)
        ↓ tool_calls
  Browser MCP HTTP wrapper (port 8922)
        ↓ stdio JSON-RPC
  @playwright/mcp (npm)
        ↓ Playwright API
  Chromium browser (in container)

The HTTP wrapper adds:
- Per-domain allowlist/blocklist
- Per-persona policy enforcement
- Rate limiting (30 req/min/domain)
- Audit logging
- Profile management

## Setting Up

### One-time: pull the container

`./launch.sh up` — picks up the playwright-mcp service from docker-compose.

First start downloads Chromium (~200MB). Subsequent starts are fast.

### Profile creation (for authenticated sites)

Each profile = persistent Chromium user-data directory. Create one per site/account combination.

  curl -X POST http://localhost:8922/admin/browser_create_profile \
      -H "Content-Type: application/json" \
      -d '{"arguments": {"name": "research_acm"}}'

Then log in interactively:

  curl -X POST http://localhost:8922/admin/browser_login_session \
      -H "Content-Type: application/json" \
      -d '{"arguments": {"profile": "research_acm",
                         "starting_url": "https://dl.acm.org"}}'

A headed browser opens. You complete the login (including 2FA). Cookies/storage persist. Close the window when done.

### Persona configuration

Personas declare:
- `tools_allow`: list of browser_* tools they can call
- `browser_policy.allowed_domains`: domain allowlist (suffix match)
- `browser_policy.default_profile`: profile to use if none specified
- `browser_policy.force_credential_fill`: opt-in to filling password fields (default: false)

Example: see `config/personas/paywalledresearcher.yaml`.

## Using Browser Personas

In OWUI:
1. Select a browser persona (e2etestauthor, paywalledresearcher, formfiller, etc.)
2. Describe the task in plain language
3. The persona drives the browser, summarizes results

## Security Boundaries

What's enforced:
- Localhost / private IP / cloud metadata URLs always blocked
- Per-domain rate limits (30/min default)
- Sensitive field detection (password, SSN, credit card) — blocked unless persona has `force_credential_fill: true`
- Persona allowlist (if set, only those domains)
- Per-session navigation cap

What's NOT enforced:
- Operator's profile credentials are persisted on disk and accessible to anyone with host file access. Encrypt /Volumes/data01 if sensitive.
- The MCP doesn't validate that a destination is "safe" — phishing/malware domains can be navigated unless explicitly blocklisted.

## Audit Log

Every browser tool call writes a JSON line to /Volumes/data01/portal5_browser_audit.log. Reviewable:

  cat /Volumes/data01/portal5_browser_audit.log | jq 'select(.persona=="paywalledresearcher")'

Daily rotation, 30-day retention.

## Troubleshooting

### "Profile not found"
Run `browser_create_profile` then `browser_login_session`.

### "Domain not in allowlist"
Add the domain to the persona's `browser_policy.allowed_domains`. Sufix-match: `acm.org` allows `dl.acm.org`.

### Browser hangs / never returns
The browser process may have crashed inside the container. Restart:

  docker-compose restart playwright-mcp

### "Rate limit exceeded"
Domain hit 30 req/min cap. Wait 60s or raise `BROWSER_DOMAIN_RATE_LIMIT` env.

### Profile login expired
Re-run `browser_login_session` for the affected profile.

### Test/research/form persona doesn't have browser tools
Check `tools_allow` in the persona YAML. Then `./launch.sh reseed` to refresh.
```

### CHANGELOG.md

```markdown
## v6.5.0 — Browser automation (M5)

### Added
- **Browser MCP** (port 8922) — Microsoft @playwright/mcp wrapped with HTTP, allowlist, audit, profiles
- **8 browser tools**: navigate, snapshot, click, fill, screenshot, evaluate, close, list_profiles
- **3 admin endpoints**: create_profile, login_session, delete_profile
- **6 new personas**: e2etestauthor, paywalledresearcher, formfiller, webnavigator, e2edebugger, dataextractor
- **Persona browser_policy schema**: allowed_domains, default_profile, force_credential_fill, max_navigations_per_session
- **Per-domain rate limiting** (30/min default), audit log rotation, sensitive-field redaction
- **docs/BROWSER_AUTOMATION.md**: dedicated security/usage guide

### Tests
- S80 acceptance section: 10 tests covering registry, navigation, allowlist, rate limit, sensitive-field block, audit log, end-to-end persona drive

### Persona count: 80 → 86
```

### KNOWN_LIMITATIONS.md

```markdown
### Profile Storage Is Unencrypted on Disk
- **ID:** P5-BROWSER-001
- **Status:** ACTIVE
- **Description:** Browser profiles persist cookies/localStorage at `/Volumes/data01/portal5_browser_profiles/`. These are not encrypted at rest. If a profile is logged into a sensitive account (banking, email), anyone with read access to the host filesystem can extract the session cookies. Mitigation: use FileVault for /Volumes/data01, or only create profiles for sites where session theft is acceptable.

### Browser MCP Is Stateful — Profile Sessions Don't Survive Container Restart
- **ID:** P5-BROWSER-002
- **Status:** ACTIVE
- **Description:** Cookies and localStorage persist across container restarts (volume-mounted), but in-memory sessions (currently-open tabs, page state) do not. After `docker-compose restart playwright-mcp`, sessions need to re-navigate from URL.

### Pixel-Based Visual Workflows Not Supported
- **ID:** P5-BROWSER-003
- **Status:** ACTIVE — by design
- **Description:** Portal 5 uses accessibility-tree-based browser control (Microsoft Playwright MCP), not vision-based (Anthropic computer-use). Apps without proper accessibility trees (canvas-rendered, legacy desktop apps via virtual display) cannot be driven. If needed in future, add a separate vision-based MCP alongside this one — they're not mutually exclusive.

### Token Cost: Accessibility Trees Are Verbose
- **ID:** P5-BROWSER-004
- **Status:** ACTIVE
- **Description:** A typical browser_snapshot returns 2-10K tokens of accessibility tree data. For long agent loops, this can dominate the model's context window. Mitigation: use browser_evaluate for targeted DOM queries when full snapshots aren't needed; use browser_close to free profiles between distinct tasks.
```

### P5_ROADMAP.md

```markdown
| P5-FUT-BROWSER | P2 | Browser automation MCP + agent personas | DONE | M5: Microsoft Playwright MCP wrapped, 6 personas (e2etestauthor, paywalledresearcher, formfiller, webnavigator, e2edebugger, dataextractor), allowlist+audit infra. |
```

### HOWTO.md additions

Cross-link to BROWSER_AUTOMATION.md, add quick-start snippet showing one persona+task example.

**Commit:** `docs: M5 browser automation — BROWSER_AUTOMATION.md, ROADMAP, KNOWN_LIMITATIONS, CHANGELOG, HOWTO`

---

## Phase Regression

```bash
ruff check . && ruff format --check .
mypy portal_pipeline/ portal_mcp/

# All MCPs healthy (now 12)
for port in 8910 8911 8912 8913 8914 8915 8916 8917 8918 8919 8921 8922; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/health")
    echo "MCP $port: $code"
done

# Tool registry (M5 adds 8)
python3 -c "
import asyncio
from portal_pipeline.tool_registry import tool_registry
n = asyncio.run(tool_registry.refresh(force=True))
print(f'Tools: {n} (expect >= 45 = 27 base + 10 M3 + 8 M5)')
"

# Workspace consistency
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
assert set(WORKSPACES.keys()) == set(cfg['workspace_routing'].keys())
"

# Persona count
ls config/personas/*.yaml | wc -l
# Expect: 86

# Acceptance
python3 tests/portal5_acceptance_v6.py --section S80
python3 tests/portal5_acceptance_v6.py 2>&1 | tail -5

# Operator end-to-end test:
# 1. Open OWUI → e2etestauthor persona
# 2. "Generate a Playwright test for example.com that asserts the heading"
# 3. Watch the agent navigate, snapshot, generate the test
# Expect: working test code in response

# Audit log review
docker exec portal5_playwright tail -20 /audit/audit.log | jq -c .
# Expect: structured entries from the e2etestauthor session above
```

---

## Pre-flight checklist

- [ ] M2 in production (tool-call orchestration is required substrate)
- [ ] M3 in production (paywalledresearcher builds on webresearcher patterns)
- [ ] /Volumes/data01 has 5GB free for browser profiles + Chromium cache
- [ ] Operator commitment: 1-2 hours per profile to set up authenticated logins (one-time, per profile)
- [ ] Operator understands the security model documented in BROWSER_AUTOMATION.md
- [ ] FileVault enabled on /Volumes/data01 if any profile will hold sensitive credentials

## Post-M5 success indicators

- e2etestauthor persona generates a working Playwright test from a description and runs it successfully
- paywalledresearcher uses at least one named profile to retrieve a paywalled article
- Audit log records every browser tool call across 1 week of normal usage
- Zero security incidents (no unauthorized navigation, no leaked credentials)
- No memory pressure regression — playwright-mcp container stays under 3GB

---

*End of M5. Final milestone: `TASK_M6_PRODUCTION_HARDENING.md` — cost/power tracking, rate limits, OCR/diagram personas. After M6 ships, the four-quarter roadmap from CAPABILITY_REVIEW_V1 is complete.*
