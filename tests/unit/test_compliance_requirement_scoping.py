"""Retrieval and closure scope by requirement identity (ONE_REGULATORY_EXTRACTION_V1 P4).

The point of the join is that a question about `CIP-007-6 R2 Part 2.2` can now
narrow the search to *that requirement's sections* BEFORE ranking, rather than
hoping the arms rank them first. So these tests assert the **candidate pool the
arms scored**, not merely the result count — a filter that runs after ranking
and a filter that runs before it produce the same count and completely different
evidence.

Two rules are load-bearing and are each pinned here. A relation narrows *which*
of a requirement's material is asked for and must never bar a passage from an
unscoped search (`capture.positional_role`'s rule). And an unanchored
requirement falls back to heading-path proximity **saying so** — an absence
claim resting on a guess has to be visibly weaker than one resting on the join.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import sys
import types
from pathlib import Path

import pytest

from portal.modules.compliance.core import requirement_anchor as ra
from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.models import SourceDocument
from portal.modules.compliance.core.repository import Repository

si = importlib.import_module("portal.modules.compliance.core.section_index")
compliance_mcp = importlib.import_module("portal.modules.compliance.tools.compliance_mcp")
cr = importlib.import_module("portal.modules.compliance.tools.compliance_retrieval")
_store = importlib.import_module("portal.platform.retrieval.store")
_embedding = importlib.import_module("portal.platform.retrieval.embedding")

DIM = 8

REQ_2_2 = (
    "At least once every 35 calendar days, evaluate security patches for "
    "applicability that have been released since the last evaluation."
)
MEASURE_2_2 = "An example of evidence may include an evaluation conducted by the entity."
REQ_2_3 = (
    "For applicable patches identified in Part 2.2, within 35 calendar days of the "
    "evaluation completion, apply the patch or create a dated mitigation plan."
)
SHARED = (
    "Both Part 2.2 and Part 2.3 rest on the same source identification duty "
    "established in Part 2.1 of this standard."
)

BODIES = [
    ("B. Requirements", f"2.2 | High Impact BES Cyber Systems | {REQ_2_2} | {MEASURE_2_2}"),
    ("B. Requirements", f"2.3 | High Impact BES Cyber Systems | {REQ_2_3} | An example."),
    ("Guidelines and Technical Basis", SHARED),
    ("Version History", "Version 5 revised under the RBS Template with no substantive change."),
]


def _vec(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    return [((digest[i] / 255.0) - 0.5) for i in range(DIM)]


async def _emb(text=None, image_path=None, is_query=False):
    return _vec(text or image_path or "")


async def _emb_batch(items):
    return [_vec(i.get("text") or i.get("image_path") or "") for i in items]


async def _rr(_q, cands, _n):
    return [{"index": i, "score": 1.0 - i * 0.1} for i in range(len(cands))]


async def _model_id():
    return ("fake-vl-model", DIM)


class _Node:
    def __init__(self, node_id: str, verbatim: str, measure: str = "") -> None:
        self.id = node_id
        self.verbatim_text = verbatim
        self.measure_text = measure
        self.applicable_systems = ""
        self.authority_tier = 0
        self.vrf = "Medium"
        self.time_horizon = "Operations Planning"
        self.lifecycle_state = "EFFECTIVE"


def _capture(path: Path) -> CapturedDocument:
    units, buf, cursor = [], [], 0
    for ordinal, (heading, body) in enumerate(BODIES):
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
        reader_strings=tuple(b for _h, b in BODIES),
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    pytest.importorskip("lancedb")
    monkeypatch.setattr(_store, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(_store, "RAG_DIR", str(tmp_path / "lance" / "rag"))
    monkeypatch.setattr(_embedding, "VL_DIM", DIM)
    monkeypatch.setattr(_embedding, "vl_embed", _emb)
    monkeypatch.setattr(_embedding, "vl_embed_batch", _emb_batch)
    monkeypatch.setattr(_embedding, "vl_rerank", _rr)
    monkeypatch.setattr(_embedding, "vl_model_id", _model_id)
    monkeypatch.setattr(cr, "_PAGES_DIR", tmp_path / "compliance_pages")
    _store._db = None
    fake = types.ModuleType("portal.modules.research.tools.rag_mcp")
    fake._read_file = lambda p: "body"
    monkeypatch.setitem(sys.modules, "portal.modules.research.tools.rag_mcp", fake)

    db_path = tmp_path / "store.db"
    repo = Repository(db_path)
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
    store_capture(repo, revision.revision_id, _capture(Path("/docs/cip-007-6.pdf")))

    # the join: 2.2 and 2.3 each anchor to their own row; the GTB passage names
    # both, so it is NOT joined to either by an exact anchor — that is the
    # honest outcome and the fallback tests rely on it.
    for node in (
        _Node("CIP-007-6 R2 Part 2.2", REQ_2_2, MEASURE_2_2),
        _Node("CIP-007-6 R2 Part 2.3", REQ_2_3),
    ):
        repo.record_anchors(ra.anchor_revision(repo, revision.revision_id, [node]))
    # one section deliberately bearing on TWO requirements, by hand: the GTB
    # passage is recorded as the technical basis of both.
    gtb = _section_at(repo, revision.revision_id, 2)
    for req in ("CIP-007-6 R2 Part 2.2", "CIP-007-6 R2 Part 2.3"):
        repo.record_anchors(
            [
                ra.Anchor(
                    requirement_id=req,
                    revision_id=revision.revision_id,
                    relation="technical_basis",
                    anchored=True,
                    char_start=0,
                    char_end=1,
                    section_ids=[gtb],
                    occurrences=1,
                )
            ]
        )

    plan = si.build_plan(repo, jurisdiction="US")
    asyncio.run(cr.project_sections(plan.kb_id, plan.units, rebuild=True))
    repo.close()

    def make():
        return Repository(db_path)

    monkeypatch.setattr(compliance_mcp, "_repo", make)
    return {"make": make, "revision_id": revision.revision_id}


def _section_at(repo: Repository, revision_id: str, ordinal: int) -> str:
    return str(
        repo._conn.execute(
            "SELECT section_id FROM source_sections WHERE revision_id = ? AND ordinal = ?",
            (revision_id, ordinal),
        ).fetchone()[0]
    )


def _ids(env, ordinal: int) -> str:
    repo = env["make"]()
    try:
        return _section_at(repo, env["revision_id"], ordinal)
    finally:
        repo.close()


# ── the pool the arms scored, not the count that came back ───────────────────
class TestRequirementNarrowsBeforeRanking:
    def test_requirement_returns_only_that_requirements_sections(self, env) -> None:
        out = compliance_mcp.compliance_search(
            query="security patches", requirement="CIP-007-6 R2 Part 2.2", top_k=10
        )
        assert out["requirement"] == "CIP-007-6 R2 Part 2.2"
        assert out["requirement_pool"] == [_ids(env, 0)]
        assert {r["section_id"] for r in out["results"]} <= {_ids(env, 0)}

    def test_the_predicate_pushed_is_an_exact_id_list_not_a_like(self, env) -> None:
        out = compliance_mcp.compliance_search(
            query="security patches", requirement="CIP-007-6 R2 Part 2.2", top_k=10
        )
        assert f"chunk_id IN ('{_ids(env, 0)}')" in out["filter_applied"]
        assert "LIKE" not in out["filter_applied"].replace("logical_id", "")

    def test_a_requirement_prefix_does_not_drag_in_its_parts(self, env) -> None:
        # 'CIP-007-6 R2' is a substring of 'CIP-007-6 R2 Part 2.2'. A LIKE
        # predicate would match both; an exact id list matches neither wrongly.
        out = compliance_mcp.compliance_search(
            query="security patches", requirement="CIP-007-6 R2", top_k=10
        )
        assert out["signal"] == "honest-BLOCKED"
        assert out["results"] == []

    def test_the_pool_shrinks_when_the_requirement_is_given(self, env) -> None:
        wide = compliance_mcp.compliance_search(query="security patches", top_k=10)
        narrow = compliance_mcp.compliance_search(
            query="security patches", requirement="CIP-007-6 R2 Part 2.2", top_k=10
        )
        assert narrow["requirement_pool"] == [_ids(env, 0)]
        assert len(narrow["results"]) < len(wide["results"])

    def test_every_hit_carries_what_it_governs_and_how(self, env, monkeypatch) -> None:
        node = _Node("CIP-007-6 R2 Part 2.2", REQ_2_2, MEASURE_2_2)
        node.applicable_systems = "High Impact BES Cyber Systems"
        monkeypatch.setattr(
            "portal.modules.compliance.core.cip_register.node_index", lambda *_a: {node.id: node}
        )
        out = compliance_mcp.compliance_search(
            query="security patches", requirement="CIP-007-6 R2 Part 2.2", top_k=10
        )
        hit = out["results"][0]
        assert hit["requirement_id"] == "CIP-007-6 R2 Part 2.2"
        assert hit["vrf"] == "Medium"
        assert hit["time_horizon"] == "Operations Planning"
        assert hit["applicable_systems"] == "High Impact BES Cyber Systems"
        assert "governing" in hit["relations"]


# ── relations narrow; they never bar ─────────────────────────────────────────
class TestRelationsNarrowNeverBar:
    def test_governing_and_the_full_set_return_different_populations(self, env) -> None:
        duty = compliance_mcp.compliance_search(
            query="patches", requirement="CIP-007-6 R2 Part 2.2", relations="governing", top_k=10
        )
        whole = compliance_mcp.compliance_search(
            query="patches",
            requirement="CIP-007-6 R2 Part 2.2",
            relations="governing,measure,applicable_systems,technical_basis",
            top_k=10,
        )
        assert duty["requirement_pool"] == [_ids(env, 0)]
        assert set(whole["requirement_pool"]) == {_ids(env, 0), _ids(env, 2)}
        assert set(duty["requirement_pool"]) < set(whole["requirement_pool"])

    def test_a_relation_never_bars_a_passage_from_an_unscoped_search(self, env) -> None:
        # the GTB passage bears only `technical_basis`. An unscoped search must
        # still be able to return it — the relation narrows, it never excludes.
        out = compliance_mcp.compliance_search(query=SHARED, top_k=10)
        assert _ids(env, 2) in {r["section_id"] for r in out["results"]}
        assert out["requirement_pool"] == []

    def test_a_section_bearing_on_two_requirements_is_found_by_both(self, env) -> None:
        shared = _ids(env, 2)
        for req in ("CIP-007-6 R2 Part 2.2", "CIP-007-6 R2 Part 2.3"):
            out = compliance_mcp.compliance_search(
                query="patches", requirement=req, relations="technical_basis", top_k=10
            )
            assert out["requirement_pool"] == [shared]
        repo = env["make"]()
        try:
            pairs = repo.requirements_for_section(shared)
        finally:
            repo.close()
        assert sorted({rid for rid, _rel in pairs}) == [
            "CIP-007-6 R2 Part 2.2",
            "CIP-007-6 R2 Part 2.3",
        ]


# ── honest-BLOCKED rather than a search that only looks filtered ─────────────
class TestTheCeilingAndTheBlock:
    def test_an_unanchored_requirement_is_blocked_with_its_recorded_reason(self, env) -> None:
        repo = env["make"]()
        try:
            repo.record_anchors(
                [
                    ra.Anchor(
                        requirement_id="CIP-007-6 R9 Part 9.9",
                        revision_id=env["revision_id"],
                        relation="governing",
                        anchored=False,
                        reason="text does not occur in the captured revision",
                    )
                ]
            )
        finally:
            repo.close()
        out = compliance_mcp.compliance_search(
            query="patches", requirement="CIP-007-6 R9 Part 9.9", top_k=10
        )
        assert out["signal"] == "honest-BLOCKED"
        assert "UNANCHORED" in out["detail"] or "text does not occur" in out["detail"]
        assert out["results"] == []

    def test_a_list_above_the_measured_ceiling_is_blocked_with_the_count(
        self, env, monkeypatch
    ) -> None:
        monkeypatch.setattr(compliance_mcp, "MAX_REQUIREMENT_SECTION_IDS", 0)
        out = compliance_mcp.compliance_search(
            query="patches", requirement="CIP-007-6 R2 Part 2.2", top_k=10
        )
        assert out["signal"] == "honest-BLOCKED"
        assert out["section_count"] == 1
        assert out["ceiling"] == 0
        assert out["results"] == [], "never a silent fallback to an unfiltered search"

    def test_the_block_names_a_narrower_requirement_as_the_way_out(self, env, monkeypatch) -> None:
        monkeypatch.setattr(compliance_mcp, "MAX_REQUIREMENT_SECTION_IDS", 0)
        out = compliance_mcp.compliance_search(
            query="patches", requirement="CIP-007-6 R2 Part 2.2", top_k=10
        )
        assert "narrower requirement" in out["detail"]


# ── the closure population comes from the join, fallback is NAMED ────────────
class TestClosurePopulation:
    def test_an_anchored_requirement_reports_the_join(self, env) -> None:
        from portal.modules.compliance.core import enumeration

        repo = env["make"]()
        try:
            population = enumeration.population_for_requirement(
                repo, "CIP-007-6 R2 Part 2.2", relations=("governing", "measure")
            )
        finally:
            repo.close()
        assert population["population_method"] == "join"
        assert population["section_ids"] == [_ids(env, 0)]

    def test_the_full_relation_set_is_the_union_of_its_relations(self, env) -> None:
        from portal.modules.compliance.core import enumeration

        repo = env["make"]()
        try:
            whole = enumeration.population_for_requirement(repo, "CIP-007-6 R2 Part 2.2")
            parts: set[str] = set()
            for relation in enumeration.ALL_RELATIONS:
                parts |= set(
                    enumeration.population_for_requirement(
                        repo, "CIP-007-6 R2 Part 2.2", relations=(relation,)
                    )["section_ids"]
                )
        finally:
            repo.close()
        assert set(whole["section_ids"]) == parts
        assert parts == {_ids(env, 0), _ids(env, 2)}

    def test_an_unanchored_requirement_falls_back_and_says_so(self, env) -> None:
        from portal.modules.compliance.core import enumeration

        repo = env["make"]()
        try:
            population = enumeration.population_for_requirement(
                repo,
                "CIP-007-6 R4 Part 4.1",
                proximity_fallback=lambda: [{"section_id": _ids(env, 3)}],
            )
        finally:
            repo.close()
        assert population["population_method"] == "proximity"
        assert "weaker basis than the join" in population["detail"]
        assert population["section_ids"] == [_ids(env, 3)]

    def test_the_reading_assembly_reports_which_derivation_it_used(self, env) -> None:
        from portal.modules.compliance.core import reading_assembly

        repo = env["make"]()
        try:
            joined = reading_assembly.assemble(repo, "CIP-007-6 R2 Part 2.2")
            guessed = reading_assembly.assemble(repo, "CIP-007-6 R4 Part 4.1")
        finally:
            repo.close()
        assert joined["population_method"] == "join"
        assert guessed["population_method"] == "proximity"
        assert "weaker basis" in guessed["population_detail"]
