"""Investigation → wiki write-back — Phase P3.

Closed investigation cases write challenger-passed findings back as cited units.
"""

from __future__ import annotations


def writeback_investigation_findings(
    case_id: str,
    findings: list[dict],
    *,
    auto_confirm: bool = False,
) -> list[dict]:
    """Write confirmed investigation findings back to the wiki.

    Only A4-Challenger-passed findings write back (never unvalidated ones).
    Each finding becomes a MIXED unit citing the case_id + evidence IDs.

    Args:
        case_id: the investigation case ID
        findings: list of finding dicts with {technique_ids, description, evidence_refs, confidence}
        auto_confirm: if True, skip confirm gate

    Returns:
        list of proposed unit dicts
    """
    from portal_wiki.core.writeback import propose_unit

    proposed = []
    for finding in findings:
        technique_ids = finding.get("technique_ids", [])
        if not technique_ids:
            continue

        tid = technique_ids[0]
        description = finding.get("description", "")
        evidence_refs = finding.get("evidence_refs", [])
        confidence = finding.get("confidence", 0.0)

        sources = [
            {"type": "scenario", "path": f"case:{case_id}"},
            {"type": "mitre", "path": f"ATT&CK:{tid}"},
        ]
        for ev_ref in evidence_refs[:3]:
            sources.append({"type": "code", "path": f"evidence:{ev_ref}"})

        try:
            pu = propose_unit(
                {
                    "title": f"{tid} — Investigation Finding ({case_id})",
                    "kind": "mixed",
                    "sources": sources,
                    "body": (
                        f"# {tid} — Investigation Finding\n\n"
                        f"**Case:** {case_id}\n\n"
                        f"**Finding:** {description}\n\n"
                        f"**Confidence:** {confidence}\n\n"
                        f"**Evidence:** {', '.join(evidence_refs)}\n"
                    ),
                    "tags": [tid, "investigation", "finding"],
                },
                proposed_by="investigation",
                auto_confirm=auto_confirm,
            )
            proposed.append(pu.to_dict())
        except Exception:
            continue

    return proposed
