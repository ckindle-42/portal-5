"""bully.investigation_pivot -- reconstruct an incident the way a defender does.

The search model this replaces is `search index=X earliest=0 latest=now |
head 20000`: an unbounded scan truncated arbitrarily. It is simultaneously
too broad (asks Splunk for 226M events across all time, discards all but
20k) and too narrow (what survives is one arbitrary slab with no
investigative structure). It also defeats the one thing Splunk is built to
optimise -- time-bucket pruning -- which is why the T.3 run managed 53
records/sec and would need ~61 days to touch the corpus once.

How defenders actually work, from the IR literature:

  * **The anchor is where you start searching, not where the incident
    started.** Incidents are discovered at the symptom stage -- a ransom
    note, a coin miner alert, anomalous outbound traffic -- and the
    investigator works BACKWARD from visible damage to initial access.
  * **Expansion is bidirectional and asymmetric.** Backward pivots reveal
    delivery, authentication, staging, parent processes; forward pivots
    reveal execution, persistence, lateral movement, collection,
    exfiltration. Backward reaches further than forward: a documented
    pattern is "all operations by this user in the preceding 24 hours, and
    in the superseding 1 hour".
  * **Pivoting is recursive across ENTITIES.** IP -> process -> parent
    process -> user -> login time. Results of one query become the input to
    the next. This is what links stages that share NO identifier: the AWS
    IAM abuse and the endpoint coin miner in BOTSv3 are one incident, but
    `web_admin` and `BSTOLL-L` are different entities. Only a pivot chain
    connects them.
  * **An investigation is a bounded body of work.** Nobody reads all the
    logs. They read what the pivots reach, and they stop.

The corpus this must run against is defined, which is why it can be tested:
BOTSv3 is a single day -- 20 Aug 2018, most activity 0900-1600, ~2.03M
events -- a multi-stage Taedonggang intrusion against Frothly crossing
`aws:cloudtrail` (IAM abuse, public S3), `symantec:ep:*` (Monero miner),
Windows endpoints, VPN and Linux. BOTSv1 (2016) and v2 (2017) are separate
scenarios. So the backward reach for this corpus is hours-to-a-day, not the
14-day median dwell of the real world -- and every query must be bounded
INSIDE the corpus's own time range, which is also where injected cousins
must live. Cousins shipped with "now" timestamps sit ~8 years away from the
haystack they were meant to hide in, and no time-bounded investigation can
ever reach them.

Emits `QueryIntent`-shaped plans; execution is the caller's. Pure planning
and assembly (COLD): no I/O, no model calls.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

ALGORITHM_VERSION = "investigation-pivot-v1"

# Asymmetric by design: an investigation reaches much further backward (toward
# delivery and initial access) than forward (toward consequences already
# visible). Defaults are tuned for a BOTS-shaped single-day scenario; a real
# environment with 14-day median dwell needs a far longer backward reach, and
# that is a per-corpus setting, not a constant.
BACKWARD_SECONDS = 24 * 3600
FORWARD_SECONDS = 1 * 3600

# An investigation is bounded work. These caps are what make it an
# investigation rather than a scan, and they are published with every result
# so a truncated reconstruction is never mistaken for a complete one.
MAX_PIVOT_DEPTH = 3
MAX_QUERIES = 40
MAX_EVENTS = 20_000

# Entity kinds worth pivoting on, in the order a defender reaches for them.
PIVOTABLE_KINDS: tuple[str, ...] = ("user", "host", "ip", "process", "hash", "resource")


@dataclass(frozen=True)
class Anchor:
    """Where the investigation STARTS -- typically a symptom late in the kill
    chain, not the beginning of the incident."""

    anchor_id: str
    at: float  # epoch seconds, inside the corpus's range
    entity: str
    entity_kind: str
    sourcetype: str
    why: str  # what made this notable
    index: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "at": self.at,
            "entity": self.entity,
            "entity_kind": self.entity_kind,
            "sourcetype": self.sourcetype,
            "why": self.why,
            "index": self.index,
        }


@dataclass(frozen=True)
class PivotQuery:
    """One bounded query. Time-bounded and entity-scoped, never
    `earliest=0`, and never sourcetype-filtered -- the whole point is to see
    every source around that moment."""

    query_id: str
    index: str
    entity: str
    entity_kind: str
    earliest: float
    latest: float
    depth: int
    parent_query_id: str | None
    reason: str

    @property
    def span_seconds(self) -> float:
        return self.latest - self.earliest

    def to_intent(self) -> dict[str, Any]:
        """Shape the existing connector consumes. `sourcetype` is deliberately
        absent: a capture that filters by sourcetype cannot discover a source
        it was not told to look at."""
        return {
            "index": self.index,
            "entities": [self.entity],
            "earliest": self.earliest,
            "latest": self.latest,
            "sourcetype": None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "index": self.index,
            "entity": self.entity,
            "entity_kind": self.entity_kind,
            "earliest": self.earliest,
            "latest": self.latest,
            "span_seconds": self.span_seconds,
            "depth": self.depth,
            "parent_query_id": self.parent_query_id,
            "reason": self.reason,
        }


def plan_initial_queries(
    anchor: Anchor,
    indexes: Iterable[str],
    *,
    backward: float = BACKWARD_SECONDS,
    forward: float = FORWARD_SECONDS,
) -> list[PivotQuery]:
    """The first expansion: bidirectional and asymmetric, across EVERY index,
    scoped to the anchor's entity."""
    out: list[PivotQuery] = []
    for i, index in enumerate(indexes):
        out.append(
            PivotQuery(
                query_id=f"q0-{i}",
                index=index,
                entity=anchor.entity,
                entity_kind=anchor.entity_kind,
                earliest=anchor.at - backward,
                latest=anchor.at + forward,
                depth=0,
                parent_query_id=None,
                reason=f"anchor_expansion:{anchor.why}",
            )
        )
    return out


