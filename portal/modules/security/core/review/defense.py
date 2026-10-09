"""review.defense -- evaluate existing detections with bounded, read-only Splunk searches."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ..siem.spl_detections import (
    spl_for_source,
    technique_signature_full,
    techniques_covered,
)
from .contracts import DefenseResponse, ReviewConcern, ReviewResult, StageReceipt
from .intake import IntakeResult

SPLUNK_EPOCH_PRECISION_S = 0.000001
_TECHNIQUE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)


class ReadOnlySearcher(Protocol):
    def __call__(self, spl: str, start: float, end: float) -> Any: ...


@dataclass(frozen=True)
class Detection:
    technique_id: str
    source: str
    spl: str
    expected_signal: str


@dataclass(frozen=True)
class DefenseAssessment:
    response: DefenseResponse
    techniques: tuple[str, ...]
    queries_examined: int
    queries_resolved: int
    matching_rows: int
    errors: int
    expected_signals: tuple[str, ...]


def techniques_from_label(label: str) -> tuple[str, ...]:
    """Extract only published ATT&CK identifiers from a knowledge-plane label."""
    return tuple(dict.fromkeys(match.upper() for match in _TECHNIQUE.findall(label)))


def detections_for(concern: ReviewConcern) -> list[Detection]:
    """Resolve the top resemblance's technique labels to every configured SPL variant."""
    if not concern.resembles:
        return []
    covered = set(techniques_covered())
    source_types = {
        source_id.split(":", 1)[1] for source_id in concern.source_ids if ":" in source_id
    }
    out: list[Detection] = []
    seen: set[tuple[str, str]] = set()
    for technique in techniques_from_label(concern.resembles[0].anchor_label):
        if technique not in covered:
            continue
        signature = technique_signature_full(technique)
        expected = str(signature.get("expected_signal") or "")
        base = str(signature.get("spl") or "").strip()
        base_applies = not source_types or any(
            spl_for_source(technique, source_type) == base for source_type in source_types
        )
        if base and base_applies and (technique, base) not in seen:
            out.append(Detection(technique, "default", base, expected))
            seen.add((technique, base))
        for variant in signature.get("spl_variants") or ():
            if not isinstance(variant, Mapping):
                continue
            spl = str(variant.get("spl") or "").strip()
            source = str(variant.get("source") or "")
            key = (technique, spl)
            if not spl or key in seen or (source_types and source and source not in source_types):
                continue
            out.append(
                Detection(
                    technique,
                    source,
                    spl,
                    str(variant.get("expected_signal") or expected),
                )
            )
            seen.add(key)
    return out


def _entity_values(entities: Sequence[str]) -> tuple[str, ...]:
    values = {
        value.strip()
        for entity in entities
        if (value := entity.partition("=")[2] or entity).strip()
    }
    return tuple(sorted(values))


def _quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")
    )
    return f'"{escaped}"'


def scope_spl(spl: str, entities: Sequence[str]) -> str:
    """Constrain a library SPL to the concern's entity values before its pipeline."""
    values = _entity_values(entities)
    if not values:
        raise ValueError("a bounded detection search requires at least one concern entity")
    base, separator, pipeline = spl.partition("|")
    base = base.strip()
    if base.lower().startswith("search "):
        base = base[7:].strip()
    entity_clause = " OR ".join(_quote(value) for value in values)
    query = f"search ({base}) AND ({entity_clause})"
    if separator:
        query += f" | {pipeline.strip()}"
    return query


def source_searcher(source: object) -> ReadOnlySearcher | None:
    """Use the existing read-only Splunk window export when the source exposes it."""
    iter_post = getattr(source, "iter_post", None)
    if not callable(iter_post):
        return None

    def search(spl: str, start: float, end: float) -> Any:
        return iter_post(spl, start, end)

    return search


def _rows_and_error(result: Any) -> tuple[list[Mapping[str, Any]], bool]:
    if isinstance(result, Mapping):
        raw_rows = result.get("rows") or []
        error = bool(result.get("error"))
    else:
        raw_rows = result
        error = False
    if isinstance(raw_rows, (Mapping, str, bytes)):
        return [], True
    if not isinstance(raw_rows, Iterable):
        return [], True
    rows = [row for row in raw_rows if isinstance(row, Mapping)]
    return rows, error


def _within_bounds(row: Mapping[str, Any], start: float, end: float) -> bool:
    raw_time = row.get("_time")
    if raw_time is None:
        return True  # Aggregate SPL rows are already scoped by the export time bounds.
    try:
        at = float(raw_time)
    except (TypeError, ValueError):
        return False
    return start <= at < end


def _query(
    detection: Detection,
    entities: Sequence[str],
    start: float,
    end: float,
    searcher: ReadOnlySearcher,
    *,
    exclude_bounds: tuple[float, float] | None = None,
) -> tuple[int, bool, int, int]:
    try:
        result = searcher(scope_spl(detection.spl, entities), start, end)
        rows, error = _rows_and_error(result)
    except Exception:
        return 0, True, 0, 0
    matched = ambiguous_time = inside_excluded_window = 0
    for row in rows:
        raw_time = row.get("_time")
        if raw_time is None:
            if exclude_bounds is not None:
                ambiguous_time += 1
            else:
                matched += int(_within_bounds(row, start, end))
            continue
        try:
            at = float(raw_time)
        except (TypeError, ValueError):
            ambiguous_time += 1
            continue
        if not start <= at < end:
            continue
        if exclude_bounds is not None and exclude_bounds[0] <= at < exclude_bounds[1]:
            inside_excluded_window += 1
        else:
            matched += 1
    return matched, error, ambiguous_time, inside_excluded_window


