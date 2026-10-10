#!/usr/bin/env python3
"""Audit the BOTS answer key against the indexed corpus before any truth is derived from it.

Every truth item since T1 has come from ``BOTS_ANSWER_KEY``, and nothing ever checked that its
entries can be found where they say they are. This reads aggregates only (``tstats`` and
``stats count by day``) and reports, per entry:

* whether each declared sourcetype exists in the index, and how much of it Portal wrote;
* whether each entity appears in the declared sourcetypes, and, if not, where it does appear;
* the UTC days each entity appears on in the declared sourcetypes, beside the days those
  sourcetypes hold data at all (an entity present whenever its sensor reports is background, not
  an attack marker);
* entries that declare the same entity set as another entry.

It decides nothing and edits nothing. Raw telemetry is never read or written.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY  # noqa: E402
from portal.modules.security.core.bully.corpus_bed import AnswerKeyEntry  # noqa: E402
from portal.modules.security.core.review.window import SplunkWindowSource  # noqa: E402

PORTAL_SOURCE_PREFIX = "portal5:"


class Search(Protocol):
    def iter_post(self, search: str, start: float, end: float) -> Iterable[Mapping[str, Any]]: ...


def _q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class Probe:
    """Read-only aggregate queries. Preview rows precede final ones, so the last row per key wins."""

    def __init__(self, source: Search) -> None:
        self.source = source

    def _rows(self, search: str) -> list[Mapping[str, Any]]:
        return list(self.source.iter_post(search, 0.0, time.time() + 1.0))

    def _keyed(self, search: str, *fields: str) -> dict[tuple[str, ...], int]:
        out: dict[tuple[str, ...], int] = {}
        for row in self._rows(search):
            if row.get("count") is None or any(row.get(f) is None for f in fields):
                continue
            out[tuple(str(row[f]) for f in fields)] = int(float(str(row["count"])))
        return out

    def sourcetype_days(self, index: str, sourcetype: str) -> set[str]:
        rows = self._keyed(
            f"| tstats count where index={index} sourcetype={_q(sourcetype)} by _time span=1d",
            "_time",
        )
        return {str(int(float(key[0]))) for key in rows}

    def sourcetype_sources(self, index: str, sourcetype: str) -> dict[str, int]:
        rows = self._keyed(
            f"| tstats count where index={index} sourcetype={_q(sourcetype)} by source", "source"
        )
        return {key[0]: count for key, count in rows.items()}

    def entity_days(self, index: str, sourcetype: str, entity: str) -> dict[str, int]:
        rows = self._keyed(
            f"search index={index} sourcetype={_q(sourcetype)} {_q(entity)}"
            " | eval day=floor(_time/86400)*86400 | stats count as count by day",
            "day",
        )
        return {key[0]: count for key, count in rows.items()}

    def entity_elsewhere(self, index: str, entity: str) -> dict[str, int]:
        rows = self._keyed(
            f"| tstats count where index={index} TERM({_q(entity)}) by sourcetype", "sourcetype"
        )
        return {key[0]: count for key, count in rows.items()}


def audit_entry(entry: AnswerKeyEntry, probe: Probe, duplicates: list[str]) -> dict[str, Any]:
    problems: list[str] = []
    sourcetypes: dict[str, Any] = {}
    sensor_days = {
        day
        for sourcetype in entry.sourcetypes
        for day in probe.sourcetype_days(entry.dataset, sourcetype)
    }
    for sourcetype in entry.sourcetypes:
        sources = probe.sourcetype_sources(entry.dataset, sourcetype)
        total = sum(sources.values())
        portal = sum(c for s, c in sources.items() if s.startswith(PORTAL_SOURCE_PREFIX))
        sourcetypes[sourcetype] = {"events": total, "portal_written_events": portal}
        if total == 0:
            problems.append(f"sourcetype_absent:{sourcetype}")
        elif portal == total:
            problems.append(f"sourcetype_only_portal_written:{sourcetype}")
    entities: dict[str, Any] = {}
    for entity in entry.entities:
        days: dict[str, int] = {}
        for sourcetype in entry.sourcetypes:
            for day, count in probe.entity_days(entry.dataset, sourcetype, entity).items():
                key = str(int(float(day)))
                days[key] = days.get(key, 0) + count
        entities[entity] = {
            "events_in_declared": sum(days.values()),
            "days_in_declared": len(days),
            "first_day": min(days, key=float) if days else None,
            "last_day": max(days, key=float) if days else None,
        }
        if not days:
            problems.append(f"entity_absent_in_declared_sourcetypes:{entity}")
            entities[entity]["elsewhere"] = dict(
                sorted(
                    probe.entity_elsewhere(entry.dataset, entity).items(), key=lambda kv: -kv[1]
                )[:5]
            )
        elif len(sensor_days) > 1 and sensor_days <= set(days):
            problems.append(f"entity_on_every_sensor_day:{entity}")
    if duplicates:
        problems.append("same_entity_set_as:" + ",".join(duplicates))
    return {
        "dataset": entry.dataset,
        "technique": entry.technique,
        "sourcetypes": sourcetypes,
        "entities": entities,
        "sensor_days": len(sensor_days),
        "problems": problems,
        "usable": not problems,
    }


def audit(entries: Iterable[AnswerKeyEntry], probe: Probe) -> dict[str, Any]:
    entries = list(entries)
    keys = [(e.dataset, frozenset(x.casefold() for x in e.entities)) for e in entries]
    rows = []
    for i, entry in enumerate(entries):
        dupes = [
            f"{e.dataset}:{e.technique}"
            for j, e in enumerate(entries)
            if j != i and keys[j] == keys[i]
        ]
        rows.append(audit_entry(entry, probe, dupes))
    return {
        "entries": rows,
        "entry_count": len(rows),
        "usable_entry_count": sum(r["usable"] for r in rows),
        "raw_telemetry_persisted": False,
    }


def render(doc: Mapping[str, Any]) -> str:
    lines = [
        "# BOTS answer-key audit",
        "",
        f"{doc['usable_entry_count']} of {doc['entry_count']} entries have no problem.",
        "",
        "| dataset | technique | problems |",
        "|---|---|---|",
    ]
    for row in doc["entries"]:
        lines.append(
            f"| {row['dataset']} | {row['technique']} | {'; '.join(row['problems']) or 'none'} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument(
        "--out", type=Path, default=REPO / "reports" / "review_eval" / "truth_audit"
    )
    args = parser.parse_args(argv)
    doc = audit(BOTS_ANSWER_KEY, Probe(SplunkWindowSource(timeout_seconds=args.timeout_seconds)))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "answer_key_audit.json").write_text(
        json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8"
    )
    (args.out / "answer_key_audit.md").write_text(render(doc), encoding="utf-8")
    print(json.dumps({"entries": doc["entry_count"], "usable": doc["usable_entry_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
