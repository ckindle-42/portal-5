"""Build and audit the labelled-event manifest the knowledge store learns from.

python -m portal.modules.security.core.hunt.notables.manifest build --source ... --manifest ... --store ...
python -m portal.modules.security.core.hunt.notables.manifest audit-labels --index ... --fields ...
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..engine import Search, _literal_term_segments
from ..executor import (
    DEFAULT_BUDGETS,
    HuntBudget,
    HuntBudgetExceededError,
    HuntExecutor,
    HuntSearchFailedError,
)
from .behaviours import MAX_TERMS, IdentityPlan, _query_terms, _quote, behaviour_key
from .cards import SourceCard, card_consumers
from .embedding import EmbeddingError, embedding_from_env, embedding_requirement
from .generators import normalized_behaviour_words
from .knowledge import PROOF_INDEXES, KnowledgeError, KnowledgeItem, build_store
from .parse import parse_row
from .run import SOURCES_FILE, default_search, load_cards
from .sample import BEHAVIOUR_SOURCES, index_facts, read_windows, source_windows

BAD_ITEMS_PER_FAMILY = 800  # effort budget: distinct known-bad items kept per family
GOOD_ITEMS_PER_FAMILY = 400  # effort budget: distinct known-good items kept per family
GOOD_LINES_PER_FILE = 40  # effort budget: unlabelled lines sampled from one keyed file
GOOD_LINE_STRIDE = 100  # effort budget: unlabelled lines skipped between samples
INDEX_SOURCES = 12  # effort budget: sourcetypes sampled for a labelled or window family
INDEX_WINDOWS = 4  # effort budget: time slices read per sampled sourcetype
INDEX_EVENTS_PER_WINDOW = 250  # effort budget: events read from one slice
AUDIT_ROWS = 5  # effort budget: rows read to prove one item locates events
LABEL_VALUES = 20  # effort budget: label values locate-checked per carrying field
LABEL_ROWS = 2000  # effort budget: distinct label values read per carrying field
LABEL_SAMPLE = 200  # effort budget: raw events read when a label field is not indexed
BUILD_REQUESTS = 12000  # effort budget: Splunk requests for one store build and audit
BUILD_JOB_SECONDS = 3600.0  # effort budget: wall time for one store build and audit
_ROTATION = re.compile(r"(\.\d+)+$")
_FIELD_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_KINDS = ("keys", "labelled", "window")


@dataclass(frozen=True)
class FamilySpec:
    """One build family: where its labels live and which run's cards normalise it."""

    name: str
    index: str
    kind: str
    cards: Path
    keys: Path | None = None
    gather: Path | None = None
    label_field: str = ""
    good_window: tuple[float, float] | None = None
    part: str = "both"


def parse_source(text: str) -> FamilySpec:
    fields: dict[str, str] = {}
    for piece in text.split(","):
        key, _, value = piece.partition("=")
        if not key.strip() or not value.strip():
            raise ValueError(f"source spec piece {piece!r} is not key=value")
        fields[key.strip()] = value.strip()
    missing = [name for name in ("name", "index", "kind", "cards") if not fields.get(name)]
    if missing:
        raise ValueError(f"source spec needs {', '.join(missing)}")
    kind = fields["kind"]
    if kind not in _KINDS:
        raise ValueError(f"source kind must be one of {', '.join(_KINDS)}")
    if fields["index"].casefold() in PROOF_INDEXES:
        raise ValueError(f"proof index {fields['index']!r} cannot enter the knowledge build")
    part = fields.get("part", "both")
    if part not in ("bad", "good", "both"):
        raise ValueError("source part must be bad, good, or both")
    keys = Path(fields["keys"]) if fields.get("keys") else None
    gather = Path(fields["gather"]) if fields.get("gather") else None
    if kind == "keys" and (keys is None or gather is None):
        raise ValueError("a keys source needs keys= and gather=")
    label_field = fields.get("label_field", "")
    if kind == "labelled" and not _FIELD_NAME.fullmatch(label_field):
        raise ValueError("a labelled source needs label_field=<indexed or extracted field>")
    return FamilySpec(
        name=fields["name"],
        index=fields["index"],
        kind=kind,
        cards=Path(fields["cards"]),
        keys=keys,
        gather=gather,
        label_field=label_field,
        good_window=_good_window(kind, fields.get("good_window", "")),
        part=part,
    )


