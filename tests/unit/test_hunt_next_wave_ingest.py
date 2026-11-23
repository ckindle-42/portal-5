"""Next-wave canonical ingest (Zeek, Sysmon, ICS) and out-of-band scorer keys."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from portal.modules.security.core.hunt.notables.knowledge import (
    PROOF_INDEXES,
    TRAINING_INDEXES,
    KnowledgeError,
    KnowledgeItem,
    build_store,
)
from portal.modules.security.core.hunt.notables.manifest import parse_source
from portal.modules.security.core.hunt.notables.relate import relatable_index
from scripts.hunt_bed import ingest_canonical, keys_nextwave
from scripts.hunt_bed.ingest_canonical import (
    GROUND_TRUTH_FIELDS,
    ST_SECURITY,
    ST_SYSMON,
    main,
    should_drop_path,
    sourcetype_for,
)

REPO = Path(__file__).resolve().parents[2]
_GT = (
    "label",
    "label_tactic",
    "label_technique",
    "mitre_attack",
    "attack_cat",
    "is_attack",
    "benign",
    "attack",
    "ground_truth",
    "technique",
)


class _FakeEmbedder:
    model = "fake-embed"

    def embed(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


def _item(index: str) -> KnowledgeItem:
    return KnowledgeItem(
        statement="actor=attacker did execute to shell",
        label="step",
        label_kind="known_bad",
        label_basis="attack_step",
        family="nextwave",
        split="build",
        index=index,
        source_kind="activity",
        query=f'search index="{index}" | head 5',
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("conn.log", "bro:conn:json"),
        ("Conn.csv", "bro:conn:json"),
        ("dns.jsonl", "bro:dns:json"),
        ("http.log", "bro:http:json"),
        ("ssl.log", "bro:ssl:json"),
        ("tls.log", "bro:ssl:json"),
        ("weird.log", "bro:weird:json"),
        ("Notice.log", "bro:notice:json"),
        ("modbus.log", "bro:modbus:json"),
        ("dnp3.json", "bro:dnp3:json"),
        ("s7comm.log", "bro:s7comm:json"),
        ("bacnet.log", "bro:bacnet:json"),
        ("zeek_conn.jsonl", "bro:conn:json"),
        ("labeled_conn.jsonl", "bro:conn:json"),
        ("sysmon.jsonl", ST_SYSMON),
        ("Microsoft-Windows-Sysmon%4Operational.xml", ST_SYSMON),
        ("Security.json", ST_SECURITY),
        ("WinEventLog-Security.jsonl", ST_SECURITY),
        ("auth.log", "linux_secure"),
        ("dnsmasq.log", "dnsmasq"),
        ("conn-summary.csv", None),
    ],
)
def test_next_wave_sourcetypes(name: str, expected: str | None) -> None:
    assert sourcetype_for(f"host/logs/{name}") == expected


@pytest.mark.parametrize(
    ("rel", "reason"),
    [
        ("mission_logs.csv", "label"),
        ("zeek/mission_logs/mission_log_5.csv", "label"),
        ("labels.csv", "label"),
        ("santos/labels/conn.log", "label"),
        ("conn_labeled.jsonl", None),
        ("LMD-2023-labelled.csv", None),
        ("conn.log", None),
    ],
)
def test_label_sidecar_vs_labeled_telemetry(rel: str, reason: str | None) -> None:
    assert should_drop_path(rel) == reason


def _zeek_attack() -> dict:
    return {
        "ts": 1700000000.0,
        "uid": "Cattack",
        "id.orig_h": "10.1.1.5",
        "id.resp_h": "10.1.1.9",
        "history": "SECRET_RAW_ZEEK",
        "label": "Malicious",
        "label_tactic": "Discovery",
        "label_technique": "T1046",
        "mitre_attack": "T1046",
        "attack_cat": "scan",
        "is_attack": 1,
        "benign": False,
    }


def _zeek_benign() -> dict:
    return {
        "ts": 1690000000.0,
        "uid": "Cbenign",
        "id.orig_h": "10.1.1.8",
        "id.resp_h": "10.1.1.9",
        "label": "Benign",
        "label_tactic": "",
        "label_technique": "",
        "is_attack": 0,
        "benign": True,
    }


def _write_corpus(root: Path) -> None:
    zeek = root / "zeek"
    zeek.mkdir(parents=True)
    rows = [_zeek_attack(), _zeek_benign()]
    (zeek / "labeled_conn.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    (zeek / "dns.csv").write_text(
        "ts,id.orig_h,id.resp_h,label,label_tactic\n"
        "1700001000,10.2.2.5,10.2.2.9,Malicious,Lateral Movement\n",
        encoding="utf-8",
    )
    (zeek / "mission_logs.csv").write_text(
        "tactic,technique,src_ip,dst_ip,start_time,end_time\n"
        "Reconnaissance,T1595,10.8.8.8,10.8.8.1,2024-02-10T03:00:00Z,2024-02-10T03:15:00Z\n",
        encoding="utf-8",
    )
    (zeek / "modbus.log").write_text(
        json.dumps(
            {
                "ts": 1700003000,
                "uid": "Cmod",
                "id.orig_h": "10.4.4.4",
                "id.resp_h": "10.4.4.5",
                "func": "READ_COILS",
                "label": "Malicious",
                "label_tactic": "Impair Process Control",
                "label_technique": "T0836",
                "is_attack": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lmd = root / "lmd"
    lmd.mkdir()
    (lmd / "LMD-2023-labelled.csv").write_text(
        "EventID,Image,CommandLine,Computer,SystemTime,Label,attack,ground_truth,technique\n"
        "1,C:\\Windows\\System32\\cmd.exe,cmd.exe SECRET_RAW_CMD,win-lab,"
        "2023-04-02T01:02:03Z,EoRS,T1059,malicious,T1059.003\n"
        "1,C:\\Windows\\explorer.exe,explorer.exe,win-lab,2023-04-02T01:00:00Z,Normal,,,\n",
        encoding="utf-8",
    )
    (lmd / "sysmon.xml").write_text(
        "<Event><System><EventID>1</EventID><Computer>win-xml</Computer></System>"
        '<EventData><Data Name="Image">C:\\Windows\\System32\\cmd.exe</Data>'
        '<Data Name="CommandLine">cmd.exe SECRET_RAW_CMD</Data></EventData>'
        "<technique>T1059</technique><label>malicious</label></Event>\n",
        encoding="utf-8",
    )


def _events(batches: list[bytes]) -> list[dict]:
    events = []
    for body in batches:
        events.extend(json.loads(line) for line in body.decode().splitlines() if line.strip())
    return events


def _assert_census(census: dict) -> None:
    assert census["zero_labels"] is True
    assert census["labels_included"] == 0
    assert census["dropped"]["by_reason"]["label"] == 1
    assert census["label_fields_stripped"] > 0
    kept = census["kept"]["by_sourcetype"]
    assert kept["bro:conn:json"] == 1
    assert kept["bro:dns:json"] == 1
    assert kept["bro:modbus:json"] == 1
    assert kept[ST_SYSMON] == 2


def _assert_shipped(events: list[dict]) -> None:
    raws = [ev["event"] for ev in events]
    joined = "\n".join(raws)
    assert "10.8.8.8" not in joined  # mission_logs never ship
    assert "T1595" not in joined
    assert "SECRET_RAW_ZEEK" in joined and "SECRET_RAW_CMD" in joined
    assert "10.1.1.5" in joined and "10.1.1.8" in joined
    assert "READ_COILS" in joined and "explorer.exe" in joined
    assert "malicious" not in joined.casefold()
    assert "EoRS" not in joined and "T1046" not in joined and "T1059" not in joined
    assert "<technique" not in joined.lower() and "<label" not in joined.lower()
    payloads = [json.loads(raw) for raw in raws if raw.lstrip()[:1] in "{["]
    assert payloads
    for payload in payloads:
        assert {str(key).casefold() for key in payload}.isdisjoint(_GT)
    preserved = next(row for row in payloads if row.get("uid") == "Cattack")
    assert preserved["id.orig_h"] == "10.1.1.5"
    assert preserved["id.resp_h"] == "10.1.1.9"
    assert preserved["ts"] == 1700000000.0
    lmd_row = next(raw for raw in raws if "SECRET_RAW_CMD" in raw and not raw.startswith("<"))
    header = next(raw for raw in raws if raw.startswith("EventID,"))
    assert header.startswith("EventID,Image,CommandLine")
    assert "win-lab" in lmd_row and "cmd.exe" in lmd_row
    assert "label" not in header.casefold() and "technique" not in header.casefold()
    attack = next(ev for ev in events if "SECRET_RAW_ZEEK" in ev["event"])
    assert attack["time"].startswith("1700000000")
    by_type = {ev["sourcetype"] for ev in events}
    assert {"bro:conn:json", "bro:dns:json", "bro:modbus:json", ST_SYSMON} <= by_type


def test_shipped_payloads_strip_labels_and_keep_telemetry(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    root = tmp_path / "corpus"
    _write_corpus(root)
    monkeypatch.setenv("LAB_SPLUNK_HEC_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("LAB_SPLUNK_HEC_TOKEN", "tok")
    batches: list[bytes] = []
    monkeypatch.setattr(ingest_canonical, "_post", lambda _url, _tok, body: batches.append(body))
    dry = main(["--root", str(root), "--index", "hb_uwf_zeek24", "--dry-run"])
    census = json.loads(capsys.readouterr().out)
    assert dry == 0
    _assert_census(census)
    out = tmp_path / "manifest"
    rc = main(
        [
            "--root",
            str(root),
            "--index",
            "hb_uwf_zeek24",
            "--ship",
            "--manifest-out",
            str(out),
            "--default-year",
            "2024",
        ]
    )
    assert rc == 0
    receipt = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["census"]["zero_labels"] is True
    assert receipt["label_fields_stripped"] == census["label_fields_stripped"]
    assert receipt["label_fields_stripped"] == sum(
        row["label_fields_stripped"] for row in receipt["files"]
    )
    _assert_shipped(_events(batches))


def _zip_tree(src: Path, dest: Path) -> None:
    with zipfile.ZipFile(dest, "w") as zf:
        for path in sorted(src.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(src).as_posix())


def test_keys_nextwave_zip_dir_and_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = tmp_path / "uwf"
    zeek = corpus / "zeek"
    zeek.mkdir(parents=True)
    (zeek / "conn.jsonl").write_text(
        json.dumps(_zeek_attack()) + "\n" + json.dumps(_zeek_benign()) + "\n",
        encoding="utf-8",
    )
    (zeek / "dns.csv").write_text(
        "ts,id.orig_h,id.resp_h,label,label_tactic,label_technique\n"
        "1700001000,10.2.2.5,10.2.2.9,Malicious,Lateral Movement,T1021\n",
        encoding="utf-8",
    )
    (zeek / "mission_logs.csv").write_text(
        "tactic,technique,src_ip,dst_ip,start_time,end_time\n"
        "Reconnaissance,T1595,10.8.8.8,10.8.8.1,2024-02-10T03:00:00Z,2024-02-10T03:15:00Z\n",
        encoding="utf-8",
    )
    archive = tmp_path / "uwf.zip"
    _zip_tree(corpus, archive)
    zip_out = tmp_path / "uwf_zip.json"
    dir_out = tmp_path / "uwf_dir.json"
    assert (
        keys_nextwave.main(
            [
                "--root",
                str(archive),
                "--dataset",
                "UWF-ZeekData24",
                "--out",
                str(zip_out),
                "--summary",
            ]
        )
        == 0
    )
    summary = capsys.readouterr().out
    assert (
        keys_nextwave.main(
            ["--root", str(corpus), "--dataset", "UWF-ZeekData24", "--out", str(dir_out)]
        )
        == 0
    )
    zip_key = json.loads(zip_out.read_text(encoding="utf-8"))
    dir_key = json.loads(dir_out.read_text(encoding="utf-8"))
    assert {**zip_key, "source": ""} == {**dir_key, "source": ""}
    assert zip_key["dataset"] == "UWF-ZeekData24"
    assert zip_key["index"] == "hb_uwf_zeek24"
    assert zip_key["split"] == "proof"
    assert zip_key["total_labelled_lines"] == 3
    assert zip_key["step_counts"] == {
        "Discovery": 1,
        "Lateral Movement": 1,
        "Reconnaissance": 1,
    }
    assert "10.1.1.8" not in zip_key["affected_hosts"]
    assert "10.1.1.5" in zip_key["affected_hosts"]
    assert "10.8.8.8" in zip_key["affected_hosts"]
    discovery = next(step for step in zip_key["attack_steps"] if step["step"] == "Discovery")
    assert discovery["rules"] == ["T1046"]
    assert discovery["count"] == 1
    assert discovery["sources"][0]["line_ranges"] == [[1, 1]]
    recon = next(step for step in zip_key["attack_steps"] if step["step"] == "Reconnaissance")
    assert recon["rules"] == ["T1595"]
    assert recon["time_window"]["start"] == "2024-02-10T03:00:00Z"
    assert recon["time_window"]["end"] == "2024-02-10T03:15:00Z"
    blob = zip_out.read_text(encoding="utf-8")
    assert "SECRET_RAW_" not in blob
    assert "SECRET_RAW_" not in summary
    assert "dataset=UWF-ZeekData24 index=hb_uwf_zeek24 split=proof" in summary
    assert "Discovery: count=1" in summary


def test_keys_lmd_and_ics(tmp_path: Path) -> None:
    lmd = tmp_path / "lmd"
    lmd.mkdir()
    (lmd / "LMD-2023.csv").write_text(
        "EventID,Image,CommandLine,Computer,SystemTime,Label\n"
        "1,C:\\Windows\\System32\\cmd.exe,cmd.exe SECRET_RAW_CMD,win-lab,2023-04-02T01:02:03Z,EoRS\n"
        "1,C:\\Windows\\explorer.exe,explorer.exe,win-lab,2023-04-02T01:00:00Z,Normal\n",
        encoding="utf-8",
    )
    out = tmp_path / "lmd_key.json"
    assert keys_nextwave.main(["--root", str(lmd), "--dataset", "LMD-2023", "--out", str(out)]) == 0
    key = json.loads(out.read_text(encoding="utf-8"))
    assert key["index"] == "hb_lmd_2023"
    assert key["split"] == "proof"
    assert key["total_labelled_lines"] == 1
    assert key["step_counts"] == {"EoRS": 1}
    assert key["affected_hosts"] == ["win-lab"]
    assert key["time_window"]["start"] == "2023-04-02T01:02:03Z"
    assert "SECRET_RAW_" not in out.read_text(encoding="utf-8")
    assert "explorer.exe" not in out.read_text(encoding="utf-8")

    ics = tmp_path / "ics"
    ics.mkdir()
    (ics / "modbus.jsonl").write_text(
        json.dumps(
            {
                "ts": 1700003000,
                "id.orig_h": "10.4.4.4",
                "id.resp_h": "10.4.4.5",
                "label_tactic": "Impair Process Control",
                "label_technique": "T0836",
                "is_attack": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ics_out = tmp_path / "ics_key.json"
    assert (
        keys_nextwave.main(["--root", str(ics), "--dataset", "ICS-pcap", "--out", str(ics_out)])
        == 0
    )
    ics_key = json.loads(ics_out.read_text(encoding="utf-8"))
    assert ics_key["index"] == "hb_ics_pcap"
    assert ics_key["step_counts"] == {"Impair Process Control": 1}
    assert ics_key["attack_steps"][0]["rules"] == ["T0836"]
    assert ics_key["affected_hosts"] == ["10.4.4.4", "10.4.4.5"]


def test_named_ground_truth_fields_are_the_strip_set() -> None:
    assert set(_GT) == set(GROUND_TRUTH_FIELDS)


def test_keys_nextwave_never_imported_by_portal() -> None:
    hits = [
        path.relative_to(REPO).as_posix()
        for path in (REPO / "portal").rglob("*.py")
        if "keys_nextwave" in path.read_text(errors="replace")
    ]
    assert hits == []


@pytest.mark.parametrize("index_name", ["hb_uwf_zeek24", "hb_lmd_2023", "hb_ics_pcap"])
def test_next_wave_proof_indexes_cannot_train(tmp_path: Path, index_name: str) -> None:
    assert index_name in PROOF_INDEXES
    assert index_name not in TRAINING_INDEXES
    item = _item(index_name)
    with pytest.raises(KnowledgeError, match="proof index"):
        item.validate()
    with pytest.raises(KnowledgeError, match="proof index"):
        build_store([item], _FakeEmbedder(), tmp_path / "knowledge.duckdb")
    with pytest.raises(ValueError, match="proof index"):
        parse_source(
            f"name=proof,index={index_name},kind=window,cards={tmp_path},good_window=0:100"
        )
    with pytest.raises(ValueError, match="proof index"):
        relatable_index(index_name)
