"""Production tool mode: the pipeline dispatches the tools, so the harness reads the row's
trace from the exec_audit event; tool_grounded grades it (live finding 2026-10-15: rows
recorded calls: [] and every grounded task failed)."""

from __future__ import annotations

import json

import portal.platform.inference.config as inference_config
from portal.platform.inference.router.streaming import _exec_audit_event
from tests.wfe import runner
from tests.wfe.checkers import CheckContext, check_tool_grounded
from tests.wfe.schema import Outcome

CALL = {
    "function": {"name": "compliance_read", "arguments": '{"ref": "OT-POL-007"}'},
    "_output": "# OT-POL-007 retention policy",
}


def _stream(*events: dict) -> list[bytes]:
    return [f"data: {json.dumps(e)}".encode() for e in events] + [b"data: [DONE]"]


def test_production_payload_requests_the_audit() -> None:
    _, payload, _ = runner._build_pipeline(
        "auto-compliance", [], "text", {}, None, "default", True, eval_scope={"campaign": "c"}
    )
    assert payload["exec_audit"] is True
    _, plain, _ = runner._build_pipeline("auto-compliance", [], "text", {}, None, "default", True)
    assert "exec_audit" not in plain


def test_pipeline_runner_forwards_thinking_budget() -> None:
    _, payload, _ = runner._build_pipeline(
        "auto-compliance",
        [],
        "text",
        {"thinking_budget": 8192},
        None,
        "default",
        True,
    )

    assert payload["thinking_budget"] == 8192


def test_ollama_runner_maps_card_documented_budget_to_think_level(monkeypatch) -> None:
    monkeypatch.setattr(runner, "ENGINE", "ollama")
    monkeypatch.setattr(runner._model_cards, "card_thinking_level", lambda _model, _budget: "low")

    payload = runner._build_v1(
        "qwen3.8-test",
        [],
        "none",
        {"thinking_budget": 8192},
        "default",
        False,
    )

    assert payload["think"] == "low"
    assert "thinking_budget" not in payload


def test_workspace_context_resolves_thinking_budget(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "portal.yaml").write_text("workspaces: {}\n")
    monkeypatch.setattr(runner, "REPO", tmp_path)
    monkeypatch.setattr(inference_config, "load_bench_workspaces_raw", lambda _repo: {})
    monkeypatch.setattr(inference_config, "load_persona_map", lambda **_kwargs: {})
    monkeypatch.setattr(
        runner,
        "effective_workspace",
        lambda _workspaces, _ws_id: {
            "module": "general",
            "model_hint": "test-model",
            "thinking_budget": 8192,
            "tools": [],
        },
    )
    monkeypatch.setattr(runner, "harness_note", lambda *_args: "")
    monkeypatch.setattr(runner, "production_tool_names", lambda _portal: [])

    context = runner.workspace_context("test::deep")

    assert context["sampling"]["thinking_budget"] == 8192


def test_audit_event_becomes_the_rows_tool_log_and_grounds_the_answer() -> None:
    lines = _stream(
        {"choices": [{"delta": {"content": '{"coverage": "FULL"}'}}]},
        json.loads(_exec_audit_event([CALL])[6:]),
    )
    msg, _, _ = runner._read_stream("v1", lines)
    log = runner._audited_calls(msg)
    assert "_exec_audit" not in msg and msg["content"] == '{"coverage": "FULL"}'
    assert [c["name"] for c in log] == ["compliance_read"] and log[0]["args"] == {
        "ref": "OT-POL-007"
    }
    spec = {"type": "tool_grounded", "evidence": [r"OT\-POL\-007(?![A-Za-z0-9])"]}
    ctx = CheckContext(final_text=msg["content"], task={}, tool_calls=log)
    assert check_tool_grounded(spec, ctx).outcome == Outcome.PASS


def test_no_audit_means_no_calls_and_tool_grounded_fails() -> None:
    msg, _, _ = runner._read_stream("v1", _stream({"choices": [{"delta": {"content": "x"}}]}))
    assert runner._audited_calls(msg) == []


def test_a_failed_lookup_that_echoes_the_id_does_not_ground_the_answer() -> None:
    """Live 2026-10-15: compliance_read answered {"ref": "OT-POL-007", "resolved": false} and
    tool_grounded called the answer grounded because the output named the document."""
    failed = {"name": "compliance_read", "output": '{"ref": "OT-POL-007", "resolved": false}'}
    ok = {"name": "compliance_read", "output": '{"ref": "OT-POL-007", "text": "retention"}'}
    spec = {"type": "tool_grounded", "evidence": [r"OT\-POL\-007(?![A-Za-z0-9])"]}
    ctx = CheckContext(final_text="x", task={}, tool_calls=[failed])
    assert check_tool_grounded(spec, ctx).outcome == Outcome.FAIL
    ctx = CheckContext(final_text="x", task={}, tool_calls=[failed, ok])
    assert check_tool_grounded(spec, ctx).outcome == Outcome.PASS
    err = {"name": "x", "output": '{"error": "boom OT-POL-007"}'}
    assert (
        check_tool_grounded(spec, CheckContext(final_text="", task={}, tool_calls=[err])).outcome
        == Outcome.FAIL
    )
