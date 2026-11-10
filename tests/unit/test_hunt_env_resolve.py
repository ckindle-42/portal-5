"""Hunt jobs resolve by environment: index over a retyped job_id, near-miss repair, bounded
views (TASK_HUNT_P2A_ENV_RESOLVE). No network; job files live under tmp_path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.hunt import jobs
from portal.modules.security.core.hunt.engine import Burst, Lead
from portal.modules.security.core.hunt.investigate import Case


@pytest.fixture()
def hunts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    return tmp_path


def _store(job_id: str, index: str, started: float, **extra: Any) -> None:
    payload: dict[str, Any] = {
        "job_id": job_id,
        "index": index,
        "status": "COMPLETE",
        "started": started,
        **extra,
    }
    jobs._write(job_id, payload)


def _lead(hour: int, host: str = "h1") -> Lead:
    return Lead(
        hour=hour,
        host=host,
        novelty=1.5,
        hosts_novel_that_hour=2,
        novel_templates=[("src", "punct", 3)] * 7,
        bursts=[
            Burst(token=f"tok{i}", this_hour=i, prior_median=0.5, prior_hours_active=2, z=2.0)
            for i in range(5)
        ],
        score=0.5,
    )


class _StubInv:
    """Stands in for the Splunk-backed Investigator; each lead becomes one empty case."""

    degraded: list[str] = []

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def investigate(self, lead: Lead) -> Case:
        return Case(seed=f"{lead.host}@{lead.hour}", seed_hour=lead.hour)


def _run_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    job_id: str,
    leads: list[Lead],
    index: str = "memory",
    dig: int = 0,
) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    monkeypatch.setattr(jobs, "hunt", lambda *_a, **_k: leads)
    monkeypatch.setattr(jobs, "Investigator", _StubInv)
    jobs._run(job_id, None, index, 0.0, 1.0, dig)


def test_status_resolves_index_to_newest_started(hunts: Path) -> None:
    _store("hunt-old", "memory", 100.0)
    _store("hunt-new", "memory", 200.0)
    _store("hunt-elsewhere", "other", 300.0)
    out = jobs.status(index="memory")
    assert out["job_id"] == "hunt-new"
    assert "resolved_from" not in out


def test_near_miss_job_id_resolves_with_resolved_from(hunts: Path) -> None:
    _store("hunt-e606e963382f", "memory", 1.0)
    out = jobs.status(job_id="hunt-e606e9633a2f")
    assert out["job_id"] == "hunt-e606e963382f"
    assert out["resolved_from"] == "hunt-e606e9633a2f"


def test_ambiguous_near_miss_is_not_guessed(hunts: Path) -> None:
    _store("hunt-aaaaaaaaaaa1", "memory", 1.0)
    _store("hunt-aaaaaaaaaaa2", "memory", 2.0)
    out = jobs.status(job_id="hunt-aaaaaaaaaaa3")
    assert "error" in out
    assert "resolved_from" not in out


def test_unknown_job_id_errors_with_three_recent_jobs(hunts: Path) -> None:
    for i in range(1, 5):
        _store(f"hunt-{i:012x}", "memory", float(i))
    out = jobs.status(job_id="hunt-ffffffffffff")
    assert "hunt-ffffffffffff" in out["error"]
    assert len(out["recent"]) == 3
    assert all(set(row) == {"job_id", "index", "status", "started"} for row in out["recent"])
    assert [row["started"] for row in out["recent"]] == [4.0, 3.0, 2.0]


def test_no_arguments_is_an_error(hunts: Path) -> None:
    assert "error" in jobs.status()


def test_leads_and_case_views_resolve_by_index(hunts: Path) -> None:
    _store(
        "hunt-viewed",
        "memory",
        1.0,
        leads=[
            {
                "hour": 0,
                "hour_utc": "1970-01-01 00:00",
                "span": 3600,
                "host": "h1",
                "score": 0.9,
                "novelty": 1.5,
                "bursts": [{"token": "tk", "this_hour": 3, "prior_median": 1.0}],
            }
        ],
        cases=[
            {
                "merged_from": ["h1@0"],
                "events": 2,
                "hosts": {"h1": 2},
                "span_hours": 1,
                "pivots": [{"token": "tk", "count": 5, "hosts": 2, "weight": 2.0}],
                "picture": [{"time": 60.0, "host": "h1", "source": "s", "raw": "raw line"}],
            }
        ],
    )
    leads = jobs.leads_view(index="memory")
    assert leads["job_id"] == "hunt-viewed"
    assert leads["leads"][0]["host"] == "h1"
    case = jobs.case_view(index="memory", case_no=1)
    assert case["job_id"] == "hunt-viewed"
    assert case["seeds"] == ["h1@0"]


def test_run_saves_every_lead_stripped_and_view_caps_at_25(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run_job(monkeypatch, tmp_path, "hunt-full", [_lead(i) for i in range(5000)])
    stored = jobs.load("hunt-full")
    assert stored is not None and len(stored["leads"]) == 5000
    lead = stored["leads"][0]
    assert len(lead["bursts"]) == 3
    assert all("links" not in burst for burst in lead["bursts"])
    assert len(lead["novel_templates"]) == 5
    out = jobs.leads_view(job_id="hunt-full", n=100)
    assert out["job_id"] == "hunt-full"
    assert len(out["leads"]) == 25


def test_large_fixture_views_stay_under_6000_chars(hunts: Path) -> None:
    leads = [
        {
            "hour_utc": "2026-01-01 00:00",
            "span": 3600,
            "host": "H" * 60,
            "score": 0.9,
            "novelty": 1.0,
            "bursts": [{"token": "T" * 200, "this_hour": 7, "prior_median": 0.5}],
        }
    ] * 40
    case = {
        "merged_from": ["h1@0"],
        "events": 30,
        "hosts": {"h1": 20, "h2": 10},
        "span_hours": 3,
        "pivots": [
            {"token": f"p{i}", "count": 12 - i, "hosts": 2, "weight": 9.0 - i} for i in range(12)
        ],
        "picture": [
            {"time": 1000.0 * i, "host": "H" * 50, "source": "S" * 30, "raw": "R" * 200}
            for i in range(30)
        ],
    }
    _store("hunt-fat", "memory", 1.0, leads=leads, cases=[case])
    views = [
        jobs.status(job_id="hunt-fat"),
        jobs.leads_view(job_id="hunt-fat", n=25),
        jobs.case_view(job_id="hunt-fat", case_no=1, n=25),
    ]
    assert all(len(json.dumps(view)) < 6000 for view in views)
    assert jobs.leads_view(job_id="hunt-fat", n=25)["truncated"] is True
    assert jobs.case_view(job_id="hunt-fat", case_no=1, n=25)["truncated"] is True


def test_hunt_tools_resolve_by_index(hunts: Path) -> None:
    review_mcp = pytest.importorskip("portal.modules.security.tools.review_mcp")
    _store(
        "hunt-tool",
        "memory",
        1.0,
        cases=[
            {
                "merged_from": ["h@0"],
                "events": 1,
                "hosts": {"h": 1},
                "span_hours": 1,
                "pivots": [],
                "picture": [],
            }
        ],
    )
    assert review_mcp.hunt_status(index="memory")["job_id"] == "hunt-tool"
    assert review_mcp.hunt_leads(index="memory")["job_id"] == "hunt-tool"
    assert review_mcp.hunt_case(index="memory")["job_id"] == "hunt-tool"


def test_hunt_start_tells_the_model_the_next_step(monkeypatch: pytest.MonkeyPatch) -> None:
    review_mcp = pytest.importorskip("portal.modules.security.tools.review_mcp")
    monkeypatch.setattr(review_mcp, "_hunt_search", lambda: None)
    monkeypatch.setattr(review_mcp.hunt_jobs, "start", lambda *_a, **_k: "hunt-abc123def456")
    out = review_mcp.hunt_start(index="memory")
    assert out["job_id"] == "hunt-abc123def456"
    assert out["index"] == "memory"
    assert out["status"] == "RUNNING"
    assert "hunt_status(index='memory')" in out["next"]
    assert "hunt_case(index='memory', case=1)" in out["next"]


def test_hunt_sources_response_is_compacted(monkeypatch: pytest.MonkeyPatch) -> None:
    review_mcp = pytest.importorskip("portal.modules.security.tools.review_mcp")

    class _FakeSearch:
        def iter_post(self, _q: str, _s: float, _e: float) -> list[dict[str, Any]]:
            return [{"index": f"idx{i:03d}-" + "x" * 200, "count": i} for i in range(100)]

    monkeypatch.setattr(review_mcp, "_hunt_search", _FakeSearch)
    out = review_mcp.hunt_sources()
    assert len(json.dumps(out)) < 6000
