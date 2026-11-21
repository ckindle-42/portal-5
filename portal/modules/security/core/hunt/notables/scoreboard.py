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
import statistics
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from importlib import import_module
from pathlib import Path
from typing import Any

import duckdb

from .cards import CARD_KIND_CONSUMERS, card_consumers
from .generators import Notable as MergeNotable
from .knowledge import PROOF_INDEXES
from .merge import (
    DEFAULT_MERGE,
    DEFAULT_WEIGHTS,
    MEASURED_SOURCE,
    UNMEASURED_WEIGHT,
    marginal_weights,
    remerge_without,
)
from .receipt import read_json
from .relate import CASE_MIN_EVIDENCE, CASES_FILE, RELATE_FILE
from .run import GENERATORS, MERGE_PRIORITY, NOTABLES_FILE, SOURCES_FILE, card_from_dict

QUIET_MAX_LINES = 250  # statement §6: quiet steps are 1 to about 250 labelled lines
CUTS: tuple[int | None, ...] = (50, 100, None)
CASE_HEAD_LINES = 10  # a run can hold thousands of cases; the report prints the head
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

MODES_RULE = (
    "loose = the artefact may sit anywhere the notable speaks (what/basis/why, entity values, "
    "evidence queries and lines); strict = what/basis/why and entity values only, so an "
    "artefact seen only inside an evidence line does not count; a key value shared by several "
    "steps credits its first step only; keys tagged B/P/T report B+P beside T; a key marked "
    "credit=false is reported but never covers; a key with requires= covers only when the "
    "required same-step values are located too."
)

LINE_RULE = (
    "line mode applies the family rule to the keyed events each locator selects: a notable "
    "covers a keyed event when the event's source is the one its evidence query selects "
    "(source= matched case-insensitively; rotation-stripped sourcetype when the query names "
    "no path) and every literal TERM its evidence query names occurs in the event's raw text "
    "(first 1500 characters, as exported); a notable whose query names no TERM is attributed "
    "by its evidence window. A step is covered when one of its keyed events is."
)

REACH_RULE = (
    "a key is reachable when its value (NFC/NFD, casefolded) is a substring of a read store "
    "row (events raw/actor/action/object/query/host, behaviour row fields, misfit shape or "
    "example), a ledger values_extracted cell, an entity spine row, or an exact cell in a "
    "complete inventory list; a step is reachable when one of its creditable artefacts is. The "
    "ceiling is the reachable step count; recall of reachable is covered reachable steps over "
    "reachable steps, at the same cut."
)

INDEX_RULE = (
    "a labelled line's evidence is in the index when its source path is one the run's own "
    "estate map (| tstats count by sourcetype source, complete and uncapped) lists; a step "
    "whose labelled lines are all absent is reported as evidence_absent and leaves the step "
    "denominator, because no ranking can reach a line the index does not hold."
)

DIFF_RULE = (
    "the step diff names steps, never a ratio: lost and gained are the covered @50 sets of "
    "this run and the baseline run, reachable_lost and reachable_gained their reachable sets."
)

CAUSE_RULE = (
    "an audit-declared cause (keys row or --causes) is reported as written; without one the "
    "scoreboard derives it: covered = strict mode is about the artefact; instrument = it "
    "surfaces only when evidence lines count; censored = its locator source had a cut read and "
    "the artefact did not surface; not_surfaced = the run read it and surfaced no notable; "
    "unreached = no creditable artefact value is in a read store."
)
STORE_FILE = "behaviours.duckdb"
SPINE_FILE = "entities.duckdb"
LEDGER_FILE = "ledger.jsonl"
INVENTORY_FILE = "inventory.json"
STORE_COLUMNS = {
    "events": ("raw", "actor", "action", "object", "query", "host"),
    "behaviour": ("actor", "action", "object", "example_raw", "example_query"),
    "misfit": ("shape", "examples"),
}
STORE_TABLE = {"events": "events", "behaviour": "behaviours", "misfit": "misfits"}

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
    klass: str = ""
    credit: bool = True
    requires: tuple[str, ...] = ()
    cause: str = ""


@dataclass(frozen=True)
class KeyedEvent:
    """One exported event a key locator selects: the line-mode material for an entity key."""

    value: str
    time: float
    source: str
    raw: str


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
    klass: str = ""
    cause: str = ""

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
        return source.casefold() in {item.casefold() for item in claim.sources}
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
        credit = stored.get("credit")
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
                str(stored.get("class") or ""),
                True if credit is None else bool(credit),
                tuple(str(name) for name in stored.get("requires") or ()),
                str(stored.get("cause") or ""),
            )
        )
    if not rows:
        raise ScoreboardError(f"keys {path} hold no entries")
    return rows


def _read_keyed_events(path: Path, dataset: str) -> list[KeyedEvent]:
    if not path.is_file():
        raise ScoreboardError(f"keyed events not found: {path}")
    rows: list[KeyedEvent] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        stored = json.loads(raw)
        if str(stored.get("dataset") or "") != dataset:
            raise ScoreboardError(
                f"keyed events are for {stored.get('dataset')!r}, another dataset "
                f"than {dataset!r}: {path}"
            )
        rows.append(
            KeyedEvent(
                str(stored["value"]),
                float(stored["time"]),
                str(stored["source"]),
                str(stored["raw"]),
            )
        )
    if not rows:
        raise ScoreboardError(f"keyed events {path} hold no rows")
    return rows


def _fold(text: str) -> str:
    """NFC-normalized then casefolded text: the form entity values are matched in."""
    return unicodedata.normalize("NFC", text).casefold()


def _entity_pattern(value: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(_fold(value)) + r"(?!\w)")


def _haystack(row: Mapping[str, Any], strict: bool = False) -> str:
    """Everything a notable says, folded: the text entity keys are matched against.

    strict drops the evidence queries and lines, leaving what/basis/why and entity values.
    """
    parts = [str(row.get(name) or "") for name in ("what", "basis", "why")]
    for entity in row.get("entities") or ():
        if isinstance(entity, Mapping):
            parts.append(str(entity.get("value") or ""))
    if strict:
        return _fold("\n".join(parts))
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


def _mark(
    steps: Mapping[str, Step],
    labels: Sequence[str],
    notable: Notable,
    covered_by_rank: dict[int, set[str]] | None = None,
) -> None:
    notable.covered = True
    if covered_by_rank is not None:
        covered_by_rank.setdefault(notable.rank, set()).update(labels)
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
    covered_by_rank: dict[int, set[str]] | None = None,
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
                    _mark(steps, labels, notable, covered_by_rank)


