from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.siem import hec_ship
from scripts import acquire_corpus_sources as acquisition
from scripts import corpus_reingest as reingest
from scripts import lab_delete_cousins


def corpus_file(
    *,
    publisher: str = "mordor",
    test_id: str = "T1003.001/test-directory",
    declared_sourcetype: str | None = None,
    declared_source: str | None = None,
    fallback_epoch: float | None = None,
) -> reingest.CorpusFile:
    return reingest.CorpusFile(
        publisher,
        test_id,
        Path("/tmp/fixture.json"),
        Path("/tmp"),
        declared_sourcetype,
        declared_source,
        fallback_epoch,
    )


def test_reingest_preserves_xml_json_line_and_cloudtrail_bodies() -> None:
    xml = "<Event><System><Channel>Microsoft-Windows-Sysmon/Operational</Channel><Computer>WIN-01</Computer></System></Event>"
    json_event = {"Channel": "Security", "Computer": "WIN-02", "EventCode": 4624}
    line = "auditd: type=EXECVE msg=audit(1.0:2): argc=1"
    cloudtrail = {
        "eventSource": "iam.amazonaws.com",
        "eventName": "CreateUser",
        "recipientAccountId": "123456789012",
    }

    assert reingest.resolve_event(corpus_file(), xml).body == xml
    assert reingest.resolve_event(corpus_file(), json_event).body == json_event
    assert reingest.resolve_event(corpus_file(), line).body == line
    assert reingest.resolve_event(corpus_file(), cloudtrail).body == cloudtrail


def test_sourcetype_and_source_precedence() -> None:
    xml = "<Event><System><Channel>Security</Channel><Computer>WIN-01</Computer></System></Event>"
    declared = reingest.resolve_event(
        corpus_file(declared_sourcetype="publisher:declared", declared_source="publisher:source"),
        xml,
    )
    assert (declared.sourcetype, declared.source) == ("publisher:declared", "publisher:source")

    xml_channel = reingest.resolve_event(corpus_file(), xml)
    assert (xml_channel.sourcetype, xml_channel.source) == (
        "XmlWinEventLog",
        "XmlWinEventLog:Security",
    )

    json_channel = reingest.resolve_event(corpus_file(), {"Channel": "Security"})
    assert (json_channel.sourcetype, json_channel.source) == ("_json", "Security")

    cloudtrail = reingest.resolve_event(
        corpus_file(), {"eventSource": "iam.amazonaws.com", "eventName": "CreateUser"}
    )
    assert (cloudtrail.sourcetype, cloudtrail.source) == ("aws:cloudtrail", "aws_cloudtrail")

    unknown = reingest.resolve_event(corpus_file(), "plain line")
    assert (unknown.sourcetype, unknown.source) == ("raw", "raw")
    assert unknown.unknown_sourcetype


def test_host_precedence_and_unknown_count() -> None:
    xml = "<Event><System><Computer>WIN-XML</Computer></System></Event>"
    assert reingest.resolve_event(corpus_file(), xml).host == "WIN-XML"
    assert (
        reingest.resolve_event(corpus_file(), {"hostname": "host-a", "host": "host-b"}).host
        == "host-a"
    )
    assert (
        reingest.resolve_event(corpus_file(), {"recipientAccountId": "123456789012"}).host
        == "123456789012"
    )
    cloud_identity = reingest.resolve_event(
        corpus_file(), {"userIdentity": {"accountId": "987654321098"}}
    )
    assert cloud_identity.host == "987654321098"
    syslog = reingest.resolve_event(
        corpus_file(), "<34>1 2024-01-02T03:04:05Z syslog-01 app 1 ID47 - message"
    )
    assert syslog.host == "syslog-01"
    unknown = reingest.resolve_event(corpus_file(), "plain line")
    assert unknown.host == "unknown"
    assert unknown.unknown_host


def test_timestamp_fallback_is_counted() -> None:
    fallback = reingest.resolve_event(
        corpus_file(fallback_epoch=1_700_000_000), {"eventName": "ListUsers"}
    )
    assert fallback.epoch == 1_700_000_000
    assert fallback.date_fallback
    assert fallback.unknown_host

    own_time = reingest.resolve_event(
        corpus_file(fallback_epoch=1_700_000_000), {"timestamp": "2020-01-02T03:04:05Z"}
    )
    assert own_time.epoch == 1_577_934_245
    assert not own_time.date_fallback

    no_date = reingest.resolve_event(corpus_file(), "plain line")
    assert no_date.epoch is None

    generated = reingest.resolve_event(corpus_file(), {"timeGenerated": "2020-01-02T03:04:05Z"})
    assert generated.epoch == 1_577_934_245
    assert not generated.date_fallback

    windows = reingest.resolve_event(
        corpus_file(),
        '<Event><System><TimeCreated SystemTime="2020-01-02T03:04:05Z" /></System></Event>',
    )
    assert windows.epoch == 1_577_934_245
    assert not windows.date_fallback

    cloudtrail = reingest.resolve_event(
        corpus_file(),
        {
            "eventSource": "iam.amazonaws.com",
            "eventName": "CreateUser",
            "eventTime": "2020-01-02T03:04:05Z",
        },
    )
    assert cloudtrail.epoch == 1_577_934_245
    assert not cloudtrail.date_fallback

    rfc3164 = reingest.resolve_event(
        corpus_file(fallback_epoch=1_577_836_800), "<34>Jan 02 03:04:05 syslog-01 app: event"
    )
    assert rfc3164.epoch == 1_577_934_245
    assert rfc3164.date_fallback


def test_zeek_json_tsv_and_apache_times_are_event_times() -> None:
    zeek_json = reingest.resolve_event(corpus_file(), {"ts": 1_588_205_199.82437})
    assert zeek_json.epoch == pytest.approx(1_588_205_199.82437)
    assert not zeek_json.date_fallback

    zeek_tsv = reingest.resolve_event(corpus_file(), "1693976006.934436\tviolation\tprotocol\tIRC")
    assert zeek_tsv.epoch == pytest.approx(1_693_976_006.934436)
    assert not zeek_tsv.date_fallback

    apache = reingest.resolve_event(
        corpus_file(), '192.168.105.83 - - [11/Jul/2018:08:41:28 +0300] "GET / HTTP/1.1" 200 11444'
    )
    expected = dt.datetime(
        2018, 7, 11, 8, 41, 28, tzinfo=dt.timezone(dt.timedelta(hours=3))
    ).timestamp()
    assert apache.epoch == expected
    assert not apache.date_fallback


def test_yearless_event_uses_only_manifest_year() -> None:
    event = "\ufeff09/14 12:33:00 [MISC] [3448] DbFlag is set"
    dated = reingest.resolve_event(corpus_file(fallback_epoch=1_600_000_000), event)
    expected = dt.datetime(2020, 9, 14, 12, 33, tzinfo=dt.UTC).timestamp()
    assert dated.epoch == expected
    assert dated.date_fallback
    assert reingest.resolve_event(corpus_file(), event).epoch is None


