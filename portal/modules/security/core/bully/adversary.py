"""bully.adversary -- HEART, the adversarial council + durable objection
gate (P2.3). API per I-8: ``review(candidate) -> CouncilRecord``.

The decision mechanism is the objection gate, not a vote: this module
reuses platform ``council.py``'s ``parse_opinion`` (seat-response parsing)
and its participation accounting *only* -- ``aggregate_opinions`` (the
vote-count decision) is deliberately never imported or called here (I-8).

Materiality validation and roster-diversity enforcement are code, not
model output: a seat's stated objection is classified into one of the
enumerated categories by code (`_classify_category`); whether it is
*material* is a code rule over that seat's own recommendation, not
something a model asserts about itself.

Model calls happen only inside this module (+ investigation.py/handoff.py/
playbooks.py, MASTER SS3) -- always through the existing `_call_model`
pattern (pipeline default -> direct-Ollama fallback), never a raw HTTP call
authored here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from portal.platform.inference.router.council import CouncilOpinion, parse_opinion

from . import config as bully_config
from .contracts import (
    OBJECTION_CATEGORIES,
    CouncilOpinionRecord,
    CouncilRecord,
    DecisionEvent,
    Objection,
    Rebuttal,
    new_id,
)
from .store import Store

_FAMILY_RE = re.compile(r"^[a-z]+")

_MATERIALITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "evidence_contradiction": ("contradict", "inconsistent", "conflicts with"),
    "covering_detection_id": ("existing detection", "already covered", "duplicate detection"),
    "benign_counter_evidence": ("benign", "legitimate", "authorized", "false positive"),
    "scope_safety": ("out of scope", "unsafe", "unauthorized target"),
    "reproducibility": ("not reproduc", "cannot reproduce", "flaky", "did not fire again"),
    "telemetry_health": ("telemetry", "sensor", "missing log", "unhealthy"),
    "relationship_classification": ("misclassif", "wrong relationship", "not similar", "not same"),
    "defense_response": ("response status", "detection status wrong", "miscategorized response"),
    "analyst_visibility": ("soc", "analyst", "not visible", "no triage"),
    "regression_risk": ("regression", "break existing", "noisy detection"),
}


def _family_of(model_tag: str) -> str:
    """Independence-family heuristic: the alphabetic prefix of the model's
    own path segment (`granite4.1:30b-ctx16k` -> `granite`,
    `mistral-small3.2:24b` -> `mistral`, `hf.co/org/Foundation-Sec-8B` ->
    `foundation`). Good enough for I-19's diversity check without a second
    hardcoded model->family table."""
    base = model_tag.split("/")[-1].split(":")[0]
    m = _FAMILY_RE.match(base.lower())
    return m.group(0) if m else base.lower()


def resolve_roster(*, hunt_config: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """HEART's seat roster: `{"seat_id", "model", "family"}` per seat,
    resolved from config (never hardcoded, MASTER SS11)."""
    models = bully_config.resolve_council_models(hunt_config=hunt_config)
    return [
        {"seat_id": f"seat-{i}", "model": model, "family": _family_of(model)}
        for i, model in enumerate(models)
    ]


def validate_roster_diversity(
    roster: list[dict[str, str]], *, min_seats: int, min_independence_families: int
) -> None:
    """I-19 / C8 CLAIM 5: 'roster family-diversity constraint rejects a
    mono-family roster at config load.'"""
    if len(roster) < min_seats:
        raise ValueError(f"HEART roster has {len(roster)} seat(s), needs >= {min_seats}")
    families = {seat["family"] for seat in roster}
    if len(families) < min_independence_families:
        raise ValueError(
            f"HEART roster spans {len(families)} independent famil{'y' if len(families) == 1 else 'ies'} "
            f"({sorted(families)}), needs >= {min_independence_families} -- mono-family roster rejected"
        )


def _classify_category(text: str) -> str | None:
    lowered = text.lower()
    for category, keywords in _MATERIALITY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return None


CallModelFn = Callable[..., dict]


def _default_call_model(model: str, messages: list[dict]) -> dict:
    from ..agentic_blue_eval import _call_model

    return _call_model(model, messages, max_tokens=1200)


