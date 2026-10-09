"""Bounded, read-only pivots over exactly the source/time scope of one window."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .intake import event_id_for, render_event
from .wall import assert_label_free
from .window import SourceSpec, normalize_splunk_record

MAX_TERM_CHARS = 256
MAX_PIVOT_RESULTS = 40


class PivotSource(Protocol):
    partition_seconds: int

    def _post(self, search: str, start: float, end: float) -> list[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class PivotReceipt:
    term_sha256: str
    partitions_examined: int
    expected: int
    fetched: int
    shown: int
    complete: bool
    truncated: bool
    degraded: str = ""


class ToolBox:
    """A model-requested bare-term search, partition checked like the initial window."""

    def __init__(
        self,
        source: PivotSource,
        *,
        sources: Sequence[SourceSpec],
        start: float,
        end: float,
        known_event_ids: Sequence[str] = (),
        max_results: int = MAX_PIVOT_RESULTS,
    ) -> None:
        if end <= start:
            raise ValueError("pivot end must be greater than start")
        if source.partition_seconds <= 0:
            raise ValueError("pivot partition duration must be positive")
        self.source = source
        self.sources = tuple(sorted(sources, key=lambda item: item.source_id))
        self.start = start
        self.end = end
        self.max_results = max_results
        self._seen = set(known_event_ids)
        self._receipts: list[PivotReceipt] = []

    @property
    def receipts(self) -> tuple[PivotReceipt, ...]:
        return tuple(self._receipts)

    def pivot(self, term: str) -> Sequence[tuple[str, str]]:
        normalized = term.strip()
        term_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if not normalized:
            self._receipts.append(PivotReceipt(term_digest, 0, 0, 0, 0, False, False, "empty term"))
            return []
        if len(normalized) > MAX_TERM_CHARS or "\x00" in normalized:
            self._receipts.append(
                PivotReceipt(term_digest, 0, 0, 0, 0, False, False, "term outside bound")
            )
            return []

        result: list[tuple[float, str, str]] = []
        partitions = expected_total = fetched_total = 0
        cursor = self.start
        while cursor < self.end:
            boundary = min(cursor + self.source.partition_seconds, self.end)
            for spec in self.sources:
                partitions += 1
                literal = _quote(normalized)
                search = (
                    f"search index={_quote(spec.index)} "
                    f"sourcetype={_quote(spec.sourcetype)} {literal}"
                )
                try:
                    count_rows = self.source._post(f"{search} | stats count", cursor, boundary)
                    rows = self.source._post(search, cursor, boundary)
                    if len(count_rows) != 1 or "count" not in count_rows[0]:
                        raise ValueError("pivot count query returned no single count")
                    expected = int(str(count_rows[0]["count"]))
                    if expected < 0:
                        raise ValueError("pivot count query returned a negative count")
                    expected_total += expected
                    fetched_total += len(rows)
                    if expected != len(rows):
                        raise ValueError(
                            f"{spec.source_id} [{cursor:g}, {boundary:g}): "
                            f"expected {expected}, fetched {len(rows)}"
                        )
                    for row in rows:
                        record = normalize_splunk_record(spec, row)
                        assert_label_free(record, where=f"pivot:{spec.source_id}")
                        event_id = event_id_for(spec.source_id, record)
                        if event_id in self._seen:
                            continue
                        result.append((float(record["_time"]), event_id, render_event(record)))
                except Exception as exc:  # fail closed and receipt source/count failures
                    detail = (
                        str(exc)
                        if isinstance(exc, (TypeError, ValueError, KeyError))
                        else type(exc).__name__
                    )
                    self._receipts.append(
                        PivotReceipt(
                            term_digest,
                            partitions,
                            expected_total,
                            fetched_total,
                            0,
                            False,
                            False,
                            detail,
                        )
                    )
                    return []
            cursor = boundary

        result.sort(key=lambda item: (item[0], item[1]))
        truncated = len(result) > self.max_results
        shown = result[: self.max_results]
        self._seen.update(event_id for _time, event_id, _text in shown)
        self._receipts.append(
            PivotReceipt(
                term_digest,
                partitions,
                expected_total,
                fetched_total,
                len(shown),
                True,
                truncated,
            )
        )
        return [(event_id, text) for _time, event_id, text in shown]


def _quote(value: str) -> str:
    """Quote a literal Splunk search value so model text cannot become SPL syntax."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