def test_multiline_csv_records_keep_raw_body_and_resolve_system_time(tmp_path: Path) -> None:
    path = tmp_path / "evtx_data.csv"
    record = '1,2020-01-02 03:04:05.123456,"first line\nsecond line"'
    path.write_bytes(f"id,SystemTime,EventXML\n{record}\n".encode())
    item = reingest.CorpusFile("evtx_samples", "evtx_data", path, tmp_path)

    events = list(reingest._iter_file_events(item))

    assert events == [record]
    resolved = reingest.resolve_event(item, events[0])
    assert resolved.body == record
    assert resolved.epoch == pytest.approx(1_577_934_245.123456)


def test_no_year_file_counts_missing_time_and_is_excluded(tmp_path: Path) -> None:
    path = tmp_path / "netlogon.log"
    path.write_text("09/14 12:33:00 [MISC] one\n09/14 12:33:02 [INIT] two\n", encoding="utf-8")
    item = reingest.CorpusFile("evtx_samples", "netlogon", path, tmp_path)

    scan = reingest.scan_inputs({"evtx_samples": [item]})

    assert scan["totals"]["missing_time"] == 2
    assert scan["totals"]["excluded_missing_time"] == 2
    assert scan["items"][reingest.p5_item_id("evtx_samples", "netlogon")]["missing_time"] == 2
    assert scan["items"][reingest.p5_item_id("evtx_samples", "netlogon")]["shipped_events"] == 0
    assert scan["items"][reingest.p5_item_id("evtx_samples", "netlogon")]["excluded_rows"] == {
        "no_year": 2
    }
    assert scan["read_errors"][0]["reason"] == "no_year"
    assert not reingest._ship_gate_blocked(scan, {}, False, None, None)


