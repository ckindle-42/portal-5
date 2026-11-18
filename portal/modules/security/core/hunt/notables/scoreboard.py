"""Stage-1 scoreboard: notable recall per labelled step, judge separation, cost and honesty.

python -m portal.modules.security.core.hunt.notables.scoreboard --out results/hunt/knowledge_s2b \
    --keys kyoushi=.../kyoushi_s1_ingest/keys.jsonl --keys santos=.../santos_ingest/keys.jsonl
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .cards import CARD_KIND_CONSUMERS, card_consumers
from .knowledge import PROOF_INDEXES
from .receipt import read_json
from .relate import RELATE_FILE
from .run import GENERATORS, NOTABLES_FILE, SOURCES_FILE, card_from_dict

QUIET_MAX_LINES = 250  # statement §6: quiet steps are 1 to about 250 labelled lines
CUTS: tuple[int | None, ...] = (50, 100, None)
PROGRESS_FILE = "progress.json"
JUDGE_CACHE = Path("cache") / "judge.json"
STAGE_ORDER = ("cards", "behaviours", "notables", "judge")
RECALL_GENERATORS = (*GENERATORS, "relate")
YES = 0.5  # a judge answer counts as yes from p_yes >= 0.5

RULE = (
    "a notable covers a labelled line when the line's source is the one its evidence query "
    "selects (exact path; rotation-stripped sourcetype when the query names no path) and every "
    "literal TERM its evidence query names occurs in the line; a notable whose query names no "
    "TERM is attributed by its evidence window (the line's event time inside [earliest,latest)). "
    "A step is covered when one of its labelled lines is."
)

ENTITY_RULE = (
    "an artefact is located when its key value appears whole-word (NFC-normalized and "
    "casefolded on both sides) in a notable's what/basis/why, its entity values, or its "
    "evidence queries and lines; a step is covered "
    "when one of its artefacts is located and a scenario is found when one of its steps is. "
    "Asset matches (victim hosts/users) are reported but never cover a step or find a scenario "
    "on their own. An entry with admitted=false (failed the live locator audit) is excluded; "
    "admitted=null is scored but flagged pending until the intake audit locates its events."
)

_TERM = re.compile(r'TERM\("((?:[^"\\]|\\.)*)"\)')
_PLAIN_TERM = re.compile(r'(?<![=\w])"((?:[^"\\]|\\.)*)"')
_SOURCE = re.compile(r'source="([^"]+)"')
_ROTATION = re.compile(r"(\.\d+)+$")
_MONTHS = {name: number for number, name in enumerate(calendar.month_abbr) if name}
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})")
_CLF = re.compile(r"\[(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})")
_CTIME = re.compile(r"\w{3} +(\w{3}) +(\d{1,2}) (\d{2}):(\d{2}):(\d{2})[.\d]* (\d{4})")
_SYSLOG = re.compile(r"^(\w{3}) +(\d{1,2}) (\d{2}):(\d{2}):(\d{2})")
_EPOCH = re.compile(r"(?:audit\(|^)(\d{10})(\.\d+)?")


class ScoreboardError(RuntimeError):
    """The receipts, keys or log tree cannot be scored as asked."""


@dataclass(frozen=True)
class KeyLine:
    host: str
    source: str
    number: int
    labels: tuple[str, ...]


@dataclass(frozen=True)
class EntityKey:
    """One cited entity-level key row: an artefact or asset of a scenario step."""

    dataset: str
    scenario: str
    step: str
    value: str
    entity: str
    role: str
    citations: tuple[str, ...]
    locator: str
    audit_count: int | None
    admitted: bool | None


@dataclass(frozen=True)
class Claim:
    """What one notable's receipts say it reproduces: sources, literal terms, time window."""

    terms: tuple[str, ...]
    folded: tuple[str, ...]
    sources: frozenset[str]
    names: frozenset[str]
    window: tuple[float, float] | None


@dataclass
class Step:
    label: str
    lines: int = 0
    first_rank: int | None = None
    by_generator: dict[str, int] = field(default_factory=dict)

    @property
    def quiet(self) -> bool:
        return self.lines <= QUIET_MAX_LINES


@dataclass
class Notable:
    rank: int
    generator: str
    claim: Claim
    p_yes: float | None
    content_key: str = ""
    covered: bool = False


def _stem(source: str) -> str:
    """The source's own file name with rotation suffixes removed, as ingest names a sourcetype."""
    return _ROTATION.sub("", source.rstrip("/").rsplit("/", 1)[-1])


def _names(source_id: str) -> frozenset[str]:
    tail = source_id.split(":", 1)[-1]
    return frozenset({_stem(tail), tail.rsplit("/", 1)[-1]})


def _unquote(value: str) -> str:
    return value.replace('\\"', '"').replace("\\\\", "\\")


def _window(evidence: Sequence[Any]) -> tuple[float, float] | None:
    lows = [
        float(item["earliest"])
        for item in evidence
        if isinstance(item, Mapping) and item.get("earliest") is not None
    ]
    highs = [
        float(item["latest"])
        for item in evidence
        if isinstance(item, Mapping) and item.get("latest") is not None
    ]
    if not lows or not highs:
        return None
    return (min(lows), max(highs))


def _claim(row: Mapping[str, Any]) -> Claim:
    items = [item for item in row.get("evidence") or () if isinstance(item, Mapping)]
    queries = [str(item.get("query") or "") for item in items]
    terms = tuple(
        dict.fromkeys(
            _unquote(found)
            for query in queries
            for found in (*_TERM.findall(query), *_PLAIN_TERM.findall(query))
        )
    )
    sources = frozenset(found for query in queries for found in _SOURCE.findall(query))
    folded = tuple(term.casefold() for term in terms)
    return Claim(terms, folded, sources, _names(str(row.get("source_id") or "")), _window(items))


def _on_source(claim: Claim, source: str) -> bool:
    if claim.sources:
        return source in claim.sources
    return _stem(source) in claim.names


def _covers(claim: Claim, folded: str, moment: float | None) -> bool:
    if claim.folded:
        return all(term in folded for term in claim.folded)
    if claim.window is None or moment is None:
        return False
    return claim.window[0] <= moment < claim.window[1]


def _epoch(year: int, month: int, day: int, hour: str, minute: str, second: str) -> float:
    return float(calendar.timegm((year, month, day, int(hour), int(minute), int(second))))


