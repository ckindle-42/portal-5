"""PROVE_THEN_SCALE_V1 — the mechanical contracts behind the campaign.

Live-only where "did it read and understand" is the question; unit-tested
where the machinery makes promises the sweep depends on:

* a determination writes at ``machine_determined`` with provenance, and never
  an edge whose justifying sentence is not in the section's text;
* the bootstrap guard: a pairing the store holds is corroborated, never
  re-created;
* the material renderer: byte-identical fixed body per revision, standing
  labels on every entry, the shared prefix FIRST;
* the sweep order: dependency order across standards, numeric order within;
* the contradiction scan: cross-reading disagreement is the review queue.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.compliance.core import (
    candidate_links,
    contradictions,
    sweep,
)
from portal.modules.compliance.core.repository import Repository


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    r = Repository(tmp_path / "pts.db")
    _seed_register(r, "CIP-007-6", [("R1", "1.1"), ("R2", "2.1"), ("R2", "2.2"), ("R2", "2.3"), ("R2", "2.4"), ("R3", "3.1"), ("R3", "3.2"), ("R3", "3.3"), ("R4", "4.4"), ("R5", "5.1"), ("R5", "5.2"), ("R5", "5.3"), ("R5", "5.4"), ("R5", "5.5"), ("R5", "5.6"), ("R5", "5.7")])
    yield r
    r.close()


def _seed_register(repo: Repository, standard: str, parts: list[tuple[str, str]]) -> None:
    """A minimal register: a standard revision and the requirement nodes the
    determinations must resolve against — parseable is not resolvable."""
    with repo._lock, repo._conn:
        repo._conn.execute(
            """INSERT INTO standard_revisions(revision_id, logical_id, family, version)
               VALUES (?, ?, ?, '1')
               ON CONFLICT(revision_id) DO NOTHING""",
            (standard, f"NERC/{standard}", standard.rsplit("-", 1)[0]),
        )
        for requirement, part in parts:
            repo._conn.execute(
                """INSERT INTO requirement_nodes(node_id, standard_revision_id, requirement, part)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(node_id) DO NOTHING""",
                (f"{standard} {requirement} Part {part}", standard, requirement, part),
            )


def _add_section(
    repo: Repository,
    section_id: str,
    text: str,
    *,
    jurisdiction: str = "internal",
    logical_id: str = "LSPG Security Patch Management Procedure",
) -> str:
    """Capture one section and return the id it actually carries."""
    from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
    from portal.modules.compliance.core.models import SourceDocument

    repo.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=logical_id,
            issuer="LSPG",
            source_kind="procedure",
            jurisdiction=jurisdiction,
        )
    )
    revision = repo.add_document_revision(logical_id, logical_id, text.encode())
    store_capture(
        repo,
        revision.revision_id,
        CapturedDocument(
            path=Path(f"{logical_id}.pdf"),
            page_count=1,
            full_text=text,
            units=[
                CapturedUnit(
                    ordinal=0,
                    unit_kind="prose",
                    heading_path="3.3 Discovery",
                    title=section_id,
                    page_start=1,
                    page_end=1,
                    char_start=0,
                    char_end=len(text),
                    text=text,
                )
            ],
            extractor="test",
            extractor_version="1",
        ),
    )
    row = repo._conn.execute(
        "SELECT section_id FROM source_sections WHERE revision_id = ?",
        (revision.revision_id,),
    ).fetchone()
    return str(row[0])


class TestRecordDetermination:
    def test_a_determination_writes_machine_determined_with_provenance(
        self, repo: Repository
    ) -> None:
        text = "At least once every thirty-five (35) calendar days, SMEs shall review all approved sources."
        sid = _add_section(repo, "3.3.1 discovery", text)
        outcome = candidate_links.record_determination(
            repo,
            requirement_id="CIP-007-6 R2 Part 2.2",
            section_id=sid,
            relation_type="IMPLEMENTS",
            answer_id="answer-1",
            sentence="At least once every thirty-five (35) calendar days, SMEs shall review",
            confidence=0.9,
            read_ref="CIP-007-6 R2 Part 2.2",
            run_id="run-1",
        )
        assert outcome["action"] == "determined"
        row = repo.get_relationship(outcome["assertion_id"])
        assert row.status == "machine_determined", "never approved by a machine"
        assert row.review_state == "machine_determined"
        assert row.derivation == "reading"
        assert row.confidence == 0.9
        citation = row.citations[0]
        assert citation["answer_id"] == "answer-1"
        assert citation["run_id"] == "run-1"
        assert "thirty-five" in citation["sentence"]

    def test_an_edge_without_a_verbatim_sentence_is_not_written(self, repo: Repository) -> None:
        sid = _add_section(repo, "3.3.2 eval", "The procedure evaluates patches regularly.")
        outcome = candidate_links.record_determination(
            repo,
            requirement_id="CIP-007-6 R2 Part 2.2",
            section_id=sid,
            relation_type="IMPLEMENTS",
            answer_id="answer-1",
            sentence="The procedure evaluates patches every 35 calendar days",
        )
        assert outcome["action"] == "rejected"
        assert "not in the section" in outcome["reason"]
        assert repo._conn.execute("SELECT COUNT(*) FROM relationship_assertions").fetchone()[0] == 0

    def test_a_regulatory_section_is_never_a_determination_target(self, repo: Repository) -> None:
        sid = _add_section(
            repo,
            "Part 2.2 governing",
            "Evaluate patches every 35 days.",
            jurisdiction="regulatory",
            logical_id="CIP-007-6",
        )
        outcome = candidate_links.record_determination(
            repo,
            requirement_id="CIP-007-6 R2 Part 2.2",
            section_id=sid,
            relation_type="IMPLEMENTS",
            answer_id="answer-1",
            sentence="Evaluate patches every 35 days.",
        )
        assert outcome["action"] == "rejected"
        assert "OPERATOR section" in outcome["reason"]

    def test_the_bootstrap_guard_corroborates_a_pairing_the_store_holds(
        self, repo: Repository
    ) -> None:
        section_id = _add_section(
            repo,
            "3.3.1 review",
            "SMEs in conjunction with Foxguard shall review all approved sources.",
        )
        first = candidate_links.record_determination(
            repo,
            requirement_id="CIP-007-6 R2 Part 2.2",
            section_id=section_id,
            relation_type="IMPLEMENTS",
            answer_id="answer-1",
            sentence="SMEs in conjunction with Foxguard shall review all approved sources.",
        )
        assert first["action"] == "determined"
        # a later reading sees the same pairing — corroborate, never re-create
        second = candidate_links.record_determination(
            repo,
            requirement_id="CIP-007-6 R2 Part 2.2",
            section_id=section_id,
            relation_type="IMPLEMENTS",
            answer_id="answer-2",
            sentence="SMEs in conjunction with Foxguard shall review all approved sources.",
        )
        assert second["action"] == "corroborated"
        assert second["assertion_id"] == first["assertion_id"]
        assert (
            repo._conn.execute(
                "SELECT COUNT(*) FROM relationship_assertions WHERE status = 'machine_determined'"
            ).fetchone()[0]
            == 1
        )
        row = repo.get_relationship(first["assertion_id"])
        citations = row.citations
        assert [c["answer_id"] for c in citations] == ["answer-1", "answer-2"]
        assert citations[1]["corroborated"] is True

    def test_a_well_formed_but_unregistered_requirement_is_refused(self, repo: Repository) -> None:
        sid = _add_section(repo, "5.1 traceability", "Appendix 1 provides a cross-reference between the standards")
        outcome = candidate_links.record_determination(
            repo,
            requirement_id="CIP-003-6 R1 Part 1.1.4",  # plausible address, no such register revision
            section_id=sid,
            relation_type="REFERENCES",
            answer_id="answer-1",
            sentence="Appendix 1 provides a cross-reference between the standards",
        )
        assert outcome["action"] == "rejected"
        assert "not in the register" in outcome["reason"]
        assert (
            repo._conn.execute("SELECT COUNT(*) FROM relationship_assertions").fetchone()[0] == 0
        )

    def test_the_relation_is_the_reading_s_choice(self, repo: Repository) -> None:
        section_id = _add_section(
            repo,
            "5.1 traceability",
            "Appendix 1 provides a cross-reference between the standards and this procedure.",
        )
        for relation in candidate_links.DETERMINATION_RELATIONS:
            outcome = candidate_links.record_determination(
                repo,
                requirement_id=f"CIP-007-6 R2 Part 2.{candidate_links.DETERMINATION_RELATIONS.index(relation) + 1}",
                section_id=section_id,
                relation_type=relation,
                answer_id="answer-1",
                sentence="Appendix 1 provides a cross-reference between the standards",
            )
            assert outcome["action"] == "determined"
        bad = candidate_links.record_determination(
            repo,
            requirement_id="CIP-007-6 R2 Part 2.1",
            section_id=section_id,
            relation_type="SUPPORTS",
            answer_id="answer-1",
            sentence="Appendix 1 provides a cross-reference between the standards",
        )
        assert bad["action"] == "rejected"


class TestMappingStoreStatuses:
    def test_machine_determined_is_a_first_class_status(self, repo: Repository) -> None:
        from portal.modules.compliance.core import mapping_store

        assert "machine_determined" in mapping_store._ALL_STATUSES
        assert "machine_determined" in mapping_store._DECIDABLE_STATUSES
        assert "approved" not in mapping_store._DECIDABLE_STATUSES

    def test_a_determined_row_is_decidable_but_never_redecidable(self, repo: Repository) -> None:
        section_id = _add_section(
            repo, "3.4 evaluate", "LSPG shall evaluate patches every 35 days."
        )
        outcome = candidate_links.record_determination(
            repo,
            requirement_id="CIP-007-6 R2 Part 2.2",
            section_id=section_id,
            relation_type="IMPLEMENTS",
            answer_id="answer-1",
            sentence="LSPG shall evaluate patches every 35 days.",
        )
        store = mapping_store_facade(repo)
        results = store.decide_batch(
            [{"mapping_id": outcome["assertion_id"], "decision": "APPROVE", "version": 1}],
            sme="sme-1",
        )
        assert results[0]["status"] == "APPLIED"
        assert repo.get_relationship(outcome["assertion_id"]).status == "approved"
        # a decided row is closed to the batch surface
        again = store.decide_batch(
            [{"mapping_id": outcome["assertion_id"], "decision": "REJECT", "version": 2}],
            sme="sme-1",
        )
        assert again[0]["status"] == "OUT_OF_SCOPE"


def mapping_store_facade(repo: Repository):
    from portal.modules.compliance.core.mapping_store import MappingStore

    store = MappingStore(repo.path)
    store._repo = repo  # share the connection the fixture manages
    return store


class TestParseDeterminations:
    def test_the_fenced_block_parses(self) -> None:
        answer = 'prose prose\n```json\n{"determinations": [{"section_id": "s", "relation_type": "IMPLEMENTS"}]}\n```\n'
        entries, error = sweep.parse_determinations(answer)
        assert error == ""
        assert entries[0]["relation_type"] == "IMPLEMENTS"

    def test_a_missing_block_is_a_recorded_reason_not_an_exception(self) -> None:
        entries, error = sweep.parse_determinations("no block here")
        assert entries == []
        assert "no determinations block" in error


class TestSweepOrder:
    def test_standards_run_in_dependency_order(self, repo: Repository) -> None:
        order = sweep.sweep_order(repo)
        assert order, "the register is empty — nothing to order"
        families = [ref.split(" ")[0].rsplit("-", 1)[0] for ref in order]
        sequence = list(dict.fromkeys(families))
        named = [s for s, _ in sweep.STANDARD_ORDER]
        assert sequence == [s for s in named if s in set(sequence)], (
            "the sweep runs the standards in the recorded dependency order"
        )
        # non-vacuous: the register genuinely carries the family revision the
        # campaign sweeps, and the order carries every one of its nodes
        cip007 = [ref for ref in order if ref.split(" ")[0].rsplit("-", 1)[0] == "CIP-007"]
        assert len(cip007) == 20, f"CIP-007-6 contributes 20 Part nodes, got {len(cip007)}"

    def test_refs_for_standard_selects_a_revision_family(self, repo: Repository) -> None:
        from portal.modules.compliance.core.cip_register import Register

        refs = sweep.refs_for_standard(Register.load(), "CIP-007-6")
        assert len(refs) == 20, "the revision key must reach its family's nodes"
        assert refs[0] == "CIP-007-6 R1 Part 1.1" and refs[-1] == "CIP-007-6 R5 Part 5.7"

    def test_within_a_standard_requirements_run_in_numeric_order(self, repo: Repository) -> None:
        order = sweep.sweep_order(repo)
        r2 = [ref for ref in order if ref.startswith("CIP-007-6 R2")]
        assert r2 == [
            "CIP-007-6 R2 Part 2.1",
            "CIP-007-6 R2 Part 2.2",
            "CIP-007-6 R2 Part 2.3",
            "CIP-007-6 R2 Part 2.4",
        ]


class TestContradictionScan:
    def test_cross_reading_disagreement_is_the_review_queue(self, repo: Repository) -> None:
        section_id = _add_section(repo, "3.3 review", "The operator reviews patches every 35 days.")
        candidate_links.record_determination(
            repo,
            requirement_id="CIP-007-6 R2 Part 2.2",
            section_id=section_id,
            relation_type="IMPLEMENTS",
            answer_id="answer-1",
            sentence="The operator reviews patches every 35 days.",
        )
        # a different reading says the same pair is EVIDENCES — no row is
        # overwritten; the scan surfaces the disagreement
        candidate_links.record_determination(
            repo,
            requirement_id="CIP-007-6 R2 Part 2.2",
            section_id=section_id,
            relation_type="EVIDENCES",
            answer_id="answer-2",
            sentence="The operator reviews patches every 35 days.",
        )
        report = contradictions.scan_contradictions(repo)
        assert len(report["relation_conflicts"]) == 1
        conflict = report["relation_conflicts"][0]
        assert {r["relation_type"] for r in conflict["relations"]} == {"IMPLEMENTS", "EVIDENCES"}
        assert report["n_items"] >= 1

    def test_a_determination_against_a_rejected_edge_is_named(self, repo: Repository) -> None:
        section_id = _add_section(repo, "3.3 sources", "Review sources for patches.")
        candidate_links.record_determination(
            repo,
            requirement_id="CIP-007-6 R2 Part 2.2",
            section_id=section_id,
            relation_type="IMPLEMENTS",
            answer_id="answer-1",
            sentence="Review sources for patches.",
        )
        store = mapping_store_facade(repo)
        row = repo._conn.execute(
            "SELECT assertion_id FROM relationship_assertions WHERE status='machine_determined'"
        ).fetchone()
        store.decide_batch(
            [{"mapping_id": row[0], "decision": "REJECT", "version": 1}], sme="sme-1"
        )
        # a later reading determines the rejected pairing again
        candidate_links.record_determination(
            repo,
            requirement_id="CIP-007-6 R2 Part 2.2",
            section_id=section_id,
            relation_type="IMPLEMENTS",
            answer_id="answer-2",
            sentence="Review sources for patches.",
        )
        report = contradictions.scan_contradictions(repo)
        assert len(report["rejected_contradictions"]) == 1
        assert report["rejected_contradictions"][0]["rejected_by"] == "sme-1"