def test_no_year_file_excludes_its_dated_rows_too(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "mixed_netlogon.log"
    path.write_text(
        '{"timestamp":"2020-09-14T12:32:00Z","eventName":"Before"}\n'
        "09/14 12:33:00 [MISC] no year\n",
        encoding="utf-8",
    )
    item = reingest.CorpusFile("evtx_samples", "netlogon", path, tmp_path)
    scan = reingest.scan_inputs({"evtx_samples": [item]})
    monkeypatch.setattr(
        reingest, "ship_batch", lambda *args, **kwargs: pytest.fail("no_year file was shipped")
    )
    excluded = {(row["publisher"], row["path"]) for row in scan["read_errors"]}

    assert scan["items"][reingest.p5_item_id("evtx_samples", "netlogon")]["shipped_events"] == 0
    assert scan["items"][reingest.p5_item_id("evtx_samples", "netlogon")]["excluded_rows"] == {
        "no_year": 2
    }
    assert reingest.ship_inputs({"evtx_samples": [item]}, excluded) == {}


def test_untimed_file_is_counted_and_excluded(tmp_path: Path) -> None:
    path = tmp_path / "loaded_scripts.log"
    path.write_text('{"@stream":"loaded_scripts","name":"script.zeek"}\n', encoding="utf-8")
    item = reingest.CorpusFile("mordor", "loaded_scripts", path, tmp_path)

    scan = reingest.scan_inputs({"mordor": [item]})

    assert scan["totals"]["missing_time"] == 1
    assert scan["totals"]["excluded_missing_time"] == 1
    item_id = reingest.p5_item_id("mordor", "loaded_scripts")
    assert scan["items"][item_id]["shipped_events"] == 0
    assert scan["items"][item_id]["excluded_rows"] == {"missing_time": 1}
    assert scan["read_errors"] == []
    assert not reingest._ship_gate_blocked(scan, {}, False, None, None)


def test_mixed_timestamp_file_ships_dated_rows_and_counts_untimed_rows(
    tmp_path: Path, monkeypatch: Any
) -> None:
    path = tmp_path / "mixed.jsonl"
    dated = {"eventName": "ListUsers", "timestamp": "2020-01-02T03:04:05Z"}
    untimed = {"eventName": "DescribeUsers"}
    path.write_text(f"{json.dumps(dated)}\n{json.dumps(untimed)}\n", encoding="utf-8")
    item = reingest.CorpusFile("mordor", "mixed", path, tmp_path)
    already_shipped_path = tmp_path / "already_shipped.jsonl"
    already_shipped_path.write_text(
        '{"eventName":"CreateUser","timestamp":"2020-01-02T03:04:05Z"}\n',
        encoding="utf-8",
    )
    already_shipped = reingest.CorpusFile(
        "mordor", "already-shipped", already_shipped_path, tmp_path
    )
    scan = reingest.scan_inputs({"mordor": [item]})
    sent: list[list[dict[str, Any] | str]] = []
    monkeypatch.setattr(
        reingest,
        "ship_batch",
        lambda events, **kwargs: sent.append(events) or {"ok": True},
    )

    shipped = reingest.ship_inputs(
        {"mordor": [item, already_shipped]},
        included_files={("mordor", "mixed.jsonl")},
    )

    item_id = reingest.p5_item_id("mordor", "mixed")
    assert scan["items"][item_id]["events"] == 2
    assert scan["items"][item_id]["shipped_events"] == 1
    assert scan["items"][item_id]["excluded_rows"] == {"missing_time": 1}
    assert scan["read_errors"] == []
    assert shipped == {item_id: 1}
    assert sent == [[dated]]


def test_p5_item_is_opaque_and_stable() -> None:
    first = reingest.p5_item_id("attack_data", "attack_techniques/T1003.001/test")
    assert first == reingest.p5_item_id("attack_data", "attack_techniques/T1003.001/test")
    assert len(first) == 16
    assert all(character in "0123456789abcdef" for character in first)
    assert first != reingest.p5_item_id("attack_data", "attack_techniques/T1003.001/other")


def test_leak_scan_catches_technique_test_directory_and_publisher() -> None:
    item = corpus_file(publisher="mordor", test_id="T1003.001/test-directory")
    assert reingest.value_has_leak("T1003.001", item)
    assert reingest.value_has_leak("source:test-directory", item)
    assert reingest.value_has_leak("Mordor", item)
    assert not reingest.value_has_leak("XmlWinEventLog:Security", item)


def test_technique_names_are_removed_from_index_fields() -> None:
    item = corpus_file(test_id="T1003.001/credential-access-case")
    resolved = reingest.resolve_event(item, "plain line")
    assert resolved.sourcetype == "raw"
    assert resolved.source == "raw"
    assert resolved.host == "unknown"
    assert not resolved.residual_leak


def test_test_directory_names_are_removed_from_source_and_host() -> None:
    item = corpus_file(
        test_id="named-test-directory/case",
        declared_sourcetype="raw",
        declared_source="/tmp/named-test-directory/event.log",
    )
    resolved = reingest.resolve_event(
        item, {"hostname": "named-test-directory.example", "timestamp": "2020-01-01T00:00:00Z"}
    )
    assert resolved.source == "raw"
    assert resolved.host == "raw"
    assert not resolved.residual_leak


def test_filename_names_are_removed_from_source_and_host(tmp_path: Path) -> None:
    event_path = tmp_path / "named-file-case.jsonl"
    event_path.write_text("{}\n", encoding="utf-8")
    item = reingest.CorpusFile(
        "mordor",
        "ordinary-test",
        event_path,
        tmp_path,
        declared_sourcetype="raw",
        declared_source="/tmp/named-file-case.jsonl",
    )

    resolved = reingest.resolve_event(
        item, {"hostname": "named-file-case.example", "timestamp": "2020-01-01T00:00:00Z"}
    )

    assert resolved.source == "raw"
    assert resolved.host == "raw"
    assert not resolved.residual_leak


def test_publisher_name_is_removed_from_sourcetype_and_source() -> None:
    item = corpus_file(
        publisher="mordor",
        test_id="ordinary-test",
        declared_sourcetype="mordor:events",
        declared_source="mordor:ordinary-test",
    )
    resolved = reingest.resolve_event(item, "plain line")
    assert resolved.sourcetype == "raw"
    assert resolved.source == "raw"
    assert not resolved.residual_leak


def test_ship_batch_keeps_old_envelope_for_existing_callers(monkeypatch: Any) -> None:
    requests: list[dict[str, Any]] = []

    class Response:
        status_code = 200

    def post(*args: Any, **kwargs: Any) -> Response:
        requests.append(kwargs)
        return Response()

    monkeypatch.setattr(hec_ship.httpx, "post", post)
    result = hec_ship.ship_batch(
        ["raw event"],
        sourcetype="raw",
        host="host-a",
        index="portal5_lab",
        event_time=1.0,
        evidence_origin="corpus:test",
        evidence_provenance="external_corpus",
    )
    envelope = json.loads(requests[0]["content"])
    assert result["ok"]
    assert envelope == {
        "time": 1.0,
        "host": "host-a",
        "source": "portal5:corpus:test",
        "sourcetype": "raw",
        "index": "portal5_lab",
        "event": "raw event",
        "fields": {"evidence_origin": "corpus:test", "evidence_provenance": "external_corpus"},
    }


def test_ship_batch_custom_fields_replace_portal_evidence_fields(monkeypatch: Any) -> None:
    requests: list[dict[str, Any]] = []

    class Response:
        status_code = 200

    monkeypatch.setattr(
        hec_ship.httpx, "post", lambda *args, **kwargs: (requests.append(kwargs), Response())[1]
    )
    hec_ship.ship_batch(
        ["raw event"],
        sourcetype="_json",
        source="Security",
        host="host-a",
        index="labelled_corpus",
        event_time=1.0,
        evidence_origin="must-not-appear",
        fields={"p5_item": "0123456789abcdef"},
    )
    envelope = json.loads(requests[0]["content"])
    assert envelope["source"] == "Security"
    assert envelope["fields"] == {"p5_item": "0123456789abcdef"}
    assert "evidence_origin" not in envelope["fields"]


def test_delete_cousins_revokes_temporary_role_in_finally(monkeypatch: Any) -> None:
    before = {"raw_count": 2, "tstats_count": 2, "reconciled": True}
    after = {"raw_count": 0, "tstats_count": 0, "reconciled": True}
    inventories = iter([before, after])
    calls: list[str] = []
    roles = {"roles": ["admin"], "imported_roles": []}

    monkeypatch.setattr(lab_delete_cousins, "cousin_inventory", lambda: next(inventories))
    monkeypatch.setattr(lab_delete_cousins, "account_roles", lambda username="admin": roles)
    monkeypatch.setattr(lab_delete_cousins, "role_exists", lambda role: False)
    monkeypatch.setattr(lab_delete_cousins, "create_delete_role", lambda: "p5_temp_delete_test")
    monkeypatch.setattr(
        lab_delete_cousins, "add_imported_role", lambda username, role: calls.append("grant")
    )
    monkeypatch.setattr(
        lab_delete_cousins, "export_rows", lambda search: calls.append("delete") or []
    )
    monkeypatch.setattr(
        lab_delete_cousins, "remove_imported_role", lambda username, role: calls.append("revoke")
    )
    monkeypatch.setattr(lab_delete_cousins, "delete_role", lambda role: calls.append("remove-role"))

    result = lab_delete_cousins.delete_cousins()
    assert result["after"]["raw_count"] == 0
    assert calls == ["grant", "delete", "revoke", "remove-role"]


def test_delete_cousins_revokes_role_when_delete_search_fails(monkeypatch: Any) -> None:
    before = {"raw_count": 1, "tstats_count": 1, "reconciled": True}
    inventories = iter([before])
    calls: list[str] = []

    monkeypatch.setattr(lab_delete_cousins, "cousin_inventory", lambda: next(inventories))
    monkeypatch.setattr(
        lab_delete_cousins,
        "account_roles",
        lambda username="admin": {"roles": ["admin"], "imported_roles": []},
    )
    monkeypatch.setattr(lab_delete_cousins, "role_exists", lambda role: False)
    monkeypatch.setattr(lab_delete_cousins, "create_delete_role", lambda: "p5_temp_delete_test")
    monkeypatch.setattr(
        lab_delete_cousins, "add_imported_role", lambda username, role: calls.append("grant")
    )

    def fail_delete(search: str) -> list[dict[str, Any]]:
        calls.append("delete")
        raise RuntimeError("search failed")

    monkeypatch.setattr(lab_delete_cousins, "export_rows", fail_delete)
    monkeypatch.setattr(
        lab_delete_cousins, "remove_imported_role", lambda username, role: calls.append("revoke")
    )
    monkeypatch.setattr(lab_delete_cousins, "delete_role", lambda role: calls.append("remove-role"))

    try:
        lab_delete_cousins.delete_cousins()
    except RuntimeError as exc:
        assert str(exc) == "search failed"
    else:
        raise AssertionError("delete search failure was swallowed")
    assert calls == ["grant", "delete", "revoke", "remove-role"]


def test_delete_cousins_uses_the_builtin_role_and_never_deletes_it(monkeypatch: Any) -> None:
    """Splunk refuses to put can_delete on a new role for an admin without it; use the built-in."""
    inventories = iter(
        [
            {"raw_count": 2, "tstats_count": 2, "reconciled": True},
            {"raw_count": 0, "tstats_count": 0, "reconciled": True},
        ]
    )
    calls: list[str] = []
    monkeypatch.setattr(lab_delete_cousins, "cousin_inventory", lambda: next(inventories))
    monkeypatch.setattr(
        lab_delete_cousins,
        "account_roles",
        lambda username="admin": {"roles": ["admin"], "imported_roles": []},
    )
    monkeypatch.setattr(lab_delete_cousins, "role_exists", lambda role: role == "can_delete")
    monkeypatch.setattr(
        lab_delete_cousins, "create_delete_role", lambda: calls.append("create") or "x"
    )
    monkeypatch.setattr(
        lab_delete_cousins,
        "add_imported_role",
        lambda username, role: calls.append(f"grant:{role}"),
    )
    monkeypatch.setattr(
        lab_delete_cousins, "export_rows", lambda search: calls.append("delete") or []
    )
    monkeypatch.setattr(
        lab_delete_cousins,
        "remove_imported_role",
        lambda username, role: calls.append(f"revoke:{role}"),
    )
    monkeypatch.setattr(lab_delete_cousins, "delete_role", lambda role: calls.append("remove-role"))

    lab_delete_cousins.delete_cousins()
    assert calls == ["grant:can_delete", "delete", "revoke:can_delete"]


def test_scan_inputs_counts_fallback_unknown_and_residual_leak(tmp_path: Path) -> None:
    event_path = tmp_path / "sample.jsonl"
    event_path.write_text('{"eventName":"ListUsers"}\n', encoding="utf-8")
    item = reingest.CorpusFile(
        "mordor",
        "test-directory",
        event_path,
        tmp_path,
        fallback_epoch=1_700_000_000,
    )
    report = reingest.scan_inputs({"mordor": [item]})
    assert report["totals"] == {
        "events": 1,
        "shipped_events": 1,
        "excluded_events": 0,
        "excluded_missing_time": 0,
        "unknown_sourcetype": 1,
        "unknown_host": 1,
        "date_fallback": 1,
        "missing_time": 0,
        "source_replacements": 1,
        "host_replacements": 0,
        "sourcetype_replacements": 1,
        "residual_leaks": 0,
    }
    assert report["by_publisher"] == {"mordor": 1}
    assert report["by_host"] == {"unknown": 1}
    assert report["unknown_hosts_by_sourcetype"] == {"_json": 1}
    assert report["date_fallback_by_format"] == {"json": 1}
    item_id = reingest.p5_item_id("mordor", "test-directory")
    assert report["items"][item_id]["date_fallback"] == 1


def test_scan_inputs_skips_zeek_metadata_lines(tmp_path: Path) -> None:
    path = tmp_path / "conn.log"
    path.write_text(
        "#separator \\x09\n#fields\tts\tuid\n#types\ttime\tstring\n1693976006.934436\tuid-1\n",
        encoding="utf-8",
    )
    item = reingest.CorpusFile("mordor", "zeek", path, tmp_path)

    scan = reingest.scan_inputs({"mordor": [item]})

    assert scan["totals"]["events"] == 1
    assert scan["totals"]["missing_time"] == 0
    assert scan["items"][reingest.p5_item_id("mordor", "zeek")]["events"] == 1


def test_tree_reader_excludes_documentation_and_tooling_trees(tmp_path: Path) -> None:
    excluded_paths = [
        "docs/images/users.csv",
        "scripts/book/tool.json",
        "notebooks/examples/example.json",
        "templates/events/template.json",
    ]
    for relative in [*excluded_paths, "datasets/case/events.jsonl"]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"timestamp":"2020-01-02T03:04:05Z"}\n', encoding="utf-8")

    files = list(reingest._tree_files("mordor", tmp_path))

    assert [item.path.relative_to(tmp_path).as_posix() for item in files] == [
        "datasets/case/events.jsonl"
    ]
    assert {item.path.relative_to(tmp_path).as_posix() for item in files}.isdisjoint(excluded_paths)


