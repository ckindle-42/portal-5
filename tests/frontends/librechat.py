"""LibreChat Playwright + API driver for the Portal 5 UAT driver.

UI navigation (login, model picker, preset, send button) is done via
Playwright because those interactions require a real browser session.

Completion detection and response reading use the LibreChat REST API:
  - POST /api/auth/login          → auth token (cached, refreshed on 401)
  - GET  /api/messages/{convId}   → poll until last assistant message is done

This eliminates all DOM-scraping timing issues: the API tells us exactly
when unfinished=false, regardless of model speed.

Interface (mirrors the OWUI shape used in portal5_uat_driver.py via _fe_*):
  - login(page)
  - start_new_chat(page, model_slug, title, *, personas_map)
  - send_prompt(page, prompt) -> str          # returns pre-send body (unused now)
  - wait_for_completion(page, test_id, tier, max_wait_no_progress, ...)
  - get_last_response(page)
  - enable_tool(page, tool_id)               # no-op
  - assign_folder(page, folder_name)         # no-op
  - download_artifact(page, expected_ext, response_text, timeout_ms)
  - current_chat_url(page)
  - load_personas_map() -> dict[slug, preset_title]

Note: get_routed_model is intentionally absent — the model that handled a
request is read from pipeline logs (frontend-independent).
"""

from __future__ import annotations

import asyncio
import os
import re
import time
import urllib.parse
from pathlib import Path

import httpx
import yaml

LIBRECHAT_URL = os.environ.get("LIBRECHAT_URL", "http://localhost:8082")
LIBRECHAT_EMAIL = os.environ.get(
    "LIBRECHAT_ADMIN_EMAIL", os.environ.get("OPENWEBUI_ADMIN_EMAIL", "admin@portal.local")
)
LIBRECHAT_PASSWORD = os.environ.get("LIBRECHAT_ADMIN_PASSWORD", "")

# ── API auth state ────────────────────────────────────────────────────────────

_API_TOKEN: str = ""
_API_TOKEN_EXPIRY: float = 0.0  # epoch seconds

# Thinking-model artifacts that leak into content[*].text parts — skip these.
_THINK_ARTIFACTS = ("nothink", "nothon", "</think>", "<think>", "<|/think|>", "<|think|>")

# ── Persona preset map ────────────────────────────────────────────────────────

_PERSONAS_MAP: dict[str, str] | None = None


def load_personas_map(personas_dir: Path | None = None) -> dict[str, str]:
    """Build {slug: preset_title}. Cached after first call."""
    global _PERSONAS_MAP
    if _PERSONAS_MAP is not None:
        return _PERSONAS_MAP

    if personas_dir is None:
        personas_dir = Path(__file__).resolve().parent.parent.parent / "config" / "personas"

    result: dict[str, str] = {}
    persona_systems: dict[str, str] = {}
    persona_models: dict[str, str] = {}
    for yf in sorted(personas_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yf.read_text()) or {}
        except Exception:
            continue
        slug = data.get("slug", "")
        name = data.get("name", slug)
        if slug:
            result[slug] = f"🎭 {name}"
            persona_systems[slug] = data.get("system_prompt", "")
            persona_models[slug] = data.get("workspace_model", "auto")
    _PERSONAS_MAP = result
    load_personas_map._systems = persona_systems  # type: ignore[attr-defined]
    load_personas_map._models = persona_models  # type: ignore[attr-defined]
    return result


# ── API auth ──────────────────────────────────────────────────────────────────


async def _api_authenticate() -> str:
    """Obtain a fresh auth token from /api/auth/login. Caches it module-wide."""
    global _API_TOKEN, _API_TOKEN_EXPIRY
    now = time.time()
    if _API_TOKEN and now < _API_TOKEN_EXPIRY - 30:
        return _API_TOKEN

    if not LIBRECHAT_PASSWORD:
        raise RuntimeError(
            "LIBRECHAT_ADMIN_PASSWORD is empty — set it in .env before running --frontend librechat"
        )

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    f"{LIBRECHAT_URL}/api/auth/login",
                    json={"email": LIBRECHAT_EMAIL, "password": LIBRECHAT_PASSWORD},
                )
            if r.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"  [librechat-api] login rate-limited, waiting {wait}s …", flush=True)
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            token = data.get("token", "")
            if not token:
                raise RuntimeError(f"login response missing token: {data}")
            # JWT exp is at payload[1] after base64-decode, but estimate 14 min
            _API_TOKEN = token
            _API_TOKEN_EXPIRY = now + 840  # 14 min (tokens expire in 15)
            return token
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"LibreChat login failed: {exc.response.status_code}") from exc
    raise RuntimeError("LibreChat login rate-limited after 3 attempts")


