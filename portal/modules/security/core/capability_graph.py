"""Capability Graph + Deterministic Gap Engine + Coverage Map.

Phase 3 of BUILD_PROGRAM_SEC_RBP_V1.  The "what is our actual posture?" readout.

Stable-ID entities (scenario, procedure, detection, episode, gap) with MITRE
technique IDs as a coverage TAG (not the join key).  Deterministic gap
classifier over the multi-axis model.  Coverage map artifact: structured JSON
+ ATT&CK Navigator layer + Markdown heatmap.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# ── Stable-ID entities ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Procedure:
    """A red procedure (attack path) exercised against a target.

    MITRE technique IDs TAG procedures (coverage axis), they are NOT the join
    key.  The join key is the stable procedure_id.
    """

    procedure_id: str  # e.g. "proc-kerberoast_to_da"
    scenario: str  # scenario name from SCENARIOS
    technique_ids: frozenset[str]  # MITRE ATT&CK IDs (tags)
    target_host: str | None = None
    difficulty: str = ""


@dataclass(frozen=True)
class Detection:
    """A blue detection rule (SPL query) that can match a technique."""

    detection_id: str  # e.g. "det-T1190"
    technique_id: str  # primary MITRE technique this detects
    spl: str = ""  # SPL query (may be empty for non-SPL detections)
    description: str = ""
    status: str = "active"  # "active" | "draft" | "disabled"


@dataclass
class Gap:
    """A capability gap — a procedure with insufficient coverage on one or
    more axes."""

    gap_id: str  # e.g. "gap-proc-kerberoast_to_da-T1558.003"
    procedure_id: str
    technique_id: str  # the specific technique with the gap
    axes: dict[str, str]  # {red: code, telemetry: code, detection: code, response: code}
    summary: str  # human summary: COVERED, RED_ONLY, BLUE_ONLY, NEITHER, BLOCKED
    reason_codes: list[str]  # all non-default reason codes
    created_at: float = 0.0


# ── Coverage summary enum ────────────────────────────────────────────────────


class CoverageSummary(str, Enum):  # noqa: UP042 — StrEnum requires 3.11+
    COVERED = "COVERED"  # all four axes satisfied
    RED_ONLY = "RED_ONLY"  # red exercised, no detection
    BLUE_ONLY = "BLUE_ONLY"  # detection exists, not exercised
    NEITHER = "NEITHER"  # neither red nor blue
    BLOCKED = "BLOCKED"  # telemetry or infrastructure failure


# ── Deterministic gap engine ─────────────────────────────────────────────────


def classify_gap(
    red_status: str,
    telemetry_status: str,
    detection_status: str,
    response_status: str = "RESPONSE_NOT_TESTED",
    used_synthetic: bool = False,
) -> str:
    """Deterministic gap classification from episode reason codes.

    Returns a CoverageSummary string.  Pure code — no model input.

    Rules:
    - BLOCKED: telemetry failed or not configured (infrastructure issue)
    - COVERED: red landed + detection confirmed + real telemetry
    - RED_ONLY: red landed but no detection (detection missing or no hit)
    - BLUE_ONLY: detection exists but red never exercised it
    - NEITHER: neither red nor blue exercised
    """
    # Blocked by infrastructure
    if telemetry_status in ("TELEMETRY_COLLECTION_FAILED", "TELEMETRY_NOT_INDEXED"):
        return CoverageSummary.BLOCKED.value

    if telemetry_status == "TELEMETRY_NOT_CONFIGURED" or used_synthetic:
        return CoverageSummary.BLOCKED.value

    # Red exercised?
    red_exercised = red_status == "RED_LANDED"
    red_failed = red_status in ("RED_EXECUTION_FAILED", "RED_TARGET_UNAVAILABLE")

    # Blue detected?
    blue_detected = detection_status == "DETECTION_CONFIRMED"
    blue_has_rule = detection_status not in ("DETECTION_MISSING", "DETECTION_NOT_RUN")

    if red_exercised and blue_detected:
        return CoverageSummary.COVERED.value

    if red_exercised and not blue_detected:
        return CoverageSummary.RED_ONLY.value

    if not red_exercised and blue_has_rule and not red_failed:
        # Detection rule exists but red never ran
        return CoverageSummary.BLUE_ONLY.value

    if red_failed:
        # Red tried but failed — we don't know if blue works
        return CoverageSummary.NEITHER.value

    return CoverageSummary.NEITHER.value


def build_gap(
    procedure: Procedure,
    technique_id: str,
    episode_data: dict[str, Any] | None,
) -> Gap:
    """Build a Gap from a Procedure + technique + optional episode data.

    If episode_data is None, the gap is NEITHER (never exercised).
    """
    if episode_data is None:
        axes = {
            "red": "RED_NOT_RUN",
            "telemetry": "TELEMETRY_NOT_REQUIRED",
            "detection": "DETECTION_NOT_RUN",
            "response": "RESPONSE_NOT_TESTED",
        }
        summary = CoverageSummary.NEITHER.value
        reason_codes = ["RED_NOT_RUN"]
    else:
        axes = {
            "red": episode_data.get("red_status", "RED_NOT_RUN"),
            "telemetry": episode_data.get("telemetry_status", "TELEMETRY_NOT_REQUIRED"),
            "detection": episode_data.get("detection_status", "DETECTION_NOT_RUN"),
            "response": episode_data.get("response_status", "RESPONSE_NOT_TESTED"),
        }
        used_synthetic = episode_data.get("used_synthetic", False)
        summary = classify_gap(
            red_status=axes["red"],
            telemetry_status=axes["telemetry"],
            detection_status=axes["detection"],
            response_status=axes["response"],
            used_synthetic=used_synthetic,
        )
        reason_codes = [
            v
            for v in axes.values()
            if v
            not in (
                "RED_NOT_RUN",
                "TELEMETRY_NOT_REQUIRED",
                "DETECTION_NOT_RUN",
                "RESPONSE_NOT_TESTED",
            )
        ]

    return Gap(
        gap_id=f"gap-{procedure.procedure_id}-{technique_id}",
        procedure_id=procedure.procedure_id,
        technique_id=technique_id,
        axes=axes,
        summary=summary,
        reason_codes=reason_codes,
        created_at=time.time(),
    )


# ── Capability graph ─────────────────────────────────────────────────────────


@dataclass
class CapabilityGraph:
    """The capability graph — procedures, detections, and gaps.

    Seeded from existing assets (SCENARIOS, spl_detections, oracles).
    Updated by episode outcomes.
    """

    procedures: dict[str, Procedure] = field(default_factory=dict)
    detections: dict[str, Detection] = field(default_factory=dict)
    gaps: dict[str, Gap] = field(default_factory=dict)

    def add_procedure(self, proc: Procedure) -> None:
        self.procedures[proc.procedure_id] = proc

    def add_detection(self, det: Detection) -> None:
        self.detections[det.detection_id] = det

    def add_gap(self, gap: Gap) -> None:
        self.gaps[gap.gap_id] = gap

    def techniques_exercised(self) -> set[str]:
        """All MITRE technique IDs exercised by procedures."""
        out: set[str] = set()
        for proc in self.procedures.values():
            out |= proc.technique_ids
        return out

    def techniques_detected(self) -> set[str]:
        """All MITRE technique IDs with a detection rule."""
        return {d.technique_id for d in self.detections.values()}

    def coverage_gaps(self) -> list[Gap]:
        """All gaps that are not COVERED."""
        return [g for g in self.gaps.values() if g.summary != CoverageSummary.COVERED.value]

    def summary_counts(self) -> dict[str, int]:
        """Count of gaps by summary category."""
        counts = {s.value: 0 for s in CoverageSummary}
        for gap in self.gaps.values():
            counts[gap.summary] = counts.get(gap.summary, 0) + 1
        return counts

    def to_dict(self) -> dict:
        """JSON-safe dict."""

        def _proc_dict(p: Procedure) -> dict:
            return {
                "procedure_id": p.procedure_id,
                "scenario": p.scenario,
                "technique_ids": sorted(p.technique_ids),
                "target_host": p.target_host,
                "difficulty": p.difficulty,
            }

        return {
            "procedures": {k: _proc_dict(v) for k, v in self.procedures.items()},
            "detections": {k: asdict(v) for k, v in self.detections.items()},
            "gaps": {k: asdict(v) for k, v in self.gaps.items()},
            "summary": self.summary_counts(),
        }


# ── Graph seeding from existing assets ───────────────────────────────────────


def seed_graph_from_assets() -> CapabilityGraph:
    """Seed the capability graph from existing SCENARIOS + spl_detections.

    This is the initial population — no episodes yet, so all gaps are NEITHER
    or BLUE_ONLY (detection exists but not exercised).
    """
    from .exec_chain import SCENARIOS
    from .siem.spl_detections import techniques_covered

    graph = CapabilityGraph()

    # Seed procedures from scenarios
    for name, scenario in SCENARIOS.items():
        technique_ids = frozenset(scenario.get("detect_ground_truth", []))
        proc = Procedure(
            procedure_id=f"proc-{name}",
            scenario=name,
            technique_ids=technique_ids,
            target_host=scenario.get("target_host"),
            difficulty=scenario.get("difficulty", ""),
        )
        graph.add_procedure(proc)

    # Seed detections from SPL library
    for tid in techniques_covered():
        det = Detection(
            detection_id=f"det-{tid}",
            technique_id=tid,
        )
        graph.add_detection(det)

    # Build initial gaps (all NEITHER — no episodes yet)
    for proc in graph.procedures.values():
        for tid in proc.technique_ids:
            gap = build_gap(proc, technique_id=tid, episode_data=None)
            graph.add_gap(gap)

    return graph


def update_graph_from_episode(graph: CapabilityGraph, episode: dict) -> None:
    """Update the capability graph with an episode outcome.

    Finds the matching procedure by scenario name, then updates gaps for each
    technique in the episode's detect_ground_truth.
    """
    scenario_name = episode.get("scenario", "")
    proc_id = f"proc-{scenario_name}"
    proc = graph.procedures.get(proc_id)
    if not proc:
        return

    for tid in proc.technique_ids:
        gap_id = f"gap-{proc_id}-{tid}"
        # Build a per-technique episode subset (the episode's status applies
        # to all techniques in the scenario's ground truth)
        episode_data = {
            "red_status": episode.get("red_status", "RED_NOT_RUN"),
            "telemetry_status": episode.get("telemetry_status", "TELEMETRY_NOT_REQUIRED"),
            "detection_status": episode.get("detection_status", "DETECTION_NOT_RUN"),
            "response_status": episode.get("response_status", "RESPONSE_NOT_TESTED"),
            "used_synthetic": episode.get("used_synthetic", False),
        }
        gap = build_gap(proc, technique_id=tid, episode_data=episode_data)
        graph.gaps[gap_id] = gap


# ── Coverage map artifacts ───────────────────────────────────────────────────


def generate_coverage_json(graph: CapabilityGraph, *, corpus: set[str] | None = None) -> dict:
    """Generate a structured coverage map as JSON.

    Per-technique four-bar status (Exercise / Telemetry / Detection / Response)
    + the three coverage tiers (Eligible / Strategic / Global denominators).

    `corpus` (D4, DESIGN_EMERGENT_LAB_AGENT_V2): an arbitrary procedure corpus
    — e.g. the technique IDs exercised by an emergent trajectory set — used AS
    the eligible-technique denominator instead of the graph's own accumulated
    exercised|detected set. No new recall formula: `tiers.detected_pct` is the
    exact same math, now scored against the corpus. Omit for the default
    scenario-signature-scoped coverage.
    """
    techniques = (
        set(corpus)
        if corpus is not None
        else (graph.techniques_exercised() | graph.techniques_detected())
    )
    per_technique: dict[str, dict] = {}

    for tid in sorted(techniques):
        # Find all gaps for this technique
        tid_gaps = [g for g in graph.gaps.values() if g.technique_id == tid]
        if not tid_gaps:
            per_technique[tid] = {
                "exercise": "NOT_EXERCISED",
                "telemetry": "NOT_EXERCISED",
                "detection": "NO_RULE",
                "response": "NOT_TESTED",
                "summary": "NEITHER",
            }
            continue

        # Aggregate across all procedures that reference this technique
        # Use the BEST outcome (COVERED > RED_ONLY > BLUE_ONLY > NEITHER > BLOCKED)
        priority = {
            "COVERED": 0,
            "RED_ONLY": 1,
            "BLUE_ONLY": 2,
            "NEITHER": 3,
            "BLOCKED": 4,
        }
        best_gap = min(tid_gaps, key=lambda g: priority.get(g.summary, 5))

        has_detection = any(d.technique_id == tid for d in graph.detections.values())

        per_technique[tid] = {
            "exercise": "EXERCISED"
            if best_gap.axes.get("red") == "RED_LANDED"
            else "NOT_EXERCISED",
            "telemetry": best_gap.axes.get("telemetry", "NOT_REQUIRED"),
            "detection": "CONFIRMED"
            if best_gap.axes.get("detection") == "DETECTION_CONFIRMED"
            else ("RULE_EXISTS" if has_detection else "NO_RULE"),
            "response": best_gap.axes.get("response", "NOT_TESTED"),
            "summary": best_gap.summary,
            "gap_id": best_gap.gap_id,
        }

    # Coverage tiers. exercised/detected are scoped to `techniques` (the
    # eligible set) — a no-op vs the graph's raw counts in the default case
    # (techniques IS that union already) and correct when `corpus` is given
    # (an emergent corpus need not overlap the graph's own accumulated sets).
    eligible = len(techniques)  # all techniques in scope
    exercised = len(techniques & graph.techniques_exercised())
    detected = len(techniques & graph.techniques_detected())

    return {
        "generated_at": time.time(),
        "technique_count": len(techniques),
        "per_technique": per_technique,
        "tiers": {
            "eligible": eligible,
            "exercised": exercised,
            "detected": detected,
            "exercised_pct": round(exercised / eligible * 100, 1) if eligible else 0,
            "detected_pct": round(detected / eligible * 100, 1) if eligible else 0,
        },
        "summary": graph.summary_counts(),
    }


_DOMAIN_TO_MATRIX = {"enterprise-attack": "enterprise", "ics-attack": "ics"}


def _load_technique_matrix() -> dict[str, list[str]]:
    """tid -> matrix list, from spl_detections.yaml's `matrix` dimension (Phase 4
    of TASK-SEC-DESIGN-GAP-DELIVERY-V1). Back-compatible: a technique missing the
    field (or missing from the detection library entirely — e.g. exercised-only,
    no detection rule yet) is treated as `matrix: [enterprise]`, per the schema's
    documented back-compat rule — never as ICS, which would be an unverified claim.
    """
    try:
        import yaml

        path = Path(__file__).resolve().parent / "siem" / "spl_detections.yaml"
        raw = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}
    return {tid: v.get("matrix", ["enterprise"]) for tid, v in raw.items() if isinstance(v, dict)}


def generate_navigator_layer(graph: CapabilityGraph, domain: str = "enterprise-attack") -> dict:
    """Generate an ATT&CK Navigator layer JSON for visualization, for ONE domain.

    Color coding:
    - GREEN (#00FF00): COVERED
    - YELLOW (#FFFF00): RED_ONLY
    - BLUE (#0000FF): BLUE_ONLY
    - RED (#FF0000): NEITHER
    - GRAY (#CCCCCC): BLOCKED

    `domain` selects which matrix's techniques populate the layer — was
    hardcoded to "enterprise-attack" only; now filters by each technique's
    `matrix` tag (Phase 4) so an "ics-attack" layer can also be generated.
    A technique with no matrix tag is treated as enterprise-only (back-compat),
    so it never silently appears in an ICS layer it was never verified against.
    """
    color_map = {
        "COVERED": "#00FF00",
        "RED_ONLY": "#FFFF00",
        "BLUE_ONLY": "#0000FF",
        "NEITHER": "#FF0000",
        "BLOCKED": "#CCCCCC",
    }
    matrix_key = _DOMAIN_TO_MATRIX.get(domain, "enterprise")
    technique_matrix = _load_technique_matrix()

    techniques = graph.techniques_exercised() | graph.techniques_detected()
    techniques = {
        tid for tid in techniques if matrix_key in technique_matrix.get(tid, ["enterprise"])
    }
    scores: list[dict] = []

    for tid in sorted(techniques):
        tid_gaps = [g for g in graph.gaps.values() if g.technique_id == tid]
        if not tid_gaps:
            summary = "NEITHER"
        else:
            priority = {"COVERED": 0, "RED_ONLY": 1, "BLUE_ONLY": 2, "NEITHER": 3, "BLOCKED": 4}
            best = min(tid_gaps, key=lambda g: priority.get(g.summary, 5))
            summary = best.summary

        scores.append(
            {
                "techniqueID": tid,
                "score": {
                    "COVERED": 4,
                    "RED_ONLY": 3,
                    "BLUE_ONLY": 2,
                    "NEITHER": 1,
                    "BLOCKED": 0,
                }.get(summary, 0),
                "color": color_map.get(summary, "#FFFFFF"),
                "comment": summary,
            }
        )

    return {
        "name": "Portal 5 Capability Coverage",
        "versions": {"attack": "15", "navigator": "4.10.0"},
        "domain": domain,
        "description": "Capability coverage map generated from R/B/P episodes",
        "techniques": scores,
    }


def generate_navigator_layers(graph: CapabilityGraph) -> dict[str, dict]:
    """Generate BOTH domain layers — {"enterprise-attack": ..., "ics-attack": ...}.

    The ICS layer is legitimately empty today (0/30 detections currently carry
    matrix: ics — Phase 4 populated NIST/tactic/NERC-CIP mappings but did not
    fabricate ATT&CK-for-ICS technique IDs without an authoritative offline
    source; see TASK-SEC-DESIGN-GAP-DELIVERY-V1 report). An empty ICS layer is
    the honest state, not a bug — the dimension exists and is wired, waiting
    for real ICS-tagged techniques.
    """
    return {
        "enterprise-attack": generate_navigator_layer(graph, domain="enterprise-attack"),
        "ics-attack": generate_navigator_layer(graph, domain="ics-attack"),
    }


def generate_markdown_heatmap(graph: CapabilityGraph) -> str:
    """Generate a Markdown table heatmap of capability coverage."""
    techniques = graph.techniques_exercised() | graph.techniques_detected()
    summary_map = {
        "COVERED": "✅",
        "RED_ONLY": "🟡",
        "BLUE_ONLY": "🔵",
        "NEITHER": "❌",
        "BLOCKED": "⬜",
    }

    lines = [
        "# Capability Coverage Heatmap",
        "",
        "| Technique | Exercise | Telemetry | Detection | Response | Summary |",
        "|-----------|----------|-----------|-----------|----------|---------|",
    ]

    for tid in sorted(techniques):
        tid_gaps = [g for g in graph.gaps.values() if g.technique_id == tid]
        if not tid_gaps:
            lines.append(f"| {tid} | — | — | — | — | ❌ NEITHER |")
            continue

        priority = {"COVERED": 0, "RED_ONLY": 1, "BLUE_ONLY": 2, "NEITHER": 3, "BLOCKED": 4}
        best = min(tid_gaps, key=lambda g: priority.get(g.summary, 5))
        icon = summary_map.get(best.summary, "?")

        lines.append(
            f"| {tid} | {best.axes.get('red', '—')} | "
            f"{best.axes.get('telemetry', '—')} | "
            f"{best.axes.get('detection', '—')} | "
            f"{best.axes.get('response', '—')} | "
            f"{icon} {best.summary} |"
        )

    # Summary row
    counts = graph.summary_counts()
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- **Total techniques:** {len(techniques)}",
            f"- **COVERED:** {counts.get('COVERED', 0)}",
            f"- **RED_ONLY:** {counts.get('RED_ONLY', 0)}",
            f"- **BLUE_ONLY:** {counts.get('BLUE_ONLY', 0)}",
            f"- **NEITHER:** {counts.get('NEITHER', 0)}",
            f"- **BLOCKED:** {counts.get('BLOCKED', 0)}",
        ]
    )

    return "\n".join(lines)
