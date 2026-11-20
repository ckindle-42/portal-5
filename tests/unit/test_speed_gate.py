"""speed_gate: config-derived rosters, per-cell setup proof, and the compare band.

Resident payloads here are the recorded response shapes of Ollama ``/api/ps`` and
oMLX ``/v1/models/status``; instrument payloads copy the JSON that
``speed_bench.py`` and ``bench_tps.py`` actually write.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from scripts import speed_gate

OLLAMA_PS_EMPTY = {"models": []}
OLLAMA_PS_RESIDENT = {
    "models": [
        {
            "name": "qwen3.8:27b",
            "model": "qwen3.8:27b",
            "size": 24696061952,
            "digest": "6a4b1a7b1a4e",
            "details": {"family": "qwen3", "parameter_size": "27B", "quantization_level": "Q4_K_M"},
        }
    ]
}
OMLX_STATUS_EMPTY = {"models": [], "final_ceiling": 63227387904, "current_model_memory": 0}
OMLX_STATUS_TARGET = {
    "models": [{"id": "model-a", "loaded": True, "estimated_size": 20552089600, "type": "mlx"}],
    "final_ceiling": 63227387904,
    "current_model_memory": 20552089600,
}
OMLX_STATUS_OTHER = {
    "models": [{"id": "other-model", "loaded": True, "estimated_size": 4294967296}],
    "final_ceiling": 63227387904,
    "current_model_memory": 4294967296,
}


class FakeHttp:
    """URL-fragment router; a fragment's value queue is popped until one remains."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.handlers: dict[str, list] = {}

    def on(self, fragment: str, *values):
        self.handlers[fragment] = list(values)
        return self

    def json(self, url, *, method="GET", payload=None, headers=None, timeout=10.0):
        self.calls.append({"url": url, "method": method, "payload": payload})
        for fragment, queue in self.handlers.items():
            if fragment in url:
                value = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected call {method} {url}")

    def urls(self) -> list[str]:
        return [call["url"] for call in self.calls]


def _ctx(tmp_path, http, **overrides) -> speed_gate.Ctx:
    values = {
        "out_dir": tmp_path / "tag",
        "pipeline_url": "http://pipeline",
        "omlx_url": "http://omlx",
        "ollama_url": "http://ollama",
        "pipeline_key": "pipeline-key",
        "omlx_key": "omlx-key",
        "http": http,
        "sleep": lambda _seconds: None,
        "host_quiet": lambda: {"returncode": 0, "stdout": "{}", "stderr": ""},
    }
    values.update(overrides)
    return speed_gate.Ctx(**values)


def _b1_payload(decode: float = 20.0, engine: str = "omlx") -> dict:
    rows = [
        {
            "size_tokens": size,
            "prompt_tokens": size,
            "prefill_tps": 1500.0,
            "decode_tps": decode,
            "load_seconds": 7.72,
            "ttft_s": 0.98 if size > 2000 else 8.1,
            "total_s": 6.5,
            "timing_source": "engine",
            "engine_ok": True,
        }
        for size in (2000, 8000, 32000)
    ]
    return {
        "engine": engine,
        "host": "http://omlx",
        "model": "model-a",
        "results": rows,
        "failures": [],
    }


def _b3_payload(engine_ok: bool = True) -> dict:
    row = {
        "size_tokens": 2000,
        "prompt_tokens": 3243,
        "prefill_tps": 749.19,
        "decode_tps": 65.38,
        "load_seconds": None,
        "ttft_s": 19.24,
        "total_s": 8.99,
        "timing_source": "engine",
        "engine_ok": engine_ok,
    }
    if not engine_ok:
        row.update({"backend": "ollama-general", "served_model": "qwen3.8:27b-ctx32k"})
        return {
            "engine": "pipeline",
            "host": "http://pipeline",
            "model": "auto-coding::heavy",
            "results": [row],
            "failures": ["WRONG ENGINE: seat 'auto-coding::heavy' expected omlx / model-a, got x"],
        }
    row.update({"backend": "omlx-coding", "served_model": "model-a", "served_engine": "omlx"})
    return {
        "engine": "pipeline",
        "host": "http://pipeline",
        "model": "auto-coding::heavy",
        "results": [row],
        "failures": [],
    }


