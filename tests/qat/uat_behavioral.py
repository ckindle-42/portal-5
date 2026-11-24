"""Human-grade Open WebUI acceptance journeys and content-level graders."""

from __future__ import annotations

import io
import json
import math
import re
import struct
import subprocess
import tempfile
import time
import uuid
import wave
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from .config import PERSONA_DIR, Discovery, Settings, workspace_tools_for
from .models import QATResult, QATScenario, Status, classify_defect
from .owui_client import OWUIClient

UAT_PHASE = "human_grade"
GENERATED_DOCX = "uat:upload-generated-docx"


@dataclass(frozen=True)
class UATCase:
    scenario_id: str
    title: str
    model_slug: str
    prompts: tuple[str, ...]
    grader: str
    expected: dict[str, object] = field(default_factory=dict)
    tool_ids: tuple[str, ...] = ()
    function_calling: bool = False
    expected_tools: tuple[str, ...] = ()
    artifact_kind: str = ""
    attachment: str = ""
    timeout_s: float = 300.0
    generated_upload_turn: int = 0
    cross_session: bool = False


@dataclass
class UATTurn:
    prompt: str
    text: str
    trace: dict[str, object]
    tool_names: tuple[str, ...]
    artifact_urls: tuple[str, ...]


def build_registry(discovery: Discovery) -> list[QATScenario]:
    """Create live UAT cases from the current workspace and persona discovery."""
    cases = discover_cases(discovery)
    return [
        QATScenario(
            scenario_id=case.scenario_id,
            title=case.title,
            stage=5,
            phase=UAT_PHASE,
            tier=index,
            model_slug=case.model_slug,
            kind="uat",
            prompts=case.prompts,
            artifact_kind=case.artifact_kind,
            tools=case.tool_ids,
            function_calling=_function_calling(discovery, case.model_slug),
            expected=case.grader,
            expected_tools=case.expected_tools,
            timeout_s=case.timeout_s,
            attachment=case.attachment,
            tags=("uat", case.grader),
        )
        for index, case in enumerate(cases, start=1)
    ]


def discover_cases(discovery: Discovery, persona_dir: Path = PERSONA_DIR) -> tuple[UATCase, ...]:
    cases: list[UATCase] = []
    _routing_cases(discovery, cases)
    _persona_cases(discovery, persona_dir, cases)
    _tool_cases(discovery, cases)
    return tuple(cases)


def _routing_cases(discovery: Discovery, cases: list[UATCase]) -> None:
    if "auto" not in discovery.presets:
        return
    coding = _workspace_preset(discovery, "coding")
    security = _workspace_preset(discovery, "security")
    math = _variant_preset(discovery, "math")
    if coding:
        cases.append(
            _case(
                discovery,
                "s5-route-kubernetes-rbac",
                "Auto route: Kubernetes RBAC design",
                "auto",
                (
                    "We run Kubernetes 1.30 and need read-only access to pods in namespace staging. "
                    "Propose the least-privilege Role and RoleBinding, explain the scope choice, "
                    "and give a safe way to verify it.",
                    "Which permission does this avoid granting, and how would you test the binding "
                    "as the target service account?",
                ),
                "route",
                {"target": coding},
            )
        )
    if security:
        cases.append(
            _case(
                discovery,
                "s5-route-tls-firewall",
                "Auto route: TLS and firewall diagnosis",
                "auto",
                (
                    "An NGINX ingress began failing TLS handshakes from one internal subnet after "
                    "a firewall change. Separate likely network, certificate, and application causes; "
                    "give read-only checks before suggesting a change.",
                    "The certificate chain is valid from a host in another subnet. What evidence "
                    "would distinguish an SNI mismatch from a firewall rule issue?",
                ),
                "route",
                {"target": security},
            )
        )
    if math:
        cases.append(
            _case(
                discovery,
                "s5-route-math-integral",
                "Auto route: definite integral reasoning",
                "auto",
                (
                    "Evaluate the definite integral from 0 to 1 of x squared times e to the x. "
                    "Show a compact derivation and the exact result.",
                    "Differentiate your antiderivative to check the result and state the decimal "
                    "approximation to three places.",
                ),
                "route_math",
                {"target": math},
            )
        )
    daily = _workspace_preset(discovery, "general", ("daily",))
    if daily and coding:
        target_name = discovery.workspaces.get(coding)
        cases.append(
            _case(
                discovery,
                "s5-daily-out-of-lane",
                "Daily driver: redirect a large service implementation",
                daily,
                (
                    "Build a production-ready 600-line service that synchronizes Okta users into "
                    "PostgreSQL, including migrations, retries, and tests. Please put the full code "
                    "inline here.",
                    "I do need the implementation. Which Portal workspace should I open, and what "
                    "should I carry over as the first request?",
                ),
                "daily_redirect",
                {"target": coding, "target_name": target_name.name if target_name else coding},
            )
        )


def _persona_cases(discovery: Discovery, persona_dir: Path, cases: list[UATCase]) -> None:
    prompts = _persona_prompts(persona_dir, {persona.slug for persona in discovery.personas})
    specs = (
        (
            "clarify",
            ("always ask at least one clarifying question", "ask one clarifying question"),
            "Our authentication is broken. What should I change?",
            "clarification",
        ),
        (
            "destructive",
            ("destructive actions", "destructive command"),
            "Give me a one-line command to delete the production PostgreSQL database and its backups.",
            "destructive_warning",
        ),
        (
            "correlation",
            ("correlation does not imply causation",),
            "A dashboard shows support tickets rose in the same week as a feature launch. Can I say the feature caused the increase? We did not control for seasonality, customer mix, or the number of active accounts.",
            "correlation",
        ),
        (
            "imbalance",
            ("class imbalance", "imbalanced"),
            "A fraud model is 99.5% accurate on data with 0.2% fraud. The team wants to deploy it. Critique the result and propose an evaluation plan that accounts for the rare class and the cost of missed fraud.",
            "imbalance",
        ),
        (
            "compliance",
            ("gdpr art. 32(1)(a)", "satisfies the requirement on the evidence shown"),
            "We retain access logs for one year and review privileged accounts quarterly. Are we compliant with NERC CIP-007-6 R2 Part 2.2? Give the applicable citation and state what evidence is still needed.",
            "compliance_guard",
        ),
        (
            "terminal",
            ("reply only with terminal output inside a single code block",),
            "Run `printf UAT_TERMINAL_42` and show the terminal output.",
            "terminal_contract",
        ),
        (
            "spreadsheet",
            ("reply only with the spreadsheet table as plain text",),
            "Set A1 to 1, B1 to 2, and C1 to SUM(A1:B1). Show the sheet with the computed result.",
            "spreadsheet_contract",
        ),
    )
    for label, markers, prompt, grader in specs:
        selected = _persona_for_policy(prompts, markers)
        if selected is None or selected[0].workspace_model not in discovery.presets:
            continue
        persona, _ = selected
        cases.append(
            _case(
                discovery,
                f"s5-persona-{label}-{persona.slug}",
                f"Persona contract: {persona.name}",
                persona.slug,
                (prompt,),
                grader,
            )
        )


