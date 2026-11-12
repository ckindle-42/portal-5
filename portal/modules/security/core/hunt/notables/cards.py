"""Source cards: what a source is and which of its fields play which role, model-assisted."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..judge import JudgeClient
from .parse import FieldStat, Parsed, field_stats, parse_events
from .sample import SourceFacts

KINDS = ("activity", "alert", "measurement", "other")
ROLES = ("actor", "action", "object", "from", "to", "outcome")
MAX_ANSWER_TOKENS = 300  # effort budget: one compact JSON answer per source
MAX_ANSWER_CHARS = 4000  # effort budget: characters read from one model answer
MAX_BASIS_CHARS = 240  # effort budget: the model's own reason kept on the card
CARD_SEED = 0

CARD_QUESTION = """You are given the fields that one kind of machine-written log event carries: how often
each field appears in a sample, how many distinct values it holds, and a few example values. Decide
what kind of source produced these events and which fields play which role.

Answer with one JSON object and nothing else, in this shape:
{"kind": "activity" | "alert" | "measurement" | "other",
 "actor": ["field"], "action": ["field"], "object": ["field"],
 "from": ["field"], "to": ["field"], "outcome": ["field"],
 "basis": "one short sentence"}

Kinds:
- activity: each event records something an actor did.
- alert: each event is a detection or alarm already raised by another system.
- measurement: each event is a periodic numeric sample of a resource.
- other: none of the above.

Roles: actor is who acted; action is what was done; object is what it was done to; from and to
are where it came from and where it went; outcome is what resulted. Use only the field names
listed below, and use [] when a role has no field.

FIELDS:"""

_JSON = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class ModelAnswer:
    text: str
    seconds: float
    served_model: str
    prompt_tokens: int | None
    error: str | None


@dataclass(frozen=True)
class Answer:
    kind: str
    roles: Mapping[str, tuple[str, ...]]
    rejected: tuple[str, ...]
    basis: str
    error: str | None


@dataclass(frozen=True)
class SourceCard:
    """One source, understood or visibly not: kind, roles, the evidence they rest on."""

    index: str
    sourcetype: str
    kind: str
    roles: Mapping[str, tuple[str, ...]]
    understood: bool
    reason: str | None
    fmt: str
    coverage: float
    fields: tuple[FieldStat, ...]
    sample: Mapping[str, Any]
    facts: Mapping[str, Any]
    model: Mapping[str, Any]
    cache_key: str
    basis: str = ""
    rejected: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()

    @property
    def source_id(self) -> str:
        return f"{self.index}:{self.sourcetype}"

    def role_fields(self, role: str) -> tuple[str, ...]:
        return tuple(self.roles.get(role, ()))

    @property
    def usable(self) -> bool:
        """An activity source with an actor or action role can carry behaviours."""
        return self.understood and self.kind == "activity" and bool(self.roles)

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "sourcetype": self.sourcetype,
            "source_id": self.source_id,
            "kind": self.kind,
            "understood": self.understood,
            "reason": self.reason,
            "roles": {role: list(fields) for role, fields in sorted(self.roles.items())},
            "rejected_fields": list(self.rejected),
            "basis": self.basis,
            "structure": self.fmt,
            "parse_coverage": round(self.coverage, 3),
            "columns": list(self.columns),
            "fields": [
                {
                    "name": stat.name,
                    "present": stat.present,
                    "distinct": stat.distinct,
                    "examples": list(stat.examples),
                }
                for stat in self.fields
            ],
            "sample": dict(self.sample),
            "facts": dict(self.facts),
            "model": dict(self.model),
            "cache_key": self.cache_key,
        }


class CardCache:
    """One JSON file per content key; a rerun with the same description asks nothing."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> ModelAnswer | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            stored = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        if not isinstance(stored, dict) or not isinstance(stored.get("text"), str):
            return None
        return ModelAnswer(
            str(stored["text"]),
            float(stored.get("seconds") or 0.0),
            str(stored.get("served_model") or ""),
            None,
            None,
        )

    def put(self, key: str, answer: ModelAnswer) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "text": answer.text,
            "seconds": answer.seconds,
            "served_model": answer.served_model,
            "prompt_tokens": answer.prompt_tokens,
        }
        self._path(key).write_text(json.dumps(payload, sort_keys=True))