def _b2_payload(match: bool = True) -> dict:
    runs = [
        {"run": 1, "tps": 3.9, "time_to_first_token_s": 51.598, "prompt_tokens": 1201},
        {"run": 2, "tps": 22.7, "time_to_first_token_s": 5.5, "prompt_tokens": 3332},
        {"run": 3, "tps": 22.4, "time_to_first_token_s": 5.1, "prompt_tokens": 3332},
    ]
    return {
        "timestamp": "2026-11-20T15:30:00+00:00",
        "mode": "pipeline",
        "results": [
            {
                "model": "auto-coding",
                "workspace": "auto-coding",
                "label": "pipeline",
                "runs_total": 3,
                "runs_success": 3,
                "avg_tps": 16.3,
                "min_tps": 3.9,
                "max_tps": 22.7,
                "stddev_tps": 10.45,
                "cv": 0.641,
                "avg_ttft_s": 20.73,
                "routed_model": "Qwen3.8-27B-oQ4e-mtp",
                "expected_model_match": match,
                "expected_model_detail": "Ollama:qwen3.8-27b",
                "runs": runs,
            }
        ],
    }


def _write_payload(path: Path, payload: dict) -> int:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return 0


BACKENDS = {
    "backends": [
        {
            "group": "coding",
            "id": "omlx-coding",
            "type": "omlx",
            "models": [{"id": "model-a"}, {"id": "model-b"}],
            "aliases": {"gguf-a": "model-a"},
        },
        {
            "group": "general",
            "id": "ollama-general",
            "type": "ollama",
            "models": [{"id": "ollama-tag"}],
        },
        {
            "group": "reasoning",
            "id": "omlx-reasoning",
            "type": "omlx",
            "models": [{"id": "model-c"}],
            "aliases": {},
        },
    ],
    "workspace_routing": {
        "auto-coding": ["coding"],
        "auto-reasoning": ["reasoning"],
        "auto-general": ["general"],
    },
    "pipeline_bench_skip": [],
}
PORTAL = {
    "workspaces": {
        "auto-coding": {
            "model_hint": "gguf-a",
            "variants": {"heavy": {"model_hint": "model-b"}, "off": {"model_hint": "ollama-tag"}},
        },
        "auto-reasoning": {"model_hint": "model-c"},
        "auto-general": {"model_hint": "model-c"},
    }
}


def test_roster_resolves_aliases_variants_and_reachable_groups():
    roster = speed_gate.build_roster(BACKENDS, PORTAL)

    assert roster["seats"] == {
        "auto-coding": "model-a",
        "auto-coding::heavy": "model-b",
        "auto-reasoning": "model-c",
    }
    assert roster["b1_models"] == ["model-a", "model-b", "model-c"]
    assert roster["b2_workspaces"] == ["auto-coding", "auto-reasoning"]
    assert roster["b3_seats"] == ["auto-coding::heavy"]


def test_roster_excludes_skipped_workspaces():
    backends = {**BACKENDS, "pipeline_bench_skip": ["auto-reasoning"]}

    roster = speed_gate.build_roster(backends, PORTAL)

    assert roster["b2_workspaces"] == ["auto-coding"]


def test_real_config_roster_comes_from_config():
    backends, portal = speed_gate.load_config()
    roster = speed_gate.build_roster(backends, portal)

    assert roster["b1_models"] and roster["b2_workspaces"] and roster["b3_seats"]
    assert set(roster["b2_workspaces"]) <= set(roster["seats"])
    assert all("::" in seat for seat in roster["b3_seats"])


def test_resident_parsers_use_recorded_shapes():
    assert speed_gate.ollama_residents(OLLAMA_PS_EMPTY) == []
    resident = speed_gate.ollama_residents(OLLAMA_PS_RESIDENT)[0]
    assert resident["name"] == "qwen3.8:27b"
    assert resident["size_gib"] == 23.0

    assert speed_gate.omlx_residents(OMLX_STATUS_EMPTY) == []
    loaded = speed_gate.omlx_residents(OMLX_STATUS_TARGET)[0]
    assert loaded["name"] == "model-a"
    assert speed_gate.omlx_residents({"models": [{"id": "idle", "loaded": False}]}) == []


