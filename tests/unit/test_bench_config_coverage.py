"""Guard test: bench harness config dicts stay in sync with live workspaces.

TASK_BENCH_CONFIG_RECONCILE_V1 / BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 4 —
the collapse (and now the alias retirement) folds/deletes workspaces, but the
bench harness's per-workspace lookup dicts (tests/benchmarks/bench/config.py
PER_WORKSPACE_TIMEOUT / REASONING_WORKSPACES, tests/benchmarks/bench/prompts.py
WORKSPACE_PROMPT_MAP) are hand-maintained and key on workspace id. A stale key
is a dead entry that silently drops per-workspace tuning; an unmapped live
workspace gets skipped or mis-prompted during a bench run. This test makes
that drift a red test the next time a workspace is renamed/added/removed,
instead of a silent measurement-quality regression discovered mid-sweep.

Uses ``get_workspace_dict(load_portal_config())`` (the same pattern as
test_pipeline.py::test_eval_gate_loads_all_104) to get an eval-gate-fresh
workspace set per call via ``monkeypatch.setenv`` — this re-derives the dict
from the (env-independent, cached) PortalConfig on every call rather than
mutating global module state, so it can't leak into other tests in the
session the way reloading portal.platform.inference.router.workspaces would.
"""

from __future__ import annotations

from portal.platform.inference.config import get_workspace_dict, load_portal_config


def _live_workspaces_with_eval(monkeypatch) -> set[str]:
    monkeypatch.setenv("PORTAL_ENABLE_EVAL", "1")
    return set(get_workspace_dict(load_portal_config()))


def test_per_workspace_timeout_no_stale_keys(monkeypatch):
    from tests.benchmarks.bench.config import PER_WORKSPACE_TIMEOUT

    live = _live_workspaces_with_eval(monkeypatch)
    stale = set(PER_WORKSPACE_TIMEOUT) - live
    assert not stale, f"PER_WORKSPACE_TIMEOUT has stale keys: {sorted(stale)}"


def test_reasoning_workspaces_no_stale_keys(monkeypatch):
    from tests.benchmarks.bench.config import REASONING_WORKSPACES

    live = _live_workspaces_with_eval(monkeypatch)
    stale = set(REASONING_WORKSPACES) - live
    assert not stale, f"REASONING_WORKSPACES has stale keys: {sorted(stale)}"


def test_workspace_prompt_map_no_stale_keys(monkeypatch):
    from tests.benchmarks.bench.prompts import WORKSPACE_PROMPT_MAP

    live = _live_workspaces_with_eval(monkeypatch)
    stale = set(WORKSPACE_PROMPT_MAP) - live
    assert not stale, f"WORKSPACE_PROMPT_MAP has stale keys: {sorted(stale)}"


def test_workspace_prompt_map_covers_all_non_eval_workspaces(monkeypatch):
    """Every live non-eval (non-bench-*) workspace must have a prompt mapping.

    bench-* workspaces are excluded here — coverage for the eval catalog is
    tracked separately below, and bench UAT tests are already skip-gated
    (see tests/uat/runner.py's eval gate / g_benchmark.py).
    """
    from tests.benchmarks.bench.prompts import WORKSPACE_PROMPT_MAP

    live = _live_workspaces_with_eval(monkeypatch)
    noneval = {w for w in live if not w.startswith("bench-")}
    unmapped = noneval - set(WORKSPACE_PROMPT_MAP)
    assert not unmapped, f"live workspaces missing WORKSPACE_PROMPT_MAP entry: {sorted(unmapped)}"


def test_workspace_prompt_map_covers_all_eval_workspaces(monkeypatch):
    """Every live bench-* (eval) workspace must also have a prompt mapping —
    a bench sweep that silently skips/mis-prompts a new intake is exactly the
    measurement-quality drift this guard exists to catch."""
    from tests.benchmarks.bench.prompts import WORKSPACE_PROMPT_MAP

    live = _live_workspaces_with_eval(monkeypatch)
    bench_ws = {w for w in live if w.startswith("bench-")}
    unmapped = bench_ws - set(WORKSPACE_PROMPT_MAP)
    assert not unmapped, (
        f"live bench-* workspaces missing WORKSPACE_PROMPT_MAP entry: {sorted(unmapped)}"
    )


def test_eval_env_actually_admits_bench_workspaces(monkeypatch):
    """Sanity check on the helper itself: with PORTAL_ENABLE_EVAL=1,
    bench-* workspaces must be present — guards against every other test in
    this file passing for the wrong reason (an empty/broken live set
    intersecting to an empty stale set)."""
    live = _live_workspaces_with_eval(monkeypatch)
    assert any(w.startswith("bench-") for w in live), (
        "expected bench-* workspaces to be present with PORTAL_ENABLE_EVAL=1"
    )
