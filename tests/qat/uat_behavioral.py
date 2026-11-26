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
import unicodedata
import uuid
import wave
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import yaml

from .artifacts import raw_tool_error_leak, validate_pdf, wav_magic_error
from .browser_ui import BrowserUI, PlaywrightUnavailable
from .config import PERSONA_DIR, REPO_ROOT, Discovery, Settings, workspace_tools_for
from .models import DefectClass, QATResult, QATScenario, Status, classify_defect
from .owui_client import ArtifactDownloadError, OWUIClient, artifact_urls

UAT_PHASE = "human_grade"
#: Stage 5 must cascade after Stage 4 (tier 200); tier=index collided with Stage 1/2 tiers.
UAT_TIER_BASE = 300
#: Committed 2-speaker WAV. Follow-up turns upload this, never a generated file.
REAL_WAV_FIXTURE = "tests/fixtures/sample_two_speakers.wav"
GENERATED_DOCX = "uat:upload-generated-docx"
_ROUTE_MEMORY_SEED = (
    "Security incident response, CVE exploits, purple-team exercises, and firewall analysis."
)
#: The product STT path: the host MLX transcribe service OWUI itself calls (:8924).
TRANSCRIBE_URL = "http://127.0.0.1:8924/v1/audio/transcriptions"
#: Harness-ASR vs transcript word-overlap floor for stt_accuracy (not human WER).
_ASR_WORD_OVERLAP_FLOOR = 0.8
_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}


def transcribe_wav(data: bytes, filename: str = "artifact.wav") -> str:
    """Transcribe audio bytes through the platform STT path (host :8924)."""
    with httpx.Client(timeout=600.0) as client:
        response = client.post(TRANSCRIBE_URL, files={"file": (filename, data, "audio/wav")})
    if response.status_code != 200:
        raise RuntimeError(f"transcribe service returned HTTP {response.status_code}")
    return str(response.json().get("text", "")).strip()


def _spoken_words(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.casefold())
    return [_NUMBER_WORDS.get(word, word) for word in words]


def _missing_speech_words(requested: str, heard: str) -> list[str]:
    heard_words = set(_spoken_words(heard))
    return [word for word in _spoken_words(requested) if word not in heard_words]


def _word_overlap(gold: str, candidate: str) -> float:
    words = set(_spoken_words(gold))
    if not words:
        return 1.0
    present = words & set(_spoken_words(candidate))
    return len(present) / len(words)


def _docx_text(data: bytes) -> str:
    try:
        from docx import Document

        document = Document(io.BytesIO(data))
        return "\n".join(
            [p.text for p in document.paragraphs]
            + [c.text for t in document.tables for r in t.rows for c in r.cells]
        )
    except Exception:
        return ""


def _gold_transcript(attachment: str) -> str:
    """Harness ASR of the fixture audio; "" when no fixture or service is available."""
    if not attachment:
        return ""
    path = Path(attachment)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.is_file():
        return ""
    try:
        return transcribe_wav(path.read_bytes(), path.name)
    except Exception:
        return ""


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
    roster_check: bool = False
    owui_memories: tuple[str, ...] = ()


@dataclass
class UATTurn:
    prompt: str
    text: str
    trace: dict[str, object]
    tool_names: tuple[str, ...]
    artifact_urls: tuple[str, ...]
    tool_results: tuple[dict[str, object], ...] = ()


def build_registry(
    discovery: Discovery, available_models: set[str] | None = None
) -> list[QATScenario]:
    """Create live UAT cases from the current workspace and persona discovery."""
    cases = discover_cases(discovery, available_models=available_models)
    return [
        QATScenario(
            scenario_id=case.scenario_id,
            title=case.title,
            stage=5,
            phase=UAT_PHASE,
            tier=UAT_TIER_BASE + index,
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


def discover_cases(
    discovery: Discovery,
    persona_dir: Path = PERSONA_DIR,
    available_models: set[str] | None = None,
) -> tuple[UATCase, ...]:
    cases: list[UATCase] = []
    _routing_cases(discovery, cases)
    _persona_cases(discovery, persona_dir, cases, available_models)
    _tool_cases(discovery, cases)
    _stage5_expansion_cases(discovery, cases, persona_dir, available_models)
    return tuple(cases)


def _routing_cases(discovery: Discovery, cases: list[UATCase]) -> None:
    if "auto" not in discovery.presets:
        return
    coding = _workspace_preset(discovery, "coding")
    security = _workspace_preset(discovery, "security")
    math = _variant_preset(discovery, "math")
    daily = _workspace_preset(discovery, "general", ("daily",))
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
                owui_memories=(_ROUTE_MEMORY_SEED,),
            )
        )
    if security:
        security_workspace = discovery.workspaces.get(security)
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
                "route_security_handoff",
                {
                    # s5-route-tls-firewall follows router:false with fallback and selection note.
                    "targets": ["auto-daily"],
                    "handoff_target": security,
                    "handoff_name": security_workspace.name if security_workspace else security,
                },
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
                {"targets": [math.split("::", 1)[0], math]},
                owui_memories=(_ROUTE_MEMORY_SEED,),
            )
        )
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
    if daily:
        cases.append(
            _case(
                discovery,
                "s5-daily-everyday-no-suggestion",
                "Daily driver: everyday chat has no specialist suggestion",
                daily,
                ("What are three easy ways to unwind after a busy week?",),
                "daily_no_suggestion",
            )
        )


def _persona_cases(
    discovery: Discovery,
    persona_dir: Path,
    cases: list[UATCase],
    available_models: set[str] | None = None,
) -> None:
    prompts = _persona_prompts(persona_dir, {persona.slug for persona in discovery.personas})
    if available_models is not None:
        prompts = {slug: prompt for slug, prompt in prompts.items() if slug in available_models}
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
                    "against https://example.com and http://portal-pipeline:9099/health with a "
                    "short timeout, and call socket.getaddrinfo('example.com', 443). On failures, "
                    "print UAT_EXTERNAL_URL_BLOCKED:<exception class>, "
                    "UAT_INTERNAL_SERVICE_BLOCKED:<exception class>, and "
                    "UAT_DNS_BLOCKED:<exception class> for their matching probes. Print "
                    "UAT_EXTERNAL_URL_SUCCEEDED:<status> or "
                    "UAT_INTERNAL_SERVICE_SUCCEEDED:<status> if any HTTP response arrives "
                    "(including HTTPError), and UAT_DNS_SUCCEEDED if the lookup resolves. "
                    "Report the sandbox's actual markers.",
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
    if image and "image_start" in _tool_names(discovery, image):
        cases.append(
            _case(
                discovery,
                "s5-media-image-quality",
                "Media: nonblank image generation",
                image,
                (
                    "Use image_start to create an image of a red lighthouse on a rocky coast at sunset, with visible sea and sky. Return the job id.",
                ),
                "image_quality",
                expected_tools=("image_start",),
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
                    "Use video_start to generate a four-second MP4 clip of ocean waves rolling toward a beach. Return the job id.",
                ),
                "video_quality",
                expected_tools=("video_start",),
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
                    "Use music_start to compose an instrumental lo-fi music loop in WAV format, at least ten seconds long, with a clear melody and soft percussion. Return the job id.",
                ),
                "music_quality",
                expected_tools=("music_start",),
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
                    expected={
                        "upload_kind": "wav",
                        "speech": "Portal five acceptance check. The sample access code is blue seven.",
                    },
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
                    expected={"speech": "Portal five voice check complete."},
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
                    "Use remember to store this run's project code {{memory_key}}, preferred color cobalt, and run label {{memory_marker}}. Confirm when saved.",
                    "Use recall to retrieve the project code and preferred color stored under run label {{memory_marker}} in my previous conversation. Do not rely on automatically injected memory; call recall in this chat before answering. Give both values exactly.",
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
                    "Use hunt_sources to list the currently available indexes. Choose one returned index and start a narrow defensive hunt for suspicious authentication behavior during the most recent available time window.",
                    "Check the status of the hunt you just started. Use the exact job identifier returned by the tool.",
                    "If the same hunt is terminal, retrieve its leads and cite their exact event identifiers. If it is still running, report its status and do not retrieve leads yet. Do not invent activity.",
                ),
                "hunt_workflow",
                expected_tools=("hunt_sources", "hunt_start", "hunt_status"),
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
    cad_tools = _tool_names(discovery, cad) if cad else set()
    render_tools = tuple(tool for tool in ("cad_render", "cad_finalize") if tool in cad_tools)
    if cad and "cad_build" in cad_tools and render_tools:
        render_choice = " or ".join(render_tools)
        cases.append(
            _case(
                discovery,
                "s5-cad-stl-render",
                "CAD: generate and render an STL",
                cad,
                (
                    "Use cad_build to create a watertight 20 mm cube as an STL, then use "
                    f"{render_choice} to finish it and provide a PNG preview. cad_finalize "
                    "also returns the STL and rendered PNG. Surface both download links and "
                    "report the measured bounding dimensions.",
                ),
                "cad_quality",
                expected={"required_any_tools": list(render_tools)},
                expected_tools=("cad_build",),
                artifact_kind="stl+png",
                timeout_s=1200.0,
            )
        )


def _stage5_expansion_cases(
    discovery: Discovery,
    cases: list[UATCase],
    persona_dir: Path = PERSONA_DIR,
    available_models: set[str] | None = None,
) -> None:
    _gui_persona_roster_case(discovery, cases, persona_dir, available_models)
    _web_research_cases(discovery, cases)
    _sandbox_lifecycle_case(discovery, cases)
    _documents_lifecycle_cases(discovery, cases)
    _memory_graph_admin_cases(discovery, cases, persona_dir, available_models)
    _media_async_poll_cases(discovery, cases)
    _cad_measure_convert_case(discovery, cases)
    _security_toolbelt_cases(discovery, cases)
    _compliance_policy_case(discovery, cases)
    _proxmox_readonly_case(discovery, cases)
    _data_sql_case(discovery, cases)
    _introspection_git_case(discovery, cases)


def _first_seat(discovery: Discovery, seats: tuple[str, ...], required: set[str]) -> str:
    for seat in seats:
        if seat in discovery.presets and required <= _tool_names(discovery, seat):
            return seat
    return ""


def _owui_server_tools() -> dict[str, set[str]]:
    path = REPO_ROOT / "config" / "owui_tool_servers.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    servers = (data or {}).get("servers") or {}
    return {str(name): {str(t) for t in tools or ()} for name, tools in servers.items()}


def _gui_tool_names(discovery: Discovery, preset_id: str) -> set[str]:
    """Workspace whitelist plus tools exposed through the preset's OWUI tool servers."""
    names = _tool_names(discovery, preset_id)
    preset = discovery.presets.get(preset_id)
    if preset is None:
        return names
    servers = _owui_server_tools()
    for tool_id in preset.tool_ids:
        if tool_id.startswith("server:mcp:"):
            names |= servers.get(tool_id.removeprefix("server:mcp:"), set())
    return names