def assess(
    concern: ReviewConcern,
    *,
    start: float,
    end: float,
    context_start: float,
    context_end: float,
    searcher: ReadOnlySearcher | None,
) -> DefenseAssessment:
    """Apply the explicit COVERED/MISSED/NEAR_MISS/INDETERMINATE mapping rule."""
    techniques = tuple(
        technique
        for technique in techniques_from_label(
            concern.resembles[0].anchor_label if concern.resembles else ""
        )
        if technique in set(techniques_covered())
    )
    detections = detections_for(concern)
    expected = tuple(
        dict.fromkeys(item.expected_signal for item in detections if item.expected_signal)
    )
    if not detections or searcher is None or not _entity_values(concern.entities):
        return DefenseAssessment(
            DefenseResponse.INDETERMINATE,
            techniques,
            0,
            0,
            0,
            0,
            expected,
        )

    exact_rows = exact_resolved = exact_errors = exact_unknown_time = 0
    for detection in detections:
        rows, error, ambiguous, _inside = _query(detection, concern.entities, start, end, searcher)
        exact_rows += rows
        exact_resolved += int(not error)
        exact_errors += int(error)
        exact_unknown_time += ambiguous
    examined = len(detections)
    if exact_rows:
        return DefenseAssessment(
            DefenseResponse.COVERED,
            techniques,
            examined,
            exact_resolved,
            exact_rows,
            exact_errors,
            expected,
        )

    context_is_wider = context_start < start or context_end > end
    context_rows = context_resolved = context_errors = context_unknown_time = 0
    context_inside = 0
    if context_is_wider:
        for detection in detections:
            rows, error, unknown_time, inside = _query(
                detection,
                concern.entities,
                context_start,
                context_end,
                searcher,
                exclude_bounds=(start, end),
            )
            context_rows += rows
            context_resolved += int(not error)
            context_errors += int(error)
            context_unknown_time += unknown_time
            context_inside += inside
        examined += len(detections)
        if context_inside:
            return DefenseAssessment(
                DefenseResponse.COVERED,
                techniques,
                examined,
                exact_resolved + context_resolved,
                context_inside,
                exact_errors + context_errors,
                expected,
            )
        if context_rows:
            return DefenseAssessment(
                DefenseResponse.NEAR_MISS,
                techniques,
                examined,
                exact_resolved + context_resolved,
                context_rows,
                exact_errors + context_errors,
                expected,
            )

    errors = exact_errors + context_errors
    response = (
        DefenseResponse.INDETERMINATE
        if errors or exact_unknown_time or context_unknown_time
        else DefenseResponse.MISSED
    )
    return DefenseAssessment(
        response,
        techniques,
        examined,
        exact_resolved + context_resolved,
        0,
        errors,
        expected,
    )


def _concern_bounds(
    concern: ReviewConcern,
    window: IntakeResult,
    request_start: float,
    request_end: float,
    unit_events: Mapping[str, Sequence[str]],
) -> tuple[float, float]:
    event_ids = unit_events.get(concern.unit_id) or tuple(ref.event_id for ref in concern.evidence)
    times: list[float] = []
    for event_id in event_ids:
        event = window.events.get(event_id)
        if event is not None and event.time is not None:
            times.append(event.time)
    if not times:
        return request_start, request_end
    start = min(times)
    end = max(times) + SPLUNK_EPOCH_PRECISION_S
    return start, min(request_end, end) if end > start else request_end


def apply_to_result(
    result: ReviewResult,
    window: IntakeResult,
    *,
    request_start: float,
    request_end: float,
    searcher: ReadOnlySearcher | None,
) -> tuple[StageReceipt, int]:
    """Annotate raised and suppressed concerns and report examined/resolved query counts."""
    concerns = [*result.concerns, *result.suppressed]
    examined = resolved = errors = 0
    counts = dict.fromkeys(DefenseResponse, 0)
    unit_events = {unit.unit.unit_id: unit.event_ids for unit in window.units}
    for concern in concerns:
        start, end = _concern_bounds(concern, window, request_start, request_end, unit_events)
        assessment = assess(
            concern,
            start=start,
            end=end,
            context_start=request_start,
            context_end=request_end,
            searcher=searcher,
        )
        concern.defense_response = assessment.response
        counts[assessment.response] += 1
        examined += assessment.queries_examined
        resolved += assessment.queries_resolved
        errors += assessment.errors
    return (
        StageReceipt(
            "defense.search",
            examined=examined,
            resolved=resolved,
            note=(
                f"concerns={len(concerns)}; covered={counts[DefenseResponse.COVERED]}; "
                f"missed={counts[DefenseResponse.MISSED]}; "
                f"near_miss={counts[DefenseResponse.NEAR_MISS]}; "
                f"indeterminate={counts[DefenseResponse.INDETERMINATE]}; "
                f"search errors={errors}; no rows persisted"
            ),
        ),
        errors,
    )
