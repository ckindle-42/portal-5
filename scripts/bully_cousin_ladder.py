#!/usr/bin/env python3
"""C.6 -- the falsification instrument (TASK_BULLY_COUSIN_RELATION_V1).

Truth by construction: ground truth is *built*, not labelled. Real
`EXTERNAL` anchors are taken from the live attack_data-derived anchor
library and used to construct cousins at known distances (rungs L0-L4).
The report can return INVALID (N5) -- a report that can only produce
numbers is not a verification.

COLD: pure compute over injected/constructed data, no network, no model
calls, no training. (`build_anchor_library` reads attack_data manifests and
the detection-coverage YAML from local disk; it does not need a live
Splunk connection, so this script is network-free.)
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scipy import stats

from portal.modules.security.core.bully import cousin_relation as cr
from portal.modules.security.core.bully import relation as relation_mod
from portal.modules.security.core.bully import signatures as sig_mod
from portal.modules.security.core.bully.data_plane import DataPlane
from scripts.bully_relate_run import build_anchor_library

RHO_MONOTONICITY_FLOOR = 0.9
FAR_ANCHOR_DISTANCE = 0.9  # shared with degeneracy.FAR_ANCHOR_DISTANCE

# Vocabulary for L2 (half-replaced) and L4 (unrelated environment) rungs --
# generic, source-agnostic filler that shares nothing with attack_data
# action vocabulary.
_FILLER_ACTIONS = ["SELECT", "INSERT", "COMMIT", "ROLLBACK", "VACUUM"]
_UNRELATED_TELEMETRY = {"source_class": "db"}
_UNRELATED_CONTEXT = {"engine": "pg"}

# L3 cross-space projection: re-express the parent's behaviour in a
# different source's schema/vocabulary while keeping exactly one rare
# shared motif -- the cousin the old grader structurally could not find.
_CROSS_SPACE_TELEMETRY = {"source_class": "cloudtrail"}
_CROSS_SPACE_CONTEXT = {"cloud": "aws"}
_CROSS_SPACE_FILLER = ["AssumeRole", "GetSessionToken", "ListBuckets", "DescribeInstances"]


def _signature_for(
    action_sequence: list[str],
    telemetry_shape: dict[str, Any],
    context_topology: dict[str, Any],
    *,
    attack_mappings: list[dict[str, str]] | None = None,
) -> Any:
    # target_host is deliberately omitted from episode_view: build_signature
    # injects it into context_topology, which would pollute the context
    # axis with a token no anchor carries and break L0's exact-identity
    # property.
    return sig_mod.build_signature(
        {},
        {
            "action_sequence": action_sequence,
            "telemetry_shape": telemetry_shape,
            "context_topology": context_topology,
            "attack_mappings": attack_mappings or [],
        },
    )


def _rare_motif(parent_actions: list[str]) -> str:
    """The single token this rung's cross-space cousin keeps in common with
    its parent -- the whole point of L3."""
    return parent_actions[0] if parent_actions else "unknown-action"


@dataclass(frozen=True)
class Rung:
    level: int
    name: str
    parent_anchor_id: str
    subject: Any


def build_rungs(anchor: dict[str, Any], *, rung_seed: int) -> list[Rung]:
    """Construct L0-L4 for one parent anchor's action_sequence."""
    parent_id = str(anchor.get("record_id") or anchor.get("signature_id"))
    actions = list(anchor.get("action_sequence") or [])
    telemetry = dict(anchor.get("telemetry_shape") or {})
    context = dict(anchor.get("context_topology") or {})
    rng = random.Random(rung_seed)

    rungs: list[Rung] = []

    # L0 -- identity: the anchor's own behaviour, re-serialized.
    rungs.append(
        Rung(
            0,
            "L0_identity",
            parent_id,
            _signature_for(list(actions), dict(telemetry), dict(context)),
        )
    )

    # L1 -- one-token substitution.
    l1_actions = list(actions)
    if l1_actions:
        idx = rng.randrange(len(l1_actions))
        l1_actions[idx] = f"{l1_actions[idx]}-variant"
    rungs.append(
        Rung(
            1,
            "L1_one_token_substitution",
            parent_id,
            _signature_for(l1_actions, dict(telemetry), dict(context)),
        )
    )

    # L2 -- half the action sequence replaced.
    l2_actions = list(actions)
    half = len(l2_actions) // 2
    for i in range(half):
        l2_actions[i] = _FILLER_ACTIONS[i % len(_FILLER_ACTIONS)]
    rungs.append(
        Rung(
            2,
            "L2_half_replaced",
            parent_id,
            _signature_for(l2_actions, dict(telemetry), dict(context)),
        )
    )

    # L3 -- cross-space projection: a different source's schema/vocabulary,
    # keeping only the rare shared motif.
    motif = _rare_motif(actions)
    l3_actions = [motif, *_CROSS_SPACE_FILLER]
    rungs.append(
        Rung(
            3,
            "L3_cross_space_projection",
            parent_id,
            _signature_for(
                l3_actions,
                dict(_CROSS_SPACE_TELEMETRY),
                dict(_CROSS_SPACE_CONTEXT),
            ),
        )
    )

    # L4 -- unrelated: different behaviour, different environment.
    rungs.append(
        Rung(
            4,
            "L4_unrelated",
            parent_id,
            _signature_for(
                list(_FILLER_ACTIONS),
                dict(_UNRELATED_TELEMETRY),
                dict(_UNRELATED_CONTEXT),
            ),
        )
    )

    return rungs


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    rho, _p = stats.spearmanr(xs, ys)
    if rho != rho:  # NaN guard
        return None
    return float(rho)


