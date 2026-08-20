"""bully.field_roles -- infer the ROLE of each field from the data itself.

This is the correction to the defect that invalidated the M.3 run: the
artifact graph read entities, timestamps and actions from hardcoded field-
name lists (`userIdentity.arn`, `eventTime`, `eventName`, ...). Those names
are CloudTrail's. Pointed at Sysmon or osquery -- whose identity lives in
`hostIdentifier`, whose time lives in `calendarTime`, and whose `action`
field holds `added`/`removed` (a diff-type, not a behaviour) -- extraction
silently returned nothing: no entities, no timestamps, every action mapped
to `other`. Extraction failure then degraded into a shared `other` shape,
a shape match became a confident concern, and nothing reported that the
adapter had failed. A hardcoded field list *is* a schema normalization, so
the "source-agnostic" claim was false the moment a second schema arrived.

Universality cannot come from a longer name list -- there is always another
schema. It comes from inferring what a field *is* from how its values
behave, which is schema-independent by construction:

    ENTITY     moderate-cardinality, recurs across records, string-ish:
               identities, hosts, keys, IPs -- the things you pivot on.
    TIMESTAMP  values parse as time and (roughly) advance across the stream.
    ACTION     low-cardinality categorical that co-varies with record shape:
               the verb/operation/event-type.
    PAYLOAD    high-cardinality free text, hashes, blobs -- carried, not
               pivoted on.
    CONSTANT   ~one value across the sample -- an index name, an account the
               whole export belongs to: structurally uninformative alone.

The output is a `FieldRoleMap` the artifact graph consumes instead of its
name lists. Crucially this module also decides when extraction has FAILED
for a source -- too few entities or timestamps inferable -- which becomes a
loud source-level `INSUFFICIENT_VIEW`, never a silent collapse into `other`.

Pure compute over sampled records. No I/O, no model calls (COLD). Values are
inspected structurally; raw payload contents are never emitted or logged.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

ALGORITHM_VERSION = "field-roles-v1"

ROLES: tuple[str, ...] = ("ENTITY", "TIMESTAMP", "ACTION", "PAYLOAD", "CONSTANT", "EMPTY")

# A source that cannot yield entities OR timestamps for most records cannot be
# related structurally at all -- that is an instrument finding about the
# adapter, reported loudly, never absorbed into the grade.
MIN_ENTITY_COVERAGE = 0.5
MIN_TIMESTAMP_COVERAGE = 0.5

# Cardinality bands are expressed as ratios of distinct values to sample size,
# so they hold whether the sample is 50 records or 5000.
_ACTION_MAX_DISTINCT_RATIO = 0.25
_ACTION_MAX_DISTINCT_ABS = 64
_ENTITY_MIN_DISTINCT_RATIO = 0.02
# An entity's values RECUR -- you pivot on a host or user that appears across
# many records. A field that is near-unique per record (a request id, a GUID
# per event) is an identifier OF the record, not a thing you pivot on.
_ENTITY_MAX_DISTINCT_RATIO = 0.80
_CONSTANT_MAX_DISTINCT = 1
_CONSTANT_MIN_COVERAGE = 0.5

# R.5b-fix: a COHESIVE identifier column (nearly all values share one
# identifier template -- IP, GUID, ARN, path, or a `stem-NNN` counter shape)
# is ENTITY at ANY cardinality. A busy real source legitimately has hundreds
# of distinct hosts/users; demanding low cardinality on top of identifier
# shape (the pre-fix rule) wrongly demoted a source's own identity column to
# PAYLOAD once it had more than _ENTITY_MAX_DISTINCT_RATIO distinct values.
# Only a near-unique column that is ALSO incohesive (mixed template shapes,
# e.g. free-text record ids) is the genuine per-record-id PAYLOAD case.
_COHESIVE_TEMPLATE_MIN_RATE = 0.9

_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_GUIDISH = re.compile(r"^[{(]?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-", re.ASCII)
_ARNISH = re.compile(r"^arn:|:iam:|@|\\", re.ASCII)
_HEX_BLOB = re.compile(r"^[0-9a-fA-F]{32,}$")
# A strong identifier carries structure a verb/operation never does. This is
# the real ENTITY-vs-ACTION discriminator: `host-3`/`WS01`/`user0` mix a name
# stem with a digit run; ARNs, IPs, GUIDs, principals and paths are patently
# identifiers. `AssumeRole`, `added`, `EventID=3` are not.
_IDENT_DIGITRUN = re.compile(r"[A-Za-z].*\d|\d.*[A-Za-z]")
_PATHISH = re.compile(r"[/\\]")

# Below this many records, per-field cardinality statistics are too thin to
# trust alone (a 3-verb chain has every verb "unique" by chance, not because
# the field is free text). Below the floor, a name hint may break a tie that
# the statistics genuinely cannot -- last resort, never primary (E.2).
_MIN_STATISTICAL_SAMPLE = 20
_ENTITY_NAME_HINTS = (
    "user",
    "host",
    "identity",
    "account",
    "actor",
    "principal",
    "device",
    "asset",
    "arn",
    "ip",
)
_ACTION_NAME_HINTS = (
    "action",
    "event",
    "verb",
    "operation",
    "command",
    "cmdline",
    "signature",
)

_TIME_HINTS = ("time", "date", "stamp", "@timestamp", "_time", "created", "occurred")
_TIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%b %d %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%a %b %d %H:%M:%S %Y",
    "%a %b %d %H:%M:%S %Y %Z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
)


def _flatten(record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Dotted-path flatten so nested schemas (CloudTrail's `userIdentity.arn`,
    Sysmon's `Event.EventData.Image`) present their leaves uniformly. Lists
    are indexed shallowly; deep payload trees are summarized, not exploded."""
    out: dict[str, Any] = {}
    for key, value in record.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, prefix=f"{path}."))
        elif isinstance(value, list):
            if value and all(not isinstance(v, (dict, list)) for v in value):
                out[path] = tuple(value)
            else:
                out[f"{path}.__len__"] = len(value)
        else:
            out[path] = value
    return out


