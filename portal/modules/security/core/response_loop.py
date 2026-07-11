"""Response Loop + Threat-Driven Intake.

Phase 7 of BUILD_PROGRAM_SEC_RBP_V1.  Closes the fourth loop (response) and
makes the system stay-current-by-construction.

Three components:
1. Response growth loop: RED_LANDED + DETECTION_CONFIRMED + RESPONSE_MISSING
   → draft a response playbook (deterministic effectiveness check)
2. Reverse growth loop: promoted detection with RED_NO_SCENARIO → draft a
   red scenario (the blue→red direction)
3. Threat-driven intake: new CVE/procedure/report → map against capability
   graph → surface missing exercise/detection/response
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .capability_graph import CapabilityGraph, CoverageSummary

# ── Response playbook draft ──────────────────────────────────────────────────


@dataclass
class ResponsePlaybook:
    """A drafted response playbook for a detected technique."""

    playbook_id: str  # resp-<technique_id>-<scenario>
    technique_id: str
    scenario: str
    actions: list[dict]  # [{action: str, target: str, parameters: dict}]
    status: str = "draft"  # "draft" | "proven" | "confirmed" | "rejected"
    effectiveness: dict = field(default_factory=dict)
    # {tested: bool, red_can_continue: bool, detail: str}
    provenance: dict = field(default_factory=dict)
    created_from_gap: str = ""

    def to_dict(self) -> dict:
        return {
            "playbook_id": self.playbook_id,
            "technique_id": self.technique_id,
            "scenario": self.scenario,
            "actions": self.actions,
            "status": self.status,
            "effectiveness": self.effectiveness,
            "provenance": self.provenance,
        }


# ── Response primitives (from existing playbook actions) ─────────────────────

RESPONSE_PRIMITIVES = {
    "block_ip": {"action": "block_ip", "description": "Block an IP address at the firewall"},
    "disable_account": {
        "action": "disable_account",
        "description": "Disable a compromised account",
    },
    "revoke_tgt": {"action": "revoke_tgt", "description": "Revoke Kerberos TGT tickets"},
    "isolate_host": {"action": "isolate_host", "description": "Isolate a host from the network"},
    "quarantine_file": {"action": "quarantine_file", "description": "Quarantine a malicious file"},
    "reset_password": {"action": "reset_password", "description": "Force password reset"},
}


# ── Response growth loop ─────────────────────────────────────────────────────


def propose_response_playbook(
    technique_id: str,
    scenario: str,
    gap_id: str = "",
) -> ResponsePlaybook:
    """Draft a response playbook for a detected technique.

    RED_LANDED + DETECTION_CONFIRMED + RESPONSE_MISSING → propose response.
    Actions come from existing response primitives (block_ip, disable_account,
    etc.) — not free-generated.
    """
    # Map techniques to appropriate response actions
    technique_responses = {
        "T1190": ["block_ip", "quarantine_file"],
        "T1059": ["isolate_host", "quarantine_file"],
        "T1059.004": ["isolate_host", "quarantine_file"],
        "T1505.003": ["quarantine_file", "isolate_host"],
        "T1003": ["reset_password", "isolate_host"],
        "T1003.001": ["reset_password", "isolate_host"],
        "T1003.003": ["reset_password", "isolate_host"],
        "T1003.006": ["revoke_tgt", "reset_password", "isolate_host"],
        "T1558.003": ["revoke_tgt", "reset_password"],
        "T1558.004": ["revoke_tgt", "reset_password"],
        "T1078": ["disable_account", "reset_password"],
        "T1078.004": ["disable_account", "reset_password"],
        "T1557": ["isolate_host", "reset_password"],
        "T1557.001": ["isolate_host", "reset_password"],
        "T1550.002": ["isolate_host", "reset_password"],
        "T1021.002": ["isolate_host", "disable_account"],
        "T1210": ["isolate_host", "block_ip"],
        "T1053.005": ["isolate_host", "quarantine_file"],
        "T1548.001": ["isolate_host"],
        "T1068": ["isolate_host"],
        "T1047": ["isolate_host"],
        "T1110.003": ["block_ip", "disable_account"],
    }

    action_names = technique_responses.get(technique_id, ["isolate_host"])
    actions = [
        {**RESPONSE_PRIMITIVES[name], "target": scenario}
        for name in action_names
        if name in RESPONSE_PRIMITIVES
    ]

    return ResponsePlaybook(
        playbook_id=f"resp-{technique_id}-{scenario}",
        technique_id=technique_id,
        scenario=scenario,
        actions=actions,
        status="draft",
        provenance={
            "source": "response-gap",
            "created_at": time.time(),
            "gap_id": gap_id,
        },
        created_from_gap=gap_id,
    )


def check_response_effectiveness(
    playbook: ResponsePlaybook,
    red_can_continue: bool,
) -> dict:
    """Check if a response playbook effectively stops the attacker.

    Deterministic: did the response change target state so red can no
    longer continue?
    """
    return {
        "tested": True,
        "red_can_continue": red_can_continue,
        "effective": not red_can_continue,
        "detail": (
            "Response effective — red cannot continue"
            if not red_can_continue
            else "Response ineffective — red can still continue"
        ),
    }


# ── Reverse growth loop (blue→red) ──────────────────────────────────────────


@dataclass
class RedScenarioDraft:
    """A drafted red scenario for a detection with no exercise."""

    draft_id: str  # red-draft-<technique_id>
    technique_id: str
    description: str
    suggested_target: str = ""
    suggested_tools: list[str] = field(default_factory=list)
    status: str = "draft"

    def to_dict(self) -> dict:
        return {
            "draft_id": self.draft_id,
            "technique_id": self.technique_id,
            "description": self.description,
            "suggested_target": self.suggested_target,
            "suggested_tools": self.suggested_tools,
            "status": self.status,
        }


def propose_red_scenario(
    technique_id: str,
    detection_description: str = "",
) -> RedScenarioDraft:
    """Draft a red scenario for a technique that has a detection but no exercise.

    BLUE_ONLY gap → propose red scenario.
    """
    return RedScenarioDraft(
        draft_id=f"red-draft-{technique_id}",
        technique_id=technique_id,
        description=f"Exercise {technique_id} to validate detection: {detection_description}",
    )


# ── Threat-driven intake ─────────────────────────────────────────────────────


@dataclass
class ThreatIntake:
    """Result of mapping a new threat against the capability graph."""

    threat_id: str  # e.g. "CVE-2024-1234" or "T1190-new-variant"
    threat_type: str  # "cve" | "technique" | "report"
    mapped_techniques: list[str] = field(default_factory=list)
    gaps_identified: list[dict] = field(default_factory=list)
    # [{technique_id, gap_type: "exercise"|"detection"|"response", current_status}]
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "threat_id": self.threat_id,
            "threat_type": self.threat_type,
            "mapped_techniques": self.mapped_techniques,
            "gaps_identified": self.gaps_identified,
            "summary": self.summary,
        }


def map_threat_to_gaps(
    graph: CapabilityGraph,
    threat_id: str,
    threat_type: str,
    technique_ids: list[str],
) -> ThreatIntake:
    """Map a new threat (CVE, technique, report) against the capability graph.

    Surfaces missing exercise/detection/response.
    """
    intake = ThreatIntake(
        threat_id=threat_id,
        threat_type=threat_type,
        mapped_techniques=technique_ids,
    )

    for tid in technique_ids:
        # Check if we have a detection
        has_detection = any(d.technique_id == tid for d in graph.detections.values())
        if not has_detection:
            intake.gaps_identified.append(
                {
                    "technique_id": tid,
                    "gap_type": "detection",
                    "current_status": "NO_RULE",
                }
            )

        # Check if we have a scenario
        has_scenario = any(tid in p.technique_ids for p in graph.procedures.values())
        if not has_scenario:
            intake.gaps_identified.append(
                {
                    "technique_id": tid,
                    "gap_type": "exercise",
                    "current_status": "NO_SCENARIO",
                }
            )

    intake.summary = (
        f"Threat {threat_id} maps to {len(technique_ids)} techniques; "
        f"{len(intake.gaps_identified)} gaps identified "
        f"({sum(1 for g in intake.gaps_identified if g['gap_type'] == 'detection')} detection, "
        f"{sum(1 for g in intake.gaps_identified if g['gap_type'] == 'exercise')} exercise)"
    )

    return intake


# ── Response loop runner ─────────────────────────────────────────────────────


@dataclass
class ResponseLoopResult:
    """Result of running the response growth loop."""

    response_gaps_found: int = 0
    playbooks_proposed: int = 0
    playbooks_proven: int = 0
    reverse_gaps_found: int = 0
    red_drafts_proposed: int = 0
    playbooks: list[ResponsePlaybook] = field(default_factory=list)
    red_drafts: list[RedScenarioDraft] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "response_gaps_found": self.response_gaps_found,
            "playbooks_proposed": self.playbooks_proposed,
            "playbooks_proven": self.playbooks_proven,
            "reverse_gaps_found": self.reverse_gaps_found,
            "red_drafts_proposed": self.red_drafts_proposed,
            "summary": self.summary,
        }


def run_response_loop(graph: CapabilityGraph) -> ResponseLoopResult:
    """Run the response growth loop.

    Finds:
    1. COVERED gaps with RESPONSE_MISSING → propose response playbook
    2. BLUE_ONLY gaps → propose red scenario (reverse loop)
    """
    result = ResponseLoopResult()

    for gap in graph.gaps.values():
        # Response loop: COVERED + RESPONSE_MISSING
        if (
            gap.summary == CoverageSummary.COVERED.value
            and gap.axes.get("response") == "RESPONSE_NOT_TESTED"
        ):
            result.response_gaps_found += 1
            playbook = propose_response_playbook(gap.technique_id, gap.procedure_id, gap.gap_id)
            result.playbooks_proposed += 1
            result.playbooks.append(playbook)

        # Reverse loop: BLUE_ONLY (detection exists, not exercised)
        if gap.summary == CoverageSummary.BLUE_ONLY.value:
            result.reverse_gaps_found += 1
            draft = propose_red_scenario(gap.technique_id)
            result.red_drafts_proposed += 1
            result.red_drafts.append(draft)

    result.summary = (
        f"{result.response_gaps_found} response gaps → {result.playbooks_proposed} playbooks; "
        f"{result.reverse_gaps_found} reverse gaps → {result.red_drafts_proposed} red drafts"
    )

    return result
