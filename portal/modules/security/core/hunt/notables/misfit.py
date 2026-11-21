"""Misfit generator: notables for rare lines that fit none of their source's card structures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .behaviours import MisfitShape, reproduction_query
from .cards import SourceCard
from .generators import NOTABLE_BUDGET, Notable, _interleave, _make
from .sample import SourceFacts

MISFIT_GENERATOR = "misfit"
MISFIT_MIN_COVERAGE = 0.9  # a source is otherwise well understood from this card coverage up
MISFIT_MAX_SHARE = 0.01  # a well-understood source still keeps its misfit share below this
MISFIT_NOTABLE_BUDGET = NOTABLE_BUDGET  # effort budget: misfit notables kept per run


def source_coverage(cards: Sequence[SourceCard]) -> dict[str, float]:
    """Per source, the best parse coverage its understood cards achieved."""
    found: dict[str, float] = {}
    for card in cards:
        if card.understood:
            found[card.source_id] = max(found.get(card.source_id, 0.0), card.coverage)
    return found


def _shape_decision(events: int, lines_read: int, misfit_lines: int, card_coverage: float) -> str:
    """keep, novel (rare line in a source the share gate would drop), or a skip reason."""
    if lines_read <= 0:
        return "no_read_stats"
    if card_coverage < MISFIT_MIN_COVERAGE:
        return "low_coverage"
    if misfit_lines / lines_read <= MISFIT_MAX_SHARE:
        return "keep"
    if events / lines_read <= MISFIT_MAX_SHARE:
        return "novel"
    return "poorly_understood_source"


def _trim_novel(
    groups: dict[str, list[tuple[float, MisfitShape, float, int]]], novel_sources: set[str]
) -> int:
    """A discarded source contributes its rarest in-threshold shape, not the whole tail."""
    trimmed = 0
    for source_id in novel_sources:
        group = groups.get(source_id)
        if not group or len(group) <= 1:
            continue
        group.sort(key=lambda item: (item[0], item[1].shape))
        trimmed += len(group) - 1
        groups[source_id] = group[:1]
    return trimmed


def generate_misfit(
    cards: Sequence[SourceCard],
    facts_by_source: Mapping[str, SourceFacts],
    misfits: Sequence[MisfitShape],
    stats: Mapping[str, Mapping[str, Any]],
    notes: Sequence[str] = (),
) -> tuple[list[Notable], dict[str, Any]]:
    """Rank out-of-structure shapes by how unusual each is for its own source."""
    coverage = source_coverage(cards)
    groups: dict[str, list[tuple[float, MisfitShape, float, int]]] = {}
    novel_sources: set[str] = set()
    skipped = {
        "low_coverage": 0,
        "poorly_understood_source": 0,
        "no_read_stats": 0,
        "novel_source_trimmed": 0,
    }
    for shape in misfits:
        source_stat = stats.get(shape.source_id) or {}
        lines_read = int(source_stat.get("lines_read") or 0)
        misfit_lines = int(source_stat.get("misfit_lines") or 0)
        card_coverage = coverage.get(shape.source_id, 0.0)
        decision = _shape_decision(shape.events, lines_read, misfit_lines, card_coverage)
        if decision in skipped:
            skipped[decision] += 1
            continue
        if decision == "novel":
            novel_sources.add(shape.source_id)
        groups.setdefault(shape.source_id, []).append(
            (shape.events / lines_read, shape, card_coverage, lines_read)
        )
    skipped["novel_source_trimmed"] = _trim_novel(groups, novel_sources)
    for group in groups.values():
        group.sort(key=lambda item: (item[0], item[1].shape))
    ordered = sorted(groups.items(), key=lambda item: (item[1][0][0], item[0]))
    notables = _interleave(
        [
            [_misfit_notable(entry, source_id, facts_by_source, stats) for entry in group]
            for source_id, group in ordered
        ],
        MISFIT_NOTABLE_BUDGET,
    )
    receipt = {
        "existed": len(misfits),
        "kept": len(notables),
        "skipped": skipped,
        "min_coverage": MISFIT_MIN_COVERAGE,
        "max_share": MISFIT_MAX_SHARE,
        "sources": len({shape.source_id for shape in misfits}),
        "sources_ranked": len(groups),
        "novel_sources": len(novel_sources),
        "notes": list(notes),
        "ordering": "sources interleaved, rarest shape of each source first",
    }
    return notables, receipt


def _misfit_notable(
    item: tuple[float, MisfitShape, float, int],
    source_id: str,
    facts_by_source: Mapping[str, SourceFacts],
    stats: Mapping[str, Mapping[str, Any]],
) -> Notable:
    share, shape, card_coverage, lines_read = item
    facts = facts_by_source.get(source_id)
    source_stat = stats.get(source_id) or {}
    evidence = tuple(
        {
            "line": str(example.get("raw") or ""),
            "query": reproduction_query(facts, [str(example.get("raw") or "")]) if facts else "",
            "earliest": example.get("earliest"),
            "latest": example.get("latest"),
        }
        for example in shape.examples
    )
    return _make(
        generator=MISFIT_GENERATOR,
        basis="out_of_structure",
        what="a line shape that fits none of this source's card structures",
        entities=(("shape", shape.shape),),
        source_id=source_id,
        first_seen=shape.first_seen,
        last_seen=shape.last_seen,
        counts={
            "events": shape.events,
            "hosts": shape.hosts,
            "misfit_lines": int(source_stat.get("misfit_lines") or 0),
            "lines_read": lines_read,
        },
        measure_name="share_of_source_lines",
        measure_value=round(share, 10),
        why=(
            f"{shape.events} of {lines_read} lines read from this source match this shape and"
            f" fit none of its card structures (card coverage {card_coverage:.2f})"
        ),
        evidence=evidence,
    )