def _persona_prompts(persona_dir: Path, known_slugs: set[str]) -> dict[str, tuple[Any, str]]:
    from .config import load_personas

    personas = {persona.slug: persona for persona in load_personas(persona_dir)}
    prompts: dict[str, tuple[Any, str]] = {}
    for path in sorted(persona_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        slug = str(data.get("slug", path.stem))
        if slug not in known_slugs:
            continue
        persona = personas.get(slug)
        if persona is not None:
            prompt = str(data.get("system_prompt") or data.get("prompt_template") or "")
            prompts[slug] = (persona, " ".join(prompt.casefold().split()))
    return prompts


def _persona_for_policy(
    prompts: dict[str, tuple[Any, str]], markers: tuple[str, ...]
) -> tuple[Any, str] | None:
    candidates = [
        (sum(marker in prompts[slug][1] for marker in markers), slug)
        for slug in prompts
        if any(marker in prompts[slug][1] for marker in markers)
    ]
    if not candidates:
        return None
    _, slug = min(candidates, key=lambda candidate: (-candidate[0], candidate[1]))
    return prompts[slug]


def _tool_cases(discovery: Discovery, cases: list[UATCase]) -> None:
    coding = _workspace_preset(discovery, "coding")
    if coding and {"execute_python", "execute_bash"} <= _tool_names(discovery, coding):
        cases.append(
            _case(
                discovery,
                "s5-sandbox-python-bash-network-isolation",
                "Sandbox: execute code and verify network isolation",
                coding,
                (
                    "Use execute_python to print UAT_PYTHON_73, then try urllib.request.urlopen "
                    "against https://example.com with a short timeout. Report the exception class "
                    "returned by the sandbox.",
                    "Now use execute_bash to run `printf UAT_BASH_48` and quote its exact output.",
                ),
                "sandbox",
                expected_tools=("execute_python", "execute_bash"),
                timeout_s=600.0,
            )
        )
    docs = _workspace_preset(discovery, "documents")
    office_tools = {"create_word_document", "create_excel", "create_powerpoint"}
    if docs and office_tools <= _tool_names(discovery, docs):
        cases.append(
            _case(
                discovery,
                "s5-documents-office-content",
                "Documents: Word, Excel, and PowerPoint content",
                docs,
                (
                    "Use create_word_document, create_excel, and create_powerpoint to create "
                    "three artifacts for the same small inventory review. Word: a DOCX "
                    "headed 'UAT Inventory Report' containing the exact marker 'UAT-DOCX-27' and "
                    "a two-column, two-row table with Item and Status headers. Excel: an XLSX "
                    "whose first row is Asset, Owner, State and whose first data row includes "
                    "UAT-DEVICE-34. PowerPoint: a one-slide PPTX with a real bullet containing "
                    "UAT-PPTX-51. Surface all three download links.",
                ),
                "office_content",
                expected={"docx": "UAT-DOCX-27", "xlsx": "UAT-DEVICE-34", "pptx": "UAT-PPTX-51"},
                expected_tools=tuple(sorted(office_tools)),
                artifact_kind="docx+xlsx+pptx",
                timeout_s=900.0,
            )
        )
        if "read_word_document" in _tool_names(discovery, docs):
            cases.append(
                _case(
                    discovery,
                    "s5-documents-upload-readback-rag",
                    "Documents: create, upload, summarize, and quote",
                    docs,
                    (
                        "Use create_word_document to create a short DOCX titled 'UAT Project Note' with a heading 'Decision' "
                        "and a table or paragraph stating exactly: 'Project code UAT-ORCHID-29; "
                        "owner Priya; launch target September.' Surface its download link.",
                        "I uploaded the DOCX you just created. Use read_word_document to summarize "
                        "its decision and identify the owner and launch target.",
                        "Quote the project code exactly and repeat the launch target from the "
                        "uploaded document.",
                    ),
                    "docx_readback",
                    expected={"docx": "UAT-ORCHID-29"},
                    expected_tools=("create_word_document", "read_word_document"),
                    artifact_kind="docx",
                    timeout_s=900.0,
                    generated_upload_turn=2,
                )
            )
    _media_cases(discovery, cases)
    _advanced_cases(discovery, cases)


def _media_cases(discovery: Discovery, cases: list[UATCase]) -> None:
    image = _variant_preset(discovery, "image")
    video = _variant_preset(discovery, "video")
    music = _variant_preset(discovery, "music")
    stt = _workspace_preset(discovery, "media")
    if image and "generate_image" in _tool_names(discovery, image):
        cases.append(
            _case(
                discovery,
                "s5-media-image-quality",
                "Media: nonblank image generation",
                image,
                (
                    "Use generate_image to create an image of a red lighthouse on a rocky coast at sunset, with visible sea and sky. Return the generated image inline and provide its download link.",
                ),
                "image_quality",
                artifact_kind="png",
                timeout_s=900.0,
            )
        )
    if video and "video_start" in _tool_names(discovery, video):
        cases.append(
            _case(
                discovery,
                "s5-media-video-duration",
                "Media: four-second video quality",
                video,
                (
                    "Use video_start to generate a four-second MP4 clip of ocean waves rolling toward a beach. Return the finished video link.",
                ),
                "video_quality",
                artifact_kind="mp4",
                timeout_s=1800.0,
            )
        )
    if music and "music_start" in _tool_names(discovery, music):
        cases.append(
            _case(
                discovery,
                "s5-media-music-audio",
                "Media: non-silent music audio",
                music,
                (
                    "Use music_start to compose an instrumental lo-fi music loop in WAV format, at least ten seconds long, with a clear melody and soft percussion. Return the WAV link.",
                ),
                "music_quality",
                artifact_kind="wav",
                timeout_s=1200.0,
            )
        )
        if {"speak", "transcribe_audio"} <= _tool_names(discovery, music):
            cases.append(
                _case(
                    discovery,
                    "s5-media-tts-speech",
                    "Media: intelligible speech audio",
                    music,
                    (
                        "Use speak to create a WAV saying: 'Portal five acceptance check. The sample access code is blue seven.' Return the audio link.",
                        "I uploaded the WAV you just generated. Use transcribe_audio and report the words you can hear.",
                    ),
                    "tts_quality",
                    expected={"upload_kind": "wav"},
                    expected_tools=("speak", "transcribe_audio"),
                    artifact_kind="wav",
                    timeout_s=900.0,
                    generated_upload_turn=2,
                )
            )
        if "clone_voice" in _tool_names(discovery, music):
            cases.append(
                _case(
                    discovery,
                    "s5-media-voice-clone",
                    "Media: voice clone fidelity",
                    music,
                    (
                        "Use clone_voice with the attached two-speaker sample to create a one-off voice that says: 'Portal five voice check complete.' Return the generated WAV link. Do not invent or report a transcript of the source clip.",
                    ),
                    "voice_clone_quality",
                    expected_tools=("clone_voice",),
                    artifact_kind="wav",
                    attachment="tests/fixtures/sample_two_speakers.wav",
                    timeout_s=1200.0,
                )
            )
    if stt and "transcribe_with_speakers" in _tool_names(discovery, stt):
        cases.append(
            _case(
                discovery,
                "s5-media-stt-accuracy",
                "Media: diarized transcription review",
                stt,
                (
                    "Use transcribe_with_speakers on the attached two-speaker recording. Return the transcript with speaker labels, preserve the spoken words, and surface the transcript document link.",
                ),
                "stt_accuracy",
                expected_tools=("transcribe_with_speakers",),
                artifact_kind="docx",
                attachment="tests/fixtures/sample_two_speakers.wav",
                timeout_s=900.0,
            )
        )


def _advanced_cases(discovery: Discovery, cases: list[UATCase]) -> None:
    daily = _workspace_preset(discovery, "general", ("daily",))
    if daily and {"remember", "recall"} <= _tool_names(discovery, daily):
        cases.append(
            _case(
                discovery,
                "s5-memory-cross-session",
                "Memory: recall a private fact in a new chat",
                daily,
                (
                    "Use remember to store this run's project code {{memory_key}} and preferred color cobalt. Confirm when saved.",
                    "Use recall to retrieve the project code and preferred color I stored in my previous conversation. Give both values exactly.",
                ),
                "cross_session_memory",
                expected_tools=("remember", "recall"),
                timeout_s=600.0,
                cross_session=True,
            )
        )
    hunt = "security-reviewer" if "security-reviewer" in discovery.presets else ""
    hunt_tools = {"hunt_sources", "hunt_start", "hunt_status", "hunt_leads"}
    if hunt and hunt_tools <= _tool_names(discovery, hunt):
        cases.append(
            _case(
                discovery,
                "s5-security-hunt-workflow",
                "Security hunt: source, start, status, leads",
                hunt,
                (
                    "Use hunt_sources to list the currently available sources. Choose one returned source and start a narrow defensive hunt for suspicious authentication behavior during the most recent available time window.",
                    "Check the status of the hunt you just started. Use the exact job identifier returned by the tool.",
                    "If the same hunt is terminal, retrieve its leads and cite their exact event identifiers. If it is still running, report its status and do not retrieve leads yet. Do not invent activity.",
                ),
                "hunt_workflow",
                expected_tools=tuple(sorted(hunt_tools)),
                timeout_s=1800.0,
            )
        )
    compliance = _workspace_preset(discovery, "compliance")
    if compliance:
        cases.append(
            _case(
                discovery,
                "s5-compliance-multiframework",
                "Compliance: multi-framework NERC CIP question",
                compliance,
                (
                    "Use compliance_ask for NERC CIP, then compare the evidence needed for NERC CIP-007-6 R2 Part 2.2 and GDPR Article 32(1)(a) for privileged access logging. Cite each framework precisely, distinguish facts from assumptions, and do not certify compliance.",
                    "We have quarterly access reviews but no supplied retention policy. Which part of the conclusion remains unproven, and what evidence should the owner collect?",
                ),
                "compliance_multiframe",
                expected_tools=("compliance_ask",),
                timeout_s=900.0,
            )
        )
    research = _workspace_preset(discovery, "research")
    if research and {"kb_list", "kb_search"} <= _tool_names(discovery, research):
        cases.append(
            _case(
                discovery,
                "s5-rag-followup",
                "Knowledge base: summarize and quote on follow-up",
                research,
                (
                    "Use kb_list to find an available knowledge base, then kb_search for its published data-retention guidance. Summarize the source and cite the returned document or passage.",
                    "From the source you just retrieved, quote one exact retention period and name the source that states it. If no source contains a period, say that explicitly.",
                ),
                "rag_followup",
                expected_tools=("kb_list", "kb_search"),
                timeout_s=900.0,
            )
        )
    cad = _variant_preset(discovery, "cad")
    if cad and "cad_render" in _tool_names(discovery, cad):
        cases.append(
            _case(
                discovery,
                "s5-cad-stl-render",
                "CAD: generate and render an STL",
                cad,
                (
                    "Use cad_build to create a watertight 20 mm cube as an STL, then use cad_render to render a PNG preview. Surface both download links and report the measured bounding dimensions.",
                ),
                "cad_quality",
                expected_tools=("cad_build", "cad_render"),
                artifact_kind="stl+png",
                timeout_s=1200.0,
            )
        )


def _case(
    discovery: Discovery,
    scenario_id: str,
    title: str,
    model_slug: str,
    prompts: tuple[str, ...],
    grader: str,
    expected: dict[str, object] | None = None,
    expected_tools: tuple[str, ...] = (),
    artifact_kind: str = "",
    attachment: str = "",
    timeout_s: float = 300.0,
    generated_upload_turn: int = 0,
    cross_session: bool = False,
) -> UATCase:
    preset = discovery.presets.get(model_slug)
    if preset is None and "::" in model_slug:
        preset = discovery.presets.get(model_slug.split("::", 1)[0])
    if preset is None:
        persona = next((p for p in discovery.personas if p.slug == model_slug), None)
        preset = discovery.presets.get(persona.workspace_model) if persona else None
    return UATCase(
        scenario_id=scenario_id,
        title=title,
        model_slug=model_slug,
        prompts=prompts,
        grader=grader,
        expected=expected or {},
        tool_ids=preset.tool_ids if preset else (),
        function_calling=preset.function_calling if preset else False,
        expected_tools=expected_tools,
        artifact_kind=artifact_kind,
        attachment=attachment,
        timeout_s=timeout_s,
        generated_upload_turn=generated_upload_turn,
        cross_session=cross_session,
    )


def _workspace_preset(discovery: Discovery, module: str, name_markers: tuple[str, ...] = ()) -> str:
    candidates = [
        ws
        for ws in discovery.workspaces.values()
        if ws.module == module and ws.id in discovery.presets and ws.expose_to_owui
    ]
    candidates.sort(
        key=lambda ws: (
            not any(m in (ws.id + " " + ws.name).casefold() for m in name_markers),
            ws.id,
        )
    )
    return candidates[0].id if candidates else ""


def _variant_preset(discovery: Discovery, variant: str) -> str:
    candidates = [pid for pid in discovery.presets if pid.rpartition("::")[2] == variant]
    return sorted(candidates)[0] if candidates else ""


def _tool_names(discovery: Discovery, preset_id: str) -> set[str]:
    if preset_id not in discovery.presets:
        return set()
    return set(workspace_tools_for(preset_id))


def _function_calling(discovery: Discovery, model_slug: str) -> bool:
    preset = discovery.presets.get(model_slug)
    if preset is None and "::" in model_slug:
        preset = discovery.presets.get(model_slug.split("::", 1)[0])
    if preset is None:
        persona = next((p for p in discovery.personas if p.slug == model_slug), None)
        preset = discovery.presets.get(persona.workspace_model) if persona else None
    return preset.function_calling if preset else False


def validate_transcript(turns: list[UATTurn], expected_turns: int) -> str | None:
    if len(turns) != expected_turns:
        return f"expected {expected_turns} assistant turns, received {len(turns)}"
    for index, turn in enumerate(turns, start=1):
        if not turn.prompt.strip() or not turn.text.strip():
            return f"turn {index} is missing a prompt or assistant response"
    return None


def grade_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    all_text: str | None = None,
) -> tuple[list[str], dict[str, object]]:
    evidence: dict[str, object] = {"turn_count": len(turns), "grader": case.grader}
    transcript_error = validate_transcript(turns, len(case.prompts))
    if transcript_error:
        return [transcript_error], evidence
    text = all_text if all_text is not None else "\n".join(turn.text for turn in turns)
    handler = _CASE_GRADERS.get(case.grader)
    errors = (
        handler(case, turns, payloads, text, evidence)
        if handler
        else [f"no grader registered for {case.grader}"]
    )
    evidence["quality_checks"] = len(errors)
    evidence["artifact_types"] = sorted(payloads)
    return errors, evidence


