"""bully.artifact_graph -- artifacts in a window, and the units worth grading.

The primitive this module exists to serve: *given the artifacts present in a
window of time, do they -- individually and in combination -- look like a
known type: exactly, similarly, or not at all.*

Everything before this graded one flattened token bag per scope, which
destroyed both halves of that question. The individual level did not exist,
and the combination level was reduced to a bag of vocabulary -- discarding
co-occurrence, ordering, and entity linkage, which is exactly the signal
that survives when an adversary changes tooling. Vocabulary is the part
that changes; shape is the part that does not.

**Structural grouping, never subset enumeration.** An arbitrary k-subset of
a window has no operational meaning and there are 2^n of them. The units
worth grading are the ones the data's own structure produces, and they are
the same ones an analyst pivots on:

    L1_ARTIFACT   one artifact alone
    L2_ENTITY     every artifact touching one entity (identity, host, key)
    L3_CHAIN      a connected component of the artifact graph -- artifacts
                  linked by shared entity, causal parent, or tight temporal
                  adjacency: the "these six events on this identity in this
                  twenty minutes" an analyst would actually pivot to
    L4_WINDOW     the whole window, the maximal case

That is O(n*k) units, not O(2^n), and every unit is something a human can
be handed.

A unit carries a `structural_signature`: the *shape* of the combination --
ordered action classes, edge-type multiset, entity-role pattern, degree
profile -- deliberately separate from its vocabulary, so a combination can
be matched on shape even when every literal token differs.

Pure compute over injected records. No I/O, no model calls, no schema
normalization: edges are derived from relations (entity, time, causality)
that exist regardless of a source's schema, which is what keeps this
source-agnostic (the Crogl property).
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol

ALGORITHM_VERSION = "artifact-graph-v1"

UNIT_LEVELS: tuple[str, ...] = ("L1_ARTIFACT", "L2_ENTITY", "L3_CHAIN", "L4_WINDOW")

EDGE_KINDS: tuple[str, ...] = ("shared_entity", "temporal_adjacency", "causal_parent")

# Tight adjacency only: a window-wide temporal link would make every window
# one component and collapse L3 into L4.
TEMPORAL_ADJACENCY_SECONDS = 300.0

# Structural caps -- a unit explosion is a measurement failure, not a finding.
MAX_UNITS_PER_LEVEL = 512
MIN_CHAIN_SIZE = 2

_ENTITY_FIELDS: tuple[str, ...] = (
    "userIdentity.arn",
    "userIdentity.userName",
    "userIdentity.accessKeyId",
    "user",
    "username",
    "host",
    "hostname",
    "target_host",
    "src_ip",
    "sourceIPAddress",
    "account_id",
    "recipientAccountId",
    "process_guid",
    "ParentProcessGuid",
)

_ACTION_FIELDS: tuple[str, ...] = (
    "eventName",
    "action",
    "command",
    "cmdline",
    "verb",
    "operation",
    "signature",
)

_TIME_FIELDS: tuple[str, ...] = ("eventTime", "_time", "timestamp", "time", "@timestamp")

_CAUSAL_PARENT_FIELDS: tuple[str, ...] = ("ParentProcessGuid", "parent_guid", "parent_process_id")
_CAUSAL_SELF_FIELDS: tuple[str, ...] = ("process_guid", "ProcessGuid", "process_id")


def _dig(record: dict[str, Any], dotted: str) -> Any:
    cursor: Any = record
    for part in dotted.split("."):
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
    return cursor


def _first_str(record: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field_name in fields:
        value = _dig(record, field_name)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return None


def _parse_time(record: dict[str, Any]) -> float | None:
    raw = _first_str(record, _TIME_FIELDS)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        pass
    import datetime as _dt

    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            return _dt.datetime.strptime(raw, fmt).timestamp()
        except ValueError:
            continue
    return None


def _entities(record: dict[str, Any]) -> tuple[str, ...]:
    found: list[str] = []
    for field_name in _ENTITY_FIELDS:
        value = _dig(record, field_name)
        if isinstance(value, (str, int, float)) and str(value).strip():
            token = f"{field_name.split('.')[-1]}={str(value).strip()}"
            if token not in found:
                found.append(token)
    return tuple(found)


ACTION_CLASSES: tuple[str, ...] = (
    "unknown",
    "auth",
    "enumerate",
    "execute",
    "destroy",
    "escalate",
    "collect",
    "other",
)


class ActionClassifier(Protocol):
    """Maps an action verb to a coarse behavioural class.

    **This is the known weak seam of the whole design.** Shape-matching
    across sources only works if two different verbs for the same behaviour
    map to the same class -- mapping a verb to a behavioural class is a
    *semantic* task, not a deterministic one. This protocol exists so a
    learned classifier can be swapped in behind it later, measurably and in
    isolation, without touching anything else in this module. **U.3 ships
    only the seam and the deterministic default; it does not add a learned
    classifier** -- M.1's cross-vocabulary ladder rung is the number that
    sizes that work, and swapping the instrument under a grader that cannot
    yet measure it is the mistake that produced the last three passes'
    misses.
    """

    def classify(self, action: str | None) -> str: ...


@dataclass(frozen=True)
class DeterministicActionClassifier:
    """Hand-written substring table. Fails the moment a source uses
    vocabulary its author did not anticipate (`Add-LocalGroupMember` is an
    escalation; no substring here says so) -- that gap is real and is
    reported, not hidden, via the U.1 cross-vocabulary test and M.1's ladder.
    """

    def classify(self, action: str | None) -> str:
        if not action:
            return "unknown"
        lowered = action.lower()
        table = (
            (("assumerole", "getsessiontoken", "logon", "authenticate", "login"), "auth"),
            (("list", "describe", "get", "enumerate", "whoami", "net user", "query"), "enumerate"),
            (("create", "put", "run", "start", "invoke", "exec", "spawn"), "execute"),
            (("delete", "remove", "stop", "terminate", "disable", "clear"), "destroy"),
            (("attach", "grant", "addrole", "putpolicy", "adduser"), "escalate"),
            (("copy", "download", "getobject", "export", "sync"), "collect"),
        )
        for needles, label in table:
            if any(needle in lowered for needle in needles):
                return label
        return "other"


DEFAULT_ACTION_CLASSIFIER = DeterministicActionClassifier()


def _action_class(action: str | None, classifier: ActionClassifier | None = None) -> str:
    """Coarse behavioural class for an action verb. See `ActionClassifier`."""
    return (classifier or DEFAULT_ACTION_CLASSIFIER).classify(action)


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    record: dict[str, Any]
    entities: tuple[str, ...]
    action: str | None
    action_class: str
    timestamp: float | None
    source_id: str

    @property
    def causal_self(self) -> str | None:
        return _first_str(self.record, _CAUSAL_SELF_FIELDS)

    @property
    def causal_parent(self) -> str | None:
        return _first_str(self.record, _CAUSAL_PARENT_FIELDS)


@dataclass(frozen=True)
class Edge:
    left: str
    right: str
    kind: str
    key: str


@dataclass(frozen=True)
class GradeableUnit:
    """One thing worth asking the question of. `structural_signature` is the
    combination's *shape*; `vocabulary` is its literal content. They are kept
    apart on purpose -- shape survives a change of tooling, vocabulary does
    not."""

    unit_id: str
    level: str
    artifact_ids: tuple[str, ...]
    entities: tuple[str, ...]
    action_classes: tuple[str, ...]
    edge_kinds: tuple[str, ...]
    span_seconds: float | None
    structural_signature: dict[str, Any]
    vocabulary: tuple[str, ...]
    source_ids: tuple[str, ...]

    @property
    def size(self) -> int:
        return len(self.artifact_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "level": self.level,
            "size": self.size,
            "artifact_ids": list(self.artifact_ids),
            "entities": list(self.entities),
            "action_classes": list(self.action_classes),
            "edge_kinds": list(self.edge_kinds),
            "span_seconds": self.span_seconds,
            "structural_signature": dict(self.structural_signature),
            "vocabulary": list(self.vocabulary),
            "source_ids": list(self.source_ids),
        }

    def grading_projection(self) -> UnitSignature:
        """The grading-facing view of this unit, shape and vocabulary kept
        in **separate** channels so cousin_relation can grade a combination
        on shape alone even when its vocabulary is unrecognisable.

        `event_graph` carries `structural_signature` -- this is the fix for
        the defect this module exists to correct: `event_graph` is declared
        on `signatures.reference_record_fields` but was never populated
        anywhere on the observed path, because the one-signature-per-scope
        design had no combination-level object to populate it from. A
        `GradeableUnit`'s `structural_signature` *is* that graph.
        `action_sequence` carries the literal vocabulary and nothing else,
        so a delta can say "same shape, entirely different vocabulary" --
        the exact case an unknown instance of a known type produces.
        `attack_mappings` is always empty: technique identity is what
        relating is meant to *produce*, never an input a unit supplies
        (C.1 inversion 3).
        """
        return UnitSignature(
            signature_id=self.unit_id,
            event_graph=dict(self.structural_signature),
            action_sequence=self.vocabulary,
            telemetry_shape=self.edge_kinds,
            parameter_families=self.entities,
            context_topology=(self.level, *self.source_ids),
        )


@dataclass(frozen=True)
class UnitSignature:
    """Grading-facing projection of a `GradeableUnit`. Field names are
    duck-typed to `cousin_relation._subject_axis_features` so a unit can be
    handed to `relate_cousin` exactly like any other subject signature, but
    every field here traces to exactly one of the two channels: shape
    (`event_graph`, `telemetry_shape`) or vocabulary (`action_sequence`,
    `parameter_families`). Never both in one field -- that conflation is
    what flattened combination-level signal into a token bag before U.1/U.2.
    """

    signature_id: str
    event_graph: dict[str, Any]
    action_sequence: tuple[str, ...]
    telemetry_shape: tuple[str, ...]
    parameter_families: tuple[str, ...]
    context_topology: tuple[str, ...]
    attack_mappings: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature_id": self.signature_id,
            "event_graph": dict(self.event_graph),
            "action_sequence": list(self.action_sequence),
            "telemetry_shape": list(self.telemetry_shape),
            "parameter_families": list(self.parameter_families),
            "context_topology": list(self.context_topology),
            "attack_mappings": list(self.attack_mappings),
        }


class ArtifactGraph:
    def __init__(self, artifacts: list[Artifact], edges: list[Edge]) -> None:
        self.artifacts = {a.artifact_id: a for a in artifacts}
        self.edges = edges
        self._adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            self._adjacency[edge.left].add(edge.right)
            self._adjacency[edge.right].add(edge.left)

    def components(self) -> list[tuple[str, ...]]:
        seen: set[str] = set()
        out: list[tuple[str, ...]] = []
        for artifact_id in self.artifacts:
            if artifact_id in seen:
                continue
            stack = [artifact_id]
            group: list[str] = []
            seen.add(artifact_id)
            while stack:
                current = stack.pop()
                group.append(current)
                for neighbour in self._adjacency.get(current, ()):
                    if neighbour not in seen:
                        seen.add(neighbour)
                        stack.append(neighbour)
            out.append(tuple(sorted(group)))
        return out

    def by_entity(self) -> dict[str, tuple[str, ...]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for artifact in self.artifacts.values():
            for entity in artifact.entities:
                groups[entity].append(artifact.artifact_id)
        return {k: tuple(sorted(v)) for k, v in groups.items() if len(v) >= MIN_CHAIN_SIZE}


def _shared_entity_edges(artifacts: list[Artifact]) -> list[Edge]:
    by_entity: dict[str, list[str]] = defaultdict(list)
    for artifact in artifacts:
        for entity in artifact.entities:
            by_entity[entity].append(artifact.artifact_id)
    edges: list[Edge] = []
    for entity, ids in by_entity.items():
        for left, right in zip(ids, ids[1:], strict=False):
            edges.append(Edge(left, right, "shared_entity", entity))
    return edges


def _temporal_adjacency_edges(artifacts: list[Artifact], adjacency_seconds: float) -> list[Edge]:
    """Temporal adjacency only ever *reinforces* an existing entity link. A
    bare "these two happened close together" edge is not a relation: in any
    steady stream every artifact is temporally adjacent to its neighbour,
    which chains the entire window into a single component and silently
    collapses L3_CHAIN into L4_WINDOW. Proximity qualifies a link; it does
    not create one."""
    timed = sorted(
        (a for a in artifacts if a.timestamp is not None), key=lambda a: a.timestamp or 0.0
    )
    edges: list[Edge] = []
    for left, right in zip(timed, timed[1:], strict=False):
        gap = (right.timestamp or 0.0) - (left.timestamp or 0.0)
        if gap > adjacency_seconds:
            continue
        if not (set(left.entities) & set(right.entities)):
            continue
        edges.append(Edge(left.artifact_id, right.artifact_id, "temporal_adjacency", f"{gap:.0f}s"))
    return edges


def _causal_parent_edges(artifacts: list[Artifact]) -> list[Edge]:
    by_causal_self: dict[str, str] = {}
    for artifact in artifacts:
        key = artifact.causal_self
        if key:
            by_causal_self[key] = artifact.artifact_id
    edges: list[Edge] = []
    for artifact in artifacts:
        parent = artifact.causal_parent
        if not parent or parent not in by_causal_self:
            continue
        parent_id = by_causal_self[parent]
        if parent_id != artifact.artifact_id:
            edges.append(Edge(parent_id, artifact.artifact_id, "causal_parent", parent))
    return edges


def build_graph(
    records: list[dict[str, Any]],
    *,
    source_id: str = "",
    adjacency_seconds: float = TEMPORAL_ADJACENCY_SECONDS,
    classifier: ActionClassifier | None = None,
) -> ArtifactGraph:
    active_classifier = classifier or DEFAULT_ACTION_CLASSIFIER
    artifacts: list[Artifact] = []
    for i, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        action = _first_str(record, _ACTION_FIELDS)
        artifacts.append(
            Artifact(
                artifact_id=f"a{i:05d}",
                record=record,
                entities=_entities(record),
                action=action,
                action_class=active_classifier.classify(action),
                timestamp=_parse_time(record),
                source_id=str(record.get("__source_id") or source_id),
            )
        )

    edges: list[Edge] = [
        *_shared_entity_edges(artifacts),
        *_temporal_adjacency_edges(artifacts, adjacency_seconds),
        *_causal_parent_edges(artifacts),
    ]

    return ArtifactGraph(artifacts, edges)


def _structural_signature(
    graph: ArtifactGraph, artifact_ids: tuple[str, ...], edge_kinds: tuple[str, ...]
) -> dict[str, Any]:
    """The combination's shape, independent of its vocabulary."""
    members = [graph.artifacts[i] for i in artifact_ids if i in graph.artifacts]
    ordered = sorted(
        members, key=lambda a: (a.timestamp is None, a.timestamp or 0.0, a.artifact_id)
    )
    class_sequence = tuple(a.action_class for a in ordered)
    class_multiset: dict[str, int] = {}
    for name in class_sequence:
        class_multiset[name] = class_multiset.get(name, 0) + 1
    entity_roles: dict[str, int] = {}
    for artifact in members:
        for entity in artifact.entities:
            kind = entity.split("=", 1)[0]
            entity_roles[kind] = entity_roles.get(kind, 0) + 1
    degrees = sorted((len(graph._adjacency.get(i, ())) for i in artifact_ids), reverse=True)
    return {
        "size": len(artifact_ids),
        "class_sequence": list(class_sequence),
        "class_multiset": class_multiset,
        "distinct_classes": len(class_multiset),
        "entity_role_profile": entity_roles,
        "degree_profile": degrees[:16],
        "edge_kinds": sorted(set(edge_kinds)),
        "source_diversity": len({a.source_id for a in members if a.source_id}),
    }


