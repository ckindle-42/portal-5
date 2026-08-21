"""bully.behavior_inference -- behaviour classes INFERRED from the data.

`telemetry_behavior.py` maps named sourcetypes and event ids to a fixed
ten-class alphabet: `4624 -> auth`, `stream:dns -> enumerate`. On the
answer-keyed corpus that is a genuine win -- it is what makes the published
technique spines expressible and the floor measurable. But it is a curated
table, and a curated table is a definition matcher: the T.3 run left ~100
sourcetypes unreadable (`OktaIM2:log`, `ms:aad:signin`, `windows:powershell`,
`aws:cloudtrail`, every `gen:*`), and no amount of table-writing closes that,
because there is always another schema. **The table is a validation
instrument, not the product.**

Two prescriptive assumptions hide in it. The obvious one is the mapping. The
subtler one is the ALPHABET: ten class names chosen in advance. On universal
data there is no reason the right abstraction is those ten.

So this module applies the cousin principle one level down. Instead of asking
"does this action match a known behaviour label", it asks **"does this action
behave like that action"** -- and derives equivalence classes from the data,
the same way `field_roles` derives ENTITY/TIMESTAMP/ACTION from how values
behave rather than from their names.

Each distinct action value gets a behavioural profile built only from
observable structure:

  * `introduces_rate`  -- how often it is the FIRST thing seen for its entity.
                          Session-opening actions (a logon, an SSO grant, an
                          assume-role) introduce entities; later-stage actions
                          do not.
  * `fanout`           -- distinct entities touched per occurrence. Sweeping,
                          enumerative actions touch many; targeted ones few.
  * `position`         -- mean normalised position in an entity's timeline,
                          0.0 = first thing that entity did, 1.0 = last.
  * `terminal_rate`    -- how often it is the LAST thing seen for its entity.
  * `entity_breadth`   -- distinct entities over total occurrences: is this
                          action spread across the estate or concentrated.
  * `burstiness`       -- repeats-per-entity, separating steady background
                          from concentrated activity.

Actions with similar profiles are the same inferred behaviour whatever they
are called, so `4624`, `USER_AUTH` and `user.session.start` land together
without anyone writing them down -- and so does the equivalent verb in a
source nobody has ever seen.

Inferred classes are **unnamed** (`ib-0`, `ib-1`, ...). Naming them is
ENRICHMENT: a run with an answer key can label a cluster by the curated class
its members map to, which is a measurement convenience and never an input to
discovery. A run without an answer key is fully functional and simply has
unnamed classes -- which is the universal case.

Pure compute over injected records (COLD). No I/O, no model, no catalogue.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ALGORITHM_VERSION = "behavior-inference-v1"

# An action seen fewer times than this has no stable profile; it is carried as
# unclassified rather than assigned on noise.
MIN_OCCURRENCES = 5

# Profile distance below which two actions are the same inferred behaviour.
# Judgement, recorded on every run; a change is a re-baseline.
SAME_BEHAVIOR_DISTANCE = 0.22

# Feature weights. `introduces_rate` and `position` carry the most signal for
# separating session-opening from late-stage activity.
_WEIGHTS: dict[str, float] = {
    "introduces_rate": 1.0,
    "position": 1.0,
    "terminal_rate": 0.7,
    "fanout": 0.6,
    "entity_breadth": 0.5,
    "burstiness": 0.4,
}


@dataclass(frozen=True)
class ActionProfile:
    action: str
    sourcetype: str
    occurrences: int
    introduces_rate: float
    fanout: float
    position: float
    terminal_rate: float
    entity_breadth: float
    burstiness: float

    def vector(self) -> dict[str, float]:
        return {
            "introduces_rate": self.introduces_rate,
            "position": self.position,
            "terminal_rate": self.terminal_rate,
            "fanout": self.fanout,
            "entity_breadth": self.entity_breadth,
            "burstiness": self.burstiness,
        }

    def to_dict(self) -> dict[str, Any]:
        d = {"action": self.action, "sourcetype": self.sourcetype, "occurrences": self.occurrences}
        d.update({k: round(v, 4) for k, v in self.vector().items()})
        return d


def _norm(values: list[float]) -> Callable[[float], float]:
    lo, hi = (min(values), max(values)) if values else (0.0, 1.0)
    span = hi - lo
    if span <= 0:
        return lambda v: 0.0
    return lambda v: (v - lo) / span


def profile_actions(  # noqa: PLR0912
    records: list[dict[str, Any]],
    *,
    action_of: Callable[[dict[str, Any]], str | None],
    entity_of: Callable[[dict[str, Any]], list[str]],
    time_of: Callable[[dict[str, Any]], float | None],
    sourcetype_of: Callable[[dict[str, Any]], str],
    min_occurrences: int = MIN_OCCURRENCES,
) -> list[ActionProfile]:
    """Build a behavioural profile per distinct action value, from structure
    only -- never from the action's text."""
    # order each entity's activity in time
    per_entity: dict[str, list[tuple[float, str]]] = defaultdict(list)
    rows: list[tuple[str, str, float, list[str]]] = []
    for rec in records:
        action = action_of(rec)
        ts = time_of(rec)
        if not action or ts is None:
            continue
        ents = [e for e in entity_of(rec) if e]
        rows.append((action, sourcetype_of(rec), ts, ents))
        for e in ents:
            per_entity[e].append((ts, action))
    for e in per_entity:
        per_entity[e].sort()

    first_action: dict[str, str] = {e: v[0][1] for e, v in per_entity.items() if v}
    last_action: dict[str, str] = {e: v[-1][1] for e, v in per_entity.items() if v}
    index_of: dict[str, dict[str, int]] = {}
    for e, seq in per_entity.items():
        index_of[e] = {}
        for i, (_ts, act) in enumerate(seq):
            index_of[e].setdefault(act, i)

    agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "st": Counter(), "intro": 0, "term": 0, "ents": set(), "fan": 0, "pos": []}
    )
    for action, st, _ts, ents in rows:
        a = agg[action]
        a["n"] += 1
        a["st"][st] += 1
        a["fan"] += len(ents)
        a["ents"].update(ents)
        for e in ents:
            seq = per_entity.get(e) or []
            if first_action.get(e) == action:
                a["intro"] += 1
            if last_action.get(e) == action:
                a["term"] += 1
            if len(seq) > 1:
                i = index_of[e].get(action, 0)
                a["pos"].append(i / (len(seq) - 1))

    out: list[ActionProfile] = []
    for action, a in agg.items():
        n = a["n"]
        if n < min_occurrences:
            continue
        n_ents = max(1, len(a["ents"]))
        out.append(
            ActionProfile(
                action=action,
                sourcetype=a["st"].most_common(1)[0][0] if a["st"] else "",
                occurrences=n,
                introduces_rate=a["intro"] / n,
                fanout=a["fan"] / n,
                position=(sum(a["pos"]) / len(a["pos"])) if a["pos"] else 0.0,
                terminal_rate=a["term"] / n,
                entity_breadth=n_ents / n,
                burstiness=n / n_ents,
            )
        )
    return out


