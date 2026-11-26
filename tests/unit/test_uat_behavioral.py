from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from docx import Document

from tests.qat import uat_behavioral as uat
from tests.qat.config import discover
from tests.qat.models import QATScenario, Status


@pytest.mark.parametrize("style_name", ["Title", "Subtitle"])
def test_validate_docx_content_accepts_title_styles(style_name: str) -> None:
    document = Document()
    document.add_paragraph("UAT Project Note", style=style_name)
    document.add_paragraph("UAT-DOCX-TITLE-1")
    stream = io.BytesIO()
    document.save(stream)

    assert (
        uat.validate_docx_content(stream.getvalue(), "UAT Project Note", "UAT-DOCX-TITLE-1") is None
    )


def test_compliance_grader_accepts_non_certification_and_unproven_phrasing() -> None:
    case = uat.UATCase(
        "compliance",
        "compliance",
        "auto-compliance",
        ("initial question", "follow-up"),
        "compliance_multiframe",
    )
    turns = [
        uat.UATTurn(
            "initial question",
            "I am not certifying compliance. NERC CIP-007-6 R2 Part 2.2 and GDPR Art. 32(1)(a) require evidence.",
            {},
            (),
            (),
        ),
        uat.UATTurn(
            "follow-up",
            "The retention-policy conclusion remains unproven until the policy is supplied.",
            {},
            (),
            (),
        ),
    ]

    errors, _evidence = uat.grade_case(case, turns, {})

    assert errors == []


def test_cross_session_prompt_requires_recall_despite_auto_injection() -> None:
    case = next(
        case
        for case in uat.discover_cases(discover())
        if case.scenario_id == "s5-memory-cross-session"
    )

    assert "{{memory_key}}" in case.prompts[0]
    assert "{{memory_marker}}" in case.prompts[0]
    assert "{{memory_marker}}" in case.prompts[1]
    assert "preferred color cobalt" in case.prompts[0]
    assert case.expected_tools == ("remember", "recall")
    assert "Use recall" in case.prompts[1]
    assert "automatically injected memory" in case.prompts[1]
    prompts = uat._memory_prompts(case, "QATUAT-CODE", "QAT-LABEL")
    assert "QATUAT-CODE" in prompts[0] and "QATUAT-CODE" not in prompts[1]
    assert all("QAT-LABEL" in prompt for prompt in prompts)
    missing_recall = uat.UATTurn(case.prompts[1], "QATUAT-123; cobalt", {}, (), ())
    assert (
        uat._required_tool_error(replace(case, expected_tools=("recall",)), [missing_recall])
        == "required tools did not complete successfully: recall"
    )


def test_cross_session_runner_requires_tools_per_chat(monkeypatch) -> None:
    from tests.qat import runner

    case = next(
        case
        for case in uat.discover_cases(discover())
        if case.scenario_id == "s5-memory-cross-session"
    )
    scenario = QATScenario(
        case.scenario_id,
        case.title,
        5,
        uat.UAT_PHASE,
        1,
        case.model_slug,
        prompts=case.prompts,
        expected_tools=case.expected_tools,
    )
    observed_tools = []

    class FakeClient:
        def __init__(self, _settings) -> None:
            self.chats = 0

        def signin(self) -> str:
            return "token"

        def create_chat(self, *_args) -> str:
            self.chats += 1
            return f"chat-{self.chats}"

    def run_sequence(
        _client, _token, chat_id, session_scenario, session_case, _deadline, memory_key
    ):
        tool = "remember" if chat_id == "chat-1" else "recall"
        observed_tools.append((session_case.expected_tools, session_scenario.expected_tools))
        turn = uat.UATTurn(
            session_case.prompts[0],
            f"{memory_key} cobalt",
            {"spans": [{"name": "tool.completed", "tool": tool, "outcome": "ok"}]},
            (tool,),
            (),
        )
        error = uat._required_tool_error(session_case, [turn])
        result = uat._status_result(session_scenario, error, chat_id, [turn]) if error else None
        return [turn], result

    monkeypatch.setattr(uat, "OWUIClient", FakeClient)
    monkeypatch.setattr(uat, "_run_sequence", run_sequence)
    monkeypatch.setattr(runner, "_finalize_chat", lambda *_args: (True, ""))

    result = uat._run_memory_case(object(), scenario, case, object())

    assert observed_tools == [(("remember",), ("remember",)), (("recall",), ("recall",))]
    assert result.status is Status.PASS


def test_sandbox_tool_results_come_from_the_turn_trace_not_prose(
    monkeypatch, tmp_path: Path
) -> None:
    from portal.platform.inference.router import trace

    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path))
    stdout = (
        "UAT_PYTHON_73\n"
        "UAT_EXTERNAL_URL_BLOCKED:URLError\n"
        "UAT_INTERNAL_SERVICE_BLOCKED:URLError\n"
        "UAT_DNS_BLOCKED:gaierror\n"
    )
    trace.start_trace("p5-sandboxtool")
    try:
        trace.span(
            "tool.completed",
            tool="execute_python",
            outcome="ok",
            **trace.bounded_tool_result({"success": True, "stdout": stdout, "stderr": ""}),
        )
        trace.finalize_trace()
        record = trace.read_trace("p5-sandboxtool")
        trace.start_trace("p5-owuitask01")
        trace.note(owui_task=True)
        trace.span(
            "tool.completed",
            tool="execute_bash",
            outcome="ok",
            **trace.bounded_tool_result({"success": True, "stdout": "UAT_BASH_48", "stderr": ""}),
        )
        trace.finalize_trace()
        task_row = trace.read_trace("p5-owuitask01")
    finally:
        trace._current.set(None)
    assert isinstance(record, dict) and isinstance(task_row, dict)
    assert uat._tool_results_from_trace(record) == (
        {"tool": "execute_python", "result": {"success": True, "stdout": stdout, "stderr": ""}},
    )
    assert uat._tool_results_from_trace(task_row) == ()
    prose = stdout + "UAT_BASH_48"
    sandbox = uat.UATCase("sandbox", "sandbox", "auto-coding", ("run", "bash"), "sandbox")
    errors, _evidence = uat.grade_case(
        sandbox,
        [
            uat.UATTurn("run", prose, record, (), (), uat._tool_results_from_trace(record)),
            uat.UATTurn("bash", prose, task_row, (), (), uat._tool_results_from_trace(task_row)),
        ],
        {},
    )
    assert "sandbox execution result is missing" in errors


def test_agent_orchestrator_prompt_requires_clarification_before_speculation() -> None:
    persona = yaml.safe_load(Path("config/personas/agentorchestrator.yaml").read_text())
    prompt = persona["system_prompt"]

    assert "1–3 concise clarifying questions" in prompt
    assert "each ending with '?'" in prompt
    assert "before proposing speculative fixes or checklists" in prompt
