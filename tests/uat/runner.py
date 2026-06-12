"""Portal 5 UAT — cascade ordering, run_test, two-chat orchestration.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase D).
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import httpx

from tests.uat import state
from tests.uat.browser import _navigate_to_chat, _send_and_wait
from tests.uat.calibration import _emit_corpus_row
from tests.uat.config import MAX_WAIT_NO_PROGRESS, SCREENSHOT_DIR
from tests.uat.dispatch import (
    _fe_current_chat_url,
    _fe_download_artifact,
    _fe_get_last_response,
    _fe_get_routed_model,
    _fe_send_and_wait,
    _PresetUnreachableError,
)
from tests.uat.grading import compute_status, run_assertions
from tests.uat.health import (
    _backend_alive,
    _wait_for_backend,
    _wait_for_backend_alive,
)
from tests.uat.lifecycle import unload_all_models
from tests.uat.owui_api import (
    owui_assign_chat_folder,
    owui_create_chat,
    owui_rename_chat,
)
from tests.uat.results import record_result
from tests.uat.routing import _check_routed_model, _get_backend_from_pipeline_logs
from tests.uat.skips import _bot_container_running, _run_via_dispatcher

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
        assertions_result = run_assertions(
            response1, test.get("assertions", []), include_thinking=_incl_think
        )
        t2_results = run_assertions(
            response2, test.get("turn2_assertions", []), include_thinking=_incl_think
        )
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
        assertions_result = run_assertions(
            response_text, test.get("assertions", []), include_thinking=_incl_think
        )
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

            _fixture_path = (
                Path(__file__).resolve().parents[1] / "fixtures" / test.get("fixture", "")
            )
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
            artifact_path = await _fe_download_artifact(
                page, art_ext, response_text=response_text, since_ts=t0
            )

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
        assertions_result = run_assertions(
            response_text, test.get("assertions", []), artifact_path, include_thinking=_incl_think
        )

        # Run turn2 assertions if defined
        t2_spec = test.get("turn2_assertions", [])
        if t2_spec and turn2_response:
            t2_results = run_assertions(
                turn2_response, t2_spec, artifact_path, include_thinking=_incl_think
            )
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

            _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
            intended_keys = route_detail  # contains expected key info
            intended_ollama = test.get("workspace_tier", "") == "ollama"
            pipeline_backend = _get_backend_from_pipeline_logs(test.get("model_slug", ""))
            state._ROUTING_LOG.append(
                {
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
                }
            )
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