@dataclass(frozen=True)
class InferredBehavior:
    """An equivalence class of actions that BEHAVE alike. Unnamed by design --
    a name is enrichment, supplied only where an answer key exists."""

    class_id: str
    members: tuple[str, ...]
    sourcetypes: tuple[str, ...]
    occurrences: int
    centroid: dict[str, float]
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_id": self.class_id,
            "name": self.name,
            "members": list(self.members),
            "sourcetypes": list(self.sourcetypes),
            "occurrences": self.occurrences,
            "centroid": {k: round(v, 4) for k, v in self.centroid.items()},
            "n_sourcetypes": len(self.sourcetypes),
        }

    @property
    def is_cross_schema(self) -> bool:
        return len(self.sourcetypes) >= 2


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    num = 0.0
    den = 0.0
    for k, w in _WEIGHTS.items():
        num += w * (a.get(k, 0.0) - b.get(k, 0.0)) ** 2
        den += w
    return math.sqrt(num / den) if den else 1.0


def infer_behaviors(
    profiles: list[ActionProfile],
    *,
    max_distance: float = SAME_BEHAVIOR_DISTANCE,
) -> list[InferredBehavior]:
    """Cluster actions into inferred behaviour classes by profile similarity.

    This is the cousin principle one level down: two actions are the same
    behaviour when they behave the same way, not when a table says so. The
    result works on a source nobody enumerated, which a mapping cannot.
    """
    if not profiles:
        return []
    # normalise the unbounded features so no single scale dominates
    scaled: list[dict[str, float]] = []
    raw = [p.vector() for p in profiles]
    norms = {k: _norm([v[k] for v in raw]) for k in ("fanout", "entity_breadth", "burstiness")}
    for v in raw:
        s = dict(v)
        for k, fn in norms.items():
            s[k] = fn(v[k])
        scaled.append(s)

    n = len(profiles)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if _distance(scaled[i], scaled[j]) <= max_distance:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    out: list[InferredBehavior] = []
    for cid, (_root, idxs) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1]))):
        members = [profiles[i] for i in idxs]
        centroid = {k: sum(scaled[i][k] for i in idxs) / len(idxs) for k in _WEIGHTS}
        out.append(
            InferredBehavior(
                class_id=f"ib-{cid}",
                members=tuple(sorted(m.action for m in members)),
                sourcetypes=tuple(sorted({m.sourcetype for m in members})),
                occurrences=sum(m.occurrences for m in members),
                centroid=centroid,
            )
        )
    return out


def name_from_answer_key(
    behaviors: list[InferredBehavior],
    curated: Callable[[str], str],
) -> list[InferredBehavior]:
    """ENRICHMENT ONLY. Label an inferred class by the curated class its
    members map to, where a curated mapping exists. Used for reporting and
    for measuring against an answer key; **never an input to discovery**, and
    a run without it is fully functional with unnamed classes."""
    import dataclasses

    out: list[InferredBehavior] = []
    for b in behaviors:
        votes = Counter(c for c in (curated(m) for m in b.members) if c)
        out.append(dataclasses.replace(b, name=votes.most_common(1)[0][0] if votes else None))
    return out


def inference_report(
    profiles: list[ActionProfile], behaviors: list[InferredBehavior]
) -> dict[str, Any]:
    """Universality is measured by what the inference covers WITHOUT a table:
    how many actions were profiled, how many classes emerged, and -- the
    number that matters -- how many classes span more than one schema."""
    cross = [b for b in behaviors if b.is_cross_schema]
    schemas = {p.sourcetype for p in profiles}
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "actions_profiled": len(profiles),
        "schemas_seen": len(schemas),
        "classes_inferred": len(behaviors),
        "cross_schema_classes": len(cross),
        "cross_schema_fraction": (round(len(cross) / len(behaviors), 4) if behaviors else None),
        "largest_class_members": max((len(b.members) for b in behaviors), default=0),
    }
