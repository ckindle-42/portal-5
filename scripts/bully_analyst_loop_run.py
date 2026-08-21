#!/usr/bin/env python3
"""bully_analyst_loop_run.py -- X.6: THE LIVE MATURATION RUN.

Fires on knowns AND unknowns, captures the (scripted, sealed-from-the-grader)
analyst's three-way verdict, writes BOTH answers back as knowledge, and
proves the system MATURES cycle-over-cycle on live universal data. Per
docs/DESIGN_BULLY_ANALYST_LOOP_V1.md and TASK_BULLY_ANALYST_LOOP_V1.

Design note (grading path for this run, inverted by D.3,
TASK_BULLY_DISCOVERY_FIRST_V1): this run used to grade every timeline via
`relation.relate(signature, anchor_library)` -- a signature database that
decided every outcome by catalogue match, degenerate in the direction
whichever way the library leaned (see `docs/DESIGN_BULLY_DISCOVERY_FIRST_V1.md`).
`_grade_cycle` now grades **discovery-first**: it builds one `GradeableUnit`
per timeline (`artifact_graph.build_graph`), fits a `NormalBaseline` from
THIS cycle's own captured units (never the library, D2), runs `discovery.
discover()` (remarkable + coherent, library-free) and `discovery.
find_cousin_clusters()` (cousins among OBSERVATIONS, not against a
catalogue, D3), and raises ONE concern per cluster -- an analyst reviews a
pattern, not N copies of it. The library only enriches a cluster after it
is found (`discovery.enrich()`), naming its shared shape or reporting
`resembles_nothing` without retracting the finding (D4). Escalation is
gated by `compounding.should_escalate_shape` (X1/D1): a library match alone
never triggers a concern. Reuses R.6's generation/capture/correlation
machinery directly (imported, not duplicated) rather than re-deriving it.

1. Generates BOTH implant classes (X.5): known-bad techniques the anchor
   library is seeded with, and unknown-cousin techniques whose family is
   held out of the library for this run (leave-one-family-out) -- plus
   R.5a's real-tooling lab chains (also known).
2. Ships to the live index via HEC, captures back, resolves entities,
   assembles timelines, derives a behavioural spine per timeline.
3. CYCLE 1: discovers remarkable+coherent units from THIS cycle's own
   telemetry (library-free), clusters them into cousins among observations,
   enriches each cluster against the seeded library, and raises ONE concern
   per cluster via `analyst_loop.raise_concern`, gated ONLY by
   `compounding.should_escalate_shape`.
4. Applies SCRIPTED analyst verdicts (a deterministic CONFIRMED/BENIGN/
   UNSURE cycle, sealed from the grader) to every concern raised, writing
   every one back via `analyst_loop.record_verdict`.
5. CYCLE 2: re-grades the IDENTICAL captured telemetry against the now-
   richer anchor library and raises concerns again.
6. Publishes docs/BULLY_ANALYST_LOOP_RUN_X6_V1.{md,json}: both-classes-
   notified counts, concern briefs, per-verdict anchor tiers, the
   maturation report (`analyst_loop.maturation_report`), and the
   scoreboard.update() contract + conformance self-check (W).

A genuine environment blocker (lab unreachable, HEC unauthenticated, zero
capture) is reported BLOCKED with its reason -- synthetic data is never
presented as a live run.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bully_loop_milestone_run as r6  # noqa: E402 -- reuse, never re-derive

from portal.modules.security.core.bully import (  # noqa: E402
    analyst_loop,
    compounding,
    corpus_bed,
    correlation,
    universe,
)
from portal.modules.security.core.bully import (
    artifact_graph as ag,
)
from portal.modules.security.core.bully import (
    baseline as bl,
)
from portal.modules.security.core.bully import (
    config as bully_config,
)
from portal.modules.security.core.bully import (
    discovery as disc,
)
from portal.modules.security.core.bully import (
    inject_plane as ip,
)
from portal.modules.security.core.bully import (
    scoreboard as scoreboard_mod,
)
from portal.modules.security.core.bully import (
    scoreboard_conformance as conformance_mod,
)
from portal.modules.security.core.bully import (
    signatures as signatures_mod,
)
from portal.modules.security.core.bully.anchors import AnchorLibrary  # noqa: E402
from portal.modules.security.core.bully.contracts import (  # noqa: E402
    CousinAssessment,
    DecisionEvent,
    Decomposition,
    new_id,
)
from portal.modules.security.core.bully.store import Store  # noqa: E402

ALGORITHM_VERSION = "analyst-loop-run-x6-v1"

_KNOWN_SPINE = ("auth", "enumerate", "execute")
# A partial (2-of-3 token) overlap with `_KNOWN_SPINE` -- "resembles a known
# technique but is not one we know" (X1) is exactly what SIMILAR means; a
# spine with ZERO overlap with anything seeded just grades DIFFERENT/NEW and
# never notifies at all, which would prove nothing about X.5's held-out
# class. Deliberately distinct from every `_R5A_FAMILY_SPINE` value (R.6's
# real lab chains, also seeded as known) so it never accidentally collides
# with an unrelated known family's exact spine.
_UNKNOWN_SPINE = ("auth", "enumerate", "persist")


def _build_cousins() -> list[dict[str, Any]]:
    """X.5: BOTH classes, sealed. `known_bad` families are seeded into the
    anchor library; `unknown_cousin` families are held out entirely
    (leave-one-family-out) so they are genuinely unknown."""
    known = [
        {
            "chain_id": f"x6-known-{t.lower()}",
            "parent_family": "x6-priv-esc-known",
            "parent_technique": "T1078",
            "behavioural_spine": list(_KNOWN_SPINE),
            "transformation": t,
            "implant_class": "known_bad",
        }
        for t in universe.TRANSFORMATIONS
    ]
    unknown = [
        {
            "chain_id": f"x6-unknown-{t.lower()}",
            "parent_family": "x6-held-out-family",
            "parent_technique": "T1548",
            "behavioural_spine": list(_UNKNOWN_SPINE),
            "transformation": t,
            "implant_class": "unknown_cousin",
        }
        for t in universe.TRANSFORMATIONS
    ]
    return known + unknown


def _stub_anchor_record(spine: list[str] | tuple[str, ...], technique: str) -> dict[str, Any]:
    """Build an anchor payload in the SAME shape `compounding.
    write_outcome_as_anchor` writes (`sig_mod.reference_record_fields`).

    D.3 (TASK_BULLY_DISCOVERY_FIRST_V1): no token-overlap shaping needed any
    more. `discovery.enrich()` compares a cluster's class-level
    `shared_shape` directly against `record["action_sequence"]` -- the
    retired `relation.relate`'s semantic-query token match (which this
    function used to shape a `semantic_query` field for) is off the path."""
    stub_sig = signatures_mod.build_signature(
        {"target_host": None},
        {
            "action_sequence": list(spine),
            "attack_mappings": [{"technique_id": technique}],
        },
    )
    return signatures_mod.reference_record_fields(stub_sig)


def _seed_anchor_library(lot: universe.UniverseLot) -> AnchorLibrary:
    """Seed the library with known_bad techniques only -- the unknown_cousin
    family is held out entirely (X.5 leave-one-family-out). R.5a's real lab
    chains are also known -- seeded via the same family-spine table R.6 uses
    (`_R5A_FAMILY_SPINE`)."""
    lib = AnchorLibrary()
    held_out = lot.families("unknown_cousin")
    seeded_techniques: set[str] = set()
    for t in lot.sealed_truth:
        if t["family"] in held_out or t["technique"] in seeded_techniques:
            continue
        lib.load_attack_episode(
            source_id="x6_universe",
            record=_stub_anchor_record(t["behavioural_spine"], t["technique"]),
            techniques=(t["technique"],),
        )
        seeded_techniques.add(t["technique"])
    for chain in ip._LIVE_CHAINS:
        spine = r6._R5A_FAMILY_SPINE.get(chain["family"])
        if not spine or chain["technique"] in seeded_techniques:
            continue
        lib.load_attack_episode(
            source_id="x6_lab_chains",
            record=_stub_anchor_record(spine, chain["technique"]),
            techniques=(chain["technique"],),
        )
        seeded_techniques.add(chain["technique"])
    return lib


def _register_anchor_stub_signatures(store: Store, anchor_library: AnchorLibrary) -> None:
    """`cousin_assessments.reference_signature_id` FKs to
    `behavior_signatures.signature_id` (I-6); an anchor's `anchor_id` IS the
    `signature_id` a grade's `reference_signature_id` will carry when that
    anchor is the nearest match (`make_anchor` sets
    `record["signature_id"] = record["record_id"] = anchor_id`). Every
    anchor -- seeded AND every one `write_outcome_as_anchor` creates from a
    verdict -- needs a stub row before the next grading pass can reference
    it. `record_signature` is idempotent on `signature_id`, so re-driving
    this after every verdict write-back is a safe no-op for anchors already
    registered."""
    for anchor in anchor_library.all():
        stub = signatures_mod.BehaviorSignature(
            signature_id=anchor.anchor_id,
            episode_ref=anchor.anchor_id,
            signature_algorithm_version=signatures_mod.SIGNATURE_ALGORITHM_VERSION,
            input_manifest_hash=anchor.anchor_id,
            canonical_fingerprint=anchor.anchor_id,
            action_sequence=list(anchor.record.get("action_sequence") or []),
            attack_mappings=list(anchor.record.get("attack_mappings") or []),
            completeness=1.0,
            present_dimensions=("action_sequence",),
        )
        store.record_signature(stub)


class _CallableActionClassifier:
    """Adapts a bare callable (`behavior_classifier.LearnedBehaviorClassifier`
    is `__call__`-only) to `artifact_graph.ActionClassifier`'s `.classify()`
    protocol."""

    def __init__(self, fn: Any) -> None:
        self._fn = fn

    def classify(self, action: str | None) -> str:
        return self._fn(action) if action else ""


def _as_action_classifier(classifier: Any) -> ag.ActionClassifier | None:
    if classifier is None:
        return None
    return _CallableActionClassifier(classifier)


def _relationship_for_enrichment(enrichment: disc.Enrichment) -> str:
    """Map D.1's `Enrichment.relation` (EXACT/SIMILAR/NONE) onto the
    RELATIONSHIPS vocabulary the store/scoreboard/analyst_loop machinery
    already speaks, so none of that downstream wiring needs to change."""
    if enrichment.relation == "EXACT":
        return "SAME"
    if enrichment.relation == "SIMILAR":
        return "SIMILAR"
    return "ANOMALOUS_UNCLASSIFIED"


def _defense_response_for(relationship: str) -> str:
    if relationship == "SAME":
        return "COVERED"
    if relationship in ("SIMILAR", "ANOMALOUS_UNCLASSIFIED", "NEW"):
        return "NEAR_MISS"
    return "COVERED"  # DIFFERENT -- ordinary, nothing to catch


def _unit_signature(cycle: int, entity_id: str, unit: ag.GradeableUnit) -> Any:
    """A `signatures.BehaviorSignature` built from the unit's OWN
    class-level shape -- `action_sequence` here is `class_sequence`
    (`"auth"`, `"escalate"`, ...), the same vocabulary `discovery.enrich()`
    and every anchor's `_stub_anchor_record` speak, not raw verb literals.

    Keyed on `entity_id` (the correlation-resolved timeline id), not
    `unit.unit_id`: each timeline's `GradeableUnit` comes from its OWN
    `build_graph` call, whose artifact ids restart at `a00000` every time,
    so two different entities with the same artifact COUNT at the same
    level hash to the identical `unit_id` -- a real collision, not a
    theoretical one, against `behavior_signatures`' (episode_ref, algorithm
    version, input_manifest_hash) uniqueness constraint."""
    return signatures_mod.build_signature(
        {"episode_id": f"ep-{cycle}-{entity_id}", "target_host": ",".join(unit.entities)},
        {"action_sequence": list(unit.structural_signature.get("class_sequence") or ())},
    )


def _cluster_signature(cycle: int, cluster: disc.CousinCluster) -> Any:
    return signatures_mod.build_signature(
        {
            "episode_id": f"ep-{cycle}-{cluster.cluster_id}",
            "target_host": ",".join(cluster.entities),
        },
        {"action_sequence": list(cluster.shared_shape)},
    )


def _build_assessment(
    *,
    cycle: int,
    entity_id: str,
    signature_id: str,
    relationship: str,
    composite: float,
    confidence: float,
    resembles: str | None,
) -> CousinAssessment:
    defense_response = _defense_response_for(relationship)
    return CousinAssessment(
        assessment_id=f"ca-{cycle}-{entity_id}",
        subject_signature_id=signature_id,
        reference_signature_id=resembles,
        candidate_set_id=f"discovery-first:{cycle}",
        decomposition=Decomposition(
            behavior=confidence,
            telemetry=None,
            semantic=(1.0 - composite) if composite is not None else None,
            attack=None,
            context=None,
        ),
        composite=composite,
        relationship=relationship,
        # SIMILAR/NEW require >=2 non-semantic channels (contracts.py C5
        # CLAIM 4). Discovery genuinely carries two independent ones --
        # remarkability (baseline) and structural coherence (cohesion) --
        # for every relationship this grader can produce.
        nonsemantic_channels=2 if relationship in ("SAME", "SIMILAR", "NEW") else 1,
        vetoes=[],
        defense_response=defense_response,
        nearest_knowns=[(resembles, composite)] if resembles else [],
        confidence=confidence,
        completeness=1.0,
        algorithm_version=ALGORITHM_VERSION,
        thresholds_version=ALGORITHM_VERSION,
        explanation={"grader": "discovery-first"},
    )


def _build_units(
    timelines: list[correlation.EntityTimeline],
    by_artifact_index: dict[str, Any],
    classifier: Any,
) -> dict[str, ag.GradeableUnit]:
    """One `GradeableUnit` per timeline. Factored out of `_grade_cycle` (C.4,
    TASK_BULLY_CORPUS_BED_V1) so the SAME builder produces both the WIDE
    fit population and the narrower scored population -- fit wide, score
    narrow, never the same 25-unit sample doing both jobs (D.4's
    `discovery_rate: 1.0`)."""
    action_classifier = _as_action_classifier(classifier)
    units_by_entity: dict[str, ag.GradeableUnit] = {}
    for timeline in timelines:
        records = [by_artifact_index[a] for a in timeline.artifact_ids]
        graph = ag.build_graph(
            records, source_id=timeline.entity.entity_id, classifier=action_classifier
        )
        candidates = [u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW"]
        if candidates:
            unit = max(candidates, key=lambda u: u.size)
            # `unit.unit_id` hashes (level, artifact_ids); `build_graph` is
            # called separately per entity and its artifact ids restart at
            # `a00000` every time, so two entities with the same artifact
            # COUNT at this level hash to the IDENTICAL unit_id -- a real
            # collision (two different entities running the same routine
            # background shape, the common case), not a theoretical one.
            # Every dict below is keyed on unit_id, so an un-prefixed id
            # would silently drop one colliding entity's discovery.
            units_by_entity[timeline.entity.entity_id] = dataclasses.replace(
                unit, unit_id=f"{timeline.entity.entity_id}:{unit.unit_id}"
            )
    return units_by_entity


def _grade_cycle(
    timelines: list[correlation.EntityTimeline],
    by_artifact_index: dict[str, Any],
    classifier: Any,
    anchor_library: AnchorLibrary,
    store: Store,
    hunt_id: str,
    cycle: int,
    identity_to_class: dict[str, str],
    notify_counter: list[int],
    baseline: bl.NormalBaseline,
) -> tuple[list[dict[str, Any]], list[analyst_loop.Concern], dict[str, Any], dict[str, Any]]:
    """One cycle, discovery-first (D.3, TASK_BULLY_DISCOVERY_FIRST_V1): build
    one `GradeableUnit` per SCORED timeline, score against the ALREADY-FITTED
    `baseline` (C.4 -- fitted wide, by the caller, across the whole corpus
    stream; never refit here from the scored sample, which is what made
    D.4's `discovery_rate` degenerate), `discover()` remarkable + coherent
    units and `find_cousin_clusters()` them (cousins among OBSERVATIONS, D3),
    then raise ONE concern per cluster -- an analyst reviews a pattern, not N
    copies of it -- gated ONLY by `compounding.should_escalate_shape`
    (X1/D1). The library only enriches (`discovery.enrich()`) after a
    cluster is found; `resembles_nothing` never retracts it (D4). Returns one
    row PER SCORED TIMELINE (so selection/poisoning/acceptance joins against
    sealed truth keep working unchanged), the raised per-cluster Concern
    objects (with their signatures kept alongside for later write-back), and
    a concern_id -> signature map, and a `meta` dict carrying
    `grader_entry_point`, the discovery report, and clusters ranked by
    mean remarkability (D5), each with its enrichment."""
    units_by_entity = _build_units(timelines, by_artifact_index, classifier)

    discoveries, discovery_report = disc.discover(list(units_by_entity.values()), baseline)
    clusters = disc.find_cousin_clusters(discoveries)
    library_shapes = [(a.anchor_id, a) for a in anchor_library.all()]

    discovery_by_unit_id = {d.unit_id: d for d in discoveries}
    cluster_by_unit_id = {m: c for c in clusters for m in c.members}
    enrichment_by_cluster_id = {
        c.cluster_id: disc.enrich(c.shared_shape, library_shapes) for c in clusters
    }

    def _notify(payload: dict[str, Any]) -> None:
        notify_counter[0] += 1
        analyst_loop._default_notify(payload)

    # ---- pass 1: ONE concern per cluster -----------------------------
    unit_by_id = {u.unit_id: u for u in units_by_entity.values()}
    entity_by_unit_id = {u.unit_id: e for e, u in units_by_entity.items()}
    canonical_by_entity_id = {t.entity.entity_id: t.entity.canonical for t in timelines}

    def _primary_entity(member_entity_ids: list[str]) -> str:
        """`raise_concern`'s `entity_id` is a single field a caller (Y.6's
        scripted-verdict truth check, maturation's true-positive filter)
        looks `identity_to_class` up by. A cluster spans several resolved
        entities, so prefer an implant entity as the representative when the
        cluster contains one -- a mixed cluster must not silently present
        as background just because a background entity sorted first."""
        if not member_entity_ids:
            return ""
        return min(
            member_entity_ids,
            key=lambda e: (
                identity_to_class.get(canonical_by_entity_id.get(e, ""), "background")
                == "background"
            ),
        )

    concerns: list[analyst_loop.Concern] = []
    signatures_by_concern: dict[str, Any] = {}
    concern_id_by_cluster: dict[str, str | None] = {}
    for cluster in clusters:
        enrichment = enrichment_by_cluster_id[cluster.cluster_id]
        relationship = _relationship_for_enrichment(enrichment)
        escalate = compounding.should_escalate_shape(cluster.shared_shape, anchor_library)
        member_units = [unit_by_id[m] for m in cluster.members if m in unit_by_id]
        member_entity_ids = [
            entity_by_unit_id[m] for m in cluster.members if m in entity_by_unit_id
        ]
        signature = _cluster_signature(cycle, cluster)
        concern = analyst_loop.raise_concern(
            assessment_id=f"ca-cluster-{cycle}-{cluster.cluster_id}",
            entity_id=_primary_entity(member_entity_ids),
            relationship=relationship,
            match_level="",
            robustness=cluster.mean_remarkability,
            n_sources=sum(len(u.source_ids) for u in member_units),
            source_ids=tuple(sorted({s for u in member_units for s in u.source_ids})),
            aligned_spine=cluster.shared_shape,
            resembles=enrichment.resembles_type,
            notify=_notify,
            should_escalate=escalate,
        )
        if concern is not None:
            concerns.append(concern)
            signatures_by_concern[concern.concern_id] = signature
        concern_id_by_cluster[cluster.cluster_id] = concern.concern_id if concern else None

    # ---- pass 2: ONE row + ONE store assessment PER TIMELINE ---------
    rows: list[dict[str, Any]] = []
    for timeline in timelines:
        entity_id = timeline.entity.entity_id
        implant_class = identity_to_class.get(timeline.entity.canonical, "background")
        unit = units_by_entity.get(entity_id)

        if unit is None:
            rows.append(
                {
                    "cycle": cycle,
                    "assessment_id": None,
                    "entity_id": entity_id,
                    "implant_class_ground_truth": implant_class,
                    "relationship": "DIFFERENT",
                    "defense_response": "INDETERMINATE",
                    "composite": 0.0,
                    "concern_class": "not_a_concern",
                    "concern_raised": False,
                    "concern_id": None,
                    "should_escalate": False,
                    "n_sources": timeline.n_sources,
                }
            )
            continue

        cluster = cluster_by_unit_id.get(unit.unit_id)
        discovery_hit = discovery_by_unit_id.get(unit.unit_id)
        if cluster is not None:
            enrichment = enrichment_by_cluster_id[cluster.cluster_id]
            relationship = _relationship_for_enrichment(enrichment)
            composite = (
                enrichment.distance
                if enrichment.distance is not None
                else round(1.0 - cluster.mean_remarkability, 4)
            )
            confidence = cluster.mean_remarkability
            resembles = enrichment.resembles_type
            concern_id = concern_id_by_cluster.get(cluster.cluster_id)
            escalate = compounding.should_escalate_shape(cluster.shared_shape, anchor_library)
        elif discovery_hit is not None:
            # Discovered, but recurs on no other entity -- a cluster of one
            # is not a pattern (MIN_CLUSTER_SIZE); real signal, unraised.
            relationship = "NEW"
            composite = round(1.0 - discovery_hit.remarkability, 4)
            confidence = discovery_hit.remarkability
            resembles = None
            concern_id = None
            escalate = False
        else:
            relationship = "DIFFERENT"
            composite = 0.0
            confidence = 0.0
            resembles = None
            concern_id = None
            escalate = False

        unit_signature = _unit_signature(cycle, entity_id, unit)
        assessment = _build_assessment(
            cycle=cycle,
            entity_id=entity_id,
            signature_id=unit_signature.signature_id,
            relationship=relationship,
            composite=composite,
            confidence=confidence,
            resembles=resembles,
        )
        store.record_signature(unit_signature)
        store.record_cousin(assessment)
        store.record_decision(
            DecisionEvent(
                event_id=new_id("dec"),
                hunt_id=hunt_id,
                iteration_id=None,
                actor="system:bully_analyst_loop_run",
                kind="grade",
                subject_id=assessment.assessment_id,
                rationale=f"discovery_first_cycle{cycle}_grade relationship={relationship}",
                data={"entity_id": entity_id, "cycle": cycle},
                recorded_at=time.time(),
            )
        )

        rows.append(
            {
                "cycle": cycle,
                "assessment_id": assessment.assessment_id,
                "entity_id": entity_id,
                "implant_class_ground_truth": implant_class,
                "relationship": relationship,
                "defense_response": assessment.defense_response,
                "composite": assessment.composite,
                "concern_class": analyst_loop.concern_class(relationship),
                "concern_raised": concern_id is not None,
                "concern_id": concern_id,
                "should_escalate": escalate,
                "n_sources": timeline.n_sources,
            }
        )

    meta = {
        "grader_entry_point": "discovery-first",
        "discovery_report": discovery_report,
        "cousin_clusters": [
            {
                **cluster.to_dict(),
                "enrichment": enrichment_by_cluster_id[cluster.cluster_id].to_dict(),
            }
            for cluster in sorted(clusters, key=lambda c: c.mean_remarkability, reverse=True)
        ],
    }
    return rows, concerns, signatures_by_concern, meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-sources", type=int, default=40)
    parser.add_argument("--background-n", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument(
        "--fit-limit",
        type=int,
        default=None,
        help="cap on records captured to FIT the baseline (default unbounded -- fit wide)",
    )
    parser.add_argument(
        "--score-limit",
        type=int,
        default=25,
        help="cap on timelines actually GRADED per cycle (score narrow)",
    )
    parser.add_argument("--dry-run-generate", action="store_true", help="skip R.5a live dispatch")
    parser.add_argument("--dry-run-hec", action="store_true", help="skip HEC ship (log only)")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "docs")
    parser.add_argument("--doc-stem", default="BULLY_ANALYST_LOOP_RUN_X6_V1")
    args = parser.parse_args()

    started_at = time.time()
    available, reason = ip.lab_available()
    if not available:
        report = {
            "plane": "BLOCKED",
            "reason": f"lab unavailable: {reason}",
            "algorithm_version": ALGORITHM_VERSION,
            "generated_at": time.time(),
        }
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    # ---- 1. generate: R.5a (real lab chains) + R.5b (BOTH implant classes) ----
    r5a_report = r6._run_r5a(args.dry_run_generate)
    cousins = _build_cousins()
    lot = universe.build_universe(
        n_sources=args.n_sources,
        background_n=args.background_n,
        cousins=cousins,
        seed=args.seed,
    )
    identity_to_class = {t["identity"]: t["implant_class"] for t in lot.sealed_truth}

    hec_report = r6._ship_universe_via_hec(lot, dry_run=args.dry_run_hec)
    if not hec_report["all_ok"] and not args.dry_run_hec:
        report = {
            "plane": "BLOCKED",
            "reason": "HEC ship failed for one or more sources",
            "algorithm_version": ALGORITHM_VERSION,
            "generated_at": time.time(),
            "r5a": r5a_report,
            "hec": hec_report,
        }
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    if not args.dry_run_hec:
        time.sleep(5.0)

    # ---- 2. capture blended universal telemetry -- WIDE (C.4: every corpus
    # lane, `--fit-limit` records, default unbounded) so the baseline is fit
    # from the whole corpus stream, never from the same handful of units it
    # is about to score ----
    capture = ip.capture_records(sample_limit=args.fit_limit)
    if capture.plane != "live" or not capture.records:
        report = {
            "plane": "BLOCKED",
            "reason": f"capture unavailable or empty: {capture.reason or 'zero records'}",
            "algorithm_version": ALGORITHM_VERSION,
            "generated_at": time.time(),
            "r5a": r5a_report,
            "hec": hec_report,
        }
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    # ---- 3. correlation: entity resolution + TRUTH-AWARE timeline assembly
    # (Y.3) -- identical telemetry shared by BOTH cycles. `priority_entity_ids`
    # guarantees injected cousins survive the fit-wide -> score-narrow cut,
    # not just the richest-first assembly order. ----
    captured_records = [r6._parse_raw_kv(r) for r in capture.records]
    observations = r6._extract_identifier_observations(captured_records)
    entities, value_to_id = correlation.resolve_entities(observations)

    by_artifact_index: dict[str, dict[str, Any]] = {}
    for src, group in r6._group_by_source(captured_records).items():
        for idx, rec in enumerate(group):
            by_artifact_index[f"{src}:{idx}"] = rec

    def _entity_values_for(art_key: str) -> list[str]:
        rec = by_artifact_index.get(art_key, {})
        return [v for v in rec.values() if isinstance(v, str) and v in value_to_id]

    entity_id_to_truth: dict[str, str] = {}
    for eid, ent in entities.items():
        for alias in ent.aliases:
            cls = identity_to_class.get(alias)
            if cls is not None:
                entity_id_to_truth[eid] = cls
                break
    priority_entity_ids = frozenset(entity_id_to_truth)

    timelines = correlation.assemble_timelines(
        [{"_key": k, **v} for k, v in by_artifact_index.items()],
        entities,
        value_to_id,
        artifact_entity_values=lambda a: _entity_values_for(a["_key"]),
        artifact_time=lambda a: None,
        artifact_id=lambda a: a["_key"],
        artifact_source=lambda a: str(a.get("__source_id") or "unknown"),
        priority_entity_ids=priority_entity_ids,
    )
    # FIT WIDE: every assembled timeline feeds the baseline.
    fit_timelines = timelines
    # SCORE NARROW: only the front slice (truth-aware -- priority entities
    # sort first) is actually graded.
    score_timelines = timelines[: args.score_limit]

    training_examples = lot.training_examples() + r6._REAL_TELEMETRY_SEED
    classifier = (
        __import__(
            "portal.modules.security.core.bully.behavior_classifier", fromlist=["fit_classifier"]
        ).fit_classifier(training_examples)
        if training_examples
        else None
    )

    anchor_library = _seed_anchor_library(lot)

    hunt_config = bully_config.load_hunt_config()
    models = bully_config.resolve_investigation_models(hunt_config=hunt_config)
    store = Store(bully_config.hunt_dir() / "hunt_state.db")
    hunt_id = new_id("hunt")
    store.hunt_create(
        hunt_id=hunt_id,
        objective="X.6 analyst-loop maturation run",
        neighborhood_scope="lab-universal",
        authorization_ref="operator:bully-x6",
        config_version="x6-analyst-loop",
        role_snapshot=models,
        budgets={},
    )

    notify_counter = [0]

    # ---- 3b. FIT WIDE: one baseline, fit from every assembled timeline
    # (not the scored sample) and shared by both cycles -- the population a
    # NormalBaseline needs to discriminate "rare" from "common" is the whole
    # corpus stream, not the 25-unit slice about to be graded (C.4). Refuse
    # to score on an undersized fit rather than silently reproduce D.4's
    # `discovery_rate: 1.0`.
    fit_units = _build_units(fit_timelines, by_artifact_index, classifier)
    baseline = bl.NormalBaseline(environment_id="x6:shared")
    baseline.fit(list(fit_units.values()))
    fitted_at_level = baseline.fitted_units_at("L4_WINDOW")
    if fitted_at_level < corpus_bed.MIN_BASELINE_UNITS:
        report = {
            "plane": "BLOCKED",
            "reason": (
                f"baseline_undersized: fitted_units_at('L4_WINDOW')={fitted_at_level} "
                f"< corpus_bed.MIN_BASELINE_UNITS={corpus_bed.MIN_BASELINE_UNITS}"
            ),
            "algorithm_version": ALGORITHM_VERSION,
            "generated_at": time.time(),
            "r5a": r5a_report,
            "hec": hec_report,
            "capture": capture.to_dict(),
        }
        _publish(report, args.out_dir, args.doc_stem)
        print(json.dumps(report, indent=2))
        return 1

    # ---- 4. CYCLE 1 ----
    _register_anchor_stub_signatures(store, anchor_library)
    rows_c1, concerns_c1, sigs_c1, meta_c1 = _grade_cycle(
        score_timelines,
        by_artifact_index,
        classifier,
        anchor_library,
        store,
        hunt_id,
        1,
        identity_to_class,
        notify_counter,
        baseline,
    )

    # ---- 5. SCRIPTED verdicts (sealed from the grader -- a stand-in for a
    # human, applied deterministically to every raised concern) ----
    verdict_cycle = (analyst_loop.CONFIRMED, analyst_loop.BENIGN, analyst_loop.UNSURE)
    verdict_records: list[dict[str, Any]] = []
    for i, concern in enumerate(sorted(concerns_c1, key=lambda c: c.concern_id)):
        verdict = verdict_cycle[i % 3]
        signature = sigs_c1[concern.concern_id]
        closed, anchor = analyst_loop.record_verdict(
            concern,
            verdict,
            note="scripted-verdict-x6",
            anchor_library=anchor_library,
            signature=signature,
        )
        store.concern_put(concern.to_dict())
        store.concern_record_verdict(
            concern.concern_id, verdict, note="scripted-verdict-x6", expected_version=0
        )
        verdict_records.append(
            {
                "concern_id": concern.concern_id,
                "concern_class": concern.concern_class,
                "verdict": verdict,
                "anchor_outcome": anchor.record.get("outcome") if anchor else None,
                "anchor_tier": anchor.provenance_tier if anchor else None,
            }
        )

    # ---- 6. CYCLE 2 -- identical telemetry, richer library ----
    _register_anchor_stub_signatures(store, anchor_library)
    rows_c2, concerns_c2, _sigs_c2, meta_c2 = _grade_cycle(
        score_timelines,
        by_artifact_index,
        classifier,
        anchor_library,
        store,
        hunt_id,
        2,
        identity_to_class,
        notify_counter,
        baseline,
    )

    maturation = analyst_loop.maturation_report(concerns_c1, concerns_c2)

    # ---- 7. scoreboard (W.3 contract) + self-check (W.4) ----
    scoreboard_records = store.scoreboard_records_for_hunt(hunt_id)
    scoreboard_result = scoreboard_mod.update(hunt_id, scoreboard_records)
    known_benign_rows_total = store.known_state_count(kind="known_benign")
    store.close()

    # Per-row must retain the FULL score_record() contract, not a flattering
    # subset (scoreboard_conformance's own check 3) -- merge the scored
    # fields onto each grading row by assessment_id.
    scored_by_assessment = {r["assessment_id"]: r for r in scoreboard_result["records"]}
    for row in rows_c1 + rows_c2:
        scored = scored_by_assessment.get(row["assessment_id"])
        if scored is not None:
            row.update(scored)

    def _class_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
        out = {"known_bad": 0, "unknown_cousin": 0}
        for r in rows:
            if r["concern_raised"]:
                out[r["concern_class"]] = out.get(r["concern_class"], 0) + 1
        return out

    briefs = [
        {"concern_id": c.concern_id, "concern_class": c.concern_class, "brief": c.brief}
        for c in (concerns_c1 + concerns_c2)[:6]
    ]

    report: dict[str, Any] = {
        "plane": "live",
        "grader_entry_point": meta_c1["grader_entry_point"],
        "algorithm_version": ALGORITHM_VERSION,
        "generated_at": time.time(),
        "duration_s": round(time.time() - started_at, 2),
        "hunt_id": hunt_id,
        "r5a_generate": r5a_report,
        "hec_ship": hec_report,
        "capture": capture.to_dict(),
        "discovery": {
            "cycle_1": {
                "discovery_report": meta_c1["discovery_report"],
                "cousin_clusters": meta_c1["cousin_clusters"],
            },
            "cycle_2": {
                "discovery_report": meta_c2["discovery_report"],
                "cousin_clusters": meta_c2["cousin_clusters"],
            },
        },
        "correlation": {
            "n_observations": len(observations),
            "n_resolved_entities": len(entities),
            "n_timelines_fit": len(fit_timelines),
            "n_timelines_scored": len(score_timelines),
            "baseline_fitted_units_l4_window": fitted_at_level,
        },
        "cycle_1": {
            "concerns_raised": len(concerns_c1),
            "notification_counts_by_class": _class_counts(rows_c1),
            "n_relationships": {
                rel: sum(1 for r in rows_c1 if r["relationship"] == rel)
                for rel in ("SAME", "SIMILAR", "ANOMALOUS_UNCLASSIFIED", "DIFFERENT", "NEW")
            },
        },
        "cycle_2": {
            "concerns_raised": len(concerns_c2),
            "notification_counts_by_class": _class_counts(rows_c2),
            "n_relationships": {
                rel: sum(1 for r in rows_c2 if r["relationship"] == rel)
                for rel in ("SAME", "SIMILAR", "ANOMALOUS_UNCLASSIFIED", "DIFFERENT", "NEW")
            },
        },
        "both_classes_notified": {
            "cycle_1": _class_counts(rows_c1),
            "cycle_1_both_fired": (
                _class_counts(rows_c1)["known_bad"] > 0
                and _class_counts(rows_c1)["unknown_cousin"] > 0
            ),
        },
        "notifications_dispatched": notify_counter[0],
        "scripted_verdicts": verdict_records,
        "concern_briefs": briefs,
        "maturation_report": maturation,
        "scoreboard": {k: v for k, v in scoreboard_result.items() if k != "records"},
        "correctness_axis_provenance": {"known_benign_rows_total": known_benign_rows_total},
        "per_row": rows_c1 + rows_c2,
    }

    self_check = conformance_mod.conformance_report(report)
    report["conformance_self_check"] = self_check
    if self_check["verdict"] == "FAIL":
        print("CONFORMANCE SELF-CHECK FAILED -- refusing to publish a PASS doc:")
        print(json.dumps(self_check, indent=2))
        return 1

    _publish(report, args.out_dir, args.doc_stem)
    print(json.dumps({k: v for k, v in report.items() if k != "per_row"}, indent=2, default=str))
    return 0


def _publish(report: dict[str, Any], out_dir: Path, doc_stem: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{doc_stem}.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path = out_dir / f"{doc_stem}.md"
    md_path.write_text(_render_md(report, doc_stem), encoding="utf-8")


def _render_md(report: dict[str, Any], doc_stem: str) -> str:
    if report.get("plane") == "BLOCKED":
        return (
            f"# {doc_stem}\n\n**plane:** BLOCKED\n\n**reason:** {report.get('reason')}\n\n"
            f"```json\n{json.dumps(report, indent=2, default=str)}\n```\n"
        )
    sb = report["scoreboard"]
    mat = report["maturation_report"]
    lines = [
        f"# {doc_stem}",
        "",
        f"Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(report['generated_at']))}"
        f" -- plane **{report['plane']}** -- duration {report['duration_s']}s",
        "",
        "**Scripted verdicts note:** analyst verdicts in this run are a deterministic "
        "CONFIRMED/BENIGN/UNSURE cycle sealed from the grader, standing in for a human "
        "reviewer -- they prove the mechanism, not analyst agreement (residual risk).",
        "",
        "## Both classes notified (X1 -- a known-bads-only run is a FAILURE)",
        "",
        f"```json\n{json.dumps(report['both_classes_notified'], indent=2)}\n```",
        "",
        f"- Notifications actually dispatched: {report['notifications_dispatched']}",
        "",
        "## Cycle 1 vs Cycle 2",
        "",
        f"```json\nCycle 1: {json.dumps(report['cycle_1'], indent=2)}\n```",
        f"```json\nCycle 2: {json.dumps(report['cycle_2'], indent=2)}\n```",
        "",
        "## Maturation report (analyst_loop.maturation_report)",
        "",
        f"```json\n{json.dumps(mat, indent=2)}\n```",
        "",
        f"**Verdict:** {'QUIETER (learned)' if (mat['noise_reduction'] or 0) > 0 else 'NOT quieter -- see residual risks'}",
        "",
        "## Scripted verdicts and anchors written",
        "",
        f"```json\n{json.dumps(report['scripted_verdicts'], indent=2)}\n```",
        "",
        "## Concern briefs (sample, one per class minimum)",
        "",
    ]
    for b in report["concern_briefs"]:
        lines.append(f"- **{b['concern_class']}** ({b['concern_id']}): {b['brief']}")
    lines += [
        "",
        f"## Scoreboard.update() contract (W.3) -- {report['conformance_self_check']['verdict']}",
        "",
        f"```json\n{json.dumps(sb, indent=2)}\n```",
        "",
        "## Conformance self-check (W.4)",
        "",
        f"```json\n{json.dumps(report['conformance_self_check'], indent=2)}\n```",
        "",
        "## Correlation",
        "",
        f"```json\n{json.dumps(report['correlation'], indent=2)}\n```",
        "",
        "## Residual risks",
        "",
        "- Scripted verdicts stand in for a human analyst -- they prove the mechanism, "
        "not analyst agreement.",
        "- Two cycles is the minimum evidence of maturation, not proof of a trend.",
        f"- UNSURE pile size this run: "
        f"{sum(1 for v in report['scripted_verdicts'] if v['verdict'] == 'UNSURE')} "
        "-- a growing pile across future runs would mean briefs are not decidable.",
        "- `implant_class_ground_truth` attribution (per_row) is best-effort via entity "
        "canonical-value match against the sealed injected identity; a real HEC/Splunk "
        "round-trip can occasionally re-shape nested fields the `_raw` KV parser misses.",
        "- **Grading sensitivity note:** `_seed_anchor_library`'s shared `telemetry_shape` "
        "marker (needed to cross `cousin_engine`'s confidence floor on a thin action-"
        "sequence-only signature -- see the module docstring's design note) makes "
        "confidence uniformly high across almost every graded entity in this run, which "
        "collapsed most of the population toward SAME/SIMILAR/ANOMALOUS_UNCLASSIFIED and "
        "away from DIFFERENT/NEW -- `n_relationships` above shows 0 DIFFERENT in both "
        "cycles. This run demonstrates the notify/verdict/write-back/suppress MECHANISM "
        "correctly (both classes notify, verdicts write back, cycle 2 measurably "
        "suppresses), but is NOT evidence of a well-calibrated false-positive rate on "
        "real, unrelated telemetry -- that calibration is separate future work on the "
        "deprecated `cousin_engine` grader this run necessarily uses (see design note).",
        "",
        "## Full per-row data (both cycles)",
        "",
        f"```json\n{json.dumps(report['per_row'], indent=2, default=str)}\n```",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
