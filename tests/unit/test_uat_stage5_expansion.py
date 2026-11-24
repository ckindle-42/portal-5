"""Offline checks for the Stage 5 full-feature UAT expansion journeys and graders."""

from __future__ import annotations

import ast
import io
import json
import struct
from pathlib import Path

import pytest
from docx import Document
from openpyxl import Workbook
from PIL import Image
from pptx import Presentation
from pptx.oxml.xmlchemy import OxmlElement

from tests.qat import uat_behavioral as uat
from tests.qat.config import PRESETS_JSON, Discovery, OwuiPreset, discover, load_presets

EXPANSION_IDS = {
    "s5-gui-persona-roster",
    "s5-browser-web-research",
    "s5-browser-web-research-obscura",
    "s5-sandbox-lifecycle",
    "s5-documents-full-lifecycle",
    "s5-documents-full-lifecycle-convert",
    "s5-memory-graph-admin",
    "s5-memory-graph-admin-lifecycle",
    "s5-media-async-poll-image",
    "s5-media-async-poll-music",
    "s5-media-async-poll-video",
    "s5-cad-measurement-and-convert",
    "s5-security-toolbelt",
    "s5-security-toolbelt-cve",
    "s5-compliance-policy-conversation",
    "s5-proxmox-readonly",
    "s5-platform-introspection-and-git",
}


def _turn(text: str, tool_names: tuple[str, ...] = ()) -> uat.UATTurn:
    return uat.UATTurn("user prompt", text, {}, tool_names, ())


def _case(
    grader: str,
    prompts: tuple[str, ...],
    expected: dict[str, object] | None = None,
    artifact_kind: str = "",
) -> uat.UATCase:
    return uat.UATCase(
        "s5-test", "t", "auto", prompts, grader, expected or {}, artifact_kind=artifact_kind
    )


