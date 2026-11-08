"""Step->manifestation join: group events into candidate stages by time and content.

Refuses any record or feature key carrying ground-truth vocabulary — the join
must run before and independently of published labels.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from portal.modules.security.core.mawa.events import ParsedEvent

# Ground-truth columns that must never flow into the join as features.
FORBIDDEN_FEATURE_KEYS = frozenset(
    {"actor", "ground_truth_label", "low_level_ids", "tag", "decoded", "normalized"}
)


class GroundTruthFeatureError(ValueError):
    """A ground-truth column was offered as a join feature or record key."""


def validate_feature_keys(keys: Sequence[str]) -> None:
    """Raise unless every requested feature key is free of ground-truth vocabulary."""
    for key in keys:
        if key in FORBIDDEN_FEATURE_KEYS:
            raise GroundTruthFeatureError(f"ground-truth column refused as feature: {key}")


def validate_records(records: Sequence[Mapping[str, object]]) -> None:
    """Raise unless no record carries a ground-truth column at all."""
    for record in records:
        present = FORBIDDEN_FEATURE_KEYS.intersection(record)
        if present:
            raise GroundTruthFeatureError(
                f"record carries ground-truth columns, refused: {sorted(present)}"
            )


@dataclass(frozen=True)
class JoinParams:
    """Frozen before any scored run; values recorded in the run record."""

    time_window_s: float = 3.0
    entity_window_s: float = 30.0
    max_entity_df: int = 10


DEFAULT_JOIN_PARAMS = JoinParams()


@dataclass(frozen=True)
class GraphParams:
    """Report-only group graph: mid-frequency entities may link candidate groups."""

    max_entity_df: int = 50


DEFAULT_GRAPH_PARAMS = GraphParams()


@dataclass(frozen=True)
class CandidateGroup:
    """A candidate stage: member event ids, span, binding evidence, files."""

    group_id: int
    member_ids: tuple[int, ...]
    ts_min: float
    ts_max: float
    files: frozenset[str]
    binding_entities: frozenset[str] = field(default_factory=frozenset)

    @property
    def size(self) -> int:
        return len(self.member_ids)

    @property
    def span_s(self) -> float:
        return self.ts_max - self.ts_min


@dataclass(frozen=True)
class GroupEdge:
    """A linkage between two candidate groups via shared discovered entities."""

    group_a: int
    group_b: int
    shared_entities: frozenset[str]
    delta_s: float


def _entity_df(events: Sequence[ParsedEvent]) -> dict[str, int]:
    df: dict[str, int] = defaultdict(int)
    for event in events:
        for entity in event.entities:
            df[entity] += 1
    return dict(df)


class _UnionFind:
    def __init__(self, ids: list[int]) -> None:
        self.parent = {i: i for i in ids}

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def build_groups(
    events: list[ParsedEvent],
    params: JoinParams = DEFAULT_JOIN_PARAMS,
    feature_keys: Sequence[str] = ("entities",),
) -> list[CandidateGroup]:
    """Single-linkage events via time proximity or shared rare entities."""
    validate_feature_keys(feature_keys)
    ordered = sorted(events, key=lambda e: (e.ts, e.event_id))
    uf = _UnionFind([e.event_id for e in ordered])
    df = _entity_df(ordered)
    rare: dict[str, list[ParsedEvent]] = defaultdict(list)
    for event in ordered:
        for entity in event.entities:
            if df[entity] <= params.max_entity_df:
                rare[entity].append(event)
    for prev, cur in zip(ordered, ordered[1:], strict=False):
        if cur.ts - prev.ts <= params.time_window_s:
            uf.union(prev.event_id, cur.event_id)
    for events_with_entity in rare.values():
        events_with_entity.sort(key=lambda e: (e.ts, e.event_id))
        for prev, cur in zip(events_with_entity, events_with_entity[1:], strict=False):
            if cur.ts - prev.ts <= params.entity_window_s:
                uf.union(prev.event_id, cur.event_id)
    members_by_root: dict[int, list[ParsedEvent]] = defaultdict(list)
    for event in ordered:
        members_by_root[uf.find(event.event_id)].append(event)
    bindings: dict[int, set[str]] = defaultdict(set)
    for entity, events_with_entity in rare.items():
        roots = {uf.find(e.event_id) for e in events_with_entity}
        if len(roots) == 1:
            bindings[next(iter(roots))].add(entity)
    out: list[CandidateGroup] = []
    for root, members in members_by_root.items():
        out.append(
            CandidateGroup(
                group_id=root,
                member_ids=tuple(sorted(e.event_id for e in members)),
                ts_min=min(e.ts for e in members),
                ts_max=max(e.ts for e in members),
                files=frozenset(e.source_file for e in members),
                binding_entities=frozenset(bindings.get(root, set())),
            )
        )
    out.sort(key=lambda g: (g.ts_min, g.ts_max, g.group_id))
    return out


def group_graph(
    events: list[ParsedEvent],
    groups: Sequence[CandidateGroup],
    params: GraphParams = DEFAULT_GRAPH_PARAMS,
) -> list[GroupEdge]:
    """Link candidate groups sharing entities with df <= params.max_entity_df."""
    df = _entity_df(events)
    group_of: dict[int, int] = {}
    for idx, group in enumerate(groups):
        for member in group.member_ids:
            group_of[member] = idx
    ent_groups: dict[str, set[int]] = defaultdict(set)
    for event in events:
        idx_or_none = group_of.get(event.event_id)
        if idx_or_none is not None:
            for entity in event.entities:
                if df[entity] <= params.max_entity_df:
                    ent_groups[entity].add(idx_or_none)
    ts_lo = [g.ts_min for g in groups]
    ts_hi = [g.ts_max for g in groups]
    edges: dict[tuple[int, int], set[str]] = defaultdict(set)
    for entity, idxs in ent_groups.items():
        ordered_idx = sorted(idxs)
        for pos, i in enumerate(ordered_idx):
            for j in ordered_idx[pos + 1 :]:
                edges[(i, j)].add(entity)
    out = [
        GroupEdge(
            group_a=groups[i].group_id,
            group_b=groups[j].group_id,
            shared_entities=frozenset(ents),
            delta_s=max(0.0, ts_lo[j] - ts_hi[i]),
        )
        for (i, j), ents in edges.items()
    ]
    out.sort(key=lambda e: (e.group_a, e.group_b))
    return out


def _record_ts(record: Mapping[str, object]) -> float:
    ts = record.get("ts")
    if not isinstance(ts, (int, float)):
        raise ValueError("record missing numeric 'ts'")
    return float(ts)


def co_group_records(
    records: Sequence[Mapping[str, object]], params: JoinParams = DEFAULT_JOIN_PARAMS
) -> list[list[int]]:
    """Mapping-record join entry point; refuses ground-truth columns.

    Single-linkage records by 'ts' proximity within params.time_window_s.
    """
    validate_records(records)
    keyed = sorted(range(len(records)), key=lambda i: (_record_ts(records[i]), i))
    uf = _UnionFind(keyed)
    for prev, cur in zip(keyed, keyed[1:], strict=False):
        if _record_ts(records[cur]) - _record_ts(records[prev]) <= params.time_window_s:
            uf.union(prev, cur)
    buckets: dict[int, list[int]] = defaultdict(list)
    for i in keyed:
        buckets[uf.find(i)].append(i)
    return [sorted(v) for v in buckets.values()]