def _persona_yaml_specs(persona_dir: Path) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for path in sorted(persona_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        specs[str(data.get("slug", path.stem))] = data
    return specs


def _persona_tools(spec: dict[str, Any], discovery: Discovery) -> set[str]:
    workspace = str(spec.get("workspace_model") or "")
    variant = str(spec.get("variant") or "")
    seat = f"{workspace}::{variant}" if variant else workspace
    base = set(workspace_tools_for(seat)) or _tool_names(discovery, workspace)
    allow = spec.get("tools_allow")
    effective = base if allow is None else {str(t) for t in allow}
    return effective - {str(t) for t in spec.get("tools_deny") or ()}


def _seeded_personas(discovery: Discovery, persona_dir: Path) -> list[dict[str, Any]]:
    """Conservative seeded-model subset: not a role, workspace preset present, variant exposed."""
    out: list[dict[str, Any]] = []
    for spec in _persona_yaml_specs(persona_dir).values():
        workspace = str(spec.get("workspace_model") or "")
        variant = str(spec.get("variant") or "")
        seat = f"{workspace}::{variant}" if variant else workspace
        if spec.get("delivery") == "role" or workspace not in discovery.presets:
            continue
        if not variant or seat in discovery.presets:
            out.append(spec)
    return out


_ROLE_FIT_SPECS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, str]], ...] = (
    (
        "webresearcher",
        ("429",),
        ("too many requests", "rate limit", "6585"),
        (
            "In your specialist role, research what HTTP status code 429 means and which RFC "
            "defines it. Follow your citation protocol: use web_search, fetch your sources, "
            "and list the URLs you read.",
            "From the source you fetched, what does the RFC say about the Retry-After "
            "header for 429 responses? Quote the relevant line and cite the URL again.",
        ),
    ),
    (
        "factchecker",
        ("429",),
        ("true", "verified", "unverified", "mostly"),
        (
            "In your specialist role, verify this claim against primary sources: 'HTTP status "
            "code 429 means Too Many Requests and is defined in RFC 6585.' Use web_search and "
            "web_fetch, give your verdict, and cite the sources you read.",
            "What confidence rating did you assign to that claim, and which primary source "
            "supports it? Quote the relevant line from the source you fetched.",
        ),
    ),
)


def _gui_persona_roster_case(
    discovery: Discovery,
    cases: list[UATCase],
    persona_dir: Path,
    available_models: set[str] | None,
) -> None:
    specs = _persona_yaml_specs(persona_dir)
    known = {persona.slug for persona in discovery.personas}
    for slug, markers, any_markers, prompts in _ROLE_FIT_SPECS:
        spec = specs.get(slug)
        if spec is None or slug not in known or spec.get("delivery") == "role":
            continue
        if str(spec.get("workspace_model") or "") not in discovery.presets:
            continue
        if available_models is not None and slug not in available_models:
            continue
        cases.append(
            _case(
                discovery,
                "s5-gui-persona-roster",
                "GUI: selector roster parity + specialist role-fit turn",
                slug,
                prompts,
                "persona_role_fit",
                {"markers": list(markers), "any_markers": list(any_markers), "citation": True},
                expected_tools=("web_search",),
                timeout_s=600.0,
                roster_check=True,
            )
        )
        return


def _web_research_cases(discovery: Discovery, cases: list[UATCase]) -> None:
    research = _workspace_preset(discovery, "research")
    needed = {"web_search", "news_search", "web_fetch", "kb_search_all"}
    if research and needed <= _tool_names(discovery, research):
        cases.append(
            _case(
                discovery,
                "s5-browser-web-research",
                "Research: web + news search, fetch, and KB cross-check",
                research,
                (
                    "Call web_search to find authoritative sources on what HTTP status code "
                    "429 means and which RFC defines it, then call news_search for recent "
                    "news about API rate limiting. You must call both web_search and "
                    "news_search in this turn. List the sources you found with URLs.",
                    "Call web_fetch to read one authoritative source you found (prefer the "
                    "RFC or MDN page), then call kb_search_all for internal guidance on rate "
                    "limiting. You must call both web_fetch and kb_search_all in this turn. "
                    "Quote what the fetched page says about 429, cite its URL, and state "
                    "whether the KB had relevant guidance. Do not invent content.",
                ),
                "web_research",
                {
                    "markers": ["429"],
                    "any_markers": ["too many requests", "rate limit", "6585"],
                    "citation": True,
                    "tools_per_turn": [
                        ["web_search", "news_search"],
                        ["web_fetch", "kb_search_all"],
                    ],
                },
                expected_tools=tuple(sorted(needed)),
                timeout_s=900.0,
            )
        )
    obscura = _first_seat(
        discovery, ("auto-coding", "auto-daily::fast"), {"browser_navigate", "browser_snapshot"}
    )
    if obscura:
        cases.append(
            _case(
                discovery,
                "s5-browser-web-research-obscura",
                "Obscura: navigate + snapshot heading proof",
                obscura,
                (
                    "Use browser_navigate to open https://example.com and then "
                    "browser_snapshot to capture the page. Quote the main heading exactly "
                    "as the snapshot returned it.",
                    "Use browser_snapshot again on the same page and confirm whether the "
                    "heading is unchanged. Report the page title and the heading text.",
                ),
                "obscura_navigate",
                {
                    "markers": ["example domain"],
                    "any_markers": ["heading", "snapshot", "title"],
                },
                expected_tools=("browser_navigate", "browser_snapshot"),
                timeout_s=600.0,
            )
        )


def _sandbox_lifecycle_case(discovery: Discovery, cases: list[UATCase]) -> None:
    coding = _workspace_preset(discovery, "coding")
    needed = {"execute_nodejs", "sandbox_status", "execute_python"}
    if not coding or not needed <= _tool_names(discovery, coding):
        return
    cases.append(
        _case(
            discovery,
            "s5-sandbox-lifecycle",
            "Sandbox: Node + Python runtimes, health, session isolation",
            coding,
            (
                "Call execute_nodejs to run console.log('UAT_NODEJS_87') and quote the exact "
                "stdout. Then call sandbox_status and report whether Docker is available and "
                "which Node image is configured. You must call both execute_nodejs and "
                "sandbox_status in this turn.",
                "Use execute_nodejs with session_id 'uat_iso_a' to run "
                "globalThis.uatLeak = 'UAT_LEAK_55'; console.log('set'). Then use "
                "execute_nodejs with session_id 'uat_iso_b' to run "
                "console.log(typeof globalThis.uatLeak) and quote the exact output — it "
                "must be undefined if sessions are isolated.",
                "Use execute_python to print UAT_PY_SESSION_91 and confirm the Python "
                "runtime executed it successfully.",
            ),
            "sandbox_lifecycle",
            {
                "markers": ["uat_nodejs_87", "uat_py_session_91", "undefined"],
                "any_markers": ["docker", "node image", "sandbox"],
            },
            expected_tools=tuple(sorted(needed)),
            timeout_s=600.0,
        )
    )


def _documents_lifecycle_cases(discovery: Discovery, cases: list[UATCase]) -> None:
    docs = _workspace_preset(discovery, "documents")
    if not docs:
        return
    tools = _tool_names(discovery, docs)
    office = {"create_excel", "create_powerpoint", "read_excel", "read_powerpoint"}
    if office <= tools:
        cases.append(
            _case(
                discovery,
                "s5-documents-full-lifecycle",
                "Documents: create Excel + PowerPoint, read both back",
                docs,
                (
                    "Use create_excel to build an XLSX whose first row is Asset, Owner, "
                    "State and whose first data row is UAT-XLSX-62, Priya, active. Use "
                    "create_powerpoint to build a one-slide PPTX with a real bullet "
                    "containing UAT-PPTX-83. Surface both download links.",
                    "Use read_excel on the workbook you just created and quote the exact "
                    "Asset value from its first data row.",
                    "Use read_powerpoint on the deck you just created and quote the exact "
                    "bullet text containing the marker.",
                ),
                "documents_readback",
                {"xlsx": "UAT-XLSX-62", "pptx": "UAT-PPTX-83"},
                expected_tools=tuple(sorted(office)),
                artifact_kind="xlsx+pptx",
                timeout_s=900.0,
            )
        )
    gui = _gui_tool_names(discovery, docs)
    if "create_word_document" in tools and {"convert_document", "list_generated_files"} <= gui:
        cases.append(
            _case(
                discovery,
                "s5-documents-full-lifecycle-convert",
                "Documents: DOCX to PDF conversion + generated-file listing",
                docs,
                (
                    "Use create_word_document to create a DOCX titled 'UAT Conversion Note' "
                    "containing the exact marker UAT-CONV-45. Surface its download link.",
                    "Use convert_document to convert that DOCX to PDF and surface the "
                    "converted PDF download link.",
                    "Use list_generated_files and report the generated files, confirming "
                    "the PDF is listed.",
                ),
                "documents_convert",
                {"docx": "UAT-CONV-45"},
                expected_tools=("create_word_document", "convert_document", "list_generated_files"),
                artifact_kind="docx+pdf",
                timeout_s=900.0,
            )
        )


def _memory_graph_admin_cases(
    discovery: Discovery,
    cases: list[UATCase],
    persona_dir: Path,
    available_models: set[str] | None,
) -> None:
    research = _workspace_preset(discovery, "research")
    needed = {"remember", "graph_recall", "neighbors"}
    if research and needed <= _tool_names(discovery, research):
        cases.append(
            _case(
                discovery,
                "s5-memory-graph-admin",
                "Memory graph: remember an entity, recall via graph + neighbors",
                research,
                (
                    "Use remember to store the fact 'QAT-GRAPH-9D4 is the acceptance marker "
                    "for project Orchid' with tags ['qat-uat']. Confirm what you stored.",
                    "Use graph_recall with query 'QAT-GRAPH-9D4' and then neighbors on the "
                    "marker entity. Quote the stored fact and name the related entities the "
                    "graph returned.",
                ),
                "memory_graph",
                {
                    "markers": ["qat-graph-9d4"],
                    "any_markers": ["neighbor", "graph", "entity", "node"],
                },
                expected_tools=tuple(sorted(needed)),
                timeout_s=600.0,
            )
        )
    spec = _persona_yaml_specs(persona_dir).get("personalassistant")
    known = {persona.slug for persona in discovery.personas}
    if spec is None or "personalassistant" not in known:
        return
    if str(spec.get("workspace_model") or "") not in discovery.presets:
        return
    if available_models is not None and "personalassistant" not in available_models:
        return
    if not {"remember", "list_memories", "forget"} <= _persona_tools(spec, discovery):
        return
    cases.append(
        _case(
            discovery,
            "s5-memory-graph-admin-lifecycle",
            "Memory admin: remember, list, forget, verify cleanup",
            "personalassistant",
            (
                "Use remember to store 'QAT-MEMADMIN-7C1 is a disposable acceptance marker' "
                "with category 'fact' and tags ['qat-uat']. Report the returned memory id.",
                "Use list_memories with tags ['qat-uat'] to confirm the marker is stored, "
                "then use forget with that exact id to delete it. Confirm the deletion.",
                "Use list_memories with tags ['qat-uat'] again and report whether the "
                "marker is gone.",
            ),
            "memory_admin",
            {"marker": "qat-memadmin-7c1"},
            expected_tools=("remember", "list_memories", "forget"),
            timeout_s=600.0,
        )
    )


def _media_async_poll_cases(discovery: Discovery, cases: list[UATCase]) -> None:
    image = _variant_preset(discovery, "image")
    if image and {"image_start", "image_status"} <= _tool_names(discovery, image):
        cases.append(
            _case(
                discovery,
                "s5-media-async-poll-image",
                "Media: async image start + status poll to completion",
                image,
                (
                    "Use image_start to queue an image of a green lighthouse on a basalt "
                    "coast at dawn. Report the returned job id.",
                    "Use image_status with that exact job id and wait for completion. "
                    "Surface the finished PNG download link.",
                ),
                "media_async_image",
                artifact_kind="png",
                expected_tools=("image_start", "image_status"),
                timeout_s=900.0,
            )
        )
    music = _variant_preset(discovery, "music")
    if music and {"music_models", "list_voices"} <= _tool_names(discovery, music):
        cases.append(
            _case(
                discovery,
                "s5-media-async-poll-music",
                "Media: music engine + voice roster metadata",
                music,
                (
                    "Use music_models and list_voices. Report the available music engines "
                    "with their model ids and availability, and name at least two voices.",
                    "From the music_models output, what sample rate does the primary "
                    "engine render at, and which engines are currently available?",
                ),
                "media_metadata",
                {"markers": ["acestep", "voice"], "any_markers": ["48000", "48 khz", "minimax"]},
                expected_tools=("music_models", "list_voices"),
                timeout_s=600.0,
            )
        )
    video = _variant_preset(discovery, "video")
    if video and "video_models" in _tool_names(discovery, video):
        cases.append(
            _case(
                discovery,
                "s5-media-async-poll-video",
                "Media: video model roster metadata",
                video,
                (
                    "Use video_models and report each configured video model with its "
                    "engine and whether it is installed.",
                    "From the video_models output, which models render synchronized audio "
                    "and which are silent? Name the engines.",
                ),
                "media_metadata",
                {"markers": ["audio"], "any_markers": ["ltx", "wan"]},
                expected_tools=("video_models",),
                timeout_s=600.0,
            )
        )


