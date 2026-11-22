"""Pin the bench-* serialization invariant: every bench lane caps at one request.

Live QAT Stage 1 caught three bench lanes without ``max_concurrent: 1`` — a bench
run then co-schedules requests on one seat and skews the latency rows it measures.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from portal.platform.inference.config import (
    get_workspace_dict,
    load_bench_workspaces_raw,
    load_portal_config,
)
from portal.platform.inference.router.concurrency import _get_workspace_concurrency_limit
from portal.platform.inference.router.workspaces import WORKSPACES


def _declared_bench() -> dict[str, Any]:
    return load_bench_workspaces_raw()


def test_every_bench_workspace_declares_max_concurrent_1() -> None:
    offenders = {
        wsid: spec.get("max_concurrent")
        for wsid, spec in _declared_bench().items()
        if spec.get("max_concurrent") != 1
    }
    assert not offenders, f"bench lanes without max_concurrent: 1: {offenders}"


def test_resolution_returns_1_for_every_bench_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declared = _declared_bench()
    # The bench-harness opt-in: without it the runtime catalog drops eval lanes.
    monkeypatch.setenv("PORTAL_BENCH_WORKSPACES", "1")
    runtime = get_workspace_dict(load_portal_config(include_bench=True))
    bench = {wid: spec for wid, spec in runtime.items() if wid.startswith("bench-")}
    dropped = set(declared) - set(bench)
    assert not dropped, f"bench lanes dropped by the catalog merge: {sorted(dropped)}"
    # Env overrides outrank the YAML and would mask a missing field.
    for key in list(os.environ):
        is_lane = key.startswith("WORKSPACE_CONCURRENCY_")
        is_default = key == "PORTAL5_DEFAULT_WORKSPACE_CONCURRENCY"
        if is_lane or is_default:
            monkeypatch.delenv(key, raising=False)
    offenders: dict[str, int] = {}
    for wid, spec in bench.items():
        monkeypatch.setitem(WORKSPACES, wid, spec)
        limit = _get_workspace_concurrency_limit(wid)
        if limit != 1:
            offenders[wid] = limit
    assert not offenders, f"_get_workspace_concurrency_limit != 1 for bench lanes: {offenders}"
