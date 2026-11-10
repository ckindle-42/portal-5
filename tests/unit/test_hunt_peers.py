"""Peer-relative bursts: a value counts only if it stands out from the values in its own slot.

The Search protocol is mocked over a fixed event list -- no network.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from portal.modules.security.core.hunt.engine import (
    HOUR,
    Burst,
    Lead,
    _burst,
    _token_series,
    fold_shared_values,
    peer_bursts,
    peer_tokens,
    rank_coherence,
)

BASE = 20 * HOUR  # start of the prior window
H = BASE + 9 * HOUR  # the lead bucket
PUNCT = "=... =..."
DST = "10.9.9.9"


class FakeSearch:
    """Only the query shapes peer discovery and token series issue, over fixed events."""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events
        self.queries: list[str] = []

    def iter_post(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
        self.queries.append(q)
        rows = [e for e in self.events if start <= float(e["_time"]) < end]
        if q.startswith("| tstats count where index="):
            return self._tstats(q, rows)
        if q.startswith("search index="):
            return self._search(q, rows)
        raise AssertionError(f"FakeSearch: unhandled query {q!r}")

    def _tstats(self, q: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        token = _term(q)
        span = int(re.search(r"span=(\d+)s", q).group(1))
        counts = Counter(
            int(float(e["_time"])) // span * span
            for e in rows
            if token is None or token in e["_raw"]
        )
        return [{"_time": t, "count": n} for t, n in counts.items()]

    def _search(self, q: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        host, punct, token = _clause(q, "host"), _clause(q, "punct"), _term(q)
        selected = [
            e
            for e in rows
            if (host is None or e["host"] == host)
            and (punct is None or e["punct"] == punct)
            and (token is None or token in e["_raw"])
        ]
        if "table _raw punct" in q:
            return [{"_raw": e["_raw"], "punct": e["punct"]} for e in selected]
        if "table _raw" in q:
            return [{"_raw": e["_raw"]} for e in selected]
        raise AssertionError(f"FakeSearch: unhandled search {q!r}")


def _clause(q: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]+)"', q)
    return m.group(1) if m else None


def _term(q: str) -> str | None:
    m = re.search(r'TERM\("([^"]+)"\)', q)
    return m.group(1) if m else None


def _events(host: str, value: str, hours: dict[int, int]) -> list[dict[str, Any]]:
    return [
        {"_time": t + 60, "host": host, "punct": PUNCT, "_raw": f"src={value} dst={DST}"}
        for t, n in hours.items()
        for _ in range(n)
    ]


def _rhythm() -> list[dict[str, Any]]:
    """Two values share one rhythm on different hosts; a third has peers that stay flat."""
    prior = {BASE + i * HOUR: 2 for i in range(4)}
    shared = {**prior, H: 10}
    alone = {**prior, H: 10}
    flat = {**prior, H: 2}
    events = _events("h1", "10.0.0.1", shared)
    events += _events("h2", "10.1.0.1", alone)
    for value in ("10.0.0.2", "10.0.0.3", "10.0.0.4"):
        events += _events("h1", value, shared)
    for value in ("10.1.0.2", "10.1.0.3", "10.1.0.4"):
        events += _events("h2", value, flat)
    return events


def _lead(host: str, *, score: float = 0.0) -> Lead:
    return Lead(H, host, 1.0, 2, [], score=score)


def _lead_with_burst(host: str, token: str, *, score: float = 0.0, span: int = HOUR) -> Lead:
    return Lead(
        H,
        host,
        1.0,
        2,
        [],
        bursts=[Burst(token, 2, 0.5, 2, 3.0)],
        score=score,
        span=span,
    )


def _burst_of(search: FakeSearch, token: str) -> Burst:
    burst = _burst(token, H, _token_series(search, "idx", token, BASE, H + HOUR))
    assert burst is not None
    return burst


def test_peer_relative_burst_ranks_alone_above_shared_rhythm() -> None:
    search = FakeSearch(_rhythm())
    shared = _lead("h1")
    shared.bursts = [_burst_of(search, "10.0.0.1")]
    alone = _lead("h2")
    alone.bursts = [_burst_of(search, "10.1.0.1")]

    peer_bursts(search, "idx", shared, BASE, H + HOUR)
    peer_bursts(search, "idx", alone, BASE, H + HOUR)

    assert shared.bursts[0].z == alone.bursts[0].z
    assert abs(shared.bursts[0].peer_z) < 0.1
    assert shared.bursts[0].peers == 3
    assert alone.bursts[0].peer_z > 2.5
    assert alone.bursts[0].peers == 3

    rank_coherence([shared, alone])
    assert alone.score > shared.score


def test_peer_tokens_take_the_same_slot_on_the_same_host() -> None:
    search = FakeSearch(_rhythm())
    lead = _lead("h1")
    lead.bursts = [_burst_of(search, "10.0.0.1")]

    peers = peer_tokens(search, "idx", lead, lead.bursts[0], BASE)

    token_query, prior_query = search.queries[-2:]
    assert token_query.startswith('search index=idx host="h1" TERM("10.0.0.1")')
    assert token_query.endswith("| head 200 | table _raw punct")
    assert 'host="h1" punct="=... =..."' in prior_query
    assert peers == ["10.0.0.2", "10.0.0.3", "10.0.0.4"]
    assert "10.0.0.1" not in peers
    assert DST not in peers


def test_fewer_than_two_peers_leaves_the_raw_z() -> None:
    prior = {BASE + i * HOUR: 2 for i in range(4)}
    events = _events("h3", "10.2.0.1", {**prior, H: 10})
    events += _events("h3", "10.2.0.2", {**prior, H: 2})
    search = FakeSearch(events)
    lead = _lead("h3")
    lead.bursts = [_burst_of(search, "10.2.0.1")]

    peer_bursts(search, "idx", lead, BASE, H + HOUR)

    assert lead.bursts[0].peers == 0
    assert lead.bursts[0].peer_z == lead.bursts[0].z


def test_coherence_uses_peer_z_not_raw_z() -> None:
    loud = Lead(H, "h1", 1.0, 2, [], bursts=[Burst("a", 20, 1.0, 3, 9.0, peer_z=0.1)])
    quiet = Lead(H, "h2", 1.0, 2, [], bursts=[Burst("b", 2, 1.0, 3, 1.0, peer_z=8.0)])

    rank_coherence([loud, quiet])

    assert quiet.score > loud.score


def test_shared_top_value_folds_across_hosts_only() -> None:
    first = _lead_with_burst("h1", "shared", score=0.6)
    same_value = _lead_with_burst("h2", "shared", score=0.5)
    other = _lead_with_burst("h3", "other", score=0.4)
    same_host = _lead_with_burst("h1", "shared", score=0.3)

    out = fold_shared_values([first, same_value, other, same_host])

    assert out == [first, other, same_host, same_value]


def test_shared_value_outside_the_bucket_does_not_fold() -> None:
    first = _lead_with_burst("h1", "shared", score=0.6)
    later = _lead_with_burst("h2", "shared", score=0.5)
    later.hour = H + 2 * HOUR

    assert fold_shared_values([first, later]) == [first, later]
