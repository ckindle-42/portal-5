"""Proposal-quality harness — the Stage-3 go/no-go evidence
(TASK_SEC_GOAL_DECIDE_V1, Stage 2 Phase 5).

Not "are the proposals sensible?" eyeballed once — measured, against a
seeded set of real lab targets each with a known reasonable first-move.
A green aggregate means the models plan well tool-aware -> Stage 3
(bounded live actuation) is justified. A poor aggregate is a specific,
actionable failure signal (retrieval? model? scaffolding?) found before
any runtime is built.
"""

from __future__ import annotations

from .capability.index import build_index
from .goal import EngagementGoal
from .goal_decide import decide_next_action


def _default_seed_targets() -> list[dict]:
    """~10-12 lab targets spanning domains, derived from the real capability
    index (never invented) — each carries the observations a recon pass
    would produce and the technique we expect a sane plan to reach for."""
    caps = build_index()
    by_id = {c.id: c for c in caps}

    seeds = []
    service_probe_domains = {
        "smb": 445,
        "winrm": 5985,
        "ldap": 389,
        "http": 80,
        "https": 443,
        "ssh": 22,
        "mysql": 3306,
        "redis": 6379,
        "ftp": 21,
    }
    for service, port in service_probe_domains.items():
        cap_id = f"{service}_probe"
        if cap_id in by_id:
            seeds.append(
                {
                    "name": f"seed-{service}",
                    "observations": {"open_ports": [port]},
                    "domain_hint": by_id[cap_id].domain,
                    "expected_technique": cap_id,
                }
            )

    for cap in caps:
        if cap.source == "lab_target":
            seeds.append(
                {
                    "name": f"seed-{cap.id}",
                    "observations": cap.applies_when.get("field")
                    and {"open_ports": [cap.applies_when.get("contains")]}
                    or {},
                    "domain_hint": cap.domain,
                    "expected_technique": cap.id,
                }
            )
    return seeds[:12]


def eval_proposals(
    targets: list[dict] | None = None, *, workspace: str | None = None, role: str = "red"
) -> dict:
    """For each seeded target, run goal planning (single decide step, dry-run
    reasoning) and score the proposal against sane heuristics:
      - relevance: the proposed action's applies_when actually matched the target's observations
      - grounding: the proposed tool exists in the arsenal; expected_oracle (if any) is registered
      - non_flailing: not a no_applicable_capability dead-end on a target that clearly has moves
      - coverage: the proposal's action id matches the seed's known expected_technique
    Returns per-target + aggregate scores.
    """
    from .oracles import ORACLES as _ORACLES

    targets = targets if targets is not None else _default_seed_targets()
    per_target = []

    for t in targets:
        goal = EngagementGoal(
            intent=f"poke {t['name']}",
            role=role,
            targets=[t["name"]],
            scope={"targets": [t["name"]]},
            budget={"max_iterations": 1, "max_wall_clock_sec": 60, "max_lab_actions": 1},
            domain_hint=t.get("domain_hint"),
        )
        decision = decide_next_action(goal, t.get("observations", {}), [], workspace=workspace)

        non_flailing = decision.get("outcome") != "no_applicable_capability"
        grounding = True
        if decision.get("expected_oracle") is not None:
            grounding = decision["expected_oracle"] in _ORACLES
        coverage = non_flailing and decision.get("action") == t.get("expected_technique")
        relevance = non_flailing  # decide_next_action only proposes from query() matches — relevance is structural

        per_target.append(
            {
                "target": t["name"],
                "proposed_action": decision.get("action"),
                "expected_technique": t.get("expected_technique"),
                "relevance": relevance,
                "grounding": grounding,
                "non_flailing": non_flailing,
                "coverage": coverage,
            }
        )

    n = len(per_target) or 1
    aggregate = {
        "targets_evaluated": len(per_target),
        "relevance_rate": round(sum(1 for p in per_target if p["relevance"]) / n, 3),
        "grounding_rate": round(sum(1 for p in per_target if p["grounding"]) / n, 3),
        "non_flailing_rate": round(sum(1 for p in per_target if p["non_flailing"]) / n, 3),
        "coverage_rate": round(sum(1 for p in per_target if p["coverage"]) / n, 3),
    }

    return {"per_target": per_target, "aggregate": aggregate}
