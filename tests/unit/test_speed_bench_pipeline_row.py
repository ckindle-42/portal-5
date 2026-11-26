"""speed_bench pipeline rows name the serving model, cold load, and intended engine.

The 2026-11-20 oMLX 0.8.0 gate produced rows whose slowness was a hidden model
load (``model_load_duration``) or a silent fallback onto Ollama instead of oMLX.
Pipeline rows must record backend, served_model, load_seconds, completion_tokens,
and reject any row that did not hit the seat's intended backend and model.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.config import load_persona_map, load_portal_config
from scripts import speed_bench
from scripts.speed_bench import (
    check_pipeline_engine,
    main,
    parse_sse_timings,
    pipeline_metrics,
    request_pipeline,
    resolve_intended_seat,
    run_bench,
)


def _sse_lines(model: str = "Huihui-Qwen3.6-27B-abliterated-MLX-4bit") -> list[bytes]:
    return [
        f'data: {{"model": "{model}", "choices": [{{"delta": {{"content": "hi"}}}}]}}\n\n'.encode(),
        b'data: {"portal_timings": {"answer_tps": 5.1, "ttft_s": 1.0, '
        b'"total_s": 25.9, "timing_source": "engine"}}\n\n',
        b'data: {"usage": {"prompt_tokens": 7670, "completion_tokens": 128, '
        b'"model_load_duration": 11.42}}\n\n',
        b"data: [DONE]\n\n",
    ]


def test_pipeline_row_carries_served_model_load_and_completion():
    timings, usage, served, _content = parse_sse_timings(_sse_lines())
    row = pipeline_metrics(
        timings,
        usage,
        served,
        route="auto-coding::uncensored-agentic;omlx-coding;Huihui-Qwen3.6-27B-abliterated-MLX-4bit",
    )
    assert row["served_model"] == "Huihui-Qwen3.6-27B-abliterated-MLX-4bit"
    assert row["response_model"] == "Huihui-Qwen3.6-27B-abliterated-MLX-4bit"
    assert row["load_seconds"] == 11.42
    assert row["completion_tokens"] == 128
    assert row["decode_tps"] == 5.1
    assert row["backend"] == "omlx-coding"


def test_pipeline_row_without_usage_leaves_the_new_fields_none():
    timings, usage, served, _content = parse_sse_timings(
        [b'data: {"portal_timings": {}}\n\n', b"data: [DONE]\n\n"]
    )
    row = pipeline_metrics(timings, usage, served)
    assert served is None
    assert row["served_model"] is None
    assert row["load_seconds"] is None
    assert row["completion_tokens"] is None


def test_pipeline_row_unifies_route_header_and_sse_model():
    timings, usage, served, _content = parse_sse_timings(_sse_lines())
    row = pipeline_metrics(
        timings,
        usage,
        served,
        route="auto-coding::uncensored-agentic;omlx-coding;Huihui-Qwen3.6-27B-abliterated-MLX-4bit",
    )
    assert row["backend"] == "omlx-coding"
    assert row["served_model"] == "Huihui-Qwen3.6-27B-abliterated-MLX-4bit"
    assert row["load_seconds"] == 11.42
    assert row["completion_tokens"] == 128

    fallback_row = pipeline_metrics(
        timings,
        usage,
        None,
        route="auto-daily::gemma-fast;omlx-general;gemma-4-26b-a4b-it-QAT-4bit",
    )
    assert fallback_row["backend"] == "omlx-general"
    assert fallback_row["served_model"] == "gemma-4-26b-a4b-it-QAT-4bit"


def test_request_pipeline_sends_no_tools_and_reads_route_header(monkeypatch):
    captured: dict[str, object] = {}

    class _Resp(io.BytesIO):
        headers = {
            "x-portal-route": "auto-daily::gemma-fast;omlx-general;gemma-4-26b-a4b-it-QAT-4bit"
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def _fake_post(url, payload, timeout, headers=None):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return _Resp(b"".join(_sse_lines("gemma-4-26b-a4b-it-QAT-4bit")))

    monkeypatch.setattr(speed_bench, "_post", _fake_post)
    timings, usage, served, route, content = request_pipeline(
        "http://localhost:9099", "auto-daily::gemma-fast", "hi", api_key="k", no_tools=True
    )
    assert captured["payload"]["portal_no_tools"] is True  # type: ignore[index]
    assert served == "gemma-4-26b-a4b-it-QAT-4bit"
    assert route == "auto-daily::gemma-fast;omlx-general;gemma-4-26b-a4b-it-QAT-4bit"
    assert timings["answer_tps"] == 5.1
    assert usage["completion_tokens"] == 128


def _synthetic_configs(tmp_path: Path):
    portal_yaml = tmp_path / "portal.yaml"
    portal_yaml.write_text(
        """