def test_precondition_unloads_reclaims_and_requires_quiet(tmp_path):
    http = (
        FakeHttp()
        .on("/api/ps", OLLAMA_PS_RESIDENT)
        .on("/api/generate", {"model": "qwen3.8:27b", "done": True})
        .on("/admin/reclaim-idle", {"unloads": [{"engine": "ollama"}], "residents": []})
    )
    ctx = _ctx(tmp_path, http)

    record = speed_gate.precondition(ctx)

    assert record["ok"] is True
    assert record["ollama_before"] == ["qwen3.8:27b"]
    assert http.urls()[0].endswith("/api/ps")
    assert http.calls[1]["payload"] == {"model": "qwen3.8:27b", "keep_alive": 0, "stream": False}
    assert http.calls[2]["url"].endswith("/admin/reclaim-idle")
    assert http.calls[2]["payload"] == {"need_gib": 64}


def test_precondition_aborts_when_host_is_not_quiet(tmp_path):
    http = FakeHttp().on("/api/ps", OLLAMA_PS_EMPTY).on("/admin/reclaim-idle", {})
    ctx = _ctx(tmp_path, http, host_quiet=lambda: {"returncode": 1, "stdout": "{}", "stderr": ""})

    record = speed_gate.precondition(ctx)

    assert record["ok"] is False
    assert record["host_quiet"]["returncode"] == 1
    assert any("not quiet" in problem for problem in record["problems"])


def test_precondition_aborts_when_ollama_is_unreadable(tmp_path):
    http = FakeHttp().on("/api/ps", OSError("connection refused"))
    ctx = _ctx(tmp_path, http)

    record = speed_gate.precondition(ctx)

    assert record["ok"] is False
    assert "connection refused" in record["problems"][0]


def test_cell_names_are_filesystem_safe():
    assert speed_gate.cell_name("B3", "auto-coding::heavy") == "b3_auto-coding__heavy.json"
    assert speed_gate.cell_name("B1", "hf.co/Model") == "b1_hf.co-Model.json"


def test_cell_invalid_setup_names_an_ollama_resident_appearing_mid_run(tmp_path):
    http = (
        FakeHttp()
        .on("/api/ps", OLLAMA_PS_EMPTY, OLLAMA_PS_RESIDENT)
        .on("/v1/models/status", OMLX_STATUS_TARGET)
        .on("/admin/reclaim-idle", {})
    )
    ctx = _ctx(
        tmp_path,
        http,
        speed=lambda _ctx, _engine, _target, path: _write_payload(path, _b1_payload()),
    )

    cell = speed_gate.run_cell(ctx, "B1", "model-a", "model-a")

    assert cell["status"] == "invalid_setup"
    assert any("ollama/qwen3.8:27b" in row["detail"] for row in cell["problems"])


def test_cell_reclaims_a_carried_non_target_resident(tmp_path):
    http = (
        FakeHttp()
        .on("/api/ps", OLLAMA_PS_EMPTY)
        .on("/v1/models/status", OMLX_STATUS_OTHER, OMLX_STATUS_TARGET, OMLX_STATUS_TARGET)
        .on("/admin/reclaim-idle", {"unloads": [{"engine": "omlx", "model": "other-model"}]})
    )
    ctx = _ctx(
        tmp_path,
        http,
        speed=lambda _ctx, _engine, _target, path: _write_payload(path, _b1_payload()),
    )

    cell = speed_gate.run_cell(ctx, "B1", "model-a", "model-a")

    assert cell["status"] == "ok"
    assert cell["setup"]["reset"]["ok"] is True
    reclaim = [call for call in http.calls if call["url"].endswith("/admin/reclaim-idle")]
    assert reclaim[0]["payload"] == {"need_gib": 64}


def test_cell_invalid_engine_when_b2_target_is_not_resident_on_omlx(tmp_path):
    http = (
        FakeHttp()
        .on("/api/ps", OLLAMA_PS_EMPTY)
        .on("/v1/models/status", OMLX_STATUS_EMPTY)
        .on("/admin/reclaim-idle", {})
    )
    ctx = _ctx(
        tmp_path, http, bench=lambda _ctx, _ws, path, _log: _write_payload(path, _b2_payload())
    )

    cell = speed_gate.run_cell(ctx, "B2", "auto-coding", "model-a")

    assert cell["status"] == "invalid_engine"
    assert any("not resident on oMLX" in row["detail"] for row in cell["problems"])


