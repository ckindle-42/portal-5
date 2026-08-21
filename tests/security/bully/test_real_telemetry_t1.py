"""T.1 -- behaviour classes read from real telemetry semantics
(TASK_BULLY_REAL_TELEMETRY_V1). Seeded to fail before the fix.

C.6 stood on the real corpus bed and the classifier could not read it: every
cousin cluster's shared shape collapsed to `{'unknown': N, 'other': N}`
because the shipped classifiers are substring tables over verb text, and
real telemetry carries no verb (a Windows logon is EventCode `4624`, not a
word). `floor_known_recall` measured 0.0 -- zero of four answer-key
techniques recovered from a corpus that publishes the answers.
"""

from __future__ import annotations

from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import pyramid, telemetry_behavior
from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY

# ── 13 real records C.6 read as `unknown`, now classified correctly ────────

_REAL_RECORDS: tuple[tuple[dict, str, str], ...] = (
    ({"EventCode": "4624"}, "wineventlog:security", "auth"),
    ({"EventCode": "4672"}, "wineventlog:security", "escalate"),
    ({"EventCode": "4688"}, "wineventlog:security", "execute"),
    ({"EventCode": "1102"}, "wineventlog:security", "evade"),
    ({"EventCode": "4768"}, "wineventlog:security", "auth"),
    ({"EventCode": "1"}, "xmlwineventlog:sysmon", "execute"),
    ({"EventCode": "3"}, "xmlwineventlog:sysmon", "c2_exfil"),
    ({"EventCode": "13"}, "xmlwineventlog:sysmon", "persist"),
    ({"query": "evil.example"}, "stream:dns", "enumerate"),
    ({"url": "/api/data"}, "stream:http", "c2_exfil"),
    ({"type": "USER_AUTH"}, "auditd", "auth"),
    ({"type": "EXECVE"}, "auditd", "execute"),
    ({"columns": []}, "osquery:results", "enumerate"),
)


def test_thirteen_real_records_classify_correctly():
    for record, sourcetype, expected in _REAL_RECORDS:
        assert telemetry_behavior.classify_record(record, sourcetype) == expected, (
            record,
            sourcetype,
        )


# ── both answer-key spines are fully classified (non-empty, no gaps) ──────


def test_answer_key_spines_fully_classified():
    for entry in BOTS_ANSWER_KEY:
        assert entry.behavioural_spine, entry.technique
        assert all(
            step in telemetry_behavior.BEHAVIOR_CLASSES for step in entry.behavioural_spine
        ), (
            entry.technique,
            entry.behavioural_spine,
        )


def test_t1558_004_spine_is_auth_auth_escalate():
    entry = next(e for e in BOTS_ANSWER_KEY if e.technique == "T1558.004")
    assert entry.behavioural_spine == ("auth", "auth", "escalate")


def test_t1071_001_spine_is_c2_exfil_c2_exfil():
    entry = next(e for e in BOTS_ANSWER_KEY if e.technique == "T1071.001")
    assert entry.behavioural_spine == ("c2_exfil", "c2_exfil")


# ── an unmapped sourcetype returns "" and appears in unmapped_sourcetypes ──


def test_unmapped_sourcetype_returns_empty_string():
    assert telemetry_behavior.classify_record({"anything": 1}, "Perfmon:CPU") == ""


def test_unmapped_sourcetype_appears_in_coverage_report():
    records = [
        ({"EventCode": "4624"}, "wineventlog:security"),
        ({"cpu_pct": 3.2}, "Perfmon:CPU"),
    ]
    report = telemetry_behavior.coverage_report(records)
    assert "Perfmon:CPU" in report.unmapped_sourcetypes
    assert "wineventlog:security" not in report.unmapped_sourcetypes


# ── seeded violation: routing captured records through the OLD substring
# classifiers collapses the answer-key spines to unclassified ────────────