def _coverage(
    steps: Mapping[str, Step],
    notables: Sequence[Notable],
    keys: Sequence[KeyLine],
    logs: Path,
    year: int,
    covered_by_rank: dict[int, set[str]] | None = None,
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
            _scan(path, lines, active, steps, year, covered_by_rank)


def _line_read_lines(directory: Path) -> set[str]:
    """Exact read lines from the behaviour sample, for the per-line families' ceiling."""
    store = directory / STORE_FILE
    if not store.is_file():
        return set()
    con = duckdb.connect(str(store), read_only=True)
    try:
        tables = {str(row[0]) for row in con.execute("SHOW TABLES").fetchall()}
        if "events" not in tables:
            return set()
        rows = con.execute("SELECT raw FROM events").fetchall()
    finally:
        con.close()
    return {str(row[0]).rstrip("\r\n") for row in rows if row[0] is not None}


def _line_reachability(
    keys: Sequence[KeyLine], logs: Path, read: set[str]
) -> tuple[dict[str, bool], int, int]:
    """Per step, whether one of its labelled lines was read verbatim; lines read of labelled."""
    reached: dict[str, bool] = {label: False for line in keys for label in line.labels}
    wanted: dict[tuple[str, str], dict[int, tuple[str, ...]]] = defaultdict(dict)
    for line in keys:
        wanted[(line.host, line.source)][line.number] = line.labels
    found = 0
    seen = 0
    for (host, source), lines in sorted(wanted.items()):
        path = logs / host / "logs" / source.lstrip("/")
        if not path.is_file():
            continue
        with path.open(encoding="utf-8", errors="replace") as handle:
            for number, raw in enumerate(handle, 1):
                labels = lines.get(number)
                if labels is None:
                    continue
                seen += 1
                if raw.rstrip("\r\n") in read:
                    found += 1
                    for label in labels:
                        reached[label] = True
    return reached, found, seen


def _index_paths(directory: Path) -> tuple[frozenset[str] | None, str]:
    """The source paths the run's own estate map counted in its index, or None when unknown."""
    path = directory / LEDGER_FILE
    if not path.is_file():
        return None, "the run wrote no ledger"
    paths: set[str] = set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if str(row.get("stage") or "") != "cards" or row.get("capped"):
            continue
        if "by sourcetype source" not in str(row.get("query") or ""):
            continue
        found = {
            str(cell) for cell in row.get("values_extracted") or () if str(cell).startswith("/")
        }
        if len(found) != int(row.get("rows") or 0):
            continue
        paths |= found
    if not paths:
        return None, "the run recorded no complete per-source index map"
    return frozenset(paths), f"ledger estate map, {len(paths)} source paths"


def _evidence_absent(keys: Sequence[KeyLine], index: frozenset[str]) -> dict[str, tuple[int, int]]:
    """Per step, how many of its labelled lines name a source the index does not hold."""
    counts: dict[str, tuple[int, int]] = {label: (0, 0) for line in keys for label in line.labels}
    for line in keys:
        for label in line.labels:
            gone, total = counts[label]
            counts[label] = (gone + (line.source not in index), total + 1)
    return counts


def _reach_recall(steps: Mapping[str, Step], reached: Mapping[str, bool]) -> dict[str, Any]:
    """Coverage restricted to steps whose evidence the run actually read."""
    reachable = [step for step in steps.values() if reached.get(step.label)]

    def block(selected: Sequence[Step]) -> dict[str, Any]:
        return {str(limit): _count(selected, lambda step: step.first_rank, limit) for limit in CUTS}

    return {
        "steps": len(steps),
        "reachable": len(reachable),
        "covered": block(reachable),
        "recall": {
            str(limit): round(block(reachable)[str(limit)] / len(reachable), 6)
            if reachable
            else None
            for limit in CUTS
        },
    }


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


def _ledger_cost(directory: Path) -> dict[str, Any]:
    reads = _read_ledger(directory)
    source_events: dict[str, int] = {}
    sources = read_json(directory / SOURCES_FILE)
    for card in sources.get("cards") or ():
        if not isinstance(card, Mapping):
            continue
        source_id = str(card.get("source_id") or "")
        facts = card.get("facts")
        if not isinstance(facts, Mapping):
            facts = {}
        source_events[source_id] = int(facts.get("events") or 0)
    total_events = sum(source_events.values())
    by_stage: dict[str, dict[str, Any]] = {}
    for row in reads:
        stage = str(row.get("stage") or "unknown")
        detail = by_stage.setdefault(stage, {"queries": 0, "events_read": 0, "censored": 0})
        detail["queries"] += 1
        detail["events_read"] += int(row.get("rows") or 0)
        detail["censored"] += bool(row.get("capped") or row.get("reason"))
    rows_read = sum(int(row.get("rows") or 0) for row in reads)
    return {
        "queries": len(reads),
        "events_read": rows_read,
        "events_available": total_events,
        "read_fraction": round(rows_read / total_events, 6) if total_events else None,
        "read_fraction_rule": "returned rows divided by indexed source events; overlapping reads count repeatedly",
        "censored_queries": sum(bool(row.get("capped") or row.get("reason")) for row in reads),
        "by_stage": by_stage,
    }


def _cost(progress: Mapping[str, Any], directory: Path) -> dict[str, Any]:
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
    reads = _ledger_cost(directory)
    for name, detail in rows.items():
        measured = reads["by_stage"].get(name, {})
        detail["searches"] = int(measured.get("queries") or 0)
        detail["events_read"] = int(measured.get("events_read") or 0)
        detail["censored_queries"] = int(measured.get("censored") or 0)
    return {
        "stages": rows,
        "seconds": round(sum(float(row["seconds"]) for row in rows.values()), 3),
        "model_requests": sum(int(row["model_requests"]) for row in rows.values()),
        "peak_memory_mb": progress.get("peak_memory_mb"),
        "search_requests": reads["queries"],
        "events_read": reads["events_read"],
        "read_fraction": reads["read_fraction"],
        "reads": reads,
    }


def _corpus_family(label: str, run_index: str, excluded: str) -> str:
    """A label naming a tuned `_v2` index is that index's corpus family, not another one."""
    try:
        plan = import_module("scripts.lab.splunk_setup.plan")
    except ImportError:  # no setup registry on this path: keep the label, keep the guard strict
        return label
    spec = getattr(plan, "TUNED_BY_TARGET", {}).get(run_index)
    if spec is None:
        return label
    names = {spec.key, spec.source_index, spec.target_index}
    names |= {name.removeprefix("hb_") for name in names}
    if label.removesuffix("_v2") not in names:
        return label
    shortened = bool(excluded) and spec.key.casefold().startswith(str(excluded).casefold())
    return str(excluded) if shortened else label


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
    family = _corpus_family(family, str(detail.get("run_index") or ""), str(excluded or ""))
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


def _median_rank(steps: Sequence[Step]) -> float | None:
    """The typical rank of the first notable covering a step: a cut-free sensitivity measure."""
    ranks = [step.first_rank for step in steps if step.first_rank is not None]
    return round(statistics.median(ranks), 1) if ranks else None


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
        "median_first_rank": _median_rank(steps),
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
        "class": step.klass,
        "first_rank": step.first_rank,
        "covered": {str(limit): _cut(step.first_rank, limit) for limit in CUTS},
        "by_generator": dict(sorted(step.by_generator.items(), key=lambda item: item[1])),
        "by_generator_covered": {
            name: {str(limit): _cut(step.by_generator.get(name), limit) for limit in CUTS}
            for name in RECALL_GENERATORS
        },
    }


def _line_ceiling(
    directory: Path, keys: Sequence[KeyLine], steps: Mapping[str, Step], logs: Path
) -> dict[str, Any]:
    reached, found, seen = _line_reachability(keys, logs, _line_read_lines(directory))
    index, mechanism = _index_paths(directory)
    absent = None if index is None else _evidence_absent(keys, index)
    present = (
        steps
        if absent is None
        else {label: step for label, step in steps.items() if absent[label][0] < absent[label][1]}
    )
    block = _reach_recall(present, reached)
    block.update(
        {
            "rule": REACH_RULE,
            "index_rule": INDEX_RULE,
            "index_map": mechanism,
            "keys_present": None
            if absent is None
            else {
                "lines": sum(total - gone for gone, total in absent.values()),
                "of": sum(total for _gone, total in absent.values()),
            },
            "steps_all": len(steps),
            "evidence_absent": None
            if absent is None
            else [
                {"step": label, "absent": gone, "lines": total}
                for label, (gone, total) in sorted(absent.items())
                if gone == total
            ],
            "lines_read": found,
            "labelled_lines": seen,
            "per_step": [
                {
                    "step": step.label,
                    "class": step.klass,
                    "cause": step.cause,
                    "reachable": bool(reached.get(step.label)),
                    "first_rank": step.first_rank,
                    "evidence_absent": None
                    if absent is None
                    else {"absent": absent[step.label][0], "lines": absent[step.label][1]},
                }
                for step in steps.values()
            ],
        }
    )
    return block


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
    covered_by_rank: dict[int, set[str]] = {}
    _coverage(steps, notables, keys, resolved, picked, covered_by_rank)
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
        "generators": _line_generator_table(rows, progress, steps, covered_by_rank),
        "ceiling": _line_ceiling(directory, keys, steps, resolved),
        "judge": _judge_block(notables, read_json(directory / JUDGE_CACHE)),
        "cost": _cost(progress, directory),
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


