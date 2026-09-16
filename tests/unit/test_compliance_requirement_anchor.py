"""The requirement → section join (ONE_REGULATORY_EXTRACTION_V1 P1/P2).

The defect these tests pin is an ABSENCE: `RegisterNode` carried no
`section_id`, `source_sections` carried no requirement reference, and the only
overlap was `source_pdf` + `source_pages` — page granularity, where a page holds
many sections and a Part spans pages. So "the sections constituting R2 Part 2.2"
was not a question the store could answer.

Two things must hold for the fix to be worth having. The anchor must be **exact**
— a fuzzy join produces citations that look correct, cannot be checked
afterwards, and get built on — and it must leave the capture **untouched**,
because `assert_faithful` raises on overlapping spans and a `table_row` already
carries the requirement text, the applicable-systems column and the Measures
column as one unit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.compliance.core import requirement_anchor as ra
from portal.modules.compliance.core import section_index as si
from portal.modules.compliance.core.capture import (
    CapturedDocument,
    CapturedUnit,
    assert_faithful,
    store_capture,
)
from portal.modules.compliance.core.models import SourceDocument
from portal.modules.compliance.core.repository import Repository

# ── the synthetic revision ───────────────────────────────────────────────────
# Three prose units and one table_row. The table_row's text is the `" | "`-join
# of its cells exactly as a real capture writes it, so the "one section, three
# relations" case is the real shape and not a convenience.

REQ_2_2 = (
    "At least once every 35 calendar days, evaluate security patches for "
    "applicability that have been released since the last evaluation."
)
SYSTEMS_2_2 = "High Impact BES Cyber Systems and their associated EACMS, PACS and PCA"
MEASURE_2_2 = "An example of evidence may include an evaluation conducted on behalf of the entity."
ROW_2_2 = f"2.2 | {SYSTEMS_2_2} | {REQ_2_2} | {MEASURE_2_2}"

SPANNING_HEAD = "Where technically feasible, limit the number of unsuccessful attempts"
SPANNING_TAIL = "and generate alerts after a threshold is crossed by any account."

BODIES: list[tuple[str, str, str]] = [
    ("A. Introduction", "prose", "This standard is CIP-007-6, Cyber Security Systems Security."),
    ("B. Requirements", "table_row", ROW_2_2),
    ("B. Requirements", "prose", SPANNING_HEAD),
    ("B. Requirements", "prose", SPANNING_TAIL),
    (
        "Guidelines and Technical Basis",
        "prose",
        f"The intent of Part 2.2 is as follows. {REQ_2_2} This is not an "
        "install-every-patch obligation.",
    ),
    ("Version History", "prose", "Version 5 revised under the RBS Template with no change."),
]


class _Node:
    """The shape `anchor_revision` reads off a `RegisterNode`, without dragging
    the whole register file into a unit test."""

    def __init__(
        self, node_id: str, verbatim: str, measure: str = "", systems: str = "", tier: int = 0
    ) -> None:
        self.id = node_id
        self.verbatim_text = verbatim
        self.measure_text = measure
        self.applicable_systems = systems
        self.authority_tier = tier
        self.vrf = "Medium"
        self.time_horizon = "Operations Planning"
        self.lifecycle_state = "EFFECTIVE"


def _capture(path: Path, bodies: list[tuple[str, str, str]]) -> CapturedDocument:
    units: list[CapturedUnit] = []
    buf: list[str] = []
    cursor = 0
    for ordinal, (heading, kind, body) in enumerate(bodies):
        piece = body + "\n"
        cells = body.split(" | ") if kind == "table_row" else []
        units.append(
            CapturedUnit(
                ordinal=ordinal,
                unit_kind=kind,
                heading_path=heading,
                title=heading,
                page_start=1,
                page_end=1,
                char_start=cursor,
                char_end=cursor + len(piece),
                text=piece,
                table_ref="#/tables/0" if kind == "table_row" else "",
                row_index=0 if kind == "table_row" else -1,
                columns=["Part", "Applicable Systems", "Requirements", "Measures"] if cells else [],
                cells=cells,
            )
        )
        buf.append(piece)
        cursor += len(piece)
    return CapturedDocument(
        path=path,
        page_count=1,
        full_text="".join(buf),
        units=units,
        reader_strings=tuple(b for _h, _k, b in bodies),
    )


@pytest.fixture
def store(tmp_path: Path):
    repo = Repository(tmp_path / "store.db")
    repo.upsert_source_document(
        SourceDocument(
            logical_id="NERC/CIP-007-6",
            title="CIP-007-6",
            issuer="NERC",
            source_kind="regulatory_standard",
            jurisdiction="US",
        )
    )
    revision = repo.add_document_revision("NERC/CIP-007-6", "/docs/cip-007-6.pdf", b"cip-007-6")
    store_capture(repo, revision.revision_id, _capture(Path("/docs/cip-007-6.pdf"), BODIES))
    repo.revision_id = revision.revision_id  # type: ignore[attr-defined]
    yield repo
    repo.close()


def _section_at(repo: Repository, ordinal: int) -> str:
    row = repo._conn.execute(
        "SELECT section_id FROM source_sections WHERE revision_id = ? AND ordinal = ?",
        (repo.revision_id, ordinal),
    ).fetchone()
    return str(row[0])


def _anchor(repo: Repository, node: _Node) -> list[ra.Anchor]:
    return ra.anchor_revision(repo, repo.revision_id, [node])


# ── the located range is the requirement's sections ──────────────────────────
class TestTheAnchorLocates:
    def test_a_requirement_anchors_to_exactly_its_own_section(self, store: Repository) -> None:
        anchors = _anchor(store, _Node("CIP-007-6 R2 Part 2.2", REQ_2_2))
        governing = next(a for a in anchors if a.relation == "governing")
        assert governing.anchored
        # the table_row, and not the introduction beside it
        assert governing.section_ids == [_section_at(store, 1)]

    def test_text_spanning_a_section_boundary_anchors_to_both_in_order(
        self, store: Repository
    ) -> None:
        anchors = _anchor(store, _Node("CIP-007-6 R5 Part 5.7", f"{SPANNING_HEAD} {SPANNING_TAIL}"))
        governing = next(a for a in anchors if a.relation == "governing")
        assert governing.anchored
        assert governing.section_ids == [_section_at(store, 2), _section_at(store, 3)]

    def test_recurring_text_takes_the_first_occurrence_and_records_the_count(
        self, store: Repository
    ) -> None:
        # REQ_2_2 appears in the requirements table AND quoted in the Guidelines.
        anchors = _anchor(store, _Node("CIP-007-6 R2 Part 2.2", REQ_2_2))
        governing = next(a for a in anchors if a.relation == "governing")
        assert governing.occurrences == 2
        assert governing.section_ids == [_section_at(store, 1)], "the table row precedes the GTB"

    def test_to_original_round_trips_into_the_captured_space(self, store: Repository) -> None:
        full = store.get_document_text(store.revision_id) or ""
        offsets = ra.OffsetMap.build(full)
        start, end, _count, reason = ra.locate(REQ_2_2, offsets)
        assert reason == ""
        assert ra.normalise(full[start:end]) == ra.normalise(REQ_2_2)


# ── a miss is named, never approximated ──────────────────────────────────────
class TestAMissIsNamed:
    def test_absent_text_writes_a_miss_and_no_join_row(self, store: Repository) -> None:
        node = _Node("CIP-007-6 R9 Part 9.9", "This sentence is nowhere in the captured revision.")
        store.record_anchors(_anchor(store, node))
        assert store.sections_for_requirement("CIP-007-6 R9 Part 9.9") == []
        misses = store.anchor_misses(revision_id=store.revision_id)
        assert [m["requirement_id"] for m in misses] == ["CIP-007-6 R9 Part 9.9"]
        assert misses[0]["reason"] == "text does not occur in the captured revision"

    def test_text_under_the_floor_is_refused_with_the_stated_reason(
        self, store: Repository
    ) -> None:
        offsets = ra.OffsetMap.build(store.get_document_text(store.revision_id) or "")
        short = "This standard is"
        assert len(short) < ra.MIN_ANCHOR_CHARS
        start, _end, _count, reason = ra.locate(short, offsets)
        assert start == -1
        assert reason == f"text too short to anchor safely ({len(short)} chars)"

    def test_the_report_names_every_miss_per_relation(self, store: Repository) -> None:
        anchors = [
            *_anchor(store, _Node("CIP-007-6 R2 Part 2.2", REQ_2_2, MEASURE_2_2, SYSTEMS_2_2)),
            *_anchor(store, _Node("CIP-007-6 R9 Part 9.9", "Absent from the captured revision.")),
        ]
        report = ra.anchor_report(anchors)
        assert report["by_relation"]["governing"]["attempted"] == 2
        assert report["by_relation"]["governing"]["rate"] == 0.5
        assert report["signal"] == ra.UNANCHORED
        named = [u["requirement_id"] for u in report["by_relation"]["governing"]["unanchored"]]
        assert named == ["CIP-007-6 R9 Part 9.9"]


# ── the licensed substitutions, and only those ───────────────────────────────
class TestNormalisationIsLicensedOnly:
    @pytest.mark.parametrize(
        "rendered",
        [
            "A dated mitigation plan – the entity’s planned actions — and a timeframe",
            "A dated mitigation plan - the entity's planned actions - and a timeframe",
            "A dated mitigation plan - the entity's planned actions - and a timeframe",
            "A dated miti­gation plan - the entity's planned actions - and a timeframe",
        ],
    )
    def test_a_rendering_difference_still_anchors(self, rendered: str) -> None:
        canonical = "A dated mitigation plan - the entity's planned actions - and a timeframe"
        assert ra.normalise(rendered) == ra.normalise(canonical)

    def test_the_pua_bullet_reconciles_with_the_hyphen_pymupdf_renders(self) -> None:
        captured = "take one of the following actions:  Apply the applicable patches"
        register = "take one of the following actions: - Apply the applicable patches"
        assert ra.normalise(captured) == ra.normalise(register)

    def test_the_two_readers_quote_marks_fold_to_one_form(self) -> None:
        # the same glyph in the PDF: pymupdf gives U+201C/U+201D, docling ASCII "'"
        register = "systems identified in the \u201cApplicable Systems\u201d column"
        captured = "systems identified in the 'Applicable Systems' column"
        assert ra.normalise(register) == ra.normalise(captured)

    def test_a_list_bullet_the_capture_folded_into_structure_is_dropped(self) -> None:
        # docling makes the unit a list_item and drops the marker glyph
        register = "shall be performed: \u2022 At least once every 30 calendar months"
        captured = "shall be performed: At least once every 30 calendar months"
        assert ra.normalise(register) == ra.normalise(captured)

    def test_the_ligature_is_licensed(self) -> None:
        assert ra.normalise("conﬁrm the conﬂict") == ra.normalise("confirm the conflict")

    def test_an_unlicensed_difference_does_not_anchor(self, store: Repository) -> None:
        # one word changed. Meaning-bearing, so it must NOT be reconciled away.
        altered = REQ_2_2.replace("35 calendar days", "45 calendar days")
        anchors = _anchor(store, _Node("CIP-007-6 R2 Part 2.2", altered))
        assert not next(a for a in anchors if a.relation == "governing").anchored

    def test_case_is_not_licensed(self, store: Repository) -> None:
        anchors = _anchor(store, _Node("CIP-007-6 R2 Part 2.2", REQ_2_2.upper()))
        assert not next(a for a in anchors if a.relation == "governing").anchored


# ── one section, three relations ─────────────────────────────────────────────
class TestOneRowBearsThreeRelations:
    def test_a_joined_table_row_yields_three_rows_for_one_section(self, store: Repository) -> None:
        node = _Node("CIP-007-6 R2 Part 2.2", REQ_2_2, MEASURE_2_2, SYSTEMS_2_2)
        result = store.record_anchors(_anchor(store, node))
        assert result["misses"] == 0
        assert result["sections_joined"] == 3, "three relations onto the one table_row"
        section_id = _section_at(store, 1)
        pairs = store.requirements_for_section(section_id)
        assert sorted(rel for _rid, rel in pairs) == [
            "applicable_systems",
            "governing",
            "measure",
        ]
        assert {rid for rid, _rel in pairs} == {"CIP-007-6 R2 Part 2.2"}

    def test_the_primary_key_accepts_all_three_and_is_idempotent(self, store: Repository) -> None:
        node = _Node("CIP-007-6 R2 Part 2.2", REQ_2_2, MEASURE_2_2, SYSTEMS_2_2)
        store.record_anchors(_anchor(store, node))
        store.record_anchors(_anchor(store, node))
        count = store._conn.execute("SELECT COUNT(*) FROM requirement_sections").fetchone()[0]
        assert count == 3


# ── the two primitives are inverses ──────────────────────────────────────────
class TestTheRetrievalPrimitives:
    @pytest.fixture(autouse=True)
    def _joined(self, store: Repository):
        store.record_anchors(
            _anchor(store, _Node("CIP-007-6 R2 Part 2.2", REQ_2_2, MEASURE_2_2, SYSTEMS_2_2))
        )
        store.record_anchors(
            _anchor(store, _Node("CIP-007-6 R5 Part 5.7", f"{SPANNING_HEAD} {SPANNING_TAIL}"))
        )

    def test_relations_narrows_the_population(self, store: Repository) -> None:
        duty = store.sections_for_requirement("CIP-007-6 R2 Part 2.2")
        assert [r["relation"] for r in duty] == ["governing"]
        whole = store.sections_for_requirement(
            "CIP-007-6 R2 Part 2.2",
            relations=("governing", "measure", "applicable_systems", "technical_basis"),
        )
        assert sorted(r["relation"] for r in whole) == [
            "applicable_systems",
            "governing",
            "measure",
        ]

    def test_sections_come_back_in_reading_order(self, store: Repository) -> None:
        rows = store.sections_for_requirement("CIP-007-6 R5 Part 5.7")
        assert [r["section_id"] for r in rows] == [_section_at(store, 2), _section_at(store, 3)]
        assert [r["ordinal"] for r in rows] == [2, 3]

    def test_requirements_for_section_is_the_exact_inverse(self, store: Repository) -> None:
        forward = {
            (r["section_id"], r["relation"])
            for rid in ("CIP-007-6 R2 Part 2.2", "CIP-007-6 R5 Part 5.7")
            for r in store.sections_for_requirement(rid, relations=ra.RELATIONS)
        }
        backward = {
            (section_id, rel)
            for section_id in {s for s, _ in forward}
            for _rid, rel in store.requirements_for_section(section_id)
        }
        assert forward == backward

    def test_a_section_bearing_on_no_requirement_has_no_inverse(self, store: Repository) -> None:
        assert store.requirements_for_section(_section_at(store, 5)) == []

    def test_an_unknown_requirement_resolves_to_nothing_rather_than_everything(
        self, store: Repository
    ) -> None:
        assert store.sections_for_requirement("CIP-999-1 R1") == []
        assert store.sections_for_requirement("") == []


# ── the capture is never edited ──────────────────────────────────────────────
class TestTheCaptureIsUntouched:
    def test_no_source_section_row_is_created_and_fidelity_still_holds(
        self, store: Repository
    ) -> None:
        before = store._conn.execute("SELECT COUNT(*) FROM source_sections").fetchone()[0]
        node = _Node("CIP-007-6 R2 Part 2.2", REQ_2_2, MEASURE_2_2, SYSTEMS_2_2)
        store.record_anchors(_anchor(store, node))
        after = store._conn.execute("SELECT COUNT(*) FROM source_sections").fetchone()[0]
        assert after == before
        # and the capture the join points into is still faithful: assert_faithful
        # RAISES on an overlap, which is exactly why the join is its own table.
        report = assert_faithful(_capture(Path("/docs/cip-007-6.pdf"), BODIES))
        assert report["character_coverage_pct"] == 100.0
        assert report["gaps"] == [] and report["overlaps"] == []
        assert report["reconstruction_diff"] == ""


# ── Measures and the Technical Basis, through the join (P5) ─────────────────
class _Bundle:
    """The shape `anchor_bundle_spans` reads off a `RevisionBundle`. Duck-typed
    on purpose — `requirement_anchor` stays free of `regulatory_bundle`, which
    re-parses PDFs at call time."""

    def __init__(self, **kw: object) -> None:
        self.technical_basis: dict = kw.get("technical_basis", {})  # type: ignore[assignment]
        self.technical_basis_parts: dict = kw.get("technical_basis_parts", {})  # type: ignore[assignment]
        self.technical_basis_rationale: dict = kw.get("technical_basis_rationale", {})  # type: ignore[assignment]
        self.measures_leadins: dict = kw.get("measures_leadins", {})  # type: ignore[assignment]
        self.technical_basis_section = "present"


class _Span:
    def __init__(self, text: str) -> None:
        self.text = text
        self.role = "TECHNICAL_BASIS"


GTB_TEXT = BODIES[4][2]


class TestTheTechnicalBasisIsReachableThroughTheJoin:
    def _nodes(self) -> list[_Node]:
        node = _Node("CIP-007-6 R2 Part 2.2", REQ_2_2, MEASURE_2_2, SYSTEMS_2_2)
        node.requirement, node.part = "R2", "2.2"  # type: ignore[attr-defined]
        return [node]

    def test_a_gtb_span_resolves_in_both_directions(self, store: Repository) -> None:
        bundle = _Bundle(technical_basis={"R2": [_Span(GTB_TEXT)]})
        anchors = ra.anchor_bundle_spans(store, store.revision_id, bundle, self._nodes())
        store.record_anchors(anchors)
        gtb = _section_at(store, 4)
        rows = store.sections_for_requirement(
            "CIP-007-6 R2 Part 2.2", relations=("technical_basis",)
        )
        assert [r["section_id"] for r in rows] == [gtb]
        assert ("CIP-007-6 R2 Part 2.2", "technical_basis") in store.requirements_for_section(gtb)

    def test_a_per_part_span_attaches_to_that_part(self, store: Repository) -> None:
        bundle = _Bundle(technical_basis_parts={"R2 Part 2.2": [_Span(GTB_TEXT)]})
        store.record_anchors(
            ra.anchor_bundle_spans(store, store.revision_id, bundle, self._nodes())
        )
        rows = store.sections_for_requirement(
            "CIP-007-6 R2 Part 2.2", relations=("technical_basis",)
        )
        assert [r["section_id"] for r in rows] == [_section_at(store, 4)]

    def test_no_source_section_row_is_created_by_the_annotation(self, store: Repository) -> None:
        before = store._conn.execute("SELECT COUNT(*) FROM source_sections").fetchone()[0]
        bundle = _Bundle(
            technical_basis={"R2": [_Span(GTB_TEXT)]},
            measures_leadins={"R2": MEASURE_2_2},
        )
        store.record_anchors(
            ra.anchor_bundle_spans(store, store.revision_id, bundle, self._nodes())
        )
        after = store._conn.execute("SELECT COUNT(*) FROM source_sections").fetchone()[0]
        assert after == before
        report = assert_faithful(_capture(Path("/docs/cip-007-6.pdf"), BODIES))
        assert report["overlaps"] == [] and report["reconstruction_diff"] == ""

    def test_a_relation_narrows_but_the_gtb_stays_reachable_unscoped(
        self, store: Repository
    ) -> None:
        bundle = _Bundle(technical_basis={"R2": [_Span(GTB_TEXT)]})
        store.record_anchors(
            ra.anchor_bundle_spans(store, store.revision_id, bundle, self._nodes())
        )
        gtb = _section_at(store, 4)
        duty = store.sections_for_requirement("CIP-007-6 R2 Part 2.2")
        assert gtb not in {r["section_id"] for r in duty}, "the relation narrows"
        # ...and the passage is still a passage: it resolves, with its text, and
        # nothing about the relation removes it from the store.
        entry = si.resolve_sections(store, [gtb])[gtb]
        assert entry["resolvable"] and entry["text"].strip()
        assert entry["relations"] == ["technical_basis"]

    def test_a_span_absent_from_the_capture_is_simply_not_joined(self, store: Repository) -> None:
        bundle = _Bundle(technical_basis={"R2": [_Span("A paragraph the capture does not hold.")]})
        anchors = ra.anchor_bundle_spans(store, store.revision_id, bundle, self._nodes())
        assert anchors == [], "never approximated to the nearest section"

    def test_a_requirement_level_span_reaches_every_part_of_that_requirement(
        self, store: Repository
    ) -> None:
        other = _Node("CIP-007-6 R2 Part 2.3", REQ_2_2)
        other.requirement, other.part = "R2", "2.3"  # type: ignore[attr-defined]
        nodes = [*self._nodes(), other]
        bundle = _Bundle(technical_basis={"R2": [_Span(GTB_TEXT)]})
        store.record_anchors(ra.anchor_bundle_spans(store, store.revision_id, bundle, nodes))
        gtb = _section_at(store, 4)
        assert sorted(r for r, rel in store.requirements_for_section(gtb)) == [
            "CIP-007-6 R2 Part 2.2",
            "CIP-007-6 R2 Part 2.3",
        ]

    def test_a_measures_leadin_is_the_statement_not_the_table_it_runs_into(self) -> None:
        # regulatory_bundle bounds a lead-in at the NEXT region, so the span
        # continues through the whole requirements table. Attaching all of it to
        # every Part would join 2.1's Measures cell to 2.4.
        leadin = (
            "Evidence must include each of the applicable documented processes. "
            "CIP-007-6 Table R2 Part Applicable Systems Requirements Measures 2.1 High Impact"
        )
        assert ra._leadin_statement(leadin) == (
            "Evidence must include each of the applicable documented processes."
        )


# ── Register facts ride in on the join ───────────────────────────────────────
class TestRegisterFactsRideOnTheJoin:
    def test_a_governing_join_carries_the_requirements_facts(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        node = _Node("CIP-007-6 R2 Part 2.2", REQ_2_2, MEASURE_2_2, SYSTEMS_2_2)
        monkeypatch.setattr(
            "portal.modules.compliance.core.cip_register.node_index", lambda *_a: {node.id: node}
        )
        store.record_anchors(_anchor(store, node))
        entry = si.resolve_sections(store, [_section_at(store, 1)])[_section_at(store, 1)]
        assert entry["requirement_id"] == "CIP-007-6 R2 Part 2.2"
        assert entry["vrf"] == "Medium"
        assert entry["time_horizon"] == "Operations Planning"
        assert entry["applicable_systems"] == SYSTEMS_2_2
        assert entry["lifecycle_state"] == "EFFECTIVE"
        assert sorted(entry["relations"]) == ["applicable_systems", "governing", "measure"]

    def test_a_section_with_no_join_acquires_no_blank_facts(self, store: Repository) -> None:
        entry = si.resolve_sections(store, [_section_at(store, 5)])[_section_at(store, 5)]
        assert entry["requirement_ids"] == []
        assert "requirement_id" not in entry
        assert "vrf" not in entry

    def test_a_tier_disagreement_is_reported_not_resolved(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        node = _Node("CIP-007-6 R2 Part 2.2", REQ_2_2, tier=4)
        monkeypatch.setattr(
            "portal.modules.compliance.core.cip_register.node_index", lambda *_a: {node.id: node}
        )
        monkeypatch.setattr(si, "recorded_tier", lambda *_a, **_k: "0", raising=False)
        monkeypatch.setattr(
            "portal.modules.compliance.core.tiers.recorded_tier", lambda *_a, **_k: "0"
        )
        store.record_anchors(_anchor(store, node))
        entry = si.resolve_sections(store, [_section_at(store, 1)])[_section_at(store, 1)]
        assert entry["authority_tier"] == "0", "the projected value is not overwritten"
        assert entry["register_authority_tier"] == "4", "and neither is the register's"
        assert "register says tier 4" in entry["authority_tier_disagreement"]