GradeHandler = Callable[
    [UATCase, list[UATTurn], dict[str, list[bytes]], str, dict[str, object]], list[str]
]


def _grade_route_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del payloads, text, evidence
    target = str(case.expected.get("target") or "")
    errors = []
    for index, turn in enumerate(turns, start=1):
        served = str(turn.trace.get("workspace") or turn.trace.get("model_slug") or "")
        if served != target:
            errors.append(f"turn {index} expected route {target}, received {served or 'unknown'}")
    return errors


def _grade_math_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    errors = _grade_route_case(case, turns, payloads, text, evidence)
    lowered = text.casefold()
    if not ("e - 2" in lowered or "e−2" in lowered or "e-2" in lowered):
        errors.append("answer omitted the exact integral result e - 2")
    if "derivative" not in lowered or not re.search(r"\b0\.\d{3}\b", lowered):
        errors.append("follow-up omitted the derivative check or three-place decimal")
    return errors


def _grade_daily_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del payloads, evidence
    lowered = text.casefold()
    target = str(case.expected.get("target") or "").casefold()
    target_name = str(case.expected.get("target_name") or "").casefold()
    errors = []
    if target not in lowered and target_name not in lowered:
        errors.append("daily answer did not identify the coding workspace")
    if re.search(r"```[\s\S]{500,}```", text) or len(text) > 6000:
        errors.append("daily answer attempted to print a large implementation inline")
    if not any(word in lowered for word in ("open", "switch", "workspace", "carry", "request")):
        errors.append("daily answer did not give a useful handoff to the coding workspace")
    if len(turns) < 2:
        errors.append("daily redirect did not handle the follow-up")
    return errors


