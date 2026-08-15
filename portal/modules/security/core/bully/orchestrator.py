"""bully.orchestrator -- LOOP, the only module that sequences a hunt
iteration (P1.7).

Stage machine (I-3): DRAFT -> AUTHORIZED -> RECALL_READY -> TARGETED ->
MUTATION_READY -> EXECUTING -> ANALYZING -> PROMOTING -> COMPOUNDING ->
CLOSED (+ BLOCKED / CANCELLED / FAILED). P1 wires exactly one iteration
end-to-end; TARGETED/MUTATION_READY are stubbed passthroughs (real TGT/MUT
land P3/P4), and PROMOTING/COMPOUNDING do not yet run BIN/HEART (P2) --
they still perform the universal index-emission step that later phases
extend, never skip.

`[GATE]` hunt authorization is operator-only: `hunt run`/`hunt resume`/
`hunt cancel`/`hunt queue` all require an `actor` starting with
``"operator:"`` -- enforced here in code, not merely documented.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from typing import Any

from . import config as bully_config
from . import evidence as evidence_mod
from . import investigation as investigation_mod
from . import signatures as signatures_mod
from .contracts import DecisionEvent, new_id
from .cousin_engine import CoverageView, candidate_set, grade
from .organ import Organ, OrganUnavailable
from .store import IllegalTransitionError, Store


class HonestBlockedError(RuntimeError):
    """A hunt/iteration is blocked by an infra/gate failure -- never a silent pass.

    MASTER SS8: gate-infrastructure failure is retryable BLOCKED, distinct
    from a gate that ran and failed. Both surface through this exception at
    the CLI boundary; the distinction is carried in the message/rationale.
    """


class OperatorRequiredError(RuntimeError):
    """Raised when a `[GATE]` command is invoked by a non-operator actor.

    Hunt authorization (`hunt run`) and resume-after-block (`hunt resume`)
    are operator-only (MASTER SS7 operator-confirmation index).
    """


LabDriver = Callable[..., Any]  # (target_cell, *, dry_run) -> live Episode


def _require_operator(actor: str) -> None:
    if not actor.startswith("operator:"):
        raise OperatorRequiredError(
            f"actor {actor!r} is not an operator; hunt authorization requires actor='operator:<id>'"
        )


def _default_lab_driver(target_cell: dict, *, dry_run: bool) -> Any:
    """Real driver: unchanged `exec_chain._prepare_scenario` + `_run_chain_test`
    -> `blue.collect_and_ship_scenario_telemetry` -> `episode.Episode`.

    `_run_chain_test`'s own `lab_exec=False` mode is already the existing
    synthetic-fallback path (no live lab connection required) -- this is
    the "synthetic lab" I2 exercises when no test-injected `lab_driver` is
    given. Only reached when a caller doesn't inject its own driver, so
    hermetic unit tests never hit this function at all.
    """
    from .. import episode as episode_mod
    from ..blue import collect_and_ship_scenario_telemetry
    from ..chain import SCENARIOS, BenchConfig
    from ..exec_chain import _prepare_scenario, _run_chain_test

    scenario_name = target_cell.get("scenario") or next(iter(SCENARIOS))
    scenario = SCENARIOS[scenario_name]
    cfg = BenchConfig()
    gate = _prepare_scenario(scenario, cfg, dry_run=dry_run, lab_exec=False)
    if not gate.get("ready", False):
        raise HonestBlockedError(f"scenario {scenario_name!r} not ready: {gate.get('reason')}")

    model = target_cell.get("model") or bully_config.resolve_role_model("tool")
    scenario_start = time.time()
    chain_result = _run_chain_test(model, cfg, dry_run=dry_run, lab_exec=False)

    episode_id = episode_mod.new_episode_id(scenario_name)
    _telemetry_path, _hit, red_status = collect_and_ship_scenario_telemetry(
        scenario, scenario_start, lab_exec=False, dry_run=dry_run, episode_id=episode_id
    )
    return episode_mod.Episode(
        episode_id=episode_id,
        scenario=scenario_name,
        target_host=gate.get("host"),
        started_at=scenario_start,
        red_status=red_status or "RED_NOT_RUN",
        used_synthetic=chain_result.get("mode") == "synthetic",
    )


def _record(
    store: Store,
    *,
    hunt_id: str,
    iteration_id: str | None,
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
            iteration_id=iteration_id,
            actor=actor,
            kind=kind,
            subject_id=subject_id,
            rationale=rationale,
            data=data,
        )
    )


def _do_recall(store: Store, organ: Organ, *, hunt_id: str, neighborhood: str, context) -> None:
    """RECALL_READY -- mandatory pre-hunt recall (I-4/C3). No code path
    reaches TARGETED without a persisted RecallReceipt: if organ.recall
    raises, the iteration is honestly BLOCKED right here, before any
    target selection or lab action."""
    try:
        organ.recall(hunt_id=hunt_id, query=f"{neighborhood} {context.neighborhood_scope}")
    except OrganUnavailable as exc:
        store.hunt_advance_stage(
            hunt_id, "BLOCKED", expected_version=store.hunt_get(hunt_id)["version"]
        )
        _record(
            store,
            hunt_id=hunt_id,
            iteration_id=None,
            actor="system:orchestrator",
            kind="recall",
            subject_id=hunt_id,
            rationale=f"recall unsatisfiable: {exc}",
            data={"error": str(exc)},
        )
        raise HonestBlockedError(
            f"hunt {hunt_id} blocked: organ recall unavailable ({exc})"
        ) from exc
    if not store.recall_receipt_exists(hunt_id):  # pragma: no cover -- structural guard
        raise HonestBlockedError(f"hunt {hunt_id}: no recall receipt persisted, refusing to target")


def _do_analyze(
    store: Store,
    organ: Organ,
    *,
    hunt_id: str,
    iteration_id: str,
    episode_view: dict,
    episode: Any,
    investigation_arm: Callable,
    dry_run: bool,
):
    """ANALYZING -- investigation arm -> signature -> cousin grade."""
    models = bully_config.resolve_investigation_models()
    inv_result = investigation_arm(episode, models=models, dry_run=dry_run)

    signature = signatures_mod.build_signature(episode_view, {"attack_mappings": []})
    semantic_candidates = organ.knn(signature.canonical_fingerprint, k=8)
    candidates = candidate_set(signature, semantic_candidates=semantic_candidates)
    coverage = CoverageView(telemetry_healthy=True)
    assessment = grade(signature, candidates, coverage)

    store.record_signature(signature)
    store.record_cousin(assessment)
    _record(
        store,
        hunt_id=hunt_id,
        iteration_id=iteration_id,
        actor="system:orchestrator",
        kind="grade",
        subject_id=assessment.assessment_id,
        rationale=f"BR-COUSIN graded relationship={assessment.relationship} response={assessment.defense_response}",
        data={
            "investigation_verdict": inv_result.verdict,
            "assessment_id": assessment.assessment_id,
        },
    )
    return inv_result, assessment


def run_hunt_iteration(
    store: Store,
    organ: Organ,
    *,
    hunt_id: str,
    actor: str,
    neighborhood: str,
    target_cell: dict | None = None,
    lab_driver: LabDriver | None = None,
    investigation_arm: Callable[..., Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Drive exactly one hunt iteration through the full P1 stage machine.

    LOAD -> RECALL -> SELECT(stub) -> DIRECT(stub) -> INVESTIGATE -> GRADE
    -> RECORD -> STOP (I2). Every stage transition is a real, checked SUB
    write; there is no code path that reaches TARGETED without a
    persisted RecallReceipt, and no code path that closes the iteration
    with a required unindexed emission still pending.
    """
    lab_driver = lab_driver or _default_lab_driver
    investigation_arm = investigation_arm or investigation_mod.run_arm
    target_cell = target_cell or {}

    def _stage(target: str) -> None:
        row = store.hunt_get(hunt_id)
        store.hunt_advance_stage(hunt_id, target, expected_version=row["version"])

    _stage("AUTHORIZED")
    _record(
        store,
        hunt_id=hunt_id,
        iteration_id=None,
        actor=actor,
        kind="config",
        subject_id=hunt_id,
        rationale="hunt authorized by operator",
        data={"neighborhood": neighborhood},
    )

    context = store.load_context(hunt_id)
    _do_recall(store, organ, hunt_id=hunt_id, neighborhood=neighborhood, context=context)
    _stage("RECALL_READY")

    # TARGETED / MUTATION_READY -- stubbed passthrough in P1 (real TGT/MUT
    # land P3/P4). Recorded as a decision event so the stub is auditable,
    # not silently skipped.
    _stage("TARGETED")
    _record(
        store,
        hunt_id=hunt_id,
        iteration_id=None,
        actor="system:orchestrator",
        kind="target_select",
        subject_id=target_cell.get("scenario", "auto"),
        rationale="P1 stub passthrough -- real TGT lands P4",
        data={"target_cell": target_cell},
    )
    _stage("MUTATION_READY")

    iteration_id = f"{hunt_id}-i1"

    # EXECUTING -- unchanged Red/Blue lab machinery via the injected driver.
    _stage("EXECUTING")
    try:
        episode = lab_driver(target_cell, dry_run=dry_run)
    except HonestBlockedError:
        store.hunt_advance_stage(
            hunt_id, "BLOCKED", expected_version=store.hunt_get(hunt_id)["version"]
        )
        raise

    episode_view = evidence_mod.adapt_episode(episode)
    if evidence_mod.episode_verdict_is_blocked(episode):
        store.hunt_advance_stage(
            hunt_id, "BLOCKED", expected_version=store.hunt_get(hunt_id)["version"]
        )
        _record(
            store,
            hunt_id=hunt_id,
            iteration_id=iteration_id,
            actor="system:orchestrator",
            kind="gate",
            subject_id=episode_view["episode_id"],
            rationale="episode verdict INDETERMINATE -- treated as blocked, never miss/pass",
            data=episode_view,
        )
        raise HonestBlockedError(
            f"hunt {hunt_id}: episode {episode_view['episode_id']} INDETERMINATE"
        )

    # ANALYZING -- investigation arm -> signature -> cousin grade.
    _stage("ANALYZING")
    inv_result, assessment = _do_analyze(
        store,
        organ,
        hunt_id=hunt_id,
        iteration_id=iteration_id,
        episode_view=episode_view,
        episode=episode,
        investigation_arm=investigation_arm,
        dry_run=dry_run,
    )

    # PROMOTING / COMPOUNDING -- BIN/HEART land P2; universal index emission
    # (I-4) happens regardless, in this same iteration, never deferred to a
    # background worker that could silently never run in P1.
    _stage("PROMOTING")
    _stage("COMPOUNDING")
    org_record = {
        "kind": "cousin",
        "hunt_id": hunt_id,
        "episode_id": episode_view["episode_id"],
        "relationship": assessment.relationship,
        "detection_response": assessment.defense_response,
        "rationale": assessment.explanation.get("product_band", ""),
        "trust_tier": "SUSPECT",
        "provenance_class": "hunt_emission",
    }
    organ.index_emissions([org_record])
    outbox_result = organ.process_outbox()

    dead_letters = store.outbox_required_dead_letters()
    if dead_letters:
        # A required dead letter blocks hunt closure (DATA_MODEL SS1.10) --
        # this is a failed iteration, never a silently-closed one.
        store.hunt_advance_stage(
            hunt_id, "BLOCKED", expected_version=store.hunt_get(hunt_id)["version"]
        )
        raise HonestBlockedError(
            f"hunt {hunt_id}: {len(dead_letters)} required outbox dead letter(s) block closure"
        )

    _stage("CLOSED")
    store.lease_release(hunt_id, owner=actor)

    return {
        "hunt_id": hunt_id,
        "iteration_id": iteration_id,
        "episode_id": episode_view["episode_id"],
        "assessment_id": assessment.assessment_id,
        "relationship": assessment.relationship,
        "defense_response": assessment.defense_response,
        "investigation_verdict": inv_result.verdict,
        "outbox": outbox_result,
        "stage": "CLOSED",
    }


