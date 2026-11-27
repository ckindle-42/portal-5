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
import sqlite3
import sys

import pytest

from portal.modules.compliance.core.served_window import (
    tag_window,
)
from scripts.compliance.truth import data_integrity as di
from scripts.compliance.truth import evidence_delivery as ed
from scripts.compliance.truth import findability as fb


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


class _AnchorRepo:
    """A stub store: requirement_sections rows plus their document texts."""

    def __init__(self, rows: list[tuple[str, str, int, int]], texts: dict[str, str]) -> None:
        # rows: (requirement_id, revision_id, char_start, char_end)
        self._rows = rows
        self._texts = texts

    @property
    def _conn(self):  # noqa: ANN202 - test stub
        stub = self

        class _Cursor:
            @staticmethod
            def execute(sql: str, params: list):  # noqa: ANN001
                wanted = set(params)

                class _Result:
                    @staticmethod
                    def fetchall():
                        return [row for row in stub._rows if row[0] in wanted]

                return _Result()

        return _Cursor()

    def get_document_text(self, revision_id: str) -> str | None:
        return self._texts.get(revision_id)


_ANCHOR_TEXT = "Identify each asset with high impact ratings every reporting period."


def _anchor_repo() -> _AnchorRepo:
    start = 40
    end = start + len(_ANCHOR_TEXT)
    full = "x" * start + _ANCHOR_TEXT + "y" * 10
    return _AnchorRepo([("STD R1 Part 1.1", "r1", start, end)], {"r1": full})


def test_required_items_takes_required_facts_only() -> None:
    operator_items, governing_items = ed.required_items(_entry())
    assert [item["section_id"] for item in operator_items] == ["isection-b"]
    assert [item["section_id"] for item in governing_items] == ["csection-a"]


def test_longest_run_words_finds_longest_contiguous_window() -> None:
    quote = ed.norm("alpha beta gamma delta")
    assert ed.longest_run_words(quote, ed.norm("nothing here at all")) == 0
    assert ed.longest_run_words(quote, ed.norm("we value gamma delta highly")) == 2
    assert ed.longest_run_words(quote, ed.norm("alpha beta then gamma delta")) == 2
    assert ed.longest_run_words(quote, quote + " plus more") == 4


def test_longest_run_words_handles_empty_inputs() -> None:
    assert ed.longest_run_words("", "blob") == 0
    assert ed.longest_run_words(ed.norm("some words"), "") == 0


def test_normative_anchor_spans_reads_governing_slice() -> None:
    spans = ed.normative_anchor_spans(_anchor_repo(), ["STD R1 Part 1.1", "STD R9 Part 9.9"])
    assert spans["STD R1 Part 1.1"] == [ed.norm(_ANCHOR_TEXT)]
    assert spans["STD R9 Part 9.9"] == []  # no governing row: reported, not invented


def test_normative_anchor_spans_empty_refs_needs_no_store() -> None:
    assert ed.normative_anchor_spans(_anchor_repo(), []) == {}


def test_score_evidence_strict_anchor_and_use() -> None:
    entry = _entry()
    # the governing key quote opens with the applicability column (strict probe
    # fails); the blob carries only the normative anchor words (anchor passes)
    entry["governing"][0]["text"] = "1.1 | High Impact Systems | " + _ANCHOR_TEXT
    operator_text = "The team applies patches every thirty days with verification."
    entry["operator_evidence"][0]["text"] = operator_text
    entry["operator_evidence"][0]["document"] = "Delta Patch Procedure"
    blob = ed.norm("preamble " + _ANCHOR_TEXT + " " + operator_text + " epilogue")
    answer = (
        "Per Delta Patch Procedure, STD R1 Part 1.1 says: " + _ANCHOR_TEXT + " The team applies "
        "patches every thirty days with verification, per the procedure."
    )
    spans = {"STD R1 Part 1.1": [ed.norm(_ANCHOR_TEXT)]}
    scored = ed.score_evidence(entry, blob, spans, answer_norm=ed.norm(answer))
    gov = scored["governing"][0]
    assert gov["strict"] is False  # applicability-first probe misses
    assert gov["anchor"] is True  # the normative span is present
    assert gov["delivered"] is True
    op = scored["operator"][0]
    assert op["strict"] is True
    assert op["run_words"] == op["quote_words"]
    # use: the answer quotes delivered text (>= 8 words) and names each document
    assert gov["use"]["use"] is True
    assert op["use"]["use"] is True


