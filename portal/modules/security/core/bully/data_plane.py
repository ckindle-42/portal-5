"""Universal data-plane profiling, catalog, and investigation planning.

This module is intentionally source-agnostic.  It describes what a source can
do from observed records and preserves native values; semantic bindings are
metadata, not a rewritten event schema.  The catalog is consequently useful to
the investigation planner without becoming a second normalized data store.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from .connectors import QueryAuditLog, QueryIntent, QueryResult, SourceConnector

SEMANTICS = ("actor", "asset", "action", "object", "outcome", "time", "location")
CAPABILITIES = (
    "episode_boundary",
    "entity_identity",
    "cross_source_entity",
    "shared_timeline",
    "semantic_text",
    "label_basis",
    "benign_present",
    "queryable_in_place",
)


@dataclass(frozen=True)
class FieldProfile:
    path: str
    observed_type: str
    count: int
    null_count: int
    cardinality: int
    nested: bool

    @property
    def null_rate(self) -> float:
        return self.null_count / self.count if self.count else 1.0


@dataclass(frozen=True)
class SourceSchema:
    source_id: str
    sample_size: int
    fields: tuple[FieldProfile, ...]
    confidence: float
    fingerprint: str
    discovered_at: float = field(default_factory=time.time)

    def field(self, path: str) -> FieldProfile | None:
        return next((item for item in self.fields if item.path == path), None)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SemanticBinding:
    meaning: str
    field_path: str | None
    confidence: float
    method: str
    present: bool


@dataclass(frozen=True)
class TimeBinding:
    source_id: str
    field_path: str | None
    representation: str
    timezone: str | None
    resolution: str | None
    clock_skew_s: float | None
    transform: str
    comparable_with_other_sources: bool


@dataclass(frozen=True)
class EntityLink:
    left_source: str
    left_id: str
    right_source: str
    right_id: str
    confidence: float
    method: str
    provenance: str


@dataclass(frozen=True)
class QualityReport:
    parse_failure_rate: float
    null_rates: dict[str, float]
    duplicate_count: int
    gap_count: int
    truncation_incidence: float
    grade: str
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class VolumeStrategy:
    tier: str
    indexed_fraction: float
    structural_fraction: float
    on_demand_fraction: float
    summarized_fraction: float
    sampling_rule: str
    sampling_bias: str


@dataclass(frozen=True)
class AccessPolicy:
    sensitivity: str = "internal"
    credential_ref: str | None = None
    least_privilege: bool = True
    export_allowed: bool = True


@dataclass(frozen=True)
class CapabilityProfile:
    episode_boundary: bool
    entity_identity: bool
    cross_source_entity: bool
    shared_timeline: bool
    semantic_text: bool
    label_basis: bool
    benign_present: bool
    queryable_in_place: bool

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)

    @property
    def completeness(self) -> float:
        return sum(self.as_dict().values()) / len(CAPABILITIES)


@dataclass(frozen=True)
class SourceProfile:
    source_id: str
    mode: str
    schema: SourceSchema
    bindings: tuple[SemanticBinding, ...]
    time_binding: TimeBinding
    capabilities: CapabilityProfile
    entity_links: tuple[EntityLink, ...]
    volume: VolumeStrategy
    quality: QualityReport
    access: AccessPolicy
    record_count: int
    profile_version: str
    freshness_at: float | None = None
    access_cost: float = 0.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CatalogDecision:
    source_id: str
    selected: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class InvestigationPlan:
    seed_id: str
    source_order: tuple[str, ...]
    decisions: tuple[CatalogDecision, ...]


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {prefix or "value": value}
    flat: dict[str, Any] = {}
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(child, Mapping):
            flat.update(_flatten(child, path))
        else:
            flat[path] = child
    return flat


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (list, tuple, set)):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "string"


def discover_schema(
    source_id: str, records: Iterable[Any], *, sample_size: int = 256
) -> SourceSchema:
    """Infer fields and quality signals from a bounded sample."""
    sample = list(records)[:sample_size]
    flattened = [
        _flatten(record) if isinstance(record, Mapping) else {"value": record} for record in sample
    ]
    observations: dict[str, list[Any]] = defaultdict(list)
    all_paths = sorted({path for row in flattened for path in row})
    for row in flattened:
        for path in all_paths:
            observations[path].append(row.get(path))
    fields: list[FieldProfile] = []
    for path in sorted(observations):
        values = observations[path]
        non_null = [value for value in values if value is not None]
        type_counts = Counter(_type_name(value) for value in non_null)
        observed_type = type_counts.most_common(1)[0][0] if type_counts else "null"
        fields.append(
            FieldProfile(
                path=path,
                observed_type=observed_type,
                count=len(values),
                null_count=len(values) - len(non_null),
                cardinality=len(
                    {json.dumps(value, sort_keys=True, default=str) for value in non_null}
                ),
                nested="." in path,
            )
        )
    fingerprint = hashlib.sha256(
        json.dumps([(item.path, item.observed_type) for item in fields]).encode()
    ).hexdigest()[:16]
    coverage = sum(1 for item in fields if item.count and item.null_rate < 1.0)
    confidence = min(1.0, (coverage / max(1, len(fields))) * min(1.0, len(sample) / 10))
    return SourceSchema(source_id, len(sample), tuple(fields), confidence, fingerprint)


_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "actor": ("actor", "user", "username", "principal", "account", "identity", "owner"),
    "asset": ("asset", "host", "hostname", "device", "computer", "resource", "instance"),
    "action": ("action", "operation", "event", "eventname", "activity", "command", "type"),
    "object": ("object", "target", "resource", "file", "path", "url", "query"),
    "outcome": ("outcome", "result", "status", "success", "error", "decision"),
    "time": ("time", "timestamp", "datetime", "date", "created", "occurred", "start", "end"),
    "location": ("location", "region", "country", "city", "ip", "address", "geo"),
}


def bind_semantics(schema: SourceSchema) -> tuple[SemanticBinding, ...]:
    """Bind meanings using field names and schema evidence; never copy values."""
    bindings: list[SemanticBinding] = []
    for meaning in SEMANTICS:
        candidates = []
        aliases = _FIELD_ALIASES[meaning]
        for field_profile in schema.fields:
            leaf = field_profile.path.rsplit(".", 1)[-1].lower()
            score = (
                1.0
                if leaf in aliases
                else max((0.7 for alias in aliases if alias in leaf), default=0.0)
            )
            if score and field_profile.null_rate <= 0.5:
                candidates.append((score, -field_profile.null_rate, field_profile.path))
        if candidates:
            score, _, path = sorted(candidates, reverse=True)[0]
            bindings.append(SemanticBinding(meaning, path, score, "schema-name", True))
        else:
            bindings.append(SemanticBinding(meaning, None, 0.0, "unbound", False))
    return tuple(bindings)


def _binding(bindings: Sequence[SemanticBinding], meaning: str) -> SemanticBinding:
    return next(item for item in bindings if item.meaning == meaning)


def bind_time(
    source_id: str,
    schema: SourceSchema,
    bindings: Sequence[SemanticBinding],
    records: Sequence[Any],
) -> TimeBinding:
    time_binding = _binding(bindings, "time")
    if not time_binding.present:
        return TimeBinding(source_id, None, "absent", None, None, None, "identity", False)
    values = []
    for record in records:
        flat = _flatten(record) if isinstance(record, Mapping) else {}
        value = flat.get(time_binding.field_path or "")
        if value is not None:
            values.append(value)
    numeric = all(
        isinstance(value, (int, float)) and not isinstance(value, bool) for value in values
    )
    if numeric and values:
        representation = "epoch-seconds" if max(values) > 1_000_000_000 else "epoch-relative"
        comparable = representation == "epoch-seconds"
        transform = "identity" if comparable else "relative-origin-required"
    else:
        representation, comparable, transform = "absolute-text", True, "parse-native"
    return TimeBinding(
        source_id,
        time_binding.field_path,
        representation,
        "UTC" if comparable else None,
        "seconds" if numeric else "native",
        None,
        transform,
        comparable,
    )


def resolve_entities(
    source_id: str,
    records: Iterable[Any],
    *,
    known_aliases: Mapping[str, str] | None = None,
    unified_ids: bool = False,
) -> tuple[EntityLink, ...]:
    """Resolve only explicit aliases/unified ids and retain provenance."""
    aliases = dict(known_aliases or {})
    links: list[EntityLink] = []
    for record in records:
        flat = _flatten(record) if isinstance(record, Mapping) else {}
        for key, value in flat.items():
            if value is None or not any(
                token in key.lower() for token in _FIELD_ALIASES["actor"] + _FIELD_ALIASES["asset"]
            ):
                continue
            identifier = str(value)
            canonical = aliases.get(identifier)
            if canonical and canonical != identifier:
                links.append(
                    EntityLink(
                        source_id,
                        identifier,
                        source_id,
                        canonical,
                        0.95,
                        "alias",
                        f"alias:{identifier}",
                    )
                )
            elif unified_ids:
                links.append(
                    EntityLink(
                        source_id,
                        identifier,
                        source_id,
                        identifier,
                        1.0,
                        "unified-id",
                        f"source:{source_id}",
                    )
                )
    return tuple(dict.fromkeys(links))


def resolve_entity_links(
    sources: Iterable[tuple[str, Iterable[Any]]],
    *,
    aliases: Mapping[str, str] | None = None,
    unified_ids: bool = False,
) -> tuple[EntityLink, ...]:
    """Resolve links across source profiles with explicit provenance.

    Only exact canonical aliases or an explicitly declared unified-id mode can
    create a cross-source link.  Similar-looking values are intentionally left
    distinct instead of becoming a silent false merge.
    """
    canonical = dict(aliases or {})
    values: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for source_id, records in sources:
        for record in records:
            flat = _flatten(record) if isinstance(record, Mapping) else {}
            for key, value in flat.items():
                if value is None or not any(
                    token in key.lower()
                    for token in _FIELD_ALIASES["actor"] + _FIELD_ALIASES["asset"]
                ):
                    continue
                raw = str(value)
                values[canonical.get(raw, raw)].append((source_id, raw, key))
    links: list[EntityLink] = []
    for canonical_id, occurrences in values.items():
        source_ids = {source_id for source_id, _, _ in occurrences}
        if len(source_ids) < 2 and not unified_ids:
            continue
        for index, (left_source, left_id, left_path) in enumerate(occurrences):
            for right_source, right_id, right_path in occurrences[index + 1 :]:
                if left_source == right_source:
                    continue
                same = canonical_id == left_id == right_id
                if not same and canonical.get(left_id, left_id) != canonical.get(
                    right_id, right_id
                ):
                    continue
                links.append(
                    EntityLink(
                        left_source,
                        left_id,
                        right_source,
                        right_id,
                        1.0 if same else 0.95,
                        "unified-id" if same else "alias",
                        f"{left_path}->{right_path}",
                    )
                )
    return tuple(dict.fromkeys(links))


def quality_report(
    records: Sequence[Any], schema: SourceSchema, *, parse_failures: int = 0
) -> QualityReport:
    serialized = [json.dumps(record, sort_keys=True, default=str) for record in records]
    duplicate_count = len(serialized) - len(set(serialized))
    null_rates = {item.path: item.null_rate for item in schema.fields}
    findings = []
    time_values = []
    time_fields = [
        item.path
        for item in schema.fields
        if any(token in item.path.lower() for token in _FIELD_ALIASES["time"])
    ]
    for record in records:
        flat = _flatten(record) if isinstance(record, Mapping) else {}
        for path in time_fields:
            value = flat.get(path)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                time_values.append(float(value))
                break
    gaps = 0
    if len(time_values) >= 3:
        ordered = sorted(set(time_values))
        deltas = [
            right - left for left, right in zip(ordered, ordered[1:], strict=False) if right > left
        ]
        if deltas:
            baseline = sorted(deltas)[len(deltas) // 2]
            gaps = sum(1 for delta in deltas if baseline and delta > baseline * 10)
            if gaps:
                findings.append(f"timeline-gaps:{gaps}")
    if duplicate_count:
        findings.append(f"duplicate-records:{duplicate_count}")
    high_null = [path for path, rate in null_rates.items() if rate > 0.5]
    if high_null:
        findings.append("high-null-fields:" + ",".join(sorted(high_null)))
    if parse_failures:
        findings.append(f"parse-failures:{parse_failures}")
    rate = parse_failures / max(1, len(records))
    score = 1.0 - rate - min(0.5, duplicate_count / max(1, len(records)))
    grade = "A" if score >= 0.95 else "B" if score >= 0.8 else "C" if score >= 0.6 else "D"
    return QualityReport(rate, null_rates, duplicate_count, gaps, 0.0, grade, tuple(findings))


def volume_strategy(record_count: int, *, indexed_limit: int = 100_000) -> VolumeStrategy:
    if record_count <= indexed_limit:
        return VolumeStrategy("indexed", 1.0, 0.0, 0.0, 0.0, "retain-all", "none")
    indexed_fraction = indexed_limit / record_count
    return VolumeStrategy(
        "tiered",
        indexed_fraction,
        min(0.25, 4 * indexed_fraction),
        max(0.0, 1.0 - indexed_fraction),
        0.0,
        f"uniform-sample:{indexed_limit}-records-plus-on-demand",
        "uniform sampling may underrepresent bursty activity",
    )


class SourceCatalog:
    """Versioned registry consulted by the planner."""

    def __init__(self, profiles: Iterable[SourceProfile] = ()) -> None:
        self._profiles: dict[str, SourceProfile] = {
            profile.source_id: profile for profile in profiles
        }
        self.version = self._version()

    def _version(self) -> str:
        payload = [
            profile.to_dict()
            for profile in sorted(self._profiles.values(), key=lambda x: x.source_id)
        ]
        return (
            "catalog-"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[
                :16
            ]
        )

    def register(self, profile: SourceProfile) -> None:
        self._profiles[profile.source_id] = profile
        self.version = self._version()

    def invalidate(self, source_id: str) -> None:
        self._profiles.pop(source_id, None)
        self.version = self._version()

    def get(self, source_id: str) -> SourceProfile | None:
        return self._profiles.get(source_id)

    def profiles(self) -> tuple[SourceProfile, ...]:
        return tuple(self._profiles.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog_version": self.version,
            "sources": [profile.to_dict() for profile in self.profiles()],
        }

    def plan(
        self, seed_id: str, *, required: Iterable[str] = (), sensitivity: str | None = None
    ) -> InvestigationPlan:
        required_set = set(required)
        decisions: list[CatalogDecision] = []
        selected: list[tuple[float, str]] = []
        for profile in self._profiles.values():
            reasons: list[str] = []
            capabilities = profile.capabilities.as_dict()
            missing = sorted(
                capability for capability in required_set if not capabilities.get(capability, False)
            )
            if missing:
                reasons.append("missing-capabilities:" + ",".join(missing))
            if (
                sensitivity
                and not profile.access.export_allowed
                and sensitivity != profile.access.sensitivity
            ):
                reasons.append("sensitivity-restricted")
            if profile.quality.grade == "D":
                reasons.append("quality-grade-D")
            is_selected = not reasons
            decisions.append(
                CatalogDecision(
                    profile.source_id, is_selected, tuple(reasons or ["catalog-capabilities-match"])
                )
            )
            if is_selected:
                cost = profile.access_cost + {"indexed": 0.1, "tiered": 0.5}.get(
                    profile.volume.tier, 1.0
                )
                quality_penalty = {"A": 0.0, "B": 0.1, "C": 0.2, "D": 1.0}.get(
                    profile.quality.grade, 1.0
                )
                selected.append((cost + quality_penalty, profile.source_id))
        return InvestigationPlan(
            seed_id, tuple(item[1] for item in sorted(selected)), tuple(decisions)
        )

    def census(self) -> dict[str, Any]:
        profiles = [
            profile.to_dict()
            for profile in sorted(self._profiles.values(), key=lambda x: x.source_id)
        ]
        blind_spots = []
        for profile in self._profiles.values():
            blind_spots.extend(
                f"{profile.source_id}:missing:{capability}"
                for capability, present in profile.capabilities.as_dict().items()
                if not present
            )
        return {
            "catalog_version": self.version,
            "sources": profiles,
            "blind_spots": sorted(blind_spots),
        }


class CatalogPlanner:
    """Planner facade that makes catalog use explicit at the call site."""

    def __init__(self, catalog: SourceCatalog) -> None:
        self.catalog = catalog

    def select(self, *, seed_id: str, intent: QueryIntent) -> InvestigationPlan:
        requirements = intent.seed.get("required_capabilities") or intent.seed.get("requires") or ()
        return self.catalog.plan(
            seed_id, required=requirements, sensitivity=intent.seed.get("sensitivity")
        )


@dataclass(frozen=True)
class DataPlaneGate:
    passed: bool
    checks: dict[str, bool]
    blockers: tuple[str, ...]


class DataPlane:
    """The ordered Phase 0 service boundary.

    ``connect`` profiles a source once; ``query`` then uses the source in its
    native mode and appends an auditable entry.  The class intentionally keeps
    records out of the catalog and does not copy query-in-place results into a
    common index.
    """

    def __init__(self) -> None:
        self.connectors: dict[str, SourceConnector] = {}
        self.records: dict[str, tuple[Any, ...]] = {}
        self.catalog = SourceCatalog()
        self.audit = QueryAuditLog()
        self.drift_reports: list[dict[str, Any]] = []
        self.live_profile_evidence: dict[str, dict[str, Any]] = {}

    def connect(
        self,
        source_id: str,
        connector: SourceConnector,
        records: Iterable[Any],
        *,
        source_meta: Mapping[str, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        unified_ids: bool = False,
    ) -> SourceProfile:
        observed = tuple(records)
        profile = profile_source(
            source_id,
            connector,
            observed,
            source_meta=source_meta,
            aliases=aliases,
            unified_ids=unified_ids,
        )
        self.connectors[source_id] = connector
        self.records[source_id] = observed
        self.catalog.register(profile)
        return profile

    def query(self, source_id: str, intent: QueryIntent) -> QueryResult:
        connector = self.connectors.get(source_id)
        if connector is None:
            raise KeyError(f"source {source_id!r} is not connected")
        result = connector.read(intent)
        profile = self.catalog.get(source_id)
        self.audit.record(result, sensitivity=profile.access.sensitivity if profile else "internal")
        return result

    def plan(self, seed_id: str, intent: QueryIntent) -> InvestigationPlan:
        return CatalogPlanner(self.catalog).select(seed_id=seed_id, intent=intent)

    def reprofile(self, source_id: str, records: Iterable[Any] | None = None) -> dict[str, Any]:
        profile = self.catalog.get(source_id)
        if profile is None:
            raise KeyError(f"source {source_id!r} is not connected")
        observed = tuple(self.records[source_id] if records is None else records)
        report = detect_drift(profile, observed)
        if report["drifted"]:
            self.catalog.invalidate(source_id)
        self.drift_reports.append(report)
        return report

    def census(self) -> dict[str, Any]:
        report = self.catalog.census()
        report["audit_entries"] = len(self.audit.entries())
        report["drift_reports"] = list(self.drift_reports)
        report["acquisition_gaps"] = capability_gap_acquisition(self.catalog)
        report["live_profile_evidence"] = dict(self.live_profile_evidence)
        return report

    def gate(self) -> DataPlaneGate:
        profiles = self.catalog.profiles()
        checks = {
            "query_in_place": any(profile.capabilities.queryable_in_place for profile in profiles),
            "schemas_discovered": bool(profiles)
            and all(profile.schema.confidence > 0 for profile in profiles),
            "semantic_bindings_declared": bool(profiles)
            and all(profile.bindings for profile in profiles),
            "time_comparability_declared": bool(profiles)
            and all(profile.time_binding is not None for profile in profiles),
            "entity_resolution_operating": bool(profiles)
            and all(profile.entity_links is not None for profile in profiles),
            "catalog_available": bool(profiles),
            "volume_quality_sensitivity": bool(profiles)
            and all(profile.volume and profile.quality and profile.access for profile in profiles),
            "query_audit_available": self.audit is not None,
            "non_telemetry_classes_connected": all(
                any(
                    any(token in profile.source_id.lower() for token in group)
                    for profile in profiles
                )
                for group in (
                    ("advis", "bulletin"),
                    ("case", "ticket"),
                    ("asset", "inventory"),
                    ("coverage", "detection"),
                )
            ),
            "census_published": bool(self.catalog.census()),
        }
        blockers = tuple(name for name, passed in checks.items() if not passed)
        return DataPlaneGate(not blockers, checks, blockers)


def profile_source(
    source_id: str,
    connector: SourceConnector,
    records: Iterable[Any],
    *,
    source_meta: Mapping[str, Any] | None = None,
    aliases: Mapping[str, str] | None = None,
    unified_ids: bool = False,
) -> SourceProfile:
    observed = tuple(records)
    schema = discover_schema(source_id, observed)
    bindings = bind_semantics(schema)
    time_info = bind_time(source_id, schema, bindings, observed)
    entities = resolve_entities(source_id, observed, known_aliases=aliases, unified_ids=unified_ids)
    quality = quality_report(observed, schema)
    metadata = dict(source_meta or {})
    declared = metadata.get("capabilities") or {}
    entity_identity = _binding(bindings, "actor").present or _binding(bindings, "asset").present
    capabilities = CapabilityProfile(
        episode_boundary=bool(
            declared.get(
                "episode_boundary", _binding(bindings, "time").present and len(observed) > 1
            )
        ),
        entity_identity=bool(declared.get("entity_identity", entity_identity)),
        cross_source_entity=bool(declared.get("cross_source_entity", bool(entities))),
        shared_timeline=bool(
            declared.get("shared_timeline", time_info.comparable_with_other_sources)
        ),
        semantic_text=bool(
            declared.get(
                "semantic_text", any(item.observed_type == "string" for item in schema.fields)
            )
        ),
        label_basis=bool(declared.get("label_basis", bool(metadata.get("label_basis")))),
        benign_present=bool(declared.get("benign_present", metadata.get("benign_present", False))),
        queryable_in_place=bool(
            declared.get("queryable_in_place", connector.mode == "query_in_place")
        ),
    )
    sensitivity = str(metadata.get("sensitivity") or "internal")
    access = AccessPolicy(
        sensitivity, metadata.get("credential_ref"), True, sensitivity != "restricted"
    )
    version = (
        "profile-"
        + hashlib.sha256(
            json.dumps(
                {"schema": schema.fingerprint, "capabilities": capabilities.as_dict()},
                sort_keys=True,
            ).encode()
        ).hexdigest()[:16]
    )
    return SourceProfile(
        source_id,
        connector.mode,
        schema,
        bindings,
        time_info,
        capabilities,
        entities,
        volume_strategy(len(observed)),
        quality,
        access,
        int(
            metadata["record_count_override"]
            if metadata.get("record_count_override") is not None
            else len(observed)
        ),
        version,
        freshness_at=metadata.get("freshness_at"),
        access_cost=float(metadata.get("access_cost", 0.0)),
    )


def detect_drift(profile: SourceProfile, records: Iterable[Any]) -> dict[str, Any]:
    new_schema = discover_schema(profile.source_id, records)
    changed = new_schema.fingerprint != profile.schema.fingerprint
    return {
        "source_id": profile.source_id,
        "drifted": changed,
        "invalidate_catalog": changed,
        "old_fingerprint": profile.schema.fingerprint,
        "new_fingerprint": new_schema.fingerprint,
    }


def capability_gap_acquisition(catalog: SourceCatalog) -> list[dict[str, Any]]:
    gaps = Counter(
        capability
        for profile in catalog.profiles()
        for capability, present in profile.capabilities.as_dict().items()
        if not present
    )
    return [
        {
            "capability": capability,
            "priority": count,
            "reason": "catalog gap; acquire correlated data without source-specific branch",
        }
        for capability, count in gaps.most_common()
    ]


def census(catalog: SourceCatalog) -> dict[str, Any]:
    return catalog.census()
