"""bully.relation_promotion -- bin gates over relation claims
(TASK_BULLY_RELATE_AND_INVESTIGATE_V1 J.2).

Routes a relation's conclusion through the existing, unchanged
promotion.process gate/council machinery (S2: gates test the *claim*, not
the data's pedigree). This module only packages a `Relation` + its subject
signature into the store rows `promotion.process` already expects
(candidate row, recorded signature, recorded cousin assessment, evidence
manifest) -- no gate in `promotion.py` is touched, and nothing here reads
anchor provenance/grade to decide a gate outcome. `origin`/`trust_tier` on
the evidence item are the caller's honest description of where the
evidence came from (an imperfect source is `IMPORTED_UNVERIFIED`, not
`synthetic`) -- G0 only ever gates on `synthetic`, never on trust_tier
value, so an imperfect-but-real source is never denied at G0 for its
pedigree alone.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from ..telemetry import SENSOR_DERIVED
from . import promotion
from .contracts import CousinAssessment
from .store import Store


def submit_relation_claim(
    store: Store,
    relation: Any,
    signature: Any,
    *,
    hunt_id: str,
    candidate_id: str | None = None,
    origin: str = SENSOR_DERIVED,
    trust_tier: str = "",
    synthetic: bool = False,
    gate_inputs: dict[str, dict],
    actor: str = "system:promotion",
    council_review: Any = None,
    soc_deliver: Any = None,
) -> promotion.BinOutcome:
    """Record `relation`'s underlying assessment + evidence and drive the
    resulting candidate through the unchanged bin gate sequence. The
    candidate's fate is decided by `gate_inputs` (the claim's evidence),
    never by `origin`/`trust_tier`/`synthetic` -- those only describe what
    kind of evidence item was recorded, exactly as any other evidence item
    in this system already does."""
    candidate_id = candidate_id or f"cand-{uuid.uuid4().hex[:12]}"
    assessment: CousinAssessment = relation.assessment
    # The nearest anchor is an A.1 anchor_id, not a row in the store's own
    # behavior_signatures table (anchors are not indexed there) -- record
    # the reference as evidence text (below) rather than a dangling FK.
    assessment = dataclasses.replace(assessment, reference_signature_id=None)

    store.record_signature(signature)
    store.record_cousin(assessment)

    manifest_id = f"em-{candidate_id}"
    store.evidence_manifest_put(
        manifest_id=manifest_id,
        episode_id=getattr(signature, "episode_ref", candidate_id),
        required_types=["relation"],
        items=[
            {
                "evidence_id": f"{manifest_id}-item",
                "type": "relation",
                "uri": f"relation://{relation.relation_id}",
                "content_hash": relation.relation_id,
                "synthetic": synthetic,
                "origin": origin,
                "trust_tier": trust_tier,
            }
        ],
        completeness=assessment.completeness,
        reasons=list(relation.uncertainty_reasons),
    )
    store.candidate_create(
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        assessment_id=assessment.assessment_id,
        evidence_manifest_id=manifest_id,
        gate_policy_version=promotion.GATE_POLICY_VERSION,
    )
    return promotion.process(
        store,
        candidate_id,
        actor=actor,
        gate_inputs=gate_inputs,
        cousin_assessment=assessment.to_dict(),
        council_review=council_review,
        soc_deliver=soc_deliver,
    )