def event_time(line: str, year: int) -> float | None:
    """The earliest ingest-readable timestamp in a line, naive times taken as UTC."""
    found: list[tuple[int, float]] = []
    if match := _ISO.search(line):
        part, month, day, hour, minute, second = match.groups()
        found.append((match.start(), _epoch(int(part), int(month), int(day), hour, minute, second)))
    if (match := _CLF.search(line)) and match.group(2) in _MONTHS:
        day, month, part, hour, minute, second = match.groups()
        found.append(
            (match.start(), _epoch(int(part), _MONTHS[month], int(day), hour, minute, second))
        )
    if (match := _CTIME.search(line)) and match.group(1) in _MONTHS:
        month, day, hour, minute, second, part = match.groups()
        found.append(
            (match.start(), _epoch(int(part), _MONTHS[month], int(day), hour, minute, second))
        )
    if (match := _SYSLOG.search(line)) and match.group(1) in _MONTHS:
        month, day, hour, minute, second = match.groups()
        found.append((match.start(), _epoch(year, _MONTHS[month], int(day), hour, minute, second)))
    if match := _EPOCH.search(line):
        found.append((match.start(), float(match.group(1)) + float(match.group(2) or 0.0)))
    return min(found)[1] if found else None


def _read_keys(path: Path) -> list[KeyLine]:
    if not path.is_file():
        raise ScoreboardError(f"keys not found: {path}")
    rows: list[KeyLine] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        stored = json.loads(raw)
        rows.append(
            KeyLine(
                str(stored["host"]),
                str(stored["source"]),
                int(stored["line"]),
                tuple(str(label) for label in stored.get("labels") or ()),
            )
        )
    if not rows:
        raise ScoreboardError(f"keys {path} hold no labelled line")
    return rows


def _keys_are_entity(path: Path) -> bool:
    """True when the first key row is entity-level (scenario/value) rather than per-line."""
    if not path.is_file():
        raise ScoreboardError(f"keys not found: {path}")
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        stored = json.loads(raw)
        if "line" in stored:
            return False
        if "value" in stored and "scenario" in stored:
            return True
        raise ScoreboardError(f"keys {path}: first row is neither per-line nor entity-level")
    return False  # an empty file stays in line mode, where _read_keys fails loudly


def _read_entity_keys(path: Path) -> list[EntityKey]:
    rows: list[EntityKey] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        stored = json.loads(raw)
        for name in ("dataset", "scenario", "step", "value", "role"):
            if name not in stored:
                raise ScoreboardError(f"entity key row lacks {name!r}: {raw[:120]}")
        audit = stored.get("audit")
        count = audit.get("count") if isinstance(audit, Mapping) else None
        admitted = stored.get("admitted")
        rows.append(
            EntityKey(
                str(stored["dataset"]),
                str(stored["scenario"]),
                str(stored["step"]),
                str(stored["value"]),
                str(stored.get("entity") or ""),
                str(stored["role"]),
                tuple(str(citation) for citation in stored.get("citations") or ()),
                str(stored.get("locator") or ""),
                int(count) if count is not None else None,
                None if admitted is None else bool(admitted),
            )
        )
    if not rows:
        raise ScoreboardError(f"keys {path} hold no entries")
    return rows


def _fold(text: str) -> str:
    """NFC-normalized then casefolded text: the form entity values are matched in."""
    return unicodedata.normalize("NFC", text).casefold()


def _entity_pattern(value: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(_fold(value)) + r"(?!\w)")


def _haystack(row: Mapping[str, Any]) -> str:
    """Everything a notable says, folded: the text entity keys are matched against."""
    parts = [str(row.get(name) or "") for name in ("what", "basis", "why")]
    for entity in row.get("entities") or ():
        if isinstance(entity, Mapping):
            parts.append(str(entity.get("value") or ""))
    for item in row.get("evidence") or ():
        if isinstance(item, Mapping):
            parts.append(str(item.get("query") or ""))
            parts.append(str(item.get("line") or ""))
    return _fold("\n".join(parts))


def _read_notables(directory: Path) -> list[dict[str, Any]]:
    path = directory / NOTABLES_FILE
    if not path.is_file():
        raise ScoreboardError(f"{path} holds no notables; run the notables stage")
    rows = [
        row
        for row in (json.loads(raw) for raw in path.read_text().splitlines() if raw.strip())
        if isinstance(row, dict)
    ]
    if not rows:
        raise ScoreboardError(f"{path} holds zero notables; there is nothing to score")
    return rows


def _run_index(directory: Path) -> tuple[str, set[str]]:
    payload = read_json(directory / SOURCES_FILE)
    sources = {
        str(name)
        for card in payload.get("cards") or ()
        if isinstance(card, Mapping)
        for name in (card.get("facts") or {}).get("sources") or ()
    }
    return str(payload.get("index") or ""), sources


def _card_contract(directory: Path) -> dict[str, Any]:
    payload = read_json(directory / SOURCES_FILE)
    cards = [card_from_dict(raw) for raw in payload.get("cards") or () if isinstance(raw, Mapping)]
    by_kind = Counter(card.kind for card in cards)
    consumer_names = sorted(
        {consumer for routes in CARD_KIND_CONSUMERS.values() for consumer in routes}
    )
    return {
        "cards": len(cards),
        "by_kind": dict(sorted(by_kind.items())),
        "consumers": {
            consumer: sorted(card.card_id for card in cards if consumer in card_consumers(card))
            for consumer in consumer_names
        },
    }


def _check_family(index: str, keys: Sequence[KeyLine], run_sources: set[str]) -> None:
    if index in PROOF_INDEXES:
        raise ScoreboardError(f"{index!r} is a proof index; it is never scored here")
    named = {line.source for line in keys}
    if run_sources and not (named & run_sources):
        raise ScoreboardError(
            f"keys name no source this run read ({sorted(named)[:2]} vs "
            f"{sorted(run_sources)[:2]}); they belong to another family"
        )


def _default_logs(keys_path: Path) -> Path:
    parent = keys_path.resolve().parent
    if parent.name.endswith("_ingest"):
        candidate = parent.parent / parent.name[: -len("_ingest")] / "gather"
        if candidate.is_dir():
            return candidate
    raise ScoreboardError(
        "cannot find the raw tree that holds the labelled lines; pass --logs "
        f"<corpus>/<family>/gather (looked under {parent.parent}/*/gather)"
    )


