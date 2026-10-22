"""Unit tests for scripts/uat_swap.py. No network."""

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx

_SPEC = importlib.util.spec_from_file_location(
    "uat_swap",
    Path(__file__).resolve().parents[2] / "scripts" / "uat_swap.py",
)
swap = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = swap
_SPEC.loader.exec_module(swap)


def _seat(workspace_id, engine, model, size_b, context_limit=8192, size_gib=None):
    return swap.Seat(
        id=workspace_id,
        engine=engine,
        backend=f"{engine}-backend",
        model=model,
        hint=model,
        size_b=size_b,
        quant_bits=4.0,
        context_limit=context_limit,
        size_gib=size_gib,
        size_source="load-plan" if size_gib is not None else "estimated",
    )


def test_param_count_ignores_expert_counts_and_bit_suffixes():
    assert swap._param_count("gemma-4-26b-a4b-it-QAT-4bit") == 26.0
    assert swap._param_count("Qwen3-Coder-30B-A3B-Instruct-4bit") == 30.0
    assert swap._param_count("Qwen3.8-27B-GGUF:Q4_K_M") == 27.0
    assert swap._param_count("kat-coder-v2.5-dev:Q4_K_M-ctx32k") == 0.0
    assert swap._param_count("glm-4.7-flash:Q4_K_M") == 0.0


def test_quant_bits_reads_the_tag_not_the_context():
    assert swap._quant_bits("Qwen3.8-27B-GGUF:Q4_K_M") == 4.0
    assert swap._quant_bits("glm-4.7-flash:Q4_K_M-ctx64k-agentic") == 4.0
    assert swap._quant_bits("hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k") == 8.0
    assert swap._quant_bits("North-Mini-Code-1.0-QAD-GGUF:NVFP4-ctx8k") == 4.0
    assert swap._quant_bits("granite-4.1-8b-mxfp8") == 8.0
    assert swap._quant_bits("some-bf16-model") == 16.0
    assert swap._quant_bits("omnicoder2:9b-q4_k_m-ctx256k") == 4.0


def test_ping_pong_alternates_the_largest_seat_of_each_engine():
    seats = [
        _seat("o35", "omlx", "o-35b", 35),
        _seat("o8", "omlx", "o-8b", 8),
        _seat("a36", "ollama", "a-36b", 36),
        _seat("a9", "ollama", "a-9b", 9),
    ]
    steps, notes = swap.ping_pong_sequence(seats, cycles=2)
    assert [step.workspace_id for step in steps] == ["o35", "a36", "o35", "a36"]
    assert notes == []


def test_ping_pong_notes_an_engine_without_a_sized_seat():
    seats = [_seat("o35", "omlx", "o-35b", 35), _seat("a9", "ollama", "a-9b", 0)]
    steps, notes = swap.ping_pong_sequence(seats, cycles=1)
    assert [step.workspace_id for step in steps] == ["o35"]
    assert notes == ["ollama: no sized seat"]


def test_ladder_ascends_then_descends_on_one_engine():
    seats = [_seat(f"a{size}", "ollama", f"a-{size}b", size) for size in (8, 9, 12, 26, 30, 35, 36)]
    seats.append(_seat("o35", "omlx", "o-35b", 35))
    steps, notes = swap.ladder_sequence(seats, size=3)
    assert notes == []
    assert {step.seat.engine for step in steps} == {"ollama"}
    sizes = [step.seat.rank_gib for step in steps]
    assert sizes[:3] == sorted(sizes[:3])
    assert sizes[3:] == sorted(sizes[3:], reverse=True)
    assert len({step.seat.model for step in steps}) == len(steps)


def test_ladder_keeps_one_seat_per_native_model_and_repeats_only_the_pivot():
    seats = [
        _seat("narrow", "ollama", "same-model", 35, context_limit=8192),
        _seat("wide", "ollama", "same-model", 35, context_limit=262144),
        _seat("small", "ollama", "small-model", 8),
    ]
    steps, _notes = swap.ladder_sequence(seats, size=2)
    assert [step.workspace_id for step in steps] == ["small", "wide", "small"]


