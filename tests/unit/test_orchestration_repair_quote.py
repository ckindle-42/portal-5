"""The finish repair quotes the tools the Pipeline ran server-side, so the model resubmits the checked artifact."""

from pathlib import Path

from portal.modules.orchestration import worker


def test_transcript_records_server_side_tool_calls(tmp_path: Path) -> None:
    transcript = worker._Transcript(tmp_path / "t.jsonl")
    transcript.append(
        "event",
        {
            "type": "exec_audit",
            "tool_calls": [{"tool": "compile_yara", "arguments": '{"rule_text": "rule a {}"}'}],
        },
    )
    transcript.append("event", {"choices": []})
    assert transcript.audited_calls == [
        {"tool": "compile_yara", "arguments": '{"rule_text": "rule a {}"}'}
    ]


def test_repair_note_quotes_the_last_call_per_tool(tmp_path: Path) -> None:
    transcript = worker._Transcript(tmp_path / "t.jsonl")
    transcript.append(
        "event",
        {"type": "exec_audit", "tool_calls": [{"tool": "validate_sigma", "arguments": "v1"}]},
    )
    transcript.append(
        "event",
        {"type": "exec_audit", "tool_calls": [{"tool": "validate_sigma", "arguments": "v2"}]},
    )
    note = worker._validated_calls_note(transcript)
    assert "validate_sigma: v2" in note and "v1" not in note
    assert "byte for byte" in note


def test_no_note_without_server_side_calls(tmp_path: Path) -> None:
    assert worker._validated_calls_note(worker._Transcript(tmp_path / "t.jsonl")) == ""


def test_bite_requests_ask_for_the_execution_audit() -> None:
    assert worker._request_body.__code__.co_consts  # function exists
    import inspect

    assert '"exec_audit": True' in inspect.getsource(worker._request_body)


def test_lab_rows_match_the_backends_nested_fields() -> None:
    from portal.modules.orchestration.disciplines.detection_engineering import checkers

    nested = {"_time": 1.0, "raw": "{}", "fields": {"ServiceName": "svc_backup", "count": "70"}}
    assert checkers._row_matches({"ServiceName": "svc_backup"}, nested)
    assert checkers._row_matches({"ServiceName": "svc_backup"}, {"ServiceName": "svc_backup"})
    assert not checkers._row_matches({"ServiceName": "svc_sql"}, nested)
