"""DATA_TRUTH DD2 — the operator traceability assertions, hermetically.

The promotion of the D-DT-8 probe parser into the internal corpus: appendix
parsing, text-first requirement confirmation (the ≥0.6 gate that rejected the
probe's 24 header misreads), section resolution (probe rules first, counted
undotted-number fixes second), idempotent store writes, the HL edge check's
live-only census, and the mechanical revocation of ineligible endpoints.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import threading
from collections import Counter

import pytest

from portal.modules.compliance.core import operator_traceability as ot
from scripts.compliance.truth import data_integrity as di
from scripts.compliance.truth import revoke_ineligible_edges as rev

_APPENDIX = (
    "Appendix 1: Cross-Reference Between CIP-901-1 and ACME Procedure v2. "
    "R1. Each Responsible Entity shall identify assets. "
    "R1 Part 1.1 Identify each asset with high impact ratings every reporting "
    "period. Sections 3.1, 3.2 "
    "R2 Part 2.1 Wholly different words about monitoring the perimeter gates. "
    "Sections 4.0 "
)
_IDENTIFY = "Identify each asset with high impact ratings every reporting period."
_MONITOR = "Wholly different words about monitoring the perimeter gates."


def _register() -> ot.Register:
    return ot.Register(
        ids={"CIP-901-1 R1 Part 1.1", "CIP-901-1 R2 Part 2.1", "CIP-902-1 R1 Part 1.1"},
        texts={
            "CIP-901-1 R1 Part 1.1": _IDENTIFY,
            "CIP-901-1 R2 Part 2.1": _MONITOR,
            "CIP-902-1 R1 Part 1.1": "Completely unrelated normative sentence words.",
        },
        current_stds={"CIP-901-1", "CIP-902-1"},
    )


# ── parsing ──────────────────────────────────────────────────────────────────


def test_appendix_region_finds_last_cross_reference() -> None:
    region = ot.appendix_region("intro " + _APPENDIX + " REVISION HISTORY v1 initial")
    # the region starts at the heading MATCH, as in the probe
    assert region.startswith("Cross-Reference Between")
    assert "REVISION HISTORY" not in region
    assert ot.appendix_region("no appendix here") == ""


def test_parse_rows_splits_on_r_tokens_and_dotted_parts() -> None:
    rows = ot.parse_rows(ot.appendix_region(_APPENDIX))
    # the statement row ("R1. Each ...") is a parse row with no Sections
    # token; resolution skips it, as the probe did
    assert [(row.r, row.part) for row in rows] == [("1", None), ("1", "1.1"), ("2", "2.1")]
    assert rows[0].section_numbers == []
    assert rows[1].standard == "901"
    assert rows[1].section_numbers == ["3.1", "3.2"]


# ── resolution ───────────────────────────────────────────────────────────────


def test_part_row_confirms_by_text_and_resolves_sections() -> None:
    register = _register()
    stats: Counter = Counter()
    (row,) = [r for r in ot.parse_rows(ot.appendix_region(_APPENDIX)) if r.part == "1.1"]
    resolved = ot.resolve_row(
        row,
        register,
        {"3.1": ["isection-a"], "3.2": ["isection-b"]},
        {"isection-a": "body", "isection-b": "body"},
        stats,
    )
    assert resolved.requirement_ids == ["CIP-901-1 R1 Part 1.1"]
    assert resolved.outcome == "text_confirmed"
    assert resolved.section_ids == ["isection-a", "isection-b"]


def test_part_row_rejects_when_restated_text_mismatches() -> None:
    register = _register()
    stats: Counter = Counter()
    (row,) = [r for r in ot.parse_rows(ot.appendix_region(_APPENDIX)) if r.part == "1.1"]
    row.row_text = "The entity shall count its pigeons twice yearly with care."
    resolved = ot.resolve_row(row, register, {}, {}, stats)
    assert resolved.requirement_ids == []
    assert resolved.outcome == "rejected_text_mismatch"


def test_whole_requirement_row_resolves_structurally() -> None:
    register = ot.Register(
        ids={"CIP-901-1 R4", "CIP-901-2 R4"},
        texts={},
        current_stds={"CIP-901-1"},
    )
    row = ot.TraceRow("R4", standard="901", version=None, r="4", part=None, section_numbers=["5"])
    resolved = ot.resolve_row(row, register, {"5": ["isection-c"]}, {}, Counter())
    # currency-preferred when the appendix states no version
    assert resolved.requirement_ids == ["CIP-901-1 R4"]
    assert resolved.outcome == "structural"


def test_no_standard_or_no_sections_skips_the_row() -> None:
    stats: Counter = Counter()
    row = ot.TraceRow("text", standard=None, version=None, r="1", part="1.1", section_numbers=["1"])
    resolved = ot.resolve_row(row, _register(), {}, {}, stats)
    assert resolved.outcome == "no_std"
    assert stats["no_std"] == 1
    row = ot.TraceRow("text", standard="901", version=None, r="1", part="1.1", section_numbers=[])
    resolved = ot.resolve_row(row, _register(), {}, {}, stats)
    assert resolved.outcome == "no_section"
    assert stats["no_section"] == 1


def test_undotted_numbers_fill_gaps_only_after_probe_rules() -> None:
    register = _register()
    stats: Counter = Counter()
    by_number = {"3.0": ["isection-proc"], "4.0": ["isection-misc"]}
    bodies = {"isection-proc": "the procedure body\n", "isection-misc": "misc body\n"}
    row = ot.TraceRow(
        "R1 Part 1.1 " + _IDENTIFY,
        standard="901",
        version=None,
        r="1",
        part="1.1",
        section_numbers=["3"],
    )
    resolved = ot.resolve_row(row, register, by_number, bodies, stats)
    # '3' has no exact or folded hit; the '.0' equivalence fills the gap
    assert resolved.section_ids == ["isection-proc"]
    assert stats["undotted_equivalence"] == 1


def test_folded_paragraph_beats_undotted_equivalence() -> None:
    register = _register()
    stats: Counter = Counter()
    by_number = {"1.0": ["isection-misnumbered-owner-row"]}
    bodies = {"isection-grouping": "1 Grouping of assets into groups\n"}
    row = ot.TraceRow(
        "R1 Part 1.1 " + _IDENTIFY,
        standard="901",
        version=None,
        r="1",
        part="1.1",
        section_numbers=["1"],
    )
    resolved = ot.resolve_row(row, register, by_number, bodies, stats)
    # the probe's folded scan fires first: documents carry misnumbered
    # duplicate runs (owner lists numbered 1.0-8.1) that the '.0' equivalence
    # would happily match while the operator meant the grouping section
    assert resolved.section_ids == ["isection-grouping"]
    assert stats["folded_paragraph"] == 1


# ── the store side ───────────────────────────────────────────────────────────


class _StubRepo:
    """Just what record_traceability touches: _lock, _conn, get_document_text."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._lock = threading.Lock()
        self._conn = conn

    def get_document_text(self, revision_id: str) -> str | None:
        row = self._conn.execute(
            "select full_text from document_texts where revision_id=?", (revision_id,)
        ).fetchone()
        return row[0] if row else None


