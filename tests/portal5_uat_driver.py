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
from tests.uat.browser import (
    _download_artifact,
    _enable_tool,
    _login,
    _navigate_to_chat,
    _send_and_wait,
    _stop_button_visible,
    _wait_for_completion,
)
from tests.uat.calibration import _emit_corpus_row, _emit_signals_from_calibration
from tests.uat.dispatch import (
    _PresetUnreachableError,
    _extract_dom_response,
    _fe_assign_folder,
    _fe_current_chat_url,
    _fe_download_artifact,
    _fe_enable_tool,
    _fe_get_last_response,
    _fe_get_routed_model,
    _fe_login,
    _fe_send_and_wait,
    _fe_start_chat,
)
from tests.uat.routing import (
    _check_routed_model,
    _get_backend_from_pipeline_logs,
    _map_slug_to_workspace,
)
from tests.uat.skips import (
    _bot_container_running,
    _env_var_set,
    _run_via_dispatcher,
    evaluate_skip_conditions,
)
# --- end TASK_UAT_MODULARIZE_V1 transitional re-imports ---

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
            pipeline_backend = _get_backend_from_pipeline_logs(test.get("model_slug", ""))
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
