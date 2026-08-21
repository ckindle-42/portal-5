"""TASK_BULLY_INVESTIGATION_V1 (I.5): suricata mapping and concentration-
aware classifier health.

`suricata -> evade` supplied 44.8% of all classified behaviour (20,317 of
45,356) from one sourcetype -- entropy alone did not catch this (2.28 bits,
`degenerate=False`). `coverage_report` must now also fail on per-class
concentration and per-source concentration, each with its own reason, while
the old entropy check keeps passing on this exact distribution (permanent
regression case).
"""

from __future__ import annotations

from portal.modules.security.core.bully import telemetry_behavior as tb


def _t3_like_records() -> list[tuple[dict, str]]:
    """A distribution shaped like T.3's real one: `evade` is 44.8% of all
    classified records (20317/45356) and every one of them came from
    `suricata`; the remaining classes are spread across several other real
    sourcetypes so entropy stays well above the 1.0-bit floor."""
    records: list[tuple[dict, str]] = []
    records += [({"EventCode": "4624"}, "wineventlog:security")] * 12000
    records += [({"EventCode": "4688"}, "wineventlog:security")] * 6000
    records += [({"EventCode": "1"}, "xmlwineventlog:sysmon")] * 4000
    records += [({"query": "x"}, "stream:dns")] * 3356
    records += [({"_raw": "{}"}, "suricata")] * 20317
    return records


def _stub_classifier_matching_t3_shape(record, sourcetype):
    """Reproduces T.3's exact numbers directly (20317 suricata->evade,
    45356 total classified, rest spread) without depending on which real
    signature categories botsv1/v3 happen to carry -- the concentration
    checks operate on the distribution, not on how it was produced."""
    if sourcetype == "suricata":
        return "evade"
    return tb.classify_record(record, sourcetype)


def test_t3_distribution_fails_new_checks_but_passes_old_entropy_check():
    records = _t3_like_records()
    report = tb.coverage_report(records, classifier=_stub_classifier_matching_t3_shape)

    assert report.n_classified == 45673
    assert not report.degenerate  # old entropy check: passes
    assert report.concentrated  # new checks: fails
    assert any(r.startswith("class_concentration:evade") for r in report.concentration_reasons)
    assert any(r.startswith("source_concentration:evade") for r in report.concentration_reasons)
    assert report.class_concentration["evade"] > tb.MAX_CLASS_SHARE
    assert report.source_concentration["evade"] > tb.MAX_SOURCE_SHARE_OF_CLASS


def test_mixed_distribution_with_real_source_spread_is_not_concentrated():
    """Each class here is genuinely fed by more than one real sourcetype, at
    a spread below both ceilings -- proof the checks don't false-positive on
    a distribution that is actually mixed, only on one that collapses."""
    records: list[tuple[dict, str]] = []
    records += [({"EventCode": "4624"}, "wineventlog:security")] * 30  # auth
    records += [({"type": "USER_AUTH"}, "auditd")] * 20  # auth
    records += [({"EventCode": "4688"}, "wineventlog:security")] * 25  # execute
    records += [({"type": "EXECVE"}, "auditd")] * 25  # execute
    records += [({"query": "x"}, "stream:dns")] * 20  # enumerate
    records += [({}, "osquery:results")] * 20  # enumerate
    report = tb.coverage_report(records)
    assert not report.concentrated, report.concentration_reasons


def test_suricata_alert_maps_by_category_not_unconditionally():
    trojan_record = {
        "_raw": '{"event_type":"alert","alert":{"category":"A Network Trojan was detected"}}'
    }
    assert tb.classify_record(trojan_record, "suricata") == "c2_exfil"

    unmapped_record = {"_raw": '{"event_type":"alert","alert":{"category":"Misc Attack"}}'}
    assert tb.classify_record(unmapped_record, "suricata") == ""

    dns_record = {"_raw": '{"event_type":"dns"}'}
    assert tb.classify_record(dns_record, "suricata") == "enumerate"

    flow_record = {"_raw": '{"event_type":"flow"}'}
    assert tb.classify_record(flow_record, "suricata") == ""


def test_suricata_no_longer_hardcoded_to_evade():
    assert "suricata" not in tb._STREAM_SOURCETYPE
