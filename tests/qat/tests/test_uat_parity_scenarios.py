"""UAT-parity scenarios from the release_1_0_final audit: the STT grading gap
and the five missing end-to-end scenarios (voice clone, document PDF read-back,
Obscura browser, RAG round-trip, memory round-trip). Offline: registry shape
against the live repo config plus the runner's round-trip tool-span check.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.qat import runner as rn
from tests.qat import scenarios as sc
from tests.qat.config import Settings, discover, workspace_tools_for
from tests.qat.models import QATScenario


def _registry() -> list[QATScenario]:
    return sc.build_registry(Settings.load(env_file=Path("/nonexistent")), discover())


def _by_id() -> dict[str, QATScenario]:
    return {scenario.scenario_id: scenario for scenario in _registry()}


def test_stt_scenario_enforces_tool_and_docx_artifact() -> None:
    stt = _by_id()["s2-p6-auto-audio-stt"]
    # Expected calls are telemetry; the UAT grader checks transcript and DOCX outcome.
    assert stt.expected_tools == ("transcribe_with_speakers",)
    assert stt.artifact_kind == "docx"
    assert stt.attachment == "tests/fixtures/sample_two_speakers.wav"
    assert stt.model_slug == "auto-audio"
    assert "transcribe_with_speakers" in stt.prompts[0]


def test_voice_clone_scenario() -> None:
    clone = _by_id()["s2-p6-voice-clone"]
    assert clone.model_slug == "auto-audio::music"
    assert clone.expected_tools == ("clone_voice",)
    assert clone.artifact_kind == "wav"
    assert clone.attachment == "tests/fixtures/sample_two_speakers.wav"
    assert clone.timeout_s >= 900.0
    assert "clone_voice" in clone.prompts[0]


def test_documents_pdf_read_scenario() -> None:
    docs = _by_id()["s2-p3-auto-documents-pdf-read"]
    assert docs.model_slug == "auto-documents"
    assert docs.expected_tools == ("read_pdf", "create_word_document")
    assert docs.artifact_kind == "docx"
    assert docs.attachment == "tests/fixtures/realuse_v1/ru-v1-001/final_invoice.pdf"
    assert docs.phase == "coding_cad_docs_data_infra"
    assert "read_pdf" in docs.prompts[0] and "also_pdf" in docs.prompts[0]
    assert (Path(docs.attachment)).is_file()


def test_obscura_browser_scenario_is_not_a_health_probe() -> None:
    obscura = _by_id()["s2-p3-obscura-browser"]
    assert obscura.model_slug == "auto-coding"
    assert obscura.expected_tools == ("browser_navigate", "browser_snapshot")
    assert obscura.kind == "chat"
    assert "browser_navigate" in obscura.prompts[0]
    assert "browser_snapshot" in obscura.prompts[0]
    assert "/health" not in obscura.prompts[0]
    assert {"browser_navigate", "browser_snapshot"} <= set(workspace_tools_for("auto-coding"))


def test_rag_roundtrip_scenario() -> None:
    rag = _by_id()["s2-p3-rag-roundtrip"]
    assert rag.model_slug == "auto-research"
    assert rag.expected_tools == ("kb_list", "kb_search")
    assert {"kb_list", "kb_search"} <= set(workspace_tools_for("auto-research"))
    assert "kb_list" in rag.prompts[0] and "kb_search" in rag.prompts[0]


def test_memory_roundtrip_scenario() -> None:
    mem = _by_id()["s2-p4-memory-roundtrip"]
    assert mem.model_slug == "auto-daily"
    assert mem.expected_tools == ("remember", "recall")
    assert len(mem.prompts) == 2
    assert "remember" in mem.prompts[0] and "recall" in mem.prompts[1]
    assert {"remember", "recall"} <= set(workspace_tools_for("auto-daily"))


def _span(tool: str, outcome: str = "ok") -> dict:
    return {"name": "tool.completed", "tool": tool, "outcome": outcome}


def test_roundtrip_tool_expectations_are_telemetry_across_spans() -> None:
    scenario = QATScenario(
        "mem", "mem", 2, "daily_omlx", 40, "auto-daily", expected_tools=("remember", "recall")
    )
    trace = {"spans": [_span("remember"), _span("recall")]}
    # poll_turn falls back to the trace's tool spans as the call list
    assert rn._tool_telemetry(scenario, trace["spans"], trace)["missing_expected_tools"] == []
    # A message-level tool call is visible as telemetry even without a completed span.
    assert rn._tool_telemetry(scenario, [{"name": "remember"}], {})["missing_expected_tools"] == [
        "remember",
        "recall",
    ]
    missing_recall = {"spans": [_span("remember")]}
    telemetry = rn._tool_telemetry(scenario, missing_recall["spans"], missing_recall)
    assert telemetry["missing_expected_tools"] == ["recall"]


def test_tool_name_substring_does_not_hide_missing_expectation_in_telemetry() -> None:
    scenario = QATScenario(
        "rag",
        "rag",
        2,
        "coding_cad_docs_data_infra",
        30,
        "auto-research",
        expected_tools=("recall",),
    )
    trace = {"spans": [_span("graph_recall")]}
    telemetry = rn._tool_telemetry(scenario, trace["spans"], trace)
    assert telemetry["observed_tools"] == ["graph_recall"]
    assert telemetry["missing_expected_tools"] == ["recall"]


def test_failed_span_is_recorded_as_telemetry_not_a_verdict() -> None:
    scenario = QATScenario(
        "stt",
        "stt",
        2,
        "media_heavy",
        60,
        "auto-audio",
        expected_tools=("transcribe_with_speakers",),
    )
    trace = {"spans": [_span("transcribe_with_speakers", outcome="error")]}
    telemetry = rn._tool_telemetry(scenario, trace["spans"], trace)
    assert telemetry["missing_expected_tools"] == ["transcribe_with_speakers"]
    assert telemetry["failed_calls"][0]["tool"] == "transcribe_with_speakers"


def _turn_outcome(tool: str, text: str) -> object:
    from types import SimpleNamespace

    spans = [_span(tool)] if tool else []
    return SimpleNamespace(
        chat_id="chat-1",
        text=text,
        done=True,
        served_model="daily-model",
        artifact_urls=(),
        leak_marker=None,
        trace={"spans": spans, "model": "daily-model", "backend": "omlx"},
        tool_calls=({"name": tool},) if tool else (),
    )


def _run_multiturn_chat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcomes: list[object]
) -> object:
    """Drive _run_chat with one canned outcome per turn (remember on turn 1,
    recall on turn 2 — the live s2-p4-memory-roundtrip shape)."""
    from .test_config_and_scenarios import make_discovery, make_settings

    class FakeResponse:
        is_success = True
        status_code = 200
        headers: dict[str, str] = {}

    remaining = list(outcomes)

    class FakeClient:
        def __init__(self, settings: object) -> None:
            pass

        def signin(self) -> str:
            return "token"

        def create_chat(self, *args: object, **kwargs: object) -> str:
            return "chat-1"

        def send_turn(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse()

        def poll_turn(self, *args: object, **kwargs: object) -> object:
            return remaining.pop(0)

    monkeypatch.setattr(rn, "OWUIClient", FakeClient)
    monkeypatch.setattr(rn, "primary_model_for", lambda workspace: "")
    monkeypatch.setattr(rn, "_finalize_chat", lambda *args: (True, "archived"))
    scenario = QATScenario(
        "mem-rt",
        "Memory round-trip",
        2,
        "daily_omlx",
        4,
        "auto-daily",
        prompts=("Use remember to store 4711.", "Use recall to tell me the number."),
        expected_tools=("remember", "recall"),
    )
    return rn._run_chat(
        make_settings(tmp_path),
        scenario,
        rn.RunState(make_settings(tmp_path), tmp_path, make_discovery()),
        rn.RunnerOptions({2}, set(), set()),
    )


def test_multiturn_expected_tools_accumulate_across_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Turn 1 calls remember, turn 2 calls recall: the required-tool check must
    see both turns' spans, not only the last turn's trace."""
    from tests.qat.models import Status

    result = _run_multiturn_chat(
        monkeypatch,
        tmp_path,
        [_turn_outcome("remember", "Stored."), _turn_outcome("recall", "4711")],
    )
    assert result.status is Status.PASS


def test_multiturn_missing_first_turn_tool_is_telemetry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tests.qat.models import Status

    result = _run_multiturn_chat(
        monkeypatch,
        tmp_path,
        [_turn_outcome("", "I did not store it."), _turn_outcome("recall", "4711")],
    )
    assert result.status is Status.PASS
    assert result.evidence["tool_telemetry"]["missing_expected_tools"] == ["remember"]


def test_parity_scenarios_gated_on_workspace_tool_grants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A workspace that stops granting the tool drops the scenario instead of
    shipping a guaranteed FAIL row."""
    real = sc.workspace_tools_for

    def without_kb_search(slug: str, portal_data: object = None) -> tuple[str, ...]:
        tools = real(slug, portal_data)
        return tuple(t for t in tools if not (slug == "auto-research" and t == "kb_search"))

    monkeypatch.setattr(sc, "workspace_tools_for", without_kb_search)
    registry = sc.build_registry(Settings.load(env_file=Path("/nonexistent")), discover())
    assert not any(s.scenario_id == "s2-p3-rag-roundtrip" for s in registry)
    assert any(s.scenario_id == "s2-p3-obscura-browser" for s in registry)