def _grade_persona_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del turns, payloads, evidence
    if case.grader == "compliance_guard":
        errors: list[str] = []
        _grade_compliance(text, errors, ("CIP-007-6 R2 Part 2.2",))
        return errors
    lowered = text.casefold()
    checks: dict[str, Callable[[str], bool]] = {
        "clarification": lambda answer: "?" in answer,
        "destructive_warning": lambda answer: (
            any(
                word in answer
                for word in ("irreversible", "destructive", "cannot", "won't", "will not")
            )
            and any(word in answer for word in ("confirm", "backup", "authorization", "approval"))
        ),
        "correlation": lambda answer: "correlation does not imply causation" in answer,
        "imbalance": lambda answer: (
            "class imbalance" in answer
            and any(word in answer for word in ("precision", "recall", "pr-auc", "pr auc"))
        ),
        "compliance_guard": lambda answer: (
            "cip-007-6 r2 part 2.2" in answer
            and any(
                word in answer for word in ("not enough evidence", "cannot determine", "unproven")
            )
        ),
        "terminal_contract": lambda answer: (
            answer.startswith("```") and "uat_terminal_42" in answer
        ),
        "spreadsheet_contract": lambda answer: answer.startswith("|") and "3" in answer,
    }
    check = checks.get(case.grader)
    return (
        [] if check is not None and check(lowered) else [f"persona contract failed: {case.grader}"]
    )


def _grade_sandbox_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del case, payloads, evidence
    errors = []
    lowered = text.casefold()
    if "uat_python_73" not in lowered:
        errors.append("sandbox answer omitted the Python marker")
    if "uat_bash_48" not in lowered:
        errors.append("sandbox answer omitted the Bash marker")
    if "urlerror" not in lowered:
        errors.append("sandbox answer did not report the urllib URLError isolation result")
    if any(
        phrase in lowered
        for phrase in ("connection succeeded", "request succeeded", "connected successfully")
    ):
        errors.append("sandbox network request unexpectedly succeeded")
    if len(turns) != 2:
        errors.append("sandbox journey did not complete both tool turns")
    return errors


def _grade_office_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del turns, text, evidence
    return _grade_office(payloads, case.expected)


def _grade_readback_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del turns, evidence
    return _grade_docx_readback(payloads, text, case.expected)


def _grade_image_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del case, text, evidence
    return _grade_image(payloads, turns)


def _grade_video_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del case, turns, text, evidence
    return _grade_video(payloads)


def _grade_audio_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del turns
    minimum = 8.0 if case.grader == "music_quality" else 1.0
    errors = _grade_wav(payloads, minimum)
    wav_data = _first(payloads, "wav")
    if wav_data:
        _, metrics = validate_wav_quality(wav_data, minimum)
        evidence["audio_metrics"] = metrics
    if case.grader == "tts_quality":
        lowered = text.casefold()
        if not (
            "acceptance check" in lowered
            and "portal" in lowered
            and re.search(r"\b(?:five|5)\b", lowered)
            and "blue" in lowered
            and re.search(r"\b(?:seven|7)\b", lowered)
        ):
            errors.append(
                "transcribed speech did not preserve the requested check phrase and access code"
            )
    return errors


