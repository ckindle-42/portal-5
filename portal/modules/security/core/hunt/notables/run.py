"""Stage orchestration: cards, behaviours, notables, relate and the judge."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from ...review.window import SplunkWindowSource
from ..engine import Search
from ..executor import ROW_CAP, HuntExecutor, Read, executor_for
from ..judge import JudgeClient
from .behaviours import (
    Behaviour,
    collect_behaviours,
    load_behaviour_peaks,
    load_behaviours,
    load_misfits,
    load_source_stats,
)
from .cards import (
    CardCache,
    ModelAnswer,
    Prepared,
    SourceCard,
    answer_cards,
    assemble_cards,
    is_alert_event,
    prepare_cards,
)
from .generators import GENERATORS as BASE_GENERATORS
from .generators import SERIES_SPAN_SECONDS, generate
from .inventory import (
    INVENTORY_FILE,
    apply_inventory,
    collect_inventory,
    inventory_summary,
    load_inventory,
)
from .judge_notables import judge_all
from .merge import DEFAULT_MERGE, MEASURED_SOURCE, merge_notables
from .misfit import MISFIT_GENERATOR, generate_misfit
from .parse import MIN_PARTITION_LINES, FieldStat, TemplateModel
from .receipt import peak_memory_mb, progress_update, read_json, utc_now, write_json
from .sample import (
    ALERT_PROBE_LINES,
    SAMPLE_LINES,
    IndexFile,
    SourceFacts,
    index_facts,
    read_alert_rows,
    read_windows,
    sample_windows,
    shared_source_names,
)
from .similar import SIMILAR_GENERATOR, generate_similar
from .spine import spine_from_store
from .window_activity import resolve_source_windows

HTTP_ERROR_THRESHOLD = 0.20
JUDGE_STAGE_DEADLINE_SECONDS = 720.0  # effort budget: the hunt job wall time (executor job_seconds)

STAGES = ("cards", "behaviours", "notables", "relate", "judge")
GENERATORS = (*BASE_GENERATORS, MISFIT_GENERATOR, SIMILAR_GENERATOR)
DEFAULT_GENERATORS = (*BASE_GENERATORS, MISFIT_GENERATOR)
MERGE_PRIORITY = (SIMILAR_GENERATOR, *BASE_GENERATORS, MISFIT_GENERATOR)
SOURCES_FILE = "sources.json"
STORE_FILE = "behaviours.duckdb"
NOTABLES_FILE = "notables.jsonl"


def _query_filter(query: str, field: str) -> str:
    found = re.search(rf'(?i)(?<![\w]){field}\s*=\s*(?:"([^"]*)"|([^\s|]+))', query)
    return str(found.group(1) or found.group(2) or "") if found else ""


def _ledger_source_id(query: str) -> str:
    index = _query_filter(query, "index")
    source = _query_filter(query, "sourcetype") or _query_filter(query, "source")
    return f"{index}:{source}" if index and source else ""


def _extracted_values(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    values: dict[str, None] = {}

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for item in value.values():
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)
        elif value is not None and str(value):
            values.setdefault(str(value), None)

    for row in rows:
        visit(row)
    return list(values)


def reset_ledger(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "ledger.jsonl").write_text("", encoding="utf-8")


def configure_ledger(search: Search, out: Path, stage: str) -> HuntExecutor:
    path = out / "ledger.jsonl"
    out.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    executor = executor_for(search)

    def record(
        query: str,
        start: float,
        end: float,
        result: Read,
        source_id: str | None,
        part: str | None,
    ) -> None:
        row = {
            "stage": stage,
            "source_id": source_id or _ledger_source_id(query),
            "part": part,
            "query": query,
            "window_start": start,
            "window_end": end,
            "rows": len(result.rows),
            "capped": result.reason == ROW_CAP,
            "reason": result.reason,
            "values_extracted": _extracted_values(result.rows),
        }
        with lock, path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")

    executor.read_observer = record
    with suppress(AttributeError, TypeError):
        cast(Any, search).executor = executor
    return executor


def default_search() -> SplunkWindowSource:
    return SplunkWindowSource()


def merge_weights_from_env() -> tuple[dict[str, int] | None, str]:
    """Merge weights and their provenance from ``PORTAL_HUNT_MERGE_WEIGHTS``.

    A JSON object is a hand-set override; anything else names a scoreboard ``--weights-out``
    file, whose weights are the measured marginal.
    """
    raw = (os.environ.get("PORTAL_HUNT_MERGE_WEIGHTS") or "").strip()
    if not raw:
        return None, "default"
    if raw.startswith("{"):
        return _weight_vector(raw, "PORTAL_HUNT_MERGE_WEIGHTS"), "override"
    return _weights_file(Path(raw))


def _weight_vector(raw: str, label: str) -> dict[str, int]:
    stored = json.loads(raw)
    if not isinstance(stored, Mapping):
        raise ValueError(f"{label} must be a JSON object of generator: weight")
    weights: dict[str, int] = {}
    for name, value in stored.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label}[{name!r}] is not a non-negative integer")
        weights[str(name)] = value
    return weights


def _weights_file(path: Path) -> tuple[dict[str, int], str]:
    """A measured-weight receipt; a file that is present but unparsable fails loud, never defaults."""
    if not path.is_file():
        raise ValueError(f"PORTAL_HUNT_MERGE_WEIGHTS names {path}, which is not a file")
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"PORTAL_HUNT_MERGE_WEIGHTS file {path} is not JSON: {error}") from error
    receipt = stored if isinstance(stored, Mapping) else {}
    vector = receipt.get("weights", stored)
    return (
        _weight_vector(json.dumps(vector), str(path)),
        str(receipt.get("source") or MEASURED_SOURCE),
    )


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
            "unparsed": sum(
                1 for card in cards if not card.understood and card.reason != "model_http_error"
            ),
            "model_http_error_cards": sum(1 for card in cards if card.reason == "model_http_error"),
            "kinds": counts,
            "model_requests": sum(int(card.model.get("requests") or 0) for card in cards),
        },
        "cards": [card.as_dict() for card in cards],
    }


def _card_failure_counts(
    cards: Sequence[SourceCard],
    answers: Mapping[str, tuple[ModelAnswer, int, bool]],
) -> tuple[int, int]:
    http_errors = sum(
        1 for answer, _requests, _cached in answers.values() if answer.error == "http_error"
    )
    unparsed = sum(1 for card in cards if not card.understood and card.reason != "model_http_error")
    return http_errors, unparsed


def _check_http_error_rate(
    stage: str, http_errors: int, requests: int, model: str, *, unparsed: int | None = None
) -> None:
    if requests and http_errors / requests > HTTP_ERROR_THRESHOLD:
        detail = f" unparsed={unparsed}" if unparsed is not None else ""
        raise RuntimeError(
            f"{stage} failed: model_http_errors={http_errors}/{requests}{detail} "
            f"exceeds >{HTTP_ERROR_THRESHOLD:.0%}; model={model}"
        )


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
        shared_sources=tuple(str(name) for name in facts.get("shared_sources") or ()),
        active_periods=int(facts.get("active_periods") or 0),
        periods=int(facts.get("periods") or 0),
        count_cv=float(facts.get("count_cv") or 0.0),
        files=tuple(
            IndexFile(
                str(item.get("path") or ""),
                int(item.get("events") or 0),
                tuple(str(name) for name in item.get("hosts") or ()),
                float(item.get("first") or 0.0),
                float(item.get("last") or 0.0),
            )
            for item in facts.get("files") or ()
            if isinstance(item, Mapping)
        ),
    )


def _search_cost(executor: HuntExecutor, before: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The searches this stage issued, by kind, so its wall cost is read not assumed."""
    delta = executor.delta(before)
    return {
        "total": sum(int(slot["requests"]) for slot in delta.values()),
        "seconds": round(sum(float(slot["seconds"]) for slot in delta.values()), 3),
        "by_kind": delta,
    }


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
        template_model=TemplateModel.from_dict(raw.get("template")),
    )


