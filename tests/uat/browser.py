"""Portal 5 UAT — Playwright helpers (login, send, completion-wait, artifacts).

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase C).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx

from tests.uat.config import (
    ADMIN_EMAIL,
    ADMIN_PASS,
    ARTIFACT_DIR,
    DOM_STABLE_API_EMPTY_MAX,
    MAX_WAIT_NO_PROGRESS,
    NO_STREAM_TIMEOUT,
    OPENWEBUI_URL,
    PHASE1_FAST_DURATION_S,
    PHASE1_FAST_S,
    PHASE1_MID_DURATION_S,
    PHASE1_MID_S,
    PHASE1_SLOW_S,
    PHASE2_DOM_STABLE_NEEDED,
    PHASE2_STREAMING_POLL_S,
    PROGRESS_LOG_INTERVAL,
)
from tests.uat.health import _backend_alive
from tests.uat.lifecycle import (
    _unload_running_ollama_models,
    _wait_for_ollama_ps_empty,
)
from tests.uat.owui_api import (
    _wait_for_response_arrival,
    owui_get_last_response,
    owui_response_complete,
)

# Playwright helpers
# ---------------------------------------------------------------------------


async def _dismiss_startup_overlays(page) -> None:
    """Dismiss Open WebUI release/onboarding overlays that cover the composer.

    Open WebUI may show a post-upgrade release-notes dialog after authentication.
    The chat input remains present in the DOM behind that dialog, so selector
    readiness alone is insufficient: Playwright finds the composer but cannot
    click it. Dismissing the explicit acknowledgement button keeps UAT aligned
    with the first-run operator experience without hiding arbitrary dialogs.
    """
    acknowledge = page.locator('button:has-text("Okay, Let\'s Go!")')
    if await acknowledge.count() > 0 and await acknowledge.first.is_visible():
        await acknowledge.first.click()
        await page.wait_for_timeout(250)


async def _login(page) -> None:
    await page.goto(OPENWEBUI_URL, wait_until="networkidle", timeout=30000)
    await page.wait_for_selector('input[type="email"]', timeout=15000)
    await page.fill('input[type="email"]', ADMIN_EMAIL)
    await page.fill('input[type="password"]', ADMIN_PASS)
    await page.locator('button[type="submit"], button:has-text("Sign in")').first.click()
    await page.wait_for_selector("textarea, [contenteditable]", timeout=20000)
    await _dismiss_startup_overlays(page)


async def _navigate_to_chat(page, chat_url: str) -> None:
    await page.goto(chat_url, wait_until="networkidle", timeout=60000)
    await page.wait_for_selector("textarea, [contenteditable='true']", timeout=30000)
    await page.wait_for_timeout(2000)


async def _stop_button_visible(page) -> bool:
    """Check if the stop/streaming button is currently visible.

    OWUI 0.9.5+ uses a round stop-circle SVG button with no aria-label or title.
    The stop-circle path includes the substring "9.564a1.312" (Heroicons stop-circle).
    """
    try:
        # Old OWUI: button with aria-label or title "Stop"
        btn = page.locator(
            'button[aria-label="Stop"], button[title="Stop"], button:has-text("Stop")'
        )
        if await btn.count() > 0 and await btn.first.is_visible():
            return True
        # OWUI 0.9.5+: round stop-circle SVG button without aria-label
        return bool(
            await page.evaluate(
                """() => {
                    for (const btn of document.querySelectorAll('button')) {
                        const path = btn.querySelector('svg path');
                        if (path && path.getAttribute('d')?.includes('9.564a1.312')) {
                            const r = btn.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) return true;
                        }
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


async def _wait_for_completion(
    page,
    test_id: str = "",
    tier: str = "any",
    max_wait_no_progress: int = MAX_WAIT_NO_PROGRESS,
    *,
    token: str = "",
    chat_id: str = "",
    min_messages: int = 1,
) -> None:
    """Progress-monitoring wait with tiered polling.

    Event-driven sibling of tests/lib/stream_wait.stream_chat (HTTP/SSE path):
    both treat token/DOM activity as the primary signal and the wall-clock as a
    last-resort ceiling. Keep the two in sync if the philosophy changes.

    Phase 1 (waiting for stream start): poll PHASE1_FAST_S → PHASE1_MID_S →
    PHASE1_SLOW_S as elapsed time grows. This catches warm-load starts (<2s)
    without forcing the same resolution on cold loads (30s+).

    Phase 2 (waiting for stream end): poll PHASE2_STREAMING_POLL_S while
    actively streaming. On stop-button-disappears edge, immediately verify
    via OWUI API (no fixed sleep). On DOM-stable path, the same 3-sample
    threshold now resolves in 4.5s instead of 90s.

    When token+chat_id are provided, the OWUI API is used as a parallel
    completion signal (early exit if content lands while DOM is stable)
    and as the canonical post-stream persistence wait (replacing fixed
    sleep(5)). When absent, falls back to a 2s safety buffer.

    Backend crash detection unchanged: BACKEND_DEAD_STRIKES consecutive
    health failures aborts early.
    """
    BACKEND_DEAD_STRIKES = 5

    t_start = time.time()
    last_log = 0.0
    prev_text = ""
    stable_count = 0
    stop_seen = False
    dead_strikes = 0
    last_backend_check = 0.0
    # API-driven tracking: content length from last poll. Used in Phase 2 to
    # prevent DOM-stable from firing while the model is still generating output.
    _prev_api_len = 0
    # Counter for consecutive "DOM stable but API empty" cycles. After
    # DOM_STABLE_API_EMPTY_MAX cycles we assume OWUI won't commit via API
    # and return early so the caller's DOM fallback can extract the response.
    _dom_stable_empty_count = 0

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
        """Return True if backend looks crashed (should abort wait).

        Rate-limited to ~once per 5s so high-frequency Phase 1/2 polls don't
        spam the health endpoint.
        """
        nonlocal dead_strikes, last_backend_check
        now = time.time()
        if now - last_backend_check < 5.0:
            return False
        last_backend_check = now
        if tier not in ("ollama",):
            return False
        alive, detail = _backend_alive(tier)
        if not alive:
            dead_strikes += 1
            tag = f"[{test_id}] " if test_id else ""
            print(
                f"  {tag}backend not responding ({detail}), strike {dead_strikes}/{BACKEND_DEAD_STRIKES}",
                flush=True,
            )
            if dead_strikes >= BACKEND_DEAD_STRIKES:
                print(f"  {tag}backend crashed — aborting wait early", flush=True)
                return True
        else:
            dead_strikes = 0
        return False

    def _phase1_interval(elapsed: float) -> float:
        """Tiered poll interval for Phase 1 (waiting for stream start)."""
        if elapsed < PHASE1_FAST_DURATION_S:
            return PHASE1_FAST_S
        if elapsed < PHASE1_FAST_DURATION_S + PHASE1_MID_DURATION_S:
            return PHASE1_MID_S
        return PHASE1_SLOW_S

    # Phase 1: wait for stop button to appear (model starts generating)
    _log("waiting for model to start…")
    while True:
        elapsed = time.time() - t_start
        if await _stop_button_visible(page):
            stop_seen = True
            _log("model streaming started")
            break
        # If no stop button but text is growing, model may be generating
        # without showing a stop button (some OWUI versions)
        curr = await page.evaluate("document.body.innerText")
        if curr != prev_text and len(curr) > len(prev_text) + 50:
            _log("text growing without stop button — treating as streaming")
            prev_text = curr
            break
        # Backend crash check — don't burn 900s on a dead model
        if _check_backend_crash():
            _unload_running_ollama_models()
            _wait_for_ollama_ps_empty(timeout_s=15.0)
            return
        # Hard safety cap
        if elapsed > max_wait_no_progress:
            _log(f"hit {max_wait_no_progress}s safety cap waiting for start")
            return
        await asyncio.sleep(_phase1_interval(elapsed))

    # Phase 2: wait for streaming to complete
    while True:
        elapsed = time.time() - t_start

        # Re-check stop button each poll — Phase 1 may have used the "text growing"
        # fallback path (stop_seen=False). If the stop button appears during Phase 2
        # (model started proper streaming after initial text growth), update stop_seen
        # and reset stable_count so the DOM stable gate works correctly.
        if await _stop_button_visible(page):
            if not stop_seen:
                stop_seen = True
                stable_count = 0
                _log("stop button appeared in Phase 2 — streaming active")
        elif stop_seen:
            # Stop button was seen and is now gone. For thinking models (AEON,
            # Qwen3), the button briefly disappears during the reasoning→response
            # transition before streaming continues. Wait 2s and re-check before
            # committing to "stream complete" to avoid false early exits.
            await asyncio.sleep(2.0)
            if await _stop_button_visible(page):
                stable_count = 0
                _log("stop button reappeared (thinking model transition) — resuming")
            else:
                _log("stream complete (stop button gone)")
                if token and chat_id:
                    await _wait_for_response_arrival(token, chat_id, min_messages=min_messages)
                else:
                    await asyncio.sleep(2.0)
                return

        # API-driven content tracking: fetch current API response length each poll.
        # If content grew since last poll (model still generating response), reset
        # DOM stable count — prevents <details type="reasoning"> collapsed blocks
        # from triggering a false DOM-stable exit while the model is still active.
        # This is the log-driven completion signal: content changes drive the
        # decision, not wall-clock timers.
        _cur_api_text = ""
        if token and chat_id:
            _cur_api_text = owui_get_last_response(token, chat_id, min_messages=min_messages)
            _cur_api_len = len(_cur_api_text)
            if _cur_api_text and owui_response_complete(token, chat_id, min_messages=min_messages):
                _log("stream complete (OWUI API done)")
                return
            if _cur_api_len > _prev_api_len + 100:
                # Content actively growing — model still generating; don't let DOM
                # stability fire prematurely
                stable_count = 0
                _log(f"API content growing ({_prev_api_len}→{_cur_api_len} chars) — resuming")
            _prev_api_len = _cur_api_len

        # Check DOM stability as secondary signal — only when stop button is gone
        # (or never appeared). Reasoning models emit <details type="reasoning">
        # blocks that collapse in the DOM, making innerText appear stable while
        # the model is still streaming the actual response. Gating on stop button
        # prevents false-stable triggers during hidden reasoning token generation.
        curr = await page.evaluate("document.body.innerText")
        if curr == prev_text:
            stable_count += 1
            stop_still_active = stop_seen and await _stop_button_visible(page)
            if stable_count >= PHASE2_DOM_STABLE_NEEDED and not stop_still_active:
                # Before declaring done via DOM, verify via API (reuse _cur_api_text
                # already fetched this poll — no extra HTTP request).
                # If API has content → run stabilization-wait then done.
                # If API is empty but we have credentials → keep polling; the model
                # may still be in the reasoning phase and hasn't started output yet.
                if token and chat_id:
                    if _cur_api_text:
                        _log("stream complete (DOM stable + API has content)")
                        await _wait_for_response_arrival(token, chat_id, min_messages=min_messages)
                        return
                    else:
                        # DOM stable but API empty.
                        stable_count = 0
                        if stop_seen:
                            # Stop button WAS seen — model started streaming but OWUI
                            # 0.9.5+ hasn't committed to API yet (thinking-model case).
                            _dom_stable_empty_count += 1
                            _log("DOM stable but API empty — model still reasoning, continuing")
                            if _dom_stable_empty_count >= DOM_STABLE_API_EMPTY_MAX:
                                # Assume done; caller's _fe_get_last_response DOM
                                # fallback will extract directly from the page.
                                _log(
                                    f"DOM stable + API empty ×{_dom_stable_empty_count}"
                                    " — assuming completion, handing off to DOM fallback"
                                )
                                return
                        else:
                            # stop_seen=False: model still loading / processing prompt,
                            # not yet streaming. Don't apply DOM_STABLE_API_EMPTY_MAX —
                            # but DO cap at NO_STREAM_TIMEOUT to allow rapid retry when
                            # the request stalls before reaching the pipeline.
                            _log("DOM stable + API empty, model not yet streaming — waiting")
                            if elapsed > NO_STREAM_TIMEOUT:
                                _log(
                                    f"DOM stable + API empty after {elapsed:.0f}s with no"
                                    " stream start — exiting for retry"
                                )
                                return
                else:
                    _log("stream complete (DOM stable)")
                    await asyncio.sleep(2.0)
                    return
        else:
            stable_count = 0
            prev_text = curr

        # Backend crash check — rate-limited inside _check_backend_crash
        if _check_backend_crash():
            _unload_running_ollama_models()
            _wait_for_ollama_ps_empty(timeout_s=15.0)
            return

        # Safety cap
        if elapsed > max_wait_no_progress:
            _log(f"hit {max_wait_no_progress}s safety cap during streaming")
            return

        await asyncio.sleep(PHASE2_STREAMING_POLL_S)


async def _send_and_wait(
    page,
    prompt: str,
    test_id: str = "",
    tier: str = "any",
    max_wait_no_progress: int = MAX_WAIT_NO_PROGRESS,
    *,
    token: str = "",
    chat_id: str = "",
    min_messages: int = 1,
) -> None:
    """Send a prompt and wait for completion.

    When token+chat_id are supplied, _wait_for_completion uses the OWUI API
    as a parallel completion signal and replaces the fixed post-stream sleep
    with a bounded content-arrival poll. Caller still fetches the response
    via owui_get_last_response after this returns.

    min_messages: forwarded to _wait_for_completion. Set to 2 for multi-turn
    turn-2 calls so completion detection requires ≥ 2 committed assistant
    responses, preventing turn-1's stable content from firing a false early exit.
    """
    # Fill + submit for OWUI's contenteditable input.
    #
    # OWUI 0.9.5+ uses a contenteditable <div> for chat input. The send button
    # (#send-message-button) is rendered dynamically by Svelte when the draft
    # is non-empty. Svelte's reactivity requires a native browser `input` event
    # with inputType='insertText' — Playwright's ta.fill() on a contenteditable
    # dispatches an 'input' event via CDP's Input.insertText, but in a headless
    # cold-session context OWUI's Svelte handler sometimes misses it, leaving
    # the draft store empty and making the submit send a null message.
    #
    # document.execCommand('insertText') fires the DOM's native input event with
    # the correct inputType and bubbles through all Svelte reactive handlers,
    # reliably updating the draft store. The send button then appears within
    # Svelte's next microtask tick (~0ms, but we wait 600ms for safety).
    #
    # NOTE: this path is called in /?models=<slug> mode (new-chat state).
    # /c/<id> (existing empty chat) mode has a separate Svelte state bug fixed
    # by the navigation change in runner.py.
    ta = page.locator("textarea, [contenteditable='true']").first
    await ta.click()
    # Use page.keyboard.type() which fires CDP Input.dispatchKeyEvent for every
    # character — the most faithful simulation of real typing. ta.fill() uses
    # CDP Input.insertText which in some headless Svelte contexts does not trigger
    # the reactive input handler (draft store stays empty → send submits null
    # message). Keyboard events go through the full browser event pipeline and
    # reliably update OWUI's Svelte draft store.
    #
    # Multi-line prompts (code blocks, etc.) are the one exception: keyboard.type()
    # sends a literal Enter keypress for every '\n', and OWUI's composer submits on
    # bare Enter — so a multi-line prompt gets prematurely split and sent as several
    # fragmented messages mid-typing. keyboard.insert_text() inserts
    # the whole string as a single atomic input event — no Enter keypresses, no
    # code-fence auto-closing side effects from character-by-character typing — and
    # still updates the Svelte draft store.
    if "\n" in prompt:
        await page.keyboard.insert_text(prompt)
    else:
        await page.keyboard.type(prompt, delay=0)
    await page.wait_for_timeout(600)  # Svelte async DOM update
    send_btn = page.locator("#send-message-button")
    if await send_btn.count() > 0:
        try:
            await send_btn.click(timeout=10000)
        except Exception:
            # Button exists in the DOM but never became actionable (visible/
            # stable/enabled) within the timeout — an intermittent Svelte
            # rendering race observed across ~26% of tests in a single long
            # rerun, spanning unrelated personas/models (not prompt-length
            # dependent). Falls back to the same Enter-key path already used
            # when the button doesn't exist at all, rather than failing the
            # whole test on a flaky click.
            await ta.press("Enter")
    else:
        await ta.press("Enter")
    await _wait_for_completion(
        page,
        test_id,
        tier,
        max_wait_no_progress,
        token=token,
        chat_id=chat_id,
        min_messages=min_messages,
    )


async def _attach_file(page, file_path: Path) -> None:
    """Attach a file to the composer via OWUI's hidden upload input.

    OWUI renders two `input[type=file]` elements: a generic hidden upload
    input (`multiple`, no `accept` restriction) and `#camera-input` (images
    only, `capture=environment`). `set_input_files` bypasses the native file
    picker and fires the same change event the "+" attach button does,
    triggering OWUI's upload/RAG-processing pipeline without needing to
    locate or click the attach button itself.
    """
    file_input = page.locator('input[type="file"]:not(#camera-input)').first
    await file_input.set_input_files(str(file_path))
    await page.wait_for_timeout(3000)  # let OWUI finish upload + processing


async def _enable_tool(page, tool_id: str) -> None:
    tool_display_names = {
        "portal_code": "Portal Code",
        "portal_documents": "Portal Documents",
        "portal_memory": "Portal Memory",
        "portal_music_minimax": "Portal Music (MiniMax)",
        "portal_music_ace": "Portal Music (ACE-Step)",
        "portal_tts": "Portal TTS",
        "portal_video": "Portal Video",
        "portal_mflux": "Portal MFLUX (image)",
        "portal_security": "Portal Security",
        "portal_whisper": "Portal Whisper",
    }
    display = tool_display_names.get(tool_id, tool_id)

    try:
        btn = page.locator(
            'button[aria-label="Tools"], button[title="Tools"], '
            'button:has-text("+"), .chat-toolbar button'
        ).first
        await btn.click(timeout=5000)
        await page.wait_for_timeout(1000)

        toggle = page.locator(f'button:has-text("{display}"), label:has-text("{display}")')
        if await toggle.count() > 0:
            await toggle.first.click()

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
    except Exception:
        pass  # best-effort; test proceeds and assertion will catch if tool missing


async def _download_artifact(
    page, expected_ext: str, timeout_ms: int = 120_000, response_text: str = ""
) -> Path | None:
    ARTIFACT_DIR.mkdir(exist_ok=True)
    # Try Playwright UI download first
    try:
        async with page.expect_download(timeout=timeout_ms) as dl_info:
            await page.locator(
                f'a[download], a[href*=".{expected_ext}"], '
                f'button:has-text("Download"), .file-attachment'
            ).last.click(timeout=10000)
        dl = await dl_info.value
        dest = ARTIFACT_DIR / dl.suggested_filename
        await dl.save_as(dest)
        return dest
    except Exception:
        pass

    # Fallback: extract file path or download URL from model response
    import re
    import subprocess

    if response_text:
        # Try 1: Match a download URL ending in /files/<...>.<ext>.
        # Covers both the localhost shape and the public shape emitted when
        # PORTAL_PUBLIC_URL is set (e.g. https://portal.example.com/files/tts/<name>.wav,
        # potentially served via Cloudflare Tunnel). The driver runs on the
        # host, so it can resolve either form via DNS or loopback. Try 1
        # fetching matters because it exercises the same URL the user's
        # browser would use.
        url_pattern = rf"https?://[^\s)>\]]+/files/\S+?\.{re.escape(expected_ext)}"
        url_match = re.search(url_pattern, response_text)
        if url_match:
            download_url = url_match.group(0)
            filename = Path(download_url).name
            dest = ARTIFACT_DIR / filename
            try:
                r = httpx.get(download_url, timeout=30)
                if r.status_code == 200:
                    dest.write_bytes(r.content)
                    return dest
            except Exception:
                pass

        # Try 2: Match /app/data/generated/<filename>.<ext> container path
        container_pattern = rf"/app/data/generated/\S+\.{re.escape(expected_ext)}"
        container_match = re.search(container_pattern, response_text)
        if container_match:
            container_path = container_match.group(0)
            for container in [
                "portal5-mcp-documents",
                "portal5-mcp-sandbox",
            ]:
                dest = ARTIFACT_DIR / Path(container_path).name
                result = subprocess.run(
                    ["docker", "cp", f"{container}:{container_path}", str(dest)],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0 and dest.exists():
                    return dest

    # Try 3: Most recent file with expected extension from MCP containers
    # (handles case where tool ran but model didn't mention the filename)
    for container in [
        "portal5-mcp-documents",
        "portal5-mcp-sandbox",
    ]:
        try:
            result = subprocess.run(
                ["docker", "exec", container, "ls", "-t", "/app/data/generated/"],
                capture_output=True,
                timeout=10,
                text=True,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    fname = line.strip()
                    if fname.endswith(f".{expected_ext}"):
                        container_path = f"/app/data/generated/{fname}"
                        dest = ARTIFACT_DIR / fname
                        cp_result = subprocess.run(
                            ["docker", "cp", f"{container}:{container_path}", str(dest)],
                            capture_output=True,
                            timeout=10,
                        )
                        if cp_result.returncode == 0 and dest.exists():
                            return dest
                        break
        except Exception:
            continue

    # The MLX generation MCPs (mflux :8933, video-mlx :8935) publish outputs
    # through Open WebUI's files API, so the /files/ and /app/data/generated/
    # paths above cover them — no engine-specific fallback needed.

    return None
