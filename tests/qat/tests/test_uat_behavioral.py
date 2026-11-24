"""Offline acceptance checks for the human-grade UAT registry and graders."""

from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from docx import Document
from openpyxl import Workbook
from PIL import Image
from pptx import Presentation
from pptx.oxml.xmlchemy import OxmlElement

from portal.platform.inference.model_addressing import alias_targets_for_model
from tests.qat import artifacts, runner
from tests.qat import config as cq
from tests.qat import uat_behavioral as uat
from tests.qat.__main__ import parse_stages
from tests.qat.config import PersonaDef, discover
from tests.qat.models import QATScenario, Status
from tests.qat.owui_client import OWUIClient

from .test_config_and_scenarios import make_settings


def _turn(text: str, workspace: str = "", spans: list[dict] | None = None) -> uat.UATTurn:
    trace: dict[str, object] = {"workspace": workspace, "spans": spans or []}
    return uat.UATTurn("user prompt", text, trace, (), ())


def _png(color: tuple[int, int, int], pattern: bool = False) -> bytes:
    image = Image.new("RGB", (160, 160), color)
    if pattern:
        for x in range(160):
            for y in range(160):
                if (x + y) % 2:
                    image.putpixel((x, y), (240, 20, 30))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _wav(duration: float, silent: bool) -> bytes:
    rate = 16_000
    frames = int(rate * duration)
    values = [
        0 if silent else int(9000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(frames)
    ]
    stream = io.BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"".join(struct.pack("<h", value) for value in values))
    return stream.getvalue()


def _office_files() -> dict[str, bytes]:
    doc = Document()
    doc.add_heading("UAT Inventory Report", level=1)
    doc.add_paragraph("UAT-DOCX-27")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Item", "Status"
    table.cell(1, 0).text, table.cell(1, 1).text = "UAT-DOCX-27", "Ready"
    docx_io = io.BytesIO()
    doc.save(docx_io)

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Asset", "Owner", "State"])
    sheet.append(["UAT-DEVICE-34", "Priya", "Ready"])
    xlsx_io = io.BytesIO()
    workbook.save(xlsx_io)

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    paragraph = slide.shapes.placeholders[1].text_frame.paragraphs[0]
    paragraph.text = "UAT-PPTX-51"
    paragraph._p.get_or_add_pPr().append(OxmlElement("a:buChar"))
    pptx_io = io.BytesIO()
    presentation.save(pptx_io)
    return {"docx": docx_io.getvalue(), "xlsx": xlsx_io.getvalue(), "pptx": pptx_io.getvalue()}


def _cube_stl() -> bytes:
    points = {
        "000": (0.0, 0.0, 0.0),
        "100": (20.0, 0.0, 0.0),
        "010": (0.0, 20.0, 0.0),
        "110": (20.0, 20.0, 0.0),
        "001": (0.0, 0.0, 20.0),
        "101": (20.0, 0.0, 20.0),
        "011": (0.0, 20.0, 20.0),
        "111": (20.0, 20.0, 20.0),
    }
    faces = (
        ("000", "010", "110"),
        ("000", "110", "100"),
        ("001", "111", "011"),
        ("001", "101", "111"),
        ("000", "011", "010"),
        ("000", "001", "011"),
        ("100", "110", "111"),
        ("100", "111", "101"),
        ("000", "100", "101"),
        ("000", "101", "001"),
        ("010", "111", "110"),
        ("010", "011", "111"),
    )
    triangles = b"".join(
        struct.pack("<12fH", 0, 0, 0, *points[a], *points[b], *points[c], 0) for a, b, c in faces
    )
    return b"uat cube".ljust(80, b"\0") + len(faces).to_bytes(4, "little") + triangles


