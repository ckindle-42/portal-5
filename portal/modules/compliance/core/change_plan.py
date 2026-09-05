"""Ordered, reviewable implementation plans for proposed compliance changes."""

from __future__ import annotations

import datetime
import uuid


def build(change_package: dict, *, owner: str = "", due_date: str = "") -> dict:
    from portal.modules.compliance.core.runtime import bump

    bump("change_plan")
    target = change_package.get("target_node_id") or change_package.get("start_ref", "unknown")
    due = due_date or (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    steps = [
        ("document", "Draft the controlled document revision"),
        ("control", "Update dependent controls and procedures"),
        ("evidence", "Update evidence specifications and retention instructions"),
        ("training", "Train affected roles before cutover"),
        ("verification", "Reassess every affected obligation and re-resolve citations"),
        ("approval", "Obtain S03 approval for the proposed redline"),
        ("rollback", "Retain the prior revision and documented rollback trigger"),
    ]
    return {
        "plan_id": "plan-" + uuid.uuid4().hex[:12],
        "target": target,
        "owner": owner,
        "owner_gap": not bool(owner),
        "due_date": due,
        "items": [
            {
                "order": index,
                "kind": kind,
                "action": action,
                "depends_on": [index - 1] if index > 1 else [],
                "status": "proposed",
            }
            for index, (kind, action) in enumerate(steps, 1)
        ],
    }
