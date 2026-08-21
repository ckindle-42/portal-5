"""C.4 -- fit wide, score narrow.

Seeded against D.4's own degeneracy: fitting a `NormalBaseline` on the SAME
25-unit population it then scores can never tell a genuinely rare shape from
one that just happens not to repeat within a sample that small -- every
shape looks equally novel, so `discovery_rate` collapses to ~1.0. Fitting the
IDENTICAL scored population against a much larger corpus -- one where a
shape among the scored set is shown to actually recur constantly -- lets the
baseline draw that distinction and produces a lower, discriminating rate.
"""

from __future__ import annotations

import itertools
import random

from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import discovery as disc

_SHARED_EDGE_KINDS = ("shared_entity", "temporal_adjacency")
_SHARED_SPAN = 200.0
_VERBS = ("auth", "enumerate", "execute", "collect", "persist", "destroy", "spawn", "query")


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


def _scored_sample() -> tuple[list[ag.GradeableUnit], tuple[tuple[str, ...], ...]]:
    """25 units, each a DISTINCT 3-verb permutation -- D.4's real shape: on a
    25-unit sample, nothing repeats, so every unit looks equally novel
    whether or not it actually is."""
    perms = list(itertools.permutations(_VERBS, 3))
    random.Random(3).shuffle(perms)
    combos = perms[:25]
    return [_unit(f"scored-{i}", f"entity-{i}", combos[i]) for i in range(25)], tuple(combos)


def test_fitting_on_the_scored_sample_reproduces_degenerate_discovery_rate():
    units, _combos = _scored_sample()
    baseline = bl.NormalBaseline(environment_id="c4-narrow")
    baseline.fit(units)  # D.4's mistake: fit == score, same 25 units

    _discoveries, report = disc.discover(units, baseline)
    # A baseline that has only ever seen these 25 units cannot tell "rare"
    # from "just never repeated yet" -- everything reads as novel.
    assert report["discovery_rate"] == 1.0


def test_fitting_wide_drops_discovery_rate_to_a_discriminating_value():
    scored, combos = _scored_sample()
    # WIDE fit: the FIRST scored shape, replayed 5000 times as background --
    # it is, in truth, a common routine pattern, just one that happened not
    # to repeat inside the 25-unit scored sample. The other 24 shapes never
    # recur in this corpus either, so they remain genuinely rare.
    common_shape = combos[0]
    wide_fit_units = [_unit(f"fit-{i}", f"fit-entity-{i}", common_shape) for i in range(5000)]
    baseline = bl.NormalBaseline(environment_id="c4-wide")
    baseline.fit(wide_fit_units)
    assert baseline.fitted_units_at("L4_WINDOW") == 5000

    discoveries, report = disc.discover(scored, baseline)
    # The identical scored population now discriminates: the one shape the
    # wide fit has actually seen thousands of times scores common, not rare.
    assert report["discovery_rate"] < 1.0
    discovered_ids = {d.unit_id for d in discoveries}
    assert "scored-0" not in discovered_ids  # the shape shown to be common
    assert "scored-1" in discovered_ids  # still genuinely rare in this corpus
