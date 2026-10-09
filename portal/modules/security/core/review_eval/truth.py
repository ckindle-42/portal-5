"""review_eval.truth -- independently derive scoped truth from the BOTS answer key.

The answer key supplies entities and source types, but no event intervals. This module searches
those sources directly, derives each interval from located event times, and computes identities
with the product intake function over product-normalized records. It never reads engine output.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY
from portal.modules.security.core.bully.corpus_bed import BOTS_INDEXES, AnswerKeyEntry
from portal.modules.security.core.review.intake import event_id_for
from portal.modules.security.core.review.window import SourceSpec

RecordFetcher = Callable[[str, str, Sequence[str], float, float], Iterable[Mapping[str, Any]]]
_ENTITY_BOUNDARY = r"(?<![A-Za-z0-9-]){}(?![A-Za-z0-9-])"


@dataclass(frozen=True)
class TruthItem:
    item_id: str
    klass: str
    event_ids: tuple[str, ...]
    anchor_ids: tuple[str, ...]
    dataset: str
    technique: str


@dataclass(frozen=True)
class EntitySearchStat:
    event_count: int
    first_epoch: float | None
    last_epoch: float | None


StatsFetcher = Callable[[str, str, Sequence[str]], EntitySearchStat]


@dataclass(frozen=True)
class EntryReceipt:
    item_id: str
    index: str
    technique: str
    sourcetypes: tuple[str, ...]
    expected_entity_count: int
    located_entity_count: int
    event_count: int
    start_epoch: float | None
    end_exclusive_epoch: float | None
    status: str
    reason: str
    entity_tokens: tuple[str, ...]
    event_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "index": self.index,
            "technique": self.technique,
            "sourcetypes": list(self.sourcetypes),
            "expected_entity_count": self.expected_entity_count,
            "located_entity_count": self.located_entity_count,
            "event_count": self.event_count,
            "interval": (
                {
                    "start_epoch": self.start_epoch,
                    "end_exclusive_epoch": self.end_exclusive_epoch,
                }
                if self.start_epoch is not None and self.end_exclusive_epoch is not None
                else None
            ),
            "status": self.status,
            "reason": self.reason,
            "entity_tokens": list(self.entity_tokens),
        }


@dataclass(frozen=True)
class TruthDerivation:
    items: tuple[TruthItem, ...]
    receipts: tuple[EntryReceipt, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "review.truth-ledger.v1",
            "answer_key_entry_count": len(self.receipts),
            "derived_item_count": len(self.items),
            "dropped_entry_count": sum(receipt.status == "dropped" for receipt in self.receipts),
            "items": [
                {
                    "item_id": item.item_id,
                    "class": item.klass,
                    "dataset": item.dataset,
                    "technique": item.technique,
                    "event_count": len(item.event_ids),
                    "event_ids": list(item.event_ids),
                    "anchor_ids": list(item.anchor_ids),
                }
                for item in self.items
            ],
            "entries": [receipt.to_dict() for receipt in self.receipts],
        }


@dataclass(frozen=True)
class CaptureTruthPopulation:
    items: tuple[TruthItem, ...]
    records_by_source: Mapping[str, tuple[Mapping[str, Any], ...]]
    admission_manifest_sha256: str
    admitted_capture_count: int
    skipped_unparseable_event_count: int


def derive_capture_truth(
    capture_dir: Path,
    admission_manifest: Mapping[str, Any],
) -> CaptureTruthPopulation:
    """Materialize only stamped, admitted recorded captures as product-shaped scorer truth.

    The manifest decides inclusion and class; capture bytes are re-hashed and revalidated before
    event IDs are built. Raw lines exist only in the returned in-memory window records.
    """
    admitted, manifest_digest = _admitted_capture_rows(admission_manifest)
    items: list[TruthItem] = []
    records_by_source: dict[str, list[Mapping[str, Any]]] = {}
    skipped_unparseable = 0
    for admitted_capture in admitted:
        capture_id, capture, interval = _load_admitted_capture(
            capture_dir, admission_manifest, admitted_capture
        )
        capture_records, event_ids, skipped = _capture_records(capture_id, capture, interval)
        for source, records in capture_records.items():
            records_by_source.setdefault(source, []).extend(records)
        if not event_ids:
            raise ValueError(f"admitted capture {capture_id!r} has no product-identifiable events")
        items.extend(_capture_items(capture_id, admitted_capture, event_ids))
        skipped_unparseable += skipped
    return CaptureTruthPopulation(
        items=tuple(items),
        records_by_source={
            source: tuple(records) for source, records in records_by_source.items() if records
        },
        admission_manifest_sha256=manifest_digest,
        admitted_capture_count=len(admitted),
        skipped_unparseable_event_count=skipped_unparseable,
    )


def _admitted_capture_rows(
    admission_manifest: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], str]:
    selftest = admission_manifest.get("selftest")
    admitted = admission_manifest.get("admitted")
    manifest_digest = admission_manifest.get("admission_manifest_sha256")
    if not isinstance(selftest, Mapping) or selftest.get("passed") is not True:
        raise ValueError("capture manifest has no passing known-answer self-test")
    if not isinstance(admitted, list) or not manifest_digest:
        raise ValueError("capture manifest has no admitted set or digest")
    if any(not isinstance(item, Mapping) for item in admitted):
        raise ValueError("capture manifest admitted row is not an object")
    return admitted, str(manifest_digest)


def _load_admitted_capture(
    capture_dir: Path,
    admission_manifest: Mapping[str, Any],
    admitted_capture: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any], tuple[float, float]]:
    from .captures import validate_capture

    capture_id = str(admitted_capture.get("capture_id") or "")
    if not capture_id or Path(capture_id).name != capture_id:
        raise ValueError("capture manifest has an invalid capture id")
    content = (capture_dir / f"{capture_id}.json").read_bytes()
    if hashlib.sha256(content).hexdigest() != admitted_capture.get("capture_sha256"):
        raise ValueError(f"admitted capture {capture_id!r} changed after certification")
    capture = json.loads(content)
    if not isinstance(capture, Mapping):
        raise ValueError(f"admitted capture {capture_id!r} is not an object")
    validation = validate_capture(capture)
    if not validation.valid or validation.interval is None:
        raise ValueError(f"admitted capture {capture_id!r} no longer validates")
    start, end = validation.interval
    recorded_interval = admitted_capture.get("interval")
    if not isinstance(recorded_interval, Mapping) or (
        float(recorded_interval.get("start_epoch", -1)) != start
        or float(recorded_interval.get("end_epoch", -1)) != end
    ):
        raise ValueError(f"admitted capture {capture_id!r} interval changed")
    host = str(capture.get("target_host") or "")
    stamp_digest = str(admission_manifest.get("stamp_digest") or "")
    token = hashlib.sha256(f"{stamp_digest}|{host}".encode()).hexdigest()[:16]
    if token != admitted_capture.get("host_token"):
        raise ValueError(f"admitted capture {capture_id!r} host token changed")
    return capture_id, capture, (start, end)


def _capture_records(
    capture_id: str,
    capture: Mapping[str, Any],
    interval: tuple[float, float],
) -> tuple[dict[str, list[Mapping[str, Any]]], list[str], int]:
    from .captures import event_time

    telemetry = capture.get("telemetry")
    if not isinstance(telemetry, Mapping):
        raise ValueError(f"admitted capture {capture_id!r} has no telemetry map")
    start, end = interval
    host = str(capture.get("target_host") or "")
    records: dict[str, list[Mapping[str, Any]]] = {}
    event_ids: list[str] = []
    skipped = 0
    for sourcetype, lines in telemetry.items():
        if not isinstance(lines, list):
            continue
        spec = SourceSpec("recorded_captures", str(sourcetype))
        selected = records.setdefault(spec.source_id, [])
        for line in lines:
            rendered = str(line)
            timestamp = event_time(rendered, source=spec.sourcetype, interval=interval)
            if timestamp is None:
                skipped += 1
                continue
            if start <= timestamp <= end:
                record = {
                    "_time": timestamp,
                    "_raw": rendered,
                    "index": spec.index,
                    "sourcetype": spec.sourcetype,
                    "host": host,
                    "source": spec.sourcetype,
                }
                selected.append(record)
                event_ids.append(event_id_for(spec.source_id, record))
    return records, event_ids, skipped


def _capture_items(
    capture_id: str,
    admitted_capture: Mapping[str, Any],
    event_ids: Sequence[str],
) -> list[TruthItem]:
    classes = admitted_capture.get("truth_class_by_technique")
    techniques = admitted_capture.get("techniques")
    if not isinstance(classes, Mapping) or not isinstance(techniques, list):
        raise ValueError(f"admitted capture {capture_id!r} has no technique class mapping")
    items: list[TruthItem] = []
    for technique in techniques:
        name = str(technique)
        klass = str(classes.get(name) or "")
        if klass not in {"cousin", "novel"}:
            raise ValueError(f"admitted capture {capture_id!r} has invalid truth class")
        items.append(
            TruthItem(
                item_id=f"capture:{capture_id}:{name}",
                klass=klass,
                event_ids=tuple(sorted(event_ids)),
                anchor_ids=(),
                dataset="recorded_captures",
                technique=name,
            )
        )
    return items


@dataclass(frozen=True)
class _EntryPopulation:
    event_count: int
    first_epoch: float | None
    end_exclusive_epoch: float | None
    located_entities: frozenset[str]


@dataclass(frozen=True)
class _FetchedEvidence:
    event_times: Mapping[str, float]
    located_entities: frozenset[str]


@lru_cache(maxsize=512)
def _entity_pattern(entity: str) -> re.Pattern[str]:
    return re.compile(_ENTITY_BOUNDARY.format(re.escape(entity)), re.IGNORECASE)


def _matching_entities(record: Mapping[str, Any], entities: Sequence[str]) -> set[str]:
    rendered = json.dumps(record, sort_keys=True, default=str)
    return {entity for entity in entities if _entity_pattern(entity).search(rendered)}


def _entity_token(item_id: str, entity: str) -> str:
    return hashlib.sha256(f"{item_id}|{entity.casefold()}".encode()).hexdigest()[:16]


def _item_id_for(entry: AnswerKeyEntry, index: str) -> str:
    identity = {
        "entities": sorted(entity.casefold() for entity in entry.entities),
        "sourcetypes": sorted(entry.sourcetypes),
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:12]
    return f"{index}:{entry.technique}:{digest}"


def _index_for(entry: AnswerKeyEntry) -> str:
    if entry.dataset not in BOTS_INDEXES:
        raise ValueError(f"answer-key dataset {entry.dataset!r} is not a BOTS index")
    return entry.dataset


def derive_bots_truth(
    fetch_records: RecordFetcher,
    query_stats: StatsFetcher,
    *,
    entries: Sequence[AnswerKeyEntry] = BOTS_ANSWER_KEY,
) -> TruthDerivation:
    """Search every declared entity/source pair and keep only fully located entries.

    Aggregate queries first establish whole-index entity counts and a time span. Raw rows are
    fetched only when every declared entity exists, and only inside that derived span. Each
    result's ``event_id`` is computed with ``review.intake.event_id_for`` over product-normalized
    records; no funnel, classifier, unit grouping, anchor, or model result participates.
    """
    items: list[TruthItem] = []
    receipts: list[EntryReceipt] = []
    for entry in entries:
        item, receipt = _derive_entry(entry, fetch_records, query_stats)
        if item is not None:
            items.append(item)
        receipts.append(receipt)
    return TruthDerivation(tuple(items), tuple(receipts))


def _derive_entry(
    entry: AnswerKeyEntry,
    fetch_records: RecordFetcher,
    query_stats: StatsFetcher,
) -> tuple[TruthItem | None, EntryReceipt]:
    index = _index_for(entry)
    item_id = _item_id_for(entry, index)
    entities = tuple(dict.fromkeys(entry.entities))
    sourcetypes = tuple(dict.fromkeys(entry.sourcetypes))
    if not entities or not sourcetypes:
        return None, _empty_receipt(item_id, index, entry.technique, sourcetypes, len(entities))

    population = _entry_population(index, sourcetypes, entities, query_stats)
    evidence = _fetch_evidence(
        index,
        sourcetypes,
        entities,
        population,
        fetch_records,
    )
    expected_count_matches = len(evidence.event_times) == population.event_count
    entities_match = len(evidence.located_entities) == len(entities)
    keep = (
        population.event_count > 0
        and population.first_epoch is not None
        and population.end_exclusive_epoch is not None
        and expected_count_matches
        and entities_match
    )
    if keep:
        item = TruthItem(
            item_id=item_id,
            klass="known",
            event_ids=tuple(sorted(evidence.event_times)),
            anchor_ids=(),
            dataset=index,
            technique=entry.technique,
        )
        reason = "all_answer_key_entities_located"
        status = "derived"
    else:
        item = None
        if not population.event_count:
            reason = "no_matching_events_in_declared_sourcetypes"
        elif not entities_match:
            reason = "answer_key_entity_count_mismatch"
        else:
            reason = "entity_event_fetch_count_mismatch"
        status = "dropped"
    receipt = EntryReceipt(
        item_id=item_id,
        index=index,
        technique=entry.technique,
        sourcetypes=sourcetypes,
        expected_entity_count=len(entities),
        located_entity_count=(
            len(evidence.located_entities)
            if evidence.located_entities
            else len(population.located_entities)
        ),
        event_count=(len(evidence.event_times) if evidence.event_times else population.event_count),
        start_epoch=population.first_epoch,
        end_exclusive_epoch=population.end_exclusive_epoch,
        status=status,
        reason=reason,
        entity_tokens=tuple(
            sorted(
                _entity_token(item_id, entity)
                for entity in (evidence.located_entities or population.located_entities)
            )
        ),
        event_ids=tuple(sorted(evidence.event_times)),
    )
    return item, receipt


def _empty_receipt(
    item_id: str,
    index: str,
    technique: str,
    sourcetypes: tuple[str, ...],
    expected_entity_count: int,
) -> EntryReceipt:
    return EntryReceipt(
        item_id=item_id,
        index=index,
        technique=technique,
        sourcetypes=sourcetypes,
        expected_entity_count=expected_entity_count,
        located_entity_count=0,
        event_count=0,
        start_epoch=None,
        end_exclusive_epoch=None,
        status="dropped",
        reason="answer_key_missing_entities_or_sourcetypes",
        entity_tokens=(),
        event_ids=(),
    )


def _entry_population(
    index: str,
    sourcetypes: Sequence[str],
    entities: Sequence[str],
    query_stats: StatsFetcher,
) -> _EntryPopulation:
    source_stats = [query_stats(index, source, entities) for source in sourcetypes]
    entity_stats = {
        entity: [query_stats(index, source, (entity,)) for source in sourcetypes]
        for entity in entities
    }
    stats = [*source_stats, *(stat for group in entity_stats.values() for stat in group)]
    if any(stat.event_count < 0 for stat in stats):
        raise ValueError("entity search returned a negative event count")
    located = frozenset(
        entity for entity, group in entity_stats.items() if any(stat.event_count for stat in group)
    )
    firsts = [stat.first_epoch for stat in source_stats if stat.first_epoch is not None]
    lasts = [stat.last_epoch for stat in source_stats if stat.last_epoch is not None]
    first = min(firsts) if firsts else None
    end_exclusive = max(lasts) + 0.000001 if lasts else None
    return _EntryPopulation(
        event_count=sum(stat.event_count for stat in source_stats),
        first_epoch=first,
        end_exclusive_epoch=end_exclusive,
        located_entities=located,
    )


def _fetch_evidence(
    index: str,
    sourcetypes: Sequence[str],
    entities: Sequence[str],
    population: _EntryPopulation,
    fetch_records: RecordFetcher,
) -> _FetchedEvidence:
    if (
        len(population.located_entities) != len(entities)
        or population.event_count == 0
        or population.first_epoch is None
        or population.end_exclusive_epoch is None
    ):
        return _FetchedEvidence({}, frozenset())
    event_times: dict[str, float] = {}
    located: set[str] = set()
    for sourcetype in sourcetypes:
        source_id = SourceSpec(index, sourcetype).source_id
        for record in fetch_records(
            index,
            sourcetype,
            entities,
            population.first_epoch,
            population.end_exclusive_epoch,
        ):
            matches = _matching_entities(record, entities)
            timestamp = _record_epoch(record)
            if not matches or timestamp is None:
                continue
            located.update(matches)
            event_times[event_id_for(source_id, record)] = timestamp
    return _FetchedEvidence(event_times, frozenset(located))


def _record_epoch(record: Mapping[str, Any]) -> float | None:
    value = record.get("_time")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def benign_interval_candidates(
    corpus_start: float,
    corpus_end: float,
    excluded_spans: Sequence[tuple[float, float]],
    *,
    margin_seconds: float,
    duration_seconds: float,
) -> tuple[tuple[float, float], ...]:
    """Return same-sized UTC-day-aligned slices in the complement of the attack spans.

    The candidate duration is supplied by the attack interval being paired. Windows begin on a
    UTC day boundary, and a day that touches any margin-expanded answer-key span is excluded.
    This prevents selecting a same-day background window or widening the indexed corpus to
    manufacture a comparison slice.
    """
    if corpus_end <= corpus_start:
        raise ValueError("corpus_end must be greater than corpus_start")
    if margin_seconds < 0:
        raise ValueError("margin_seconds must be non-negative")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    seconds_per_day = 86_400.0
    expanded = tuple(
        (start - margin_seconds, end + margin_seconds) for start, end in excluded_spans
    )
    candidates: list[tuple[float, float]] = []
    gap_start = corpus_start
    for excluded_start, excluded_end in sorted(expanded):
        if excluded_start > gap_start:
            day_index = int(gap_start // seconds_per_day)
            aligned_start = (
                day_index * seconds_per_day
                if gap_start % seconds_per_day == 0
                else (day_index + 1) * seconds_per_day
            )
            candidate_end = aligned_start + duration_seconds
            if candidate_end <= min(excluded_start, corpus_end):
                candidates.append((aligned_start, candidate_end))
        gap_start = max(gap_start, excluded_end)
    if gap_start < corpus_end:
        day_index = int(gap_start // seconds_per_day)
        aligned_start = (
            day_index * seconds_per_day
            if gap_start % seconds_per_day == 0
            else (day_index + 1) * seconds_per_day
        )
        candidate_end = aligned_start + duration_seconds
        if candidate_end <= corpus_end:
            candidates.append((aligned_start, candidate_end))
    return tuple(candidates)
