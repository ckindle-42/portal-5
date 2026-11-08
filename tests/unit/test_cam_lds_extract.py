"""CAM-LDS extractor: readers, granularity rules and the time+entity join."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.cam_lds_extract import (
    CampaignEvents,
    Event,
    Reader,
    _parse_dir_name,
    canonical,
    compare_bundles,
    entity_host,
    extract_entities,
    granularity,
    host_map,
    join,
    load_steps,
    parse_iso,
    parse_syslog_ts,
    read_fast_log,
    read_step_file,
    read_syslog,
    read_wazuh,
    sequence_group_rule,
    unlabelled_profile,
    variant_grid,
    window_check,
)

UTC = UTC
START = datetime(2025, 9, 22, 18, 0, 0, tzinfo=UTC)


def _write_steps(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")


def _step(ts: str, cmd: str, techniques: str | None = "T1059", type_: str = "shell") -> dict:
    meta = {"techniques": techniques, "tactics": "Execution"} if techniques else None
    return {"start-datetime": ts, "type": type_, "cmd": cmd, "parameters": {"metadata": meta}}


def _steps_in_tmp(rows: list[dict], view: str = "steps", name: str = "c-1") -> list:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        _write_steps(Path(tmp) / view / name / "attacker/logs/attackmate.json", rows)
        return load_steps(Path(tmp), view).records


def test_parse_iso_normalises_offsets_and_naive_stamps() -> None:
    assert parse_iso("2025-12-11T14:28:03.325538") == datetime(
        2025, 12, 11, 14, 28, 3, 325538, tzinfo=UTC
    )
    assert parse_iso("2025-12-11T14:28:04.494+0000") == datetime(
        2025, 12, 11, 14, 28, 4, 494000, tzinfo=UTC
    )
    assert parse_iso("2025-12-11T14:28:04Z") == datetime(2025, 12, 11, 14, 28, 4, tzinfo=UTC)
    assert parse_iso("not a timestamp") is None


def test_parse_syslog_ts_uses_campaign_year() -> None:
    assert parse_syslog_ts("Dec 11 14:28:09 inetfw dnsmasq[736]: query[A] x", 2025) == datetime(
        2025, 12, 11, 14, 28, 9, tzinfo=UTC
    )
    assert parse_syslog_ts("garbage", 2025) is None


def test_extract_entities_takes_maximal_names_and_valid_ips() -> None:
    got = extract_entities("ssh root@video.attackbed.com from 192.42.1.174 via http://a.example/x")
    assert "host:video.attackbed.com" in got
    assert "host:attackbed.com" not in got  # nested suffix is not a separate entity
    assert "ip:192.42.1.174" in got
    assert "url:http://a.example/x" in got
    assert "host:a.example" in got
    assert extract_entities("999.1.2.3") == frozenset()


def test_read_step_file_counts_steps_and_records_parse_failures(tmp_path: Path) -> None:
    path = tmp_path / "attackmate.json"
    path.write_text(
        json.dumps(_step("2025-09-22T18:29:48.382738", "dnsenum attackbed.com", "T1590.002,T1591"))
        + "\n{not json\n"
        + json.dumps(_step("2025-09-22T18:30:07.591219", "id", None))
        + "\n"
    )
    reader = Reader()
    steps = read_step_file(path, campaign="c", view="steps", sequence="c-1", run=1, reader=reader)
    assert [s.techniques for s in steps] == [("T1590.002", "T1591"), ()]
    assert [f.line for f in reader.failures] == [2]
    assert steps[1].ts > steps[0].ts


def test_load_steps_derives_campaign_and_run_from_directory_names(tmp_path: Path) -> None:
    _write_steps(
        tmp_path / "steps" / "c_variant-1" / "attacker/logs/attackmate.json",
        [_step("2025-09-22T18:00:00", "id")],
    )
    _write_steps(
        tmp_path / "steps" / "c_variant-2" / "attacker/logs/attackmate.json",
        [_step("2025-09-22T18:00:10", "id")],
    )
    _write_steps(
        tmp_path / "sequences" / "c_variant-1_2" / "attacker/logs/attackmate.json",
        [_step("2025-09-22T18:00:00", "id")],
    )
    reader = load_steps(tmp_path, "steps")
    assert [s.run for s in reader.records] == [1, 2]
    assert {s.campaign for s in reader.records} == {"c_variant"}
    assert len(load_steps(tmp_path, "sequences").records) == 1


def test_parse_dir_name_handles_grouped_runs() -> None:
    assert _parse_dir_name("1_autostart_pam-13") == ("1_autostart_pam", [13])
    assert _parse_dir_name("6_screensharing_cron-40_41_42") == (
        "6_screensharing_cron",
        [40, 41, 42],
    )


def test_defender_readers_parse_and_report_bad_lines(tmp_path: Path) -> None:
    wazuh = tmp_path / "s" / "wazuh" / "logs" / "alerts" / "alerts.json"
    wazuh.parent.mkdir(parents=True)
    wazuh.write_text(
        json.dumps(
            {
                "timestamp": "2025-12-11T14:28:04.494+0000",
                "rule": {"description": "Suricata: Alert", "level": 3},
                "agent": {"name": "inetfw", "ip": "192.168.100.254"},
                "data": {"src_ip": "192.42.1.174", "dest_ip": "172.17.100.122"},
            }
        )
        + "\nnot-json\n"
    )
    fast = tmp_path / "s" / "inetfw" / "logs" / "log" / "suricata" / "fast.log"
    fast.parent.mkdir(parents=True)
    fast.write_text(
        "12/11/2025-14:28:03.251218  [**] [1:2001219:20] ET SCAN Potential SSH Scan [**] "
        "[Classification: Attempted Information Leak] [Priority: 2] {TCP} "
        "192.42.1.174:56754 -> 172.17.100.122:22\nbroken line\n"
    )
    syslog = tmp_path / "s" / "corpdns" / "logs" / "log" / "syslog"
    syslog.parent.mkdir(parents=True)
    syslog.write_text(
        "Dec 11 14:28:02 corpdns dnsmasq[834]: auth[A] fw.attackbed.com from 192.42.2.2\n"
    )

    reader = Reader()
    events = read_wazuh(wazuh, 2025, reader) + read_fast_log(fast, 2025, reader, "inetfw")
    events += read_syslog(syslog, 2025, reader, "syslog", "corpdns")
    assert sorted(e.kind for e in events) == ["suricata_fast", "syslog", "wazuh"]
    assert {f.path.rsplit("/", 1)[-1] for f in reader.failures} == {"alerts.json", "fast.log"}
    assert "ip:192.42.1.174" in events[0].entities
    assert events[0].host == "inetfw"


def test_host_map_and_canonical_resolve_ip_to_inventory_host() -> None:
    agent = Event(
        ts=START,
        host="inetfw",
        kind="wazuh",
        entities=frozenset(),
        raw="",
        attrs=(("ip", "192.168.100.254"), ("name", "inetfw")),
    )
    dns = Event(
        ts=START,
        host="corpdns",
        kind="syslog",
        entities=frozenset(),
        raw="Dec 11 14:28:02 corpdns dnsmasq: config fw.attackbed.com is 192.42.0.254",
    )
    dns_map, agents = host_map([agent, dns])
    assert dns_map == {"fw.attackbed.com": "192.42.0.254"}
    assert agents == {"192.168.100.254": "inetfw"}
    assert entity_host("host:fw.attackbed.com", dns_map, agents) is None
    inventory = {"192.42.1.174": "attacker"}
    assert canonical("ip:192.42.1.174", inventory) == "host:attacker"
    assert canonical("ip:10.9.9.9", inventory) == "ip:10.9.9.9"
    assert canonical("host:video.attackbed.com", inventory) == "host:video.attackbed.com"


def test_join_attributes_events_by_window_and_marks_silent_steps() -> None:
    steps = _steps_in_tmp(
        [
            _step("2025-09-22T18:00:00", "nmap 172.17.100.121"),
            _step("2025-09-22T18:01:00", "sleep", None, "sleep"),
            _step("2025-09-22T18:02:00", "id", None),
        ]
    )
    events = [
        Event(
            START + timedelta(seconds=5),
            "inetfw",
            "suricata_fast",
            extract_entities("192.42.1.174 -> 172.17.100.121"),
            "e1",
        ),
        Event(START + timedelta(seconds=90), "corpdns", "syslog", frozenset(), "e2"),
    ]
    rows, summary = join(
        steps, {"c": CampaignEvents(events)}, {}, {"172.17.100.121": "videoserver"}
    )
    assert [r.manifestations for r in rows] == [1, 1, 0]
    assert [r.silent for r in rows] == [False, False, True]
    assert rows[0].shared_entities == ("host:videoserver",)
    assert rows[0].hosts == ("inetfw",)
    assert summary["silent"] == 1
    # the entity names videoserver but was observed at inetfw
    assert summary["cross_host_edges"] == 1


def test_join_counts_cross_host_edge_for_attacker_ip_seen_on_victim() -> None:
    steps = _steps_in_tmp([_step("2025-09-22T18:00:00", "curl http://192.42.1.174/x")])
    events = [
        Event(
            START + timedelta(seconds=2),
            "videoserver",
            "wazuh",
            extract_entities("192.42.1.174"),
            "e",
        )
    ]
    rows, summary = join(steps, {"c": CampaignEvents(events)}, {}, {"192.42.1.174": "attacker"})
    assert summary["cross_host_edges"] == 1
    assert summary["steps_with_cross_host_edge"] == 1
    assert rows[0].shared_entities == ("host:attacker",)


def test_campaign_events_dedupe_and_bound_the_window() -> None:
    first = Event(START, "a", "syslog", frozenset(), "same")
    duplicate = Event(START, "a", "syslog", frozenset(), "same")
    later = Event(START + timedelta(seconds=30), "b", "syslog", frozenset(), "other")
    index = CampaignEvents([first, duplicate, later])
    assert index.between(START, START + timedelta(seconds=31)) == [first, later]
    assert index.between(START + timedelta(seconds=1), START + timedelta(seconds=2)) == []


def test_window_check_flags_events_before_and_after_the_window() -> None:
    seq_steps = _steps_in_tmp([_step("2025-09-22T18:00:00", "id")], view="sequences")
    events = {
        "c-1": [
            Event(START - timedelta(seconds=30), "corpdns", "syslog", frozenset(), "early"),
            Event(START + timedelta(seconds=30), "corpdns", "syslog", frozenset(), "inside"),
        ]
    }
    got = window_check(seq_steps, events, 1800)
    assert got["checked"] == 1
    assert got["dirs_with_events_before_step"] == 1
    assert got["max_lead_s"] == 29


def test_unlabelled_profile_splits_sleeps_from_commands() -> None:
    steps = _steps_in_tmp(
        [
            _step("2025-09-22T18:00:00", "sleep", None, "sleep"),
            _step("2025-09-22T18:00:10", "id"),
            _step("2025-09-22T18:00:20", ":wq!", None, "msf-session"),
        ]
    )
    profile = unlabelled_profile(steps)
    assert profile["no_technique"] == 2
    assert profile["by_type"] == {"msf-session": 1, "sleep": 1}
    assert profile["by_shape"] == {"editor-keystroke": 1, "sleep": 1}


def test_sequence_group_rule_explains_a_same_technique_block(tmp_path: Path) -> None:
    for index, tech in enumerate(["T1105", "T1059", "T1059", "T1033"], start=1):
        _write_steps(
            tmp_path / "steps" / f"c-{index}" / "attacker/logs/attackmate.json",
            [_step(f"2025-09-22T18:0{index}:00", "x", tech)],
        )
    _write_steps(
        tmp_path / "sequences" / "c-2_3" / "attacker/logs/attackmate.json",
        [
            _step("2025-09-22T18:02:00", "x", "T1059"),
            _step("2025-09-22T18:03:00", "x", "T1059"),
        ],
    )
    steps = load_steps(tmp_path, "steps").records
    seq_steps = load_steps(tmp_path, "sequences").records
    rule = sequence_group_rule(seq_steps, steps)
    assert rule["multi_run_dirs"] == 1
    assert rule["dirs_at_maximal_block"] == 1
    assert rule["failure_count"] == 0


def test_variant_grid_reports_archive_and_bundle_steps() -> None:
    steps = _steps_in_tmp([_step("2025-09-22T18:00:00", "id")])
    rows = variant_grid(steps, ["c-1"], ["c-1"], steps)
    assert rows[0]["steps"] == 1 and rows[0]["archive_steps"] == 1
    assert rows[0]["chain"] == "shell:T1059"
    assert rows[0]["chain_full"] == "shell:T1059"


def test_granularity_lists_step_dirs_without_steps(tmp_path: Path) -> None:
    _write_steps(
        tmp_path / "steps" / "c-1" / "attacker/logs/attackmate.json",
        [_step("2025-09-22T18:00:00", "id")],
    )
    (tmp_path / "steps" / "c-2" / "attacker/logs").mkdir(parents=True)
    (tmp_path / "sequences" / "c-1" / "attacker/logs").mkdir(parents=True)
    got = granularity(load_steps(tmp_path, "steps").records, tmp_path, {})
    assert got["step_dirs"] == 2
    assert got["step_dirs_without_steps"] == ["c-2"]


def test_compare_bundles_detects_a_strict_line_subset(tmp_path: Path) -> None:
    small = tmp_path / "filtered.zip"
    large = tmp_path / "raw.zip"
    with zipfile.ZipFile(small, "w") as z:
        z.writestr("f/sequences/a/logs/log/syslog", "line1\n")
        z.writestr("f/sequences/a/attacker/logs/attackmate.json", "{}\n")
    with zipfile.ZipFile(large, "w") as z:
        z.writestr("r/sequences/a/logs/log/syslog", "line1\nline2\n")
        z.writestr("r/sequences/a/attacker/logs/attackmate.json", "{}\n")
        z.writestr("r/sequences/a/logs/log/collectd/collectd.log", "noise\n")
    got = compare_bundles(small, large)
    assert got["only_in_a"] == 0
    assert got["only_in_b"] == 1
    assert got["identical_crc"] == 1
    assert got["line_subset_violations"] == 0
    assert got["only_in_b_kinds"] == {"logs/log/collectd/collectd.log": 1}
