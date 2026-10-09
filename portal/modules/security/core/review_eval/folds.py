"""review_eval.folds -- leave-one-family-out anchor libraries with an explicit leak guard."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from portal.modules.security.core.review.intake import IntakeResult
from portal.modules.security.core.review.pipeline import anchors_from_units


class FoldLeakError(ValueError):
    """A held-out probe event appears in an anchor library for its fold."""


@dataclass(frozen=True)
class FamilyFold:
    held_out_family: str
    anchors: tuple[Any, ...]
    probe_event_ids: frozenset[str]
    library_event_ids: frozenset[str]


def _anchor_event_ids(anchor: Any) -> set[str]:
    record = getattr(anchor, "record", None)
    if not isinstance(record, Mapping):
        raise FoldLeakError("fold anchor has no metadata record")
    event_ids = record.get("event_ids")
    if not isinstance(event_ids, (tuple, list)) or not event_ids:
        raise FoldLeakError("fold anchor lacks source event ids needed to prove isolation")
    return {str(event_id) for event_id in event_ids}


def assert_no_probe_leak(
    anchors: Sequence[Any], probe_event_ids: set[str] | frozenset[str]
) -> None:
    """Fail closed if a fold library is missing source receipts or overlaps its probe."""
    for anchor in anchors:
        leaked = _anchor_event_ids(anchor) & set(probe_event_ids)
        if leaked:
            raise FoldLeakError(
                f"held-out family leaked {len(leaked)} event id(s) into anchor "
                f"{getattr(anchor, 'anchor_id', '<unknown>')}"
            )


def build_leave_one_family_out(
    attack_windows: Mapping[str, IntakeResult],
) -> dict[str, FamilyFold]:
    """Build each fold from other attack families using the product intake unit representation."""
    if len(attack_windows) < 2:
        raise ValueError("leave-one-family-out needs at least two attack families")
    folds: dict[str, FamilyFold] = {}
    for held_out, probe in sorted(attack_windows.items()):
        probe_ids = frozenset(probe.events)
        anchors: list[Any] = []
        library_ids: set[str] = set()
        ordinal = 0
        for family, library in sorted(attack_windows.items()):
            if family == held_out:
                continue
            for unit in library.units:
                event_ids = tuple(unit.event_ids)
                library_ids.update(event_ids)
                anchors.extend(
                    anchors_from_units(
                        [unit],
                        kind="attack_episode",
                        label=f"attack family {family}",
                        malice="malicious",
                        prefix=f"fold-{held_out}-{ordinal:06d}",
                        metadata={"family": family, "event_ids": list(event_ids)},
                    )
                )
                ordinal += 1
        assert_no_probe_leak(anchors, probe_ids)
        folds[held_out] = FamilyFold(
            held_out_family=held_out,
            anchors=tuple(anchors),
            probe_event_ids=probe_ids,
            library_event_ids=frozenset(library_ids),
        )
    return folds