def run_hunt(
    *,
    neighborhood: str = "auto",
    budget_class: str = "default",
    dry_run: bool = False,
    actor: str,
    store: Store | None = None,
    organ: Organ | None = None,
    lab_driver: LabDriver | None = None,
    investigation_arm: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """`hunt run` -- authorize + drive a new hunt through the LOOP stage
    machine. [GATE] operator-only."""
    _require_operator(actor)

    owns_store = store is None
    if store is None:
        store = Store(bully_config.hunt_dir() / "hunt_state.db")
    if organ is None:
        organ = Organ(store=store, db_path=bully_config.hunt_dir() / "hunt_memory")

    snapshot = bully_config.HuntConfigSnapshot.capture()
    hunt_id = new_id("hunt")
    try:
        store.hunt_create(
            hunt_id=hunt_id,
            objective=f"hunt {neighborhood}",
            neighborhood_scope=neighborhood,
            authorization_ref=actor,
            config_version=snapshot.version,
            role_snapshot=bully_config.resolve_investigation_models(),
            budgets=snapshot.hunt.get("budgets", {}),
        )
        store.lease_acquire(hunt_id, owner=actor)
        _record(
            store,
            hunt_id=hunt_id,
            iteration_id=None,
            actor=actor,
            kind="config",
            subject_id=hunt_id,
            rationale="HUNT_CREATED",
            data={"neighborhood": neighborhood, "budget_class": budget_class, "dry_run": dry_run},
        )
        result = run_hunt_iteration(
            store,
            organ,
            hunt_id=hunt_id,
            actor=actor,
            neighborhood=neighborhood,
            lab_driver=lab_driver,
            investigation_arm=investigation_arm,
            dry_run=dry_run,
        )
        return {
            "hunt_id": hunt_id,
            "iterations": 1,
            "candidates_graded": 1,
            "promotions": 0,
            "stop_reason": "single-iteration P1 proof",
            "cost_summary": {},
            **result,
        }
    finally:
        if owns_store:
            organ.close()
            store.close()


def resume_hunt(hunt_id: str, *, actor: str) -> dict[str, Any]:
    """`hunt resume` -- resume a blocked/interrupted hunt. [GATE] operator-only."""
    _require_operator(actor)
    raise NotImplementedError(
        "orchestrator.resume_hunt: multi-iteration resume lands with TGT/PLT (P3/P4)"
    )


def hunt_status(hunt_id: str, *, store: Store | None = None) -> dict[str, Any]:
    """`hunt status` -- read-only report; no operator gate."""
    owns_store = store is None
    store = store or Store(bully_config.hunt_dir() / "hunt_state.db")
    try:
        row = store.hunt_get(hunt_id)
        if row is None:
            raise HonestBlockedError(f"no such hunt: {hunt_id}")
        return {"hunt_id": hunt_id, "stage": row["stage"], "status": row["status"]}
    finally:
        if owns_store:
            store.close()


def cancel_hunt(
    hunt_id: str, *, actor: str, reason: str = "", store: Store | None = None
) -> dict[str, Any]:
    """`hunt cancel` -- revokes leases, never deletes evidence. [GATE] operator-only."""
    _require_operator(actor)
    owns_store = store is None
    store = store or Store(bully_config.hunt_dir() / "hunt_state.db")
    try:
        row = store.hunt_get(hunt_id)
        if row is None:
            raise HonestBlockedError(f"no such hunt: {hunt_id}")
        with contextlib.suppress(IllegalTransitionError):
            # already terminal -- cancellation is idempotent, never re-raises
            store.hunt_advance_stage(hunt_id, "CANCELLED", expected_version=row["version"])
        store.lease_release(hunt_id, owner=actor)
        _record(
            store,
            hunt_id=hunt_id,
            iteration_id=None,
            actor=actor,
            kind="config",
            subject_id=hunt_id,
            rationale=reason or "operator cancellation",
            data={"reason": reason},
        )
        return {"hunt_id": hunt_id, "stage": "CANCELLED"}
    finally:
        if owns_store:
            store.close()


def hunt_doctor(*, store: Store | None = None) -> dict[str, Any]:
    """`hunt doctor` -- SUB integrity check (P1.2)."""
    owns_store = store is None
    store = store or Store(bully_config.hunt_dir() / "hunt_state.db")
    try:
        return store.doctor()
    finally:
        if owns_store:
            store.close()


def queue_resolve(
    *,
    item_id: str | None,
    actor: str,
    rationale: str = "",
    action: str = "confirm",
    store: Store | None = None,
) -> dict[str, Any]:
    """`hunt queue` (list) / `hunt queue --confirm <id>` / `hunt queue
    --reject <id> --rationale ...` -- promotion-queue resolution. [GATE]
    operator-only (P2.5): `_require_operator` refuses a non-operator actor
    before this function ever touches the store, and `store.promotion_resolve`
    /`store.candidate_promote` each independently DB-enforce the same
    requirement -- there is no code path here that promotes/rejects
    without an operator actor (MASTER SS7).
    """
    _require_operator(actor)
    from . import promotion as promotion_mod

    owns_store = store is None
    store = store or Store(bully_config.hunt_dir() / "hunt_state.db")
    try:
        if item_id is None:
            return {"pending": store.promotion_list(state="pending")}

        if action not in ("confirm", "reject"):
            raise ValueError(f"unknown queue action: {action!r}")
        target_state = "confirmed" if action == "confirm" else "rejected"
        if target_state == "rejected" and not rationale.strip():
            raise HonestBlockedError("hunt queue --reject requires a rationale")

        row = store.promotion_get(item_id)
        if row is None:
            raise HonestBlockedError(f"no such promotion_queue item: {item_id}")

        if row["item_kind"] == "cousin_detection":
            if target_state == "confirmed":
                promotion_mod.promote(store, row["item_id"], operator_actor=actor, note=rationale)
            else:
                promotion_mod.kill(
                    store,
                    row["item_id"],
                    gate="operator_reject",
                    rationale=rationale,
                    actor=actor,
                )

        store.promotion_resolve(item_id, actor=actor, state=target_state, rationale=rationale)

        with contextlib.suppress(Exception):
            # Provenance (I-21/existing): append_entry is best-effort and
            # never blocks the resolution itself on a ledger write failure.
            from portal.platform.wiki.provenance_ledger import append_entry

            append_entry(
                episode_id=row["item_id"],
                scenario=row.get("hunt_id") or "",
                capability_verdict=target_state.upper(),
                event="bully_promotion",
            )

        return {"queue_id": item_id, "state": target_state, "item_kind": row["item_kind"]}
    finally:
        if owns_store:
            store.close()
