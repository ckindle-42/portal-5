"""Unknown Defense — defending beyond the known-signature library.

DESIGN-SEC-UNKNOWN-DEFENSE-V1.  Three kinds of unknown, three mechanisms:

U1: Similarity tier — catch known-unknowns (variants) via graded match
U2: Unknown→investigation bridge — route SIMILAR flags to investigation
U3: Baseline generation — model normal behavior
U4: Anomaly-vs-baseline — catch unknown-unknowns via deviation scoring
U5: Anomaly→investigation→write-back — close the loop around novelty
U6: Purple outcome-space expansion — confirmed/variant/anomaly/missed scored distinctly
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# U1 — Similarity Tier (graded match: EXACT / SIMILAR / NONE)
# ═══════════════════════════════════════════════════════════════════════════════


class MatchGrade:
    EXACT = "EXACT"
    SIMILAR = "SIMILAR"
    NONE = "NONE"


@dataclass
class SimilarityResult:
    """Result of similarity matching against the wiki."""

    grade: str  # MatchGrade value
    matched_technique: str = ""  # closest technique ID
    matched_unit_id: str = ""  # wiki unit ID
    overlapping_features: list[str] = field(default_factory=list)
    confidence: float = 0.0
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "grade": self.grade,
            "matched_technique": self.matched_technique,
            "matched_unit_id": self.matched_unit_id,
            "overlapping_features": self.overlapping_features,
            "confidence": self.confidence,
            "detail": self.detail,
        }


def compute_similarity(
    observed_features: dict[str, Any],
    wiki_descriptions: dict[str, str],
) -> SimilarityResult:
    """Compute similarity between observed telemetry features and wiki descriptions.

    U1: Heuristic feature-overlap (explainable, cited) — not embeddings.

    Args:
        observed_features: {tactic, process_names, ports, protocols, payload_family, etc.}
        wiki_descriptions: {technique_id: behavioral_description} from the wiki

    Returns:
        SimilarityResult with EXACT/SIMILAR/NONE grade
    """
    if not wiki_descriptions:
        return SimilarityResult(grade=MatchGrade.NONE, detail="No wiki descriptions available")

    best_score = 0.0
    best_tid = ""
    best_features: list[str] = []

    observed_words = set()
    for v in observed_features.values():
        if isinstance(v, str):
            observed_words.update(v.lower().split())
        elif isinstance(v, list):
            for item in v:
                observed_words.update(str(item).lower().split())

    for tid, desc in wiki_descriptions.items():
        desc_words = set(desc.lower().split())
        overlap = observed_words & desc_words
        if not overlap:
            continue

        # Jaccard-like score weighted by feature specificity
        score = len(overlap) / max(len(observed_words | desc_words), 1)
        if score > best_score:
            best_score = score
            best_tid = tid
            best_features = sorted(overlap)

    if best_score >= 0.5:
        return SimilarityResult(
            grade=MatchGrade.EXACT,
            matched_technique=best_tid,
            overlapping_features=best_features,
            confidence=best_score,
            detail=f"High overlap ({best_score:.2f}) with {best_tid}",
        )
    elif best_score >= 0.15:
        return SimilarityResult(
            grade=MatchGrade.SIMILAR,
            matched_technique=best_tid,
            overlapping_features=best_features,
            confidence=best_score,
            detail=f"Partial overlap ({best_score:.2f}) with {best_tid} — possible variant",
        )
    else:
        return SimilarityResult(
            grade=MatchGrade.NONE,
            detail=f"No significant overlap (best: {best_score:.2f})",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# U2 — Unknown→Investigation Bridge
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class InvestigationIntake:
    """An intake for the investigation layer from a SIMILAR or anomaly flag."""

    intake_id: str
    source: str  # "similarity" | "anomaly"
    alert_text: str
    similarity: SimilarityResult | None = None
    anomaly_score: float = 0.0
    episode_id: str = ""
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "intake_id": self.intake_id,
            "source": self.source,
            "alert_text": self.alert_text,
            "similarity": self.similarity.to_dict() if self.similarity else None,
            "anomaly_score": self.anomaly_score,
            "episode_id": self.episode_id,
            "created_at": self.created_at,
        }


def route_to_investigation(
    similarity: SimilarityResult | None = None,
    anomaly_score: float = 0.0,
    episode_id: str = "",
) -> InvestigationIntake:
    """Route a SIMILAR flag or anomaly to the investigation layer.

    U2: the bridge between detection and reasoning.
    """
    intake_id = f"intake-{int(time.time())}"

    if similarity and similarity.grade == MatchGrade.SIMILAR:
        alert_text = (
            f"Possible variant of {similarity.matched_technique} detected. "
            f"Does not match known signature but shares features: "
            f"{', '.join(similarity.overlapping_features)}. "
            f"Confidence: {similarity.confidence:.2f}. "
            f"Needs investigation to determine if this is a known variant or genuinely novel."
        )
        source = "similarity"
    elif anomaly_score > 0:
        alert_text = (
            f"Anomalous activity detected (score: {anomaly_score:.2f}). "
            f"No matching signature found. Needs investigation to classify."
        )
        source = "anomaly"
    else:
        alert_text = "Unclassified activity requiring investigation."
        source = "unknown"

    return InvestigationIntake(
        intake_id=intake_id,
        source=source,
        alert_text=alert_text,
        similarity=similarity,
        anomaly_score=anomaly_score,
        episode_id=episode_id,
        created_at=time.time(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# U3 — Baseline Generation (model normal behavior)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class BaselineProfile:
    """A profile of normal behavior for a host/service/telemetry-source."""

    profile_id: str  # e.g. "baseline-dc01-windows:security"
    host: str
    sourcetype: str
    normal_processes: dict[str, float] = field(default_factory=dict)  # process → frequency
    normal_event_codes: dict[str, float] = field(default_factory=dict)  # code → frequency
    normal_ports: dict[str, float] = field(default_factory=dict)  # port → frequency
    sample_count: int = 0
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "host": self.host,
            "sourcetype": self.sourcetype,
            "normal_processes": self.normal_processes,
            "normal_event_codes": self.normal_event_codes,
            "normal_ports": self.normal_ports,
            "sample_count": self.sample_count,
            "created_at": self.created_at,
        }


def generate_baseline(
    host: str,
    sourcetype: str,
    benign_events: list[dict],
) -> BaselineProfile:
    """Generate a baseline profile from benign traffic.

    U3: model what "normal" looks like so anomalies can be detected.
    """
    processes: Counter[str] = Counter()
    event_codes: Counter[str] = Counter()
    ports: Counter[str] = Counter()

    for event in benign_events:
        if "NewProcessName" in event:
            processes[event["NewProcessName"]] += 1
        if "EventCode" in event:
            event_codes[str(event["EventCode"])] += 1
        if "port" in event:
            ports[str(event["port"])] += 1

    total = max(len(benign_events), 1)
    return BaselineProfile(
        profile_id=f"baseline-{host}-{sourcetype}",
        host=host,
        sourcetype=sourcetype,
        normal_processes={k: v / total for k, v in processes.items()},
        normal_event_codes={k: v / total for k, v in event_codes.items()},
        normal_ports={k: v / total for k, v in ports.items()},
        sample_count=total,
        created_at=time.time(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# U4 — Anomaly-vs-Baseline (statistical deviation scoring)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class AnomalyResult:
    """Result of anomaly-vs-baseline scoring."""

    score: float  # 0.0 = normal, 1.0 = highly anomalous
    flagged: bool  # True if score exceeds threshold
    deviant_features: list[str] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "flagged": self.flagged,
            "deviant_features": self.deviant_features,
            "detail": self.detail,
        }


def score_anomaly(
    observed: dict[str, Any],
    baseline: BaselineProfile,
    threshold: float = 0.7,
) -> AnomalyResult:
    """Score how anomalous observed telemetry is vs the baseline.

    U4: statistical deviation — technique-agnostic, explainable.
    """
    if baseline.sample_count < 10:
        return AnomalyResult(score=0.0, flagged=False, detail="Insufficient baseline data")

    deviations: list[float] = []
    deviant: list[str] = []

    # Process deviation
    if "NewProcessName" in observed:
        proc = observed["NewProcessName"]
        freq = baseline.normal_processes.get(proc, 0.0)
        if freq == 0.0:
            deviations.append(1.0)
            deviant.append(f"novel_process:{proc}")
        else:
            deviations.append(max(0, 1.0 - freq * 10))  # rare = more anomalous

    # Event code deviation
    if "EventCode" in observed:
        code = str(observed["EventCode"])
        freq = baseline.normal_event_codes.get(code, 0.0)
        if freq == 0.0:
            deviations.append(0.8)
            deviant.append(f"rare_event_code:{code}")

    # Port deviation
    if "port" in observed:
        port = str(observed["port"])
        freq = baseline.normal_ports.get(port, 0.0)
        if freq == 0.0:
            deviations.append(0.6)
            deviant.append(f"novel_port:{port}")

    if not deviations:
        return AnomalyResult(score=0.0, flagged=False, detail="No features to score")

    avg_dev = sum(deviations) / len(deviations)
    return AnomalyResult(
        score=round(avg_dev, 3),
        flagged=avg_dev >= threshold,
        deviant_features=deviant,
        detail=f"Deviation: {avg_dev:.3f} (threshold: {threshold})",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# U5 — Anomaly→Investigation→Write-back
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class InvestigationOutcome:
    """Outcome of investigating an unknown."""

    outcome_id: str
    classification: str  # "variant" | "new_technique" | "benign"
    technique_id: str = ""  # if variant or new
    description: str = ""
    write_back_unit: dict | None = None  # unit to write back to wiki
    baseline_update: bool = False  # if benign, update baseline

    def to_dict(self) -> dict:
        return {
            "outcome_id": self.outcome_id,
            "classification": self.classification,
            "technique_id": self.technique_id,
            "description": self.description,
            "write_back_unit": self.write_back_unit,
            "baseline_update": self.baseline_update,
        }


def resolve_unknown(
    intake: InvestigationIntake,
    investigation_findings: list[dict],
) -> InvestigationOutcome:
    """Resolve an unknown from investigation findings.

    U5: three honest outcomes, all write back.
    """
    outcome_id = f"outcome-{intake.intake_id}-{int(time.time())}"

    if not investigation_findings:
        return InvestigationOutcome(
            outcome_id=outcome_id,
            classification="indeterminate",
            description="Investigation produced no findings",
        )

    # Check if findings point to a known technique
    for finding in investigation_findings:
        tids = finding.get("technique_ids", [])
        if tids:
            return InvestigationOutcome(
                outcome_id=outcome_id,
                classification="variant",
                technique_id=tids[0],
                description=finding.get("description", ""),
                write_back_unit={
                    "title": f"{tids[0]} — Variant (investigation {intake.intake_id})",
                    "kind": "mixed",
                    "sources": [
                        {"type": "scenario", "path": f"intake:{intake.intake_id}"},
                        {"type": "mitre", "path": f"ATT&CK:{tids[0]}"},
                    ],
                    "body": f"# {tids[0]} — Variant\n\n{finding.get('description', '')}",
                    "tags": [tids[0], "variant", "investigation"],
                },
            )

    # No technique match — could be benign or genuinely new
    return InvestigationOutcome(
        outcome_id=outcome_id,
        classification="benign",
        description="No technique match — classified as benign anomaly",
        baseline_update=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# U6 — Purple Outcome-Space Expansion
# ═══════════════════════════════════════════════════════════════════════════════


class PurpleOutcome:
    """Expanded purple outcome space — U6."""

    CONFIRMED = "CONFIRMED"  # exact SPL match, detection confirmed
    VARIANT_FLAGGED = "VARIANT_FLAGGED"  # SIMILAR match, needs review
    ANOMALY_FLAGGED = "ANOMALY_FLAGGED"  # no match, anomalous — investigate
    MISSED = "MISSED"  # red landed, blue silent (the dangerous failure)


@dataclass
class ExpandedPurpleResult:
    """Purple result with expanded outcome space."""

    outcome: str  # PurpleOutcome value
    technique_id: str = ""
    match_grade: str = ""  # MatchGrade value
    anomaly_score: float = 0.0
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "technique_id": self.technique_id,
            "match_grade": self.match_grade,
            "anomaly_score": self.anomaly_score,
            "detail": self.detail,
        }


def score_expanded_purple(
    red_landed: bool,
    match_grade: str,
    anomaly_score: float = 0.0,
    detection_confirmed: bool = False,
) -> ExpandedPurpleResult:
    """Score purple with the expanded outcome space.

    U6: confirmed / variant-flagged / anomaly-flagged / missed — distinctly scored.
    """
    if not red_landed:
        return ExpandedPurpleResult(
            outcome=PurpleOutcome.CONFIRMED if detection_confirmed else PurpleOutcome.MISSED,
            match_grade=match_grade,
            detail="Red did not land — outcome based on detection alone",
        )

    if detection_confirmed and match_grade == MatchGrade.EXACT:
        return ExpandedPurpleResult(
            outcome=PurpleOutcome.CONFIRMED,
            match_grade=match_grade,
            detail="Exact match confirmed",
        )

    if match_grade == MatchGrade.SIMILAR:
        return ExpandedPurpleResult(
            outcome=PurpleOutcome.VARIANT_FLAGGED,
            match_grade=match_grade,
            anomaly_score=anomaly_score,
            detail="Possible variant — needs review",
        )

    if anomaly_score > 0.7:
        return ExpandedPurpleResult(
            outcome=PurpleOutcome.ANOMALY_FLAGGED,
            match_grade=match_grade,
            anomaly_score=anomaly_score,
            detail="Anomalous activity — needs investigation",
        )

    return ExpandedPurpleResult(
        outcome=PurpleOutcome.MISSED,
        match_grade=match_grade,
        detail="Red landed, blue silent — the dangerous failure",
    )
