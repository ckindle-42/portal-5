"""DATA_TRUTH D1 — the instruments' decision logic, hermetically.

The live wiring (real store, real Lance dir, real engines) is exercised by the
registered HL check and the D-step baselines; these tests pin the logic the
gates read: evidence-set extraction, rank mapping, in-run output parsing,
part/heading population parsing, the exclusion-class matcher, the
ineligible-endpoint reasoner, the revision-currency census, and the
served-window resolver's config handling (no live engine).
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

import pytest

from portal.modules.compliance.core.served_window import (
    expand_env,
    served_window_for_hint,
    tag_window,
)
from scripts.compliance.truth import data_integrity as di
from scripts.compliance.truth import evidence_delivery as ed
from scripts.compliance.truth import findability as fb

# ── evidence_delivery ────────────────────────────────────────────────────────


def _entry() -> dict:
    return {
        "question_id": "conversational:x",
        "question": "What about X?",
        "governing": [
            {"section_id": "csection-a", "ref": "STD R1 Part 1.1", "text": "The entity shall do A."}
        ],
        "operator_evidence": [
            {
                "section_id": "isection-b",
                "document": "d",
                "locator": "1",
                "text": "The team does A.",
            },
            {
                "section_id": "isection-c",
                "document": "d",
                "locator": "2",
                "text": "Optional evidence.",
            },
        ],
        "facts": [
            {
                "id": "F1",
                "statement": "s",
                "required": True,
                "evidence": ["csection-a", "isection-b"],
            },
            {"id": "F2", "statement": "s", "required": False, "evidence": ["isection-c"]},
        ],
    }


def test_evidence_sets_takes_required_facts_only() -> None:
    operator_ids, governing_ids = ed.evidence_sets(_entry())
    assert operator_ids == ["isection-b"]
    assert governing_ids == ["csection-a"]


def test_search_ranks_prefers_row_section_id() -> None:
    rows = [{"section_id": "csection-a"}, {"chunk_id": "isection-b#2"}]
    assert ed._search_ranks(rows) == {"csection-a": 1, "isection-b": 2}


def test_tool_output_blob_parses_json_and_folds_escapes() -> None:
    transcript = {
        "tool_outputs": [
            {"output": json.dumps({"results": [{"text": "line one\nline two"}]})},
            {"output": "raw \n text"},
        ]
    }
    blob = ed.tool_output_blob(transcript)
    assert "line one line two" in blob
    assert "raw text" in blob


def test_transcript_question_id_maps_suites() -> None:
    assert ed.transcript_question_id(
        pathlib.Path("/r/product/transcripts/CIP-007-6__exceedance.json")
    ) == ("product:CIP-007-6:exceedance")
    assert ed.transcript_question_id(
        pathlib.Path("/r/rep1/conversational/transcripts/baselines.json")
    ) == ("conversational:baselines")


# ── findability ──────────────────────────────────────────────────────────────


def test_part_query_from_titled_table_row() -> None:
    text = "5.3 | High Impact BES Cyber Systems | Identify individuals who have authorized access."
    fields = [f.strip() for f in text.split(" | ")]
    assert len(fields) == 3
    assert fields[2] == "Identify individuals who have authorized access."


def test_part_query_from_part_token_text() -> None:
    text = "1.2.6. Require vendor electronic remote access approvals."
    match = fb.PART_TOKEN_RE.match(text)
    assert match is not None
    assert text[match.end() :].startswith("Require vendor")


def test_part_token_rejects_measures_and_roman_numerals() -> None:
    assert fb.PART_TOKEN_RE.match("M1. Acceptable evidence") is None
    assert fb.PART_TOKEN_RE.match("i. Control Centers") is None


def test_part_title_regex() -> None:
    assert fb.PART_TITLE_RE.match("5.3")
    assert fb.PART_TITLE_RE.match("1.2.6.")
    assert not fb.PART_TITLE_RE.match("B. Requirements and Measures")
    assert not fb.PART_TITLE_RE.match("CIP-004-7 Table R1 -")


# ── data_integrity ───────────────────────────────────────────────────────────


@pytest.fixture
def memory_store() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        create table source_documents (logical_id text primary key, jurisdiction text);
        create table document_revisions (
            revision_id text primary key, logical_id text, effective_date text,
            inactive_date text, retrieved_at text);
        create table source_sections (
            section_id text primary key, revision_id text, path text, title text,
            char_start int, char_end int, unit_kind text, role text);
        create table document_texts (revision_id text primary key, full_text text);
        create table relationship_assertions (
            assertion_id text primary key, relation_type text, src_ref text,
            dst_ref text, derivation text, review_state text);
        """
    )
    conn.execute("insert into source_documents values ('NERC/X-1', 'US')")
    conn.execute("insert into document_revisions values ('r1', 'NERC/X-1', '2020-01-01', '', '')")
    conn.execute(
        "insert into source_sections values ('csection-a', 'r1', 'B. R / 1.1', '1.1', 0, 40, 'table_row', 'B_REQUIREMENTS_AND_MEASURES')"
    )
    conn.execute(
        "insert into source_sections values ('csection-b', 'r1', 'toc.p3', 'Table of Contents', 40, 60, 'prose', '')"
    )
    conn.execute("insert into document_texts values ('r1', 'X' * 40 + 'TOC' + 'Y' * 17)")
    conn.execute(
        "insert into relationship_assertions values ('e1', 'IMPLEMENTS', 'STD R1 Part 1.1', 'csection-b', 'projection_rerank', 'proposed')"
    )
    conn.commit()
    return conn