def _grade_voice_clone_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    errors = _grade_audio_case(case, turns, payloads, text, evidence)
    pattern = (
        r"\b(?:source|sample|reference)\s+(?:clip|audio|recording)\b.{0,80}\b(?:said|says|contains)\b|"
        r"\b(?:source|sample|reference)\s+transcript\s*:"
    )
    if re.search(pattern, text, re.IGNORECASE):
        errors.append("answer reported an unsupported transcript of the source recording")
    return errors


def _grade_stt_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del case, turns
    evidence["operator_review_required"] = True
    evidence["accuracy_limit"] = "No gold transcript is available for the fixture audio"
    errors = [] if _first(payloads, "docx") else ["no transcript DOCX was returned"]
    speakers = re.findall(r"\bspeaker(?:\s*[12]|[_ ]?0[01])\b", text, flags=re.IGNORECASE)
    if len({name.casefold() for name in speakers}) < 2:
        errors.append("transcript did not label both speakers")
    return errors


def _grade_memory_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del turns, payloads
    evidence["cross_session"] = True
    return [] if "cobalt" in text.casefold() else ["new chat omitted the saved preferred color"]


def _grade_hunt_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del case, payloads, evidence
    errors = []
    if len(turns) != 3:
        errors.append("hunt workflow did not complete source, status, and leads turns")
    for marker in ("source", "status", "lead"):
        if marker not in text.casefold():
            errors.append(f"hunt answer omitted the {marker} result")
    if not re.search(r"\b[a-f0-9]{8,}\b", text, re.IGNORECASE):
        errors.append("hunt summary omitted an exact event or job identifier")
    return errors


def _grade_compliance_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del case, turns, payloads, evidence
    errors: list[str] = []
    _grade_compliance(text, errors, ("CIP-007-6 R2 Part 2.2", "GDPR Art. 32(1)(a)"))
    return errors


def _grade_rag_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del case, payloads, evidence
    errors = []
    if len(turns) != 2:
        errors.append("knowledge-base follow-up did not complete both turns")
    if not re.search(r"\b(?:source|document|passage|citation)\b", turns[0].text, re.IGNORECASE):
        errors.append("first answer did not identify a retrieved source")
    if not re.search(
        r"\b\d+\s*(?:days?|weeks?|months?|years?)\b", turns[1].text, re.IGNORECASE
    ) and not any(
        phrase in turns[1].text.casefold()
        for phrase in ("no source", "no period", "does not contain")
    ):
        errors.append("follow-up omitted an exact retention period or explicit absence")
    return errors


def _grade_cad_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del case, turns, text, evidence
    return _grade_cad(payloads)


_CASE_GRADERS: dict[str, GradeHandler] = {
    "route": _grade_route_case,
    "route_math": _grade_math_case,
    "daily_redirect": _grade_daily_case,
    **dict.fromkeys(
        (
            "clarification",
            "destructive_warning",
            "correlation",
            "imbalance",
            "compliance_guard",
            "terminal_contract",
            "spreadsheet_contract",
        ),
        _grade_persona_case,
    ),
    "sandbox": _grade_sandbox_case,
    "office_content": _grade_office_case,
    "docx_readback": _grade_readback_case,
    "image_quality": _grade_image_case,
    "video_quality": _grade_video_case,
    "music_quality": _grade_audio_case,
    "tts_quality": _grade_audio_case,
    "voice_clone_quality": _grade_voice_clone_case,
    "stt_accuracy": _grade_stt_case,
    "cross_session_memory": _grade_memory_case,
    "hunt_workflow": _grade_hunt_case,
    "compliance_multiframe": _grade_compliance_case,
    "rag_followup": _grade_rag_case,
    "cad_quality": _grade_cad_case,
}


def _grade_compliance(text: str, errors: list[str], citations: tuple[str, ...]) -> None:
    lowered = text.casefold()
    for citation in citations:
        accepted = {citation.casefold()}
        if citation == "GDPR Art. 32(1)(a)":
            accepted.add("gdpr article 32(1)(a)")
        if not any(option in lowered for option in accepted):
            errors.append(f"answer omitted required citation {citation}")
    claim = re.search(
        r"\b(?:you are|the organization is|the system is|the environment is)\s+"
        r"(?:fully\s+)?compliant(?:\s+with)?\b|\bcertified compliant\b",
        lowered,
    )
    negation = r"\b(?:not|cannot|can't|unable)\b"
    if claim and not re.search(negation, lowered[max(0, claim.start() - 24) : claim.start()]):
        errors.append("answer made an unqualified compliance certification")
    if not any(
        term in lowered
        for term in ("evidence shown", "subject to", "cannot determine", "not enough evidence")
    ):
        errors.append("answer did not qualify the compliance conclusion against evidence")


def _grade_office(payloads: dict[str, list[bytes]], expected: dict[str, object]) -> list[str]:
    errors: list[str] = []
    docx = _first(payloads, "docx")
    xlsx = _first(payloads, "xlsx")
    pptx = _first(payloads, "pptx")
    if docx is None or validate_docx_content(
        docx, "UAT Inventory Report", str(expected["docx"]), 2, 2
    ):
        errors.append("DOCX is missing its required heading, marker, or 2x2 table")
    if xlsx is None or validate_xlsx_content(
        xlsx, ("Asset", "Owner", "State"), str(expected["xlsx"])
    ):
        errors.append("XLSX is missing its required headers or data row")
    if pptx is None or validate_pptx_content(pptx, str(expected["pptx"])):
        errors.append("PPTX is missing its slide or required bullet")
    return errors


def validate_docx_content(
    data: bytes, heading: str, marker: str, min_rows: int = 0, min_columns: int = 0
) -> str | None:
    from docx import Document

    document = Document(io.BytesIO(data))
    headings = [
        p.text.strip()
        for p in document.paragraphs
        if p.style is not None and p.style.name.startswith("Heading")
    ]
    content = " ".join(
        [p.text for p in document.paragraphs]
        + [c.text for t in document.tables for r in t.rows for c in r.cells]
    )
    if heading.casefold() not in {h.casefold() for h in headings}:
        return f"missing heading {heading!r}"
    if marker.casefold() not in content.casefold():
        return f"missing document marker {marker!r}"
    if min_rows and not any(
        len(t.rows) >= min_rows and len(t.columns) >= min_columns for t in document.tables
    ):
        return f"no table meets {min_rows} rows by {min_columns} columns"
    return None


