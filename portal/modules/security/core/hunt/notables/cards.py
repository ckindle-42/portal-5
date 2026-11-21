"""Source cards: what a source is and which of its fields play which role, model-assisted."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from ..judge import (
    BackpressureClient,
    JudgeClient,
    ThrottleBudgetExceededError,
)
from .parse import (
    FieldStat,
    Parsed,
    TemplateModel,
    choose_partition,
    field_stats,
    parse_sample,
    partition_groups,
)
from .sample import SourceFacts

KINDS = ("activity", "alert", "measurement", "other")
ROLES = ("actor", "action", "object", "from", "to", "outcome")
ALERT_EVENT_TYPE = "alert"  # the event_type value that marks a Suricata/Zeek detection event
FAST_ALERT = re.compile(r"^\d{2}/\d{2}/\d{4}-\d{2}:\d{2}:\d{2}\.\d+\s+\[\*\*\] \[\d+:\d+:\d+\] ")
CARD_KIND_CONSUMERS = {
    "activity": frozenset({"behaviours", "peer_rare", "similar_to_known", "manifest"}),
    "alert": frozenset({"alerts"}),
    "measurement": frozenset(),
    "other": frozenset(),
}
ROLE_CONSUMERS = frozenset({"behaviours", "peer_rare", "similar_to_known", "manifest"})
MAX_ANSWER_TOKENS = 300  # effort budget: one compact JSON answer per source
MAX_ANSWER_CHARS = 4000  # effort budget: characters read from one model answer
MAX_BASIS_CHARS = 240  # effort budget: the model's own reason kept on the card
CARD_SEED = 0
NUMERIC_SHARE_FOR_MEASUREMENT = 0.5  # a measurement stream is mostly numeric samples
CARD_CONCURRENCY = 2  # effort budget: the seat serves one request at a time
CARDS_REQUEST_BUDGET = 120  # effort budget: cards' share of ~200 model requests per hunt

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
    completion_tokens: int | None = None
    finish_reason: str = ""


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
    part_field: str = ""
    part_value: str = ""
    kind_said: str = ""
    kind_note: str | None = None
    kind_facts: Mapping[str, Any] = field(default_factory=dict)
    template_model: TemplateModel | None = None

    @property
    def source_id(self) -> str:
        return f"{self.index}:{self.sourcetype}"

    @property
    def card_id(self) -> str:
        if not self.part_field:
            return self.source_id
        return f"{self.source_id}#{self.part_field}={self.part_value}"

    def role_fields(self, role: str) -> tuple[str, ...]:
        return tuple(self.roles.get(role, ()))

    def in_part(self, fields: Mapping[str, str]) -> bool:
        """True when an event's parsed fields select this card's part."""
        if not self.part_field:
            return True
        return (fields.get(self.part_field) or "").strip() == self.part_value

    @property
    def usable(self) -> bool:
        """An activity source with an actor or action role can carry behaviours."""
        return "behaviours" in card_consumers(self)

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "sourcetype": self.sourcetype,
            "source_id": self.source_id,
            "card_id": self.card_id,
            "part": (
                {"field": self.part_field, "value": self.part_value} if self.part_field else None
            ),
            "kind": self.kind,
            "kind_said": self.kind_said or self.kind,
            "kind_note": self.kind_note,
            "kind_facts": dict(self.kind_facts),
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
                    "variety": stat.variety,
                    "examples": list(stat.examples),
                }
                for stat in self.fields
            ],
            "sample": dict(self.sample),
            "facts": dict(self.facts),
            "model": dict(self.model),
            "cache_key": self.cache_key,
            "template": self.template_model.to_dict() if self.template_model else None,
        }


def card_consumers(card: SourceCard) -> frozenset[str]:
    """The downstream consumers permitted by one understood card kind and its roles."""
    if not card.understood:
        return frozenset()
    consumers = CARD_KIND_CONSUMERS.get(card.kind, frozenset())
    return consumers if card.roles else consumers - ROLE_CONSUMERS


def is_alert_line(raw: str) -> bool:
    """True when one raw line is a detection: a JSON alert event or a Suricata fast-log line."""
    if FAST_ALERT.match(raw):
        return True
    if not raw.lstrip().startswith("{"):
        return False
    try:
        parsed = json.loads(raw)
    except ValueError:
        return False
    return isinstance(parsed, Mapping) and str(parsed.get("event_type") or "") == ALERT_EVENT_TYPE


def is_alert_event(row: Mapping[str, Any]) -> bool:
    """True when one raw event is a detection."""
    return is_alert_line(str(row.get("_raw") or ""))


def count_alert_lines(rows: Sequence[Mapping[str, Any]]) -> int:
    """How many of a sample's events are detections, recognised by shape only."""
    return sum(1 for row in rows if is_alert_event(row))


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
            _optional_int(stored.get("completion_tokens")),
            str(stored.get("finish_reason") or ""),
        )

    def put(self, key: str, answer: ModelAnswer) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "text": answer.text,
            "seconds": answer.seconds,
            "served_model": answer.served_model,
            "prompt_tokens": answer.prompt_tokens,
            "completion_tokens": answer.completion_tokens,
            "finish_reason": answer.finish_reason,
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


