"""The three duplicate paths, and the boundaries they crossed.

Each of these is a surface that had grown a second, weaker implementation of
something the module already did correctly: a search that filtered after
ranking beside one that filters before it, a citation read as an assertion
beside a store that has relation types for the distinction, and a batch
decision that took any row id at all beside `approve`/`revoke`, which do not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.compliance.core import candidate_links
from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.mapping_store import MappingStore
from portal.modules.compliance.core.models import RelationshipAssertion, SourceDocument
from portal.modules.compliance.core.repository import Repository


def _capture(path: Path, rows: list[tuple[str, str]]) -> CapturedDocument:
    units, buf, cursor = [], [], 0
    for ordinal, (heading, body) in enumerate(rows):
        piece = body + "\n"
        units.append(
            CapturedUnit(
                ordinal=ordinal,
                unit_kind="prose",
                heading_path=heading,
                title=heading,
                page_start=1,
                page_end=1,
                char_start=cursor,
                char_end=cursor + len(piece),
                text=piece,
            )
        )
        buf.append(piece)
        cursor += len(piece)
    return CapturedDocument(
        path=path,
        page_count=1,
        full_text="".join(buf),
        units=units,
        reader_strings=tuple(body for _h, body in rows),
    )


@pytest.fixture
def store(tmp_path: Path) -> Repository:
    repo = Repository(tmp_path / "store.db")
    repo.upsert_source_document(
        SourceDocument(
            logical_id="LSPG/patching",
            title="patching",
            issuer="LSPG",
            source_kind="procedure",
            jurisdiction="internal",
        )
    )
    revision = repo.add_document_revision("LSPG/patching", "/docs/patching", b"patching")
    store_capture(
        repo,
        revision.revision_id,
        _capture(
            Path("/docs/patching"),
            [
                ("3 Patching", "The OT team evaluates security patches every 30 calendar days."),
                ("4 Sources", "Patch sources are registered in the asset inventory."),
            ],
        ),
    )
    yield repo
    repo.close()


def _sections(repo: Repository) -> list[str]:
    return [
        str(row[0])
        for row in repo._conn.execute("SELECT section_id FROM source_sections ORDER BY ordinal")
    ]


def _answer(repo: Repository, answer: str, sections: list[str]) -> str:
    from portal.modules.compliance.core.temporal import now_iso

    answer_id = "answer-test"
    with repo._lock, repo._conn:
        repo._conn.execute(
            """INSERT INTO conversation_answers(answer_id, thread_id, asked_at, question,
                   answer, model, subject_ref, org_id)
               VALUES (?,'',?,?,?,'stub','CIP-007-6 R2 Part 2.2','default')""",
            (answer_id, now_iso(), "does what we do achieve this?", answer),
        )
        repo._conn.executemany(
            """INSERT INTO answer_citations(answer_id, cited_ref, resolved, resolves_to,
                   revision_id, jurisdiction, source_kind, detail)
               VALUES (?,?,1,'','','internal','procedure','')""",
            [(answer_id, section_id) for section_id in sections],
        )
    return answer_id


class TestOneSearchComposition:
    """The reader's tool had grown a second search: retrieve an unscoped top-k,
    then drop the results not joined to `requirement`. That is the keyhole the
    shared predicate removes, rebuilt beside it — and because it filtered
    against the REGULATORY anchors, `requirement=` also discarded every operator
    hit, in the one tool a bilateral reading uses to find the operator's side."""

    def test_the_reader_tool_delegates_to_the_shared_composition(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import reading_tools, search_service

        seen: dict = {}

        def _search(repo, query, **kwargs):  # noqa: ANN001, ANN202
            seen.update({"query": query, **kwargs})
            return {"results": [{"section_id": "csection-x"}]}

        monkeypatch.setattr(search_service, "search", _search)
        out = reading_tools.compliance_search(store, "patches", requirement="CIP-007-6 R2 Part 2.2")
        assert seen["requirement"] == "CIP-007-6 R2 Part 2.2"
        assert out["section_ids"] == ["csection-x"]

    def test_the_reader_asks_for_every_relation_not_just_the_duty_text(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import enumeration, reading_tools, search_service

        seen: dict = {}
        monkeypatch.setattr(
            search_service,
            "search",
            lambda repo, query, **kwargs: (seen.update(kwargs), {"results": []})[1],
        )
        reading_tools.compliance_search(store, "patches", requirement="CIP-007-6 R2")
        assert set(seen["relations"].split(",")) == set(enumeration.ALL_RELATIONS)

    def test_the_post_filter_is_gone(self) -> None:
        import inspect

        from portal.modules.compliance.core import reading_tools

        source = inspect.getsource(reading_tools.compliance_search)
        assert "sections_for_requirement" not in source
        assert "search_service.search" in source


class TestACitationIsEvidenceNotAnAssertion:
    """Every resolved internal citation became an IMPLEMENTS proposal — including
    the sentence saying the section does NOT satisfy the duty. Those proposals
    reach the review queue and, once approved, the labelled evaluation set, so
    counterevidence was recorded as the implementation of what it contradicts."""

    @pytest.mark.parametrize(
        ("sentence", "expected"),
        [
            ("Our procedure implements this duty [x].", "IMPLEMENTS"),
            ("The runbook satisfies the 35-day ceiling [x].", "IMPLEMENTS"),
            ("The change log evidences each evaluation [x].", "EVIDENCES"),
            ("Our procedure does not implement this duty [x].", ""),
            ("The note conflicts with the procedure [x].", ""),
            ("We are stricter than the standard requires [x].", ""),
            ("Section 3 discusses patch sources [x].", ""),
            ("", ""),
        ],
    )
    def test_only_a_positive_assertion_yields_a_relation(
        self, sentence: str, expected: str
    ) -> None:
        assert candidate_links.classify_assertion(sentence)[0] == expected

    def test_a_negating_sentence_proposes_nothing_and_says_why(self, store: Repository) -> None:
        sections = _sections(store)
        answer_id = _answer(
            store,
            f"Our procedure does not implement the 35-day evaluation [{sections[0]}].",
            [sections[0]],
        )
        out = candidate_links.links_from_answer(store, answer_id, "CIP-007-6 R2 Part 2.2")
        assert out["proposed"] == []
        assert out["withheld"][0]["section_id"] == sections[0]
        assert "negates" in out["withheld"][0]["reason"]
        assert (
            store._conn.execute("SELECT COUNT(*) FROM relationship_assertions").fetchone()[0] == 0
        )

    def test_an_asserting_sentence_proposes_the_relation_it_named(self, store: Repository) -> None:
        sections = _sections(store)
        answer_id = _answer(
            store,
            f"Our procedure implements the evaluation duty [{sections[0]}]. "
            f"The inventory does not cover third-party sources [{sections[1]}].",
            sections,
        )
        out = candidate_links.links_from_answer(store, answer_id, "CIP-007-6 R2 Part 2.2")
        assert [entry["section_id"] for entry in out["proposed"]] == [sections[0]]
        assert out["proposed"][0]["relation"] == "IMPLEMENTS"
        assert [entry["section_id"] for entry in out["withheld"]] == [sections[1]]

    def test_a_relation_is_never_inferred_by_the_recorder(self, store: Repository) -> None:
        with pytest.raises(ValueError, match="relation must be one of"):
            candidate_links.record_reading_link(
                store,
                src_ref="CIP-007-6 R2 Part 2.2",
                dst_section_id=_sections(store)[0],
                answer_id="a",
                relation="RELATES_TO",
            )


class TestTheBatchDecidesOnlyOpenMappings:
    """Authentication says who is deciding. It does not say WHAT they may
    decide: the batch took any relationship_assertions id at all."""

    def _row(self, store: Repository, **overrides) -> str:
        fields = {
            "assertion_id": "rel-x",
            "relation_type": "IMPLEMENTS",
            "src_ref": "CIP-007-6 R2 Part 2.2",
            "src_revision_id": None,
            "dst_ref": "LSPG/patching::" + _sections(store)[0],
            "dst_revision_id": None,
            "scope": "",
            "citations": [],
            "status": "proposed",
            "review_state": "proposed",
        }
        fields.update(overrides)
        saved = store.propose_relationship(RelationshipAssertion(**fields))
        return saved.assertion_id

    def _decide(self, store: Repository, assertion_id: str, **kwargs) -> dict:
        mapping_store = MappingStore(store.path)
        version = store.get_relationship(assertion_id).version
        (result,) = mapping_store.decide_batch(
            [{"mapping_id": assertion_id, "version": version, "decision": "APPROVE"}],
            "reviewer",
            **kwargs,
        )
        return result

    def test_an_open_mapping_is_decided(self, store: Repository) -> None:
        assert self._decide(store, self._row(store))["status"] == "APPLIED"

    def test_a_non_mapping_relation_is_refused(self, store: Repository) -> None:
        result = self._decide(store, self._row(store, relation_type="SUPERSEDES"))
        assert result["status"] == "OUT_OF_SCOPE"
        assert "not a mapping relation" in result["error"]

    def test_a_row_from_another_organisation_is_refused(self, store: Repository) -> None:
        result = self._decide(store, self._row(store, org_id="other"))
        assert result["status"] == "OUT_OF_SCOPE"
        assert "another organisation" in result["error"]

    def test_an_already_decided_mapping_is_not_redecided_here(self, store: Repository) -> None:
        assertion_id = self._row(store)
        assert self._decide(store, assertion_id)["status"] == "APPLIED"
        result = self._decide(store, assertion_id)
        assert result["status"] == "OUT_OF_SCOPE"
        assert "already approved" in result["error"]
