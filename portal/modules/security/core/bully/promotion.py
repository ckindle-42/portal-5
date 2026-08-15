"""bully.promotion -- BIN, the suspect-until-proven promotion state machine
(P2.2). API per I-7: ``process``, ``promote``, ``kill``.

Gate order (I-7 "Gate internals", normative): G-1 -> G0 -> G1a -> G1b -> G2
-> HEART (persisted as gate_id='G5') -> G3. Nothing auto-promotes: `process`
only ever advances a candidate as far as AWAITING_OPERATOR; only `promote`
(operator-only, delegating to `store.candidate_promote`'s DB-enforced check)
moves AWAITING_OPERATOR -> PROMOTED.

Boundary rules (MASTER SS3): this module is invoked BY orchestrator.py, it
does not sequence a hunt iteration itself -- only the bin's own internal
gate sequence. It never touches SQL directly (`store.py` is the sole SQL
owner); every gate write goes through a `Store` method. Model calls happen
only in adversary.py (HEART) -- this module calls `adversary.review`, it
never calls a model itself.

Each gate's *default* implementation is a real check against the existing
lab/telemetry machinery (capture_store replay, benign_corpus_bench,
blue_orchestrate's verdict-grounding policy) -- never a placeholder-true
leg (MASTER SS0 / the P2 task file's "growth_loop disease" failure
meaning). Every gate accepts an injectable override (mirroring
orchestrator.py's `lab_driver`/`investigation_arm` injection pattern) so
unit tests stay hermetic (no network/Splunk/Ollama) while the production
default path is the real check.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from typing import Any

from . import evidence as evidence_mod
from .contracts import BinOutcome, DecisionEvent, new_id
from .store import Store

GATE_POLICY_VERSION = "bin-gates-v1"


def _bully_notify_enabled() -> bool:
    return os.environ.get("BULLY_NOTIFY_ENABLED", "true").lower() in ("true", "1", "yes")


def _notify_queue_arrival(item_kind: str, item_id: str, hunt_id: str | None) -> None:
    """I-21: reuse the existing notification subsystem exactly as
    `loop.py:232-298` does (fire-and-forget, non-fatal, an env-gated flag)
    for promotion-queue arrivals. No new channel code -- same dispatcher,
    same channel set."""
    if not _bully_notify_enabled():
        return
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
        disp.add_channel(SlackChannel())
        disp.add_channel(TelegramChannel())
        disp.add_channel(EmailChannel())
        disp.add_channel(PushoverChannel())
        disp.add_channel(WebhookChannel())
        disp._schedule(
            disp.dispatch(
                AlertEvent(
                    type=EventType.PROMOTION_QUEUED,
                    message=f"Bully promotion_queue arrival: {item_kind} {item_id}",
                    metadata={"item_kind": item_kind, "item_id": item_id, "hunt_id": hunt_id},
                )
            )
        )
    except Exception:  # pragma: no cover -- notify failure is never fatal
        pass


# gate_id -> the candidate state it produces on a pass, and the state it
# advances FROM (must match contracts._BIN_MAIN_ORDER's adjacency).
_GATE_SEQUENCE: tuple[tuple[str, str], ...] = (
    ("G-1", "G_MINUS_1_PASS"),
    ("G0", "G0_PASS"),
    ("G1a", "G1A_PASS"),
    ("G1b", "G1B_PASS"),
    ("G2", "G2_PASS"),
    ("G5", "COUNCIL_PASS"),  # HEART's clearance, persisted as gate_id='G5'
    ("G3", "G3_PASS"),
)


class GateInfrastructureError(RuntimeError):
    """Raised (and caught) internally to distinguish an infra failure
    (-> BLOCKED, retryable) from a gate that ran and legitimately failed
    (-> terminal DISPROVED with rationale), per MASTER SS8."""


def _record(
    store: Store,
    *,
    hunt_id: str | None,
    actor: str,
    kind: str,
    subject_id: str,
    rationale: str,
    data: dict,
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


# ── G-1: approved scope / mutation class / tool allowlist / budgets ────────


def _default_g_minus_1(candidate_row: dict, gate_input: dict) -> dict:
    """Fail-closed: G-1 passes only if the caller supplied an explicit,
    already-approved scope record (this is the "recorded pre-creation"
    authorization -- promotion.py never invents approval)."""
    scope = gate_input.get("approved_scope")
    if not scope:
        return {
            "outcome": "fail",
            "reasons": ["no approved scope/mutation-class/budget record supplied"],
        }
    if not scope.get("approved", False):
        return {"outcome": "fail", "reasons": [f"scope record present but not approved: {scope}"]}
    return {"outcome": "pass", "reasons": [], "evidence": {"scope": scope}}


# ── G0: observed-origin evidence + complete manifest + healthy telemetry ──


def _default_g0(candidate_row: dict, gate_input: dict, *, store: Store) -> dict:
    manifest_id = candidate_row.get("evidence_manifest_id")
    if not manifest_id:
        return {"outcome": "blocked", "reasons": ["no evidence manifest attached to candidate"]}
    items = store.evidence_items_for_manifest(manifest_id)
    if not items:
        return {"outcome": "blocked", "reasons": [f"evidence manifest {manifest_id} has no items"]}
    refs = [
        evidence_mod.EvidenceItemRef(
            evidence_id=i["evidence_id"],
            type=i["type"],
            uri=i["uri"],
            content_hash=i["content_hash"],
            origin=i.get("origin") or "",
            trust_tier=i.get("trust_tier") or "",
            source_actor=i.get("source_actor") or "",
            synthetic=bool(i.get("synthetic")),
        )
        for i in items
    ]
    telemetry_healthy = bool(gate_input.get("telemetry_healthy", True))
    if not telemetry_healthy:
        return {"outcome": "blocked", "reasons": ["telemetry unhealthy at G0 evaluation time"]}
    if not evidence_mod.synthetic_never_passes_g0(refs):
        return {
            "outcome": "fail",
            "reasons": ["no gradeable-origin evidence item (synthetic-only or empty)"],
        }
    return {"outcome": "pass", "reasons": [], "evidence": {"manifest_id": manifest_id}}


# ── G1a: static SPL execution reproduction ─────────────────────────────────


def replay_and_build_g1a_input(
    capture_path: str, *, draft_spl: str, has_spl_hit: bool, within_window: bool, target_match: bool
) -> dict:
    """Real G1a evidence gathering: confirms the capture actually replays
    (indexed-confirmed) before handing the caller's SPL-execution booleans
    on to `_default_g1a_static` -- the *production* wiring path
    (orchestrator calls this to build `gate_inputs["G1a"]` before invoking
    `promotion.process`). Kept separate from `_default_g1a_static` itself
    so the gate's pass/fail *decision* logic stays a pure function over
    already-gathered evidence (unit-testable with `tmp_path`, no network),
    exactly like every other gate in this module -- only this adapter
    touches the capture store.
    """
    from ..siem.capture_store import replay_capture

    try:
        replay = replay_capture(capture_path)
    except Exception as exc:  # infra failure, not a gate failure
        raise GateInfrastructureError(f"capture replay failed: {exc}") from exc
    if not replay.get("ok", False):
        raise GateInfrastructureError(f"capture replay not ok: {replay.get('error')}")
    return {
        "draft_spl": draft_spl,
        "has_spl_hit": has_spl_hit,
        "within_window": within_window,
        "target_match": target_match,
        "replay": replay,
    }


def check_g1a_static(gate_input: dict) -> dict:
    """Public wrapper over the G1a decision logic for callers outside the
    bin state machine (`growth_loop.prove_draft`'s fresh-positive leg) that
    want the same real reproduction check without going through
    `promotion.process`'s candidate-row plumbing."""
    return _default_g1a_static({}, gate_input)


def check_g1b_dynamic(gate_input: dict) -> dict:
    """Public wrapper over the G1b decision logic, same rationale as
    `check_g1a_static`."""
    return _default_g1b_dynamic({}, gate_input)


def _default_g1a_static(candidate_row: dict, gate_input: dict) -> dict:
    """Check the candidate's draft SPL fires within window on the right
    target against already-gathered replay evidence -- mirrors
    `episode.derive_detection_status` semantics (I-7 "G1a static"). Consumes
    evidence gathered by `replay_and_build_g1a_input`; does not itself
    touch the capture store (see that function's docstring)."""
    from ..episode import derive_detection_status

    if "has_spl_hit" not in gate_input:
        return {
            "outcome": "blocked",
            "reasons": ["no G1a replay evidence supplied -- gate infrastructure incomplete"],
        }
    status = derive_detection_status(
        has_spl_hit=bool(gate_input.get("has_spl_hit", False)),
        used_synthetic=False,
        within_window=bool(gate_input.get("within_window", False)),
        target_match=bool(gate_input.get("target_match", False)),
        has_detection_rule=True,
    )
    if status == "DETECTION_CONFIRMED":
        return {"outcome": "pass", "reasons": [], "evidence": {"detection_status": status}}
    return {
        "outcome": "fail",
        "reasons": [f"detection_status={status}"],
        "evidence": {"detection_status": status},
    }


# ── G1b: dynamic re-execution reproduction ─────────────────────────────────


def _default_g1b_dynamic(candidate_row: dict, gate_input: dict) -> dict:
    """Re-execution reproduces the behavior chain via `capture_recipes`
    where a recipe exists, else a directed Red re-run within MUT budget;
    2-of-3 policy for nondeterministic targets (I-7 "G1b dynamic")."""
    from ..capture_recipes import CAPTURE_RECIPES

    recipe_name = gate_input.get("recipe_name")
    runs = gate_input.get("reexecution_runs")  # list[bool], pre-collected pass/fail per attempt
    if runs is None:
        return {
            "outcome": "blocked",
            "reasons": ["no re-execution runs supplied -- gate infrastructure incomplete"],
        }
    if recipe_name is not None and recipe_name not in CAPTURE_RECIPES:
        return {"outcome": "blocked", "reasons": [f"unknown capture recipe: {recipe_name!r}"]}
    if len(runs) < 3:
        return {"outcome": "blocked", "reasons": [f"2-of-3 policy needs >=3 runs, got {len(runs)}"]}
    passes = sum(1 for r in runs[:3] if r)
    if passes >= 2:
        return {
            "outcome": "pass",
            "reasons": [],
            "evidence": {"runs": runs[:3], "passes": passes, "recipe": recipe_name},
        }
    return {
        "outcome": "fail",
        "reasons": [f"only {passes}/3 dynamic re-execution runs reproduced the behavior"],
        "evidence": {"runs": runs[:3], "passes": passes},
    }


# ── G2: matched controls + benign zero-fire + verdict-contract evidence ────


def _default_g2(candidate_row: dict, gate_input: dict, *, cousin_assessment: dict | None) -> dict:
    """Benign-corpus zero-fire + verdict-contract counter-evidence (I-7
    "G2"). The verdict-contract leg is a structural check that the
    cousin-engine's own discriminator-contradiction evaluation
    (`vetoes`, produced by cousin_engine -- never re-derived here, since
    that would require a model call this module is not allowed to make)
    ran and did not surface an unresolved contradiction."""
    benign_fires = gate_input.get("benign_corpus_fires")
    if benign_fires is None:
        return {
            "outcome": "blocked",
            "reasons": ["no benign_corpus_bench result supplied -- gate infrastructure incomplete"],
        }
    if benign_fires:
        return {
            "outcome": "fail",
            "reasons": ["candidate discriminators fired on a benign-corpus fixture"],
        }
    vetoes = (cousin_assessment or {}).get("vetoes") or []
    unresolved_contradictions = [
        v for v in vetoes if v.get("contradicted") and not v.get("resolved")
    ]
    if unresolved_contradictions:
        return {
            "outcome": "fail",
            "reasons": [
                "unresolved discriminator contradiction (verdict-contract counter-evidence)"
            ],
            "evidence": {"vetoes": vetoes},
        }
    return {
        "outcome": "pass",
        "reasons": [],
        "evidence": {"benign_fires": False, "vetoes": vetoes},
    }


# ── process() ────────────────────────────────────────────────────────────

GateFn = Callable[..., dict]


def _dispatch_gate(
    store: Store,
    gate_id: str,
    cur: dict,
    gate_inputs: dict[str, dict],
    *,
    cousin_assessment: dict | None,
    council_review: Callable[[dict, dict], Any] | None,
    soc_deliver: Callable[[dict], Any] | None,
) -> dict:
    """One gate's real check, dispatched by id. Split out of `process` to
    keep it under the repo's complexity budget; the dispatch itself is pure
    routing, no decision logic lives here."""
    if gate_id == "G-1":
        return _default_g_minus_1(cur, gate_inputs.get("G-1", {}))
    if gate_id == "G0":
        return _default_g0(cur, gate_inputs.get("G0", {}), store=store)
    if gate_id == "G1a":
        return _default_g1a_static(cur, gate_inputs.get("G1a", {}))
    if gate_id == "G1b":
        return _default_g1b_dynamic(cur, gate_inputs.get("G1b", {}))
    if gate_id == "G2":
        return _default_g2(cur, gate_inputs.get("G2", {}), cousin_assessment=cousin_assessment)
    if gate_id == "G5":
        return _run_heart(cur, council_review=council_review)
    if gate_id == "G3":
        return _run_g3(cur, soc_deliver=soc_deliver)
    raise AssertionError(gate_id)  # pragma: no cover -- exhaustive _GATE_SEQUENCE


def _handle_blocked(
    store: Store, candidate_id: str, cur: dict, gate_id: str, result: dict, actor: str
) -> BinOutcome:
    store.candidate_advance(
        candidate_id,
        "BLOCKED",
        expected_version=cur["version"],
        terminal_reason=gate_id,
        rationale="; ".join(result.get("reasons", [])),
    )
    _record(
        store,
        hunt_id=cur["hunt_id"],
        actor=actor,
        kind="gate",
        subject_id=candidate_id,
        rationale=f"{gate_id} infrastructure failure -- retryable BLOCKED, not DISPROVED",
        data={"gate_id": gate_id, "reasons": result.get("reasons", [])},
    )
    return BinOutcome(candidate_id=candidate_id, state="BLOCKED", gate_results={})


def _handle_escalate(
    store: Store, candidate_id: str, cur: dict, gate_id: str, result: dict, actor: str
) -> BinOutcome:
    store.candidate_advance(
        candidate_id,
        "OPERATOR_ESCALATED",
        expected_version=cur["version"],
        terminal_reason=gate_id,
        rationale="; ".join(result.get("reasons", [])),
    )
    queue_id = f"pq-{uuid.uuid4().hex[:12]}"
    store.promotion_enqueue(
        queue_id=queue_id,
        item_kind="review_escalation",
        item_id=candidate_id,
        hunt_id=cur["hunt_id"],
    )
    _notify_queue_arrival("review_escalation", candidate_id, cur["hunt_id"])
    _record(
        store,
        hunt_id=cur["hunt_id"],
        actor=actor,
        kind="council_block",
        subject_id=candidate_id,
        rationale=f"{gate_id} sub-floor participation -- operator escalation, never auto-pass",
        data={"gate_id": gate_id, "reasons": result.get("reasons", [])},
    )
    return BinOutcome(candidate_id=candidate_id, state="OPERATOR_ESCALATED", gate_results={})


def _handle_fail(
    store: Store, candidate_id: str, cur: dict, gate_id: str, result: dict, actor: str
) -> BinOutcome:
    if result.get("escalate"):
        return _handle_escalate(store, candidate_id, cur, gate_id, result, actor)
    store.candidate_kill(
        candidate_id,
        expected_version=cur["version"],
        gate=gate_id,
        rationale="; ".join(result.get("reasons", [])) or f"{gate_id} failed",
    )
    _record(
        store,
        hunt_id=cur["hunt_id"],
        actor=actor,
        kind="kill",
        subject_id=candidate_id,
        rationale=f"{gate_id} ran and failed -- terminal DISPROVED",
        data={"gate_id": gate_id, "reasons": result.get("reasons", [])},
    )
    return BinOutcome(
        candidate_id=candidate_id,
        state="DISPROVED",
        gate_results={},
        council_record_ref=result.get("council_record_ref"),
    )


def process(
    store: Store,
    candidate_id: str,
    *,
    actor: str = "system:promotion",
    gate_inputs: dict[str, dict] | None = None,
    cousin_assessment: dict | None = None,
    council_review: Callable[[dict, dict], Any] | None = None,
    soc_deliver: Callable[[dict], Any] | None = None,
    validator_version: str = GATE_POLICY_VERSION,
) -> BinOutcome:
    """Drive a candidate through G-1 -> G0 -> G1a -> G1b -> G2 -> HEART(G5)
    -> G3 (I-7). Stops (without raising) at the first gate that fails,
    blocks, or -- for HEART -- escalates; the candidate's persisted state
    always reflects exactly how far it got. Re-runnable: a candidate
    already past a gate at its current alert_version is not re-gated
    (idempotent retry, I-7 "gates are re-runnable; duplicate transitions
    ignored")."""
    gate_inputs = gate_inputs or {}
    row = store.candidate_get(candidate_id)
    if row is None:
        raise ValueError(f"no such candidate: {candidate_id}")
    alert_version = row["alert_version"]
    gate_outcomes: dict[str, str] = {}

    if row["current_state"] in ("BLOCKED", "OPERATOR_ESCALATED"):
        # Resume: re-drive from the state just after the last gate that
        # actually passed at this alert_version, never a bare hop out of
        # BLOCKED/OPERATOR_ESCALATED (store.candidate_resume is the
        # dedicated path `is_legal_bin_transition` forces callers through).
        passed_gate_ids = {
            g["gate_id"]
            for g in store.gate_results_for_candidate(candidate_id, alert_version=alert_version)
            if g["outcome"] == "pass"
        }
        resume_target = "CREATED"
        for gate_id, next_state in _GATE_SEQUENCE:
            if gate_id in passed_gate_ids:
                resume_target = next_state
        store.candidate_resume(
            candidate_id, expected_version=row["version"], target_state=resume_target
        )

    for gate_id, next_state in _GATE_SEQUENCE:
        cur = store.candidate_get(candidate_id)
        already_passed = any(
            g["gate_id"] == gate_id and g["outcome"] == "pass"
            for g in store.gate_results_for_candidate(candidate_id, alert_version=alert_version)
        )
        if already_passed:
            gate_outcomes[gate_id] = "pass"
            continue

        try:
            result = _dispatch_gate(
                store,
                gate_id,
                cur,
                gate_inputs,
                cousin_assessment=cousin_assessment,
                council_review=council_review,
                soc_deliver=soc_deliver,
            )
        except GateInfrastructureError as exc:
            result = {"outcome": "blocked", "reasons": [str(exc)]}

        attempt = store.gate_next_attempt(candidate_id, alert_version, gate_id)
        store.gate_result_put(
            result_id=f"gr-{uuid.uuid4().hex[:12]}",
            candidate_id=candidate_id,
            alert_version=alert_version,
            gate_id=gate_id,
            attempt=attempt,
            outcome=result["outcome"],
            validator_version=validator_version,
            inputs=gate_inputs.get(gate_id, {}),
            evidence=result.get("evidence", {}),
            checks=result.get("checks", []),
            reasons=result.get("reasons", []),
        )
        gate_outcomes[gate_id] = result["outcome"]

        if result["outcome"] == "blocked":
            outcome = _handle_blocked(store, candidate_id, cur, gate_id, result, actor)
            return replace_gate_results(outcome, gate_outcomes)
        if result["outcome"] == "fail":
            outcome = _handle_fail(store, candidate_id, cur, gate_id, result, actor)
            return replace_gate_results(outcome, gate_outcomes)

        # pass -- advance one hop.
        store.candidate_advance(candidate_id, next_state, expected_version=cur["version"])

    # All seven gates passed -- queue for operator confirmation (never
    # auto-promote).
    final_row = store.candidate_get(candidate_id)
    store.candidate_advance(
        candidate_id, "AWAITING_OPERATOR", expected_version=final_row["version"]
    )
    queue_id = f"pq-{uuid.uuid4().hex[:12]}"
    store.promotion_enqueue(
        queue_id=queue_id,
        item_kind="cousin_detection",
        item_id=candidate_id,
        hunt_id=final_row["hunt_id"],
    )
    _notify_queue_arrival("cousin_detection", candidate_id, final_row["hunt_id"])
    _record(
        store,
        hunt_id=final_row["hunt_id"],
        actor=actor,
        kind="gate",
        subject_id=candidate_id,
        rationale="full gate chain passed -- queued for operator confirmation",
        data={"gate_results": gate_outcomes, "queue_id": queue_id},
    )
    return BinOutcome(
        candidate_id=candidate_id,
        state="AWAITING_OPERATOR",
        gate_results=gate_outcomes,
        queue_id=queue_id,
    )


def replace_gate_results(outcome: BinOutcome, gate_outcomes: dict[str, str]) -> BinOutcome:
    """`_handle_*` helpers build their `BinOutcome` before the caller's
    accumulated per-gate outcome map is available -- stitch it in here
    rather than threading `gate_outcomes` through every handler's
    signature."""
    from dataclasses import replace

    return replace(outcome, gate_results=dict(gate_outcomes))


def _run_heart(candidate_row: dict, *, council_review) -> dict:
    """HEART's clearance persisted as gate_id='G5'. `council_review` is
    `adversary.review` (injected so promotion.py never imports adversary.py
    at module scope and vice versa isn't required -- kept as a parameter
    per the LabDriver injection precedent, real default supplied by the
    caller (orchestrator/tests), never hardcoded here)."""
    if council_review is None:
        raise GateInfrastructureError("no council_review callable supplied for HEART (G5)")
    record = council_review(candidate_row, {})
    if not record.review_valid:
        return {
            "outcome": "fail",
            "escalate": True,
            "reasons": [f"sub-floor council participation={record.participation}"],
            "evidence": {"packet_id": record.packet_id},
        }
    if record.unresolved:
        return {
            "outcome": "fail",
            "reasons": ["material objection unresolved after rebuttal round"],
            "evidence": {"packet_id": record.packet_id},
            "council_record_ref": record.packet_id,
        }
    return {"outcome": "pass", "reasons": [], "evidence": {"packet_id": record.packet_id}}


def _run_g3(candidate_row: dict, *, soc_deliver) -> dict:
    if soc_deliver is None:
        raise GateInfrastructureError("no soc_deliver callable supplied for G3")
    receipt = soc_deliver(candidate_row)
    if not receipt.sufficient:
        reasons = []
        if not receipt.producer_ack:
            reasons.append("no producer ack")
        if not receipt.consumer_query_ran:
            reasons.append("producer ack without a consumer query is insufficient")
        if not receipt.content_hash_match:
            reasons.append("content-hash mismatch")
        return {
            "outcome": "fail",
            "reasons": reasons,
            "evidence": {"delivery_id": receipt.delivery_id},
        }
    return {"outcome": "pass", "reasons": [], "evidence": {"delivery_id": receipt.delivery_id}}


# ── promote() / kill() ──────────────────────────────────────────────────


def promote(store: Store, candidate_id: str, *, operator_actor: str, note: str = "") -> dict:
    """I-7 `promote(candidate_id, operator_actor, note) -> Promotion`.
    Operator-only; DB-enforced (candidates trigger requires the full gate
    chain, and this function itself refuses a non-operator actor before
    ever reaching the store)."""
    row = store.candidate_get(candidate_id)
    if row is None:
        raise ValueError(f"no such candidate: {candidate_id}")
    store.candidate_promote(
        candidate_id, expected_version=row["version"], operator_actor=operator_actor, note=note
    )
    _record(
        store,
        hunt_id=row["hunt_id"],
        actor=operator_actor,
        kind="promote",
        subject_id=candidate_id,
        rationale=note or "operator promotion",
        data={"candidate_id": candidate_id},
    )
    return {"candidate_id": candidate_id, "state": "PROMOTED", "operator_actor": operator_actor}


def kill(
    store: Store, candidate_id: str, *, gate: str, rationale: str, actor: str = "system:promotion"
) -> None:
    """I-7 `kill(candidate_id, gate, rationale) -> None`."""
    row = store.candidate_get(candidate_id)
    if row is None:
        raise ValueError(f"no such candidate: {candidate_id}")
    store.candidate_kill(
        candidate_id, expected_version=row["version"], gate=gate, rationale=rationale
    )
    _record(
        store,
        hunt_id=row["hunt_id"],
        actor=actor,
        kind="kill",
        subject_id=candidate_id,
        rationale=rationale,
        data={"gate": gate},
    )