def run_ladder(
    anchors: list[dict[str, Any]], *, parents: list[dict[str, Any]], seed: int = 0
) -> dict[str, Any]:
    """Grade every rung of every parent's ladder through the new cousin
    grader. Returns per-parent and aggregate results, plus the negative and
    shuffled-anchor controls."""
    index = cr.build_discriminative_index(anchors)

    rung_records: list[dict[str, Any]] = []
    for parent in parents:
        for rung in build_rungs(parent, rung_seed=seed):
            rel = cr.relate_cousin(rung.subject, anchors, index=index)
            rung_records.append(
                {
                    "parent_anchor_id": rung.parent_anchor_id,
                    "level": rung.level,
                    "name": rung.name,
                    "distance": rel.distance,
                    "status": rel.status,
                    "confidence": rel.confidence,
                    "matched_anchor_id": rel.anchor_id,
                    "ranked_cousins": list(rel.ranked_cousins),
                }
            )

    # Monotonicity: rho between rung level and distance, per parent then
    # averaged, and pooled across all parents.
    per_parent_rho: dict[str, float | None] = {}
    for parent in parents:
        pid = str(parent.get("record_id") or parent.get("signature_id"))
        rows = [
            r for r in rung_records if r["parent_anchor_id"] == pid and r["distance"] is not None
        ]
        levels = [float(r["level"]) for r in rows]
        distances = [float(r["distance"]) for r in rows]
        per_parent_rho[pid] = _spearman(levels, distances)

    valid_rhos = [r for r in per_parent_rho.values() if r is not None]
    pooled_levels = [float(r["level"]) for r in rung_records if r["distance"] is not None]
    pooled_distances = [float(r["distance"]) for r in rung_records if r["distance"] is not None]
    pooled_rho = _spearman(pooled_levels, pooled_distances)
    mean_parent_rho = sum(valid_rhos) / len(valid_rhos) if valid_rhos else None

    # L3 recovery rate: fraction of cross-space cousins whose correct parent
    # is returned as the *nearest* cousin (`ranked_cousins[0]`) -- the raw
    # distance-ranking diagnostic, not `matched_anchor_id`, which N3's
    # overclaim guard deliberately withholds outside a COUSIN_CANDIDATE
    # verdict (a far L3 match can be correctly nearest yet still too far to
    # be *claimed* as a cousin).
    l3_rows = [r for r in rung_records if r["level"] == 3]
    l3_recovered = sum(
        1
        for r in l3_rows
        if r["ranked_cousins"] and r["ranked_cousins"][0][0] == r["parent_anchor_id"]
    )
    l3_recovery_rate = (l3_recovered / len(l3_rows)) if l3_rows else None

    # Negative control: L4 must not be graded COUSIN_CANDIDATE against its
    # own parent.
    l4_rows = [r for r in rung_records if r["level"] == 4]
    l4_violations = [
        r
        for r in l4_rows
        if r["status"] == "COUSIN_CANDIDATE" and r["matched_anchor_id"] == r["parent_anchor_id"]
    ]
    negative_control_holds = not l4_violations

    # Shuffled-anchor control: shuffle the rung-level labels among the
    # pooled (level, distance) pairs and recompute rho -- must collapse
    # toward 0. (Same idiom as measurement.shuffled_label_control: shuffling
    # the label that claims to explain a measurement must destroy any real
    # correlation if the correlation was genuine.)
    rng = random.Random(seed)
    shuffled_levels = list(pooled_levels)
    rng.shuffle(shuffled_levels)
    shuffled_rho = _spearman(shuffled_levels, pooled_distances)

    monotonicity_valid = mean_parent_rho is not None and mean_parent_rho >= RHO_MONOTONICITY_FLOOR
    shuffle_collapsed = shuffled_rho is None or abs(shuffled_rho) < 0.3
    overall_valid = monotonicity_valid and shuffle_collapsed and negative_control_holds

    return {
        "n_parents": len(parents),
        "n_rungs": len(rung_records),
        "per_parent_rho": per_parent_rho,
        "mean_parent_rho": mean_parent_rho,
        "pooled_rho": pooled_rho,
        "monotonicity_floor": RHO_MONOTONICITY_FLOOR,
        "monotonicity_valid": monotonicity_valid,
        "l3_recovery_rate": l3_recovery_rate,
        "l3_recovered": l3_recovered,
        "l3_total": len(l3_rows),
        "negative_control_holds": negative_control_holds,
        "negative_control_violations": l4_violations,
        "shuffled_rho": shuffled_rho,
        "shuffle_collapsed": shuffle_collapsed,
        "valid": overall_valid,
        "rung_records": rung_records,
    }


