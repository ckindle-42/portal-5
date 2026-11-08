"""Scorer tests: truth bridge matching, per-event metrics, per-stage recovery."""

from __future__ import annotations

import csv

from portal.modules.security.core.mawa.events import ParsedEvent, read_events
from portal.modules.security.core.mawa.join import build_groups
from portal.modules.security.core.mawa.truth import (
    LowRow,
    StageTruth,
    match_events_to_truth,
    per_event_metrics,
    per_stage_recovery,
    plaso_apache_message,
    plaso_syslog_message,
    read_low_level,
)

BASE_TS = 1_787_380_200.0  # 2026-08-22 13:30:00 +07:00


def _apache_event(event_id: int, ts: float, url: str, code: str = "200") -> ParsedEvent:
    fields = {
        "method": "GET",
        "url": url,
        "proto": "HTTP/1.1",
        "client": "192.0.2.9",
        "code": code,
        "bytes": "10",
        "referer": "-",
        "user_agent": "UA",
    }
    raw = f'192.0.2.9 - - [22/Aug/2026:13:30:00 +0700] "GET {url} HTTP/1.1" {code} 10 "-" "UA"'
    return ParsedEvent(
        event_id=event_id,
        ts=ts,
        source_file="log/apache2/access.log",
        kind="apache_access",
        tag="",
        pid="",
        message=f"GET {url} HTTP/1.1",
        fields=fields,
        entities=frozenset({f"path:{url.split('?')[0]}", f"code:{code}"}),
        raw=raw,
    )


def _syslog_event(event_id: int, ts: float, tag: str, pid: str, message: str) -> ParsedEvent:
    return ParsedEvent(
        event_id=event_id,
        ts=ts,
        source_file="log/auth.log",
        kind="syslog",
        tag=tag,
        pid=pid,
        message=message,
        fields={},
        entities=frozenset({"user:x"}),
        raw=f"raw {message}",
    )


def _low_row(event_id: int, ts: float, base: str, message: str, label: str) -> LowRow:
    return LowRow(
        event_id=event_id,
        ts=ts,
        display_name=f"OS:evidences\\\\{base}",
        parser="text/apache_access" if "access.log" in base else "text/syslog_traditional",
        message=message,
        label=label,
    )


def test_plaso_message_reconstruction() -> None:
    msg = plaso_apache_message(
        {
            "method": "GET",
            "url": "/a",
            "proto": "HTTP/1.1",
            "client": "1.1.1.1",
            "code": "200",
            "referer": "-",
            "user_agent": "UA",
        }
    )
    assert msg == "http_request: GET /a HTTP/1.1 from: 1.1.1.1 code: 200 user_agent: UA"
    msg2 = plaso_apache_message(
        {
            "method": "GET",
            "url": "/a",
            "proto": "HTTP/1.1",
            "client": "1.1.1.1",
            "code": "200",
            "referer": "http://r/x",
            "user_agent": "UA",
        }
    )
    assert "referer: http://r/x " in msg2
    assert (
        plaso_syslog_message("sshd", "1548", "closed for user dvwa")
        == "[sshd  pid: 1548] closed for user dvwa"
    )
    assert plaso_syslog_message("sudo", "", "a, b 'c'") == "[sudo] a  b \\'c\\'"


def test_bridge_matches_and_reports_unmatched(tmp_path) -> None:
    events = [_apache_event(1, BASE_TS, "/one"), _apache_event(2, BASE_TS + 1, "/two")]
    rows = [
        _low_row(
            101,
            BASE_TS,
            "access.log",
            "http_request: GET /one HTTP/1.1 from: 192.0.2.9 code: 200 user_agent: UA",
            "attack_x",
        ),
        _low_row(
            102,
            BASE_TS + 1,
            "access.log",
            "http_request: GET /two HTTP/1.1 from: 192.0.2.9 code: 200 user_agent: UA",
            "benign",
        ),
    ]
    bridge = match_events_to_truth(events, rows)
    assert bridge.raw_to_gt == {1: 101, 2: 102}
    assert bridge.unmatched_raw == [] and bridge.unmatched_gt == []


def test_bridge_dedup_leaves_extra_raw_copy_unmatched() -> None:
    events = [_apache_event(1, BASE_TS, "/same"), _apache_event(2, BASE_TS, "/same")]
    rows = [
        _low_row(
            101,
            BASE_TS,
            "access.log",
            "http_request: GET /same HTTP/1.1 from: 192.0.2.9 code: 200 user_agent: UA",
            "benign",
        )
    ]
    bridge = match_events_to_truth(events, rows)
    assert bridge.raw_to_gt == {1: 101}
    assert [e.event_id for e in bridge.unmatched_raw] == [2]


