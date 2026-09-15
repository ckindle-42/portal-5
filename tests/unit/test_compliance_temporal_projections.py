"""END_TO_END Phase 5 — both clocks operational + projection fingerprints.

Under test: two-clock selection of governing revisions (late-recorded facts,
corrected effectivity, future revisions, replay before/after a correction),
the valid_at/known_at predicates on relationship traversal (trace/impact),
and canonical-fingerprint projection manifests that detect staleness (L14).
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core import projections
from portal.modules.compliance.core.impact import analyze as impact_analyze
from portal.modules.compliance.core.models import RelationshipAssertion, SourceDocument
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.temporal import now_iso
from portal.modules.compliance.core.temporal_selection import (
    select_revision_effectivity,
    store_nodes_for_revisions,
    withhold_unknown_knowledge,
)
from portal.modules.compliance.core.traceability import trace


@pytest.fixture
def repo(tmp_path):
    r = Repository(tmp_path / "store.db")
    yield r
    r.close()


def _family_nodes(repo: Repository, *, recorded_from: str, recorded_to: str | None = None):
    """Two revisions of one family with sourced effectivity: version 6
    effective 2016-07-01→2028-06-30 and version 7.1 effective 2028-07-01,
    both recorded at ``recorded_from`` (the late-recorded shape: the effectivity
    start predates its recording by years)."""
    conn = repo._conn
    with repo._lock, conn:
        for version, revision_id in (("6", "rev-6"), ("7.1", "rev-71")):
            conn.execute(
                "INSERT OR IGNORE INTO standard_revisions(revision_id, logical_id, family, version) VALUES (?,?,?,?)",
                (revision_id, f"logical-{version}", "CIP-007", version),
            )
            for part in ("R1 Part 1.1", "R2 Part 2.1"):
                node_id = f"CIP-007-{version} {part}"
                conn.execute(
                    "INSERT OR IGNORE INTO requirement_nodes(node_id, standard_revision_id, requirement, part) VALUES (?,?,?,?)",
                    (node_id, revision_id, part.split(" Part ")[0], part.split(" Part ")[1]),
                )
                v_from, v_to = (
                    ("2016-07-01", "2028-06-30") if version == "6" else ("2028-07-01", None)
                )
                conn.execute(
                    """INSERT INTO effectivity_assertions(assertion_id, node_id, valid_from,
                           valid_to, recorded_from, recorded_to, approval_status)
                       VALUES (?,?,?,?,?,?, 'verified')""",
                    (f"ea-{node_id}", node_id, v_from, v_to, recorded_from, recorded_to),
                )


class TestSelectRevisionEffectivity:
    def test_current_selection(self, repo):
        _family_nodes(repo, recorded_from="2026-09-15T11:42:05+00:00")
        selection = select_revision_effectivity(repo._conn, family="CIP-007", valid_at="2026-09-14")
        assert [rev["version"] for rev in selection["selected"]] == ["6"]
        # the known future revision is disclosed, never merged into selected
        assert [rev["version"] for rev in selection["future"]] == ["7.1"]
        repo.close()

    def test_future_revision_is_future_not_current(self, repo):
        _family_nodes(repo, recorded_from="2026-09-15T11:42:05+00:00")
        selection = select_revision_effectivity(repo._conn, family="CIP-007", valid_at="2028-08-01")
        assert [rev["version"] for rev in selection["selected"]] == ["7.1"]
        retired = [rev["version"] for rev in selection["historical"]]
        assert retired == ["6"]
        repo.close()

    def test_historical_valid_at_selects_the_historical_revision(self, repo):
        _family_nodes(repo, recorded_from="2026-09-15T11:42:05+00:00")
        selection = select_revision_effectivity(repo._conn, family="CIP-007", valid_at="2020-01-01")
        assert [rev["version"] for rev in selection["selected"]] == ["6"]
        repo.close()

    def test_late_recorded_fact_is_unknown_knowledge_before_recording(self, repo):
        """The effectivity was true since 2016 but only recorded 2026-09-15:
        a query 'as known 2026-09-01' must NOT claim the knowledge."""
        _family_nodes(repo, recorded_from="2026-09-15T11:42:05+00:00")
        before = select_revision_effectivity(
            repo._conn, family="CIP-007", valid_at="2020-01-01", known_at="2026-09-01"
        )
        assert before["selected"] == []
        assert "6" in [rev["version"] for rev in before["unknown_knowledge"]]
        # ... and the same valid_at after recording selects normally
        after = select_revision_effectivity(
            repo._conn, family="CIP-007", valid_at="2020-01-01", known_at="2026-09-16"
        )
        assert [rev["version"] for rev in after["selected"]] == ["6"]
        assert after["unknown_knowledge"] == []
        repo.close()

    def test_corrected_effectivity_replays_before_and_after(self, repo):
        """A correction closes the prior row's recorded_to and adds a new
        row: replay before the correction sees the old fact, after sees the
        correction, and neither mutates."""
        _family_nodes(repo, recorded_from="2026-09-15T11:42:05+00:00")
        conn = repo._conn
        with repo._lock, conn:
            # correction on 2026-09-20: version 7.1 is NOT effective 2028-07-01
            # after all — moved to 2029-07-01
            conn.execute(
                "UPDATE effectivity_assertions SET recorded_to = ? WHERE node_id LIKE 'CIP-007-7.1%'",
                ("2026-09-20T00:00:00+00:00",),
            )
            for part in ("R1 Part 1.1", "R2 Part 2.1"):
                node_id = f"CIP-007-7.1 {part}"
                conn.execute(
                    """INSERT INTO effectivity_assertions(assertion_id, node_id, valid_from,
                           valid_to, recorded_from, approval_status)
                       VALUES (?,?,?,?, '2026-09-20T00:00:00+00:00', 'verified')""",
                    (f"ea-corr-{node_id}", node_id, "2029-07-01", None),
                )
        before = select_revision_effectivity(
            repo._conn, family="CIP-007", valid_at="2028-08-01", known_at="2026-09-19"
        )
        assert [rev["version"] for rev in before["selected"]] == ["7.1"]
        after = select_revision_effectivity(
            repo._conn, family="CIP-007", valid_at="2028-08-01", known_at="2026-09-21"
        )
        assert after["selected"] == []
        assert [rev["version"] for rev in after["future"]] == ["7.1"]
        repo.close()

    def test_no_sourced_effectivity_is_never_guessed(self, repo):
        repo.upsert_source_document(SourceDocument("d.pdf", "d", "", "procedure", ""))
        repo.add_document_revision("d.pdf", "/d.pdf", b"x")
        selection = select_revision_effectivity(repo._conn, family="CIP-999", valid_at="2026-09-14")
        assert selection["selected"] == [] and selection["future"] == []
        repo.close()


class TestClocksOnTraversal:
    def _edge(self, repo: Repository, *, assertion_id: str, valid_from: str | None) -> None:
        repo.upsert_source_document(SourceDocument("d.pdf", "d", "", "procedure", ""))
        rev = repo.add_document_revision("d.pdf", "/d.pdf", b"x")
        rel = RelationshipAssertion(
            assertion_id,
            "IMPLEMENTS",
            "req-a",
            rev.revision_id,
            "control-a",
            rev.revision_id,
            "CIP-007",
            valid_from=valid_from,
            recorded_from=now_iso(),
        )
        rel.status = "approved"
        rel.review_state = "CONFIRMED"
        repo.propose_relationship(rel)
        repo.decide_relationship(assertion_id, "CONFIRMED", "tester", expected_version=1)

    def test_unknown_validity_is_excluded_not_always_valid(self, repo):
        self._edge(repo, assertion_id="r-unknown", valid_from=None)
        self._edge(repo, assertion_id="r-dated", valid_from="2020-01-01")
        # undated rows remain on the governed (default) surface
        assert len(repo.list_relationship_assertions(ref="req-a")) == 2
        # ... but a temporal query never treats unknown as "always valid" (F02)
        temporal = repo.list_relationship_assertions(ref="req-a", valid_at="2024-01-01")
        assert [rel.assertion_id for rel in temporal] == ["r-dated"]
        repo.close()

    def test_known_at_excludes_later_recorded_edges(self, repo):
        self._edge(repo, assertion_id="r-old", valid_from="2020-01-01")
        temporal = repo.list_relationship_assertions(
            ref="req-a", valid_at="2024-01-01", known_at="1999-01-01"
        )
        assert temporal == []
        temporal_now = repo.list_relationship_assertions(
            ref="req-a", valid_at="2024-01-01", known_at=now_iso()
        )
        assert [rel.assertion_id for rel in temporal_now] == ["r-old"]
        repo.close()

    def test_trace_and_impact_disclose_temporal_exclusions(self, repo):
        self._edge(repo, assertion_id="r-dated", valid_from="2020-01-01")
        result = trace(repo, "req-a", valid_at="2024-01-01")
        assert result["temporal"]["valid_at"] == "2024-01-01"
        assert result["edges"]
        impact = impact_analyze(repo, "req-a", valid_at="2024-01-01")
        assert impact["temporal"]["excluded_unknown_validity"] >= 0
        repo.close()


class TestWithholdAndStoreNodes:
    def test_withhold_unknown_knowledge_splits_parts(self):
        selection = {
            "unknown_knowledge": [
                {"version": "6", "detail": "recorded later"},
            ]
        }
        parts = [
            {"id": "CIP-007-6 R1", "standard": "CIP-007-6"},
            {"id": "CIP-007-7.1 R1", "standard": "CIP-007-7.1"},
        ]
        kept, withheld = withhold_unknown_knowledge(parts, selection)
        assert [p["id"] for p in kept] == ["CIP-007-7.1 R1"]
        assert withheld == [
            {
                "id": "CIP-007-6 R1",
                "version": "6",
                "as_known": "UNKNOWN_KNOWLEDGE",
                "detail": "recorded later",
            }
        ]
        # no selection (family unresolvable) withholds nothing
        kept2, withheld2 = withhold_unknown_knowledge(parts, None)
        assert kept2 == parts and withheld2 == []

    def test_store_nodes_resolve_verbatim_clauses(self, repo):
        _family_nodes(repo, recorded_from="2026-09-15T11:42:05+00:00")
        with repo._lock, repo._conn:
            repo._conn.execute(
                """INSERT INTO obligation_atoms(atom_id, node_id, actor, modality, action)
                   VALUES ('a1','CIP-007-7.1 R2 Part 2.1','entity','shall','track')"""
            )
            repo._conn.execute(
                "UPDATE obligation_atoms SET clause_text = 'The entity shall track patches.' WHERE atom_id = 'a1'"
            )
        parts = store_nodes_for_revisions(repo._conn, {"rev-71"})
        assert "CIP-007-7.1 R2 Part 2.1" in parts
        assert parts["CIP-007-7.1 R2 Part 2.1"]["clauses"] == ["The entity shall track patches."]
        repo.close()


class TestProjectionManifests:
    def test_fingerprint_is_deterministic_and_state_sensitive(self, repo):
        fp1 = projections.canonical_fingerprint(repo)
        fp2 = projections.canonical_fingerprint(repo)
        assert fp1 == fp2
        repo.upsert_source_document(SourceDocument("d.pdf", "d", "", "procedure", ""))
        repo.add_document_revision("d.pdf", "/d.pdf", b"x")
        assert projections.canonical_fingerprint(repo) != fp1
        repo.close()

    def test_manifest_records_fingerprint_and_detects_staleness(self, repo):
        fp = projections.canonical_fingerprint(repo)
        projections.record_index_manifest(
            repo,
            index_kind="retrieval",
            generation_id="gen-1",
            canonical_fingerprint_value=fp,
            counts={"chunks": 10},
        )
        status = projections.projection_status(repo, "retrieval", fp)
        assert status["status"] == "FRESH" and status["generation_id"] == "gen-1"
        # a canonical change (new revision) invalidates the built-from stamp
        repo.upsert_source_document(SourceDocument("d2.pdf", "d2", "", "procedure", ""))
        repo.add_document_revision("d2.pdf", "/d2.pdf", b"y")
        stale = projections.projection_status(repo, "retrieval")
        assert stale["status"] == "STALE"
        assert stale["built_from_fingerprint"] == fp
        assert stale["canonical_fingerprint"] != fp
        repo.close()

    def test_absent_projection_is_absent(self, repo):
        status = projections.projection_status(repo, "graph")
        assert status["status"] == "ABSENT"
        repo.close()

    def test_new_generation_deactivates_the_previous(self, repo):
        fp = projections.canonical_fingerprint(repo)
        projections.record_index_manifest(
            repo, index_kind="graph", generation_id="g1", canonical_fingerprint_value=fp
        )
        projections.record_index_manifest(
            repo, index_kind="graph", generation_id="g2", canonical_fingerprint_value=fp
        )
        status = projections.projection_status(repo, "graph", fp)
        assert status["generation_id"] == "g2"
        rows = repo._conn.execute(
            "SELECT generation_id FROM index_manifests WHERE index_kind='graph' AND active=1"
        ).fetchall()
        assert [r[0] for r in rows] == ["g2"]
        repo.close()
