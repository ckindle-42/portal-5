"""bully.universe -- schema-agnostic source universe.

The correction to the last generator's ceiling. `haystack.py` hardcoded six
sourcetypes with hand-written verb pools -- a prescriptive set, the exact
`_ENTITY_FIELDS` mistake one level up: it can only generate schemas its author
enumerated. A real analyst, hunting something that "doesn't look quite right,"
pivots across HUNDREDS of source types -- firewall, DNS, Windows, Linux,
container, web-server, cloud, proxy, EDR, IAM, VPN, database audit, mail
gateway, k8s, custom app logs -- each with a different shape and a different
LEVEL of information (some rich and structured, some a single free-text line).
The product is used universally; it cannot assume any fixed set.

So the universe is *procedurally generated*: source-type SHAPES are synthesized
with random-but-realistic structure -- varying field counts, nesting depth,
naming conventions (snake/camel/Pascal/dotted), which roles are even present
(some sources have no timestamp of their own; some no stable identity; some are
pure free text), and an information LEVEL from `sparse` (one opaque line) to
`rich` (deeply nested, many entities). None of these shapes is written down
anywhere; the field-role inference and the grader must cope with all of them
cold. That is the real test of "data agnostic."

Two capabilities, both schema-blind:

1. **Procedural background.** Invent K source-type shapes, then emit high-volume
   benign events conforming to them -- the natural, messy hay an analyst wades
   through. Realized as generic records (dicts of the shape's fields); NOT a
   fixed vocabulary.

2. **Behaviour-preserving implant.** Given a behavioural spine (a sequence of
   ATT&CK-style behaviour classes -- the invariant that survives everything),
   realize it as artifacts *conforming to a chosen generated shape*, using that
   shape's own field names and value conventions, with fresh identities. The
   cousin shares its parent's BEHAVIOUR and nothing else -- not the schema, not
   the field names, not the vocabulary. Recoverable only at the behavioural
   (L3) level, which is the whole product.

The behavioural class -> concrete-observable realization is deliberately
indirect: a class like `escalate` is realized as *whatever this generated
source would emit for an escalation* -- a numeric code, a syscall, a verb, a
URL path -- so the grader can never cheat by lexical matching. The generator
seals `true_behavior_class` per artifact (out of band) so discovery is
measurable against a source the grader has genuinely never seen.

Pure record synthesis (COLD). No I/O. Deterministic under a seed so a run is
reproducible and the offline fixture equals the live implant.
"""

from __future__ import annotations

import hashlib
import random
import string
from dataclasses import dataclass
from typing import Any

ALGORITHM_VERSION = "universe-v1"

# The behavioural alphabet -- the ONLY fixed vocabulary in this module, because
# behaviour is the invariant the product is built on. Everything else (field
# names, value shapes, which roles exist) is generated.
BEHAVIOR_CLASSES = (
    "auth",
    "enumerate",
    "execute",
    "escalate",
    "collect",
    "destroy",
    "persist",
    "evade",
    "lateral",
    "c2_exfil",
)

INFO_LEVELS = ("sparse", "medium", "rich")
NAMING = ("snake", "camel", "pascal", "dotted", "screaming")

TRANSFORMATIONS = ("REVOCABULARY", "REIDENTITY", "REORDER_MINOR", "RESCHEMA", "DOWNLEVEL")


def _rand_token(rng: random.Random, n: int = 6) -> str:
    return "".join(rng.choice(string.ascii_lowercase) for _ in range(n))


def _name(rng: random.Random, parts: list[str], convention: str) -> str:
    if convention == "snake":
        return "_".join(parts)
    if convention == "camel":
        return parts[0] + "".join(p.capitalize() for p in parts[1:])
    if convention == "pascal":
        return "".join(p.capitalize() for p in parts)
    if convention == "dotted":
        return ".".join(parts)
    if convention == "screaming":
        return "_".join(p.upper() for p in parts)
    return "_".join(parts)


@dataclass(frozen=True)
class SourceShape:
    """A procedurally-invented source type. None of this is written in code --
    it is generated, so the pipeline must handle shapes it was never told
    about."""

    source_id: str
    info_level: str
    naming: str
    identity_field: str | None  # some sources have no stable identity
    time_field: str | None  # some sources carry no own timestamp
    action_field: str  # every source expresses *some* action-ish field
    entity_fields: tuple[str, ...]  # extra pivotable fields (may be empty)
    noise_fields: tuple[str, ...]  # payload/free-text/opaque fields
    nesting: int  # 0 = flat, 1-2 = nested under a container
    container: str | None  # nesting wrapper key, if any
    # how this source realizes each behavioural class as a concrete value:
    behavior_realization: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "info_level": self.info_level,
            "naming": self.naming,
            "identity_field": self.identity_field,
            "time_field": self.time_field,
            "action_field": self.action_field,
            "entity_fields": list(self.entity_fields),
            "noise_fields": list(self.noise_fields),
            "nesting": self.nesting,
            "container": self.container,
        }


