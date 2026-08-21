"""bully.pyramid -- the abstraction level of an observable / a match.

The axis every grader in this module has been missing. Bianco's Pyramid of
Pain, formalized by MITRE's Summiting the Pyramid, orders detection
observables by how costly they are for an adversary to change:

    L1_EPHEMERAL   hash, IP, domain, request-id, a specific ARN, a source
                   port -- a single byte defeats a detection built on these.
    L2_TOOL        the tool/implementation used: a binary name, a specific
                   command string, an EventID tied to one utility. Evadable
                   by bringing a different tool.
    L3_BEHAVIOR    the invariant behavioural choke point -- the action
                   *class* sequence (auth -> enumerate -> escalate) that any
                   implementation of the technique must exhibit. Unavoidable
                   without a substantially different technique. The top of
                   the pyramid, and the only level a cousin survives a
                   change of tooling at.

Why this module exists: every prior grader scored similarity on strings
drawn from the payload -- verb names, field values, sourcetypes -- which are
L1/L2. That is why cross-vocabulary recovery kept needing rescue: two
implementations of one technique share *no* payload tokens, precisely
because payload tokens are the evadable layer. A cousin that only matches at
L1/L2 is a fragile cousin and must be devalued *as such*; a cousin that
matches at L3 is the product. The system could not tell them apart because
it had no level to express the difference. This module supplies it.

A feature's level is a property of the feature, not of a name list. It is
inferred from the feature's kind (produced by field-role inference) and its
value shape. `match_level` then reports the *highest* pyramid level at which
two signatures actually agree -- the honest robustness of the relation.

Pure compute. No I/O, no model calls (COLD). The L2->L3 abstraction (a raw
verb to its behavioural class) is the one learned-classifier seam, isolated
behind `classify_behavior`; the deterministic default is a transparent table
whose failures are visible, never hidden.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ALGORITHM_VERSION = "pyramid-v1"

L1_EPHEMERAL = "L1_EPHEMERAL"
L2_TOOL = "L2_TOOL"
L3_BEHAVIOR = "L3_BEHAVIOR"

LEVELS: tuple[str, ...] = (L1_EPHEMERAL, L2_TOOL, L3_BEHAVIOR)
_LEVEL_RANK = {L1_EPHEMERAL: 1, L2_TOOL: 2, L3_BEHAVIOR: 3}


# Robustness of a match is the rank of the highest level it holds at,
# normalized. A match that only holds at ephemeral values is near-worthless
# against an adapting adversary; one that holds at the behavioural choke
# point is maximally robust.
def robustness(level: str) -> float:
    return _LEVEL_RANK.get(level, 0) / _LEVEL_RANK[L3_BEHAVIOR]


# The one learned seam: a raw action verb -> a behavioural class. The
# deterministic table is transparent and its misses are reported, never
# silently absorbed (that was the RC1/`other`-collapse failure). A learned
# ActionClassifier is a drop-in that this signature accepts.
BehaviorClassifier = Callable[[str], str]

_BEHAVIOR_TABLE: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "auth",
            "assumerole",
            "getsessiontoken",
            "logon",
            "authenticate",
            "login",
            "kerberos",
            "asrep",
            "tgt",
        ),
        "auth",
    ),
    (
        (
            "list",
            "describe",
            "get",
            "enumerate",
            "whoami",
            "net user",
            "query",
            "find",
            "search",
            "smb",
            "ldap",
            "bloodhound",
        ),
        "enumerate",
    ),
    (
        (
            "create",
            "put",
            "run",
            "start",
            "invoke",
            "exec",
            "spawn",
            "psexec",
            "wmiexec",
            "command",
        ),
        "execute",
    ),
    (("destroy", "delete", "remove", "stop", "terminate", "disable", "clear", "wipe"), "destroy"),
    (
        (
            "escalate",
            "attach",
            "grant",
            "addrole",
            "putpolicy",
            "adduser",
            "addmember",
            "setowner",
            "dcsync",
            "secretsdump",
        ),
        "escalate",
    ),
    (
        ("copy", "download", "getobject", "export", "sync", "collect", "archive", "compress"),
        "collect",
    ),
    (("connect", "beacon", "post", "dns", "exfil", "upload"), "c2_exfil"),
)


def default_behavior_classifier(verb: str) -> str:
    """Deterministic verb -> behavioural class. Returns '' (not 'other') on a
    miss, so callers can *count* the miss as unclassified rather than treat
    it as a shared class -- the exact bug that let extraction failure become
    a false match."""
    if not verb:
        return ""
    low = verb.lower()
    for needles, label in _BEHAVIOR_TABLE:
        if any(n in low for n in needles):
            return label
    return ""


def classify_behavior(verb: str, classifier: BehaviorClassifier | None = None) -> str:
    return (classifier or default_behavior_classifier)(verb)


# ── feature-level inference ────────────────────────────────────────────────

# Field roles (from field_roles.py) map onto pyramid levels by their evasion
# cost. An ENTITY *value* (a specific IP/ARN/host) is ephemeral. An ACTION
# verb is a tool-level artifact until it is abstracted to a behavioural
# class, at which point it is L3.
_ROLE_BASE_LEVEL = {
    "ENTITY": L1_EPHEMERAL,  # a specific principal/host/key value
    "TIMESTAMP": L1_EPHEMERAL,  # ephemeral by definition
    "ACTION": L2_TOOL,  # a raw verb is tool-level until abstracted
    "PAYLOAD": L1_EPHEMERAL,  # hashes, blobs, free text
    "CONSTANT": L1_EPHEMERAL,
}


@dataclass(frozen=True)
class LeveledFeature:
    token: str
    role: str
    level: str
    behavior_class: str  # populated only when the feature abstracts to L3


def level_feature(
    token: str,
    role: str,
    *,
    raw_verb: str | None = None,
    classifier: BehaviorClassifier | None = None,
) -> LeveledFeature:
    """Assign a pyramid level to one feature. An ACTION verb that abstracts
    to a known behavioural class is promoted to L3_BEHAVIOR carrying that
    class; an ACTION whose verb does not classify stays L2_TOOL (honest: we
    saw a tool artifact but could not lift it to behaviour)."""
    base = _ROLE_BASE_LEVEL.get(role, L1_EPHEMERAL)
    behavior_class = ""
    level = base
    if role == "ACTION":
        behavior_class = classify_behavior(raw_verb if raw_verb is not None else token, classifier)
        level = L3_BEHAVIOR if behavior_class else L2_TOOL
    return LeveledFeature(token=token, role=role, level=level, behavior_class=behavior_class)


@dataclass(frozen=True)
class MatchLevel:
    """The honest robustness of a relation: the highest pyramid level at
    which the two signatures actually agree, with the evidence at each level
    itemised so a fragile (L1-only) match is self-evidently fragile."""

    level: str  # highest level with a real agreement
    robustness: float
    behavior_overlap: tuple[str, ...]  # shared L3 behavioural classes
    tool_overlap: tuple[str, ...]  # shared L2 tool artifacts
    ephemeral_overlap: tuple[str, ...]  # shared L1 values
    holds_at_behavior: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "robustness": round(self.robustness, 4),
            "behavior_overlap": list(self.behavior_overlap),
            "tool_overlap": list(self.tool_overlap),
            "ephemeral_overlap": list(self.ephemeral_overlap),
            "holds_at_behavior": self.holds_at_behavior,
        }


def match_level(
    subject_features: list[LeveledFeature],
    anchor_features: list[LeveledFeature],
) -> MatchLevel:
    """Report the highest pyramid level at which subject and anchor agree.

    Behavioural agreement is on the *class sequence* (order-sensitive at the
    class level), because a technique's choke point is the ordered sequence
    of behavioural classes, not a bag. Tool and ephemeral agreement are set
    overlaps. A relation that shares behaviour but no literal tokens -- the
    cross-vocabulary cousin -- correctly reports L3_BEHAVIOR here even though
    its L1/L2 overlaps are empty. That is the whole point.
    """

    def classes(feats: list[LeveledFeature]) -> tuple[str, ...]:
        return tuple(f.behavior_class for f in feats if f.level == L3_BEHAVIOR and f.behavior_class)

    def tools(feats: list[LeveledFeature]) -> set[str]:
        return {f.token for f in feats if f.level == L2_TOOL}

    def ephem(feats: list[LeveledFeature]) -> set[str]:
        return {f.token for f in feats if f.level == L1_EPHEMERAL}

    s_classes, a_classes = classes(subject_features), classes(anchor_features)
    behavior_overlap = _ordered_common_subsequence(s_classes, a_classes)
    tool_overlap = tools(subject_features) & tools(anchor_features)
    ephemeral_overlap = ephem(subject_features) & ephem(anchor_features)

    if behavior_overlap:
        level = L3_BEHAVIOR
    elif tool_overlap:
        level = L2_TOOL
    elif ephemeral_overlap:
        level = L1_EPHEMERAL
    else:
        level = ""  # no agreement at any level

    return MatchLevel(
        level=level,
        robustness=robustness(level) if level else 0.0,
        behavior_overlap=behavior_overlap,
        tool_overlap=tuple(sorted(tool_overlap)),
        ephemeral_overlap=tuple(sorted(ephemeral_overlap)),
        holds_at_behavior=bool(behavior_overlap),
    )


def _ordered_common_subsequence(a: tuple[str, ...], b: tuple[str, ...]) -> tuple[str, ...]:
    """Longest common subsequence of two class sequences -- the shared
    behavioural spine, order preserved. A shared spine of >=2 classes is a
    genuine behavioural choke point; a single shared class is weak and the
    caller can treat it as such via length."""
    if not a or not b:
        return ()
    m, n = len(a), len(b)
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