def _parse_time(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # plausible epoch seconds or millis for the last ~decade
        if 1_000_000_000 <= value <= 2_000_000_000:
            return float(value)
        if 1_000_000_000_000 <= value <= 2_000_000_000_000:
            return float(value) / 1000.0
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None:
        return _parse_time(numeric)
    import datetime as _dt

    candidates = [text]
    if text.endswith(" UTC"):
        candidates.append(text[:-4])
    for candidate in candidates:
        for fmt in _TIME_FORMATS:
            try:
                return _dt.datetime.strptime(candidate, fmt).timestamp()
            except ValueError:
                continue
    return None


def _looks_entity(value: Any) -> bool:
    """Weak signal: could this VALUE be an identifier at all (not free text,
    not a hash blob, not a bare count)."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or len(text) > 256:
        return False
    if text.isdigit():
        return False
    return len(text) <= 128 and text.count(" ") <= 1 and not _HEX_BLOB.match(text)


def _strong_identifier(value: Any) -> bool:
    """Strong signal: this value has the STRUCTURE of a thing you pivot on --
    an IP, GUID, ARN/email/principal, a path, or a name+digit-run TOKEN
    (`svc344`, `host-3`, `dev-248` -- the ubiquitous `stem-NNN` counter-id
    shape). A closed-vocabulary verb (`AssumeRole`, `added`) has none of
    these, which is what lets ACTION and ENTITY separate without a field-name
    list. The digit-run check requires a single whitespace-free token: a
    free-text sentence that happens to contain a digit (`"free text 3
    unrelated content"`) is not a counter-id and must not qualify -- without
    this, `_IDENT_DIGITRUN`'s unanchored letter/digit search matches almost
    any prose containing a number."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or len(text) > 256:
        return False
    if _IPV4.match(text) or _GUIDISH.match(text) or _ARNISH.search(text):
        return True
    if _PATHISH.search(text):
        return True
    if " " in text:
        return False
    return bool(_IDENT_DIGITRUN.search(text))


def _identifier_template(value: Any) -> str:
    """The identifier SHAPE a value belongs to, coarse enough that every
    rendering of "the same kind of id" collides: an IP/GUID/ARN/path each get
    their own bucket, and the ubiquitous `stem-NNN` counter-id shape
    (`svc344`, `dev-248`, `host-3`) collapses its digit run so `svc1` and
    `svc9999` land in the same template. Values with no recognizable shape
    bucket to themselves (incohesive)."""
    if not isinstance(value, str):
        return "opaque"
    text = value.strip()
    if _IPV4.match(text):
        return "ipv4"
    if _GUIDISH.match(text):
        return "guid"
    if _ARNISH.search(text):
        return "arn"
    if _PATHISH.search(text):
        return "path"
    if _IDENT_DIGITRUN.search(text):
        return re.sub(r"\d+", "#", text)
    return "opaque"


def _cohesion_rate(values: list[Any]) -> float:
    """Fraction of STRONG-IDENTIFIER-shaped values sharing the single most
    common identifier template. A cohesive column (nearly all `stem-NNN`, or
    nearly all IPs) is one identity kind at any cardinality; an incohesive
    one (a grab-bag of unrelated shapes) is not a real pivot column even if
    every individual value looks identifier-ish.

    GUID-templated values are deliberately excluded from ever counting as
    cohesion evidence: a per-event GUID (`requestID`) is the archetypal
    record identifier -- globally unique by construction, never a pivotable
    entity -- so a column of nothing but GUIDs must stay incohesive here and
    fall through to the near-unique-record-id PAYLOAD rule, however uniform
    the GUID shape looks. `stem-NNN` counter ids (`svc344`, `host-3`), IPs,
    ARNs, and paths are the genuine cohesive-entity shapes.
    """
    templates = [_identifier_template(v) for v in values if _strong_identifier(v)]
    templates = [t for t in templates if t != "guid"]
    if not templates:
        return 0.0
    counts = Counter(templates)
    return counts.most_common(1)[0][1] / len(templates)


@dataclass(frozen=True)
class FieldProfile:
    name: str
    role: str
    coverage: float  # fraction of records where the field is present+nonempty
    distinct_ratio: float
    distinct_count: int
    time_parse_rate: float
    entity_like_rate: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "coverage": round(self.coverage, 4),
            "distinct_ratio": round(self.distinct_ratio, 4),
            "distinct_count": self.distinct_count,
            "time_parse_rate": round(self.time_parse_rate, 4),
            "entity_like_rate": round(self.entity_like_rate, 4),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class FieldRoleMap:
    source_id: str
    sample_size: int
    profiles: dict[str, FieldProfile]
    extraction_valid: bool
    entity_coverage: float
    timestamp_coverage: float
    action_coverage: float
    failure_reasons: tuple[str, ...]

    def fields_for(self, role: str) -> tuple[str, ...]:
        return tuple(sorted(name for name, p in self.profiles.items() if p.role == role))

    @property
    def entity_fields(self) -> tuple[str, ...]:
        return self.fields_for("ENTITY")

    @property
    def timestamp_fields(self) -> tuple[str, ...]:
        return self.fields_for("TIMESTAMP")

    @property
    def action_fields(self) -> tuple[str, ...]:
        return self.fields_for("ACTION")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "sample_size": self.sample_size,
            "extraction_valid": self.extraction_valid,
            "entity_coverage": round(self.entity_coverage, 4),
            "timestamp_coverage": round(self.timestamp_coverage, 4),
            "action_coverage": round(self.action_coverage, 4),
            "failure_reasons": list(self.failure_reasons),
            "profiles": {n: p.to_dict() for n, p in sorted(self.profiles.items())},
        }