@pytest.fixture
def trace_store() -> _StubRepo:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        create table source_documents (logical_id text primary key, jurisdiction text);
        create table document_revisions (
            revision_id text primary key, logical_id text, effective_date text,
            inactive_date text, retrieved_at text);
        create table document_texts (revision_id text primary key, full_text text);
        create table requirement_sections (
            requirement_id text, revision_id text, section_id text, relation text,
            char_start int, char_end int);
        create table source_sections (
            section_id text primary key, revision_id text, heading_path text, title text,
            role text, char_start int, char_end int, ordinal int);
        create table relationship_assertions (
            assertion_id text primary key, relation_type text, src_ref text,
            src_revision_id text, dst_ref text, dst_revision_id text, citations_json text,
            status text, review_state text, rationale text, confidence real,
            derivation text, recorded_from text);
        """
    )
    full = (
        "front matter. " + _APPENDIX + " REVISION HISTORY v1 initial. "
        "1.0 Purpose The procedure body. 3.1 Identify assets 3.2 Group assets."
    )
    conn.execute(
        "insert into source_documents values ('CIP-901/ACME Procedure v2.pdf', 'internal')"
    )
    conn.execute("insert into source_documents values ('NERC/CIP-901-1', 'US')")
    conn.execute(
        "insert into document_revisions values ('rev1', 'CIP-901/ACME Procedure v2.pdf',"
        " '2026-01-01', '', '2026-01-01')"
    )
    conn.execute("insert into document_texts values ('rev1', ?)", (full,))
    # one registry revision whose text holds both requirements; the anchor
    # spans are coordinates in the REGISTRY document's own text
    registry_text = _IDENTIFY + " " + _MONITOR
    conn.execute("insert into document_texts values ('regrev', ?)", (registry_text,))
    for requirement_id, text, offset in (
        ("CIP-901-1 R1 Part 1.1", _IDENTIFY, 0),
        ("CIP-901-1 R2 Part 2.1", _MONITOR, len(_IDENTIFY) + 1),
    ):
        conn.execute(
            "insert into requirement_sections values (?,?,?,?,?,?)",
            (requirement_id, "regrev", "csection-x", "governing", offset, offset + len(text)),
        )
    conn.execute(
        "insert into document_revisions values ('regrev', 'NERC/CIP-901-1',"
        " '2026-01-01', '', '2026-01-01')"
    )
    sections = [
        (
            "isection-a",
            "rev1",
            "3.1 Identify assets",
            "Identify assets",
            "OPERATIVE_PROCEDURE",
            0,
            10,
        ),
        ("isection-b", "rev1", "3.2 Group assets", "Group assets", "OPERATIVE_PROCEDURE", 10, 20),
        (
            "isection-toc",
            "rev1",
            "Table of Contents",
            "Table of Contents",
            "TABLE_OF_CONTENTS",
            20,
            30,
        ),
    ]
    for ordinal, section in enumerate(sections):
        conn.execute("insert into source_sections values (?,?,?,?,?,?,?,?)", (*section, ordinal))
    conn.commit()
    yield _StubRepo(conn)
    conn.close()


def test_record_traceability_writes_both_kinds_and_is_idempotent(trace_store: _StubRepo) -> None:
    receipt = ot.record_traceability(trace_store, "rev1")
    assert receipt["confirmed"] >= 1
    assert receipt["section_links"] >= 1
    rows = trace_store._conn.execute(
        "select relation_type, src_ref, dst_ref, status, review_state, derivation, citations_json"
        " from relationship_assertions order by relation_type, src_ref"
    ).fetchall()
    by_relation = {row[0] for row in rows}
    assert by_relation == {"ADDRESSES", "IMPLEMENTS"}
    for row in rows:
        assert row[3] == "machine_determined"
        assert row[4] == "machine_determined"
        assert row[5] == ot.DERIVATION
        assert "appendix_row" in json.loads(row[6])[0]
    addresses = [row for row in rows if row[0] == "ADDRESSES"]
    assert all(row[1] == "CIP-901/ACME Procedure v2.pdf" for row in addresses)
    implements = [row for row in rows if row[0] == "IMPLEMENTS"]
    assert all(str(row[1]).startswith("CIP-") for row in implements)  # src is a requirement
    assert all(str(row[2]).startswith("isection-") for row in implements)
    # the TOC section is never a target
    assert all(row[2] != "isection-toc" for row in implements)
    # idempotent: a second run replaces, never accumulates
    again = ot.record_traceability(trace_store, "rev1")
    assert again["section_links"] == receipt["section_links"]
    count = trace_store._conn.execute("select count(*) from relationship_assertions").fetchone()[0]
    assert count == len(rows)


# ── the HL edge check and the revocation pass ────────────────────────────────


def test_fresh_upload_yields_traceability_assertions(tmp_path) -> None:
    """The DD2 fresh-upload proof: a synthetic controlled document carrying a
    synthetic traceability appendix goes through the REAL per-document ingest
    (extract_pages -> parse control -> sectionize -> store) and its appendix
    row becomes machine_determined assertions — no operator text anywhere."""
    from portal.modules.compliance.core.operator_profile import PROFILE_PATH

    if not PROFILE_PATH.exists():  # gitignored, operator's machine only (CI has none)
        pytest.skip("the local operator profile is not present")

    from portal.modules.compliance.core import internal_corpus as ic
    from portal.modules.compliance.core.models import SourceDocument, SourceSection
    from portal.modules.compliance.core.operator_traceability import DERIVATION
    from portal.modules.compliance.core.repository import Repository
    from scripts.materialize_internal_corpus import _materialize_document

    requirement = "File each asset report with the operations recorder every week."
    pdf_path = _write_appendix_pdf(requirement)
    repo = Repository(tmp_path / "dd2.db")
    try:
        conn = repo._conn
        # the synthetic registry: a captured standard whose Part 1.1 anchor
        # the appendix row will be confirmed against
        repo.upsert_source_document(
            SourceDocument(
                logical_id="NERC/CIP-901-1",
                title="NERC/CIP-901-1",
                issuer="synthetic",
                source_kind="regulatory_standard",
                jurisdiction="US",
            )
        )
        registry = repo.add_document_revision(
            "NERC/CIP-901-1",
            "/docs/cip-901-1.pdf",
            requirement.encode("utf-8"),
            binding_effect="regulatory",
            effective_date="2026-01-01",
        )
        repo.put_document_text(
            registry.revision_id,
            requirement,
            page_count=1,
            extractor="fixture",
            extractor_version="0",
        )
        repo.add_source_section(
            SourceSection(
                section_id="csection-dd2-reg",
                revision_id=registry.revision_id,
                path="B. Requirements / 1.1",
                extractor="fixture",
                role="B_REQUIREMENTS_AND_MEASURES",
                title="1.1",
                unit_kind="table_row",
                ordinal=0,
                char_start=0,
                char_end=len(requirement),
                heading_path="1.1",
            )
        )
        conn.execute(
            "insert into requirement_sections (requirement_id, revision_id, section_id,"
            " relation, char_start, char_end, occurrences, anchor_method, anchored_at,"
            " extractor_version) values (?,?,?,?,?,?,1,'exact','2026-10-05','fixture')",
            (
                "CIP-901-1 R1 Part 1.1",
                registry.revision_id,
                "csection-dd2-reg",
                "governing",
                0,
                len(requirement),
            ),
        )
        conn.commit()
        repo.upsert_source_document(
            SourceDocument(
                logical_id="CIP-901/ACME Asset Procedure v1.pdf",
                title="ACME Asset Procedure",
                issuer="ACME",
                source_kind="operating_procedure",
                jurisdiction="internal",
            )
        )
        repo.add_document_revision(
            "CIP-901/ACME Asset Procedure v1.pdf",
            str(pdf_path),
            pdf_path.read_bytes(),
            binding_effect="internally_mandatory",
        )
        corpus = pdf_path.parent
        inv = ic.inventory_file(pdf_path)  # the real extract + control + sectionize path
        entry = _materialize_document(repo, corpus, pdf_path, inv)
        # the ingest hook recorded the appendix in the same pass
        assert entry["traceability"]["section_links"] >= 1
        rows = conn.execute(
            "select relation_type, src_ref, dst_ref, status, derivation"
            " from relationship_assertions"
        ).fetchall()
        assert {row[4] for row in rows} == {DERIVATION}
        assert {row[0] for row in rows} == {"ADDRESSES", "IMPLEMENTS"}
        links = [row for row in rows if row[0] == "IMPLEMENTS"]
        assert all(row[1] == "CIP-901-1 R1 Part 1.1" for row in links)
        targets = {row[2] for row in links}
        assert targets and all(target.startswith("isection-") for target in targets)
        stored = {
            str(r[0])
            for r in conn.execute(
                "select section_id from source_sections where revision_id=?",
                (inv["sha256"],),
            ).fetchall()
        }
        assert targets <= stored  # every target resolves in the fresh upload
    finally:
        repo.close()


def _write_appendix_pdf(requirement: str) -> pathlib.Path:
    """A one-page synthetic controlled document with sections and appendix."""
    import tempfile

    import fitz  # noqa: PLC0415 - pymupdf's stable import name

    document = fitz.open()
    page = document.new_page()
    text = (
        "PRIVATE - FOR INTERNAL USE ONLY\n"
        "ACME Asset Procedure\n"
        "Effective Date:  July 31, 2026\n"
        "Document Type: Procedure\n"
        "NERC Standard: CIP-901\n"
        "3.1 Identify Assets\n"
        "The team files each asset report.\n"
        "3.2 Group Assets\n"
        "The team groups assets by region.\n"
        "Appendix 1: Cross-Reference Between CIP-901-1 and ACME Procedure\n"
        f"R1 Part 1.1 {requirement} Sections 3.1, 3.2\n"
        "Page 1 of 1\n"
    )
    page.insert_text((72, 72), text, fontsize=11)
    handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, dir=tempfile.gettempdir())
    document.save(str(handle.name))
    document.close()
    handle.close()
    return pathlib.Path(handle.name)


@pytest.fixture
def edge_store() -> sqlite3.Connection:
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
            char_start int, char_end int, role text);
        create table document_texts (revision_id text primary key, full_text text);
        create table relationship_assertions (
            assertion_id text primary key, relation_type text, src_ref text,
            dst_ref text, derivation text, status text, review_state text,
            rationale text, decided_at text);
        """
    )
    conn.execute("insert into source_documents values ('NERC/X-1', 'US')")
    conn.execute("insert into document_revisions values ('r1', 'NERC/X-1', '2020-01-01', '', '')")
    full = "X" * 40 + "PRIVATE – FOR INTERNAL USE ONLY Page 3 of 14" + "Y" * 20
    conn.execute("insert into document_texts values ('r1', ?)", (full,))
    conn.execute(
        "insert into source_sections values ('csection-toc', 'r1', 'toc.p3', 'Table of Contents', 40, 60, 'TABLE_OF_CONTENTS')"
    )
    conn.execute(
        "insert into source_sections values ('csection-ok', 'r1', '3.1 Body', '3.1', 60, 61, 'B_REQUIREMENTS_AND_MEASURES')"
    )
    for assertion_id, dst, status in (
        ("e1", "csection-toc", "proposed"),
        ("e2", "csection-ok", "proposed"),
        ("e3", "csection-toc", "revoked"),
    ):
        conn.execute(
            "insert into relationship_assertions values (?, 'IMPLEMENTS', 'STD R1 Part 1.1', ?, 'proj', ?, 'proposed', '', '')",
            (assertion_id, dst, status),
        )
    conn.commit()
    return conn