def test_score_evidence_use_requires_delivery_and_document() -> None:
    entry = _entry()
    operator_text = "The team applies patches every thirty days with verification."
    entry["operator_evidence"][0]["text"] = operator_text
    entry["governing"][0]["text"] = "1.1 | High Impact Systems | " + _ANCHOR_TEXT
    answer = ed.norm(
        "The team applies patches every thirty days with verification. Std R1 Part 1.1 "
        "applies: identify each asset with high impact ratings every reporting period."
    )
    scored = ed.score_evidence(entry, blob="", anchor_spans={}, answer_norm=answer)
    # nothing was delivered, so quoting it in the answer is NOT use
    assert scored["operator"][0]["use"]["quote_used"] is True
    assert scored["operator"][0]["use"]["use"] is False
    assert ed.summarize_scored(scored)["use_operator"]["delivered"] == 0
    # delivered (anchor) and both documents named: quoted and used
    spans = {"STD R1 Part 1.1": [ed.norm(_ANCHOR_TEXT)]}
    blob = ed.norm(_ANCHOR_TEXT)
    scored = ed.score_evidence(entry, blob, spans, answer_norm=answer)
    assert scored["governing"][0]["delivered"] is True
    assert scored["governing"][0]["use"]["quote_used"] is True
    assert scored["governing"][0]["use"]["document_named"] is True
    summary = ed.summarize_scored(scored)
    assert summary["governing_anchor"] == {"hits": 1, "total": 1}
    assert summary["governing_delivered"]["hits"] == 1
    assert summary["refs_without_anchor"] == []