def _decide_role(
    *,
    name_lc: str,
    distinct: int,
    distinct_ratio: float,
    coverage: float,
    time_rate: float,
    entity_rate: float,
    strong_rate: float,
    sample_size: int = _MIN_STATISTICAL_SAMPLE,
    cohesion_rate: float = 0.0,
) -> tuple[str, tuple[str, ...]]:
    """Role by strongest evidence, not by branch order.

    The decisive discriminator between ACTION and ENTITY -- both of which can
    be low-cardinality and recurring -- is *entity shape*: a host or user
    looks like an identifier (`host-3`, `CORP\\alice`, an IP), while a verb
    (`added`, `AssumeRole`) does not. So an entity-shaped low-cardinality
    field is an ENTITY you can pivot on; a non-entity-shaped low-cardinality
    field is the ACTION. This is what makes the two separable without a name
    list.

    Below `_MIN_STATISTICAL_SAMPLE` records, cardinality ratios stop being
    trustworthy on their own -- a 3-step chain makes every verb "distinct"
    by construction, not because the field is free text. Below that floor, a
    generic name hint may resolve what the statistics genuinely cannot; this
    is the last-resort fallback the module docstring promises, never the
    primary path (E.2) -- it only ever fires when distinct-value evidence
    alone is ambiguous.
    """
    small_sample = sample_size < _MIN_STATISTICAL_SAMPLE
    entity_hinted = any(h in name_lc for h in _ENTITY_NAME_HINTS)
    action_hinted = any(h in name_lc for h in _ACTION_NAME_HINTS)

    # TIMESTAMP is decided before CONSTANT: a field that is parseable as
    # time is a timestamp even in a one-record sample (where every field is
    # trivially "single-valued" by construction, `distinct <= 1`) -- the
    # CONSTANT check must never shadow it.
    if time_rate >= 0.9 or (time_rate >= 0.6 and any(h in name_lc for h in _TIME_HINTS)):
        return "TIMESTAMP", (f"time_parse_rate={time_rate:.2f}",)

    if distinct <= _CONSTANT_MAX_DISTINCT:
        # A field present across (nearly) the whole sample with one value is
        # a genuine constant -- an index name, the account the whole export
        # belongs to. A field that is *sparse* (present on a minority of
        # records) but structurally identifier-shaped where it does appear
        # is a rare-but-real entity (a single attacker identity threaded
        # through a handful of records in an otherwise benign stream) --
        # exactly the case a low-and-slow chain produces, and exactly what
        # CONSTANT must not swallow.
        if strong_rate >= 0.6 and coverage < _CONSTANT_MIN_COVERAGE:
            return "ENTITY", (
                f"single_value_but_sparse_strong_identifier(coverage={coverage:.2f})",
            )
        if small_sample and entity_hinted:
            return "ENTITY", (f"small_sample_entity_name_hint(n={sample_size})",)
        if small_sample and action_hinted:
            return "ACTION", (f"small_sample_action_name_hint(n={sample_size})",)
        return "CONSTANT", ("single_value_in_sample",)

    low_card = (
        distinct <= _ACTION_MAX_DISTINCT_ABS
        and distinct_ratio <= _ACTION_MAX_DISTINCT_RATIO
        and coverage >= 0.5
    )
    is_identifier = strong_rate >= 0.6

    # ENTITY: structurally an identifier (strong signal) AND recurs across
    # records. Near-unique identifiers are record ids (request id, per-event
    # GUID) -> PAYLOAD, never pivoted on -- UNLESS the column is COHESIVE (one
    # identifier template dominates: nearly all IPs, or nearly all `stem-NNN`
    # counter ids), in which case high cardinality is expected of a busy real
    # source's own identity column, not evidence it is a record id (R.5b-fix).
    if is_identifier and distinct_ratio <= _ENTITY_MAX_DISTINCT_RATIO:
        return "ENTITY", (f"strong_identifier={strong_rate:.2f} recurs(dr={distinct_ratio:.2f})",)
    if is_identifier and distinct_ratio > _ENTITY_MAX_DISTINCT_RATIO:
        if cohesion_rate >= _COHESIVE_TEMPLATE_MIN_RATE:
            return "ENTITY", (
                f"cohesive_identifier_template(cohesion={cohesion_rate:.2f}) at any cardinality",
            )
        return "PAYLOAD", (
            f"identifier_but_unique_per_record_and_incohesive"
            f"(dr={distinct_ratio:.2f}, cohesion={cohesion_rate:.2f})",
        )

    # ACTION: a low-cardinality categorical that is NOT an identifier -- a verb
    # from a closed vocabulary (`added`, `AssumeRole`, `EventID=3`).
    if low_card:
        return "ACTION", (f"closed_vocabulary_verb={distinct}({distinct_ratio:.2f})",)
    if small_sample and action_hinted and distinct <= _ACTION_MAX_DISTINCT_ABS and coverage >= 0.5:
        return "ACTION", (f"small_sample_action_name_hint(n={sample_size})",)

    return "PAYLOAD", (f"high_card_freetext dr={distinct_ratio:.2f} strong={strong_rate:.2f}",)