def test_cell_invalid_engine_when_b2_routed_model_mismatches(tmp_path):
    http = FakeHttp().on("/api/ps", OLLAMA_PS_EMPTY).on("/v1/models/status", OMLX_STATUS_TARGET)
    ctx = _ctx(
        tmp_path,
        http,
        bench=lambda _ctx, _ws, path, _log: _write_payload(path, _b2_payload(match=False)),
    )

    cell = speed_gate.run_cell(ctx, "B2", "auto-coding", "model-a")

    assert cell["status"] == "invalid_engine"
    assert any("does not match" in row["detail"] for row in cell["problems"])


def test_cell_invalid_engine_on_a_wrong_engine_pipeline_row(tmp_path):
    http = FakeHttp().on("/api/ps", OLLAMA_PS_EMPTY).on("/v1/models/status", OMLX_STATUS_TARGET)
    ctx = _ctx(
        tmp_path,
        http,
        speed=lambda _ctx, _engine, _target, path: _write_payload(path, _b3_payload(False)) or 1,
    )

    cell = speed_gate.run_cell(ctx, "B3", "auto-coding::heavy", "model-a")

    assert cell["status"] == "invalid_engine"
    assert all(row["kind"] != "failed" for row in cell["problems"])


def test_cell_fails_when_the_instrument_reports_no_rows(tmp_path):
    http = FakeHttp().on("/api/ps", OLLAMA_PS_EMPTY).on("/v1/models/status", OMLX_STATUS_TARGET)
    ctx = _ctx(tmp_path, http, speed=lambda _ctx, _engine, _target, _path: 1)

    cell = speed_gate.run_cell(ctx, "B1", "model-a", "model-a")

    assert cell["status"] == "failed"


def test_env_values_are_the_two_named_keys_only(tmp_path, monkeypatch):
    monkeypatch.setattr(speed_gate, "ROOT", tmp_path)
    monkeypatch.delenv("PIPELINE_API_KEY", raising=False)
    monkeypatch.delenv("OMLX_API_KEY", raising=False)
    (tmp_path / ".env").write_text(
        'OTHER_SECRET="leak"\nPIPELINE_API_KEY="pipeline value"\nOMLX_API_KEY=omlx-value\n',
        encoding="utf-8",
    )

    keys = speed_gate.credentials()

    assert set(keys) == {"PIPELINE_API_KEY", "OMLX_API_KEY"}
    assert keys["PIPELINE_API_KEY"] == "pipeline value"
    assert keys["OMLX_API_KEY"] == "omlx-value"


def test_run_aborts_before_any_cell_when_precondition_fails(tmp_path, monkeypatch):
    http = FakeHttp().on("/api/ps", OLLAMA_PS_EMPTY).on("/admin/reclaim-idle", {})
    ctx = _ctx(
        tmp_path / "tag",
        http,
        host_quiet=lambda: {"returncode": 1, "stdout": "{}", "stderr": ""},
    )
    ctx.out_dir = tmp_path / "speed_gate" / "pre"
    monkeypatch.setattr(speed_gate, "load_config", lambda _dir=None: (BACKENDS, PORTAL))
    monkeypatch.setattr(speed_gate, "context", lambda _out, _args: ctx)

    args = speed_gate._parser().parse_args(
        ["run", "pre", "--out-dir", str(tmp_path / "speed_gate")]
    )

    assert speed_gate.cmd_run(args) == 3
    run = json.loads((ctx.out_dir / "run.json").read_text())
    assert run["stopped"] == "precondition"
    assert run["cells"] == []
    assert not list(ctx.out_dir.glob("b[123]_*.json"))