def _realize_behavior_value(rng: random.Random, cls: str, style: str) -> str:
    """How a source of a given STYLE expresses a behavioural class as a concrete
    observable. Styles mimic real families WITHOUT the module hardcoding any
    specific real schema: numeric-code sources (like Windows EIDs), verb
    sources (like cloud APIs), syscall sources (like auditd), path sources
    (like web logs), free-text sources (like syslog). The mapping is
    intentionally lossy and style-dependent so the grader cannot lexically
    recover the class -- only behaviourally."""
    if style == "numeric":
        base = {
            "auth": 46,
            "enumerate": 46,
            "execute": 46,
            "escalate": 46,
            "collect": 46,
            "destroy": 11,
            "persist": 45,
            "evade": 10,
            "lateral": 51,
            "c2_exfil": 51,
        }.get(cls, 40)
        return str(base * 100 + rng.randint(10, 99))
    if style == "syscall":
        pool = {
            "auth": ("CRED_ACQ",),
            "enumerate": ("openat", "getdents"),
            "execute": ("execve",),
            "escalate": ("setuid", "setgid"),
            "collect": ("read", "pread"),
            "destroy": ("unlink",),
            "persist": ("chmod", "symlink"),
            "evade": ("ptrace",),
            "lateral": ("connect",),
            "c2_exfil": ("sendto",),
        }.get(cls, ("ioctl",))
        return rng.choice(pool)
    if style == "path":
        pool = {
            "auth": ("/login", "/oauth/token"),
            "enumerate": ("/api/list", "/users"),
            "execute": ("/exec", "/run"),
            "escalate": ("/admin/grant",),
            "collect": ("/download", "/export"),
            "destroy": ("/delete",),
            "persist": ("/cron/add",),
            "evade": ("/logs/clear",),
            "lateral": ("/rpc",),
            "c2_exfil": ("/upload", "/beacon"),
        }.get(cls, ("/misc",))
        return rng.choice(pool)
    if style == "freetext":
        # a single opaque line -- the sparse, hard case
        return f"{_rand_token(rng)} {cls[:3]}{rng.randint(0, 9)} {_rand_token(rng, 8)}"
    # default: verb style (cloud-API-like), invented per-source so no two share vocab
    verb = _rand_token(rng, rng.randint(4, 9)).capitalize()
    return f"{verb}{cls.capitalize()}"


def invent_source_shape(rng: random.Random, index: int) -> SourceShape:
    """Synthesize one never-before-seen source type."""
    info = rng.choice(INFO_LEVELS)
    naming = rng.choice(NAMING)
    style = rng.choice(("numeric", "syscall", "path", "verb", "freetext"))
    sid = f"gen:{style}:{_rand_token(rng, 5)}-{index}"

    # info level governs how much structure exists
    n_entities = {"sparse": 0, "medium": rng.randint(1, 2), "rich": rng.randint(2, 4)}[info]
    n_noise = {"sparse": 1, "medium": rng.randint(1, 3), "rich": rng.randint(3, 6)}[info]

    has_identity = info != "sparse" or rng.random() < 0.4
    has_time = rng.random() < 0.85  # some sources genuinely lack their own time

    identity_field = (
        _name(rng, [rng.choice(["user", "actor", "principal", "src", "acct"]), "id"], naming)
        if has_identity
        else None
    )
    time_field = (
        _name(
            rng,
            [rng.choice(["event", "log", "record", ""]), rng.choice(["time", "ts", "stamp"])],
            naming,
        ).strip("._")
        if has_time
        else None
    )
    action_field = _name(
        rng,
        [
            rng.choice(["event", "action", "op", "activity", "msg", "req"]),
            rng.choice(["name", "type", "code", "kind", ""]),
        ],
        naming,
    ).strip("._")
    entity_fields = tuple(
        _name(
            rng,
            [
                rng.choice(["host", "dst", "device", "asset", "container", "pod"]),
                rng.choice(["name", "id", "ip"]),
            ],
            naming,
        )
        for _ in range(n_entities)
    )
    noise_fields = tuple(_name(rng, [_rand_token(rng, 4)], naming) for _ in range(n_noise))
    nesting = 0 if info == "sparse" else rng.choice([0, 0, 1, 1, 2])
    container = (
        _name(rng, [rng.choice(["data", "detail", "body", "fields"])], naming) if nesting else None
    )

    realization = {
        cls: tuple(_realize_behavior_value(rng, cls, style) for _ in range(rng.randint(1, 3)))
        for cls in BEHAVIOR_CLASSES
    }

    return SourceShape(
        source_id=sid,
        info_level=info,
        naming=naming,
        identity_field=identity_field,
        time_field=time_field,
        action_field=action_field,
        entity_fields=entity_fields,
        noise_fields=noise_fields,
        nesting=nesting,
        container=container,
        behavior_realization=realization,
    )


def _place(record: dict, shape: SourceShape, field_name: str, value: Any) -> None:
    if shape.nesting and shape.container and field_name != shape.time_field:
        record.setdefault(shape.container, {})[field_name] = value
    else:
        record[field_name] = value


