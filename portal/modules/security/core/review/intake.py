"""review.intake -- records from any number of sources become gradeable units.

What the old assembled runs got wrong, and this does differently (each is tested):

* ONE role map for a whole window. ``artifact_graph.build_graph`` infers a single field-role
  map from the records it is handed, so a window mixing a firewall and a Windows log mis-reads
  both. Here every source gets its own graph and its own role map.
* Entities that never link across sources. Entity tokens carry the *field name*
  (``src_ip=10.0.0.5`` vs ``ClientIP=10.0.0.5``), so differently named identifiers never
  met. Here identifier *values* are resolved across sources (``correlation``) and the merged
  graph is built over canonical entity ids.
* A silent unit cap. ``enumerate_units`` keeps only the first 512 artifacts / entities per
  level by default, in sorted order -- a lesson-1 violation hiding behind a docstring that says
  "never an arbitrary subset". Here the cap is set above the artifact count, so it can never
  bind, and the receipts say ``examined == resolved``.

Every event gets a stable ``event_id`` so any later claim can cite it and a deterministic
checker can find it (``grounding``).

Observation plane: no label identifiers (see ``wall``).
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from ..bully import artifact_graph as ag
from ..bully import correlation
from .content import DEFAULT_LIMIT, content_terms, flatten_values
from .contracts import StageReceipt


@dataclass(frozen=True)
class EventView:
    event_id: str
    source_id: str
    time: float | None
    text: str


@dataclass(frozen=True)
class IntakeUnit:
    unit: ag.GradeableUnit
    event_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    terms: tuple[str, ...]
    card: str


@dataclass
class IntakeResult:
    units: list[IntakeUnit] = field(default_factory=list)
    events: dict[str, EventView] = field(default_factory=dict)
    receipts: list[StageReceipt] = field(default_factory=list)
    blind_sources: list[str] = field(default_factory=list)


#: The event's own identity: its content, its partition, and Splunk's stable bucket address
#: (``_cd``). Hashing the whole record instead made the id depend on search-job metadata
#: (``_serial`` is a per-result ordinal, ``_si``/``_bkt``/``_indextime`` vary by server and
#: bucket state) and on search-time field extraction, so the same event came back with a
#: different id in a later export: D-T2-TRUTH-STRATIFICATION reconciled 804 of 22,397 ids at
#: identical row counts and rejected a stratification on that evidence.
_IDENTITY_FIELDS = ("index", "sourcetype", "host", "source", "_time", "_raw", "_cd")


def event_id_for(source_id: str, record: Mapping[str, Any]) -> str:
    if "_raw" in record and "_time" in record:
        body: Mapping[str, Any] = {k: record[k] for k in _IDENTITY_FIELDS if k in record}
    else:
        # Not a telemetry-shaped record (capture rows, corpus-derived twins): the whole body
        # is the identity, as before.
        body = {k: v for k, v in record.items() if not str(k).startswith("__")}
    digest = hashlib.sha1(
        json.dumps(body, sort_keys=True, default=str).encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:12]
    return f"{source_id}:{digest}"


def render_event(record: Mapping[str, Any], *, max_chars: int = 480) -> str:
    """The text a reader (human or model) sees for one event; quotes are checked against it."""
    parts = [
        f"{path}={'|'.join(values)}"
        for path, values in flatten_values(record).items()
        if not path.startswith("__")
    ]
    return " ".join(parts)[:max_chars]


def _interleave(groups: Sequence[Sequence[str]], limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    depth = 0
    while len(out) < limit and any(depth < len(g) for g in groups):
        for group in groups:
            if depth < len(group) and group[depth] not in seen:
                seen.add(group[depth])
                out.append(group[depth])
                if len(out) >= limit:
                    break
        depth += 1
    return out


def compress_classes(sequence: Sequence[str], *, max_runs: int = 12) -> str:
    """Run-length form of a class sequence (``other*41 > execute*3``), first ``max_runs`` runs.

    A long entity history must not turn the card into a wall of repeated ``other``."""
    runs: list[tuple[str, int]] = []
    for item in sequence:
        if runs and runs[-1][0] == item:
            runs[-1] = (item, runs[-1][1] + 1)
        else:
            runs.append((item, 1))
    parts = [f"{name}*{count}" if count > 1 else name for name, count in runs[:max_runs]]
    if len(runs) > max_runs:
        parts.append(f"...(+{len(runs) - max_runs} runs)")
    return " > ".join(parts)


def unit_card(unit: ag.GradeableUnit, terms: Sequence[str]) -> str:
    """Content-first text for embedding and for the judge. No schema words, no labels."""
    classes = compress_classes(
        [str(c) for c in unit.structural_signature.get("class_sequence") or ()]
    )
    sources = ", ".join(unit.source_ids)
    values = "; ".join(terms)
    return f"sources: {sources} | classes: {classes} | values: {values}"


class NoClassifier:
    """The "no behavioural classes" arm: every action is ``unclassified``.

    The library default (``artifact_graph.DEFAULT_ACTION_CLASSIFIER``) reads a curated
    sourcetype -> behaviour table (``telemetry_behavior``) plus a verb-substring table: a
    definition matcher. Whether classes help at all is measured, not assumed -- this is the
    control arm, and ``review.classify`` (see the core task) adds the table-free inferred one."""

    def classify(self, action: str | None) -> str:
        return "unclassified"


def build_window_units(
    records_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    adjacency_seconds: float = ag.TEMPORAL_ADJACENCY_SECONDS,
    term_limit: int = DEFAULT_LIMIT,
    classifier: ag.ActionClassifier | None = None,
) -> IntakeResult:
    result = IntakeResult()
    artifacts: list[ag.Artifact] = []
    roles_by_source: dict[str, dict[str, str]] = {}
    artifact_event: dict[str, str] = {}
    total_records = 0

    for source_id, records in sorted(records_by_source.items()):
        dict_records = [{**r, "__source_id": source_id} for r in records if isinstance(r, Mapping)]
        total_records += len(dict_records)
        graph = ag.build_graph(dict_records, source_id=source_id, classifier=classifier)
        role_map = graph.role_map
        if graph.insufficient_view or role_map is None:
            result.blind_sources.append(source_id)
            continue
        roles_by_source[source_id] = {
            name: profile.role for name, profile in role_map.profiles.items()
        }
        for artifact in graph.artifacts.values():
            new_id = f"{source_id}#{artifact.artifact_id}"
            event_id = event_id_for(source_id, artifact.record)
            artifact_event[new_id] = event_id
            result.events.setdefault(
                event_id,
                EventView(event_id, source_id, artifact.timestamp, render_event(artifact.record)),
            )
            artifacts.append(replace(artifact, artifact_id=new_id))

    result.receipts.append(
        StageReceipt(
            "intake.sources",
            examined=len(records_by_source),
            resolved=len(roles_by_source),
            note=f"blind: {sorted(result.blind_sources)}" if result.blind_sources else "",
        )
    )
    result.receipts.append(
        StageReceipt("intake.events", examined=total_records, resolved=len(artifacts))
    )
    if not artifacts:
        return result

    observations: list[correlation.IdentifierObservation] = []
    for artifact in artifacts:
        for token in artifact.entities:
            name, _, value = token.partition("=")
            if value:
                observations.append(
                    correlation.IdentifierObservation(
                        value=value,
                        field_path=name,
                        source_id=artifact.source_id,
                        artifact_id=artifact.artifact_id,
                    )
                )
    _entities, value_to_id = correlation.resolve_entities(observations)

    canonical: list[ag.Artifact] = []
    for artifact in artifacts:
        ids = {
            f"entity={value_to_id.get(value, value)}"
            for value in (t.partition("=")[2] for t in artifact.entities)
            if value
        }
        canonical.append(replace(artifact, entities=tuple(sorted(ids))))

    edges = [
        *ag._shared_entity_edges(canonical),
        *ag._temporal_adjacency_edges(canonical, adjacency_seconds),
        *ag._causal_parent_edges(canonical),
    ]
    graph = ag.ArtifactGraph(canonical, edges)
    units = ag.enumerate_units(graph, max_per_level=len(canonical) + 1)
    by_id = {a.artifact_id: a for a in canonical}

    for unit in units:
        members = [by_id[i] for i in unit.artifact_ids if i in by_id]
        per_source: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for member in members:
            per_source[member.source_id].append(member.record)
        groups = [
            content_terms(recs, roles_by_source.get(src, {}), limit=term_limit)
            for src, recs in sorted(per_source.items())
        ]
        terms = tuple(_interleave(groups, term_limit))
        result.units.append(
            IntakeUnit(
                unit=unit,
                event_ids=tuple(
                    dict.fromkeys(
                        artifact_event[i] for i in unit.artifact_ids if i in artifact_event
                    )
                ),
                source_ids=tuple(unit.source_ids),
                terms=terms,
                card=unit_card(unit, terms),
            )
        )

    level_one = sum(1 for u in units if u.level == "L1_ARTIFACT")
    result.receipts.append(
        StageReceipt(
            "intake.units",
            examined=len(canonical),
            resolved=len(units),
            note=f"uncapped; L1_ARTIFACT {level_one} of {len(canonical)} artifacts",
        )
    )
    return result