def infer_field_roles(
    records: list[dict[str, Any]],
    *,
    source_id: str = "",
    min_entity_coverage: float = MIN_ENTITY_COVERAGE,
    min_timestamp_coverage: float = MIN_TIMESTAMP_COVERAGE,
) -> FieldRoleMap:
    """Infer a role for every field from value behaviour, and decide whether
    the source is structurally extractable at all.

    When records carry `__source_id` (the multi-schema blend/live-capture
    shape), a field's *coverage* is measured against only the records drawn
    from the source(s) that field actually appears in, not the whole
    cross-schema pool. Without this, a field present in every record of one
    schema but absent from every other schema in the pool -- e.g.
    CloudTrail's `awsRegion` when blended with Sysmon/osquery/firewall
    records -- reads as globally sparse purely because most of the pool is
    a different schema, which used to trip the sparse-strong-identifier
    ENTITY override on a field that is a genuine whole-source CONSTANT.
    Coverage inside a single-schema sample (or one with no `__source_id`
    at all) is unaffected: with one source, "that field's home sources"
    is the whole pool, identical to the old denominator.
    """
    flat = [_flatten(r) for r in records if isinstance(r, dict)]
    n = len(flat)
    if n == 0:
        return FieldRoleMap(source_id, 0, {}, False, 0.0, 0.0, 0.0, ("empty_sample",))

    record_sources = [str(r.get("__source_id") or source_id or "") for r in flat]
    source_record_counts = Counter(record_sources)

    present: dict[str, list[Any]] = defaultdict(list)
    field_home_sources: dict[str, set[str]] = defaultdict(set)
    for idx, record in enumerate(flat):
        for name, value in record.items():
            if value is None or value == "" or value == ():
                continue
            present[name].append(value)
            field_home_sources[name].add(record_sources[idx])

    profiles: dict[str, FieldProfile] = {}
    for name, values in present.items():
        home_sources = field_home_sources[name]
        coverage_denominator = sum(source_record_counts[s] for s in home_sources) or n
        coverage = len(values) / coverage_denominator
        distinct = len({repr(v) for v in values})
        distinct_ratio = distinct / len(values)
        time_hits = sum(1 for v in values if _parse_time(v) is not None)
        time_rate = time_hits / len(values)
        entity_hits = sum(1 for v in values if _looks_entity(v))
        entity_rate = entity_hits / len(values)
        strong_hits = sum(1 for v in values if _strong_identifier(v))
        strong_rate = strong_hits / len(values)
        cohesion_rate = _cohesion_rate(values)

        name_lc = name.lower()

        # Fields commonly satisfy more than one predicate (a host id is both
        # low-cardinality AND entity-shaped). An ordered elif-cascade would let
        # whichever branch comes first win by accident, which is exactly how
        # hostIdentifier landed as ACTION. Score each role on the evidence and
        # take the strongest, with deterministic tiebreaks.
        role, reasons = _decide_role(
            name_lc=name_lc,
            distinct=distinct,
            distinct_ratio=distinct_ratio,
            coverage=coverage,
            time_rate=time_rate,
            entity_rate=entity_rate,
            strong_rate=strong_rate,
            sample_size=n,
            cohesion_rate=cohesion_rate,
        )

        profiles[name] = FieldProfile(
            name=name,
            role=role,
            coverage=coverage,
            distinct_ratio=distinct_ratio,
            distinct_count=distinct,
            time_parse_rate=time_rate,
            entity_like_rate=entity_rate,
            reasons=tuple(reasons),
        )

    # There is usually exactly one true action field. If several qualified,
    # keep the best categorical (highest coverage, lowest cardinality) as
    # ACTION and demote the rest to PAYLOAD, so the shape sequence is stable.
    action_candidates = [p for p in profiles.values() if p.role == "ACTION"]
    if len(action_candidates) > 1:
        action_candidates.sort(key=lambda p: (-p.coverage, p.distinct_count))
        for demoted in action_candidates[1:]:
            profiles[demoted.name] = FieldProfile(
                **{
                    **demoted.__dict__,
                    "role": "PAYLOAD",
                    "reasons": demoted.reasons + ("demoted_secondary_action",),
                }
            )

    entity_cov = _role_record_coverage(flat, profiles, "ENTITY")
    time_cov = _role_record_coverage(flat, profiles, "TIMESTAMP")
    action_cov = _role_record_coverage(flat, profiles, "ACTION")

    failure_reasons: list[str] = []
    if entity_cov < min_entity_coverage:
        failure_reasons.append(f"entity_coverage_{entity_cov:.2f}<{min_entity_coverage}")
    if time_cov < min_timestamp_coverage:
        failure_reasons.append(f"timestamp_coverage_{time_cov:.2f}<{min_timestamp_coverage}")
    extraction_valid = not failure_reasons

    return FieldRoleMap(
        source_id=source_id,
        sample_size=n,
        profiles=profiles,
        extraction_valid=extraction_valid,
        entity_coverage=entity_cov,
        timestamp_coverage=time_cov,
        action_coverage=action_cov,
        failure_reasons=tuple(failure_reasons),
    )


def _role_record_coverage(
    flat: list[dict[str, Any]], profiles: dict[str, FieldProfile], role: str
) -> float:
    names = [n for n, p in profiles.items() if p.role == role]
    if not names or not flat:
        return 0.0
    hits = 0
    for record in flat:
        if any(record.get(n) not in (None, "", ()) for n in names):
            hits += 1
    return hits / len(flat)
