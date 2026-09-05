"""Derive the asset applicability scope from the operator's own corpus (P4).

``applicability.py``'s docstring asserts asset scope is not derivable from any
document in the corpus. False once the operator's own policies are ingested:
CIP-002 R1 *requires* the entity to identify and categorize its BES Cyber
Systems, and every CIP policy states its applicability in exactly the language
``parse_applicable_systems`` already reads. ``AssetScope.declared_by`` existed
for this from the start — nobody populated it.

Weighting: an explicit applicability statement is strong evidence; the absence
of a corroborating CIP-005/CIP-007 procedure is weak negative evidence and must
**never**, by itself, exclude an impact rating (a missing procedure is exactly
what the coverage matrix exists to surface — using it to narrow scope hides the
gap instead of reporting it). ``has_erc`` / ``has_control_center`` therefore
default to the inclusive ``True`` (the same default ``AssetScope()`` carries)
unless the caller has independent evidence to override.
"""

from __future__ import annotations

import re
import time

from portal.modules.compliance.core import review_queue as rq
from portal.modules.compliance.core.applicability import AssetScope, parse_applicable_systems

_SETTLING_DOC = "the entity's CIP-002 R1 BES Cyber System identification and categorization record"
_IMPACT_CUE = re.compile(r"\b(high|medium|low)\s+impact\b", re.I)


def derive_scope(kb_id: str = "operator_corpus") -> tuple[AssetScope, dict]:
    """Union declared impact ratings and associated types across every
    ingested span that names an impact-rating applicability statement.
    Honest failure: if the corpus does not declare scope, names the document
    that would settle it rather than asking abstractly."""
    from portal.platform.retrieval import store as _store

    ttbl = _store.text_table(kb_id, create=False, prefix="compliance_")
    if ttbl is None:
        return AssetScope(), {
            "declared": False,
            "reason": f"no ingested corpus at kb_id={kb_id!r} — run compliance_ingest first",
            "settling_document": _SETTLING_DOC,
        }

    impacts: set[str] = set()
    associated: set[str] = set()
    evidence: list[dict] = []
    for row in ttbl.to_pandas().to_dict("records"):
        text = row.get("text", "") or ""
        if not _IMPACT_CUE.search(text):
            continue  # a blank-cell default parse carries no new information
        parsed = parse_applicable_systems(text)
        impacts |= parsed["impacts"]
        associated |= parsed["associated"]
        evidence.append(
            {
                "document": row.get("source_file", ""),
                "section": f"chunk {row.get('chunk_index')}",
                "page": row.get("page"),
                "span": text[:300],
            }
        )

    if not impacts:
        return AssetScope(), {
            "declared": False,
            "reason": "no explicit impact-rating applicability language found in the ingested corpus",
            "settling_document": _SETTLING_DOC,
        }

    scope = AssetScope(
        impact_present=impacts,
        associated_present=associated or {"bcs"},
        # P3/F07: unconfirmed, not an inclusive-True default — `has_erc=True`
        # here previously meant "assume ERC present," which is a positive
        # claim about the entity's network, not "absence of evidence never
        # excludes." Unconfirmed is honestly unknown (see
        # `AssetScope.is_confirmed` / `applicability_state`).
        has_erc=None,
        has_control_center=None,
        declared_by="derived:corpus",
        declared_at=time.strftime("%Y-%m-%d"),
    )
    item = rq.propose(
        "applicability_scope",
        subject_id="entity",
        proposed_value={
            "impact_present": sorted(impacts),
            "associated_present": sorted(scope.associated_present),
            "has_erc": scope.has_erc,
            "has_control_center": scope.has_control_center,
        },
        evidence=evidence[:25],
        confidence=0.7 if len(evidence) >= 3 else 0.4,
    )
    return scope, {
        "declared": True,
        "queue_item_id": item.id,
        "n_citing_spans": len(evidence),
        "note": "has_erc/has_control_center default True (inclusive) — the corpus was not "
        "searched for a negative declaration; confirm or correct via compliance_review_decide",
    }