def _cases_payload(directory: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The S3 case payload: cases.json when the cases were built over the spine."""
    path = directory / CASES_FILE
    if path.is_file():
        stored = read_json(path)
        return (
            [dict(item) for item in stored.get("cases") or () if isinstance(item, Mapping)],
            dict(stored.get("receipt") or {}),
        )
    payload = read_json(directory / RELATE_FILE)
    return (
        [dict(item) for item in payload.get("cases") or () if isinstance(item, Mapping)],
        dict(payload.get("receipt") or {}),
    )


def _case_quality(
    cases: Sequence[Mapping[str, Any]],
    case_receipt: Mapping[str, Any],
    relate_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """The S3 case properties measured on the run's own case payload."""
    evidence = [len(case.get("evidence") or ()) for case in cases]
    pieces = [int(case.get("pieces") or 0) for case in cases]
    promotion = relate_receipt.get("promotion")
    promotion = promotion if isinstance(promotion, Mapping) else {}
    lifted = [item for item in promotion.get("ids") or () if isinstance(item, Mapping)]
    censored = case_receipt.get("censored")
    return {
        "cases": len(cases),
        "min_evidence": min(pieces) if pieces else 0,
        "evidence_rows": min(evidence) if evidence else 0,
        "two_evidence_violations": sum(1 for count in pieces if count < CASE_MIN_EVIDENCE),
        "unjudged_cases": sum(1 for case in cases if case.get("unjudged")),
        "coverage_complete": case_receipt.get("coverage_complete"),
        "uncapped_fraction": case_receipt.get("uncapped_fraction"),
        "censored": dict(censored) if isinstance(censored, Mapping) else {},
        "promoted": int(promotion.get("lifted") or 0),
        "promotion_judged_only": bool(promotion.get("judged_only")),
        "promoted_unjudged": sum(1 for item in lifted if item.get("unjudged")),
    }


def _case_claim_recall(
    cases: Sequence[Mapping[str, Any]],
    ordered: Sequence[Mapping[str, Any]],
    keys: Sequence[KeyLine],
    hits: Mapping[int, Collection[str]],
) -> dict[str, Any]:
    """Per labelled step: a case holds it only when one of its own members' claims covers it."""
    positions: dict[str, int] = {}
    for position, row in enumerate(ordered):
        notable_id = str(row.get("notable_id") or "")
        if notable_id:
            positions.setdefault(notable_id, position)
    covered: dict[str, set[str]] = {str(limit): set() for limit in CUTS}
    rows: list[dict[str, Any]] = []
    for rank, case in enumerate(cases):
        ids = [
            str(item)
            for name in ("seed_notables", "related_notables")
            for item in case.get(name) or ()
        ]
        found = sorted({label for item in ids for label in hits.get(positions.get(item, -1), ())})
        for limit in CUTS:
            if _cut(rank, limit):
                covered[str(limit)].update(found)
        if found:
            rows.append({"rank": rank, "labels": found})
    total = len({label for line in keys for label in line.labels})
    return {
        "scenarios": total,
        "overall": {key: len(value) for key, value in covered.items()},
        "recall": {
            key: round(len(value) / total, 6) if total else None for key, value in covered.items()
        },
        "dataset_covered": {key: bool(value) for key, value in covered.items()},
        "cases": rows,
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
    payload = read_json(path) if path.is_file() else {}
    cases, case_receipt = _cases_payload(directory)
    if not payload and not cases:
        return None
    related = [item for item in payload.get("notables") or () if isinstance(item, dict)]
    after_rows = _with_related(rows, related)
    after_steps = _steps(keys)
    hits: dict[int, set[str]] = {}
    _coverage(after_steps, _ranked_notables(after_rows), keys, logs, year, hits)
    purity = _case_purity(cases, keys, logs)
    return {
        "related_notables": len(related),
        "cases": len(cases),
        "before": _recall(before_steps),
        "after": _recall(
            sorted(after_steps.values(), key=lambda step: (not step.quiet, step.lines, step.label))
        ),
        "case_purity": purity,
        "case_member_recall": _case_claim_recall(cases, after_rows, keys, hits),
        "case_quality": _case_quality(cases, case_receipt, payload.get("receipt") or {}),
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


def _entity_ownership(artefacts: Sequence[EntityKey]) -> dict[str, str]:
    """value -> the first step (keys order) citing it; later steps share that key."""
    owners: dict[str, str] = {}
    for key in artefacts:
        owners.setdefault(key.value, f"{key.scenario}/{key.step}")
    return owners


def _fold_forms(value: str) -> tuple[str, ...]:
    """The value in both Unicode normal forms, so an index that stores NFD still matches."""
    forms = {value, unicodedata.normalize("NFC", value), unicodedata.normalize("NFD", value)}
    return tuple(sorted(form for form in forms if form))


def _table_hits(
    con: duckdb.DuckDBPyConnection, table: str, columns: Sequence[str], forms: Sequence[str]
) -> int:
    clauses: list[str] = []
    params: list[str] = []
    for form in forms:
        for column in columns:
            clauses.append(f"contains(lower({column}), lower(?))")
            params.append(form)
    if not clauses:
        return 0
    row = con.execute(
        f"SELECT count(*) FROM {table} WHERE " + " OR ".join(clauses), params
    ).fetchone()
    return int(row[0]) if row else 0


def _inventory_cells(directory: Path) -> set[str]:
    payload = read_json(directory / INVENTORY_FILE)
    cells: set[str] = set()
    for item in payload.get("fields") or ():
        if isinstance(item, Mapping) and item.get("status") == "complete":
            for value in item.get("values") or ():
                if isinstance(value, Mapping):
                    cells.update(_fold_forms(str(value.get("value") or "")))
    for joint in payload.get("joints") or ():
        if not isinstance(joint, Mapping) or joint.get("status") != "complete":
            continue
        for row in joint.get("rows") or ():
            if isinstance(row, Mapping):
                for value in (row.get("values") or {}).values():
                    cells.update(_fold_forms(str(value)))
    for flow in payload.get("flows") or ():
        if isinstance(flow, Mapping) and flow.get("status") == "complete":
            cells.update(_fold_forms(str(flow.get("value") or "")))
    return {cell for cell in cells if cell}


def _read_ledger(directory: Path) -> list[dict[str, Any]]:
    path = directory / "ledger.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except ValueError as exc:
            raise ScoreboardError(f"{path}:{number} is not valid JSON") from exc
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _ledger_has_value(rows: Sequence[Mapping[str, Any]], value: str) -> bool:
    forms = tuple(_fold(form) for form in _fold_forms(value))
    return any(
        form in _fold(str(cell))
        for row in rows
        for cell in row.get("values_extracted") or ()
        for form in forms
    )


def _sql_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _spine_hits(directory: Path, values: Sequence[str]) -> set[str]:
    path = directory / SPINE_FILE
    if not path.is_file():
        return set()
    found: set[str] = set()
    con = duckdb.connect(str(path), read_only=True)
    try:
        tables = [
            str(row[0])
            for row in con.execute("SHOW TABLES").fetchall()
            if any(word in str(row[0]).casefold() for word in ("spine", "entity", "episode"))
        ]
        for table in tables:
            table_name = _sql_identifier(table)
            columns = [str(row[0]) for row in con.execute(f"DESCRIBE {table_name}").fetchall()]
            if not columns:
                continue
            predicates = [
                f"contains(lower(CAST({_sql_identifier(column)} AS VARCHAR)), lower(?))"
                for column in columns
            ]
            for value in dict.fromkeys(values):
                params = [form for form in _fold_forms(value) for _column in columns]
                clauses = [predicate for form in _fold_forms(value) for predicate in predicates]
                row = con.execute(
                    f"SELECT count(*) FROM {table_name} WHERE " + " OR ".join(clauses), params
                ).fetchone()
                if row and int(row[0]):
                    found.add(value)
    finally:
        con.close()
    return found


def _query_filter_value(query: str, field: str) -> str:
    found = re.search(rf'(?i)(?<![\w]){field}\s*=\s*(?:"([^"]*)"|([^\s|]+))', query)
    return str(found.group(1) or found.group(2) or "") if found else ""


def _same_locator_source(key: EntityKey, read: Mapping[str, Any]) -> bool:
    index = _query_filter_value(key.locator, "index") or key.dataset
    source = _query_filter_value(key.locator, "sourcetype") or _query_filter_value(
        key.locator, "source"
    )
    source_id = str(read.get("source_id") or "")
    if source:
        return source_id.casefold() == f"{index}:{source}".casefold()
    query_index = _query_filter_value(str(read.get("query") or ""), "index")
    return query_index.casefold() == index.casefold() or source_id.casefold().startswith(
        f"{index}:".casefold()
    )


def _censored_steps(
    artefacts: Sequence[EntityKey],
    owners: Mapping[str, str],
    stores: Mapping[str, tuple[str, ...]],
    ledger: Sequence[Mapping[str, Any]],
) -> dict[str, bool]:
    censored: dict[str, bool] = {}
    for key in artefacts:
        if not key.credit or owners.get(key.value) != f"{key.scenario}/{key.step}":
            continue
        if stores.get(key.value):
            continue
        relevant = [row for row in ledger if _same_locator_source(key, row)]
        if any(row.get("capped") or row.get("reason") for row in relevant):
            censored[f"{key.scenario}/{key.step}"] = True
    return censored


def _reachable_stores(directory: Path, values: Sequence[str]) -> dict[str, tuple[str, ...]]:
    """For each key value, the instrument stores that recorded the value."""
    found: dict[str, list[str]] = {value: [] for value in values}
    ledger = _read_ledger(directory)
    spine = _spine_hits(directory, values)
    store = directory / STORE_FILE
    if store.is_file():
        con = duckdb.connect(str(store), read_only=True)
        try:
            tables = {str(row[0]) for row in con.execute("SHOW TABLES").fetchall()}
            for value in dict.fromkeys(values):
                forms = _fold_forms(value)
                for label, columns in STORE_COLUMNS.items():
                    if STORE_TABLE[label] not in tables:
                        continue
                    if _table_hits(con, STORE_TABLE[label], columns, forms):
                        found[value].append(label)
        finally:
            con.close()
    cells = _inventory_cells(directory)
    for value in dict.fromkeys(values):
        if any(form in cells for form in _fold_forms(value)):
            found[value].append("inventory")
        if value in spine:
            found[value].append("spine")
        if _ledger_has_value(ledger, value):
            found[value].append("ledger")
    return {value: tuple(stores) for value, stores in found.items()}


def _entity_reachability(
    artefacts: Sequence[EntityKey], owners: Mapping[str, str], stores: Mapping[str, tuple[str, ...]]
) -> dict[str, dict[str, Any]]:
    """Per owning step: the creditable artefacts that are in a read store."""
    reached: dict[str, dict[str, Any]] = {}
    for key in artefacts:
        if not key.credit or owners.get(key.value) != f"{key.scenario}/{key.step}":
            continue
        label = f"{key.scenario}/{key.step}"
        entry = reached.setdefault(label, {"reachable": False, "stores": set(), "values": []})
        if stores.get(key.value):
            entry["reachable"] = True
            entry["stores"].update(stores[key.value])
            entry["values"].append(key.value)
    return {
        label: {
            "reachable": bool(entry["reachable"]),
            "stores": sorted(entry["stores"]),
            "values": entry["values"],
        }
        for label, entry in reached.items()
    }


def _entity_groups(
    artefacts: Sequence[EntityKey], owners: Mapping[str, str]
) -> tuple[dict[str, Step], dict[str, Step]]:
    """Steps and scenarios the keys declare: shared values credit the owner's step only,
    and a step whose every key holds no credit stays in the denominator at zero lines."""
    steps: dict[str, Step] = {}
    scenarios: dict[str, Step] = {}
    for key in artefacts:
        label = f"{key.scenario}/{key.step}"
        if owners.get(key.value) != label:
            continue
        step = steps.setdefault(label, Step(label, klass=key.klass))
        if key.klass and not step.klass:
            step.klass = key.klass
        if key.cause and not step.cause:
            step.cause = key.cause
        if not key.credit:
            continue
        step.lines += key.audit_count or 0
        scenario = scenarios.setdefault(key.scenario, Step(key.scenario))
        scenario.lines += key.audit_count or 0
    return steps, scenarios


def _entity_order(groups: Mapping[str, Step]) -> list[Step]:
    return sorted(groups.values(), key=lambda step: (not step.quiet, step.lines, step.label))


def _mark_at(
    group: Mapping[str, Step], label: str, rank: int, generators: Mapping[str, int]
) -> None:
    step = group[label]
    if step.first_rank is None or rank < step.first_rank:
        step.first_rank = rank
    for name, gen_rank in generators.items():
        known = step.by_generator.get(name)
        if known is None or gen_rank < known:
            step.by_generator[name] = gen_rank


def _mark_hit(step: Step, rank: int, generator: str) -> None:
    if step.first_rank is None or rank < step.first_rank:
        step.first_rank = rank
    known = step.by_generator.get(generator)
    if known is None or rank < known:
        step.by_generator[generator] = rank


def _entity_pass(
    artefacts: Sequence[EntityKey],
    rows: Sequence[dict[str, Any]],
    hays: Sequence[str],
    owners: Mapping[str, str],
    cover: bool = True,
) -> tuple[list[Notable], list[int | None], list[dict[str, int]], dict[str, Step], dict[str, Step]]:
    """One ranked pass: first notable locating each artefact, marking steps and scenarios.

    A located artefact credits its step only when it holds credit, owns its value, and every
    value it requires is located too (at any rank).
    """
    notables = _ranked_notables(rows)
    steps, scenarios = _entity_groups(artefacts, owners)
    patterns = [_entity_pattern(key.value) for key in artefacts]
    firsts: list[int | None] = [None] * len(artefacts)
    by_generator: list[dict[str, int]] = [{} for _ in artefacts]
    located: set[str] = set()
    for notable, hay in zip(notables, hays, strict=True):
        for position, pattern in enumerate(patterns):
            if not pattern.search(hay):
                continue
            key = artefacts[position]
            located.add(key.value)
            if firsts[position] is None:
                firsts[position] = notable.rank
            by_generator[position].setdefault(notable.generator, notable.rank)
            if cover:
                notable.covered = True
    for position, key in enumerate(artefacts):
        rank = firsts[position]
        if rank is None or not key.credit:
            continue
        if owners.get(key.value) != f"{key.scenario}/{key.step}":
            continue
        if any(name not in located for name in key.requires):
            continue
        _mark_at(steps, f"{key.scenario}/{key.step}", rank, by_generator[position])
        _mark_at(scenarios, key.scenario, rank, by_generator[position])
    return notables, firsts, by_generator, steps, scenarios


def _artefact_rows(
    artefacts: Sequence[EntityKey],
    firsts: Sequence[int | None],
    generators: Sequence[dict[str, int]],
    strict_firsts: Sequence[int | None],
    owners: Mapping[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for position, key in enumerate(artefacts):
        owner = owners.get(key.value)
        counts = bool(key.credit) and owner == f"{key.scenario}/{key.step}"
        rows.append(
            {
                "scenario": key.scenario,
                "step": key.step,
                "value": key.value,
                "entity": key.entity,
                "events": key.audit_count,
                "admitted": key.admitted,
                "class": key.klass,
                "credit": key.credit,
                "cause": key.cause,
                "requires": list(key.requires),
                "shared_step": None if owner == f"{key.scenario}/{key.step}" else owner,
                "first_rank": firsts[position],
                "first_rank_strict": strict_firsts[position],
                "covered": {str(limit): counts and _cut(firsts[position], limit) for limit in CUTS},
                "by_generator": dict(
                    sorted(generators[position].items(), key=lambda item: item[1])
                ),
            }
        )
    return rows


def _class_recall(steps: Sequence[Step]) -> dict[str, Any]:
    """Recall over the keys' B/P/T classes: B+P (the behavioural set) beside T (trivia)."""

    def block(selected: list[Step]) -> dict[str, Any]:
        return {
            "steps": len(selected),
            "covered": {
                str(limit): _count(selected, lambda step: step.first_rank, limit) for limit in CUTS
            },
        }

    out: dict[str, Any] = {}
    for klass in ("B", "P", "T"):
        chosen = [step for step in steps if step.klass == klass]
        if chosen:
            out[klass] = block(chosen)
    both = [step for step in steps if step.klass in ("B", "P")]
    if both:
        out["B+P"] = block(both)
    return out


def _cause_row(
    step: Step,
    reachable: bool,
    strict_steps: Mapping[str, Step],
    line_steps: Mapping[str, Step] | None,
    censored: bool = False,
) -> tuple[str, str]:
    """The audit's cause when declared, else one derived from what the run actually did."""
    if step.cause:
        return step.cause, "audit"
    strict = strict_steps.get(step.label)
    strict_rank = strict.first_rank if strict is not None else None
    line = (line_steps or {}).get(step.label)
    line_rank = line.first_rank if line is not None else None
    if _cut(strict_rank, 50):
        return "covered", "derived"
    if _cut(line_rank, 50) or _cut(step.first_rank, 50):
        return "instrument", "derived"
    if censored:
        return "censored", "derived"
    if reachable:
        return "not_surfaced", "derived"
    return "unreached", "derived"


def _reach_block(
    steps: Sequence[Step], reached: Mapping[str, Any], rank_of: Callable[[str], int | None]
) -> dict[str, Any]:
    reachable = [step for step in steps if (reached.get(step.label) or {}).get("reachable")]
    ranks = [rank_of(step.label) for step in reachable]
    covered_ranks = [rank for rank in ranks if rank is not None]
    return {
        "steps": len(steps),
        "reachable": len(reachable),
        "covered": {
            str(limit): _count(reachable, lambda step: rank_of(step.label), limit) for limit in CUTS
        },
        "median_first_rank": round(statistics.median(covered_ranks), 1) if covered_ranks else None,
        "recall": {
            str(limit): round(
                _count(reachable, lambda step: rank_of(step.label), limit) / len(reachable), 6
            )
            if reachable
            else None
            for limit in CUTS
        },
    }


def _entity_ceiling(
    steps: Sequence[Step],
    strict_steps: Mapping[str, Step],
    reached: Mapping[str, Any],
    stores: Mapping[str, tuple[str, ...]],
    artefacts: Sequence[EntityKey],
    owners: Mapping[str, str],
    line_steps: Mapping[str, Step] | None,
    censored: Mapping[str, bool],
) -> dict[str, Any]:
    loose = _reach_block(steps, reached, lambda label: _rank(steps, label))
    strict = _reach_block(steps, reached, lambda label: _rank_of(strict_steps, label))
    line = (
        None
        if line_steps is None
        else _reach_block(
            list(line_steps.values()), reached, lambda label: _rank_of(line_steps, label)
        )
    )
    by_class: dict[str, dict[str, Any]] = {}
    for klass in ("B", "P", "T"):
        chosen = [step for step in steps if step.klass == klass]
        if chosen:
            block = _reach_block(chosen, reached, lambda label: _rank(steps, label))
            by_class[klass] = {"steps": len(chosen), "reachable": block["reachable"]}
    behavioural = [step for step in steps if step.klass in ("B", "P")]
    if behavioural:
        by_class["B+P"] = {
            "steps": len(behavioural),
            "reachable": sum(
                1 for step in behavioural if (reached.get(step.label) or {}).get("reachable")
            ),
        }
    per_step = []
    for step in steps:
        entry = reached.get(step.label) or {}
        was_censored = bool(censored.get(step.label))
        cause, source = _cause_row(
            step, bool(entry.get("reachable")), strict_steps, line_steps, was_censored
        )
        per_step.append(
            {
                "step": step.label,
                "class": step.klass,
                "cause": cause,
                "cause_source": source,
                "reachable": bool(entry.get("reachable")),
                "read_censored": was_censored,
                "stores": list(entry.get("stores") or ()),
                "values": list(entry.get("values") or ()),
                "first_rank": step.first_rank,
            }
        )
    store_counts = Counter(store for value in stores.values() for store in value)
    return {
        "rule": REACH_RULE,
        "cause_rule": CAUSE_RULE,
        "keys": sum(
            1
            for key in artefacts
            if key.credit and owners.get(key.value) == f"{key.scenario}/{key.step}"
        ),
        "keys_reachable": sum(
            1
            for key in artefacts
            if key.credit
            and owners.get(key.value) == f"{key.scenario}/{key.step}"
            and stores.get(key.value)
        ),
        "stores": dict(sorted(store_counts.items())),
        "loose": loose,
        "strict": strict,
        "line": line,
        "by_class": by_class,
        "per_step": per_step,
    }


def _rank(steps: Sequence[Step], label: str) -> int | None:
    for step in steps:
        if step.label == label:
            return step.first_rank
    return None


def _rank_of(steps: Mapping[str, Step], label: str) -> int | None:
    step = steps.get(label)
    return step.first_rank if step is not None else None


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


def _case_hypothesis_rows(
    cases: Sequence[Mapping[str, Any]],
    artefacts: Sequence[EntityKey],
    owners: Mapping[str, str],
    rows: Sequence[Mapping[str, Any]],
    related: Sequence[Mapping[str, Any]],
    classes: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    patterns = [
        (key, _entity_pattern(key.value))
        for key in artefacts
        if key.credit
        and owners.get(key.value) == f"{key.scenario}/{key.step}"
        and (not classes or key.klass in classes)
    ]
    members = {
        str(row.get("notable_id") or ""): row for row in (*rows, *related) if row.get("notable_id")
    }
    found_rows: list[dict[str, Any]] = []
    for rank, case in enumerate(cases):
        ids = [
            str(item)
            for name in ("seed_notables", "related_notables")
            for item in case.get(name) or ()
        ]
        text = "\n".join(
            _haystack(members[item], strict=True)
            for item in ids
            if item in members and members[item].get("generator") != "relate"
        )
        matched = sorted(
            {(key.scenario, key.value) for key, pattern in patterns if pattern.search(text)}
        )
        found_rows.append(
            {
                "rank": rank,
                "case_id": str(case.get("case_id") or ""),
                "members": ids,
                "artefacts": [
                    {"scenario": scenario, "value": value} for scenario, value in matched
                ],
                "scenarios": sorted({scenario for scenario, _value in matched}),
            }
        )
    return found_rows


def _case_recall(
    cases: Sequence[Mapping[str, Any]],
    artefacts: Sequence[EntityKey],
    owners: Mapping[str, str],
    rows: Sequence[Mapping[str, Any]],
    related: Sequence[Mapping[str, Any]],
    classes: tuple[str, ...] = (),
) -> dict[str, Any]:
    scenarios = {
        key.scenario
        for key in artefacts
        if key.credit
        and owners.get(key.value) == f"{key.scenario}/{key.step}"
        and (not classes or key.klass in classes)
    }
    case_rows = _case_hypothesis_rows(cases, artefacts, owners, rows, related, classes)
    overall: dict[str, int] = {}
    recall: dict[str, float | None] = {}
    for limit in CUTS:
        label = str(limit)
        covered = {
            scenario
            for row in case_rows
            if _cut(int(row["rank"]), limit)
            for scenario in row["scenarios"]
        }
        overall[label] = len(covered)
        recall[label] = round(len(covered) / len(scenarios), 6) if scenarios else None
    return {
        "scenarios": len(scenarios),
        "overall": overall,
        "recall": recall,
        "cases": case_rows,
    }


def _entity_line_mode(
    artefacts: Sequence[EntityKey],
    owners: Mapping[str, str],
    events: Sequence[KeyedEvent],
    rows: Sequence[dict[str, Any]],
    keep: dict[str, Step] | None = None,
) -> dict[str, Any]:
    """The family rule over the keyed events: which notables' queries select them."""
    by_value: dict[str, EntityKey] = {}
    for key in artefacts:
        by_value.setdefault(key.value, key)  # the owner row: same order as _entity_ownership
    creditable = {
        key.value
        for key in artefacts
        if key.credit and owners.get(key.value) == f"{key.scenario}/{key.step}"
    }
    steps: dict[str, Step] = {}
    folded: list[tuple[str, KeyedEvent, str]] = []
    for event in events:
        owner: EntityKey | None = by_value.get(event.value)
        if owner is None or event.value not in creditable:
            continue
        if any(by_value.get(name) is None or name not in creditable for name in owner.requires):
            continue
        label = f"{owner.scenario}/{owner.step}"
        step = steps.setdefault(label, Step(label, klass=owner.klass))
        if owner.klass and not step.klass:
            step.klass = owner.klass
        step.lines += 1
        folded.append((label, event, event.raw.casefold()))
    by_source: defaultdict[str, list[tuple[str, KeyedEvent, str]]] = defaultdict(list)
    by_stem: defaultdict[str, list[tuple[str, KeyedEvent, str]]] = defaultdict(list)
    for item in folded:
        by_source[item[1].source.casefold()].append(item)
        by_stem[_stem(item[1].source)].append(item)
    for notable in _ranked_notables(rows):
        claim = notable.claim
        if claim.sources:
            candidates = [
                item for source in claim.sources for item in by_source.get(source.casefold(), ())
            ]
        else:
            candidates = [item for name in claim.names for item in by_stem.get(name, ())]
        for label, event, text in candidates:
            if _covers(claim, text, event.time):
                _mark_hit(steps[label], notable.rank, notable.generator)
    ordered = sorted(steps.values(), key=lambda step: (not step.quiet, step.lines, step.label))
    if keep is not None:
        keep.update(steps)
    return {
        "rule": LINE_RULE,
        "events": len(folded),
        "steps": [_step_row(step) for step in ordered],
        "recall": _recall(ordered),
        "class_recall": _class_recall(ordered),
    }


def _merge_candidate(row: Mapping[str, Any]) -> MergeNotable:
    measure = row.get("measure")
    measure = measure if isinstance(measure, Mapping) else {}
    counts = row.get("counts")
    counts = counts if isinstance(counts, Mapping) else {}
    entities = tuple(
        (str(item.get("role") or ""), str(item.get("value") or ""))
        for item in row.get("entities") or ()
        if isinstance(item, Mapping)
    )
    evidence = tuple(item for item in row.get("evidence") or () if isinstance(item, Mapping))
    return MergeNotable(
        str(row.get("generator") or ""),
        str(row.get("basis") or ""),
        str(row.get("what") or ""),
        entities,
        str(row.get("source_id") or ""),
        _float_value(row.get("first_seen")),
        _float_value(row.get("last_seen")),
        counts,
        str(measure.get("name") or ""),
        _float_value(measure.get("value")),
        str(row.get("why") or ""),
        evidence,
        str(row.get("content_key") or row.get("notable_id") or ""),
        tuple(item for item in row.get("nearest_known") or () if isinstance(item, Mapping)),
        None,
    )


def _float_value(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _remerge_without(
    rows: Sequence[dict[str, Any]], generator: str, receipt: Mapping[str, Any]
) -> list[dict[str, Any]]:
    candidates: list[MergeNotable] = []
    originals: dict[int, dict[str, Any]] = {}
    for row in rows:
        candidate = _merge_candidate(row)
        candidates.append(candidate)
        originals[id(candidate)] = row
    priority = receipt.get("priority")
    priority = (
        tuple(str(item) for item in priority) if isinstance(priority, list) else MERGE_PRIORITY
    )
    method = str(receipt.get("method") or DEFAULT_MERGE)
    weights = receipt.get("weights")
    weights = weights if isinstance(weights, Mapping) else None
    merged = remerge_without(candidates, priority, method, weights, generator)
    return [originals[id(candidate)] for candidate in merged]


def _head_composition(rows: Sequence[dict[str, Any]]) -> Counter[str]:
    """How many of the merged head's first 50 slots each generator holds."""
    return Counter(str(row.get("generator") or "") for row in rows[:50])


def _used_weight(used: Mapping[str, Any], name: str) -> int | None:
    value = used.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _line_generator_table(
    rows: Sequence[dict[str, Any]],
    progress: Mapping[str, Any],
    steps: Mapping[str, Step],
    covered_by_rank: Mapping[int, set[str]],
) -> dict[str, dict[str, Any]]:
    stages = progress.get("stages")
    stages = stages if isinstance(stages, Mapping) else {}
    notables_stage = stages.get("notables")
    notables_stage = notables_stage if isinstance(notables_stage, Mapping) else {}
    relate_stage = stages.get("relate")
    relate_stage = relate_stage if isinstance(relate_stage, Mapping) else {}
    merge_receipt = notables_stage.get("merge")
    merge_receipt = merge_receipt if isinstance(merge_receipt, Mapping) else {}
    used = merge_receipt.get("weights")
    used = used if isinstance(used, Mapping) else {}
    head = _head_composition(rows)
    names = set(RECALL_GENERATORS) | {str(row.get("generator") or "") for row in rows}
    kept_counts = Counter(str(row.get("generator") or "") for row in rows)
    with50 = {step.label for step in steps.values() if _cut(step.first_rank, 50)}
    with100 = {step.label for step in steps.values() if _cut(step.first_rank, 100)}
    attribution: Counter[str] = Counter()
    for step in steps.values():
        if step.label in with50 and step.by_generator:
            name = min(step.by_generator.items(), key=lambda item: (item[1], item[0]))[0]
            attribution[name] += 1
    original_ranks = {id(row): rank for rank, row in enumerate(rows)}
    result: dict[str, dict[str, Any]] = {}
    for name in sorted(item for item in names if item):
        detail = notables_stage.get(name)
        detail = detail if isinstance(detail, Mapping) else {}
        existed = (
            int(relate_stage.get("related_events") or 0)
            if name == "relate"
            else int(detail.get("existed") or 0)
        )
        kept = int(detail["kept"]) if detail.get("kept") is not None else kept_counts[name]
        without = _remerge_without(rows, name, merge_receipt)
        without_first: dict[str, int] = {}
        for rank, row in enumerate(without):
            old_rank = original_ranks[id(row)]
            for label in covered_by_rank.get(old_rank, ()):
                without_first.setdefault(label, rank)
        without50 = {label for label, rank in without_first.items() if _cut(rank, 50)}
        without100 = {label for label, rank in without_first.items() if _cut(rank, 100)}
        marginal50 = len(with50 - without50)
        marginal100 = len(with100 - without100)
        result[name] = {
            "candidates": existed,
            "kept": kept,
            "head@50": head[name],
            "attribution@50": {
                "steps": attribution[name],
                "share": round(attribution[name] / len(with50), 6) if with50 else None,
            },
            "marginal@50": marginal50,
            "marginal@100": marginal100,
            "merge_weight": max(UNMEASURED_WEIGHT, marginal50),
            "used_weight": _used_weight(used, name),
        }
    return result


def _entity_metrics(
    rows: Sequence[dict[str, Any]],
    artefacts: Sequence[EntityKey],
    owners: Mapping[str, str],
    cases: Sequence[Mapping[str, Any]],
    related: Sequence[Mapping[str, Any]],
    events: Sequence[KeyedEvent] | None,
) -> dict[str, Any]:
    hays = [_haystack(row) for row in rows]
    strict_hays = [
        "" if row.get("generator") == "relate" else _haystack(row, strict=True) for row in rows
    ]
    notables, _firsts, _by_generator, steps, scenarios = _entity_pass(artefacts, rows, hays, owners)
    _strict_notables, _strict_firsts, _strict_generators, strict_steps, strict_scenarios = (
        _entity_pass(artefacts, rows, strict_hays, owners, cover=False)
    )
    ordered = _entity_order(steps)
    line = None if events is None else _entity_line_mode(artefacts, owners, events, rows)
    return {
        "notables": {"total": len(notables), "covering": sum(row.covered for row in notables)},
        "recall": _recall(ordered),
        "scenario_recall": _recall(_entity_order(scenarios)),
        "strict_recall": _recall(_entity_order(strict_steps)),
        "strict_scenario_recall": _recall(_entity_order(strict_scenarios)),
        "class_recall": _class_recall(ordered),
        "line_mode": line,
        "case_recall": _case_recall(cases, artefacts, owners, rows, related),
    }


def _generator_table(
    rows: Sequence[dict[str, Any]],
    progress: Mapping[str, Any],
    artefacts: Sequence[EntityKey],
    owners: Mapping[str, str],
    strict_steps: Mapping[str, Step],
) -> dict[str, dict[str, Any]]:
    stages = progress.get("stages")
    stages = stages if isinstance(stages, Mapping) else {}
    notables_stage = stages.get("notables")
    notables_stage = notables_stage if isinstance(notables_stage, Mapping) else {}
    merge_receipt = notables_stage.get("merge")
    merge_receipt = merge_receipt if isinstance(merge_receipt, Mapping) else {}
    used = merge_receipt.get("weights")
    used = used if isinstance(used, Mapping) else {}
    head = _head_composition(rows)
    names = set(RECALL_GENERATORS) | {str(row.get("generator") or "") for row in rows}
    kept_counts = Counter(str(row.get("generator") or "") for row in rows)
    covered = {step.label for step in strict_steps.values() if _cut(step.first_rank, 50)}
    attribution: Counter[str] = Counter()
    for step in strict_steps.values():
        if step.label not in covered or not step.by_generator:
            continue
        name = min(step.by_generator.items(), key=lambda item: (item[1], item[0]))[0]
        attribution[name] += 1
    result: dict[str, dict[str, Any]] = {}
    for name in sorted(item for item in names if item):
        detail = notables_stage.get(name)
        detail = detail if isinstance(detail, Mapping) else {}
        existed = int(detail.get("existed") or 0)
        kept = int(detail["kept"]) if detail.get("kept") is not None else kept_counts[name]
        without = _remerge_without(rows, name, merge_receipt)
        without_hays = [
            "" if row.get("generator") == "relate" else _haystack(row, strict=True)
            for row in without
        ]
        _ns, _fs, _gs, without_steps, _sc = _entity_pass(
            artefacts, without, without_hays, owners, cover=False
        )
        without50 = {step.label for step in without_steps.values() if _cut(step.first_rank, 50)}
        without100 = {step.label for step in without_steps.values() if _cut(step.first_rank, 100)}
        with100 = {step.label for step in strict_steps.values() if _cut(step.first_rank, 100)}
        marginal50 = len(covered - without50)
        marginal100 = len(with100 - without100)
        result[name] = {
            "candidates": existed,
            "kept": kept,
            "head@50": head[name],
            "attribution@50": {
                "steps": attribution[name],
                "share": round(attribution[name] / len(covered), 6) if covered else None,
            },
            "marginal@50": marginal50,
            "marginal@100": marginal100,
            "merge_weight": max(UNMEASURED_WEIGHT, marginal50),
            "used_weight": _used_weight(used, name),
        }
    return result


def _promotion_ids(payload: Mapping[str, Any]) -> set[str]:
    receipt = payload.get("receipt")
    promotion = receipt.get("promotion") if isinstance(receipt, Mapping) else None
    rows = promotion.get("ids") if isinstance(promotion, Mapping) else ()
    return {
        str(row.get("notable_id") or "")
        for row in rows or ()
        if isinstance(row, Mapping) and row.get("notable_id")
    }


def _promotion_effect(
    rows: Sequence[dict[str, Any]],
    without_promotions: Sequence[dict[str, Any]],
    promoted: set[str],
    artefacts: Sequence[EntityKey],
    owners: Mapping[str, str],
    cases: Sequence[Mapping[str, Any]],
    related: Sequence[Mapping[str, Any]],
    without_related: Sequence[Mapping[str, Any]],
    events: Sequence[KeyedEvent] | None,
) -> dict[str, Any]:
    return {
        "promoted": len(promoted),
        "with": _entity_metrics(rows, artefacts, owners, cases, related, events),
        "without": _entity_metrics(
            without_promotions, artefacts, owners, cases, without_related, events
        ),
    }


def _entity_relation(
    directory: Path,
    rows: Sequence[dict[str, Any]],
    artefacts: Sequence[EntityKey],
    before_steps: Mapping[str, Step],
    before_scenarios: Mapping[str, Step],
    owners: Mapping[str, str],
) -> dict[str, Any] | None:
    path = directory / RELATE_FILE
    payload = read_json(path) if path.is_file() else {}
    cases, case_receipt = _cases_payload(directory)
    if not payload and not cases:
        return None
    related = [item for item in payload.get("notables") or () if isinstance(item, dict)]
    after_rows = _with_related(rows, related)
    after_hays = [_haystack(row) for row in after_rows]
    _, _, _, after_steps, after_scenarios = _entity_pass(artefacts, after_rows, after_hays, owners)
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
        "case_member_recall": _case_recall(
            cases, artefacts, owners, rows, related, classes=("B", "P")
        ),
        "case_quality": _case_quality(cases, case_receipt, payload.get("receipt") or {}),
        "first_true_case_rank": first_true,
        "false_cases_above_first_true": false_above,
        "receipt": payload.get("receipt") or {},
    }


def _apply_causes(keys: Sequence[EntityKey], causes: Mapping[str, str] | None) -> list[EntityKey]:
    if not causes:
        return list(keys)
    return [replace(key, cause=causes.get(f"{key.scenario}/{key.step}", key.cause)) for key in keys]


def _ceiling_for(
    directory: Path,
    artefacts: Sequence[EntityKey],
    owners: Mapping[str, str],
    steps: Mapping[str, Step],
    strict_steps: Mapping[str, Step],
    line_steps: Mapping[str, Step] | None,
) -> dict[str, Any]:
    stores = _reachable_stores(directory, [key.value for key in artefacts])
    reached = _entity_reachability(artefacts, owners, stores)
    censored = _censored_steps(artefacts, owners, stores, _read_ledger(directory))
    return _entity_ceiling(
        list(steps.values()),
        strict_steps,
        reached,
        stores,
        artefacts,
        owners,
        line_steps,
        censored,
    )


def _entity_family(
    family: str,
    directory: Path,
    keys_path: Path,
    events_path: Path | None = None,
    causes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    rows = _read_notables(directory)
    progress = read_json(directory / PROGRESS_FILE)
    if not progress:
        raise ScoreboardError(f"{directory / PROGRESS_FILE} is missing; this run is not scored")
    keys = _apply_causes(_read_entity_keys(keys_path), causes)
    index, _run_sources = _run_index(directory)
    _check_entity_family(index, keys)
    artefacts, assets, rejected = _entity_split(keys)
    owners = _entity_ownership(artefacts)
    hays = [_haystack(row) for row in rows]
    strict_hays = [
        "" if row.get("generator") == "relate" else _haystack(row, strict=True) for row in rows
    ]
    notables, firsts, by_generator, steps, scenarios = _entity_pass(artefacts, rows, hays, owners)
    _, strict_firsts, _, strict_steps, strict_scenarios = _entity_pass(
        artefacts, rows, strict_hays, owners, cover=False
    )
    ordered, ordered_scenarios = _entity_order(steps), _entity_order(scenarios)
    events = None if events_path is None else _read_keyed_events(events_path, index)
    line_steps: dict[str, Step] = {}
    line = (
        None
        if events is None
        else _entity_line_mode(artefacts, owners, events, rows, keep=line_steps)
    )
    relation_payload = read_json(directory / RELATE_FILE)
    related = [item for item in relation_payload.get("notables") or () if isinstance(item, Mapping)]
    cases, _case_receipt = _cases_payload(directory)
    promoted = _promotion_ids(relation_payload)
    without_promotions = [row for row in rows if str(row.get("notable_id") or "") not in promoted]
    without_related = [row for row in related if str(row.get("notable_id") or "") not in promoted]
    case_recall = _case_recall(cases, artefacts, owners, rows, related)
    generators = _generator_table(rows, progress, artefacts, owners, strict_steps)
    report = {
        "family": family,
        "index": index,
        "mode": "entity",
        "card_contract": _card_contract(directory),
        "rule": ENTITY_RULE,
        "modes_rule": MODES_RULE,
        "keys": {
            "file": str(keys_path),
            "scenarios": len({key.scenario for key in keys}),
            "steps": len({(key.scenario, key.step) for key in keys}),
            "scored_steps": len(steps),
            "artefacts": len(artefacts),
            "assets": len(assets),
            "pending_audit": sum(1 for key in artefacts if key.admitted is None),
            "not_admitted": rejected,
            "shared_keys": sum(
                1 for key in artefacts if owners.get(key.value) != f"{key.scenario}/{key.step}"
            ),
            "no_credit_keys": sum(1 for key in artefacts if not key.credit),
            "classes": dict(
                sorted(
                    Counter(
                        key.klass
                        for key in artefacts
                        if key.klass and key.role == "artefact" and key.admitted is not False
                    ).items()
                )
            ),
        },
        "notables": {
            "total": len(notables),
            "by_generator": _tally(notables),
            "covering": sum(1 for notable in notables if notable.covered),
            "cost": {str(limit): _read_count(limit, len(notables)) for limit in CUTS},
        },
        "artefacts": _artefact_rows(artefacts, firsts, by_generator, strict_firsts, owners),
        "assets": _asset_rows(assets, rows, hays),
        "steps": [_step_row(step) for step in ordered],
        "scenarios": [_step_row(step) for step in ordered_scenarios],
        "recall": _recall(ordered),
        "scenario_recall": _recall(ordered_scenarios),
        "strict_recall": _recall(_entity_order(strict_steps)),
        "strict_scenario_recall": _recall(_entity_order(strict_scenarios)),
        "class_recall": _class_recall(ordered),
        "case_recall": case_recall,
        "promotion_effect": _promotion_effect(
            rows,
            without_promotions,
            promoted,
            artefacts,
            owners,
            cases,
            related,
            without_related,
            events,
        ),
        "generators": generators,
        "ceiling": _ceiling_for(
            directory, artefacts, owners, steps, strict_steps, line_steps or None
        ),
        "line_mode": line,
        "judge": _judge_block(notables, read_json(directory / JUDGE_CACHE)),
        "cost": _cost(progress, directory),
        "honesty": _honesty(progress, family),
    }
    relation = _entity_relation(directory, rows, artefacts, steps, scenarios, owners)
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


def _case_lines(relation: Mapping[str, Any]) -> list[str]:
    """The S3 case properties: member recall per scenario, evidence, coverage, promotion."""
    quality = relation.get("case_quality") or {}
    member = relation.get("case_member_recall") or {}
    if not quality:
        return []
    overall = member.get("overall") or {}
    dataset = (member.get("dataset_covered") or {}).get("50")
    covered = "" if dataset is None else f"  scenario covered {_flag(bool(dataset))}"
    lines = [
        f"case members top50 {overall.get('50')}/{member.get('scenarios')} "
        f"top100 {overall.get('100')}/{member.get('scenarios')} "
        f"all {overall.get('None')}/{member.get('scenarios')} (B/P steps in a case){covered}",
        f"case evidence pieces min {quality.get('min_evidence')} violations "
        f"{quality.get('two_evidence_violations')}  rows min {quality.get('evidence_rows')}  "
        f"unjudged cases {quality.get('unjudged_cases')}  "
        f"coverage_complete {quality.get('coverage_complete')}  "
        f"uncapped_fraction {quality.get('uncapped_fraction')}  censored {quality.get('censored')}",
        f"case promotion judged_only {_flag(bool(quality.get('promotion_judged_only')))} "
        f"lifted {quality.get('promoted')} unjudged_lifted {quality.get('promoted_unjudged')}",
    ]
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
    lines.extend(_case_lines(relation))
    lines.extend(
        f"  case {case['rank'] + 1}: {case['case_id']}  "
        f"keyed events {case['keyed_events']}/{case['events']}  purity {case['purity']}"
        for case in purity["cases"][:CASE_HEAD_LINES]
    )
    return lines


def _cost_lines(report: Mapping[str, Any]) -> list[str]:
    cost = report["cost"]
    stages = "  ".join(
        f"{name}={row['seconds']}s/{row['model_requests']}model-req/"
        f"{row['searches']}searches/{row['events_read']}rows"
        for name, row in cost["stages"].items()
    )
    return [
        f"cost {stages}  total={cost['seconds']}s model-requests={cost['model_requests']} "
        f"searches={cost['search_requests']} rows={cost['events_read']} "
        f"read_fraction={cost['read_fraction']} peak={cost['peak_memory_mb']}MB"
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
        f"keys {keys['file']}  scenarios {keys['scenarios']}  declared steps {keys['steps']}"
        f"  scored steps {keys['scored_steps']}  artefacts {keys['artefacts']}  "
        f"assets {keys['assets']}",
        f"notables {notables['total']} {notables['by_generator']}  covering any artefact "
        f"{notables['covering']}",
        f"shared keys {keys['shared_keys']} (a shared value credits its first step only)  "
        f"no-credit keys {keys['no_credit_keys']}  classes {keys['classes'] or 'untagged'}",
        f"quiet = a step whose creditable artefacts total <= {QUIET_MAX_LINES} keyed events "
        "(audit counts; an artefact pending audit counts 0)",
        "top N = the first N lines of notables.jsonl, the run's own order",
        "rule: " + report["rule"],
        "modes: " + report["modes_rule"],
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
        f"{'top50':>5} {'top100':>6} {'all':>4} {'rank':>6} {'strict':>6}  "
        f"{'covered by':<30}note"
    ]
    for row in artefacts:
        covered = row["covered"]
        events = row["events"] if row["events"] is not None else "pending"
        rank = row["first_rank"] if row["first_rank"] is not None else "-"
        strict = row["first_rank_strict"] if row["first_rank_strict"] is not None else "-"
        notes = []
        if not row["credit"]:
            notes.append("no credit")
        if row["shared_step"]:
            notes.append(f"shared of {row['shared_step']}")
        if row["requires"]:
            notes.append("requires " + ",".join(row["requires"]))
        lines.append(
            f"  {row['scenario'] + '/' + row['step']:<40}{str(row['value'])[:44]:<46}"
            f"{row['entity']:<10}{str(events):>9}  "
            f"{_flag(bool(covered['50'])):>5} {_flag(bool(covered['100'])):>6} "
            f"{_flag(bool(covered['None'])):>4} {str(rank):>6} {str(strict):>6}  "
            f"{_generator_line(row):<30}{'; '.join(notes) or '-'}"
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


def _class_bits(classes: Mapping[str, Any]) -> str:
    return "   ".join(
        f"{name} {block['covered']['50']}/{block['steps']} (top50) "
        f"{block['covered']['None']}/{block['steps']} (all)"
        for name, block in classes.items()
    )


def _entity_mode_lines(report: Mapping[str, Any]) -> list[str]:
    strict = report["strict_recall"]
    strict_scenarios = report["strict_scenario_recall"]
    lines = [
        f"strict     top50 {strict['overall']['50']}/{strict['steps']}   "
        f"top100 {strict['overall']['100']}/{strict['steps']}   "
        f"all {strict['overall']['None']}/{strict['steps']}   "
        f"(what/basis/why/entities only; scenarios "
        f"{strict_scenarios['overall']['None']}/{strict_scenarios['steps']} all)",
    ]
    classes = report.get("class_recall") or {}
    if classes:
        lines.append(f"  class    {_class_bits(classes)}")
    return lines


def _entity_line_lines(report: Mapping[str, Any]) -> list[str]:
    line = report.get("line_mode")
    if line is None:
        return []
    recall = line["recall"]
    overall = recall["overall"]
    lines = [
        f"line mode  top50 {overall['50']}/{recall['steps']}   "
        f"top100 {overall['100']}/{recall['steps']}   "
        f"all {overall['None']}/{recall['steps']}   keyed events {line['events']}",
    ]
    classes = line.get("class_recall") or {}
    if classes:
        lines.append(f"  class    {_class_bits(classes)}")
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
    lines.extend(_case_lines(relation))
    lines.extend(
        f"  case {row['rank'] + 1}: {row['case_id']}  events {row['events']}  "
        f"scenarios {', '.join(row['scenarios']) or '-'}"
        for row in relation["case_rows"][:CASE_HEAD_LINES]
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
    lines += _entity_mode_lines(report)
    lines += _entity_line_lines(report)
    lines += _entity_measure_lines(report)
    lines += _ceiling_lines(report)
    lines += _diff_lines(report)
    relation_lines = _entity_relate_lines(report)
    if relation_lines:
        lines += ["", *relation_lines]
    lines += _judge_lines(report)
    lines += _cost_lines(report)
    lines += _honesty_lines(report)
    return "\n".join(lines)


def _generator_lines(report: Mapping[str, Any]) -> list[str]:
    """Each generator's head share beside its measured marginal and the weight the run used."""
    lines = [
        "generator marginal (candidates kept head@50 attribution@50 marginal@50/@100 measured used)"
    ]
    lines.extend(
        f"  {name:<18}{detail['candidates']:>10}{detail['kept']:>7}{detail['head@50']:>7} "
        f"{detail['attribution@50']['steps']:>7} {detail['marginal@50']:>10}/"
        f"{detail['marginal@100']:<4} {detail['merge_weight']:>6}"
        f"{detail['used_weight'] if detail['used_weight'] is not None else '-':>6}"
        for name, detail in report["generators"].items()
    )
    return lines


def _line_generator_lines(report: Mapping[str, Any]) -> list[str]:
    return _generator_lines(report)


def _entity_measure_lines(report: Mapping[str, Any]) -> list[str]:
    case_recall = report["case_recall"]
    promotion = report["promotion_effect"]
    lines = [
        f"case recall top50 {case_recall['overall']['50']}/{case_recall['scenarios']} "
        f"top100 {case_recall['overall']['100']}/{case_recall['scenarios']} "
        f"all {case_recall['overall']['None']}/{case_recall['scenarios']}",
        f"promotion effect promoted={promotion['promoted']} "
        f"strict top50 {promotion['with']['strict_recall']['overall']['50']}/"
        f"{promotion['without']['strict_recall']['overall']['50']} with/without; "
        f"case top50 {promotion['with']['case_recall']['overall']['50']}/"
        f"{promotion['without']['case_recall']['overall']['50']} with/without",
        *_generator_lines(report),
    ]
    return lines


def _reach_text(block: Mapping[str, Any]) -> str:
    return "  ".join(
        f"{'all' if cut == 'None' else '@' + cut} {block['covered'][cut]}/{block['reachable']}"
        for cut in ("50", "100", "None")
    )


def _evidence_absent_lines(ceiling: Mapping[str, Any]) -> list[str]:
    rows = ceiling.get("evidence_absent")
    if rows is None:
        return [f"C0 evidence absent  n/a ({ceiling.get('index_map')})"]
    return [
        f"C0 evidence absent (excluded from the step denominator)  {row['step']} "
        f"{row['absent']}/{row['lines']} labelled lines"
        for row in rows
    ]


def _diff_lines(report: Mapping[str, Any]) -> list[str]:
    base = report.get("baseline")
    if not isinstance(base, Mapping):
        return []
    diff = base["diff"]

    def named(key: str) -> str:
        return ", ".join(diff[key]) or "-"

    return [
        f"C0 step diff vs {base['path']}",
        f"  covered@50  lost {named('lost')}  gained {named('gained')}",
        f"  reachable   lost {named('reachable_lost')}  gained {named('reachable_gained')}",
    ]


def _ceiling_lines(report: Mapping[str, Any]) -> list[str]:
    ceiling = report.get("ceiling")
    if not isinstance(ceiling, Mapping):
        return []
    if report.get("mode") != "entity":
        overall = report["recall"]["overall"]
        steps = report["recall"]["steps"]
        return [
            f"C0 ceiling  steps {ceiling['reachable']}/{ceiling['steps']} reachable  "
            f"labelled lines read verbatim {ceiling['lines_read']}/"
            f"{ceiling['labelled_lines']}",
            *_evidence_absent_lines(ceiling),
            f"C0 recall-of-reachable  line {_reach_text(ceiling)}",
            f"C0 modes  line {overall['50']}/{steps} @50  {overall['100']}/{steps} @100  "
            f"{overall['None']}/{steps} all   strict n/a for per-line keys",
        ]
    loose, strict, line = ceiling["loose"], ceiling["strict"], ceiling["line"]
    both = ceiling["by_class"].get("B+P") or {"reachable": 0, "steps": loose["steps"]}
    counts = Counter(row["cause"] for row in ceiling["per_step"])
    declared = sum(1 for row in ceiling["per_step"] if row["cause_source"] == "audit")
    causes = ", ".join(f"{name} {count}" for name, count in sorted(counts.items()))
    if declared:
        causes += f"  (audit-declared {declared})"
    line_reach = "n/a (no keyed-events export)" if line is None else _reach_text(line)
    overall = report["recall"]["overall"]
    strict_overall = report["strict_recall"]["overall"]
    line_overall = (
        None if report.get("line_mode") is None else report["line_mode"]["recall"]["overall"]
    )
    steps = report["recall"]["steps"]
    line_modes = (
        "n/a"
        if line_overall is None
        else f"{line_overall['50']}/{steps} @50  {line_overall['100']}/{steps} @100  "
        f"{line_overall['None']}/{steps} all"
    )
    return [
        f"C0 ceiling  keys {ceiling['keys_reachable']}/{ceiling['keys']} reachable  "
        f"steps {loose['reachable']}/{loose['steps']} (B+P {both['reachable']}/"
        f"{both['steps']})  stores {ceiling['stores'] or 'none'}",
        f"C0 recall-of-reachable  loose {_reach_text(loose)}   strict {_reach_text(strict)}"
        f"   line {line_reach}",
        f"C0 modes  loose {overall['50']}/{steps} @50  {overall['100']}/{steps} @100  "
        f"{overall['None']}/{steps} all   strict {strict_overall['50']}/{steps} @50  "
        f"{strict_overall['100']}/{steps} @100  {strict_overall['None']}/{steps} all   "
        f"line {line_modes}",
        f"C0 causes  {causes}",
        "C0 cause rule: " + str(ceiling["cause_rule"]),
        "C0 reach rule: " + str(ceiling["rule"]),
    ]


def render(report: Mapping[str, Any]) -> str:
    if report.get("mode") == "entity":
        return _render_entity(report)
    lines = [*_summary_lines(report), "", f"QUIET steps (<= {QUIET_MAX_LINES} lines)"]
    lines += _step_table(report["steps"], True) or ["  none"]
    lines += ["", f"LOUD steps (> {QUIET_MAX_LINES} lines)"]
    lines += _step_table(report["steps"], False) or ["  none"]
    lines += ["", *_recall_lines(report)]
    lines += _line_generator_lines(report)
    lines += _ceiling_lines(report)
    lines += _diff_lines(report)
    relation_lines = _relate_lines(report)
    if relation_lines:
        lines += ["", *relation_lines]
    lines += _judge_lines(report)
    lines += _cost_lines(report)
    lines += _honesty_lines(report)
    return "\n".join(lines)


def _read_causes(path: Path) -> dict[str, str]:
    stored = read_json(path)
    if not stored:
        raise ScoreboardError(f"causes file is missing or empty: {path}")
    if isinstance(stored.get("causes"), Mapping):
        stored = stored["causes"]
    return {str(step): str(cause) for step, cause in stored.items() if isinstance(cause, str)}


def _cause_paths(values: Sequence[str], families: Sequence[str]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for value in values:
        family, _, path = value.partition("=")
        if not family or not path:
            raise ScoreboardError(f"--causes {value!r} is not family=path")
        found[family.strip()] = Path(path)
    missing = [family for family in families if family in found and not found[family].is_file()]
    if missing:
        raise ScoreboardError(f"causes file not found for {', '.join(missing)}")
    return found


def _step_sets(report: Mapping[str, Any]) -> dict[str, list[str]]:
    """This family's covered@50 and reachable step names, as sets a diff can name."""
    ceiling = report.get("ceiling") or {}
    return {
        "covered": sorted(
            str(row["step"])
            for row in report.get("steps") or ()
            if (row.get("covered") or {}).get("50")
        ),
        "reachable": sorted(
            str(row["step"]) for row in ceiling.get("per_step") or () if row.get("reachable")
        ),
    }


def _step_diff(now: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, list[str]]:
    """The four step lists a regression is reported as, never a ratio."""
    here, before = _step_sets(now), _step_sets(baseline)
    return {
        "lost": sorted(set(before["covered"]) - set(here["covered"])),
        "gained": sorted(set(here["covered"]) - set(before["covered"])),
        "reachable_lost": sorted(set(before["reachable"]) - set(here["reachable"])),
        "reachable_gained": sorted(set(here["reachable"]) - set(before["reachable"])),
    }


def _baseline_dir(baseline: Path, family: str, single: bool) -> Path:
    path = baseline if single else baseline / family
    if not (path / NOTABLES_FILE).is_file():
        raise ScoreboardError(f"baseline {path} holds no {NOTABLES_FILE} to diff against")
    return path


def _baseline_block(path: Path, other: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "family": other.get("family"),
        "steps": other.get("recall", {}).get("steps"),
        "sets": _step_sets(other),
    }


def _scored(
    family: str,
    directory: Path,
    key_path: Path,
    events: Path | None,
    declared: dict[str, str] | None,
    logs: Path | None,
    year: int | None,
) -> dict[str, Any]:
    if _keys_are_entity(key_path):
        return _entity_family(family, directory, key_path, events, declared)
    return _family(family, directory, key_path, logs, year)


def _weight_evidence(report: Mapping[str, Any]) -> dict[str, Any]:
    marginal_generators: dict[str, dict[str, int]] = {}
    measured_generators = report.get("generators")
    measured_generators = measured_generators if isinstance(measured_generators, Mapping) else {}
    for name in report["recall"].get("by_generator") or {}:
        measured = measured_generators.get(name)
        if isinstance(measured, Mapping):
            marginal_generators[name] = {
                "candidates": int(measured.get("candidates") or 0),
                "marginal@50": int(measured.get("marginal@50") or 0),
                "marginal@100": int(measured.get("marginal@100") or 0),
                "merge_weight": int(measured.get("merge_weight") or UNMEASURED_WEIGHT),
            }
    return {
        "family": report["family"],
        "steps": report["recall"]["steps"],
        "marginal_generators": marginal_generators,
    }


def _weights_block(evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    folds = [{"held_out": None, "weights": marginal_weights(evidence)}]
    for family in evidence:
        rest = [item for item in evidence if item["family"] != family["family"]]
        folds.append({"held_out": family["family"], "weights": marginal_weights(rest)})
    return {
        "rule": (
            "weight = mean re-merge marginal steps at @50 over the families where the "
            "generator had candidates (candidates > 0); a generator that was never exercised, "
            "or whose only hit fell outside the head, keeps a unit weight; no evidence at all "
            "keeps DEFAULT_WEIGHTS"
        ),
        "default": dict(DEFAULT_WEIGHTS),
        "evidence": list(evidence),
        "folds": folds,
    }


def _write_weights_out(path: Path, block: Mapping[str, Any]) -> None:
    """The measured vector a hunt consumes through ``PORTAL_HUNT_MERGE_WEIGHTS``."""
    folds = block["folds"]
    payload = {
        "source": MEASURED_SOURCE,
        "rule": block["rule"],
        "families": [item["family"] for item in block["evidence"]],
        "weights": folds[0]["weights"],
        "folds": folds,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def score(
    out: Path,
    key_args: Sequence[str],
    *,
    logs: Path | None = None,
    year: int | None = None,
    keyed_events: Sequence[str] | None = None,
    causes: Sequence[str] | None = None,
    weights: bool = False,
    baseline: Path | None = None,
    weights_out: Path | None = None,
) -> dict[str, Any]:
    targets = _targets(out)
    families = [family for family, _directory in targets]
    keys = _key_paths(key_args, families)
    events = _optional_paths(keyed_events or ())
    cause_paths = _cause_paths(causes or (), families)
    reports = []
    for family, directory in targets:
        declared = _read_causes(cause_paths[family]) if family in cause_paths else None
        report = _scored(family, directory, keys[family], events.get(family), declared, logs, year)
        if baseline is not None:
            path = _baseline_dir(baseline, family, len(targets) == 1)
            other = _scored(family, path, keys[family], events.get(family), declared, logs, year)
            report["baseline"] = {
                **_baseline_block(path, other),
                "diff": _step_diff(report, other),
                "rule": DIFF_RULE,
            }
        reports.append(report)
    result: dict[str, Any] = {"families": reports}
    if weights or weights_out is not None:
        evidence = [_weight_evidence(report) for report in reports]
        block = _weights_block(evidence)
        result["weights"] = block
        if weights_out is not None:
            _write_weights_out(weights_out, block)
            result["weights_out"] = str(weights_out)
    return result


def _optional_paths(values: Sequence[str]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for value in values:
        family, _, path = value.partition("=")
        if not family or not path:
            raise ScoreboardError(f"--keyed-events {value!r} is not family=path")
        found[family.strip()] = Path(path)
    return found


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="run dir, or the dir of families")
    parser.add_argument(
        "--keys",
        action="append",
        required=True,
        help="family=path to that family's keys.jsonl (repeat per family)",
    )
    parser.add_argument(
        "--keyed-events",
        action="append",
        help="family=path to that family's keyed-event export; entity families only, "
        "adds line mode beside entity mode (repeat per family)",
    )
    parser.add_argument(
        "--causes",
        action="append",
        help="family=path to that family's audit cause map (JSON step -> cause); entity "
        "families only (repeat per family)",
    )
    parser.add_argument(
        "--weights",
        action="store_true",
        help="report the measured marginal generator weights and their leave-one-family-out folds",
    )
    parser.add_argument(
        "--weights-out",
        type=Path,
        help="write the measured weights to this file, the form PORTAL_HUNT_MERGE_WEIGHTS "
        "takes (implies --weights)",
    )
    parser.add_argument("--logs", type=Path, help="raw log tree holding the labelled lines")
    parser.add_argument("--year", type=int, help="year for a timestamp that carries none")
    parser.add_argument(
        "--baseline",
        type=Path,
        help="another run's dir (its family dirs when --out holds several) to diff the step sets against",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def _weights_lines(report: Mapping[str, Any]) -> list[str]:
    weights = report.get("weights")
    if not isinstance(weights, Mapping):
        return []
    folds = weights["folds"]
    original_names = list(weights["default"])
    extras = sorted(
        {name for fold in folds for name in fold["weights"] if name not in original_names}
    )
    names = [*original_names, *extras]
    lines = ["C4 marginal generator weights  (" + str(weights["rule"]) + ")"]
    lines.append("  held out   " + "  ".join(f"{name:<16}" for name in names))
    for fold in folds:
        label = "all" if fold["held_out"] is None else str(fold["held_out"])
        cells = "  ".join(f"{fold['weights'].get(name, 0):<16}" for name in names)
        lines.append(f"  {label:<10} {cells}")
    if report.get("weights_out"):
        lines.append(f"  written    {report['weights_out']}")
    return lines


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    started = time.monotonic()
    try:
        report = score(
            args.out,
            args.keys,
            logs=args.logs,
            year=args.year,
            keyed_events=args.keyed_events,
            causes=args.causes,
            weights=args.weights,
            baseline=args.baseline,
            weights_out=args.weights_out,
        )
    except ScoreboardError as error:
        print(f"scoreboard: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=1, sort_keys=False))
    else:
        text = "\n\n".join(render(family) for family in report["families"])
        weight_lines = _weights_lines(report)
        if weight_lines:
            text += "\n\n" + "\n".join(weight_lines)
        print(text + f"\n\nscored in {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