def _year(progress: Mapping[str, Any], notables: Sequence[Mapping[str, Any]]) -> int:
    windows = [
        float(item["earliest"])
        for row in notables
        for item in row.get("evidence") or ()
        if isinstance(item, Mapping) and item.get("earliest") is not None
    ]
    if windows:
        return time.gmtime(min(windows)).tm_year
    cards = (progress.get("stages") or {}).get("cards")
    start = cards.get("start") if isinstance(cards, Mapping) else None
    return (
        time.gmtime(float(start)).tm_year if isinstance(start, (int, float)) and start > 0 else 1970
    )


def _steps(keys: Sequence[KeyLine]) -> dict[str, Step]:
    steps: dict[str, Step] = {}
    for line in keys:
        for label in line.labels:
            steps.setdefault(label, Step(label)).lines += 1
    return steps


def _mark(steps: Mapping[str, Step], labels: Sequence[str], notable: Notable) -> None:
    notable.covered = True
    for label in labels:
        step = steps[label]
        if step.first_rank is None or notable.rank < step.first_rank:
            step.first_rank = notable.rank
        known = step.by_generator.get(notable.generator)
        if known is None or notable.rank < known:
            step.by_generator[notable.generator] = notable.rank


def _scan(
    path: Path,
    wanted: Mapping[int, tuple[str, ...]],
    active: Sequence[Notable],
    steps: Mapping[str, Step],
    year: int,
) -> None:
    """One pass over a labelled file, each line against the notables that name that source."""
    timed = any(not notable.claim.terms for notable in active)
    with path.open(encoding="utf-8", errors="replace") as handle:
        for number, raw in enumerate(handle, 1):
            labels = wanted.get(number)
            if labels is None:
                continue
            text = raw.rstrip("\r\n")
            folded = text.casefold()
            moment = event_time(text, year) if timed else None
            for notable in active:
                if _covers(notable.claim, folded, moment):
                    _mark(steps, labels, notable)


def _coverage(
    steps: Mapping[str, Step],
    notables: Sequence[Notable],
    keys: Sequence[KeyLine],
    logs: Path,
    year: int,
) -> None:
    wanted: dict[tuple[str, str], dict[int, tuple[str, ...]]] = defaultdict(dict)
    for line in keys:
        wanted[(line.host, line.source)][line.number] = line.labels
    for (host, source), lines in sorted(wanted.items()):
        path = logs / host / "logs" / source.lstrip("/")
        if not path.is_file():
            raise ScoreboardError(f"keys name {host}{source} but {path} is not there")
        active = [notable for notable in notables if _on_source(notable.claim, source)]
        if active:
            _scan(path, lines, active, steps, year)


def _auc(bad: Sequence[float], good: Sequence[float]) -> float | None:
    if not bad or not good:
        return None
    ordered = sorted([(value, 1) for value in bad] + [(value, 0) for value in good])
    ranks, offset = 0.0, 0
    while offset < len(ordered):
        stop = offset + 1
        while stop < len(ordered) and ordered[stop][0] == ordered[offset][0]:
            stop += 1
        rank = (offset + 1 + stop) / 2
        ranks += rank * sum(1 for _value, label in ordered[offset:stop] if label == 1)
        offset = stop
    return (ranks - len(bad) * (len(bad) + 1) / 2) / (len(bad) * len(good))


def _judged(notables: Sequence[Notable], cache: Mapping[str, Any]) -> list[tuple[Notable, float]]:
    scored: list[tuple[Notable, float]] = []
    for notable in notables:
        stored = cache.get(notable.content_key)
        p_yes = notable.p_yes
        if p_yes is None and isinstance(stored, Mapping) and stored.get("p_yes") is not None:
            p_yes = float(stored["p_yes"])
        if p_yes is not None:
            scored.append((notable, p_yes))
    return scored


def _rate(values: Sequence[float]) -> float | None:
    return sum(1 for value in values if value >= YES) / len(values) if values else None


def _judge_block(notables: Sequence[Notable], cache: Mapping[str, Any]) -> dict[str, Any] | None:
    scored = _judged(notables, cache)
    if not scored:
        return None
    bad = [value for notable, value in scored if notable.covered]
    good = [value for notable, value in scored if not notable.covered]
    return {
        "judged": len(scored),
        "bad": len(bad),
        "good": len(good),
        "auc": _auc(bad, good),
        "yes_rate_bad": _rate(bad),
        "yes_rate_good": _rate(good),
        "labelling": "bad = the notable covers a labelled line; good = it covers none",
    }


def _request_count(name: str, stage: Mapping[str, Any]) -> int:
    if name == "cards":
        return int(stage.get("model_requests") or 0)
    if name == "judge":
        return int(stage.get("requests") or 0)
    return 0


def _stage_seconds(name: str, stage: Mapping[str, Any]) -> float:
    raw = stage.get("seconds")
    if isinstance(raw, Mapping):
        return float(raw.get("total") or 0.0)
    if name == "behaviours" and stage.get("seconds_total") is not None:
        return float(stage["seconds_total"])
    return float(raw or 0.0)


def _cost(progress: Mapping[str, Any]) -> dict[str, Any]:
    stages = progress.get("stages") or {}
    rows: dict[str, Any] = {}
    for name in STAGE_ORDER:
        stage = stages.get(name)
        if isinstance(stage, Mapping):
            rows[name] = {
                "seconds": round(_stage_seconds(name, stage), 3),
                "model_requests": _request_count(name, stage),
                "peak_memory_mb": stage.get("peak_memory_mb"),
            }
    return {
        "stages": rows,
        "seconds": round(sum(float(row["seconds"]) for row in rows.values()), 3),
        "model_requests": sum(int(row["model_requests"]) for row in rows.values()),
        "peak_memory_mb": progress.get("peak_memory_mb"),
    }


