"""LibreChat Playwright driver for the Portal 5 UAT driver.

Pure DOM operation. No httpx, no /api/* calls. Auth state lives on the
Playwright browser context cookie jar after `login()`. Every helper accepts
a Playwright `page` and operates on the current DOM.

Selectors are validated against docs/UAT_LIBRECHAT_DOM_NOTES.md — update this
file IN SYNC with that doc when LibreChat ships a UI change.

Interface (mirrors the OWUI shape used in portal5_uat_driver.py via _fe_*):
  - login(page)
  - start_new_chat(page, model_slug, title, *, personas_map)
  - send_prompt(page, prompt)
  - wait_for_completion(page, test_id, tier, max_wait_no_progress, ...)
  - get_last_response(page)
  - enable_tool(page, tool_id)   # no-op
  - assign_folder(page, folder_name)   # no-op
  - download_artifact(page, expected_ext, response_text, timeout_ms)
  - current_chat_url(page)
  - load_personas_map() -> dict[slug, preset_title]

Backend timeout / crash detection is driven from the calling code in
portal5_uat_driver.py — these helpers do not poll Ollama or MLX directly.

Note: `get_routed_model` is intentionally absent. The model that handled a
request is read from pipeline logs (frontend-independent), not from the
LibreChat DOM. See `_fe_get_routed_model` in `tests/portal5_uat_driver.py`
and `docs/UAT_LIBRECHAT_DOM_NOTES.md` § Routed-model readout.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import time
from pathlib import Path

import yaml

LIBRECHAT_URL = os.environ.get("LIBRECHAT_URL", "http://localhost:8082")
LIBRECHAT_EMAIL = os.environ.get(
    "LIBRECHAT_ADMIN_EMAIL", os.environ.get("OPENWEBUI_ADMIN_EMAIL", "admin@portal.local")
)
LIBRECHAT_PASSWORD = os.environ.get("LIBRECHAT_ADMIN_PASSWORD", "")

# Module-level personas cache (populated by load_personas_map on first call)
_PERSONAS_MAP: dict[str, str] | None = None


# ── Persona preset map ───────────────────────────────────────────────────────


def load_personas_map(personas_dir: Path | None = None) -> dict[str, str]:
    """Build {slug: preset_title} so the driver can find the right preset by slug.

    Mirrors the seeding logic in scripts/frontend_seeder/adapters/librechat.py
    (`title = f"🎭 {name}"`). Cached after first call.
    """
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
    # Stash the fallback details alongside the title map. Stored as a wrapper
    # dict so callers can pull either piece via the slug key.
    _PERSONAS_MAP = result
    # Side channel for fallback (used by start_new_chat when preset click fails)
    load_personas_map._systems = persona_systems  # type: ignore[attr-defined]
    load_personas_map._models = persona_models  # type: ignore[attr-defined]
    return result


# ── Auth ─────────────────────────────────────────────────────────────────────


async def login(page) -> None:
    """Fill email/password, click submit, wait for the chat composer."""
    if not LIBRECHAT_PASSWORD:
        raise RuntimeError(
            "LIBRECHAT_ADMIN_PASSWORD is empty — set it in .env before running --frontend librechat"
        )
    await page.goto(LIBRECHAT_URL, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_selector('input[type="email"], input[name="email"]', timeout=20_000)
    await page.fill('input[type="email"], input[name="email"]', LIBRECHAT_EMAIL)
    await page.fill('input[type="password"], input[name="password"]', LIBRECHAT_PASSWORD)
    await page.locator('button[type="submit"]').first.click()
    # Wait for the chat composer (login succeeded). LibreChat uses WebSockets;
    # "networkidle" never fires, so we wait on the composer directly.
    await page.wait_for_selector("textarea, nav, [class*='sidebar']", timeout=20_000)
    # Settle for the UI to render the agent selector
    await asyncio.sleep(1.0)


# ── Chat creation ────────────────────────────────────────────────────────────


async def start_new_chat(
    page,
    model_slug: str,
    title: str,
    *,
    personas_map: dict[str, str] | None = None,
) -> str:
    """Open a fresh conversation. Returns the current page URL after navigation.

    For workspace tests (model_slug = "auto", "auto-coding", ...) — select the
    Portal 5 endpoint model from the model picker.

    For persona tests (model_slug = "techreviewer", "techwriter", ...) — try to
    click the seeded preset `🎭 {name}`. If the preset is not reachable, fall
    back to selecting the persona's workspace_model and pasting the persona's
    system_prompt into the Custom Instructions field. If both fail, raise
    PresetUnreachable so the runner can record SKIP with a clear reason.

    The chat URL is captured AFTER the first message lands in send_prompt /
    wait_for_completion (that's when LibreChat assigns the conversation_id).
    Here we return the new-chat URL for navigation purposes only.
    """
    if personas_map is None:
        personas_map = load_personas_map()

    await page.goto(f"{LIBRECHAT_URL}/c/new", wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_selector("textarea, nav, [class*='sidebar']", timeout=20_000)
    await asyncio.sleep(1.0)

    if model_slug in personas_map:
        # Persona test — preset-click path
        try:
            await _select_preset(page, personas_map[model_slug])
            return page.url
        except _PresetNotFoundError:
            pass

        # Fallback: workspace_model + custom instructions
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
        # Workspace test — select the workspace model directly
        await _select_workspace_model(page, model_slug)
        return page.url


class PresetUnreachableError(RuntimeError):
    """Raised when neither the preset nor the fallback persona-injection path works."""


class _PresetNotFoundError(RuntimeError):
    """Internal — preset click failed, try fallback."""


class _CustomInstructionsNotFoundError(RuntimeError):
    """Internal — fallback path's UI is also unavailable."""


async def _select_preset(page, preset_title: str) -> None:
    """Click a preset by title.

    Selectors verified against docs/UAT_LIBRECHAT_DOM_NOTES.md:
    - Preset button: button[aria-label="Presets"]
    - Preset row: click by text match

    LibreChat v0.8.6-rc1: presets are accessible via the "Presets" button
    in the chat header area.
    """
    # Open the presets popover
    # Note: aria-label has a leading space (" Presets", not "Presets")
    preset_btn = page.locator('#presets-button, button[aria-label=" Presets"]').first
    try:
        await preset_btn.click(timeout=5000)
    except Exception as exc:
        raise _PresetNotFoundError(f"Presets button not clickable: {exc}") from exc

    await asyncio.sleep(0.5)

    # Click the row with this title — match by text content.
    # Presets are listed in a popover/menu; clicking the title text activates it.
    try:
        await page.get_by_text(preset_title, exact=False).first.click(timeout=5000)
    except Exception as exc:
        raise _PresetNotFoundError(f"preset row '{preset_title}' not clickable: {exc}") from exc

    # Brief settle so the model/system-prompt apply before the next action
    await asyncio.sleep(0.5)


async def _select_workspace_model(page, model_slug: str) -> None:
    """Pick the given workspace model from the endpoint/model picker.

    Verified selector: button[aria-label="Select a model"] — displays "My Agents" text.
    The model list is a dropdown containing all seeded agents + Portal 5 endpoint models.
    """
    # Click the model/agent picker button
    model_btn = page.locator('button[aria-label="Select a model"]').first
    try:
        await model_btn.click(timeout=5000)
    except Exception:
        # Fallback: try aria-label match
        try:
            await page.locator('button[aria-label*="model" i]').first.click(timeout=5000)
        except Exception as exc:
            raise RuntimeError(f"model picker not clickable: {exc}") from exc

    await asyncio.sleep(0.5)

    # Click the row matching the model slug. In LibreChat v0.8.6-rc1,
    # workspace models appear as agents in the dropdown list.
    try:
        await page.get_by_text(model_slug, exact=True).first.click(timeout=5000)
    except Exception:
        # Try a fuzzy match (slug may render with display label)
        with contextlib.suppress(Exception):
            await page.get_by_text(model_slug, exact=False).first.click(timeout=5000)

    await asyncio.sleep(0.5)


async def _set_custom_instructions(page, sysprompt: str) -> None:
    """Open the per-conversation settings, fill the system-prompt textarea, save.

    LibreChat v0.8.6-rc1 does NOT expose a per-conversation "Custom Instructions"
    or promptPrefix textarea in the standard chat UI. The Agent Builder sidebar
    tool can create agents with system prompts, but this is not accessible
    programmatically for ad-hoc per-test injection.

    This function intentionally raises _CustomInstructionsNotFound — the fallback
    path is not viable on this LibreChat version. Preset-based persona selection
    (clicking a seeded agent) is the primary path.
    """
    raise _CustomInstructionsNotFoundError(
        "LibreChat v0.8.6-rc1 does not have a per-conversation system-prompt textarea. "
        "Use preset-based persona selection instead."
    )


# ── Send + completion ────────────────────────────────────────────────────────


async def send_prompt(page, prompt: str) -> str:
    """Fill the composer and submit. Returns the pre-send body text as a baseline.

    The caller should pass the returned value to wait_for_completion as
    pre_send_content so Phase 1 can detect response growth even for fast
    models that respond in <500 ms (before wait_for_completion would otherwise
    capture its own baseline).

    LibreChat v0.8.6-rc1: Enter alone does NOT send — must click the Send button.
    """
    # Capture baseline BEFORE filling — the model has definitely not responded yet.
    try:
        pre_send_body = await page.evaluate("document.body.innerText")
    except Exception:
        pre_send_body = ""
    ta = page.locator("textarea").first
    await ta.click()
    await ta.fill(prompt)
    await asyncio.sleep(0.3)
    # Click the Send button (Enter does not submit in LibreChat)
    await page.locator('button[aria-label="Send message"]').first.click()
    return pre_send_body


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

    Detection signal: stop button appears → disappears. DOM stability is a
    secondary signal. LibreChat does NOT inject <details type="reasoning">
    around <think> tokens, so DOM-stable detection works cleanly without the
    OWUI API-polling workaround.

    `backend_alive_fn` is an optional callable `(tier) -> (bool, str)` passed
    from the main driver to detect MLX/Ollama crashes during long waits. If
    omitted, the wait runs without crash detection.
    """
    PHASE1_FAST_S = 0.5
    PHASE1_FAST_DURATION_S = 10
    PHASE1_MID_S = 2.0
    PHASE1_MID_DURATION_S = 30
    PHASE1_SLOW_S = 5.0
    PHASE2_STREAMING_POLL_S = 1.5
    PHASE2_DOM_STABLE_NEEDED = 3
    PROGRESS_LOG_INTERVAL = 120
    BACKEND_DEAD_STRIKES = 5

    def _stop_selector() -> str:
        return 'button[aria-label*="Stop" i], button[title*="Stop"], button:has-text("Stop")'

    async def _stop_visible() -> bool:
        try:
            btn = page.locator(_stop_selector())
            return await btn.count() > 0 and await btn.first.is_visible()
        except Exception:
            return False

    t_start = time.time()
    last_log = 0.0
    # Capture .message-content count right now (after send_prompt, so the user
    # message is already in the DOM). When the model responds, a new element
    # appears — count goes above this baseline. Used by fast-completion path.
    try:
        msg_count_start = await page.locator(".message-content").count()
    except Exception:
        msg_count_start = 0
    # Phase 2 DOM-stable baseline: use pre-send snapshot if the caller provided
    # one, otherwise fall back to the current page state.
    if pre_send_content:
        prev_text = pre_send_content
    else:
        try:
            prev_text = await page.evaluate("document.body.innerText")
        except Exception:
            prev_text = ""
    stable_count = 0
    stop_seen = False
    dead_strikes = 0
    last_backend_check = 0.0

    def _log(msg: str) -> None:
        nonlocal last_log
        now = time.time()
        msg_lower = msg.lower()
        if (
            now - last_log >= PROGRESS_LOG_INTERVAL
            or "complete" in msg_lower
            or "started" in msg_lower
        ):
            elapsed = now - t_start
            tag = f"[{test_id}] " if test_id else ""
            print(f"  {tag}{msg} ({elapsed:.0f}s elapsed)", flush=True)
            last_log = now

    def _check_backend_crash() -> bool:
        nonlocal dead_strikes, last_backend_check
        if backend_alive_fn is None or tier not in ("mlx_large", "mlx_small", "ollama"):
            return False
        now = time.time()
        if now - last_backend_check < 5.0:
            return False
        last_backend_check = now
        alive, detail = backend_alive_fn(tier)
        if not alive:
            dead_strikes += 1
            tag = f"[{test_id}] " if test_id else ""
            print(
                f"  {tag}backend not responding ({detail}), "
                f"strike {dead_strikes}/{BACKEND_DEAD_STRIKES}",
                flush=True,
            )
            return dead_strikes >= BACKEND_DEAD_STRIKES
        dead_strikes = 0
        return False

    def _phase1_interval(elapsed: float) -> float:
        if elapsed < PHASE1_FAST_DURATION_S:
            return PHASE1_FAST_S
        if elapsed < PHASE1_FAST_DURATION_S + PHASE1_MID_DURATION_S:
            return PHASE1_MID_S
        return PHASE1_SLOW_S

    # Phase 1: wait for stream to start.
    # Primary signal: stop button appears (streaming in progress).
    # Fast-completion path: .message-content count exceeds the baseline set
    # right after send_prompt (user message already counted). A new element
    # means the assistant responded — stop button already gone by then.
    _log("waiting for model to start…")
    while True:
        elapsed = time.time() - t_start
        if await _stop_visible():
            stop_seen = True
            _log("model streaming started")
            break
        # Fast-completion: new .message-content appeared and stop button gone
        try:
            mc = await page.locator(".message-content").count()
            if mc > msg_count_start and not await _stop_visible():
                _log("fast completion — new message-content appeared without stop button")
                await asyncio.sleep(2.0)  # settle for DOM render
                return
        except Exception:
            pass
        if _check_backend_crash():
            return
        if elapsed > max_wait_no_progress:
            _log(f"hit {max_wait_no_progress}s safety cap waiting for start")
            return
        await asyncio.sleep(_phase1_interval(elapsed))

    # Phase 2: wait for stream to end
    while True:
        elapsed = time.time() - t_start

        if await _stop_visible():
            if not stop_seen:
                stop_seen = True
                stable_count = 0
                _log("stop button appeared in Phase 2 — streaming active")
        elif stop_seen:
            await asyncio.sleep(2.0)
            if await _stop_visible():
                stable_count = 0
                _log("stop button reappeared (thinking transition) — resuming")
            else:
                _log("stream complete (stop button gone)")
                await asyncio.sleep(2.0)  # settle for DOM render
                return

        curr = await page.evaluate("document.body.innerText")
        if curr == prev_text:
            stable_count += 1
            stop_still_active = stop_seen and await _stop_visible()
            if stable_count >= PHASE2_DOM_STABLE_NEEDED and not stop_still_active:
                _log("stream complete (DOM stable)")
                await asyncio.sleep(2.0)
                return
        else:
            stable_count = 0
            prev_text = curr

        if _check_backend_crash():
            return
        if elapsed > max_wait_no_progress:
            _log(f"hit {max_wait_no_progress}s safety cap during streaming")
            return

        await asyncio.sleep(PHASE2_STREAMING_POLL_S)


# ── Response reading ─────────────────────────────────────────────────────────


async def get_last_response(page) -> str:
    """Extract the last assistant message text from the rendered DOM.

    Verified selector: .message-content (LibreChat v0.8.6-rc1).
    """
    container_candidates = [
        ".message-content",
        '[data-message-role="assistant"]',
        ".markdown",
    ]
    for sel in container_candidates:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                text = await loc.last.inner_text()
                if text.strip():
                    return text
        except Exception:
            continue
    # Last-resort fallback: full body
    try:
        return await page.inner_text("body")
    except Exception:
        return ""


# ── No-op operations (deliberate — LibreChat handles these differently) ──────


async def enable_tool(page, tool_id: str) -> None:
    """No-op. LibreChat tools are global per librechat.yaml mcpServers map.

    Tool dispatch on Portal 5's pipeline is identical regardless of which
    frontend posts the request — the pipeline injects tool definitions and
    handles tool_calls before the response streams back to LibreChat.
    """
    return None


async def assign_folder(page, folder_name: str) -> None:
    """No-op. LibreChat does not have a folder concept — uses conversation tags.

    Operators review the run by sorting the conversation list by date. The
    test report's chat-URL link is sufficient for per-test review.
    """
    return None


# ── Chat URL + artifact download ─────────────────────────────────────────────


def current_chat_url(page) -> str:
    """Return the current page URL — used as the report row's chat link.

    After the first message lands LibreChat replaces /c/new with /c/{id}.
    Call this after wait_for_completion returns to get the stable URL.
    """
    try:
        return page.url or ""
    except Exception:
        return ""


async def download_artifact(
    page, expected_ext: str, response_text: str = "", timeout_ms: int = 120_000
) -> Path | None:
    """Try to obtain the generated artifact file.

    LibreChat surfaces file attachments differently from OWUI; the file
    attachment UI selector lives in UAT_LIBRECHAT_DOM_NOTES.md § File
    attachment download. The URL-from-response-text fallback (already used by
    the OWUI path) works identically — Portal 5's MCP servers emit absolute
    download URLs in the assistant message.
    """
    import subprocess as _sp

    import httpx as _httpx

    artifact_dir = Path("/tmp/uat_artifacts")
    artifact_dir.mkdir(exist_ok=True)

    # Try 1: Playwright download event from clicking the LibreChat attachment.
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

    # Try 2: URL extraction from response text (works for portal_* MCP servers
    # that emit /files/<name>.<ext> or ComfyUI /view?filename=<name>.<ext> URLs)
    if response_text:
        url_pat = rf"https?://[^\s)>\]]+/files/\S+?\.{re.escape(expected_ext)}"
        m = re.search(url_pat, response_text)
        if m:
            url = m.group(0)
            dest = artifact_dir / Path(url).name
            try:
                r = _httpx.get(url, timeout=30)
                if r.status_code == 200:
                    dest.write_bytes(r.content)
                    return dest
            except Exception:
                pass

        comfyui_pat = (
            rf"https?://[^\s)>\]]*/view\?filename=[^\s)>\]]*\.{re.escape(expected_ext)}[^\s)>\]]*"
        )
        m = re.search(comfyui_pat, response_text)
        if m:
            from urllib.parse import parse_qs, urlparse

            url = m.group(0)
            qs = parse_qs(urlparse(url).query)
            fname = qs.get("filename", ["unknown"])[0]
            dest = artifact_dir / Path(fname).name
            try:
                r = _httpx.get(url, timeout=30)
                if r.status_code == 200:
                    dest.write_bytes(r.content)
                    return dest
            except Exception:
                pass

        container_pat = rf"/app/data/generated/\S+\.{re.escape(expected_ext)}"
        m = re.search(container_pat, response_text)
        if m:
            container_path = m.group(0)
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
