"""Portal 5 UAT — argparse main() + run orchestration.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase D). The operator entry point remains tests/portal5_uat_driver.py.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx

from tests.memory_guard import memory_pct as _get_memory_pct
from tests.uat import config, state
from tests.uat.calibration import _emit_signals_from_calibration
from tests.uat.config import (
    ADMIN_EMAIL,
    MEMORY_CRITICAL_PCT,
    MEMORY_SAME_MODEL_EVICT_PCT,
    MEMORY_WARN_PCT,
    OLLAMA_URL,
    OPENWEBUI_URL,
)
from tests.uat.dispatch import _fe_login
from tests.uat.freshness import _check_image_freshness
from tests.uat.health import (
    _backend_alive,
    _check_memory_before_test,
    _wait_for_backend,
    _wait_for_drain,
)
from tests.uat.lifecycle import (
    _comfyui_running,
    _pipeline_pre_warm,
    _start_comfyui,
    _stop_comfyui,
    _wait_for_ollama_ps_empty,
    cleanup_after_uat,
    unload_all_models,
)
from tests.uat.monitor import MemoryMonitor, _crash_watcher, settling_delay
from tests.uat.notify import (
    _notify_test_end,
    _notify_test_start,
    _notify_test_summary,
)
from tests.uat.owui_api import (
    _archive_run_chats,
    _install_archival_signal_handler,
    _owui_list_folders,
    owui_get_or_create_folder,
    owui_headers,
    owui_migrate_loose_uat_chats,
    owui_token,
)
from tests.uat.results import (
    _parse_failed_test_ids,
    _rebuild_summary_from_rows,
    _remove_rows_for_test_ids,
    _write_routing_summary,
    init_results,
    record_result,
    update_summary,
)
from tests.uat.runner import run_test, sort_tests_cascade
from tests.uat.skips import evaluate_skip_conditions
from tests.uat_catalog import TEST_CATALOG


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
        print("  [targeted run] --append implied — UAT_RESULTS.md preserved (use --rerun to replace rows)")
    if not args.append:
        init_results(run_ts)
    counts: dict[str, int] = {}

    calibration_records: list | None = [] if args.calibrate else None
    if args.calibrate:
        print(f"  Calibration mode — responses will be saved to {args.calibrate_output}")

    # Always-on response corpus. See TASK_UAT_CORPUS_CAPTURE_V1.md §A2.
    corpus_run_id: str = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    print(f"  Corpus: tests/uat_corpus/uat_{corpus_run_id}.jsonl")

    from playwright.async_api import async_playwright  # lazy: keeps unit-test collection light
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

            # Post-test memory cleanup: evict unconditionally on model change.
            # With OLLAMA_MAX_LOADED_MODELS=3 and keep_alive=-1, prior models
            # stay resident even after we switch — they stack with the next
            # large model and exhaust Metal memory. Always evict on model
            # change regardless of current memory percentage.
            # Same-model runs still respect a threshold to preserve KV cache
            # (avoids re-loading cost for same-model test groups).
            if i < len(tests):
                next_test = tests[i]
                same_model = test.get("model_slug") == next_test.get("model_slug") and test.get(
                    "workspace_tier"
                ) == next_test.get("workspace_tier")
                mem_pct = _get_memory_pct()
                if not same_model:
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
