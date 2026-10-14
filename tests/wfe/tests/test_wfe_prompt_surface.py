from __future__ import annotations

import pytest

from tests.wfe.prompt_surface import (
    HARNESS_NOTE_MARKER,
    harness_note,
    production_tool_names,
    prompt_tool_mismatches,
    suite_warnings,
    task_tool_mismatches,
    taxonomy_conflicts,
)
from tests.wfe.runner import TOOL_NAMES, workspace_context

HARNESS = {"file_read", "file_list", "repo_search", "file_write", "http_get", "pytest_run"}
KNOWN = {"nerc_cip_requirement", "compliance_ask", "nerc_cip_currency", "file_read"}


def test_flags_production_tools_the_harness_does_not_offer() -> None:
    prompt = "Begin with nerc_cip_requirement; then use compliance_ask. Use file_read for packets."
    assert prompt_tool_mismatches(prompt, HARNESS, KNOWN) == [
        "compliance_ask",
        "nerc_cip_requirement",
    ]


def test_clean_prompt_has_no_mismatch_and_no_note() -> None:
    prompt = "Read packet.json with file_read."
    assert prompt_tool_mismatches(prompt, HARNESS, KNOWN) == []
    assert harness_note(prompt, sorted(HARNESS), KNOWN) == ""


def test_production_tool_names_skips_plain_words() -> None:
    portal = {"workspaces": {"a": {"tools": ["web_search", "neighbors"]}, "b": {}}}
    assert production_tool_names(portal) == {"web_search"}


def test_note_declares_the_surface_and_silences_both_warnings() -> None:
    prompt = "Use nerc_cip_currency. Coverage: Full | Partial."
    user = "Reply with determination SUPPORTED or ABSENT."
    note = harness_note(prompt, sorted(HARNESS), KNOWN)
    assert HARNESS_NOTE_MARKER in note and "file_read" in note
    assert suite_warnings(prompt + note, user, HARNESS, KNOWN) == []


def test_taxonomy_conflict_detected() -> None:
    system = "Coverage: one of Full / Partial / None / Ambiguous."
    user = "Reply with a single JSON object: determination (SUPPORTED, PARTIAL, ABSENT)."
    assert taxonomy_conflicts(system, user) == ["coverage", "determination"]


def test_single_taxonomy_is_not_a_conflict() -> None:
    assert taxonomy_conflicts("Use Full or None.", "Say what you found.") == []


def test_suite_warnings_reports_both_kinds() -> None:
    warnings = suite_warnings(
        "Use nerc_cip_currency. Coverage: Full | Partial.",
        "Reply with determination SUPPORTED or ABSENT.",
        HARNESS,
        KNOWN,
    )
    assert any("nerc_cip_currency" in w for w in warnings)
    assert any("taxonomy conflict" in w for w in warnings)


def test_auto_compliance_is_served_with_the_note() -> None:
    ctx = workspace_context("auto-compliance")
    assert ctx["harness_note"] is True
    assert ctx["system_prompt"].rstrip().endswith("these instructions describe.")
    assert set(ctx["tool_surface"]) <= set(TOOL_NAMES)


def test_pipeline_mode_carries_the_note() -> None:
    ctx = workspace_context("auto-compliance")
    assert HARNESS_NOTE_MARKER in ctx["system_prompt_pipeline"]
    assert ctx["system_prompt_pipeline"].startswith(ctx["system_prompt_base"])


@pytest.mark.parametrize(("ws", "note_sent"), [("auto-security", True), ("auto-compliance", False)])
def test_pipeline_run_row_sends_the_note_only_in_sandbox_mode(
    tmp_path, monkeypatch, ws, note_sent
) -> None:
    """A sandbox-mode row explains its substitute tools; a production-mode row (tool_modes.yaml)
    runs the workspace's own tools and carries no harness note."""
    from tests.wfe import campaign

    class _Sent(BaseException):
        pass

    def fake_run_task(model, system_prompt, *a, **k):
        raise _Sent(system_prompt)

    monkeypatch.setattr(campaign, "ENGINE", "pipeline")
    monkeypatch.setattr(campaign, "run_task", fake_run_task)
    monkeypatch.setattr(campaign, "make_sandbox", lambda *a, **k: None)
    wsc = workspace_context(ws)
    row = {
        "run_id": "r1",
        "workspace": ws,
        "arm": wsc["model"],
        "arm_role": "incumbent",
        "suite": "compliance_agentic",
        "task_id": "t",
        "repeat": 0,
        "overrides": {},
    }
    manifest = {"campaign_id": "test_pipeline_note", "env": {}}
    try:
        campaign.run_row(tmp_path, manifest, row, wsc, {"id": "t"}, 1, 1, None, False)
    except _Sent as sent:
        assert (HARNESS_NOTE_MARKER in str(sent)) is note_sent
    else:
        raise AssertionError("run_task was not called")


def test_task_demanding_a_production_tool_warns() -> None:
    task = {"id": "t", "instruction": "Call compliance_ask, then file_read."}
    assert task_tool_mismatches(task, HARNESS, KNOWN) == ["compliance_ask"]


def test_task_declaring_requires_tools_is_blocked_not_warned() -> None:
    task = {"id": "t", "instruction": "Call compliance_ask.", "requires_tools": ["compliance_ask"]}
    assert task_tool_mismatches(task, HARNESS, KNOWN) == []


def test_home_compliance_suite_has_no_unblocked_tool_demand() -> None:
    import json
    from pathlib import Path

    suite = Path(__file__).resolve().parents[1] / "suites" / "compliance_agentic.jsonl"
    rows = [json.loads(line) for line in suite.read_text().splitlines() if line.strip()]
    known = production_tool_names(
        __import__("yaml").safe_load(
            (Path(__file__).resolve().parents[3] / "config/portal.yaml").read_text()
        )
    )
    assert [t["id"] for t in rows if task_tool_mismatches(t, HARNESS, known)] == []


def test_task_requiring_absent_tools_is_blocked(tmp_path) -> None:
    from tests.wfe import runner as rn
    from tests.wfe.schema import Outcome

    task = {
        "id": "c",
        "instruction": "Call compliance_ask.",
        "requires_tools": ["compliance_ask"],
        "checkers": [{"type": "answer_contains", "patterns": ["x"]}],
    }
    out = rn.run_task(
        "m", "sys", task, rn.Sandbox(tmp_path), max_turns=3, budget_s=60, use_tools=True
    )
    assert out["outcome"] == Outcome.BLOCKED.value
    assert out["tool_calls"] == 0
