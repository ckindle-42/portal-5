"""D.1 -- data-intrinsic discovery and cousins among observations
(TASK_BULLY_DISCOVERY_FIRST_V1). Library-free by construction (D2)."""

from __future__ import annotations

import inspect

from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import discovery as disc

_MAJORITY_CLASSES = ("enumerate", "collect", "enumerate", "collect")
_MINORITY_CLASSES = ("auth", "enumerate", "auth", "enumerate")
_ATTACK_CLASSES = ("auth", "escalate", "execute", "collect")
_ODDITY_CLASSES = ("destroy", "other", "destroy", "other")

_SHARED_EDGE_KINDS = ("shared_entity", "temporal_adjacency")
_SHARED_SPAN = 200.0


def _unit(unit_id: str, entity: str, classes: tuple[str, ...]) -> ag.GradeableUnit:
    n = len(classes)
    return ag.GradeableUnit(
        unit_id=unit_id,
        level="L4_WINDOW",
        artifact_ids=tuple(f"{unit_id}-a{i}" for i in range(n)),
        entities=(entity,),
        action_classes=classes,
        edge_kinds=_SHARED_EDGE_KINDS,
        span_seconds=_SHARED_SPAN,
        structural_signature={
            "class_sequence": list(classes),
            "entity_role_profile": {"actor": 1},
        },
        vocabulary=(),
        source_ids=(f"src-{unit_id}",),
    )


def _fitted_baseline(n_majority: int = 100) -> bl.NormalBaseline:
    """A baseline fit ONLY on the routine majority shape -- discovery must
    never see the library, but it must see this environment's own history."""
    model = bl.NormalBaseline(environment_id="d1-env")
    model.fit([_unit(f"maj-{i}", f"benign-{i}", _MAJORITY_CLASSES) for i in range(n_majority)])
    return model


def _minority_units(n: int = 23) -> list[ag.GradeableUnit]:
    """A rarer-but-still-ordinary shape: never fit into the baseline, so its
    two behavioural bigrams score fully rare, but it shares every structural
    boilerplate token (edge mix, span, size, entity role) with the fitted
    majority -- an ordinary cluster, not an attack."""
    return [_unit(f"min-{i}", f"minor-{i}", _MINORITY_CLASSES) for i in range(n)]


def _attack_units(n: int = 3) -> list[ag.GradeableUnit]:
    """The injected attack shape on N distinct entities -- three of its four
    bigrams are wholly unseen by the baseline, so it out-ranks the ordinary
    cluster on rarity even though the ordinary cluster is larger."""
    return [_unit(f"atk-{i}", f"attacker-{i}", _ATTACK_CLASSES) for i in range(n)]


def _oddity_unit() -> ag.GradeableUnit:
    """A one-off: unusual, coherent, but shaped like nothing else present --
    a cluster of one, which is not a pattern (MIN_CLUSTER_SIZE)."""
    return _unit("odd-0", "oddball", _ODDITY_CLASSES)


def test_attack_cluster_ranks_first_by_remarkability_and_is_pure():
    baseline = _fitted_baseline()
    units = _minority_units() + _attack_units() + [_oddity_unit()]
    discoveries, report = disc.discover(units, baseline)

    assert report["discovered"] > 0
    clusters = disc.find_cousin_clusters(discoveries)
    by_remarkability = sorted(clusters, key=lambda c: c.mean_remarkability, reverse=True)

    top = by_remarkability[0]
    assert set(top.members) == {u.unit_id for u in _attack_units()}
    assert top.n_distinct_entities == 3
    assert all(m.startswith("atk-") for m in top.members)  # pure: no minority/oddity bled in


def test_discover_takes_no_anchor_library_argument():
    """D2, signature-check: discovery is library-free by construction."""
    params = inspect.signature(disc.discover).parameters
    for name in params:
        assert "library" not in name.lower() and "anchor" not in name.lower(), (
            f"discover() must not accept a library/anchor parameter, found {name!r}"
        )
    assert "library" not in params


def test_empty_library_still_yields_the_cluster_and_resembles_nothing():
    baseline = _fitted_baseline()
    discoveries, _ = disc.discover(_attack_units(), baseline)
    clusters = disc.find_cousin_clusters(discoveries)
    assert len(clusters) == 1
    cluster = clusters[0]

    enrichment = disc.enrich(cluster.shared_shape, library_shapes=[])
    assert enrichment.resembles_nothing is True
    assert enrichment.relation == "NONE"
    # the finding stands regardless of enrichment (D4)
    assert cluster.n_distinct_entities == 3


def test_seeded_violation_reverting_to_mean_remarkability_rejects_attack_units():
    """Seeded to fail: swap `tail_remarkability` for `baseline.remarkability`
    (the mean-over-all-tokens shape) and the attack units drop below the
    discovery threshold, because five-plus shared boilerplate tokens dilute
    the two-to-three genuinely rare bigrams. This is the defect the payload's
    docstring documents and `tail_remarkability` exists to fix."""
    baseline = _fitted_baseline()
    for unit in _attack_units():
        mean_remarkability = baseline.remarkability(unit)
        tail = disc.tail_remarkability(unit, baseline)
        assert tail > mean_remarkability
        assert mean_remarkability < disc.DISCOVERY_MIN_REMARKABILITY
        assert tail >= disc.DISCOVERY_MIN_REMARKABILITY


def test_single_member_cluster_is_not_emitted():
    baseline = _fitted_baseline()
    discoveries, _ = disc.discover(_attack_units(n=1) + [_oddity_unit()], baseline)
    clusters = disc.find_cousin_clusters(discoveries)
    all_members = {m for c in clusters for m in c.members}
    assert "odd-0" not in all_members
    assert all(len(c.members) >= disc.MIN_CLUSTER_SIZE for c in clusters)


def test_cluster_size_does_not_outrank_rarity():
    """D5: the ordinary cluster is larger (23 members) than the attack
    cluster (3 members), but ranking by mean remarkability -- the analyst
    queue's actual ranking -- puts the smaller, rarer attack cluster first."""
    baseline = _fitted_baseline()
    units = _minority_units(23) + _attack_units(3)
    discoveries, _ = disc.discover(units, baseline)
    clusters = disc.find_cousin_clusters(discoveries)
    assert len(clusters) == 2

    by_size = max(clusters, key=lambda c: len(c.members))
    by_rarity = sorted(clusters, key=lambda c: c.mean_remarkability, reverse=True)[0]

    assert len(by_size.members) == 23
    assert by_rarity is not by_size
    assert set(by_rarity.members) == {u.unit_id for u in _attack_units(3)}