def test_uat_discovery_uses_configured_workspaces_and_personas() -> None:
    discovery = discover()
    cases = uat.discover_cases(discovery)
    persona_slugs = {persona.slug for persona in discovery.personas}

    assert cases
    assert all(
        case.model_slug in discovery.presets or case.model_slug in persona_slugs for case in cases
    )
    assert {str(case.expected["target"]) for case in cases if case.grader == "route"} <= set(
        discovery.presets
    )
    assert all(
        case.model_slug in persona_slugs
        for case in cases
        if case.scenario_id.startswith("s5-persona-")
    )
    stage = uat.build_registry(discovery)
    assert stage and {scenario.stage for scenario in stage} == {5}
    assert {scenario.phase for scenario in stage} == {uat.UAT_PHASE}
    discovered_ids = {scenario.scenario_id for scenario in stage}
    assert {
        "s5-sandbox-python-bash-network-isolation",
        "s5-documents-office-content",
        "s5-media-tts-speech",
        "s5-memory-cross-session",
        "s5-security-hunt-workflow",
        "s5-rag-followup",
        "s5-cad-stl-render",
    } <= discovered_ids
    assert any(case.grader == "imbalance" for case in cases)


def test_uat_stage_cli_alias() -> None:
    assert parse_stages("uat") == {5}
    assert parse_stages("2,uat") == {2, 5}
    assert 5 in parse_stages("all")


def test_generated_artifact_upload_uses_openwebui_file_endpoint(tmp_path: Path) -> None:
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.read())
        return httpx.Response(200, json={"id": "file-uat"})

    client = OWUIClient(make_settings(tmp_path), httpx.MockTransport(handler))
    uploaded = client.upload_attachment_bytes("token", "uat-note.docx", b"docx-content")
    assert uploaded == {"type": "file", "id": "file-uat"}
    assert b"uat-note.docx" in bodies[0] and b"docx-content" in bodies[0]


def test_route_and_lane_behavior_graders() -> None:
    route = uat.UATCase("r", "r", "auto", ("first", "second"), "route", {"target": "auto-coding"})
    good_route = [_turn("Role answer", "auto-coding"), _turn("Follow-up", "auto-coding")]
    bad_route = [_turn("Role answer", "auto-security"), _turn("Follow-up", "auto-security")]
    assert uat.grade_case(route, good_route, {})[0] == []
    assert "expected route" in uat.grade_case(route, bad_route, {})[0][0]

    math_case = uat.UATCase(
        "m", "m", "auto", ("first", "second"), "route_math", {"target": "auto-reasoning::math"}
    )
    math_turns = [
        _turn("Integral result e - 2", "auto-reasoning::math"),
        _turn("Derivative check gives 0.718", "auto-reasoning::math"),
    ]
    assert uat.grade_case(math_case, math_turns, {})[0] == []

    daily = uat.UATCase(
        "d",
        "d",
        "auto-daily",
        ("first", "second"),
        "daily_redirect",
        {"target": "auto-coding", "target_name": "Portal Code Expert"},
    )
    assert (
        uat.grade_case(
            daily,
            [
                _turn("A 600-line service is too large to print inline. Open auto-coding."),
                _turn("Use the coding workspace next."),
            ],
            {},
        )[0]
        == []
    )
    assert uat.grade_case(daily, [_turn("Here is code"), _turn("```\n" + "x\n" * 40 + "```")], {})[
        0
    ]

    large_code = (
        "```python\n"
        + "\n".join(f"step_{index:03d} = process(input_{index:03d})" for index in range(600))
        + "\n```"
    )
    errors = uat.grade_case(
        daily, [_turn(large_code), _turn("Open auto-coding for the implementation.")], {}
    )[0]
    assert "daily answer attempted to print a large implementation inline" in errors


def test_route_grader_reads_resolved_route_span() -> None:
    case = uat.UATCase("r", "r", "auto", ("prompt",), "route", {"target": "auto-coding"})
    routed = _turn(
        "The role answer", spans=[{"name": "route.resolved", "workspace": "auto-coding"}]
    )
    assert uat.grade_case(case, [routed], {})[0] == []


def test_text_journey_does_not_require_artifact_payload() -> None:
    case = uat.UATCase("text", "text", "auto", ("prompt",), "route")
    assert uat._grade_payload_types(case, {}) == []


