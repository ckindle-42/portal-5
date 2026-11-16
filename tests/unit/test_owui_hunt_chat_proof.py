"""The OWUI hunt chat proof grades the product path from stubbed HTTP evidence only."""

from __future__ import annotations

import json

from scripts.proofs import owui_hunt_chat as proof

JOB = "hunt-0123456789ab"
PROMPT = "Start a hunt on index hb_kyoushi_s1 and show me the top leads and the first case."


def _calls() -> list[dict]:
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
            "output": json.dumps({"status": "COMPLETE"}),
            "source": "exec_audit",
        },
        {
            "tool": "hunt_leads",
            "arguments": {"job_id": JOB, "n": 3},
            "output": json.dumps(
                {"job_id": JOB, "leads": [{"rank": 1, "notable_id": "not-77"}, {"rank": 2}]}
            ),
            "source": "exec_audit",
        },
        {
            "tool": "hunt_case",
            "arguments": {"job_id": JOB, "case": 1},
            "output": json.dumps({"job_id": JOB, "case": 1}),
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


def test_grade_passes_on_the_full_product_path() -> None:
    answer = f"Job {JOB} completed. Top lead not-77 pivots on service x; case 1 shares it."
    passed, reasons, details = proof.grade(_calls(), answer)
    assert passed, reasons
    assert details["job_id"] == JOB
    assert "not-77" in details["citation"]


def test_grade_fails_when_hunt_case_is_missing() -> None:
    calls = [c for c in _calls() if c["tool"] != "hunt_case"]
    passed, reasons, _ = proof.grade(calls, f"{JOB} top lead not-77")
    assert not passed
    assert any("hunt_case was never called" in r for r in reasons)


def test_grade_fails_when_leads_carry_a_different_job_id() -> None:
    calls = _calls()
    calls[2]["arguments"] = {"job_id": "hunt-ffffffffffff"}
    passed, reasons, _ = proof.grade(calls, f"{JOB} top lead not-77")
    assert not passed
    assert any("hunt_leads used job id" in r for r in reasons)


def test_grade_fails_when_the_answer_cites_no_lead() -> None:
    passed, reasons, _ = proof.grade(_calls(), "The hunt finished successfully.")
    assert not passed
    assert any("does not cite leads" in r for r in reasons)


def test_grade_accepts_weak_citation_only_when_outputs_are_unobservable() -> None:
    calls = [{**c, "output": None} for c in _calls()]
    passed, _, details = proof.grade(
        calls, f"Job {JOB} produced 3 leads; the top one is a service."
    )
    assert passed
    assert "not observable" in details["citation"]
    passed, reasons, _ = proof.grade(calls, "The hunt produced 3 leads.")
    assert not passed
    assert any("cites no notable id and no job id" in r for r in reasons)


def test_grade_reports_unobservable_arguments_from_bare_trace_spans() -> None:
    calls = [
        {"tool": "hunt_start", "arguments": None, "output": None, "source": "trace"},
        {"tool": "hunt_leads", "arguments": None, "output": None, "source": "trace"},
        {"tool": "hunt_case", "arguments": None, "output": None, "source": "trace"},
    ]
    passed, reasons, _ = proof.grade(calls, f"{JOB} lead not-77 case 1")
    assert not passed
    assert sum("not observable" in r for r in reasons) == 2


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


def _stub_turn(monkeypatch, turn: proof.Turn) -> list[str]:
    seen: list[str] = []

    def fake_stream(url: str, key: str, model: str, prompt: str, *_a, **_k) -> proof.Turn:
        seen.append(prompt)
        assert "sk-live" not in prompt
        return turn

    monkeypatch.setattr(proof, "stream_turn", fake_stream)
    monkeypatch.setattr(proof, "env", lambda name: "sk-live" if name.endswith("API_KEY") else "")
    return seen


def test_main_prints_a_pass_receipt_without_leaking_the_key(monkeypatch, capsys) -> None:
    turn = proof.Turn(t0=0.0, t_end=420.0, m0=0.0, finish="stop", done=True)
    turn.content = [f"Job {JOB} done. Top lead not-77; case 1 pivots on it."]
    turn.calls = _calls()
    seen = _stub_turn(monkeypatch, turn)
    code = proof.main(["--index", "hb_kyoushi_s1"])
    out = capsys.readouterr().out
    assert code == 0
    assert seen == [PROMPT]
    assert "PASS" in out and "hunt_start" in out and "hunt_case" in out
    assert "sk-live" not in out
    assert "total: 420.0s" in out


def test_main_fails_on_deadline_and_on_unobservable_calls(monkeypatch, capsys) -> None:
    turn = proof.Turn(t0=0.0, t_end=1500.0, m0=0.0, timed_out=True)
    turn.content = ["partial"]
    _stub_turn(monkeypatch, turn)
    monkeypatch.setattr(proof, "find_turn_trace", lambda *_a, **_k: None)
    code = proof.main(["--deadline-s", "1"])
    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL" in out
    assert "deadline" in out
    assert "unobservable" in out


def test_main_fails_when_the_request_errors_out(monkeypatch, capsys) -> None:
    def boom(*_a, **_k):
        raise OSError("connection refused")

    monkeypatch.setattr(proof, "stream_turn", boom)
    monkeypatch.setattr(proof, "env", lambda name: "sk-live" if name.endswith("API_KEY") else "")
    assert proof.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL: the OWUI chat request failed" in out
    assert "sk-live" not in out