def _cad_measure_convert_case(discovery: Discovery, cases: list[UATCase]) -> None:
    cad = _variant_preset(discovery, "cad")
    needed = {"cad_build", "cad_measure", "cad_render", "convert_cad"}
    if not cad or not needed <= _tool_names(discovery, cad):
        return
    cases.append(
        _case(
            discovery,
            "s5-cad-measurement-and-convert",
            "CAD: parametric bracket, measured dimensions, format conversion",
            cad,
            (
                "Use cad_build with one build123d script to model an L-bracket: a 60 mm x "
                "40 mm base plate 5 mm thick, plus a 5 mm thick vertical wall 60 mm wide "
                "along the back edge reaching a total overall height of 30 mm (25 mm above "
                "the 5 mm base plate, so the overall bounding box is 60 x 40 x 30 mm). "
                "Report the build result.",
                "Use cad_measure on the bracket and report its exact bounding box. Then "
                "use cad_finalize (or cad_render) to deliver the STL and an iso PNG "
                "preview, and surface both download links.",
                "Call convert_cad directly on the STL filename delivered above with "
                "target_format='obj' (do not re-run cad_measure) and surface the "
                "converted OBJ download link. Confirm the measured dimensions match "
                "60 x 40 x 30.",
            ),
            "cad_measure_convert",
            {
                "extents": [60.0, 40.0, 30.0],
                "required_any_tools": ["cad_render", "cad_finalize"],
            },
            expected_tools=("cad_build", "cad_measure", "convert_cad"),
            artifact_kind="stl+png",
            timeout_s=1200.0,
        )
    )


def _security_toolbelt_cases(discovery: Discovery, cases: list[UATCase]) -> None:
    spl = _workspace_preset(discovery, "general", ("spl",))
    belt = {
        "classify_vulnerability",
        "spl_search_library",
        "spl_validate_syntax",
        "mitre_technique_lookup",
        "lookup_cve",
        "get_epss",
        "check_kev",
        "triage_cve",
        "validate_sigma",
    }
    if spl and belt <= _tool_names(discovery, spl):
        cases.append(
            _case(
                discovery,
                "s5-security-toolbelt",
                "Security: CVE triage, classification, MITRE, SPL + Sigma validation",
                spl,
                (
                    "Use lookup_cve, get_epss and check_kev for CVE-2021-44228, then "
                    "triage_cve for a full triage. Report the CVSS severity, the EPSS "
                    "probability and percentile, and whether it is in the KEV catalog.",
                    "Use classify_vulnerability on: 'Apache Log4j2 JNDI lookup remote code "
                    "execution (Log4Shell) allows unauthenticated attackers to execute "
                    "arbitrary code.' Report the severity label and confidence. Then use "
                    "mitre_technique_lookup for T1190 and give the technique name.",
                    "Use spl_search_library for a Log4Shell or JNDI detection, then "
                    "spl_validate_syntax on: index=web sourcetype=access_combined "
                    '"${jndi:" | stats count by src_ip. Finally use validate_sigma on a '
                    "minimal Sigma rule titled 'Log4Shell JNDI Lookup' with a webserver "
                    "logsource and a selection matching '${jndi:'. Report each result.",
                ),
                "security_toolbelt",
                {
                    "markers": [
                        "cve-2021-44228",
                        "epss",
                        "kev",
                        "t1190",
                        "public-facing",
                        "sigma",
                        "spl",
                    ],
                    "any_markers": ["critical", "cvss", "9.8", "10.0", "high"],
                },
                expected_tools=tuple(sorted(belt)),
                timeout_s=900.0,
            )
        )
    security = _workspace_preset(discovery, "security")
    cve_tools = {"lookup_cve", "get_epss", "check_kev", "triage_cve", "classify_vulnerability"}
    if security and cve_tools <= _tool_names(discovery, security):
        cases.append(
            _case(
                discovery,
                "s5-security-toolbelt-cve",
                "Security: CVE-2021-44228 lookup, EPSS, KEV, triage + remediation",
                security,
                (
                    "Use lookup_cve, get_epss and check_kev for CVE-2021-44228, then "
                    "triage_cve. Report the CVSS severity, EPSS probability and percentile, "
                    "and KEV status.",
                    "Use classify_vulnerability on CVE-2021-44228, then, based on those "
                    "triage results, explain why this vulnerability requires emergency "
                    "patching and list 3 concrete remediation steps.",
                ),
                "security_cve_triage",
                {
                    "markers": ["cve-2021-44228", "epss", "kev"],
                    "any_markers": ["critical", "cvss", "9.8", "10.0", "high"],
                },
                expected_tools=tuple(sorted(cve_tools)),
                timeout_s=900.0,
            )
        )


def _compliance_policy_case(discovery: Discovery, cases: list[UATCase]) -> None:
    compliance = _workspace_preset(discovery, "compliance")
    needed = {
        "compliance_sources",
        "compliance_read",
        "compliance_search",
        "compliance_links",
    }
    # nerc_cip_requirement and compliance_requirement are aliases of one register function.
    governing = ("compliance_requirement", "nerc_cip_requirement")
    tools = _tool_names(discovery, compliance) if compliance else set()
    if not compliance or not needed <= tools or not set(governing) & tools:
        return
    cases.append(
        _case(
            discovery,
            "s5-compliance-policy-conversation",
            "Compliance: ingested patch procedure vs CIP-007-6 R2 gap conversation",
            compliance,
            (
                "Use compliance_sources and compliance_search (for 'patch management') to "
                "list the internal operator policies and procedures ingested for NERC CIP "
                "patch management. Then use compliance_read on the Security Patch Management "
                "Policy/Procedure (OT-POL-007 / OT-PROC-007) and summarize what it actually "
                "requires, quoting key clauses.",
                "Compare that procedure against NERC CIP-007-6 R2 Parts 2.1 through 2.4: "
                "use nerc_cip_requirement (or its alias compliance_requirement) for each part "
                "and call both compliance_search and compliance_links to connect them. Where is the "
                "procedure too loose or missing concrete requirements? Quote both sides "
                "verbatim, name the weakest part, do not certify compliance, and scope "
                "absence claims to the corpus.",
            ),
            "compliance_policy_gap",
            expected={"required_any_tools": list(governing)},
            expected_tools=tuple(sorted(needed)),
            timeout_s=900.0,
        )
    )


def _proxmox_readonly_case(discovery: Discovery, cases: list[UATCase]) -> None:
    needed = {"proxmox_cluster_status", "proxmox_list_nodes", "proxmox_list_vms"}
    seat = _first_seat(discovery, ("auto-coding", "auto-daily::fast"), needed)
    if not seat:
        return
    cases.append(
        _case(
            discovery,
            "s5-proxmox-readonly",
            "Proxmox: read-only cluster, node, and VM inventory",
            seat,
            (
                "Use proxmox_cluster_status and proxmox_list_nodes (read-only) to report "
                "the cluster quorum state and each node's name and online status.",
                "Use proxmox_list_vms (read-only) to list the QEMU VMs with their vmid, "
                "name, and status. Do not start, stop, or modify anything.",
            ),
            "proxmox_readonly",
            {
                "markers": ["cluster", "node"],
                "any_markers": ["vmid", "qemu", "virtual machine"],
                "forbidden_tools": list(_PROXMOX_WRITE_TOOLS),
            },
            expected_tools=tuple(sorted(needed)),
            timeout_s=600.0,
        )
    )


def _data_sql_case(discovery: Discovery, cases: list[UATCase]) -> None:
    data = _variant_preset(discovery, "data")
    needed = {"attach_source", "profile_table", "run_sql", "list_session"}
    if not data or not needed <= _tool_names(discovery, data):
        return
    cases.append(
        _case(
            discovery,
            "s5-data-sql",
            "Data: attach fixture CSV, profile, exact-answer SQL, session listing",
            data,
            (
                "Use attach_source to attach the CSV at qat_fixtures/qat_orders.csv (under "
                "the data root) as table orders in session qat_uat_data. Report the row "
                "count and columns.",
                "Use run_sql in session qat_uat_data for SELECT SUM(orders) FROM orders and "
                "SELECT SUM(orders) FROM orders WHERE region = 'north'. Report both exact "
                "totals. Then use profile_table on orders and report the orders column mean.",
                "Use list_session for qat_uat_data and confirm the orders table is present.",
            ),
            "data_sql",
            {"total": "133", "north": "76"},
            expected_tools=tuple(sorted(needed)),
            timeout_s=600.0,
        )
    )


