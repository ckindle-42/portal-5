"""Stage-4 root-cause fixes: heavy-seat timeouts, tool-aware -tools prompts, oMLX alias gate."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest

from portal.platform.inference.config import (
    get_workspace_dict,
    load_portal_config,
    merge_workspace_variant,
)
from portal.platform.inference.model_addressing import alias_targets_for_model
from tests.qat import config as cq
from tests.qat import runner, scenarios
from tests.qat.models import DefectClass, QATScenario, Status
from tests.qat.owui_client import TurnOutcome

from .test_config_and_scenarios import PORTAL, _preset, make_discovery, make_settings

GENERIC_TOOLS_PROMPT = "Use your attached tools to verify one fact, then cite the tool result."
STT_FIXTURE = "tests/fixtures/sample_two_speakers.wav"
TOOL_SEATS: dict[str, str] = {
    "auto-audio": "transcribe_with_speakers",
    "auto-audio::image": "generate_image",
    "auto-daily": "remember",
    "auto-daily::nemotron": "remember",
    "auto-documents": "create_word_document",
    "auto-security": "lookup_cve",
    "auto-vision": "generate_image",
}
ALIAS_SEATS: dict[str, str] = {
    "auto-compliance": "omlx-reasoning",
    "auto-compliance::reading": "omlx-general",
    "auto-daily::fast": "omlx-general",
}


def _stage4(tmp_path: Path, discovery: cq.Discovery) -> dict[str, QATScenario]:
    registry = scenarios.build_registry(make_settings(tmp_path), discovery)
    return {s.scenario_id: s for s in registry if s.stage == 4}


def _tools_discovery() -> cq.Discovery:
    return cq.discover(portal=PORTAL, presets=[_preset(pid, tools=["x"]) for pid in TOOL_SEATS])


class TestStage4Timeouts:
    def test_every_stage4_scenario_gets_at_least_360(self, tmp_path: Path) -> None:
        by_id = _stage4(tmp_path, make_discovery())
        assert by_id
        for sid, s in by_id.items():
            assert s.timeout_s >= 360.0, sid

    def test_default_seat_timeout_is_360(self, tmp_path: Path) -> None:
        by_id = _stage4(tmp_path, make_discovery())
        for sid in ("s4-auto-daily-core", "s4-auto-coding-core", "s4-auto-security-continuity"):
            assert by_id[sid].timeout_s == 360.0, sid

    def test_heavy_seats_get_600(self, tmp_path: Path) -> None:
        by_id = _stage4(tmp_path, make_discovery())
        for sid in (
            "s4-auto-research-core",
            "s4-auto-research-continuity",
            "s4-auto-coding-cad-core",
            "s4-auto-coding-cad-continuity",
            "s4-auto-compliance-core",
            "s4-auto-compliance-continuity",
        ):
            assert by_id[sid].timeout_s == 600.0, sid

    def test_live_compliance_variants_get_600(self) -> None:
        d = cq.discover()
        registry = scenarios.build_registry(cq.Settings.load(env_file=Path("/nonexistent")), d)
        by_id = {s.scenario_id: s for s in registry if s.stage == 4}
        seen = 0
        for pid in (
            "auto-compliance",
            "auto-compliance::reading",
            "auto-research",
            "auto-coding::cad",
        ):
            sid = f"s4-{pid.replace('::', '-')}-core"
            if sid in by_id:
                assert by_id[sid].timeout_s == 600.0, sid
                seen += 1
        assert seen >= 3


class TestStage4ToolPrompts:
    def test_tool_seats_name_a_declared_tool(self, tmp_path: Path) -> None:
        by_id = _stage4(tmp_path, _tools_discovery())
        for pid, tool in TOOL_SEATS.items():
            s = by_id[f"s4-{pid.replace('::', '-')}-tools"]
            assert tool in s.prompts[0], pid
            assert tool in cq.workspace_tools_for(pid), pid
            assert runner._requires_tool(s), pid

    def test_audio_tools_attaches_the_stt_fixture(self, tmp_path: Path) -> None:
        by_id = _stage4(tmp_path, _tools_discovery())
        s = by_id["s4-auto-audio-tools"]
        assert s.attachment == STT_FIXTURE
        assert (cq.REPO_ROOT / STT_FIXTURE).is_file()

    def test_vision_tools_keeps_the_inline_png(self, tmp_path: Path) -> None:
        by_id = _stage4(tmp_path, _tools_discovery())
        s = by_id["s4-auto-vision-tools"]
        assert s.attachment == scenarios.INLINE_VISION_PNG
        assert "image" in s.prompts[0].casefold()

    def test_unmapped_seat_keeps_the_generic_prompt(self, tmp_path: Path) -> None:
        d = cq.discover(portal=PORTAL, presets=[_preset("auto-coding", tools=["execute_python"])])
        by_id = _stage4(tmp_path, d)
        assert by_id["s4-auto-coding-tools"].prompts == (GENERIC_TOOLS_PROMPT,)

    def test_missing_tool_falls_back_to_generic(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(scenarios, "workspace_tools_for", lambda pid: ())
        by_id = _stage4(tmp_path, _tools_discovery())
        assert by_id["s4-auto-documents-tools"].prompts == (GENERIC_TOOLS_PROMPT,)

    def test_live_registry_tool_prompts_target_declared_tools(self) -> None:
        d = cq.discover()
        registry = scenarios.build_registry(cq.Settings.load(env_file=Path("/nonexistent")), d)
        seen = 0
        for s in registry:
            if s.stage == 4 and s.model_slug in TOOL_SEATS and s.scenario_id.endswith("-tools"):
                tool = TOOL_SEATS[s.model_slug]
                assert tool in s.prompts[0], s.scenario_id
                assert tool in cq.workspace_tools_for(s.model_slug), s.scenario_id
                seen += 1
        assert seen >= 5


def _s4_scenario(workspace: str) -> QATScenario:
    return QATScenario(
        f"s4-{workspace.replace('::', '-')}-continuity",
        "Continuity",
        4,
        "adaptive_deep",
        200,
        workspace,
        prompts=("Remember the code name ORCHID-9.", "What code name did I give you?"),
    )


def _served_trace(workspace: str, model: str, backend: str, **extra: object) -> dict[str, object]:
    return {
        "workspace": workspace,
        "model": model,
        "backend": backend,
        "outcome": "complete",
        "spans": [
            {"name": "route.resolved", "at_ms": 0.3},
            {"name": "backend.selected", "backend": backend, "model": model, "at_ms": 0.4},
            {"name": "stream.finished", "outcome": "complete", "at_ms": 1000.0},
        ],
        **extra,
    }


class TestOmlxPrimaryAliasGate:
    @pytest.mark.parametrize("workspace", sorted(ALIAS_SEATS))
    def test_configured_alias_served_cleanly_passes(self, workspace: str) -> None:
        expected = cq.primary_model_for(workspace)
        aliases = alias_targets_for_model(expected)
        assert expected and aliases, workspace
        for alias in sorted(aliases):
            trace = _served_trace(workspace, alias, ALIAS_SEATS[workspace])
            assert runner._primary_model_failure(_s4_scenario(workspace), trace, alias) is None

    @pytest.mark.parametrize("workspace", sorted(ALIAS_SEATS))
    def test_hint_itself_served_cleanly_passes(self, workspace: str) -> None:
        expected = cq.primary_model_for(workspace)
        trace = _served_trace(workspace, expected, "ollama-general")
        assert runner._primary_model_failure(_s4_scenario(workspace), trace, expected) is None

    @pytest.mark.parametrize("workspace", sorted(ALIAS_SEATS))
    def test_wrong_model_fails(self, workspace: str) -> None:
        expected = cq.primary_model_for(workspace)
        wrong = f"{expected}-not-configured"
        trace = _served_trace(workspace, wrong, ALIAS_SEATS[workspace])
        result = runner._primary_model_failure(_s4_scenario(workspace), trace, wrong)
        assert result is not None and result.status is Status.FAIL
        assert "served model differs from primary" in result.detail

    def test_capacity_fallback_to_another_seat_fails(self) -> None:
        # Live chat 3cb99310: turn 2 was answered by the lighter reading seat.
        other = cq.primary_model_for("auto-compliance::reading")
        trace = _served_trace("auto-compliance", other, "omlx-reasoning")
        result = runner._primary_model_failure(_s4_scenario("auto-compliance"), trace, other)
        assert result is not None and result.status is Status.FAIL
        assert result.defect_class is DefectClass.INFRA_ENV_GAP

    def test_failed_attempt_trace_still_fails(self) -> None:
        # Live turn-2 HTTP 507: the trace names the selected seat, but no answer was served.
        expected = cq.primary_model_for("auto-daily::fast")
        alias = sorted(alias_targets_for_model(expected))[0]
        trace: dict[str, object] = {
            "workspace": "auto-daily::fast",
            "model": alias,
            "backend": "omlx-general",
            "outcome": "error",
            "spans": [
                {"name": "backend.selected", "backend": "omlx-general", "model": alias},
                {"name": "backend.failed", "backend": "omlx-general", "at_ms": 2575.2},
            ],
        }
        result = runner._primary_model_failure(_s4_scenario("auto-daily::fast"), trace, alias)
        assert result is not None and result.status is Status.FAIL
        assert result.defect_class is DefectClass.INFRA_ENV_GAP

    def test_trace_fallback_flag_fails(self) -> None:
        expected = cq.primary_model_for("auto-compliance")
        alias = sorted(alias_targets_for_model(expected))[0]
        trace = _served_trace("auto-compliance", alias, "omlx-reasoning", fallback=True)
        result = runner._primary_model_failure(_s4_scenario("auto-compliance"), trace, alias)
        assert result is not None and result.status is Status.FAIL
        assert "trace fallback=true" in result.detail

    def test_discovery_attempt_then_alias_served_passes(self) -> None:
        expected = cq.primary_model_for("auto-compliance::reading")
        alias = sorted(alias_targets_for_model(expected))[0]
        trace = _served_trace("auto-compliance::reading", alias, "omlx-general")
        spans = trace["spans"]
        assert isinstance(spans, list)
        trace["spans"] = [
            {"name": "backend.attempt", "backend": "ollama-general", "outcome": "failed"},
            *spans,
        ]
        assert (
            runner._primary_model_failure(_s4_scenario("auto-compliance::reading"), trace, alias)
            is None
        )


class TestToolLoopCaps:
    """s4-auto-compliance-core / s4-auto-coding-core ran uncapped tool loops into
    the 600s/360s deadlines (live Release 1.0 QAT stages 3-4); both seats now
    declare hop/call caps like auto-research (a79933204)."""

    def test_auto_compliance_declares_the_loop_cap(self) -> None:
        catalog = get_workspace_dict(load_portal_config(_force_reload=True))
        assert catalog["auto-compliance"]["max_tool_hops"] == 5
        assert catalog["auto-compliance"]["max_tool_calls"] == 8

    def test_auto_compliance_reading_inherits_the_loop_cap(self) -> None:
        config = load_portal_config(_force_reload=True)
        merged = merge_workspace_variant(
            get_workspace_dict(config)["auto-compliance"],
            config.workspaces["auto-compliance"].variants["reading"],
        )
        assert merged["max_tool_hops"] == 5
        assert merged["max_tool_calls"] == 8

    def test_auto_coding_declares_the_loop_cap(self) -> None:
        catalog = get_workspace_dict(load_portal_config(_force_reload=True))
        assert catalog["auto-coding"]["max_tool_hops"] == 6
        assert catalog["auto-coding"]["max_tool_calls"] == 10

    def test_auto_coding_cad_keeps_its_deep_measure_and_verify_loop(self) -> None:
        config = load_portal_config(_force_reload=True)
        merged = merge_workspace_variant(
            get_workspace_dict(config)["auto-coding"],
            config.workspaces["auto-coding"].variants["cad"],
        )
        # 2026-11-24: capped at 10 (still deeper than base auto-coding's 6) to stop
        # runaway 15+ cad_build/generate_part loops after cad_finalize delivery.
        assert merged.get("max_tool_hops") == 10
        assert merged.get("max_tool_calls") is None

    def test_auto_coding_bigfix_inherits_the_coding_cap(self) -> None:
        config = load_portal_config(_force_reload=True)
        merged = merge_workspace_variant(
            get_workspace_dict(config)["auto-coding"],
            config.workspaces["auto-coding"].variants["bigfix"],
        )
        assert merged["max_tool_hops"] == 6
        assert merged["max_tool_calls"] == 10


class _RecallClient:
    """Turn-1 acknowledgement, turn-2 recall text; primary-model trace stays clean."""

    def __init__(self, recall_text: str) -> None:
        self._recall_text = recall_text
        self._turn = 0

    def send_turn(self, *args: object, **kwargs: object) -> httpx.Response:
        return httpx.Response(200)

    def poll_turn(self, *args: object, **kwargs: object) -> TurnOutcome:
        self._turn += 1
        model = runner.primary_model_for("auto-daily")
        return TurnOutcome(
            chat_id="chat-1",
            text="Acknowledged." if self._turn == 1 else self._recall_text,
            done=True,
            served_model=model,
            artifact_urls=(),
            leak_marker=None,
            trace={"workspace": "auto-daily", "model": model, "backend": "ollama-general"},
        )


def _continuity_scenario() -> QATScenario:
    return QATScenario(
        "s4-auto-daily-continuity",
        "Continuity",
        4,
        "adaptive_deep",
        200,
        "auto-daily",
        prompts=(
            "For this conversation, our project code name is ORCHID-9. Acknowledge briefly.",
            "What code name did I just give you, and what is it for?",
        ),
        tags=("adaptive", "continuity"),
    )


class TestContinuityRecall:
    """s4-auto-daily-continuity: turn 1 must not command the remember MCP tool,
    and the turn-2 recall gate must match the marker case-insensitively."""

    def test_turn1_prompt_does_not_command_remember(self, tmp_path: Path) -> None:
        by_id = _stage4(tmp_path, make_discovery())
        continuity = [s for s in by_id.values() if "continuity" in s.tags]
        assert continuity
        for s in continuity:
            assert "ORCHID-9" in s.prompts[0], s.scenario_id
            assert not s.prompts[0].casefold().startswith("remember"), s.scenario_id

    def test_turn2_recall_matches_lowercase_marker(self) -> None:
        client = _RecallClient("The code name is orchid-9 — our project marker.")
        outcome, failure, _spans, _calls = runner._run_chat_turns(
            client, "token", "chat-1", _continuity_scenario(), time.monotonic() + 60.0
        )
        assert failure is None
        assert outcome is not None

    def test_turn2_missing_marker_still_fails(self) -> None:
        client = _RecallClient("I do not have a code name for this conversation.")
        _outcome, failure, _spans, _calls = runner._run_chat_turns(
            client, "token", "chat-1", _continuity_scenario(), time.monotonic() + 60.0
        )
        assert failure is not None and failure.status is Status.FAIL
        assert "continuity turn 2" in failure.detail