def _unit_id(level: str, artifact_ids: tuple[str, ...]) -> str:
    digest = hashlib.sha256(
        json.dumps([level, sorted(artifact_ids)], sort_keys=True).encode()
    ).hexdigest()
    return f"u-{digest[:14]}"


def _make_unit(graph: ArtifactGraph, level: str, artifact_ids: tuple[str, ...]) -> GradeableUnit:
    members = [graph.artifacts[i] for i in artifact_ids if i in graph.artifacts]
    member_set = set(artifact_ids)
    edge_kinds = tuple(
        e.kind for e in graph.edges if e.left in member_set and e.right in member_set
    )
    stamps = [a.timestamp for a in members if a.timestamp is not None]
    span = (max(stamps) - min(stamps)) if len(stamps) >= 2 else (0.0 if stamps else None)
    vocabulary: list[str] = []
    for artifact in members:
        if artifact.action and artifact.action not in vocabulary:
            vocabulary.append(artifact.action)
    entities: list[str] = []
    for artifact in members:
        for entity in artifact.entities:
            if entity not in entities:
                entities.append(entity)
    return GradeableUnit(
        unit_id=_unit_id(level, artifact_ids),
        level=level,
        artifact_ids=tuple(sorted(artifact_ids)),
        entities=tuple(entities),
        action_classes=tuple(a.action_class for a in members),
        edge_kinds=tuple(sorted(set(edge_kinds))),
        span_seconds=span,
        structural_signature=_structural_signature(graph, artifact_ids, edge_kinds),
        vocabulary=tuple(vocabulary),
        source_ids=tuple(sorted({a.source_id for a in members if a.source_id})),
    )


