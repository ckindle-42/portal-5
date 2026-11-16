"""Investigation and job behavior, seeded from observation episodes."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pytest

from portal.modules.security.core.hunt import jobs
from portal.modules.security.core.hunt.engine import HOUR, host_hour_novelty
from portal.modules.security.core.hunt.jobs import (
    BudgetedSearch,
    HuntBudget,
    query_budget_kind,
)
from portal.modules.security.core.hunt.ranking import query_progress_kind, query_progress_shape
from tests.unit.test_hunt_observations import GridSearch
from tests.unit.test_hunt_wire import _raw_rows

DAY = 86400
T0 = 100 * DAY + 3 * HOUR
LEAD = T0 + 5 * HOUR
ATTACK = "attackvalue1"
PUNCT = " Victim !"
TEMPLATES = 20000
LINK_ROWS = 12000


def _reduced(rows: list[dict[str, Any]], span: int) -> list[dict[str, Any]]:
    first: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: float(item["_time"])):
        key = (row["host"], row["source"], row["punct"])
        if key not in first:
            bucket = dict(row)
            bucket["_time"] = float(int(float(row["_time"])) // span * span)
            first[key] = bucket
    return list(first.values())


def _novelty_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(4):
        rows.append(
            {
                "_time": float(T0 + index * HOUR),
                "host": "h",
                "source": "s",
                "punct": f"p{index}",
                "count": 1,
            }
        )
    return rows


def test_first_occurrence_reduction_preserves_novelty_exactly() -> None:
    rows = _novelty_rows()
    for span in (60, 600, HOUR, DAY):
        full = host_hour_novelty(rows, span=span)
        reduced = host_hour_novelty(_reduced(rows, span), span=span)
        assert set(full) == set(reduced)
        for key in full:
            assert full[key][0] == reduced[key][0]


def _event(hour: int, host: str, raw: str, *, punct: str, n: int = 1) -> list[dict[str, Any]]:
    return [
        {
            "_time": float(hour),
            "host": host,
            "source": "svc",
            "sourcetype": "a",
            "punct": punct,
            "_raw": raw,
        }
        for _ in range(n)
    ]


def _victim(host: str, *, spike: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for hour in range(5):
        rows += _event(T0 + hour * HOUR, host, f"user={ATTACK} cmd=runx", punct="svc..", n=2)
    rows += _event(LEAD, host, f"user={ATTACK} cmd=runx", punct=PUNCT, n=spike)
    return rows


def _background(n: int) -> list[dict[str, Any]]:
    return [
        row
        for index in range(n)
        for row in _event(T0, f"bg{index % 50}", f"bg template {index} ok", punct=f"bgp{index}..")
    ]


class EpisodeSearch(GridSearch):
    """Observation grids plus the investigation reads, recording every cap."""

    def __init__(
        self,
        events: list[dict[str, Any]],
        *,
        censor_neighborhood: bool = False,
        template_width: int = 0,
        evidence_rows: int = 8,
    ) -> None:
        super().__init__(events)
        self.seen: list[tuple[str, str, int | None, int]] = []
        self.censor_neighborhood = censor_neighborhood
        self.template_width = template_width
        self.evidence_rows = evidence_rows

    def iter_post(self, query: str, start: float, end: float) -> list[dict[str, Any]]:
        if self.censor_neighborhood and "| dedup 2 source punct" in query:
            exc = RuntimeError("search finalized before completion")
            exc.censored = True  # type: ignore[attr-defined]
            raise exc
        if "by host source punct" in query and "sourcetype" not in query and "span=" not in query:
            if self.template_width:
                return [
                    {"host": f"h{i % 3}", "source": "svc", "punct": f"p{i}", "count": 1}
                    for i in range(self.template_width)
                ]
            return self._template_counts(start, end)
        if "table _time host source punct _raw" in query:
            rows = _raw_rows(query, self._window(start, end))
            if "where punct=" not in query:
                rows = rows[: self.evidence_rows]
            return rows
        if " by host source _time span=" in query:
            return self._cells(query, start, end)
        return super().iter_post(query, start, end)

    def iter_post_bounded(
        self,
        query: str,
        start: float,
        end: float,
        timeout_seconds: float = 0,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        del timeout_seconds
        if self.censor_neighborhood and "| dedup 2 source punct" in query:
            exc = RuntimeError("search finalized before completion")
            exc.censored = True  # type: ignore[attr-defined]
            raise exc
        out = self.iter_post(query, start, end)
        returned = out[: max_results or None]
        self.seen.append((query, query_budget_kind(query), max_results, len(returned)))
        return returned

    def _template_counts(self, start: float, end: float) -> list[dict[str, Any]]:
        counts: Counter[tuple[str, str, str]] = Counter()
        for row in self._window(start, end):
            counts[(row["host"], row["source"], row["punct"])] += 1
        return [
            {"host": host, "source": source, "punct": punct, "count": count}
            for (host, source, punct), count in sorted(counts.items())
        ]

    def _cells(self, query: str, start: float, end: float) -> list[dict[str, Any]]:
        host = _quoted(query, "host")
        source = _quoted(query, "source")
        term = re.search(r'TERM\("([^"]*)"\)', query)
        if term is None:
            term = re.search(r'index="[^\"]+"\s+"([^\"]+)"\s+by', query)
        counts: Counter[tuple[str, str, int]] = Counter()
        for row in self._window(start, end):
            if host is not None and row["host"] != host:
                continue
            if source is not None and row["source"] != source:
                continue
            if term is not None and term.group(1) not in str(row.get("_raw", "")):
                continue
            hour = int(float(row["_time"])) // HOUR * HOUR
            counts[(row["host"], row["source"], hour)] += 1
        return [
            {"host": item_host, "source": item_source, "_time": float(hour), "count": count}
            for (item_host, item_source, hour), count in sorted(counts.items())
        ]


def _quoted(query: str, name: str) -> str | None:
    found = re.search(rf'\b{name}="([^"]*)"', query)
    return found.group(1) if found else None


def test_discovery_cardinality_over_the_evidence_budget_still_yields_leads(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    search = EpisodeSearch(_victim("victim", spike=40) + _background(TEMPLATES))
    job_id = "hunt-discovery1"

    jobs._run(job_id, search, "idx", float(T0), float(LEAD + HOUR), dig=15)

    job = jobs.load(job_id)
    assert job is not None
    assert job["status"] in {"COMPLETE", "PARTIAL"}
    assert job["status"] != "FAILED"
    assert job.get("error") is None
    assert "budget" not in str(job.get("coverage_reason"))
    progress = job["progress"]
    assert progress["exhausted_reason"] is None

    assert progress["discovery_row_count"] >= TEMPLATES
    assert progress["cell_count"] <= progress["limits"]["cells"]
    assert progress["event_count"] <= progress["limits"]["events"]

    leads = job.get("leads", [])
    assert leads
    assert leads[0]["host"] == "victim"
    assert leads[0]["score"] > 0
    burst_tokens = {b["token"] for lead in leads for b in lead.get("bursts", [])}
    assert ATTACK in burst_tokens

    cases = job.get("cases", [])
    assert cases
    assert ATTACK in {p["token"] for p in cases[0]["pivots"]}

    # ranking samples kept their per-sample cap; link enumerations streamed; investigation
    # evidence reads were bound by the events budget
    for q, _kind, cap, _rows in search.seen:
        if "md5(_raw)" in q and "where punct=" not in q:
            assert cap == 200, q
        elif q.endswith("by host source"):
            assert cap is None, q
        elif "table _time host source punct _raw" in q:
            assert isinstance(cap, int) and 0 < cap <= 5000, q


def test_ranking_reads_never_starve_lead_persistence_or_evidence_budgets(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    events = []
    for host in ("v1", "v2", "v3"):
        events += _victim(host, spike=500)
    search = EpisodeSearch(
        events,
        template_width=12 * 2000 + 12 * LINK_ROWS,
        evidence_rows=20,
    )
    job_id = "hunt-ranking1"

    jobs._run(
        job_id, search, "idx", float(T0), float(LEAD + HOUR), dig=15, budgets={"requests": 4000}
    )

    job = jobs.load(job_id)
    assert job is not None
    assert job["status"] in {"COMPLETE", "PARTIAL"}
    # ranking streamed 12 full 2000-row samples and 12 link enumerations, yet leads persisted
    leads = job.get("leads", [])
    assert leads and leads[0]["host"] == "v1"
    assert ATTACK in {b["token"] for lead in leads for b in lead.get("bursts", [])}

    progress = job["progress"]
    assert progress["discovery_row_count"] >= 12 * 2000 + 12 * LINK_ROWS
    assert progress["event_count"] <= progress["limits"]["events"]
    assert progress["cell_count"] <= progress["limits"]["cells"]

    sample_caps = {
        cap for q, _k, cap, _r in search.seen if "md5(_raw)" in q and "where punct=" not in q
    }
    assert sample_caps == {
        200
    }  # key-sample head is the declared slice budget, held for every sample
    assert all(cap is None for q, _k, cap, _r in search.seen if q.endswith("by host source"))
    # the investigator's seed read was bounded server-side by its own head, under the events cap
    seed_reads = [
        (q, cap, rows)
        for q, _k, cap, rows in search.seen
        if "table _time host source punct _raw" in q and "TERM(" not in q
    ]
    assert seed_reads and seed_reads[0][1:] == (5000, 401)
    seed_query = seed_reads[0][0]
    assert 'punct=" Victim !"' in seed_query and "head 401" in seed_query


def test_partial_current_case_survives_work_exhaustion(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    raw = "tok1=aaaa tok2=bbbb tok3=cccc tok4=dddd tok5=eeee tok6=ffff"
    search = EpisodeSearch(
        _victim("solo", spike=0) + _event(LEAD, "solo", raw, punct=PUNCT, n=800),
        evidence_rows=600,
    )
    # spike 0 still adds the punct via the extra events; drop the empty spike call's punct dup
    job_id = "hunt-partial1"

    jobs._run(
        job_id, search, "idx", float(T0), float(LEAD + HOUR), dig=15, budgets={"events": 2000}
    )

    job = jobs.load(job_id)
    assert job is not None
    assert job["status"] == "PARTIAL"
    assert "budget" in str(job["progress"]["exhausted_reason"])
    cases = job.get("cases", [])
    assert len(cases) == 1
    assert cases[0]["partial"] is True  # marked in-progress, never a whole-case claim
    assert job["completed_case_count"] == 0
    assert len(cases[0]["pivots"]) >= 4  # evidence gathered before exhaustion is retained
    assert len(cases[0]["evidence"]) > 0


def test_a_censored_lookup_censors_itself_and_the_case_continues(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    jobs._run(
        "hunt-cens1",
        EpisodeSearch(_victim("victim", spike=40), censor_neighborhood=True),
        "idx",
        float(T0),
        float(LEAD + HOUR),
        dig=15,
    )

    job = jobs.load("hunt-cens1")
    assert job is not None
    assert job["status"] != "FAILED"
    assert job.get("progress", {}).get("exhausted_reason") is None  # no shared budget was spent
    cases = job.get("cases", [])
    assert (
        len(cases) == 1 and cases[0]["pivots"]
    )  # investigation went on past the censored look-around
    assert any(str(d).startswith("near ") for d in cases[0]["degraded"])


def test_narrow_window_reports_standalone_shape() -> None:
    """A single-bucket term scan is flagged standalone; a multi-bucket variant is not."""
    narrow = '| tstats count where index=idx TERM("spk0") by _time span=3600s'
    wide = '| tstats count where index=idx TERM("spk0") by _time span=600s'
    assert query_progress_shape(narrow, float(LEAD), float(LEAD + HOUR)) == "standalone"
    assert query_progress_shape(wide, float(LEAD), float(LEAD + 4 * HOUR)) == "other"


def test_plain_quoted_tstats_terms_keep_their_progress_kinds() -> None:
    narrow = '| tstats count where index="idx" "uid=0" by _time span=3600s'
    cells = '| tstats count where index="idx" "uid=0" by host source'

    assert query_progress_shape(narrow, float(LEAD), float(LEAD + HOUR)) == "standalone"
    assert query_progress_kind(narrow, float(LEAD), float(LEAD + HOUR)) == "hour_screen"
    assert query_progress_kind(cells, float(LEAD), float(LEAD + HOUR)) == "term_tstats"


def test_packed_parent_reports_packed_shape() -> None:
    """A query carrying ``eval _ht=`` is flagged packed, regardless of window width."""
    packed_narrow = (
        '| tstats count where index="idx" '
        'TERM("spk0") by _time span=3600s '
        '| eval _hc=printf("%d:%d",_time,count) | eval _ht="0"'
    )
    packed_wide = (
        '| tstats count where index="idx" '
        'TERM("spk0") by _time span=600s '
        '| eval _hc=printf("%d:%d",_time,count) | eval _ht="0"'
    )
    assert query_progress_shape(packed_narrow, float(LEAD), float(LEAD + HOUR)) == "packed"
    assert query_progress_shape(packed_wide, float(LEAD), float(LEAD + 4 * HOUR)) == "packed"


def test_budget_records_shape_when_a_query_is_issued() -> None:
    """``HuntBudget.add_kind`` with a query attaches the live-declared shape to kind_stats."""

    class _Bounded:
        def iter_post_bounded(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            return [{"_time": float(LEAD), "count": 1}]

    budget_narrow = HuntBudget(
        {"query_seconds": 5, "job_seconds": 10, "requests": 10, "cells": 100, "events": 100}
    )
    search_narrow = BudgetedSearch(_Bounded(), budget_narrow)
    narrow = '| tstats count where index=idx TERM("spk0") by _time span=3600s'
    list(search_narrow.iter_post(narrow, float(LEAD), float(LEAD + HOUR)))
    kinds_narrow = budget_narrow.snapshot()["request_kinds"]
    assert kinds_narrow["hour_screen"]["shape"] == "standalone"

    budget_packed = HuntBudget(
        {"query_seconds": 5, "job_seconds": 10, "requests": 10, "cells": 100, "events": 100}
    )
    search_packed = BudgetedSearch(_Bounded(), budget_packed)
    packed = (
        '| tstats count where index="idx" TERM("spk0") by _time span=3600s '
        '| eval _hc=printf("%d:%d",_time,count) | eval _ht="0"'
    )
    list(search_packed.iter_post(packed, float(LEAD), float(LEAD + HOUR)))
    kinds_packed = budget_packed.snapshot()["request_kinds"]
    assert kinds_packed["hour_screen"]["shape"] == "packed"

    budget_other = HuntBudget(
        {"query_seconds": 5, "job_seconds": 10, "requests": 10, "cells": 100, "events": 100}
    )
    search_other = BudgetedSearch(_Bounded(), budget_other)
    other = '| tstats count where index="idx" by host'
    list(search_other.iter_post(other, float(LEAD), float(LEAD + HOUR)))
    kinds_other = budget_other.snapshot()["request_kinds"]
    assert kinds_other.get("host_inventory", {}).get("shape") == "other"
