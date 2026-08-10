#!/usr/bin/env python3
"""Portal 5 — repair-loop coding bench (entry-point shim).

The implementation lives in the tests/benchmarks/bench_repair/ package.
This file is the stable operator-facing entry point.

    python3 tests/benchmarks/bench_repair.py --dry-run
    python3 tests/benchmarks/bench_repair.py
    python3 tests/benchmarks/bench_repair.py --models bench-devstral,bench-qwen36-27b
    python3 tests/benchmarks/bench_repair.py --problems c2_1,c2_5 --output /tmp/quick.md

Measures execution-graded pass rate under two arms (one-shot n=5,
+1-repair n=2, temp=1.0). See tests/benchmarks/bench_repair/__init__.py
for the module map. All public names are re-exported here so existing
importers keep working.
"""

import sys
from pathlib import Path

# Make `tests.*` / `portal.*` imports resolve to this repo even when
# PYTHONPATH already contains an unrelated same-named package earlier in
# sys.path (e.g. another checkout on this machine) — repo root must lead.
_REPO_STR = str(Path(__file__).resolve().parents[2])
if _REPO_STR in sys.path:
    sys.path.remove(_REPO_STR)
sys.path.insert(0, _REPO_STR)

from tests.benchmarks.bench_repair import (  # noqa: E402,F401
    ARM_ONESHOT,
    ARM_REPAIR,
    ARMS,
    OLLAMA_URL,
    ONE_SHOT_TEMPLATE,
    ONESHOT_N,
    REPAIR_N,
    REPAIR_TEMPLATE,
    TARGETS,
    TEMPERATURE,
    compute_gsha,
    evict_all,
    load_corpus,
    main,
    render_matrix,
    run_one_shot,
    run_repair,
    score_code,
)

if __name__ == "__main__":
    raise SystemExit(main())
