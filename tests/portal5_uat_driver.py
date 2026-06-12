#!/usr/bin/env python3
"""Portal 5 UAT Conversation Driver (entry-point shim).

The implementation lives in the tests/uat/ package (TASK_UAT_MODULARIZE_V1).
This file is the stable operator-facing entry point — invoke it exactly as
before:

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

See tests/uat/__init__.py for the module map and tests/uat/cli.py for
orchestration. All public/test-imported names are re-exported here so
existing importers (``import portal5_uat_driver``) keep working. NOTE:
monkeypatching internals must target the module that owns them (e.g. patch
tests.uat.config.RESULTS_FILE, tests.uat.health._backend_alive,
tests.uat.owui_api.owui_get_last_response), not these re-exports.
"""

import asyncio
import sys
from pathlib import Path

# Make `tests.*` imports work when invoked as a script from anywhere.
_TESTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parent
for _p in (str(_PROJECT_ROOT), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.memory_guard import (  # noqa: E402, F401
    memory_pct as _get_memory_pct,
)
from tests.uat import config, state  # noqa: E402, F401
from tests.uat.browser import (  # noqa: E402, F401
    _download_artifact,
    _enable_tool,
    _login,
    _navigate_to_chat,
    _send_and_wait,
    _stop_button_visible,
    _wait_for_completion,
)
from tests.uat.calibration import (  # noqa: E402, F401
    _emit_corpus_row,
    _emit_signals_from_calibration,
)
from tests.uat.cli import main  # noqa: E402, F401
from tests.uat.config import (  # noqa: E402, F401
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
    RESULTS_FILE,
    SCREENSHOT_DIR,
    SECTIONS_REQUIRE_UNLOAD,
    SEND_TIMEOUT,
)
from tests.uat.dispatch import (  # noqa: E402, F401
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
from tests.uat.freshness import _REPO_ROOT, _check_image_freshness  # noqa: E402, F401
from tests.uat.grading import (  # noqa: E402, F401
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
from tests.uat.health import (  # noqa: E402, F401
    _backend_alive,
    _check_for_oom_crash,
    _check_memory_before_test,
    _wait_for_backend,
    _wait_for_backend_alive,
    _wait_for_drain,
)
from tests.uat.lifecycle import (  # noqa: E402, F401
    _comfyui_running,
    _pipeline_pre_warm,
    _start_comfyui,
    _stop_comfyui,
    _unload_running_ollama_models,
    _wait_for_ollama_ps_empty,
    cleanup_after_uat,
    unload_all_models,
)
from tests.uat.monitor import (  # noqa: E402, F401
    _DIAG_DIR,
    SETTLING,
    CrashWatcher,
    MemoryMonitor,
    _crash_watcher,
    settling_delay,
)
from tests.uat.notify import (  # noqa: E402, F401
    _git_sha,
    _notify_test_end,
    _notify_test_start,
    _notify_test_summary,
    _send_notification,
)
from tests.uat.owui_api import (  # noqa: E402, F401
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
from tests.uat.results import (  # noqa: E402, F401
    _parse_failed_test_ids,
    _parse_test_ids_from_results,
    _rebuild_summary_from_rows,
    _remove_rows_for_test_ids,
    _write_routing_summary,
    init_results,
    record_result,
    update_summary,
)
from tests.uat.routing import (  # noqa: E402, F401
    _check_routed_model,
    _get_backend_from_pipeline_logs,
    _map_slug_to_workspace,
)
from tests.uat.runner import (  # noqa: E402, F401
    _TIER_ORDER,
    _run_two_chat_test,
    run_test,
    sort_tests_cascade,
)
from tests.uat.skips import (  # noqa: E402, F401
    _bot_container_running,
    _env_var_set,
    _run_via_dispatcher,
    evaluate_skip_conditions,
)

if __name__ == "__main__":
    asyncio.run(main())