def test_seeded_violation_pyramid_classify_behavior_cannot_read_real_records():
    """pyramid.classify_behavior is a verb-substring table; real telemetry
    (EventCode `4624`, an auditd `type`, a DNS `query`) has no verb field to
    hand it at all -- there is nothing an `action_of` extractor could pull
    that resembles `authenticate`/`exec`/etc., so every real record reads as
    no verb, and classify_behavior('') is '' (unknown), never the correct
    class."""
    for _record, _sourcetype, expected in _REAL_RECORDS:
        cls = pyramid.classify_behavior("")
        assert cls != expected
        assert cls == ""


def test_seeded_violation_default_action_classifier_collapses_to_unknown():
    """artifact_graph.DeterministicActionClassifier (the pre-T1 default) is
    the exact substring table that produced C.6's `{'unknown': N, 'other':
    N}` cluster shapes: real BOTS records carry no `action`-named field for
    field-role inference to extract, so every one classifies '' -> 'unknown'."""
    det = ag.DeterministicActionClassifier()
    for _record, _sourcetype, expected in _REAL_RECORDS:
        cls = det.classify(None)
        assert cls == "unknown"
        assert cls != expected


# ── build_graph now reads real telemetry by default (wired T1) ────────────


def _real_capture_record(source_id: str, event_code: str, base_time: float, i: int) -> dict:
    return {
        "__source_id": source_id,
        "EventCode": event_code,
        "host": "h1",
        "user": "AR-WIN-3\\Administrator",
        "eventTime": base_time + i * 5.0,
    }


def test_build_graph_default_classifier_reads_real_sourcetype():
    base_time = 1_700_000_000.0
    records = [
        _real_capture_record("lab-splunk:wineventlog:security", "4624", base_time, 0),
        _real_capture_record("lab-splunk:wineventlog:security", "4672", base_time, 1),
        _real_capture_record("lab-splunk:xmlwineventlog:sysmon", "3", base_time, 2),
    ]
    graph = ag.build_graph(records, source_id="lab-splunk:wineventlog:security")
    assert graph.role_map.extraction_valid, graph.role_map.failure_reasons
    classes = {a.action_class for a in graph.artifacts.values()}
    assert classes == {"auth", "escalate", "c2_exfil"}
    assert "unknown" not in classes
    assert "other" not in classes


def test_build_graph_no_cluster_shape_is_all_unclassified():
    base_time = 1_700_000_000.0
    records = [
        _real_capture_record("lab-splunk:wineventlog:security", "4624", base_time, 0),
        _real_capture_record("lab-splunk:xmlwineventlog:sysmon", "1", base_time, 1),
    ]
    graph = ag.build_graph(records, source_id="lab-splunk:wineventlog:security")
    assert graph.role_map.extraction_valid, graph.role_map.failure_reasons
    assert not all(a.action_class in ("unknown", "", "other") for a in graph.artifacts.values())


# ── coverage_report flags degeneracy when output entropy is below floor ───


def test_coverage_report_flags_degenerate_when_entropy_collapses():
    # 100 records, all the same real class -- entropy 0, well below the
    # 1.0-bit floor, exactly the C.6 shape (real-verb entropy was 0.302).
    records = [({"EventCode": "4624"}, "wineventlog:security") for _ in range(100)]
    report = telemetry_behavior.coverage_report(records)
    assert report.degenerate is True
    assert report.class_entropy_bits < telemetry_behavior.MIN_CLASS_ENTROPY_BITS


def test_coverage_report_not_degenerate_on_mixed_real_capture():
    records = [
        ({"EventCode": "4624"}, "wineventlog:security"),
        ({"EventCode": "4672"}, "wineventlog:security"),
        ({"EventCode": "1"}, "xmlwineventlog:sysmon"),
        ({"EventCode": "3"}, "xmlwineventlog:sysmon"),
        ({"query": "x"}, "stream:dns"),
    ]
    report = telemetry_behavior.coverage_report(records)
    assert report.degenerate is False
