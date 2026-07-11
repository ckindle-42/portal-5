"""Canonical telemetry contracts — unified backend protocol + health + provenance.

Phase 2 of BUILD_PROGRAM_SEC_RBP_V1.  Replaces the dual-backend seam
(blue.py's SplunkBackend/WinEventBackend protocol vs matrix.py's WazuhBackend
protocol) with one canonical TelemetryBackend, a TelemetryContract describing
each source, and TelemetryHealth pre-checks.

Every telemetry fetch attaches its contract id + data_as_of timestamp to the
evidence it produces — provenance is structural, not accidental.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# ── Canonical TelemetryBackend protocol ──────────────────────────────────────


@runtime_checkable
class TelemetryBackend(Protocol):
    """Backend-agnostic telemetry query interface.

    The single canonical protocol.  All backend implementations
    (SplunkBackend, WinEventBackend, WazuhBackend) conform to this.
    blue.py, matrix.py, and any future module import from here.
    """

    name: str

    def query(self, technique_id: str, window: dict) -> dict:
        """Query telemetry for a technique within a time window.

        Returns:
            {
                "telemetry": str,      # raw telemetry text (may be empty)
                "source": str,         # "live" | "synthetic-fallback" | "synthetic"
                "backend": str,        # backend name (self.name)
            }
        """
        ...


# ── TelemetryContract — describes a telemetry source ─────────────────────────


@dataclass
class TelemetryContract:
    """Describes a telemetry source: what it provides, what it requires, and
    how to verify it's healthy.

    Contracts are versioned, deterministic, and map to episode reason codes.
    """

    id: str  # e.g. "splunk-web", "winevent-ad", "wazuh-alerts"
    platform: str  # "splunk" | "winevent" | "wazuh" | "custom"
    channel: str  # "web:access" | "windows:security" | "wazuh:alerts" | ...
    backend_name: str  # matches TelemetryBackend.name

    # What the source needs to produce data
    requirements: dict = field(default_factory=dict)
    # e.g. {"audit_policy": "ProcessCreation", "sourcetype": "web:access"}

    # What events/fields the detection library expects from this source
    signal: dict = field(default_factory=dict)
    # e.g. {"event_codes": [4688], "required_fields": ["EventCode", "NewProcessName"]}

    # Health check parameters
    freshness_query: str = ""  # SPL/Lucene/PowerShell to verify source is flowing
    freshness_timeout_s: int = 30
    minimum_events: int = 1  # minimum hits to consider "healthy"

    # Latency expectations
    expected_max_index_delay_s: int = 120  # max time from event to queryable

    # Provenance
    schema_version: int = 1

    def to_dict(self) -> dict:
        """JSON-safe dict for embedding in evidence records."""
        return {
            "id": self.id,
            "platform": self.platform,
            "channel": self.channel,
            "backend_name": self.backend_name,
            "requirements": self.requirements,
            "signal": self.signal,
            "schema_version": self.schema_version,
        }


# ── TelemetryHealth — pre-check that a source is flowing ────────────────────


@dataclass
class TelemetryHealthResult:
    """Result of a TelemetryHealth pre-check."""

    contract_id: str
    healthy: bool
    reason_code: str  # "TELEMETRY_OBSERVED" | "TELEMETRY_NOT_CONFIGURED" | ...
    event_count: int = 0
    checked_at: float = 0.0
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "contract_id": self.contract_id,
            "healthy": self.healthy,
            "reason_code": self.reason_code,
            "event_count": self.event_count,
            "checked_at": self.checked_at,
            "detail": self.detail,
        }


def check_source_health(
    contract: TelemetryContract,
    backend: TelemetryBackend,
    window: dict | None = None,
) -> TelemetryHealthResult:
    """Pre-check that a telemetry source is actually flowing BEFORE a
    detection runs.

    A dead source → reason code on the episode, NOT a silent skip and NOT a
    detection gap.  This is the TelemetryHealth gate the design requires.

    Args:
        contract: the TelemetryContract describing the source
        backend: the TelemetryBackend to query
        window: optional time window dict (earliest/latest)

    Returns:
        TelemetryHealthResult with healthy=True/False and the appropriate
        reason code for the episode's telemetry_status.
    """
    check_window = window or {"earliest": "-15m", "latest": "now"}
    t0 = time.time()

    try:
        result = backend.query(contract.id, check_window)
    except Exception as exc:
        return TelemetryHealthResult(
            contract_id=contract.id,
            healthy=False,
            reason_code="TELEMETRY_COLLECTION_FAILED",
            checked_at=t0,
            detail=f"backend.query raised: {exc}",
        )

    telemetry_text = result.get("telemetry", "")
    source_tag = result.get("source", "")

    # Source returned nothing or synthetic-only
    if not telemetry_text.strip():
        return TelemetryHealthResult(
            contract_id=contract.id,
            healthy=False,
            reason_code="TELEMETRY_NOT_CONFIGURED",
            checked_at=t0,
            detail="backend returned empty telemetry",
        )

    if source_tag in ("synthetic-fallback", "synthetic"):
        return TelemetryHealthResult(
            contract_id=contract.id,
            healthy=False,
            reason_code="TELEMETRY_NOT_CONFIGURED",
            checked_at=t0,
            detail=f"source tagged as {source_tag}",
        )

    # Source returned real data
    return TelemetryHealthResult(
        contract_id=contract.id,
        healthy=True,
        reason_code="TELEMETRY_OBSERVED",
        event_count=max(1, telemetry_text.count("\n") + 1),
        checked_at=t0,
        detail=f"source={source_tag}, backend={result.get('backend', 'unknown')}",
    )


# ── Well-known contracts (built from the current backends) ───────────────────

CONTRACT_SPLUNK_WEB = TelemetryContract(
    id="splunk-web",
    platform="splunk",
    channel="web:access",
    backend_name="splunk",
    requirements={"sourcetype": "web:access"},
    signal={"required_fields": ["source", "sourcetype"]},
)

CONTRACT_WINEVENT_AD = TelemetryContract(
    id="winevent-ad",
    platform="winevent",
    channel="windows:security",
    backend_name="winrm-winevent",
    requirements={"audit_policy": "ProcessCreation"},
    signal={"event_codes": [4688, 4769, 4771], "required_fields": ["EventCode"]},
)

CONTRACT_WAZUH = TelemetryContract(
    id="wazuh-alerts",
    platform="wazuh",
    channel="wazuh:alerts",
    backend_name="wazuh",
    requirements={},
    signal={},
)

# Contract registry — lookup by id
CONTRACTS: dict[str, TelemetryContract] = {
    c.id: c for c in [CONTRACT_SPLUNK_WEB, CONTRACT_WINEVENT_AD, CONTRACT_WAZUH]
}


def get_contract(contract_id: str) -> TelemetryContract | None:
    """Look up a contract by id."""
    return CONTRACTS.get(contract_id)


def contract_for_technique(technique_id: str, target_host: str | None = None) -> TelemetryContract:
    """Return the appropriate contract for a technique+target combination.

    AD targets → winevent-ad, everything else → splunk-web.
    """
    ad_targets = {"dc01", "srv01", "ws01", "meta3", "lab-dc01", "lab-srv01"}
    if target_host and any(ad in target_host.lower() for ad in ad_targets):
        return CONTRACT_WINEVENT_AD
    return CONTRACT_SPLUNK_WEB