def test_per_event_metrics_math() -> None:
    events = [
        _apache_event(1, BASE_TS, "/a1"),
        _apache_event(2, BASE_TS + 1, "/a2"),
        _apache_event(3, BASE_TS + 2, "/b1"),
        _apache_event(4, BASE_TS + 3, "/miss"),
    ]
    rows = [
        _low_row(
            101,
            BASE_TS,
            "access.log",
            "http_request: GET /a1 HTTP/1.1 from: 192.0.2.9 code: 200 user_agent: UA",
            "attack_x",
        ),
        _low_row(
            102,
            BASE_TS + 1,
            "access.log",
            "http_request: GET /a2 HTTP/1.1 from: 192.0.2.9 code: 200 user_agent: UA",
            "attack_x",
        ),
        _low_row(
            103,
            BASE_TS + 2,
            "access.log",
            "http_request: GET /b1 HTTP/1.1 from: 192.0.2.9 code: 200 user_agent: UA",
            "benign",
        ),
        _low_row(
            104,
            BASE_TS + 9,
            "access.log",
            "http_request: GET /a9 HTTP/1.1 from: 192.0.2.9 code: 200 user_agent: UA",
            "attack_x",
        ),
    ]
    bridge = match_events_to_truth(events, rows)
    groups = build_groups(events)
    metrics = per_event_metrics(groups, bridge, rows)
    assert metrics.attack_total == 3
    assert metrics.tp == 2
    assert metrics.fn == 1
    assert metrics.unmatched_flagged == 1
    assert metrics.flagged == 4
    assert metrics.fp_matched_only == 1
    assert metrics.fp_strict == 2
    assert abs(metrics.precision_matched_only - 2 / 3) < 1e-9
    assert metrics.precision_strict == 0.5
    assert abs(metrics.recall - 2 / 3) < 1e-9


def test_per_stage_recovery_iou_and_split() -> None:
    events = [
        _apache_event(1, BASE_TS, "/solo"),
        _apache_event(2, BASE_TS + 60, "/pair1"),
        _apache_event(3, BASE_TS + 60, "/pair2"),
    ]
    rows = [
        _low_row(
            201,
            BASE_TS,
            "access.log",
            "http_request: GET /solo HTTP/1.1 from: 192.0.2.9 code: 200 user_agent: UA",
            "solo_stage",
        ),
        _low_row(
            202,
            BASE_TS + 60,
            "access.log",
            "http_request: GET /pair1 HTTP/1.1 from: 192.0.2.9 code: 200 user_agent: UA",
            "pair_stage",
        ),
        _low_row(
            203,
            BASE_TS + 60,
            "access.log",
            "http_request: GET /pair2 HTTP/1.1 from: 192.0.2.9 code: 200 user_agent: UA",
            "pair_stage",
        ),
    ]
    bridge = match_events_to_truth(events, rows)
    groups = build_groups(events)
    stages = [
        StageTruth("solo_stage", "", frozenset({201}), "a"),
        StageTruth("pair_stage", "", frozenset({202, 203}), "b"),
        StageTruth("absent_stage", "", frozenset({999}), "c"),
    ]
    results = per_stage_recovery(groups, bridge, stages)
    by_label = {r.label: r for r in results}
    assert by_label["solo_stage"].best_iou == 1.0 and by_label["solo_stage"].recovered
    assert by_label["pair_stage"].best_iou == 1.0 and by_label["pair_stage"].recovered
    assert by_label["absent_stage"].best_group_id is None
    assert not by_label["absent_stage"].recovered and not by_label["absent_stage"].any_overlap


def test_reader_events_flow_through_full_stack(tmp_path) -> None:
    log = tmp_path / "access.log"
    log.write_text(
        '192.0.2.9 - - [22/Aug/2026:13:30:00 +0700] "GET /one HTTP/1.1" 200 10 "-" "UA"\n'
        '192.0.2.9 - - [22/Aug/2026:13:30:01 +0700] "GET /one HTTP/1.1" 200 10 "-" "UA"\n',
        encoding="utf-8",
    )
    events, reports = read_events([str(log)], syslog_year=2026, syslog_tz_hours=7.0)
    assert reports[0].events == 2
    expected = "http_request: GET /one HTTP/1.1 from: 192.0.2.9 code: 200 user_agent: UA"
    rows = [_low_row(301, BASE_TS, "access.log", expected, "attack_x")]
    bridge = match_events_to_truth(events, rows)
    assert len(bridge.raw_to_gt) == 1 and bridge.unmatched_gt == []


def test_low_level_csv_round_trip(tmp_path) -> None:
    path = tmp_path / "low.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "event_id",
                "datetime",
                "timestamp_desc",
                "source",
                "source_long",
                "message",
                "parser",
                "display_name",
                "tag",
                "normalized",
                "actor",
                "decoded",
                "ground_truth_label",
            ]
        )
        writer.writerow(
            [
                1,
                "2026-08-22T13:30:00.000000+07:00",
                "Recorded Time",
                "LOG",
                "Log File",
                "msg",
                "text/apache_access",
                "OS:evidences\\\\apache2\\\\access.log",
                "-",
                "n",
                "a",
                "-",
                "attack_x",
            ]
        )
    rows = read_low_level(str(path))
    assert rows[0].event_id == 1 and rows[0].label == "attack_x"
    assert rows[0].ts == BASE_TS