def _prompt_tokens(response: Mapping[str, Any]) -> int | None:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return None
    value = usage.get("prompt_tokens", usage.get("input_tokens"))
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _content(response: Mapping[str, Any]) -> str:
    from .pipeline import content_of

    return content_of(response)


def ask_model(client: JudgeClient, model: str, prompt: str) -> ModelAnswer:
    """One bounded request; a transport failure is recorded, never replaced by a default."""
    began = time.monotonic()
    try:
        response = client.complete(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            seed=CARD_SEED,
            max_tokens=MAX_ANSWER_TOKENS,
            reasoning_effort="none",
            stream=False,
        )
    except Exception:  # noqa: BLE001 -- per-source unclassified coverage
        return ModelAnswer("", round(time.monotonic() - began, 3), "", None, "request_failed")
    seconds = round(time.monotonic() - began, 3)
    if not isinstance(response, Mapping):
        return ModelAnswer("", seconds, "", None, "invalid_response")
    return ModelAnswer(
        _content(response)[:MAX_ANSWER_CHARS],
        seconds,
        str(response.get("model") or ""),
        _prompt_tokens(response),
        None,
    )


def describe_fields(stats: Sequence[FieldStat], lines: int) -> str:
    if not stats:
        return "(no field could be read from the sample)"
    rows = [
        f"- {stat.name} present={stat.present}/{lines} distinct={stat.distinct} "
        f"examples: " + " | ".join(f'"{value}"' for value in stat.examples)
        for stat in stats
    ]
    return "\n".join(rows)


def build_prompt(stats: Sequence[FieldStat], lines: int) -> str:
    return f"{CARD_QUESTION}\n{describe_fields(stats, lines)}"


def _field_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, (str, int))]
    return []


def apply_answer(text: str, names: Iterable[str]) -> Answer:
    """Validate the model's answer against the fields that actually exist in the sample."""
    match = _JSON.search(text or "")
    if match is None:
        return Answer("other", {}, (), "", "unparseable_answer")
    try:
        answer = json.loads(match.group(0))
    except ValueError:
        return Answer("other", {}, (), "", "unparseable_answer")
    if not isinstance(answer, Mapping):
        return Answer("other", {}, (), "", "unparseable_answer")
    kind = str(answer.get("kind") or "").strip().lower()
    if kind not in KINDS:
        return Answer("other", {}, (), "", "invalid_kind")
    known = set(names)
    roles: dict[str, tuple[str, ...]] = {}
    rejected: list[str] = []
    for role in ROLES:
        found: list[str] = []
        for name in _field_list(answer.get(role)):
            if name in known:
                if name not in found:
                    found.append(name)
            elif name not in rejected:
                rejected.append(name)
        if found:
            roles[role] = tuple(found)
    basis = str(answer.get("basis") or "")[:MAX_BASIS_CHARS]
    return Answer(kind, roles, tuple(sorted(rejected)), basis, None)


def _structure(parsed: Sequence[Parsed]) -> tuple[str, int]:
    formats = Counter(item.fmt for item in parsed if item.fields)
    if not formats:
        return "text", 0
    return sorted(formats.items(), key=lambda item: (-item[1], item[0]))[0][0], sum(
        formats.values()
    )


def _columns(parsed: Sequence[Parsed], fmt: str) -> tuple[str, ...]:
    """Column names a delimited sample established, so later events read with the same names."""
    if fmt != "delimited":
        return ()
    for item in parsed:
        if item.fmt == "delimited" and item.fields:
            return tuple(item.fields)
    return ()