def test_run_writes_one_cell_per_phase_and_exits_zero(tmp_path, monkeypatch):
    backends = {
        "backends": [
            {
                "group": "coding",
                "type": "omlx",
                "models": [{"id": "model-a"}],
                "aliases": {"gguf-a": "model-a"},
            }
        ],
        "workspace_routing": {"auto-coding": ["coding"]},
        "pipeline_bench_skip": [],
    }
    portal = {
        "workspaces": {
            "auto-coding": {
                "model_hint": "gguf-a",
                "variants": {"heavy": {"model_hint": "model-a"}},
            }
        }
    }
    http = (
        FakeHttp()
        .on("/api/ps", OLLAMA_PS_EMPTY)
        .on("/v1/models/status", OMLX_STATUS_TARGET)
        .on("/admin/reclaim-idle", {})
    )
    ctx = _ctx(tmp_path / "tag", http)
    ctx.out_dir = tmp_path / "speed_gate" / "run1"
    payloads = {"B1": _b1_payload(), "B2": _b2_payload(), "B3": _b3_payload()}
    ctx.speed = lambda _ctx, engine, _target, path: _write_payload(
        path, payloads["B1" if engine == "omlx" else "B3"]
    )
    ctx.bench = lambda _ctx, _ws, path, _log: _write_payload(path, payloads["B2"])
    monkeypatch.setattr(speed_gate, "load_config", lambda _dir=None: (backends, portal))
    monkeypatch.setattr(speed_gate, "context", lambda _out, _args: ctx)

    args = speed_gate._parser().parse_args(
        ["run", "run1", "--out-dir", str(tmp_path / "speed_gate")]
    )

    assert speed_gate.cmd_run(args) == 0
    assert sorted(path.name for path in ctx.out_dir.glob("b[123]_*.json")) == [
        "b1_model-a.json",
        "b2_auto-coding.json",
        "b3_auto-coding__heavy.json",
    ]
    run = json.loads((ctx.out_dir / "run.json").read_text())
    assert run["ok"] is True
    assert run["counts"]["ok"] == 3


def _cell(phase: str, rows: list[dict], status: str = "ok") -> dict:
    return {
        "phase": phase,
        "target": "x",
        "model": "model-a",
        "status": status,
        "problems": [{"kind": "setup", "detail": "ollama/extra resident after cell"}]
        if status != "ok"
        else [],
        "instrument": {"results": rows},
        "setup": {},
    }


def _b1_row(size: int, decode: float = 20.0, ttft: float = 1.0) -> dict:
    return {
        "size_tokens": size,
        "decode_tps": decode,
        "prefill_tps": 1500.0,
        "ttft_s": ttft,
    }


def _compare(target: dict, baselines: list[dict]) -> tuple[str, int]:
    lines, code = speed_gate.compare_tags(target, baselines)
    return "\n".join(lines), code


def test_compare_bands_against_the_worse_of_two_baselines():
    target = {"b1_model-a": _cell("B1", [_b1_row(8000, decode=17.0)])}
    baselines = [
        {"b1_model-a": _cell("B1", [_b1_row(8000, decode=20.0)])},
        {"b1_model-a": _cell("B1", [_b1_row(8000, decode=22.0)])},
    ]

    text, code = _compare(target, baselines)

    assert code == 1
    assert "REGRESSIONS (1):" in text
    assert "band=2.00" in text


def test_compare_uses_ten_percent_for_a_single_baseline():
    within = {"b1_model-a": _cell("B1", [_b1_row(8000, decode=18.5)])}
    worse = {"b1_model-a": _cell("B1", [_b1_row(8000, decode=17.5)])}
    baseline = [{"b1_model-a": _cell("B1", [_b1_row(8000, decode=20.0)])}]

    assert _compare(within, baseline)[1] == 0
    assert _compare(worse, baseline)[1] == 1


def test_compare_never_bands_an_invalid_target_cell():
    target = {"b1_model-a": _cell("B1", [_b1_row(8000, decode=1.0)], status="invalid_setup")}
    baseline = [{"b1_model-a": _cell("B1", [_b1_row(8000, decode=20.0)])}]

    text, code = _compare(target, baseline)

    assert code == 1
    assert "INVALID (1):" in text
    assert "REGRESSIONS (0):" in text
    assert "ollama/extra resident" in text


def test_compare_reports_an_invalid_baseline_and_does_not_band(tmp_path):
    target = {"b1_model-a": _cell("B1", [_b1_row(8000, decode=1.0)])}
    baseline = [{"b1_model-a": _cell("B1", [_b1_row(8000, decode=20.0)], status="invalid_engine")}]

    text, code = _compare(target, baseline)

    assert code == 1
    assert "baseline b1_model-a: invalid_engine" in text
    assert "REGRESSIONS (0):" in text


