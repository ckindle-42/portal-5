"""Portal 5 UAT driver package (TASK_UAT_MODULARIZE_V1).

Decomposition of tests/portal5_uat_driver.py. Module map:

    config       env constants, timeouts, memory thresholds, result paths
    state        mutable per-run state (routing log, chat ids, archival)
    freshness    running-image vs git-HEAD freshness check
    health       backend health, memory pressure, OOM/zombie detection
    lifecycle    model unload, pipeline pre-warm, ComfyUI start/stop
    owui_api     OWUI REST helpers, chat archival, response retrieval
    routing      slug->workspace mapping, routed-model validation
    browser      Playwright helpers (login, send, completion-wait, artifacts)
    dispatch     frontend dispatch shims (_fe_*) over browser + owui_api
    grading      think-block stripping, assertion engine, compute_status
    results      UAT_RESULTS.md recorder, summary/rerun row management
    skips        skip-condition detection, bot dispatcher path
    monitor      inter-test settling, MemoryMonitor, CrashWatcher
    runner       cascade ordering, run_test, two-chat orchestration
    calibration  calibration corpus + quality-signal emission
    notify       run notifications, git sha
    cli          argparse main() + run orchestration

tests/portal5_uat_driver.py remains the operator-facing entry point.

Monkeypatching note: patch names on the module that OWNS them
(e.g. tests.uat.config.RESULTS_FILE, tests.uat.health._backend_alive,
tests.uat.owui_api.owui_get_last_response), never on re-exports.
"""

import sys
from pathlib import Path

# Make both `tests.*` package imports and legacy flat imports
# (expected_models, quality_signals, memory_guard, uat_catalog) resolve
# regardless of how the entry script is invoked.
_TESTS_DIR = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _TESTS_DIR.parent
for _p in (str(_PROJECT_ROOT), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