_REVIEW_SYSTEM_PROMPT = (
    "You are an adversarial reviewer on Portal 5's HEART falsification council. "
    "A candidate hunt finding is presented with its evidence and gate results so far. "
    "Your job is to try to falsify it, not to be agreeable. Return the standard "
    "council JSON contract (recommendation, confidence, findings, missing_evidence, "
    "strongest_objection, conditions_to_change). Use REJECT only when you have a "
    "concrete falsifying objection; use ABSTAIN if the material is insufficient."
)


def _render_packet(candidate_row: dict, context: dict) -> str:
    lines = [
        f"candidate_id: {candidate_row.get('candidate_id')}",
        f"current_state: {candidate_row.get('current_state')}",
        f"alert_version: {candidate_row.get('alert_version')}",
    ]
    for key, value in sorted((context or {}).items()):
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _run_seat(
    seat: dict[str, str], candidate_row: dict, context: dict, *, call_model: CallModelFn
) -> CouncilOpinionRecord:
    packet_text = _render_packet(candidate_row, context)
    try:
        msg = call_model(
            seat["model"],
            [
                {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": f"## CANDIDATE PACKET\n\n{packet_text}"},
            ],
        )
        text = msg.get("content", "") if isinstance(msg, dict) else ""
        opinion: CouncilOpinion = parse_opinion(
            {"id": seat["seat_id"], "label": seat["seat_id"], "model": seat["model"]}, text
        )
    except Exception as exc:  # seat failure -> non-participant (I-8 failure semantics)
        opinion = parse_opinion(
            {"id": seat["seat_id"], "label": seat["seat_id"], "model": seat["model"]},
            "",
            error=f"{type(exc).__name__}: {exc}",
        )
    return CouncilOpinionRecord(
        opinion_id=new_id("cop"),
        packet_id="",  # filled in by the caller once the packet_id is known
        seat_id=seat["seat_id"],
        attempt=1,
        member_id=seat["seat_id"],
        model=seat["model"],
        family=seat["family"],
        valid=opinion.valid,
        recommendation=opinion.recommendation,
        confidence=opinion.confidence,
        error=opinion.error,
        findings=opinion.findings,
        strongest_objection=opinion.strongest_objection,
        missing_evidence=opinion.missing_evidence,
        conditions_to_change=opinion.conditions_to_change,
    )


def _record_event(
    store: Store, *, hunt_id, actor: str, kind: str, subject_id: str, rationale: str, data: dict
) -> None:
    store.record_decision(
        DecisionEvent(
            event_id=new_id("de"),
            hunt_id=hunt_id,
            iteration_id=None,
            actor=actor,
            kind=kind,
            subject_id=subject_id,
            rationale=rationale,
            data=data,
        )
    )


def review(
    candidate_row: dict,
    context: dict | None = None,
    *,
    store: Store,
    hunt_config: dict[str, Any] | None = None,
    heart_config: dict[str, Any] | None = None,
    call_model: CallModelFn | None = None,
    actor: str = "system:adversary",
) -> CouncilRecord:
    """I-8: gather independent seat opinions, classify objections, and
    apply the objection gate (code, not a vote). `unresolved=True` iff a
    material objection currently has status 'open' -- rebuttal/withdrawal/
    waiver close it via `rebut`/`withdraw_objection`/`waive_objection`
    below, each of which re-persists the recomputed `unresolved` flag."""
    context = context or {}
    hunt_config = hunt_config or bully_config.load_hunt_config()
    heart_config = heart_config or bully_config.load_heart_config()
    roster_cfg = heart_config.get("roster", {})
    floors_cfg = heart_config.get("floors", {})
    materiality_version = heart_config.get("materiality_version", "bully-heart-materiality-v1")

    roster = resolve_roster(hunt_config=hunt_config)
    validate_roster_diversity(
        roster,
        min_seats=roster_cfg.get("min_seats", 3),
        min_independence_families=roster_cfg.get("min_independence_families", 2),
    )

    call_model = call_model or _default_call_model
    packet_id = new_id("pkt")
    evidence_manifest_hash = context.get("evidence_manifest_hash", "")

    # Insert the packet row first (provisional values) -- council_opinions
    # and objections FK-reference council_packets, so the packet must exist
    # before any seat's opinion is persisted. Finalized below once all
    # seats have answered and objections are classified.
    store.council_packet_put(
        packet_id=packet_id,
        candidate_id=candidate_row["candidate_id"],
        evidence_manifest_id=candidate_row.get("evidence_manifest_id"),
        evidence_manifest_hash=evidence_manifest_hash,
        roster_snapshot={"seats": roster},
        materiality_version=materiality_version,
        unresolved=False,
        review_valid=True,
        participation=None,
    )

    opinions: list[CouncilOpinionRecord] = []
    for seat in roster:
        opinion = _run_seat(seat, candidate_row, context, call_model=call_model)
        opinion = _with_packet_id(opinion, packet_id)
        opinions.append(opinion)
        store.council_opinion_put(
            opinion_id=opinion.opinion_id,
            packet_id=packet_id,
            seat_id=opinion.seat_id,
            attempt=opinion.attempt,
            member_id=opinion.member_id,
            model=opinion.model,
            family=opinion.family,
            valid=opinion.valid,
            recommendation=opinion.recommendation,
            confidence=opinion.confidence,
            error=opinion.error,
            findings=opinion.findings,
            strongest_objection=opinion.strongest_objection,
            missing_evidence=opinion.missing_evidence,
            conditions_to_change=opinion.conditions_to_change,
        )

    # Participation accounting (reused from council.py's own logic: valid
    # AND not a bare ABSTAIN counts as participating) -- never
    # aggregate_opinions (I-8: the decision is the objection gate).
    participating = sum(1 for o in opinions if o.valid and o.recommendation != "ABSTAIN")
    participation = participating / len(roster) if roster else 0.0
    min_participation = floors_cfg.get("min_participation", 0.6)
    review_valid = participation >= min_participation

    objections: list[Objection] = []
    if review_valid:
        for opinion in opinions:
            if not opinion.valid or not opinion.strongest_objection:
                continue
            category = _classify_category(opinion.strongest_objection)
            if category is None:
                continue
            material = opinion.recommendation == "REJECT"
            objection = Objection(
                objection_id=new_id("obj"),
                packet_id=packet_id,
                seat_id=opinion.seat_id,
                category=category,
                material=material,
                claim=opinion.strongest_objection,
                evidence_citations=opinion.missing_evidence,
                status="open",
            )
            objections.append(objection)
            store.objection_put(
                objection_id=objection.objection_id,
                packet_id=packet_id,
                seat_id=opinion.seat_id,
                category=category,
                material=material,
                claim=objection.claim,
                evidence_citations=objection.evidence_citations,
                missing_proof_citations=[],
                status="open",
            )

    unresolved = any(o.material for o in objections)

    store.council_packet_finalize(
        packet_id, review_valid=review_valid, participation=participation, unresolved=unresolved
    )
    _record_event(
        store,
        hunt_id=candidate_row.get("hunt_id"),
        actor=actor,
        kind="council_block" if unresolved else "objection",
        subject_id=candidate_row["candidate_id"],
        rationale=(
            f"HEART review: participation={participation:.2f} valid={review_valid} "
            f"unresolved={unresolved} objections={len(objections)}"
        ),
        data={"packet_id": packet_id, "objection_ids": [o.objection_id for o in objections]},
    )

    return CouncilRecord(
        packet_id=packet_id,
        candidate_id=candidate_row["candidate_id"],
        evidence_manifest_hash=evidence_manifest_hash,
        materiality_version=materiality_version,
        roster_snapshot={"seats": roster},
        opinions=opinions,
        objections=objections,
        rebuttals=[],
        unresolved=unresolved,
        review_valid=review_valid,
        participation=participation,
    )


def _with_packet_id(opinion: CouncilOpinionRecord, packet_id: str) -> CouncilOpinionRecord:
    from dataclasses import replace

    return replace(opinion, packet_id=packet_id)


_STANDING_STATUSES = frozenset({"open", "re_review", "sustained"})


def _recompute_and_persist_unresolved(store: Store, packet_id: str) -> bool:
    """A material objection is still 'standing' (and therefore blocks) while
    its status is open/re_review/sustained; rebutted/withdrawn/waived/
    superseded all close it (I-8 "closure paths")."""
    objections = store.objections_for_packet(packet_id)
    unresolved = any(o["material"] and o["status"] in _STANDING_STATUSES for o in objections)
    store.council_packet_set_unresolved(packet_id, unresolved)
    return unresolved


def rebut(
    store: Store,
    objection_id: str,
    *,
    author: str,
    claim: str,
    evidence_citations: list[str],
    falsification_repass: bool = False,
    actor: str = "system:adversary",
) -> Rebuttal:
    """I-8 closure path 1: 'rebuttal with cited evidence + falsification
    re-pass on the same evidence version [closes the objection].' A
    rebuttal without a confirmed falsification re-pass moves the objection
    to `re_review` (still open for the purposes of `unresolved`, awaiting
    that re-pass) rather than silently closing it."""
    objection = store.objection_get(objection_id)
    if objection is None:
        raise ValueError(f"no such objection: {objection_id}")
    rebuttal_id = new_id("reb")
    store.rebuttal_put(
        rebuttal_id=rebuttal_id,
        objection_id=objection_id,
        author=author,
        claim=claim,
        evidence_citations=evidence_citations,
        requested_review="falsification_repass" if not falsification_repass else None,
        re_review_result="confirmed" if falsification_repass else None,
    )
    new_status = "rebutted" if falsification_repass else "re_review"
    store.objection_set_status(objection_id, new_status)
    unresolved = _recompute_and_persist_unresolved(store, objection["packet_id"])
    _record_event(
        store,
        hunt_id=None,
        actor=actor,
        kind="objection",
        subject_id=objection_id,
        rationale=f"rebuttal recorded (falsification_repass={falsification_repass}) -> {new_status}",
        data={"packet_id": objection["packet_id"], "unresolved": unresolved},
    )
    return Rebuttal(
        rebuttal_id=rebuttal_id,
        objection_id=objection_id,
        author=author,
        claim=claim,
        evidence_citations=evidence_citations,
        requested_review=None if falsification_repass else "falsification_repass",
        re_review_result="confirmed" if falsification_repass else None,
    )


def withdraw_objection(
    store: Store, objection_id: str, *, seat_id: str, actor: str = "system:adversary"
) -> None:
    """I-8 closure path 2: withdrawal by the originating (or equally
    independent) seat. A seat other than the originating one may withdraw
    only if it is a distinct, equally-independent seat on the same
    packet's roster -- enforced here by checking `seat_id` against the
    objection's own `seat_id` OR the packet's roster membership (equal
    independence is the roster's own diversity guarantee, already enforced
    at review() time)."""
    objection = store.objection_get(objection_id)
    if objection is None:
        raise ValueError(f"no such objection: {objection_id}")
    packet = store.council_packet_get(objection["packet_id"])
    roster_snapshot = json.loads(packet["roster_snapshot"]) if packet else {}
    roster_seat_ids = {s["seat_id"] for s in (roster_snapshot.get("seats") or [])}
    if seat_id != objection["seat_id"] and seat_id not in roster_seat_ids:
        raise ValueError(
            f"seat {seat_id!r} is not the originating seat and not on the packet's roster -- "
            f"withdrawal denied"
        )
    store.objection_set_status(objection_id, "withdrawn")
    unresolved = _recompute_and_persist_unresolved(store, objection["packet_id"])
    _record_event(
        store,
        hunt_id=None,
        actor=actor,
        kind="objection",
        subject_id=objection_id,
        rationale=f"objection withdrawn by seat={seat_id}",
        data={"packet_id": objection["packet_id"], "unresolved": unresolved},
    )


def waive_objection(store: Store, objection_id: str, *, operator_actor: str, reason: str) -> None:
    """`[GATE]` I-8: 'the objection waiver is a separate authenticated
    operator command with a durable reason, visible in the handoff.'
    Operator-only -- refuses any non-operator actor before ever touching
    the store, mirroring `store.promotion_resolve`'s own guard."""
    if not operator_actor.startswith("operator:"):
        raise ValueError(
            f"actor {operator_actor!r} is not an operator; waive_objection requires "
            f"actor='operator:<id>'"
        )
    if not reason.strip():
        raise ValueError("waive_objection requires a durable, non-empty reason")
    objection = store.objection_get(objection_id)
    if objection is None:
        raise ValueError(f"no such objection: {objection_id}")
    store.objection_set_status(objection_id, "waived")
    unresolved = _recompute_and_persist_unresolved(store, objection["packet_id"])
    _record_event(
        store,
        hunt_id=None,
        actor=operator_actor,
        kind="waiver",
        subject_id=objection_id,
        rationale=reason,
        data={"packet_id": objection["packet_id"], "unresolved": unresolved},
    )


__all__ = [
    "OBJECTION_CATEGORIES",
    "resolve_roster",
    "validate_roster_diversity",
    "review",
    "rebut",
    "withdraw_objection",
    "waive_objection",
]
