"""bully.orchestrator -- LOOP, the only module that sequences a hunt
iteration (P1.7, P3 MUT/drift wiring, P4 TGT/COST wiring).

Stage machine (I-3): DRAFT -> AUTHORIZED -> RECALL_READY -> TARGETED ->
MUTATION_READY -> EXECUTING -> ANALYZING -> PROMOTING -> COMPOUNDING ->
CLOSED (+ BLOCKED / CANCELLED / FAILED). TARGETED now runs real TGT
selection via `targeting.py` (P4.3, replacing the P1 stub); MUTATION_READY
compiles a real `MutationPlan` via `mutation.py` (P3.1, replacing an
earlier P1 stub); ANALYZING now also runs BR-DRIFT (P3.2) after the cousin
grade, followed by COST metering (P4.1) via `costing.py`. PROMOTING/
COMPOUNDING do not yet run BIN/HEART here (P2's promotion pipeline is
driven separately via `hunt queue --confirm/--reject`) -- they still
perform the universal index-emission step that later phases extend, never
skip.

`[GATE]` hunt authorization is operator-only: `hunt run`/`hunt resume`/
`hunt cancel`/`hunt queue` all require an `actor` starting with
``"operator:"`` -- enforced here in code, not merely documented.
"""

from __future__ import annotations

import contextlib
import dataclasses
import time
from collections.abc import Callable
from typing import Any

from . import config as bully_config
from . import costing, cutover, drift_engine
from . import evidence as evidence_mod
from . import investigation as investigation_mod
from . import mutation as mutation_mod
from . import plateau as plateau_mod
from . import playbooks as playbooks_mod
from . import scoreboard as scoreboard_mod
from . import signatures as signatures_mod
from . import targeting as targeting_mod
from .contracts import DecisionEvent, DecisionImpact, MutationPlan, new_id
from .cousin_engine import CoverageView, grade, retrieve_candidate_axes
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


def _resolve_live_investigation_models(store: Store) -> dict[str, str]:
    """Resolve config models, then apply only operator-served TRAIN aliases."""
    models = bully_config.resolve_investigation_models()
    mode = cutover.feed_mode(bully_config.load_hunt_config(), "fleet_local_fine_tune")
    for refinement_role, investigation_role in bully_config.REFINEMENT_ROLE_MAP.items():
        alias = store.model_alias_get(refinement_role)
        if alias is not None and mode == "authoritative":
            models[investigation_role] = alias["model_tag"]
    return models


def _require_operator(actor: str) -> None:
    if not actor.startswith("operator:"):
        raise OperatorRequiredError(
            f"actor {actor!r} is not an operator; hunt authorization requires actor='operator:<id>'"
        )