def test_security_route_checks_allowed_destination_and_manual_handoff() -> None:
    discovery = discover()
    case = next(
        item
        for item in uat.discover_cases(discovery)
        if item.scenario_id == "s5-route-tls-firewall"
    )
    allowed = case.expected["targets"]
    assert case.grader == "route_security_handoff"
    assert isinstance(allowed, list) and "auto-daily" in allowed
    assert set(allowed) <= set(discovery.presets)

    turns = [
        _turn(
            "For security analysis, select the auto-security workspace, Portal Security Analyst.",
            "auto-daily",
        ),
        _turn("Check SNI and the firewall path before changing either.", "auto-daily"),
    ]
    assert uat.grade_case(case, turns, {})[0] == []
    turns[0] = _turn("Check the certificate chain and subnet route.", "auto-daily")
    assert any("select auto-security" in error for error in uat.grade_case(case, turns, {})[0])
    turns[0] = _turn(
        "Select a safe diagnostic and mention the auto-security workspace separately.",
        "auto-daily",
    )
    assert any("select auto-security" in error for error in uat.grade_case(case, turns, {})[0])
    turns[0] = _turn("Select the auto-security workspace for security analysis.", "auto-security")
    assert uat.grade_case(case, turns, {})[0] == []
    turns[1] = _turn("Follow-up", "auto-coding")
    assert any("expected route" in error for error in uat.grade_case(case, turns, {})[0])


def test_persona_cases_only_target_models_returned_by_owui(tmp_path: Path) -> None:
    discovery = discover()
    persona_dir = tmp_path / "personas"
    persona_dir.mkdir()
    registered = PersonaDef("registered_persona", "Registered", "auto-research", "data", "")
    unavailable = PersonaDef("unavailable_persona", "Unavailable", "auto-research", "data", "")
    configured = replace(discovery, personas=(registered, unavailable))
    for persona in (registered, unavailable):
        (persona_dir / f"{persona.slug}.yaml").write_text(
            "slug: "
            + persona.slug
            + "\n"
            + "name: "
            + persona.name
            + "\n"
            + "workspace_model: auto-research\n"
            + "system_prompt: Handle class imbalance carefully.\n",
            encoding="utf-8",
        )

    cases = uat.discover_cases(
        configured, persona_dir=persona_dir, available_models={"registered_persona"}
    )
    persona_cases = [case for case in cases if case.scenario_id.startswith("s5-persona-")]
    assert [case.model_slug for case in persona_cases] == ["registered_persona"]


def test_output_hygiene_rejects_cjk_markup_and_repeated_lines() -> None:
    prompt = "Explain the database migration plan."
    assert uat.check_output_hygiene(prompt, "A concise English response.") == []
    assert any("CJK" in error for error in uat.check_output_hygiene(prompt, "你" * 11))
    assert not any("CJK" in error for error in uat.check_output_hygiene(prompt, "你" * 10))
    assert not any("CJK" in error for error in uat.check_output_hygiene("翻译这个句子", "你" * 11))
    for leaked_tag in (
        "</tool_response>",
        "<tool_call>",
        "</tool_call>",
        "</工具使用记录>",
    ):
        assert uat.check_output_hygiene(prompt, f"Leaked payload {leaked_tag}")
    assert any(
        "repetition" in error
        for error in uat.check_output_hygiene(prompt, "\n".join(["Repeated output line"] * 5))
    )
    assert not any(
        "repetition" in error
        for error in uat.check_output_hygiene(prompt, "\n".join(["Repeated output line"] * 4))
    )

    clarity = uat.UATCase("c", "c", "persona", (prompt,), "clarification")
    response = "Which database and migration window are you using? " + "你" * 11
    assert any("CJK" in error for error in uat.grade_case(clarity, [_turn(response)], {})[0])


def test_raw_http_error_inside_fenced_code_is_not_a_leak() -> None:
    code = "Example handler:\n```python\nexcept httpx.HTTPStatusError as exc:\n    print(exc)\n```"
    assert artifacts.raw_tool_error_leak(code) is None
    assert artifacts.raw_tool_error_leak("The request failed with httpx.HTTPStatusError")