def test_score_offline_reports_material_governing_anchor() -> None:
    entry = _entry()
    entry["governing"][0]["text"] = "1.1 | High Impact Systems | " + _ANCHOR_TEXT
    measured = {
        "search_unscoped": {},
        "search_scoped": {},
        "material": {"blob": ed.norm(_ANCHOR_TEXT), "chars": 10, "fixed_chars": 0, "errors": []},
        "anchor_spans": {},
    }
    rows = ed.score_offline(entry, measured)
    # strict probe misses the applicability-first quote; the anchor span hits
    assert rows["material.governing"] == {"hits": 0, "total": 1}
    assert rows["material.governing_anchor"] == {"hits": 0, "total": 1}
    assert rows["errors"] == ["no governing anchor row: STD R1 Part 1.1"]
    measured["anchor_spans"] = {"STD R1 Part 1.1": [ed.norm(_ANCHOR_TEXT)]}
    rows = ed.score_offline(entry, measured)
    assert rows["material.governing_anchor"] == {"hits": 1, "total": 1}
    assert "errors" not in rows


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
            dst_ref text, derivation text, review_state text,
            status text default 'proposed');
        """
    )
    conn.execute("insert into source_documents values ('NERC/X-1', 'US')")
    conn.execute("insert into document_revisions values ('r1', 'NERC/X-1', '2020-01-01', '', '')")
    conn.execute(
        "insert into source_sections values ('csection-a', 'r1', 'B. R / 1.1', '1.1', 0, 40, 'table_row', 'B_REQUIREMENTS_AND_MEASURES')"
    )
    conn.execute(
        "insert into source_sections values ('csection-b', 'r1', 'toc.p3', 'Table of Contents', 40, 60, 'prose', 'TABLE_OF_CONTENTS')"
    )
    conn.execute("insert into document_texts values ('r1', 'X' * 40 + 'TOC' + 'Y' * 17)")
    conn.execute(
        "insert into relationship_assertions values ('e1', 'IMPLEMENTS', 'STD R1 Part 1.1', 'csection-b', 'projection_rerank', 'proposed', 'proposed')"
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


def test_ineligible_reason_flags_dangling_endpoint(memory_store: sqlite3.Connection) -> None:
    """D-DT-19 review 2: a section-shaped endpoint whose row a re-capture
    re-cut is not eligible — the census used to pass it."""
    full = {"r1": "X" * 40 + "TOC" + "Y" * 17}
    assert di._ineligible_reason(memory_store, full, "csection-gone") == "dangling"
    assert di._ineligible_reason(memory_store, full, "isection-gone") == "dangling"


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


def test_normative_field_parses_pipe_rows_and_prose() -> None:
    from portal.modules.compliance.core.section_index import normative_field

    row = "5.3 | High Impact BES Cyber Systems | Identify individuals who have authorized access."
    assert normative_field(row) == "Identify individuals who have authorized access."
    assert normative_field("R1. Each Responsible Entity shall implement a process.") == (
        "Each Responsible Entity shall implement a process."
    )
    assert normative_field("Free-standing text stays whole.") == "Free-standing text stays whole."


def test_tag_window_reads_ctx_suffix() -> None:
    assert tag_window("gemma4:26b-a4b-it-q4_K_M-ctx32k") == 32768
    assert tag_window("granite4.1:30b-ctx98k") == 98 * 1024
    assert tag_window("qwen:latest") is None


def test_store_coverage_loads_conversation_table_and_flags_missing_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    table_names = (
        "compliance_nerc_corpus",
        "compliance_operator_corpus",
        "compliance_operator_notes",
        "compliance_conversation",
    )
    indexed_row = {
        "chunk_id": "conversation-section#0",
        "text": "Conversation source text",
        "headings": "",
        "logical_id": "conversation/source",
        "revision_id": "r1",
        "effective_from": "",
        "effective_to": "",
        "is_superseded": 0,
        "unit_kind": "prose",
    }
    table_data = {name: [] for name in table_names}
    table_data["compliance_conversation"] = [indexed_row]
    opened: list[str] = []

    class _ArrowRows:
        def __init__(self, rows: list[dict]) -> None:
            self.rows = rows

        def select(self, _columns: list[str]) -> _ArrowRows:
            return self

        def to_pylist(self) -> list[dict]:
            return self.rows

    class _Table:
        def __init__(self, rows: list[dict]) -> None:
            self.rows = rows

        def to_arrow(self) -> _ArrowRows:
            return _ArrowRows(self.rows)

    class _Database:
        def open_table(self, name: str) -> _Table:
            opened.append(name)
            return _Table(table_data[name])

    monkeypatch.setattr(di, "LANCE_RAG_DIR", di.REPO_ROOT)
    monkeypatch.setitem(
        sys.modules,
        "lancedb",
        SimpleNamespace(connect=lambda _path: _Database()),
    )
    rows = di._lance_rows()
    assert tuple(opened) == table_names
    assert rows["compliance_conversation"] == [indexed_row]

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("create table source_sections (section_id text)")
    conn.execute("insert into source_sections values ('conversation-section')")
    repo = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr("portal.modules.compliance.core.repository.Repository", lambda: repo)
    plan = SimpleNamespace(excluded_sections={}, superseded_sections=set(), unprojectable=[])
    assert di.check_coverage(conn, rows, build=lambda *_args, **_kwargs: plan).status == "pass"

    rows["compliance_conversation"] = []
    missing = di.check_coverage(conn, rows, build=lambda *_args, **_kwargs: plan)
    assert missing.status == "fail"
    assert missing.findings[0]["unexplained_examples"] == [{"section_id": "conversation-section"}]
    conn.close()


def _window_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "portal.yaml").write_text(
        "workspaces:\n  auto-compliance:\n    model_hint: qwen-ctx32k\n    context_limit: 32768\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "backends.yaml").write_text(
        "workspace_routing:\n  auto-compliance: [omlx-general]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(di, "REPO_ROOT", tmp_path)


def test_window_declared_served_allows_larger_served_window(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from portal.modules.compliance.core import served_window

    _window_config(tmp_path, monkeypatch)
    monkeypatch.setattr(
        served_window,
        "served_window_for_hint",
        lambda hint, **_kwargs: SimpleNamespace(
            applied_window=262144,
            resolved_model="hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
            aliased=True,
            route_windows=[("omlx-general", 262144)],
        ),
    )

    result = di.check_windows()
    assert result.status == "pass"


def test_window_declared_served_fails_when_served_window_is_too_small(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from portal.modules.compliance.core import served_window

    _window_config(tmp_path, monkeypatch)
    monkeypatch.setattr(
        served_window,
        "served_window_for_hint",
        lambda hint, **_kwargs: SimpleNamespace(
            applied_window=16384,
            resolved_model="short-window-model",
            aliased=False,
            route_windows=[("omlx-general", 16384)],
        ),
    )

    result = di.check_windows()
    assert result.status == "fail"
    assert "declared 32768" in result.detail
    assert "served 16384" in result.detail


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


def test_default_compliance_search_excludes_derived_conversation_corpus(monkeypatch) -> None:
    from portal.modules.compliance.core import search_service as ss

    seen: list[str] = []

    async def _fake_kb_search(kb_id: str, *_args, **_kwargs) -> dict:
        seen.append(kb_id)
        return {"results": []}

    monkeypatch.setattr(
        "portal.modules.compliance.tools.compliance_retrieval.search", _fake_kb_search
    )
    monkeypatch.setattr(ss, "_addressed_hits", lambda *_a, **_kw: [])
    monkeypatch.setattr(
        "portal.modules.compliance.core.section_index.resolve_sections", lambda *_a: {}
    )

    res_default = ss.search(object(), "Part 5.2")
    assert "conversation" not in res_default["corpora_searched"]
    assert "nerc_corpus" in res_default["corpora_searched"]

    seen.clear()
    res_derived = ss.search(object(), "Part 5.2", jurisdiction="derived")
    assert res_derived["corpora_searched"] == ["conversation"]