def enumerate_units(
    graph: ArtifactGraph,
    *,
    levels: tuple[str, ...] = UNIT_LEVELS,
    max_per_level: int = MAX_UNITS_PER_LEVEL,
) -> list[GradeableUnit]:
    """Every unit the data's structure produces -- never an arbitrary subset.

    A unit appearing at more than one level is kept once per level: the level
    is part of the claim ("this artifact alone" is a different assertion from
    "these six together"), and downstream reporting prefers the *smallest*
    unit that matches, because that is the most specific claim available.
    """
    units: list[GradeableUnit] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    def _add(level: str, artifact_ids: tuple[str, ...]) -> None:
        """One artifact set is one claim at a given level, no matter how many
        entity keys happen to produce it (an identity and a source IP over the
        same six events are the same six events)."""
        key = (level, tuple(sorted(artifact_ids)))
        if key in seen:
            return
        seen.add(key)
        units.append(_make_unit(graph, level, artifact_ids))

    all_ids = tuple(sorted(graph.artifacts))
    if not all_ids:
        return units

    if "L1_ARTIFACT" in levels:
        for artifact_id in all_ids[:max_per_level]:
            _add("L1_ARTIFACT", (artifact_id,))

    if "L2_ENTITY" in levels:
        for _entity, ids in sorted(graph.by_entity().items())[:max_per_level]:
            _add("L2_ENTITY", ids)

    if "L3_CHAIN" in levels:
        chains = [c for c in graph.components() if len(c) >= MIN_CHAIN_SIZE]
        chains.sort(key=len, reverse=True)
        for component in chains[:max_per_level]:
            _add("L3_CHAIN", component)

    if "L4_WINDOW" in levels and len(all_ids) >= MIN_CHAIN_SIZE:
        _add("L4_WINDOW", all_ids)

    return units