def _honesty(progress: Mapping[str, Any], family: str) -> dict[str, Any]:
    stages = progress.get("stages")
    notables = stages.get("notables") if isinstance(stages, Mapping) else None
    detail = notables.get("similar_to_known") if isinstance(notables, Mapping) else None
    if not isinstance(detail, Mapping):
        return {"knowledge": "none loaded (similar_to_known did not run in this receipt)"}
    excluded = detail.get("excluded_family")
    loaded = [str(f) for f in detail.get("loaded_families") or ()]
    if detail.get("index_unseen") and not excluded and family not in loaded:
        # A dataset the store has never seen has nothing of its own to leave out; the loader's
        # leak guard already refused rows carrying the run's index (2026-11-18, botsv2).
        excluded = family
    if excluded is None or str(excluded) != family:
        raise ScoreboardError(
            f"the notables receipt excludes {excluded!r}, not {family!r}: the run under test "
            "learned from its own family"
        )
    reliability = detail.get("reliability")
    return {
        "knowledge": "loaded",
        "families": list(detail.get("loaded_families") or ()),
        "excluded_family": excluded,
        "knowledge_items": detail.get("knowledge_items"),
        "embedding_model": detail.get("embedding_model"),
        "reliability_auc": reliability.get("auc") if isinstance(reliability, Mapping) else None,
    }


def _cut(rank: int | None, limit: int | None) -> bool:
    return rank is not None and (limit is None or rank < limit)


def _count(steps: Sequence[Step], rank_of: Callable[[Step], int | None], limit: int | None) -> int:
    return sum(1 for step in steps if _cut(rank_of(step), limit))


def _generator_rank(name: str) -> Callable[[Step], int | None]:
    def rank_of(step: Step) -> int | None:
        return step.by_generator.get(name)

    return rank_of


def _read_count(limit: int | None, total: int) -> int:
    return total if limit is None else min(limit, total)


def _recall(steps: Sequence[Step]) -> dict[str, Any]:
    def quiet(step: Step) -> int | None:
        return step.first_rank if step.quiet else None

    def loud(step: Step) -> int | None:
        return None if step.quiet else step.first_rank

    return {
        "steps": len(steps),
        "overall": {
            str(limit): _count(steps, lambda step: step.first_rank, limit) for limit in CUTS
        },
        "by_generator": {
            name: {str(limit): _count(steps, _generator_rank(name), limit) for limit in CUTS}
            for name in RECALL_GENERATORS
        },
        "quiet": {
            "steps": sum(1 for step in steps if step.quiet),
            "covered": {str(limit): _count(steps, quiet, limit) for limit in CUTS},
        },
        "loud": {
            "steps": sum(1 for step in steps if not step.quiet),
            "covered": {str(limit): _count(steps, loud, limit) for limit in CUTS},
        },
    }