def _sample_facts(rows: Sequence[Mapping[str, Any]], parsed: Sequence[Parsed]) -> dict[str, Any]:
    hits = sum(1 for item in parsed if item.fields)
    hosts = sorted({str(row.get("host") or "") for row in rows} - {""})
    search_types = sorted({str(row.get("sourcetype") or "") for row in rows} - {""})
    return {
        "lines": len(parsed),
        "parsed": hits,
        "search_sourcetypes": search_types[:12],
        "hosts": hosts[:12],
    }


def _failure(
    facts: SourceFacts,
    *,
    reason: str,
    fmt: str,
    coverage: float,
    stats: Sequence[FieldStat],
    sample: Mapping[str, Any],
    model: Mapping[str, Any],
    cache_key: str,
) -> SourceCard:
    return SourceCard(
        index=facts.index,
        sourcetype=facts.sourcetype,
        kind="other",
        roles={},
        understood=False,
        reason=reason,
        fmt=fmt,
        coverage=coverage,
        fields=tuple(stats),
        sample=sample,
        facts=_facts(facts),
        model=model,
        cache_key=cache_key,
    )


def _facts(facts: SourceFacts) -> dict[str, Any]:
    return {
        "events": facts.events,
        "first": facts.first,
        "last": facts.last,
        "host_count": facts.host_count,
        "source_count": facts.source_count,
        "hosts": list(facts.hosts),
        "sources": list(facts.sources[:12]),
    }


def build_card(
    facts: SourceFacts,
    rows: Sequence[Mapping[str, Any]],
    *,
    windows: int,
    client: JudgeClient,
    model: str,
    cache: CardCache,
) -> SourceCard:
    """One card per source: parse the sample, ask once, validate, and keep the evidence."""
    parsed = parse_events([str(row.get("_raw") or "") for row in rows])
    stats = field_stats(parsed)
    fmt, hits = _structure(parsed)
    coverage = hits / len(parsed) if parsed else 0.0
    sample = _sample_facts(rows, parsed)
    sample["windows"] = windows
    prompt = build_prompt(stats, len(parsed))
    cache_key = hashlib.sha256(f"{model}\n{prompt}".encode()).hexdigest()
    if not parsed:
        return _failure(
            facts,
            reason="no_sample",
            fmt="text",
            coverage=0.0,
            stats=stats,
            sample=sample,
            model={"requests": 0, "cached": False},
            cache_key=cache_key,
        )
    if not hits:
        return _failure(
            facts,
            reason="unparsed_sample",
            fmt="text",
            coverage=0.0,
            stats=stats,
            sample=sample,
            model={"requests": 0, "cached": False},
            cache_key=cache_key,
        )
    cached = cache.get(cache_key)
    if cached is not None:
        answer = cached
        requests = 0
    else:
        answer = ask_model(client, model, prompt)
        if answer.error is None:
            cache.put(cache_key, answer)
        requests = 1
    applied = apply_answer(answer.text, [stat.name for stat in stats])
    model_facts = {
        "requests": requests,
        "seconds": answer.seconds,
        "served_model": answer.served_model,
        "prompt_tokens": answer.prompt_tokens,
        "cached": cached is not None,
        "error": answer.error or applied.error,
        "prompt_chars": len(prompt),
        "prompt": prompt,
    }
    if answer.error is not None:
        return _failure(
            facts,
            reason=f"model_{answer.error}",
            fmt=fmt,
            coverage=coverage,
            stats=stats,
            sample=sample,
            model=model_facts,
            cache_key=cache_key,
        )
    if applied.error is not None:
        return _failure(
            facts,
            reason=applied.error,
            fmt=fmt,
            coverage=coverage,
            stats=stats,
            sample=sample,
            model=model_facts,
            cache_key=cache_key,
        )
    return SourceCard(
        index=facts.index,
        sourcetype=facts.sourcetype,
        kind=applied.kind,
        roles=applied.roles,
        understood=True,
        reason=None,
        fmt=fmt,
        coverage=coverage,
        fields=tuple(stats),
        sample=sample,
        facts=_facts(facts),
        model=model_facts,
        cache_key=cache_key,
        basis=applied.basis,
        rejected=applied.rejected,
        columns=_columns(parsed, fmt),
    )
