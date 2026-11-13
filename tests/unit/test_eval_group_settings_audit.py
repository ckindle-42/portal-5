"""Eval-group seats are judged against bench_engines.yaml, not silenced."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from portal.platform.inference.cluster_backends import BackendRegistry
from tests.wfe import settings_audit as audit

CONFIG = "config/backends.yaml"
_QWEN = "Qwen3.8-27B-4bit"


def test_eval_group_hints_resolve_on_the_eval_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PORTAL_ENABLE_EVAL", raising=False)
    monkeypatch.delenv("PORTAL_BENCH_WORKSPACES", raising=False)
    reg = BackendRegistry(CONFIG, include_eval_backends=True)
    rows: list[dict] = []
    seats = [
        (
            "bench-engine-daily-moe",
            {"model_hint": "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp"},
        ),
        ("bench-engine-coding", {"model_hint": _QWEN}),
        (
            "bench-engine-task-router",
            {"model_hint": "hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k"},
        ),
        ("bench-engine-hunt", {"model_hint": "gemma-4-26b-a4b-it-QAT-4bit"}),
        ("bench-engine-council-json", {"model_hint": _QWEN}),
    ]
    backends = yaml.safe_load(Path(CONFIG).read_text(encoding="utf-8"))
    audit._audit_routable(seats, backends, rows)
    assert rows == []
    served = audit._served_path("bench-engine-coding", _QWEN, reg)
    assert served == ("eval_openai", "eval-openai", _QWEN)


def test_an_eval_only_hint_on_a_production_group_stays_unroutable() -> None:
    rows: list[dict] = []
    audit._audit_routable(
        [("auto-coding", {"model_hint": "not-a-registered-eval-or-production-model"})],
        {"workspace_routing": {"auto-coding": ["coding"]}},
        rows,
    )
    assert [row["kind"] for row in rows] == ["hint_unroutable"]
    assert "config/backends.yaml" in rows[0]["detail"]


def test_an_eval_group_miss_names_bench_engines() -> None:
    rows: list[dict] = []
    audit._audit_routable(
        [("bench-engine-coding", {"model_hint": "not-on-the-eval-backend"})],
        {"workspace_routing": {"bench-engine-coding": ["eval"]}},
        rows,
    )
    assert [row["kind"] for row in rows] == ["hint_unroutable"]
    assert "config/bench_engines.yaml" in rows[0]["detail"]


def test_eval_route_registration_is_the_eval_backend_not_backends_yaml() -> None:
    rows: list[dict] = []
    audit._audit_workspace(
        "bench-engine-coding",
        {"model_hint": _QWEN, "module": "eval", "tools": ["execute_python"]},
        set(),
        set(),
        {},
        rows,
        eval_ids={_QWEN},
        route_groups=["eval"],
        eval_tool_flags={_QWEN: True},
    )
    assert rows == []


def test_eval_model_off_the_eval_route_stays_unregistered() -> None:
    rows: list[dict] = []
    audit._audit_workspace(
        "auto-coding",
        {"model_hint": _QWEN, "module": "coding"},
        set(),
        set(),
        {},
        rows,
        eval_ids={_QWEN},
        route_groups=["coding"],
    )
    kinds = [row["kind"] for row in rows if row["severity"] == "FAIL"]
    assert kinds == ["hint_absent", "hint_unregistered"]


def test_bench_coding_think_override_matches_the_production_record() -> None:
    bench = yaml.safe_load(Path("config/bench_workspaces.yaml").read_text(encoding="utf-8"))
    portal = yaml.safe_load(Path("config/portal.yaml").read_text(encoding="utf-8"))
    seat = bench["workspaces"]["bench-engine-coding"]
    production = portal["workspaces"]["auto-coding"]["think_override_reason"]
    assert seat["think"] is True
    assert seat["think_override_reason"] == production
    hunt = bench["workspaces"]["bench-engine-hunt"]["sampling_override"]
    assert hunt == portal["workspaces"]["hunt-reasoning"]["sampling_override"]
    router = bench["workspaces"]["bench-engine-task-router"]["sampling_override"]
    assert router == portal["workspaces"]["task-router"]["sampling_override"]
    assert bench["workspaces"]["bench-engine-task-router"]["ctx_validated"] is True
