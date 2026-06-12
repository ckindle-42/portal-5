#!/usr/bin/env python3
"""Portal 5 — Comprehensive TPS Benchmark (entry-point shim).

The implementation lives in the tests/benchmarks/bench/ package
(TASK_BENCH_MODULARIZE_V1). This file is the stable operator-facing entry
point — invoke it exactly as before:

    python3 tests/benchmarks/bench_tps.py                                    # everything, 5 runs
    python3 tests/benchmarks/bench_tps.py --runs 1                           # single run (faster)
    python3 tests/benchmarks/bench_tps.py --mode direct                      # Ollama direct only
    python3 tests/benchmarks/bench_tps.py --mode pipeline                    # workspaces only
    python3 tests/benchmarks/bench_tps.py --mode personas                    # personas only
    python3 tests/benchmarks/bench_tps.py --mode all --order size --runs 5 --cooldown 10  # standard baseline
    python3 tests/benchmarks/bench_tps.py --model dolphin-llama3             # filter by model substring
    python3 tests/benchmarks/bench_tps.py --workspace auto-coding            # single workspace
    python3 tests/benchmarks/bench_tps.py --persona cybersecurity            # filter personas
    python3 tests/benchmarks/bench_tps.py --output results.json              # custom output
    python3 tests/benchmarks/bench_tps.py --dry-run                          # show plan

See bench/__init__.py for the module map and bench/cli.py for orchestration.
All public names are re-exported here so existing importers
(`from tests.benchmarks import bench_tps`) keep working. NOTE: monkeypatching
internals must target the module that owns them (e.g. patch
tests.benchmarks.bench.discovery._load_backends_config), not these re-exports.
"""

import sys
from pathlib import Path

# Make `tests.*` imports work when invoked as a script from anywhere.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tests.benchmarks.bench.cli import main  # noqa: E402
from tests.benchmarks.bench.config import (  # noqa: E402, F401
    INFERENCE_TIMEOUT,
    MATH_MAX_TOKENS,
    MATH_SPECIALIST_WORKSPACES,
    MAX_TOKENS,
    OLLAMA_URL,
    PIPELINE_API_KEY,
    PIPELINE_INACTIVITY_TIMEOUT,
    PIPELINE_URL,
    PROJECT_ROOT,
    REASONING_MAX_TOKENS,
    REASONING_WORKSPACES,
    REQUEST_TIMEOUT,
    RESULTS_DIR,
    RESULTS_FILE,
    WARMUP_TIMEOUT,
    _is_reasoning_model,
)
from tests.benchmarks.bench.discovery import (  # noqa: E402, F401
    _config_ollama_models_by_group,
    _config_ollama_models_unique,
    _config_workspaces,
    _discover_personas,
    _load_backends_config,
    _parse_model_size_gb,
    _runtime_ollama_models,
)
from tests.benchmarks.bench.lifecycle import (  # noqa: E402, F401
    _check_backend,
    _cleanup_all_backends,
    _get_hardware_info,
    _unload_all_running_ollama_models,
    _unload_ollama_model,
    _wait_metal_drain,
    _wait_ollama_idle,
    _warmup_ollama_model,
)
from tests.benchmarks.bench.measure import (  # noqa: E402, F401
    _warmup_pipeline_model,
    bench_tps,
    close_bench_client,
)
from tests.benchmarks.bench.prompts import (  # noqa: E402, F401
    GROUP_PROMPT_MAP,
    PERSONA_CATEGORY_PROMPT_MAP,
    PROMPTS,
    WORKSPACE_PROMPT_MAP,
)
from tests.benchmarks.bench.runners import (  # noqa: E402, F401
    bench_direct,
    bench_personas,
    bench_pipeline,
)

if __name__ == "__main__":
    main()
