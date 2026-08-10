#!/usr/bin/env python3
"""Portal 5 — repair-loop coding bench (entry-point shim for tests/benchmarks/bench_repair/).

python3 tests/benchmarks/bench_repair.py --dry-run
python3 tests/benchmarks/bench_repair.py --models bench-devstral,bench-qwen36-27b
"""

import sys
from pathlib import Path

# Repo root must lead sys.path even if an unrelated same-named package
# sits earlier on PYTHONPATH (e.g. another checkout on this machine).
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
