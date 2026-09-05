"""Two independent clocks (P2 / DESIGN_COMPLIANCE_REASONING_V2 §5.1).

``valid_from <= valid_at < valid_to`` — legal/operational effect: what applied
at a given moment, independent of when the system learned about it.

``recorded_from <= known_at < recorded_to`` — system knowledge: what the store
believed at a given moment, independent of what was actually true. A
correction closes the prior row's ``recorded_to`` and inserts a new row; the
prior row is NEVER mutated in place, so "what did we believe on date X" stays
replayable after the correction.

Both are half-open intervals: the start is inclusive, the end is exclusive.
An open end (``None``) means "still current" — but an open ``valid_from`` is
never assumed; a missing start means the fact is UNKNOWN, not "always true"
(F02). A missing ``recorded_from`` is a bug — every row must know when the
system started believing it.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ISO_DATETIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?")


def parse_iso_date(value: str, *, field: str = "date") -> str:
    """Validate an ISO-8601 calendar date. Raises rather than silently
    defaulting — an unparseable date must never resolve to "today"."""
    if not isinstance(value, str) or not _ISO_DATE_RE.fullmatch(value or ""):
        raise ValueError(f"invalid ISO date for {field}: {value!r} (expected YYYY-MM-DD)")
    try:
        datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid ISO date for {field}: {value!r}") from exc
    return value


def parse_iso_datetime(value: str, *, field: str = "timestamp") -> str:
    if not isinstance(value, str) or not _ISO_DATETIME_RE.fullmatch(value or ""):
        raise ValueError(f"invalid ISO timestamp for {field}: {value!r}")
    return value


def now_iso() -> str:
    """Microsecond precision — two review decisions in rapid succession (a
    concurrency test, an import loop) must not collide onto the same
    recorded-time timestamp and corrupt as-known replay ordering."""
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class Interval:
    """A half-open interval ``[start, end)``. ``start`` MUST be known;
    ``end`` of ``None`` means open-ended (still current)."""

    start: str
    end: str | None = None

    def __post_init__(self) -> None:
        if not self.start:
            raise ValueError(
                "Interval.start is required — an unknown start is not an open interval"
            )

    def contains(self, at: str) -> bool:
        if at < self.start:
            return False
        return not (self.end and self.end <= at)

    def overlaps(self, other: Interval) -> bool:
        if self.end and other.start >= self.end:
            return False
        return not (other.end and self.start >= other.end)


def is_effective_at(valid_from: str | None, valid_to: str | None, valid_at: str) -> bool:
    """Interval-based validity check (F01): unlike a lifecycle-label gate,
    this only needs the interval — a RETIRED label does not exclude a node
    from a historical ``valid_at`` still inside its own interval. An unknown
    ``valid_from`` is never effective (F02) — unknown is not "always"."""
    if not valid_from:
        return False
    if valid_from > valid_at:
        return False
    return not (valid_to and valid_to <= valid_at)
