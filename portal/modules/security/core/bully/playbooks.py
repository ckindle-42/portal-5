"""bully.playbooks -- PLAY, the learned-playbook lifecycle (P6.3, I-16).

``draft_update(store, scenario_class, hunt_id)`` distills a completed hunt's
decision-event trajectory into a versioned learned instruction set;
``mark_replay_validated`` / ``run_canary`` advance it through the DRAFT ->
REPLAY_VALIDATED -> CANARY -> AWAITING_OPERATOR lifecycle (auto-reverting to
ROLLED_BACK on a canary failure, cause recorded); ``activate`` is the
confirm-only operator gate that flips it ACTIVE via SUB's atomic pointer CAS
(``store.playbook_activate``); ``for_hunt(store, scenario_class)`` is LOOP's
read path (P6.2 already wired ``investigation.run_arm``'s ``playbook``
kwarg + ``_apply_playbook_context`` -- this module supplies the value).

Reuse, not duplication (MASTER SS1A "reuse the existing playbooks.py
container/validation pattern -- the file stays untouched"): the sibling
``portal/modules/security/core/playbooks.py`` (red-side engagement
playbooks) is a YAML container with a `validate_*` gate before anything is
usable -- this module mirrors that *shape* (a dict container +
`validate_instruction_set` gate before a draft can advance) without
importing or editing that file at all (verified by the boundary import-scan
and by this build never touching that path).

Boundary rules (MASTER SS3): this module never touches SQL directly
(``store.py`` is the sole SQL owner); it is one of the four modules allowed
to make model calls (investigation/adversary/handoff/playbooks) but does
not do so by default -- see A1 below.

A1 (non-obvious choice): `draft_update`'s instruction set is built
*deterministically* from the hunt's own decision-event trajectory (no
model call). I-16 permits PLAY to call a model (it is in the four allowed
model-calling modules) but does not require it -- recall priorities /
deciding discriminators / common kills / stop rules are all things the
hunt's own recorded rationales already state in plain text, so
synthesizing them by extraction is honest and needs no model round-trip. A
future model-assisted draft (e.g. summarizing many hunts at once) is
additive scope, not exercised by any C11 PLAY test.
"""

from __future__ import annotations

from typing import Any

from . import config as bully_config
from .contracts import DecisionEvent, new_id
from .store import OperatorActorRequiredError, Store

_REPLAY_MIN_SUCCESS_RATE = 0.6
_CANARY_MIN_SUCCESS_RATE = 0.6


class PlaybookError(RuntimeError):
    """Raised on an illegal PLAY lifecycle transition."""


def validate_instruction_set(instruction_set: dict) -> list[str]:
    """Mirrors the red-side `playbooks.validate_playbook`'s shape (a list of
    problems, empty == valid) without importing that module -- PLAY's
    container is a JSON instruction_set, not a YAML engagement file, so the
    schema differs, but the "return problems, never raise" contract is the
    same reusable pattern."""
    problems: list[str] = []
    if not isinstance(instruction_set, dict):
        return ["instruction_set must be a dict"]
    has_any_content = any(
        instruction_set.get(k)
        for k in ("recall_priorities", "deciding_discriminators", "common_kills", "stop_rules")
    )
    if not has_any_content:
        problems.append("instruction_set has no recall/discriminator/kill/stop content")
    return problems


def _record(
    store: Store, *, hunt_id: str | None, actor: str, subject_id: str, rationale: str, data: dict
) -> None:
    store.record_decision(
        DecisionEvent(
            event_id=new_id("de"),
            hunt_id=hunt_id,
            iteration_id=None,
            actor=actor,
            kind="playbook",
            subject_id=subject_id,
            rationale=rationale,
            data=data,
        )
    )


def _build_instruction_set(events: list[DecisionEvent]) -> dict[str, Any]:
    recall_priorities = [e.rationale for e in events if e.kind in ("target_select", "recall")]
    deciding_discriminators = [e.rationale for e in events if e.kind == "grade" and e.rationale]
    common_kills = [e.rationale for e in events if e.kind == "kill"]
    stop_rules = [e.rationale for e in events if e.kind in ("objection", "council_block")]
    return {
        "recall_priorities": recall_priorities,
        "deciding_discriminators": deciding_discriminators,
        "common_kills": common_kills,
        "stop_rules": stop_rules,
        "budget_shape": {},
        "fallback": "unshaped",
    }


def draft_update(store: Store, scenario_class: str, hunt_id: str) -> dict[str, Any]:
    """I-16 `draft_update(scenario_class, hunt_record) -> PlaybookDraft`.
    `hunt_id` stands in for `hunt_record` here (SUB's decision_events for
    that hunt *are* its recorded trajectory)."""
    events = store.decision_events_for_hunt(hunt_id)
    instruction_set = _build_instruction_set(events)
    problems = validate_instruction_set(instruction_set)
    content_hash = bully_config.content_hash(
        {"scenario_class": scenario_class, "instruction_set": instruction_set}
    )
    prior = store.playbook_active_for_class(scenario_class)
    playbook_id = new_id("pb")
    version = store.playbook_draft_put(
        playbook_id=playbook_id,
        scenario_class=scenario_class,
        content_hash=content_hash,
        instruction_set=instruction_set,
        source_hunts=[hunt_id],
        supersedes=None,  # supersession only happens at activation (atomic pointer CAS)
    )
    _record(
        store,
        hunt_id=hunt_id,
        actor="system:playbooks",
        subject_id=playbook_id,
        rationale=(
            f"drafted playbook v{version} for {scenario_class}"
            if not problems
            else f"drafted thin playbook v{version} for {scenario_class} ({'; '.join(problems)})"
        ),
        data={"scenario_class": scenario_class, "problems": problems},
    )
    return {
        "playbook_id": playbook_id,
        "scenario_class": scenario_class,
        "version": version,
        "status": "draft",
        "instruction_set": instruction_set,
        "problems": problems,
        "supersedes_active": prior["playbook_id"] if prior else None,
    }