def test_incident_ids_resolve_against_the_real_catalog():
    config = swap.load_portal_config()
    seats, unresolved, _skipped, _down = swap.derive_seats(config)
    by_id = {seat.id: seat for seat in seats}
    assert unresolved == []
    for workspace_id in swap.INCIDENT_20261022:
        assert workspace_id in by_id
    assert by_id["auto-coding::cad"].engine == "omlx"
    for workspace_id in swap.INCIDENT_20261022[1:]:
        assert by_id[workspace_id].engine == "ollama"


def test_pinned_seat_can_be_an_extra_id_outside_the_served_set():
    config = swap.load_portal_config()
    seats, _unresolved, _skipped, _down = swap.derive_seats(config, ("task-router",))
    by_id = {seat.id: seat for seat in seats}
    assert by_id["task-router"].engine == "ollama"
    steps, notes = swap.pinned_sequence(seats, "task-router", "test pin")
    assert notes == []
    assert [step.workspace_id for step in steps][-1] == "task-router"
    assert steps[0].seat.engine == "omlx"


def test_config_pinned_workspace_is_the_router_model_seat():
    config = swap.load_portal_config()
    pinned_id, note = swap.config_pinned_workspace(config)
    assert pinned_id == "task-router"
    assert "task-router" in note


def test_pinned_sequence_puts_the_long_request_on_the_other_engine():
    seats = [
        _seat("pinned-ollama", "ollama", "pinned-model", 0, size_gib=5.0),
        _seat("long-omlx", "omlx", "long-model", 0, size_gib=22.0),
        _seat("small-omlx", "omlx", "small-model", 0, size_gib=4.0),
    ]
    steps, notes = swap.pinned_sequence(seats, "pinned-ollama", "test pin")
    assert notes == []
    assert [step.workspace_id for step in steps] == ["long-omlx", "pinned-ollama"]


def test_apply_plan_sizes_prefers_the_guard_projection(monkeypatch):
    seats = [_seat("a", "ollama", "a-14b", 14), _seat("b", "omlx", "b-30b", 30)]
    rows = {
        "models": [
            {"engine": "ollama", "model": "a-14b", "adds_gib": 17.7},
            {"engine": "omlx", "model": "b-30b", "projected_gib": 16.8, "adds_gib": 0},
        ]
    }
    seen = {}

    def fake(url, *, method="GET", api_key="", payload=None):
        seen.update(url=url, method=method, api_key=api_key, payload=payload)
        return rows

    monkeypatch.setattr(swap.host_quiet, "_json_request", fake)
    sized, note = swap.apply_plan_sizes(seats, "http://pipeline:9099", "k")
    assert [seat.size_gib for seat in sized] == [17.7, 16.8]
    assert {seat.size_source for seat in sized} == {"load-plan"}
    assert seen["method"] == "POST"
    assert seen["payload"]["models"][0] == {"engine": "ollama", "model": "a-14b"}
    assert "2/2" in note


def test_apply_plan_sizes_falls_back_and_labels_estimated(monkeypatch):
    seats = [_seat("a", "ollama", "kat-coder-v2.5-dev", 0), _seat("b", "omlx", "b-30b", 30)]

    def fail(*_args, **_kwargs):
        raise OSError("down")

    monkeypatch.setattr(swap.host_quiet, "_json_request", fail)
    sized, note = swap.apply_plan_sizes(seats, "http://pipeline:9099", "k")
    assert sized[0].size_gib is None
    assert sized[0].size_source == "estimated"
    assert sized[1].rank_gib > 0
    assert "estimated" in note


