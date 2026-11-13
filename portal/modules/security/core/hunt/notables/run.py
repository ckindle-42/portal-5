"""Stage orchestration: cards, behaviours, notables and the judge, one receipt per stage."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ...review.window import SplunkWindowSource
from ..engine import Search
from ..executor import executor_for
from ..judge import JudgeClient
from .behaviours import (
    Behaviour,
    collect_behaviours,
    load_behaviours,
    load_source_stats,
)
from .cards import (
    CardCache,
    Prepared,
    SourceCard,
    answer_cards,
    assemble_cards,
    prepare_cards,
)
from .generators import generate
from .judge_notables import judge_all
from .parse import FieldStat
from .receipt import peak_memory_mb, progress_update, read_json, utc_now, write_json
from .sample import SAMPLE_LINES, SourceFacts, index_facts, read_windows, sample_windows

CARD_SOURCE_CONCURRENCY = 2  # effort budget: with READ_CONCURRENCY, below the lab's 19 searches

STAGES = ("cards", "behaviours", "notables", "judge")
GENERATORS = ("alerts", "peer_rare", "deviation")
SOURCES_FILE = "sources.json"
STORE_FILE = "behaviours.duckdb"
NOTABLES_FILE = "notables.jsonl"


def default_search() -> SplunkWindowSource:
    return SplunkWindowSource()


def _sources_payload(
    index: str, start: float, end: float, cards: Sequence[SourceCard]
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for card in cards:
        counts[card.kind] = counts.get(card.kind, 0) + 1
    return {
        "index": index,
        "start": start,
        "end": end,
        "generated": utc_now(),
        "totals": {
            "sources": len({card.source_id for card in cards}),
            "cards": len(cards),
            "understood": sum(1 for card in cards if card.understood),
            "kinds": counts,
            "model_requests": sum(int(card.model.get("requests") or 0) for card in cards),
        },
        "cards": [card.as_dict() for card in cards],
    }


def _fact_dict(card: SourceCard) -> SourceFacts:
    facts = card.facts
    return SourceFacts(
        index=str(facts.get("index") or card.index),
        sourcetype=str(facts.get("sourcetype") or card.sourcetype),
        events=int(facts.get("events") or 0),
        first=float(facts.get("first") or 0.0),
        last=float(facts.get("last") or 0.0),
        hosts=tuple(str(name) for name in facts.get("hosts") or ()),
        host_count=int(facts.get("host_count") or 0),
        sources=tuple(str(name) for name in facts.get("sources") or ()),
        source_count=int(facts.get("source_count") or 0),
        active_periods=int(facts.get("active_periods") or 0),
        periods=int(facts.get("periods") or 0),
        count_cv=float(facts.get("count_cv") or 0.0),
    )


def _field_from(item: Mapping[str, Any], lines: int) -> FieldStat:
    return FieldStat(
        str(item.get("name") or ""),
        int(item.get("present") or 0),
        int(item.get("distinct") or 0),
        tuple(str(value) for value in item.get("examples") or ()),
        lines,
    )


def _roles_from(raw: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    found = raw.get("roles")
    if not isinstance(found, Mapping):
        return {}
    return {str(role): tuple(str(name) for name in names or ()) for role, names in found.items()}


def _fields_from(raw: Mapping[str, Any], lines: int) -> tuple[FieldStat, ...]:
    found = raw.get("fields")
    if not isinstance(found, list):
        return ()
    return tuple(_field_from(item, lines) for item in found if isinstance(item, Mapping))


def _strings_from(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in value or ())


def _part_from(raw: Mapping[str, Any]) -> tuple[str, str]:
    part = raw.get("part")
    if not isinstance(part, Mapping):
        return "", ""
    return str(part.get("field") or ""), str(part.get("value") or "")


def _optional_text(value: Any) -> str | None:
    return str(value) if value else None


def card_from_dict(raw: Mapping[str, Any]) -> SourceCard:
    sample = raw.get("sample") or {}
    lines = int(sample.get("lines") or 0)
    part_field, part_value = _part_from(raw)
    return SourceCard(
        index=str(raw.get("index") or ""),
        sourcetype=str(raw.get("sourcetype") or ""),
        kind=str(raw.get("kind") or "other"),
        roles=_roles_from(raw),
        understood=bool(raw.get("understood")),
        reason=_optional_text(raw.get("reason")),
        fmt=str(raw.get("structure") or "text"),
        coverage=float(raw.get("parse_coverage") or 0.0),
        fields=tuple(
            _field_from(item, lines)
            for item in raw.get("fields") or ()
            if isinstance(item, Mapping)
        ),
        sample=sample,
        facts=dict(raw.get("facts") or {}),
        model=dict(raw.get("model") or {}),
        cache_key=str(raw.get("cache_key") or ""),
        basis=str(raw.get("basis") or ""),
        rejected=_strings_from(raw.get("rejected_fields")),
        columns=_strings_from(raw.get("columns")),
        part_field=part_field,
        part_value=part_value,
        kind_said=str(raw.get("kind_said") or ""),
        kind_note=_optional_text(raw.get("kind_note")),
        kind_facts=dict(raw.get("kind_facts") or {}),
    )


def load_cards(out: Path) -> list[SourceCard]:
    payload = read_json(out / SOURCES_FILE)
    cards = payload.get("cards")
    if not isinstance(cards, list):
        raise FileNotFoundError(f"{out / SOURCES_FILE} holds no source cards; run the cards stage")
    return [card_from_dict(item) for item in cards if isinstance(item, Mapping)]


def facts_by_source(cards: Sequence[SourceCard]) -> dict[str, SourceFacts]:
    return {card.source_id: _fact_dict(card) for card in cards}


def _sample_source(executor: Any, facts: SourceFacts) -> tuple[SourceFacts, Any]:
    read = read_windows(
        executor, facts, sample_windows(facts), per_window=SAMPLE_LINES, kind="source_sample"
    )
    return facts, read


def _card_receipt(card: SourceCard, notes: Sequence[str]) -> dict[str, Any]:
    return {
        "card_id": card.card_id,
        "source_id": card.source_id,
        "part": {"field": card.part_field, "value": card.part_value} if card.part_field else None,
        "kind": card.kind,
        "kind_said": card.kind_said,
        "kind_note": card.kind_note,
        "kind_facts": dict(card.kind_facts),
        "understood": card.understood,
        "reason": card.reason,
        "roles": {role: list(names) for role, names in card.roles.items()},
        "structure": card.fmt,
        "sample_lines": card.sample.get("lines"),
        "parse_coverage": round(card.coverage, 3),
        "model_requests": int(card.model.get("requests") or 0),
        "model_seconds": card.model.get("seconds"),
        "cached": bool(card.model.get("cached")),
        "notes": notes,
    }


def _source_receipts(cards: Sequence[SourceCard], reads: Mapping[str, Any]) -> list[dict[str, Any]]:
    receipts = [
        _card_receipt(
            card,
            list(getattr(reads.get(card.source_id), "notes", ()) or ()),
        )
        for card in cards
    ]
    for source_id, read in reads.items():
        group = [card for card in cards if card.source_id == source_id]
        assigned = sum(int(card.sample.get("lines") or 0) for card in group)
        receipts.append(
            {
                "source_id": source_id,
                "parts": len(group),
                "sample_unassigned": max(0, len(read.rows) - assigned),
            }
        )
    return receipts


def cards_stage(
    *,
    index: str,
    out: Path,
    start: float,
    end: float,
    client: JudgeClient,
    model: str,
    search: Search,
) -> dict[str, Any]:
    """Sample every source, then ask once per distinct structure, concurrently."""
    began = time.monotonic()
    executor = executor_for(search)
    facts, notes = index_facts(executor, index, start, end)
    cache = CardCache(out / "cache" / "cards")
    with ThreadPoolExecutor(max_workers=CARD_SOURCE_CONCURRENCY) as pool:
        sampled = list(pool.map(lambda item: _sample_source(executor, item), facts))
    reads = {f"{item.index}:{item.sourcetype}": read for item, read in sampled}
    prepared: list[Prepared] = []
    for item, read in sampled:
        prepared.extend(prepare_cards(item, read.rows, read.windows, model))
    answers, answer_stats = answer_cards(prepared, client, model, cache)
    cards = assemble_cards(prepared, answers)
    write_json(out / SOURCES_FILE, _sources_payload(index, start, end, cards))
    requests = int(answer_stats["requests"])
    receipt = {
        "index": index,
        "start": start,
        "end": end,
        "sources": len({card.source_id for card in cards}),
        "cards": len(cards),
        "understood": sum(1 for card in cards if card.understood),
        "unparsed": sum(1 for card in cards if not card.understood),
        "structures": answer_stats["structures"],
        "model_requests": requests,
        "answers_reused": len(prepared) - requests,
        "cache_hits": answer_stats["disk_hits"],
        "request_budget": answer_stats["request_budget"],
        "unasked": answer_stats["unasked"],
        "unasked_sources": answer_stats["unasked_sources"],
        "backpressure": answer_stats.get("backpressure", {}),
        "model_seconds": answer_stats["model_seconds"],
        "cached": sum(1 for card in cards if card.model.get("cached")),
        "seconds": round(time.monotonic() - began, 3),
        "peak_memory_mb": peak_memory_mb(),
        "notes": notes,
        "sources_receipt": _source_receipts(cards, reads),
    }
    progress_update(out, "cards", receipt)
    return receipt


def behaviours_stage(*, out: Path, search: Search) -> tuple[list[Behaviour], dict[str, Any]]:
    """Count distinct behaviours for every activity source on DuckDB, declaring coverage."""
    cards = load_cards(out)
    began = time.monotonic()
    behaves, receipt = collect_behaviours(
        executor_for(search), cards, facts_by_source(cards), out / STORE_FILE
    )
    receipt["seconds_total"] = round(time.monotonic() - began, 3)
    receipt["peak_memory_mb"] = peak_memory_mb()
    progress_update(out, "behaviours", receipt)
    return behaves, receipt


def notables_stage(
    *, index: str, out: Path, start: float, end: float, search: Search, enabled: Sequence[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Raise notables from each independent generator, bounded and ordered, to notables.jsonl."""
    cards = load_cards(out)
    store = out / STORE_FILE
    if not store.exists():
        raise FileNotFoundError(f"{store} holds no behaviour table; run the behaviours stage")
    behaviours = load_behaviours(store)
    notables, receipt = generate(
        executor_for(search),
        index,
        start,
        end,
        cards,
        facts_by_source(cards),
        behaviours,
        load_source_stats(store),
        enabled,
    )
    rows = [notable.as_dict() for notable in notables]
    path = out / NOTABLES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    receipt["file"] = str(path)
    receipt["peak_memory_mb"] = peak_memory_mb()
    progress_update(out, "notables", receipt)
    return rows, receipt


def read_notables(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"{path} holds no notables; run the notables stage")
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if line.strip():
            stored = json.loads(line)
            if isinstance(stored, dict):
                rows.append(stored)
    return rows


def judge_stage(
    *, out: Path, client: JudgeClient, model: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Judge every distinct notable once through the Pipeline and write p_yes back."""
    path = out / NOTABLES_FILE
    rows = read_notables(path)
    judged, receipt = judge_all(
        rows, client=client, model=model, cache_path=out / "cache" / "judge.json"
    )
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in judged))
    receipt["file"] = str(path)
    receipt["peak_memory_mb"] = peak_memory_mb()
    progress_update(out, "judge", receipt)
    return judged, receipt
