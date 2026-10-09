"""review.verdicts -- an analyst's verdict becomes knowledge; the machine never overrules it.

``record_verdict`` is the whole learning loop:

* ``something`` -> a ``confirmed_finding`` anchor (malicious): the next occurrence is the floor
  ("existing knowledge owns it"), and cousins of it are found as cousins.
* ``nothing``   -> a ``benign_pattern`` anchor. Suppression of a later look-alike is a policy
  (``pipeline.ReviewConfig.suppress_benign``, default ``exact_only``): only an EXACT repeat is
  silenced; a malicious cousin of a benign-closed pattern still surfaces.
* ``unsure``    -> nothing is learned; the concern stays in the queue.

A reversal (a later verdict opposite to an earlier one) quarantines the anchor the earlier one
wrote -- poisoned knowledge is quarantined, never deleted, and a replay "as of" a past time
still sees what was believed then. Scripted verdicts (a harness answering with ground truth)
must say so in the actor name, and are recorded as scripted: a maturation number measured with
a scripted analyst is labelled as such everywhere it appears.

``contradictions`` is the operator's review queue by exception: not every row, only the places
where the system's own records disagree.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .contracts import ReviewConcern, ReviewResult, TruthClass, Verdict, to_plain
from .intake import IntakeResult
from .knowledge import AnchorCard, record_from_unit
from .store import ReviewStore

SCRIPTED_PREFIX = "scripted:"


class VerdictError(ValueError):
    """A verdict that may not be recorded (unknown concern, mislabelled scripted actor)."""


@dataclass
class WriteBack:
    verdict_id: str
    anchor_id: str | None = None
    quarantined: list[str] = field(default_factory=list)


def persist_run(store: ReviewStore, result: ReviewResult, window: IntakeResult) -> list[str]:
    """Store every concern of ``result`` with the unit record needed to learn from it later."""
    by_unit = {u.unit.unit_id: u for u in window.units}
    stored: list[str] = []
    for concern in [*result.concerns, *result.suppressed]:
        unit = by_unit.get(concern.unit_id)
        record = record_from_unit(unit.unit, unit.terms, unit.card) if unit is not None else {}
        if unit is not None:
            record["unit_id"] = unit.unit.unit_id
            record["event_ids"] = list(unit.event_ids)
        store.put_concern(
            result.run_id,
            concern.concern_id,
            concern.unit_id,
            concern.outcome.value,
            concern.priority_p,
            to_plain(concern),
            record,
            at=result.finished_at or None,
        )
        stored.append(concern.concern_id)
    return stored


def _label_for(payload: dict[str, Any], default: str) -> str:
    resembles = payload.get("resembles") or []
    return str(resembles[0]["anchor_label"]) if resembles else default


def record_verdict(
    store: ReviewStore,
    concern_id: str,
    verdict: Verdict,
    *,
    actor: str,
    note: str = "",
    scripted: bool = False,
    at: float | None = None,
) -> WriteBack:
    concern = store.get_concern(concern_id)
    if concern is None:
        raise VerdictError(f"unknown concern {concern_id!r}")
    if not actor.strip():
        raise VerdictError("a verdict needs an actor")
    if scripted != actor.startswith(SCRIPTED_PREFIX):
        raise VerdictError(
            f"scripted verdicts (and only they) use an actor starting {SCRIPTED_PREFIX!r}"
        )

    previous = store.effective_verdict(concern_id)
    verdict_id = store.append_verdict(
        concern_id,
        verdict,
        actor=actor,
        note=note,
        truth_class=TruthClass.OPERATOR_DECISION,
        scripted=scripted,
        at=at,
    )
    out = WriteBack(verdict_id=verdict_id)

    if (
        previous is not None
        and previous.verdict in (Verdict.SOMETHING, Verdict.NOTHING)
        and verdict in (Verdict.SOMETHING, Verdict.NOTHING)
        and previous.verdict != verdict
    ):
        for anchor in store.anchors(include_quarantined=False):
            if anchor.derived_from == concern_id:
                store.quarantine_anchor(anchor.anchor_id, f"reversed by {verdict_id}", at=at)
                out.quarantined.append(anchor.anchor_id)

    if verdict == Verdict.UNSURE or not concern.record.get("card"):
        return out
    malicious = verdict == Verdict.SOMETHING
    anchor_id = f"an-{uuid.uuid4().hex[:12]}"
    store.put_anchor(
        anchor_id=anchor_id,
        kind="confirmed_finding" if malicious else "benign_pattern",
        malice="malicious" if malicious else "benign",
        label=_label_for(
            concern.payload, "analyst-confirmed" if malicious else "analyst-closed-benign"
        ),
        record=concern.record,
        derived_from=concern_id,
        truth_class=TruthClass.OPERATOR_DECISION,
        at=at,
    )
    out.anchor_id = anchor_id
    return out


def cards_from_store(store: ReviewStore, *, as_of: float | None = None) -> list[AnchorCard]:
    """The knowledge a review may use, as of ``as_of`` (None: now)."""
    return [a.card() for a in store.anchors(as_of=as_of) if a.card().text]


def contradictions(store: ReviewStore) -> list[dict[str, Any]]:
    """Where the system's own records disagree -- the review queue, generated not browsed."""
    found: list[dict[str, Any]] = []
    effective: dict[str, Verdict] = {}
    card_of: dict[str, str] = {}
    for concern in store.concerns():
        card_of[concern.concern_id] = concern.card
        history = [
            v
            for v in store.verdicts_for(concern.concern_id)
            if v.truth_class == TruthClass.OPERATOR_DECISION
        ]
        decided = [v.verdict for v in history if v.verdict != Verdict.UNSURE]
        if len(set(decided)) > 1:
            found.append(
                {
                    "kind": "analyst_reversal",
                    "concern_ids": [concern.concern_id],
                    "detail": " -> ".join(v.value for v in decided),
                }
            )
        if history:
            effective[concern.concern_id] = history[-1].verdict
        machine = (concern.payload.get("judge") or {}).get("verdict")
        if (
            history
            and machine in ("something", "nothing")
            and history[-1].verdict.value
            in (
                "something",
                "nothing",
            )
            and machine != history[-1].verdict.value
        ):
            found.append(
                {
                    "kind": "machine_vs_operator",
                    "concern_ids": [concern.concern_id],
                    "detail": f"judge {machine}, analyst {history[-1].verdict.value}",
                }
            )

    by_card: dict[str, list[str]] = defaultdict(list)
    for concern_id, card in card_of.items():
        if card and concern_id in effective and effective[concern_id] != Verdict.UNSURE:
            by_card[card].append(concern_id)
    for ids in by_card.values():
        if len({effective[i] for i in ids}) > 1:
            found.append(
                {
                    "kind": "same_evidence_opposite_verdicts",
                    "concern_ids": sorted(ids),
                    "detail": "identical unit evidence, opposite analyst verdicts",
                }
            )

    benign_cards = {a.record.get("card") for a in store.anchors() if a.malice == "benign"}
    for concern_id, verdict in effective.items():
        if verdict == Verdict.SOMETHING and card_of.get(concern_id) in benign_cards:
            found.append(
                {
                    "kind": "malicious_matches_benign_anchor",
                    "concern_ids": [concern_id],
                    "detail": "confirmed something, yet a benign anchor has the identical card",
                }
            )
    return sorted(found, key=lambda c: (c["kind"], c["concern_ids"]))


def queue_summary(store: ReviewStore, concerns: Sequence[ReviewConcern]) -> dict[str, int]:
    """Counts an analyst sees at a glance: open, decided, unsure."""
    open_n = decided = unsure = 0
    for concern in concerns:
        effective = store.effective_verdict(concern.concern_id)
        if effective is None:
            open_n += 1
        elif effective.verdict == Verdict.UNSURE:
            unsure += 1
        else:
            decided += 1
    return {"open": open_n, "decided": decided, "unsure": unsure}
