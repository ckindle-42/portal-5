"""The OWUI hunt chat proof grades the product path from stubbed HTTP evidence only."""

from __future__ import annotations

import json

from scripts.proofs import owui_hunt_chat as proof

JOB = "hunt-r2-c3af6e161598"


def _progress_calls() -> list[dict]:
    return [
        {
            "tool": "hunt_start",
            "arguments": {"index": "hb_kyoushi_s1"},
            "output": json.dumps({"job_id": JOB, "status": "QUEUED"}),
            "source": "exec_audit",
        },
        {
            "tool": "hunt_status",
            "arguments": {"job_id": JOB},
            "output": json.dumps(
                {
                    "job_id": JOB,
                    "status": "RUNNING",
                    "stage": "cards",
                    "progress": {"current": {"phase": "cards"}, "stages": {}},
                }
            ),
            "source": "exec_audit",
        },
    ]


def _result_calls() -> list[dict]:
    return [
        {
            "tool": "hunt_status",
            "arguments": {"job_id": JOB},
            "output": json.dumps({"job_id": JOB, "status": "COMPLETE"}),
            "source": "exec_audit",
        },
        {
            "tool": "hunt_sources",
            "arguments": {"job_id": JOB},
            "output": json.dumps({"job_id": JOB, "status": "COMPLETE", "cards": []}),
            "source": "exec_audit",
        },
        {
            "tool": "hunt_leads",
            "arguments": {"job_id": JOB, "n": 3},
            "output": json.dumps(
                {
                    "job_id": JOB,
                    "leads": [{"rank": 1, "notable_id": "not-77"}],
                    "total_leads": 1,
                }
            ),
            "source": "exec_audit",
        },
        {
            "tool": "hunt_case",
            "arguments": {"job_id": JOB, "case": 1},
            "output": json.dumps({"job_id": JOB, "case": 1, "anchor_entity": "service x"}),
            "source": "exec_audit",
        },
    ]


def test_fold_payload_collects_answer_audit_and_terminal_state() -> None:
    turn = proof.Turn()
    payloads = [
        json.dumps({"choices": [{"delta": {"content": "Top lead "}, "finish_reason": None}]}),
        json.dumps({"choices": [{"delta": {"content": "not-77"}, "finish_reason": "stop"}]}),
        json.dumps({"usage": {"prompt_tokens": 1200}}),
        json.dumps(
            {
                "type": "exec_audit",
                "tool_calls": [{"tool": "hunt_start", "arguments": '{"index": "hb_kyoushi_s1"}'}],
            }
        ),
        "[DONE]",
        "not json at all",
    ]
    for payload in payloads:
        proof.fold_payload(turn, payload)
    assert turn.answer == "Top lead not-77"
    assert turn.finish == "stop"
    assert turn.usage == {"prompt_tokens": 1200}
    assert turn.done is True
    assert turn.calls == [
        {
            "tool": "hunt_start",
            "arguments": {"index": "hb_kyoushi_s1"},
            "output": None,
            "source": "exec_audit",
        }
    ]


def test_fold_payload_records_error_frames() -> None:
    turn = proof.Turn()
    proof.fold_payload(turn, json.dumps({"error": "Backend returned HTTP 500", "status": 500}))
    assert turn.error == "Backend returned HTTP 500"


def test_grade_progress_accepts_a_running_r2_hunt() -> None:
    answer = f"Hunt {JOB} is still running in the cards stage. Ask me for results later."
    passed, reasons, details = proof.grade_progress(_progress_calls(), answer)
    assert passed, reasons
    assert details["job_id"] == JOB
    assert details["status"] == "RUNNING"


def test_grade_progress_rejects_result_reads_while_running() -> None:
    calls = _progress_calls() + [_result_calls()[2]]
    passed, reasons, _ = proof.grade_progress(calls, f"Hunt {JOB} is running in cards.")
    assert not passed
    assert any("called a result view before the hunt finished" in r for r in reasons)


def test_grade_results_passes_on_the_later_turn_with_the_real_r2_job_id() -> None:
    answer = f"Job {JOB} completed. Top lead not-77 pivots on service x; case 1 shares it."
    passed, reasons, details = proof.grade_results(_result_calls(), answer, JOB)
    assert passed, reasons
    assert details["job_id"] == JOB
    assert "not-77" in details["citation"]


def test_grade_results_fails_when_hunt_case_is_missing() -> None:
    calls = [c for c in _result_calls() if c["tool"] != "hunt_case"]
    passed, reasons, _ = proof.grade_results(calls, f"{JOB} top lead not-77", JOB)
    assert not passed
    assert any("hunt_case was never called" in r for r in reasons)


def test_grade_results_fails_when_leads_carry_a_different_job_id() -> None:
    calls = _result_calls()
    calls[2]["arguments"] = {"job_id": "hunt-r2-ffffffffffff"}
    passed, reasons, _ = proof.grade_results(calls, f"{JOB} top lead not-77", JOB)
    assert not passed
    assert any("hunt_leads used job id" in r for r in reasons)


def test_grade_results_fails_when_a_tool_returns_a_different_job_id() -> None:
    calls = _result_calls()
    calls[2]["output"] = json.dumps(
        {"job_id": "hunt-r2-ffffffffffff", "leads": [{"notable_id": "not-77"}]}
    )
    passed, reasons, _ = proof.grade_results(calls, f"{JOB} top lead not-77", JOB)
    assert not passed
    assert any("hunt_leads output did not identify" in r for r in reasons)


def test_grade_results_fails_when_the_answer_cites_no_lead() -> None:
    passed, reasons, _ = proof.grade_results(
        _result_calls(), "The hunt finished successfully.", JOB
    )
    assert not passed
    assert any("does not cite a returned lead" in r for r in reasons)