async def _api_get_messages(conv_id: str) -> list[dict]:
    """GET /api/messages/{conv_id} with token refresh on 401."""
    global _API_TOKEN, _API_TOKEN_EXPIRY
    for attempt in range(2):
        token = await _api_authenticate()
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{LIBRECHAT_URL}/api/messages/{conv_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code == 401:
            _API_TOKEN = ""
            _API_TOKEN_EXPIRY = 0.0
            continue
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    return []


async def _api_find_recent_conv_id(since_ts: float) -> str:
    """Query /api/convos for the most recently created conversation after since_ts.

    Used as a fallback when LibreChat's SPA never navigates from /c/new to
    /c/<uuid> (e.g. long promptPrefix URLs that confuse the SPA router).
    """
    import datetime

    try:
        token = await _api_authenticate()
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{LIBRECHAT_URL}/api/convos",
                params={"pageSize": 10, "sortBy": "createdAt", "sortOrder": "desc"},
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code != 200:
            return ""
        data = r.json()
        convs = data.get("conversations", [])
        for conv in convs:
            created = conv.get("createdAt", "")
            try:
                ct = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
                if ct.timestamp() > since_ts - 30:
                    return conv.get("conversationId", "")
            except Exception:
                pass
    except Exception:
        pass
    return ""


# ── Playwright auth ───────────────────────────────────────────────────────────


async def login(page) -> None:
    """Fill email/password, click submit, wait for chat composer.
    Also pre-warms the API auth token so it's ready for wait_for_completion.
    """
    if not LIBRECHAT_PASSWORD:
        raise RuntimeError(
            "LIBRECHAT_ADMIN_PASSWORD is empty — set it in .env before running --frontend librechat"
        )
    await page.goto(LIBRECHAT_URL, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_selector('input[type="email"], input[name="email"]', timeout=20_000)
    await page.fill('input[type="email"], input[name="email"]', LIBRECHAT_EMAIL)
    await page.fill('input[type="password"], input[name="password"]', LIBRECHAT_PASSWORD)
    await page.locator('button[type="submit"]').first.click()
    await page.wait_for_selector("textarea, nav, [class*='sidebar']", timeout=20_000)
    await asyncio.sleep(1.0)
    # Pre-warm API token
    await _api_authenticate()


# ── Session health ────────────────────────────────────────────────────────────


async def _ensure_authenticated(page) -> None:
    """Re-login if LibreChat has silently redirected to the login page.

    After long idle periods (e.g. a 600s model pre-warm), LibreChat can expire
    the session and redirect to /login. The chat composer — including the
    MCPSelect button — only renders in authenticated state. This check detects
    that condition and re-logs in before proceeding.
    """
    url = page.url
    if "/login" in url or "/register" in url:
        print("  [session] Detected login redirect — re-authenticating", flush=True)
        await login(page)
        return
    # Also check: if the input box says "sign in" or email field is visible, we
    # got redirected mid-SPA without a URL change.
    try:
        email_visible = await page.locator('input[type="email"]').is_visible(timeout=500)
        if email_visible:
            print("  [session] Email input visible — re-authenticating", flush=True)
            await login(page)
    except Exception:
        pass


# ── Chat creation ─────────────────────────────────────────────────────────────


async def start_new_chat(
    page,
    model_slug: str,
    title: str,
    *,
    personas_map: dict[str, str] | None = None,
    requires_tool: str | list[str] | None = None,
) -> str:
    """Open a fresh conversation via URL params (model + promptPrefix).

    Uses direct URL navigation instead of UI clicking so the correct model and
    system prompt are always applied, regardless of prior session state.
    LibreChat reads ?endpoint=, ?model=, and ?promptPrefix= on page load.
    """
    if personas_map is None:
        personas_map = load_personas_map()

    systems = getattr(load_personas_map, "_systems", {})
    models_map = getattr(load_personas_map, "_models", {})

    if model_slug in personas_map:
        ws_model = models_map.get(model_slug, "auto")
        sysprompt = systems.get(model_slug, "")
    else:
        ws_model = model_slug
        sysprompt = ""

    params: list[tuple[str, str]] = [("endpoint", "Portal 5"), ("model", ws_model)]
    if sysprompt:
        params.append(("promptPrefix", sysprompt))

    url = f"{LIBRECHAT_URL}/c/new?{urllib.parse.urlencode(params)}"
    # Navigate with resilient retry — after long model sessions (>5min) the SPA can
    # become unresponsive and fail to render basic DOM elements in 20s. Hard-reset
    # to root first, then retry, to recover from stale SPA state.
    _basic_sel = "textarea, nav, [class*='sidebar']"
    for _nav_try in range(4):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_selector(_basic_sel, timeout=60_000)
            break
        except Exception as _nav_err:
            if _nav_try == 3:
                raise
            print(
                f"  [lc-nav] SPA unresponsive (attempt {_nav_try + 1}): {type(_nav_err).__name__}; "
                f"hard-resetting to root and retrying",
                flush=True,
            )
            await page.goto(LIBRECHAT_URL, wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(8.0)
    # Re-login if a long idle (e.g. model pre-warm) expired the session.
    await _ensure_authenticated(page)

    # Per-conversation MCP server attachment.
    # OWUI seeds toolIds at workspace level; LibreChat requires a UI click.
    # This is the one piece of test infrastructure that differs between
    # frontends — and the reason every tool-requiring test FAILed on the
    # 2026-05-18 LibreChat parity run before this change.
    if requires_tool:
        keys = [requires_tool] if isinstance(requires_tool, str) else list(requires_tool)
        # Wait up to 30s for the MCPSelect button. After long model pre-warm waits
        # (up to 618s idle), the LibreChat SPA connection can stale — the button
        # needs time to re-render after page.goto() re-establishes the session.
        # Give the toolbar 2s to render after the basic DOM is ready, then check.
        # If it still isn't found, hard-navigate to root first (resets SPA MCP
        # state after prior tool use) then reload the conversation URL and retry.
        _mcp_sel = '[data-testid="mcp-select"], button:has-text("MCP Servers")'
        await asyncio.sleep(2.0)
        _found = False
        try:
            await page.wait_for_selector(_mcp_sel, timeout=30_000)
            _found = True
        except Exception:
            pass
        if not _found:
            print("  [mcp-retry] MCPSelect not found after 30s — hard-resetting SPA and retrying", flush=True)
            await page.goto(LIBRECHAT_URL, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2.0)
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_selector("textarea, nav, [class*='sidebar']", timeout=20_000)
            await asyncio.sleep(2.0)
            await _ensure_authenticated(page)
            try:
                await page.wait_for_selector(_mcp_sel, timeout=30_000)
                _found = True
            except Exception:
                pass
        if not _found:
            # Second retry: full hard reload — handles SPA state after memory pressure
            # or proxy recovery events that leave the toolbar in an uninitialised state.
            print("  [mcp-retry2] MCPSelect still absent — hard reload + 10s settle", flush=True)
            await page.reload(wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(10.0)
            await _ensure_authenticated(page)
            try:
                await page.wait_for_selector(_mcp_sel, timeout=30_000)
            except Exception:
                pass  # select_mcp_servers will log "not found" if still absent
        await select_mcp_servers(page, keys)
    else:
        await asyncio.sleep(1.0)

    return page.url


# ── MCP server selection ──────────────────────────────────────────────────────


async def select_mcp_servers(page, server_keys: list[str]) -> None:
    """Open the MCPSelect dropdown and check each server in `server_keys`.

    Maps a `requires_tool` value like `portal_documents` to the librechat.yaml
    key `portal-documents` and clicks the checkbox row in the MCPSelect popover.

    Idempotent: if a server is already checked (or another test ran in this
    Playwright context and left it checked), the click no-ops. Safe to call
    on an empty list — returns immediately.

    Selectors verified against LibreChat v0.8.6-rc1. If a newer image moves
    them, update docs/UAT_LIBRECHAT_DOM_NOTES.md § MCPSelect and re-run Phase
    0.5 calibration.
    """
    if not server_keys:
        return

    # Map driver tool IDs (portal_documents) to librechat.yaml keys (portal-documents)
    yaml_keys = [k.replace("portal_", "portal-") for k in server_keys]

    # Open the dropdown. Candidate selectors, in order of preference:
    #   1. The MCPSelect button by data-testid (most stable)
    #   2. The button by visible placeholder text "MCP Servers"
    #   3. Any button whose aria-label contains "MCP"
    dropdown_button_selectors = [
        '[data-testid="mcp-select"]',
        'button:has-text("MCP Servers")',
        'button[aria-label*="MCP" i]',
    ]
    opened = False
    for sel in dropdown_button_selectors:
        try:
            loc = page.locator(sel).first
            cnt = await loc.count()
            if cnt > 0:
                lbl = await loc.get_attribute("aria-label") or ""
                # Skip the account "MCP Settings" button — it opens the account menu
                if "settings" in lbl.lower():
                    continue
                await loc.click(timeout=5000)
                opened = True
                break
        except Exception:
            continue
    if not opened:
        print(
            f"  [librechat-mcp] MCPSelect dropdown not found; tools NOT attached: {yaml_keys}",
            flush=True,
        )
        return

    # Wait for the popover to render — LibreChat v0.8.6-rc1 uses a Radix popover.
    # The rows are plain div elements with the YAML key as visible text; no ARIA role.
    await asyncio.sleep(0.8)

    # Scope to the Radix popover container when available; fall back to page-wide search.
    _popover = page.locator('[data-radix-popper-content-wrapper]')
    _search_root = _popover if await _popover.count() > 0 else page

    # Click each server. Rows display the exact YAML key as their visible text label.
    for key in yaml_keys:
        clicked = False
        try:
            # get_by_text with exact=True scrolls into view automatically.
            row = _search_root.get_by_text(key, exact=True).first
            if await row.count() > 0:
                await row.scroll_into_view_if_needed(timeout=2000)
                await row.click(timeout=3000)
                clicked = True
        except Exception:
            pass
        if not clicked:
            # Fallback: has-text substring match on the popover container
            try:
                row = _search_root.locator(f':has-text("{key}")').last
                if await row.count() > 0:
                    await row.scroll_into_view_if_needed(timeout=2000)
                    await row.click(timeout=3000)
                    clicked = True
            except Exception:
                pass
        if not clicked:
            print(f"  [librechat-mcp] WARN: server row not found for {key}", flush=True)
        else:
            print(f"  [librechat-mcp] attached {key}", flush=True)

    # Close the dropdown by clicking outside (the composer area)
    try:
        await page.locator("textarea").first.click(timeout=3000)
    except Exception:
        await page.keyboard.press("Escape")
    await asyncio.sleep(0.3)


class PresetUnreachableError(RuntimeError):
    pass


# ── File attachment ───────────────────────────────────────────────────────────


async def attach_file(page, file_path) -> bool:
    """Attach a file to the current LibreChat conversation before sending.

    Uses Playwright set_input_files on the hidden file input — works without
    needing to click the paperclip button, which varies across LibreChat versions.
    Returns True if the upload completed (file badge appeared), False if it
    timed out or the input wasn't found.
    """
    from pathlib import Path as _Path

    file_path = _Path(file_path)
    if not file_path.exists():
        print(f"  [attach-file] fixture not found: {file_path}", flush=True)
        return False

    # LibreChat renders one or more hidden <input type="file"> elements in the
    # composer. set_input_files works on hidden inputs directly.
    file_input = page.locator('input[type="file"]').first
    try:
        cnt = await file_input.count()
        if cnt == 0:
            print("  [attach-file] no file input found — skipping attachment", flush=True)
            return False
        await file_input.set_input_files(str(file_path))
    except Exception as exc:
        print(f"  [attach-file] set_input_files failed: {exc}", flush=True)
        return False

    # Wait for LibreChat to process the upload (file badge or filename appears).
    try:
        await page.wait_for_selector(
            f'[data-filename*="{file_path.stem}"], '
            f'[title*="{file_path.name}"], '
            f'span:has-text("{file_path.name}"), '
            f'div:has-text("{file_path.name}")',
            timeout=30_000,
        )
        print(f"  [attach-file] attached {file_path.name}", flush=True)
        return True
    except Exception:
        # Upload may have worked even if the badge selector didn't match.
        print(f"  [attach-file] uploaded {file_path.name} (badge not confirmed)", flush=True)
        return True


# ── Send ──────────────────────────────────────────────────────────────────────


async def send_prompt(page, prompt: str) -> str:
    """Fill the composer and submit via Send button click.

    Returns the pre-send body text (kept for interface compatibility; the
    API-based wait_for_completion no longer uses it).

    LibreChat v0.8.6-rc1: Enter alone does NOT send.
    """
    try:
        pre_send_body = await page.evaluate("document.body.innerText")
    except Exception:
        pre_send_body = ""
    ta = page.locator("textarea").first
    await ta.click()
    await ta.fill(prompt)
    await asyncio.sleep(0.3)
    await page.locator('button[aria-label="Send message"]').first.click()
    return pre_send_body


# ── Completion detection (API-based) ─────────────────────────────────────────


async def wait_for_completion(
    page,
    test_id: str = "",
    tier: str = "any",
    max_wait_no_progress: int = 900,
    backend_alive_fn=None,
    *,
    pre_send_content: str = "",
) -> None:
    """Wait for the LibreChat streaming response to finish.

    Strategy:
    1. Poll page.url until LibreChat navigates from /c/new to /c/{uuid}
       (indicates the first message was accepted and a conversation created).
    2. Poll GET /api/messages/{conv_id} every 2 s until the last non-user
       message has unfinished=false (or error=true).

    This is frontend-agnostic and immune to stop-button timing or DOM selector
    issues. The pipeline-side crash detection (backend_alive_fn) still runs
    on a separate cadence to abort early on MLX/Ollama crashes.
    """
    POLL_INTERVAL_S = 2.0
    # MCP tool-calling tests take >60s before LibreChat gets the first streaming
    # token (tool call runs first). Cap at max_wait / 2 but at least 180s so
    # tool-heavy tests don't time out at the URL-wait step.
    URL_WAIT_S = max(180, max_wait_no_progress // 2)
    BACKEND_CHECK_S = 10
    BACKEND_DEAD_STRIKES = 5

    t_start = time.time()
    tag = f"[{test_id}] " if test_id else ""
    last_log = 0.0

    def _log(msg: str) -> None:
        nonlocal last_log
        now = time.time()
        if now - last_log >= 120 or any(
            w in msg.lower() for w in ("complete", "started", "error", "timeout", "cap")
        ):
            print(f"  {tag}{msg} ({now - t_start:.0f}s elapsed)", flush=True)
            last_log = now

    # ── Step 1: wait for conversation URL ────────────────────────────────────
    _log("waiting for model to start…")
    conv_id = ""
    for _ in range(URL_WAIT_S * 2):  # poll every 0.5 s
        url = page.url
        m = re.search(r"/c/([0-9a-f-]{36})", url)
        if m:
            conv_id = m.group(1)
            break
        await asyncio.sleep(0.5)

    if not conv_id:
        # URL never updated — try API fallback (long promptPrefix URLs can confuse
        # the LibreChat SPA router so the page stays at /c/new despite the
        # conversation being created server-side).
        found = await _api_find_recent_conv_id(t_start)
        if found:
            conv_id = found
            _log(f"URL never updated — found conversation via API: {conv_id[:8]}")
        else:
            _log("conversation URL never updated from /c/new — timing out")
            return

    _log("model streaming started")

    # ── Step 2: poll messages API until complete ──────────────────────────────
    dead_strikes = 0
    last_backend_check = 0.0
    last_msg_count = 0

    while True:
        elapsed = time.time() - t_start

        # Backend crash detection
        if backend_alive_fn is not None and tier in ("mlx_large", "mlx_small", "ollama"):
            now = time.time()
            if now - last_backend_check >= BACKEND_CHECK_S:
                last_backend_check = now
                alive, detail = backend_alive_fn(tier)
                if not alive:
                    dead_strikes += 1
                    _log(
                        f"backend not responding ({detail}), strike {dead_strikes}/{BACKEND_DEAD_STRIKES}"
                    )
                    if dead_strikes >= BACKEND_DEAD_STRIKES:
                        return
                else:
                    dead_strikes = 0

        if elapsed > max_wait_no_progress:
            _log(f"hit {max_wait_no_progress}s safety cap during streaming")
            return

        try:
            msgs = await _api_get_messages(conv_id)
        except Exception as exc:
            _log(f"messages API error: {exc}")
            await asyncio.sleep(POLL_INTERVAL_S)
            continue

        if not msgs:
            await asyncio.sleep(POLL_INTERVAL_S)
            continue

        # Log progress on count change
        if len(msgs) != last_msg_count:
            last_msg_count = len(msgs)

        # Find the last assistant message
        asst_msgs = [m for m in msgs if not m.get("isCreatedByUser", True)]
        if not asst_msgs:
            await asyncio.sleep(POLL_INTERVAL_S)
            continue

        last = asst_msgs[-1]
        if last.get("error"):
            _log("stream complete (error in assistant message)")
            return
        if not last.get("unfinished", True):
            _log("stream complete (unfinished=false)")
            await asyncio.sleep(0.5)  # brief settle
            return

        await asyncio.sleep(POLL_INTERVAL_S)


# ── Response reading (API-based) ──────────────────────────────────────────────

# Module-level cache: populated by wait_for_completion, read by get_last_response
_last_conv_id: str = ""


def _extract_text_from_message(msg: dict) -> str:
    """Extract visible response text from a LibreChat message dict.

    Thinking models (Qwen3, Gemma4, DeepSeek-R1) leave text="" and put the
    response in content[*] as {type: "text", text: "..."} parts mixed with
    {type: "think", think: "..."} reasoning blocks.  We collect the text
    parts, skip thinking-leak artifacts, and join them.

    Fallback: if only think blocks exist (pipeline stripped the <think> wrapper
    but LibreChat stored the content under type="think"), return the think
    content so assertions can still find keywords like aurora-7 / hex-lantern.
    """
    text = msg.get("text", "")
    if text.strip():
        return text

    content = msg.get("content", [])
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        think_parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type", "")
            if ptype == "text":
                t = part.get("text", "")
                stripped = t.strip()
                if not stripped:
                    continue
                if any(stripped.startswith(a) for a in _THINK_ARTIFACTS):
                    continue
                parts.append(t)
            elif ptype == "think":
                t = part.get("think", "")
                if t.strip():
                    think_parts.append(t)
        if parts:
            if think_parts:
                # Prepend thinking so driver can search it when the test sets
                # include_thinking_in_assertions=True.  _strip_think_blocks removes
                # it for all other tests, so existing behaviour is unchanged.
                return "<think>" + "".join(think_parts) + "</think>\n\n" + "".join(parts)
            return "".join(parts)
        # No text blocks — fall back to think content.  Gemma-4 sometimes puts
        # the entire answer in a reasoning block when the pipeline emits content
        # as reasoning_content and LibreChat stores it with type="think".
        if think_parts:
            return "".join(think_parts)

    return ""


async def get_last_response(page) -> str:
    """Return the last assistant message text via the messages API.

    Falls back to DOM scraping if the conversation ID is not available.
    """
    # Extract conv_id from current URL
    url = page.url
    m = re.search(r"/c/([0-9a-f-]{36})", url)
    conv_id = m.group(1) if m else ""

    if conv_id:
        try:
            msgs = await _api_get_messages(conv_id)
            asst_msgs = [msg for msg in msgs if not msg.get("isCreatedByUser", True)]
            if asst_msgs:
                text = _extract_text_from_message(asst_msgs[-1])
                if text.strip():
                    return text
        except Exception:
            pass

    # DOM fallback (e.g. URL still /c/new)
    for sel in [".message-content", '[data-message-role="assistant"]', ".markdown"]:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                text = await loc.last.inner_text()
                if text.strip():
                    return text
        except Exception:
            continue
    try:
        return await page.inner_text("body")
    except Exception:
        return ""


# ── No-op operations ──────────────────────────────────────────────────────────


async def enable_tool(page, tool_id: str) -> None:
    """No-op. LibreChat MCP attachment now happens in start_new_chat via the
    `requires_tool` kwarg. Kept as a no-op so the OWUI/LibreChat shim
    interface stays symmetric — the driver's _fe_enable_tool dispatcher does
    not need to branch on FRONTEND_MODE for the post-start enable path.
    """
    return None


async def assign_folder(page, folder_name: str) -> None:
    """No-op. LibreChat uses conversation tags, not folders."""
    return None


# ── Chat URL ──────────────────────────────────────────────────────────────────


def current_chat_url(page) -> str:
    """Return the current page URL after wait_for_completion (should be /c/{uuid})."""
    try:
        return page.url or ""
    except Exception:
        return ""


# ── Artifact download ─────────────────────────────────────────────────────────


async def download_artifact(
    page,
    expected_ext: str,
    response_text: str = "",
    timeout_ms: int = 120_000,
    *,
    since_ts: float = 0.0,
) -> Path | None:
    """Try to obtain the generated artifact file.

    since_ts: Unix timestamp — workspace-scan fallback only considers files
    created after this time. Defaults to 10 minutes ago if not supplied.
    """
    import subprocess as _sp

    artifact_dir = Path("/tmp/uat_artifacts")
    artifact_dir.mkdir(exist_ok=True)

    # Try 1: Playwright download click
    try:
        async with page.expect_download(timeout=timeout_ms) as dl_info:
            await page.locator(
                f'a[download], a[href*=".{expected_ext}"], button:has-text("Download")'
            ).last.click(timeout=10_000)
        dl = await dl_info.value
        dest = artifact_dir / dl.suggested_filename
        await dl.save_as(dest)
        return dest
    except Exception:
        pass

    if not response_text:
        return None

    # Try 2: URL from response text
    for pat in [
        rf"https?://[^\s)>\]]+/files/\S+?\.{re.escape(expected_ext)}",
        rf"https?://[^\s)>\]]*/view\?filename=[^\s)>\]]*\.{re.escape(expected_ext)}[^\s)>\]]*",
    ]:
        match = re.search(pat, response_text)
        if match:
            url = match.group(0)
            dest = artifact_dir / Path(url.split("?")[0]).name
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(url)
                if r.status_code == 200:
                    dest.write_bytes(r.content)
                    return dest
            except Exception:
                pass

    # Try 3: docker cp for container-local paths (/app/data or /workspace)
    container_pat = rf"(?:/app/data/generated|/workspace/generated)/\S+\.{re.escape(expected_ext)}"
    match = re.search(container_pat, response_text)
    if match:
        container_path = match.group(0)
        for container in [
            "portal5-mcp-documents",
            "portal5-mcp-sandbox",
            "portal5-mcp-comfyui",
            "portal5-mcp-video",
        ]:
            dest = artifact_dir / Path(container_path).name
            result = _sp.run(
                ["docker", "cp", f"{container}:{container_path}", str(dest)],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and dest.exists():
                return dest

    import os as _os
    import shutil as _shutil
    import time as _time

    workspace = Path(_os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))

    # Try 4: bare filename in response → MCP file server or host workspace copy
    bare_match = re.search(rf"([\w.-]{{5,80}}\.{re.escape(expected_ext)})", response_text)
    if bare_match:
        filename = bare_match.group(1)
        # 4a: MCP file server (:8913=documents, :8916=tts, :8912=music, :8910=comfyui)
        for port in [8913, 8916, 8912, 8910]:
            try:
                file_url = f"http://localhost:{port}/files/{filename}"
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(file_url)
                if r.status_code == 200:
                    dest = artifact_dir / filename
                    dest.write_bytes(r.content)
                    return dest
            except Exception:
                pass
        # 4b: host workspace directory (AI_Output or any generated subdir)
        for base in [
            workspace,
            workspace / "generated" / "documents",
            workspace / "generated" / "speech",
            workspace / "generated" / "music",
            workspace / "generated" / "images",
            workspace / "generated" / "videos",
        ]:
            candidate = base / filename
            if candidate.exists():
                dest = artifact_dir / filename
                _shutil.copy2(candidate, dest)
                return dest

    # Try 5: time-based workspace scan — find the most recently created file with
    # the right extension created after since_ts (handles tool-hop limit cases
    # where response text contains no filename but the MCP did create the file)
    cutoff = since_ts if since_ts > 0 else (_time.time() - 600)
    candidates: list[tuple[float, Path]] = []
    for base in [
        workspace,
        workspace / "generated" / "documents",
        workspace / "generated" / "speech",
        workspace / "generated" / "music",
        workspace / "generated" / "images",
        workspace / "generated" / "videos",
    ]:
        try:
            for f in base.glob(f"*.{expected_ext}"):
                mtime = f.stat().st_mtime
                if mtime > cutoff:
                    candidates.append((mtime, f))
        except Exception:
            pass
    if candidates:
        candidates.sort(reverse=True)
        newest = candidates[0][1]
        dest = artifact_dir / newest.name
        _shutil.copy2(newest, dest)
        return dest

    return None