def _good_window(kind: str, raw: str) -> tuple[float, float] | None:
    if kind != "window":
        return None
    start, _, end = raw.partition(":")
    try:
        window = (float(start), float(end))
    except ValueError as exc:
        raise ValueError("a window source needs good_window=<start>:<end>") from exc
    if window[1] <= window[0]:
        raise ValueError("good_window end must be after its start")
    return window


def _plans(cards_dir: Path) -> dict[str, list[tuple[SourceCard, IdentityPlan]]]:
    """Cards with the behaviours stage's recorded keying, grouped by source."""
    payload = json.loads((cards_dir / SOURCES_FILE).read_text(encoding="utf-8"))
    overrides = {
        str(card.get("card_id") or ""): card.get("role_overrides")
        for card in payload.get("cards", [])
        if isinstance(card, Mapping)
    }
    grouped: dict[str, list[tuple[SourceCard, IdentityPlan]]] = {}
    for card in load_cards(cards_dir):
        summary = overrides.get(card.card_id)
        if not isinstance(summary, Mapping) or "manifest" not in card_consumers(card):
            continue
        actor = summary.get("actor") or {}
        action = summary.get("action") or {}
        objects = tuple(
            (str(item.get("field") or ""), str(item.get("mode") or ""))
            for item in summary.get("objects") or ()
            if isinstance(item, Mapping)
        )
        plan = IdentityPlan(
            str(actor.get("field") or ""),
            str(actor.get("mode") or ""),
            str(action.get("field") or ""),
            str(action.get("mode") or ""),
            objects,
            (),
            {},
        )
        grouped.setdefault(card.source_id, []).append((card, plan))
    return grouped


def _normalize(card: SourceCard, plan: IdentityPlan, raw: str) -> tuple[str, list[str]] | None:
    """One raw line in the run's own normalised behaviour form, with its literal terms."""
    parsed = parse_row(raw, card.fmt, card.columns, card.template_model)
    if not parsed.fields or not card.in_part(parsed.fields):
        return None
    key = behaviour_key(card, parsed.fields, plan)
    actor, action, object_value = key[1], key[3], key[5]
    if not actor and not object_value:
        return None
    return (
        normalized_behaviour_words(
            actor,
            action,
            object_value,
            actor_field=plan.actor_field,
            action_field=plan.action_field,
        ),
        _query_terms(plan, parsed.fields),
    )


def _provenance_query(index: str, host: str, source: str, terms: Sequence[str]) -> str:
    """Build a provenance query from whole Splunk-indexed terms."""
    tail = " ".join(
        _quote(segment) for value in terms[:MAX_TERMS] for segment in _literal_term_segments(value)
    )
    head = f"search index={_quote(index)} host={_quote(host)} source={_quote(source)}"
    return head + (f" {tail}" if tail else "") + f" | head {AUDIT_ROWS}"


def _item(
    spec: FamilySpec,
    statement: str,
    label: str,
    label_kind: str,
    label_basis: str,
    host: str,
    source: str,
    terms: Sequence[str],
) -> KnowledgeItem:
    return KnowledgeItem(
        statement=statement,
        label=label,
        label_kind=label_kind,
        label_basis=label_basis,
        family=spec.name,
        split="build",
        index=spec.index,
        source_kind="activity",
        query=_provenance_query(spec.index, host, source, terms),
    )


def _keyed_lines(spec: FamilySpec) -> Iterator[tuple[str, str, str, list[str] | None]]:
    """Labelled lines plus a deterministic stride sample of unlabelled lines, per keyed file."""
    wanted: dict[tuple[str, str], dict[int, list[str]]] = {}
    assert spec.keys is not None
    for line in spec.keys.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = (str(row["host"]), str(row["source"]))
        wanted.setdefault(key, {})[int(row["line"])] = [str(label) for label in row["labels"]]
    assert spec.gather is not None
    for (host, source), lines in sorted(wanted.items()):
        path = spec.gather / host / "logs" / source.lstrip("/")
        taken = 0
        seen = 0
        with path.open(encoding="utf-8", errors="replace") as handle:
            for number, raw in enumerate(handle, 1):
                raw = raw.rstrip("\r\n")
                labels = lines.get(number)
                if labels is not None:
                    yield host, source, raw, labels
                elif raw.strip() and taken < GOOD_LINES_PER_FILE:
                    seen += 1
                    if seen % GOOD_LINE_STRIDE == 0:
                        taken += 1
                        yield host, source, raw, None


