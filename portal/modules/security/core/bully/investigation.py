"""bully.investigation -- LOOP's investigation arm, adapting the
`blue_orchestrate.py` section runners (P1.6).

Imported, not forked: `_run_three_section` already IS the multi-round
tool-loop over `spl_backend.query_episode` with per-role budgets and stall
caps built in (MASTER SS3's "multi-round tool-loop ... label-blind,
episode-scoped"). This module's job is narrow -- resolve model ids as
config aliases (never hardcoded), accept a live Episode, run the existing
arm, and apply `blue.py`'s grounding gates
(`_cite_or_drop` / `_discriminator_contradicts`) to the result before
handing it back to LOOP.

Model calls happen only inside this module (+ later adversary.py/
handoff.py/playbooks.py), always through the existing `_call_model`
pattern -- which is exactly what `_run_three_section` already uses
internally; this module never calls a model directly itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_MAX_ROUNDS = 6
DEFAULT_STALL_CAP = 3


@dataclass(frozen=True)
class InvestigationResult:
    verdict: str
    technique_ids: tuple[str, ...]
    grounded_technique_ids: tuple[str, ...]
    dropped_technique_ids: tuple[str, ...]
    contradicted_technique_ids: tuple[str, ...]
    reasoning: str
    match_grade: str
    evidence: tuple[str, ...] = field(default_factory=tuple)


def _render_playbook_directive(instruction_set: dict) -> str:
    """Render a learned playbook's instruction_set (PLAY, I-16) into a short
    directive string. Only the fields DATA_MODEL SS1.15 documents
    (`recall priorities, deciding discriminators, common kills, ... stop
    rules`) are rendered; unknown/empty fields are silently skipped rather
    than fabricated."""
    parts = []
    priorities = instruction_set.get("recall_priorities")
    if priorities:
        parts.append(f"recall priorities: {', '.join(priorities)}")
    discriminators = instruction_set.get("deciding_discriminators")
    if discriminators:
        parts.append(f"deciding discriminators: {', '.join(discriminators)}")
    common_kills = instruction_set.get("common_kills")
    if common_kills:
        parts.append(f"common non-findings to rule out early: {', '.join(common_kills)}")
    stop_rules = instruction_set.get("stop_rules")
    if stop_rules:
        parts.append(f"stop rules: {', '.join(stop_rules)}")
    return "; ".join(parts)


def _apply_playbook_context(episode: Any, playbook: dict | None) -> Any:
    """PLAY injection point (I-16 CONSUMER: LOOP -- 'injection into the
    investigation context'). Absence is neutral: with no active playbook
    for the hunt's scenario_class, the original `episode` is returned
    completely untouched -- the hunt proceeds unshaped, never a fabricated
    default (I-16 FAILURE SEMANTICS).

    A1 (non-obvious choice): `_build_trigger` (blue_orchestrate.py) is the
    only free-text field the model sees before the tool loop starts, built
    from `episode.scenario` + `episode.target_host` + telemetry source
    names -- there is no dedicated "context" field on this Episode
    dataclass to inject into without editing blue_orchestrate.py (out of
    scope, KEEP-SIBLING). So the playbook directive is appended to a
    *copy* of `episode.scenario` (`dataclasses.replace`, original object
    never mutated) -- `episode.techniques` (ground truth) and
    `episode.telemetry` are untouched, so grading is unaffected by
    playbook shaping."""
    if not playbook:
        return episode
    directive = _render_playbook_directive(playbook.get("instruction_set") or {})
    if not directive:
        return episode
    import dataclasses

    return dataclasses.replace(
        episode, scenario=f"{episode.scenario} | LEARNED PLAYBOOK: {directive}"
    )


def _to_acceptance_episode(episode: Any) -> Any:
    """Compatibility adapter from canonical truth Episode to bench reader."""
    if hasattr(episode, "techniques") and hasattr(episode, "telemetry"):
        return episode
    from ..agentic_blue_eval import Episode as AcceptanceEpisode
    from ..chain import SCENARIOS

    scenario = SCENARIOS.get(episode.scenario) or {}
    telemetry: dict[str, list[str]] = {}
    for reference in getattr(episode, "evidence_refs", ()):
        path = Path(reference)
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for sourcetype, lines in (payload.get("telemetry") or {}).items():
            telemetry.setdefault(sourcetype, []).extend(str(line) for line in lines)
    return AcceptanceEpisode(
        scenario=episode.scenario,
        target_host=episode.target_host or "",
        techniques=list(scenario.get("detect_ground_truth") or []),
        telemetry=telemetry,
        captured_at=episode.started_at,
    )


def run_arm(
    episode: Any,
    *,
    models: dict[str, str],
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    wall_clock_s: float | None = None,
    dry_run: bool = False,
    playbook: dict | None = None,
) -> InvestigationResult:
    """Run the investigation arm over a live Episode and apply the
    grounding gates to its own output before returning.

    `models` carries the role-resolved tags this adapter's caller (LOOP,
    P1.7) obtained from `bully.config.resolve_role_model` -- this function
    never resolves or hardcodes a model id itself; it only forwards
    whatever it is handed to `_run_three_section`'s existing `models` dict
    (which expects `{"tool": ..., "reasoning": ..., "expert": ...}`, same
    keys `_run_three_section` already documents).

    `playbook`, when given (LOOP's active playbook for this hunt's
    scenario_class, P6.3), shapes the investigation context via
    `_apply_playbook_context` -- absence (`None`) leaves the episode
    completely unshaped.
    """
    from ..blue import _cite_or_drop, _discriminator_contradicts
    from ..blue_orchestrate import ExpertHandoff, HunterHandoff, _run_three_section

    shaped_episode = _apply_playbook_context(_to_acceptance_episode(episode), playbook)
    result = _run_three_section(
        shaped_episode,
        models=models,
        max_rounds=max_rounds,
        wall_clock_s=wall_clock_s,
        check_additional=False,
        dry_run=dry_run,
    )

    if isinstance(result, (ExpertHandoff, HunterHandoff)):
        # A hand-off object means the arm stopped mid-chain (e.g. captured
        # for replay elsewhere) rather than concluding -- LOOP treats this
        # as UNRESOLVED, never fabricates a verdict from a partial state.
        return InvestigationResult(
            verdict="UNRESOLVED",
            technique_ids=(),
            grounded_technique_ids=(),
            dropped_technique_ids=(),
            contradicted_technique_ids=(),
            reasoning="investigation arm stopped mid-chain (hand-off captured, not a conclusion)",
            match_grade="NONE",
        )

    evidence_blob = " ".join(result.evidence)
    # No per-technique evidence field: OrchestrationResult only exposes a
    # flat evidence list, not a technique->evidence map, so `evidence` is
    # deliberately left unset per reported claim -- setting it to the same
    # shared blob every technique also gets compared against would make
    # _cite_or_drop's rule 1 trivially self-grounding for everything,
    # defeating the gate. Rule 2 (technique ID literally present in the
    # gathered telemetry text) is what actually discriminates here.
    reported = [{"technique_id": tid} for tid in result.technique_ids]
    telemetry = {"gathered": {"telemetry": evidence_blob}}
    grounded = _cite_or_drop(reported, telemetry)
    grounded_ids = {d["technique_id"] for d in grounded}
    dropped_ids = set(result.technique_ids) - grounded_ids

    contradicted = []
    for tid in sorted(grounded_ids):
        contradicts, _tokens = _discriminator_contradicts(tid, evidence_blob)
        if contradicts:
            contradicted.append(tid)
    grounded_ids -= set(contradicted)

    return InvestigationResult(
        verdict=result.verdict,
        technique_ids=tuple(result.technique_ids),
        grounded_technique_ids=tuple(sorted(grounded_ids)),
        dropped_technique_ids=tuple(sorted(dropped_ids)),
        contradicted_technique_ids=tuple(contradicted),
        reasoning=result.reasoning,
        match_grade=result.match_grade,
        evidence=tuple(result.evidence),
    )