def _optional_int(value: Any) -> int | None:
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
    except ThrottleBudgetExceededError:
        return ModelAnswer("", round(time.monotonic() - began, 3), "", None, "throttled")
    except httpx.HTTPStatusError:
        return ModelAnswer("", round(time.monotonic() - began, 3), "", None, "http_error")
    except Exception:  # noqa: BLE001 -- per-source unclassified coverage
        return ModelAnswer("", round(time.monotonic() - began, 3), "", None, "request_failed")
    seconds = round(time.monotonic() - began, 3)
    if not isinstance(response, Mapping):
        return ModelAnswer("", seconds, "", None, "invalid_response")
    text = _content(response)[:MAX_ANSWER_CHARS]
    usage = response.get("usage")
    completion = (
        _optional_int(usage.get("completion_tokens")) if isinstance(usage, Mapping) else None
    )
    choices = response.get("choices")
    reason = ""
    if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
        reason = str(choices[0].get("finish_reason") or "")
    return ModelAnswer(
        text,
        seconds,
        str(response.get("model") or ""),
        _prompt_tokens(response),
        None if "{" in text else "no_answer",
        completion,
        reason,
    )


def describe_fields(stats: Sequence[FieldStat], lines: int) -> str:
    if not stats:
        return "(no field could be read from the sample)"
    rows = [
        f"- {stat.name} present={stat.present}/{lines} distinct={stat.distinct} "
        f"variety={stat.variety} examples: " + " | ".join(f'"{value}"' for value in stat.examples)
        for stat in stats
    ]
    return "\n".join(rows)


def build_prompt(stats: Sequence[FieldStat], lines: int, structure: str = "") -> str:
    shape = f"\nEVENT STRUCTURE: {structure}" if structure else ""
    return f"{CARD_QUESTION}{shape}\n{describe_fields(stats, lines)}"


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
    ambiguous = _ambiguous_core_role(roles)
    if ambiguous is not None:
        return Answer(kind, {}, tuple(sorted(rejected)), "", f"ambiguous_roles:{ambiguous}")
    basis = str(answer.get("basis") or "")[:MAX_BASIS_CHARS]
    return Answer(kind, roles, tuple(sorted(rejected)), basis, None)


CORE_ROLES = ("actor", "action", "object")


def _ambiguous_core_role(roles: Mapping[str, tuple[str, ...]]) -> str | None:
    """The first field the answer gives two incompatible core roles, if any."""
    seen: dict[str, str] = {}
    for role in CORE_ROLES:
        for name in roles.get(role, ()):
            if name in seen:
                return name
            seen[name] = role
    return None


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


def _is_number(value: str) -> bool:
    try:
        float(value.replace(",", ""))
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def value_facts(parsed: Sequence[Parsed], stats: Sequence[FieldStat]) -> dict[str, float]:
    """How numeric the values are, and how much of them belong to recurring identities."""
    total = 0
    numeric = 0
    for item in parsed:
        for value in item.fields.values():
            if not value:
                continue
            total += 1
            if _is_number(value):
                numeric += 1
    recurring = sum(stat.present for stat in stats if stat.variety == "identity")
    return {
        "numeric_share": round(numeric / total, 4) if total else 0.0,
        "identity_share": round(recurring / total, 4) if total else 0.0,
    }


def cadence_facts(facts: SourceFacts) -> dict[str, Any]:
    active = facts.active_periods
    span = facts.periods
    return {
        "active_periods": active,
        "periods": span,
        "active_share": round(active / span, 4) if span else 0.0,
        "count_cv": facts.count_cv,
    }


