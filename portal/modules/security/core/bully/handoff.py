"""bully.handoff -- HND, the detection-engineering exit (P5.2, I-14).

``build_package(store, candidate_id)`` turns a PROMOTED candidate into an
11-part family-generalizing detection proposal (DESIGN SS23). SPL/Sigma
generalization is drafted by a model from the cousin's discriminators
(``siem.spl_detections.technique_signature_full`` / ``spl_variants_for``)
and then validated in code: ``validate_spl_syntax`` (imported from
the retired growth-loop gate (now successor-owned here) plus dry execution
against the replayed capture. The three detection-proof legs execute for
real:

- **fires-on-attack** via ``capture_recipes``/``capture_store`` replay
- **quiet-on-benign** via the benign corpus (``benign_corpus_bench``)
- **no-regression** via the BQ/AZ ``validate_system`` lanes

Every leg follows the same injectable-gather / pure-decide split
``promotion.py`` established for G1a/G1b/G2 (``replay_and_build_g1a_input`` /
``_default_g1a_static``): the *production default* gather function really
touches the lab/corpus/validation machinery; the decision function is a pure
check over already-gathered evidence so unit tests stay hermetic (no
network) while the default path is the real check -- never a placeholder-
true leg (MASTER SS0's "growth_loop disease" failure meaning).

Boundary rules (MASTER SS3): this module never touches SQL directly
(``store.py`` is the sole SQL owner); it never touches the ``hunt_memory``
projection directly (``organ.py`` is the sole toucher -- callers index the
``org_record`` this module returns). Model calls happen only through the
injected ``call_model`` (default mirrors ``adversary.py``'s
``agentic_blue_eval._call_model`` pattern); no model name is hardcoded.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from . import config as bully_config
from .contracts import DecisionEvent, HandoffPackage, new_id
from .store import Store

CallModelFn = Callable[..., dict]


class HandoffInfrastructureError(RuntimeError):
    """Real gather-adapter infra failure (capture replay down, corpus
    missing, validate_system lane import failure, ...) -- distinct from a
    gate that ran and legitimately failed (MASTER SS8)."""


def _default_call_model(model: str, messages: list[dict]) -> dict:
    from ..agentic_blue_eval import _call_model

    return _call_model(model, messages, max_tokens=1400)


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


# ── SPL/Sigma generalization draft (model-drafted, code-validated) ─────────

_DRAFT_SYSTEM_PROMPT = (
    "You are drafting a family-generalizing SIEM detection for Portal 5's "
    "detection-engineering handoff. You are given a MITRE ATT&CK technique's "
    "existing SPL detection, its discriminator tokens, and a cousin's "
    "distance decomposition against it. Generalize the SPL so it also "
    "covers the cousin's behavior, and draft an equivalent Sigma rule. "
    "Reply with two fenced blocks labeled ```spl ... ``` and "
    "```sigma ... ```. Never invent an index or sourcetype not already "
    "present in the reference material."
)


def _render_draft_context(technique_id: str, signature: dict, discriminators: dict) -> str:
    lines = [
        f"technique_id: {technique_id}",
        f"reference_spl: {discriminators.get('spl', '')}",
        f"expected_signal: {discriminators.get('expected_signal', '')}",
        f"discriminator_tokens: {discriminators.get('distinguishing_features', {}).get('discriminator_tokens', [])}",
        f"sibling_ids: {discriminators.get('distinguishing_features', {}).get('sibling_ids', [])}",
        f"cousin_action_sequence: {signature.get('action_sequence', [])}",
    ]
    return "\n".join(lines)


def draft_generalization(
    technique_id: str,
    signature: dict,
    discriminators: dict,
    *,
    call_model: CallModelFn | None = None,
) -> dict:
    """Model drafts the SPL/Sigma generalization from the cousin's
    discriminators (I-14). A model failure is an honest degrade to the
    library's existing SPL, never a fabricated new detection -- the caller's
    `validate_spl_syntax` + dry-exec gate is what actually decides whether
    the result is usable, not this function."""
    call_model = call_model or _default_call_model
    fallback_spl = discriminators.get("spl", "") or f"# TODO: draft SPL for {technique_id}"
    context = _render_draft_context(technique_id, signature, discriminators)
    try:
        msg = call_model(
            "bully-handoff-drafter",
            [
                {"role": "system", "content": _DRAFT_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
        )
        text = msg.get("content", "") if isinstance(msg, dict) else ""
    except Exception as exc:  # honest degrade, never a crash (I-14 failure semantics)
        return {
            "spl": fallback_spl,
            "sigma_rule": "",
            "rationale": f"model draft unavailable ({type(exc).__name__}); fell back to library SPL",
        }
    spl_match = re.search(r"```spl\s*\n(.*?)```", text, re.DOTALL)
    sigma_match = re.search(r"```sigma\s*\n(.*?)```", text, re.DOTALL)
    return {
        "spl": (spl_match.group(1).strip() if spl_match else fallback_spl),
        "sigma_rule": (sigma_match.group(1).strip() if sigma_match else ""),
        "rationale": text.strip(),
    }


# ── dry execution against replayed telemetry (deterministic, real) ────────


# Splunk routing/meta fields never appear inside a raw event body -- they
# select *which* index/sourcetype to search, they are not event content --
# so they are excluded from the discriminator-token set a dry run checks
# for. Mirrors validate_spl_syntax's own `has_index` treatment of `index=`
# as a routing signal rather than evidentiary content.
_SPL_META_FIELDS = frozenset({"index", "sourcetype", "source", "host"})


def _discriminator_tokens(spl: str) -> list[str]:
    """Extract `key=value` / `key="value"` predicates from an SPL string --
    the literal content tokens a real Splunk search filters event bodies on
    (routing fields excluded, see `_SPL_META_FIELDS`). Used both to
    dry-execute against a replayed capture and to check the same tokens
    never appear in the benign corpus."""
    return [
        f"{k}={v}"
        for k, v in re.findall(r'([A-Za-z_][\w.]*)=("[^"]*"|\S+)', spl)
        if k.lower() not in _SPL_META_FIELDS
    ]


def dry_execute(spl: str, raw_events: list[str]) -> int:
    """Deterministic dry execution: count how many raw telemetry lines
    contain every discriminator token the SPL filters on. Real code, not a
    placeholder -- this is what 'validated ... + dry execution against the
    replayed capture' means at I-14 (no live Splunk round-trip needed for
    a syntactic/token-presence dry run)."""
    tokens = _discriminator_tokens(spl)
    if not tokens:
        return 0
    hits = 0
    for line in raw_events:
        if all(token in line for token in tokens):
            hits += 1
    return hits


def validate_spl_syntax(spl: str) -> tuple[bool, list[str]]:
    """Successor-owned deterministic SPL gate (retired growth-loop adapter)."""
    errors: list[str] = []
    if not spl or not spl.strip():
        return False, ["empty SPL"]
    stripped = spl.strip()
    if stripped.startswith("#"):
        return False, ["SPL is a placeholder comment, not a real query"]
    has_index = "index=" in stripped or "index " in stripped
    has_pipe = "|" in stripped
    has_search = stripped.startswith("search ") or has_index or has_pipe
    if not has_search:
        errors.append("SPL lacks a search command or index reference")
    return not errors, errors


# ── proof leg 1: fires-on-attack (capture_recipes replay) ─────────────────


def gather_fires_on_attack(capture_path: str, spl: str, *, replay_capture_fn=None) -> dict:
    """Real: replays the capture (`siem.capture_store.replay_capture` by
    default, injectable for tests) and dry-executes the drafted SPL against
    its telemetry -- mirrors `promotion.replay_and_build_g1a_input`."""
    from pathlib import Path

    replay_fn = replay_capture_fn
    if replay_fn is None:
        from ..siem.capture_store import replay_capture as replay_fn
    try:
        replay = replay_fn(capture_path)
    except Exception as exc:  # infra failure, not a leg failure
        raise HandoffInfrastructureError(f"capture replay failed: {exc}") from exc
    if not replay.get("ok", False):
        raise HandoffInfrastructureError(f"capture replay not ok: {replay.get('error')}")
    ok, syntax_errors = validate_spl_syntax(spl)
    telemetry = json.loads(Path(capture_path).read_text()).get("telemetry", {})
    raw_events = [e for events in telemetry.values() for e in events]
    hits = dry_execute(spl, raw_events) if ok else 0
    return {
        "replay": replay,
        "syntax_ok": ok,
        "syntax_errors": syntax_errors,
        "dry_exec_hits": hits,
    }


def check_fires_on_attack(evidence: dict) -> dict:
    if "replay" not in evidence:
        return {"outcome": "blocked", "reasons": ["no fires-on-attack replay evidence supplied"]}
    if not evidence.get("syntax_ok", False):
        return {
            "outcome": "fail",
            "reasons": [f"SPL syntax invalid: {'; '.join(evidence.get('syntax_errors', []))}"],
        }
    if not evidence.get("dry_exec_hits"):
        return {
            "outcome": "fail",
            "reasons": ["drafted SPL produced zero dry-exec hits against the replayed capture"],
        }
    return {
        "outcome": "pass",
        "reasons": [],
        "evidence": {"dry_exec_hits": evidence["dry_exec_hits"]},
    }


# ── proof leg 2: quiet-on-benign (benign corpus) ───────────────────────────


def gather_quiet_on_benign(spl: str, *, benign_events: list[str] | None = None) -> dict:
    """Real: checks the drafted SPL's discriminator tokens against the
    benign corpus (`benign_corpus_bench.BENIGN_CELLS` by default -- local
    fixture data, no network needed to read it; injectable for tests)."""
    if benign_events is None:
        from ..benign_corpus_bench import BENIGN_CELLS

        benign_events = [e for cell in BENIGN_CELLS for e in cell["events"]]
    hits = dry_execute(spl, benign_events)
    return {"benign_hits": hits, "benign_sample_size": len(benign_events)}


def check_quiet_on_benign(evidence: dict) -> dict:
    if "benign_hits" not in evidence:
        return {"outcome": "blocked", "reasons": ["no benign-corpus evidence supplied"]}
    if evidence.get("benign_sample_size", 0) == 0:
        return {"outcome": "blocked", "reasons": ["empty benign-corpus sample"]}
    if evidence["benign_hits"] > 0:
        return {
            "outcome": "fail",
            "reasons": [
                f"drafted SPL fired {evidence['benign_hits']} time(s) on the benign corpus"
            ],
        }
    return {
        "outcome": "pass",
        "reasons": [],
        "evidence": {"benign_sample_size": evidence["benign_sample_size"]},
    }


# ── proof leg 3: no-regression (BQ/AZ validate_system lanes) ──────────────


def gather_no_regression() -> dict:
    """Real: runs the BQ (benign alert-fatigue semantics) and AZ (detection
    recall vs emergent corpus) `validate_system.py` lanes MASTER SS4 holds
    green at every commit -- the concrete 'no-regression via BQ/AZ lanes'
    evidence (I-14)."""
    from scripts.validation.blue_orchestration import (
        check_benign_alert_fatigue,
        check_recall_metric,
    )

    bq_status, bq_detail, _ = check_benign_alert_fatigue()
    az_status, az_detail, _ = check_recall_metric()
    return {"bq": bq_status, "bq_detail": bq_detail, "az": az_status, "az_detail": az_detail}


def check_no_regression(evidence: dict) -> dict:
    if "bq" not in evidence or "az" not in evidence:
        return {"outcome": "blocked", "reasons": ["no BQ/AZ lane evidence supplied"]}
    if evidence["bq"] != "PASS" or evidence["az"] != "PASS":
        return {
            "outcome": "fail",
            "reasons": [f"BQ={evidence['bq']} AZ={evidence['az']}"],
        }
    return {"outcome": "pass", "reasons": []}


# ── build_package (I-14) ────────────────────────────────────────────────


def _run_proof_legs(
    *,
    draft_spl: str,
    capture_path: str | None,
    replay_capture_fn,
    benign_events: list[str] | None,
    fires_on_attack_evidence: dict | None,
    quiet_on_benign_evidence: dict | None,
    no_regression_evidence: dict | None,
) -> dict[str, dict]:
    """Gather + decide all three detection-proof legs. Split out of
    `build_package` to keep it under the repo's complexity budget (mirrors
    `promotion._dispatch_gate`'s split rationale: pure routing/sequencing,
    no decision logic added here beyond what each leg's own gather/check
    pair already does)."""
    if fires_on_attack_evidence is not None:
        fa_evidence = fires_on_attack_evidence
    elif capture_path is not None:
        fa_evidence = gather_fires_on_attack(
            capture_path, draft_spl, replay_capture_fn=replay_capture_fn
        )
    else:
        fa_evidence = {}
    fa_result = check_fires_on_attack(fa_evidence)

    qb_evidence = quiet_on_benign_evidence or gather_quiet_on_benign(
        draft_spl, benign_events=benign_events
    )
    qb_result = check_quiet_on_benign(qb_evidence)

    if no_regression_evidence is not None:
        nr_result = check_no_regression(no_regression_evidence)
    else:
        try:
            nr_evidence = gather_no_regression()
        except Exception as exc:  # infra failure -- honest blocked, never a fabricated pass
            nr_result = {"outcome": "blocked", "reasons": [f"BQ/AZ lane infra error: {exc}"]}
        else:
            nr_result = check_no_regression(nr_evidence)

    return {"fires_on_attack": fa_result, "quiet_on_benign": qb_result, "no_regression": nr_result}


def _assemble_package(
    *,
    candidate_id: str,
    row: dict,
    technique_id: str,
    discriminators: dict,
    spl_variants: list[dict],
    draft: dict,
    assessment: dict | None,
    gate_results: list[dict],
    recipe_name: str,
    proof_legs: dict,
    owner: str,
    expiry: float | None,
) -> dict:
    """Assemble the 11-part package dict (DESIGN SS23). Split out of
    `build_package` for the same complexity-budget reason as
    `_run_proof_legs`."""
    g2 = next((g for g in gate_results if g["gate_id"] == "G2"), None)
    fp_analysis = json.loads(g2["evidence_json"]) if g2 is not None else {}

    from ..response_loop import propose_response_playbook

    ir_playbook = propose_response_playbook(technique_id, scenario=candidate_id)
    regression_recipe = {
        "recipe_name": recipe_name,
        "command": f"# replay capture for {candidate_id} against the generalized SPL",
        "success_pattern": r"(?m)^__PORTAL_RECIPE_OK__$",
    }
    complete = bool(assessment and assessment.get("completeness", 1.0) >= 1.0)
    return {
        "spl": draft["spl"],
        "spl_variants": spl_variants,
        "sigma_rule": draft["sigma_rule"],
        "required_telemetry": [v.get("source", "") for v in spl_variants]
        or [discriminators.get("expected_signal", "")],
        "attack_mapping_delta": {
            "technique_id": technique_id,
            "sibling_ids": discriminators.get("distinguishing_features", {}).get("sibling_ids", []),
            "new_family": True,
        },
        "evidence_package": {
            "candidate_id": candidate_id,
            "hunt_id": row["hunt_id"],
            "assessment_id": row["assessment_id"],
            "gate_results": [
                {"gate_id": g["gate_id"], "outcome": g["outcome"]} for g in gate_results
            ],
        },
        "regression_recipe_name": recipe_name,
        "regression_recipe": regression_recipe,
        "fp_analysis": fp_analysis,
        "known_limitations": (
            [] if complete else ["cousin evidence completeness below 1.0 -- see evidence_package"]
        ),
        "ir_implications": ir_playbook.actions,
        "coverage_impact_preview": {
            "cell": f"cell:{technique_id}",
            "delta": "adds known_covered pending deployment",
        },
        "rollout_plan": f"Deploy {recipe_name} to spl_detections.yaml; monitor for {int(expiry or 0) or 'n/a'}.",
        "rollback_plan": "Revert the spl_detections.yaml commit; no live detection removed automatically.",
        "owner": owner,
        "expiry": expiry,
        "proof_legs": proof_legs,
    }


def build_package(
    store: Store,
    candidate_id: str,
    *,
    owner: str = "",
    expiry: float | None = None,
    capture_path: str | None = None,
    recipe_name: str | None = None,
    benign_events: list[str] | None = None,
    replay_capture_fn=None,
    call_model: CallModelFn | None = None,
    fires_on_attack_evidence: dict | None = None,
    quiet_on_benign_evidence: dict | None = None,
    no_regression_evidence: dict | None = None,
) -> HandoffPackage:
    """I-14 `build_package(candidate_id) -> HandoffPackage`. The candidate
    must already be PROMOTED (BIN+HEART live, MASTER phase-dependency
    rule). Failure semantics: a proof-leg failure never raises -- the
    proposal is persisted `status='draft'` (rework, never shipped) and the
    returned package's `proof_legs` records exactly which leg(s) failed;
    only when all three legs pass does the proposal advance to
    `'submitted'` (ready for operator review, I-14 STATE EFFECT).

    Each proof leg accepts a pre-gathered `*_evidence` override (mirrors
    `promotion.py`'s gate-input injection) so unit tests stay hermetic; the
    production default gathers real evidence via `gather_fires_on_attack`/
    `gather_quiet_on_benign`/`gather_no_regression`.
    """
    row = store.candidate_get(candidate_id)
    if row is None:
        raise ValueError(f"no such candidate: {candidate_id}")
    if row["current_state"] != "PROMOTED":
        raise ValueError(
            f"build_package requires a PROMOTED candidate, got {row['current_state']!r}"
        )

    assessment = store.cousin_assessment_get(row["assessment_id"])
    signature = store.signature_get(assessment["subject_signature_id"]) if assessment else None
    attack_mappings = (signature or {}).get("attack_mappings") or []
    technique_id = attack_mappings[0]["technique_id"] if attack_mappings else "UNKNOWN"

    from ..siem.spl_detections import spl_variants_for, technique_signature_full

    discriminators = technique_signature_full(technique_id)
    spl_variants = spl_variants_for(technique_id)

    draft = draft_generalization(
        technique_id, signature or {}, discriminators, call_model=call_model
    )
    recipe_name = recipe_name or f"cousin_{candidate_id}"

    proof_legs = _run_proof_legs(
        draft_spl=draft["spl"],
        capture_path=capture_path,
        replay_capture_fn=replay_capture_fn,
        benign_events=benign_events,
        fires_on_attack_evidence=fires_on_attack_evidence,
        quiet_on_benign_evidence=quiet_on_benign_evidence,
        no_regression_evidence=no_regression_evidence,
    )
    fires_on_attack = proof_legs["fires_on_attack"]["outcome"] == "pass"
    quiet_on_benign = proof_legs["quiet_on_benign"]["outcome"] == "pass"
    no_regression = proof_legs["no_regression"]["outcome"] == "pass"

    gate_results = store.gate_results_for_candidate(
        candidate_id, alert_version=row["alert_version"]
    )
    package = _assemble_package(
        candidate_id=candidate_id,
        row=row,
        technique_id=technique_id,
        discriminators=discriminators,
        spl_variants=spl_variants,
        draft=draft,
        assessment=assessment,
        gate_results=gate_results,
        recipe_name=recipe_name,
        proof_legs=proof_legs,
        owner=owner,
        expiry=expiry,
    )
    fp_analysis = package["fp_analysis"]
    regression_recipe = package["regression_recipe"]
    content_hash = bully_config.content_hash(package)

    prior = store.detection_proposal_latest_for_candidate(candidate_id)
    proposal_id = new_id("prop")
    artifacts_dir = str(bully_config.hunt_dir() / "artifacts" / proposal_id)
    store.detection_proposal_put(
        proposal_id=proposal_id,
        candidate_id=candidate_id,
        hunt_id=row["hunt_id"],
        family=technique_id,
        package=package,
        content_hash=content_hash,
        owner=owner,
        expiry=expiry,
        artifacts_dir=artifacts_dir,
        supersedes=(prior["proposal_id"] if prior is not None else None),
    )
    store.detection_proposal_set_proof_legs(
        proposal_id,
        fires_on_attack=fires_on_attack,
        quiet_on_benign=quiet_on_benign,
        no_regression=no_regression,
        proof_legs=proof_legs,
        regression_recipe_name=recipe_name,
    )
    all_legs_passed = fires_on_attack and quiet_on_benign and no_regression
    if all_legs_passed:
        store.detection_proposal_set_status(proposal_id, "submitted")
    _record(
        store,
        hunt_id=row["hunt_id"],
        actor="system:handoff",
        kind="handoff",
        subject_id=proposal_id,
        rationale=(
            "HND package built -- all proof legs passed, submitted for operator review"
            if all_legs_passed
            else "HND package built -- proof-leg failure, returned for rework (never shipped)"
        ),
        data={"candidate_id": candidate_id, "proof_legs": proof_legs},
    )

    return HandoffPackage(
        proposal_id=proposal_id,
        candidate_id=candidate_id,
        family=technique_id,
        spl=package["spl"],
        spl_variants=package["spl_variants"],
        sigma_rule=package["sigma_rule"],
        required_telemetry=package["required_telemetry"],
        attack_mapping_delta=package["attack_mapping_delta"],
        evidence_package=package["evidence_package"],
        regression_recipe_name=recipe_name,
        regression_recipe=regression_recipe,
        fp_analysis=fp_analysis,
        known_limitations=package["known_limitations"],
        ir_implications=package["ir_implications"],
        coverage_impact_preview=package["coverage_impact_preview"],
        rollout_plan=package["rollout_plan"],
        rollback_plan=package["rollback_plan"],
        owner=owner,
        expiry=expiry,
        proof_legs=proof_legs,
        content_hash=content_hash,
    )


# ── operator dispositions: deploy / replay / reject (P5.3) ────────────────


def deploy(
    store: Store,
    proposal_id: str,
    *,
    operator_actor: str,
    spl_commit_ref: str,
    receipt_hash: str,
) -> dict:
    """The `spl_detections.yaml` change itself is an operator commit through
    the repo's normal pre-push validation (BQ/AZ green) -- this records the
    *receipt* of that already-made commit (I-14 operator boundary). Refuses
    (DB-enforced, `trg_detection_proposal_deploy_requires_proof_legs`) unless
    all three proof legs are recorded pass."""
    proposal = store.detection_proposal_get(proposal_id)
    if proposal is None:
        raise ValueError(f"no such detection_proposal: {proposal_id}")
    deployment_id = store.deployment_put(
        deployment_id=new_id("dep"),
        proposal_id=proposal_id,
        spl_commit_ref=spl_commit_ref,
        deployed_by=operator_actor,
        receipt_hash=receipt_hash,
    )
    store.detection_proposal_set_status(proposal_id, "deployed")
    store.detection_proposal_set_deployment(proposal_id, deployment_id)
    _record(
        store,
        hunt_id=proposal.get("hunt_id"),
        actor=operator_actor,
        kind="deploy",
        subject_id=proposal_id,
        rationale=f"operator commit {spl_commit_ref} deployed",
        data={"deployment_id": deployment_id, "spl_commit_ref": spl_commit_ref},
    )
    try:
        from portal.platform.wiki.provenance_ledger import append_entry

        append_entry(
            episode_id=proposal["candidate_id"],
            scenario=proposal.get("hunt_id") or "",
            capability_verdict="DEPLOYED",
            event="bully_handoff_deploy",
        )
    except Exception:  # best-effort, never blocks the deployment record (I-21 precedent)
        pass
    return {"proposal_id": proposal_id, "deployment_id": deployment_id, "status": "deployed"}


def record_replay(
    store: Store,
    deployment_id: str,
    *,
    passed: bool,
    noise_estimate: float | None = None,
    detail: str = "",
) -> dict:
    """Post-deploy Purple replay result (I-14). Only a *passed* replay
    closes the cell to `KNOWN_COVERED` -- DB-enforced
    (`trg_known_covered_requires_deploy_replay`); a failed replay records
    `replay-failed` and never touches `known_state`."""
    deployment = store.deployment_get(deployment_id)
    if deployment is None:
        raise ValueError(f"no such deployment: {deployment_id}")
    proposal = store.detection_proposal_get(deployment["proposal_id"])
    validation_id = new_id("val")
    store.replay_validation_put(
        validation_id=validation_id,
        deployment_id=deployment_id,
        passed=passed,
        noise_estimate=noise_estimate,
        detail=detail,
    )
    org_record: dict[str, Any] | None = None
    if passed:
        store.detection_proposal_set_status(proposal["proposal_id"], "replay-validated")
        entry_id = store.update_known_state(
            f"cell:{proposal['family']}",
            "known_covered",
            {"deployment_id": deployment_id, "validation_id": validation_id, "detail": detail},
            hunt_id=proposal.get("hunt_id"),
            trust_tier="OPERATOR_CONFIRMED",
            deployment_id=deployment_id,
        )
        store.detection_proposal_set_coverage_validation_ref(proposal["proposal_id"], entry_id)
        rationale = f"post-deploy replay passed -- cell {proposal['family']} now KNOWN_COVERED"
    else:
        store.detection_proposal_set_status(proposal["proposal_id"], "replay-failed")
        rationale = "post-deploy replay failed -- cell stays uncovered"
        org_record = {
            "kind": "detection_change",
            "hunt_id": proposal.get("hunt_id"),
            "technique_ids": [proposal["family"]],
            "detection_response": "replay-failed",
            "rationale": detail or rationale,
            "trust_tier": "OPERATOR_CONFIRMED",
            "provenance_class": "operator_assertion",
        }
    _record(
        store,
        hunt_id=proposal.get("hunt_id"),
        actor="system:handoff",
        kind="deploy",
        subject_id=proposal["proposal_id"],
        rationale=rationale,
        data={"deployment_id": deployment_id, "passed": passed, "detail": detail},
    )
    return {
        "proposal_id": proposal["proposal_id"],
        "validation_id": validation_id,
        "passed": passed,
        "status": store.detection_proposal_get(proposal["proposal_id"])["status"],
        "org_record": org_record,
    }


def reject(store: Store, proposal_id: str, *, operator_actor: str, rationale: str) -> dict:
    """Operator reject -> DISPROVED-equivalent for a proposal; rationale is
    mandatory (DB-enforced, `trg_detection_proposal_reject_requires_
    rationale`) and the disposition is ORG-indexed as negative learning
    (DESIGN SS23: 'rejected/revised/expired dispositions feed ORG as
    negative learning'). Only `orchestrator.py` may actually call
    `organ.index_emissions` (MASTER SS3); this returns the record for the
    caller to index."""
    if not operator_actor.startswith("operator:"):
        from .store import OperatorActorRequiredError

        raise OperatorActorRequiredError(
            f"actor {operator_actor!r} is not an operator; handoff.reject requires "
            f"actor='operator:<id>'"
        )
    proposal = store.detection_proposal_get(proposal_id)
    if proposal is None:
        raise ValueError(f"no such detection_proposal: {proposal_id}")
    store.detection_proposal_set_status(proposal_id, "rejected", rationale=rationale)
    _record(
        store,
        hunt_id=proposal.get("hunt_id"),
        actor=operator_actor,
        kind="handoff",
        subject_id=proposal_id,
        rationale=rationale,
        data={"status": "rejected"},
    )
    org_record = {
        "kind": "detection_change",
        "hunt_id": proposal.get("hunt_id"),
        "technique_ids": [proposal["family"]],
        "detection_response": "rejected",
        "rationale": rationale,
        "trust_tier": "OPERATOR_CONFIRMED",
        "provenance_class": "operator_assertion",
    }
    return {"proposal_id": proposal_id, "status": "rejected", "org_record": org_record}