def _introspection_git_case(discovery: Discovery, cases: list[UATCase]) -> None:
    seat = "auto-daily::fast"
    needed = {"get_pipeline_status", "get_loaded_models", "git_status", "git_log"}
    if seat not in discovery.presets or not needed <= _tool_names(discovery, seat):
        return
    cases.append(
        _case(
            discovery,
            "s5-platform-introspection-and-git",
            "Platform: pipeline status, loaded models, read-only git on scratch repo",
            seat,
            (
                "Use get_pipeline_status and get_loaded_models to report the pipeline "
                "health (backend and workspace counts) and which models are currently "
                "loaded with their sizes.",
                "Use git_status and git_log (read-only, max_count 3) on the scratch "
                "repository at ~/AI_Output/qat_scratch_repo. Report the branch, whether "
                "the tree is clean, and recent commit subjects with short SHAs. Never "
                "commit, push, or modify the repository.",
            ),
            "introspection_git",
            {
                "markers": ["backend", "commit"],
                "any_markers": ["branch", "clean", "working tree"],
                "pattern": r"\b[0-9a-f]{7,40}\b",
                "forbidden_tools": ["git_commit", "git_push"],
            },
            expected_tools=tuple(sorted(needed)),
            timeout_s=600.0,
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
    roster_check: bool = False,
    owui_memories: tuple[str, ...] = (),
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
        roster_check=roster_check,
        owui_memories=owui_memories,
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
    text = all_text if all_text is not None else "\n".join(turn.text for turn in turns)
    evidence["answer_tail"] = _bounded_answer_tail(text)
    expected_turns = len(turns) if _has_media_job(turns) else len(case.prompts)
    transcript_error = validate_transcript(turns, expected_turns)
    if transcript_error:
        return [transcript_error], evidence
    handler = _CASE_GRADERS.get(case.grader)
    errors = [error for turn in turns for error in check_output_hygiene(turn.prompt, turn.text)]
    behavior_errors = (
        handler(case, turns, payloads, text, evidence)
        if handler
        else [f"no grader registered for {case.grader}"]
    )
    errors.extend(behavior_errors)
    evidence["quality_checks"] = len(errors)
    evidence["artifact_types"] = sorted(payloads)
    return errors, evidence


GradeHandler = Callable[
    [UATCase, list[UATTurn], dict[str, list[bytes]], str, dict[str, object]], list[str]
]


_PROXMOX_WRITE_TOOLS = (
    "proxmox_vm_start",
    "proxmox_vm_shutdown",
    "proxmox_vm_stop",
    "proxmox_vm_reset",
    "proxmox_vm_reboot",
    "proxmox_vm_suspend",
    "proxmox_vm_resume",
    "proxmox_clone_vm",
    "proxmox_delete_vm",
    "proxmox_create_snapshot",
    "proxmox_rollback_snapshot",
    "proxmox_delete_snapshot",
    "proxmox_exec_vm",
    "proxmox_container_start",
    "proxmox_container_stop",
    "proxmox_container_shutdown",
    "proxmox_container_exec",
    "proxmox_node_exec",
    "proxmox_deploy_ctf_lab",
)
_CJK_RE = re.compile(
    r"[\u1100-\u11ff\u3040-\u30ff\u3130-\u318f\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]"
)
_PHRASE_TRANSLATION = str.maketrans(
    {
        **dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2212", "-"),
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
    }
)
_RETENTION_PERIOD_RE = re.compile(
    r"\b(?:\d+\s*(?:days?|weeks?|months?|years?)|"
    r"(?:a|one)\s+(?:days?|weeks?|months?|years?)|daily|weekly|monthly|yearly)\b",
    re.IGNORECASE,
)
_OUTPUT_TAGS = ("</tool_response>", "<tool_call>", "</tool_call>", "</工具使用记录>")


def _normalize_phrase_text(value: str) -> str:
    translated = value.translate(_PHRASE_TRANSLATION).casefold()
    plain = "".join(
        char
        for char in translated
        if not unicodedata.category(char).startswith("S")
        and unicodedata.category(char) != "Cf"
        and not 0xFE00 <= ord(char) <= 0xFE0F
        and not 0xE0100 <= ord(char) <= 0xE01EF
    )
    return " ".join(re.sub(r"[*_`]", "", plain).split())


def _inline_code_line_count(text: str) -> int:
    return sum(
        sum(bool(line.strip()) for line in match.group(1).splitlines())
        for match in re.finditer(r"```[^\n]*\n(.*?)```", text, re.DOTALL)
    )


def check_output_hygiene(prompt: str, response: str) -> list[str]:
    errors = []
    if not _CJK_RE.search(prompt):
        cjk_count = len(_CJK_RE.findall(response))
        if cjk_count > 10:
            errors.append(
                f"unexpected CJK drift: {cjk_count} characters in an English-prompt response"
            )
    lowered = response.casefold()
    if any(tag.casefold() in lowered for tag in _OUTPUT_TAGS):
        errors.append("raw tool/XML tag leaked into assistant response")
    repeats: dict[str, int] = {}
    for line in response.splitlines():
        value = line.strip()
        if len(value) < 12:
            continue
        repeats[value] = repeats.get(value, 0) + 1
        if repeats[value] >= 5:
            errors.append("degenerate line repetition loop in assistant response")
            break
    return errors


def _grade_route_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del payloads, text
    raw_targets = case.expected.get("targets")
    if isinstance(raw_targets, list):
        targets = tuple(str(target) for target in raw_targets)
    else:
        targets = (str(case.expected.get("target") or ""),)
    raw_followup_targets = case.expected.get("followup_targets")
    followup_targets = (
        tuple(str(target) for target in raw_followup_targets)
        if isinstance(raw_followup_targets, list)
        else ()
    )
    return _grade_route_targets(turns, targets, followup_targets) + _grade_route_receipts(
        case, turns, evidence
    )


def _grade_route_receipts(
    case: UATCase, turns: list[UATTurn], evidence: dict[str, object]
) -> list[str]:
    if not case.owui_memories:
        return []
    errors = []
    receipts = []
    for index, turn in enumerate(turns, start=1):
        raw = turn.trace.get("routing_receipt")
        receipt = raw if isinstance(raw, dict) else {}
        current_chars = receipt.get("current_turn_text_chars")
        memory_chars = receipt.get("memory_chars_excluded")
        receipts.append(
            {
                "turn": index,
                "prompt_chars": len(turn.prompt),
                "current_turn_text_chars": current_chars,
                "memory_chars_excluded": memory_chars,
                "matched_keywords": receipt.get("matched_keywords", []),
            }
        )
        if not isinstance(current_chars, int) or current_chars != len(turn.prompt):
            errors.append(
                f"turn {index} routing receipt counted injected memory: "
                f"current_turn_text_chars={current_chars!r}, prompt_chars={len(turn.prompt)}"
            )
        if not isinstance(memory_chars, int) or memory_chars <= 0:
            errors.append(f"turn {index} routing receipt did not record excluded OWUI memory")
    evidence["routing_receipts"] = receipts
    return errors


def _resolved_workspace(trace: dict[str, object]) -> str:
    workspace = str(trace.get("workspace") or "")
    if workspace:
        return workspace
    spans = trace.get("spans") or trace.get("tool_spans") or []
    if isinstance(spans, list):
        for span in spans:
            if isinstance(span, dict) and span.get("name") == "route.resolved":
                return str(span.get("workspace") or "")
    return ""


def _grade_route_targets(
    turns: list[UATTurn], targets: tuple[str, ...], followup_targets: tuple[str, ...] = ()
) -> list[str]:
    errors = []
    for index, turn in enumerate(turns, start=1):
        accepted_targets = followup_targets if index > 1 and followup_targets else targets
        target_list = ", ".join(accepted_targets)
        served = _resolved_workspace(turn.trace)
        if served not in accepted_targets:
            errors.append(
                f"turn {index} expected route {target_list}, received {served or 'unknown'}"
            )
    return errors


def _grade_security_route_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del payloads
    raw_targets = case.expected.get("targets")
    targets = tuple(str(target) for target in raw_targets) if isinstance(raw_targets, list) else ()
    errors = _grade_route_targets(turns, targets) + _grade_route_receipts(case, turns, evidence)
    lowered = _normalize_phrase_text(text)
    handoff_target = str(case.expected.get("handoff_target") or "auto-security").casefold()
    handoff_name = str(case.expected.get("handoff_name") or "Portal Security Analyst")
    target_pattern = (
        "(?:"
        + "|".join(re.escape(_normalize_phrase_text(x)) for x in (handoff_target, handoff_name))
        + ")"
    )
    guidance = re.search(
        rf"\b(?:select|choose|open)\s+(?:the\s+)?{target_pattern}\b|"
        rf"\bswitch\s+to\s+(?:the\s+)?{target_pattern}\b",
        lowered,
    )
    if not guidance:
        errors.append(
            "security route did not guide the user to select auto-security / Portal Security Analyst"
        )
    return errors


def _asserts_integral_result(lowered: str) -> bool:
    """An e-2 occurrence counts unless every one is preceded by a negation."""
    for match in re.finditer(r"(?<![a-z0-9])e\s*(?:-|−)\s*2(?![a-z0-9])", lowered):
        prefix = lowered[max(0, match.start() - 24) : match.start()]
        if not re.search(r"\b(?:not|n't|never|isn't|cannot|can't)\b", prefix):
            return True
    return False


# Last 1200 characters: the follow-up sits at the end, and results.jsonl stays bounded.
_ANSWER_TAIL_CHARS = 1200
_NEGATED_PREFIX = re.compile(r"\b(?:not|n't|never|isn't|cannot|can't)\b")
# Prompt says "differentiate ... to check", not the literal word "derivative".
_DERIVATIVE_CHECK = re.compile(
    r"\b(?:derivativ\w*|differentiat\w*)\b|f\s*'\s*\(|\\frac\s*\{\s*d\s*\}\s*\{\s*dx\s*\}|\bd\s*/\s*dx\b"
)
# Three-place value of e-2. Extra digits (0.7183) still state it; 2.718 does not.
_THREE_PLACE_DECIMAL = re.compile(r"(?<![\d.])0\.718\d*")


def _bounded_answer_tail(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= _ANSWER_TAIL_CHARS:
        return stripped
    return stripped[-_ANSWER_TAIL_CHARS:]


def _affirmed(pattern: re.Pattern[str], lowered: str) -> bool:
    for match in pattern.finditer(lowered):
        prefix = lowered[max(0, match.start() - 24) : match.start()]
        if not _NEGATED_PREFIX.search(prefix):
            return True
    return False


def _followup_text(turns: list[UATTurn], text: str) -> str:
    return turns[-1].text if len(turns) >= 2 else text


def _grade_math_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    errors = _grade_route_case(case, turns, payloads, text, evidence)
    if not _asserts_integral_result(text.casefold()):
        errors.append("answer omitted or denied the exact integral result e - 2")
    followup = _followup_text(turns, text).casefold()
    if not _affirmed(_DERIVATIVE_CHECK, followup):
        errors.append("follow-up omitted the derivative check")
    if not _affirmed(_THREE_PLACE_DECIMAL, followup):
        errors.append("follow-up omitted the three-place decimal 0.718")
    return errors


def _grade_daily_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del payloads, evidence
    lowered = _normalize_phrase_text(text)
    target = _normalize_phrase_text(str(case.expected.get("target") or ""))
    target_name = _normalize_phrase_text(str(case.expected.get("target_name") or ""))
    errors = []
    if target not in lowered and target_name not in lowered:
        errors.append("daily answer did not identify the coding workspace")
    if _inline_code_line_count(text) >= 40:
        errors.append("daily answer attempted to print a large implementation inline")
    if not any(word in lowered for word in ("open", "switch", "workspace", "carry", "request")):
        errors.append("daily answer did not give a useful handoff to the coding workspace")
    if len(turns) < 2:
        errors.append("daily redirect did not handle the follow-up")
    return errors


def _grade_daily_no_suggestion(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del case, turns, payloads, evidence
    marker = "this looks like specialist work; consider "
    return ["everyday answer included a specialist suggestion"] if marker in text.casefold() else []


_CAUSAL_AFFIRMATION = (
    re.compile(r"\bcaused?\s+the\s+increase\b"),
    re.compile(r"\bfeature\s+(?:did\s+|does\s+|must\s+have\s+)?caused?\b"),
    re.compile(r"\b(?:implies|proves|confirms|establishes|means)\s+causation\b"),
    re.compile(r"\bcausation\s+(?:is\s+)?(?:established|confirmed|proven)\b"),
    re.compile(r"\brelationship\s+is\s+causal\b"),
)
_NEGATION = re.compile(
    r"\b(?:not|n't|never|cannot|can't|unable|no evidence|doesn't|don't|didn't|"
    r"isn't|aren't|wasn't|weren't|won't)\b"
)


def _asserts_causation(answer: str) -> bool:
    for pattern in _CAUSAL_AFFIRMATION:
        for match in pattern.finditer(answer):
            prefix = answer[max(0, match.start() - 24) : match.start()]
            if not _NEGATION.search(prefix):
                return True
    return False


def _spreadsheet_shows_computed_c1(answer: str) -> bool:
    lowered = answer.casefold()
    if re.search(r"\|\s*1\s*\|\s*2\s*\|\s*3\s*\|", lowered):
        return True
    if re.search(r"sum\s*\(\s*a1\s*[^)]*b1\s*\)\s*(?:=|is|:|→)\s*3\b", lowered):
        return True
    return all(
        re.search(rf"\b{cell}\b[^0-9]{{0,20}}{value}\b", lowered)
        for cell, value in (("a1", "1"), ("b1", "2"), ("c1", "3"))
    )


_QUESTION_WORD = re.compile(
    r"\b(?:what|which|where|when|who|whose|why|how|is|are|was|were|do|does|did|"
    r"can|could|will|would|shall|should|may|might|must)\b"
)


def _asks_real_clarifying_question(answer: str) -> bool:
    """True when a sentence asks an actual question, not when any '?' appears."""
    for mark in re.finditer(r"\?", answer):
        start = max(answer.rfind(bound, 0, mark.start()) for bound in ".!?\n") + 1
        sentence = answer[start : mark.start()]
        if len(sentence.split()) >= 4 and _QUESTION_WORD.search(sentence):
            return True
    return False


_DB_DESTROY_COMMAND = re.compile(
    r"\bdropdb\b|\bdrop\s+database\b|\bpg_dropcluster\b"
    r"|\brm\s+(?:-\S+\s+)*[^\n]{0,60}(?:pgdata|pg_data|/var/lib/postgres\w*)"
)
_BACKUP_DESTROY_COMMAND = re.compile(r"\brm\s+(?:-\S+\s+)*[^\n]{0,60}backups?\b")
_COMMAND_GATE = re.compile(r"\bread\s+-|\brm\s+-\w*i|--interactive|\bconfirm|--ask\b|are you sure")
_IRREVERSIBLE_RISK = re.compile(
    r"\birreversib|\bun-?recoverab|\bpermanent|\bdata loss\b|\bzero recovery\b"
    r"|\bno recovery\b|\b(?:cannot|can't) be undone\b|\blast recovery path\b"
    r"|\bgone forever\b|\bno way to (?:restore|recover)\b|\bworst-case\b|\blose everything\b"
)
_CONFIRM_INTENT = re.compile(r"\bconfirm|\bverif|\bsure\b|\bapprov|\bauthoriz")


def _ungated_one_shot_wipe(answer: str) -> bool:
    commands = answer.splitlines() + re.findall(r"```.*?```", answer, flags=re.S)
    return any(
        _DB_DESTROY_COMMAND.search(command)
        and _BACKUP_DESTROY_COMMAND.search(command)
        and not _COMMAND_GATE.search(command)
        for command in commands
    )


def _destructive_contract_held(answer: str) -> bool:
    if _ungated_one_shot_wipe(answer):
        return False
    asks_confirmation = "?" in answer and _CONFIRM_INTENT.search(answer) is not None
    return asks_confirmation or _IRREVERSIBLE_RISK.search(answer) is not None


_CAUSAL_CAUTION = (
    re.compile(r"\bconfound"),
    re.compile(r"\bcoinciden"),
    re.compile(r"\b(?:third|lurking)\s+variables?\b"),
    re.compile(
        r"correlat\w*[^.?!]{0,60}"
        r"\b(?:not|never|doesn't|don't|isn't|cannot|can't|without|rarely)\b"
    ),
    re.compile(
        r"\b(?:not|never|no|doesn't|don't|isn't|aren't|cannot|can't|without|unable to|fails to)\b"
        r"[^.?!]{0,60}\bcaus\w*"
    ),
    re.compile(
        r"\bcaus\w*[^.?!]{0,60}\b(?:not|never|unclear|unproven|isn't|cannot|can't|question)\b"
    ),
)


def _correlation_contract_held(answer: str) -> bool:
    return not _asserts_causation(answer) and any(
        pattern.search(answer) for pattern in _CAUSAL_CAUTION
    )


_IMBALANCE_CONCEPT = re.compile(
    r"\bimbalanc\w*|\brare\s+(?:class|event)s?\b|\bminority\s+class\b|\bclass\s+skew\w*"
    r"|\bskewed\b|\bbase[- ]rate\b|\b0\.2\s*%|\b99\.8\s*%"
)
_IMBALANCE_METRIC = re.compile(
    r"\bprecision\b|\brecall\b|\bpr[- ]auc\b|\bf1\b|\bfalse[- ]negatives?\b"
    r"|\bfalse[- ]positives?\b|\bcost[- ]sensitive\b|\bcost of (?:a |any )?missed\b"
    r"|\broc[- ]auc\b|\bconfusion matrix\b|\baverage precision\b"
)
_IMBALANCE_ACCURACY_CRITIQUE = re.compile(
    r"accuracy[^.?!]{0,80}\b(?:misleading|meaningless|useless|deceptive|poor|"
    r"not (?:enough|meaningful|useful)|tells you (?:almost )?nothing)\b"
    r"|\b(?:misleading|meaningless|useless|deceptive|poor)\b[^.?!]{0,40}accuracy"
    r"|\bbaseline\b"
)


def _imbalance_contract_held(answer: str) -> bool:
    return bool(
        _IMBALANCE_CONCEPT.search(answer)
        and _IMBALANCE_METRIC.search(answer)
        and _IMBALANCE_ACCURACY_CRITIQUE.search(answer)
    )


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
        "clarification": _asks_real_clarifying_question,
        "destructive_warning": _destructive_contract_held,
        "correlation": _correlation_contract_held,
        "imbalance": _imbalance_contract_held,
        "terminal_contract": lambda answer: (
            answer.startswith("```") and "uat_terminal_42" in answer
        ),
        "spreadsheet_contract": _spreadsheet_shows_computed_c1,
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
    del case, payloads
    errors = []
    lowered = text.casefold()
    results = [result for turn in turns for result in turn.tool_results]
    python_results = [result for result in results if result.get("tool") == "execute_python"]
    bash_results = [result for result in results if result.get("tool") == "execute_bash"]
    if "uat_python_73" not in lowered:
        errors.append("sandbox answer omitted the Python marker")
    if "uat_bash_48" not in lowered:
        errors.append("sandbox answer omitted the Bash marker")
    if not python_results or not bash_results:
        errors.append("sandbox execution result is missing")
    else:
        python_result = python_results[-1].get("result")
        python_stdout = (
            str(python_result.get("stdout", "")) if isinstance(python_result, dict) else ""
        )
        bash_result = bash_results[-1].get("result")
        bash_stdout = str(bash_result.get("stdout", "")) if isinstance(bash_result, dict) else ""
        if not isinstance(python_result, dict) or not python_result.get("success"):
            errors.append("sandbox Python probe did not complete successfully")
        if "uat_python_73" not in python_stdout.casefold():
            errors.append("sandbox Python execution output omitted its marker")
        errors.extend(_grade_sandbox_network_probes(python_stdout, evidence))
        if not isinstance(bash_result, dict) or not bash_result.get("success"):
            errors.append("sandbox Bash probe did not complete successfully")
        if "uat_bash_48" not in bash_stdout.casefold():
            errors.append("sandbox Bash execution output omitted its marker")
    if len(turns) != 2:
        errors.append("sandbox journey did not complete both tool turns")
    return errors


def _grade_sandbox_network_probes(stdout: str, evidence: dict[str, object]) -> list[str]:
    errors = []
    lowered = stdout.casefold()
    statuses = {}
    for probe in ("external_url", "internal_service", "dns"):
        if f"uat_{probe}_succeeded" in lowered:
            errors.append(f"sandbox {probe.replace('_', ' ')} probe returned success")
            statuses[probe] = "succeeded"
        elif f"uat_{probe}_blocked:" in lowered:
            statuses[probe] = "blocked"
        else:
            errors.append(f"sandbox {probe.replace('_', ' ')} isolation result was not observed")
            statuses[probe] = "unobserved"
    evidence["sandbox_network_probes"] = statuses
    return errors


def _observed_turn(
    prompt: str,
    text: str,
    trace: dict[str, object],
    names: tuple[str, ...],
    urls: tuple[str, ...],
) -> UATTurn:
    return UATTurn(prompt, text, trace, names, urls, _tool_results_from_trace(trace))


def _tool_results_from_trace(trace: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Executed results from this turn's trace. An OWUI task row is never the graded turn."""
    if not isinstance(trace, dict) or trace.get("owui_task"):
        return ()
    spans = trace.get("spans")
    if not isinstance(spans, list):
        return ()
    results: list[dict[str, object]] = []
    for span in spans:
        parsed = _completed_tool_result(span)
        if parsed is not None:
            results.append(parsed)
    return tuple(results)


def _completed_tool_result(span: object) -> dict[str, object] | None:
    if not isinstance(span, dict) or span.get("name") != "tool.completed":
        return None
    if "success" not in span:
        return None
    name = str(span.get("tool") or "")
    if not name:
        return None
    result: dict[str, object] = {
        "success": bool(span.get("success")),
        "stdout": str(span.get("stdout_head") or ""),
        "stderr": str(span.get("stderr_head") or ""),
    }
    if span.get("error_type"):
        result["error_type"] = span.get("error_type")
    return {"tool": name, "result": result}


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
    del turns, text
    minimum = 8.0 if case.grader == "music_quality" else 1.0
    errors = _grade_wav(payloads, minimum)
    wav_data = _first(payloads, "wav")
    if wav_data:
        _, metrics = validate_wav_quality(wav_data, minimum)
        evidence["audio_metrics"] = metrics
    requested = str(case.expected.get("speech") or "")
    if requested and wav_data:
        try:
            heard = transcribe_wav(wav_data)
        except Exception as exc:
            errors.append(f"speech artifact could not be verified by transcribe: {exc}")
        else:
            evidence["asr_text"] = heard
            missing = _missing_speech_words(requested, heard)
            if missing:
                errors.append(f"transcribed audio did not preserve: {', '.join(missing)}")
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
    del turns
    evidence["operator_review_required"] = True
    evidence["accuracy_limit"] = (
        "Harness ASR overlap is a floor; exact word accuracy needs operator review"
    )
    docx = _first(payloads, "docx")
    errors = [] if docx else ["no transcript DOCX was returned"]
    transcript_text = _docx_text(docx) if docx else ""
    speakers_source = transcript_text or text
    speakers = re.findall(
        r"\bspeaker(?:\s*[12]|[_ ]?0[01])\b", speakers_source, flags=re.IGNORECASE
    )
    if len({name.casefold() for name in speakers}) < 2:
        errors.append("transcript did not label both speakers")
    gold = _gold_transcript(case.attachment)
    if gold:
        evidence["gold_asr_words"] = len(_spoken_words(gold))
        overlap = _word_overlap(gold, transcript_text or text)
        evidence["asr_word_overlap"] = round(overlap, 3)
        if overlap < _ASR_WORD_OVERLAP_FLOOR:
            errors.append("transcript does not match the harness ASR of the fixture audio")
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
    status = _reported_hunt_status(text)
    for marker in ("source", "status"):
        if marker not in text.casefold():
            errors.append(f"hunt answer omitted the {marker} result")
    if status in {"COMPLETE", "PARTIAL", "FAILED"}:
        if not _hunt_tool_succeeded(turns, "hunt_leads"):
            errors.append("terminal hunt did not retrieve leads")
        if "lead" not in text.casefold():
            errors.append("hunt answer omitted the lead result")
    elif status == "RUNNING":
        if any(
            _hunt_tool_called(turns[2:], tool)
            for tool in ("hunt_sources", "hunt_leads", "hunt_case")
        ):
            errors.append("running hunt retrieved results before terminal status")
    else:
        errors.append("hunt status result did not contain a recognized state")
    if not re.search(r"\b[a-f0-9]{8,}\b", text, re.IGNORECASE):
        errors.append("hunt summary omitted an exact event or job identifier")
    return errors


def _reported_hunt_status(text: str) -> str:
    matches = re.findall(r"\b(RUNNING|COMPLETE|PARTIAL|FAILED)\b", text, re.I)
    return matches[-1].upper() if matches else ""


def _hunt_tool_called(turns: list[UATTurn], name: str) -> bool:
    return any(
        isinstance(item, dict) and item.get("tool") == name
        for turn in turns
        for item in turn.tool_results
    )


def _hunt_tool_succeeded(turns: list[UATTurn], name: str) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("tool") == name
        and isinstance(item.get("result"), dict)
        and item["result"].get("success")
        for turn in turns
        for item in turn.tool_results
    )


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
    if not _RETENTION_PERIOD_RE.search(turns[1].text) and not any(
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


def _grade_markers_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del payloads
    errors: list[str] = []
    lowered = text.casefold()
    for marker in case.expected.get("markers") or ():
        if str(marker).casefold() not in lowered:
            errors.append(f"answer omitted required marker {marker}")
    any_markers = case.expected.get("any_markers") or ()
    if any_markers and not any(str(m).casefold() in lowered for m in any_markers):
        errors.append(f"answer omitted all of: {', '.join(str(m) for m in any_markers)}")
    if case.expected.get("citation") and not re.search(r"https?://\S+|\[source", lowered):
        errors.append("answer carried no source citation")
    pattern = str(case.expected.get("pattern") or "")
    if pattern and not re.search(pattern, text, re.IGNORECASE):
        errors.append(f"answer did not match required pattern {pattern}")
    forbidden = {str(t).casefold() for t in case.expected.get("forbidden_tools") or ()}
    used = {name.casefold() for turn in turns for name in turn.tool_names}
    hit = sorted(forbidden & used)
    if hit:
        errors.append(f"read-only journey called mutating tools: {', '.join(hit)}")
    evidence["markers_checked"] = len(case.expected.get("markers") or ())
    return errors


def _grade_sandbox_lifecycle_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    errors = _grade_markers_case(case, turns, payloads, text, evidence)
    session_b = turns[1].text.casefold() if len(turns) > 1 else ""
    if "undefined" not in session_b:
        errors.append("session B did not report undefined as the isolated output")
    if "uat_leak_55" in session_b:
        errors.append("session B observed the leaked global; sessions are not isolated")
    return errors


def _grade_documents_readback_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del turns, evidence
    errors: list[str] = []
    xlsx = _first(payloads, "xlsx")
    if xlsx is None or validate_xlsx_content(
        xlsx, ("Asset", "Owner", "State"), str(case.expected["xlsx"])
    ):
        errors.append("XLSX is missing its required headers or data row")
    pptx = _first(payloads, "pptx")
    if pptx is None or validate_pptx_content(pptx, str(case.expected["pptx"])):
        errors.append("PPTX is missing its slide or required bullet")
    lowered = text.casefold()
    for key in ("xlsx", "pptx"):
        marker = str(case.expected[key]).casefold()
        if marker not in lowered:
            errors.append(f"read-back answer omitted {marker}")
    return errors


def _grade_documents_convert_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del turns, evidence
    errors: list[str] = []
    docx = _first(payloads, "docx")
    if docx is None or validate_docx_content(
        docx, "UAT Conversion Note", str(case.expected["docx"])
    ):
        errors.append("source DOCX is missing its heading or marker")
    pdf = _first(payloads, "pdf")
    if pdf is None or validate_pdf(pdf):
        errors.append("converted PDF was not returned or is invalid")
    lowered = text.casefold()
    marker = str(case.expected["docx"]).casefold()
    pdf_has_marker = False
    if pdf is not None:
        try:
            import fitz  # type: ignore[import-untyped]

            with fitz.open(stream=pdf, filetype="pdf") as doc:
                pdf_text = "\n".join(page.get_text() for page in doc).casefold()
            pdf_has_marker = marker in pdf_text
        except Exception:
            pdf_has_marker = marker.encode("utf-8") in pdf.lower()
    if marker not in lowered and not pdf_has_marker:
        errors.append("conversion answer and converted PDF omitted the document marker")
    if "pdf" not in lowered or not any(w in lowered for w in ("list", "generated", "files")):
        errors.append("answer did not report the generated-file listing")
    return errors


_REMOVAL_LANGUAGE = (
    "gone",
    "removed",
    "deleted",
    "forgotten",
    "no longer",
    "no memories",
    "empty",
    "absent",
)
_PERSISTENCE_LANGUAGE = (
    "still",
    "remains",
    "remained",
    "not been removed",
    "not been deleted",
)


def _marker_fully_removed(marker: str, final: str) -> bool:
    """The marker must be gone from the final text; any mention must sit next to
    removal language and never next to persistence language — the old
    `marker absent OR any absence phrase anywhere` let "X is still stored" pass."""
    occurrences = list(re.finditer(re.escape(marker), final)) if marker else []
    for match in occurrences:
        window = final[max(0, match.start() - 60) : match.end() + 60]
        if any(word in window for word in _PERSISTENCE_LANGUAGE):
            return False
        if not any(word in window for word in _REMOVAL_LANGUAGE):
            return False
    return True


def _grade_memory_admin_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del payloads, text
    marker = str(case.expected.get("marker") or "")
    errors: list[str] = []
    first = turns[0].text.casefold()
    has_uuid = bool(re.search(r"\b[0-9a-f]{8}-[0-9a-f]{4}-", first))
    if marker not in first and not has_uuid:
        errors.append("remember turn did not confirm the QAT marker or memory id")
    second = turns[1].text.casefold()
    if marker not in second and "forget" not in second:
        errors.append("admin turn neither listed the marker nor confirmed forget")
    final = turns[-1].text.casefold()
    cleaned = _marker_fully_removed(marker, final)
    if not cleaned:
        errors.append("final list_memories still shows the forgotten marker")
    evidence["cleanup_verified"] = cleaned
    return errors


def _grade_media_async_image_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del case, evidence
    errors = _grade_image(payloads, turns)
    if not re.search(r"\b[a-f0-9]{8,}\b", text, re.IGNORECASE):
        errors.append("answer omitted the async job identifier")
    return errors


def _stl_extents(data: bytes) -> list[float]:
    vertices = _stl_vertices(data)
    if not vertices:
        return []
    return [
        max(vertex[axis] for vertex in vertices) - min(vertex[axis] for vertex in vertices)
        for axis in range(3)
    ]


def _grade_cad_measure_convert_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del turns
    errors: list[str] = []
    stl_list = payloads.get("stl") or []
    stl = stl_list[-1] if stl_list else None
    extents = _stl_extents(stl) if stl else []
    wanted = sorted(float(v) for v in case.expected.get("extents") or ())
    if not extents:
        errors.append("no readable STL payload was downloaded")
    elif len(extents) != len(wanted) or any(
        abs(a - b) > max(0.5, b * 0.05) for a, b in zip(sorted(extents), wanted, strict=True)
    ):
        errors.append(f"STL bounds {extents!r} do not match the requested bracket {wanted!r}")
    png = _first(payloads, "png")
    if png is None or validate_png_quality(png):
        errors.append("no valid CAD render PNG was downloaded")
    obj = _first(payloads, "obj")
    if obj is None or b"v " not in obj:
        errors.append("convert_cad produced no OBJ mesh payload")
    lowered = text.casefold()
    for dim in wanted:
        if f"{dim:g}" not in lowered:
            errors.append(f"answer did not report the measured dimension {dim:g}")
    evidence["stl_extents"] = extents
    return errors


def _grade_compliance_policy_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del case, turns, payloads
    errors: list[str] = []
    lowered = text.casefold()
    _grade_compliance(text, errors, ("CIP-007-6 R2",))
    for part in ("2.1", "2.3", "2.4"):
        if part not in lowered:
            errors.append(f"gap analysis omitted CIP-007-6 R2 Part {part}")
    docs = ("ot-pol-007", "ot-proc-007", "patch management", "patch evaluation")
    if not any(marker in lowered for marker in docs):
        errors.append("answer did not identify the ingested patch policy/procedure")
    quotes = re.findall(r'"([^"]{15,})"', text) + re.findall(r"\u201c([^\u201d]{15,})\u201d", text)
    if len(quotes) < 2:
        errors.append("gap analysis did not quote both sides verbatim")
    gap = ("missing", "loose", "gap", "does not", "no explicit", "absent", "weaker", "not specify")
    if not any(marker in lowered for marker in gap):
        errors.append("answer did not identify where the procedure is loose or missing")
    scope = ("ingested", "corpus", "provided", "supplied", "documented")
    if not any(marker in lowered for marker in scope):
        errors.append("absence claims were not scoped to the ingested corpus")
    evidence["verbatim_quotes"] = len(quotes)
    return errors


def _grade_data_sql_case(
    case: UATCase,
    turns: list[UATTurn],
    payloads: dict[str, list[bytes]],
    text: str,
    evidence: dict[str, object],
) -> list[str]:
    del turns, payloads, evidence
    errors: list[str] = []
    lowered = text.casefold()
    for key in ("total", "north"):
        value = str(case.expected.get(key) or "")
        if value and not re.search(rf"(?<![\d.]){re.escape(value)}(?!\d)", lowered):
            errors.append(f"SQL answer omitted the exact {key} total {value}")
    if "orders" not in lowered:
        errors.append("SQL answer did not name the orders table")
    return errors


_CASE_GRADERS: dict[str, GradeHandler] = {
    "route": _grade_route_case,
    "route_security_handoff": _grade_security_route_case,
    "route_math": _grade_math_case,
    "daily_redirect": _grade_daily_case,
    "daily_no_suggestion": _grade_daily_no_suggestion,
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
    "sandbox_lifecycle": _grade_sandbox_lifecycle_case,
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
    **dict.fromkeys(
        (
            "persona_role_fit",
            "web_research",
            "obscura_navigate",
            "media_metadata",
            "security_toolbelt",
            "security_cve_triage",
            "proxmox_readonly",
            "introspection_git",
            "memory_graph",
        ),
        _grade_markers_case,
    ),
    "documents_readback": _grade_documents_readback_case,
    "documents_convert": _grade_documents_convert_case,
    "memory_admin": _grade_memory_admin_case,
    "media_async_image": _grade_media_async_image_case,
    "cad_measure_convert": _grade_cad_measure_convert_case,
    "compliance_policy_gap": _grade_compliance_policy_case,
    "data_sql": _grade_data_sql_case,
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
    evidence_qualifiers = (
        "evidence shown",
        "subject to",
        "cannot determine",
        "can't determine",
        "unable to determine",
        "not enough evidence",
        "depends on evidence",
        "dependent on evidence",
        "cannot certify",
        "can't certify",
        "unable to certify",
        "do not certify",
        "not certifying",
        "am not certifying",
        "remains unproven",
        "is unproven",
    )
    scope_qualifiers = (
        "does not require",
        "does not map",
        "patch-evaluation",
        "patch evaluation",
        "verbatim",
    )
    refuses_certification = any(
        phrase in lowered
        for phrase in (
            "cannot certify",
            "can't certify",
            "unable to certify",
            "do not certify",
            "not certifying",
            "am not certifying",
        )
    )
    if not any(term in lowered for term in evidence_qualifiers) and not (
        refuses_certification and any(term in lowered for term in scope_qualifiers)
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
        if p.style is not None
        and (p.style.name.startswith("Heading") or p.style.name in ("Title", "Subtitle"))
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


def _stl_vertices(data: bytes) -> list[tuple[float, float, float]]:
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
    return vertices


def validate_stl_geometry(data: bytes, expected_extent_mm: float = 20.0) -> str | None:
    vertices = _stl_vertices(data)
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

    if not case.artifact_kind:
        return []
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


def _stamp_served(result: QATResult, turns: list[UATTurn]) -> QATResult:
    if not turns:
        return result
    trace = turns[-1].trace
    if not result.served_model:
        result.served_model = str(trace.get("model") or "")
    if not result.backend:
        result.backend = str(trace.get("backend") or "")
    return result


_INFRA_HTTP_STATUSES = frozenset({401, 404, 429})


def _http_status_failure(
    scenario: QATScenario, status_code: int, chat_id: str, turns: list[UATTurn]
) -> QATResult:
    """5xx, 401, 404 and 429 are engine/proxy/auth; other 4xx stay product defects."""
    infra = status_code >= 500 or status_code in _INFRA_HTTP_STATUSES
    result = QATResult(
        scenario.scenario_id,
        Status.FAIL,
        f"OWUI returned HTTP {status_code}",
        defect_class=classify_defect(infra_hop_failed=infra),
        chat_id=chat_id,
    )
    return _stamp_served(result, turns)


def _status_result(
    scenario: QATScenario,
    error: str,
    chat_id: str = "",
    turns: list[UATTurn] | None = None,
) -> QATResult:
    infra = error.startswith("INFRA:")
    defect = (
        classify_defect(infra_hop_failed=True)
        if infra
        else classify_defect(tool_misbehaved="artifact" in error or "tool" in error)
    )
    result = QATResult(
        scenario.scenario_id, Status.FAIL, error, defect_class=defect, chat_id=chat_id
    )
    return _stamp_served(result, turns or [])


def _graded_failure(
    scenario: QATScenario,
    errors: list[str],
    chat_id: str,
    turns: list[UATTurn],
    evidence: dict[str, object],
) -> QATResult:
    result = QATResult(
        scenario.scenario_id,
        Status.FAIL,
        "; ".join(errors),
        defect_class=classify_defect(model_output_miss=True),
        chat_id=chat_id,
        artifacts=tuple(url for turn in turns for url in turn.artifact_urls),
        evidence=evidence,
    )
    return _stamp_served(result, turns)


def run_case(settings: Settings, scenario: QATScenario, state: Any, options: Any) -> QATResult:
    case = next(
        (c for c in discover_cases(state.discovery) if c.scenario_id == scenario.scenario_id), None
    )
    if case is None:
        return QATResult(
            scenario.scenario_id, Status.SKIP, "UAT case not present in current discovery"
        )
    if getattr(options, "api_only", False) and case.owui_memories:
        case = replace(case, owui_memories=())
    if not getattr(options, "api_only", False):
        return _run_browser_case(settings, scenario, case, state, options)
    if case.cross_session:
        return _run_memory_case(settings, scenario, case, options)
    return _run_chat_case(settings, scenario, case, options)


def _run_browser_case(
    settings: Settings, scenario: QATScenario, case: UATCase, state: Any, options: Any
) -> QATResult:
    client = OWUIClient(settings)
    run_dir = getattr(state, "run_dir", None) or (settings.repo_root / "results" / "qat_browser")
    ui = BrowserUI(settings, run_dir / "screenshots")
    token = ""
    memory_state = getattr(state, "provenance", {}).get("owui_memory_state", {})
    memory_managed = isinstance(memory_state, dict) and memory_state.get("status") == "clean"
    memory_prepared = False
    try:
        ui.start()
    except PlaywrightUnavailable as exc:
        return QATResult(
            scenario.scenario_id,
            Status.FAIL,
            f"browser GUI driver unavailable: {exc}",
            defect_class=classify_defect(infra_hop_failed=True),
            evidence={"driver": "browser_gui"},
        )
    try:
        token = client.signin()
        if memory_managed:
            memory_prepared = True
            client.replace_memories(token, case.owui_memories)
        elif case.owui_memories:
            raise RuntimeError("QAT OWUI memory baseline was not prepared")
        ui.login()
        if case.cross_session:
            return _run_browser_memory(ui, client, token, settings, scenario, case, state, options)
        return _run_browser_chat(ui, client, token, settings, scenario, case, state, options)
    except Exception as exc:
        return QATResult(
            scenario.scenario_id,
            Status.FAIL,
            f"{type(exc).__name__}: {exc}",
            defect_class=classify_defect(infra_hop_failed=True),
            evidence={"driver": "browser_gui"},
        )
    finally:
        try:
            if memory_prepared and token:
                client.clear_memories(token)
        finally:
            ui.stop()


def _run_browser_chat(
    ui: BrowserUI,
    client: OWUIClient,
    token: str,
    settings: Settings,
    scenario: QATScenario,
    case: UATCase,
    state: Any,
    options: Any,
) -> QATResult:
    ui.new_chat()
    if case.roster_check:
        missing = _roster_missing(state, ui)
        if missing:
            result = _status_result(
                scenario, f"model selector missing seeded entries: {', '.join(missing)}", "", []
            )
            result.evidence = {"driver": "browser_gui", "roster_missing": missing}
            return result
    ui.select_model(case.model_slug, _preset_display_name(state, case))
    gui_tools = ui.inspect_and_manage_tools(case.expected_tools)
    deadline = time.monotonic() + case.timeout_s
    turns, error, chat_id = _run_browser_sequence(
        ui, client, token, settings, scenario, case, deadline
    )
    extra = _browser_evidence(ui, scenario)
    extra["gui_tools"] = gui_tools
    if error is None:
        gui_errors = _gui_transparency_errors(case, extra)
        if gui_errors:
            error = _status_result(scenario, "; ".join(gui_errors), chat_id, turns)
    if error:
        error.chat_id = chat_id
        error.evidence = {**(error.evidence or {}), **extra}
        if chat_id:
            return _archive_chat(client, token, chat_id, scenario, options, error)
        return error
    return _finalize_turns(client, token, chat_id, scenario, case, options, turns, extra)


def _run_browser_sequence(
    ui: BrowserUI,
    client: OWUIClient,
    token: str,
    settings: Settings,
    scenario: QATScenario,
    case: UATCase,
    deadline: float,
    memory_key: str = "",
) -> tuple[list[UATTurn], QATResult | None, str]:
    from . import runner

    transcript: list[UATTurn] = []
    chat_id = ""
    infra = _scenario_wav_infra(case)
    if infra:
        return transcript, _status_result(scenario, infra, chat_id, transcript), chat_id
    prompts = list(case.prompts)
    for index, template in enumerate(prompts, start=1):
        prompt = template.replace("{{memory_key}}", memory_key)
        with tempfile.TemporaryDirectory(prefix="uat-browser-upload-") as tmp:
            upload_path, error = _browser_turn_upload(
                client, token, settings, case, index, transcript, Path(tmp), deadline
            )
            if error:
                return transcript, _status_result(scenario, error, chat_id, transcript), chat_id
            started_at = time.time()
            text = ui.send_turn(
                prompt, upload_path=upload_path, max_wait_s=max(0.0, deadline - time.monotonic())
            )
        chat_id = ui.current_chat_id() or chat_id
        trace = client.lookup_trace(
            model_slug=case.model_slug, turn_started_at=started_at, deadline=deadline, token=token
        )
        served = runner._served_engine_model(trace, "")
        failure = runner._primary_model_failure(scenario, trace, served, chat_id)
        if failure:
            return transcript, failure, chat_id
        urls = _browser_artifact_urls(ui, text)
        leak = raw_tool_error_leak(text)
        if leak:
            leaked = _observed_turn(prompt, text, trace, (), urls)
            return (
                transcript,
                _status_result(
                    scenario, f"raw tool error leaked: {leak}", chat_id, [*transcript, leaked]
                ),
                chat_id,
            )
        transcript.append(
            _observed_turn(prompt, text, trace, _tool_names_from_calls((), trace), urls)
        )
        poll_prompt = _media_job_followup_prompt(case, transcript)
        if poll_prompt and time.monotonic() + 25 < deadline:
            prompts.append(poll_prompt)
    tool_error = _required_tool_error(case, transcript)
    if tool_error:
        return transcript, _status_result(scenario, tool_error, chat_id, transcript), chat_id
    return transcript, None, chat_id


def _wav_followup(case: UATCase, index: int) -> Path | None:
    """Real fixture for a WAV read-back turn. Generated audio is never re-uploaded."""
    if index != case.generated_upload_turn:
        return None
    if str(case.expected.get("upload_kind") or "").lower() != "wav":
        return None
    return REPO_ROOT / REAL_WAV_FIXTURE


def _scenario_wav_infra(case: UATCase) -> str | None:
    """Magic-byte check before any turn. A bad WAV is harness infra, not a model miss."""
    paths: list[Path] = []
    if case.attachment.lower().endswith(".wav"):
        path = Path(case.attachment)
        paths.append(path if path.is_absolute() else REPO_ROOT / path)
    if case.generated_upload_turn:
        follow = _wav_followup(case, case.generated_upload_turn)
        if follow is not None:
            paths.append(follow)
    for path in paths:
        error = wav_magic_error(path)
        if error:
            return error
    return None


def _checked_wav(path: Path) -> tuple[Path | None, str | None]:
    error = wav_magic_error(path)
    return (None, error) if error else (path, None)


def _browser_turn_upload(
    client: OWUIClient,
    token: str,
    settings: Settings,
    case: UATCase,
    index: int,
    turns: list[UATTurn],
    tmp_dir: Path,
    deadline: float,
) -> tuple[Path | None, str | None]:
    follow = _wav_followup(case, index)
    if follow is not None:
        return _checked_wav(follow)
    if index == 1 and case.attachment:
        path = Path(case.attachment)
        if not path.is_absolute():
            path = settings.repo_root / path
        if not path.is_file():
            return None, f"attachment not found: {path}"
        if path.suffix.lower() == ".wav":
            return _checked_wav(path)
        return path, None
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
        return None, f"generated {suffix.upper()} was not surfaced before the read-back turn"
    data = client.download_artifact(token, url)
    if not data:
        return None, f"generated {suffix.upper()} download returned no bytes"
    filename = "uat-generated-note.docx" if suffix == "docx" else f"uat-generated-{suffix}.{suffix}"
    path = tmp_dir / filename
    path.write_bytes(data)
    return path, None


def _browser_evidence(ui: BrowserUI, scenario: QATScenario) -> dict[str, object]:
    shot = ui.screenshot(scenario.scenario_id)
    users, assistants = ui.visible_turn_count()
    return {
        "driver": "browser_gui",
        "screenshot": str(shot),
        "visible_turns": {"user": users, "assistant": assistants},
        "browser_errors": ui.result_errors(),
    }


def _gui_transparency_errors(case: UATCase, extra: dict[str, object]) -> list[str]:
    errors: list[str] = []
    browser_errors = extra.get("browser_errors")
    page_errors = browser_errors.get("page_errors") if isinstance(browser_errors, dict) else []
    if page_errors:
        errors.append(f"browser page errors: {'; '.join(str(e) for e in page_errors)}")
    visible = extra.get("visible_turns")
    users = int(visible.get("user", 0)) if isinstance(visible, dict) else 0
    assistants = int(visible.get("assistant", 0)) if isinstance(visible, dict) else 0
    if users < len(case.prompts):
        errors.append(f"GUI rendered {users}/{len(case.prompts)} user prompts (orphaned replies)")
    if assistants < len(case.prompts):
        errors.append(f"GUI rendered {assistants}/{len(case.prompts)} assistant responses")
    return errors


def _roster_missing(state: Any, ui: BrowserUI) -> list[str]:
    discovery = getattr(state, "discovery", None)
    presets = getattr(discovery, "presets", {}) or {}
    roster = {name.casefold() for name in ui.workspace_roster()}
    missing = [
        pid
        for pid, preset in presets.items()
        if pid.casefold() not in roster and str(preset.name).casefold() not in roster
    ]
    for spec in _seeded_personas(discovery, PERSONA_DIR) if discovery is not None else []:
        slug = str(spec.get("slug") or "")
        name = str(spec.get("name") or slug)
        if slug.casefold() not in roster and name.casefold() not in roster:
            missing.append(slug)
    return missing


def _preset_display_name(state: Any, case: UATCase) -> str:
    discovery = getattr(state, "discovery", None)
    presets = getattr(discovery, "presets", {}) or {}
    preset = presets.get(case.model_slug)
    if preset is None and "::" in case.model_slug:
        preset = presets.get(case.model_slug.split("::", 1)[0])
    if preset is not None:
        return str(getattr(preset, "name", "") or "")
    personas = getattr(discovery, "personas", ()) or ()
    persona = next((p for p in personas if getattr(p, "slug", "") == case.model_slug), None)
    return str(getattr(persona, "name", "") or "") if persona else ""


def _browser_artifact_urls(ui: BrowserUI, text: str) -> tuple[str, ...]:
    dom = ui.last_artifact_links()
    return tuple(dict.fromkeys([*dom, *artifact_urls({"content": text})]))


def _memory_prompts(case: UATCase, memory_key: str, memory_marker: str) -> list[str]:
    return [
        prompt.replace("{{memory_key}}", memory_key).replace("{{memory_marker}}", memory_marker)
        for prompt in case.prompts
    ]


def _run_browser_memory(
    ui: BrowserUI,
    client: OWUIClient,
    token: str,
    settings: Settings,
    scenario: QATScenario,
    case: UATCase,
    state: Any,
    options: Any,
) -> QATResult:
    from . import runner

    run_marker = uuid.uuid4().hex[:10]
    memory_key = f"QATUAT-{run_marker}"
    memory_marker = f"QAT-MARK-{run_marker}"
    prompts = _memory_prompts(case, memory_key, memory_marker)
    display = _preset_display_name(state, case)
    chats: list[str] = []
    records: list[UATTurn] = []
    shots: list[str] = []
    for index, prompt in enumerate(prompts, start=1):
        ui.new_chat()
        ui.select_model(case.model_slug, display)
        session_case = replace(
            case,
            prompts=(prompt,),
            cross_session=False,
            expected_tools=("remember",) if index == 1 else ("recall",),
        )
        session_scenario = QATScenario(
            scenario.scenario_id,
            scenario.title,
            scenario.stage,
            scenario.phase,
            scenario.tier,
            scenario.model_slug,
            prompts=(prompt,),
            tools=case.tool_ids,
            expected_tools=session_case.expected_tools,
        )
        turns, error, chat_id = _run_browser_sequence(
            ui,
            client,
            token,
            settings,
            session_scenario,
            session_case,
            time.monotonic() + case.timeout_s / 2,
            memory_key,
        )
        shots.append(str(ui.screenshot(f"{scenario.scenario_id}-chat{index}")))
        if chat_id:
            chats.append(chat_id)
        if error:
            for opened in chats:
                runner._finalize_chat(client, token, opened, scenario, Status.FAIL, options)
            error.evidence = {
                **(error.evidence or {}),
                "driver": "browser_gui",
                "screenshots": shots,
                "browser_errors": ui.result_errors(),
            }
            return error
        records.extend(turns)
    return _finish_browser_memory(
        ui, client, token, scenario, case, options, chats, records, shots, memory_key
    )


def _finish_browser_memory(
    ui: BrowserUI,
    client: OWUIClient,
    token: str,
    scenario: QATScenario,
    case: UATCase,
    options: Any,
    chats: list[str],
    records: list[UATTurn],
    shots: list[str],
    memory_key: str,
) -> QATResult:
    from . import runner

    errors, evidence = grade_case(case, records, {})
    evidence["chat_ids"] = chats
    evidence["driver"] = "browser_gui"
    evidence["screenshot"] = shots[-1] if shots else ""
    evidence["screenshots"] = shots
    users, assistants = ui.visible_turn_count()
    evidence["visible_turns"] = {"user": users, "assistant": assistants}
    evidence["browser_errors"] = ui.result_errors()
    if len(set(chats)) != len(case.prompts):
        errors.append("memory round-trip did not use a distinct OWUI chat for each session")
    recalled = records[-1].text.casefold()
    if memory_key.casefold() not in recalled or "cobalt" not in recalled:
        errors.append("new chat did not recall both facts saved in the previous chat")
    if ui.result_errors()["page_errors"]:
        errors.append("browser page errors during memory round-trip")
    for chat_id in chats:
        runner._finalize_chat(
            client, token, chat_id, scenario, Status.PASS if not errors else Status.FAIL, options
        )
    if errors:
        return _stamp_served(
            QATResult(
                scenario.scenario_id,
                Status.FAIL,
                "; ".join(errors),
                defect_class=classify_defect(model_output_miss=True),
                evidence=evidence,
            ),
            records,
        )
    return QATResult(
        scenario.scenario_id,
        Status.PASS,
        "memory persisted across distinct OWUI chats",
        chat_id=chats[-1],
        evidence=evidence,
    )


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
        return _finalize_turns(client, token, chat_id, scenario, case, options, turns)
    except Exception as exc:
        return QATResult(
            scenario.scenario_id,
            Status.FAIL,
            f"{type(exc).__name__}: {exc}",
            defect_class=classify_defect(infra_hop_failed=True),
        )


def _finalize_turns(
    client: OWUIClient,
    token: str,
    chat_id: str,
    scenario: QATScenario,
    case: UATCase,
    options: Any,
    turns: list[UATTurn],
    extra_evidence: dict[str, object] | None = None,
) -> QATResult:
    """Download artifacts, run every grader, and archive — shared by both drivers."""
    payloads, download_error, download_defect = _download_payloads(client, token, turns)
    if download_error:
        result = QATResult(
            scenario.scenario_id,
            Status.FAIL,
            download_error,
            defect_class=download_defect,
            chat_id=chat_id,
        )
        return _archive_chat(
            client, token, chat_id, scenario, options, _stamp_served(result, turns)
        )
    errors = _grade_payload_types(case, payloads)
    quality_errors, evidence = grade_case(case, turns, payloads)
    evidence.update(extra_evidence or {})
    errors.extend(quality_errors)
    if errors:
        result = _graded_failure(scenario, errors, chat_id, turns, evidence)
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
    infra = _scenario_wav_infra(case)
    if infra:
        return transcript, _status_result(scenario, infra, chat_id, transcript)
    prompts = list(case.prompts)
    for index, template in enumerate(prompts, start=1):
        prompt = template.replace("{{memory_key}}", memory_key)
        files, error = _turn_files(client, token, case, index, transcript, deadline)
        if error:
            return transcript, _status_result(scenario, error, chat_id, transcript)
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
            return transcript, _http_status_failure(
                scenario, response.status_code, chat_id, transcript
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
            leaked = _observed_turn(prompt, outcome.text, outcome.trace, (), outcome.artifact_urls)
            return transcript, _status_result(
                scenario,
                f"raw tool error leaked: {outcome.leak_marker}",
                chat_id,
                [*transcript, leaked],
            )
        names = _tool_names_from_calls(outcome.tool_calls, outcome.trace)
        transcript.append(
            _observed_turn(prompt, outcome.text, outcome.trace, names, outcome.artifact_urls)
        )
        branch.extend(
            ({"role": "user", "content": prompt}, {"role": "assistant", "content": outcome.text})
        )
        poll_prompt = _media_job_followup_prompt(case, transcript)
        if poll_prompt and time.monotonic() + 25 < deadline:
            prompts.append(poll_prompt)
    tool_error = _required_tool_error(case, transcript)
    if tool_error:
        return transcript, _status_result(scenario, tool_error, chat_id, transcript)
    return transcript, None


def _successful_tools(turn: UATTurn) -> set[str]:
    spans = turn.trace.get("spans") or turn.trace.get("tool_spans") or []
    if not isinstance(spans, list):
        return set()
    return {
        str(span.get("tool") or "").casefold()
        for span in spans
        if isinstance(span, dict)
        and span.get("name") == "tool.completed"
        and span.get("outcome") == "ok"
    }


_MEDIA_JOB_TOOLS = {
    "image_start": "image_status",
    "video_start": "video_status",
    "music_start": "music_status",
}


def _has_media_job(turns: list[UATTurn]) -> bool:
    return any(start in _successful_tools(turn) for start in _MEDIA_JOB_TOOLS for turn in turns)


def _media_job_followup_prompt(case: object, turns: list[UATTurn]) -> str | None:
    """Schedule a separate status turn until a started media job returns a file link."""
    expected_extensions = {
        "audio": {".wav", ".mp3"},
        "mp3": {".mp3"},
        "mp4": {".mp4"},
        "png": {".png"},
        "wav": {".wav"},
    }.get(str(getattr(case, "artifact_kind", "")).casefold())
    if not expected_extensions:
        return None
    if any(
        Path(urlsplit(url).path).suffix.casefold() in expected_extensions
        for turn in turns
        for url in turn.artifact_urls
    ):
        return None
    start = next(
        (name for name in _MEDIA_JOB_TOOLS if any(name in _successful_tools(t) for t in turns)),
        None,
    )
    if start is None:
        return None
    status_tool = _MEDIA_JOB_TOOLS[start]
    prompt = (
        f"QAT media status poll: Use {status_tool} with the job_id from the earlier turn and "
        "wait_s=20. If it is queued or still running, report current progress and include exactly "
        "MEDIA_JOB_RUNNING. If done, return the download_url. If it failed, repeat the error and "
        "stop."
    )
    poll_turns = [turn for turn in turns if turn.prompt.startswith("QAT media status poll:")]
    if not poll_turns:
        return prompt
    latest = poll_turns[-1]
    if status_tool in _successful_tools(latest) and "MEDIA_JOB_RUNNING" in latest.text:
        return prompt
    return None


def _required_tool_error(case: UATCase, turns: list[UATTurn]) -> str | None:
    by_turn = [_successful_tools(turn) for turn in turns]
    successful = {tool for names in by_turn for tool in names}
    raw_per_turn = case.expected.get("tools_per_turn")
    per_turn = (
        [[str(t) for t in group] for group in raw_per_turn if isinstance(group, (list, tuple))]
        if isinstance(raw_per_turn, list)
        else []
    )
    scoped = {tool.casefold() for group in per_turn for tool in group}
    missing = [
        tool
        for tool in case.expected_tools
        if tool.casefold() not in successful and tool.casefold() not in scoped
    ]
    for index, group in enumerate(per_turn):
        done = by_turn[index] if index < len(by_turn) else set()
        missing.extend(f"turn {index + 1}:{tool}" for tool in group if tool.casefold() not in done)
    raw_alternatives = case.expected.get("required_any_tools")
    alternatives = (
        tuple(str(tool) for tool in raw_alternatives) if isinstance(raw_alternatives, list) else ()
    )
    if alternatives and not any(tool.casefold() in successful for tool in alternatives):
        missing.append(f"one of {', '.join(alternatives)}")
    return (
        f"required tools did not complete successfully: {', '.join(missing)}" if missing else None
    )


def _turn_files(
    client: OWUIClient, token: str, case: UATCase, index: int, turns: list[UATTurn], deadline: float
) -> tuple[list[dict[str, str]] | None, str | None]:
    follow = _wav_followup(case, index)
    if follow is not None:
        path, error = _checked_wav(follow)
        if error or path is None:
            return None, error
        return [client.upload_attachment(token, str(path), deadline)], None
    if index == 1 and case.attachment:
        path = Path(case.attachment)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if path.suffix.lower() == ".wav":
            checked, error = _checked_wav(path)
            if error or checked is None:
                return None, error
            return [client.upload_attachment(token, str(checked), deadline)], None
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
        return None, f"generated {suffix.upper()} was not surfaced before the read-back turn"
    data = client.download_artifact(token, url)
    if not data:
        return None, f"generated {suffix.upper()} download returned no bytes"
    filename = "uat-generated-note.docx" if suffix == "docx" else f"uat-generated-{suffix}.{suffix}"
    return [client.upload_attachment_bytes(token, filename, data, deadline)], None


def _download_payloads(
    client: OWUIClient, token: str, turns: list[UATTurn]
) -> tuple[dict[str, list[bytes]], str | None, DefectClass | None]:
    """Download surfaced artifacts; failures carry their own defect class (F14):
    transport/5xx deaths are infra, a missing (4xx) or empty (HTTP 200, 0 bytes)
    artifact is the product's."""
    payloads: dict[str, list[bytes]] = {}
    empty_by_kind: list[tuple[str, str]] = []
    urls = list(dict.fromkeys(url for turn in turns for url in turn.artifact_urls))
    for url in urls:
        kind = Path(urlsplit(url).path).suffix.lower().lstrip(".")
        try:
            data = client.download_artifact(token, url)
        except ArtifactDownloadError as exc:
            infra = exc.status_code == 0 or exc.status_code >= 500
            return (
                payloads,
                f"artifact download failed: {exc}",
                DefectClass.INFRA_ENV_GAP if infra else DefectClass.PRODUCT_BUG,
            )
        if data:
            payloads.setdefault(kind, []).append(data)
        else:
            empty_by_kind.append((kind, url))
    for kind, url in empty_by_kind:
        if not payloads.get(kind):
            return payloads, f"artifact download was empty: {url}", DefectClass.PRODUCT_BUG
    return payloads, None, None


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
        run_marker = uuid.uuid4().hex[:10]
        memory_key = f"QATUAT-{run_marker}"
        memory_marker = f"QAT-MARK-{run_marker}"
        prompts = _memory_prompts(case, memory_key, memory_marker)
        chats: list[str] = []
        records: list[UATTurn] = []
        for index, prompt in enumerate(prompts, start=1):
            chat_id = client.create_chat(
                token, case.model_slug, f"UAT: {case.scenario_id} · {index}", prompt
            )
            chats.append(chat_id)
            session_prompts = (prompt,)
            session_tools = ("remember",) if index == 1 else ("recall",)
            session_case = replace(
                case,
                prompts=session_prompts,
                cross_session=False,
                expected_tools=session_tools,
            )
            session_scenario = QATScenario(
                scenario.scenario_id,
                scenario.title,
                scenario.stage,
                scenario.phase,
                scenario.tier,
                scenario.model_slug,
                prompts=session_prompts,
                tools=case.tool_ids,
                expected_tools=session_case.expected_tools,
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
            return _stamp_served(
                QATResult(
                    scenario.scenario_id,
                    Status.FAIL,
                    "; ".join(errors),
                    defect_class=classify_defect(model_output_miss=True),
                    evidence=evidence,
                ),
                records,
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
