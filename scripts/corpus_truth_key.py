#!/usr/bin/env python3
"""Build a 10-entry labelled_corpus answer key from attack_data labels.

Read-only Splunk aggregates. Entities come from corpus rarity and co-occurrence, not from prose.
The key records which item and which rule produced each entry. Raw events are not written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portal.modules.security.core.review.window import SplunkWindowSource  # noqa: E402
from portal.modules.security.core.review_eval.corpus_truth import (  # noqa: E402
    KEY_PATH,
    LEAK_MATCH,
    LEAK_WHERE,
    SELECTION_RULE,
    EntityCandidate,
    behaviour_spine,
    pair_score,
    rank_entity_pairs,
)
from scripts.corpus_ingest import load_manifest_catalog  # noqa: E402
from scripts.corpus_reingest import p5_item_id  # noqa: E402

INDEX = "labelled_corpus"
PUBLISHER = "attack_data"
TECHNIQUES = (
    "T1003.001",
    "T1059.001",
    "T1053.005",
    "T1547.001",
    "T1055",
    "T1112",
    "T1078",
    "T1021.002",
    "T1562.001",
    "T1110",
)
_DAY = 86_400
_ATTACK_ROOT = Path("/Volumes/data01/portal5_hunt/sources/attack_data")


@dataclass(frozen=True)
class CatalogItem:
    test_id: str
    p5_item: str
    techniques: frozenset[str]


def load_attack_items(root: Path) -> dict[str, CatalogItem]:
    """Join each attack_data directory to its data.yml techniques and p5_item id."""
    grouped: dict[str, set[str]] = {}
    for manifest in load_manifest_catalog(root):
        try:
            test_id = manifest.path.parent.relative_to(root).as_posix()
        except ValueError:
            continue
        grouped.setdefault(test_id, set()).update(manifest.techniques)
    return {
        test_id: CatalogItem(test_id, p5_item_id(PUBLISHER, test_id), frozenset(techniques))
        for test_id, techniques in grouped.items()
    }


def candidates_for(items: Mapping[str, CatalogItem], technique: str) -> list[CatalogItem]:
    """Items whose data.yml technique set is exactly this one technique."""
    chosen = [item for item in items.values() if item.techniques == frozenset({technique})]
    return sorted(chosen, key=lambda item: item.test_id)


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _count(row: Mapping[str, Any], field: str = "count") -> int:
    value = row.get(field)
    if value is None:
        return 0
    return int(float(str(value)))


class AggregateProbe:
    """Read-only aggregate export. Rows stay in memory and are not persisted."""

    def __init__(self, source: SplunkWindowSource) -> None:
        self.source = source
        self._terms: dict[str, int] = {}
        self._days: dict[tuple[str, str], int] = {}
        self._sensor_days: dict[str, int] = {}
        self._portal_only: dict[str, bool] = {}

    def rows(
        self, search: str, start: float = 0.0, end: float | None = None
    ) -> list[dict[str, Any]]:
        latest = time.time() + 1.0 if end is None else end
        return [dict(row) for row in self.source.iter_post(search, start, latest)]

    def term_counts(self, terms: Iterable[str]) -> dict[str, int]:
        ordered = list(dict.fromkeys(terms))
        pending = [term for term in ordered if term not in self._terms]
        for offset in range(0, len(pending), 15):
            self._fetch_term_chunk(pending[offset : offset + 15])
        return {term: self._terms.get(term, 0) for term in ordered}

    def _fetch_term_chunk(self, terms: Sequence[str]) -> None:
        searches = [
            f"| tstats count where index={INDEX} TERM({_quote(term)}) | eval entity={_quote(term)}"
            for term in terms
        ]
        search = searches[0]
        for extra in searches[1:]:
            search += f" | append [{extra}]"
        for row in self.rows(search):
            entity = str(row.get("entity", ""))
            if entity:
                self._terms[entity] = _count(row)
        for term in terms:
            self._terms.setdefault(term, 0)

    def sensor_days(self, sourcetype: str) -> int:
        if sourcetype not in self._sensor_days:
            self._sensor_days[sourcetype] = self._day_rows(sourcetype, None)
        return self._sensor_days[sourcetype]

    def entity_days(self, sourcetype: str, term: str) -> int:
        key = (sourcetype, term)
        if key not in self._days:
            self._days[key] = self._day_rows(sourcetype, term)
        return self._days[key]

    def _day_rows(self, sourcetype: str, term: str | None) -> int:
        clause = f" TERM({_quote(term)})" if term else ""
        rows = self.rows(
            f"| tstats count where index={INDEX} sourcetype={_quote(sourcetype)}{clause}"
            " by _time span=1d | stats count as days"
        )
        return _count(rows[-1], "days") if rows else 0

    def portal_only(self, sourcetype: str) -> bool:
        if sourcetype not in self._portal_only:
            rows = self.rows(
                f"| tstats count where index={INDEX} sourcetype={_quote(sourcetype)} by source"
            )
            total = 0
            portal = 0
            for row in rows:
                count = _count(row)
                total += count
                if str(row.get("source", "")).startswith("portal5:"):
                    portal += count
            self._portal_only[sourcetype] = total > 0 and portal == total
        return self._portal_only[sourcetype]

    def joint(self, sourcetype: str, host: str, artifact: str) -> int:
        rows = self.rows(
            f"| tstats count where index={INDEX} sourcetype={_quote(sourcetype)}"
            f' NOT source="portal5:*" TERM({_quote(host)}) TERM({_quote(artifact)})'
        )
        return _count(rows[-1]) if rows else 0


def _item_counts(probe: AggregateProbe, item_ids: Sequence[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for offset in range(0, len(item_ids), 40):
        chunk = item_ids[offset : offset + 40]
        predicate = " OR ".join(f"p5_item={item_id}" for item_id in chunk)
        rows = probe.rows(f"| tstats count where index={INDEX} ({predicate}) by p5_item")
        for row in rows:
            item_id = str(row.get("p5_item", ""))
            if item_id:
                found[item_id] = _count(row)
    return found


def _dominant_day(probe: AggregateProbe, item_id: str) -> int | None:
    rows = probe.rows(f"| tstats count where index={INDEX} p5_item={item_id} by _time span=1d")
    best_day: int | None = None
    best_count = -1
    for row in rows:
        if row.get("_time") is None:
            continue
        count = _count(row)
        day = int(float(str(row["_time"])))
        if count > best_count:
            best_count = count
            best_day = day
    return best_day


def _sourcetypes_on_day(probe: AggregateProbe, item_id: str, day: int) -> list[tuple[str, int]]:
    latest = day + _DAY
    rows = probe.rows(
        f"| tstats count where index={INDEX} p5_item={item_id} earliest={day} latest={latest}"
        " by sourcetype"
    )
    found = [
        (str(row["sourcetype"]), _count(row))
        for row in rows
        if row.get("sourcetype") is not None and _count(row) > 0
    ]
    return sorted(found, key=lambda item: -item[1])


def _pair_search(item_id: str, sourcetype: str, day: int) -> str:
    latest = day + _DAY
    return (
        f"search index={INDEX} p5_item={item_id} sourcetype={_quote(sourcetype)} "
        f"earliest={day} latest={latest} | {LEAK_WHERE} | "
        "eval host_entity=coalesce(Computer, dvc_nt_host, host) | "
        'rex field=_raw "(?i)<Computer>(?<host_xml>[^<]+)" | '
        "eval host_entity=coalesce(host_entity, host_xml) | "
        "eval artifact=mvappend(Image_File_Name, process_name) | "
        'rex field=_raw "(?i)<Data Name=.Image.>(?<image_xml>[^<]+)" | '
        'rex field=CommandLine "(?i)(?<script>[A-Za-z0-9_.\\\\-]+\\\\.ps1)" | '
        "eval artifact=mvdedup(mvappend(artifact, image_xml, script)) | "
        "mvexpand artifact | "
        'eval artifact=replace(artifact, ".*[\\\\/]", "") | '
        "where isnotnull(host_entity) AND isnotnull(artifact) AND len(host_entity)>2 "
        "AND len(artifact)>2 AND host_entity!=artifact | "
        "stats count as cooccur by host_entity artifact | sort 300 -cooccur"
    )


def _basename(value: str) -> str:
    return value.replace("\\", "/").rsplit("/", 1)[-1].strip()


def _clean_pairs(
    probe: AggregateProbe, item_id: str, sourcetype: str, day: int
) -> list[tuple[str, str, int]]:
    merged: dict[tuple[str, str], int] = {}
    rows = probe.rows(_pair_search(item_id, sourcetype, day), float(day), float(day + _DAY))
    for row in rows:
        host = str(row.get("host_entity", "")).strip()
        artifact = _basename(str(row.get("artifact", "")))
        cooccur = _count(row, "cooccur")
        if not host or not artifact or cooccur < 1 or artifact.casefold() == host.casefold():
            continue
        key = (host, artifact)
        merged[key] = merged.get(key, 0) + cooccur
    ranked = sorted(merged.items(), key=lambda item: -item[1])[:300]
    return [(host, artifact, count) for (host, artifact), count in ranked]


def _leak_totals(probe: AggregateProbe, item_id: str) -> tuple[int, int]:
    rows = probe.rows(
        f"search index={INDEX} p5_item={item_id} | "
        f"eval leaked=if({LEAK_MATCH}, 1, 0) | stats count sum(leaked) as leaked"
    )
    if not rows:
        return 0, 0
    return _count(rows[-1]), _count(rows[-1], "leaked")


def _sample_spine(
    probe: AggregateProbe, item_id: str, sourcetype: str, day: int
) -> tuple[str, ...]:
    latest = day + _DAY
    search = (
        f"search index={INDEX} p5_item={item_id} sourcetype={_quote(sourcetype)} "
        f"earliest={day} latest={latest} | {LEAK_WHERE} | head 15 | "
        "fields _raw EventCode EventID sourcetype"
    )
    return behaviour_spine(probe.rows(search, float(day), float(latest)), sourcetype)


def _candidates_for_pairs(
    probe: AggregateProbe,
    sourcetype: str,
    pairs: Sequence[tuple[str, str, int]],
    sensor_days: int,
) -> list[EntityCandidate]:
    hosts = [host for host, _artifact, _cooccur in pairs]
    artifacts = [artifact for _host, artifact, _cooccur in pairs]
    counts = probe.term_counts([*hosts, *artifacts])
    built: list[EntityCandidate] = []
    for host, artifact, cooccur in pairs:
        host_corpus = counts.get(host, 0)
        artifact_corpus = counts.get(artifact, 0)
        built.append(
            EntityCandidate(
                host,
                artifact,
                cooccur,
                host_corpus,
                artifact_corpus,
                _days_if_needed(probe, sourcetype, host, host_corpus, sensor_days),
                _days_if_needed(probe, sourcetype, artifact, artifact_corpus, sensor_days),
                host_corpus > 0,
                artifact_corpus > 0,
            )
        )
    return built


def _days_if_needed(
    probe: AggregateProbe, sourcetype: str, term: str, corpus_count: int, sensor_days: int
) -> int:
    if sensor_days <= 1 or corpus_count < sensor_days:
        return 0
    return probe.entity_days(sourcetype, term)


@dataclass(frozen=True)
class BuiltEntry:
    technique: str
    payload: dict[str, Any]
    seen: int
    excluded: int


def _payload(
    item: CatalogItem,
    technique: str,
    sourcetype: str,
    day: int,
    pair: EntityCandidate,
    joint: int,
    spine: tuple[str, ...],
    sensor_days: int,
) -> dict[str, Any]:
    return {
        "dataset": INDEX,
        "technique": technique,
        "behavioural_spine": list(spine),
        "entities": [pair.host, pair.artifact],
        "sourcetypes": [sourcetype],
        "confirmed_at": float(day),
        "p5_item": item.p5_item,
        "test_id": item.test_id,
        "dominant_day": day,
        "cooccurrence": pair.cooccurrence,
        "host_corpus": pair.host_corpus,
        "artifact_corpus": pair.artifact_corpus,
        "joint_events": joint,
        "sensor_days": sensor_days,
        "host_days": pair.host_days,
        "artifact_days": pair.artifact_days,
        "score": pair_score(pair),
        "why": (
            f"cooccur={pair.cooccurrence} host_corpus={pair.host_corpus} "
            f"artifact_corpus={pair.artifact_corpus} joint={joint} "
            f"score={pair_score(pair):.6g} sensor_days={sensor_days}"
        ),
    }


def _first_joint(
    probe: AggregateProbe,
    sourcetype: str,
    ranked: Sequence[EntityCandidate],
    used: set[frozenset[str]],
) -> tuple[EntityCandidate, int] | None:
    for pair in ranked:
        entity_set = frozenset({pair.host.casefold(), pair.artifact.casefold()})
        if entity_set in used:
            continue
        joint = probe.joint(sourcetype, pair.host, pair.artifact)
        if joint > 0:
            return pair, joint
    return None


def _from_sourcetype(
    probe: AggregateProbe,
    item: CatalogItem,
    technique: str,
    sourcetype: str,
    day: int,
    used: set[frozenset[str]],
) -> BuiltEntry | None:
    if probe.portal_only(sourcetype):
        return None
    pairs = _clean_pairs(probe, item.p5_item, sourcetype, day)
    if not pairs:
        return None
    sensor_days = probe.sensor_days(sourcetype)
    if sensor_days < 1:
        return None
    ranked = rank_entity_pairs(
        _candidates_for_pairs(probe, sourcetype, pairs, sensor_days), sensor_days, used
    )
    accepted = _first_joint(probe, sourcetype, ranked[:20], used)
    if accepted is None:
        return None
    pair, joint = accepted
    seen, excluded = _leak_totals(probe, item.p5_item)
    spine = _sample_spine(probe, item.p5_item, sourcetype, day)
    return BuiltEntry(
        technique,
        _payload(item, technique, sourcetype, day, pair, joint, spine, sensor_days),
        seen,
        excluded,
    )


def _from_item(
    probe: AggregateProbe,
    item: CatalogItem,
    technique: str,
    used: set[frozenset[str]],
) -> BuiltEntry | None:
    day = _dominant_day(probe, item.p5_item)
    if day is None:
        return None
    for sourcetype, _count in _sourcetypes_on_day(probe, item.p5_item, day):
        built = _from_sourcetype(probe, item, technique, sourcetype, day, used)
        if built is not None:
            return built
    return None


def _ranked_items(items: Sequence[CatalogItem], counts: Mapping[str, int]) -> list[CatalogItem]:
    present = [item for item in items if counts.get(item.p5_item, 0) > 0]
    return sorted(present, key=lambda item: (-counts.get(item.p5_item, 0), item.test_id))


def build_technique(
    probe: AggregateProbe,
    items: Sequence[CatalogItem],
    technique: str,
    counts: Mapping[str, int],
    used: set[frozenset[str]],
) -> tuple[BuiltEntry | None, str]:
    """Try the largest single-technique items until one pair passes the audit rules."""
    if not items:
        return None, "no_single_technique_item"
    ranked = _ranked_items(items, counts)
    if not ranked:
        return None, "no_indexed_events"
    for item in ranked[:8]:
        built = _from_item(probe, item, technique, used)
        if built is not None:
            return built, ""
    return None, "no_pair_passed_rarity_cooccurrence_and_term_rules"


def _remember(used: set[frozenset[str]], built: BuiltEntry) -> None:
    host, artifact = built.payload["entities"]
    used.add(frozenset({str(host).casefold(), str(artifact).casefold()}))


def _attack_commit(root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip()


def build_key(probe: AggregateProbe, root: Path) -> dict[str, Any]:
    catalog = load_attack_items(root)
    by_technique = {technique: candidates_for(catalog, technique) for technique in TECHNIQUES}
    counts = _item_counts(
        probe,
        [item.p5_item for items in by_technique.values() for item in items],
    )
    used: set[frozenset[str]] = set()
    entries: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    leak_by_technique: dict[str, dict[str, int]] = {}
    for technique in TECHNIQUES:
        built, reason = build_technique(probe, by_technique[technique], technique, counts, used)
        if built is None:
            failures.append({"technique": technique, "reason": reason})
            print(f"{technique} FAILED {reason}", file=sys.stderr)
            continue
        _remember(used, built)
        entries.append(built.payload)
        leak_by_technique[technique] = {
            "events_seen": built.seen,
            "events_excluded": built.excluded,
        }
        print(
            f"{technique} {built.payload['entities']} item={built.payload['p5_item']}",
            file=sys.stderr,
        )
    seen = sum(row["events_seen"] for row in leak_by_technique.values())
    excluded = sum(row["events_excluded"] for row in leak_by_technique.values())
    return {
        "provenance": {
            "index": INDEX,
            "publisher": PUBLISHER,
            "label_basis": "data_yml",
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "rule": SELECTION_RULE,
            "attack_data_root": str(root),
            "attack_data_commit": _attack_commit(root),
            "techniques": list(TECHNIQUES),
            "leak_filter": {
                "scans_raw": True,
                "match": LEAK_MATCH,
                "events_seen": seen,
                "events_excluded": excluded,
                "by_technique": leak_by_technique,
            },
        },
        "entries": entries,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack-root", type=Path, default=_ATTACK_ROOT)
    parser.add_argument("--out", type=Path, default=KEY_PATH)
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    args = parser.parse_args(argv)
    if not args.attack_root.is_dir():
        print(f"attack_data root is not a directory: {args.attack_root}", file=sys.stderr)
        return 1
    document = build_key(
        AggregateProbe(SplunkWindowSource(timeout_seconds=args.timeout_seconds)),
        args.attack_root,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "entries": len(document["entries"]),
                "failures": [row["technique"] for row in document["failures"]],
                "events_excluded": document["provenance"]["leak_filter"]["events_excluded"],
                "out": str(args.out),
            }
        )
    )
    return 0 if document["entries"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
