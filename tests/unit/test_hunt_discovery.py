"""Indexed discovery stays exact at environment scale: the server reduces, the client reasons.

The live lab returns 1.8M by-hour template cells for one index; the first-occurrence reduction
in ``template_rows`` must preserve the novelty scores exactly while discovery streams far more
rows than the evidence budgets could ever hold.
"""

from __future__ import annotations

import re
import threading
import time
from collections import Counter
from typing import Any

import pytest

from portal.modules.security.core.hunt import engine, jobs
from portal.modules.security.core.hunt.engine import (
    HOUR,
    PACK_PARENTS,
    SERIES_BATCH,
    TEMPLATE_HOST_GROUP,
    Lead,
    _fill_series_cache,
    _packed_series,
    _token_series,
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


def _packed_rows(rows: list[dict[str, Any]], q: str) -> list[dict[str, Any]]:
    """Evaluate a packed-series query over universe rows like the append subsearches would:
    one packed row per TERM in order (term id, declared cell count, serialized cells), and no
    row at all for a term with no matching events."""
    terms = re.findall(r'TERM\("((?:[^"\\]|\\.)*)"\)', q)
    span = int(re.search(r"span=(\d+)s", q).group(1))
    out = []
    for i, term in enumerate(terms):
        counts: Counter[int] = Counter()
        for r in rows:
            if term in str(r.get("_raw", "")):
                counts[int(float(r["_time"])) // span * span] += int(r["count"])
        if not counts:
            continue
        cells = [f"{t}:{c}" for t, c in counts.items()]
        out.append({"_ht": str(i), "_hn": str(len(cells)), "_hs": ",".join(cells)})
    return out


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
        if 'eval _ht="' in q:
            terms = re.findall(r'TERM\("((?:[^"\\]|\\.)*)"\)', q)
            self.series_scans.extend(terms)
            return _packed_rows(rows, q)
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
        packed = 'eval _ht="' in q
        term = None if packed else _term(q)  # each packed subsearch scans the full window
        matched = [r for r in rows if term is None or term in str(r.get("_raw", ""))]
        if "| dedup host source punct sortby +_time" in q:
            return _reduced(matched, int(re.search(r"span=(\d+)s", q).group(1)))
        if packed:
            return _packed_rows(matched, q)
        if q.rstrip().endswith("by host"):
            counts = Counter(r["host"] for r in matched)
            return [{"host": h, "count": c} for h, c in counts.items()]
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
    assert job["status"] in {"COMPLETE", "PARTIAL"}
    # ranking streamed 12 full 2000-row samples and 12 link enumerations, yet leads persisted
    leads = job.get("leads", [])
    assert leads and leads[0]["host"] == "v1"
    assert ATTACK in {b["token"] for lead in leads for b in lead.get("bursts", [])}

    progress = job["progress"]
    assert progress["discovery_row_count"] >= 12 * 2000 + 12 * LINK_ROWS
    assert progress["event_count"] <= progress["limits"]["events"]
    assert progress["cell_count"] <= progress["limits"]["cells"]

    sample_caps = {cap for q, _k, cap, _r in search.seen if "eval r=random()" in q}
    assert sample_caps == {2000}  # per-sample budget held for every ranking sample
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


def test_packed_series_matches_per_token_scans_exactly() -> None:
    search = _CountingSearch(_universe())
    tokens = [ATTACK, "user", "cmd", "runx"]

    packed = _packed_series(search, "idx", tokens, float(T0), float(LEAD + HOUR), HOUR)

    assert packed is not None
    for token in tokens:
        single = _token_series(search, "idx", token, float(T0), float(LEAD + HOUR), HOUR)
        assert packed[token] == single, token


def _batch_universe() -> list[dict[str, Any]]:
    """24 distinct present tokens over three hourly rows: enough terms for three packs."""
    raw = " ".join(f"tkn{i:02d}x=v{i:02d}" for i in range(24))
    return [
        {
            "_time": float(T0 + h * HOUR),
            "host": "h",
            "source": "s",
            "punct": "p..",
            "count": 1,
            "_raw": raw,
        }
        for h in range(3)
    ]


def test_series_requests_scale_with_batch_count_not_term_count() -> None:
    search = _CountingSearch(_batch_universe())
    tokens = [f"tkn{i:02d}x" for i in range(24)]
    cache: dict[tuple[str, int], dict[int, int]] = {}

    _fill_series_cache(cache, search, "idx", tokens, float(T0), float(T0 + 3 * HOUR), HOUR)

    packed = [q for q in search.queries if 'eval _ht="' in q]
    singles = [q for q in search.queries if "TERM(" in q and 'eval _ht="' not in q]
    assert len(packed) == (24 + SERIES_BATCH - 1) // SERIES_BATCH  # ceil(24/8) = 3 jobs
    assert singles == []
    for token in tokens:
        assert cache[(token, HOUR)] == _token_series(
            search, "idx", token, float(T0), float(T0 + 3 * HOUR), HOUR
        )


class _PeakSearch(_CountingSearch):
    """Counts packed parent jobs in flight while each one holds the slot briefly."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        super().__init__(rows)
        self._active = 0
        self.peak = 0
        self._lock = threading.Lock()

    def iter_post(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
        if 'eval _ht="' not in q:
            return super().iter_post(q, start, end)
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)
        try:
            time.sleep(0.1)
            return super().iter_post(q, start, end)
        finally:
            with self._lock:
                self._active -= 1


def test_parallel_parent_packs_stay_inside_the_lab_child_concurrency() -> None:
    # Append children run serially, so the live peak is parent + one child, not batch * parents.
    assert 2 * PACK_PARENTS <= engine.LAB_SEARCH_CONCURRENCY
    search = _CountingSearch(_batch_universe())
    cache: dict[tuple[str, int], dict[int, int]] = {}
    tokens = [f"tkn{i:02d}x" for i in range(16)]

    _fill_series_cache(cache, search, "idx", tokens, float(T0), float(T0 + 3 * HOUR), HOUR)

    assert len([q for q in search.queries if 'eval _ht="' in q]) == 2  # one wave, two parents
    assert len(cache) == 16

    wide = _PeakSearch(_batch_universe())
    wide_cache: dict[tuple[str, int], dict[int, int]] = {}
    wide_tokens = [f"tkn{i:02d}x" for i in range(SERIES_BATCH * (PACK_PARENTS + 1))]
    _fill_series_cache(wide_cache, wide, "idx", wide_tokens, float(T0), float(T0 + 3 * HOUR), HOUR)

    packed = [q for q in wide.queries if 'eval _ht="' in q]
    assert len(packed) == PACK_PARENTS + 1  # one extra batch proves the wave split
    assert 1 < wide.peak <= PACK_PARENTS


def _apply_pack_corruption(out: list[dict[str, Any]], corrupt: str) -> list[dict[str, Any]]:
    """One malformed packed term, the way truncation, duplicates, and bad ids arrive."""
    if corrupt == "missing":
        return [row for row in out if row["_ht"] != "1"]
    for row in out:
        if row["_ht"] != "1":
            continue
        cells = str(row["_hs"]).split(",")
        if corrupt == "truncated":
            row["_hn"] = str(len(cells) + 3)  # declares more cells than serialized
        elif corrupt == "duplicate":
            row["_hs"] = ",".join(cells + [cells[0]])
            row["_hn"] = str(len(cells))  # declares the deduped count
        elif corrupt == "negative":
            bucket, _count = cells[0].split(":")
            cells[0] = f"{bucket}:-1"
            row["_hs"] = ",".join(cells)
        elif corrupt == "bad-id":
            row["_ht"] = "99"
    return out


class _LossySearch(_CountingSearch):
    """Corrupts packed payloads the way real truncation/limits would, per term id."""

    def __init__(self, rows: list[dict[str, Any]], corrupt: str) -> None:
        super().__init__(rows)
        self.corrupt = corrupt

    def iter_post(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
        self.queries.append(q)
        rows = [r for r in self.rows if start <= float(r["_time"]) < end]
        if 'eval _ht="' in q:
            return _apply_pack_corruption(_packed_rows(rows, q), self.corrupt)
        return super().iter_post(q, start, end)


def test_censored_pack_falls_back_to_exact_singles_and_a_spent_budget_does_not() -> None:
    tokens = [f"tkn{i:02d}x" for i in range(SERIES_BATCH)]
    window = (float(T0), float(T0 + 3 * HOUR))

    class _Censor(_CountingSearch):
        def iter_post(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
            if 'eval _ht="' in q:
                self.queries.append(q)
                raise jobs.HuntCoverageError("subsearch truncated", sid="sid-pack")
            return super().iter_post(q, start, end)

    censored = _Censor(_batch_universe())
    cache: dict[tuple[str, int], dict[int, int]] = {}
    _fill_series_cache(cache, censored, "idx", tokens, *window, HOUR)
    assert any('eval _ht="' in q for q in censored.queries)
    singles = [q for q in censored.queries if "TERM(" in q and 'eval _ht="' not in q]
    assert len(singles) == len(tokens)
    exact = _CountingSearch(_batch_universe())
    for token in tokens:
        assert cache[(token, HOUR)] == _token_series(exact, "idx", token, *window, HOUR)

    class _Spent(_CountingSearch):
        def iter_post(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
            if 'eval _ht="' in q:
                self.queries.append(q)
                raise engine.SearchBudgetExceededError("result_budget_exhausted")
            return super().iter_post(q, start, end)

    spent = _Spent(_batch_universe())
    with pytest.raises(engine.SearchBudgetExceededError):
        _fill_series_cache({}, spent, "idx", tokens, *window, HOUR)
    assert spent.queries
    assert all('eval _ht="' in q for q in spent.queries)


def test_corrupt_packed_records_fall_back_and_the_cache_stays_exact() -> None:
    tokens = [ATTACK, "user", "cmd", "runx"]
    exact = _CountingSearch(_universe())
    for corrupt in ("missing", "truncated", "duplicate", "negative", "bad-id"):
        cache: dict[tuple[str, int], dict[int, int]] = {}
        lossy = _LossySearch(_universe(), corrupt)
        _fill_series_cache(cache, lossy, "idx", tokens, float(T0), float(LEAD + HOUR), HOUR)
        for token in tokens:
            assert cache[(token, HOUR)] == _token_series(
                exact, "idx", token, float(T0), float(LEAD + HOUR), HOUR
            ), f"{corrupt}:{token}"


def test_packed_query_declares_subsearch_limits_and_escapes_terms() -> None:
    class _CapSearch(_CountingSearch):
        query_allowance_seconds = 45.0

    search = _CapSearch(_universe())
    weird = 'a"b\\c'

    _packed_series(search, "idx", [weird, "plain"], float(T0), float(LEAD + HOUR), HOUR)

    query = search.queries[-1]
    assert "maxtime=105" in query  # adapter allowance 45s + 60s: longer than the parent job
    assert "maxout=2" in query  # explicit, and at least one packed row
    assert 'TERM("a\\"b\\\\c")' in query  # the escaped term reaches TERM() intact


class _PartitionSearch:
    """Answers the host inventory and evaluates each host-partitioned template query."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.queries: list[str] = []

    def iter_post(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
        self.queries.append(q)
        rows = [r for r in self.rows if start <= float(r["_time"]) < end]
        if q.rstrip().endswith("by host"):
            counts = Counter(r["host"] for r in rows)
            return [{"host": h, "count": c} for h, c in counts.items()]
        if "| dedup host source punct sortby +_time" in q:
            head = q.split("by host")[0]
            hosts = set(re.findall(r'host="([^"]+)"', head))
            if hosts:
                rows = [r for r in rows if r["host"] in hosts]
            return _reduced(rows, int(re.search(r"span=(\d+)s", q).group(1)))
        raise AssertionError(f"unhandled query {q!r}")


def test_host_partition_rows_stay_exact_across_zooms_on_a_large_inventory() -> None:
    rows: list[dict[str, Any]] = []
    for h in range(150):  # forces ceil(150/64) = 3 host groups per zoom
        host = f"h{h}"
        rows.append(
            {
                "_time": float(T0),
                "host": host,
                "source": "s",
                "punct": "p0..",
                "count": 1,
                "_raw": f"{host} heartbeat",
            }
        )
        rows.append(
            {
                "_time": float(T0 + (h % 40) * HOUR),
                "host": host,
                "source": "s",
                "punct": f"p{h}..",
                "count": 2,
                "_raw": f"{host} event {h}",
            }
        )
    window = (float(T0), float(LEAD + HOUR))

    for span in (60, HOUR, DAY):
        search = _PartitionSearch(rows)
        partitioned = template_rows(search, "idx", *window, span=span)
        partitions = [q for q in search.queries if "| dedup host source punct" in q]
        assert len(partitions) == (150 + TEMPLATE_HOST_GROUP - 1) // TEMPLATE_HOST_GROUP
        seen_hosts = [set(re.findall(r'host="([^"]+)"', q.split("by host")[0])) for q in partitions]
        assert set().union(*seen_hosts) == {f"h{h}" for h in range(150)}
        assert sum(len(group) for group in seen_hosts) == 150  # no host in two groups
        exact = _reduced([r for r in rows if window[0] <= float(r["_time"]) < window[1]], span)

        def keyed(row: dict[str, Any]) -> tuple[str, str, str]:
            return (row["host"], row["source"], row["punct"])

        assert {keyed(r): (r["_time"], r["count"]) for r in partitioned} == {
            keyed(r): (r["_time"], r["count"]) for r in exact
        }


def _partial_universe() -> list[dict[str, Any]]:
    """One host whose lead hour holds 10000 events of six common recurring tokens."""
    rows = [
        {
            "_time": float(T0),
            "host": "solo",
            "source": "svc",
            "punct": "p0..",
            "count": 1,
            "_raw": "solo heartbeat ok",
        }
    ]
    for _j in range(10000):
        rows.append(
            {
                "_time": float(LEAD),
                "host": "solo",
                "source": "svc",
                "punct": "s1..",
                "count": 1,
                "_raw": "tok1=A tok2=B tok3=C tok4=D tok5=E tok6=F",
            }
        )
    return rows


def test_partial_current_case_survives_work_exhaustion(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    search = _DiscoverySplunk(_partial_universe())
    job_id = "hunt-partial1"

    jobs._run(job_id, search, "idx", float(T0), float(LEAD + HOUR), dig=1, budgets={"events": 2000})

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


class _CensoredNeighborhood(_DiscoverySplunk):
    """Every look-around query is finalized early by the server: censored, not failed."""

    def iter_post_bounded(
        self, q: str, start: float, end: float, **kw: Any
    ) -> list[dict[str, Any]]:
        if "| dedup 2 source punct" in q:
            exc = RuntimeError("search finalized before completion")
            exc.censored = True  # type: ignore[attr-defined]
            raise exc
        return super().iter_post_bounded(q, start, end, **kw)


def test_a_censored_lookup_censors_itself_and_the_case_continues(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "_ROOT", tmp_path)
    jobs._run(
        "hunt-cens1",
        _CensoredNeighborhood(_universe()),
        "idx",
        float(T0),
        float(LEAD + HOUR),
        dig=1,
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