workspaces:
  auto-daily:
    module: general
    name: Daily
    description: Daily
    model_hint: gemma4:26b-a4b-it-qat-ctx8k
    context_limit: 8192
    variants:
      fast:
        model_hint: gemma4:26b-a4b-it-qat-ctx32k
  auto-chain:
    module: general
    name: Chain
    description: Chain
    model_hint: gemma4:26b-a4b-it-qat-ctx8k
    chain:
    - model: granite4.1:8b-ctx8k
      label: hop
      system: You are a hop.
      user_template: '{hop_0}'
  ollama-only:
    module: general
    name: Ollama Only
    description: Unaliased seat
    model_hint: granite4.1:8b-ctx8k
mcp_fleet: []
""",
        encoding="utf-8",
    )
    (tmp_path / "bench_workspaces.yaml").write_text(
        """
workspaces:
  bench-omlx:
    module: eval
    name: Bench oMLX
    description: Bench
    model_hint: gemma4:26b-a4b-it-qat-ctx32k
""",
        encoding="utf-8",
    )
    backends_yaml = tmp_path / "backends.yaml"
    backends_yaml.write_text(
        """
backends:
- id: omlx-general
  group: general
  type: omlx
  url: http://localhost:8085
  priority: 10
  models:
  - id: gemma-4-26b-a4b-it-QAT-4bit
  aliases:
    gemma4:26b-a4b-it-qat-ctx8k: gemma-4-26b-a4b-it-QAT-4bit
    gemma4:26b-a4b-it-qat-ctx32k: gemma-4-26b-a4b-it-QAT-4bit
- id: ollama-general
  group: general
  type: ollama
  url: http://localhost:11434
  priority: 0
  models:
  - id: gemma4:26b-a4b-it-qat-ctx8k
  - id: gemma4:26b-a4b-it-qat-ctx32k
  - id: granite4.1:8b-ctx8k
workspace_routing:
  auto-daily: [general]
  auto-chain: [general]
  ollama-only: [general]
  bench-omlx: [general]