def _select(items: Sequence[KnowledgeItem], cap: int) -> list[KnowledgeItem]:
    """Distinct (label, statement) items, round-robin across labels inside the budget."""
    unique: dict[tuple[str, str], KnowledgeItem] = {}
    for item in items:
        unique.setdefault((item.label, item.statement), item)
    by_label: dict[str, list[KnowledgeItem]] = {}
    for item in unique.values():
        by_label.setdefault(item.label, []).append(item)
    for group in by_label.values():
        group.sort(key=lambda entry: entry.statement)
    chosen: list[KnowledgeItem] = []
    labels = sorted(by_label)
    while len(chosen) < cap and any(by_label.values()):
        for label in labels:
            if by_label[label] and len(chosen) < cap:
                chosen.append(by_label[label].pop(0))
    return chosen


def _build_keyed(spec: FamilySpec) -> tuple[list[KnowledgeItem], dict[str, Any]]:
    """Normalise a keyed family's labelled and unlabelled lines with its recorded plans."""
    plans = _plans(spec.cards)
    bad: list[KnowledgeItem] = []
    good: list[KnowledgeItem] = []
    detail: dict[str, Any] = {
        "lines": 0,
        "labelled": 0,
        "good_sampled": 0,
        "no_card": 0,
        "unparsed": 0,
    }
    for host, source, raw, labels in _keyed_lines(spec):
        detail["lines"] += 1
        sourcetype = _ROTATION.sub("", source.rstrip("/").rsplit("/", 1)[-1])
        entries = plans.get(f"{spec.index}:{sourcetype}")
        if not entries:
            detail["no_card"] += 1
            continue
        for card, plan in entries:
            normalized = _normalize(card, plan, raw)
            if normalized is None:
                continue
            statement, terms = normalized
            if labels:
                detail["labelled"] += 1
                bad.extend(
                    _item(spec, statement, label, "known_bad", "attack_step", host, source, terms)
                    for label in labels
                )
            else:
                detail["good_sampled"] += 1
                good.append(
                    _item(
                        spec,
                        statement,
                        "unlabelled",
                        "known_good",
                        "unlabelled",
                        host,
                        source,
                        terms,
                    )
                )
            break
        else:
            detail["unparsed"] += 1
    items = (_select(bad, BAD_ITEMS_PER_FAMILY) if spec.part != "good" else []) + (
        _select(good, GOOD_ITEMS_PER_FAMILY) if spec.part != "bad" else []
    )
    detail.update(
        bad_items=sum(1 for item in items if item.label_kind == "known_bad"),
        good_items=sum(1 for item in items if item.label_kind == "known_good"),
    )
    return items, detail


def _build_indexed(
    spec: FamilySpec, executor: HuntExecutor, start: float, end: float
) -> tuple[list[KnowledgeItem], dict[str, Any]]:
    """Sample a labelled or non-attack-window family from its index and normalise it."""
    plans = _plans(spec.cards)
    bounds = spec.good_window or (start, end)
    facts, notes = index_facts(executor, spec.index, bounds[0], bounds[1])
    ranked = sorted(facts, key=lambda fact: (-fact.events, fact.sourcetype))[:INDEX_SOURCES]
    items: list[KnowledgeItem] = []
    detail: dict[str, Any] = {
        "sources": len(ranked),
        "events": 0,
        "normalized": 0,
        "no_card": 0,
        "unparsed": 0,
        "notes": notes,
    }
    for fact in ranked:
        entries = plans.get(f"{spec.index}:{fact.sourcetype}")
        if not entries:
            detail["no_card"] += 1
            continue
        windows = source_windows(fact, INDEX_WINDOWS)
        read = read_windows(
            executor,
            fact,
            windows,
            per_window=INDEX_EVENTS_PER_WINDOW,
            kind="knowledge_events",
            max_sources=BEHAVIOUR_SOURCES,
        )
        for row in read.rows:
            detail["events"] += 1
            label = (
                str(row.get(spec.label_field) or "")
                if spec.kind == "labelled"
                else "non_attack_day"
            )
            if not label:
                continue
            host, source = str(row.get("host") or ""), str(row.get("source") or "")
            for card, plan in entries:
                normalized = _normalize(card, plan, str(row.get("_raw") or ""))
                if normalized is None:
                    continue
                statement, terms = normalized
                kind, basis = (
                    ("known_bad", "technique")
                    if spec.kind == "labelled"
                    else ("known_good", "non_attack_day")
                )
                items.append(_item(spec, statement, label, kind, basis, host, source, terms))
                detail["normalized"] += 1
                break
            else:
                detail["unparsed"] += 1
    selected = _select(
        items, BAD_ITEMS_PER_FAMILY if spec.kind == "labelled" else GOOD_ITEMS_PER_FAMILY
    )
    detail["items"] = len(selected)
    return selected, detail