def test_tts_followup_uploads_the_generated_wav_even_when_docx_is_stale() -> None:
    class AttachmentClient:
        downloaded: list[str] = []
        uploaded: list[tuple[str, bytes]] = []

        def download_artifact(self, token: str, url: str) -> bytes:
            self.downloaded.append(url)
            return b"RIFF wav bytes"

        def upload_attachment_bytes(
            self, token: str, filename: str, data: bytes, deadline: float
        ) -> dict[str, str]:
            self.uploaded.append((filename, data))
            return {"type": "file", "id": "generated-wav"}

    client = AttachmentClient()
    case = uat.UATCase(
        "tts",
        "tts",
        "auto-audio::music",
        ("speak", "transcribe"),
        "tts_quality",
        expected={"upload_kind": "wav"},
        generated_upload_turn=2,
    )
    stale_docx = "http://owui/api/v1/files/12345678/content/old.docx"
    generated_wav = "http://owui/api/v1/files/87654321/content/generated.wav"
    turns = [uat.UATTurn("speak", "audio ready", {}, (), (stale_docx, generated_wav))]

    files, error = uat._turn_files(client, "token", case, 2, turns, 60.0)
    assert error is None
    assert client.downloaded == [generated_wav]
    assert client.uploaded == [("uat-generated-wav.wav", b"RIFF wav bytes")]
    assert files == [{"type": "file", "id": "generated-wav"}]