def test_scan_merges_valid_files_from_one_item(tmp_path: Path) -> None:
    files = []
    for name in ("first.jsonl", "second.jsonl"):
        path = tmp_path / name
        path.write_text(
            '{"eventName":"ListUsers","timestamp":"2020-01-01T00:00:00Z"}\n',
            encoding="utf-8",
        )
        files.append(reingest.CorpusFile("mordor", "one-test", path, tmp_path))

    scan = reingest.scan_inputs({"mordor": files})

    item_id = reingest.p5_item_id("mordor", "one-test")
    assert scan["totals"]["events"] == 2
    assert scan["items"][item_id]["events"] == 2
    assert {file["path"] for file in scan["items"][item_id]["data_files"]} == {
        "first.jsonl",
        "second.jsonl",
    }


def _configure_ship_main(
    monkeypatch: Any,
    tmp_path: Path,
    root: Path,
    files: list[reingest.CorpusFile],
    shipped: list[set[tuple[str, str]]],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "corpus_reingest.py",
            "--ship",
            "--sources-root",
            str(tmp_path / "sources"),
            "--corpora-root",
            str(tmp_path / "corpora"),
            "--output-root",
            str(tmp_path / "reports"),
        ],
    )
    monkeypatch.setattr(reingest, "_roots_from_args", lambda args: ({"mordor": root}, set()))
    monkeypatch.setattr(
        reingest,
        "prefer_pinned_siblings",
        lambda roots, *args: (dict(roots), {"mordor": {"root": str(root), "source": "test"}}),
    )
    monkeypatch.setattr(
        reingest,
        "source_facts",
        lambda name, path: {
            "status": "available_local",
            "path": str(path),
            "commit": "a" * 40,
            "expected_commit": "a" * 40,
            "dirty_paths": 0,
            "commit_matches_expected": True,
        },
    )
    monkeypatch.setattr(reingest, "_report_blocked_sources", lambda facts: False)
    monkeypatch.setattr(reingest, "publisher_files", lambda publisher, path: files)
    monkeypatch.setattr(reingest, "write_report", lambda output_root, *args: output_root)
    monkeypatch.setattr(
        reingest,
        "ship_inputs",
        lambda files_by_publisher, excluded_files, included_files=None: (
            shipped.append(excluded_files) or {}
        ),
    )