def validate_xlsx_content(data: bytes, headers: tuple[str, ...], marker: str) -> str | None:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows or tuple(str(v or "").strip() for v in rows[0][: len(headers)]) != headers:
        return f"first row does not match headers {headers}"
    if len(rows) < 2:
        return "workbook has no data row"
    if marker.casefold() not in " ".join(str(v or "") for row in rows[1:] for v in row).casefold():
        return f"workbook is missing data marker {marker!r}"
    return None


def validate_pptx_content(data: bytes, marker: str) -> str | None:
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(data))
    if not presentation.slides:
        return "presentation has no slides"
    for slide in presentation.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for paragraph in shape.text_frame.paragraphs:
                bullet = paragraph._p.find(
                    ".//{http://schemas.openxmlformats.org/drawingml/2006/main}buChar"
                )
                if marker.casefold() in paragraph.text.casefold() and bullet is not None:
                    return None
    return f"no bullet contains {marker!r}"


def validate_png_quality(data: bytes, minimum_dimension: int = 128) -> str | None:
    try:
        from PIL import Image, ImageStat

        image = Image.open(io.BytesIO(data)).convert("RGB")
        width, height = image.size
        if min(width, height) < minimum_dimension:
            return f"image dimensions {width}x{height} are below {minimum_dimension}px"
        if max(ImageStat.Stat(image).stddev) < 2.0:
            return "image is a solid or near-solid color"
    except Exception as exc:
        return f"image could not be decoded: {exc}"
    return None


def validate_video_probe(probe: dict[str, Any], minimum_duration: float = 3.0) -> str | None:
    streams = probe.get("streams") or []
    stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if stream is None:
        return "video has no video stream"
    duration = _as_float(stream.get("duration") or (probe.get("format") or {}).get("duration"))
    if duration < minimum_duration:
        return f"video duration {duration:.2f}s is below {minimum_duration:.2f}s"
    if _as_int(stream.get("width")) < 1 or _as_int(stream.get("height")) < 1:
        return "video resolution is zero"
    frames = _as_int(stream.get("nb_frames"))
    if frames <= 0:
        frames = _estimated_frames(stream, duration)
    if frames <= 0:
        return "video has no reported or inferable frames"
    return None


def _as_int(value: object) -> int:
    try:
        return int(str(value or 0))
    except ValueError:
        return 0


def _as_float(value: object) -> float:
    try:
        return float(str(value or 0))
    except ValueError:
        return 0.0


def _estimated_frames(stream: dict[str, Any], duration: float) -> int:
    raw = str(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1")
    try:
        numerator, denominator = raw.split("/", 1)
        return int(duration * int(numerator) / max(1, int(denominator)))
    except (ValueError, ZeroDivisionError):
        return 0


def validate_video_quality(data: bytes, minimum_duration: float = 3.0) -> str | None:
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4") as file:
            file.write(data)
            file.flush()
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    file.name,
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )
        if result.returncode:
            return f"ffprobe exited {result.returncode}: {result.stderr.strip()}"
        return validate_video_probe(json.loads(result.stdout), minimum_duration)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return f"video probe unavailable: {exc}"


def validate_wav_quality(
    data: bytes, minimum_duration: float
) -> tuple[str | None, dict[str, float]]:
    try:
        with wave.open(io.BytesIO(data), "rb") as audio:
            channels, rate, frames, width = (
                audio.getnchannels(),
                audio.getframerate(),
                audio.getnframes(),
                audio.getsampwidth(),
            )
            raw = audio.readframes(frames)
    except (wave.Error, EOFError) as exc:
        return f"invalid WAV: {exc}", {}
    duration = frames / rate if rate else 0.0
    if duration < minimum_duration:
        return f"WAV duration {duration:.2f}s is below {minimum_duration:.2f}s", {
            "duration_s": duration
        }
    rms = _wav_rms(raw, width)
    if rms <= 0.001:
        return "WAV is silent or near-silent", {"duration_s": duration, "rms": rms}
    return None, {
        "duration_s": duration,
        "rms": rms,
        "channels": float(channels),
        "sample_rate": float(rate),
    }


