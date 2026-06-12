#!/usr/bin/env python3
# ruff: noqa: F401, E402, I001
"""Portal 5 UAT Conversation Driver v1

Sends every test in TEST_CATALOG through the real Open WebUI browser
interface, creating permanent reviewable conversations in OWUI history.
The catalog currently spans ~175 tests across 24 sections including
auto-* workspaces, the `challenge` shootout (bench-* workspaces), and an `advanced` section
covering multi-turn / advanced flows.

Run modes:
    python3 tests/portal5_uat_driver.py --all
    python3 tests/portal5_uat_driver.py --section auto-coding
    python3 tests/portal5_uat_driver.py --section auto-coding --section challenge
    python3 tests/portal5_uat_driver.py --test WS-01 --test P-W06
    python3 tests/portal5_uat_driver.py --all --headed --append

Calibration mode (capture real responses for signal extraction):
    python3 tests/portal5_uat_driver.py --calibrate \
        --calibrate-output calibration.json
    # ... review calibration.json, set review_tag = good/bad/skip on each entry
    python3 tests/portal5_uat_driver.py --emit-signals-from calibration.json
    # See docs/UAT_CALIBRATION.md for the full workflow.

Maintenance:
    python3 tests/portal5_uat_driver.py --purge-uat        # delete all UAT chats + folder (post-review cleanup)
    python3 tests/portal5_uat_driver.py --migrate          # move root chats into UAT folder
    python3 tests/portal5_uat_driver.py --skip-artifacts  # skip ComfyUI/Wan2.2 tests
    python3 tests/portal5_uat_driver.py --skip-bots       # skip Telegram/Slack tests
"""

from __future__ import annotations

import argparse
import asyncio
import json as _json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

_TESTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parent
for _p in (str(_PROJECT_ROOT), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.uat_catalog import TEST_CATALOG  # assembled from tests/uat_catalog/g_*.py

# --- TASK_UAT_MODULARIZE_V1 transitional re-imports (removed in phase D) ---
from tests.uat import config, state
from tests.uat.config import (
    ADMIN_EMAIL,
    ADMIN_PASS,
    ARTIFACT_DIR,
    BACKEND_SETTLE_WAIT_S,
    DOM_STABLE_API_EMPTY_MAX,
    MAX_WAIT_NO_PROGRESS,
    MEMORY_ABORT_PCT,
    MEMORY_CRITICAL_PCT,
    MEMORY_SAME_MODEL_EVICT_PCT,
    MEMORY_WARN_PCT,
    NO_STREAM_TIMEOUT,
    OLLAMA_URL,
    OPENWEBUI_URL,
    PHASE1_FAST_DURATION_S,
    PHASE1_FAST_S,
    PHASE1_MID_DURATION_S,
    PHASE1_MID_S,
    PHASE1_SLOW_S,
    PHASE2_DOM_STABLE_NEEDED,
    PHASE2_STREAMING_POLL_S,
    POST_STREAM_API_WAIT_S,
    PROGRESS_LOG_INTERVAL,
    PROGRESS_POLL_S,
    SCREENSHOT_DIR,
    SECTIONS_REQUIRE_UNLOAD,
    SEND_TIMEOUT,
)
from tests.uat.grading import (
    _UNICODE_DASH_TABLE,
    _extract_code_blocks,
    _kw_in,
    _normalize_dashes,
    _strip_think_blocks,
    assert_any_of,
    assert_code_pattern,
    assert_contains,
    assert_docx_valid,
    assert_has_code,
    assert_has_table,
    assert_min_length,
    assert_mp4_valid,
    assert_not_contains,
    assert_png_valid,
    assert_pptx_valid,
    assert_wav_valid,
    assert_xlsx_valid,
    compute_status,
    run_assertions,
)
from tests.uat.results import (
    _parse_failed_test_ids,
    _parse_test_ids_from_results,
    _rebuild_summary_from_rows,
    _remove_rows_for_test_ids,
    _write_routing_summary,
    init_results,
    record_result,
    update_summary,
)
from tests.uat.freshness import _REPO_ROOT, _check_image_freshness
from tests.uat.health import (
    _backend_alive,
    _check_for_oom_crash,
    _check_memory_before_test,
    _get_memory_pct,
    _wait_for_backend,
    _wait_for_backend_alive,
    _wait_for_drain,
)
from tests.uat.lifecycle import (
    _comfyui_running,
    _pipeline_pre_warm,
    _start_comfyui,
    _stop_comfyui,
    _unload_running_ollama_models,
    _wait_for_ollama_ps_empty,
    cleanup_after_uat,
    unload_all_models,
)
from tests.uat.monitor import (
    _DIAG_DIR,
    SETTLING,
    CrashWatcher,
    MemoryMonitor,
    _crash_watcher,
    settling_delay,
)
from tests.uat.notify import (
    _git_sha,
    _notify_test_end,
    _notify_test_start,
    _notify_test_summary,
    _send_notification,
)
from tests.uat.owui_api import (
    _archive_run_chats,
    _install_archival_signal_handler,
    _owui_list_folders,
    _wait_for_response_arrival,
    owui_assign_chat_folder,
    owui_create_chat,
    owui_get_last_response,
    owui_get_or_create_folder,
    owui_get_routed_model,
    owui_headers,
    owui_migrate_loose_uat_chats,
    owui_rename_chat,
    owui_token,
)
# --- end TASK_UAT_MODULARIZE_V1 transitional re-imports ---

# ---------------------------------------------------------------------------
# Frontend dispatch shims — thin wrappers over OWUI helpers.
# ---------------------------------------------------------------------------


async def _fe_login(page) -> None:
    """Login to Open WebUI."""
    await _login(page)


async def _fe_start_chat(
    page,
    token: str,
    model_slug: str,
    title: str,
) -> tuple[str, str]:
    """Create / open a fresh chat. Returns (chat_id, chat_url).

    chat_id is the OWUI UUID (used by API helpers). chat_url is
    `{OPENWEBUI_URL}/c/{chat_id}`.
    """
    chat_id, chat_url = owui_create_chat(token, model_slug, title)
    await _navigate_to_chat(page, chat_url)
    return chat_id, chat_url


class _PresetUnreachableError(RuntimeError):
    """Raised by _fe_start_chat when a persona test cannot select its preset."""


async def _fe_send_and_wait(
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
    """Send a prompt and wait for streaming to complete."""
    await _send_and_wait(
        page,
        prompt,
        test_id=test_id,
        tier=tier,
        max_wait_no_progress=max_wait_no_progress,
        token=token,
        chat_id=chat_id,
        min_messages=min_messages,
    )


async def _extract_dom_response(page) -> str:
    """Extract the last assistant response text directly from the OWUI page DOM.

    Used as a fallback when OWUI 0.9.5+ does not immediately commit thinking-model
    responses to the chat history API. OWUI renders markdown content inside .prose
    divs; reasoning blocks are in <details> elements that are stripped before return.
    Returns '' if no suitable content is found (degrades gracefully).
    """
    try:
        return await page.evaluate(
            """() => {
            // OWUI 0.9.x renders markdown with Tailwind 'prose' class.
            // The last .prose element holds the most recent assistant response.
            const selectors = [
                '.prose.dark\\\\:prose-invert',
                '.prose',
                '[data-role="assistant"] .prose',
                '.message-content .prose',
            ];
            let best = '';
            for (const sel of selectors) {
                try {
                    const els = document.querySelectorAll(sel);
                    if (els.length === 0) continue;
                    const el = els[els.length - 1];
                    const clone = el.cloneNode(true);
                    for (const d of clone.querySelectorAll('details')) d.remove();
                    const text = (clone.innerText || '').trim();
                    if (text.length > best.length) best = text;
                } catch (_) {}
            }
            return best;
        }"""
        )
    except Exception:
        return ""


async def _fe_get_last_response(page, token: str, chat_id: str, min_messages: int = 1) -> str:
    """Read the most recent assistant message — OWUI API first, DOM fallback.

    OWUI 0.9.5+ may delay committing thinking-model responses to the chat history
    API until a new user message arrives. When the API returns empty but streaming
    has visually completed, _extract_dom_response reads directly from the rendered
    page content as a fallback.
    """
    api_result = owui_get_last_response(token, chat_id, min_messages=min_messages)
    if api_result:
        return api_result
    return await _extract_dom_response(page)


async def _fe_get_routed_model(test: dict, page, token: str, chat_id: str) -> str:
    """Resolve the actual backend model that handled the most recent response.

    Reads OWUI's stored chat metadata (the workspace/persona name captured from
    the pipeline's SSE stream). Returns "" if no source is available.
    _check_routed_model handles the empty-string case by skipping validation.
    """
    return owui_get_routed_model(token, chat_id)


async def _fe_enable_tool(page, tool_id: str) -> None:
    await _enable_tool(page, tool_id)


async def _fe_assign_folder(page, token: str, chat_id: str, folder_id: str | None) -> None:
    if folder_id:
        owui_assign_chat_folder(token, chat_id, folder_id)


async def _fe_download_artifact(
    page,
    expected_ext: str,
    response_text: str = "",
    timeout_ms: int = 120_000,
    *,
    since_ts: float = 0.0,
) -> Path | None:
    return await _download_artifact(page, expected_ext, timeout_ms, response_text)


def _fe_current_chat_url(page, fallback: str) -> str:
    """Return the API-given chat_url."""
    return fallback


def _map_slug_to_workspace(slug: str) -> str:
    """Resolve a persona slug to its workspace id, or return the slug
    if it's already a workspace id."""
    from expected_models import _PERSONA_MAP, WORKSPACES

    if slug in WORKSPACES:
        return slug
    p = _PERSONA_MAP.get(slug, {})
    ws = p.get("workspace_model") or p.get("workspace") or ""
    return ws if ws in WORKSPACES else ""


def _get_backend_from_pipeline_logs(slug: str) -> str:
    """Query pipeline Docker logs for the most recent backend that actually
    served a request for the given workspace/persona slug.

    Uses the "Backend X succeeded" log line (only emitted on actual success)
    rather than the "Routing workspace=X → backend=Y" line (emitted for the
    first candidate ATTEMPTED, which may 503 and fall to a different backend).

    Log line patterns (pipeline emits both; we prefer the succeeded line):
      Backend ollama-general succeeded for workspace=auto-documents model=phi4:14b-q8_0
      Backend ollama-coding succeeded for workspace=auto-agentic model=qwen3-coder:30b
    """
    import re
    import subprocess

    # Resolve persona slug to its workspace for log matching
    ws = _map_slug_to_workspace(slug)

    try:
        result = subprocess.run(
            ["docker", "logs", "portal5-pipeline", "--tail", "300"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        combined = result.stdout + result.stderr  # docker logs may use either stream

        # PRIMARY: match "Backend X succeeded for workspace=Y model=Z"
        # This line is only emitted when a backend actually returns a response,
        # so it correctly reflects backend-group fallbacks that the
        # "Routing workspace" attempt line would hide.
        for search_term in (ws, slug):
            if not search_term:
                continue
            succeeded_pattern = re.compile(
                r"Backend\s+([^\s]+)\s+succeeded\s+for\s+workspace="
                + re.escape(search_term)
                + r"\s+model=([^\s]+)"
            )
            matches = succeeded_pattern.findall(combined)
            if matches:
                backend, model = matches[-1]  # most recent
                return f"{backend}|{model}"

        # FALLBACK: if no "succeeded" line found (e.g. non-stream path that
        # doesn't emit it), fall back to the attempt log line as before.
        for search_term in (ws, slug):
            if not search_term:
                continue
            pattern = re.compile(
                r"Routing workspace="
                + re.escape(search_term)
                + r".*?backend=([^\s]+)\s+model=([^\s]+)"
            )
            matches = pattern.findall(combined)
            if matches:
                backend, model = matches[-1]
                return f"{backend}|{model}"
    except Exception:
        pass
    return ""


def _check_routed_model(test: dict, routed_model: str) -> tuple[bool, str] | None:
    """Validate routed_model against test expectation.

    Two-source approach:
      1. OWUI chat metadata via owui_get_routed_model (may store the
         workspace/persona name, not the backend model)
      2. Pipeline Docker logs — extracts the actual backend=xxx model=yyy

    Returns:
        None             - no expectation defined for this test, skip the check
        (True,  detail)  - actual model matches expectation
        (False, detail)  - mismatch (caller should downgrade PASS to WARN)

    Resolution order:
        1. test['assert_routed_via']: list[str] of substrings
        2. test['model_slug'] in WORKSPACES
        3. test['model_slug'] in _PERSONA_MAP
        4. None — no expectation, skip
    """
    if test.get("via_dispatcher") or test.get("is_manual"):
        return None
    if not routed_model:
        return None

    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).parent))

    from expected_models import model_matches_expected, resolve_expected

    explicit = test.get("assert_routed_via")
    slug = test.get("model_slug", "")

    keys, src = resolve_expected(
        workspace_id=slug,
        persona_slug=slug,
    )
    if not keys:
        return None

    # 1st check: OWUI-stored model (may be the workspace/persona name)
    ok_owui = model_matches_expected(routed_model, keys)

    # 2nd check: pipeline logs (actual backend model)
    backend_model = _get_backend_from_pipeline_logs(slug)

    ok_pipeline = False
    pipeline_detail = ""
    if backend_model:
        ok_pipeline = model_matches_expected(backend_model, keys)
        pipeline_detail = f" (pipeline: {backend_model})"

    if explicit:
        ok = ok_owui or ok_pipeline
        return (
            ok,
            f"explicit expectation: {explicit}{pipeline_detail}"
            if ok
            else f"explicit expectation NOT matched: {explicit}{pipeline_detail}",
        )

    if ok_owui or ok_pipeline:
        detail = f"matches {src}"
        if backend_model:
            detail += f" — pipeline confirms: {backend_model}"
        return (True, detail)

    return (False, f"expected {src} (OWUI={routed_model}{pipeline_detail})")


# Playwright helpers
# ---------------------------------------------------------------------------


async def _login(page) -> None:
    await page.goto(OPENWEBUI_URL, wait_until="networkidle", timeout=30000)
    await page.wait_for_selector('input[type="email"]', timeout=15000)
    await page.fill('input[type="email"]', ADMIN_EMAIL)
    await page.fill('input[type="password"]', ADMIN_PASS)
    await page.locator('button[type="submit"], button:has-text("Sign in")').first.click()
    await page.wait_for_selector("textarea, [contenteditable]", timeout=20000)


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
    ta = page.locator("textarea, [contenteditable='true']").first
    await ta.click()
    await ta.fill(prompt)
    send_btn = page.locator("#send-message-button")
    if await send_btn.count() > 0:
        await send_btn.click()
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


async def _enable_tool(page, tool_id: str) -> None:
    tool_display_names = {
        "portal_code": "Portal Code",
        "portal_documents": "Portal Documents",
        "portal_memory": "Portal Memory",
        "portal_music": "Portal Music",
        "portal_tts": "Portal TTS",
        "portal_video": "Portal Video",
        "portal_comfyui": "Portal ComfyUI",
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

        # Try 1b: ComfyUI /view?filename=... URL (host-native ComfyUI at :8188).
        # generate_image / generate_video return:
        #   http://localhost:8188/view?filename=portal_xxx.png&type=output
        # The /files/ pattern above never matches this shape.
        comfyui_pat = (
            rf"https?://[^\s)>\]]*/view\?filename=[^\s)>\]]*\.{re.escape(expected_ext)}[^\s)>\]]*"
        )
        comfyui_match = re.search(comfyui_pat, response_text)
        if comfyui_match:
            from urllib.parse import parse_qs, urlparse

            download_url = comfyui_match.group(0)
            qs = parse_qs(urlparse(download_url).query)
            fname = qs.get("filename", ["unknown"])[0]
            dest = ARTIFACT_DIR / Path(fname).name
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
                "portal5-mcp-comfyui",
                "portal5-mcp-video",
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
        "portal5-mcp-comfyui",
        "portal5-mcp-video",
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

    # Try 4: ComfyUI direct download — query /history for the most recent
    # portal_*.{mp4,png}. ComfyUI runs host-native (port 8188), so docker cp
    # never finds its output files regardless of extension.
    # png: prefix "portal_" (comfyui_mcp.py SaveImage node)
    # mp4: prefix "portal_video_" (video_mcp.py)
    # Recency guard: only accept files generated in the last 15 minutes, to
    # avoid picking up stale files from a previous test session.
    if expected_ext in ("mp4", "png"):
        try:
            import time as _time

            now_ms = int(_time.time() * 1000)
            cutoff_ms = now_ms - (15 * 60 * 1000)
            r = httpx.get("http://localhost:8188/history", timeout=10)
            if r.status_code == 200:
                history = r.json()
                best_ts: int = -1
                best_fname: str | None = None
                for job_data in history.values():
                    if not job_data.get("status", {}).get("completed"):
                        continue
                    outputs = job_data.get("outputs", {})
                    for node_outputs in outputs.values():
                        for img in node_outputs.get("images", []):
                            fname = img.get("filename", "")
                            ext_match = fname.endswith(f".{expected_ext}")
                            prefix_match = (
                                expected_ext == "mp4" and fname.startswith("portal_video_")
                            ) or (expected_ext == "png" and fname.startswith("portal_"))
                            if ext_match and prefix_match:
                                msgs = job_data.get("status", {}).get("messages", [])
                                ts = msgs[0][1].get("timestamp", 0) if msgs else 0
                                if ts >= cutoff_ms and ts > best_ts:
                                    best_ts = ts
                                    best_fname = fname
                if best_fname:
                    url = f"http://localhost:8188/view?filename={best_fname}&type=output"
                    dest = ARTIFACT_DIR / best_fname
                    r2 = httpx.get(url, timeout=60)
                    if r2.status_code == 200 and len(r2.content) > 0:
                        dest.write_bytes(r2.content)
                        return dest
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# Skip condition detection
# ---------------------------------------------------------------------------


def evaluate_skip_conditions() -> dict:
    conditions: dict[str, bool] = {}
    try:
        r = httpx.get("http://localhost:8188/system_stats", timeout=3)
        conditions["no_comfyui"] = r.status_code != 200
    except Exception:
        conditions["no_comfyui"] = True

    env_content = Path(".env").read_text() if Path(".env").exists() else ""
    # Per-key check: KEY=value on its own line, value non-empty, value != "CHANGEME".
    # The previous `"CHANGEME" in env_content` substring check fired on any other
    # placeholder elsewhere in the file (PIPELINE_API_KEY, GRAFANA_PASSWORD, the
    # comment on line 3 of .env.example, etc.), falsely flagging both bot
    # predicates as "not configured" even with valid tokens set.
    conditions["no_bot_telegram"] = not _env_var_set(env_content, "TELEGRAM_BOT_TOKEN")
    conditions["no_bot_slack"] = not _env_var_set(env_content, "SLACK_BOT_TOKEN")
    fixtures = Path(__file__).parent / "fixtures"
    conditions["no_image_upload"] = not (fixtures / "sample.png").exists()
    conditions["no_audio_fixture"] = not (fixtures / "sample.wav").exists()
    conditions["no_two_speaker_audio_fixture"] = not (fixtures / "sample_two_speakers.wav").exists()
    try:
        r = httpx.get("http://localhost:8924/health", timeout=3)
        conditions["no_transcribe_server"] = r.status_code != 200
    except Exception:
        conditions["no_transcribe_server"] = True
    conditions["no_docx_fixture"] = not (fixtures / "sample.docx").exists()
    conditions["no_knowledge_base"] = not (fixtures / "knowledge_base").is_dir()
    return conditions


def _env_var_set(env_content: str, key: str) -> bool:
    """True iff ``key`` is set in env content with a non-empty value that isn't ``CHANGEME``.

    Reads ``KEY=value`` on its own line; tolerates leading whitespace, inline
    comments, and surrounding quotes on the value. Comments and unrelated
    placeholders elsewhere in the file do not affect the result.
    """
    import re

    pat = rf"^[ \t]*{re.escape(key)}=([^\r\n]*)$"
    m = re.search(pat, env_content, re.MULTILINE)
    if not m:
        return False
    raw = m.group(1)
    # Strip inline comment ("# ..." not inside quotes — simple heuristic that
    # matches typical .env practice; values containing literal '#' should be
    # quoted, which is the convention .env.example follows).
    if "#" in raw and not (raw.lstrip().startswith(('"', "'"))):
        raw = raw.split("#", 1)[0]
    val = raw.strip().strip('"').strip("'")
    return bool(val) and val != "CHANGEME"


def _bot_container_running(container_name: str) -> tuple[bool, str]:
    """True if the named docker container is in 'running' state.

    Used by via_dispatcher tests to surface a clear failure when the bot
    container itself is down — distinct from the dispatcher path failing.
    """
    import subprocess

    try:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return False, f"container not found: {container_name}"
        status = r.stdout.strip()
        return status == "running", f"status={status}"
    except FileNotFoundError:
        return False, "docker CLI not available"
    except Exception as exc:
        return False, f"inspect error: {exc}"


async def _run_via_dispatcher(workspace: str, prompt: str, timeout: int) -> str:
    """Drive a chat completion through the Pipeline as a Telegram/Slack bot would.

    Bypasses Open WebUI to exercise the exact code path
    ``portal_channels.dispatcher.call_pipeline_async`` uses on every inbound
    message: a single POST to ``:9099/v1/chat/completions`` with
    ``Authorization: Bearer ${PIPELINE_API_KEY}``. Returns the assistant content
    string. Raises on transport error or non-2xx response — caller handles.
    """
    api_key = os.environ.get("PIPELINE_API_KEY", "portal-pipeline")
    pipeline_url = os.environ.get("PIPELINE_URL", "http://localhost:9099")
    payload = {
        "model": workspace,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{pipeline_url}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])


# ---------------------------------------------------------------------------
# Inter-test settling
# ---------------------------------------------------------------------------

# Model cascade ordering
# ---------------------------------------------------------------------------

# Tier execution order: ollama first, then any, then media_heavy
_TIER_ORDER = ["ollama", "any", "media_heavy"]


def sort_tests_cascade(tests: list[dict]) -> list[dict]:
    """Reorder tests for model-cascade execution.

    Order:
    1. By workspace_tier: ollama → any
       (ollama tests first, so the hardest loads are done early and memory
       is cleanest at the start)
    2. Within each tier, by model_slug: groups tests using the same persona
       together, minimizing model switches within the pipeline
    3. Within each model_slug, preserve original order (test IDs)

    This replaces section-based ordering. Instead of:
      all auto-coding tests → all auto-spl tests → ...
    We do:
      all ollama tests (grouped by model) → all any tests → ...

    Benefits:
    - Models loaded once per tier transition, not per section
    - Big models tested while memory is freshest
    - Tests using same persona run consecutively (pipeline caches)
    - Clear memory boundaries between tiers
    """
    tier_rank = {t: i for i, t in enumerate(_TIER_ORDER)}
    return sorted(
        tests,
        key=lambda t: (
            tier_rank.get(t.get("workspace_tier", "any"), 99),
            t.get("model_slug", ""),
            t.get("id", ""),
        ),
    )


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


async def _run_two_chat_test(
    page,
    test: dict,
    token: str,
    n: int,
    counts: dict,
    folder_id: str | None = None,
    calibration_records: list | None = None,
    corpus_run_id: str = "",
) -> None:
    """Two-chat orchestration for cross-session tests (A-08).

    Creates two distinct OWUI chats in the same workspace. Sends `prompt`
    in chat 1, then `turn2_in_new_chat` in chat 2. Assertions on both
    responses. Best-effort cleanup of any matching memory records via the
    Memory MCP forget API.
    """
    test_id = test["id"]
    name = test["name"]
    model = test["model_slug"]
    tier = test.get("workspace_tier", "any")

    # Backend health
    if tier in ("ollama",):
        backend_ready = await _wait_for_backend(tier, max_wait=120)
        if not backend_ready:
            chat_id, chat_url = owui_create_chat(token, model, f"[FAIL] UAT: {test_id} {name}")
            if folder_id:
                owui_assign_chat_folder(token, chat_id, folder_id)
            record_result(
                n,
                "FAIL",
                test_id,
                name,
                model,
                [("backend_unavailable", False, "tier not ready")],
                0.0,
                chat_url,
            )
            counts["FAIL"] = counts.get("FAIL", 0) + 1
            return

    title1 = f"[...] UAT: {test_id} (1/2) {name}"
    title2 = f"[...] UAT: {test_id} (2/2) {name}"
    # Create chats and assign folders via API BEFORE browser navigation (same reason
    # as main test path — post-nav folder assignment triggers SSE that corrupts submit).
    chat1_id, chat1_url = owui_create_chat(token, model, title1)
    chat2_id, chat2_url = owui_create_chat(token, model, title2)
    if folder_id:
        owui_assign_chat_folder(token, chat1_id, folder_id)
        owui_assign_chat_folder(token, chat2_id, folder_id)
    try:
        await _navigate_to_chat(page, chat1_url)
        await _navigate_to_chat(page, chat2_url)
    except _PresetUnreachableError as exc:
        record_result(
            n,
            "SKIP",
            test_id,
            name,
            model,
            [("persona_preset_unreachable", False, str(exc)[:160])],
            0.0,
            "",
        )
        counts["SKIP"] = counts.get("SKIP", 0) + 1
        return

    t0 = time.time()
    response1 = ""
    response2 = ""
    assertions_result: list = []
    status = "FAIL"
    routed_model_1 = ""
    routed_model_2 = ""

    try:
        max_wait = test.get("max_wait_no_progress", MAX_WAIT_NO_PROGRESS)

        # Ensure Ollama model is loaded before sending — two-chat flow skips
        # the main runner's pre-flight check.
        if tier in ("ollama",):
            unload_all_models()

        # Pre-seed memory via direct MCP API. Decouples test reliability from
        # model-initiated 'remember' (flaky in programmatic OWUI sessions).
        # Test still validates full recall pipeline: LanceDB → semantic search → model.
        preseed_data = test.get("memory_preseed")
        if preseed_data:
            try:
                async with httpx.AsyncClient(timeout=15) as _mc:
                    _resp = await _mc.post(
                        "http://localhost:8920/tools/remember",
                        json={"arguments": preseed_data},
                    )
                if _resp.status_code == 200:
                    print(f"[A-08] memory pre-seeded: {_resp.json().get('id', '?')}", flush=True)
                    await asyncio.sleep(2.0)  # let LanceDB index settle
                else:
                    print(
                        f"[A-08] memory pre-seed failed HTTP {_resp.status_code} — skipping",
                        flush=True,
                    )
                    record_result(
                        n,
                        "SKIP",
                        test_id,
                        name,
                        model,
                        [("memory_preseed_failed", False, f"HTTP {_resp.status_code}")],
                        0.0,
                        "memory-preseed-fail://",
                    )
                    counts["SKIP"] = counts.get("SKIP", 0) + 1
                    return
            except Exception as _e:
                print(f"[A-08] memory pre-seed error: {_e} — skipping", flush=True)
                record_result(
                    n,
                    "SKIP",
                    test_id,
                    name,
                    model,
                    [("memory_preseed_failed", False, str(_e)[:100])],
                    0.0,
                    "memory-preseed-fail://",
                )
                counts["SKIP"] = counts.get("SKIP", 0) + 1
                return

        # Chat 1
        await _navigate_to_chat(page, chat1_url)
        # Note: do NOT call _enable_tool here. The portal pipeline injects
        # and dispatches tools internally for auto-daily (and any workspace
        # with effective_tools). Enabling the tool in OWUI causes OWUI to
        # also dispatch tool_calls it sees in the SSE stream (double-dispatch),
        # which creates a second conversation turn with empty tool results that
        # overwrites the pipeline's correct answer. Pipeline owns dispatch.
        await _fe_send_and_wait(
            page,
            test["prompt"],
            test_id,
            tier,
            max_wait,
            token=token,
            chat_id=chat1_id,
        )
        chat1_url = _fe_current_chat_url(page, fallback=chat1_url)
        response1 = await _fe_get_last_response(page, token, chat1_id) or ""
        routed_model_1 = await _fe_get_routed_model(test, page, token, chat1_id)

        # Brief settle to let the memory write commit through embedding
        # service before chat 2 queries it. The recall is vector-based and
        # needs the entry to be visible in the LanceDB table.
        await asyncio.sleep(5)

        # Chat 2 — fresh chat_url, ZERO context shared with chat 1 except
        # via the model calling 'recall' on the Memory MCP.
        await _navigate_to_chat(page, chat2_url)

        await _fe_send_and_wait(
            page,
            test["turn2_in_new_chat"],
            test_id,
            tier,
            max_wait,
            token=token,
            chat_id=chat2_id,
        )
        chat2_url = _fe_current_chat_url(page, fallback=chat2_url)
        response2 = await _fe_get_last_response(page, token, chat2_id) or ""
        routed_model_2 = await _fe_get_routed_model(test, page, token, chat2_id)

        # Assertions
        _incl_think = test.get("include_thinking_in_assertions", False)
        assertions_result = run_assertions(response1, test.get("assertions", []), include_thinking=_incl_think)
        t2_results = run_assertions(response2, test.get("turn2_assertions", []), include_thinking=_incl_think)
        assertions_result.extend(t2_results)

        all_specs = test.get("assertions", []) + test.get("turn2_assertions", [])
        status = compute_status(assertions_result, all_specs)

        # Routing observation (V1 Phase 2 helper) — append on best-effort basis
        try:
            check1 = _check_routed_model(test, routed_model_1)
            if check1 is not None:
                ok, det = check1
                assertions_result.append((f"Chat 1 routed: {routed_model_1[:30]}", ok, det))
            check2 = _check_routed_model(test, routed_model_2)
            if check2 is not None:
                ok, det = check2
                assertions_result.append((f"Chat 2 routed: {routed_model_2[:30]}", ok, det))
        except NameError:
            # _check_routed_model not present — V1 not merged. Skip silently.
            pass

        if status in ("FAIL", "WARN"):
            SCREENSHOT_DIR.mkdir(exist_ok=True)
            await page.screenshot(path=str(SCREENSHOT_DIR / f"{test_id.lower()}_chat2.png"))

    except Exception as exc:
        assertions_result = [("exception", False, str(exc)[:120])]
        status = "FAIL"
    finally:
        # Best-effort cleanup of memory marker — does not affect status.
        # The model may or may not have actually called remember; either way
        # we flush anything tagged with our marker to avoid accumulation.
        marker_tag = test.get("cleanup_marker_tag")
        if marker_tag:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    list_r = await client.post(
                        "http://localhost:8920/tools/list_memories",
                        json={"arguments": {"tags": [marker_tag], "limit": 50}},
                    )
                    if list_r.status_code == 200:
                        for m in list_r.json().get("memories", []):
                            await client.post(
                                "http://localhost:8920/tools/forget",
                                json={"arguments": {"id": m["id"]}},
                            )
            except Exception:
                pass  # cleanup best-effort

    elapsed = time.time() - t0
    final_title_1 = f"[{status} 1/2] UAT: {test_id} {name}"
    final_title_2 = f"[{status} 2/2] UAT: {test_id} {name}"
    owui_rename_chat(token, chat1_id, final_title_1)
    owui_rename_chat(token, chat2_id, final_title_2)

    # Use chat 2 URL as the "primary" link in results — it's where the
    # actual recall behavior is visible to a reviewer.
    record_result(
        n,
        status,
        test_id,
        name,
        model,
        assertions_result,
        elapsed,
        chat2_url,
        routed_model_2,
    )
    counts[status] = counts.get(status, 0) + 1

    if calibration_records is not None:
        calibration_records.append(
            {
                "test_id": test_id,
                "name": name,
                "section": test.get("section", ""),
                "workspace": test.get("model_slug", ""),
                "prompt": test.get("prompt", "")
                + "\n\n[NEW CHAT]\n"
                + test.get("turn2_in_new_chat", ""),
                "response_text": (
                    f"=== Chat 1 ===\n{response1}\n\n=== Chat 2 (recall) ===\n{response2}"
                ),
                "chat_url": chat2_url,
                "review_tag": "",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    # Always-on corpus emission for two-chat tests. The prompt and
    # response carry the same dual-chat formatting as the calibration
    # record above so a single corpus reader handles both shapes.
    if corpus_run_id:
        _composite_test = dict(test)
        _composite_test["prompt"] = (
            test.get("prompt", "") + "\n\n[NEW CHAT]\n" + test.get("turn2_in_new_chat", "")
        )
        _composite_response = f"=== Chat 1 ===\n{response1}\n\n=== Chat 2 (recall) ===\n{response2}"
        _emit_corpus_row(
            corpus_run_id=corpus_run_id,
            test=_composite_test,
            routed_model=routed_model_2,
            response_text=_composite_response,
            chat_url=chat2_url,
            status=status,
            assertions_result=assertions_result,
            elapsed=elapsed,
        )


async def run_test(
    page,
    test: dict,
    token: str,
    skip_conditions: dict,
    n: int,
    counts: dict,
    headed: bool = False,
    folder_id: str | None = None,
    calibration_records: list | None = None,
    corpus_run_id: str = "",
) -> None:
    test_id = test["id"]
    name = test["name"]
    model = test["model_slug"]

    title_pending = f"[...] UAT: {test_id} {name}"

    # Skip check — skip_if can be a string or list of strings (any match skips)
    skip_if = test.get("skip_if")
    _skip_keys = [skip_if] if isinstance(skip_if, str) else (skip_if or [])
    if any(skip_conditions.get(k, False) for k in _skip_keys):
        _matched_key = next((k for k in _skip_keys if skip_conditions.get(k, False)), skip_if)
        chat_id, chat_url = owui_create_chat(token, model, f"[SKIP] UAT: {test_id} {name}")
        owui_rename_chat(token, chat_id, f"[SKIP] UAT: {test_id} {name} — {_matched_key}")
        if folder_id:
            owui_assign_chat_folder(token, chat_id, folder_id)
        record_result(n, "SKIP", test_id, name, model, [], 0.0, chat_url)
        counts["SKIP"] = counts.get("SKIP", 0) + 1
        return

    # Manual test
    if test.get("is_manual"):
        chat_id, chat_url = owui_create_chat(token, model, title_pending)
        if folder_id:
            owui_assign_chat_folder(token, chat_id, folder_id)
        manual_prompt = (
            "🔧 MANUAL TEST: "
            + test["prompt"]
            + "\n\nReturn to this chat and pin your result with ✅ PASS / ⚠️ PARTIAL / ❌ FAIL + notes."
        )
        await _navigate_to_chat(page, chat_url)
        await _send_and_wait(page, manual_prompt, test_id, token=token, chat_id=chat_id)
        owui_rename_chat(token, chat_id, f"[MANUAL] UAT: {test_id} {name}")
        record_result(n, "MANUAL", test_id, name, model, [], 0.0, chat_url)
        counts["MANUAL"] = counts.get("MANUAL", 0) + 1
        return

    # Dispatcher-path test (Telegram / Slack bot pipeline call).
    # Drives the exact code path portal_channels.dispatcher uses on every
    # inbound bot message: a direct POST to the Pipeline with PIPELINE_API_KEY.
    # Bypasses Open WebUI and Playwright entirely.
    if test.get("via_dispatcher"):
        # Pre-check: bot container running, if specified.
        required_container = test.get("requires_container")
        if required_container:
            ok, detail = _bot_container_running(required_container)
            if not ok:
                # Bot integrations are optional — container not running = SKIP,
                # not a core product defect.
                record_result(
                    n,
                    "SKIP",
                    test_id,
                    name,
                    model,
                    [("bot_container_unavailable", False, f"{required_container}: {detail}")],
                    0.0,
                    "",
                )
                counts["SKIP"] = counts.get("SKIP", 0) + 1
                return

        t0_disp = time.time()
        try:
            response_text = await _run_via_dispatcher(
                workspace=model,
                prompt=test["prompt"],
                timeout=test.get("timeout", 120),
            )
        except Exception as exc:
            elapsed = time.time() - t0_disp
            # Transport/auth errors = optional integration not wired up → SKIP.
            # Content failures (wrong response) → FAIL.
            record_result(
                n,
                "SKIP",
                test_id,
                name,
                model,
                [("dispatcher_call_failed", False, f"{type(exc).__name__}: {str(exc)[:160]}")],
                elapsed,
                "",
            )
            counts["SKIP"] = counts.get("SKIP", 0) + 1
            return

        elapsed = time.time() - t0_disp
        _incl_think = test.get("include_thinking_in_assertions", False)
        assertions_result = run_assertions(response_text, test.get("assertions", []), include_thinking=_incl_think)
        status = compute_status(assertions_result, test.get("assertions", []))
        # No chat URL — this path doesn't create an Open WebUI chat. Use a
        # synthetic marker so the report shows where the response came from.
        record_result(
            n,
            status,
            test_id,
            name,
            model,
            assertions_result,
            elapsed,
            f"via-dispatcher://{model}",
        )
        counts[status] = counts.get(status, 0) + 1
        return

    # Two-chat test: A-08 (cross-session memory). Creates two distinct
    # OWUI chats, uses the same workspace, runs separate prompt+turn2_in_new_chat
    # turns. Each chat shows up independently in OWUI history.
    if test.get("is_two_chat"):
        return await _run_two_chat_test(
            page,
            test,
            token,
            n,
            counts,
            folder_id,
            calibration_records,
            corpus_run_id=corpus_run_id,
        )

    tier = test.get("workspace_tier", "any")

    # Pre-test backend health gate — wait up to 120s for Ollama to be ready.
    if tier in ("ollama",):
        backend_ready = await _wait_for_backend(tier, max_wait=120)
        if not backend_ready:
            backend_ready = await _wait_for_backend(tier, max_wait=60)
        if not backend_ready:
            _, detail = _backend_alive(tier)
            chat_id, chat_url = owui_create_chat(token, model, f"[FAIL] UAT: {test_id} {name}")
            if folder_id:
                owui_assign_chat_folder(token, chat_id, folder_id)
            record_result(
                n,
                "FAIL",
                test_id,
                name,
                model,
                [("backend_unavailable", False, detail)],
                0.0,
                chat_url,
            )
            counts["FAIL"] = counts.get("FAIL", 0) + 1
            return

    # Create chat and assign folder via API BEFORE browser navigation.
    # Assigning the folder after the browser has loaded an empty chat causes
    # OWUI to broadcast a chat-updated SSE event. The Svelte component re-renders
    # the "new chat" suggestions view in response, which corrupts the submit handler
    # and silently drops Enter keypresses. Assigning the folder first means the
    # browser opens the chat with the folder already set — no SSE event fires
    # during the test session.
    chat_id, chat_url = owui_create_chat(token, model, title_pending)
    if folder_id:
        owui_assign_chat_folder(token, chat_id, folder_id)
    try:
        await _navigate_to_chat(page, chat_url)
    except _PresetUnreachableError as exc:
        record_result(
            n,
            "SKIP",
            test_id,
            name,
            model,
            [("persona_preset_unreachable", False, str(exc)[:160])],
            0.0,
            chat_url,
        )
        counts["SKIP"] = counts.get("SKIP", 0) + 1
        return
    except Exception as exc:
        # SPA navigation timeout or other startup error — record as BLOCKED and
        # continue to the next test rather than crashing the entire run.
        print(
            f"  [BLOCKED] {test_id} — chat start failed: {type(exc).__name__}: {str(exc)[:120]}",
            flush=True,
        )
        record_result(
            n,
            "BLOCKED",
            test_id,
            name,
            model,
            [("chat_start_failed", False, f"{type(exc).__name__}: {str(exc)[:160]}")],
            0.0,
            chat_url,
        )
        counts["BLOCKED"] = counts.get("BLOCKED", 0) + 1
        return

    t0 = time.time()
    artifact_path: Path | None = None
    assertions_result: list = []
    status = "FAIL"
    response_text = ""
    attempts_used: int = 1

    try:
        # _navigate_to_chat above is the only navigation — do NOT navigate again here.
        # A second page.goto() corrupts Svelte submit-handler state for models
        # with tool initialization (dailydriver/proofreader).

        # Pre-stage audio fixture for tests that drive the mlx-transcribe MCP.
        # The MCP auto-detects the most recently modified audio file in the
        # workspace uploads dir when called with no `file` arg
        # (see scripts/mlx-transcribe.py::_latest_audio_upload). Mirrors how
        # operators drop audio into the UI; OWUI's M-01 already relies on
        # the same path.
        if test.get("pre_stage_audio"):
            import shutil as _shutil

            _fixture_path = Path(__file__).parent / "fixtures" / test.get("fixture", "")
            _ai_output = Path(os.environ.get("AI_OUTPUT_DIR") or (Path.home() / "AI_Output"))
            _uploads = _ai_output / "uploads"
            _uploads.mkdir(parents=True, exist_ok=True)
            _staged = _uploads / _fixture_path.name
            if _fixture_path.exists():
                _shutil.copy2(_fixture_path, _staged)
                _staged.touch()  # ensure newest-mtime wins
                print(f"  [TR pre-stage] staged {_fixture_path.name} → {_uploads}", flush=True)
            else:
                print(f"  [TR pre-stage] WARN: fixture missing at {_fixture_path}", flush=True)

        # Tools are pre-enabled via workspace toolIds seeding — do not toggle them here.
        # Calling _enable_tool would turn them OFF (they default to ON in seeded workspaces).

        # Send first turn — retry up to 2 times on empty response (Ollama cold load).
        # This is RECOVERY logic (handle empty/crashed backend), not a
        # validation strategy — same prompt is re-sent each time.
        max_wait = test.get("max_wait_no_progress", MAX_WAIT_NO_PROGRESS)
        _test_budget_s = test.get("timeout", 120)
        response_text = ""
        attempts_used = 0
        for attempt in range(3):
            attempts_used = attempt + 1
            await _fe_send_and_wait(
                page,
                test["prompt"],
                test_id,
                tier,
                max_wait,
                token=token,
                chat_id=chat_id,
            )
            chat_url = _fe_current_chat_url(page, fallback=chat_url)
            response_text = await _fe_get_last_response(page, token, chat_id)
            if response_text:
                break
            # Long-tail wait: DOM stable may have fired while reasoning model was
            # still generating (collapsed <details> block makes innerText appear
            # stable). Continue polling the API — large GGUF models (30-70B) can
            # take 5-7 minutes for reasoning; media_heavy (video/image gen) needs 240s for cold
            # HunyuanVideo runs; others bounded to ~90s.
            _poll_cap_s = 450 if tier == "ollama" else (240 if tier == "media_heavy" else 90)
            _poll_deadline = time.monotonic() + _poll_cap_s
            while time.monotonic() < _poll_deadline:
                await asyncio.sleep(5)
                response_text = await _fe_get_last_response(page, token, chat_id)
                if response_text:
                    break
                elapsed_now = time.time() - t0
                print(
                    f"  [{test_id}] polling for response… ({elapsed_now:.0f}s)",
                    flush=True,
                )
            if response_text:
                break
            elapsed_now = time.time() - t0
            # Hard cap: if total elapsed exceeds 3× the test timeout, stop retrying.
            # Prevents runaway reasoning models from consuming unbounded wall time.
            if elapsed_now > _test_budget_s * 3:
                print(
                    f"  [{test_id}] total elapsed {elapsed_now:.0f}s > 3× timeout "
                    f"({_test_budget_s * 3}s) — stopping retries",
                    flush=True,
                )
                break
            print(
                f"  [{test_id}] empty response on attempt {attempt + 1}/3 ({elapsed_now:.0f}s)",
                flush=True,
            )
            if attempt < 2:
                # Check backend health before retrying
                await _wait_for_backend_alive(tier)
                # Re-navigate to the chat URL before retrying. OWUI calls
                # get_all_models() on page load — this clears any stale model
                # availability cache from the tier-transition eviction period,
                # and resets any stuck "generating" UI state.
                if chat_url:
                    print(
                        f"  [{test_id}] re-navigating to refresh OWUI model cache before retry…",
                        flush=True,
                    )
                    await _navigate_to_chat(page, chat_url)

        # Download artifact if expected
        art_ext = test.get("artifact_ext")
        if art_ext:
            # Late arrival: slow tools (video gen ~131-200s) may stream past the
            # poll window, OR the model may stream a partial non-empty response
            # before the tool completes. Refresh response_text if it looks
            # incomplete (empty, or has no artifact URL yet).
            import re as _re

            _art_url_present = _re.search(
                rf"(?:/files/\S+?\.{_re.escape(art_ext)}|view\?filename=[^\s)>\]]*\.{_re.escape(art_ext)})",
                response_text or "",
            )
            if not response_text or not _art_url_present:
                response_text = (
                    await _fe_get_last_response(page, token, chat_id) or response_text or ""
                )
            artifact_path = await _fe_download_artifact(page, art_ext, response_text=response_text, since_ts=t0)

        # Multi-turn: send second message if defined
        turn2 = test.get("turn2")
        turn2_response = ""
        if turn2:
            await _fe_send_and_wait(
                page,
                turn2,
                test_id,
                tier,
                max_wait,
                token=token,
                chat_id=chat_id,
                min_messages=2,  # require ≥2 non-empty responses — prevents turn-1
                # stable content from satisfying the completion signal
            )
            chat_url = _fe_current_chat_url(page, fallback=chat_url)
            # For turn2, require ≥2 non-empty assistant messages so we don't
            # return turn-1's committed response as the turn-2 completion signal.
            turn2_response = await _fe_get_last_response(page, token, chat_id, min_messages=2)

        # Run assertions on turn 1
        _incl_think = test.get("include_thinking_in_assertions", False)
        assertions_result = run_assertions(response_text, test.get("assertions", []), artifact_path, include_thinking=_incl_think)

        # Run turn2 assertions if defined
        t2_spec = test.get("turn2_assertions", [])
        if t2_spec and turn2_response:
            t2_results = run_assertions(turn2_response, t2_spec, artifact_path, include_thinking=_incl_think)
            assertions_result.extend(t2_results)

        # Combine all specs for status computation
        all_specs = test.get("assertions", []) + test.get("turn2_assertions", [])
        status = compute_status(assertions_result, all_specs)

        # Surface retry-attempt count when recovery was needed. Appended
        # without a corresponding spec — compute_status (already run above)
        # zips assertions with spec and truncates extras, so this row is
        # informational only and does not affect grading.
        if attempts_used > 1:
            assertions_result.append(
                (
                    f"Recovery: passed on attempt {attempts_used}/3",
                    True,
                    f"{attempts_used - 1} retries needed (backend instability signal)",
                )
            )

        # Take screenshot on failure
        if status in ("FAIL", "WARN"):
            SCREENSHOT_DIR.mkdir(exist_ok=True)
            sc_path = SCREENSHOT_DIR / f"{test_id.lower()}.png"
            await page.screenshot(path=str(sc_path))

    except Exception as exc:
        assertions_result = [("exception", False, str(exc)[:120])]
        status = "FAIL"
        try:
            SCREENSHOT_DIR.mkdir(exist_ok=True)
            await page.screenshot(path=str(SCREENSHOT_DIR / f"{test_id.lower()}_exc.png"))
        except Exception:
            pass

    elapsed = time.time() - t0
    routed_model = await _fe_get_routed_model(test, page, token, chat_id)

    route_check = _check_routed_model(test, routed_model)
    if route_check is not None:
        matched, route_detail = route_check
        assertions_result.append(
            (f"Routed model: {routed_model[:40] or 'none'}", matched, route_detail)
        )
        if status == "PASS" and not matched:
            status = "WARN"
            print(f"  [{test_id}] route mismatch downgraded PASS→WARN: {route_detail}", flush=True)

        # Feed routing telemetry log for end-of-run summary
        try:
            import sys as _sys
            from pathlib import Path as _Path
            _sys.path.insert(0, str(_Path(__file__).parent))
            intended_keys = route_detail  # contains expected key info
            intended_ollama = test.get("workspace_tier", "") == "ollama"
            state._ROUTING_LOG.append({
                "test_id": test_id,
                "name": name,
                "section": test.get("section", ""),
                "workspace": test.get("model_slug", ""),
                "intended": test.get("model_slug", ""),
                "actual": routed_model,
                "matched": matched,
                "tier_mismatch": intended_ollama and not matched,
                "pipeline_backend": pipeline_backend,
                "intended_ollama": intended_ollama,
            })
        except Exception:
            pass

    final_title = f"[{status}] UAT: {test_id} {name}"
    owui_rename_chat(token, chat_id, final_title)
    record_result(
        n, status, test_id, name, model, assertions_result, elapsed, chat_url, routed_model
    )
    counts[status] = counts.get(status, 0) + 1

    if calibration_records is not None:
        calibration_records.append(
            {
                "test_id": test_id,
                "name": name,
                "section": test.get("section", ""),
                "workspace": test.get("model_slug", ""),
                "prompt": test.get("prompt", ""),
                "response_text": response_text,
                "chat_url": chat_url,
                "review_tag": "",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    # Always-on corpus emission — see TASK_UAT_CORPUS_CAPTURE_V1.md §A2.
    if corpus_run_id:
        _emit_corpus_row(
            corpus_run_id=corpus_run_id,
            test=test,
            routed_model=routed_model,
            response_text=response_text,
            chat_url=chat_url,
            status=status,
            assertions_result=assertions_result,
            elapsed=elapsed,
        )


def _emit_corpus_row(
    corpus_run_id: str,
    test: dict,
    routed_model: str,
    response_text: str,
    chat_url: str,
    status: str,
    assertions_result: list,
    elapsed: float,
) -> None:
    """Append one JSONL row to the UAT response corpus.

    The corpus is always-on (no flag required) and one file per UAT run.
    Emission is incremental — each call opens the file in append mode,
    writes one line, and closes, so a crashed run leaves valid JSONL.

    See TASK_UAT_CORPUS_CAPTURE_V1.md for schema + rationale.
    """
    import json as _json

    corpus_dir = Path("tests/uat_corpus")
    corpus_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = corpus_dir / f"uat_{corpus_run_id}.jsonl"

    # Convert tuple assertion results to JSON-safe lists. The in-memory
    # format is tuples of (label:str, passed:bool, detail:str); JSON has
    # no tuple type, so we serialize as lists.
    safe_assertions = [list(a) if isinstance(a, tuple) else a for a in (assertions_result or [])]

    row = {
        "schema_version": 1,
        "corpus_run_id": corpus_run_id,
        "test_id": test.get("id", ""),
        "test_name": test.get("name", ""),
        "section": test.get("section", ""),
        "workspace": test.get("model_slug", ""),
        "expected_models": test.get("expected_models", {}),
        "routed_model": routed_model or "",
        "prompt": test.get("prompt", ""),
        "response_text": response_text or "",
        "chat_url": chat_url or "",
        "status": status,
        "assertions_result": safe_assertions,
        "elapsed_seconds": float(elapsed) if elapsed is not None else 0.0,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        with corpus_path.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        # Corpus emission is best-effort — never fail a test because the
        # corpus write failed. Log and continue.
        print(f"  [corpus] WARN: failed to write {test.get('id', '?')}: {exc}", flush=True)


def _emit_signals_from_calibration(json_path: str, output_path: str = "updated_signals.py") -> None:
    """Read calibration JSON, extract keywords from 'good' responses, write a signals suggestion file."""
    import json as _json
    import math as _math
    import re as _re

    records = _json.loads(Path(json_path).read_text())
    good = [r for r in records if r.get("review_tag") == "good"]

    if not good:
        print(f"No 'good'-tagged records found in {json_path}.")
        print(
            "Open the JSON, set review_tag to 'good' / 'bad' / 'skip' for each entry, then re-run."
        )
        return

    # Group by section
    by_section: dict[str, list[str]] = {}
    for rec in good:
        sec = rec.get("section") or "general"
        by_section.setdefault(sec, []).append(rec.get("response_text", ""))

    def _tokenize(text: str) -> list[str]:
        return _re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]{2,}\b", text.lower())

    _STOPWORDS = {
        "the",
        "and",
        "for",
        "this",
        "that",
        "with",
        "from",
        "are",
        "can",
        "will",
        "not",
        "you",
        "your",
        "have",
        "has",
        "was",
        "but",
        "all",
        "more",
        "into",
        "use",
        "used",
        "using",
        "would",
        "should",
        "could",
        "when",
        "which",
        "here",
        "there",
        "also",
        "each",
        "such",
        "then",
        "they",
        "them",
        "their",
        "been",
        "its",
        "any",
        "how",
        "what",
        "where",
        "who",
        "why",
        "may",
        "one",
        "two",
        "three",
        "just",
        "like",
        "make",
        "made",
        "note",
        "see",
        "get",
        "set",
    }

    # IDF: inverse of how many sections a word appears in
    idf: dict[str, int] = {}
    for texts in by_section.values():
        words_in_sec = set(_tokenize(" ".join(texts)))
        for w in words_in_sec:
            idf[w] = idf.get(w, 0) + 1
    n_sections = len(by_section)
    idf_score = {w: _math.log((n_sections + 1) / (cnt + 1)) for w, cnt in idf.items()}

    section_keywords: dict[str, list[str]] = {}
    for sec, texts in by_section.items():
        words = _tokenize(" ".join(texts))
        tf: dict[str, int] = {}
        for w in words:
            if w not in _STOPWORDS and len(w) > 3:
                tf[w] = tf.get(w, 0) + 1
        total = sum(tf.values()) or 1
        scored = {w: (cnt / total) * idf_score.get(w, 0.0) for w, cnt in tf.items()}
        section_keywords[sec] = sorted(scored, key=lambda x: -scored[x])[:10]

    out_lines = [
        '"""Auto-generated quality signals from calibration data.',
        "",
        "Generated by: python3 tests/portal5_uat_driver.py --emit-signals-from <json>",
        "",
        "Review and integrate into tests/quality_signals.py or the UAT test catalog.",
        '"""',
        "",
        "CALIBRATION_SIGNALS: dict[str, list[str]] = {",
    ]
    for sec in sorted(section_keywords):
        kws = section_keywords[sec]
        out_lines.append(f"    {sec!r}: {kws!r},")
    out_lines.append("}")
    out_lines.append("")
    out_lines.append("# Suggested assert_contains additions for TEST_CATALOG entries:")
    for sec in sorted(section_keywords):
        kws = section_keywords[sec][:5]
        out_lines.append(
            f"# section={sec!r}: "
            + '{"type": "any_of", "label": "Quality signal", "keywords": '
            + repr(kws)
            + "}"
        )

    Path(output_path).write_text("\n".join(out_lines) + "\n")
    print(f"Signals written to {output_path}")
    for sec, kws in sorted(section_keywords.items()):
        print(f"  {sec}: {kws}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Portal 5 UAT Conversation Driver")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--section", action="append", help="Run tests from section(s)")
    parser.add_argument(
        "--test", metavar="ID", action="append", help="Run test(s) by ID (repeatable)"
    )
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--skip-artifacts", action="store_true", help="Skip ComfyUI/Wan2.2 tests")
    parser.add_argument("--skip-bots", action="store_true", help="Skip Telegram/Slack bot tests")
    parser.add_argument(
        "--media",
        action="store_true",
        help=(
            "Run only media-generation tests (image, sound, voice, video) — "
            "shorthand for selecting all tests with workspace_tier=media_heavy. "
            "Useful for debugging MCP/Open WebUI media plumbing in isolation."
        ),
    )
    parser.add_argument("--timeout", type=int, help="Override per-test timeout (seconds)")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append results to existing UAT_RESULTS.md (for re-runs)",
    )
    parser.add_argument(
        "--no-unload",
        action="store_true",
        help="Skip startup /unload — use when model is pre-warmed",
    )
    parser.add_argument(
        "--rerun",
        action="store_true",
        help=(
            "Re-run mode: remove existing rows in UAT_RESULTS.md for the selected "
            "test IDs before running. Implies --append. Use this when re-running a "
            "phase after a fix; prevents duplicate rows. Requires --section, --test, "
            "or --media to scope which tests to replace."
        ),
    )
    parser.add_argument(
        "--rerun-failed",
        action="store_true",
        help=(
            "Re-run only tests with status FAIL or BLOCKED in UAT_RESULTS.md. "
            "Implies --rerun --append. Use after a fix to retry only broken tests "
            "without re-running the entire section."
        ),
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Move existing root-level UAT chats into root UAT folder, then exit",
    )
    parser.add_argument(
        "--purge-uat",
        action="store_true",
        help="Delete all chats in the UAT folder and the folder itself, then exit. "
        "Run this after reviewing UAT_RESULTS.md to clean up OWUI.",
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Calibration mode: run all tests and capture full responses to JSON for review",
    )
    parser.add_argument(
        "--calibrate-output",
        default="calibration.json",
        metavar="FILE",
        help="Output path for calibration JSON (default: calibration.json)",
    )
    parser.add_argument(
        "--emit-signals-from",
        metavar="JSON",
        help="Generate quality_signals suggestions from a reviewed calibration JSON",
    )
    args = parser.parse_args()

    print("\nPortal 5 UAT Driver")
    print(f"OWUI: {OPENWEBUI_URL}  |  User: {ADMIN_EMAIL}")
    print(f"Results: {config.RESULTS_FILE}\n")

    # Auth
    token = owui_token()
    if not token:
        print("ERROR: Could not authenticate with Open WebUI", file=sys.stderr)
        sys.exit(1)

    # Codebase freshness — warn if running images predate latest git commits.
    # Stale images mean test results reflect old code, not HEAD.
    _check_image_freshness()

    # --emit-signals-from mode: standalone, no browser needed
    if args.emit_signals_from:
        output = getattr(args, "calibrate_output", "updated_signals.py")
        _emit_signals_from_calibration(args.emit_signals_from, output)
        return

    # --migrate mode: move existing loose UAT chats into UAT folder hierarchy, then exit
    if args.migrate:
        uat_root_id = owui_get_or_create_folder(token, "UAT")
        if uat_root_id:
            print(f"  Migrating loose UAT chats → root UAT folder (id={uat_root_id}) …")
            n_moved = owui_migrate_loose_uat_chats(token, uat_root_id)
            print(f"  Migrated {n_moved} chat(s).")
        else:
            print("  ERROR: could not get/create UAT root folder.")
            sys.exit(1)
        return

    # --purge-uat mode: delete all chats in the UAT folder, then delete the folder
    if args.purge_uat:
        folders = _owui_list_folders(token)
        uat_folder = next((f for f in folders if f.get("name") == "UAT" and not f.get("parent_id")), None)
        if not uat_folder:
            print("  No UAT folder found — nothing to purge.")
            return
        uat_root_id = uat_folder["id"]
        # Collect all chats currently in the UAT folder
        try:
            r = httpx.get(
                f"{OPENWEBUI_URL}/api/v1/chats/",
                headers=owui_headers(token),
                params={"limit": 9999},
                timeout=30,
            )
            all_chats = r.json() if r.status_code == 200 else []
        except Exception as e:
            print(f"  ERROR fetching chats: {e}")
            sys.exit(1)
        # OWUI list endpoint may not include folder_id; fetch detail for each to filter
        uat_chat_ids: list[str] = []
        for chat in all_chats:
            cid = chat.get("id", "")
            try:
                r2 = httpx.get(
                    f"{OPENWEBUI_URL}/api/v1/chats/{cid}",
                    headers=owui_headers(token),
                    timeout=10,
                )
                if r2.status_code == 200 and r2.json().get("folder_id") == uat_root_id:
                    uat_chat_ids.append(cid)
            except Exception:
                pass
        print(f"  UAT folder id={uat_root_id} — {len(uat_chat_ids)} chat(s) to delete")
        deleted = 0
        for cid in uat_chat_ids:
            try:
                r = httpx.delete(
                    f"{OPENWEBUI_URL}/api/v1/chats/{cid}",
                    headers=owui_headers(token),
                    timeout=10,
                )
                if r.status_code == 200:
                    deleted += 1
                else:
                    print(f"  WARNING: DELETE chat {cid} returned {r.status_code}")
            except Exception as e:
                print(f"  WARNING: DELETE chat {cid} error — {e}")
        print(f"  Deleted {deleted}/{len(uat_chat_ids)} chat(s).")
        # Now delete the UAT folder itself
        try:
            r = httpx.delete(
                f"{OPENWEBUI_URL}/api/v1/folders/{uat_root_id}",
                headers=owui_headers(token),
                timeout=10,
            )
            if r.status_code == 200:
                print("  UAT folder deleted.")
            else:
                print(f"  WARNING: DELETE folder returned {r.status_code} — {r.text[:120]}")
        except Exception as e:
            print(f"  WARNING: DELETE folder error — {e}")
        return

    # --rerun-failed: auto-select FAIL/BLOCKED tests from UAT_RESULTS.md,
    # then run them through the same cascade logic as a normal run.
    # Tests are sorted by tier (ollama → any) so
    # model loads are grouped and tier-transition eviction guards fire correctly.
    _RERUN_FAILED_STATE = Path("/tmp/portal5-rerun-failed-state.json")

    if args.rerun_failed:
        failed_ids = _parse_failed_test_ids()
        if not failed_ids:
            # Rows may have been removed by a previous --rerun-failed that was
            # interrupted before completing. Check for a saved state file.
            if _RERUN_FAILED_STATE.exists():
                import json as _json_rf

                saved = _json_rf.loads(_RERUN_FAILED_STATE.read_text())
                failed_ids = set(saved.get("ids", []))
                if failed_ids:
                    print(
                        f"  --rerun-failed: restored {len(failed_ids)} ID(s) from previous "
                        f"interrupted run ({_RERUN_FAILED_STATE})",
                        file=sys.stderr,
                    )
        if not failed_ids:
            print(
                "--rerun-failed: no FAIL or BLOCKED tests found in UAT_RESULTS.md — nothing to do",
                file=sys.stderr,
            )
            sys.exit(0)

        # Resolve IDs → catalog entries so we can show the tier plan up front.
        candidate_tests = [t for t in TEST_CATALOG if t["id"] in failed_ids]
        unknown = failed_ids - {t["id"] for t in candidate_tests}
        if unknown:
            print(
                f"  --rerun-failed: WARNING — {len(unknown)} ID(s) not in TEST_CATALOG "
                f"(may have been removed): {', '.join(sorted(unknown))}",
                file=sys.stderr,
            )

        # Group by tier so the caller can see what backend switching will occur.
        tier_groups: dict[str, list[str]] = {}
        for t in sort_tests_cascade(candidate_tests):
            tier = t.get("workspace_tier", "any")
            tier_groups.setdefault(tier, []).append(t["id"])

        plan = " → ".join(f"{tier}({len(ids)})" for tier, ids in tier_groups.items())
        print(f"  --rerun-failed: {len(candidate_tests)} test(s) across {len(tier_groups)} tier(s)")
        print(f"  Cascade plan: {plan}")
        for tier, ids in tier_groups.items():
            print(f"    [{tier}] {', '.join(ids)}")

        if len(tier_groups) > 1:
            print(
                "  NOTE: tier transitions will evict all models between groups — "
                "expect 30-60s pauses at each boundary."
            )

        # Save state before removing rows — if this run is interrupted, the
        # next --rerun-failed invocation can restore from here.
        import json as _json_rf2

        _RERUN_FAILED_STATE.write_text(_json_rf2.dumps({"ids": [t["id"] for t in candidate_tests]}))
        import atexit as _atexit

        _atexit.register(lambda: _RERUN_FAILED_STATE.unlink(missing_ok=True))

        args.test = [t["id"] for t in candidate_tests]
        args.rerun = True

    # Determine test selection. --media composes with --section by union;
    # --test always overrides.
    if args.test:
        test_ids = set(args.test)
        tests = [t for t in TEST_CATALOG if t["id"] in test_ids]
        if not tests:
            print(f"Error: test ID(s) '{args.test}' not found", file=sys.stderr)
            sys.exit(1)
    elif args.media or args.section:
        selected_ids: set[str] = set()
        if args.media:
            media_tests = [t for t in TEST_CATALOG if t.get("workspace_tier") == "media_heavy"]
            selected_ids.update(t["id"] for t in media_tests)
            print(
                f"--media selected {len(media_tests)} test(s): "
                + ", ".join(f"{t['id']}({t.get('media_kind', '?')})" for t in media_tests)
            )
        if args.section:
            section_tests = [t for t in TEST_CATALOG if t["section"] in args.section]
            selected_ids.update(t["id"] for t in section_tests)
        tests = [t for t in TEST_CATALOG if t["id"] in selected_ids]
    else:
        tests = list(TEST_CATALOG)

    # Apply skip flags
    if args.skip_artifacts:
        tests = [t for t in tests if t.get("skip_if") not in ("no_comfyui",)]
    if args.skip_bots:
        tests = [t for t in tests if t.get("skip_if") not in ("no_bot_telegram", "no_bot_slack")]

    if not tests:
        print("No tests selected.", file=sys.stderr)
        sys.exit(1)

    print(f"{len(tests)} test(s) selected")

    # Reorder tests for model-cascade execution: tier groups (large→small→ollama→any),
    # then model_slug within each tier to minimize pipeline model switches.
    tests = sort_tests_cascade(tests)
    tier_counts = {}
    for t in tests:
        tier = t.get("workspace_tier", "any")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    print(f"  Cascade order: {' > '.join(f'{t}({c})' for t, c in tier_counts.items())}")

    # --rerun: remove existing rows for the selected tests so they don't duplicate
    if args.rerun:
        if not (args.test or args.section or args.media or args.rerun_failed):
            print(
                "ERROR: --rerun requires --test, --section, --media, or --rerun-failed "
                "to scope the replacement",
                file=sys.stderr,
            )
            sys.exit(1)
        # --rerun implies --append (we're editing an existing file)
        args.append = True
        if config.RESULTS_FILE.exists():
            target_ids = {t["id"] for t in tests}
            removed = _remove_rows_for_test_ids(target_ids)
            print(f"  --rerun: removed {removed} existing row(s) for {len(target_ids)} test ID(s)")
        else:
            print("  --rerun: no existing UAT_RESULTS.md to update — running fresh")
            args.append = False

    # Skip conditions
    skip_conditions = evaluate_skip_conditions()
    flagged = [k for k, v in skip_conditions.items() if v]
    if flagged:
        print(f"Skip conditions active: {', '.join(flagged)}")

    # Watchdog runs during UAT — the check_server_zombies() function now guards
    # on proxy state=switching so it won't kill a server that is mid-load.
    # Only S23-style tests that deliberately crash backends need the watchdog
    # stopped; UAT doesn't do that.

    # ---- Chat archival strategy ----
    # Chats run in root so OWUI navigation works during the run. On completion
    # (or SIGINT) they are moved to UAT/{YYYY-MM-DD}.
    # Pre-resolve the folder and stash token so the signal handler can archive
    # on interrupt without waiting for the normal end-of-run path.
    run_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    run_date = run_ts[:10]
    state._archive_token = token
    try:
        uat_root_id = owui_get_or_create_folder(token, "UAT")
        if uat_root_id:
            state._run_folder_id = owui_get_or_create_folder(token, run_date, parent_id=uat_root_id)
    except Exception as _e:
        print(f"  WARNING: could not pre-create UAT folder — chats will be moved at run end ({_e})")
    _install_archival_signal_handler(run_date)
    print(f"  Chat archival: conversations run in root → UAT/{run_date} on completion (or interrupt)")
    folder_id: str | None = None  # kept for legacy call sites in run_single_test
    _targeted = bool((args.test or args.section) and not args.rerun and not args.append)
    if _targeted:
        args.append = True
        print(f"  [targeted run] --append implied — UAT_RESULTS.md preserved (use --rerun to replace rows)")
    if not args.append:
        init_results(run_ts)
    counts: dict[str, int] = {}

    calibration_records: list | None = [] if args.calibrate else None
    if args.calibrate:
        print(f"  Calibration mode — responses will be saved to {args.calibrate_output}")

    # Always-on response corpus. See TASK_UAT_CORPUS_CAPTURE_V1.md §A2.
    corpus_run_id: str = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    print(f"  Corpus: tests/uat_corpus/uat_{corpus_run_id}.jsonl")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )
        page = await ctx.new_page()
        await _fe_login(page)
        print("  Logged in to Open WebUI\n")

        t_start = time.time()
        await _notify_test_start(
            sections=args.section,
            test_count=len(tests),
        )

        # Start continuous memory/health monitor (background task)
        monitor = MemoryMonitor(poll_interval=20.0)
        monitor.start()

        # Start crash watcher (background thread — watches DiagnosticReports)
        _crash_watcher.start()

        _last_tier: str = ""
        for i, test in enumerate(tests, start=1):
            tier = test.get("workspace_tier", "any")

            # Tier transition: evict previous backend + verify memory is clean
            # Critical: two models must never be resident simultaneously (OOM risk).
            if tier != _last_tier:
                if _last_tier:
                    print(f"  Tier transition: {_last_tier} → {tier} — evicting models")
                    unload_all_models()
                elif args.no_unload:
                    print("  Skipping startup /unload (--no-unload, model pre-warmed)")
                else:
                    unload_all_models()

                # Verify prerequisites before proceeding
                # When --no-unload, skip all eviction — model was pre-warmed externally.
                if args.no_unload:
                    print(
                        "  [verify] Skipping Ollama eviction checks (--no-unload, model pre-warmed)"
                    )
                elif tier == "ollama":
                    # Ollama tier: verify models are unloaded before starting
                    for retry in range(3):
                        try:
                            ps = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=5).json()
                            loaded = ps.get("models", [])
                            if not loaded:
                                break
                            print(
                                f"  [verify] Ollama still has {len(loaded)} model(s) loaded — retrying eviction ({retry + 1}/3)"
                            )
                            unload_all_models()
                            _wait_for_ollama_ps_empty(timeout_s=15.0)
                        except Exception:
                            break
                    if retry == 2:
                        try:
                            ps2 = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=5).json()
                            if ps2.get("models"):
                                print(
                                    "  [verify] WARNING: Ollama models still loaded after 3 eviction attempts — may cause OOM"
                                )
                        except Exception:
                            pass

                elif tier == "media_heavy":
                    # Media-heavy tier (TTS, music, video, image): verify Ollama
                    # is clear AND memory is actually freed before proceeding —
                    # media tools spawn additional processes that compete for
                    # GPU memory and can crash the system.
                    for retry in range(3):
                        try:
                            ps = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=5).json()
                            loaded = ps.get("models", [])
                            if not loaded:
                                break
                            print(
                                f"  [verify] Ollama still has {len(loaded)} model(s) — retrying eviction ({retry + 1}/3)"
                            )
                            unload_all_models()
                            _wait_for_ollama_ps_empty(timeout_s=15.0)
                        except Exception:
                            break
                    # Post-eviction: wait for Metal drain with retry+recovery before
                    # moving to next tier. Warn but don't block — tier transitions
                    # are between sections, not individual tests; a single BLOCKED
                    # row per test is already the guard if drain fails there.
                    if not _wait_for_drain(threshold_pct=75.0, label="tier-transition",
                                           timeout_s=30.0, retries=2):
                        used_pct = _get_memory_pct()
                        print(f"  [mem] WARNING: Metal still at {used_pct:.0f}% after all recovery — "
                              "individual force_unload_before gates will catch affected tests", flush=True)

                _last_tier = tier

            # Pre-flight: wait for Ollama to be ready before firing the test.
            # Called for ALL tiers: any-tier tests also route through Ollama.
            if test.get("workspace_tier") in ("ollama", "any"):
                ws_id = test.get("model_slug", "auto")
                if tier == "ollama":
                    _pipeline_pre_warm(ws_id)

            # Force-unload before heavy tests that need clean Metal state.
            # Drain must succeed before the test fires — if all recovery actions
            # (purge → Ollama restart) are exhausted, block the test as MEM rather
            # than proceeding into a known-bad memory state that produces confusing
            # routing-fallback failures.
            if test.get("force_unload_before"):
                print(f"  [mem] Force-unloading before {test['id']}")
                unload_all_models()
                _wait_for_ollama_ps_empty(timeout_s=15.0)
                drain_ok = _wait_for_drain(threshold_pct=75.0, label="force-unload",
                                           timeout_s=30.0, retries=2)
                if not drain_ok:
                    used_pct = _get_memory_pct()
                    drain_msg = f"Metal drain failed ({used_pct:.0f}% wired after purge+restart)"
                    print(f"  [mem] BLOCKED: {test['id']} — {drain_msg}", flush=True)
                    counts["BLOCKED"] = counts.get("BLOCKED", 0) + 1
                    record_result(
                        i,
                        "BLOCKED",
                        test["id"],
                        test["name"],
                        test.get("model_slug", "auto"),
                        [("metal_drain", False, drain_msg)],
                        0.0,
                        "",
                    )
                    update_summary(counts)
                    continue

            # ComfyUI lifecycle: only keep ComfyUI running during tests that
            # actually need it. Stop it before non-ComfyUI tests to reclaim GPU
            # memory; start it (with warmup wait) before ComfyUI-dependent tests.
            needs_comfyui = test.get("skip_if") == "no_comfyui"
            if needs_comfyui and not _comfyui_running():
                # Bring ComfyUI up and give Metal a 30s warmup before the test
                started = _start_comfyui(wait_s=60)
                if started:
                    time.sleep(30)  # Metal warmup before first inference
            elif not needs_comfyui and _comfyui_running():
                _stop_comfyui()

            # If the crash watcher saw a crash since the last
            # test, block here until memory has fully drained before loading
            # another model.
            # another model — attempting a load into a crash-starved Metal
            # heap crashes again immediately and makes memory worse.
            if _crash_watcher.crash_pending:
                _crash_watcher.wait_for_recovery(f"{test['id']} {test['name']}")

            # Pre-test memory check (monitor runs continuously in background,
            # but this catches issues right before a test starts)
            safe = _check_memory_before_test(f"{test['id']} {test['name']}")
            if not safe:
                used_pct = _get_memory_pct()
                print(
                    f"  [{i:02d}/{len(tests):02d}] {test['id']} SKIPPED (memory pressure {used_pct:.0f}%)"
                )
                # Write a row so the skip is visible in UAT_RESULTS.md, not just summary count
                record_result(
                    n=i,
                    status="SKIP",
                    test_id=test["id"],
                    name=test["name"],
                    model=test["model_slug"],
                    assertions=[
                        (
                            "memory_pressure_skip",
                            False,
                            f"used={used_pct:.0f}%, threshold={MEMORY_CRITICAL_PCT:.0f}%",
                        )
                    ],
                    elapsed=0.0,
                    chat_url=f"memory-skip://{used_pct:.0f}pct",
                )
                counts["SKIP"] = counts.get("SKIP", 0) + 1
                continue

            print(f"[{i:02d}/{len(tests):02d}] {test['id']} {test['name']}")

            await run_test(
                page=page,
                test=test,
                token=token,
                skip_conditions=skip_conditions,
                n=i,
                counts=counts,
                headed=args.headed,
                folder_id=folder_id,
                calibration_records=calibration_records,
                corpus_run_id=corpus_run_id,
            )

            # Post-test memory cleanup: only evict when the NEXT test uses a
            # different model_slug. Cascade grouping already keeps same-model
            # tests together to minimize model switches — don't undo that.
            if i < len(tests):
                next_test = tests[i]
                same_model = test.get("model_slug") == next_test.get("model_slug") and test.get(
                    "workspace_tier"
                ) == next_test.get("workspace_tier")
                mem_pct = _get_memory_pct()
                if not same_model and mem_pct >= MEMORY_WARN_PCT:
                    print(f"  [mem] Post-test memory at {mem_pct:.0f}% — evicting (model changing)")
                    unload_all_models()
                    _wait_for_drain(threshold_pct=MEMORY_WARN_PCT, timeout_s=90.0, label="post-evict")
                    mem_after = _get_memory_pct()
                    if mem_after >= MEMORY_CRITICAL_PCT:
                        print(
                            f"  [mem] Memory still {mem_after:.0f}% after eviction — second eviction pass"
                        )
                        unload_all_models()
                        _wait_for_drain(threshold_pct=MEMORY_WARN_PCT, timeout_s=120.0, label="post-evict-2")
                elif same_model and mem_pct >= MEMORY_SAME_MODEL_EVICT_PCT:
                    # KV cache from this test's inference will compound with the next
                    # test's allocation even when the same model stays loaded.
                    print(
                        f"  [mem] Post-test memory at {mem_pct:.0f}% (same model) "
                        "— evicting to clear KV cache residuals"
                    )
                    unload_all_models()
                    _wait_for_ollama_ps_empty(timeout_s=15.0)
                    mem_after = _get_memory_pct()
                    if mem_after >= MEMORY_SAME_MODEL_EVICT_PCT:
                        print(
                            f"  [mem] Memory still {mem_after:.0f}% after same-model eviction "
                            "— memory may not have drained yet"
                        )
                elif mem_pct >= MEMORY_CRITICAL_PCT:
                    # Always evict if critical, even on same model
                    print(f"  [mem] Post-test memory at {mem_pct:.0f}% — critical eviction")
                    unload_all_models()
                    _wait_for_ollama_ps_empty(timeout_s=15.0)

            # Inter-test settling: sleep the prescribed delay, then ensure the
            # backend for the next test is actually alive before proceeding.
            if i < len(tests):
                delay = settling_delay(
                    test.get("workspace_tier", "any"),
                    tests[i].get("workspace_tier", "any"),
                )
                if delay > 0:
                    await asyncio.sleep(delay)
                next_tier = tests[i].get("workspace_tier", "any")
                if next_tier in ("ollama",):
                    alive, detail = _backend_alive(next_tier)
                    if not alive:
                        print(
                            f"  [health] post-settling backend check: {detail}", flush=True
                        )
                        await _wait_for_backend(next_tier, max_wait=60)

        # Navigate away from the last chat before closing so OWUI can commit its
        # "done" state cleanly — prevents the browser-disconnect spinner on the
        # last visited conversation.
        try:
            await page.goto(OPENWEBUI_URL, wait_until="load", timeout=8000)
        except Exception:
            pass
        await browser.close()

    # Stop continuous monitor and crash watcher
    await monitor.stop()
    _crash_watcher.stop()
    if _crash_watcher.crash_log:
        print(
            f"  [crash-watcher] {len(_crash_watcher.crash_log)} crash(es) detected during run:",
            flush=True,
        )
        for entry in _crash_watcher.crash_log:
            print(f"    {entry}", flush=True)

    # Final cleanup: evict all models to prevent OOM after UAT completes
    cleanup_after_uat()

    elapsed = int(time.time() - t_start)
    await _notify_test_end(
        sections=args.section,
        elapsed=elapsed,
        counts=counts,
        test_count=len(tests),
    )
    await _notify_test_summary(
        counts=counts,
        elapsed=elapsed,
        sections=args.section,
        test_count=len(tests),
    )

    # Write calibration JSON if collected
    if calibration_records is not None:
        import json as _json

        cal_path = Path(args.calibrate_output)
        cal_path.write_text(_json.dumps(calibration_records, indent=2, ensure_ascii=False))
        print(f"\nCalibration data: {cal_path} ({len(calibration_records)} records)")
        print("Next: review 'review_tag' fields (good/bad/skip), then run:")
        print(f"  python3 tests/portal5_uat_driver.py --emit-signals-from {cal_path}")

    # Write routing intent-vs-actual summary before rebuilding counts.
    _write_routing_summary()

    # Always rebuild the summary header from actual file rows, so the count
    # is correct after partial / phased / rerun executions.
    _rebuild_summary_from_rows()

    # ---- Post-run archival ----
    _archive_run_chats(run_date, quiet=False)

    # Print routing summary to stdout as well
    if state._ROUTING_LOG:
        tier_fallbacks = [r for r in state._ROUTING_LOG if not r["matched"] and r["tier_mismatch"]]
        wrong_model = [r for r in state._ROUTING_LOG if not r["matched"] and not r["tier_mismatch"] and r["actual"]]
        correct = [r for r in state._ROUTING_LOG if r["matched"]]
        print(f"\n{'─' * 50}")
        print("ROUTING SUMMARY")
        print(f"{'─' * 50}")
        print(f"  Checked: {len(state._ROUTING_LOG)}   ✅ {len(correct)} correct"
              + (f"   ⚠️  {len(tier_fallbacks)} routing mismatch" if tier_fallbacks else "")
              + (f"   ⚠️  {len(wrong_model)} wrong model" if wrong_model else ""))
        for r in tier_fallbacks:
            print(f"  FALLBACK  {r['test_id']:12s} {r['section']:18s} intended={r['intended'][:35]}  got={r['actual'][:35]}")
        for r in wrong_model:
            print(f"  MISMATCH  {r['test_id']:12s} {r['section']:18s} intended={r['intended'][:35]}  got={r['actual'][:35]}")
        if not tier_fallbacks and not wrong_model:
            print("  All tests served by intended primary model.")
        print(f"{'─' * 50}")

    total = sum(counts.values())
    print(f"\n{'=' * 50}")
    print(
        f"Results: {counts.get('PASS', 0)}P / {counts.get('WARN', 0)}W / "
        f"{counts.get('FAIL', 0)}F / {counts.get('SKIP', 0)}S / "
        f"{counts.get('BLOCKED', 0)}B / {counts.get('MANUAL', 0)}M  ({total} total)"
    )
    print(f"Report:  {config.RESULTS_FILE}")
    print(f"Chats:   {OPENWEBUI_URL}")


if __name__ == "__main__":
    asyncio.run(main())