def test_compare_skips_first_size_ttft_as_load_dominated():
    target = {"b1_model-a": _cell("B1", [_b1_row(2000, decode=20.0, ttft=99.0)])}
    baseline = [{"b1_model-a": _cell("B1", [_b1_row(2000, decode=20.0, ttft=1.0)])}]

    text, _code = _compare(target, baseline)

    assert "ttft_s" not in text


def _b2_compare_row(avg_tps: float, cv: float, warm_ttft: float) -> dict:
    return {
        "workspace": "auto-coding",
        "avg_tps": avg_tps,
        "cv": cv,
        "runs": [
            {"time_to_first_token_s": 51.6},
            {"time_to_first_token_s": warm_ttft},
            {"time_to_first_token_s": warm_ttft},
        ],
    }


def test_compare_b2_warm_ttft_skips_the_cold_first_run():
    target = {"b2_auto-coding": _cell("B2", [_b2_compare_row(16.0, 0.1, 20.0)])}
    baseline = {"b2_auto-coding": _cell("B2", [_b2_compare_row(16.0, 0.1, 5.0)])}

    text, code = _compare(target, [baseline])

    assert code == 1
    assert "warm_ttft_s" in text
    assert "pre=[5.0] post=20.00 band=0.50" in text


def test_compare_b2_cv_widens_the_avg_tps_band():
    target = {"b2_auto-coding": _cell("B2", [_b2_compare_row(9.0, 0.1, 5.0)])}
    noisy = {"b2_auto-coding": _cell("B2", [_b2_compare_row(16.0, 0.5, 5.0)])}
    steady = {"b2_auto-coding": _cell("B2", [_b2_compare_row(16.0, 0.1, 5.0)])}

    assert _compare(target, [noisy])[0].count("avg_tps") == 0
    assert "avg_tps" in _compare(target, [steady])[0]


def test_load_tag_uses_the_run_manifest_and_ignores_stale_cells(tmp_path):
    tag = tmp_path / "run1"
    tag.mkdir()
    current = _cell("B1", [_b1_row(8000)])
    stale = _cell("B1", [_b1_row(8000, decode=1.0)])
    (tag / "b1_model-a.json").write_text(json.dumps(current), encoding="utf-8")
    (tag / "b1_retired-model.json").write_text(json.dumps(stale), encoding="utf-8")
    manifest = {"tag": "run1", "cells": [{"file": "b1_model-a.json", "status": "ok"}]}
    (tag / "run.json").write_text(json.dumps(manifest), encoding="utf-8")

    cells = speed_gate.load_tag(tmp_path, "run1")

    assert list(cells) == ["b1_model-a"]


def test_cell_fails_when_the_instrument_writes_no_report(tmp_path):
    http = FakeHttp().on("/api/ps", OLLAMA_PS_EMPTY).on("/v1/models/status", OMLX_STATUS_TARGET)
    ctx = _ctx(tmp_path, http, speed=lambda _ctx, _engine, _target, _path: 0)

    cell = speed_gate.run_cell(ctx, "B1", "model-a", "model-a")

    assert cell["status"] == "failed"


def test_compare_reports_missing_and_dropped_cells():
    target = {"b1_model-a": _cell("B1", [_b1_row(8000)])}
    baseline = [{"b1_model-b": _cell("B1", [_b1_row(8000)])}]

    text, code = _compare(target, baseline)

    assert code == 0
    assert "NO BASELINE (1):" in text
    assert "b1_model-a" in text
    assert "MISSING FROM TARGET (1):" in text
    assert "b1_model-b" in text


def test_compare_returns_two_when_a_tag_has_no_cells(tmp_path):
    args = speed_gate._parser().parse_args(
        ["compare", "missing", "--against", "baseline", "--out-dir", str(tmp_path)]
    )

    assert speed_gate.cmd_compare(args) == 2


@pytest.mark.parametrize("bad", ["", "0", "2000,nope"])
def test_size_parser_rejects_bad_input(bad):
    with pytest.raises(argparse.ArgumentTypeError):
        speed_gate._sizes(bad)