def reconcile_kind(kind: str, facts: Mapping[str, Any]) -> tuple[str, str | None]:
    """Facts overrule a measurement claim that is not numeric; other conflicts are recorded."""
    numeric = float(facts.get("numeric_share") or 0.0)
    if kind == "measurement" and numeric < NUMERIC_SHARE_FOR_MEASUREMENT:
        return "activity", f"facts_override:measurement_numeric_share={numeric:.2f}"
    if kind == "activity" and numeric >= NUMERIC_SHARE_FOR_MEASUREMENT:
        return kind, f"kind_conflict:activity_numeric_share={numeric:.2f}"
    return kind, None


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
    part_field: str = "",
    part_value: str = "",
    kind_facts: Mapping[str, Any] | None = None,
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
        part_field=part_field,
        part_value=part_value,
        kind_facts=dict(kind_facts or {}),
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
        "shared_sources": [name for name in facts.sources[:12] if name in facts.shared_sources],
        "active_periods": facts.active_periods,
        "periods": facts.periods,
        "count_cv": facts.count_cv,
    }


class _Inputs:
    """What the sample says before any model call: the prompt and the evidence behind it."""

    def __init__(
        self,
        rows: Sequence[Mapping[str, Any]],
        parsed: Sequence[Parsed],
        windows: int,
        model: str,
    ) -> None:
        self.parsed = list(parsed)
        self.stats = field_stats(self.parsed)
        self.fmt, hits = _structure(self.parsed)
        considered = sum(1 for item in self.parsed if item.fmt != "header")
        self.coverage = hits / considered if considered else 0.0
        self.hits = hits
        self.sample = _sample_facts(rows, self.parsed)
        self.sample["windows"] = windows
        self.prompt = build_prompt(self.stats, considered, self.fmt)
        self.cache_key = hashlib.sha256(f"{model}\n{self.prompt}".encode()).hexdigest()
        self.value_facts = value_facts(self.parsed, self.stats)


def _answer(
    given: _Inputs, client: JudgeClient, model: str, cache: CardCache
) -> tuple[ModelAnswer, int, bool]:
    """The cached answer for this exact prompt, or one request whose answer is then cached."""
    cached = cache.get(given.cache_key)
    if cached is not None:
        return cached, 0, True
    answer = ask_model(client, model, given.prompt)
    if answer.error is None:
        cache.put(given.cache_key, answer)
    return answer, 1, False


def _model_facts(
    answer: ModelAnswer,
    *,
    requests: int,
    cached: bool,
    error: str | None,
    prompt: str,
) -> dict[str, Any]:
    return {
        "requests": requests,
        "seconds": answer.seconds,
        "served_model": answer.served_model,
        "prompt_tokens": answer.prompt_tokens,
        "completion_tokens": answer.completion_tokens,
        "finish_reason": answer.finish_reason,
        "raw_answer": answer.text,
        "answer_chars": len(answer.text),
        "cached": cached,
        "error": error,
        "prompt_chars": len(prompt),
        "prompt": prompt,
    }


@dataclass
class Prepared:
    """One structure ready to ask about, before any model request is made."""

    facts: SourceFacts
    given: _Inputs
    part_field: str = ""
    part_value: str = ""
    template: TemplateModel | None = None
    alert: bool = False
    alert_lines: int = 0


def prepare_cards(
    facts: SourceFacts, rows: Sequence[Mapping[str, Any]], windows: int, model: str
) -> list[Prepared]:
    """Parse one source's sample into one prepared structure per part."""
    parsed, template = parse_sample(_raws(rows))
    if template is not None:
        alert_lines = count_alert_lines(rows)
        alert = bool(rows) and alert_lines == len(rows)
        return [
            Prepared(
                facts,
                _Inputs(rows, parsed, windows, model),
                template=template,
                alert=alert,
                alert_lines=alert_lines,
            )
        ]
    partition = choose_partition(parsed)
    if partition is None:
        return [
            Prepared(
                facts,
                _Inputs(rows, parsed, windows, model),
                alert_lines=count_alert_lines(rows),
            )
        ]
    groups = partition_groups(parsed, rows, partition)
    prepared: list[Prepared] = []
    for value in partition.values:
        group = groups.get(value)
        if group is None:
            continue
        group_rows, group_parsed = group
        alert_lines = count_alert_lines(group_rows)
        prepared.append(
            Prepared(
                facts,
                _Inputs(group_rows, group_parsed, windows, model),
                partition.field,
                value,
                alert_lines=alert_lines,
                alert=bool(group_rows) and alert_lines == len(group_rows),
            )
        )
    return prepared or [
        Prepared(facts, _Inputs(rows, parsed, windows, model), alert_lines=count_alert_lines(rows))
    ]