def _tally(notables: Sequence[Notable]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for notable in notables:
        counts[notable.generator] = counts.get(notable.generator, 0) + 1
    return counts


def _step_row(step: Step) -> dict[str, Any]:
    return {
        "step": step.label,
        "lines": step.lines,
        "quiet": step.quiet,
        "first_rank": step.first_rank,
        "covered": {str(limit): _cut(step.first_rank, limit) for limit in CUTS},
        "by_generator": dict(sorted(step.by_generator.items(), key=lambda item: item[1])),
        "by_generator_covered": {
            name: {str(limit): _cut(step.by_generator.get(name), limit) for limit in CUTS}
            for name in RECALL_GENERATORS
        },
    }


def _family(
    family: str,
    directory: Path,
    keys_path: Path,
    logs: Path | None,
    year: int | None,
) -> dict[str, Any]:
    rows = _read_notables(directory)
    progress = read_json(directory / PROGRESS_FILE)
    if not progress:
        raise ScoreboardError(f"{directory / PROGRESS_FILE} is missing; this run is not scored")
    keys = _read_keys(keys_path)
    index, run_sources = _run_index(directory)
    _check_family(index, keys, run_sources)
    resolved = logs if logs is not None else _default_logs(keys_path)
    picked = year if year is not None else _year(progress, rows)
    labelled_sources = {line.source for line in keys}
    steps = _steps(keys)
    notables = _ranked_notables(rows)
    _coverage(steps, notables, keys, resolved, picked)
    ordered = sorted(steps.values(), key=lambda step: (not step.quiet, step.lines, step.label))
    report = {
        "family": family,
        "index": index,
        "card_contract": _card_contract(directory),
        "rule": RULE,
        "keys": {
            "file": str(keys_path),
            "labelled_lines": len(keys),
            "sources": sorted({line.source for line in keys}),
            "logs": str(resolved),
            "year": picked,
        },
        "notables": {
            "total": len(notables),
            "by_generator": _tally(notables),
            "on_labelled_sources": sum(
                1
                for notable in notables
                if any(_on_source(notable.claim, source) for source in labelled_sources)
            ),
            "covering": sum(1 for notable in notables if notable.covered),
            "unattributable": sum(
                1
                for notable in notables
                if not notable.claim.terms and notable.claim.window is None
            ),
            "cost": {str(limit): _read_count(limit, len(notables)) for limit in CUTS},
        },
        "steps": [_step_row(step) for step in ordered],
        "recall": _recall(ordered),
        "judge": _judge_block(notables, read_json(directory / JUDGE_CACHE)),
        "cost": _cost(progress),
        "honesty": _honesty(progress, family),
    }
    relation = _relation_report(directory, rows, keys, resolved, picked, ordered)
    if relation is not None:
        report["relate"] = relation
    return report


def _ranked_notables(rows: Sequence[Mapping[str, Any]]) -> list[Notable]:
    return [
        Notable(
            rank,
            str(row.get("generator") or ""),
            _claim(row),
            float(row["p_yes"]) if row.get("p_yes") is not None else None,
            str(row.get("content_key") or ""),
        )
        for rank, row in enumerate(rows)
    ]


def _with_related(
    rows: Sequence[dict[str, Any]], related: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    def anchor_rank(item: Mapping[str, Any]) -> int:
        try:
            raw = item.get("anchor_rank")
            return int(raw) if raw is not None else len(rows)
        except (TypeError, ValueError):
            return len(rows)

    appended = sorted(
        related,
        key=lambda item: (
            anchor_rank(item),
            -float(item.get("relation_score") or 0.0),
            str(item.get("notable_id") or ""),
        ),
    )
    return [*rows, *appended]


def _keyed_event_hashes(
    keys: Sequence[KeyLine], logs: Path
) -> dict[tuple[str, str, str], tuple[str, ...]]:
    wanted: dict[tuple[str, str], dict[int, list[str]]] = defaultdict(dict)
    for item in keys:
        wanted[(item.host, item.source)][item.number] = list(item.labels)
    found: dict[tuple[str, str, str], tuple[str, ...]] = {}
    for (host, source), lines in sorted(wanted.items()):
        path = logs / host / "logs" / source.lstrip("/")
        with path.open(encoding="utf-8", errors="replace") as handle:
            for number, raw in enumerate(handle, 1):
                labels = lines.get(number)
                if labels is None:
                    continue
                digest = hashlib.sha256(raw.rstrip("\r\n").encode()).hexdigest()
                identity = (host, source, digest)
                found[identity] = tuple(sorted(set(found.get(identity, ()) + tuple(labels))))
    return found


def _case_purity(
    cases: Sequence[Mapping[str, Any]],
    keys: Sequence[KeyLine],
    logs: Path,
) -> dict[str, Any]:
    keyed = _keyed_event_hashes(keys, logs)
    results: list[dict[str, Any]] = []
    for rank, case in enumerate(cases):
        events = [item for item in case.get("evidence") or () if isinstance(item, Mapping)]
        labels: Counter[str] = Counter()
        matched = 0
        for event in events:
            identity = (
                str(event.get("host") or ""),
                str(event.get("source") or ""),
                str(event.get("raw_sha256") or ""),
            )
            found = keyed.get(identity)
            if found is not None:
                matched += 1
                labels.update(found)
        results.append(
            {
                "rank": rank,
                "case_id": str(case.get("case_id") or ""),
                "events": len(events),
                "keyed_events": matched,
                "purity": round(matched / len(events), 6) if events else None,
                "labels": dict(sorted(labels.items())),
            }
        )
    measurable = [float(row["purity"]) for row in results if row["purity"] is not None]
    return {
        "cases": results,
        "mean": round(sum(measurable) / len(measurable), 6) if measurable else None,
    }


def _relation_report(
    directory: Path,
    rows: Sequence[dict[str, Any]],
    keys: Sequence[KeyLine],
    logs: Path,
    year: int,
    before_steps: Sequence[Step],
) -> dict[str, Any] | None:
    path = directory / RELATE_FILE
    if not path.is_file():
        return None
    payload = read_json(path)
    related = [item for item in payload.get("notables") or () if isinstance(item, dict)]
    cases = [item for item in payload.get("cases") or () if isinstance(item, Mapping)]
    after_rows = _with_related(rows, related)
    after_steps = _steps(keys)
    _coverage(after_steps, _ranked_notables(after_rows), keys, logs, year)
    return {
        "related_notables": len(related),
        "cases": len(cases),
        "before": _recall(before_steps),
        "after": _recall(
            sorted(after_steps.values(), key=lambda step: (not step.quiet, step.lines, step.label))
        ),
        "case_purity": _case_purity(cases, keys, logs),
        "receipt": payload.get("receipt") or {},
    }


def _check_entity_family(index: str, keys: Sequence[EntityKey]) -> None:
    if index in PROOF_INDEXES:
        raise ScoreboardError(f"{index!r} is a proof index; it is never scored here")
    datasets = {key.dataset for key in keys}
    for dataset in sorted(datasets):
        if dataset in PROOF_INDEXES:
            raise ScoreboardError(f"keys cite proof index {dataset!r}; it is never scored here")
    if len(datasets) != 1 or (index and datasets != {index}):
        raise ScoreboardError(
            f"keys are for {', '.join(sorted(datasets))} but this run read {index or '?'}; "
            "they belong to another family"
        )


def _entity_split(keys: Sequence[EntityKey]) -> tuple[list[EntityKey], list[EntityKey], int]:
    artefacts = [key for key in keys if key.role == "artefact" and key.admitted is not False]
    assets = [key for key in keys if key.role == "asset"]
    rejected = sum(1 for key in keys if key.role == "artefact" and key.admitted is False)
    return artefacts, assets, rejected


def _entity_groups(artefacts: Sequence[EntityKey]) -> tuple[dict[str, Step], dict[str, Step]]:
    steps: dict[str, Step] = {}
    scenarios: dict[str, Step] = {}
    for key in artefacts:
        step = steps.setdefault(f"{key.scenario}/{key.step}", Step(f"{key.scenario}/{key.step}"))
        step.lines += key.audit_count or 0
        scenario = scenarios.setdefault(key.scenario, Step(key.scenario))
        scenario.lines += key.audit_count or 0
    return steps, scenarios


def _entity_order(groups: Mapping[str, Step]) -> list[Step]:
    return sorted(groups.values(), key=lambda step: (not step.quiet, step.lines, step.label))


def _entity_pass(
    artefacts: Sequence[EntityKey],
    rows: Sequence[dict[str, Any]],
    hays: Sequence[str],
) -> tuple[list[Notable], list[int | None], list[dict[str, int]], dict[str, Step], dict[str, Step]]:
    """One ranked pass: first notable locating each artefact, marking steps and scenarios."""
    notables = _ranked_notables(rows)
    steps, scenarios = _entity_groups(artefacts)
    patterns = [_entity_pattern(key.value) for key in artefacts]
    firsts: list[int | None] = [None] * len(artefacts)
    by_generator: list[dict[str, int]] = [{} for _ in artefacts]
    for notable, hay in zip(notables, hays, strict=True):
        for position, pattern in enumerate(patterns):
            if not pattern.search(hay):
                continue
            key = artefacts[position]
            if firsts[position] is None:
                firsts[position] = notable.rank
            by_generator[position].setdefault(notable.generator, notable.rank)
            notable.covered = True
            _mark(steps, [f"{key.scenario}/{key.step}"], notable)
            _mark(scenarios, [key.scenario], notable)
    return notables, firsts, by_generator, steps, scenarios


def _artefact_rows(
    artefacts: Sequence[EntityKey],
    firsts: Sequence[int | None],
    generators: Sequence[dict[str, int]],
) -> list[dict[str, Any]]:
    return [
        {
            "scenario": key.scenario,
            "step": key.step,
            "value": key.value,
            "entity": key.entity,
            "events": key.audit_count,
            "admitted": key.admitted,
            "first_rank": firsts[position],
            "covered": {str(limit): _cut(firsts[position], limit) for limit in CUTS},
            "by_generator": dict(sorted(generators[position].items(), key=lambda item: item[1])),
        }
        for position, key in enumerate(artefacts)
    ]


def _asset_rows(
    assets: Sequence[EntityKey], rows: Sequence[dict[str, Any]], hays: Sequence[str]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in assets:
        pattern = _entity_pattern(key.value)
        first: int | None = None
        by_generator: dict[str, int] = {}
        for position, hay in enumerate(hays):
            if not pattern.search(hay):
                continue
            if first is None:
                first = position
            by_generator.setdefault(str(rows[position].get("generator") or ""), position)
        out.append(
            {
                "scenario": key.scenario,
                "step": key.step,
                "value": key.value,
                "entity": key.entity,
                "events": key.audit_count,
                "first_rank": first,
                "by_generator": dict(sorted(by_generator.items(), key=lambda item: item[1])),
            }
        )
    return out


def _case_rows(
    cases: Sequence[Mapping[str, Any]], artefacts: Sequence[EntityKey]
) -> list[dict[str, Any]]:
    patterns = [(key, _entity_pattern(key.value)) for key in artefacts]
    out: list[dict[str, Any]] = []
    for rank, case in enumerate(cases):
        events = [item for item in case.get("evidence") or () if isinstance(item, Mapping)]
        parts = [
            str(event.get(name) or "") for event in events for name in ("line", "query", "host")
        ]
        text = _fold("\n".join(parts))
        found = sorted(
            {(key.scenario, key.value) for key, pattern in patterns if pattern.search(text)}
        )
        out.append(
            {
                "rank": rank,
                "case_id": str(case.get("case_id") or ""),
                "events": len(events),
                "artefacts": [
                    {"scenario": found_scenario, "value": value} for found_scenario, value in found
                ],
                "scenarios": sorted({found_scenario for found_scenario, _ in found}),
            }
        )
    return out


def _entity_relation(
    directory: Path,
    rows: Sequence[dict[str, Any]],
    artefacts: Sequence[EntityKey],
    before_steps: Mapping[str, Step],
    before_scenarios: Mapping[str, Step],
) -> dict[str, Any] | None:
    path = directory / RELATE_FILE
    if not path.is_file():
        return None
    payload = read_json(path)
    related = [item for item in payload.get("notables") or () if isinstance(item, dict)]
    cases = [item for item in payload.get("cases") or () if isinstance(item, Mapping)]
    after_rows = _with_related(rows, related)
    after_hays = [_haystack(row) for row in after_rows]
    _, _, _, after_steps, after_scenarios = _entity_pass(artefacts, after_rows, after_hays)
    case_rows = _case_rows(cases, artefacts)
    true_ranks = [row["rank"] for row in case_rows if row["scenarios"]]
    first_true = min(true_ranks) if true_ranks else None
    false_above = sum(1 for row in case_rows if first_true is not None and row["rank"] < first_true)
    return {
        "related_notables": len(related),
        "cases": len(cases),
        "before": _recall(_entity_order(before_steps)),
        "after": _recall(_entity_order(after_steps)),
        "scenario_before": _recall(_entity_order(before_scenarios)),
        "scenario_after": _recall(_entity_order(after_scenarios)),
        "case_rows": case_rows,
        "first_true_case_rank": first_true,
        "false_cases_above_first_true": false_above,
        "receipt": payload.get("receipt") or {},
    }


def _entity_family(family: str, directory: Path, keys_path: Path) -> dict[str, Any]:
    rows = _read_notables(directory)
    progress = read_json(directory / PROGRESS_FILE)
    if not progress:
        raise ScoreboardError(f"{directory / PROGRESS_FILE} is missing; this run is not scored")
    keys = _read_entity_keys(keys_path)
    index, _run_sources = _run_index(directory)
    _check_entity_family(index, keys)
    artefacts, assets, rejected = _entity_split(keys)
    hays = [_haystack(row) for row in rows]
    notables, firsts, by_generator, steps, scenarios = _entity_pass(artefacts, rows, hays)
    ordered, ordered_scenarios = _entity_order(steps), _entity_order(scenarios)
    report = {
        "family": family,
        "index": index,
        "mode": "entity",
        "card_contract": _card_contract(directory),
        "rule": ENTITY_RULE,
        "keys": {
            "file": str(keys_path),
            "scenarios": len({key.scenario for key in keys}),
            "steps": len({(key.scenario, key.step) for key in keys}),
            "artefacts": len(artefacts),
            "assets": len(assets),
            "pending_audit": sum(1 for key in artefacts if key.admitted is None),
            "not_admitted": rejected,
        },
        "notables": {
            "total": len(notables),
            "by_generator": _tally(notables),
            "covering": sum(1 for notable in notables if notable.covered),
            "cost": {str(limit): _read_count(limit, len(notables)) for limit in CUTS},
        },
        "artefacts": _artefact_rows(artefacts, firsts, by_generator),
        "assets": _asset_rows(assets, rows, hays),
        "steps": [_step_row(step) for step in ordered],
        "scenarios": [_step_row(step) for step in ordered_scenarios],
        "recall": _recall(ordered),
        "scenario_recall": _recall(ordered_scenarios),
        "judge": _judge_block(notables, read_json(directory / JUDGE_CACHE)),
        "cost": _cost(progress),
        "honesty": _honesty(progress, family),
    }
    relation = _entity_relation(directory, rows, artefacts, steps, scenarios)
    if relation is not None:
        report["relate"] = relation
    return report


def _targets(out: Path) -> list[tuple[str, Path]]:
    if (out / NOTABLES_FILE).is_file():
        return [(out.name, out)]
    found = [
        (child.name, child)
        for child in sorted(out.iterdir())
        if child.is_dir() and (child / NOTABLES_FILE).is_file()
    ]
    if not found:
        raise ScoreboardError(f"{out} holds no <family>/{NOTABLES_FILE} to score")
    return found


def _key_paths(values: Sequence[str], families: Sequence[str]) -> dict[str, Path]:
    if len(values) == 1 and "=" not in values[0]:
        if len(families) != 1:
            raise ScoreboardError(
                "several families are scored, so --keys needs one family=path for each "
                f"({', '.join(families)})"
            )
        return {families[0]: Path(values[0])}
    found: dict[str, Path] = {}
    for value in values:
        family, _, path = value.partition("=")
        if not family or not path:
            raise ScoreboardError(f"--keys {value!r} is not family=path")
        found[family.strip()] = Path(path)
    missing = [family for family in families if family not in found]
    if missing:
        raise ScoreboardError(f"no --keys given for {', '.join(missing)}")
    return found


def _flag(value: bool) -> str:
    return "yes" if value else "no"


def _generator_line(step: Mapping[str, Any]) -> str:
    ranks = step.get("by_generator") or {}
    return ",".join(f"{name}@{rank}" for name, rank in ranks.items()) or "-"


def _step_table(steps: Sequence[Mapping[str, Any]], quiet: bool) -> list[str]:
    chosen = [step for step in steps if step["quiet"] is quiet]
    if not chosen:
        return []
    lines = [
        f"  {'step':<24}{'lines':>8}  {'top50':>5} {'top100':>6} {'all':>4}  covered by",
    ]
    for step in chosen:
        covered = step.get("covered") or {}
        lines.append(
            f"  {step['step']:<24}{step['lines']:>8}  "
            f"{_flag(bool(covered['50'])):>5} {_flag(bool(covered['100'])):>6} "
            f"{_flag(bool(covered['None'])):>4}  {_generator_line(step)}"
        )
    return lines


def _summary_lines(report: Mapping[str, Any]) -> list[str]:
    recall = report["recall"]
    keys = report["keys"]
    notables = report["notables"]
    lines = [
        f"family {report['family']}  index {report['index'] or '?'}",
        f"keys {keys['file']}  labelled lines {keys['labelled_lines']}  "
        f"steps {recall['steps']}  logs {keys['logs']} (year {keys['year']})",
        f"notables {notables['total']} {notables['by_generator']}  on a labelled source "
        f"{notables['on_labelled_sources']}  covering any labelled line "
        f"{notables['covering']}  unattributable {notables['unattributable']}",
        f"quiet = a step with <= {QUIET_MAX_LINES} labelled lines (§6)",
        "top N = the first N lines of notables.jsonl, the run's own order",
        "rule: " + report["rule"],
    ]
    if not notables["on_labelled_sources"]:
        lines.append(
            "WARNING no notable names a source the keys label; this family's zeros are the "
            "run's, not the keys'"
        )
    return lines


def _recall_lines(report: Mapping[str, Any]) -> list[str]:
    recall = report["recall"]
    overall = recall["overall"]
    quiet, loud = recall["quiet"], recall["loud"]
    cost = report["notables"]
    lines = [
        f"recall  top50 {overall['50']}/{recall['steps']}   top100 {overall['100']}/"
        f"{recall['steps']}   all {overall['None']}/{recall['steps']}   "
        f"notables that cost {cost['cost']}",
        f"  quiet {quiet['covered']['50']}/{quiet['steps']} (top50) "
        f"{quiet['covered']['None']}/{quiet['steps']} (all)   "
        f"loud {loud['covered']['50']}/{loud['steps']} (top50) "
        f"{loud['covered']['None']}/{loud['steps']} (all)",
        f"  {'generator':<18}{'top50':>8}{'top100':>8}{'all':>8}",
    ]
    for name, counts in recall["by_generator"].items():
        lines.append(f"  {name:<18}{counts['50']:>8}{counts['100']:>8}{counts['None']:>8}")
    return lines


def _relate_lines(report: Mapping[str, Any]) -> list[str]:
    relation = report.get("relate")
    if not isinstance(relation, Mapping):
        return []
    before = relation["before"]
    after = relation["after"]
    purity = relation["case_purity"]
    lines = [
        f"relate recall before top50 {before['overall']['50']}/{before['steps']} "
        f"top100 {before['overall']['100']}/{before['steps']} "
        f"all {before['overall']['None']}/{before['steps']}",
        f"relate recall after  top50 {after['overall']['50']}/{after['steps']} "
        f"top100 {after['overall']['100']}/{after['steps']} "
        f"all {after['overall']['None']}/{after['steps']}",
        f"relate cases {relation['cases']}  related events {relation['related_notables']}  "
        f"key overlap mean purity {purity['mean']}",
    ]
    lines.extend(
        f"  case {case['rank'] + 1}: {case['case_id']}  "
        f"keyed events {case['keyed_events']}/{case['events']}  purity {case['purity']}"
        for case in purity["cases"]
    )
    return lines


def _cost_lines(report: Mapping[str, Any]) -> list[str]:
    cost = report["cost"]
    stages = "  ".join(
        f"{name}={row['seconds']}s/{row['model_requests']}req"
        for name, row in cost["stages"].items()
    )
    return [
        f"cost {stages}  total={cost['seconds']}s requests={cost['model_requests']} "
        f"peak={cost['peak_memory_mb']}MB"
    ]


def _judge_lines(report: Mapping[str, Any]) -> list[str]:
    judge = report["judge"]
    if judge is None:
        return ["judge: no judge result in this run (omitted)"]
    auc = judge["auc"]
    return [
        f"judge  judged {judge['judged']}  bad {judge['bad']}  good {judge['good']}  "
        f"AUC {'n/a' if auc is None else round(auc, 3)}  "
        f"yes-rate bad {judge['yes_rate_bad']} good {judge['yes_rate_good']}  "
        f"({judge['labelling']})"
    ]


def _honesty_lines(report: Mapping[str, Any]) -> list[str]:
    honesty = report["honesty"]
    if honesty["knowledge"] != "loaded":
        return [f"honesty knowledge: {honesty['knowledge']}"]
    return [
        f"honesty knowledge families {honesty['families']}  items {honesty['knowledge_items']}  "
        f"excluded {honesty['excluded_family']}  reliability AUC {honesty['reliability_auc']}"
    ]


def _entity_summary_lines(report: Mapping[str, Any]) -> list[str]:
    keys = report["keys"]
    notables = report["notables"]
    lines = [
        f"family {report['family']}  index {report['index'] or '?'}  mode entity",
        f"keys {keys['file']}  scenarios {keys['scenarios']}  steps {keys['steps']}  "
        f"artefacts {keys['artefacts']}  assets {keys['assets']}",
        f"notables {notables['total']} {notables['by_generator']}  covering any artefact "
        f"{notables['covering']}",
        f"quiet = a step whose artefacts total <= {QUIET_MAX_LINES} keyed events (audit counts; "
        "an artefact pending audit counts 0)",
        "top N = the first N lines of notables.jsonl, the run's own order",
        "rule: " + report["rule"],
    ]
    if keys["pending_audit"]:
        lines.append(
            f"WARNING {keys['pending_audit']} artefacts are pending the live locator audit "
            "(admitted=null); the family does not count until it passes"
        )
    if keys["not_admitted"]:
        lines.append(
            f"{keys['not_admitted']} artefacts excluded: a live audit found no events "
            "(admitted=false)"
        )
    return lines


def _entity_artefact_table(artefacts: Sequence[Mapping[str, Any]]) -> list[str]:
    if not artefacts:
        return ["  none"]
    lines = [
        f"  {'scenario/step':<40}{'artefact':<46}{'kind':<10}{'events':>9}  "
        f"{'top50':>5} {'top100':>6} {'all':>4} {'rank':>6}  covered by"
    ]
    for row in artefacts:
        covered = row["covered"]
        events = row["events"] if row["events"] is not None else "pending"
        rank = row["first_rank"] if row["first_rank"] is not None else "-"
        lines.append(
            f"  {row['scenario'] + '/' + row['step']:<40}{str(row['value'])[:44]:<46}"
            f"{row['entity']:<10}{str(events):>9}  "
            f"{_flag(bool(covered['50'])):>5} {_flag(bool(covered['100'])):>6} "
            f"{_flag(bool(covered['None'])):>4} {str(rank):>6}  {_generator_line(row)}"
        )
    return lines


def _entity_asset_table(assets: Sequence[Mapping[str, Any]]) -> list[str]:
    if not assets:
        return ["  none"]
    lines = [f"  {'scenario/step':<40}{'asset':<46}{'kind':<10}{'events':>9} {'rank':>6}"]
    for row in assets:
        events = row["events"] if row["events"] is not None else "pending"
        rank = row["first_rank"] if row["first_rank"] is not None else "-"
        lines.append(
            f"  {row['scenario'] + '/' + row['step']:<40}{str(row['value'])[:44]:<46}"
            f"{row['entity']:<10}{str(events):>9} {str(rank):>6}"
        )
    return lines


def _entity_recall_lines(report: Mapping[str, Any]) -> list[str]:
    recall = report["recall"]
    scenarios = report["scenario_recall"]
    overall, scenario_overall = recall["overall"], scenarios["overall"]
    lines = [
        f"steps      top50 {overall['50']}/{recall['steps']}   "
        f"top100 {overall['100']}/{recall['steps']}   all {overall['None']}/{recall['steps']}   "
        f"notables that cost {report['notables']['cost']}",
        f"scenarios  top50 {scenario_overall['50']}/{scenarios['steps']}   "
        f"top100 {scenario_overall['100']}/{scenarios['steps']}   "
        f"all {scenario_overall['None']}/{scenarios['steps']}",
        f"  {'generator':<18}{'top50':>8}{'top100':>8}{'all':>8}",
    ]
    for name, counts in recall["by_generator"].items():
        lines.append(f"  {name:<18}{counts['50']:>8}{counts['100']:>8}{counts['None']:>8}")
    return lines


def _entity_relate_lines(report: Mapping[str, Any]) -> list[str]:
    relation = report.get("relate")
    if not isinstance(relation, Mapping):
        return []
    before, after = relation["before"], relation["after"]
    lines = [
        f"relate steps before top50 {before['overall']['50']}/{before['steps']} "
        f"all {before['overall']['None']}/{before['steps']}",
        f"relate steps after  top50 {after['overall']['50']}/{after['steps']} "
        f"all {after['overall']['None']}/{after['steps']}",
        f"relate cases {relation['cases']}  related notables {relation['related_notables']}  "
        f"first true case {relation['first_true_case_rank']}  "
        f"false cases above it {relation['false_cases_above_first_true']}",
    ]
    lines.extend(
        f"  case {row['rank'] + 1}: {row['case_id']}  events {row['events']}  "
        f"scenarios {', '.join(row['scenarios']) or '-'}"
        for row in relation["case_rows"]
    )
    return lines


def _render_entity(report: Mapping[str, Any]) -> str:
    lines = [
        *_entity_summary_lines(report),
        "",
        "ARTEFACTS (a step/scenario counts only through these)",
        *_entity_artefact_table(report["artefacts"]),
        "",
        "ASSETS (reported, never count on their own)",
        *_entity_asset_table(report["assets"]),
        "",
        f"QUIET steps (<= {QUIET_MAX_LINES} keyed events)",
    ]
    lines += _step_table(report["steps"], True) or ["  none"]
    lines += ["", f"LOUD steps (> {QUIET_MAX_LINES} keyed events)"]
    lines += _step_table(report["steps"], False) or ["  none"]
    lines += ["", *_entity_recall_lines(report)]
    relation_lines = _entity_relate_lines(report)
    if relation_lines:
        lines += ["", *relation_lines]
    lines += _judge_lines(report)
    lines += _cost_lines(report)
    lines += _honesty_lines(report)
    return "\n".join(lines)


def render(report: Mapping[str, Any]) -> str:
    if report.get("mode") == "entity":
        return _render_entity(report)
    lines = [*_summary_lines(report), "", f"QUIET steps (<= {QUIET_MAX_LINES} lines)"]
    lines += _step_table(report["steps"], True) or ["  none"]
    lines += ["", f"LOUD steps (> {QUIET_MAX_LINES} lines)"]
    lines += _step_table(report["steps"], False) or ["  none"]
    lines += ["", *_recall_lines(report)]
    relation_lines = _relate_lines(report)
    if relation_lines:
        lines += ["", *relation_lines]
    lines += _judge_lines(report)
    lines += _cost_lines(report)
    lines += _honesty_lines(report)
    return "\n".join(lines)


def score(
    out: Path,
    key_args: Sequence[str],
    *,
    logs: Path | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    targets = _targets(out)
    keys = _key_paths(key_args, [family for family, _directory in targets])
    return {
        "families": [
            _entity_family(family, directory, keys[family])
            if _keys_are_entity(keys[family])
            else _family(family, directory, keys[family], logs, year)
            for family, directory in targets
        ]
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="run dir, or the dir of families")
    parser.add_argument(
        "--keys",
        action="append",
        required=True,
        help="family=path to that family's keys.jsonl (repeat per family)",
    )
    parser.add_argument("--logs", type=Path, help="raw log tree holding the labelled lines")
    parser.add_argument("--year", type=int, help="year for a timestamp that carries none")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    started = time.monotonic()
    try:
        report = score(args.out, args.keys, logs=args.logs, year=args.year)
    except ScoreboardError as error:
        print(f"scoreboard: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=1, sort_keys=False))
    else:
        print(
            "\n\n".join(render(family) for family in report["families"])
            + f"\n\nscored in {time.monotonic() - started:.1f}s"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
