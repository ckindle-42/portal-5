"""Indexed discovery stays exact at environment scale: the server reduces, the client reasons.

The live lab returns 1.8M by-hour template cells for one index; the first-occurrence reduction
in ``template_rows`` must preserve the novelty scores exactly while discovery streams far more
rows than the evidence budgets could ever hold.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pytest

from portal.modules.security.core.hunt import jobs
from portal.modules.security.core.hunt.engine import (
    HOUR,
    Lead,
    host_hour_novelty,
    hunt,
    template_rows,
    value_bursts,
)
from portal.modules.security.core.hunt.jobs import query_budget_kind

DAY = 86400

T0 = 100 * DAY + 3 * HOUR
LEAD = T0 + 60 * HOUR  # the victim hour, days of prior history after it
ATTACK = "attackvalue1"
TEMPLATES = 20000
STREAMS = [(f"bg{h}", f"svc{s}") for h in range(5) for s in range(3)]


def _universe() -> list[dict[str, Any]]:
    """20k background templates, each stream's templates all first seen in its own first bucket
    (so the background is never novel again), plus a victim stream: known-value priors in the
    first hours, one novel template and a burst of the known value in the lead hour. Every
    (host, source, punct, bucket) is unique at every zoom span, like real tstats output."""
    rows: list[dict[str, Any]] = []
    per_stream = TEMPLATES // len(STREAMS)
    for idx, (host, source) in enumerate(STREAMS):
        count = (
            per_stream if idx < len(STREAMS) - 1 else TEMPLATES - per_stream * (len(STREAMS) - 1)
        )
        for j in range(count):
            rows.append(
                {
                    "_time": float(T0 + idx * HOUR),
                    "host": host,
                    "source": source,
                    "punct": f"bgp{idx}_{j}..",
                    "count": 3,
                    "_raw": f"bg template {idx}_{j} ok",
                }
            )
    rows.append(
        {
            "_time": float(T0),
            "host": "victim",
            "source": "svc",
            "punct": "svc..",
            "count": 2,
            "_raw": "svc heartbeat ok",
        }
    )
    for hour in (1, 2, 3, 4):
        rows.append(
            {
                "_time": float(T0 + hour * HOUR),
                "host": "victim",
                "source": "svc",
                "punct": f"svc{hour}..",
                "count": 2,
                "_raw": f"x={ATTACK} y=qqzz",
            }
        )
    rows.append(
        {
            "_time": float(LEAD),
            "host": "victim",
            "source": "svc",
            "punct": " Victim !",
            "count": 6,
            "_raw": f"user={ATTACK} cmd=runx",
        }
    )
    return rows


def _reduced(rows: list[dict[str, Any]], span: int) -> list[dict[str, Any]]:
    """What ``dedup host source punct sortby +_time`` returns: each template's first bucket,
    with that bucket's count and its stream origin."""
    first: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in sorted(rows, key=lambda r: float(r["_time"])):
        key = (row["host"], row["source"], row["punct"])
        if key not in first:
            bucket = dict(row)
            bucket["_time"] = float(int(float(row["_time"])) // span * span)
            first[key] = bucket
    return list(first.values())


def test_first_occurrence_reduction_preserves_novelty_exactly() -> None:
    rows = _universe()
    for span in (60, 600, HOUR, DAY):
        full = host_hour_novelty(rows, span=span)
        reduced = host_hour_novelty(_reduced(rows, span), span=span)
        assert set(full) == set(reduced)
        for key, (score, items) in full.items():
            assert reduced[key][0] == pytest.approx(score)
            assert sorted(reduced[key][1]) == sorted(items)


class _CountingSearch:
    """Answers hunt()'s aggregate and sample shapes; records every issued query."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.queries: list[str] = []
        self.series_scans: list[str] = []

    def iter_post(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
        self.queries.append(q)
        rows = [r for r in self.rows if start <= float(r["_time"]) < end]
        if q.startswith("| tstats min(_time)"):
            return [{"lo": min(float(r["_time"]) for r in rows), "hi": float(LEAD + HOUR)}]
        if "| dedup host source punct sortby +_time" in q:
            return _reduced(rows, int(re.search(r"span=(\d+)s", q).group(1)))
        if q.startswith("search index="):
            host = _clause(q, "host")
            return [
                {"_raw": r["_raw"], "punct": r["punct"]}
                for r in rows
                if host is None or r["host"] == host
            ]
        token = _term(q)
        if token:
            self.series_scans.append(token)
            if " by host source" in q:  # link(): host/source cells, not a series
                counts = Counter(
                    (r["host"], r["source"])
                    for r in rows
                    if token in str(r.get("_raw", ""))
                    for _ in range(int(r["count"]))
                )
                return [{"host": h, "source": s, "count": c} for (h, s), c in counts.items()]
            span = int(re.search(r"span=(\d+)s", q).group(1))
            counts: Counter[int] = Counter()
            for row in rows:
                if token in str(row.get("_raw", "")):
                    counts[int(float(row["_time"])) // span * span] += int(row["count"])
            return [{"_time": float(t), "count": c} for t, c in counts.items()]
        return []


def test_template_rows_reduces_first_occurrence_server_side() -> None:
    search = _CountingSearch(_universe())

    rows = template_rows(search, "idx", float(T0), float(LEAD + HOUR), span=60)

    assert "| dedup host source punct sortby +_time" in search.queries[-1]
    assert len(rows) == TEMPLATES + 6  # one row per distinct (host, source, punct)
    first = {(r["host"], r["source"], r["punct"]): r for r in rows}
    assert int(first[("victim", "svc", " Victim !")]["count"]) == 6


def test_a_token_is_scanned_once_when_leads_share_the_series() -> None:
    search = _CountingSearch(_universe())
    lead = Lead(LEAD, "victim", 1.0, 1, [])
    cache: dict[tuple[str, int], dict[int, int]] = {}

    first = value_bursts(
        search, "idx", lead, float(T0), float(LEAD + HOUR), sample=50, top=10, cache=cache
    )
    second = value_bursts(
        search, "idx", lead, float(T0), float(LEAD + HOUR), sample=50, top=10, cache=cache
    )

    assert first == second
    assert first
    assert len(search.series_scans) == len(set(search.series_scans))
    assert search.series_scans.count(ATTACK) == 1


def test_hunt_still_ranks_the_novel_lead_through_the_reduced_scan() -> None:
    search = _CountingSearch(_universe())

    leads = hunt(search, "idx", float(T0), float(LEAD + HOUR))

    assert leads
    assert leads[0].host == "victim"
    assert leads[0].hour == LEAD
    assert leads[0].score > 0
    assert leads[0].bursts and leads[0].bursts[0].token == ATTACK


class _DiscoverySplunk:
    """A bounded fake over the universe: aggregates like tstats, honors max_results like the
    transport, and records the budget kind and cap of every query."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.seen: list[tuple[str, str, int | None, int]] = []

    def iter_post_bounded(
        self,
        q: str,
        start: float,
        end: float,
        *,
        timeout_seconds: float,
        max_results: int | None,
    ) -> list[dict[str, Any]]:
        out = self._rows(q, start, end)
        returned = out[: max_results or None]
        self.seen.append((q, query_budget_kind(q), max_results, len(returned)))
        return returned

    def _rows(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
        rows = [r for r in self.rows if start <= float(r["_time"]) < end]
        if q.startswith("| tstats min(_time)"):
            return [{"lo": min(float(r["_time"]) for r in rows), "hi": float(LEAD + HOUR)}]
        if q.startswith("| tstats count where index="):
            return self._tstats(q, rows)
        return self._search(q, rows)

    def _tstats(self, q: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        term = _term(q)
        matched = [r for r in rows if term is None or term in str(r.get("_raw", ""))]
        if "| dedup host source punct sortby +_time" in q:
            return _reduced(matched, int(re.search(r"span=(\d+)s", q).group(1)))
        if " by host source _time span=3600s" in q:
            return self._cells(matched, host=_clause(q, "host"), source=_clause(q, "source"))
        if " by _time span=1h | stats count" in q:
            return [{"count": len({int(float(r["_time"])) // HOUR for r in matched})}]
        if " by host source punct" in q:
            counts = Counter(
                (r["host"], r["source"], r["punct"])
                for r in matched
                for _ in range(int(r["count"]))
            )
            return [
                {"host": h, "source": s, "punct": p, "count": c} for (h, s, p), c in counts.items()
            ]
        if " by host source" in q:
            counts = Counter(
                (r["host"], r["source"]) for r in matched for _ in range(int(r["count"]))
            )
            return [{"host": h, "source": s, "count": c} for (h, s), c in counts.items()]
        if " by _time span=" in q:
            span = int(re.search(r"span=(\d+)s", q).group(1))
            counts: Counter[int] = Counter()
            for r in matched:
                for _ in range(int(r["count"])):
                    counts[int(float(r["_time"])) // span * span] += 1
            return [{"_time": float(t), "count": c} for t, c in counts.items()]
        return [{"count": sum(int(r["count"]) for r in matched)}]

    def _cells(
        self, rows: list[dict[str, Any]], host: str | None, source: str | None
    ) -> list[dict[str, Any]]:
        counts: Counter[tuple[str, str, int]] = Counter()
        for r in rows:
            if (host is None or r["host"] == host) and (source is None or r["source"] == source):
                counts[(r["host"], r["source"], int(float(r["_time"])) // HOUR * HOUR)] += int(
                    r["count"]
                )
        return [
            {"host": h, "source": s, "_time": float(t), "count": c}
            for (h, s, t), c in counts.items()
        ]

    def _search(self, q: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        host, source, punct = _clause(q, "host"), _clause(q, "source"), _clause(q, "punct")
        term, literal = _term(q), _literal(q)
        scopes = [
            (h, s, int(lo), int(hi))
            for h, s, lo, hi in re.findall(
                r'\(host="([^"]+)" source="([^"]+)" _time>=(\d+) _time<(\d+)\)', q
            )
        ]
        selected = [
            r
            for r in rows
            if (host is None or r["host"] == host)
            and (source is None or r["source"] == source)
            and (punct is None or r["punct"] == punct)
            and (term is None or term in str(r.get("_raw", "")))
            and (literal is None or literal in str(r.get("_raw", "")))
            and (
                not scopes
                or any(
                    r["host"] == h and r["source"] == s and lo <= float(r["_time"]) < hi
                    for h, s, lo, hi in scopes
                )
            )
        ]
        head = re.search(r"head (\d+)", q)
        if head:
            selected = selected[: int(head.group(1))]
        if "dedup 2 source punct" in q:
            seen: Counter[tuple[str, str]] = Counter()
            kept = []
            for r in selected:
                if seen[(r["source"], r["punct"])] < 2:
                    seen[(r["source"], r["punct"])] += 1
                    kept.append(r)
            selected = kept
        if "table _time host source punct _raw" in q:
            return [
                {
                    "_time": r["_time"],
                    "host": r["host"],
                    "source": r["source"],
                    "punct": r["punct"],
                    "_raw": r["_raw"],
                }
                for r in selected
            ]
        if "table _raw punct" in q:
            return [{"_raw": r["_raw"], "punct": r["punct"]} for r in selected]
        return [{"_raw": r["_raw"]} for r in selected]


def _clause(q: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]+)"', q)
    return m.group(1) if m else None


def _term(q: str) -> str | None:
    m = re.search(r'TERM\("([^"]+)"\)', q)
    return m.group(1) if m else None


def _literal(q: str) -> str | None:
    head = q.split("|", 1)[0]
    stripped = re.sub(r'\b(?:index|host|source|punct)="[^"]+"', "", head)
    stripped = re.sub(r'TERM\("[^"]+"\)', "", stripped)
    quoted = re.findall(r'"([^"]+)"', stripped)
    return quoted[-1] if quoted else None


def test_discovery_cardinality_over_the_evidence_budget_still_yields_leads(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    search = _DiscoverySplunk(_universe())
    job_id = "hunt-discovery1"

    jobs._run(job_id, search, "idx", float(T0), float(LEAD + HOUR), dig=1)

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
        if "eval r=random()" in q:
            assert cap == 2000, q
        elif q.endswith("by host source"):
            assert cap is None, q
        elif "table _time host source punct _raw" in q:
            assert isinstance(cap, int) and 0 < cap <= 5000, q


LINK_HOSTS = 1764  # BOTS-scale host count for one link() enumeration
LINK_ROWS = 12000


def _ranking_universe() -> list[dict[str, Any]]:
    """Three hosts, each with known-value priors and a 20000-event lead hour: ranking alone
    streams far more than the evidence budgets hold, and investigation's first raw read
    fills the events budget exactly."""
    rows: list[dict[str, Any]] = []
    for host in ("v1", "v2", "v3"):
        rows.append(
            {
                "_time": float(T0),
                "host": host,
                "source": "svc",
                "punct": "prior..",
                "count": 1,
                "_raw": "svc heartbeat ok",
            }
        )
        for hour in (1, 2, 3, 4):
            rows.append(
                {
                    "_time": float(T0 + hour * HOUR),
                    "host": host,
                    "source": "svc",
                    "punct": "prior..",
                    "count": 2,
                    "_raw": f"x={ATTACK} y=qqzz",
                }
            )
        for j in range(20000):
            rows.append(
                {
                    "_time": float(LEAD),
                    "host": host,
                    "source": "svc",
                    "punct": " Victim !",
                    "count": 1,
                    "_raw": f"user={ATTACK} cmd=runx note=val{j}",
                }
            )
    return rows


class _RankingSplunk(_DiscoverySplunk):
    """Serves link() with a host-count-scale enumeration; records every cap like the transport."""

    def _rows(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
        if q.endswith("by host source") and "TERM(" in q:
            return [
                {
                    "_time": float(LEAD),
                    "host": f"h{i % LINK_HOSTS}",
                    "source": f"s{i % 3}",
                    "count": 1,
                }
                for i in range(LINK_ROWS)
            ]
        return super()._rows(q, start, end)


def test_ranking_reads_never_starve_lead_persistence_or_evidence_budgets(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    search = _RankingSplunk(_ranking_universe())
    job_id = "hunt-ranking1"

    jobs._run(job_id, search, "idx", float(T0), float(LEAD + HOUR), dig=1)

    job = jobs.load(job_id)
    assert job is not None
    assert job["status"] == "PARTIAL"  # honest: investigation hit its evidence budget
    assert "budget" in str(job["progress"]["exhausted_reason"])
    # ranking streamed 12 full 2000-row samples and 12 link enumerations, yet leads persisted
    leads = job.get("leads", [])
    assert leads and leads[0]["host"] == "v1"
    assert ATTACK in {b["token"] for lead in leads for b in lead.get("bursts", [])}

    progress = job["progress"]
    assert progress["discovery_row_count"] >= 12 * 2000 + 12 * LINK_ROWS
    assert progress["event_count"] == 5000  # investigation spent exactly the evidence budget
    assert progress["cell_count"] <= progress["limits"]["cells"]

    sample_caps = {cap for q, _k, cap, _r in search.seen if "eval r=random()" in q}
    assert sample_caps == {2000}  # per-sample budget held for every ranking sample
    assert all(cap is None for q, _k, cap, _r in search.seen if q.endswith("by host source"))
    # the investigator's unheaded raw read was capped by the events budget, then refused
    seed_reads = [
        (cap, rows)
        for q, _k, cap, rows in search.seen
        if "table _raw punct" in q and "TERM(" not in q
    ]
    assert seed_reads and seed_reads[0] == (5000, 5000)
