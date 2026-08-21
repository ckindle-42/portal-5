"""bully.cousin_inject -- generate and ship cousins of answer-key-confirmed
BOTS techniques into the real corpus via Lane B (C.5, TASK_BULLY_CORPUS_BED_V1).

No new transport: this reuses `siem.hec_ship.ship_batch`, the same primitive
`scripts/corpus_ingest.py` already uses for Lane B. Every injected event is
tagged `evidence_origin=corpus:cousin:<cousin_id>`, attributable and
reversible with the documented rollback
(`unit-corpus-injection-rollback`):

    index=<lab index> evidence_origin=corpus:cousin:* | delete

The grader never sees this tag (Q3): it rides in the HEC envelope's `source`
field (Splunk-side metadata `ship_batch` sets from `evidence_origin`), never
inside the shipped event body itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..siem.hec_ship import ship_batch
from . import corpus_bed

ALGORITHM_VERSION = "cousin-inject-v1"

# REVOCABULARY/RESCHEMA/SCATTER cousins must share NO literal action token
# with their parent's behavioural spine -- recoverable only at the
# behavioural level, which is the whole claim (C.5). REORDER_MINOR and
# REIDENTITY keep the parent's own verbs (they vary order/principal, not
# vocabulary), so they are deliberately absent from this map.
#
# Keyed on the shared behaviour-class alphabet (T1, TASK_BULLY_REAL_
# TELEMETRY_V1) -- `bots_answer_key.BOTS_ANSWER_KEY.behavioural_spine` was
# updated to that vocabulary (`auth`/`escalate`/`c2_exfil`/`execute`, ...)
# so `discovery.enrich()` can compare a real-classified cluster shape
# against it; this map's keys moved with it.
_REVOCABULARY_MAP: dict[str, str] = {
    "auth": "identity_ticket_probe",
    "escalate": "privilege_state_change",
    "c2_exfil": "periodic_outbound_signal",
    "execute": "background_worker_launch",
    "enumerate": "passive_directory_sweep",
    "collect": "staged_artifact_pull",
    "persist": "residual_footprint_write",
    "evade": "trace_suppression_action",
    "lateral": "adjacent_session_pivot",
    "destroy": "irreversible_state_removal",
}

_REVOCABULARIED_TRANSFORMATIONS = frozenset({"REVOCABULARY", "RESCHEMA", "SCATTER"})


def _cousin_spine(cousin: corpus_bed.CousinSpec) -> tuple[str, ...]:
    if cousin.transformation in _REVOCABULARIED_TRANSFORMATIONS:
        return tuple(
            _REVOCABULARY_MAP.get(step, f"variant_{step}") for step in cousin.behavioural_spine
        )
    return cousin.behavioural_spine


def render_cousin_event(cousin: corpus_bed.CousinSpec, *, step_index: int) -> dict[str, Any]:
    """One synthetic event body for a single step of a cousin's spine."""
    spine = _cousin_spine(cousin)
    step = spine[step_index % len(spine)] if spine else "unknown_step"
    return {
        "action": step,
        "cousin_id": cousin.cousin_id,
        "parent_technique": cousin.parent_technique,
        "transformation": cousin.transformation,
        "step_index": step_index,
    }


@dataclass(frozen=True)
class InjectReport:
    cousin_id: str
    sourcetypes_used: tuple[str, ...]
    n_events: int
    ok: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "cousin_id": self.cousin_id,
            "sourcetypes_used": list(self.sourcetypes_used),
            "n_events": self.n_events,
            "ok": self.ok,
        }


def inject_cousins(
    cousins: list[corpus_bed.CousinSpec],
    *,
    corpus_earliest: float,
    corpus_latest: float,
    index: str | None = None,
    dry_run: bool = True,
) -> list[InjectReport]:
    """Ship every planned cousin's synthetic events via `ship_batch`, each at
    its own `cousin.injected_at` -- inside the corpus's real time range,
    never at ship time (`now`). `corpus_earliest`/`corpus_latest` are
    required, not defaulted: an injection with no real range to be validated
    against is exactly the T.3 defect (cousins shipped ~8 years outside
    every BOTS index). A cousin whose `injected_at` falls outside that range
    is refused outright with `CousinOutsideCorpusRangeError`
    (`cousin_outside_corpus_range`), never silently shipped.

    SCATTER cousins round-robin their spine's steps across every target
    sourcetype (the whole point of the transformation -- a chain expressed
    across several real sourcetypes and identities); every other
    transformation ships to its single resolved sourcetype.
    """
    for cousin in cousins:
        corpus_bed.validate_cousin_in_range(
            cousin, corpus_earliest=corpus_earliest, corpus_latest=corpus_latest
        )

    target_index = index or corpus_bed.CORPUS_INDEX
    reports: list[InjectReport] = []
    for cousin in cousins:
        sourcetypes = cousin.target_sourcetypes or ("corpus:cousin",)
        spine = _cousin_spine(cousin)
        events_by_sourcetype: dict[str, list[dict[str, Any]]] = {}
        for i in range(len(spine)):
            st = (
                sourcetypes[i % len(sourcetypes)]
                if cousin.transformation == "SCATTER"
                else sourcetypes[0]
            )
            events_by_sourcetype.setdefault(st, []).append(
                render_cousin_event(cousin, step_index=i)
            )
        ok = True
        n_events = 0
        for st, events in events_by_sourcetype.items():
            result = ship_batch(
                events,
                sourcetype=st,
                host=f"corpus-cousin-{cousin.cousin_id}",
                index=target_index,
                event_times=[cousin.injected_at] * len(events),
                evidence_origin=f"corpus:cousin:{cousin.cousin_id}",
                evidence_provenance="cousin_injection",
                dry_run=dry_run,
            )
            ok = ok and bool(result.get("ok"))
            n_events += len(events)
        reports.append(
            InjectReport(
                cousin_id=cousin.cousin_id,
                sourcetypes_used=tuple(events_by_sourcetype),
                n_events=n_events,
                ok=ok,
            )
        )
    return reports