def _ordered_structures(prepared: Sequence[Prepared]) -> list[Prepared]:
    """Distinct structures, highest-volume source first, then by content key."""
    unique: dict[str, Prepared] = {}
    for item in prepared:
        if item.template is None and item.given.parsed and item.given.hits:
            unique.setdefault(item.given.cache_key, item)
    return sorted(unique.values(), key=lambda item: (-item.facts.events, item.given.cache_key))


def answer_cards(
    prepared: Sequence[Prepared],
    client: JudgeClient,
    model: str,
    cache: CardCache,
    *,
    request_budget: int = CARDS_REQUEST_BUDGET,
) -> tuple[dict[str, tuple[ModelAnswer, int, bool]], dict[str, Any]]:
    """Cache first, then one request per distinct structure in priority order, inside the budget."""
    answers: dict[str, tuple[ModelAnswer, int, bool]] = {}
    pending: list[Prepared] = []
    for item in _ordered_structures(prepared):
        cached = cache.get(item.given.cache_key)
        if cached is not None:
            answers[item.given.cache_key] = (cached, 0, True)
        else:
            pending.append(item)
    budget = max(0, request_budget)
    ask, unasked = pending[:budget], pending[budget:]
    asker = client if isinstance(client, BackpressureClient) else BackpressureClient(client)
    with ThreadPoolExecutor(max_workers=CARD_CONCURRENCY) as pool:
        futures = {
            pool.submit(_answer, item.given, asker, model, cache): item.given.cache_key
            for item in ask
        }
        for future in as_completed(futures):
            answers[futures[future]] = future.result()
    for item in unasked:
        answers[item.given.cache_key] = (
            ModelAnswer("", 0.0, "", None, "budget_exhausted"),
            0,
            False,
        )
    stats: dict[str, Any] = {
        "structures": len(answers),
        "requests": sum(1 for _answer_value, requests, _cached in answers.values() if requests),
        "disk_hits": sum(1 for _answer_value, _requests, cached in answers.values() if cached),
        "unasked": len(unasked),
        "request_budget": budget,
        "unasked_sources": sorted(
            {f"{item.facts.index}:{item.facts.sourcetype}" for item in unasked}
        )[:12],
        "model_seconds": round(
            sum(answer.seconds for answer, requests, _cached in answers.values() if requests),
            3,
        ),
    }
    if isinstance(asker, BackpressureClient):
        stats["backpressure"] = asker.stats()
    return answers, stats


def _model_seconds(answer: ModelAnswer) -> float:  # kept for receipt symmetry
    return answer.seconds


def _template_card(item: Prepared, kind_facts: Mapping[str, Any]) -> SourceCard:
    """A free-text source understood by its header and templates, with roles taken from data."""
    facts, given, model = item.facts, item.given, item.template
    assert model is not None
    states = dict(model.states)
    given.sample["templates"] = states
    given.sample["header"] = {
        "tokens": model.header_tokens,
        "program_position": model.program_position,
    }
    model_facts = {
        "requests": 0,
        "reason": "structure",
        "templates": states,
        "header": given.sample["header"],
    }
    if not given.hits:
        return _failure(
            facts,
            reason=f"no_templates:coverage={given.coverage:.2f}",
            fmt="template",
            coverage=0.0,
            stats=given.stats,
            sample=given.sample,
            model=model_facts,
            cache_key=given.cache_key,
            kind_facts=kind_facts,
        )
    slot_fields = tuple(
        sorted({name for template in model.templates for _position, name in template.slots})
    )
    numeric = float(kind_facts.get("numeric_share") or 0.0)
    kind = (
        "alert"
        if item.alert
        else ("measurement" if numeric >= NUMERIC_SHARE_FOR_MEASUREMENT else "activity")
    )
    return SourceCard(
        index=facts.index,
        sourcetype=facts.sourcetype,
        kind=kind,
        roles={"actor": ("program",), "action": ("template",), "object": slot_fields},
        understood=True,
        reason=None,
        fmt="template",
        coverage=given.coverage,
        fields=tuple(given.stats),
        sample=given.sample,
        facts=_facts(facts),
        model=model_facts,
        cache_key=given.cache_key,
        basis=(
            "log template mining: header, per-program template and recurring slot values; "
            "roles from the data"
        ),
        kind_said="structure",
        kind_note=(
            "fast_log_alert_lines"
            if item.alert
            else (
                f"template_numeric_share={numeric:.2f}"
                if kind == "measurement"
                else "roles_from_data"
            )
        ),
        kind_facts=kind_facts,
        template_model=model,
    )