def test_ineligible_reason_flags_toc(memory_store: sqlite3.Connection) -> None:
    full = {"r1": "X" * 40 + "TOC" + "Y" * 17}
    assert di._ineligible_reason(memory_store, full, "csection-b") == "toc"
    assert di._ineligible_reason(memory_store, full, "csection-a") == ""
    # requirement refs and doc::S refs are not section ids: never flagged
    assert di._ineligible_reason(memory_store, full, "STD R1 Part 1.1") == ""
    assert di._ineligible_reason(memory_store, full, "doc.pdf::S4.2") == ""


def test_edge_census_fails_on_toc_endpoint(memory_store: sqlite3.Connection) -> None:
    full = {"r1": "X" * 40 + "TOC" + "Y" * 17}
    result = di.check_edges(memory_store, full)
    assert result.status == "fail"
    assert result.findings[0]["ineligible_count"] == 1


def test_revision_currency_flags_future_and_inactive() -> None:
    rows = {
        "t": [
            {
                "chunk_id": "a#0",
                "is_superseded": 0,
                "effective_from": "2028-07-01",
                "effective_to": "",
                "logical_id": "NERC/X-5",
            },
            {
                "chunk_id": "b#0",
                "is_superseded": 0,
                "effective_from": "2020-01-01",
                "effective_to": "2026-03-31",
                "logical_id": "NERC/X-8",
            },
            {
                "chunk_id": "c#0",
                "is_superseded": 1,
                "effective_from": "2028-07-01",
                "effective_to": "",
                "logical_id": "NERC/X-9",
            },
        ]
    }
    result = di.check_revision_currency(rows, "2026-10-04")
    assert result.status == "fail"
    assert result.findings[0]["future_count"] == 1
    assert result.findings[0]["inactive_count"] == 1


def test_class_matching_jurisdiction_regex_and_kind() -> None:
    entry_class = {
        "applies": {
            "jurisdiction": "US",
            "logical_id_regex": " RSAW$",
            "unit_kind": ["prose", "table_row"],
        }
    }
    assert di._class_matches(entry_class, "US", "NERC/CIP-007-6 RSAW", "prose")
    assert not di._class_matches(entry_class, "internal", "NERC/CIP-007-6 RSAW", "prose")
    assert not di._class_matches(entry_class, "US", "NERC/CIP-007-6", "prose")
    assert not di._class_matches(entry_class, "US", "NERC/CIP-007-6 RSAW", "table")


