"""Report model for ``portal trace``: hops, sections, and their renderings."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):  # noqa: UP042 — StrEnum requires 3.11+
    """Outcome of one live hop."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


@dataclass(frozen=True)
class Hop:
    """One observed value beside the value the repo says it should be."""

    name: str
    status: Status
    observed: str = ""
    expected: str = ""
    detail: str = ""


@dataclass
class Section:
    """One independently runnable section of the trace."""

    key: str
    title: str
    hops: list[Hop] = field(default_factory=list)


@dataclass
class TraceReport:
    """Every section the run produced."""

    sections: list[Section]
    elapsed_s: float
    head: str = ""

    def counts(self) -> dict[str, int]:
        tally = {status.value: 0 for status in Status}
        for section in self.sections:
            for hop in section.hops:
                tally[hop.status.value] += 1
        return tally

    @property
    def ok(self) -> bool:
        return self.counts()[Status.FAIL.value] == 0


def short(text: object, limit: int = 96) -> str:
    """One-line, length-bounded rendering of an observed value."""
    rendered = " ".join(str(text).split())
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"


def format_hop(hop: Hop) -> str:
    """``  PASS name  observed  expected …  | detail``."""
    line = f"  {hop.status.value:<4} {hop.name:<38} {hop.observed}"
    if hop.expected:
        line += f"  expected {hop.expected}"
    if hop.detail:
        line += f"  | {hop.detail}"
    return line.rstrip()


def hop_to_dict(hop: Hop) -> dict[str, Any]:
    return {
        "name": hop.name,
        "status": hop.status.value,
        "observed": hop.observed,
        "expected": hop.expected,
        "detail": hop.detail,
    }


def report_to_dict(report: TraceReport) -> dict[str, Any]:
    return {
        "head": report.head,
        "elapsed_s": round(report.elapsed_s, 2),
        "ok": report.ok,
        "counts": report.counts(),
        "sections": [
            {
                "key": section.key,
                "title": section.title,
                "hops": [hop_to_dict(hop) for hop in section.hops],
            }
            for section in report.sections
        ],
    }


def render_text(report: TraceReport) -> str:
    lines = [f"Portal trace  head={report.head or 'unknown'}"]
    for section in report.sections:
        lines.append("")
        lines.append(section.title)
        lines.extend(format_hop(hop) for hop in section.hops)
    tally = report.counts()
    lines.append("")
    lines.append(
        f"SUMMARY  PASS={tally['PASS']} FAIL={tally['FAIL']} WARN={tally['WARN']}"
        f"  ({report.elapsed_s:.1f}s)"
    )
    return "\n".join(lines)


def render_json(report: TraceReport) -> str:
    return json.dumps(report_to_dict(report), indent=2)