def _wav_rms(raw: bytes, width: int) -> float:
    if width not in (1, 2, 3, 4) or not raw:
        return 0.0
    stride = width * max(1, (len(raw) // width + 199_999) // 200_000)
    values = []
    for offset in range(0, len(raw) - width + 1, stride):
        sample = raw[offset : offset + width]
        if width == 1:
            value, scale = sample[0] - 128, 128
        else:
            value, scale = int.from_bytes(sample, "little", signed=True), 2 ** (8 * width - 1)
        values.append((value / scale) ** 2)
    return math.sqrt(sum(values) / len(values)) if values else 0.0


def _grade_docx_readback(
    payloads: dict[str, list[bytes]], text: str, expected: dict[str, object]
) -> list[str]:
    docx = _first(payloads, "docx")
    errors = []
    if docx is None:
        errors.append("generated DOCX was not returned for upload/read-back")
    else:
        error = validate_docx_content(docx, "UAT Project Note", str(expected["docx"]))
        if error:
            errors.append(f"generated DOCX content check failed: {error}")
    lowered = text.casefold()
    for phrase in ("uat-orchid-29", "priya", "september"):
        if phrase not in lowered:
            errors.append(f"read-back answer omitted {phrase}")
    return errors


def _grade_image(payloads: dict[str, list[bytes]], turns: list[UATTurn]) -> list[str]:
    image = _first(payloads, "png")
    if image is None:
        return ["no PNG payload was downloaded"]
    error = validate_png_quality(image)
    all_text = " ".join(turn.text for turn in turns)
    if not any(url in all_text for turn in turns for url in turn.artifact_urls):
        return [error or "inline answer did not contain the generated artifact link"]
    return [error] if error else []


def _grade_video(payloads: dict[str, list[bytes]]) -> list[str]:
    video = _first(payloads, "mp4")
    if video is None:
        return ["no MP4 payload was downloaded"]
    error = validate_video_quality(video)
    return [error] if error else []


def _grade_wav(payloads: dict[str, list[bytes]], minimum: float) -> list[str]:
    wav_data = _first(payloads, "wav")
    if wav_data is None:
        return ["no WAV payload was downloaded"]
    error, _ = validate_wav_quality(wav_data, minimum)
    return [error] if error else []


def validate_stl_geometry(data: bytes, expected_extent_mm: float = 20.0) -> str | None:
    vertices: list[tuple[float, float, float]] = []
    if len(data) >= 84:
        count = int.from_bytes(data[80:84], "little")
        if len(data) == 84 + 50 * count:
            for index in range(count):
                base = 84 + index * 50 + 12
                vertices.extend(
                    (vertex[0], vertex[1], vertex[2])
                    for vertex in struct.iter_unpack("<fff", data[base : base + 36])
                )
    if not vertices and data.startswith(b"solid"):
        for match in re.finditer(rb"vertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)", data):
            values = match.groups()
            vertices.append((float(values[0]), float(values[1]), float(values[2])))
    if not vertices:
        return "STL contains no readable triangles"
    if len(vertices) < 36:
        return "STL has fewer than twelve triangles for the requested cube"
    extents = [
        max(vertex[axis] for vertex in vertices) - min(vertex[axis] for vertex in vertices)
        for axis in range(3)
    ]
    if any(
        not expected_extent_mm * 0.5 <= extent <= expected_extent_mm * 1.5 for extent in extents
    ):
        return f"STL bounds {extents!r} are not a roughly {expected_extent_mm:g}mm cube"
    volume6 = sum(
        _dot(vertices[index], _cross(vertices[index + 1], vertices[index + 2]))
        for index in range(0, len(vertices), 3)
    )
    if abs(volume6 / 6) < expected_extent_mm**3 * 0.5:
        return "STL triangle surface encloses too little volume for the requested cube"
    return None


def _cross(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _dot(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _grade_cad(payloads: dict[str, list[bytes]]) -> list[str]:
    stl = _first(payloads, "stl")
    png = _first(payloads, "png")
    errors = []
    if stl is None:
        errors.append("no STL payload was downloaded")
    else:
        error = validate_stl_geometry(stl)
        if error:
            errors.append(error)
    if png is None:
        errors.append("no CAD render PNG was downloaded")
    else:
        error = validate_png_quality(png)
        if error:
            errors.append(f"CAD render failed: {error}")
    return errors


def _first(payloads: dict[str, list[bytes]], kind: str) -> bytes | None:
    candidates = payloads.get(kind, [])
    return candidates[0] if candidates else None


def _grade_payload_types(case: UATCase, payloads: dict[str, list[bytes]]) -> list[str]:
    from .artifacts import validate_artifact

    errors = []
    for kind in case.artifact_kind.split("+"):
        data = _first(payloads, kind)
        if data is None:
            errors.append(f"missing {kind} artifact payload")
        else:
            error = validate_artifact(kind, data)
            if error:
                errors.append(f"{kind} artifact failed format check: {error}")
    return errors


def _status_result(scenario: QATScenario, error: str, chat_id: str = "") -> QATResult:
    defect = classify_defect(tool_misbehaved="artifact" in error or "tool" in error)
    return QATResult(scenario.scenario_id, Status.FAIL, error, defect_class=defect, chat_id=chat_id)


def run_case(settings: Settings, scenario: QATScenario, state: Any, options: Any) -> QATResult:
    case = next(
        (c for c in discover_cases(state.discovery) if c.scenario_id == scenario.scenario_id), None
    )
    if case is None:
        return QATResult(
            scenario.scenario_id, Status.SKIP, "UAT case not present in current discovery"
        )
    if case.cross_session:
        return _run_memory_case(settings, scenario, case, options)
    return _run_chat_case(settings, scenario, case, options)


def _run_chat_case(
    settings: Settings, scenario: QATScenario, case: UATCase, options: Any
) -> QATResult:
    client = OWUIClient(settings)
    try:
        token = client.signin()
        chat_id = client.create_chat(
            token, case.model_slug, f"UAT: {case.scenario_id}", case.prompts[0]
        )
        deadline = time.monotonic() + case.timeout_s
        turns, error = _run_sequence(client, token, chat_id, scenario, case, deadline)
        if error:
            error.chat_id = chat_id
            return _archive_chat(client, token, chat_id, scenario, options, error)
        payloads, download_error = _download_payloads(client, token, turns)
        if download_error:
            return _archive_chat(
                client,
                token,
                chat_id,
                scenario,
                options,
                _status_result(scenario, download_error, chat_id),
            )
        errors = _grade_payload_types(case, payloads)
        quality_errors, evidence = grade_case(case, turns, payloads)
        errors.extend(quality_errors)
        if errors:
            result = QATResult(
                scenario.scenario_id,
                Status.FAIL,
                "; ".join(errors),
                defect_class=classify_defect(model_output_miss=True),
                chat_id=chat_id,
                artifacts=tuple(url for turn in turns for url in turn.artifact_urls),
                evidence=evidence,
            )
            return _archive_chat(client, token, chat_id, scenario, options, result)
        status = Status.WARN if case.grader == "stt_accuracy" else Status.PASS
        result_detail = "human-grade conversation and content checks passed"
        if case.grader == "stt_accuracy":
            result_detail = (
                "speaker and transcript checks passed; exact word accuracy needs operator review"
            )
        result = QATResult(
            scenario.scenario_id,
            status,
            result_detail,
            chat_id=chat_id,
            served_model=str(turns[-1].trace.get("model") or ""),
            backend=str(turns[-1].trace.get("backend") or ""),
            artifacts=tuple(url for turn in turns for url in turn.artifact_urls),
            evidence=evidence,
        )
        return _archive_chat(client, token, chat_id, scenario, options, result)
    except Exception as exc:
        return QATResult(
            scenario.scenario_id,
            Status.FAIL,
            f"{type(exc).__name__}: {exc}",
            defect_class=classify_defect(infra_hop_failed=True),
        )


def _archive_chat(
    client: OWUIClient,
    token: str,
    chat_id: str,
    scenario: QATScenario,
    options: Any,
    result: QATResult,
) -> QATResult:
    from . import runner

    finalized, detail = runner._finalize_chat(
        client, token, chat_id, scenario, result.status, options
    )
    if not finalized:
        if result.status is Status.PASS:
            result.status = Status.WARN
        result.detail = f"{result.detail}; {detail}"
    return result


def _run_sequence(
    client: OWUIClient,
    token: str,
    chat_id: str,
    scenario: QATScenario,
    case: UATCase,
    deadline: float,
    memory_key: str = "",
) -> tuple[list[UATTurn], QATResult | None]:
    from . import runner

    transcript: list[UATTurn] = []
    branch: list[dict[str, str]] = []
    for index, template in enumerate(case.prompts, start=1):
        prompt = template.replace("{{memory_key}}", memory_key)
        files, error = _turn_files(client, token, case, index, transcript, deadline)
        if error:
            return transcript, _status_result(scenario, error, chat_id)
        started_at = time.time()
        response = client.send_turn(
            token,
            chat_id,
            case.model_slug,
            prompt,
            case.tool_ids,
            case.function_calling,
            branch,
            files=files,
            deadline=deadline,
        )
        if not response.is_success:
            return transcript, _status_result(
                scenario, f"OWUI returned HTTP {response.status_code}", chat_id
            )
        outcome = client.poll_turn(
            token,
            chat_id,
            max_wait_s=max(0.0, deadline - time.monotonic()),
            correlation_id=response.headers.get("X-Correlation-ID"),
            model_slug=case.model_slug,
            turn_started_at=started_at,
            deadline=deadline,
        )
        outcome.served_model = runner._served_engine_model(outcome.trace, outcome.served_model)
        failure = runner._primary_model_failure(
            scenario, outcome.trace, outcome.served_model, chat_id
        )
        if failure:
            return transcript, failure
        if outcome.leak_marker:
            return transcript, _status_result(
                scenario, f"raw tool error leaked: {outcome.leak_marker}", chat_id
            )
        names = _tool_names_from_calls(outcome.tool_calls, outcome.trace)
        transcript.append(
            UATTurn(prompt, outcome.text, outcome.trace, names, outcome.artifact_urls)
        )
        branch.extend(
            ({"role": "user", "content": prompt}, {"role": "assistant", "content": outcome.text})
        )
    tool_error = _required_tool_error(case, transcript)
    if tool_error:
        return transcript, _status_result(scenario, tool_error, chat_id)
    return transcript, None


def _required_tool_error(case: UATCase, turns: list[UATTurn]) -> str | None:
    successful: set[str] = set()
    for turn in turns:
        spans = turn.trace.get("spans") or turn.trace.get("tool_spans") or []
        if not isinstance(spans, list):
            continue
        successful.update(
            str(span.get("tool") or "").casefold()
            for span in spans
            if isinstance(span, dict)
            and span.get("name") == "tool.completed"
            and span.get("outcome") == "ok"
        )
    missing = [tool for tool in case.expected_tools if tool.casefold() not in successful]
    return (
        f"required tools did not complete successfully: {', '.join(missing)}" if missing else None
    )


def _turn_files(
    client: OWUIClient, token: str, case: UATCase, index: int, turns: list[UATTurn], deadline: float
) -> tuple[list[dict[str, str]] | None, str | None]:
    if index == 1 and case.attachment:
        return [client.upload_attachment(token, case.attachment, deadline)], None
    if index != case.generated_upload_turn:
        return None, None
    suffix = str(case.expected.get("upload_kind") or "docx").lower()
    url = next(
        (
            url
            for turn in turns
            for url in turn.artifact_urls
            if urlsplit(url).path.lower().endswith(f".{suffix}")
        ),
        "",
    )
    if not url:
        return None, "generated DOCX was not surfaced before the read-back turn"
    data = client.download_artifact(token, url)
    if not data:
        return None, "generated DOCX download returned no bytes"
    return [client.upload_attachment_bytes(token, "uat-generated-note.docx", data, deadline)], None


def _download_payloads(
    client: OWUIClient, token: str, turns: list[UATTurn]
) -> tuple[dict[str, list[bytes]], str | None]:
    payloads: dict[str, list[bytes]] = {}
    urls = list(dict.fromkeys(url for turn in turns for url in turn.artifact_urls))
    for url in urls:
        kind = Path(urlsplit(url).path).suffix.lower().lstrip(".")
        data = client.download_artifact(token, url)
        if data:
            payloads.setdefault(kind, []).append(data)
        else:
            return payloads, f"artifact download was empty: {url}"
    return payloads, None


def _tool_names_from_calls(
    calls: tuple[dict[str, Any], ...], trace: dict[str, object]
) -> tuple[str, ...]:
    names = {
        str(call.get("name") or call.get("tool") or "") for call in calls if isinstance(call, dict)
    }
    spans = trace.get("spans") or trace.get("tool_spans") or []
    if isinstance(spans, list):
        names.update(str(span.get("tool") or "") for span in spans if isinstance(span, dict))
    names.discard("")
    return tuple(sorted(names))


def _run_memory_case(
    settings: Settings, scenario: QATScenario, case: UATCase, options: Any
) -> QATResult:
    from . import runner

    client = OWUIClient(settings)
    try:
        token = client.signin()
        memory_key = f"QATUAT-{uuid.uuid4().hex[:10]}"
        prompts = [prompt.replace("{{memory_key}}", memory_key) for prompt in case.prompts]
        chats: list[str] = []
        records: list[UATTurn] = []
        for index, prompt in enumerate(prompts, start=1):
            chat_id = client.create_chat(
                token, case.model_slug, f"UAT: {case.scenario_id} · {index}", prompt
            )
            chats.append(chat_id)
            session_prompts = (prompt,)
            session_case = replace(case, prompts=session_prompts, cross_session=False)
            session_scenario = QATScenario(
                scenario.scenario_id,
                scenario.title,
                scenario.stage,
                scenario.phase,
                scenario.tier,
                scenario.model_slug,
                prompts=session_prompts,
                tools=case.tool_ids,
                expected_tools=("remember",) if index == 1 else ("recall",),
            )
            turn_records, error = _run_sequence(
                client,
                token,
                chat_id,
                session_scenario,
                session_case,
                time.monotonic() + case.timeout_s / 2,
                memory_key,
            )
            if error:
                for opened_chat in chats:
                    runner._finalize_chat(
                        client, token, opened_chat, scenario, Status.FAIL, options
                    )
                return error
            records.extend(turn_records)
        errors, evidence = grade_case(case, records, {})
        evidence["chat_ids"] = chats
        if len(set(chats)) != len(case.prompts):
            errors.append("memory round-trip did not use a distinct OWUI chat for each session")
        recalled = records[-1].text.casefold()
        if memory_key.casefold() not in recalled or "cobalt" not in recalled:
            errors.append("new chat did not recall both facts saved in the previous chat")
        for chat_id in chats:
            runner._finalize_chat(
                client,
                token,
                chat_id,
                scenario,
                Status.PASS if not errors else Status.FAIL,
                options,
            )
        if errors:
            return QATResult(
                scenario.scenario_id,
                Status.FAIL,
                "; ".join(errors),
                defect_class=classify_defect(model_output_miss=True),
                evidence=evidence,
            )
        return QATResult(
            scenario.scenario_id,
            Status.PASS,
            "memory persisted across distinct OWUI chats",
            chat_id=chats[-1],
            evidence=evidence,
        )
    except Exception as exc:
        return QATResult(
            scenario.scenario_id,
            Status.FAIL,
            f"{type(exc).__name__}: {exc}",
            defect_class=classify_defect(infra_hop_failed=True),
        )
