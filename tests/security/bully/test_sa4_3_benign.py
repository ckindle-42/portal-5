"""SA4.3 -- benign/background corpus as first-class context (A3).

Hermetic: benign volume is ingested deliberately, the realized benign:attack
ratio is a measured property, and a benign-only neighborhood can never
manufacture a discovery (T3 references resolve INDETERMINATE).
"""

from __future__ import annotations

from portal.modules.security.core.bully.analyst_corpus import (
    T0_AUTHORITATIVE,
    T3_UNKNOWN,
    benign_ratio,
    canonical_embed_text,
    ingest_benign,
    ingest_events,
    per_class_benign_coverage,
    resolve_pair_band,
    snapshot_composition,
)


def _attack_specimen(specimen_id: str, sourcetype: str = "windows:security") -> dict:
    return ingest_events(
        [{"EventCode": 4688, "Image": "cmd.exe", "CommandLine": "/c whoami"}],
        specimen_id=specimen_id,
        sourcetype=sourcetype,
        labeling="authoritative",
        provenance={"source_id": "attack_data", "origin": "external_corpus"},
    )


def test_benign_specimens_are_retrievable_context():
    benign = ingest_benign(
        [{"EventCode": 4688, "Image": "C:\\Windows\\System32\\explorer.exe"}],
        specimen_id="benign-1",
        sourcetype="windows:security",
        provenance={"source_id": "dayjob_corp", "origin": "benign_corpus"},
    )
    assert benign["source_lane"] == "benign"
    assert benign["label_tier"] == T3_UNKNOWN
    assert benign["scoreable"] is False
    # Retrievable context: the engine view still carries the endpoint
    # dimensions so retrieval and dedup work on it.
    assert "action_sequence" in benign["engine_view"]["telemetry_view"]
    assert canonical_embed_text(benign)  # participates in canonical-text dedup


def test_benign_ratio_is_measured_not_targeted():
    attack = [_attack_specimen(f"att-{index}") for index in range(3)]
    benign = [
        ingest_benign(
            [{"EventCode": 4688, "Image": "explorer.exe"}],
            specimen_id=f"benign-{index}",
            sourcetype="windows:security",
        )
        for index in range(1)
    ]
    specimens = attack + benign
    ratio = benign_ratio(specimens)
    assert ratio == 1 / 4
    coverage = per_class_benign_coverage(specimens)
    assert coverage["windows:security"]["benign"] == 1
    assert coverage["windows:security"]["total"] == 4


def test_benign_only_neighborhood_does_not_manufacture_discoveries():
    """A graded pair whose reference is benign (T3) resolves INDETERMINATE
    even when the engine's raw relationship x response would read DISCOVERY --
    a benign-only neighborhood has no negative space to manufacture against
    (A3)."""
    benign = ingest_benign(
        [{"EventCode": 4688, "Image": "explorer.exe"}],
        specimen_id="benign-ref",
        sourcetype="windows:security",
    )
    attack = _attack_specimen("attack-probe")
    band = resolve_pair_band(
        attack["label_tier"],
        benign["label_tier"],
        relationship="SIMILAR",
        response="MISSED",
    )
    assert band == "INDETERMINATE"
    # Control: an all-attack (T0/T0) pair with the same raw verdicts IS a
    # discovery -- the INDETERMINATE above is a tier effect, not a scorer bug.
    control = resolve_pair_band(
        T0_AUTHORITATIVE, T0_AUTHORITATIVE, relationship="SIMILAR", response="MISSED"
    )
    assert control == "DISCOVERY"
    # A benign-only snapshot has a benign ratio of 1.0, reported as measured.
    composition = snapshot_composition([benign], ())
    assert composition["benign_ratio"] == 1.0


def test_benign_ratio_zero_when_no_benign():
    specimens = [_attack_specimen(f"att-{index}") for index in range(2)]
    assert benign_ratio(specimens) == 0.0
    assert benign_ratio([]) == 0.0


def test_per_class_benign_coverage_reports_mixed_classes():
    attack_win = _attack_specimen("att-win", "windows:security")
    attack_okta = ingest_events(
        [{"eventType": "user.authentication.auth_via_mfa"}],
        specimen_id="att-okta",
        sourcetype="OktaIM2:log",
        labeling="authoritative",
        provenance={"source_id": "okta"},
    )
    benign_win = ingest_benign(
        [{"EventCode": 4688, "Image": "explorer.exe"}],
        specimen_id="ben-win",
        sourcetype="windows:security",
    )
    coverage = per_class_benign_coverage([attack_win, attack_okta, benign_win])
    assert coverage["windows:security"]["benign_fraction"] == 0.5
    assert coverage["OktaIM2:log"]["benign_fraction"] == 0.0