def test_apply_plan_sizes_without_key_sends_nothing(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr(swap.host_quiet, "_json_request", fail)
    seats = [_seat("a", "ollama", "a-14b", 14)]
    sized, note = swap.apply_plan_sizes(seats, "http://pipeline:9099", "")
    assert sized == seats
    assert "PIPELINE_API_KEY" in note


def test_render_plan_labels_the_size_source():
    seat = _seat("a", "ollama", "a-14b", 14, size_gib=17.7)
    sequence = swap.Sequence("incident", "sequential", [swap.Step("a", seat)])
    out = swap.render_plan([seat], [sequence], [], [], [], "sizes: 1/1 from the load-plan")
    assert "~17.7 GiB (load-plan)" in out
    assert "sizes: 1/1 from the load-plan" in out


def test_build_sequences_keeps_the_extra_pinned_seat_out_of_the_ladder():
    seats = [
        _seat("a8", "ollama", "a-8b", 8),
        _seat("a30", "ollama", "a-30b", 30),
        _seat("pin", "ollama", "pinned-model", 0, size_gib=5.0),
    ]
    sequences = swap.build_sequences(["ladder"], seats, 1, 1, "pin", "test pin", ("pin",))
    ladder = next(sequence for sequence in sequences if sequence.name == "ladder")
    assert all(step.workspace_id != "pin" for step in ladder.steps)


def test_fire_step_records_a_passing_shot_without_docker():
    seat = _seat("auto-coding::cad", "omlx", "Qwen3-Coder-30B-A3B-Instruct-4bit", 30, size_gib=16.8)
    step = swap.Step(seat.id, seat)
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            headers={
                "x-portal-route": f"omlx;omlx-coding;{seat.model}",
                "x-correlation-id": "cid",
            },
            json={"choices": [{"message": {"content": "OK"}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    record = swap.fire_step(client, "http://pipeline:9099", "k", step, "incident", 1, container="")
    assert seen["model"] == "auto-coding::cad"
    assert seen["messages"][0]["content"] == swap.ONE_WORD
    assert record["ok"] is True
    assert record["route_model"] == seat.model
    assert record["size_gib"] == 16.8
    assert record["size_source"] == "load-plan"
    assert record["guard_error"] == "disabled"


def test_fire_step_excuses_a_507_body_that_waited():
    seat = _seat("auto-coding::fast-repair", "ollama", "kat-coder-v2.5-dev", 0, size_gib=24.9)
    step = swap.Step(seat.id, seat)

    def handler(_request):
        detail = "Cannot load kat-coder-v2.5-dev: projected memory ... after waiting 118.0s"
        return httpx.Response(507, json={"error": detail})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    record = swap.fire_step(client, "http://pipeline:9099", "k", step, "incident", 3, container="")
    assert record["http_status"] == 507
    assert record["ok"] is True
    assert record["refusal_excused"] is True
    assert "after waiting" in record["reason"]


def test_judge_step_passes_a_200_with_the_expected_model():
    verdict = swap.judge_step(200, "ollama;ollama-coding;m", True, None, "m", [])
    assert verdict["ok"] is True
    assert verdict["refusal_excused"] is False


def test_judge_step_fails_a_200_with_a_fallback_model():
    verdict = swap.judge_step(200, "ollama;ollama-coding;other", True, None, "m", [])
    assert verdict["ok"] is False
    assert "served other" in verdict["reason"]


def test_judge_step_fails_a_200_with_no_answer():
    verdict = swap.judge_step(200, "omlx;omlx-coding;m", False, None, "m", [])
    assert verdict["ok"] is False


def test_judge_step_allows_an_empty_answer_for_a_pressure_request():
    verdict = swap.judge_step(200, "omlx;omlx-coding;m", False, None, "m", [], require_answer=False)
    assert verdict["ok"] is True


def test_judge_step_fails_a_quiet_guard_refusal():
    line = (
        "load_guard: Cannot load m: projected memory 20.0 GiB would exceed host "
        "headroom 5.0 GiB ... with nothing in flight to wait for"
    )
    verdict = swap.judge_step(502, "", False, None, "m", [line])
    assert verdict["ok"] is False
    assert verdict["refusal_excused"] is False


def test_judge_step_excuses_a_refusal_that_waited_for_in_flight_work():
    line = (
        "load_guard: Cannot load m: projected memory 20.0 GiB would exceed host "
        "headroom 5.0 GiB ... after waiting 118.0s"
    )
    verdict = swap.judge_step(507, "", False, None, "m", [line])
    assert verdict["ok"] is True
    assert verdict["refusal_excused"] is True
    assert "after waiting" in verdict["guard_evidence"]


def test_judge_step_excuses_a_swap_that_outlasted_its_wait():
    line = "load_guard: Cannot load m: engine model transition still active after waiting 120.0s"
    verdict = swap.judge_step(502, "", False, None, "m", [line])
    assert verdict["ok"] is True
    assert verdict["refusal_excused"] is True


def test_judge_step_excuses_a_507_body_that_waited_without_docker_logs():
    detail = "Cannot load m: projected memory 20.0 GiB ... after waiting 118.0s"
    verdict = swap.judge_step(507, "", False, None, "m", [], detail)
    assert verdict["ok"] is True
    assert verdict["refusal_excused"] is True


def test_judge_step_fails_a_507_body_that_saw_nothing_in_flight():
    detail = "Cannot load m: projected memory 20.0 GiB ... with nothing in flight to wait for"
    verdict = swap.judge_step(507, "", False, None, "m", [], detail)
    assert verdict["ok"] is False


def test_detail_reads_both_error_shapes():
    assert swap._detail({"error": "x"}) == "x"
    assert swap._detail({"error": {"message": "y"}}) == "y"
    assert swap._detail({"detail": "z"}) == "z"
    assert swap._detail({}) == ""


def test_waiting_for_engine_activity_alone_is_not_proof():
    line = "load_guard: m needs 22.1 GiB, 17.6 available; waiting for engine activity"
    assert swap.refusal_excused([line]) == (False, "")


def test_a_refusal_for_another_model_is_not_evidence():
    line = "load_guard: Cannot load other: projected memory ... after waiting 118.0s"
    assert swap.refusal_excused([line], "m") == (False, "")


def test_request_error_is_a_failure():
    verdict = swap.judge_step(0, "", False, "timed out", "m", [])
    assert verdict["ok"] is False
    assert verdict["reason"] == "timed out"


def test_capture_guard_logs_keeps_only_load_guard_lines(monkeypatch):
    done = SimpleNamespace(
        returncode=0,
        stdout="2026-10-22T14:00:00Z INFO load_guard: unloaded m\n2026-10-22T14:00:01Z INFO other\n",
        stderr="2026-10-22T14:00:02Z WARNING load_guard: could not free m\n",
    )
    monkeypatch.setattr(swap.subprocess, "run", lambda *_args, **_kwargs: done)
    lines, error = swap.capture_guard_logs("portal5-pipeline", datetime.now(UTC), datetime.now(UTC))
    assert error is None
    assert len(lines) == 2
    assert all("load_guard" in line for line in lines)


def test_capture_guard_logs_reports_docker_failure(monkeypatch):
    done = SimpleNamespace(returncode=1, stdout="", stderr="No such container")
    monkeypatch.setattr(swap.subprocess, "run", lambda *_args, **_kwargs: done)
    lines, error = swap.capture_guard_logs("missing", datetime.now(UTC), datetime.now(UTC))
    assert lines == []
    assert error and "No such container" in error


def test_totals_count_excused_refusal_as_pass():
    sequences = [
        {
            "name": "x",
            "steps": [{"ok": True}, {"ok": False}],
        }
    ]
    assert swap.compute_totals(sequences) == {"pass": 1, "fail": 1, "excused": 0, "skip": 0}


def test_dry_run_sends_nothing(monkeypatch, capsys):
    def fail(*_args, **_kwargs):
        raise AssertionError("dry run touched the live stack")

    monkeypatch.setattr(swap, "_pipeline_key", lambda: "")
    monkeypatch.setattr(swap, "make_client", fail)
    monkeypatch.setattr(swap.host_quiet, "start_run", fail)
    assert swap.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "sizes estimated: PIPELINE_API_KEY is not set" in out
    assert "sequence incident (5 steps)" in out
    assert "auto-coding::cad" in out
