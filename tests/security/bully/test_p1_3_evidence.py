"""P1.3 -- evidence manifests + Episode adapter + flagged shadow ingestion.

FINAL_VALIDATION C2 (evidence integrity / truth boundaries) + I1
(compat -- byte-stability with the shadow flag off).
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import evidence as ev
from portal.modules.security.core.episode import Episode


def _episode(**overrides) -> Episode:
    defaults = {
        "episode_id": "ep-20260101T000000Z-scn-abcd1234",
        "scenario": "lateral-movement-wmi",
        "target_host": "host-1",
        "started_at": 0.0,
        "red_status": "RED_LANDED",
        "telemetry_status": "TELEMETRY_INDEXED",
        "detection_status": "DETECTION_CONFIRMED",
        "used_synthetic": False,
    }
    defaults.update(overrides)
    return Episode(**defaults)


# ── manifest hash mismatch rejected on dereference (C2) ─────────────────────


def test_verified_item_when_hash_matches():
    payload = b"telemetry bytes"
    item = ev.EvidenceItemRef(
        evidence_id="ev-1",
        type="telemetry",
        uri="results/captures/blue/x.json",
        content_hash=ev.content_hash(payload),
        origin="observed_packet",
    )
    verified = ev.verify_item(item, payload)
    assert verified.verification_status == "verified"


def test_manifest_hash_mismatch_rejected_on_dereference():
    item = ev.EvidenceItemRef(
        evidence_id="ev-1",
        type="telemetry",
        uri="results/captures/blue/x.json",
        content_hash=ev.content_hash(b"original bytes"),
        origin="observed_packet",
    )
    tampered = ev.verify_item(item, b"tampered bytes")
    assert tampered.verification_status == "invalid"


# ── observed-origin requirement (G0 / C2) ───────────────────────────────────


def test_synthetic_only_manifest_fails_g0():
    items = [
        ev.EvidenceItemRef(
            evidence_id="ev-1",
            type="telemetry",
            uri="x",
            content_hash="h",
            origin="synthetic_fixture",
            synthetic=True,
        )
    ]
    assert ev.synthetic_never_passes_g0(items) is False


def test_observed_origin_manifest_passes_g0():
    items = [
        ev.EvidenceItemRef(
            evidence_id="ev-1",
            type="telemetry",
            uri="x",
            content_hash="h",
            origin="observed_target_log",
        )
    ]
    assert ev.synthetic_never_passes_g0(items) is True


def test_imported_observed_passes_g0_but_cannot_mint_known_covered():
    items = [
        ev.EvidenceItemRef(
            evidence_id="ev-imported",
            type="telemetry",
            uri="x",
            content_hash="h",
            origin="imported_observed",
        )
    ]
    assert ev.synthetic_never_passes_g0(items) is True
    assert ev.can_mint_known_covered(items) is False


def test_mixed_synthetic_and_observed_still_passes_g0():
    items = [
        ev.EvidenceItemRef(
            evidence_id="ev-1",
            type="t",
            uri="x",
            content_hash="h",
            origin="synthetic_fixture",
            synthetic=True,
        ),
        ev.EvidenceItemRef(
            evidence_id="ev-2",
            type="t",
            uri="y",
            content_hash="h2",
            origin="sensor_derived",
        ),
    ]
    assert ev.synthetic_never_passes_g0(items) is True


# ── manifest completeness ────────────────────────────────────────────────────


def test_manifest_completeness_and_missing_reasons():
    items = [ev.EvidenceItemRef(evidence_id="ev-1", type="telemetry", uri="x", content_hash="h")]
    manifest = ev.build_manifest(
        episode_id="ep-1", required_types=["telemetry", "detection_query"], items=items
    )
    assert manifest.completeness == 0.5
    assert manifest.missing_reasons == ["missing required evidence type: detection_query"]


# ── Episode adapter (I-2) ────────────────────────────────────────────────────


def test_adapt_episode_projects_expected_fields():
    ep = _episode()
    adapted = ev.adapt_episode(ep)
    assert adapted["episode_id"] == ep.episode_id
    assert adapted["verdict"] == "PROVEN"
    assert adapted["used_synthetic"] is False


def test_indeterminate_verdict_is_blocked_not_scored():
    ep = _episode(telemetry_status="TELEMETRY_COLLECTION_FAILED")
    assert ep.verdict() == "INDETERMINATE"
    assert ev.episode_verdict_is_blocked(ep) is True


def test_proven_verdict_is_not_blocked():
    ep = _episode()
    assert ev.episode_verdict_is_blocked(ep) is False


# ── shadow ingestion (I-22) ──────────────────────────────────────────────────


def test_shadow_flag_off_is_a_pure_noop_byte_stability():
    ep = _episode()
    result = ev.shadow_ingest(ep, flag="off")
    assert result is None


def test_shadow_flag_shadow_returns_adapter_view_without_mutating_episode():
    ep = _episode()
    before = ep.to_dict()
    result = ev.shadow_ingest(ep, flag="shadow")
    assert result is not None
    assert result["episode_id"] == ep.episode_id
    assert ep.to_dict() == before  # Episode itself is untouched


def test_shadow_flag_rejects_unknown_value():
    ep = _episode()
    with pytest.raises(ValueError):
        ev.shadow_ingest(ep, flag="turbo")
