"""The graph runner reads bounded cells in one order and reports its own coverage."""

from __future__ import annotations

from portal.modules.security.core.hunt.engine import HOUR
from portal.modules.security.core.hunt.observations import Observation
from scripts.hunt_bed import graph_hunt

START = 1_700_000_000 // HOUR * HOUR

INDEX = "idx"


def _obs(
    kind: str,
    host: str,
    entity: str,
    hour: int,
    score: float,
    prior: tuple[int, ...] = (),
) -> Observation:
    return Observation(
        kind,
        host,
        entity,
        hour,
        score,
        {
            "signal": "burst",
            "now": 1,
            "prior": [{"hour": stamp, "count": 1} for stamp in prior],
            "scores": {"current": score, "seasonal": None, "peer": None, "left": None},
        },
    )


def test_one_cell_is_read_once_with_the_first_observations_literal() -> None:
    plan = graph_hunt.cell_plan(
        INDEX,
        [_obs("volume", "h0", "", START, 2.0), _obs("value", "h0", "uid=a", START, 9.0)],
    )

    assert [(cell.host, cell.hour, cell.baseline) for cell in plan] == [("h0", START, False)]
    assert plan[0].literal == 'search index="idx" host="h0"'


def test_cells_follow_the_observation_order_then_prior_hours() -> None:
    plan = graph_hunt.cell_plan(
        INDEX,
        [
            _obs("value", "h1", "uid=alpha", START + 2 * HOUR, 9.0, prior=(START + HOUR, START)),
            _obs("volume", "h2", "", START + 3 * HOUR, 5.0, prior=(START + HOUR,)),
        ],
    )

    assert [(cell.host, cell.hour, cell.baseline) for cell in plan] == [
        ("h1", START + 2 * HOUR, False),
        ("h1", START + HOUR, True),
        ("h1", START, True),
        ("h2", START + 3 * HOUR, False),
        ("h2", START + HOUR, True),
    ]
    assert plan[0].literal == 'search index="idx" host="h1" "uid=alpha" "alpha"'


def test_cell_plan_stops_at_the_budget() -> None:
    observations = [
        _obs("volume", f"h{index}", "", START + index * HOUR, 1.0)
        for index in range(graph_hunt.CELL_BUDGET + 10)
    ]

    plan = graph_hunt.cell_plan(INDEX, observations)

    assert len(plan) == graph_hunt.CELL_BUDGET
    assert len({(cell.host, cell.hour) for cell in plan}) == len(plan)


def test_history_query_is_the_indexed_term_over_the_whole_retention() -> None:
    assert (
        graph_hunt.history_query(INDEX, "op=pam:accounting")
        == '| tstats count where index="idx" TERM("op=pam:accounting") by _time span=1h'
    )


def test_a_value_that_is_not_a_term_is_recorded_not_dropped() -> None:
    observation = _obs("value", "h1", "msg=a,b", START, 9.0)

    targets, skipped = graph_hunt.history_plan({"msg=a,b"}, [observation], [])

    assert targets == []
    assert skipped == [("msg=a,b", "not_a_term")]
