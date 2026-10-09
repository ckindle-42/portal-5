"""review_eval.captures -- time-bound certification of immutable recorded exercises.

The capture corpus is private. Only hashes, bounded interval metadata, host tokens, and reason
counts leave this module; telemetry lines are inspected in memory and never copied to reports.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY
from portal.modules.security.core.exec_chain import SCENARIOS
from portal.modules.security.core.siem.capture_enrichment import (
    EXPECTED_SIGNALS,
    validate_capture_signals,
)

_ISO_TIME = re.compile(
    r"(?<!\d)(20\d{2}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?)"
)
_ISO_DATE_ONLY = re.compile(r"^(20\d{2}-\d{2}-\d{2})$")
_EPOCH = re.compile(r"(?<!\d)(\d{10,13}(?:\.\d+)?)(?!\d)")
_TIME_KEY = re.compile(
    r"(?:^|[\s,{<])([@_a-zA-Z][\w.@-]*)\s*[:=]\s*"
    r"(\"[^\"]*\"|'[^']*'|[^\s,}]+)",
    re.IGNORECASE,
)
_SYSLOG_PREFIX = re.compile(r"^\s*([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d\d?):(\d\d?):(\d\d?)")
_TIMESTAMP_KEYS = frozenset(
    {
        "time",
        "_time",
        "timestamp",
        "@timestamp",
        "eventtime",
        "timecreated",
        "datetime",
        "date",
        "epoch",
        "time_ms",
    }
)


class CaptureSelfTestError(RuntimeError):
    """The temporal capture validator failed one of its known-answer cases."""


@dataclass(frozen=True)
class CaptureValidation:
    valid: bool
    reasons: tuple[str, ...]
    technique_reasons: dict[str, tuple[str, ...]]
    interval: tuple[float, float] | None
    timed_in_interval: int
    timed_outside_interval: int
    time_unscoped_count: int
    unparseable_time: int


def _parse_epoch_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number / 1000.0 if number > 100_000_000_000 else number
    text = str(value).strip().strip("\"'")
    iso_match = _ISO_TIME.search(text)
    if iso_match:
        normalized = iso_match.group(1).replace(",", ".")
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        normalized = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", normalized)
        try:
            moment = datetime.fromisoformat(normalized)
        except ValueError:
            moment = None
        if moment is not None:
            return (moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment).timestamp()
    epoch_match = _EPOCH.fullmatch(text)
    if epoch_match:
        number = float(epoch_match.group(1))
        return number / 1000.0 if number > 100_000_000_000 else number
    return None


def _time_from_json(value: Any) -> float | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _TIMESTAMP_KEYS or any(
                part in normalized for part in ("timestamp", "timecreated", "eventtime", "epoch")
            ):
                parsed = _parse_epoch_value(item)
                if parsed is not None:
                    return parsed
        for item in value.values():
            parsed = _time_from_json(item)
            if parsed is not None:
                return parsed
    elif isinstance(value, list):
        for item in value:
            parsed = _time_from_json(item)
            if parsed is not None:
                return parsed
    return None


def _syslog_time(line: str, interval: tuple[float, float]) -> float | None:
    """Resolve the yearless Linux syslog prefix against its recorded capture interval."""
    match = _SYSLOG_PREFIX.match(line)
    if not match:
        return None
    month, day, hour, minute, second = match.groups()
    start, end = interval
    start_year = datetime.fromtimestamp(start, UTC).year
    end_year = datetime.fromtimestamp(end, UTC).year
    candidates: list[float] = []
    for year in range(start_year - 1, end_year + 2):
        try:
            moment = datetime.strptime(
                f"{year} {month} {day} {hour}:{minute}:{second}", "%Y %b %d %H:%M:%S"
            ).replace(tzinfo=UTC)
        except ValueError:
            continue
        candidates.append(moment.timestamp())
    if not candidates:
        return None
    inside = [candidate for candidate in candidates if start <= candidate <= end]
    if inside:
        return min(inside)
    return min(candidates, key=lambda candidate: min(abs(candidate - start), abs(candidate - end)))


def event_time(
    line: str,
    *,
    source: str | None = None,
    interval: tuple[float, float] | None = None,
) -> float | None:
    """Extract event time from named fields or the timestamp prefix of known event formats.

    ISO timestamps are accepted at the start of a record, where the recorded sources place
    their event time. Yearless month/day prefixes are accepted only for Linux syslog and are
    resolved against that capture's interval. Dates embedded later in payload text do not count.
    """
    try:
        decoded = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        decoded = None
    if decoded is not None:
        parsed = _time_from_json(decoded)
        if parsed is not None:
            return parsed
    for match in _TIME_KEY.finditer(line):
        key = match.group(1).strip().lower()
        if key not in _TIMESTAMP_KEYS and not any(
            part in key for part in ("timestamp", "timecreated", "eventtime", "epoch")
        ):
            continue
        parsed = _parse_epoch_value(match.group(2))
        if parsed is not None:
            return parsed
    prefix = line.lstrip(' \t["')
    iso_match = _ISO_TIME.match(prefix)
    if iso_match:
        parsed = _parse_epoch_value(iso_match.group(1))
        if parsed is not None:
            return parsed
    if source == "linux:syslog" and interval is not None:
        return _syslog_time(line, interval)
    return None


def _date_only_bounds(value: Any) -> tuple[float, float] | None:
    text = str(value).strip().strip("\"'")
    match = _ISO_DATE_ONLY.fullmatch(text)
    if not match:
        return None
    try:
        day_start = datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC).timestamp()
    except ValueError:
        return None
    return day_start, day_start + 86_400 - 0.000_001


def _date_bounds_from_json(value: Any) -> tuple[float, float] | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _TIMESTAMP_KEYS or any(
                part in normalized for part in ("timestamp", "timecreated", "eventtime", "epoch")
            ):
                bounds = _date_only_bounds(item)
                if bounds is not None:
                    return bounds
        for item in value.values():
            bounds = _date_bounds_from_json(item)
            if bounds is not None:
                return bounds
    elif isinstance(value, list):
        for item in value:
            bounds = _date_bounds_from_json(item)
            if bounds is not None:
                return bounds
    return None


def event_time_bounds(
    line: str,
    *,
    source: str | None = None,
    interval: tuple[float, float] | None = None,
) -> tuple[float, float] | None:
    """Return event-time precision bounds; date-only source fields remain day-wide."""
    exact = event_time(line, source=source, interval=interval)
    if exact is not None:
        return exact, exact
    try:
        decoded = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        decoded = None
    if decoded is not None:
        bounds = _date_bounds_from_json(decoded)
        if bounds is not None:
            return bounds
    for match in _TIME_KEY.finditer(line):
        key = match.group(1).strip().lower()
        if key not in _TIMESTAMP_KEYS and not any(
            part in key for part in ("timestamp", "timecreated", "eventtime", "epoch")
        ):
            continue
        bounds = _date_only_bounds(match.group(2))
        if bounds is not None:
            return bounds
    prefix = line.lstrip(' \t["')
    date_match = re.match(r"^(20\d{2}-\d{2}-\d{2})(?=$|\s)", prefix)
    return _date_only_bounds(date_match.group(1)) if date_match else None


def _interval(capture: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        start = float(capture["collected_since_epoch"])
        end = float(capture["captured_at"])
    except (KeyError, TypeError, ValueError):
        return None
    return (start, end) if end >= start else None


def _filter_telemetry(
    telemetry: Any, interval: tuple[float, float] | None
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]], int, int, int]:
    inside: dict[str, list[str]] = {}
    outside: dict[str, list[str]] = {}
    unscoped: dict[str, list[str]] = {}
    outside_count = 0
    unscoped_count = 0
    unparseable_count = 0
    if interval is None or not isinstance(telemetry, Mapping):
        return inside, outside, unscoped, outside_count, unscoped_count, unparseable_count
    start, end = interval
    for source, lines in telemetry.items():
        if not isinstance(lines, list):
            continue
        for line in lines:
            text = str(line)
            bounds = event_time_bounds(text, source=str(source), interval=interval)
            if bounds is None:
                unparseable_count += 1
            elif start <= bounds[0] and bounds[1] <= end:
                inside.setdefault(str(source), []).append(text)
            elif bounds[1] < start or bounds[0] > end:
                outside.setdefault(str(source), []).append(text)
                outside_count += 1
            else:
                unscoped.setdefault(str(source), []).append(text)
                unscoped_count += 1
    return inside, outside, unscoped, outside_count, unscoped_count, unparseable_count


def _signal_reasons(
    scenario: str,
    inside: Mapping[str, list[str]],
    outside: Mapping[str, list[str]],
    unscoped: Mapping[str, list[str]],
    all_telemetry: Mapping[str, list[str]],
    *,
    schema_version: Any,
    episode_id: Any,
) -> tuple[dict[str, tuple[str, ...]], bool]:
    validation = validate_capture_signals(scenario, dict(inside))
    outside_validation = validate_capture_signals(scenario, dict(outside))
    unscoped_validation = validate_capture_signals(scenario, dict(unscoped))
    all_validation = validate_capture_signals(scenario, dict(all_telemetry))
    found = set(validation.get("found") or [])
    missing = set(validation.get("missing") or [])
    unchecked = set(validation.get("unchecked") or [])
    outside_found = set(outside_validation.get("found") or [])
    unscoped_found = set(unscoped_validation.get("found") or [])
    all_found = set(all_validation.get("found") or [])
    declared = tuple(
        str(item) for item in SCENARIOS.get(scenario, {}).get("detect_ground_truth", [])
    )
    result: dict[str, tuple[str, ...]] = {}
    for technique in declared:
        reasons: set[str] = set()
        if technique in unchecked:
            reasons.add("NO_SIGNAL_RULE")
        elif technique in missing:
            reasons.add("SIGNAL_MISSING_IN_INTERVAL")
        elif technique not in found:
            reasons.add("SIGNAL_NOT_CHECKED")
        if technique in missing and technique in outside_found:
            reasons.add("SIGNAL_PRESENT_ONLY_OUTSIDE_INTERVAL")
        if technique in missing and technique in unscoped_found:
            reasons.add("SIGNAL_EVENT_TIME_PRECISION_EXCEEDS_INTERVAL")
        if (
            technique in missing
            and technique in all_found
            and technique not in (outside_found | unscoped_found)
        ):
            reasons.add("SIGNAL_PRESENT_WITHOUT_EVENT_TIMESTAMP")
        if schema_version != 2:
            reasons.add("LEGACY_CAPTURE_UNSCOPED")
        if not episode_id:
            reasons.add("MISSING_EPISODE_ID")
        result[technique] = tuple(sorted(reasons))
    return result, bool(validation.get("valid"))


def validate_capture(capture: Mapping[str, Any]) -> CaptureValidation:
    """Validate integrity and technique signals using only events inside the recorded interval."""
    interval = _interval(capture)
    (
        inside,
        outside,
        unscoped,
        outside_count,
        unscoped_count,
        unparseable_count,
    ) = _filter_telemetry(capture.get("telemetry"), interval)
    reasons: set[str] = set()
    if interval is None:
        reasons.add("INVALID_EXERCISE_INTERVAL")
    if not any(inside.values()):
        reasons.add("NO_TIMED_EVENTS_IN_INTERVAL")
    if capture.get("schema_version") != 2:
        reasons.add("LEGACY_CAPTURE_UNSCOPED")
    if not capture.get("episode_id"):
        reasons.add("MISSING_EPISODE_ID")
    original_telemetry = capture.get("telemetry")
    if not isinstance(original_telemetry, Mapping) or not any(
        isinstance(lines, list) and lines for lines in original_telemetry.values()
    ):
        reasons.add("NO_OBSERVED_TELEMETRY")

    all_telemetry = {
        str(source): [str(line) for line in lines]
        for source, lines in (
            original_telemetry.items() if isinstance(original_telemetry, Mapping) else []
        )
        if isinstance(lines, list)
    }
    technique_reasons, signals_valid = _signal_reasons(
        str(capture.get("scenario") or ""),
        inside,
        outside,
        unscoped,
        all_telemetry,
        schema_version=capture.get("schema_version"),
        episode_id=capture.get("episode_id"),
    )
    for per_technique in technique_reasons.values():
        reasons.update(per_technique)
    if not signals_valid:
        reasons.add("CAPTURE_GROUND_TRUTH_INVALID")
    return CaptureValidation(
        valid=not reasons,
        reasons=tuple(sorted(reasons)),
        technique_reasons=technique_reasons,
        interval=interval,
        timed_in_interval=sum(len(lines) for lines in inside.values()),
        timed_outside_interval=outside_count,
        time_unscoped_count=unscoped_count,
        unparseable_time=unparseable_count,
    )


def _known_answer_fixture() -> tuple[dict[str, Any], str]:
    for scenario, definition in sorted(SCENARIOS.items()):
        techniques = tuple(str(item) for item in definition.get("detect_ground_truth", []))
        if len(techniques) != 1:
            continue
        signal = EXPECTED_SIGNALS.get(techniques[0])
        if signal and signal[1]:
            source, lines = signal
            start = 1_700_000_000.0
            end = start + 60.0
            return (
                {
                    "scenario": scenario,
                    "schema_version": 2,
                    "episode_id": "review-capture-selftest",
                    "collected_since_epoch": start,
                    "captured_at": end,
                    "telemetry": {source: [f"{lines[0]} TimeCreated={start + 10.0:.0f}"]},
                },
                source,
            )
    raise CaptureSelfTestError("no single-technique known-answer capture fixture is available")


def run_known_answer_selftest() -> dict[str, Any]:
    """Require signal-present PASS and removed, shifted, and empty FAIL before store access."""
    fixture, source = _known_answer_fixture()
    telemetry = fixture["telemetry"]
    positive = validate_capture(fixture)
    removed = {**fixture, "telemetry": {source: []}}
    removed_result = validate_capture(removed)
    line = str(telemetry[source][0])
    shifted_time = float(fixture["captured_at"]) + 1.0
    shifted_line = re.sub(r"TimeCreated=\d+(?:\.\d+)?", f"TimeCreated={shifted_time:.0f}", line)
    shifted = {**fixture, "telemetry": {source: [shifted_line]}}
    shifted_result = validate_capture(shifted)
    empty = {**fixture, "telemetry": {}}
    empty_result = validate_capture(empty)
    cases = {
        "signal_present": positive.valid,
        "signal_removed": not removed_result.valid,
        "events_shifted_outside_interval": not shifted_result.valid,
        "empty_capture": not empty_result.valid,
    }
    if not all(cases.values()):
        raise CaptureSelfTestError(f"capture validator self-test failed: {cases}")
    fixture_hash = hashlib.sha256(
        json.dumps(
            {
                "scenario": fixture["scenario"],
                "source": source,
                "technique": next(iter(positive.technique_reasons)),
                "cases": cases,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return {"passed": True, "cases": cases, "fixture_sha256": fixture_hash}


def certify_capture_store(
    capture_dir: Path,
    *,
    stamp_digest: str,
    output: Path | None = None,
) -> dict[str, Any]:
    """Self-test first, then validate the whole store and persist a non-telemetry admission manifest."""
    selftest = run_known_answer_selftest()
    files = sorted(capture_dir.glob("*.json"))
    technique_histograms: dict[str, Counter[str]] = defaultdict(Counter)
    admitted: list[dict[str, Any]] = []
    rejected = 0
    file_digest = hashlib.sha256()
    for path in files:
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        file_digest.update(path.name.encode("utf-8"))
        file_digest.update(digest.encode("ascii"))
        try:
            capture = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            rejected += 1
            technique_histograms["<unknown>"]["MALFORMED_CAPTURE_JSON"] += 1
            continue
        if not isinstance(capture, Mapping):
            rejected += 1
            technique_histograms["<unknown>"]["CAPTURE_NOT_OBJECT"] += 1
            continue
        result = validate_capture(capture)
        if result.valid:
            scenario = str(capture.get("scenario") or "")
            techniques = tuple(
                str(item) for item in SCENARIOS.get(scenario, {}).get("detect_ground_truth", [])
            )
            known_techniques = {entry.technique for entry in BOTS_ANSWER_KEY}
            truth_class = {
                technique: "cousin" if technique in known_techniques else "novel"
                for technique in techniques
            }
            start, end = result.interval or (0.0, 0.0)
            host = str(capture.get("target_host") or "")
            host_token = hashlib.sha256(f"{stamp_digest}|{host}".encode()).hexdigest()[:16]
            admitted.append(
                {
                    "capture_id": path.stem,
                    "capture_sha256": digest,
                    "scenario": scenario,
                    "techniques": list(techniques),
                    "truth_class_by_technique": truth_class,
                    "interval": {"start_epoch": start, "end_epoch": end},
                    "host_token": host_token,
                    "timed_events": result.timed_in_interval,
                    "time_unscoped_events": result.time_unscoped_count,
                }
            )
        else:
            rejected += 1
            for technique, reasons in result.technique_reasons.items():
                for reason in reasons or result.reasons:
                    technique_histograms[technique][reason] += 1
            if not result.technique_reasons:
                for reason in result.reasons:
                    technique_histograms["<unknown>"][reason] += 1
    payload: dict[str, Any] = {
        "schema": "review.capture-admission.v1",
        "stamp_digest": stamp_digest,
        "capture_store_sha256": file_digest.hexdigest(),
        "capture_store_file_count": len(files),
        "admitted_count": len(admitted),
        "rejected_count": rejected,
        "admitted": admitted,
        "rejection_reason_histogram_by_technique": {
            technique: dict(sorted(counts.items()))
            for technique, counts in sorted(technique_histograms.items())
        },
        "selftest": selftest,
        "raw_telemetry_persisted": False,
    }
    payload["admission_manifest_sha256"] = hashlib.sha256(
        json.dumps(admitted, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return payload
