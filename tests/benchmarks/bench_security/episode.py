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