def audit_items(
    executor: HuntExecutor, items: Sequence[KnowledgeItem], start: float, end: float
) -> dict[str, Any]:
    """Every item's provenance query must locate real events; counts per family and label."""
    counts: dict[tuple[str, str, str], dict[str, int]] = {}
    missing: list[KnowledgeItem] = []
    rows_total = 0
    reads = executor.read_many(
        (item.query, start, end, "knowledge_audit", AUDIT_ROWS) for item in items
    )
    for item, read in zip(items, reads, strict=True):
        located = len(read.rows)
        slot = counts.setdefault(
            (item.family, item.label_kind, item.label),
            {
                "items": 0,
                "located": 0,
                "rows": 0,
            },
        )
        slot["items"] += 1
        slot["located"] += 1 if located else 0
        slot["rows"] += located
        rows_total += located
        if not located:
            missing.append(item)
    if missing:
        detail = "; ".join(
            f"{item.family}/{item.label} {item.statement!r} query={item.query}"
            for item in missing[:5]
        )
        raise KnowledgeError(f"{len(missing)} knowledge items locate no events: {detail}")
    rows = [
        {"family": family, "label_kind": kind, "label": label, **slot}
        for (family, kind, label), slot in sorted(counts.items())
    ]
    return {"items": len(items), "rows": rows_total, "counts": rows}


def _print_audit(report: Mapping[str, Any]) -> None:
    for row in report["counts"]:
        print(
            f"  {row['family']} {row['label_kind']} {row['label']}: "
            f"items={row['items']} located={row['located']} rows={row['rows']}"
        )
    print(f"audit: items={report['items']} located_events={report['rows']}")


def _label_values(
    executor: HuntExecutor, index: str, field: str, start: float, end: float
) -> tuple[list[tuple[str, int]], str]:
    """Distinct values of one carrying field with event counts, indexed or search-time."""
    try:
        read = executor.read(
            f"| tstats count where index={_quote(index)} by {field}",
            start,
            end,
            kind="discovery",
            row_cap=LABEL_ROWS,
        )
        counted = [
            (str(row.get(field) or ""), int(row.get("count") or 0))
            for row in read.rows
            if row.get(field)
        ]
        if counted:
            return sorted(counted, key=lambda pair: (-pair[1], pair[0])), "indexed"
    except HuntSearchFailedError:
        pass
    read = executor.read(
        f"search index={_quote(index)} | head {LABEL_SAMPLE}",
        start,
        end,
        kind="knowledge_audit",
        row_cap=LABEL_SAMPLE,
    )
    seen: dict[str, int] = {}
    for row in read.rows:
        value = str(row.get(field) or "")
        if value:
            seen[value] = seen.get(value, 0) + 1
    return sorted(seen.items(), key=lambda pair: (-pair[1], pair[0])), "search-time"


