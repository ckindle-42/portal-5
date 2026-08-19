"""bully.compounding -- outcomes become anchors, the compounding loop closes
(TASK_BULLY_RELATE_AND_INVESTIGATE_V1 J.3).

Every investigation outcome -- including `BENIGN_CLOSE` and an analyst
override, not only escalations -- is written back into the anchor library
(S6) with provenance, so a later relation against the same or a similar
neighbourhood retrieves it. This is the compounding claim: the knowledge
grows the anchor library, which makes the next relation better.
"""

from __future__ import annotations

from typing import Any

from . import signatures as sig_mod
from .anchors import Anchor, AnchorLibrary


def write_outcome_as_anchor(
    anchor_library: AnchorLibrary,
    signature: Any,
    *,
    source_id: str,
    outcome: str,
    analyst_confirmed: bool,
    derived_from: tuple[str, ...] = (),
    generation_depth: int = 0,
) -> Anchor:
    """Write one investigation outcome back as a `confirmed_finding` anchor
    (S6). `analyst_confirmed=False` still writes the anchor -- it is just
    graded weak and tiered SYSTEM_GENERATED (A.1), never rejected. Applies
    equally to `BENIGN_CLOSE`, `ESCALATE`, `RESPOND`, and
    `ANOMALOUS_UNCLASSIFIED` outcomes and to an analyst override -- there is
    no outcome kind this function refuses to record."""
    record = dict(sig_mod.reference_record_fields(signature))
    return anchor_library.load_confirmed_finding(
        source_id=source_id,
        record=record,
        outcome=outcome,
        analyst_confirmed=analyst_confirmed,
        derived_from=derived_from,
        generation_depth=generation_depth,
    )


def should_escalate(relation: Any, anchor_library: AnchorLibrary) -> bool:
    """A relation whose nearest match is a `BENIGN_CLOSE` anchor should not
    re-escalate the same neighbourhood (J.3's compounding claim). Any other
    match, or no match at all, defers to the ordinary escalation decision
    (True: nothing here says "don't escalate")."""
    if relation.verdict not in ("SAME", "SIMILAR"):
        return True
    anchor_id = relation.assessment.reference_signature_id
    anchor = anchor_library.get(anchor_id) if anchor_id else None
    return not (
        anchor is not None
        and anchor.kind == "confirmed_finding"
        and anchor.record.get("outcome") == "BENIGN_CLOSE"
    )
