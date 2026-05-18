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
import contextlib
import os
import re
import time
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


# ── Chat creation ─────────────────────────────────────────────────────────────


async def start_new_chat(
    page,
    model_slug: str,
    title: str,
    *,
    personas_map: dict[str, str] | None = None,
) -> str:
    """Open a fresh conversation. Returns the current page URL."""
    if personas_map is None:
        personas_map = load_personas_map()

    await page.goto(f"{LIBRECHAT_URL}/c/new", wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_selector("textarea, nav, [class*='sidebar']", timeout=20_000)
    await asyncio.sleep(1.0)

    if model_slug in personas_map:
        try:
            await _select_preset(page, personas_map[model_slug])
            return page.url
        except _PresetNotFoundError:
            pass

        systems = getattr(load_personas_map, "_systems", {})
        models = getattr(load_personas_map, "_models", {})
        ws_model = models.get(model_slug, "auto")
        sysprompt = systems.get(model_slug, "")
        try:
            await _select_workspace_model(page, ws_model)
            if sysprompt:
                await _set_custom_instructions(page, sysprompt)
            return page.url
        except _CustomInstructionsNotFoundError as exc:
            raise PresetUnreachableError(
                f"persona '{model_slug}' preset not visible and Custom Instructions UI not found: {exc}"
            ) from exc
    else:
        await _select_workspace_model(page, model_slug)
        return page.url


class PresetUnreachableError(RuntimeError):
    pass


class _PresetNotFoundError(RuntimeError):
    pass


class _CustomInstructionsNotFoundError(RuntimeError):
    pass


async def _select_preset(page, preset_title: str) -> None:
    preset_btn = page.locator('#presets-button, button[aria-label=" Presets"]').first
    try:
        await preset_btn.click(timeout=5000)
    except Exception as exc:
        raise _PresetNotFoundError(f"Presets button not clickable: {exc}") from exc
    await asyncio.sleep(0.5)
    try:
        await page.get_by_text(preset_title, exact=False).first.click(timeout=5000)
    except Exception as exc:
        raise _PresetNotFoundError(f"preset row '{preset_title}' not clickable: {exc}") from exc
    await asyncio.sleep(0.5)


async def _select_workspace_model(page, model_slug: str) -> None:
    model_btn = page.locator('button[aria-label="Select a model"]').first
    try:
        await model_btn.click(timeout=5000)
    except Exception:
        try:
            await page.locator('button[aria-label*="model" i]').first.click(timeout=5000)
        except Exception as exc:
            raise RuntimeError(f"model picker not clickable: {exc}") from exc
    await asyncio.sleep(0.5)
    try:
        await page.get_by_text(model_slug, exact=True).first.click(timeout=5000)
    except Exception:
        with contextlib.suppress(Exception):
            await page.get_by_text(model_slug, exact=False).first.click(timeout=5000)
    await asyncio.sleep(0.5)


async def _set_custom_instructions(page, sysprompt: str) -> None:
    raise _CustomInstructionsNotFoundError(
        "LibreChat v0.8.6-rc1 does not have a per-conversation system-prompt textarea. "
        "Use preset-based persona selection instead."
    )


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
    URL_WAIT_S = 60      # max wait for /c/new → /c/{uuid} navigation
    BACKEND_CHECK_S = 10
    BACKEND_DEAD_STRIKES = 5

    t_start = time.time()
    tag = f"[{test_id}] " if test_id else ""
    last_log = 0.0

    def _log(msg: str) -> None:
        nonlocal last_log
        now = time.time()
        if now - last_log >= 120 or any(w in msg.lower() for w in ("complete", "started", "error", "timeout", "cap")):
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
        # URL never updated — the message may not have been accepted
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
                    _log(f"backend not responding ({detail}), strike {dead_strikes}/{BACKEND_DEAD_STRIKES}")
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
    """
    text = msg.get("text", "")
    if text.strip():
        return text

    content = msg.get("content", [])
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "text":
                continue
            t = part.get("text", "")
            stripped = t.strip()
            if not stripped:
                continue
            if any(stripped.startswith(a) for a in _THINK_ARTIFACTS):
                continue
            parts.append(t)
        if parts:
            return "".join(parts)

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
    """No-op. LibreChat tools are global per librechat.yaml mcpServers map."""
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
    page, expected_ext: str, response_text: str = "", timeout_ms: int = 120_000
) -> Path | None:
    """Try to obtain the generated artifact file."""
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

    # Try 3: docker cp for container-local paths
    container_pat = rf"/app/data/generated/\S+\.{re.escape(expected_ext)}"
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

    return None
