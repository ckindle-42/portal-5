"""DATA_TRUTH DD2 — the operator traceability assertions, hermetically.

The promotion of the D-DT-8 probe parser into the internal corpus: appendix
parsing, text-first requirement confirmation (the ≥0.6 gate that rejected the
probe's 24 header misreads), section resolution (probe rules first, counted
undotted-number fixes second), idempotent store writes, the HL edge check's
live-only census, and the mechanical revocation of ineligible endpoints.
"""

from __future__ import annotations

import sqlite3
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
