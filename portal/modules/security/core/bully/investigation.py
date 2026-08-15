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

from dataclasses import dataclass, field
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


def run_arm(
    episode: Any,
    *,
    models: dict[str, str],
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    wall_clock_s: float | None = None,
    dry_run: bool = False,
) -> InvestigationResult:
    """Run the investigation arm over a live Episode and apply the
    grounding gates to its own output before returning.

    `models` carries the role-resolved tags this adapter's caller (LOOP,
    P1.7) obtained from `bully.config.resolve_role_model` -- this function
    never resolves or hardcodes a model id itself; it only forwards
    whatever it is handed to `_run_three_section`'s existing `models` dict
    (which expects `{"tool": ..., "reasoning": ..., "expert": ...}`, same
    keys `_run_three_section` already documents).
    """
    from ..blue import _cite_or_drop, _discriminator_contradicts
    from ..blue_orchestrate import ExpertHandoff, HunterHandoff, _run_three_section

    result = _run_three_section(
        episode,
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
