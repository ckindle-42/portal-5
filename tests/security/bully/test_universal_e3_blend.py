"""E.3 -- the deterministic, offline multi-schema blend fixture.
TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1."""

from __future__ import annotations

from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import blend


def test_compose_blend_spans_at_least_three_schemas() -> None:
    records, provenance = blend.compose_blend()
    schemas = blend.schemas_present(records, provenance)
    assert len(schemas) >= 3
    assert schemas <= set(blend.SCHEMAS)


def test_blend_is_extractable_by_field_role_inference() -> None:
    records, _provenance = blend.compose_blend()
    graph = ag.build_graph(records)
    assert graph.role_map is not None
    assert graph.role_map.extraction_valid, graph.role_map.failure_reasons
    units = ag.enumerate_units(graph)
    assert units


def test_injected_artifacts_carry_family_technique_chain_step() -> None:
    _records, provenance = blend.compose_blend()
    injected = [p for p in provenance.values() if p.injected]
    assert injected
    for p in injected:
        assert p.family is not None
        assert p.technique is not None
        assert p.chain_id is not None
        assert p.step_idx is not None


def test_benign_artifacts_carry_no_family_or_technique() -> None:
    _records, provenance = blend.compose_blend()
    benign = [p for p in provenance.values() if not p.injected]
    assert benign
    for p in benign:
        assert p.family is None
        assert p.technique is None


def test_injected_is_sparse_relative_to_benign() -> None:
    _records, provenance = blend.compose_blend()
    injected = sum(1 for p in provenance.values() if p.injected)
    benign = sum(1 for p in provenance.values() if not p.injected)
    assert injected < benign / 5


def test_provenance_never_rides_inside_the_blind_record() -> None:
    """Q3: ground truth is never present on the graded record itself."""
    records, _provenance = blend.compose_blend()
    forbidden_keys = {"family", "technique", "chain_id", "step_idx", "injected"}
    for record in records:
        assert not (forbidden_keys & set(record)), record


def test_fingerprint_is_stable_and_joins_records_to_provenance() -> None:
    records, provenance = blend.compose_blend()
    for record in records[:20]:
        fp = blend._fingerprint(record)
        assert fp in provenance


def test_deterministic_across_calls() -> None:
    records_a, provenance_a = blend.compose_blend()
    records_b, provenance_b = blend.compose_blend()
    assert records_a == records_b
    assert {k: v.to_dict() for k, v in provenance_a.items()} == {
        k: v.to_dict() for k, v in provenance_b.items()
    }


def test_seeded_violation_single_schema_corpus_fails_plurality() -> None:
    """The regression this fixture exists to prevent: a single-schema
    corpus (M.3's actual defect) must never satisfy the Q2 plurality bar."""
    records, provenance = blend.compose_blend()
    single_schema_records = [
        r for r in records if provenance[blend._fingerprint(r)].schema == "cloudtrail"
    ]
    single_schema_provenance = {fp: p for fp, p in provenance.items() if p.schema == "cloudtrail"}
    schemas = blend.schemas_present(single_schema_records, single_schema_provenance)
    assert schemas == {"cloudtrail"}
    assert len(schemas) < 3