def _emit_record(
    rng: random.Random, shape: SourceShape, action_value: str, identity: str, ts: float
) -> dict[str, Any]:
    rec: dict[str, Any] = {}
    if shape.time_field:
        rec[shape.time_field] = _iso(ts)
    _place(rec, shape, shape.action_field, action_value)
    if shape.identity_field:
        _place(rec, shape, shape.identity_field, identity)
    for ef in shape.entity_fields:
        _place(rec, shape, ef, f"{ef.split('.')[-1][:3]}-{rng.randint(0, 300)}")
    for nf in shape.noise_fields:
        _place(rec, shape, nf, _rand_token(rng, rng.randint(6, 20)))
    return rec


def _iso(ts: float) -> str:
    import datetime as _dt

    return _dt.datetime.fromtimestamp(ts, tz=_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fp(record: dict[str, Any]) -> str:
    import json

    return (
        "art-"
        + hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()[:16]
    )


@dataclass(frozen=True)
class UniverseLot:
    events: tuple[dict[str, Any], ...]  # {source_id, time, event, _labels}
    sealed_truth: tuple[dict[str, Any], ...]
    shapes: tuple[SourceShape, ...]
    benign_count: int
    implant_count: int

    def indexable(self) -> list[dict[str, Any]]:
        return [{k: v for k, v in e.items() if k != "_labels"} for e in self.events]


def _benign_behavior(rng: random.Random) -> str:
    # ordinary activity leans on the mundane classes
    return rng.choice(("auth", "enumerate", "execute", "collect", "auth", "enumerate"))


def build_universe(
    *,
    n_sources: int,
    background_n: int,
    cousins: list[dict[str, Any]],
    start_ts: float = 1_700_000_000.0,
    seed: int = 20260820,
) -> UniverseLot:
    """Invent `n_sources` never-seen source types, flood `background_n` benign
    events across them, and implant `cousins` -- each realized in a chosen (or
    random) generated shape by its behavioural spine. The grader sees only the
    raw records of shapes it was never told about."""
    rng = random.Random(seed)
    shapes = [invent_source_shape(rng, i) for i in range(n_sources)]
    events: list[dict[str, Any]] = []

    for i in range(background_n):
        shape = rng.choice(shapes)
        cls = _benign_behavior(rng)
        value = rng.choice(shape.behavior_realization[cls])
        identity = f"svc{rng.randint(0, 500)}"
        ts = start_ts + i * rng.uniform(0.05, 2.5)
        rec = _emit_record(rng, shape, value, identity, ts)
        events.append(
            {
                "source_id": shape.source_id,
                "time": ts,
                "event": rec,
                "_labels": {
                    "injected": False,
                    "malicious": False,
                    "family": None,
                    "technique": None,
                    "true_behavior_class": cls,
                    "source_id": shape.source_id,
                },
            }
        )

    sealed: list[dict[str, Any]] = []
    span = max(1.0, background_n * 1.2)
    for ci, spec in enumerate(cousins):
        # choose a target shape: named, or a random generated one (the realistic case)
        target = rng.choice(shapes)
        spine = list(spec["behavioural_spine"])
        if spec.get("transformation") == "REORDER_MINOR":
            spine = _interleave(spine, "enumerate")
        if spec.get("transformation") == "DOWNLEVEL":
            target = min(shapes, key=lambda s: {"sparse": 0, "medium": 1, "rich": 2}[s.info_level])
        identity = f"adv{rng.randint(1000, 9999)}"
        at = start_ts + rng.uniform(0, span)
        chain_id = spec.get("chain_id", f"cousin-{ci:03d}")
        fps: list[str] = []
        for step_idx, cls in enumerate(spine):
            value = rng.choice(target.behavior_realization.get(cls) or ("unknown",))
            ts = at + step_idx * rng.uniform(4.0, 45.0)
            rec = _emit_record(rng, target, value, identity, ts)
            fps.append(_fp(rec))
            events.append(
                {
                    "source_id": target.source_id,
                    "time": ts,
                    "event": rec,
                    "_labels": {
                        "injected": True,
                        "malicious": True,
                        "family": spec["parent_family"],
                        "technique": spec["parent_technique"],
                        "chain_id": chain_id,
                        "step_idx": step_idx,
                        "transformation": spec.get("transformation", "RESCHEMA"),
                        "true_behavior_class": cls,
                        "source_id": target.source_id,
                    },
                }
            )
        sealed.append(
            {
                "chain_id": chain_id,
                "family": spec["parent_family"],
                "technique": spec["parent_technique"],
                "behavioural_spine": list(spec["behavioural_spine"]),
                "transformation": spec.get("transformation", "RESCHEMA"),
                "realized_in_source": target.source_id,
                "realized_in_info_level": target.info_level,
                "artifact_fingerprints": fps,
                "n_steps": len(fps),
            }
        )

    events.sort(key=lambda e: e["time"])
    return UniverseLot(
        events=tuple(events),
        sealed_truth=tuple(sealed),
        shapes=tuple(shapes),
        benign_count=background_n,
        implant_count=sum(t["n_steps"] for t in sealed),
    )


def _interleave(spine: list[str], filler: str) -> list[str]:
    out: list[str] = []
    for i, c in enumerate(spine):
        out.append(c)
        if 0 < i < len(spine) - 1:
            out.append(filler)
    return out
