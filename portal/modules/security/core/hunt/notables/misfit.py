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
    skipped = {
        "low_coverage": 0,
        "poorly_understood_source": 0,
        "no_read_stats": 0,
    }
    for shape in misfits:
        source_stat = stats.get(shape.source_id) or {}
        lines_read = int(source_stat.get("lines_read") or 0)
        misfit_lines = int(source_stat.get("misfit_lines") or 0)
        card_coverage = coverage.get(shape.source_id, 0.0)
        if lines_read <= 0:
            skipped["no_read_stats"] += 1
        elif card_coverage < MISFIT_MIN_COVERAGE:
            skipped["low_coverage"] += 1
        elif misfit_lines / lines_read > MISFIT_MAX_SHARE:
            skipped["poorly_understood_source"] += 1
        else:
            groups.setdefault(shape.source_id, []).append(
                (shape.events / lines_read, shape, card_coverage, lines_read)
            )
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