def run_old_engine_arm(
    anchors: list[dict[str, Any]], *, parents: list[dict[str, Any]]
) -> dict[str, Any]:
    """Run the identical ladder through `relation.relate` (the provoked
    grader, unmodified). Records whatever actually happens -- if the old
    engine recovers L3 cousins, this task's premise is wrong and that must
    be reported, not buried."""
    from portal.modules.security.core.bully.anchors import AnchorLibrary

    lib = AnchorLibrary()
    for record in anchors:
        lib.load_attack_episode(
            source_id=str(record.get("source_id") or "ladder"),
            record=dict(record),
            techniques=tuple(
                m.get("technique_id")
                for m in (record.get("attack_mappings") or [])
                if isinstance(m, dict) and m.get("technique_id")
            ),
        )

    outcome_counts: dict[str, int] = {}
    l0_outcomes: dict[str, int] = {}
    l3_outcomes: dict[str, int] = {}
    l3_total = 0
    l3_recovered = 0
    for parent in parents:
        parent_id = str(parent.get("record_id") or parent.get("signature_id"))
        for rung in build_rungs(parent, rung_seed=0):
            rel = relation_mod.relate(rung.subject, lib, capabilities=None)
            outcome_counts[rel.verdict] = outcome_counts.get(rel.verdict, 0) + 1
            bucket = l0_outcomes if rung.level == 0 else (l3_outcomes if rung.level == 3 else None)
            if bucket is not None:
                bucket[rel.verdict] = bucket.get(rel.verdict, 0) + 1
            if rung.level == 3:
                l3_total += 1
                nearest = rel.nearest_knowns[0][0] if rel.nearest_knowns else None
                if nearest == parent_id:
                    l3_recovered += 1

    total = sum(outcome_counts.values())
    return {
        "outcome_distribution": outcome_counts,
        "l0_identity_outcome_distribution": l0_outcomes,
        "l3_cross_space_outcome_distribution": l3_outcomes,
        "anomalous_unclassified_rate": (
            outcome_counts.get("ANOMALOUS_UNCLASSIFIED", 0) / total if total else None
        ),
        "l3_recovery_rate": (l3_recovered / l3_total) if l3_total else None,
    }


def _select_parents(anchors: list[dict[str, Any]], *, n: int, seed: int) -> list[dict[str, Any]]:
    candidates = [
        a
        for a in anchors
        if a.get("action_sequence") and len(a["action_sequence"]) >= 2 and a.get("attack_mappings")
    ]
    rng = random.Random(seed)
    rng.shuffle(candidates)
    return candidates[:n]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-parents", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("docs/BULLY_COUSIN_LADDER_C6_V1.json"))
    args = parser.parse_args()

    base = Path("/Volumes/data01/portal5_hunt")
    attack_data_root = base / "sources/attack_data/datasets"
    coverage_path = Path("portal/modules/security/core/siem/spl_detections.yaml")

    empty_plane = DataPlane()
    library = build_anchor_library(attack_data_root, coverage_path, empty_plane)
    anchors = library.records(kinds=("attack_episode",))

    parents = _select_parents(anchors, n=args.n_parents, seed=args.seed)

    if not parents:
        payload = {
            "schema": "BULLY_COUSIN_LADDER_C6_V1",
            "valid": False,
            "invalid_reason": "no eligible parent anchors found in the live attack_data library",
        }
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
        print(json.dumps({"valid": False, "output": str(args.output)}))
        return 1

    ladder_report = run_ladder(anchors, parents=parents, seed=args.seed)
    old_engine_report = run_old_engine_arm(anchors, parents=parents)

    # Deliberately break the grader and confirm the report turns INVALID
    # (self-check, not part of the published result).
    orig = cr.relate_cousin

    def _broken_relate_cousin(subject, anchor_records, **kwargs):
        rel = orig(subject, anchor_records, **kwargs)
        import dataclasses

        return dataclasses.replace(rel, distance=0.0 if rel.distance is not None else None)

    cr.relate_cousin = _broken_relate_cousin
    try:
        broken_report = run_ladder(anchors, parents=parents[: min(5, len(parents))], seed=args.seed)
    finally:
        cr.relate_cousin = orig
    self_check_ok = broken_report["valid"] is False

    payload = {
        "schema": "BULLY_COUSIN_LADDER_C6_V1",
        "n_anchors_in_library": len(anchors),
        "ladder": ladder_report,
        "old_engine_arm": old_engine_report,
        "self_check_broken_grader_reports_invalid": self_check_ok,
        "valid": ladder_report["valid"],
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "valid": ladder_report["valid"],
                "mean_parent_rho": ladder_report["mean_parent_rho"],
                "l3_recovery_rate": ladder_report["l3_recovery_rate"],
                "negative_control_holds": ladder_report["negative_control_holds"],
                "shuffled_rho": ladder_report["shuffled_rho"],
                "self_check_broken_grader_reports_invalid": self_check_ok,
                "old_engine_anomalous_unclassified_rate": old_engine_report[
                    "anomalous_unclassified_rate"
                ],
            },
            sort_keys=True,
        )
    )
    return 0 if ladder_report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