def _assemble(
    item: Prepared,
    answer: ModelAnswer,
    requests: int,
    cached: bool,
) -> SourceCard:
    """Apply one structure's answer to its card, or record exactly why it was not used."""
    facts, given = item.facts, item.given
    kind_facts = {**given.value_facts, **cadence_facts(facts)}
    if item.alert_lines:
        kind_facts["alert_lines"] = item.alert_lines
    if item.template is not None:
        return _template_card(item, kind_facts)
    if item.part_field:
        given.sample["part"] = {"field": item.part_field, "value": item.part_value}
    if not given.parsed or not given.hits:
        reason = (
            "no_sample" if not given.parsed else f"unparsed_sample:coverage={given.coverage:.2f}"
        )
        return _failure(
            facts,
            reason=reason,
            fmt="text",
            coverage=0.0,
            stats=given.stats,
            sample=given.sample,
            model={"requests": 0, "cached": False},
            cache_key=given.cache_key,
            part_field=item.part_field,
            part_value=item.part_value,
            kind_facts=kind_facts,
        )
    applied = apply_answer(answer.text, [stat.name for stat in given.stats])
    model_facts = _model_facts(
        answer,
        requests=requests,
        cached=cached,
        error=answer.error or applied.error,
        prompt=given.prompt,
    )
    model_failed = answer.error is not None or applied.error is not None or applied.rejected
    if model_failed and not item.alert:
        reason = f"model_{answer.error}" if answer.error else str(applied.error)
        if not reason or reason == "None":
            reason = "unknown_fields:" + ",".join(applied.rejected)
        return _failure(
            facts,
            reason=reason,
            fmt=given.fmt,
            coverage=given.coverage,
            stats=given.stats,
            sample=given.sample,
            model=model_facts,
            cache_key=given.cache_key,
            part_field=item.part_field,
            part_value=item.part_value,
            kind_facts=kind_facts,
        )
    kind, note = reconcile_kind(applied.kind, kind_facts)
    if item.alert and kind != "alert":
        kind, note = "alert", f"alert_structure:model_said_{applied.kind}"
    return SourceCard(
        index=facts.index,
        sourcetype=facts.sourcetype,
        kind=kind,
        roles=applied.roles,
        understood=True,
        reason=None,
        fmt=given.fmt,
        coverage=given.coverage,
        fields=tuple(given.stats),
        sample=given.sample,
        facts=_facts(facts),
        model=model_facts,
        cache_key=given.cache_key,
        basis=applied.basis,
        rejected=applied.rejected,
        columns=_columns(given.parsed, given.fmt),
        part_field=item.part_field,
        part_value=item.part_value,
        kind_said=applied.kind,
        kind_note=note,
        kind_facts=kind_facts,
    )


def assemble_cards(
    prepared: Sequence[Prepared], answers: Mapping[str, tuple[ModelAnswer, int, bool]]
) -> list[SourceCard]:
    """Build every card, charging a request only to the first card that needed it."""
    used: set[str] = set()
    cards: list[SourceCard] = []
    for item in prepared:
        key = item.given.cache_key
        answer, requests, cached = answers.get(
            key, (ModelAnswer("", 0.0, "", None, None), 0, False)
        )
        if key in used:
            requests, cached = 0, True
        used.add(key)
        cards.append(_assemble(item, answer, requests, cached))
    return cards


def _raws(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(row.get("_raw") or "") for row in rows]


def build_card(
    facts: SourceFacts,
    rows: Sequence[Mapping[str, Any]],
    *,
    windows: int,
    client: JudgeClient,
    model: str,
    cache: CardCache,
) -> SourceCard:
    """One card for one sample, without partitioning (the stage uses prepare/assemble)."""
    prepared = prepare_cards(facts, rows, windows, model)
    answers, _stats = answer_cards(prepared, client, model, cache)
    return assemble_cards(prepared, answers)[0]


def build_cards(
    facts: SourceFacts,
    rows: Sequence[Mapping[str, Any]],
    *,
    windows: int,
    client: JudgeClient,
    model: str,
    cache: CardCache,
) -> list[SourceCard]:
    """One card per distinct structure in the sample, split on the field that selects it."""
    prepared = prepare_cards(facts, rows, windows, model)
    answers, _stats = answer_cards(prepared, client, model, cache)
    return assemble_cards(prepared, answers)