def test_roster_omits_seats_in_disabled_modules():
    portal = {
        **PORTAL,
        "modules": {"security": {"enabled": True}, "security_redteam": {"enabled": False}},
        "workspaces": {
            **PORTAL["workspaces"],
            "auto-security": {
                "module": "security",
                "model_hint": "model-c",
                "variants": {
                    "redteam": {"model_hint": "model-c", "module": "security_redteam"},
                    "blue": {"model_hint": "model-c"},
                },
            },
        },
    }
    backends = {
        **BACKENDS,
        "workspace_routing": {**BACKENDS["workspace_routing"], "auto-security": ["reasoning"]},
    }

    roster = speed_gate.build_roster(backends, portal)

    assert "auto-security::blue" in roster["b3_seats"]
    assert "auto-security::redteam" not in roster["b3_seats"]
    assert "auto-security::redteam" in roster["skipped_seats"]


def test_real_config_roster_skips_the_disabled_redteam_variants():
    backends, portal = speed_gate.load_config()
    roster = speed_gate.build_roster(backends, portal)

    assert "auto-security::redteam" in roster["skipped_seats"]
    assert "auto-security::redteam" not in roster["b3_seats"]
    assert "auto-security::redteam-deep" not in roster["b3_seats"]
    assert "auto-security::purpleteam-exec" not in roster["b3_seats"]


def test_b3_skipped_context_and_multi_hop_rows_are_notes_not_engine_failures():
    payload = {
        "results": [
            {"size_tokens": 2000, "seat_status": "ok", "engine_ok": True},
            {"size_tokens": 8000, "seat_status": "skipped_context", "engine_ok": None},
            {"size_tokens": 32000, "seat_status": "multi_hop", "engine_ok": None},
        ],
        "failures": [],
    }

    problems = speed_gate._engine_problems("B3", "auto-security::purpleteam", payload, {}, 0)

    assert [problem["kind"] for problem in problems] == ["note", "note"]
    assert speed_gate._status(problems) == "ok"


def test_b3_reasoning_only_row_is_a_note_and_stays_in_the_comparison():
    payload = {
        "results": [
            {
                "size_tokens": 2000,
                "seat_status": "reasoning_only",
                "engine_ok": None,
                "decode_tps": 92.8,
                "completion_tokens": 128,
            }
        ],
        "failures": [],
    }

    problems = speed_gate._engine_problems("B3", "auto-security::pentest", payload, {}, 0)

    assert [problem["kind"] for problem in problems] == ["note"]
    assert "reasoning_only" in problems[0]["detail"]
    assert speed_gate._status(problems) == "ok"
    cell = _cell("B3", payload["results"])
    assert speed_gate._cell_rows(cell)["2000"]["decode_tps"] == 92.8


def test_compare_ignores_skipped_rows():
    row = {**_b1_row(8000), "seat_status": "skipped_context"}
    cell = _cell("B3", [row])

    assert speed_gate._cell_rows(cell) == {}


def test_run_phases_restricts_the_cells(tmp_path, monkeypatch):
    backends = {
        "backends": [
            {
                "group": "coding",
                "type": "omlx",
                "models": [{"id": "model-a"}],
                "aliases": {"gguf-a": "model-a"},
            }
        ],
        "workspace_routing": {"auto-coding": ["coding"]},
        "pipeline_bench_skip": [],
    }
    portal = {
        "workspaces": {
            "auto-coding": {
                "model_hint": "gguf-a",
                "variants": {"heavy": {"model_hint": "model-a"}},
            }
        }
    }
    http = (
        FakeHttp()
        .on("/api/ps", OLLAMA_PS_EMPTY)
        .on("/v1/models/status", OMLX_STATUS_TARGET)
        .on("/admin/reclaim-idle", {})
    )
    ctx = _ctx(tmp_path / "tag", http)
    ctx.out_dir = tmp_path / "speed_gate" / "b3only"
    ctx.speed = lambda _ctx, _engine, _target, path: _write_payload(path, _b3_payload())
    monkeypatch.setattr(speed_gate, "load_config", lambda _dir=None: (backends, portal))
    monkeypatch.setattr(speed_gate, "context", lambda _out, _args: ctx)

    args = speed_gate._parser().parse_args(
        ["run", "b3only", "--out-dir", str(tmp_path / "speed_gate"), "--phases", "B3"]
    )

    assert speed_gate.cmd_run(args) == 0
    assert [path.name for path in ctx.out_dir.glob("b[123]_*.json")] == [
        "b3_auto-coding__heavy.json"
    ]
