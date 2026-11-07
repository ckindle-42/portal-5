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
* entries that declare the same entity set as another entry;
* for an entry with more than one entity, whether they ever appear together in one event of the
  declared sourcetypes, outside Portal-written sources (D-T11 matches an entry's entities with AND).

Entities are resolved against indexed term metadata (``TERM()`` -- the full entity term when the
index holds it, otherwise its major tokens ANDed) and never through a search-time ``sourcetype=``
field: BOTS corpora rename ``wineventlog:*`` at search time, which is exactly what made this audit
report an entity absent from a sourcetype while its own elsewhere map showed it there. An internal
consistency check turns that contradiction into its own finding instead of an absence verdict.

It decides nothing and edits nothing. Raw telemetry is never read or written.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

REPO = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("PORTAL_DATA_ROOT", str(Path.home() / "AI_Output" / "portal-data")))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY  # noqa: E402
from portal.modules.security.core.bully.corpus_bed import AnswerKeyEntry  # noqa: E402
from portal.modules.security.core.review.window import SplunkWindowSource  # noqa: E402
from portal.modules.security.core.review_eval import bots_truth_key  # noqa: E402

PORTAL_SOURCE_PREFIX = "portal5:"


class Search(Protocol):
    def iter_post(self, search: str, start: float, end: float) -> Iterable[Mapping[str, Any]]: ...


def _q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class Probe:
    """Read-only aggregate queries over indexed metadata. Preview rows precede final ones,
    so the last row per key wins."""

    def __init__(self, source: Search) -> None:
        self.source = source
        self._presence: dict[tuple[str, str], dict[str, int]] = {}
        self._forms: dict[tuple[str, str], str] = {}

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
        form = self._form(index, entity)
        if not form:
            return {}
        rows = self._keyed(
            f"| tstats count where index={index} sourcetype={_q(sourcetype)} {form}"
            " by _time span=1d",
            "_time",
        )
        return {key[0]: count for key, count in rows.items()}

    def joint_events(self, index: str, sourcetype: str, entities: Iterable[str]) -> int:
        forms = " ".join(form for form in (self._form(index, e) for e in entities) if form)
        if not forms:
            return 0
        rows = self._rows(
            f"| tstats count where index={index} sourcetype={_q(sourcetype)}"
            f' NOT source="{PORTAL_SOURCE_PREFIX}*" {forms}'
        )
        return int(float(str(rows[-1].get("count", 0)))) if rows else 0

    def entity_elsewhere(self, index: str, entity: str) -> dict[str, int]:
        return dict(self._presence_map(index, entity))

    def _presence_map(self, index: str, entity: str) -> dict[str, int]:
        """Resolve the entity's metadata term form and where it lives, once per (index, entity).

        The full entity is tried as a ``TERM()`` first; when the index holds none of it and the
        entity spans major breakers (``BSTOLL-L``, ``bstoll@froth.ly``), its alphanumeric tokens
        are tried ANDed -- verified per entity against the live index, and upper-bounding real
        presence for the token form.
        """
        key = (index, entity)
        if key not in self._presence:
            chosen = ""
            presence: dict[str, int] = {}
            candidates = [f"TERM({_q(entity)})"]
            tokens = re.findall(r"[A-Za-z0-9]+", entity)
            if len(tokens) > 1:
                candidates.append(" ".join(f"TERM({_q(t)})" for t in tokens))
            for candidate in candidates:
                rows = self._keyed(
                    f"| tstats count where index={index} {candidate} by sourcetype", "sourcetype"
                )
                if rows:
                    chosen = candidate
                    presence = {k[0]: count for k, count in rows.items()}
                    break
            self._forms[key] = chosen
            self._presence[key] = dict(sorted(presence.items(), key=lambda kv: -kv[1]))
        return self._presence[key]

    def _form(self, index: str, entity: str) -> str:
        self._presence_map(index, entity)
        return self._forms[(index, entity)]


def _record_absence(
    problems: list[str],
    entity: str,
    entities: dict[str, Any],
    sourcetypes: Iterable[str],
    elsewhere: Mapping[str, int],
) -> None:
    """Absence must never contradict the elsewhere map: when the map names a declared
    sourcetype with events, the verdict is recorded as that contradiction instead."""
    contradicted = sorted(st for st in sourcetypes if elsewhere.get(st, 0) > 0)
    if contradicted:
        problems.append(f"entity_metadata_contradiction:{entity}:" + ",".join(contradicted))
    else:
        problems.append(f"entity_absent_in_declared_sourcetypes:{entity}")
    entities[entity]["elsewhere"] = dict(sorted(elsewhere.items(), key=lambda kv: -kv[1])[:5])


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
            _record_absence(
                problems,
                entity,
                entities,
                entry.sourcetypes,
                probe.entity_elsewhere(entry.dataset, entity),
            )
        elif len(sensor_days) > 1 and sensor_days <= set(days):
            problems.append(f"entity_on_every_sensor_day:{entity}")
    joint = None
    if len(entry.entities) > 1 and all(e["events_in_declared"] for e in entities.values()):
        joint = sum(
            probe.joint_events(entry.dataset, sourcetype, entry.entities)
            for sourcetype in entry.sourcetypes
        )
        if not joint:
            problems.append("entities_never_share_an_event")
    if duplicates:
        problems.append("same_entity_set_as:" + ",".join(duplicates))
    return {
        "dataset": entry.dataset,
        "technique": entry.technique,
        "sourcetypes": sourcetypes,
        "entities": entities,
        "sensor_days": len(sensor_days),
        "joint_events": joint,
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
        "--key", choices=("bots_answer_key", "bots_truth_key"), default="bots_answer_key"
    )
    parser.add_argument(
        "--out", type=Path, default=DATA_ROOT / "reports" / "review_eval" / "truth_audit"
    )
    args = parser.parse_args(argv)
    entries = (
        [entry.answer_key_entry() for entry in bots_truth_key.load()]
        if args.key == "bots_truth_key"
        else list(BOTS_ANSWER_KEY)
    )
    doc = audit(entries, Probe(SplunkWindowSource(timeout_seconds=args.timeout_seconds)))
    doc["key"] = args.key
    args.out.mkdir(parents=True, exist_ok=True)
    name = "answer_key_audit" if args.key == "bots_answer_key" else "truth_key_audit"
    (args.out / f"{name}.json").write_text(
        json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8"
    )
    (args.out / f"{name}.md").write_text(render(doc), encoding="utf-8")
    print(json.dumps({"entries": doc["entry_count"], "usable": doc["usable_entry_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