def _default_lab_driver(target_cell: dict, *, dry_run: bool) -> Any:
    """Real driver: unchanged `exec_chain._prepare_scenario` + `_run_chain_test`
    -> `blue.collect_and_ship_scenario_telemetry` -> `episode.Episode`.

    ``dry_run=True`` selects the existing synthetic fallback; a real run
    passes ``lab_exec=True`` through the unchanged Red/Blue machinery.
    Only reached when a caller does not inject its own driver.
    """
    from .. import episode as episode_mod
    from .._config import BenchConfig
    from ..blue import _run_blue_chain_test, collect_and_ship_scenario_telemetry
    from ..chain import CHAIN_TOOLS_BASE, SCENARIOS
    from ..episode import derive_detection_status
    from ..exec_chain import _prepare_scenario, _run_chain_test

    scenario_name = target_cell.get("scenario") or next(iter(SCENARIOS))
    scenario = SCENARIOS[scenario_name]
    overlay = target_cell.get("mutation_overlay")
    if overlay:
        # MUT-compiled overlay (P3.1, I-1) -- data only. The overlay's
        # red_order/red_prompt/mission_objective are handed to the same
        # unchanged _prepare_scenario/set_scenario path a raw SCENARIOS
        # entry uses; this is a dict key override, never a Red source edit.
        scenario = {
            **scenario,
            "red_order": list(overlay["red_order"]),
            "red_prompt": overlay["red_prompt"],
            "mission_objective": overlay.get("mission_objective"),
        }
    cfg = BenchConfig(chain_tools=list(CHAIN_TOOLS_BASE))
    lab_exec = not dry_run
    gate = _prepare_scenario(scenario, cfg, dry_run=dry_run, lab_exec=lab_exec)
    if not gate.get("ready", False):
        raise HonestBlockedError(f"scenario {scenario_name!r} not ready: {gate.get('reason')}")

    model = target_cell.get("model") or bully_config.resolve_role_model("tool")
    scenario_start = time.time()
    chain_result = _run_chain_test(model, cfg, dry_run=dry_run, lab_exec=lab_exec)

    episode_id = episode_mod.new_episode_id(scenario_name)
    telemetry_path, indexed, telemetry_error = collect_and_ship_scenario_telemetry(
        scenario, scenario_start, lab_exec=lab_exec, dry_run=dry_run, episode_id=episode_id
    )
    blue_result = _run_blue_chain_test(
        model,
        scenario,
        dry_run=dry_run,
        lab_exec=lab_exec,
        scenario_start=scenario_start,
        query_live=lab_exec,
        mode="discovery",
        episode_id=episode_id,
    )
    observed = bool(
        blue_result.get("episode_inventory_origins")
        or any(blue_result.get("telemetry_origins", {}).values())
    )
    used_synthetic = bool(blue_result.get("synthetic_fallback")) or not lab_exec
    episode_match = blue_result.get("episode_id") == episode_id
    red_landed = bool(chain_result.get("lab_success"))
    has_spl_hit = bool(blue_result.get("reported")) and red_landed and observed and episode_match
    detection_status = derive_detection_status(
        has_spl_hit=has_spl_hit,
        used_synthetic=used_synthetic,
        within_window=episode_match,
        target_match=episode_match,
        has_detection_rule=bool(scenario.get("detect_ground_truth")),
    )
    if observed:
        telemetry_status = "TELEMETRY_OBSERVED"
    elif indexed is False or telemetry_error == "TELEMETRY_NOT_INDEXED":
        telemetry_status = "TELEMETRY_NOT_INDEXED"
    elif lab_exec:
        telemetry_status = "TELEMETRY_COLLECTION_FAILED"
    else:
        telemetry_status = "TELEMETRY_NOT_CONFIGURED"
    return episode_mod.Episode(
        episode_id=episode_id,
        scenario=scenario_name,
        target_host=gate.get("host"),
        started_at=scenario_start,
        red_status="RED_LANDED" if red_landed else "RED_EXECUTION_FAILED",
        telemetry_status=telemetry_status,
        detection_status=detection_status,
        used_synthetic=used_synthetic,
        evidence_refs=[telemetry_path] if telemetry_path else [],
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


def _do_recall(store: Store, organ: Organ, *, hunt_id: str, neighborhood: str, context) -> Any:
    """RECALL_READY -- mandatory pre-hunt recall (I-4/C3). No code path
    reaches TARGETED without a persisted RecallReceipt: if organ.recall
    raises, the iteration is honestly BLOCKED right here, before any
    target selection or lab action. Returns the `RecallReceipt` so TGT
    (P4.3) can be recall-influenced without re-fetching it."""
    try:
        receipt = organ.recall(
            hunt_id=hunt_id, query=f"{neighborhood} {context.neighborhood_scope}"
        )
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
    return receipt


def _do_target(
    store: Store,
    *,
    hunt_id: str,
    context: Any,
    recall_receipt: Any,
    target_cell: dict,
) -> dict:
    """TARGETED (P4.3, replacing the P1 stub) -- real TGT selection over
    coverage cells + known-state (SUB), the just-persisted RecallReceipt
    (ORG), and this hunt's own cost ledger (I-13). Fail-closed: an honest
    "no eligible target"/"unrankable" `TargetDecision` blocks the hunt here
    (recorded), never silently falls through to an unranked scenario.

    Default cells are seeded content-idempotently into SUB and read back on
    demand; this replaces the legacy capability-graph cold rebuild. A
    caller/test may inject `target_cell["candidate_cells"]` to override the
    persisted default readout directly.

    A hunt's very first iteration has no *measured* cost yet (COST only
    meters after EXECUTING) -- an honest "estimated" pre-flight cost
    observation is seeded once per hunt (never "measured", never
    zero-filled) so TGT always has *some* real cost data to rank the
    default scenario cells against; a cell whose own `cost_ref` points
    elsewhere (never pre-flighted) still declines `MISSING_COST` exactly
    as I-11 requires.
    """
    from ..chain import SCENARIOS

    if not store.cost_ledger_for_hunt(hunt_id):
        preflight = costing.build_record(
            hunt_id,
            None,
            [
                costing.observation(
                    "lab_minutes", f"{hunt_id}:preflight_estimate", 5.0, quality="estimated"
                )
            ],
        )
        store.cost_ledger_put(preflight)

    cells = target_cell.get("candidate_cells")
    if cells is None:
        for name in SCENARIOS:
            store.coverage_cell_put(
                {
                    "cell_id": f"cell:{name}",
                    "subject": f"cell:{name}",
                    "scenario": name,
                    "prior": 0.5,
                }
            )
        cells = [
            {**cell, "cost_ref": cell.get("cost_ref") or hunt_id} for cell in store.coverage_cells()
        ]

    ranking_context = dataclasses.replace(context, open_cells=cells)
    baseline_context = dataclasses.replace(ranking_context, known_state_view=[])
    baseline_recall = dataclasses.replace(recall_receipt, selected_context=[])

    class _UniformLegacyCostView:
        @staticmethod
        def units_for(_reference: str) -> tuple[float, None]:
            return 1.0, None

    baseline_ledger = _UniformLegacyCostView()
    replacement_ledger = costing.CostView(store.cost_ledger())
    cfg = bully_config.load_hunt_config()
    recall_mode = cutover.feed_mode(cfg, "semantic_hunt_memory")
    known_mode = cutover.feed_mode(cfg, "known_state")
    roi_mode = cutover.feed_mode(cfg, "roi_target_intelligence")
    effective_recall = recall_receipt if recall_mode == "authoritative" else baseline_recall
    effective_context = ranking_context if known_mode == "authoritative" else baseline_context
    effective_ledger = replacement_ledger if roi_mode == "authoritative" else baseline_ledger
    decision = targeting_mod.select(effective_context, effective_recall, effective_ledger)

    # Paired, isolated feed comparisons produce durable causal links. Each
    # replacement is compared with all other feeds held at the baseline.
    baseline_decision = targeting_mod.select(baseline_context, baseline_recall, baseline_ledger)
    feed_decisions = {
        "semantic_hunt_memory": targeting_mod.select(
            baseline_context, recall_receipt, baseline_ledger
        ),
        "known_state": targeting_mod.select(ranking_context, baseline_recall, baseline_ledger),
        "roi_target_intelligence": targeting_mod.select(
            baseline_context, baseline_recall, replacement_ledger
        ),
    }

    def _projection(value) -> dict[str, Any]:
        return {
            "status": value.status,
            "selected_cell_id": value.selected_cell_id,
            "ordered_cell_ids": [row["cell_id"] for row in value.ordered_targets],
        }

    before_projection = _projection(baseline_decision)
    semantic_ids = [
        str((item.get("record") or {}).get("record_id"))
        for item in recall_receipt.selected_context
        if (item.get("record") or {}).get("record_id")
    ]
    known_ids = [
        str(item.get("entry_id"))
        for item in ranking_context.known_state_view
        if item.get("entry_id")
    ]
    cost_ids = [str(record["record_id"]) for record in store.cost_ledger()]
    citations = {
        "semantic_hunt_memory": semantic_ids,
        "known_state": known_ids,
        "roi_target_intelligence": cost_ids,
    }
    for feed, feed_decision in feed_decisions.items():
        after_projection = _projection(feed_decision)
        if before_projection == after_projection:
            change_kind = "NO_EFFECT"
        elif feed_decision.selected_cell_id is None:
            change_kind = "AVOIDED"
        elif feed_decision.selected_cell_id != baseline_decision.selected_cell_id:
            change_kind = "SELECTED"
        else:
            change_kind = "DEPRIORITIZED"
        store.decision_impact_put(
            DecisionImpact(
                impact_id=new_id("impact"),
                recall_id=recall_receipt.recall_id,
                consuming_decision_ref=decision.decision_id,
                before=before_projection,
                after=after_projection,
                cited_record_ids=citations[feed],
                change_kind=change_kind,
                explanation=(
                    f"P7 paired cutover proof for {feed}; mode={cutover.feed_mode(cfg, feed)}"
                ),
            )
        )

    _record(
        store,
        hunt_id=hunt_id,
        iteration_id=None,
        actor="system:orchestrator",
        kind="target_select",
        subject_id=decision.decision_id,
        rationale=f"TGT status={decision.status} selected={decision.selected_cell_id!r}",
        data=decision.to_dict(),
    )

    if decision.status != "selected":
        store.hunt_advance_stage(
            hunt_id, "BLOCKED", expected_version=store.hunt_get(hunt_id)["version"]
        )
        raise HonestBlockedError(f"hunt {hunt_id}: targeting {decision.status}, no target selected")

    chosen = next(c for c in cells if c["cell_id"] == decision.selected_cell_id)
    return {
        **target_cell,
        "cell_id": chosen["cell_id"],
        "subject": chosen.get("subject", chosen["cell_id"]),
        "prior": chosen.get("prior", 0.5),
        "scenario": chosen.get("scenario", target_cell.get("scenario")),
        "target_decision_id": decision.decision_id,
    }


def _do_mutate(
    store: Store,
    *,
    hunt_id: str,
    actor: str,
    target_cell: dict,
    mutation_plan: MutationPlan | None,
) -> dict:
    """MUTATION_READY (P3.1, replacing the P1 stub) -- compile a
    `MutationPlan` into a scenario overlay via `mutation.validate_and_compile`
    and stash it on `target_cell` for the lab driver. Fail-closed: a
    validation failure blocks the hunt honestly (no Red call, decision event
    recorded) rather than silently falling back to an unmutated scenario.

    When the caller doesn't inject an explicit `mutation_plan`, a trivial
    zero-operator plan is built (pure passthrough -- the overlay equals the
    reference scenario unchanged) so every iteration goes through the same
    validated/compiled/recorded path, never an implicit bypass.
    """
    from ..chain import SCENARIOS

    hunt_config = bully_config.load_hunt_config()
    scenario_name = target_cell.get("scenario") or next(iter(SCENARIOS))
    reference_scenario = SCENARIOS[scenario_name]

    plan = mutation_plan or mutation_mod.build_plan(
        reference_scenario=scenario_name,
        operators=[],
        allowed_targets=(
            (reference_scenario["target_host"],) if reference_scenario.get("target_host") else ()
        ),
        proposer=actor,
    )

    try:
        overlay = mutation_mod.validate_and_compile(
            plan, reference_scenario=reference_scenario, hunt_config=hunt_config
        )
    except mutation_mod.MutationValidationError as exc:
        store.mutation_plan_record(
            plan,
            status="rejected",
            rejection_reason_code=exc.reason_code,
            rejection_detail=str(exc),
        )
        store.hunt_advance_stage(
            hunt_id, "BLOCKED", expected_version=store.hunt_get(hunt_id)["version"]
        )
        _record(
            store,
            hunt_id=hunt_id,
            iteration_id=None,
            actor="system:orchestrator",
            kind="gate",
            subject_id=plan.plan_id,
            rationale=f"MUT validation failed: {exc.reason_code}",
            data={"reason_code": exc.reason_code, "detail": str(exc)},
        )
        raise HonestBlockedError(
            f"hunt {hunt_id}: mutation plan {plan.plan_id} rejected ({exc.reason_code})"
        ) from exc

    store.mutation_plan_record(plan, status="validated", overlay=overlay)
    _record(
        store,
        hunt_id=hunt_id,
        iteration_id=None,
        actor="system:orchestrator",
        kind="gate",
        subject_id=plan.plan_id,
        rationale=(
            f"MUT compiled overlay for {scenario_name} "
            f"(operators={list(overlay.applied_operators)}, truncated={overlay.truncated})"
        ),
        data={
            "applied_operators": list(overlay.applied_operators),
            "truncated": overlay.truncated,
            "truncation_rationale": overlay.truncation_rationale,
        },
    )
    return {**target_cell, "scenario": scenario_name, "mutation_overlay": overlay.to_dict()}


def _do_drift(store: Store, *, hunt_id: str, episode_view: dict) -> list:
    """ANALYZING (continued) -- BR-DRIFT temporal-cousin classification
    (P3.2, I-9), run after the cousin grade.

    Documented simplification (MASTER SS0 finding): the investigation arm
    does not yet hand LOOP a per-SPL-detection outcome breakdown, so this
    wiring treats the episode's own telemetry/detection reason codes as one
    detection sample keyed by scenario (`episode:<scenario>`).
    `drift_engine.update` itself is fully general over a real per-detection
    breakdown whenever one is wired in (P4+) -- see its own unit tests for
    multi-detection fixtures.
    """
    detection_id = f"episode:{episode_view['scenario']}"
    telemetry_status = episode_view.get("telemetry_status")
    detection_status = episode_view.get("detection_status")
    sensor_healthy = telemetry_status not in (
        "TELEMETRY_COLLECTION_FAILED",
        "TELEMETRY_NOT_INDEXED",
    )
    completeness = {
        "TELEMETRY_OBSERVED": 1.0,
        "TELEMETRY_NOT_INDEXED": 0.4,
        "TELEMETRY_COLLECTION_FAILED": 0.0,
    }.get(telemetry_status, 0.9)
    sample = {
        "detection_id": detection_id,
        "fired": detection_status == "DETECTION_CONFIRMED",
        "sourcetype_completeness": completeness,
        "clause_satisfied": (False if detection_status == "DETECTION_HIT_UNATTRIBUTED" else None),
        "row_shape": None,
        "environment_fingerprint": episode_view.get("target_host"),
        "sensor_healthy": sensor_healthy,
    }
    hunt_config = bully_config.load_hunt_config()
    policy_version = hunt_config.get("thresholds", {}).get("calibration_artifact", "v1")
    key = drift_engine.baseline_key(detection_id, policy_version)
    existing = store.detection_baseline_get(key)
    baselines = {key: existing} if existing is not None else {}

    flags, updated_baselines = drift_engine.update(
        episode_view["episode_id"], [sample], baselines, policy_version=policy_version
    )
    for baseline in updated_baselines.values():
        store.detection_baseline_upsert(baseline)
    for flag in flags:
        store.drift_flag_record(flag)
        _record(
            store,
            hunt_id=hunt_id,
            iteration_id=None,
            actor="system:orchestrator",
            kind="grade",
            subject_id=flag.detection_id,
            rationale=f"BR-DRIFT classified {flag.drift_class} (status={flag.status})",
            data={"flag_id": flag.flag_id, "routed": flag.routed, "score": flag.score},
        )
    return flags


def _do_cost(
    store: Store,
    *,
    hunt_id: str,
    iteration_id: str,
    exec_seconds: float,
    models: dict[str, str],
) -> Any:
    """COST (P4.1, I-13): meter this iteration's real resource use and
    append it to the cost ledger. `lab_minutes` and `analyst_minutes` are
    directly measured (wall clock around the lab call; no human analyst
    time in an automated LOOP iteration). `inference_calls` is an honest
    coarse proxy (one call attempt per resolved investigation role) marked
    `quality="estimated"` -- this build has no per-call token/latency
    instrumentation wired from `investigation.run_arm` yet, so those meters
    are simply not observed here rather than guessed at (I-13: never
    zero-fill a measurement this code doesn't actually have)."""
    components = [
        costing.observation(
            "lab_minutes", f"{iteration_id}:lab_minutes", round(exec_seconds / 60.0, 4)
        ),
        costing.observation("analyst_minutes", f"{iteration_id}:analyst_minutes", 0.0),
        costing.observation(
            "inference_calls",
            f"{iteration_id}:inference_calls",
            float(len(models)),
            quality="estimated",
        ),
    ]
    record = costing.build_record(hunt_id, iteration_id, components)
    store.cost_ledger_put(record)
    return record


def _do_plateau(store: Store, organ: Organ, *, hunt_id: str, neighborhood: str) -> Any:
    """COMPOUNDING -> CLOSED (P4.4, I-12): evaluate whether `neighborhood`
    is statistically exhausted now that this iteration's own hunt has just
    closed (so it counts as a valid trial for the *next* iteration's
    decision -- this evaluation informs future targeting, it never blocks
    the current iteration's own closure). Trials are assembled by
    `store.plateau_trials_for_neighborhood`; `discovery_positive` per trial
    is derived here via `scoreboard.score_record` (P4.2) over each trial's
    cousin assessment, reusing the same discovery-axis definition SCORE
    reports on rather than a second one.
    """
    hunt_config = bully_config.load_hunt_config()
    plateau_cfg = hunt_config.get("plateau", {})
    window = int(plateau_cfg.get("window", plateau_mod.MIN_VALID_TRIALS))
    has_other_neighborhoods = bool(plateau_cfg.get("has_other_neighborhoods", True))

    raw_trials = store.plateau_trials_for_neighborhood(neighborhood)
    trials: list[dict[str, Any]] = []
    for t in raw_trials:
        assessment = t.get("assessment")
        if assessment is not None:
            scored = scoreboard_mod.score_record(assessment)
            response_state = assessment.get("defense_response") or "NONE"
            discovery_positive = scored["discovery_value"] > 0.0
        else:
            response_state = "NONE"
            discovery_positive = False
        trials.append(
            {
                "trial_id": t["trial_id"],
                "neighborhood": t["neighborhood"],
                "mutation_dim": t["mutation_dim"],
                "valid": t["valid"],
                "promoted": t["promoted"],
                "response_state": response_state,
                "discovery_positive": discovery_positive,
                "version": t["version"],
            }
        )

    decision = plateau_mod.evaluate(
        neighborhood,
        trials,
        window,
        has_other_neighborhoods=has_other_neighborhoods,
        hunt_id=hunt_id,
    )
    store.plateau_put(decision)
    _record(
        store,
        hunt_id=hunt_id,
        iteration_id=None,
        actor="system:orchestrator",
        kind="plateau",
        subject_id=decision.plateau_id,
        rationale=f"PLT {decision.decision}/{decision.action} for {neighborhood!r}: {decision.note}",
        data=decision.to_dict(),
    )
    with contextlib.suppress(OrganUnavailable):
        # Same shared record shape the P1 "cousin" emission established
        # (the hunt_memory projection is one table across emission kinds --
        # `kind` differentiates); a dedicated plateau schema is future
        # work, not invented here to avoid a schema-alignment break on the
        # existing table.
        organ.index_emissions(
            [
                {
                    "kind": "plateau",
                    "hunt_id": hunt_id,
                    "episode_id": neighborhood,
                    "relationship": decision.decision,
                    "detection_response": decision.action,
                    "rationale": decision.note,
                    "trust_tier": "SUSPECT",
                    "provenance_class": "hunt_emission",
                }
            ]
        )
        organ.process_outbox()
    return decision


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
    models = _resolve_live_investigation_models(store)
    # PLAY (P6.3, I-16 CONSUMER: LOOP): inject the active playbook for this
    # hunt's scenario_class, if any -- absence is neutral (None), the hunt
    # proceeds unshaped. `episode.scenario` is the closest existing field to
    # a "scenario_class" label; injected only as an explicit kwarg so
    # pre-P6 investigation_arm stubs (fixed signature, no **kwargs) are
    # unaffected when no playbook is active.
    scenario_class = getattr(episode, "scenario", None)
    playbook_candidate = playbooks_mod.for_hunt(store, scenario_class) if scenario_class else None
    playbook_mode = cutover.feed_mode(bully_config.load_hunt_config(), "playbook_memory")
    playbook = playbook_candidate if playbook_mode == "authoritative" else None
    extra = {"playbook": playbook} if playbook else {}
    inv_result = investigation_arm(episode, models=models, dry_run=dry_run, **extra)

    telemetry_view = evidence_mod.adapt_episode_telemetry(episode)
    signature = signatures_mod.build_signature(episode_view, telemetry_view)
    candidates = retrieve_candidate_axes(signature, organ)
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
            "playbook_id": playbook["playbook_id"] if playbook else None,
        },
    )
    recall_id = store.latest_recall_id_for_hunt(hunt_id)
    if recall_id is not None:
        baseline_models = bully_config.resolve_investigation_models()
        model_changed = baseline_models != models
        store.decision_impact_put(
            DecisionImpact(
                impact_id=new_id("impact"),
                recall_id=recall_id,
                consuming_decision_ref=assessment.assessment_id,
                before={"models": baseline_models},
                after={"models": models},
                cited_record_ids=sorted(set(models.values()) - set(baseline_models.values())),
                change_kind="SELECTED" if model_changed else "NO_EFFECT",
                explanation=(
                    "P7 paired cutover proof for fleet_local_fine_tune; "
                    f"mode={cutover.feed_mode(bully_config.load_hunt_config(), 'fleet_local_fine_tune')}"
                ),
            )
        )
        store.decision_impact_put(
            DecisionImpact(
                impact_id=new_id("impact"),
                recall_id=recall_id,
                consuming_decision_ref=assessment.assessment_id,
                before={"playbook_id": None},
                after={
                    "playbook_id": playbook_candidate["playbook_id"] if playbook_candidate else None
                },
                cited_record_ids=(
                    [playbook_candidate["playbook_id"]] if playbook_candidate else []
                ),
                change_kind="CONTROL_ADDED" if playbook_candidate else "NO_EFFECT",
                explanation=f"P7 paired cutover proof for playbook_memory; mode={playbook_mode}",
            )
        )
    return inv_result, assessment, signature


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
    mutation_plan: MutationPlan | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Drive exactly one hunt iteration through the full stage machine.

    LOAD -> RECALL -> SELECT(stub) -> DIRECT(MUT, P3.1) -> INVESTIGATE ->
    GRADE -> DRIFT(P3.2) -> RECORD -> STOP. Every stage transition is a
    real, checked SUB write; there is no code path that reaches TARGETED
    without a persisted RecallReceipt, and no code path that closes the
    iteration with a required unindexed emission still pending.

    `mutation_plan` lets a caller (CLI, test) inject an explicit
    `MutationPlan`; when omitted, `_do_mutate` builds a trivial zero-operator
    passthrough plan so every iteration still goes through the same
    validated/compiled/recorded MUT path.
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
    recall_receipt = _do_recall(
        store, organ, hunt_id=hunt_id, neighborhood=neighborhood, context=context
    )
    _stage("RECALL_READY")

    # TARGETED -- real TGT selection (P4.3, replacing the P1 stub).
    target_cell = _do_target(
        store,
        hunt_id=hunt_id,
        context=context,
        recall_receipt=recall_receipt,
        target_cell=target_cell,
    )
    _stage("TARGETED")

    # MUTATION_READY -- MUT compiles a MutationPlan into a scenario overlay
    # (P3.1, replacing the P1 stub). Fail-closed: raises HonestBlockedError
    # (already recorded + hunt advanced to BLOCKED inside _do_mutate).
    target_cell = _do_mutate(
        store, hunt_id=hunt_id, actor=actor, target_cell=target_cell, mutation_plan=mutation_plan
    )
    _stage("MUTATION_READY")

    iteration_id = f"{hunt_id}-i1"

    # EXECUTING -- unchanged Red/Blue lab machinery via the injected driver.
    _stage("EXECUTING")
    _exec_started_at = time.time()
    try:
        episode = lab_driver(target_cell, dry_run=dry_run)
    except HonestBlockedError:
        store.hunt_advance_stage(
            hunt_id, "BLOCKED", expected_version=store.hunt_get(hunt_id)["version"]
        )
        raise

    episode_view = evidence_mod.adapt_episode(episode)
    _record(
        store,
        hunt_id=hunt_id,
        iteration_id=iteration_id,
        actor="system:orchestrator",
        kind="gate",
        subject_id=episode_view["episode_id"],
        rationale="episode truth-plane evidence recorded before grading",
        data=episode_view,
    )
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

    # ANALYZING -- investigation arm -> signature -> cousin grade -> BR-DRIFT.
    _stage("ANALYZING")
    inv_result, assessment, signature = _do_analyze(
        store,
        organ,
        hunt_id=hunt_id,
        iteration_id=iteration_id,
        episode_view=episode_view,
        episode=episode,
        investigation_arm=investigation_arm,
        dry_run=dry_run,
    )
    drift_flags = _do_drift(store, hunt_id=hunt_id, episode_view=episode_view)

    # COST (P4.1) -- meter this iteration's real resource use before
    # PROMOTING/COMPOUNDING so later hunts' TGT selection has a real ledger
    # to rank against.
    cost_record = _do_cost(
        store,
        hunt_id=hunt_id,
        iteration_id=iteration_id,
        exec_seconds=max(time.time() - _exec_started_at, 0.0),
        models=_resolve_live_investigation_models(store),
    )
    if target_cell.get("cell_id"):
        store.coverage_cell_put(
            {
                "cell_id": target_cell["cell_id"],
                "subject": target_cell.get("subject", target_cell["cell_id"]),
                "scenario": target_cell.get("scenario"),
                "prior": target_cell.get("prior", 0.5),
                "cost_ref": hunt_id,
            }
        )

    # PROMOTING / COMPOUNDING -- BIN/HEART land P2; universal index emission
    # (I-4) happens regardless, in this same iteration, never deferred to a
    # background worker that could silently never run in P1.
    _stage("PROMOTING")
    _stage("COMPOUNDING")
    org_record = {
        **signatures_mod.reference_record_fields(signature),
        "kind": "cousin",
        "signature_id": signature.signature_id,
        "hunt_id": hunt_id,
        "episode_id": episode_view["episode_id"],
        "subject": target_cell.get("subject", target_cell.get("cell_id")),
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

    # COMPOUNDING -> CLOSED plateau decision (P4.4) -- informs whether the
    # *next* hunt in this neighborhood should continue/rotate/stop; never
    # blocks this iteration's own closure.
    plateau_decision = _do_plateau(store, organ, hunt_id=hunt_id, neighborhood=neighborhood)

    return {
        "hunt_id": hunt_id,
        "iteration_id": iteration_id,
        "episode_id": episode_view["episode_id"],
        "assessment_id": assessment.assessment_id,
        "relationship": assessment.relationship,
        "defense_response": assessment.defense_response,
        "investigation_verdict": inv_result.verdict,
        "outbox": outbox_result,
        "drift_flags": [
            {"drift_class": f.drift_class, "status": f.status, "routed": f.routed}
            for f in drift_flags
        ],
        "cost": {
            "record_id": cost_record.record_id,
            "computed_units": cost_record.computed_units,
            "quality_flag": cost_record.quality_flag,
        },
        "plateau": {
            "plateau_id": plateau_decision.plateau_id,
            "decision": plateau_decision.decision,
            "action": plateau_decision.action,
        },
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
    target_cell: dict | None = None,
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
            role_snapshot=_resolve_live_investigation_models(store),
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
        try:
            result = run_hunt_iteration(
                store,
                organ,
                hunt_id=hunt_id,
                actor=actor,
                neighborhood=neighborhood,
                target_cell=target_cell,
                lab_driver=lab_driver,
                investigation_arm=investigation_arm,
                dry_run=dry_run,
            )
        except Exception:
            row = store.hunt_get(hunt_id)
            if row is not None and row["stage"] not in {"BLOCKED", "CLOSED", "FAILED"}:
                with contextlib.suppress(IllegalTransitionError):
                    store.hunt_advance_stage(hunt_id, "BLOCKED", expected_version=row["version"])
            with contextlib.suppress(Exception):
                store.lease_release(hunt_id, owner=actor)
            raise
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
    handoff_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`hunt queue` (list) / `hunt queue --confirm <id>` / `hunt queue
    --reject <id> --rationale ...` -- promotion-queue resolution. [GATE]
    operator-only (P2.5): `_require_operator` refuses a non-operator actor
    before this function ever touches the store, and `store.promotion_resolve`
    /`store.candidate_promote` each independently DB-enforce the same
    requirement -- there is no code path here that promotes/rejects
    without an operator actor (MASTER SS7).

    `handoff_inputs` (P5.3, ARCH SS4.2 "promotion.promote -> handoff.
    build_package"): opt-in -- when supplied on a `cousin_detection`
    confirm, `handoff.build_package` runs immediately after promotion using
    these kwargs (capture_path/benign_events/evidence overrides, ...) and
    the resulting package summary is attached to the return value. Left
    `None` (the default) this call behaves exactly as it did before P5 --
    MASTER SS2 forbids changing existing runtime behavior outside an
    explicit cutover phase, so HND only runs when a caller opts in.
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

        handoff_package = None
        if row["item_kind"] == "cousin_detection":
            if target_state == "confirmed":
                promotion_mod.promote(store, row["item_id"], operator_actor=actor, note=rationale)
                if handoff_inputs is not None:
                    from . import handoff as handoff_mod

                    pkg = handoff_mod.build_package(store, row["item_id"], **handoff_inputs)
                    handoff_package = {
                        "proposal_id": pkg.proposal_id,
                        "family": pkg.family,
                        "proof_legs": pkg.proof_legs,
                    }
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

        result = {"queue_id": item_id, "state": target_state, "item_kind": row["item_kind"]}
        if handoff_package is not None:
            result["handoff"] = handoff_package
        return result
    finally:
        if owns_store:
            store.close()


# ── HND deployment + post-deploy replay + cell closure (P5.3, I-14) ────────


def handoff_deploy(
    *,
    proposal_id: str,
    actor: str,
    spl_commit_ref: str,
    receipt_hash: str,
    store: Store | None = None,
) -> dict[str, Any]:
    """`portal security hunt handoff --deploy <proposal_id>` -- records the
    operator's already-made `spl_detections.yaml` commit as a deployment
    receipt (I-14 operator boundary: the commit itself goes through the
    repo's normal pre-push BQ/AZ validation, outside this call). [GATE]
    operator-only; DB-enforced independently
    (`trg_deployment_operator_only`, `trg_detection_proposal_deploy_
    requires_proof_legs`)."""
    _require_operator(actor)
    from . import handoff as handoff_mod

    owns_store = store is None
    store = store or Store(bully_config.hunt_dir() / "hunt_state.db")
    try:
        return handoff_mod.deploy(
            store,
            proposal_id,
            operator_actor=actor,
            spl_commit_ref=spl_commit_ref,
            receipt_hash=receipt_hash,
        )
    finally:
        if owns_store:
            store.close()


def handoff_record_replay(
    *,
    deployment_id: str,
    passed: bool,
    noise_estimate: float | None = None,
    detail: str = "",
    store: Store | None = None,
    organ: Organ | None = None,
) -> dict[str, Any]:
    """Post-deploy Purple replay result (I-14): only a passed replay closes
    the cell to `KNOWN_COVERED` (DB-enforced,
    `trg_known_covered_requires_deploy_replay`); a failed replay is
    ORG-indexed as negative learning (DESIGN SS23) -- `organ.py` is the only
    module that touches the projection (MASTER SS3), so this orchestrator
    function is what actually calls `organ.index_emissions` for the
    `org_record` `handoff.record_replay` returns."""
    from . import handoff as handoff_mod

    owns_store = store is None
    store = store or Store(bully_config.hunt_dir() / "hunt_state.db")
    owns_organ = organ is None
    try:
        result = handoff_mod.record_replay(
            store,
            deployment_id,
            passed=passed,
            noise_estimate=noise_estimate,
            detail=detail,
        )
        org_record = result.pop("org_record", None)
        if org_record is not None:
            if organ is None:
                organ = Organ(store=store, db_path=bully_config.hunt_dir() / "hunt_memory")
            organ.index_emissions([org_record])
        return result
    finally:
        if owns_organ and organ is not None:
            organ.close()
        if owns_store:
            store.close()


def handoff_reject(
    *,
    proposal_id: str,
    actor: str,
    rationale: str,
    store: Store | None = None,
    organ: Organ | None = None,
) -> dict[str, Any]:
    """Operator reject -> DISPROVED-equivalent for a detection proposal;
    ORG-indexed as negative learning (DESIGN SS23). [GATE] operator-only."""
    _require_operator(actor)
    from . import handoff as handoff_mod

    owns_store = store is None
    store = store or Store(bully_config.hunt_dir() / "hunt_state.db")
    owns_organ = organ is None
    try:
        result = handoff_mod.reject(store, proposal_id, operator_actor=actor, rationale=rationale)
        org_record = result.pop("org_record", None)
        if org_record is not None:
            if organ is None:
                organ = Organ(store=store, db_path=bully_config.hunt_dir() / "hunt_memory")
            organ.index_emissions([org_record])
        return result
    finally:
        if owns_organ and organ is not None:
            organ.close()
        if owns_store:
            store.close()