def mark_replay_validated(
    store: Store, playbook_id: str, *, replay_result: dict[str, Any]
) -> dict[str, Any]:
    """DRAFT -> REPLAY_VALIDATED, gated on a replay success rate (injectable
    `replay_result` keeps this hermetic for tests; production callers
    compute it by re-running the source hunts' scenarios against the
    drafted instruction set)."""
    row = store.playbook_get(playbook_id)
    if row is None:
        raise PlaybookError(f"no such playbook: {playbook_id}")
    if row["status"] != "draft":
        raise PlaybookError(f"mark_replay_validated requires status='draft', got {row['status']!r}")
    passed = replay_result.get("success_rate", 0.0) >= _REPLAY_MIN_SUCCESS_RATE
    status = "replay_validated" if passed else "draft"
    store.playbook_set_status(playbook_id, status, replay_results=replay_result)
    _record(
        store,
        hunt_id=None,
        actor="system:playbooks",
        subject_id=playbook_id,
        rationale=f"replay {'passed' if passed else 'failed'}: {replay_result}",
        data={"replay_result": replay_result, "passed": passed},
    )
    return {"playbook_id": playbook_id, "status": status, "passed": passed}


def run_canary(store: Store, playbook_id: str, *, canary_result: dict[str, Any]) -> dict[str, Any]:
    """REPLAY_VALIDATED -> CANARY -> (AWAITING_OPERATOR | ROLLED_BACK).
    I-16 FAILURE SEMANTICS 'canary regression -> reject/rollback': a failing
    canary auto-reverts to `rolled_back` with the cause recorded, never
    silently stays in an ambiguous state."""
    row = store.playbook_get(playbook_id)
    if row is None:
        raise PlaybookError(f"no such playbook: {playbook_id}")
    if row["status"] != "replay_validated":
        raise PlaybookError(f"run_canary requires status='replay_validated', got {row['status']!r}")
    store.playbook_set_status(playbook_id, "canary")
    passed = canary_result.get("success_rate", 0.0) >= _CANARY_MIN_SUCCESS_RATE
    if passed:
        store.playbook_set_status(playbook_id, "awaiting_operator", canary_results=canary_result)
        status = "awaiting_operator"
        cause = None
    else:
        cause = (
            f"canary success_rate={canary_result.get('success_rate', 0.0):.3f} "
            f"below floor {_CANARY_MIN_SUCCESS_RATE}"
        )
        store.playbook_set_status(
            playbook_id, "rolled_back", canary_results=canary_result, revert_cause=cause
        )
        status = "rolled_back"
    _record(
        store,
        hunt_id=None,
        actor="system:playbooks",
        subject_id=playbook_id,
        rationale=cause or "canary passed -- awaiting operator activation",
        data={"canary_result": canary_result, "passed": passed},
    )
    return {"playbook_id": playbook_id, "status": status, "passed": passed, "revert_cause": cause}


def activate(store: Store, draft_id: str, operator_actor: str) -> dict[str, Any]:
    """I-16 `activate(draft_id, operator_actor)`. Confirm-only (`[GATE]`):
    requires status='awaiting_operator' and an operator-prefixed actor --
    the atomic pointer CAS itself (supersede prior active + flip this one)
    is `store.playbook_activate`."""
    row = store.playbook_get(draft_id)
    if row is None:
        raise PlaybookError(f"no such playbook: {draft_id}")
    if row["status"] != "awaiting_operator":
        raise PlaybookError(f"activate requires status='awaiting_operator', got {row['status']!r}")
    if not operator_actor.startswith("operator:"):
        raise OperatorActorRequiredError(
            f"actor {operator_actor!r} is not an operator; playbooks.activate requires "
            f"actor='operator:<id>'"
        )
    store.playbook_activate(draft_id, operator_actor=operator_actor)
    _record(
        store,
        hunt_id=None,
        actor=operator_actor,
        subject_id=draft_id,
        rationale=f"playbook {draft_id} activated for {row['scenario_class']}",
        data={"scenario_class": row["scenario_class"]},
    )
    return {"playbook_id": draft_id, "status": "active"}


def for_hunt(store: Store, scenario_class: str) -> dict[str, Any] | None:
    """I-16 `for_hunt(scenario_class) -> Playbook | None`. LOOP's read path
    (P6.2 wired `investigation.run_arm`'s `playbook` kwarg to accept exactly
    this shape). No active playbook for the class -> `None` -- 'hunt
    proceeds unshaped (absence is neutral, never fabricated)'."""
    return store.playbook_active_for_class(scenario_class)