EntityExtractor = Callable[[dict[str, Any]], list[tuple[str, str]]]  # -> [(kind, value)]


@dataclass
class Investigation:
    """The assembled narrative: everything the pivots reached, with the
    provenance of how each piece was found."""

    anchor: Anchor
    events: list[dict[str, Any]] = field(default_factory=list)
    queries: list[PivotQuery] = field(default_factory=list)
    entities_seen: dict[str, str] = field(default_factory=dict)  # value -> kind
    pivots: list[dict[str, Any]] = field(default_factory=list)
    truncated_reasons: list[str] = field(default_factory=list)

    @property
    def sourcetypes(self) -> tuple[str, ...]:
        return tuple(sorted({str(e.get("sourcetype") or "") for e in self.events} - {""}))

    @property
    def span_seconds(self) -> float | None:
        stamps = [e["_time"] for e in self.events if isinstance(e.get("_time"), (int, float))]
        return (max(stamps) - min(stamps)) if len(stamps) >= 2 else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor.to_dict(),
            "n_events": len(self.events),
            "n_queries": len(self.queries),
            "n_entities": len(self.entities_seen),
            "sourcetypes": list(self.sourcetypes),
            "n_sourcetypes": len(self.sourcetypes),
            "span_seconds": self.span_seconds,
            "pivots": self.pivots,
            "truncated_reasons": self.truncated_reasons,
            "queries": [q.to_dict() for q in self.queries],
        }