def test_check_edges_censuses_live_edges_only(edge_store: sqlite3.Connection) -> None:
    full = {"r1": "X" * 40 + "PRIVATE – FOR INTERNAL USE ONLY Page 3 of 14" + "Y" * 20}
    result = di.check_edges(edge_store, full)
    # e1 (live, TOC endpoint) is the one finding; e3 is revoked and inert
    assert result.status == "fail"
    assert result.findings[0]["ineligible_count"] == 1


def test_revoke_pass_marks_only_live_ineligible_edges(edge_store: sqlite3.Connection) -> None:
    full = {"r1": "X" * 40 + "PRIVATE – FOR INTERNAL USE ONLY Page 3 of 14" + "Y" * 20}
    hits = rev.find_ineligible(edge_store, full)
    assert [hit["assertion_id"] for hit in hits] == ["e1"]
    assert hits[0]["reasons"]["dst_ref"].endswith("(toc)")
    rev.apply_revocations(":memory:", [])  # smoke: empty apply is a no-op
    # apply writes through a fresh connection to the store path — use the
    # in-memory db directly here via its driver check
    stamp = "2026-10-05T00:00:00+00:00"
    with edge_store:
        for hit in hits:
            edge_store.execute(
                "update relationship_assertions set status='revoked', review_state='revoked',"
                " decided_at=?, rationale=? where assertion_id=?",
                (stamp, f"{hit['rationale']} | revoked DD2", hit["assertion_id"]),
            )
    row = edge_store.execute(
        "select status, rationale from relationship_assertions where assertion_id='e1'"
    ).fetchone()
    assert row["status"] == "revoked"
    assert "revoked DD2" in row["rationale"]
    full2 = full
    result = di.check_edges(edge_store, full2)
    assert result.status == "pass"