def load_cards(out: Path) -> list[SourceCard]:
    payload = read_json(out / SOURCES_FILE)
    cards = payload.get("cards")
    if not isinstance(cards, list):
        raise FileNotFoundError(f"{out / SOURCES_FILE} holds no source cards; run the cards stage")
    return [card_from_dict(item) for item in cards if isinstance(item, Mapping)]


def facts_by_source(cards: Sequence[SourceCard]) -> dict[str, SourceFacts]:
    facts = {card.source_id: _fact_dict(card) for card in cards}
    shared = shared_source_names({key: source.sources for key, source in facts.items()})
    for key, source in facts.items():
        inferred = tuple(s for s in source.sources if s.casefold() in shared)
        if inferred:
            facts[key] = replace(
                source, shared_sources=tuple(dict.fromkeys((*source.shared_sources, *inferred)))
            )
    return facts


def _sample_source(executor: Any, facts: SourceFacts) -> tuple[SourceFacts, Any]:
    read = read_windows(
        executor, facts, sample_windows(facts), per_window=SAMPLE_LINES, kind="source_sample"
    )
    sampled_alerts = sum(1 for row in read.rows if is_alert_event(row))
    json_sample = any(str(row.get("_raw") or "").lstrip().startswith("{") for row in read.rows)
    if sampled_alerts < MIN_PARTITION_LINES:
        probe = read_alert_rows(executor, facts) if json_sample else None
        if probe is None or not any(is_alert_event(row) for row in probe.rows):
            probe = read_windows(
                executor,
                facts,
                sample_windows(facts),
                per_window=ALERT_PROBE_LINES,
                kind="alert_probe",
            )
        alerts = [row for row in probe.rows if is_alert_event(row)]
        if alerts:
            seen = {str(row.get("_raw") or "") for row in read.rows}
            read.rows.extend(row for row in alerts if str(row.get("_raw") or "") not in seen)
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
        "templates": card.sample.get("templates"),
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
    configure_ledger(search, out, "cards")
    executor = executor_for(search)
    facts, notes = index_facts(executor, index, start, end)
    cache = CardCache(out / "cache" / "cards")
    with ThreadPoolExecutor(max_workers=min(len(facts) or 1, executor.budget.concurrency)) as pool:
        sampled = list(pool.map(lambda item: _sample_source(executor, item), facts))
    reads = {f"{item.index}:{item.sourcetype}": read for item, read in sampled}
    prepared: list[Prepared] = []
    for item, read in sampled:
        prepared.extend(prepare_cards(item, read.rows, read.windows, model))
    answers, answer_stats = answer_cards(prepared, client, model, cache)
    cards = assemble_cards(prepared, answers)
    http_errors, unparsed = _card_failure_counts(cards, answers)
    _check_http_error_rate(
        "cards_stage", http_errors, int(answer_stats["requests"]), model, unparsed=unparsed
    )
    write_json(out / SOURCES_FILE, _sources_payload(index, start, end, cards))
    requests = int(answer_stats["requests"])
    receipt = {
        "index": index,
        "start": start,
        "end": end,
        "sources": len({card.source_id for card in cards}),
        "cards": len(cards),
        "understood": sum(1 for card in cards if card.understood),
        "unparsed": unparsed,
        "model_http_errors": http_errors,
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


def _write_role_overrides(out: Path, overrides: Mapping[str, Any]) -> None:
    """Record each source's keying decision on its card so the override is auditable."""
    payload = read_json(out / SOURCES_FILE)
    cards = payload.get("cards")
    if not isinstance(cards, list) or not overrides:
        return
    for card in cards:
        if isinstance(card, dict):
            summary = overrides.get(str(card.get("card_id") or ""))
            if summary is not None:
                card["role_overrides"] = summary
    write_json(out / SOURCES_FILE, payload)


def behaviours_stage(*, out: Path, search: Search) -> tuple[list[Behaviour], dict[str, Any]]:
    """Count distinct behaviours for every activity source on DuckDB, declaring coverage."""
    cards = load_cards(out)
    began = time.monotonic()
    sources = read_json(out / SOURCES_FILE)
    configure_ledger(search, out, "behaviours")
    executor = executor_for(search)
    before = executor.stats()
    inventory = collect_inventory(
        executor,
        cards,
        str(sources.get("index") or ""),
        float(sources.get("start") or 0.0),
        float(sources.get("end") or 0.0),
    )
    write_json(out / INVENTORY_FILE, inventory)
    behaves, receipt = collect_behaviours(
        executor, cards, facts_by_source(cards), out / STORE_FILE, inventory
    )
    receipt["inventory"] = inventory_summary(inventory)
    receipt["spine"] = spine_from_store(out, receipts=receipt.get("receipts") or ())
    receipt["searches"] = _search_cost(executor, before)
    _write_role_overrides(out, receipt.get("identity_overrides") or {})
    receipt.pop("identity_overrides", None)
    receipt["seconds_total"] = round(time.monotonic() - began, 3)
    receipt["peak_memory_mb"] = peak_memory_mb()
    progress_update(out, "behaviours", receipt)
    return behaves, receipt


def _stored_inventory(
    out: Path, cards: Sequence[SourceCard], behaviours: Sequence[Behaviour]
) -> tuple[list[Behaviour], dict[str, SourceFacts], dict[str, Any]]:
    """Apply the stored value lists in memory. The behaviour table stays sample-based."""
    source_facts = facts_by_source(cards)
    updated, receipt = apply_inventory(
        behaviours, load_inventory(out / INVENTORY_FILE), source_facts
    )
    return updated, source_facts, receipt


def notables_stage(
    *,
    index: str,
    out: Path,
    start: float,
    end: float,
    search: Search,
    enabled: Sequence[str],
    family: str | None = None,
    knowledge_store: Path | None = None,
    knowledge_families: Sequence[str] | None = None,
    embedder: Any | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Raise notables from each independent generator, bounded and ordered, to notables.jsonl."""
    began = time.monotonic()
    configure_ledger(search, out, "notables")
    weights, weights_source = merge_weights_from_env()
    cards = load_cards(out)
    store = out / STORE_FILE
    if not store.exists():
        raise FileNotFoundError(f"{store} holds no behaviour table; run the behaviours stage")
    behaviours = load_behaviours(store)
    standard_enabled = [
        name for name in enabled if name not in (SIMILAR_GENERATOR, MISFIT_GENERATOR)
    ]
    executor = executor_for(search)
    behaviours, source_facts, inventory_receipt = _stored_inventory(out, cards, behaviours)
    notables, receipt = generate(
        executor,
        index,
        start,
        end,
        cards,
        source_facts,
        behaviours,
        load_source_stats(store),
        standard_enabled,
        behaviour_peaks=load_behaviour_peaks(store, SERIES_SPAN_SECONDS)
        if "deviation" in standard_enabled
        else None,
    )
    if MISFIT_GENERATOR in enabled:
        started = time.monotonic()
        misfits, misfit_stats, misfit_notes = load_misfits(store)
        found, detail = generate_misfit(
            cards, facts_by_source(cards), misfits, misfit_stats, misfit_notes
        )
        notables.extend(found)
        receipt[MISFIT_GENERATOR] = detail
        receipt["seconds"][MISFIT_GENERATOR] = round(time.monotonic() - started, 3)
    if SIMILAR_GENERATOR in enabled:
        if knowledge_store is None or embedder is None:
            raise ValueError(
                "similar_to_known requires --knowledge-store and Pipeline embedding settings"
            )
        similar, detail = generate_similar(
            behaviours,
            cards,
            store_path=knowledge_store,
            run_index=index,
            expected_family=family,
            allowed_families=knowledge_families,
            embedder=embedder,
        )
        notables = [*similar, *notables]
        receipt[SIMILAR_GENERATOR] = detail
        receipt["seconds"][SIMILAR_GENERATOR] = detail["seconds"]
    merged, merge_receipt = merge_notables(
        notables,
        MERGE_PRIORITY,
        DEFAULT_MERGE,
        weights=weights,
        weights_source=weights_source,
    )
    if "deviation" in enabled:
        receipt["source_windows"] = resolve_source_windows(merged, executor, cards, source_facts)
    receipt.update(inventory=inventory_receipt, merge=merge_receipt)
    receipt["enabled"] = list(enabled)
    receipt["total"] = len(merged)
    receipt["seconds"]["total"] = round(time.monotonic() - began, 3)
    rows = [notable.as_dict() for notable in merged]
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
    *,
    out: Path,
    client: JudgeClient,
    model: str,
    deadline_seconds: float = JUDGE_STAGE_DEADLINE_SECONDS,
    request_budget: int | None = None,
    max_notables: int | None = None,
    explain: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Judge all rows, or annotate a bounded Stage 1 prefix, and save the result."""
    path = out / NOTABLES_FILE
    rows = read_notables(path)
    candidates = rows if max_notables is None else rows[: max(0, max_notables)]
    judged, receipt = judge_all(
        candidates,
        client=client,
        model=model,
        cache_path=out / "cache" / "judge.json",
        request_budget=request_budget,
        deadline_seconds=deadline_seconds,
        explain=explain,
    )
    http_errors = int(receipt["unjudged_reasons"].get("http_error", 0))
    _check_http_error_rate("judge_stage", http_errors, int(receipt["requests"]), model)
    if max_notables is None:
        receipt["ranking"] = {"order": "merged_file_order"}
        policy = "stage1_rank"
        saved = judged
        candidate_count = len(candidates)
        annotation_cut = 0
    else:
        receipt["ranking"] = {"source": "stage1_order", "reordered": False}
        policy = "stage1_order_annotation_limit"
        saved = [*judged, *rows[len(candidates) :]]
        candidate_count = len(rows)
        annotation_cut = max(0, len(rows) - len(candidates))
    cut = int(receipt.get("unasked") or 0) + annotation_cut
    cut_reasons = []
    if annotation_cut:
        cut_reasons.append("annotation_limit")
    if receipt.get("unasked"):
        cut_reasons.append("judge_stage_budget_exhausted")
    receipt["selection"] = {
        "policy": policy,
        "candidates": candidate_count,
        "judged": int(receipt["judged"]),
        "cached": int(receipt.get("cached") or 0),
        "cut": cut,
        "cut_reason": "; ".join(cut_reasons) or None,
    }
    saved = [{**row, "unjudged": row.get("p_yes") is None} for row in saved]
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in saved))
    receipt["file"] = str(path)
    receipt["peak_memory_mb"] = peak_memory_mb()
    progress_update(out, "judge", receipt)
    return saved, receipt


def _judge_order(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Spend the Stage 2 judge budget on similar-to-known notables first."""
    indexed = list(enumerate(rows))

    def rank(item: tuple[int, dict[str, Any]]) -> tuple[int, float, int]:
        index, row = item
        if row.get("generator") != SIMILAR_GENERATOR:
            return (1, 0.0, index)
        measure = row.get("measure")
        value = measure.get("value") if isinstance(measure, Mapping) else 0.0
        try:
            score = 0.0 if value is None else float(value)
        except (TypeError, ValueError):
            score = 0.0
        return (0, -score, index)

    return [row for _index, row in sorted(indexed, key=rank)]
