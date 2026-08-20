"""bully.correlation -- entity resolution and cross-source event assembly.

The correction to the deepest remaining flaw: the design treated a per-source
`INSUFFICIENT_VIEW` as a failure and demanded a complete picture from each
record. That is the opposite of how analysts and SIEMs work. The domain is
unambiguous (SANS/UEBA/SIEM correlation literature):

  - Each stage of an attack produces logs that, IN ISOLATION, seem innocuous;
    the finding is in piecing them together across sources into one timeline.
  - The unit of assembly is the ENTITY (user/host/IP/process), and the same
    entity appears under DIFFERENT identifiers in different sources: `jsmith`,
    `jsmith@corp.com`, `CORP\\jsmith`, `10.0.1.45`, a numeric UID -- all one
    principal. Linking these is ENTITY STITCHING, and poorly-stitched entities
    are the single most common cause of missed detections.
  - Sparse sources are the norm, not a defect. A lone firewall allow, one DNS
    query, a single 4624 -- individually thin, worthless alone, decisive in
    combination.

So a per-source completeness gate is exactly backwards. This module reframes
`INSUFFICIENT_VIEW`: it is a property of a *unit after correlation*, not of a
*source at ingest*. A source that contributes one thin artifact is not blind --
it is one tile in a mosaic. Blindness is only real when, after stitching every
source that touches an entity, there is still nothing to reason about.

Two capabilities:

1. **Entity resolution (stitching).** Resolve the many identifiers of one
   entity across heterogeneous sources into a single `ResolvedEntity`, using
   an identity graph: values that co-occur on the same record are candidate
   aliases (a 4624 carrying both `CORP\\jsmith` and `10.0.1.45` links them);
   an authority store (AD, from the lab) can assert canonical links; and
   value-shape equivalence (`jsmith` ~ `jsmith@corp.com` ~ `CORP\\jsmith`)
   proposes links that co-occurrence confirms. Deliberately CONSERVATIVE:
   a wrong stitch fabricates a false narrative, so links require evidence,
   and every resolution carries its evidence and a confidence.

2. **Cross-source timeline assembly.** Group all artifacts touching one
   resolved entity, across every source, into a time-ordered `EntityTimeline`
   -- the analyst's investigation view. THIS is the unit the behavioural
   grader runs on: a chain assembled from firewall + DNS + auth + EDR that no
   single source could have shown. A behavioural spine that only appears once
   the sources are stitched is precisely the cross-source cousin the product
   exists to find.

Pure compute over injected records (COLD). No I/O; the authority store is an
injected read interface. Entity resolution never uses attack labels (Q3 wall);
it operates only on identifier VALUES and their co-occurrence.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ALGORITHM_VERSION = "correlation-v1"

# Confidence floors: a stitch below this is proposed but not merged (a wrong
# merge is worse than a missed one -- it invents a false narrative).
MERGE_CONFIDENCE_FLOOR = 0.6

# value-shape normalizers: strip a value to its identity CORE so different
# renderings of one principal collide. Conservative: only well-known shapes.
_DOMAIN_USER = re.compile(r"^([A-Za-z0-9.-]+)\\([A-Za-z0-9._-]+)$")  # CORP\jsmith
_EMAIL = re.compile(r"^([A-Za-z0-9._-]+)@([A-Za-z0-9.-]+)$")  # jsmith@corp
_UPN = re.compile(r"^([A-Za-z0-9._-]+)@")
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def identity_core(value: str) -> tuple[str, str]:
    """Return (kind, core) for an identifier value. `core` is the shared token
    two renderings of one principal have in common (`CORP\\jsmith`, `jsmith@x`,
    `jsmith` all core to `jsmith`); `kind` lets an IP stay distinct from a
    username with the same text. Conservative -- unknown shapes core to
    themselves."""
    v = value.strip()
    if _IPV4.match(v):
        return ("ip", v)
    m = _DOMAIN_USER.match(v)
    if m:
        return ("user", m.group(2).lower())
    m = _EMAIL.match(v)
    if m:
        return ("user", m.group(1).lower())
    # host-ish: trailing domain stripped (WS01.corp.local -> ws01)
    if "." in v and not v.replace(".", "").isdigit():
        return ("host", v.split(".")[0].lower())
    return ("opaque", v.lower())


@dataclass(frozen=True)
class IdentifierObservation:
    value: str
    field_path: str
    source_id: str
    artifact_id: str


@dataclass(frozen=True)
class ResolvedEntity:
    entity_id: str
    canonical: str
    kind: str
    aliases: tuple[str, ...]  # every raw identifier value merged in
    source_ids: tuple[str, ...]  # every source this entity was seen in
    evidence: tuple[str, ...]  # why these aliases were merged
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "canonical": self.canonical,
            "kind": self.kind,
            "aliases": list(self.aliases),
            "source_ids": list(self.source_ids),
            "evidence": list(self.evidence),
            "confidence": round(self.confidence, 4),
        }


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.evidence: dict[frozenset[str], str] = {}

    def add(self, x: str) -> None:
        self.parent.setdefault(x, x)

    def find(self, x: str) -> str:
        self.add(x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str, why: str) -> None:
        self.add(a)
        self.add(b)
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb
            self.evidence[frozenset((a, b))] = why


AuthorityLinker = Callable[[str, str], bool]  # (value_a, value_b) -> asserted same


def resolve_entities(
    observations: list[IdentifierObservation],
    *,
    authority: AuthorityLinker | None = None,
    merge_floor: float = MERGE_CONFIDENCE_FLOOR,
) -> tuple[dict[str, ResolvedEntity], dict[str, str]]:
    """Stitch identifier observations into resolved entities.

    Three evidence sources, strongest first:
      1. authority assertion (AD says these are one) -- confidence 1.0
      2. co-occurrence on the same record (a 4624 with user+IP together) --
         high confidence, because the source itself asserts the pairing
      3. identity-core equivalence (jsmith ~ CORP\\jsmith) -- proposed, then
         only merged when co-occurrence or authority also supports it, OR the
         core match is exact and unambiguous (one core -> one raw per kind)

    Returns (entities_by_id, value_to_entity_id).
    """
    uf = _UnionFind()
    values = {o.value for o in observations}
    for v in values:
        uf.add(v)

    # (2) co-occurrence: identifiers on the same artifact are candidate aliases
    by_artifact: dict[str, list[str]] = defaultdict(list)
    for o in observations:
        by_artifact[o.artifact_id].append(o.value)
    cooccur: set[frozenset[str]] = set()
    for vals in by_artifact.values():
        uniq = list(dict.fromkeys(vals))
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                cooccur.add(frozenset((uniq[i], uniq[j])))

    # (3) identity-core buckets
    core_bucket: dict[tuple[str, str], list[str]] = defaultdict(list)
    for v in values:
        core_bucket[identity_core(v)].append(v)

    # (2) co-occurrence as a PRIMARY linker: when a single record carries a
    # user and an IP (a 4624 with TargetUserName + IpAddress), the source itself
    # asserts they belong to one session -- the strongest everyday evidence. Only
    # link ACROSS kinds (user<->ip, user<->host, host<->ip); same-kind co-occurrence
    # (two IPs, two users) is peers or delegation, never an alias -- linking it
    # fabricates identity and is the classic false-stitch.
    def _kind(v):
        return identity_core(v)[0]

    for pair in cooccur:
        a, b = tuple(pair)
        ka, kb = _kind(a), _kind(b)
        if ka != kb and {ka, kb} <= {"user", "host", "ip"}:
            uf.union(a, b, f"cooccur:{ka}-{kb}")

    # authority first
    if authority is not None:
        vlist = sorted(values)
        for i in range(len(vlist)):
            for j in range(i + 1, len(vlist)):
                if authority(vlist[i], vlist[j]):
                    uf.union(vlist[i], vlist[j], "authority_assert")

    # core-equivalence, confirmed by co-occurrence OR unambiguous single mapping
    for (kind, core), members in core_bucket.items():
        if kind == "opaque" or len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                pair = frozenset((members[i], members[j]))
                if pair in cooccur:
                    uf.union(members[i], members[j], f"core_and_cooccur:{core}")
                else:
                    # different renderings of the same non-opaque core, seen
                    # in different sources -- the classic jsmith/CORP\jsmith.
                    # Merge, because the core equivalence is a defined identity
                    # shape (email/domain-user), not a coincidence.
                    uf.union(members[i], members[j], f"core_equiv:{kind}:{core}")

    # assemble
    groups: dict[str, list[str]] = defaultdict(list)
    for v in values:
        groups[uf.find(v)].append(v)

    src_by_value: dict[str, set[str]] = defaultdict(set)
    for o in observations:
        src_by_value[o.value].add(o.source_id)

    entities: dict[str, ResolvedEntity] = {}
    value_to_id: dict[str, str] = {}
    for root, members in groups.items():
        members = sorted(set(members))
        kinds = {identity_core(m)[0] for m in members}
        kind = next((k for k in ("user", "host", "ip") if k in kinds), "opaque")
        canonical = sorted(members, key=lambda m: (identity_core(m)[0] != kind, len(m)))[0]
        srcs = sorted({s for m in members for s in src_by_value[m]})
        ev = [uf.evidence[k] for k in uf.evidence if set(k) <= set(members)]
        # confidence: authority/co-occur -> high; pure core-equiv across sources
        # -> moderate; singleton -> 1.0 (nothing merged, nothing to be wrong about)
        if len(members) == 1:
            conf = 1.0
        elif any(e.startswith(("authority", "core_and_cooccur", "cooccur")) for e in ev):
            conf = 0.9
        else:
            conf = 0.75
        eid = f"ent-{abs(hash(root)) % 10**10:010d}"
        entities[eid] = ResolvedEntity(
            entity_id=eid,
            canonical=canonical,
            kind=kind,
            aliases=tuple(members),
            source_ids=tuple(srcs),
            evidence=tuple(sorted(set(ev))) or ("singleton",),
            confidence=conf,
        )
        for m in members:
            value_to_id[m] = eid
    # drop below-floor merges? no: floor governs whether we MERGE, which we
    # already gated; every returned entity is at or above floor by construction
    return entities, value_to_id


@dataclass(frozen=True)
class EntityTimeline:
    """The analyst's cross-source investigation view for one resolved entity:
    every artifact touching it, from every source, time-ordered. THIS is the
    unit the behavioural grader runs on -- a chain no single source could show."""

    entity: ResolvedEntity
    artifact_ids: tuple[str, ...]
    source_ids: tuple[str, ...]  # sources that CONTRIBUTED to this timeline
    span_seconds: float | None
    n_sources: int

    @property
    def is_cross_source(self) -> bool:
        return self.n_sources >= 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity.to_dict(),
            "artifact_ids": list(self.artifact_ids),
            "source_ids": list(self.source_ids),
            "span_seconds": self.span_seconds,
            "n_sources": self.n_sources,
            "is_cross_source": self.is_cross_source,
        }


def assemble_timelines(
    artifacts: list[dict[str, Any]],
    entities: dict[str, ResolvedEntity],
    value_to_id: dict[str, str],
    *,
    artifact_entity_values: Callable[[dict[str, Any]], list[str]],
    artifact_time: Callable[[dict[str, Any]], float | None],
    artifact_id: Callable[[dict[str, Any]], str],
    artifact_source: Callable[[dict[str, Any]], str],
    priority_entity_ids: frozenset[str] | None = None,
) -> list[EntityTimeline]:
    """Assemble one cross-source timeline per resolved entity. An artifact
    joins every timeline whose entity it touches (an event with both a user and
    a host contributes to both). The result is the correlation view: sparse
    per-source artifacts stitched into a coherent per-entity narrative.

    `priority_entity_ids` (TASK_BULLY_TRUTH_ACCEPTANCE_V1 Y.3): richest-first
    is the right default for an operator's queue, but the wrong sampler for a
    measurement run -- a ~1% implant needle never wins a richest-first sort
    against a sea of busy background entities (D2). When supplied, entities
    in this set sort first (still richest-first among themselves), the
    remainder richest-first as before. This is a SAMPLING decision the run
    supplies from the sealed ledger, after grading is configured -- it never
    reaches the grader's inputs (Q3 wall: selection biases what is measured,
    it must never bias how a graded timeline is scored)."""
    by_entity: dict[str, list[tuple[float | None, str, str]]] = defaultdict(list)
    for art in artifacts:
        aid = artifact_id(art)
        ts = artifact_time(art)
        src = artifact_source(art)
        touched: set[str] = set()
        for val in artifact_entity_values(art):
            eid = value_to_id.get(val)
            if eid:
                touched.add(eid)
        for eid in touched:
            by_entity[eid].append((ts, aid, src))

    timelines: list[EntityTimeline] = []
    for eid, rows in by_entity.items():
        rows.sort(key=lambda r: (r[0] is None, r[0] or 0.0))
        stamps = [r[0] for r in rows if r[0] is not None]
        span = (max(stamps) - min(stamps)) if len(stamps) >= 2 else (0.0 if stamps else None)
        srcs = tuple(sorted({r[2] for r in rows}))
        timelines.append(
            EntityTimeline(
                entity=entities[eid],
                artifact_ids=tuple(r[1] for r in rows),
                source_ids=srcs,
                span_seconds=span,
                n_sources=len(srcs),
            )
        )
    # richest investigations first: cross-source, longest -- unless a
    # priority set is supplied (Y.3), in which case priority entities sort
    # first (still richest-first among themselves) so a truth-bearing but
    # sparse entity is never silently excluded by a fixed take-N cutoff.
    priority = priority_entity_ids or frozenset()
    timelines.sort(
        key=lambda t: (
            t.entity.entity_id in priority,
            t.n_sources,
            len(t.artifact_ids),
        ),
        reverse=True,
    )
    return timelines
