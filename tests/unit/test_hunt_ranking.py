"""Ranking is repeatable, exact against an exhaustive series, and skips tokens that cannot place.

The search double is an in-memory event list. It is the regression net, not a live proof.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

from portal.modules.security.core.hunt.engine import (
    HOUR,
    Burst,
    Lead,
    _burst,
    _fill_series_cache,
    _token_series,
    hunt,
    peer_tokens,
    value_bursts,
)
from portal.modules.security.core.hunt.jobs import BudgetedSearch, HuntBudget

START = 20 * HOUR
LEAD = START + 4 * HOUR
INDEX = "idx"


def _md5(raw: str) -> str:
    return hashlib.md5(raw.encode()).hexdigest()


def _rows(
    token: str, hour: int, n: int, *, host: str = "h", punct: str = "id="
) -> list[dict[str, Any]]:
    return [
        {
            "_time": float(hour + 1),
            "host": host,
            "source": "svc",
            "punct": punct,
            "_raw": f"id={token}",
            "count": 1,
        }
        for _ in range(n)
    ]


def _universe(fillers: int, spikes: int, *, common: bool = False) -> list[dict[str, Any]]:
    """Spikes jump at the lead hour. Fillers stay at one event per hour. ``common`` is flat and loud."""
    rows: list[dict[str, Any]] = []
    hours = [START + i * HOUR for i in range(4)] + [LEAD]
    for s in range(spikes):
        token = f"spk{s}"
        for hour in hours[:-1]:
            rows += _rows(token, hour, 1)
        rows += _rows(token, LEAD, 8)
    for f in range(fillers):
        token = f"fil{f:02d}"
        for hour in hours:
            rows += _rows(token, hour, 1, punct="ff=")
    if common:
        for hour in hours:
            rows += _rows("common", hour, 30, punct="cc=")
    # one prior template and one novel template so hunt() has a lead to dig
    rows.append(
        {
            "_time": float(START),
            "host": "h",
            "source": "svc",
            "punct": "old..",
            "_raw": "svc heartbeat ok",
            "count": 1,
        }
    )
    rows.append(
        {
            "_time": float(LEAD),
            "host": "h",
            "source": "svc",
            "punct": "new!!",
            "_raw": "svc novel ok",
            "count": 1,
        }
    )
    return rows


class Ledger:
    """Answers the ranking queries. Search rows come back in md5(_raw) order, not insert order."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, float, float]] = []

    def iter_post(self, query: str, start: float, end: float) -> list[dict[str, Any]]:
        self.calls.append((query, start, end))
        rows = [row for row in self.rows if start <= float(row["_time"]) < end]
        if "eval _ht=" in query:
            return _packed(rows, query)
        if query.startswith("| tstats min(_time)"):
            return [
                {
                    "lo": min(float(r["_time"]) for r in rows),
                    "hi": max(float(r["_time"]) for r in rows),
                }
            ]
        if "dedup host source punct" in query:
            return _reduced(rows, int(re.search(r"span=(\d+)s", query).group(1)))
        if query.startswith("| tstats") and query.rstrip().endswith("by host"):
            return [
                {"host": host, "count": n} for host, n in Counter(r["host"] for r in rows).items()
            ]
        if (
            query.startswith("| tstats")
            and "TERM(" in query
            and query.rstrip().endswith("by host source")
        ):
            return _links(rows, _terms(query)[0])
        if query.startswith("| tstats") and "TERM(" in query and " by _time span=" in query:
            return _series(rows, _terms(query)[0], int(re.search(r"span=(\d+)s", query).group(1)))
        if query.startswith("search "):
            return self._search(query, rows)
        raise AssertionError(query)

    def _search(self, query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        host = _clause(query, "host")
        where = _where_punct(query)
        selected = []
        for row in rows:
            if host is not None and row["host"] != host:
                continue
            if where is not None and row["punct"] != where:
                continue
            if where is None and _search_punct_wildcard(query, row["punct"]):
                continue
            selected.append(row)
        selected.sort(
            key=lambda row: (_md5(str(row["_raw"])), float(row["_time"]), str(row["_raw"]))
        )
        head = re.search(r"head (\d+)", query)
        if head:
            selected = selected[: int(head.group(1))]
        return [{"_raw": row["_raw"], "punct": row["punct"]} for row in selected]


def _terms(query: str) -> list[str]:
    return [
        bytes(term, "utf-8").decode("unicode_escape")
        for term in re.findall(r'TERM\("((?:[^"\\]|\\.)*)"\)', query)
    ]


def _clause(query: str, name: str) -> str | None:
    match = re.search(rf'\b{name}="([^"]*)"', query)
    return match.group(1) if match else None


def _where_punct(query: str) -> str | None:
    match = re.search(r'\| where punct="((?:\\.|[^"\\])*)"', query)
    if not match:
        return None
    raw = match.group(1)
    out: list[str] = []
    i = 0
    while i < len(raw):
        if raw[i] == "\\" and i + 1 < len(raw):
            out.append(raw[i + 1])
            i += 2
        else:
            out.append(raw[i])
            i += 1
    return "".join(out)


def _search_punct_wildcard(query: str, punct: str) -> bool:
    """True when a search-clause punct= should reject this row (wildcard semantics)."""
    head = query.split("|", 1)[0]
    match = re.search(r'\bpunct="([^"]*)"', head)
    if not match:
        return False
    pattern = "^" + re.escape(match.group(1)).replace(r"\*", ".*") + "$"
    return re.match(pattern, punct) is None


def _packed(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    span = int(re.search(r"span=(\d+)s", query).group(1))
    out = []
    for i, term in enumerate(_terms(query)):
        counts: Counter[int] = Counter()
        for row in rows:
            if term in str(row["_raw"]):
                counts[int(float(row["_time"])) // span * span] += int(row["count"])
        if not counts:
            continue
        cells = [f"{bucket}:{count}" for bucket, count in sorted(counts.items())]
        out.append({"_ht": str(i), "_hn": str(len(cells)), "_hs": ",".join(cells)})
    return out


def _series(rows: list[dict[str, Any]], term: str, span: int) -> list[dict[str, Any]]:
    counts: Counter[int] = Counter()
    for row in rows:
        if term in str(row["_raw"]):
            counts[int(float(row["_time"])) // span * span] += int(row["count"])
    return [{"_time": float(bucket), "count": count} for bucket, count in sorted(counts.items())]


def _links(rows: list[dict[str, Any]], term: str) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        if term in str(row["_raw"]):
            counts[(row["host"], row["source"])] += int(row["count"])
    return [
        {"host": host, "source": source, "count": count} for (host, source), count in counts.items()
    ]


def _reduced(rows: list[dict[str, Any]], span: int) -> list[dict[str, Any]]:
    first: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: float(item["_time"])):
        key = (row["host"], row["source"], row["punct"])
        if key not in first:
            bucket = dict(row)
            bucket["_time"] = float(int(float(row["_time"])) // span * span)
            first[key] = bucket
    return list(first.values())


def _wide_terms(search: Ledger, span: int = HOUR) -> list[str]:
    terms: list[str] = []
    for query, start, end in search.calls:
        if end - start <= span:
            continue
        if "TERM(" in query and " by _time span=" in query:
            terms.extend(_terms(query))
    return terms


def _kept(bursts: list[Burst]) -> list[tuple[str, float]]:
    return [(burst.token, burst.z) for burst in bursts]


def _exhaustive(
    rows: list[dict[str, Any]], tokens: list[str], keep: int
) -> list[tuple[str, float]]:
    search = Ledger(rows)
    cache: dict[tuple[str, int], dict[int, int]] = {}
    _fill_series_cache(cache, search, INDEX, tokens, float(START), float(LEAD + HOUR), HOUR)
    bursts = []
    for token in tokens:
        burst = _burst(token, LEAD, cache[(token, HOUR)])
        if burst is not None:
            bursts.append(burst)
    bursts.sort(key=lambda burst: (-burst.z, burst.token))
    return _kept(bursts[:keep])


def _census_tokens(rows: list[dict[str, Any]]) -> list[str]:
    from portal.modules.security.core.hunt.engine import _census_tokens as tokens

    lead_rows = [
        row for row in rows if LEAD <= float(row["_time"]) < LEAD + HOUR and row["host"] == "h"
    ]
    return list(tokens(lead_rows))


def test_two_runs_and_a_warm_cache_return_the_same_leads() -> None:
    rows = _universe(fillers=6, spikes=5)
    first = hunt(Ledger(rows), INDEX, float(START), float(LEAD + HOUR), sample=500)
    second = hunt(Ledger(list(reversed(rows))), INDEX, float(START), float(LEAD + HOUR), sample=500)
    assert [
        (lead.host, lead.hour, lead.span, lead.score, _kept(lead.bursts)) for lead in first
    ] == [(lead.host, lead.hour, lead.span, lead.score, _kept(lead.bursts)) for lead in second]

    search = Ledger(rows)
    lead = Lead(LEAD, "h", 1.0, 1, [], span=HOUR)
    cache: dict[tuple[str, int], dict[int, int]] = {}
    hours: dict[tuple[str, int, int], int] = {}
    cold = value_bursts(
        search,
        INDEX,
        lead,
        float(START),
        float(LEAD + HOUR),
        sample=500,
        top=60,
        cache=cache,
        keep=5,
        hour_cache=hours,
    )
    wide = len(_wide_terms(search))
    warm = value_bursts(
        search,
        INDEX,
        lead,
        float(START),
        float(LEAD + HOUR),
        sample=500,
        top=60,
        cache=cache,
        keep=5,
        hour_cache=hours,
    )
    assert _kept(cold) == _kept(warm)
    assert _wide_terms(search)[wide:] == []


def test_tied_scores_order_by_hour_then_host_then_span() -> None:
    def host_rows(host: str, token: str) -> list[dict[str, Any]]:
        rows = []
        for hour in (START, START + HOUR, START + 2 * HOUR, START + 3 * HOUR):
            rows += _rows(token, hour, 1, host=host)
        rows += _rows(token, LEAD, 8, host=host)
        rows.append(
            {
                "_time": float(START),
                "host": host,
                "source": "svc",
                "punct": "old..",
                "_raw": "svc heartbeat ok",
                "count": 1,
            }
        )
        rows.append(
            {
                "_time": float(LEAD),
                "host": host,
                "source": "svc",
                "punct": "new!!",
                "_raw": "svc novel ok",
                "count": 1,
            }
        )
        return rows

    # hB is inserted first. The total order still places hA ahead when the scores tie.
    rows = host_rows("hB", "spkB") + host_rows("hA", "spkA")
    leads = [
        lead
        for lead in hunt(Ledger(rows), INDEX, float(START), float(LEAD + HOUR), sample=500)
        if lead.score > 0 and lead.hour == LEAD and lead.span == HOUR
    ]
    assert [lead.host for lead in leads[:2]] == ["hA", "hB"]
    assert leads[0].score == leads[1].score


def test_efficient_bursts_match_the_exhaustive_series() -> None:
    rows = _universe(fillers=40, spikes=5, common=True)
    tokens = _census_tokens(rows)
    assert len(tokens) > 5  # more candidates than the kept set
    search = Ledger(rows)
    lead = Lead(LEAD, "h", 1.0, 1, [], span=HOUR)
    efficient = value_bursts(
        search, INDEX, lead, float(START), float(LEAD + HOUR), sample=500, top=3, keep=5
    )
    assert _kept(efficient) == _exhaustive(rows, tokens, 5)
    assert [token for token, _z in _kept(efficient)] == [f"spk{s}" for s in range(5)]


def test_full_history_requests_follow_contenders_not_filler_tokens() -> None:
    base = Ledger(_universe(fillers=10, spikes=5))
    value_bursts(
        base,
        INDEX,
        Lead(LEAD, "h", 1.0, 1, [], span=HOUR),
        float(START),
        float(LEAD + HOUR),
        sample=500,
        top=3,
        keep=5,
    )
    base_terms = _wide_terms(base)
    assert set(base_terms) == {f"spk{s}" for s in range(5)}

    more = Ledger(_universe(fillers=40, spikes=5))
    value_bursts(
        more,
        INDEX,
        Lead(LEAD, "h", 1.0, 1, [], span=HOUR),
        float(START),
        float(LEAD + HOUR),
        sample=500,
        top=3,
        keep=5,
    )
    assert set(_wide_terms(more)) == set(base_terms)

    extra = Ledger(_universe(fillers=10, spikes=7))
    value_bursts(
        extra,
        INDEX,
        Lead(LEAD, "h", 1.0, 1, [], span=HOUR),
        float(START),
        float(LEAD + HOUR),
        sample=500,
        top=3,
        keep=5,
    )
    assert set(_wide_terms(extra)) == {f"spk{s}" for s in range(7)}


def test_a_loud_flat_token_is_still_scanned_because_its_bound_can_win() -> None:
    rows = _universe(fillers=4, spikes=5, common=True)
    search = Ledger(rows)
    kept = value_bursts(
        search,
        INDEX,
        Lead(LEAD, "h", 1.0, 1, [], span=HOUR),
        float(START),
        float(LEAD + HOUR),
        sample=500,
        top=3,
        keep=5,
    )
    assert "common" in _wide_terms(search)
    assert "common" not in {token for token, _z in _kept(kept)}
    assert _kept(kept) == _exhaustive(rows, _census_tokens(rows), 5)


def test_peer_history_star_and_quotes_match_only_the_literal_shape() -> None:
    star = "a*b"
    quoted = 'say "hi" *'
    rows = [
        {
            "_time": float(LEAD),
            "host": "h",
            "punct": star,
            "_raw": "left=self",
            "count": 1,
            "source": "svc",
        },
        {
            "_time": float(START),
            "host": "h",
            "punct": star,
            "_raw": "left=onlystar",
            "count": 1,
            "source": "svc",
        },
        {
            "_time": float(START),
            "host": "h",
            "punct": "axxb",
            "_raw": "left=fromwild",
            "count": 1,
            "source": "svc",
        },
        {
            "_time": float(LEAD),
            "host": "h",
            "punct": quoted,
            "_raw": "left=self",
            "count": 1,
            "source": "svc",
        },
        {
            "_time": float(START),
            "host": "h",
            "punct": quoted,
            "_raw": "left=quotedpeer",
            "count": 1,
            "source": "svc",
        },
        {
            "_time": float(START),
            "host": "h",
            "punct": 'say "hi" extra',
            "_raw": "left=notquote",
            "count": 1,
            "source": "svc",
        },
    ]
    search = Ledger(rows)
    lead = Lead(LEAD, "h", 1.0, 1, [], span=HOUR)
    peers = peer_tokens(search, INDEX, lead, Burst("self", 2, 1.0, 2, 1.0), float(START))
    history = [query for query, _s, _e in search.calls if "where punct=" in query]
    assert any(r'where punct="a*b"' in query for query in history)
    assert any(r'where punct="say \"hi\" *"' in query for query in history)
    assert peers == ["onlystar", "quotedpeer"]
    assert "fromwild" not in peers
    assert "notquote" not in peers


def test_finer_series_rolls_up_without_a_second_history_scan() -> None:
    rows = _rows("spk0", START, 2) + _rows("spk0", START + 10 * 60, 3) + _rows("spk0", LEAD, 8)
    search = Ledger(rows)
    cache: dict[tuple[str, int], dict[int, int]] = {}
    _fill_series_cache(cache, search, INDEX, ["spk0"], float(START), float(LEAD + HOUR), 60)
    before = len(search.calls)
    _fill_series_cache(cache, search, INDEX, ["spk0"], float(START), float(LEAD + HOUR), 600)
    assert len(search.calls) == before
    direct = _token_series(Ledger(rows), INDEX, "spk0", float(START), float(LEAD + HOUR), 600)
    assert cache[("spk0", 600)] == direct


def test_progress_records_request_kind_counts_and_seconds() -> None:
    class _Bounded:
        def iter_post_bounded(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            return [{"_ht": "0", "_hn": "0", "_hs": ""}]

    budget = HuntBudget(
        {"query_seconds": 5, "job_seconds": 10, "requests": 5, "cells": 10, "events": 10}
    )
    search = BudgetedSearch(_Bounded(), budget)
    query = (
        '| tstats count where index="idx" TERM("spk0") by _time span=3600s '
        '| eval _hc=printf("%d:%d",_time,count) | eval _ht="0"'
    )
    assert list(search.iter_post(query, float(LEAD), float(LEAD + HOUR)))
    kinds = budget.snapshot()["request_kinds"]
    assert kinds["hour_screen"]["requests"] == 1
    assert kinds["hour_screen"]["seconds"] >= 0
    assert budget.snapshot()["ranking_coverage_complete"] is True
