"""Production tool mode: the pipeline dispatches the tools, so the harness reads the row's
trace from the exec_audit event; tool_grounded grades it (live finding 2026-10-15: rows
recorded calls: [] and every grounded task failed)."""

from __future__ import annotations

import json

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
