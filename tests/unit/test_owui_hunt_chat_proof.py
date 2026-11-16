"""The OWUI hunt chat proof grades the product path from stubbed HTTP evidence only."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

from mcp.client.streamable_http import streamable_http_client

from scripts.proofs import owui_hunt_chat as proof

JOB = "hunt-r2-c3af6e161598"
CASE_ID = "c34871dd325af64e"


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
            "output": json.dumps(
                {"job_id": JOB, "case": 1, "case_id": CASE_ID, "anchor_entity": "service x"}
            ),
            "source": "exec_audit",
        },
    ]


def _results_calls_without_sources() -> list[dict]:
    """Turn 2 as the live receipt shows it: leads and case, no sources."""
    return [call for call in _result_calls() if call["tool"] != "hunt_sources"]


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
    answer = f"Job {JOB} completed. Top lead not-77 pivots on service x; case {CASE_ID} shares it."
    passed, reasons, details = proof.grade_results(_result_calls(), answer, JOB)
    assert passed, reasons
    assert details["job_id"] == JOB
    assert "not-77" in details["citation"]
    assert CASE_ID in details["case_citation"]


def test_grade_results_passes_without_hunt_sources_when_the_prompt_never_asked() -> None:
    answer = f"Top lead not-77; case {CASE_ID} shares the same anchor."
    passed, reasons, _ = proof.grade_results(_results_calls_without_sources(), answer, JOB)
    assert passed, reasons


def test_grade_results_requires_hunt_sources_only_with_the_flag() -> None:
    answer = f"Top lead not-77; case {CASE_ID} shares the same anchor."
    passed, reasons, _ = proof.grade_results(
        _results_calls_without_sources(), answer, JOB, require_sources=True
    )
    assert not passed
    assert any("hunt_sources was never called" in reason for reason in reasons)


def test_grade_results_passes_without_hunt_status_when_the_answer_is_complete() -> None:
    calls = [call for call in _results_calls_without_sources() if call["tool"] != "hunt_status"]
    answer = f"Top lead not-77; case {CASE_ID} shares the same anchor."
    passed, reasons, _ = proof.grade_results(calls, answer, JOB)
    assert passed, reasons


def test_grade_results_fails_when_a_called_hunt_status_is_not_terminal() -> None:
    calls = _results_calls_without_sources()
    calls[0]["output"] = json.dumps({"job_id": JOB, "status": "RUNNING"})
    answer = f"Top lead not-77; case {CASE_ID} shares the same anchor."
    passed, reasons, _ = proof.grade_results(calls, answer, JOB)
    assert not passed
    assert any("did not observe a terminal status" in reason for reason in reasons)


def test_grade_results_fails_when_the_answer_omits_the_case_id() -> None:
    answer = f"Job {JOB} completed; the top lead is not-77 and case 1 shares it."
    passed, reasons, _ = proof.grade_results(_results_calls_without_sources(), answer, JOB)
    assert not passed
    assert any("does not cite the returned case" in reason for reason in reasons)


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
    first.usage = {"prompt_tokens": 1200}
    second = proof.Turn(t0=500.0, t_end=540.0, m0=500.0, finish="stop", done=True)
    second.content = [f"Job {JOB} completed. Top lead not-77; case {CASE_ID} pivots on service x."]
    second.calls = _result_calls()
    second.usage = {"prompt_tokens": 2240}
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
    assert "prompt tokens: 1200 | peak prompt tokens: 1200" in out
    assert "prompt tokens: 2240 | peak prompt tokens: 2240" in out


def test_stream_turn_has_no_total_wall_clock_deadline(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __iter__(self):
            return iter(
                [
                    b'data: {"choices":[{"delta":{"content":"hello"}}]}\n',
                    b"data: [DONE]\n",
                ]
            )

    monotonic_values = iter([0.0, 2000.0])
    monkeypatch.setattr(proof.urllib.request, "urlopen", lambda *_a, **_k: Response())
    monkeypatch.setattr(proof.time, "monotonic", lambda: next(monotonic_values))

    turn = proof.stream_turn("http://owui", "key", "model", "prompt", idle_s=2)

    assert turn.answer == "hello"
    assert turn.done


def test_main_fails_when_the_request_errors_out(monkeypatch, capsys) -> None:
    def boom(*_a, **_k):
        raise OSError("connection refused")

    monkeypatch.setattr(proof, "stream_turn", boom)
    monkeypatch.setattr(proof, "env", lambda name: "sk-live" if name.endswith("API_KEY") else "")
    assert proof.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL: the OWUI chat request failed" in out
    assert "sk-live" not in out


def test_proof_uses_the_real_sdk_v2_streamable_http_client() -> None:
    assert proof.streamable_http_client is streamable_http_client


def test_wait_for_terminal_reports_progress_until_terminal(monkeypatch, capsys) -> None:
    statuses = [
        {"job_id": JOB, "status": "RUNNING", "stage": "cards"},
        {"job_id": JOB, "status": "COMPLETE", "stage": "done"},
    ]

    class Session:
        def __init__(self, _read, _write):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def initialize(self):
            return None

        async def call_tool(self, *_args):
            return SimpleNamespace(structuredContent=statuses.pop(0), content=[], isError=False)

    @asynccontextmanager
    async def transport(url):
        assert url == "http://review/mcp"
        yield (object(), object())

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(proof, "streamable_http_client", transport, raising=False)
    monkeypatch.setattr(proof, "ClientSession", Session, raising=False)
    monkeypatch.setattr(proof.asyncio, "sleep", no_sleep)

    result = proof.wait_for_terminal("http://review/mcp", JOB)
    output = capsys.readouterr().out
    assert result["status"] == "COMPLETE"
    assert [check["status"] for check in result["polls"]] == ["RUNNING", "COMPLETE"]
    assert "status=RUNNING stage=cards" in output
    assert "status=COMPLETE stage=done" in output


def test_main_resumes_an_existing_job_without_starting_turn_one(monkeypatch, capsys) -> None:
    second = proof.Turn(t0=500.0, t_end=540.0, m0=500.0, finish="stop", done=True)
    second.content = [f"Job {JOB} completed. Top lead not-77; case {CASE_ID} pivots on service x."]
    second.calls = _result_calls()
    seen = _stub_turns(monkeypatch, [second])
    wait_calls = []

    def fake_wait(url, job_id):
        wait_calls.append((url, job_id))
        return {"job_id": JOB, "status": "COMPLETE", "elapsed_s": 1.0, "polls": []}

    monkeypatch.setattr(proof, "wait_for_terminal", fake_wait)
    code = proof.main(["--job-id", JOB])
    out = capsys.readouterr().out

    assert code == 0
    assert len(seen) == 1
    assert seen[0][0] == f"Show me the hunt results for job {JOB}: the top leads and first case."
    assert seen[0][1] == [{"role": "user", "content": seen[0][0]}]
    assert wait_calls == [("http://localhost:8943/mcp", JOB)]
    assert "TURN 1" not in out and "TURN 2" in out and "PASS" in out


def test_main_require_sources_flag_fails_a_turn_that_skips_sources(monkeypatch, capsys) -> None:
    second = proof.Turn(t0=500.0, t_end=540.0, m0=500.0, finish="stop", done=True)
    second.content = [f"Top lead not-77; case {CASE_ID} shares the same anchor."]
    second.calls = _results_calls_without_sources()
    _stub_turns(monkeypatch, [second])
    monkeypatch.setattr(
        proof, "wait_for_terminal", lambda *_a, **_k: {"job_id": JOB, "status": "COMPLETE"}
    )
    assert proof.main(["--job-id", JOB, "--require-sources"]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "hunt_sources was never called" in out