def test_grade_results_fails_when_outputs_are_unobservable() -> None:
    calls = [{**c, "output": None} for c in _result_calls()]
    passed, reasons, _ = proof.grade_results(
        calls, f"Job {JOB} produced 3 leads; the top one is a service.", JOB
    )
    assert not passed
    assert any("lead outputs were not observable" in r for r in reasons)


def test_grade_results_reports_unobservable_arguments_from_trace_spans() -> None:
    calls = [
        {**call, "arguments": None, "output": None, "source": "trace"} for call in _result_calls()
    ]
    passed, reasons, _ = proof.grade_results(calls, f"{JOB} lead not-77 case 1", JOB)
    assert not passed
    assert sum("not observable" in r for r in reasons) >= 3


def test_calls_from_trace_pairs_spans_with_captured_arguments() -> None:
    record = {
        "bodies": {
            "tool_arguments": [
                {"hunt_start": {"index": "hb_kyoushi_s1"}},
                {"hunt_leads": {"job_id": JOB}},
                {"hunt_case": {"job_id": JOB, "case": 1}},
            ]
        },
        "spans": [
            {"name": "tool.requested", "tool": "hunt_start", "tool_call_id": "a", "at_ms": 10.0},
            {"name": "tool.completed", "tool": "hunt_start", "tool_call_id": "a", "outcome": "ok"},
            {"name": "tool.requested", "tool": "hunt_leads", "tool_call_id": "b", "at_ms": 90.0},
            {"name": "tool.completed", "tool": "hunt_leads", "tool_call_id": "b", "outcome": "ok"},
            {"name": "tool.requested", "tool": "hunt_case", "tool_call_id": "c", "at_ms": 120.0},
        ],
    }
    calls = proof.calls_from_trace(record)
    assert [(c["tool"], c["arguments"], c.get("outcome")) for c in calls] == [
        ("hunt_start", {"index": "hb_kyoushi_s1"}, "ok"),
        ("hunt_leads", {"job_id": JOB}, "ok"),
        ("hunt_case", {"job_id": JOB, "case": 1}, None),
    ]


def test_env_falls_back_to_the_repo_dotenv(monkeypatch, tmp_path) -> None:
    (tmp_path / ".env").write_text("OWUI_API_KEY='sk-dotenv'\nOTHER=1\n")
    monkeypatch.setattr(proof, "REPO", tmp_path)
    monkeypatch.delenv("OWUI_API_KEY", raising=False)
    assert proof.env("OWUI_API_KEY") == "sk-dotenv"
    monkeypatch.setenv("OWUI_API_KEY", "sk-env")
    assert proof.env("OWUI_API_KEY") == "sk-env"


def _stub_turns(monkeypatch, turns: list[proof.Turn]) -> list[tuple[str, list[dict] | None]]:
    seen: list[tuple[str, list[dict] | None]] = []

    def fake_stream(
        url: str,
        key: str,
        model: str,
        prompt: str,
        *_a,
        messages: list[dict] | None = None,
        **_k,
    ) -> proof.Turn:
        seen.append((prompt, messages))
        assert "sk-live" not in prompt
        return turns.pop(0)

    monkeypatch.setattr(proof, "stream_turn", fake_stream)
    monkeypatch.setattr(proof, "env", lambda name: "sk-live" if name.endswith("API_KEY") else "")
    return seen


def test_main_proves_progress_then_a_later_results_turn(monkeypatch, capsys) -> None:
    first = proof.Turn(t0=0.0, t_end=45.0, m0=0.0, finish="stop", done=True)
    first.content = [f"Hunt {JOB} is still running in the cards stage. Ask me for results later."]
    first.calls = _progress_calls()
    second = proof.Turn(t0=500.0, t_end=540.0, m0=500.0, finish="stop", done=True)
    second.content = [f"Job {JOB} completed. Top lead not-77; case 1 pivots on service x."]
    second.calls = _result_calls()
    seen = _stub_turns(monkeypatch, [first, second])
    monkeypatch.setattr(
        proof, "wait_for_terminal", lambda *_a, **_k: {"job_id": JOB, "status": "COMPLETE"}
    )
    code = proof.main(["--index", "hb_kyoushi_s1"])
    out = capsys.readouterr().out
    assert code == 0
    assert seen[0][0] == "Start a hunt on index hb_kyoushi_s1 and tell me its status and stage."
    assert "show me the hunt results" in seen[1][0].lower()
    assert seen[1][1] == [
        {"role": "user", "content": seen[0][0]},
        {"role": "assistant", "content": first.answer},
        {"role": "user", "content": seen[1][0]},
    ]
    assert "PASS" in out and "TURN 1" in out and "TURN 2" in out and "hunt_case" in out
    assert "sk-live" not in out
    assert "total: 45.0s" in out and "total: 40.0s" in out


def test_main_fails_on_first_turn_deadline(monkeypatch, capsys) -> None:
    turn = proof.Turn(t0=0.0, t_end=1500.0, m0=0.0, timed_out=True)
    turn.content = ["partial"]
    turn.calls = _progress_calls()
    _stub_turns(monkeypatch, [turn])
    monkeypatch.setattr(proof, "find_turn_trace", lambda *_a, **_k: None)
    code = proof.main(["--deadline-s", "1"])
    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL" in out
    assert "deadline" in out
    assert "TURN 1" in out


def test_main_fails_when_the_request_errors_out(monkeypatch, capsys) -> None:
    def boom(*_a, **_k):
        raise OSError("connection refused")

    monkeypatch.setattr(proof, "stream_turn", boom)
    monkeypatch.setattr(proof, "env", lambda name: "sk-live" if name.endswith("API_KEY") else "")
    assert proof.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL: the OWUI chat request failed" in out
    assert "sk-live" not in out