def test_exclusion_table_loader_tolerates_missing_file(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(di, "EXCLUSION_TABLE_PATH", tmp_path / "absent.json")
    assert di._load_exclusion_table() == []


class _UnprojectablePlan:
    """A plan whose only receipt is one unprojectable section."""

    def __init__(self, section_id: str) -> None:
        self.excluded_sections: dict = {}
        self.excluded_by_class: dict = {}
        self.superseded_sections: list = []
        self.unprojectable: list = [
            {"section_id": section_id, "reason": "span [0, 1) does not resolve"}
        ]
        self.eligible_sections: list = []
        self.units: list = []
        self.kb_id = "nerc_corpus"
        self.jurisdiction = "US"


def test_coverage_explains_unprojectable_from_plan_receipt(
    memory_store: sqlite3.Connection,
) -> None:
    rows = {"t": [{"chunk_id": "csection-c#0"}]}
    result = di.check_coverage(
        memory_store,
        rows,
        build=lambda repo, jurisdiction: _UnprojectablePlan("csection-b"),
    )
    # csection-a is unindexed with no verdict and no class: real drift
    assert result.status == "fail"
    assert result.findings[0]["unexplained_count"] == 1
    # build runs per jurisdiction, so the fake plan's one row counts twice
    assert result.findings[0]["plan_verdicts"]["unprojectable"] == 2


# ── DATA_TRUTH D2: requirement-first unit composition ────────────────────────


def test_normative_field_parses_pipe_rows_and_prose() -> None:
    from portal.modules.compliance.core.section_index import normative_field

    row = "5.3 | High Impact BES Cyber Systems | Identify individuals who have authorized access."
    assert normative_field(row) == "Identify individuals who have authorized access."
    assert normative_field("R1. Each Responsible Entity shall implement a process.") == (
        "Each Responsible Entity shall implement a process."
    )
    assert normative_field("Free-standing text stays whole.") == "Free-standing text stays whole."


def _fixture_standard_store(tmp_path: pathlib.Path):
    """A one-standard store whose R1 Part 1.1 is an applicability-first row."""
    from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
    from portal.modules.compliance.core.models import SourceDocument
    from portal.modules.compliance.core.repository import Repository

    repo = Repository(tmp_path / "dt2.db")
    repo.upsert_source_document(
        SourceDocument(
            logical_id="NERC/CIP-TEST-1",
            title="NERC/CIP-TEST-1",
            issuer="x",
            source_kind="regulatory_standard",
            jurisdiction="US",
        )
    )
    revision = repo.add_document_revision("NERC/CIP-TEST-1", "/docs/cip-test-1.pdf", b"cip-test-1")
    # the requirement sentence stays above SHORT_REQUIREMENT_CHARS so the full
    # composition (identity + sentence + Applies to + Measures) is exercised
    row_text = (
        "1.1 | Critical Impact Plant Systems and attached Controllers | "
        "Identify each high impact BES Cyber System according to the asset groups "
        "recorded in the facility's asset inventory, including each EACMS and PACS "
        "associated with those systems. | "
        "An example of evidence may include a listing of identified systems."
    )
    measure_text = "M1. Acceptable evidence includes a listing of identified systems."
    full = row_text + "\n" + measure_text + "\n"
    row_len, measure_len = len(row_text) + 1, len(measure_text) + 1
    units = [
        CapturedUnit(
            ordinal=0,
            unit_kind="table_row",
            heading_path="B. Requirements and Measures",
            title="1.1",
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=row_len,
            text=row_text + "\n",
        ),
        CapturedUnit(
            ordinal=1,
            unit_kind="table_row",
            heading_path="B. Requirements and Measures",
            title="1.1 Measures",
            page_start=1,
            page_end=1,
            char_start=row_len,
            char_end=row_len + measure_len,
            text=measure_text + "\n",
        ),
    ]
    document = CapturedDocument(
        path=pathlib.Path("cip-test-1.pdf"),
        page_count=1,
        full_text=full,
        units=units,
        extractor="docling",
        reader_strings=(row_text,),
    )
    store_capture(repo, revision.revision_id, document)
    part_id = repo._conn.execute(
        "select section_id from source_sections where title='1.1'"
    ).fetchone()["section_id"]
    measure_id = repo._conn.execute(
        "select section_id from source_sections where title='1.1 Measures'"
    ).fetchone()["section_id"]
    for anchor_id, relation in (
        (part_id, "governing"),
        (part_id, "applicable_systems"),
        (measure_id, "measure"),
    ):
        repo._conn.execute(
            "insert into requirement_sections (requirement_id, revision_id, section_id, relation,"
            " char_start, char_end, occurrences, anchor_method, anchored_at, extractor_version)"
            " values (?,?,?,?,0,1,1,'exact','2026-10-04','fixture')",
            ("CIP-TEST-1 R1 Part 1.1", revision.revision_id, anchor_id, relation),
        )
    repo._conn.commit()
    return repo


def test_requirement_first_texts_composes_identity(tmp_path: pathlib.Path) -> None:
    from portal.modules.compliance.core.section_index import requirement_first_texts

    repo = _fixture_standard_store(tmp_path)
    try:
        composed = requirement_first_texts(repo)
        assert len(composed) == 1
        (text,) = composed.values()
        assert text.startswith("CIP-TEST-1 R1 Part 1.1 — ")
        assert "Identify each high impact BES Cyber System according to the asset" in text
        assert "Applies to: Critical Impact Plant Systems and attached Controllers." in text
        assert "Measures: M1. Acceptable evidence" in text
    finally:
        repo.close()


def _part_ids(repo) -> set[str]:
    rows = repo._conn.execute("select section_id from source_sections where title='1.1'").fetchall()
    return {str(row["section_id"]) for row in rows}


def test_build_plan_emits_identity_bearing_part_units(tmp_path: pathlib.Path) -> None:
    from portal.modules.compliance.core.section_index import build_plan

    repo = _fixture_standard_store(tmp_path)
    try:
        plan = build_plan(repo, jurisdiction="US")
        parts = [u for u in plan.units if u.section_id in _part_ids(repo)]
        assert parts, "the Part row must be projected"
        for unit in parts:
            assert unit.text.startswith("CIP-TEST-1 R1 Part 1.1"), unit.text[:60]
            assert unit.unit_kind == "table_row"
        assert plan.requirement_first_units >= 1
    finally:
        repo.close()


# ── served_window ────────────────────────────────────────────────────────────


def test_expand_env_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_VAR", raising=False)
    assert expand_env("${TEST_VAR:-http://fallback:1}") == "http://fallback:1"
    monkeypatch.setenv("TEST_VAR", "http://override:2")
    assert expand_env("${TEST_VAR:-http://fallback:1}") == "http://override:2"


def test_tag_window_reads_ctx_suffix() -> None:
    assert tag_window("gemma4:26b-a4b-it-q4_K_M-ctx32k") == 32768
    assert tag_window("granite4.1:30b-ctx98k") == 98 * 1024
    assert tag_window("qwen:latest") is None


def _write_config(tmp_path: pathlib.Path) -> pathlib.Path:
    config = tmp_path / "backends.yaml"
    config.write_text(
        """
backends:
  - id: ollama-general
    type: ollama
    url: ${OLLAMA_URL:-http://host.docker.internal:11434}
    group: general
    models:
      - gemma4:26b-a4b-it-q4_K_M-ctx32k
  - id: omlx-general
    type: omlx
    url: ${OMLX_URL:-http://host.docker.internal:8085}
    group: general
    models:
      - mlx-served-model
    aliases:
      gemma4:26b-a4b-it-q4_K_M-ctx32k: mlx-served-model
workspace_routing:
  reading-ws:
    - general
""",
        encoding="utf-8",
    )
    return config


def test_resolver_reports_alias_and_out_of_group_route(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("OMLX_URL", raising=False)
    probed: list[str] = []

    def fake_http(result, method, url, *, payload=None, timeout=3.0):
        probed.append(url)
        if "/v1/models" in url:
            return {"data": [{"id": "mlx-served-model", "max_model_len": 262144}]}
        if url.endswith("/api/show"):
            return {"model_info": {"gemma4:26b-a4b-it-q4_K_M-ctx32k.context_length": 32768}}
        return {"models": [{"name": "gemma4:26b-a4b-it-q4_K_M-ctx32k", "context_length": 32768}]}

    monkeypatch.setattr("portal.modules.compliance.core.served_window._http_json", fake_http)
    scoped = served_window_for_hint("gemma4:26b-a4b-it-q4_K_M-ctx32k", config, groups=["general"])
    assert scoped.applied_window == 32768  # the ollama route answers first
    assert scoped.aliased is False
    assert ("ollama-general", 32768) in scoped.route_windows
    assert ("omlx-general", 262144) in scoped.route_windows
    assert any("routes disagree" in note for note in scoped.notes)
    assert any("host.docker.internal" in url for url in probed)
    unscoped = served_window_for_hint("gemma4:26b-a4b-it-q4_K_M-ctx32k", config)
    # with no group scoping both routes answer; the alias route is recorded
    assert ("omlx-general", 262144) in unscoped.route_windows


def test_resolver_without_probe_stays_static(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path)

    def fail_http(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("probe attempted with probe=False")

    monkeypatch.setattr("portal.modules.compliance.core.served_window._http_json", fail_http)
    result = served_window_for_hint(
        "gemma4:26b-a4b-it-q4_K_M-ctx32k", config, probe=False, groups=["general"]
    )
    assert result.applied_window is None
    assert result.resolved_model == "gemma4:26b-a4b-it-q4_K_M-ctx32k"


def test_resolver_never_raises_on_unreachable(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path)

    def boom(result, method, url, **kwargs):
        result.notes.append(f"probe {url} failed: connection refused")
        return None

    monkeypatch.setattr("portal.modules.compliance.core.served_window._http_json", boom)
    result = served_window_for_hint("gemma4:26b-a4b-it-q4_K_M-ctx32k", config, groups=["general"])
    assert result.applied_window is None
    assert "no in-group candidate backend answered a probe" in result.notes


# ── DATA_TRUTH D3: operator ingest units (strip furniture, merge headings) ───


def _procedure_pages() -> list[str]:
    """A synthetic controlled document shaped like the real corpus: repeated
    furniture, a ToC page, heading-only fragments before their bodies."""
    return [
        (
            " \nPRIVATE – FOR INTERNAL USE ONLY \n \n"
            "ACME Security Patch Management Procedure \n \n"
            "Effective Date:  July 31, 2026 \n"
            "Document Type: Procedure \nNERC Standard: CIP-007 \n"
        ),
        (
            " \nPRIVATE – FOR INTERNAL USE ONLY \nPage 2 of 9 \n \n"
            "1.0 Introduction \n1.1 \nPurpose \n"
            "The purpose is patch tracking across the fleet. \n"
            "1.2 \nApplicability \n"
            "This applies to all ACME registrations. \n"
        ),
        (
            " \nPRIVATE – FOR INTERNAL USE ONLY \nPage 3 of 9 \n \n"
            "2.0 Patch Evaluation \n2.1 \n"
            "Patches are evaluated every thirty days by the OT team. \n"
        ),
    ]


def test_strip_furniture_removes_repeated_lines() -> None:
    from portal.modules.compliance.core.internal_corpus import strip_furniture

    pages = _procedure_pages()
    stripped = strip_furniture(pages)
    joined = "\n".join(stripped)
    assert "PRIVATE – FOR INTERNAL USE ONLY" not in joined
    assert "Page 2 of 9" not in joined
    assert "Patch Evaluation" in joined  # content survives


def test_sectionize_merges_heading_only_into_body() -> None:
    from portal.modules.compliance.core import internal_corpus as ic

    pages = ic.strip_furniture(_procedure_pages())
    full = "\n".join(pages)
    sections = ic.sectionize(pages)
    texts = {s.path: s.text.strip() for s in sections}
    # the bare-number line '2.1' introduces the body directly: no heading-only
    # section may survive with the number as its whole content
    assert not any(t.strip() == "2.1" for t in texts.values()), sorted(texts)
    body = texts.get("2.0", "")
    assert "2.1" in body
    assert "evaluated every thirty days" in body
    # spans stay contiguous with the stripped full text
    for section in sections:
        assert full[section.char_start : section.char_end] == section.text


def test_fresh_upload_yields_furniture_free_findable_units() -> None:
    """The D3 fresh-upload proof: a synthetic document through the REAL ingest
    path (extract_pages -> parse control -> sectionize) yields furniture-free
    units whose headings are the section titles."""
    from portal.modules.compliance.core import internal_corpus as ic

    pdf = _make_pdf()
    got_pages, got_full = ic.extract_pages(pdf)
    assert "PRIVATE – FOR INTERNAL USE ONLY" not in got_full
    assert "Page 1 of 1" not in got_full
    sections = ic.sectionize(got_pages)
    operative = [s for s in sections if s.path.startswith(("1.", "2."))]
    assert operative, [s.path for s in sections]
    for section in operative:
        assert "PRIVATE" not in section.text
        assert section.heading.strip() in section.text


def _make_pdf() -> pathlib.Path:
    """A one-page synthetic PDF carrying the controlled-document shape."""
    import fitz  # noqa: PLC0415 - pymupdf's stable import name

    document = fitz.open()
    page = document.new_page()
    text = (
        "PRIVATE - FOR INTERNAL USE ONLY\n"
        "ACME Security Patch Management Procedure\n"
        "Effective Date:  July 31, 2026\n"
        "Document Type: Procedure\n"
        "NERC Standard: CIP-007\n"
        "1.0 Introduction\n"
        "The purpose is patch tracking across the fleet.\n"
        "Page 1 of 1\n"
    )
    page.insert_text((72, 72), text, fontsize=11)
    path = pathlib.Path(_tmpdir_name())
    document.save(str(path))
    document.close()
    return path


def _tmpdir_name() -> str:
    import tempfile

    handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    handle.close()
    return handle.name


# ── DATA_TRUTH D6: default scope is effective-on-the-asked-date ──────────────


def test_search_predicate_default_excludes_future_and_inactive() -> None:
    from portal.modules.compliance.core import search_service as ss

    clause = ss.search_predicate(standard="", layer="", valid_at="", known_at="")
    assert "is_superseded" in clause
    assert "effective_from" in clause and "effective_to" in clause
    # the module's one clock (temporal.now_iso, UTC) — never the local date,
    # which disagrees every evening west of UTC
    from portal.modules.compliance.core.section_index import _today

    assert _today() in clause


def test_search_predicate_explicit_clock_skips_the_default() -> None:
    from portal.modules.compliance.core import search_service as ss

    clause = ss.search_predicate(standard="", layer="", valid_at="2028-07-01", known_at="")
    assert "2028-07-01" in clause
    assert "is_superseded" not in clause
