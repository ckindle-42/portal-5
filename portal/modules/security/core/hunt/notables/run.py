"""Stage orchestration: cards, behaviours, notables and the judge, one receipt per stage."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
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
from .cards import CardCache, SourceCard, build_card
from .generators import generate
from .judge_notables import judge_all
from .parse import FieldStat
from .receipt import peak_memory_mb, progress_update, read_json, utc_now, write_json
from .sample import SourceFacts, index_facts, read_windows, sample_windows

STAGES = ("cards", "behaviours", "notables", "judge")
GENERATORS = ("alerts", "peer_rare", "deviation")
SOURCES_FILE = "sources.json"
PROGRESS_FILE = "progress.json"
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
            "sources": len(cards),
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
    )


def card_from_dict(raw: Mapping[str, Any]) -> SourceCard:
    sample = raw.get("sample") or {}
    lines = int(sample.get("lines") or 0)
    fields = tuple(
        FieldStat(
            str(item.get("name") or ""),
            int(item.get("present") or 0),
            int(item.get("distinct") or 0),
            tuple(str(value) for value in item.get("examples") or ()),
            lines,
        )
        for item in raw.get("fields") or ()
    )
    roles = {
        str(role): tuple(str(name) for name in names)
        for role, names in (raw.get("roles") or {}).items()
    }
    return SourceCard(
        index=str(raw.get("index") or ""),
        sourcetype=str(raw.get("sourcetype") or ""),
        kind=str(raw.get("kind") or "other"),
        roles=roles,
        understood=bool(raw.get("understood")),
        reason=str(raw["reason"]) if raw.get("reason") else None,
        fmt=str(raw.get("structure") or "text"),
        coverage=float(raw.get("parse_coverage") or 0.0),
        fields=fields,
        sample=sample,
        facts=dict(raw.get("facts") or {}),
        model=dict(raw.get("model") or {}),
        cache_key=str(raw.get("cache_key") or ""),
        basis=str(raw.get("basis") or ""),
        rejected=tuple(str(name) for name in raw.get("rejected_fields") or ()),
        columns=tuple(str(name) for name in raw.get("columns") or ()),
    )


def load_cards(out: Path) -> list[SourceCard]:
    payload = read_json(out / SOURCES_FILE)
    cards = payload.get("cards")
    if not isinstance(cards, list):
        raise FileNotFoundError(f"{out / SOURCES_FILE} holds no source cards; run the cards stage")
    return [card_from_dict(item) for item in cards if isinstance(item, Mapping)]


def facts_by_source(cards: Sequence[SourceCard]) -> dict[str, SourceFacts]:
    return {card.source_id: _fact_dict(card) for card in cards}


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
    """One card per source: a deterministic sample, one bounded model request, validated."""
    began = time.monotonic()
    executor = executor_for(search)
    facts, notes = index_facts(executor, index, start, end)
    cache = CardCache(out / "cache" / "cards")
    cards: list[SourceCard] = []
    source_receipts: list[dict[str, Any]] = []
    for item in facts:
        started = time.monotonic()
        read = read_windows(
            executor, item, sample_windows(item), per_window=40, kind="source_sample"
        )
        card = build_card(
            item, read.rows, windows=read.windows, client=client, model=model, cache=cache
        )
        cards.append(card)
        source_receipts.append(
            {
                "source_id": card.source_id,
                "kind": card.kind,
                "understood": card.understood,
                "reason": card.reason,
                "roles": {role: list(names) for role, names in card.roles.items()},
                "structure": card.fmt,
                "sample_lines": len(read.rows),
                "parse_coverage": round(card.coverage, 3),
                "model_requests": int(card.model.get("requests") or 0),
                "model_seconds": card.model.get("seconds"),
                "cached": bool(card.model.get("cached")),
                "seconds": round(time.monotonic() - started, 3),
                "notes": read.notes,
            }
        )
    write_json(out / SOURCES_FILE, _sources_payload(index, start, end, cards))
    receipt = {
        "index": index,
        "start": start,
        "end": end,
        "sources": len(cards),
        "understood": sum(1 for card in cards if card.understood),
        "unparsed": sum(1 for card in cards if not card.understood),
        "model_requests": sum(int(card.model.get("requests") or 0) for card in cards),
        "model_seconds": round(sum(float(card.model.get("seconds") or 0.0) for card in cards), 3),
        "cached": sum(1 for card in cards if card.model.get("cached")),
        "seconds": round(time.monotonic() - began, 3),
        "peak_memory_mb": peak_memory_mb(),
        "notes": notes,
        "sources_receipt": source_receipts,
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
