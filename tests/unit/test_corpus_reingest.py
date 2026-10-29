from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from portal.modules.security.core.siem import hec_ship
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
    assert (unknown.sourcetype, unknown.source) == ("mordor:unknown", "mordor:unknown")
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
        "unknown_sourcetype": 1,
        "unknown_host": 1,
        "date_fallback": 1,
        "missing_time": 0,
        "source_replacements": 1,
        "host_replacements": 0,
        "residual_leaks": 1,
    }
    assert report["by_publisher"] == {"mordor": 1}
    assert report["by_host"] == {"unknown": 1}
    item_id = reingest.p5_item_id("mordor", "test-directory")
    assert report["items"][item_id]["date_fallback"] == 1


def test_evtx_reader_uses_python_evtx_xml_records(tmp_path: Path, monkeypatch: Any) -> None:
    import importlib

    evtx_module = importlib.import_module("Evtx.Evtx")

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
    monkeypatch.setattr(evtx_module, "Evtx", Source)
    assert list(reingest.iter_evtx_text(tmp_path / "sample.evtx")) == [
        "<Event><System><Channel>Security</Channel></System></Event>"
    ]


def test_ship_iterator_uses_python_evtx_xml_records(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "sample.evtx"
    path.write_bytes(b"fixture")
    body = "<Event><System><Channel>Security</Channel></System></Event>"
    item = reingest.CorpusFile("evtx_samples", "Security/4624", path, tmp_path)
    monkeypatch.setattr(reingest, "iter_evtx_text", lambda _: iter([body]))

    resolved = list(reingest._iter_resolved(iter([item])))

    assert len(resolved) == 1
    assert resolved[0][1].body == body
