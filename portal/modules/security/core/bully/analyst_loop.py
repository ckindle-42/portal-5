"""bully.analyst_loop -- the verdict loop that makes the system mature.

The hinge the whole flywheel turns on, and the one piece that was never
built. Everything upstream -- universal intake, entity correlation, series
alignment, the pyramid axis -- produces concerns. Everything downstream --
`compounding.write_outcome_as_anchor`, `compounding.should_escalate`, the
T0-T3 analyst corpus, BIN, handoff, the LoRA flywheel -- consumes *analyst
verdicts*. Between them there was nothing: no queue, no verdict capture, no
write-back. So no `BENIGN_CLOSE` anchor was ever created, `should_escalate`
could never suppress anything, the corpus never grew in either direction,
and every cycle re-graded against a static library and re-raised the same
noise.

The design this implements is deliberately **not** a gate. There is no
filter deciding what deserves attention:

  - Fire on **knowns AND unknowns that are same-or-similar**. A known-bad and
    an unknown cousin both reach the analyst; the notification carries the
    class so triage is possible from the alert itself.
  - The analyst decides whether it is **actually something, or just noise**.
  - **Both answers are knowledge.** "Nothing" is not a discard -- it is
    documented as a `BENIGN_CLOSE` anchor, and `should_escalate` then
    suppresses that neighbourhood next cycle. Suppression is *earned by
    accumulated knowledge*, never set by a threshold.
  - It is **organic, not binary**. A verdict may be `UNSURE`; that still
    writes back, weak and `SYSTEM_GENERATED`/T2, staying in retrieval
    without pretending to be ground truth. Uncertainty is retained, not
    thrown away.

That is why the system *matures* rather than being tuned: noise falls
because the benign side of the corpus grows, and recognition sharpens
because the confirmed side does. BIN and handoff sit further downstream --
they gate the *detection-engineering exit*, where replay and re-execution
are answerable questions, and are not on this notification path at all.

Pure compute over injected store/library/dispatcher seams (COLD); the
notification dispatch is fire-and-forget and never fatal, mirroring
`promotion._notify_queue_arrival`.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

ALGORITHM_VERSION = "analyst-loop-v1"

# The three-way verdict. Deliberately not promote/kill: an analyst who cannot
# tell yet must be able to say so without that being coerced into a decision.
CONFIRMED = "CONFIRMED"  # it is something
BENIGN = "BENIGN"  # investigated, it is nothing -- documented, not discarded
UNSURE = "UNSURE"  # cannot tell yet -- retained, matures

VERDICTS: tuple[str, ...] = (CONFIRMED, BENIGN, UNSURE)

# Verdict -> the outcome written back as an anchor. Every verdict writes.
_VERDICT_OUTCOME: dict[str, str] = {
    CONFIRMED: "ESCALATE",
    BENIGN: "BENIGN_CLOSE",
    UNSURE: "ANOMALOUS_UNCLASSIFIED",
}

# Only an explicit CONFIRMED/BENIGN is an analyst label basis; UNSURE stays
# SYSTEM_GENERATED so it enters retrieval but cannot raise confidence (G.2).
_VERDICT_ANALYST_CONFIRMED: dict[str, bool] = {
    CONFIRMED: True,
    BENIGN: True,
    UNSURE: False,
}

# The concern classes that fire. BOTH knowns and unknowns notify -- that is
# the product requirement, not a tunable.
KNOWN_CLASSES: frozenset[str] = frozenset({"SAME"})
UNKNOWN_CLASSES: frozenset[str] = frozenset({"SIMILAR", "ANOMALOUS_UNCLASSIFIED"})
NOTIFYING_CLASSES: frozenset[str] = KNOWN_CLASSES | UNKNOWN_CLASSES


def concern_class(relationship: str) -> str:
    """`known_bad` vs `unknown_cousin` -- carried in the notification so an
    analyst can triage from the alert, and so a Splunk notable / email can be
    built from the payload directly."""
    if relationship in KNOWN_CLASSES:
        return "known_bad"
    if relationship in UNKNOWN_CLASSES:
        return "unknown_cousin"
    return "not_a_concern"


@dataclass(frozen=True)
class Concern:
    """A queued item awaiting analyst review. Carries everything needed to
    decide without going back to raw logs."""

    concern_id: str
    assessment_id: str
    entity_id: str
    relationship: str
    concern_class: str
    match_level: str
    robustness: float
    n_sources: int
    source_ids: tuple[str, ...]
    span_seconds: float | None
    aligned_spine: tuple[str, ...]
    resembles: str | None
    brief: str
    raised_at: float = field(default_factory=time.time)
    verdict: str | None = None
    verdict_note: str = ""
    verdict_at: float | None = None

    @property
    def is_open(self) -> bool:
        return self.verdict is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "concern_id": self.concern_id,
            "assessment_id": self.assessment_id,
            "entity_id": self.entity_id,
            "relationship": self.relationship,
            "concern_class": self.concern_class,
            "match_level": self.match_level,
            "robustness": self.robustness,
            "n_sources": self.n_sources,
            "source_ids": list(self.source_ids),
            "span_seconds": self.span_seconds,
            "aligned_spine": list(self.aligned_spine),
            "resembles": self.resembles,
            "brief": self.brief,
            "raised_at": self.raised_at,
            "verdict": self.verdict,
            "verdict_note": self.verdict_note,
            "verdict_at": self.verdict_at,
        }


NotifyFn = Callable[[dict[str, Any]], None]


def _default_notify(payload: dict[str, Any]) -> None:
    """Reuse the existing dispatcher exactly as `promotion._notify_queue_arrival`
    does -- same channels, fire-and-forget, never fatal. A Splunk notable or
    an email escalation is a CHANNEL added here later, not a redesign."""
    try:
        from portal.platform.inference.notifications import (
            AlertEvent,
            EventType,
            NotificationDispatcher,
        )
        from portal.platform.inference.notifications.channels import (
            EmailChannel,
            PushoverChannel,
            SlackChannel,
            TelegramChannel,
            WebhookChannel,
        )

        disp = NotificationDispatcher()
        for ch in (
            SlackChannel(),
            TelegramChannel(),
            EmailChannel(),
            PushoverChannel(),
            WebhookChannel(),
        ):
            disp.add_channel(ch)
        cls = payload.get("concern_class", "concern")
        disp._schedule(
            disp.dispatch(
                AlertEvent(
                    type=EventType.CONCERN_RAISED,
                    message=(
                        f"Bully {cls}: {payload.get('relationship')} on "
                        f"{payload.get('entity_id')} across "
                        f"{payload.get('n_sources')} sources -- {payload.get('brief', '')[:160]}"
                    ),
                    metadata=payload,
                )
            )
        )
    except Exception:  # pragma: no cover -- notify failure is never fatal
        pass


def build_brief(
    *,
    relationship: str,
    entity_id: str,
    n_sources: int,
    source_ids: tuple[str, ...],
    aligned_spine: tuple[str, ...],
    resembles: str | None,
    span_seconds: float | None,
) -> str:
    """A sentence an analyst can act on without opening raw logs."""
    what = (
        "matches a known technique"
        if relationship in KNOWN_CLASSES
        else (
            "resembles a known technique but is not one we know"
            if resembles
            else "shows notable behaviour matching nothing known"
        )
    )
    spine = " -> ".join(aligned_spine) if aligned_spine else "no shared behavioural spine"
    span = f"{span_seconds:.0f}s" if span_seconds else "unknown span"
    ref = f" (resembles {resembles})" if resembles else ""
    return (
        f"{entity_id} {what}{ref}: behaviour {spine}, seen across {n_sources} "
        f"source(s) {list(source_ids)[:4]} within {span}."
    )


def raise_concern(
    *,
    assessment_id: str,
    entity_id: str,
    relationship: str,
    match_level: str = "",
    robustness: float = 0.0,
    n_sources: int = 0,
    source_ids: tuple[str, ...] = (),
    span_seconds: float | None = None,
    aligned_spine: tuple[str, ...] = (),
    resembles: str | None = None,
    notify: NotifyFn | None = None,
    should_escalate: bool = True,
) -> Concern | None:
    """Queue a concern and notify. Returns None when `should_escalate` is
    False -- the ONLY suppressor, and it is knowledge-driven
    (`compounding.should_escalate`: the nearest match is a BENIGN_CLOSE
    anchor an analyst already closed), never a threshold or a gate.
    """
    if relationship not in NOTIFYING_CLASSES:
        return None
    if not should_escalate:
        return None

    cls = concern_class(relationship)
    brief = build_brief(
        relationship=relationship,
        entity_id=entity_id,
        n_sources=n_sources,
        source_ids=source_ids,
        aligned_spine=aligned_spine,
        resembles=resembles,
        span_seconds=span_seconds,
    )
    concern = Concern(
        concern_id=f"cn-{uuid.uuid4().hex[:12]}",
        assessment_id=assessment_id,
        entity_id=entity_id,
        relationship=relationship,
        concern_class=cls,
        match_level=match_level,
        robustness=robustness,
        n_sources=n_sources,
        source_ids=source_ids,
        span_seconds=span_seconds,
        aligned_spine=aligned_spine,
        resembles=resembles,
        brief=brief,
    )
    (notify or _default_notify)(concern.to_dict())
    return concern


def record_verdict(
    concern: Concern,
    verdict: str,
    *,
    note: str = "",
    anchor_library: Any = None,
    signature: Any = None,
    source_id: str = "analyst",
    write_back: Callable[..., Any] | None = None,
) -> tuple[Concern, Any]:
    """Record an analyst verdict and write it back as knowledge.

    EVERY verdict writes -- `CONFIRMED` and `BENIGN` as analyst-confirmed
    (label basis `analyst_decision`, ANALYST_CONFIRMED tier), `UNSURE` weak
    and SYSTEM_GENERATED so it enters retrieval without raising confidence.
    "Nothing" is documented, not discarded: that BENIGN_CLOSE anchor is what
    lets `should_escalate` quiet the neighbourhood next cycle.
    """
    if verdict not in VERDICTS:
        raise ValueError(f"unknown verdict {verdict!r}; expected one of {VERDICTS}")

    closed = Concern(
        **{
            **{
                k: v
                for k, v in concern.to_dict().items()
                if k not in ("verdict", "verdict_note", "verdict_at", "source_ids", "aligned_spine")
            },
            "source_ids": concern.source_ids,
            "aligned_spine": concern.aligned_spine,
            "verdict": verdict,
            "verdict_note": note,
            "verdict_at": time.time(),
        }
    )

    anchor = None
    if anchor_library is not None and signature is not None:
        fn = write_back
        if fn is None:
            from . import compounding

            fn = compounding.write_outcome_as_anchor
        anchor = fn(
            anchor_library,
            signature,
            source_id=source_id,
            outcome=_VERDICT_OUTCOME[verdict],
            analyst_confirmed=_VERDICT_ANALYST_CONFIRMED[verdict],
        )
    return closed, anchor


def open_queue(concerns: list[Concern]) -> list[Concern]:
    """The review queue: everything awaiting an analyst, richest first. The
    enumeration the store never had."""
    return sorted(
        [c for c in concerns if c.is_open],
        key=lambda c: (c.concern_class == "unknown_cousin", c.n_sources, c.robustness),
        reverse=True,
    )


def maturation_report(before: list[Concern], after: list[Concern]) -> dict[str, Any]:
    """Cycle-over-cycle change -- the measure that distinguishes a maturing
    system from a matcher. A system that has learned raises FEWER concerns on
    the same telemetry (benign neighbourhoods suppressed) while retaining the
    confirmed ones."""
    b_ids = {c.entity_id for c in before}
    a_ids = {c.entity_id for c in after}
    return {
        "concerns_before": len(before),
        "concerns_after": len(after),
        "suppressed_entities": sorted(b_ids - a_ids),
        "n_suppressed": len(b_ids - a_ids),
        "still_raised": sorted(b_ids & a_ids),
        "newly_raised": sorted(a_ids - b_ids),
        "noise_reduction": (round((len(before) - len(after)) / len(before), 4) if before else None),
    }
