"""Live-run defect (run-33f8f167db31, portal5_lab/windows:security): every
real Windows event reached the grader unclassified. `_raw_kv_fields` read
only ONE `key=value` pair per line (`partition("=")`), so a real Splunk
Windows line -- several pairs on one line -- had its first key swallow the
whole remainder: `EventCode=4634 TimeCreated=2026-11-07 07:29:27` parsed as
EventCode `4634 TimeCreated=2026-11-07 07:29:27`, missed `_WINSEC_EVENTS`,
and `classify_record` honestly returned "" -- for events that ARE mapped.
The wire shape, not the map, was the defect.
"""

from __future__ import annotations

from portal.modules.security.core.bully import telemetry_behavior as tb

LIVE_LINE = "EventCode=4634 TimeCreated=2026-11-07 07:29:27"


def test_both_pairs_of_the_live_line_with_timecreated_intact():
    fields = tb._raw_kv_fields({"_raw": LIVE_LINE})
    assert fields["EventCode"] == "4634"
    assert fields["TimeCreated"] == "2026-11-07 07:29:27"


def test_classify_live_windows_security_line_is_mapped_not_empty():
    assert tb.classify_record({"_raw": LIVE_LINE}, "windows:security") == "auth"
    assert (
        tb.classify_record(
            {"_raw": "EventCode=4624 TimeCreated=2026-11-07 07:29:27"}, "windows:security"
        )
        == "auth"
    )


def test_single_pair_per_line_with_space_bearing_value_unchanged():
    fields = tb._raw_kv_fields({"_raw": "Message=An account was successfully logged on"})
    assert fields == {"Message": "An account was successfully logged on"}


def test_json_bodied_raw_branch_untouched():
    fields = tb._raw_kv_fields({"_raw": '{"cousin_id": "cz-T1-00", "n": 2}'})
    assert fields == {"cousin_id": "cz-T1-00", "n": "2"}


def test_multiline_classic_windows_text_still_one_pair_per_line():
    record = {
        "_raw": "08/20/2018 03:17:58 AM\nLogName=Security\nEventCode=4689\n"
        "ComputerName=BSTOLL-L.froth.ly\n"
    }
    fields = tb._raw_kv_fields(record)
    assert fields["EventCode"] == "4689"
    assert fields["LogName"] == "Security"
    assert fields["ComputerName"] == "BSTOLL-L.froth.ly"


def test_multiline_auditd_text_still_one_pair_per_line():
    record = {"_raw": "type=CRED_ACQ\npid=812\nmsg=audit(1730000000.123:456)\n"}
    assert tb.classify_record(record, "auditd") == "auth"


def test_line_without_equals_is_skipped():
    assert tb._raw_kv_fields({"_raw": "header line with no pairs\nEventCode=4689"}) == {
        "EventCode": "4689"
    }


def test_key_with_empty_value_kept():
    assert tb._raw_kv_fields({"_raw": "EventCode="}) == {"EventCode": ""}


def test_value_containing_equals_not_truncated_at_inner_equals():
    assert tb._raw_kv_fields({"_raw": "foo=a=b"}) == {"foo": "a=b"}
    assert tb._raw_kv_fields({"_raw": "data=SGVsbG8="}) == {"data": "SGVsbG8="}
