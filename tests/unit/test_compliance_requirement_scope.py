"""A parent requirement reaches its Parts' evidence (ONE_REGULATORY_EXTRACTION_V1 P4.3).

The defect these pin: an analyst asks about ``CIP-007-6 R2``, and the store
keys every anchor and every operator edge to ``R2 Part 2.1`` … ``Part 2.4``. An
exact lookup on the parent returned nothing, so the closure receipt reported
``eligible=[] examined=[] unread=[]`` — which reads as *a complete reading*
rather than as *no population at all*, and classified the answer's own
regulatory citations as ``outside`` scope.

So the scope is asserted from both ends: that the parent expands, and that the
expansion comes from the standard's own numbering rather than from string
shape — ``'CIP-007-6 R2'`` is a prefix of ``'CIP-007-6 R20'`` exactly as
readily as of ``'CIP-007-6 R2 Part 2.1'``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.compliance.core import requirement_scope
from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.models import RelationshipAssertion, SourceDocument
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.temporal import now_iso

PART_ROWS = [
    ("B. Requirements and Measures", "2.1 | High Impact | Identify a source for patches. | M."),
    ("B. Requirements and Measures", "2.2 | High Impact | Evaluate every 35 calendar days. | M."),
    ("B. Requirements and Measures", "2.3 | High Impact | Apply within 35 days. | M."),
    ("B. Requirements and Measures", "2.4 | High Impact | Implement the plan. | M."),
]
OPERATOR_ROWS = [
    ("3 Patching", "The OT team evaluates patches once every 30 calendar days."),
    ("4 Sources", "Patch sources are registered in the asset inventory."),
]


def _capture(path: Path, rows: list[tuple[str, str]]) -> CapturedDocument:
    units, buf, cursor = [], [], 0
    for ordinal, (heading, body) in enumerate(rows):
        piece = body + "\n"
        units.append(
            CapturedUnit(
                ordinal=ordinal,
                unit_kind="table_row" if " | " in body else "prose",
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


def _document(repo: Repository, logical_id: str, jurisdiction: str, kind: str, rows: list) -> str:
    repo.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=logical_id,
            issuer="x",
            source_kind=kind,
            jurisdiction=jurisdiction,
        )
    )
    revision = repo.add_document_revision(logical_id, f"/docs/{logical_id}", logical_id.encode())
    store_capture(repo, revision.revision_id, _capture(Path(f"/docs/{logical_id}"), rows))
    return revision.revision_id


def _sections(repo: Repository, revision_id: str) -> list[str]:
    return [
        str(row[0])
        for row in repo._conn.execute(
            "SELECT section_id FROM source_sections WHERE revision_id = ? ORDER BY ordinal",
            (revision_id,),
        )
    ]


@pytest.fixture
def store(tmp_path: Path) -> Repository:
    repo = Repository(tmp_path / "store.db")
    regulatory = _document(repo, "NERC/CIP-007-6", "US", "regulatory_standard", PART_ROWS)
    operator = _document(repo, "LSPG/patching", "internal", "procedure", OPERATOR_ROWS)

    # the register: the standard's own numbering, which is where the scope comes
    # from. Four Parts under R2 and one under R20, so a prefix match would be
    # visibly wrong rather than merely untested.
    with repo._lock, repo._conn:
        repo._conn.execute(
            "INSERT OR IGNORE INTO standard_revisions(revision_id, logical_id, family, version,"
            " org_id) VALUES ('CIP-007-6','CIP-007','CIP-007','6','default')"
        )
        for part in ("2.1", "2.2", "2.3", "2.4", "2.10"):
            repo._conn.execute(
                "INSERT OR IGNORE INTO requirement_nodes(node_id, standard_revision_id,"
                " requirement, part, logical_lineage_id, org_id) VALUES (?,?,?,?,'','default')",
                (f"CIP-007-6 R2 Part {part}", "CIP-007-6", "R2", part),
            )
        repo._conn.execute(
            "INSERT OR IGNORE INTO requirement_nodes(node_id, standard_revision_id,"
            " requirement, part, logical_lineage_id, org_id) VALUES"
            " ('CIP-007-6 R20 Part 20.1','CIP-007-6','R20','20.1','','default')"
        )

    # anchors and edges live on the LEAVES, never on the parent — the live shape
    from portal.modules.compliance.core import requirement_anchor as ra

    rows = _sections(repo, regulatory)
    for index, part in enumerate(("2.1", "2.2", "2.3", "2.4")):
        repo.record_anchors(
            [
                ra.Anchor(
                    requirement_id=f"CIP-007-6 R2 Part {part}",
                    revision_id=regulatory,
                    relation="governing",
                    anchored=True,
                    char_start=0,
                    char_end=1,
                    section_ids=[rows[index]],
                    occurrences=1,
                )
            ]
        )
    operator_sections = _sections(repo, operator)
    for part, section_id in (("2.1", operator_sections[1]), ("2.2", operator_sections[0])):
        repo.propose_relationship(
            RelationshipAssertion(
                assertion_id=f"rel-{part}",
                relation_type="IMPLEMENTS",
                src_ref=f"CIP-007-6 R2 Part {part}",
                src_revision_id=None,
                dst_ref=f"LSPG/patching::{section_id}",
                dst_revision_id=None,
                scope="",
                citations=[],
                status="proposed",
                review_state="proposed",
                valid_from=now_iso()[:10],
            )
        )
    yield repo
    repo.close()


class TestTheParentStandsForItsParts:
    def test_a_parent_requirement_resolves_to_its_parts(self, store: Repository) -> None:
        scope = requirement_scope.resolve(store, "CIP-007-6 R2")
        assert scope.is_parent
        assert scope.leaves == [
            "CIP-007-6 R2 Part 2.1",
            "CIP-007-6 R2 Part 2.2",
            "CIP-007-6 R2 Part 2.3",
            "CIP-007-6 R2 Part 2.4",
            "CIP-007-6 R2 Part 2.10",
        ]

    def test_the_parent_stays_in_its_own_scope(self, store: Repository) -> None:
        # some standards anchor material to the bare requirement as well as to
        # its Parts; dropping it trades one empty population for another
        assert requirement_scope.resolve(store, "CIP-007-6 R2").refs[0] == "CIP-007-6 R2"

    def test_a_part_is_its_own_leaf(self, store: Repository) -> None:
        scope = requirement_scope.resolve(store, "CIP-007-6 R2 Part 2.2")
        assert scope.leaves == []
        assert scope.refs == ["CIP-007-6 R2 Part 2.2"]

    def test_a_sibling_requirement_is_never_dragged_in_by_prefix(self, store: Repository) -> None:
        # 'CIP-007-6 R2' is a prefix of 'CIP-007-6 R20 Part 20.1'
        leaves = requirement_scope.resolve(store, "CIP-007-6 R2").leaves
        assert not any("R20" in leaf for leaf in leaves)

    def test_a_requirement_with_no_parts_stands_for_itself(self, store: Repository) -> None:
        scope = requirement_scope.resolve(store, "CIP-007-6 R9")
        assert scope.refs == ["CIP-007-6 R9"]
        assert "numbers no Parts" in scope.detail

    def test_something_that_is_not_an_address_is_not_guessed_at(self, store: Repository) -> None:
        scope = requirement_scope.resolve(store, "csection-" + "0" * 20)
        assert scope.refs == ["csection-" + "0" * 20]
        assert "not a regulatory address" in scope.detail


class TestThePopulationIsBilateralAndScoped:
    def test_the_parent_population_is_not_empty(self, store: Repository) -> None:
        # the defect, stated as an assertion: this returned NOTHING
        population = requirement_scope.population(store, "CIP-007-6 R2")
        assert population["population_method"] == "join"
        assert len(population["regulatory"]) == 4
        assert len(population["operator"]) == 2

    def test_every_eligible_section_keeps_the_part_it_belongs_to(self, store: Repository) -> None:
        population = requirement_scope.population(store, "CIP-007-6 R2")
        assert {entry["requirement_id"] for entry in population["sections"].values()} == {
            "CIP-007-6 R2 Part 2.1",
            "CIP-007-6 R2 Part 2.2",
            "CIP-007-6 R2 Part 2.3",
            "CIP-007-6 R2 Part 2.4",
        }

    def test_an_operator_edge_keeps_its_status(self, store: Repository) -> None:
        population = requirement_scope.population(store, "CIP-007-6 R2")
        operator = population["operator"]
        assert {entry["link_status"] for entry in operator} == {"proposed"}
        assert all(entry["side"] == "operator" for entry in operator)

    def test_a_leaf_population_is_a_subset_of_its_parents(self, store: Repository) -> None:
        parent = set(requirement_scope.population(store, "CIP-007-6 R2")["section_ids"])
        leaf = set(requirement_scope.population(store, "CIP-007-6 R2 Part 2.2")["section_ids"])
        assert leaf and leaf < parent

    def test_the_proximity_fallback_is_named_never_silent(self, store: Repository) -> None:
        population = requirement_scope.population(
            store, "CIP-007-6 R9", proximity_fallback=lambda: [{"section_id": "x"}]
        )
        assert population["population_method"] == "proximity"
        assert "weaker basis than the join" in population["detail"]


class TestTheAssemblyAndTheClosureShareTheScope:
    def test_the_assembly_of_a_parent_carries_every_part(self, store: Repository) -> None:
        from portal.modules.compliance.core.reading_assembly import assemble

        context = assemble(store, "CIP-007-6 R2")
        assert context["population_method"] == "join"
        assert context["scope"]["method"] == "parts"
        text = " ".join(
            section["text"]
            for component in context["components"]
            if component["component"] == "requirement"
            for section in component["sections"]
        )
        for part in ("2.1", "2.2", "2.3", "2.4"):
            assert f"{part} | High Impact" in text

    def test_the_linked_operator_sections_reach_a_parent_requirement(
        self, store: Repository
    ) -> None:
        from portal.modules.compliance.core.reading_assembly import linked_internal

        linked = linked_internal(store, "CIP-007-6 R2")
        assert len(linked) == 2
        assert {entry["link_requirement"] for entry in linked} == {
            "CIP-007-6 R2 Part 2.1",
            "CIP-007-6 R2 Part 2.2",
        }

    def test_the_closure_receipt_of_a_parent_reading_has_a_population(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import reader, reading_transport

        monkeypatch.setattr(
            reading_transport,
            "_post",
            lambda payload, timeout: {
                "message": {"content": "an answer"},
                "prompt_eval_count": 900,
                "eval_count": 40,
            },
        )
        closure = reader.read(
            store, "are we stricter than we need to be?", "CIP-007-6 R2", model="stub", store=False
        )["closure_receipt"]
        assert closure["eligible"], "an empty population reports complete and reads as a finding"
        assert closure["scope"]["leaves"]
        assert set(closure["population"]) == set(closure["eligible"])


class TestTheNoteIsPartOfThePopulation:
    """Found live: a Part 2.2 reading correctly engaged the operator's own note
    — *we evaluate every 30 days, not the 35 the Part allows, and the extra
    strictness is deliberate* — and the receipt classified that citation as
    `outside` scope, because the population was anchors and edges only. A note
    is neither, and it travels in the assembly already."""

    def test_an_operator_note_is_eligible_material(self, store: Repository) -> None:
        from portal.modules.compliance.core.notes import write_note

        note = write_note(
            store,
            subject_ref="CIP-007-6 R2 Part 2.2",
            body="We evaluate every 30 days, not the 35 the Part allows. Deliberate.",
            kind="intentional_strictness",
        )
        population = requirement_scope.population(store, "CIP-007-6 R2 Part 2.2")
        assert note["section_id"] in population["section_ids"]
        assert population["sections"][note["section_id"]]["side"] == "operator_note"

    def test_a_parents_notes_sit_on_its_parts(self, store: Repository) -> None:
        from portal.modules.compliance.core.notes import write_note

        note = write_note(store, subject_ref="CIP-007-6 R2 Part 2.3", body="x", kind="decision")
        assert (
            note["section_id"] in requirement_scope.population(store, "CIP-007-6 R2")["section_ids"]
        )


class TestReadOrSayWhatYouDidNotRead:
    """The disclosure asks the reader to read what its answer depends on and to
    say plainly what it did not read and why. Three live Part 2.2 runs did
    exactly that — and were scored as having an undisclosed gap."""

    def _read(self, store: Repository, monkeypatch: pytest.MonkeyPatch, answer: str) -> dict:
        from portal.modules.compliance.core import reader, reading_transport

        monkeypatch.setattr(
            reading_transport,
            "_post",
            lambda payload, timeout: {
                "message": {"content": answer},
                "prompt_eval_count": 900,
                "eval_count": 40,
            },
        )
        return reader.read(
            store, "what do we do?", "CIP-007-6 R2 Part 2.2", model="stub", store=False
        )

    def test_the_unread_population_is_stated_to_the_reader(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import reader, reading_transport

        seen: dict = {}

        def _post(payload, timeout):  # noqa: ANN001, ANN202
            seen.setdefault("messages", payload["messages"])
            return {"message": {"content": "ok"}, "prompt_eval_count": 9, "eval_count": 2}

        monkeypatch.setattr(reading_transport, "_post", _post)
        reader.read(store, "q", "CIP-007-6 R2 Part 2.2", model="stub", store=False)
        blob = "\n".join(str(m.get("content", "")) for m in seen["messages"])
        assert "you have not read them" in blob
        assert "operator's OWN documents" in blob

    def test_a_named_omission_is_accounted_for(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = self._read(store, monkeypatch, "placeholder")
        unread = payload["closure_receipt"]["unread"]
        assert unread, "this fixture leaves something unread"
        declared = self._read(
            store,
            monkeypatch,
            f"I did not read {unread[0]} because its text is reproduced in the row I have. "
            f"There is no evidence of dated evaluations [{unread[0]}].",
        )
        closure = declared["closure_receipt"]
        assert closure["omitted_with_reason"] == [unread[0]]
        assert closure["undeclared_unread"] == []
        assert closure["accounted_for"] is True
        assert closure["complete"] is False, "a declared omission is not a full read"

    def test_an_undeclared_gap_still_bars_an_absence_claim(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import reader, reading_transport

        turns: list[int] = []

        def _post(payload, timeout):  # noqa: ANN001, ANN202
            turns.append(1)
            if len(turns) == 1:
                # a tool call, so the zero-tool rule is not what fires here
                return {
                    "message": {
                        "content": "",
                        "tool_calls": [{"function": {"name": "compliance_notes", "arguments": {}}}],
                    },
                    "prompt_eval_count": 9,
                    "eval_count": 2,
                }
            return {
                "message": {
                    "content": (
                        f"The requirement says this [{cited}]. There is no operator "
                        "procedure covering this at all."
                    )
                },
                "prompt_eval_count": 900,
                "eval_count": 40,
            }

        monkeypatch.setattr(reading_transport, "_post", _post)
        # cite one eligible section, so neither the zero-tool rule nor the
        # nothing-in-scope rule is what fires
        cited = requirement_scope.population(store, "CIP-007-6 R2 Part 2.2")["section_ids"][0]
        payload = reader.read(
            store, "what do we do?", "CIP-007-6 R2 Part 2.2", model="stub", store=False
        )
        assert payload["closure_receipt"]["model_tool_calls"] == 1
        assert payload["failed"] is True
        assert "neither read nor named" in payload["failure"]