def test_previous_plan_file_sets_are_disjoint(tmp_path: Path) -> None:
    plan = tmp_path / "items.json"
    plan.write_text(
        json.dumps(
            {
                "items": {
                    "a": {
                        "publisher": "mordor",
                        "data_files": [{"path": "sent.jsonl"}, {"path": "excluded.jsonl"}],
                        "excluded_files": [{"path": "excluded.jsonl"}],
                    },
                    "b": {
                        "publisher": "evtx_samples",
                        "data_files": [{"path": "sent.evtx"}],
                        "excluded_files": [{"path": "missing.evtx"}],
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    excluded, shipped = reingest.previous_plan_file_sets(plan)

    assert excluded == {
        ("mordor", "excluded.jsonl"),
        ("evtx_samples", "missing.evtx"),
    }
    assert shipped == {("mordor", "sent.jsonl"), ("evtx_samples", "sent.evtx")}
    assert excluded.isdisjoint(shipped)


def test_ship_only_previously_excluded_uses_the_plan_file_set(
    tmp_path: Path, monkeypatch: Any
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    path = root / "recovered.jsonl"
    path.write_text('{"timestamp":"2020-01-01T00:00:00Z"}\n', encoding="utf-8")
    item = reingest.CorpusFile("mordor", "recovered", path, root)
    plan = tmp_path / "old-items.json"
    plan.write_text(
        json.dumps(
            {
                "items": {
                    reingest.p5_item_id("mordor", "recovered"): {
                        "publisher": "mordor",
                        "data_files": [{"path": "recovered.jsonl"}],
                        "excluded_files": [{"path": "recovered.jsonl", "reason": "missing_time"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    shipped: list[set[tuple[str, str]]] = []
    _configure_ship_main(monkeypatch, tmp_path, root, [item], shipped)
    included: list[set[tuple[str, str]] | None] = []
    monkeypatch.setattr(
        reingest,
        "ship_inputs",
        lambda files_by_publisher, excluded_files, included_files: (
            included.append(included_files) or {}
        ),
    )
    sys.argv.extend(["--only-previously-excluded", "--items", str(plan)])

    result = reingest.main()

    assert result == 0
    assert included == [{("mordor", "recovered.jsonl")}]


def test_verify_uses_shippable_event_count(tmp_path: Path, monkeypatch: Any) -> None:
    item_id = reingest.p5_item_id("mordor", "mixed")
    legacy_item_id = reingest.p5_item_id("mordor", "legacy")
    no_year_item_id = reingest.p5_item_id("evtx_samples", "netlogon")
    plan = tmp_path / "items.json"
    plan.write_text(
        json.dumps(
            {
                "items": {
                    item_id: {
                        "events": 5,
                        "missing_time": 1,
                        "shipped_events": 4,
                    },
                    legacy_item_id: {"events": 10, "missing_time": 3},
                    no_year_item_id: {
                        "events": 2,
                        "missing_time": 2,
                        "excluded_files": [{"reason": "no_year"}],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        reingest.lab_delete_cousins,
        "export_rows",
        lambda query: [
            {"p5_item": item_id, "count": 4},
            {"p5_item": legacy_item_id, "count": 7},
        ],
    )

    assert reingest.verify_plan(plan) == {
        "ok": True,
        "mismatches": {},
        "extra_p5_items": [],
    }


def test_upstream_missing_file_does_not_block_ship(tmp_path: Path, monkeypatch: Any) -> None:
    root = tmp_path / "source"
    _init_repo(root)
    item = reingest.CorpusFile("mordor", "missing-upstream-test", root / "absent.jsonl", root)
    shipped: list[set[tuple[str, str]]] = []
    _configure_ship_main(monkeypatch, tmp_path, root, [item], shipped)

    result = reingest.main()

    assert result == 0
    assert shipped == [{("mordor", "absent.jsonl")}]


def test_acquisition_gap_blocks_ship(tmp_path: Path, monkeypatch: Any) -> None:
    root = tmp_path / "source"
    _init_repo(root)
    missing = root / "tracked-but-missing.jsonl"
    missing.write_text('{"timestamp":"2020-01-01T00:00:00Z"}\n', encoding="utf-8")
    _commit_all(root, "add tracked input")
    missing.unlink()
    item = reingest.CorpusFile("mordor", "acquisition-gap-test", missing, root)
    shipped: list[set[tuple[str, str]]] = []
    _configure_ship_main(monkeypatch, tmp_path, root, [item], shipped)

    result = reingest.main()

    assert result == 2
    assert shipped == []


def test_unparseable_file_does_not_block_ship(tmp_path: Path, monkeypatch: Any) -> None:
    root = tmp_path / "source"
    _init_repo(root)
    path = root / "malformed.evtx"
    path.write_bytes(b"fixture")
    _commit_all(root, "add malformed EVTX")
    item = reingest.CorpusFile("mordor", "malformed-test", path, root)
    parse_calls: list[Path] = []
    shipped: list[set[tuple[str, str]]] = []

    def fail_after_one(event_path: Path) -> Any:
        parse_calls.append(event_path)
        yield "<Event><System><Channel>Security</Channel></System></Event>"
        raise ValueError("malformed record")

    monkeypatch.setattr(reingest, "iter_evtx_text", fail_after_one)
    _configure_ship_main(monkeypatch, tmp_path, root, [item], shipped)

    result = reingest.main()

    assert result == 0
    assert shipped == [{("mordor", "malformed.evtx")}]
    assert parse_calls == [path]


def test_evtx_parse_failure_is_atomic_excluded_from_ship_and_reported(
    tmp_path: Path, monkeypatch: Any
) -> None:
    root = tmp_path / "evtx_samples"
    _init_repo(root)
    bad_path = root / "malformed.evtx"
    bad_path.write_bytes(b"fixture")
    gap_path = root / "tracked-gap.evtx"
    gap_path.write_bytes(b"tracked")
    _commit_all(root, "add EVTX fixtures")
    gap_path.unlink()
    items = [
        reingest.CorpusFile("evtx_samples", "malformed-test", bad_path, root),
        reingest.CorpusFile("evtx_samples", "upstream-missing-test", root / "absent.evtx", root),
        reingest.CorpusFile("evtx_samples", "acquisition-gap-test", gap_path, root),
    ]
    parse_calls: list[Path] = []
    tracked_calls: list[Path] = []
    xml = "<Event><System><Channel>Security</Channel><Computer>WIN-01</Computer></System></Event>"

    def fail_after_one(path: Path) -> Any:
        parse_calls.append(path)
        yield xml
        raise ValueError("malformed record")

    tracked_files = reingest._tracked_files
    monkeypatch.setattr(reingest, "iter_evtx_text", fail_after_one)
    monkeypatch.setattr(
        reingest,
        "_tracked_files",
        lambda path: tracked_calls.append(path) or tracked_files(path),
    )

    scan = reingest.scan_inputs({"evtx_samples": items})

    assert scan["totals"].get("events", 0) == 0
    assert scan["by_publisher"] == {}
    assert tracked_calls == [root.resolve()]
    assert parse_calls == [bad_path]
    assert {row["reason"] for row in scan["read_errors"]} == {
        "unparseable",
        "upstream_missing",
        "acquisition_gap",
    }
    for row in scan["read_errors"]:
        item_id = reingest.p5_item_id(row["publisher"], row["test_id"])
        assert scan["items"][item_id]["excluded_files"] == [
            {"path": row["path"], "reason": row["reason"], "error": row["error"]}
        ]

    excluded = {(row["publisher"], row["path"]) for row in scan["read_errors"]}
    monkeypatch.setattr(
        reingest, "ship_batch", lambda *args, **kwargs: pytest.fail("unexpected ship")
    )
    assert reingest.ship_inputs({"evtx_samples": items}, excluded) == {}
    assert parse_calls == [bad_path]

    report_dir = reingest.write_report(
        tmp_path / "reports",
        {"evtx_samples": root},
        scan,
        {
            "evtx_samples": {
                "status": "available_local",
                "commit": "a" * 40,
                "expected_commit": "a" * 40,
                "dirty_paths": 0,
            }
        },
        None,
        {},
        {},
        None,
    )
    items_doc = json.loads((report_dir / "items.json").read_text(encoding="utf-8"))
    exclusions = [entry for item in items_doc["items"].values() for entry in item["excluded_files"]]
    assert {entry["reason"] for entry in exclusions} == {
        "unparseable",
        "upstream_missing",
        "acquisition_gap",
    }
    fidelity = (report_dir / "fidelity.md").read_text(encoding="utf-8")
    assert "### Source files excluded from this run" in fidelity
    assert "`unparseable` (ValueError)" in fidelity
    assert "`upstream_missing` (missing_file)" in fidelity
    assert "`acquisition_gap` (missing_file)" in fidelity


def test_evtx_reader_uses_python_evtx_xml_records(tmp_path: Path, monkeypatch: Any) -> None:
    import types

    # A stand-in module: python-evtx lives in the optional `corpora` extra, which CI's
    # `.[dev]` install does not include, and the reader's behaviour is what's under test.
    evtx_pkg = types.ModuleType("Evtx")
    evtx_module = types.ModuleType("Evtx.Evtx")
    evtx_pkg.Evtx = evtx_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "Evtx", evtx_pkg)
    monkeypatch.setitem(sys.modules, "Evtx.Evtx", evtx_module)

    class Record:
        def xml(self) -> str:
            return "<Event><System><Channel>Security</Channel></System></Event>"

    class Source:
        def __init__(self, path: str) -> None:
            assert path == str(tmp_path / "sample.evtx")

        def __enter__(self) -> Source:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def records(self) -> list[Record]:
            return [Record()]

    (tmp_path / "sample.evtx").write_bytes(b"fixture")
    monkeypatch.setattr(evtx_module, "Evtx", Source, raising=False)
    assert list(reingest.iter_evtx_text(tmp_path / "sample.evtx")) == [
        "<Event><System><Channel>Security</Channel></System></Event>"
    ]


def test_ship_iterator_uses_python_evtx_xml_records(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "sample.evtx"
    path.write_bytes(b"fixture")
    body = (
        "<Event><System><Channel>Security</Channel><TimeCreated "
        'SystemTime="2020-01-02T03:04:05Z"/></System></Event>'
    )
    item = reingest.CorpusFile("evtx_samples", "Security/4624", path, tmp_path)
    monkeypatch.setattr(reingest, "iter_evtx_text", lambda _: iter([body]))

    resolved = list(reingest._iter_resolved(iter([item])))

    assert len(resolved) == 1
    assert resolved[0][1].body == body


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def test_dry_run_refuses_dirty_source_checkout(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    source_root = tmp_path / "sources"
    dirty_repo = source_root / "attack_data"
    dirty_repo.mkdir(parents=True)
    _git(dirty_repo, "init")
    _git(dirty_repo, "config", "user.name", "Unit Test")
    _git(dirty_repo, "config", "user.email", "unit@example.invalid")
    tracked = dirty_repo / "tracked.txt"
    tracked.write_text("clean baseline\n", encoding="utf-8")
    _git(dirty_repo, "add", "tracked.txt")
    _git(dirty_repo, "commit", "-m", "baseline")
    (dirty_repo / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
    output_root = tmp_path / "reports"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "corpus_reingest.py",
            "--dry-run",
            "--sources-root",
            str(source_root),
            "--corpora-root",
            str(tmp_path / "corpora"),
            "--output-root",
            str(output_root),
        ],
    )

    assert reingest.main() == 2
    assert '"mode": "BLOCKED"' in capsys.readouterr().out
    assert not output_root.exists()
    assert (dirty_repo / "dirty.txt").read_text(encoding="utf-8") == "uncommitted\n"


def test_acquisition_clones_alongside_dirty_checkout(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init")
    _git(upstream, "config", "user.name", "Unit Test")
    _git(upstream, "config", "user.email", "unit@example.invalid")
    (upstream / "payload.txt").write_text("pinned\n", encoding="utf-8")
    _git(upstream, "add", "payload.txt")
    _git(upstream, "commit", "-m", "pinned")
    commit = _git(upstream, "rev-parse", "HEAD")
    target = tmp_path / "sources" / "attack_data"
    target.mkdir(parents=True)
    _git(target, "init")
    _git(target, "config", "user.name", "Unit Test")
    _git(target, "config", "user.email", "unit@example.invalid")
    (target / "tracked.txt").write_text("clean baseline\n", encoding="utf-8")
    _git(target, "add", "tracked.txt")
    _git(target, "commit", "-m", "baseline")
    (target / "local-only.txt").write_text("keep\n", encoding="utf-8")
    dirty_status = _git(target, "status", "--porcelain")
    spec = acquisition.SourceSpec("attack_data", str(upstream), commit, target)

    result = acquisition.acquire_checkout(spec)

    sibling = acquisition.sibling_checkout(target, commit)
    assert result["status"] == "acquired"
    assert Path(result["path"]) == sibling
    assert acquisition.inspect_checkout(sibling, commit)["status"] == "verified"
    assert (target / "local-only.txt").read_text(encoding="utf-8") == "keep\n"
    assert _git(target, "status", "--porcelain") == dirty_status


def test_acquisition_verification_rejects_lfs_pointers(tmp_path: Path, monkeypatch: Any) -> None:
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Unit Test")
    _git(repo, "config", "user.email", "unit@example.invalid")
    pointer = repo / "sample.evtx"
    pointer.write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:0123456789abcdef\nsize 2048\n",
        encoding="utf-8",
    )
    _git(repo, "add", "sample.evtx")
    _git(repo, "commit", "-m", "pointer")
    commit = _git(repo, "rev-parse", "HEAD")
    git = acquisition._git

    def without_git_lfs(
        root: Path, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ("lfs", "ls-files", "--json"):
            return subprocess.CompletedProcess(args, 1, "", "git-lfs unavailable")
        return git(root, *args, env=env)

    monkeypatch.setattr(acquisition, "_git", without_git_lfs)

    result = acquisition.inspect_checkout(repo, commit)

    assert result["status"] == "lfs_incomplete"
    assert result["upstream_defects"] == []


def _commit_all(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _init_repo(root: Path, *, dirty: bool = False) -> str:
    root.mkdir(parents=True)
    _git(root, "init")
    _git(root, "config", "user.name", "Unit Test")
    _git(root, "config", "user.email", "unit@example.invalid")
    (root / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    commit = _commit_all(root, "baseline")
    if dirty:
        (root / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
    return commit


def _clone(source: Path, target: Path) -> None:
    # A host-wide `git lfs install` (CI runners have one) would smudge real content on
    # checkout; the pinned-clone fixtures need the pointer files the real failure had.
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
    for argv in (
        ["git", "clone", "-q", "--no-checkout", str(source), str(target)],
        ["git", "-C", str(target), "checkout", "-q", "--detach", "HEAD"],
    ):
        subprocess.run(argv, check=True, capture_output=True, text=True, env=env)


def _lfs_upstream(root: Path, payload: bytes = b"real-lfs-payload\n") -> str:
    root.mkdir(parents=True)
    _git(root, "init")
    _git(root, "config", "user.name", "Unit Test")
    _git(root, "config", "user.email", "unit@example.invalid")
    _git(root, "lfs", "install", "--local")
    (root / ".gitattributes").write_text(
        "*.bin filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8"
    )
    (root / "payload.bin").write_bytes(payload)
    return _commit_all(root, "lfs object")


def _git_lfs_available() -> bool:
    probe = subprocess.run(["git", "lfs", "version"], capture_output=True, check=False)
    return probe.returncode == 0


def test_report_stamp_uses_twelve_char_commits_and_fits_filename_limit() -> None:
    facts = {name: {"commit": commit} for name, commit in reingest.EXPECTED_COMMITS.items()}

    stamp = reingest._stamp(facts)

    assert len(stamp.encode()) < 255
    for name, fact in facts.items():
        assert f"{name}-{fact['commit'][:12]}" in stamp
        assert fact["commit"] not in stamp
    assert len(set(stamp.split("__")[1:])) == len(facts)
    assert reingest._stamp({"attack_data": {}}).endswith("__attack_data-missing")


def test_source_roots_prefer_verified_pinned_sibling(tmp_path: Path, monkeypatch: Any) -> None:
    sources = tmp_path / "sources"
    corpora = tmp_path / "corpora"
    attack = _init_repo(sources / "attack_data", dirty=True)
    attack_sibling = acquisition.sibling_checkout(sources / "attack_data", attack)
    _clone(sources / "attack_data", attack_sibling)
    mordor = _init_repo(sources / "mordor")
    evtx = _init_repo(sources / "evtx_samples", dirty=True)
    evtx_sibling = acquisition.sibling_checkout(sources / "evtx_samples", evtx)
    _clone(sources / "evtx_samples", evtx_sibling)
    (evtx_sibling / "uncommitted.txt").write_text("dirty\n", encoding="utf-8")
    evtx_mitre = _init_repo(sources / "evtx_mitre")
    repo = corpora / "invictus_ir_aws_dataset" / "repo"
    invictus = _init_repo(repo, dirty=True)
    invictus_sibling = acquisition.sibling_checkout(repo, invictus)
    _clone(repo, invictus_sibling)
    monkeypatch.setattr(
        acquisition,
        "SOURCES",
        {
            "attack_data": ("unused", attack),
            "mordor": ("unused", mordor),
            "evtx_samples": ("unused", evtx),
            "evtx_mitre": ("unused", evtx_mitre),
            "invictus_ir": ("unused", invictus),
        },
    )
    roots = reingest.default_roots(sources, corpora)

    resolved, selections = reingest.prefer_pinned_siblings(roots, sources, corpora, set())

    assert resolved["attack_data"] == attack_sibling
    assert resolved["mordor"] == roots["mordor"]
    assert resolved["evtx_samples"] == roots["evtx_samples"]
    assert resolved["evtx_mitre"] == roots["evtx_mitre"]
    assert resolved["invictus_ir"] == invictus_sibling / "CloudTrail"
    assert selections["attack_data"] == {
        "root": str(attack_sibling),
        "source": "pinned_sibling",
        "pinned_commit": attack[:12],
    }
    assert selections["mordor"]["source"] == "default"
    overridden, _ = reingest.prefer_pinned_siblings(roots, sources, corpora, {"attack_data"})
    assert overridden["attack_data"] == roots["attack_data"]


def test_dry_run_prefers_pinned_sibling_and_records_it(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    sources = tmp_path / "sources"
    main_repo = sources / "attack_data"
    _init_repo(main_repo)
    (main_repo / "events.jsonl").write_text('{"eventName":"ListUsers"}\n', encoding="utf-8")
    commit = _commit_all(main_repo, "events")
    sibling = acquisition.sibling_checkout(main_repo, commit)
    _clone(main_repo, sibling)
    (main_repo / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
    monkeypatch.setattr(reingest, "EXPECTED_COMMITS", {"attack_data": commit})
    patched_sources = dict(acquisition.SOURCES)
    patched_sources["attack_data"] = ("unused", commit)
    monkeypatch.setattr(acquisition, "SOURCES", patched_sources)
    output_root = tmp_path / "reports"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "corpus_reingest.py",
            "--dry-run",
            "--sources-root",
            str(sources),
            "--corpora-root",
            str(tmp_path / "corpora"),
            "--output-root",
            str(output_root),
        ],
    )

    exit_code = reingest.main()

    assert exit_code == 2
    out = capsys.readouterr().out
    assert "[source-root] attack_data:" in out
    report_dirs = list(output_root.glob("*"))
    assert len(report_dirs) == 1
    assert commit[:12] in report_dirs[0].name
    assert len(report_dirs[0].name.encode()) < 255
    summary = json.loads((report_dirs[0] / "acquisition.json").read_text(encoding="utf-8"))
    attack_record = next(s for s in summary["sources"] if s["publisher"] == "attack_data")
    assert attack_record["root_selection"]["source"] == "pinned_sibling"
    assert attack_record["path"] == str(sibling)
    assert (main_repo / "dirty.txt").read_text(encoding="utf-8") == "uncommitted\n"


def test_lfs_repair_pulls_via_install_local(monkeypatch: Any) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_git(
        root: Path, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(acquisition, "_git", fake_git)

    assert acquisition._lfs_repair(Path("/tmp/checkout")) is None
    assert calls == [("lfs", "version"), ("lfs", "install", "--local"), ("lfs", "pull")]


def test_lfs_repair_names_repo_when_git_lfs_missing(monkeypatch: Any) -> None:
    def fail_git(
        root: Path, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1, "", "git: 'lfs' is not a git command")

    monkeypatch.setattr(acquisition, "_git", fail_git)

    failed = acquisition._lfs_repair(Path("/tmp/attack_data.pinned-abc"))

    assert failed is not None
    assert failed["status"] == "lfs_unavailable"
    assert "attack_data.pinned-abc" in failed["detail"]


def test_lfs_repair_reports_pull_failure(monkeypatch: Any) -> None:
    codes = {"version": 0, "install": 0, "pull": 1}

    def fake_git(
        root: Path, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, codes[args[1]], "", "pull failed")

    monkeypatch.setattr(acquisition, "_git", fake_git)

    failed = acquisition._lfs_repair(Path("/tmp/checkout"))

    assert failed is not None
    assert failed["status"] == "lfs_pull_failed"
    assert failed["detail"] == "pull failed"


def _pointer_upstream(upstream: Path) -> str:
    upstream.mkdir(parents=True)
    _git(upstream, "init")
    _git(upstream, "config", "user.name", "Unit Test")
    _git(upstream, "config", "user.email", "unit@example.invalid")
    (upstream / "sample.evtx").write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:0123456789abcdef\nsize 2048\n",
        encoding="utf-8",
    )
    return _commit_all(upstream, "pointer")


def _pinned_sibling_scenario(tmp_path: Path) -> tuple[Path, str, Path]:
    sources = tmp_path / "sources"
    upstream = sources / "upstream"
    commit = _pointer_upstream(upstream)
    main = sources / "attack_data"
    _init_repo(main, dirty=True)
    sibling = acquisition.sibling_checkout(main, commit)
    _clone(upstream, sibling)
    return upstream, commit, sibling


def test_acquire_repairs_pinned_sibling_with_incomplete_lfs(
    tmp_path: Path, monkeypatch: Any
) -> None:
    upstream, commit, sibling = _pinned_sibling_scenario(tmp_path)
    assert acquisition.inspect_checkout(sibling, commit)["status"] == "lfs_incomplete"
    repairs: list[Path] = []

    def fake_repair(target: Path) -> dict[str, Any] | None:
        repairs.append(Path(target))
        return None

    monkeypatch.setattr(acquisition, "_lfs_repair", fake_repair)

    result = acquisition.acquire_checkout(
        acquisition.SourceSpec(
            "attack_data", str(upstream), commit, tmp_path / "sources" / "attack_data"
        )
    )

    assert repairs == [sibling]
    assert result["status"] == "lfs_incomplete"


def test_acquire_propagates_lfs_repair_failure(tmp_path: Path, monkeypatch: Any) -> None:
    upstream, commit, sibling = _pinned_sibling_scenario(tmp_path)
    failure = {"path": str(sibling), "status": "lfs_unavailable", "detail": "install git lfs"}
    monkeypatch.setattr(acquisition, "_lfs_repair", lambda target: failure)

    result = acquisition.acquire_checkout(
        acquisition.SourceSpec(
            "attack_data", str(upstream), commit, tmp_path / "sources" / "attack_data"
        )
    )

    assert result == failure


@pytest.mark.skipif(not _git_lfs_available(), reason="git lfs not installed")
def test_acquire_pulls_lfs_into_fresh_clone(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    commit = _lfs_upstream(upstream)
    target = tmp_path / "sources" / "attack_data"

    result = acquisition.acquire_checkout(
        acquisition.SourceSpec("attack_data", str(upstream), commit, target)
    )

    assert result["status"] == "acquired"
    assert (target / "payload.bin").read_bytes() == b"real-lfs-payload\n"
    assert acquisition.inspect_checkout(target, commit)["status"] == "verified"


@pytest.mark.skipif(not _git_lfs_available(), reason="git lfs not installed")
def test_verification_reports_pulled_pointer_looking_content_as_upstream_defect(
    tmp_path: Path,
) -> None:
    upstream = tmp_path / "upstream"
    payload = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:0123456789abcdef\n"
        b"size 253\n<<<<<<< HEAD\nconflicting content\n>>>>>>> branch\n"
    )
    commit = _lfs_upstream(upstream, payload)

    result = acquisition.inspect_checkout(upstream, commit)

    assert result["status"] == "verified"
    assert result["upstream_defects"] == ["payload.bin"]


@pytest.mark.skipif(not _git_lfs_available(), reason="git lfs not installed")
def test_acquire_repairs_existing_pinned_lfs_clone(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    commit = _lfs_upstream(upstream)
    main = tmp_path / "sources" / "attack_data"
    _init_repo(main, dirty=True)
    sibling = acquisition.sibling_checkout(main, commit)
    _clone(upstream, sibling)
    assert acquisition.inspect_checkout(sibling, commit)["status"] == "lfs_incomplete"

    result = acquisition.acquire_checkout(
        acquisition.SourceSpec("attack_data", str(upstream), commit, main)
    )

    assert result["status"] == "verified"
    assert (sibling / "payload.bin").read_bytes() == b"real-lfs-payload\n"


def test_verify_uses_the_latest_items_report(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    output = tmp_path / "reports"
    older = output / "20260101T000000Z__attack_data-aaaaaaaaaaaa"
    newer = output / "20261029T000000Z__attack_data-bbbbbbbbbbbb"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "items.json").write_text('{"items": {}}\n', encoding="utf-8")
    (newer / "items.json").write_text('{"items": {}}\n', encoding="utf-8")
    seen: dict[str, Path] = {}

    def fake_verify(path: Path) -> dict[str, Any]:
        seen["path"] = path
        return {"ok": True, "mismatches": {}, "extra_p5_items": []}

    monkeypatch.setattr(reingest, "verify_plan", fake_verify)
    monkeypatch.setattr(
        sys,
        "argv",
        ["corpus_reingest.py", "--verify", "--output-root", str(output)],
    )

    assert reingest.main() == 0
    assert seen["path"] == newer / "items.json"
    assert f"VERIFY items: {newer / 'items.json'}" in capsys.readouterr().out


def test_verify_explicit_items_beats_a_newer_report(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    output = tmp_path / "reports"
    newer = output / "20261029T000000Z__attack_data-bbbbbbbbbbbb"
    chosen = tmp_path / "items.json"
    newer.mkdir(parents=True)
    (newer / "items.json").write_text('{"items": {}}\n', encoding="utf-8")
    chosen.write_text('{"items": {}}\n', encoding="utf-8")
    seen: dict[str, Path] = {}

    def fake_verify(path: Path) -> dict[str, Any]:
        seen["path"] = path
        return {"ok": False, "mismatches": {"x": {}}, "extra_p5_items": []}

    monkeypatch.setattr(reingest, "verify_plan", fake_verify)
    monkeypatch.setattr(
        sys,
        "argv",
        ["corpus_reingest.py", "--verify", "--items", str(chosen), "--output-root", str(output)],
    )

    assert reingest.main() == 1
    assert seen["path"] == chosen
    capsys.readouterr()


def test_verify_without_a_report_exits(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["corpus_reingest.py", "--verify", "--output-root", str(tmp_path / "missing")],
    )

    with pytest.raises(SystemExit) as caught:
        reingest.main()

    assert caught.value.code == 2