def test_model_catalog_lists_registered_openwebui_ids(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/models"
        assert request.headers["Authorization"] == "Bearer token"
        return httpx.Response(
            200,
            json={"data": [{"id": "agentorchestrator"}, {"id": "auto-data"}]},
        )

    client = OWUIClient(make_settings(tmp_path), httpx.MockTransport(handler))
    assert client.list_models("token") == {"agentorchestrator", "auto-data"}


def test_persona_contract_graders() -> None:
    cases = [
        ("clarification", "Which operating system and authentication symptom are you seeing?"),
        (
            "destructive_warning",
            "Warning: deleting production data is irreversible. Confirm the approved backup first.",
        ),
        (
            "correlation",
            "Correlation does not imply causation. Seasonality and customer mix may confound this relationship.",
        ),
        (
            "imbalance",
            "Class imbalance makes accuracy misleading; compare the baseline, precision and recall for fraud.",
        ),
        (
            "compliance_guard",
            "CIP-007-6 R2 Part 2.2; this is not enough evidence to determine compliance, subject to SME review.",
        ),
        ("terminal_contract", "```text\nUAT_TERMINAL_42\n```"),
        ("spreadsheet_contract", "| 1 | 2 | 3 |"),
    ]
    for grader, response in cases:
        case = uat.UATCase(grader, grader, "persona", ("prompt",), grader)
        assert uat.grade_case(case, [_turn(response)], {})[0] == []

    compliance_guard = uat.UATCase(
        "compliance", "compliance", "persona", ("prompt",), "compliance_guard"
    )
    certified = "CIP-007-6 R2 Part 2.2: You are fully compliant, based on the evidence shown."
    assert uat.grade_case(compliance_guard, [_turn(certified)], {})[0]

    compliance = uat.UATCase("c", "c", "persona", ("prompt",), "compliance_multiframe")
    response = "CIP-007-6 R2 Part 2.2 and GDPR Art. 32(1)(a); evidence is not enough to determine compliance, subject to review."
    assert uat.grade_case(compliance, [_turn(response)], {})[0] == []
    incomplete = (
        "CIP-007-6 R2 and GDPR Art. 32(1)(a); cannot determine compliance from this evidence."
    )
    assert uat.grade_case(compliance, [_turn(incomplete)], {})[0]
    assert uat.grade_case(compliance, [_turn("You are fully compliant.")], {})[0]


def test_office_artifact_graders_inspect_content() -> None:
    payloads = _office_files()
    assert (
        uat.validate_docx_content(payloads["docx"], "UAT Inventory Report", "UAT-DOCX-27", 2, 2)
        is None
    )
    assert (
        uat.validate_xlsx_content(payloads["xlsx"], ("Asset", "Owner", "State"), "UAT-DEVICE-34")
        is None
    )
    assert uat.validate_pptx_content(payloads["pptx"], "UAT-PPTX-51") is None
    case = uat.UATCase(
        "o",
        "o",
        "auto-documents",
        ("prompt",),
        "office_content",
        {"docx": "UAT-DOCX-27", "xlsx": "UAT-DEVICE-34", "pptx": "UAT-PPTX-51"},
    )
    grouped = {kind: [data] for kind, data in payloads.items()}
    assert uat.grade_case(case, [_turn("Artifacts ready")], grouped)[0] == []
    assert uat.grade_case(case, [_turn("Artifacts ready")], {"docx": [], "xlsx": [], "pptx": []})[0]


def test_media_graders_reject_blank_short_and_silent_artifacts() -> None:
    assert uat.validate_png_quality(_png((80, 80, 80))) is not None
    assert uat.validate_png_quality(_png((0, 0, 0), pattern=True)) is None

    short = {
        "streams": [
            {
                "codec_type": "video",
                "width": 640,
                "height": 360,
                "duration": "2.4",
                "nb_frames": "72",
            }
        ]
    }
    good = {
        "streams": [
            {
                "codec_type": "video",
                "width": 640,
                "height": 360,
                "duration": "4",
                "nb_frames": "120",
            }
        ]
    }
    assert uat.validate_video_probe(short) is not None
    assert uat.validate_video_probe(good) is None
    assert (
        uat.validate_video_probe({"streams": [{"codec_type": "video", "duration": "4"}]})
        is not None
    )

    assert (
        uat.validate_wav_quality(_wav(8.2, silent=True), 8.0)[0] == "WAV is silent or near-silent"
    )
    error, metrics = uat.validate_wav_quality(_wav(8.2, silent=False), 8.0)
    assert error is None and metrics["duration_s"] >= 8.0 and metrics["rms"] > 0.001
    assert uat.validate_wav_quality(_wav(1.0, silent=False), 8.0)[0].startswith("WAV duration")

    tts = uat.UATCase("tts", "tts", "auto-audio::music", ("speak", "transcribe"), "tts_quality")
    turns = [_turn("Created WAV"), _turn("Portal five acceptance check. Access code blue seven.")]
    assert uat.grade_case(tts, turns, {"wav": [_wav(1.5, silent=False)]})[0] == []
    assert uat.grade_case(tts, turns, {"wav": [_wav(1.5, silent=False)]}, "Portal 5. Blue 7.")[0]

    voice = uat.UATCase("voice", "voice", "auto-audio::music", ("clone",), "voice_clone_quality")
    assert uat.grade_case(voice, [_turn("Audio generated")], {"wav": [_wav(1.5, False)]})[0] == []
    assert uat.grade_case(
        voice,
        [_turn("The source audio says hello")],
        {"wav": [_wav(1.5, False)]},
    )[0]


def test_multiturn_transcript_and_tool_grading() -> None:
    turns = [
        _turn("first", spans=[{"name": "tool.completed", "tool": "remember", "outcome": "ok"}]),
        _turn("second", spans=[{"name": "tool.completed", "tool": "recall", "outcome": "ok"}]),
    ]
    assert uat.validate_transcript(turns, 2) is None
    assert "expected 3" in uat.validate_transcript(turns, 3)
    assert (
        uat._required_tool_error(
            uat.UATCase(
                "mem",
                "mem",
                "auto-daily",
                ("a", "b"),
                "cross_session_memory",
                expected_tools=("remember", "recall"),
            ),
            turns,
        )
        is None
    )
    assert (
        uat._required_tool_error(
            uat.UATCase(
                "mem",
                "mem",
                "auto-daily",
                ("a", "b"),
                "cross_session_memory",
                expected_tools=("remember", "recall"),
            ),
            turns[:1],
        )
        == "required tools did not complete successfully: recall"
    )
    memory = uat.UATCase(
        "memory", "memory", "auto-daily", ("store", "recall"), "cross_session_memory"
    )
    errors, evidence = uat.grade_case(
        memory,
        [_turn("Saved QATUAT-123 and cobalt"), _turn("QATUAT-123; cobalt")],
        {},
    )
    assert errors == [] and evidence["cross_session"] is True


def test_sandbox_hunt_and_rag_behavior_graders() -> None:
    sandbox = uat.UATCase("sandbox", "sandbox", "auto-coding", ("run", "bash"), "sandbox")
    assert (
        uat.grade_case(
            sandbox,
            [_turn("UAT_PYTHON_73; URLError"), _turn("UAT_BASH_48")],
            {},
        )[0]
        == []
    )
    assert uat.grade_case(
        sandbox,
        [_turn("UAT_PYTHON_73; connection succeeded"), _turn("UAT_BASH_48")],
        {},
    )[0]

    hunt = uat.UATCase(
        "hunt", "hunt", "security-reviewer", ("sources", "status", "leads"), "hunt_workflow"
    )
    assert (
        uat.grade_case(
            hunt,
            [
                _turn("Source selected"),
                _turn("Hunt status: complete"),
                _turn("Leads: event 12345678"),
            ],
            {},
        )[0]
        == []
    )

    rag = uat.UATCase("rag", "rag", "auto-research", ("find", "quote"), "rag_followup")
    assert (
        uat.grade_case(
            rag,
            [_turn("Source document: Retention guide"), _turn("The source states 7 years.")],
            {},
        )[0]
        == []
    )


def test_stl_geometry_grader_rejects_empty_data() -> None:
    assert uat.validate_stl_geometry(b"bad data") is not None
    assert uat.validate_stl_geometry(_cube_stl()) is None


def test_stt_transcript_is_marked_for_human_accuracy_review() -> None:
    case = uat.UATCase("s", "s", "auto-audio", ("transcribe",), "stt_accuracy")
    response = "Speaker 1: Hello, this is the first speaker testing diarization. Speaker 2: Yes, this is the second speaker responding clearly to the first speaker."
    errors, evidence = uat.grade_case(case, [_turn(response)], {"docx": [b"docx"]})
    assert errors == []
    assert evidence["operator_review_required"]
    alternate = "SPEAKER_00: Hello. SPEAKER_01: Good morning."
    assert uat.grade_case(case, [_turn(alternate)], {"docx": [b"docx"]})[0] == []


def _trace_client(tmp_path: Path, summaries: list[dict], details: dict[str, dict]) -> OWUIClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/trace":
            return httpx.Response(200, json={"data": summaries})
        correlation_id = request.url.path.rsplit("/", 1)[-1]
        detail = details.get(correlation_id)
        if detail is None:
            return httpx.Response(404, json={})
        return httpx.Response(200, json=detail)

    return OWUIClient(make_settings(tmp_path), httpx.MockTransport(handler))


def test_lookup_trace_matches_auto_requested_and_persona(tmp_path: Path) -> None:
    started = 1_700_000_000.0
    summaries = [
        {
            "correlation_id": "c-auto",
            "workspace": "auto-coding",
            "requested": "auto",
            "persona": "",
            "started_at": started,
        },
        {
            "correlation_id": "c-persona",
            "workspace": "auto-daily",
            "requested": "auto-daily",
            "persona": "agentorchestrator",
            "started_at": started,
        },
    ]
    details = {
        "c-auto": {"correlation_id": "c-auto", "workspace": "auto-coding", "model": "coding-model"},
        "c-persona": {
            "correlation_id": "c-persona",
            "workspace": "auto-daily",
            "model": "daily-model",
            "persona": "agentorchestrator",
        },
    }
    client = _trace_client(tmp_path, summaries, details)
    auto = client.lookup_trace(model_slug="auto", turn_started_at=started)
    persona = client.lookup_trace(model_slug="agentorchestrator", turn_started_at=started)
    assert auto.get("model") == "coding-model"
    assert persona.get("model") == "daily-model"


def test_lookup_trace_falls_back_when_correlation_id_is_missing(tmp_path: Path) -> None:
    started = 1_700_000_000.0
    summaries = [
        {
            "correlation_id": "c-auto",
            "workspace": "auto-coding",
            "requested": "auto",
            "started_at": started,
        }
    ]
    details = {"c-auto": {"correlation_id": "c-auto", "model": "coding-model"}}
    client = _trace_client(tmp_path, summaries, details)
    found = client.lookup_trace(
        correlation_id="missing-id", model_slug="auto", turn_started_at=started
    )
    assert found.get("model") == "coding-model"
    stale = client.lookup_trace(
        correlation_id="missing-id", model_slug="auto", turn_started_at=started + 30.0
    )
    assert stale == {}


def _scenario(scenario_id: str, stage: int, model_slug: str) -> QATScenario:
    return QATScenario(scenario_id, scenario_id, stage, "phase", 1, model_slug)


@pytest.mark.parametrize("stage", [2, 4, 5])
def test_primary_model_failure_rejects_unverified_serving_model(stage: int) -> None:
    scenario = _scenario(f"s{stage}-auto", stage, "auto")
    missing = runner._primary_model_failure(scenario, {}, "")
    blank = runner._primary_model_failure(
        scenario, {"workspace": "auto-coding", "model": "", "backend": "omlx-general"}, ""
    )
    assert missing is not None and blank is not None
    assert missing.status is Status.FAIL and blank.status is Status.FAIL
    assert missing.detail == "missing pipeline trace or served_model; cannot verify serving model"
    assert blank.detail == missing.detail


def test_primary_model_failure_checks_routed_workspace_for_auto_and_persona() -> None:
    expected = cq.primary_model_for("auto-coding")
    assert expected
    aliases = alias_targets_for_model(expected)
    served = sorted(aliases)[0] if aliases else expected
    trace = {
        "workspace": "auto-coding",
        "requested": "auto",
        "model": served,
        "backend": "omlx-general",
        "spans": [],
    }
    assert runner._primary_model_failure(_scenario("s5-route", 5, "auto"), trace, served) is None
    persona_trace = {**trace, "persona": "agentorchestrator", "requested": "agentorchestrator"}
    assert (
        runner._primary_model_failure(
            _scenario("s5-persona", 5, "agentorchestrator"), persona_trace, served
        )
        is None
    )
    wrong = {**trace, "model": f"{expected}-not-served"}
    missed = runner._primary_model_failure(
        _scenario("s5-route", 5, "auto"), wrong, str(wrong["model"])
    )
    assert missed is not None and missed.status is Status.FAIL
    assert "served model differs from primary" in missed.detail
    fallback = {**trace, "fallback": True}
    fell_back = runner._primary_model_failure(_scenario("s5-route", 5, "auto"), fallback, served)
    assert fell_back is not None and fell_back.status is Status.FAIL
    assert "trace fallback=true" in fell_back.detail


def test_failed_stage5_rows_record_served_model_and_backend() -> None:
    scenario = _scenario("s5-documents-office-content", 5, "auto-documents")
    turns = [
        uat.UATTurn("first", "ok", {"model": "earlier", "backend": "earlier-b"}, (), ()),
        uat.UATTurn(
            "second",
            "bad",
            {"model": "coding-primary", "backend": "omlx-general"},
            (),
            ("http://localhost/a.docx",),
        ),
    ]
    status = uat._status_result(scenario, "required tools did not complete", "chat-9", turns)
    graded = uat._graded_failure(scenario, ["content mismatch"], "chat-9", turns, {"grade": "fail"})
    assert status.status is Status.FAIL and graded.status is Status.FAIL
    assert status.served_model == "coding-primary" and status.backend == "omlx-general"
    assert graded.served_model == "coding-primary" and graded.backend == "omlx-general"
    assert graded.artifacts == ("http://localhost/a.docx",)
    assert graded.evidence == {"grade": "fail"}