def investigate(  # noqa: PLR0912, C901
    anchor: Anchor,
    indexes: list[str],
    execute: Callable[[PivotQuery], list[dict[str, Any]]],
    extract_entities: EntityExtractor,
    *,
    backward: float = BACKWARD_SECONDS,
    forward: float = FORWARD_SECONDS,
    max_depth: int = MAX_PIVOT_DEPTH,
    max_queries: int = MAX_QUERIES,
    max_events: int = MAX_EVENTS,
    corpus_earliest: float | None = None,
    corpus_latest: float | None = None,
) -> Investigation:
    """Reconstruct an incident from an anchor by recursive, bounded,
    time-scoped entity pivoting.

    Every query is clamped to the corpus's own time range when one is given,
    so an investigation cannot wander outside the data it is meant to explain
    -- and so a cousin injected outside that range is provably unreachable
    rather than silently missed.
    """
    inv = Investigation(anchor=anchor)
    inv.entities_seen[anchor.entity] = anchor.entity_kind

    frontier: list[PivotQuery] = plan_initial_queries(
        anchor, indexes, backward=backward, forward=forward
    )
    seen_scopes: set[tuple[str, str, int, int]] = set()
    qn = 0

    while frontier:
        query = frontier.pop(0)

        if len(inv.queries) >= max_queries:
            inv.truncated_reasons.append(f"max_queries:{max_queries}")
            break
        if len(inv.events) >= max_events:
            inv.truncated_reasons.append(f"max_events:{max_events}")
            break

        earliest, latest = query.earliest, query.latest
        if corpus_earliest is not None:
            earliest = max(earliest, corpus_earliest)
        if corpus_latest is not None:
            latest = min(latest, corpus_latest)
        if latest <= earliest:
            continue
        query = PivotQuery(
            query_id=query.query_id,
            index=query.index,
            entity=query.entity,
            entity_kind=query.entity_kind,
            earliest=earliest,
            latest=latest,
            depth=query.depth,
            parent_query_id=query.parent_query_id,
            reason=query.reason,
        )

        scope = (query.index, query.entity, int(earliest), int(latest))
        if scope in seen_scopes:
            continue
        seen_scopes.add(scope)

        rows = execute(query)
        inv.queries.append(query)
        # A single query's own result can exceed the remaining event budget
        # in one call (a live run against botsv3 hit this: one bounded,
        # entity-scoped query returned 26k+ rows in one round trip) -- the
        # cap has to trim the batch itself, not just stop issuing queries,
        # or `max_events` is not actually a bound on events read.
        remaining = max_events - len(inv.events)
        if len(rows) > remaining:
            rows = rows[:remaining]
            inv.truncated_reasons.append(f"max_events:{max_events}")
        inv.events.extend(rows)

        if query.depth >= max_depth:
            continue

        # Recursive pivot: entities discovered in these results become the
        # next queries. This is what links stages that share no identifier.
        discovered: list[tuple[str, str]] = []
        for row in rows:
            for kind, value in extract_entities(row):
                if kind not in PIVOTABLE_KINDS or not value:
                    continue
                if value in inv.entities_seen:
                    continue
                inv.entities_seen[value] = kind
                discovered.append((kind, value))

        for kind, value in discovered:
            qn += 1
            inv.pivots.append(
                {
                    "from_entity": query.entity,
                    "to_entity": value,
                    "to_kind": kind,
                    "depth": query.depth + 1,
                    "via_query": query.query_id,
                }
            )
            for index in indexes:
                frontier.append(
                    PivotQuery(
                        query_id=f"q{query.depth + 1}-{qn}-{index}",
                        index=index,
                        entity=value,
                        entity_kind=kind,
                        earliest=query.earliest,
                        latest=query.latest,
                        depth=query.depth + 1,
                        parent_query_id=query.query_id,
                        reason=f"pivot_from:{query.entity}",
                    )
                )
    return inv


@dataclass(frozen=True)
class ReachReport:
    """Did the investigation reach what the answer key says is there?

    This is the floor measured the way a defender would judge it: starting
    from a symptom, did the reconstruction reach the documented stages of the
    incident. A flat slab read cannot answer this at all.
    """

    anchor_id: str
    expected_stage_entities: tuple[str, ...]
    reached: tuple[str, ...]
    missed: tuple[str, ...]
    reach_recall: float | None
    n_sourcetypes: int
    n_queries: int
    span_seconds: float | None
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "expected_stage_entities": list(self.expected_stage_entities),
            "reached": list(self.reached),
            "missed": list(self.missed),
            "reach_recall": self.reach_recall,
            "n_sourcetypes": self.n_sourcetypes,
            "n_queries": self.n_queries,
            "span_seconds": self.span_seconds,
            "truncated": self.truncated,
        }


def reach_report(inv: Investigation, expected_stage_entities: Iterable[str]) -> ReachReport:
    expected = tuple(expected_stage_entities)
    seen = set(inv.entities_seen)
    reached = tuple(e for e in expected if e in seen)
    missed = tuple(e for e in expected if e not in seen)
    return ReachReport(
        anchor_id=inv.anchor.anchor_id,
        expected_stage_entities=expected,
        reached=reached,
        missed=missed,
        reach_recall=(len(reached) / len(expected)) if expected else None,
        n_sourcetypes=len(inv.sourcetypes),
        n_queries=len(inv.queries),
        span_seconds=inv.span_seconds,
        truncated=bool(inv.truncated_reasons),
    )
