"""N.3 -- likelihood-ratio discriminative weight (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import cousin_relation as cr

_JUNK_TOKEN_RECORD = {"context_topology": {"noise": "heartbeat_ping"}}


def _known_records() -> list[dict]:
    """Known malicious types never mention the junk token."""
    return [
        {"action_sequence": ["proc_create", "net_connect"]},
        {"action_sequence": ["proc_create", "escalate"]},
        {"action_sequence": ["collect", "exfil"]},
    ]


def _baseline_records_with_frequent_junk() -> list[dict]:
    """The environment's own corpus: the junk token is nearly ubiquitous."""
    return [_JUNK_TOKEN_RECORD for _ in range(50)] + [{"action_sequence": ["proc_create"]}]


def test_feature_frequent_in_baseline_and_absent_from_known_scores_at_or_below_neutral():
    baseline_records = _baseline_records_with_frequent_junk()
    index = cr.build_discriminative_index(_known_records(), baseline_records=baseline_records)
    weight = index.weight("noise=heartbeat_ping")
    assert weight <= 1.0, (
        "a feature ubiquitous in baseline and absent from known types must not exceed neutral"
    )


def test_same_feature_under_legacy_idf_scores_maximal():
    """Documents the inversion N.3 fixes: without a baseline, the very same
    unseen-in-known token scores at the ceiling (maximally distinctive)."""
    index = cr.build_discriminative_index(_known_records())
    weight = index.weight("noise=heartbeat_ping")
    assert weight == index.default_weight


def test_feature_common_in_known_and_absent_from_baseline_scores_high():
    known = [
        {"action_sequence": ["proc_create", "escalate", "rare_signature_token"]} for _ in range(10)
    ]
    baseline = [{"action_sequence": ["proc_create"]} for _ in range(10)]
    index = cr.build_discriminative_index(known, baseline_records=baseline)
    weight = index.weight("rare_signature_token")
    assert weight > 1.0


def test_default_weight_stays_bounded_ceiling_with_baseline():
    known = _known_records()
    baseline = _baseline_records_with_frequent_junk()
    index = cr.build_discriminative_index(known, baseline_records=baseline)
    for token in index.known_df:
        assert index.weight(token) <= index.default_weight
    assert index.weight("never_seen_anywhere_token") <= index.default_weight
