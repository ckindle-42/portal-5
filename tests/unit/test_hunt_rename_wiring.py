"""Dynamic sourcetype renames flow from hunt() into observe() and read_cells()."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import portal.modules.security.core.hunt.notables.sample as sample_module
import portal.modules.security.core.hunt.observations as observations_module
import portal.modules.security.core.hunt.order as order_module
from portal.modules.security.core.hunt.engine import HOUR, hunt
from portal.modules.security.core.hunt.executor import executor_for
from portal.modules.security.core.hunt.observations import Observation
from portal.modules.security.core.hunt.order import rank_from_observations
from tests.unit.test_hunt_observations import END, INDEX, START, GridSearch, _event

_RENAMES = {"bro:http": "stream:http"}


class _Client:
    def complete(self, **request: Any) -> Mapping[str, Any]:
        raise AssertionError("no cell is judged in these wiring tests")


def _rows() -> list[dict[str, Any]]:
    return (
        _event(START, "h1", "uid=alpha", n=2, sourcetype="bro:http")
        + _event(START + HOUR, "h1", "uid=alpha", n=8, punct="!!", sourcetype="bro:http")
        + _event(START + 2 * HOUR, "h2", "uid=beta", n=4, punct="!!", sourcetype="bro:http")
    )


def _spy_observe(monkeypatch: Any) -> dict[str, Any]:
    """Wrap observe(): record the renames each call received and the run it returned."""
    real = observations_module.observe
    seen: dict[str, Any] = {"renames": [], "runs": []}

    def spy(
        search: Any,
        index: str,
        start: float,
        end: float,
        baseline: str = "current",
        renames: Mapping[str, str] | None = None,
    ) -> Any:
        seen["renames"].append(renames)
        run = real(search, index, start, end, baseline=baseline, renames=renames)
        seen["runs"].append(run)
        return run

    monkeypatch.setattr(observations_module, "observe", spy)
    return seen


def _spy_rank(monkeypatch: Any) -> dict[str, Any]:
    """Wrap rank_from_observations(): record renames, return an empty composed order."""
    seen: dict[str, Any] = {"renames": []}

    def spy(*args: Any, **kwargs: Any) -> dict[str, Any]:
        seen["renames"].append(kwargs.get("renames"))
        return {"leads": [], "judge_cost": {"requests": 0, "seconds": 0.0}, "served_models": set()}

    monkeypatch.setattr(order_module, "rank_from_observations", spy)
    return seen


def _spy_read_cells(monkeypatch: Any) -> dict[str, Any]:
    """Wrap read_cells(): record renames, return no reads."""
    seen: dict[str, Any] = {"renames": []}

    def spy(*args: Any, **kwargs: Any) -> list[Any]:
        seen["renames"].append(kwargs.get("renames"))
        return []

    monkeypatch.setattr(order_module, "read_cells", spy)
    return seen


def test_hunt_passes_explicit_renames_to_observe(monkeypatch: Any) -> None:
    seen = _spy_observe(monkeypatch)

    hunt(GridSearch(_rows()), INDEX, float(START), float(END), renames=_RENAMES)

    assert seen["renames"] == [_RENAMES]


def test_hunt_observe_literals_use_the_renamed_sourcetype(monkeypatch: Any) -> None:
    seen = _spy_observe(monkeypatch)

    hunt(GridSearch(_rows()), INDEX, float(START), float(END), renames=_RENAMES)

    literals = [
        str(observation.evidence.get("literal") or "")
        for run in seen["runs"]
        for observation in run.observations
    ]
    assert any('sourcetype="stream:http"' in literal for literal in literals)
    assert not any('sourcetype="bro:http"' in literal for literal in literals)


def test_hunt_discovers_renames_once_and_degrades_on_a_test_double(
    monkeypatch: Any,
) -> None:
    """A double without REST support answers the discovery query; renames resolve empty."""
    seen = _spy_observe(monkeypatch)
    discovery: list[Any] = []
    real_discovery = sample_module.sourcetype_renames

    def spy_discovery(executor: Any) -> Any:
        discovery.append(executor)
        return real_discovery(executor)

    monkeypatch.setattr(sample_module, "sourcetype_renames", spy_discovery)
    search = GridSearch(_rows())

    leads = hunt(search, INDEX, float(START), float(END))

    assert len(discovery) == 1
    assert seen["renames"] == [{}]
    assert any("rest" in query for query in search.calls)
    assert isinstance(leads, list)


def test_hunt_degrades_to_no_renames_when_discovery_raises(monkeypatch: Any) -> None:
    seen = _spy_observe(monkeypatch)

    def boom(executor: Any) -> Any:
        raise RuntimeError("no REST support")

    monkeypatch.setattr(sample_module, "sourcetype_renames", boom)

    leads = hunt(GridSearch(_rows()), INDEX, float(START), float(END))

    assert seen["renames"] == [{}]
    assert isinstance(leads, list)


def test_hunt_passes_renames_to_rank_from_observations(monkeypatch: Any) -> None:
    seen = _spy_rank(monkeypatch)
    search = GridSearch(_rows())
    search.executor = executor_for(search)

    hunt(
        search, INDEX, float(START), float(END), judge=_Client(), judge_model="m", renames=_RENAMES
    )

    assert seen["renames"] == [_RENAMES]


def test_rank_from_observations_forwards_renames_to_read_cells(monkeypatch: Any) -> None:
    seen = _spy_read_cells(monkeypatch)

    rank_from_observations(
        [Observation("volume", "h1", "alpha", START, 1.0, {"signal": "alpha"})],
        executor_for(GridSearch(_rows())),
        INDEX,
        float(START),
        float(END),
        _Client(),
        "m",
        budget_order="accumulated",
        judge_cells=0,
        order_mode="fused",
        evidence_mode="rarest",
        event_chars=500,
        renames=_RENAMES,
    )

    assert seen["renames"] == [_RENAMES]
