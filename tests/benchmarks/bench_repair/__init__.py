"""Portal 5 — repair-loop coding bench: one-shot vs +1-repair pass rate.

Monkeypatching must target the owning module (e.g. `runner._chat_ollama`),
not these re-exports.
"""

from tests.benchmarks.bench_repair.checkpoint import (
    append_samples,
    cell_done,
    checkpoint_path,
    load_checkpoint,
    samples_for_cell,
)
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
    "checkpoint_path",
    "load_checkpoint",
    "append_samples",
    "cell_done",
    "samples_for_cell",
]
