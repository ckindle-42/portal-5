"""Y.3 -- truth-aware selection. Reproduction of D2 (TASK_BULLY_TRUTH_ACCEPTANCE_V1):
`assemble_timelines` sorted richest-first, so a sparse implant entity never
won a take-top-N cutoff against a sea of busy background entities. See
docs/DESIGN_BULLY_TRUTH_ACCEPTANCE_V1.md.
"""

from __future__ import annotations

from portal.modules.security.core.bully.correlation import (
    ResolvedEntity,
    assemble_timelines,
)

MAX_TIMELINES = 5


def _build(n_background: int) -> tuple[list[dict], dict[str, ResolvedEntity], dict[str, str]]:
    entities: dict[str, ResolvedEntity] = {}
    value_to_id: dict[str, str] = {}
    artifacts: list[dict] = []

    # One sparse implant entity: a single source, a single artifact -- exactly
    # the shape a richest-first sort ranks last.
    entities["ent-implant"] = ResolvedEntity(
        entity_id="ent-implant",
        canonical="implant-host",
        kind="host",
        aliases=("implant-host",),
        source_ids=("src0",),
        evidence=("singleton",),
        confidence=1.0,
    )
    value_to_id["implant-host"] = "ent-implant"
    artifacts.append({"_key": "a-implant", "v": "implant-host", "src": "src0"})

    # A sea of rich background entities: many sources, many artifacts each.
    for i in range(n_background):
        eid = f"ent-bg-{i}"
        canonical = f"bg-host-{i}"
        entities[eid] = ResolvedEntity(
            entity_id=eid,
            canonical=canonical,
            kind="host",
            aliases=(canonical,),
            source_ids=tuple(f"src{j}" for j in range(4)),
            evidence=("singleton",),
            confidence=1.0,
        )
        value_to_id[canonical] = eid
        for j in range(4):
            artifacts.append({"_key": f"a-bg-{i}-{j}", "v": canonical, "src": f"src{j}"})

    return artifacts, entities, value_to_id


def _assemble(artifacts, entities, value_to_id, priority_entity_ids=None):
    return assemble_timelines(
        artifacts,
        entities,
        value_to_id,
        artifact_entity_values=lambda a: [a["v"]],
        artifact_time=lambda a: None,
        artifact_id=lambda a: a["_key"],
        artifact_source=lambda a: a["src"],
        priority_entity_ids=priority_entity_ids,
    )


def test_richest_first_selection_excludes_the_implant() -> None:
    """Reproduces X.6's D2: without a priority set, the sparse implant loses
    the richest-first sort and a take-top-N cutoff drops it entirely."""
    artifacts, entities, value_to_id = _build(n_background=20)
    timelines = _assemble(artifacts, entities, value_to_id)
    selected = timelines[:MAX_TIMELINES]
    selected_ids = {t.entity.entity_id for t in selected}
    assert "ent-implant" not in selected_ids


def test_priority_entity_ids_guarantees_implant_selection() -> None:
    artifacts, entities, value_to_id = _build(n_background=20)
    timelines = _assemble(
        artifacts, entities, value_to_id, priority_entity_ids=frozenset({"ent-implant"})
    )
    selected = timelines[:MAX_TIMELINES]
    selected_ids = {t.entity.entity_id for t in selected}
    assert "ent-implant" in selected_ids
    # remainder is still richest-first among themselves
    assert selected[0].entity.entity_id == "ent-implant"
    rest = selected[1:]
    assert rest == sorted(rest, key=lambda t: (t.n_sources, len(t.artifact_ids)), reverse=True)
