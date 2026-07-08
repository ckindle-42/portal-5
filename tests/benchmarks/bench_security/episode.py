"""Evidence Episode — the immutable correlation substrate for R/B/P capability measurement.

One episode per purple run. Deterministic — no model touches it.

V3 DESIGN §2.3 / TASK_SEC_RBP_STEP0_1_EVIDENCE_GROUNDING_V1 Phase 1.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

# ── Reason-coded status axes (V3 §Reason-coded status axes) ──────────────────
# Deterministic; drive later auto-work.  Each axis is independent.

REASON_CODES: dict[str, list[str]] = {
    "red": [
        "RED_NO_SCENARIO",
        "RED_NOT_RUN",
        "RED_TARGET_UNAVAILABLE",
        "RED_EXECUTION_FAILED",
        "RED_LANDED",
    ],
    "telemetry": [
        "TELEMETRY_NOT_REQUIRED",
        "TELEMETRY_NOT_CONFIGURED",
        "TELEMETRY_COLLECTION_FAILED",
        "TELEMETRY_NOT_INDEXED",
        "TELEMETRY_OBSERVED",
    ],
    "detection": [
        "DETECTION_MISSING",
        "DETECTION_NOT_RUN",
        "DETECTION_NO_HIT",
        "DETECTION_HIT_UNATTRIBUTED",
        "DETECTION_CONFIRMED",
    ],
    "response": [
        "RESPONSE_NOT_TESTED",
        "RESPONSE_MISSING",
        "RESPONSE_RECOMMENDED",
        "RESPONSE_EXECUTED",
        "RESPONSE_EFFECTIVE",
        "RESPONSE_FAILED",
    ],
}

CAPABILITY_VERDICTS = ["PROVEN", "FAILED", "INDETERMINATE", "UNAVAILABLE"]


def new_episode_id(scenario: str) -> str:
    """Generate a unique episode ID: ep-<ISO timestamp>-<scenario>-<short hash>.

    Deterministic given (scenario, time).  No model involvement.
    """
    now = datetime.now(UTC)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    h = hashlib.sha256(f"{scenario}{ts}{time.monotonic_ns()}".encode()).hexdigest()[:8]
    return f"ep-{ts}-{scenario}-{h}"


# ── Episode dataclass ────────────────────────────────────────────────────────


@dataclass
class Episode:
    """Immutable correlation substrate.  One per purple run.

    Every field is set by deterministic code — no model input.
    Serialisable via ``asdict()`` for embedding in result JSON.
    """

    episode_id: str  # ep-YYYYMMDDTHHMMSSZ-<scenario>-<hash>
    scenario: str
    target_host: str | None
    started_at: float  # epoch — window start
    telemetry_cutoff_at: float | None = None  # window end (attack complete + indexing grace)
    red_status: str = "RED_NOT_RUN"
    telemetry_status: str = "TELEMETRY_NOT_REQUIRED"
    detection_status: str = "DETECTION_NOT_RUN"
    response_status: str = "RESPONSE_NOT_TESTED"
    used_synthetic: bool = False
    evidence_refs: list[str] = field(default_factory=list)  # paths/ids of real evidence

    def verdict(self) -> str:
        """Deterministic capability verdict derived only from reason codes.

        Truth plane — code decides, never a model.
        """
        return derive_verdict(self)

    def to_dict(self) -> dict:
        """JSON-safe dict for embedding in result records."""
        return asdict(self)


# ── DetectionCorrelation (Phase 2 — per-technique correlation) ───────────────


@dataclass
class DetectionCorrelation:
    """One record per ground-truth technique (and any reported technique).

    Built by the telemetry fetch path. Consumed by _score_purple to derive
    per-technique detection status.  Serialisable via asdict() for evidence.
    """

    technique_id: str
    # Rule availability (SEC-003 fix — no longer bool(gt))
    has_detection_rule: bool  # spl_for(technique_id) is not None
    spl_variant_ids: list[str] = field(default_factory=list)
    # Hit outcome
    has_spl_hit: bool = False
    row_count: int = 0
    used_synthetic: bool = False
    source: str = ""  # "live" | "synthetic-fallback" | "synthetic"
    # Correlation (SEC-002 fix — no longer hardcoded True)
    within_window: bool = False
    target_match: bool = False
    # Provenance
    query_id: str = ""
    time_bounds: dict = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    # Human-readable rationale for the reason code
    reason: str = ""


def _aggregate_detection_status(per_technique: dict[str, str], gt: set[str]) -> str:
    """Aggregate per-technique detection statuses into a single episode status.

    Conservative aggregation rule:
    1. If any GT technique is DETECTION_CONFIRMED and NONE are
       DETECTION_HIT_UNATTRIBUTED → DETECTION_CONFIRMED
    2. If any GT technique is DETECTION_HIT_UNATTRIBUTED → downgrade
       to DETECTION_HIT_UNATTRIBUTED (never CONFIRMED)
    3. If all GT statuses are DETECTION_MISSING → DETECTION_MISSING
    4. Otherwise → DETECTION_NO_HIT
    """
    gt_statuses = [per_technique.get(tid, "DETECTION_NO_HIT") for tid in gt]

    if not gt_statuses:
        return "DETECTION_NO_HIT"

    has_confirmed = any(s == "DETECTION_CONFIRMED" for s in gt_statuses)
    has_unattributed = any(s == "DETECTION_HIT_UNATTRIBUTED" for s in gt_statuses)
    all_missing = all(s == "DETECTION_MISSING" for s in gt_statuses)

    if all_missing:
        return "DETECTION_MISSING"

    if has_confirmed and not has_unattributed:
        return "DETECTION_CONFIRMED"

    if has_unattributed:
        return "DETECTION_HIT_UNATTRIBUTED"

    if has_confirmed:
        return "DETECTION_CONFIRMED"

    return "DETECTION_NO_HIT"


# ── Deterministic verdict derivation (V3 Edit E2) ────────────────────────────


def derive_verdict(ep: Episode) -> str:
    """Derive a deterministic capability verdict from episode reason codes.

    Rules (V3 §3 / TASK Phase 3):
    - UNAVAILABLE: red never ran / no scenario / target unavailable
    - INDETERMINATE: telemetry failed or not indexed, OR used synthetic data
    - PROVEN: red landed AND detection confirmed (real telemetry, in window, right target)
    - FAILED: red landed but detection missed (no hit or missing detection rule)
    - INDETERMINATE: everything else (partial, ambiguous, response-only, etc.)

    Synthetic telemetry NEVER yields PROVEN — enforced here, not by prompt.
    """
    if ep.red_status in (
        "RED_TARGET_UNAVAILABLE",
        "RED_NOT_RUN",
        "RED_NO_SCENARIO",
    ):
        return "UNAVAILABLE"

    if ep.telemetry_status in (
        "TELEMETRY_COLLECTION_FAILED",
        "TELEMETRY_NOT_INDEXED",
    ):
        return "INDETERMINATE"

    if ep.used_synthetic:
        return "INDETERMINATE"

    if ep.red_status == "RED_LANDED" and ep.detection_status == "DETECTION_CONFIRMED":
        return "PROVEN"

    if ep.red_status == "RED_LANDED" and ep.detection_status in (
        "DETECTION_NO_HIT",
        "DETECTION_MISSING",
    ):
        return "FAILED"

    return "INDETERMINATE"


# ── Detection-status derivation (Phase 2) ────────────────────────────────────


def derive_detection_status(
    *,
    has_spl_hit: bool,
    used_synthetic: bool,
    within_window: bool,
    target_match: bool,
    has_detection_rule: bool,
) -> str:
    """Classify detection status from evidence attributes.  Pure code.

    Returns one of the ``detection`` reason codes:
    - DETECTION_CONFIRMED: real SPL hit + real telemetry + within window + target match
    - DETECTION_NO_HIT: real telemetry, SPL ran, no rows
    - DETECTION_HIT_UNATTRIBUTED: SPL rows but synthetic / outside window / wrong target
    - DETECTION_MISSING: no detection rule for the technique
    """
    if not has_detection_rule:
        return "DETECTION_MISSING"

    if has_spl_hit:
        if used_synthetic or not within_window or not target_match:
            return "DETECTION_HIT_UNATTRIBUTED"
        return "DETECTION_CONFIRMED"

    return "DETECTION_NO_HIT"