def _png() -> bytes:
    image = Image.new("RGB", (160, 160), (10, 20, 30))
    for x in range(160):
        for y in range(160):
            if (x + y) % 2:
                image.putpixel((x, y), (240, 20, 30))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _box_stl(dims: tuple[float, float, float]) -> bytes:
    dx, dy, dz = dims
    points = {
        "000": (0.0, 0.0, 0.0),
        "100": (dx, 0.0, 0.0),
        "010": (0.0, dy, 0.0),
        "110": (dx, dy, 0.0),
        "001": (0.0, 0.0, dz),
        "101": (dx, 0.0, dz),
        "011": (0.0, dy, dz),
        "111": (dx, dy, dz),
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
    return b"uat box".ljust(80, b"\0") + len(faces).to_bytes(4, "little") + triangles


def _xlsx(marker: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Asset", "Owner", "State"])
    sheet.append([marker, "Priya", "active"])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _pptx(marker: str) -> bytes:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    paragraph = slide.shapes.placeholders[1].text_frame.paragraphs[0]
    paragraph.text = marker
    paragraph._p.get_or_add_pPr().append(OxmlElement("a:buChar"))
    stream = io.BytesIO()
    presentation.save(stream)
    return stream.getvalue()


def _docx(heading: str, marker: str) -> bytes:
    doc = Document()
    doc.add_heading(heading, level=1)
    doc.add_paragraph(marker)
    stream = io.BytesIO()
    doc.save(stream)
    return stream.getvalue()


# --------------------------------------------------------------- discovery


def test_expansion_journeys_are_discovered_and_multiturn() -> None:
    cases = uat.discover_cases(discover())
    found = {case.scenario_id: case for case in cases if case.scenario_id in EXPANSION_IDS}
    # s5-data-sql's ::data variant is not an exposed OWUI preset at HEAD, so it skips cleanly.
    assert EXPANSION_IDS - {"s5-data-sql"} <= set(found)
    for case in found.values():
        assert len(case.prompts) >= 2, case.scenario_id
        assert case.grader in uat._CASE_GRADERS, case.scenario_id
        assert case.expected_tools, case.scenario_id
    assert found["s5-gui-persona-roster"].roster_check is True


def test_expansion_registry_is_stage5_and_unique() -> None:
    registry = uat.build_registry(discover())
    expansion = [s for s in registry if s.scenario_id in EXPANSION_IDS]
    assert expansion
    assert {s.stage for s in expansion} == {5}
    assert {s.phase for s in expansion} == {uat.UAT_PHASE}
    ids = [s.scenario_id for s in registry]
    assert len(ids) == len(set(ids))


def test_expansion_skips_cleanly_on_empty_discovery() -> None:
    empty = Discovery(
        modules_enabled=frozenset(),
        workspaces={},
        presets={},
        personas=(),
        bench_workspaces={},
        mcp_fleet=(),
    )
    cases = uat.discover_cases(empty)
    assert not (EXPANSION_IDS & {case.scenario_id for case in cases})


def test_expansion_gates_on_tool_names(monkeypatch: pytest.MonkeyPatch) -> None:
    discovery = discover()
    real = uat._tool_names
    # Drop execute_nodejs from every seat: the sandbox lifecycle journey must vanish.
    monkeypatch.setattr(
        uat,
        "_tool_names",
        lambda d, preset: real(d, preset) - {"execute_nodejs"},
    )
    cases = uat.discover_cases(discovery)
    ids = {case.scenario_id for case in cases}
    assert "s5-sandbox-lifecycle" not in ids
    assert "s5-security-toolbelt" in ids  # unrelated journey still present


def test_data_sql_emits_when_variant_exposed(monkeypatch: pytest.MonkeyPatch) -> None:
    discovery = discover()
    discovery.presets["auto-research::data"] = OwuiPreset(
        "auto-research::data", "Data", ("server:mcp:portal_data"), True, ""
    )
    monkeypatch.setattr(
        uat,
        "_tool_names",
        lambda _d, preset: (
            {"attach_source", "profile_table", "run_sql", "list_session"}
            if preset == "auto-research::data"
            else set()
        ),
    )
    cases: list[uat.UATCase] = []
    uat._data_sql_case(discovery, cases)
    assert [case.scenario_id for case in cases] == ["s5-data-sql"]
    assert cases[0].expected == {"total": "133", "north": "76"}
    assert cases[0].expected_tools == ("attach_source", "list_session", "profile_table", "run_sql")


# --------------------------------------------------------------- generic marker grader


@pytest.mark.parametrize(
    ("grader", "expected", "good", "bad"),
    [
        (
            "persona_role_fit",
            {"markers": ["429"], "any_markers": ["too many requests"], "citation": True},
            "429 means too many requests; see https://rfc-editor.org/rfc6585",
            "The status code is defined in an RFC.",
        ),
        (
            "web_research",
            {"markers": ["429"], "any_markers": ["rate limit"], "citation": True},
            "429 is rate limiting. Source: https://developer.mozilla.org/429",
            "429 is rate limiting, no source given.",
        ),
        (
            "obscura_navigate",
            {"markers": ["example domain"], "any_markers": ["heading"]},
            "The snapshot heading reads Example Domain.",
            "The page loaded successfully.",
        ),
        (
            "sandbox_lifecycle",
            {
                "markers": ["uat_nodejs_87", "uat_py_session_91", "undefined"],
                "any_markers": ["docker"],
            },
            "UAT_NODEJS_87 and UAT_PY_SESSION_91 printed; typeof is undefined; docker available.",
            "UAT_NODEJS_87 printed; the leak variable was a string.",
        ),
        (
            "media_metadata",
            {"markers": ["acestep", "voice"], "any_markers": ["48000"]},
            "acestep renders at 48000 Hz; voice af_heart is listed.",
            "Music engines are available.",
        ),
        (
            "memory_graph",
            {"markers": ["qat-graph-9d4"], "any_markers": ["neighbor"]},
            "graph_recall returned QAT-GRAPH-9D4 with neighbor entity Orchid.",
            "The graph returned several entities.",
        ),
        (
            "security_cve_triage",
            {"markers": ["cve-2021-44228", "epss", "kev"], "any_markers": ["critical"]},
            "CVE-2021-44228 is critical; EPSS 0.97; in KEV catalog.",
            "CVE-2021-44228 is a serious vulnerability.",
        ),
    ],
)
def test_marker_graders_pass_and_fail(
    grader: str, expected: dict[str, object], good: str, bad: str
) -> None:
    case = _case(grader, ("first", "second"), expected)
    assert uat.grade_case(case, [_turn(good), _turn(good)], {})[0] == []
    assert uat.grade_case(case, [_turn(bad), _turn(bad)], {})[0]


def test_security_toolbelt_full_markers() -> None:
    expected = {
        "markers": ["cve-2021-44228", "epss", "kev", "t1190", "public-facing", "sigma", "spl"],
        "any_markers": ["critical", "cvss"],
    }
    case = _case("security_toolbelt", ("a", "b", "c"), expected)
    good = (
        "CVE-2021-44228 CVSS critical; EPSS 0.97; in KEV. T1190 Exploit Public-Facing "
        "Application. SPL validated ok; Sigma rule valid."
    )
    assert uat.grade_case(case, [_turn(good)] * 3, {})[0] == []
    assert uat.grade_case(case, [_turn("CVE-2021-44228 critical")] * 3, {})[0]


def test_readonly_journeys_reject_mutating_tools() -> None:
    proxmox = _case(
        "proxmox_readonly",
        ("a", "b"),
        {
            "markers": ["cluster", "node"],
            "any_markers": ["vmid"],
            "forbidden_tools": list(uat._PROXMOX_WRITE_TOOLS),
        },
    )
    good = "cluster quorate; node pve1 online; vmid 100 running."
    assert uat.grade_case(proxmox, [_turn(good, ("proxmox_list_vms",))] * 2, {})[0] == []
    errors = uat.grade_case(proxmox, [_turn(good, ("proxmox_vm_start",))] * 2, {})[0]
    assert any("mutating tools" in error for error in errors)

    git = _case(
        "introspection_git",
        ("a", "b"),
        {
            "markers": ["backend", "commit"],
            "any_markers": ["branch"],
            "pattern": r"\b[0-9a-f]{7,40}\b",
            "forbidden_tools": ["git_commit", "git_push"],
        },
    )
    good_git = "3 backends healthy; branch main clean; commit abc1234def initial."
    assert uat.grade_case(git, [_turn(good_git, ("git_status", "git_log"))] * 2, {})[0] == []
    assert any(
        "mutating tools" in error
        for error in uat.grade_case(git, [_turn(good_git, ("git_push",))] * 2, {})[0]
    )
    assert uat.grade_case(git, [_turn("backends; branch main; commit none")] * 2, {})[0]


# --------------------------------------------------------------- artifact graders


def test_documents_readback_grader() -> None:
    case = _case(
        "documents_readback",
        ("a", "b", "c"),
        {"xlsx": "UAT-XLSX-62", "pptx": "UAT-PPTX-83"},
        artifact_kind="xlsx+pptx",
    )
    payloads = {"xlsx": [_xlsx("UAT-XLSX-62")], "pptx": [_pptx("UAT-PPTX-83")]}
    good = "read_excel shows UAT-XLSX-62; read_powerpoint bullet UAT-PPTX-83."
    assert uat.grade_case(case, [_turn(good)] * 3, payloads)[0] == []
    assert uat.grade_case(case, [_turn("nothing quoted")] * 3, payloads)[0]
    assert uat.grade_case(case, [_turn(good)] * 3, {})[0]


def test_documents_convert_grader() -> None:
    case = _case(
        "documents_convert",
        ("a", "b", "c"),
        {"docx": "UAT-CONV-45"},
        artifact_kind="docx+pdf",
    )
    payloads = {"docx": [_docx("UAT Conversion Note", "UAT-CONV-45")], "pdf": [b"%PDF-1.4 test"]}
    good = "Converted UAT-CONV-45 to PDF; list_generated_files shows the PDF."
    assert uat.grade_case(case, [_turn(good)] * 3, payloads)[0] == []
    assert uat.grade_case(case, [_turn(good)] * 3, {"docx": payloads["docx"]})[0]


def test_media_async_image_grader() -> None:
    case = _case("media_async_image", ("a", "b"), artifact_kind="png")
    url = "http://localhost/api/v1/files/abcd1234/content/image.png"
    turn = uat.UATTurn("p", f"Job abcd1234ef done. {url}", {}, (), (url,))
    assert uat.grade_case(case, [turn, turn], {"png": [_png()]})[0] == []
    assert uat.grade_case(case, [turn, turn], {})[0]
    no_job = uat.UATTurn("p", "Image ready. http://localhost/files/xyz/image.png", {}, (), ())
    assert any(
        "job identifier" in e for e in uat.grade_case(case, [no_job, no_job], {"png": [_png()]})[0]
    )


def test_cad_measure_convert_grader() -> None:
    case = _case(
        "cad_measure_convert",
        ("a", "b", "c"),
        {"extents": [60.0, 40.0, 30.0]},
        artifact_kind="stl+png",
    )
    payloads = {
        "stl": [_box_stl((60.0, 40.0, 30.0))],
        "png": [_png()],
        "obj": [b"v 0 0 0\nv 60 0 0\nv 0 40 0\nf 1 2 3\n"],
    }
    good = "Measured bounding box 60 x 40 x 30 mm; converted to OBJ."
    assert uat.grade_case(case, [_turn(good)] * 3, payloads)[0] == []
    wrong = {"stl": [_box_stl((20.0, 20.0, 20.0))], "png": [_png()], "obj": payloads["obj"]}
    assert any("do not match" in e for e in uat.grade_case(case, [_turn(good)] * 3, wrong)[0])
    assert uat.grade_case(case, [_turn(good)] * 3, {"stl": payloads["stl"], "png": [_png()]})[0]


def test_stl_extents_helper() -> None:
    assert sorted(uat._stl_extents(_box_stl((60.0, 40.0, 30.0)))) == [30.0, 40.0, 60.0]
    assert uat._stl_extents(b"not an stl") == []
    # The cube refactor still validates a 20mm cube.
    assert uat.validate_stl_geometry(_box_stl((20.0, 20.0, 20.0))) is None


# --------------------------------------------------------------- memory admin lifecycle


def test_memory_admin_grader_verifies_cleanup() -> None:
    case = _case("memory_admin", ("a", "b", "c"), {"marker": "qat-memadmin-7c1"})
    good = [
        _turn("Stored QAT-MEMADMIN-7C1 with id mem-1."),
        _turn("list_memories shows QAT-MEMADMIN-7C1; forget mem-1 deleted it."),
        _turn("list_memories now returns no memories for that tag."),
    ]
    errors, evidence = uat.grade_case(case, good, {})
    assert errors == [] and evidence["cleanup_verified"] is True
    bad = [
        _turn("Stored QAT-MEMADMIN-7C1 with id mem-1."),
        _turn("list_memories shows QAT-MEMADMIN-7C1; forget mem-1."),
        _turn("list_memories still shows QAT-MEMADMIN-7C1 present."),
    ]
    assert any("still shows" in e for e in uat.grade_case(case, bad, {})[0])


# --------------------------------------------------------------- compliance gap conversation


def test_compliance_policy_gap_grader() -> None:
    case = _case("compliance_policy_gap", ("a", "b"))
    good = (
        'The ingested OT-POL-007 patch management policy says "evaluate patches every 35 '
        'calendar days". NERC CIP-007-6 R2 Part 2.1, Part 2.3 and Part 2.4 require more: '
        '"install security patches within 35 calendar days of evaluation". Part 2.3 is the '
        "weakest: the procedure has a gap and does not specify installation timelines. I cannot "
        "certify compliance; this absence is scoped to the ingested corpus."
    )
    assert uat.grade_case(case, [_turn(good), _turn(good)], {})[0] == []
    certified = good.replace("I cannot certify compliance", "You are fully compliant")
    assert uat.grade_case(case, [_turn(certified)] * 2, {})[0]
    assert uat.grade_case(case, [_turn("The policy is fine. CIP-007-6 R2 satisfied.")] * 2, {})[0]


# --------------------------------------------------------------- data sql exact answer


def test_data_sql_grader_exact_totals() -> None:
    case = _case("data_sql", ("a", "b", "c"), {"total": "133", "north": "76"})
    good = "SUM(orders)=133; north total 76; orders table present in session."
    assert uat.grade_case(case, [_turn(good)] * 3, {})[0] == []
    assert any(
        "total" in e for e in uat.grade_case(case, [_turn("SUM=999 north=76 orders")] * 3, {})[0]
    )


# --------------------------------------------------------------- roster parity


def test_roster_missing_flags_absent_presets_and_personas() -> None:
    discovery = discover()

    class FakeUI:
        def __init__(self, roster: set[str]) -> None:
            self._roster = roster

        def workspace_roster(self) -> set[str]:
            return self._roster

    full = set(discovery.presets)
    full |= {str(p.name) for p in discovery.presets.values()}
    for spec in uat._seeded_personas(discovery, uat.PERSONA_DIR):
        full.add(str(spec.get("slug")))
        full.add(str(spec.get("name")))
    state = type("S", (), {"discovery": discovery})()
    assert uat._roster_missing(state, FakeUI(full)) == []
    missing = uat._roster_missing(state, FakeUI(set()))
    assert "auto-coding" in missing
    assert "webresearcher" in missing


def test_seeded_personas_excludes_role_and_unexposed_variant() -> None:
    discovery = discover()
    seeded = {str(spec.get("slug")) for spec in uat._seeded_personas(discovery, uat.PERSONA_DIR)}
    assert "webresearcher" in seeded
    assert "personalassistant" in seeded
    # role-delivered personas are slash commands, not selector models.
    assert "networkengineer" not in seeded
    assert "techwriter" not in seeded
    # variant=data is not an exposed preset, so its personas are conservatively excluded.
    assert "databasearchitect" not in seeded


# --------------------------------------------------------------- browser-harness fixes


class _FakeUI:
    def __init__(self, roster: set[str]) -> None:
        self._roster = roster

    def workspace_roster(self) -> set[str]:
        return self._roster


def _span_turn(text: str, tools: tuple[str, ...]) -> uat.UATTurn:
    spans = [{"name": "tool.completed", "tool": tool, "outcome": "ok"} for tool in tools]
    return uat.UATTurn("prompt", text, {"spans": spans}, tools, ())


def _journey(scenario_id: str) -> uat.UATCase:
    return next(c for c in uat.discover_cases(discover()) if c.scenario_id == scenario_id)


def test_load_presets_reads_top_level_display_name() -> None:
    presets = load_presets(
        [
            {"id": "auto", "name": "🤖 Portal Auto Router", "meta": {}, "params": {}},
            {"id": "meta-only", "meta": {"name": "Meta Name"}, "params": {}},
            {"id": "bare", "meta": {}, "params": {}},
        ]
    )
    assert presets["auto"].name == "🤖 Portal Auto Router"
    assert presets["meta-only"].name == "Meta Name"
    assert presets["bare"].name == "bare"


def test_roster_missing_accepts_display_name_only_roster() -> None:
    discovery = discover()
    # The live virtualized selector renders the configured display names, not raw slugs.
    # Read them from the preset bundle directly so the check is independent of load_presets.
    raw = json.loads(PRESETS_JSON.read_text(encoding="utf-8"))
    roster = {str(entry.get("name") or entry["id"]) for entry in raw}
    for spec in uat._seeded_personas(discovery, uat.PERSONA_DIR):
        roster.add(str(spec.get("name") or spec.get("slug")))
    state = type("S", (), {"discovery": discovery})()
    assert uat._roster_missing(state, _FakeUI(roster)) == []
    assert "auto-coding" in uat._roster_missing(state, _FakeUI(set()))


def test_obscura_journey_targets_public_example_domain() -> None:
    case = _journey("s5-browser-web-research-obscura")
    joined = " ".join(case.prompts).casefold()
    assert "https://example.com" in joined
    assert "host.docker.internal" not in joined
    assert "browser_navigate" in joined and "browser_snapshot" in joined
    assert "example domain" in {str(m).casefold() for m in case.expected["markers"]}


def test_web_research_scopes_exact_tools_per_turn() -> None:
    case = _journey("s5-browser-web-research")
    per_turn = case.expected["tools_per_turn"]
    assert per_turn == [["web_search", "news_search"], ["web_fetch", "kb_search_all"]]
    assert {tool for group in per_turn for tool in group} == set(case.expected_tools)
    for prompt, group in zip(case.prompts, per_turn, strict=True):
        for tool in group:
            assert tool in prompt


def test_required_tool_error_enforces_tools_per_turn() -> None:
    case = uat.UATCase(
        "wr",
        "wr",
        "auto-research",
        ("a", "b"),
        "web_research",
        {"tools_per_turn": [["web_search", "news_search"], ["web_fetch", "kb_search_all"]]},
        expected_tools=("kb_search_all", "news_search", "web_fetch", "web_search"),
    )
    good = [
        _span_turn("t1", ("web_search", "news_search")),
        _span_turn("t2", ("web_fetch", "kb_search_all")),
    ]
    assert uat._required_tool_error(case, good) is None
    dropped = [
        _span_turn("t1", ("web_search",)),
        _span_turn("t2", ("web_fetch", "kb_search_all")),
    ]
    error = uat._required_tool_error(case, dropped)
    assert error and "turn 1:news_search" in error
    # A tool completed in the wrong turn does not satisfy its scoped turn.
    swapped = [
        _span_turn("t1", ("web_search", "web_fetch")),
        _span_turn("t2", ("news_search", "kb_search_all")),
    ]
    swapped_error = uat._required_tool_error(case, swapped)
    assert swapped_error
    assert "turn 1:news_search" in swapped_error and "turn 2:web_fetch" in swapped_error


def test_compliance_policy_accepts_requirement_alias() -> None:
    case = _journey("s5-compliance-policy-conversation")
    assert case.timeout_s == 900.0
    assert set(case.expected["required_any_tools"]) == {
        "nerc_cip_requirement",
        "compliance_requirement",
    }
    assert "nerc_cip_requirement" not in case.expected_tools
    for alias in ("nerc_cip_requirement", "compliance_requirement"):
        turns = [
            _span_turn("t1", ("compliance_sources", "compliance_read")),
            _span_turn("t2", (alias, "compliance_search", "compliance_links")),
        ]
        assert uat._required_tool_error(case, turns) is None
    neither = [
        _span_turn("t1", ("compliance_sources", "compliance_read")),
        _span_turn("t2", ("compliance_search", "compliance_links")),
    ]
    error = uat._required_tool_error(case, neither)
    assert error and "one of" in error


# --------------------------------------------------------------- complexity budget


def test_expansion_adds_no_god_functions() -> None:
    path = Path(uat.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))

    def branches(node: ast.AST) -> int:
        return sum(
            1
            for n in ast.walk(node)
            if isinstance(
                n, ast.If | ast.For | ast.While | ast.Try | ast.BoolOp | ast.ExceptHandler
            )
        )

    over = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and (node.end_lineno - node.lineno + 1 > 80 or branches(node) > 15)
    }
    # Exactly the four pre-existing god functions; the expansion introduced none.
    assert over == {"_routing_cases", "_media_cases", "_advanced_cases", "_run_memory_case"}


def test_expansion_constants_stay_under_data_budget() -> None:
    path = Path(uat.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign | ast.AnnAssign):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            name = getattr(target, "id", "")
            if name in {"_PROXMOX_WRITE_TOOLS", "_ROLE_FIT_SPECS"}:
                assert node.end_lineno - node.lineno + 1 <= 30, name
