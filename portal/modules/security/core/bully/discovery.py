"""bully.discovery -- data-intrinsic discovery and cousins among OBSERVATIONS.

The inversion this module exists to make. As built, `unit_outcome.resolve_
unit_outcome` consults the anchor library FIRST and falls back to the
baseline only when nothing matched:

    matches = [... if r.overall_relation in ("EXACT", "SIMILAR")]
    if matches:   outcome = KNOWN_INSTANCE / UNKNOWN_SAME / COUSIN / ...
    else:         outcome = "NOVEL" if baseline.is_remarkable(unit) else "NORMAL"

So the library decides everything and the baseline is a tiebreaker. That is a
signature database with an anomaly fallback, and whichever way the library
leans determines 100% of outcomes -- which is precisely the observed history:
a library that matched everything (token-Jaccard, X.6/Y.6) never let the
baseline run at all; a library that matched nothing (series, W.6) sent every
unit to the fallback. Two graders, one architecture, degenerate both ways.

A catalogue can only ever find what someone already enumerated, and a cousin
by definition is not enumerated. Known-bad matching is the floor -- we have
tagged attack data and matching it is easy. The product is everything else,
on universal data, across source types nobody wrote a rule for.

So discovery here is **data-intrinsic and primary**:

  * `remarkability` -- how unusual a unit is for THIS environment, from the
    environment's own observed distribution (`baseline.py`), never from the
    type library. Works on the hundredth schema as well as the first.
  * `cohesion` -- structural coherence from the artifact graph: does this
    unit hang together (shared entity, causal link, tight span) or is it an
    accident of grouping.

and cousinhood is **among observations**:

  * `find_cousin_clusters` -- two entities doing structurally similar
    *unusual* things are cousins OF EACH OTHER. No catalogue is consulted.
    This primitive has never existed in this codebase: every comparison
    (`relate`, `decide_cousin`, `grade_unit_against_type`,
    `grade_unit_against_library`, `relate_cousin`) compares an observation
    against the library. Zero compare two observations. You do not need a
    name for either thing to see that they rhyme -- which is what makes
    "unknown but similar" tractable without knowing what either one is.

The library returns as **enrichment**: once something is discovered, ask
whether it resembles a known type and attach that as context and a name.
`resembles nothing` is a first-class result, never a miss.

Pure compute over injected units and an injected baseline (COLD). No I/O, no
model calls, no catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .artifact_graph import GradeableUnit
from .baseline import NormalBaseline, _feature_tokens

ALGORITHM_VERSION = "discovery-v1"

# A unit must be unusual for its environment before it is a discovery
# candidate. This is the PRIMARY gate and it is library-free.
DISCOVERY_MIN_REMARKABILITY = 0.6

# How many of the RAREST tokens define unusualness. `baseline.remarkability`
# averages rarity over ALL of a unit's tokens, which dilutes the signal:
# measured on a 120-unit environment, an attack unit carrying two
# never-before-seen behavioural transitions (rarity 1.000 each) scored a MEAN
# of 0.483 -- below threshold -- because five boilerplate tokens every unit
# shares (edge_mix, entity_role, span_bucket, and a common bigram) averaged it
# down. Unusualness is evidenced by the PRESENCE of something rare, not by the
# average commonness of everything; the same unit's top-3 mean is 0.936.
DISCOVERY_TAIL_K = 3

# Structural coherence floor: a unit whose artifacts share no entity, no
# causal link and no tight span is an accident of grouping, not an episode.
DISCOVERY_MIN_COHESION = 0.34

# Two observations are cousins when their structural signatures agree this
# closely. Deliberately stricter than a library match: with no catalogue to
# anchor it, only a strong mutual resemblance is meaningful.
COUSIN_MAX_DISTANCE = 0.45

# A cluster of one is not a pattern. Recurrence across DIFFERENT entities is
# the signal -- the same unusual shape appearing on several principals.
MIN_CLUSTER_SIZE = 2


def tail_remarkability(
    unit: GradeableUnit, baseline: NormalBaseline, *, k: int = DISCOVERY_TAIL_K
) -> float:
    """Unusualness as the mean rarity of a unit's `k` RAREST feature tokens.

    `baseline.remarkability`'s mean-over-all-tokens is the right shape for
    "how ordinary is this overall" but the wrong shape for "does this contain
    something never seen here", which is what discovery asks. Structural
    boilerplate (size/span/edge-mix/entity-role) is present on every unit and
    swamps the few tokens that actually carry the signal. Taking the tail
    keeps the baseline's own frequencies -- and its level partitioning, which
    E.4 fixed -- while asking the question discovery needs answered.
    """
    fitted = baseline.fitted_units_at(unit.level)
    tokens = _feature_tokens(unit)
    if fitted == 0 or not tokens:
        return 0.0
    rarities = sorted(
        (1.0 - baseline.token_frequency(t, level=unit.level) for t in tokens), reverse=True
    )
    top = rarities[: max(1, k)]
    return sum(top) / len(top)


def cohesion(unit: GradeableUnit) -> float:
    """Structural coherence in [0,1] from the graph facts the unit already
    carries -- edge kinds present, entity concentration, span tightness.
    Library-free by construction."""
    if unit.size <= 1:
        return 1.0  # a single artifact is trivially coherent
    score = 0.0
    kinds = set(unit.edge_kinds or ())
    if "shared_entity" in kinds:
        score += 0.4
    if "causal_parent" in kinds:
        score += 0.4
    if "temporal_adjacency" in kinds:
        score += 0.2
    # a unit spanning a whole capture window is a bucket, not an episode
    if unit.span_seconds is not None and unit.span_seconds <= 3600.0:
        score += 0.2
    return min(1.0, score)


@dataclass(frozen=True)
class Discovery:
    """A unit that is unusual for its environment and structurally coherent.
    Found WITHOUT consulting any catalogue."""

    unit_id: str
    level: str
    entities: tuple[str, ...]
    remarkability: float
    cohesion: float
    salience: float
    n_sources: int
    span_seconds: float | None
    shape: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "level": self.level,
            "entities": list(self.entities),
            "remarkability": round(self.remarkability, 4),
            "cohesion": round(self.cohesion, 4),
            "salience": round(self.salience, 4),
            "n_sources": self.n_sources,
            "span_seconds": self.span_seconds,
            "shape": list(self.shape),
        }


def _shape(unit: GradeableUnit) -> tuple[str, ...]:
    return tuple(unit.structural_signature.get("class_sequence") or ())


def discover(
    units: list[GradeableUnit],
    baseline: NormalBaseline,
    *,
    min_remarkability: float = DISCOVERY_MIN_REMARKABILITY,
    min_cohesion: float = DISCOVERY_MIN_COHESION,
) -> tuple[list[Discovery], dict[str, Any]]:
    """PRIMARY discovery: unusual-for-this-environment AND coherent. The
    anchor library is not consulted and is not a parameter."""
    out: list[Discovery] = []
    n_unremarkable = 0
    n_incoherent = 0
    for unit in units:
        r = tail_remarkability(unit, baseline)
        c = cohesion(unit)
        if r < min_remarkability:
            n_unremarkable += 1
            continue
        if c < min_cohesion:
            n_incoherent += 1
            continue
        out.append(
            Discovery(
                unit_id=unit.unit_id,
                level=unit.level,
                entities=unit.entities,
                remarkability=r,
                cohesion=c,
                salience=r * c,
                n_sources=len(unit.source_ids),
                span_seconds=unit.span_seconds,
                shape=_shape(unit),
            )
        )
    out.sort(key=lambda d: d.salience, reverse=True)
    report = {
        "algorithm_version": ALGORITHM_VERSION,
        "units_examined": len(units),
        "discovered": len(out),
        "rejected_unremarkable": n_unremarkable,
        "rejected_incoherent": n_incoherent,
        "discovery_rate": round(len(out) / len(units), 4) if units else None,
    }
    return out, report


# ── cousins among observations ─────────────────────────────────────────────


def _shape_distance(a: tuple[str, ...], b: tuple[str, ...]) -> float:
    """Distance between two observed shapes. Order-aware (a technique's
    choke point is an ordered spine) but tolerant of insertions, via the
    longest common subsequence normalized by the longer shape."""
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
    lcs = dp[0][0]
    return 1.0 - (lcs / max(m, n))


@dataclass(frozen=True)
class CousinCluster:
    """Observations that resemble each other. No catalogue was consulted, so
    this cluster is meaningful even when nothing in it is known."""

    cluster_id: str
    members: tuple[str, ...]  # unit_ids
    entities: tuple[str, ...]  # distinct entities represented
    shared_shape: tuple[str, ...]
    mean_remarkability: float
    n_distinct_entities: int
    cohesion: float

    @property
    def recurs_across_entities(self) -> bool:
        return self.n_distinct_entities >= MIN_CLUSTER_SIZE

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "members": list(self.members),
            "entities": list(self.entities),
            "shared_shape": list(self.shared_shape),
            "mean_remarkability": round(self.mean_remarkability, 4),
            "n_distinct_entities": self.n_distinct_entities,
            "cohesion": round(self.cohesion, 4),
            "recurs_across_entities": self.recurs_across_entities,
        }


def _lcs_shape(a: tuple[str, ...], b: tuple[str, ...]) -> tuple[str, ...]:
    m, n = len(a), len(b)
    if not m or not n:
        return ()
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
    out: list[str] = []
    i = j = 0
    while i < m and j < n:
        if a[i] == b[j]:
            out.append(a[i])
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return tuple(out)


def find_cousin_clusters(
    discoveries: list[Discovery],
    *,
    max_distance: float = COUSIN_MAX_DISTANCE,
    min_cluster_size: int = MIN_CLUSTER_SIZE,
) -> list[CousinCluster]:
    """Cluster discoveries by mutual resemblance -- cousins OF EACH OTHER.

    Single-link agglomeration on shape distance. The catalogue is never
    consulted: a cluster of three entities running the same unusual shape is
    a finding whether or not any of them matches a known technique, which is
    the entire point of "unknown but similar".
    """
    n = len(discoveries)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i in range(n):
        for j in range(i + 1, n):
            if _shape_distance(discoveries[i].shape, discoveries[j].shape) <= max_distance:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    clusters: list[CousinCluster] = []
    for root, idxs in groups.items():
        if len(idxs) < min_cluster_size:
            continue
        members = [discoveries[i] for i in idxs]
        shared = members[0].shape
        for m in members[1:]:
            shared = _lcs_shape(shared, m.shape)
        entities = sorted({e for m in members for e in m.entities})
        clusters.append(
            CousinCluster(
                cluster_id=f"cc-{root:04d}",
                members=tuple(m.unit_id for m in members),
                entities=tuple(entities),
                shared_shape=shared,
                mean_remarkability=sum(m.remarkability for m in members) / len(members),
                n_distinct_entities=len(entities),
                cohesion=sum(m.cohesion for m in members) / len(members),
            )
        )
    clusters.sort(key=lambda c: (c.n_distinct_entities, c.mean_remarkability), reverse=True)
    return clusters


# ── the library, demoted to enrichment ─────────────────────────────────────


@dataclass(frozen=True)
class Enrichment:
    """What a discovery resembles, if anything. Context and a NAME -- never
    the reason it was surfaced. `resembles_nothing` is a first-class result."""

    resembles_type: str | None
    resembles_technique: str | None
    distance: float | None
    relation: str  # EXACT | SIMILAR | NONE
    malice: str | None

    @property
    def resembles_nothing(self) -> bool:
        return self.resembles_type is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resembles_type": self.resembles_type,
            "resembles_technique": self.resembles_technique,
            "distance": self.distance,
            "relation": self.relation,
            "malice": self.malice,
            "resembles_nothing": self.resembles_nothing,
        }


def enrich(
    shape: tuple[str, ...],
    library_shapes: list[tuple[str, Any]],
    *,
    exact_max: float = 0.10,
    similar_max: float = 0.45,
) -> Enrichment:
    """Name a discovery against the catalogue, AFTER it has been discovered.

    `library_shapes` is [(anchor_id, anchor)] where each anchor's shape is
    read from its record. Returning `resembles_nothing` does not retract the
    discovery -- the discovery stands on remarkability and cohesion alone.
    """
    best_id = None
    best_anchor = None
    best_d = 1.0
    for anchor_id, anchor in library_shapes:
        record = getattr(anchor, "record", None) or {}
        lib_shape = tuple(record.get("action_sequence") or ())
        if not lib_shape:
            continue
        d = _shape_distance(shape, lib_shape)
        if d < best_d:
            best_d, best_id, best_anchor = d, anchor_id, anchor
    if best_id is None or best_d > similar_max:
        return Enrichment(None, None, None, "NONE", None)
    technique = None
    for mapping in (getattr(best_anchor, "record", None) or {}).get("attack_mappings") or []:
        if isinstance(mapping, dict) and mapping.get("technique_id"):
            technique = str(mapping["technique_id"])
            break
    return Enrichment(
        resembles_type=best_id,
        resembles_technique=technique,
        distance=round(best_d, 4),
        relation="EXACT" if best_d <= exact_max else "SIMILAR",
        malice=getattr(best_anchor, "malice", None),
    )
