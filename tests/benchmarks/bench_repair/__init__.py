"""Portal 5 — repair-loop coding bench.

Measures execution-graded pass rate under two arms:
  one-shot   : n=5 samples per (model, problem)
  +1-repair  : n=2 samples per (model, problem); on failure, second attempt
               receives the model's own code + pytest stderr and one retry.

Reuses capability_lib.run_python_against_tests for grading. Reuses
bench_capability's _emits_reasoning + _get_token_budget for reasoning-model
token allocation. Ollama-direct chat with keep_alive=0 model-major eviction
between models. No auto-promotion (PROMOTE_POLICY: confirm).

Public API stability: monkeypatching internals must target the module that
owns them (e.g. `bench_repair.runner._chat_ollama`), not the shim
re-exports.
"""

from tests.benchmarks.bench_repair.cli import main
from tests.benchmarks.bench_repair.config import (
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
)
from tests.benchmarks.bench_repair.corpus import compute_gsha, load_corpus
from tests.benchmarks.bench_repair.report import render_matrix
from tests.benchmarks.bench_repair.runner import evict_all, run_one_shot, run_repair
from tests.benchmarks.bench_repair.scoring import score_code

__all__ = [
    "main",
    "TARGETS",
    "ARM_ONESHOT",
    "ARM_REPAIR",
    "ARMS",
    "ONESHOT_N",
    "REPAIR_N",
    "TEMPERATURE",
    "OLLAMA_URL",
    "ONE_SHOT_TEMPLATE",
    "REPAIR_TEMPLATE",
    "load_corpus",
    "compute_gsha",
    "run_one_shot",
    "run_repair",
    "evict_all",
    "score_code",
    "render_matrix",
]
