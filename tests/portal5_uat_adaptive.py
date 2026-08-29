#!/usr/bin/env python3
"""Portal 5 Adaptive UAT — agent/operator tooling entry point (offline).

Generative, per-space, intended-use, operator-reviewed UAT for the v9 release
sign-off (TASK_UAT_ADAPTIVE_OVERHAUL_V1). The challenges are authored and
first-pass-judged by the executing Claude Code agent — independent of the
Portal 5 fleet under test — and signed off by the operator. Execution runs
through the main driver over OWUI; this shim covers the offline steps.

Full workflow:

    # 1. AUTHOR (agent). Emit worksheets, then fill each "prompt" reviewing the
    #    authoring_brief + design docs, then freeze:
    python3 tests/portal5_uat_adaptive.py --emit-worksheets
    #    ... agent edits tests/uat_adaptive/worksheets/*.json ...
    python3 tests/portal5_uat_adaptive.py --ingest-worksheets

    # 2. EXECUTE (through OWUI, main driver; loads the frozen agent-authored suites):
    python3 tests/portal5_uat_driver.py --adaptive --section adaptive-coding --append
    #    (repeat per module section; --headed for a smoke first)

    # 3. ASSESS (agent first pass). Dump pending, reason over each, apply a batch:
    python3 tests/portal5_uat_adaptive.py --assess-pending > pending.json
    #    ... agent writes agent_verdicts.json = [{test_id, scores{}, verdict, rationale}] ...
    python3 tests/portal5_uat_adaptive.py --assess-apply agent_verdicts.json

    # 4. REVIEW (operator). Build the packet (agent proposals pre-filled),
    #    confirm/override in the browser, Export verdicts JSON, ingest:
    python3 tests/portal5_uat_adaptive.py --packet
    python3 tests/portal5_uat_adaptive.py --ingest verdicts_<run>.json

Sign-off lands in tests/ADAPTIVE_UAT_RESULTS.md behind an operator [GATE].
For automated dev/regression runs (non-sign-off) the driver can auto-author with
--adaptive-regenerate (template) or --adaptive-author-model (non-independent).
"""

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parent
for _p in (str(_PROJECT_ROOT), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.uat.adaptive.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