def audit_labels(
    executor: HuntExecutor, index: str, fields: Sequence[str], start: float, end: float
) -> dict[str, Any]:
    """How an index carries its labels: values, event counts, and that each locates events."""
    if index.casefold() in PROOF_INDEXES:
        raise KnowledgeError(f"proof index {index!r} cannot be audited into knowledge")
    report: dict[str, Any] = {}
    failures: list[str] = []
    for field in fields:
        values, carriage = _label_values(executor, index, field, start, end)
        checked = values[:LABEL_VALUES]
        located = 0
        reads = executor.read_many(
            (
                f"search index={_quote(index)} {field}={_quote(value)} | head 1",
                start,
                end,
                "knowledge_audit",
                1,
            )
            for value, _count in checked
        )
        for (value, _count), read in zip(checked, reads, strict=True):
            if read.rows:
                located += 1
            else:
                failures.append(f"{field}={value!r}")
        report[field] = {
            "carriage": carriage,
            "distinct": len(values),
            "checked": len(checked),
            "located": located,
            "top": [{"value": value, "events": count} for value, count in checked],
        }
        print(
            f"  {field}: carriage={carriage} distinct={len(values)} "
            f"located={located}/{len(checked)}"
        )
    if failures:
        raise KnowledgeError(f"label values locate no events: {', '.join(failures[:5])}")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build and audit the manifest, then the store")
    build.add_argument(
        "--source",
        action="append",
        required=True,
        help="name=,index=,kind=keys|labelled|window,cards=DIR[,keys=,gather=,label_field=,"
        "good_window=start:end,part=bad|good|both]",
    )
    build.add_argument("--manifest", type=Path, required=True, help="audited JSONL output")
    build.add_argument("--store", type=Path, required=True, help="DuckDB output path")
    labels = sub.add_parser("audit-labels", help="audit how an index carries its labels")
    labels.add_argument("--index", required=True)
    labels.add_argument("--fields", required=True, help="comma-separated carrying fields")
    for item in (build, labels):
        item.add_argument("--start", type=float, default=0.0)
        item.add_argument("--end", type=float, default=None)
    return parser


def _run_build(args: argparse.Namespace, executor: HuntExecutor, start: float, end: float) -> int:
    specs = [parse_source(text) for text in args.source]
    if len({spec.name for spec in specs}) != len(specs):
        raise ValueError("source names must be distinct")
    if len({spec.index.casefold() for spec in specs}) != len(specs):
        raise ValueError("each source index may appear only once (family exclusion is per index)")
    items: list[KnowledgeItem] = []
    details: dict[str, Any] = {}
    for spec in specs:
        found, detail = (
            _build_keyed(spec)
            if spec.kind == "keys"
            else _build_indexed(spec, executor, start, end)
        )
        if not found:
            raise KnowledgeError(f"family {spec.name!r} produced no knowledge items: {detail}")
        items.extend(found)
        details[spec.name] = detail
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        "".join(json.dumps(item.as_dict(), sort_keys=True) + "\n" for item in items),
        encoding="utf-8",
    )
    audit = audit_items(executor, items, start, end)
    _print_audit(audit)
    embedder = embedding_from_env()
    if embedder is None:
        print(embedding_requirement(), file=sys.stderr)
        return 2
    try:
        receipt = build_store(items, embedder, args.store)
        receipt["family_details"] = details
        receipt["audit"] = audit
        args.store.with_suffix(".receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(receipt, sort_keys=True))
    finally:
        embedder.close()
    return 0


def main(argv: list[str] | None = None, *, search: Search | None = None) -> int:
    args = _parser().parse_args(argv)
    resolved = default_search() if search is None else search
    executor = HuntExecutor(
        resolved,
        HuntBudget(
            {**DEFAULT_BUDGETS, "requests": BUILD_REQUESTS, "job_seconds": BUILD_JOB_SECONDS}
        ),
    )
    end = args.end if args.end is not None else time.time() + 1.0
    try:
        if args.command == "audit-labels":
            fields = [name.strip() for name in args.fields.split(",") if name.strip()]
            if not fields or not all(_FIELD_NAME.fullmatch(name) for name in fields):
                raise ValueError("--fields must be comma-separated field names")
            report = audit_labels(executor, args.index, fields, args.start, end)
            print(json.dumps(report, sort_keys=True))
            return 0
        return _run_build(args, executor, args.start, end)
    except (ValueError, OSError, KnowledgeError, EmbeddingError) as exc:
        print(f"knowledge manifest failed: {exc}", file=sys.stderr)
        return 1
    except (HuntBudgetExceededError, HuntSearchFailedError) as exc:
        print(f"knowledge manifest read failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