""",
        encoding="utf-8",
    )
    reg = BackendRegistry(str(backends_yaml))
    cfg = load_portal_config(portal_yaml, _force_reload=True, include_bench=True)
    return reg, cfg


def test_resolve_intended_seat_uses_routing_and_aliases(tmp_path: Path):
    reg, cfg = _synthetic_configs(tmp_path)
    personas = {
        "fast-persona": SimpleNamespace(
            workspace_model="auto-daily", variant="fast", model_pin=None
        )
    }
    assert resolve_intended_seat(
        "auto-daily", registry=reg, portal_config=cfg, personas=personas
    ) == ("omlx-general", "omlx", "gemma-4-26b-a4b-it-QAT-4bit")
    assert resolve_intended_seat(
        "auto-daily::fast", registry=reg, portal_config=cfg, personas=personas
    ) == ("omlx-general", "omlx", "gemma-4-26b-a4b-it-QAT-4bit")
    assert resolve_intended_seat(
        "bench-omlx", registry=reg, portal_config=cfg, personas=personas
    ) == ("omlx-general", "omlx", "gemma-4-26b-a4b-it-QAT-4bit")
    assert resolve_intended_seat(
        "fast-persona", registry=reg, portal_config=cfg, personas=personas
    ) == ("omlx-general", "omlx", "gemma-4-26b-a4b-it-QAT-4bit")
    assert resolve_intended_seat(
        "ollama-only", registry=reg, portal_config=cfg, personas=personas
    ) == ("ollama-general", "ollama", "granite4.1:8b-ctx8k")
    assert (
        resolve_intended_seat("missing-seat", registry=reg, portal_config=cfg, personas=personas)
        is None
    )


def test_resolve_intended_seat_matches_real_repo_config():
    reg = BackendRegistry()
    cfg = load_portal_config(include_bench=True)
    personas = load_persona_map(include_bench=True)
    assert resolve_intended_seat(
        "auto-coding::uncensored-agentic", registry=reg, portal_config=cfg, personas=personas
    ) == ("omlx-coding", "omlx", "Huihui-Qwen3.6-27B-abliterated-MLX-4bit")
    assert resolve_intended_seat(
        "security-reviewer", registry=reg, portal_config=cfg, personas=personas
    ) == ("omlx-general", "omlx", "Inkling-2-Mini-oQ4e-mtp")


def test_run_bench_pipeline_accepts_intended_and_rejects_wrong_engine(
    tmp_path: Path, monkeypatch, capsys
):
    reg, cfg = _synthetic_configs(tmp_path)
    out_ok = tmp_path / "ok.json"

    monkeypatch.setattr(
        speed_bench,
        "request_pipeline",
        lambda *_a, **_kw: (
            {"answer_tps": 42.0, "prefill_s": 1.0, "ttft_s": 0.5, "total_s": 3.5},
            {"prompt_tokens": 2000, "completion_tokens": 128, "model_load_duration": 0.0},
            "gemma-4-26b-a4b-it-QAT-4bit",
            "auto-daily::fast;omlx-general;gemma-4-26b-a4b-it-QAT-4bit",
            "measured answer",
        ),
    )
    rc_ok = run_bench(
        "pipeline",
        "http://localhost:9099",
        "auto-daily::fast",
        [2000],
        out=str(out_ok),
        registry=reg,
        portal_config=cfg,
        personas={},
    )
    assert rc_ok == 0
    ok_data = json.loads(out_ok.read_text(encoding="utf-8"))
    assert ok_data["results"][0]["engine_ok"] is True
    assert ok_data["results"][0]["served_engine"] == "omlx"
    assert "WRONG ENGINE" not in capsys.readouterr().err

    out_bad = tmp_path / "bad.json"
    monkeypatch.setattr(
        speed_bench,
        "request_pipeline",
        lambda *_a, **_kw: (
            {"answer_tps": 12.0, "prefill_s": 2.0, "ttft_s": 2.1, "total_s": 12.0},
            {"prompt_tokens": 2000, "completion_tokens": 128},
            "gemma4:26b-a4b-it-qat-ctx32k",
            "auto-daily::fast;ollama-general;gemma4:26b-a4b-it-qat-ctx32k",
            "measured answer",
        ),
    )
    rc_bad = run_bench(
        "pipeline",
        "http://localhost:9099",
        "auto-daily::fast",
        [2000],
        out=str(out_bad),
        registry=reg,
        portal_config=cfg,
        personas={},
    )
    assert rc_bad == 1
    captured = capsys.readouterr()
    assert "WRONG ENGINE" in captured.err
    bad_data = json.loads(out_bad.read_text(encoding="utf-8"))
    assert len(bad_data["results"]) == 1
    assert bad_data["results"][0]["engine_ok"] is False
    assert bad_data["results"][0]["served_engine"] == "ollama"
    assert any("WRONG ENGINE" in msg for msg in bad_data["failures"])


def test_check_pipeline_engine_catches_model_mismatch_and_missing_route():
    row_model_mismatch = {
        "backend": "omlx-general",
        "served_model": "wrong-model",
    }
    msg = check_pipeline_engine(
        row_model_mismatch,
        "auto-daily",
        intended=("omlx-general", "omlx", "gemma-4-26b-a4b-it-QAT-4bit"),
        backend_types={"omlx-general": "omlx"},
    )
    assert msg is not None and msg.startswith("WRONG ENGINE")
    assert row_model_mismatch["engine_ok"] is False
    assert row_model_mismatch["served_engine"] == "omlx"

    row_no_route = {"backend": None, "served_model": "gemma-4-26b-a4b-it-QAT-4bit"}
    msg2 = check_pipeline_engine(
        row_no_route,
        "auto-daily",
        intended=("omlx-general", "omlx", "gemma-4-26b-a4b-it-QAT-4bit"),
        backend_types={"omlx-general": "omlx"},
    )
    assert msg2 is not None and msg2.startswith("WRONG ENGINE")
    assert row_no_route["engine_ok"] is False
    assert row_no_route["served_engine"] == "unknown"


@pytest.mark.parametrize("engine", ["omlx", "ollama"])
def test_direct_engines_are_engine_ok_by_construction(engine: str, tmp_path: Path, monkeypatch):
    out = tmp_path / f"{engine}.json"
    if engine == "omlx":
        monkeypatch.setattr(
            speed_bench,
            "request_omlx",
            lambda *_a, **_kw: {
                "usage": {
                    "prompt_tokens": 2000,
                    "completion_tokens": 128,
                    "prompt_eval_duration": 0.5,
                    "generation_duration": 2.0,
                }
            },
        )
    else:
        monkeypatch.setattr(
            speed_bench,
            "request_chat",
            lambda *_a, **_kw: {
                "prompt_eval_count": 2000,
                "prompt_eval_duration": 500_000_000,
                "eval_count": 128,
                "eval_duration": 2_000_000_000,
                "load_duration": 0,
            },
        )
    rc = main(["--engine", engine, "--model", "some-model", "--sizes", "2000", "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["results"][0]["engine_ok"] is True


def test_pipeline_route_model_wins_over_the_echoed_workspace_id():
    lines = [
        b'data: {"model": "auto-security::pentest", "choices": [{"delta": {"content": "x"}}]}\n\n',
        b'data: {"portal_timings": {"answer_tps": 1.0}}\n\n',
        b"data: [DONE]\n\n",
    ]
    timings, usage, served, content = parse_sse_timings(lines)
    row = pipeline_metrics(
        timings,
        usage,
        served,
        route="auto-security::pentest;omlx-security;Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit",
        content=content,
    )
    assert row["served_model"] == "Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit"
    assert row["response_model"] == "auto-security::pentest"
    assert row["content"] == "x"


def test_request_pipeline_sends_the_intended_backend_as_an_eval_pin(monkeypatch):
    captured: dict[str, object] = {}

    class _Resp(io.BytesIO):
        headers = {"x-portal-route": "auto-daily::fast;omlx-general;model"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def _fake_post(url, payload, timeout, headers=None):
        captured["payload"] = payload
        return _Resp(b"".join(_sse_lines("model")))

    monkeypatch.setattr(speed_bench, "_post", _fake_post)
    request_pipeline("http://localhost:9099", "auto-daily::fast", "hi", backend_pin="omlx-general")
    assert captured["payload"]["portal_backend"] == "omlx-general"  # type: ignore[index]


def test_run_bench_skips_sizes_beyond_the_seat_context(tmp_path: Path, monkeypatch, capsys):
    reg, cfg = _synthetic_configs(tmp_path)
    measured: list[int] = []

    def _fake_request(*_args, **_kwargs):
        measured.append(len(_args[2]))
        return (
            {"answer_tps": 42.0, "ttft_s": 0.5, "total_s": 3.5},
            {"prompt_tokens": 2000, "completion_tokens": 128},
            "gemma-4-26b-a4b-it-QAT-4bit",
            "auto-daily::fast;omlx-general;gemma-4-26b-a4b-it-QAT-4bit",
            "ok",
        )

    monkeypatch.setattr(speed_bench, "request_pipeline", _fake_request)
    out = tmp_path / "skip.json"
    rc = run_bench(
        "pipeline",
        "http://localhost:9099",
        "auto-daily::fast",
        [2000, 8192, 32000],
        out=str(out),
        registry=reg,
        portal_config=cfg,
        personas={},
    )

    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [row["size_tokens"] for row in data["results"]] == [2000]
    assert data["failures"] == []
    assert any("SKIP size 8192" in note for note in data["notes"])
    assert any("SKIP size 32000" in note for note in data["notes"])
    assert len(measured) == 1
    assert "SKIP" in capsys.readouterr().err


def test_pipeline_context_refusal_is_reported_not_wrong_engine(tmp_path: Path, monkeypatch):
    reg, cfg = _synthetic_configs(tmp_path)
    monkeypatch.setattr(
        speed_bench,
        "request_pipeline",
        lambda *_a, **_kw: (
            {"timing_source": "measured"},
            {"prompt_tokens": 0, "completion_tokens": 0},
            "auto-daily::fast",
            "auto-daily::fast;omlx-general;model",
            "The conversation exceeds this workspace's context (about 10,672 tokens)",
        ),
    )
    out = tmp_path / "refused.json"
    rc = run_bench(
        "pipeline",
        "http://localhost:9099",
        "auto-daily::fast",
        [2000],
        out=str(out),
        registry=reg,
        portal_config=cfg,
        personas={},
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert data["results"][0]["seat_status"] == "skipped_context"
    assert data["results"][0]["engine_ok"] is None
    assert data["failures"] == []
    assert any("SKIP" in note for note in data["notes"])


def test_pipeline_no_answer_is_reported_as_such(tmp_path: Path, monkeypatch):
    reg, cfg = _synthetic_configs(tmp_path)
    monkeypatch.setattr(
        speed_bench,
        "request_pipeline",
        lambda *_a, **_kw: (
            {"answer_tps": 0.0, "ttft_s": 1.0, "total_s": 9.0},
            {"prompt_tokens": 2000, "completion_tokens": 128},
            "model",
            "auto-daily::fast;omlx-general;model",
            "⚠️ The model did not produce an answer. Please retry.",
        ),
    )
    out = tmp_path / "noanswer.json"
    rc = run_bench(
        "pipeline",
        "http://localhost:9099",
        "auto-daily::fast",
        [2000],
        out=str(out),
        registry=reg,
        portal_config=cfg,
        personas={},
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 1
    assert data["results"][0]["seat_status"] == "no_answer"
    assert data["results"][0]["engine_ok"] is None
    assert any("NO ANSWER" in failure for failure in data["failures"])
    assert not any("WRONG ENGINE" in failure for failure in data["failures"])


def test_reasoning_only_budget_row_is_a_decode_sample_not_a_failure(tmp_path: Path, monkeypatch):
    """pentest/deep spent max_tokens=128 entirely on reasoning: decode is still measured."""
    reg, cfg = _synthetic_configs(tmp_path)
    monkeypatch.setattr(
        speed_bench,
        "request_pipeline",
        lambda *_a, **_kw: (
            {
                "answer_tps": None,
                "ttft_s": 3.10,
                "total_s": 4.48,
                "reasoning_tokens": 129,
                "completion_tokens": 128,
                "timing_source": "engine",
            },
            {"prompt_tokens": 3310, "completion_tokens": 128},
            "model",
            "auto-daily::fast;omlx-general;model",
            "⚠️ The model did not produce an answer. Please retry.",
        ),
    )
    out = tmp_path / "reasoning.json"
    rc = run_bench(
        "pipeline",
        "http://localhost:9099",
        "auto-daily::fast",
        [2000],
        out=str(out),
        registry=reg,
        portal_config=cfg,
        personas={},
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert data["results"][0]["seat_status"] == "reasoning_only"
    assert data["results"][0]["engine_ok"] is None
    assert data["failures"] == []
    assert any("output budget as reasoning" in note for note in data["notes"])
    assert data["results"][0]["decode_tps"] == pytest.approx(128 / (4.48 - 3.10))


def test_seat_context_limit_and_multi_hop(tmp_path: Path):
    _reg, cfg = _synthetic_configs(tmp_path)
    assert speed_bench.seat_context_limit("auto-daily", portal_config=cfg, personas={}) == 8192
    assert speed_bench.seat_is_multi_hop("auto-daily", portal_config=cfg, personas={}) is False
    assert speed_bench.seat_is_multi_hop("auto-chain", portal_config=cfg, personas={}) is True


def test_intended_engine_ignores_transient_backend_health(tmp_path: Path, monkeypatch):
    """A failed health probe must not reclassify an oMLX seat as Ollama."""
    reg, cfg = _synthetic_configs(tmp_path)
    omlx = next(b for b in reg.list_backends() if b.id == "omlx-general")
    ollama = next(b for b in reg.list_backends() if b.id == "ollama-general")
    monkeypatch.setattr(reg, "get_backend_candidates", lambda _ws: [ollama])

    assert resolve_intended_seat("auto-daily", registry=reg, portal_config=cfg, personas={}) == (
        omlx.id,
        "omlx",
        "gemma-4-26b-a4b-it-QAT-4bit",
    )


def test_reasoning_only_row_reports_raw_decode_instead_of_zero():
    row = pipeline_metrics(
        {"answer_tps": 0.0, "ttft_s": 1.0, "total_s": 9.0, "timing_source": "engine"},
        {"prompt_tokens": 2000, "completion_tokens": 128},
        "model",
        route="auto-daily::fast;omlx-general;model",
    )
    assert row["answer_tps"] == 0.0
    assert row["raw_decode_tps"] == 16.0
    assert row["decode_tps"] == 16.0


def test_row_without_a_served_model_is_reported_as_such(tmp_path: Path, monkeypatch):
    reg, cfg = _synthetic_configs(tmp_path)
    monkeypatch.setattr(
        speed_bench,
        "request_pipeline",
        lambda *_a, **_kw: (
            {"answer_tps": 12.0, "ttft_s": 1.0, "total_s": 5.0},
            {"prompt_tokens": 2000, "completion_tokens": 64},
            "auto-daily::fast",
            "",
            "an answer",
        ),
    )
    out = tmp_path / "nomodel.json"
    rc = run_bench(
        "pipeline",
        "http://localhost:9099",
        "auto-daily::fast",
        [2000],
        out=str(out),
        registry=reg,
        portal_config=cfg,
        personas={},
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 1
    assert data["results"][0]["seat_status"] == "no_served_model"
    assert any("NO SERVED MODEL" in failure for failure in data["failures"])
    assert not any("WRONG ENGINE" in failure for failure in data["failures"])


def test_run_bench_creates_missing_output_dirs(tmp_path: Path, monkeypatch):
    out = tmp_path / "new_subdir" / "off_rep1.json"
    assert not out.parent.exists()
    monkeypatch.setattr(
        speed_bench,
        "_measure",
        lambda *_a, **_kw: {
            "prompt_tokens": 2000,
            "prefill_tps": 1500.0,
            "decode_tps": 40.0,
            "load_seconds": 0.5,
            "ttft_s": 1.0,
            "timing_source": "engine",
        },
    )
    rc = run_bench("omlx", "http://localhost:8085", "Qwen3.8-27B-4bit", [2000], out=str(out))
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["failures"] == []
    assert payload["results"][0]["size_tokens"] == 2000
