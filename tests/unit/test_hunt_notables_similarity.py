from __future__ import annotations

from dataclasses import replace

import pytest

from portal.modules.security.core.hunt.notables.behaviours import Behaviour
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.similar import (
    SimilarityError,
    _ranked_notables,
)


def _behaviour() -> Behaviour:
    return Behaviour(
        source_id="run:activity",
        actor_field="user",
        actor="alice",
        action_field="action",
        action="execute",
        object_field="path",
        object="shell",
        actor_mode="literal",
        action_mode="literal",
        object_mode="literal",
        events=2,
        first_seen=10.0,
        last_seen=20.0,
        hosts=1,
        actors=1,
        example_time=10.0,
        example_query='search index="run" TERM("alice") | head 5',
        example_raw="event line",
        example_earliest=0.0,
        example_latest=60.0,
    )


def _card() -> SourceCard:
    return SourceCard(
        index="run",
        sourcetype="activity",
        kind="activity",
        roles={"actor": ("user",), "action": ("action",)},
        understood=True,
        reason=None,
        fmt="json",
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="",
    )


def test_similarity_error_names_source_and_actual_card_kind() -> None:
    measurement = replace(_card(), kind="measurement", roles={})

    with pytest.raises(SimilarityError, match=r"run:activity.*measurement"):
        _ranked_notables(None, [_behaviour()], [measurement], {}, {"score": "known_bad"})  # type: ignore[arg-type]


def test_similarity_diversifies_repeating_numeric_patterns() -> None:
    from portal.modules.security.core.hunt.notables.similar import _diversify_ranked

    noisy = [
        (0.90 - idx * 0.001, idx, replace(_behaviour(), actor=str(90 + idx), action="", object=""))
        for idx in range(5)
    ]
    distinct = (
        0.85,
        5,
        replace(_behaviour(), source_id="run:web", actor="1.2.3.4", object="/login"),
    )
    ordered = _diversify_ranked([*noisy, distinct])
    assert [row[2].source_id for row in ordered[:2]] == ["run:activity", "run:web"]
