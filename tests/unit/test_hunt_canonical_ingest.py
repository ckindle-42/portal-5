"""Unit tests for scripts/hunt_bed/ingest_canonical.py (canonical TA sourcetypes, §5.1) and
scripts/hunt_bed/keys_flaws.py isolation (scorer plane only, never imported under portal/)."""

import argparse
import calendar
import io
import json
import tarfile
from collections import Counter
from pathlib import Path

import pytest

from scripts.hunt_bed import ingest_canonical, keys_flaws
from scripts.hunt_bed.ingest_canonical import main, should_drop_path, sourcetype_for

REPO = Path(__file__).resolve().parents[2]

# (file name incl. rotation suffix, canonical sourcetype) — every §5.1 mapper rule
MAP_CASES = [
    ("auth.log", "linux_secure"),
    ("auth.log.1", "linux_secure"),
    ("auth.log.2.gz", "linux_secure"),
    ("audit.log", "linux_audit"),
    ("audit.log.3.gz", "linux_audit"),
    ("messages", "syslog"),
    ("messages.1", "syslog"),
    ("syslog", "syslog"),
    ("syslog.7.gz", "syslog"),
    ("kern.log", "syslog"),
    ("kern.log.2.gz", "syslog"),
    ("user.log", "syslog"),
    ("user-1000.journal.txt", "syslog"),
    ("access.log", "access_combined"),
    ("access.log.4", "access_combined"),
    ("other_vhosts_access.log", "access_combined"),
    ("horde-access.log", "access_combined"),
    ("error.log", "apache:error"),
    ("error.log.1", "apache:error"),
    ("eve.json", "suricata"),
    ("eve.json.1", "suricata"),
    ("fast.log", "suricata:fast"),
    ("dnsmasq.log", "dnsmasq"),
    ("mail.log", "postfix_syslog"),
    ("mail.info", "postfix_syslog"),
    ("mainlog", "postfix_syslog"),
    ("openvpn.log", "openvpn"),
    ("flaws_cloudtrail00.json.gz", "aws:cloudtrail"),
    ("CloudTrail_us-east-1_20201009T00Z.json", "aws:cloudtrail"),
]

DROP_CASES = [
    ("stats.log", "metrics_noise"),
    ("stats.log.1", "metrics_noise"),
    ("web-1.cpu.log", "metrics_noise"),
    ("web-1.mem.log.2", "metrics_noise"),
    ("2022-01-14-system.service.log", "filebeat_dup"),
    ("2022-01-14-system.syslog.log", "filebeat_dup"),
    ("2022-01-14-system.auth.log", "filebeat_dup"),
    ("system.journal.txt", "filebeat_dup"),
    ("host/logs/system.journal.txt", "filebeat_dup"),
    ("labels.csv", "label"),
    ("ground_truth.json", "label"),
    ("answers.txt", "label"),
    ("attack_meta.json", "label"),
    ("santos/labels/2022-01-14-system.service.log", "label"),
]

KEEP_CASES = [
    "auth.log",
    "syslog",
    "eve.json",
    "user-1000.journal.txt",
    "messages",
    "dnsmasq.log",
    "2022-01-15-access.log",
]


@pytest.mark.parametrize(("name", "expected"), MAP_CASES)
def test_sourcetype_map(name, expected):
    assert sourcetype_for(f"host/logs/{name}") == expected


@pytest.mark.parametrize(("rel", "reason"), DROP_CASES)
def test_drop_rules(rel, reason):
    assert should_drop_path(rel) == reason


@pytest.mark.parametrize("rel", KEEP_CASES)
def test_keep_rules(rel):
    assert should_drop_path(rel) is None


def test_user_journal_is_not_a_filebeat_duplicate():
    assert sourcetype_for("host/logs/user-1000.journal.txt") == "syslog"
    assert should_drop_path("host/logs/user-1000.journal.txt") is None
    assert should_drop_path("host/logs/system.journal.txt") == "filebeat_dup"


def _tree(tmp_path: Path) -> Path:
    host_a = tmp_path / "hostA" / "logs"
    host_b = tmp_path / "hostB" / "logs"
    for d in (host_a, host_b):
        d.mkdir(parents=True)
    for name in (
        "auth.log",
        "messages",
        "eve.json",
        "stats.log",
        "2022-01-14-system.service.log",
        "labels.csv",
        "ground_truth.json",
    ):
        (host_a / name).write_text("Jan 14 03:12:01 host service: line\n")
    for name in (
        "access.log",
        "error.log",
        "dnsmasq.log",
        "mail.log",
        "openvpn.log",
        "fast.log",
        "audit.log",
        "user-1000.journal.txt",
        "system.journal.txt",
        "kern.log",
        "syslog",
        "2022-01-14-system.auth.log",
    ):
        (host_b / name).write_text("Jan 14 03:12:01 host service: line\n")
    return tmp_path


def test_census_cli_counts_and_zero_labels(tmp_path, capsys):
    rc = main(["--root", str(_tree(tmp_path)), "--index", "hb_t", "--dry-run"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["total_files"] == 19
    assert out["kept"]["by_sourcetype"] == {
        "linux_secure": 1,
        "syslog": 4,
        "suricata": 1,
        "suricata:fast": 1,
        "linux_audit": 1,
        "access_combined": 1,
        "apache:error": 1,
        "dnsmasq": 1,
        "postfix_syslog": 1,
        "openvpn": 1,
    }
    assert out["dropped"]["by_reason"] == {"filebeat_dup": 3, "label": 2, "metrics_noise": 1}
    assert out["labels_dropped"] == 2 and out["labels_included"] == 0
    assert out["zero_labels"] is True


def test_census_tar_archive_with_cloudtrail_members(tmp_path, capsys):
    tar_path = tmp_path / "flaws_cloudtrail_logs.tar"
    doc = json.dumps(
        {"Records": [{"eventTime": "2020-10-09T09:20:12Z", "recipientAccountId": "811596193553"}]}
    )
    with tarfile.open(tar_path, "w") as tf:
        for i in range(2):
            data = doc.encode()
            info = tarfile.TarInfo(f"flaws_cloudtrail_logs/flaws_cloudtrail0{i}.json")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    rc = main(["--root", str(tar_path), "--index", "hb_flaws_aws", "--dry-run"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["kept"]["by_sourcetype"] == {"aws:cloudtrail": 2}
    assert out["zero_labels"] is True


def _args(tmp_path, **kw):
    base = {
        "index": "hb_flaws_aws",
        "dry_run": False,
        "default_year": 2020,
        "batch": 100,
        "root": tmp_path,
        "archive": False,
        "manifest_out": tmp_path / "out",
    }
    return argparse.Namespace(**(base | kw))


def _ship_one(tmp_path, name, text, monkeypatch, dry_run=True):
    """Ship one file through _ship_file with HEC mocked; return (stats, hec batches, manifest rows)."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    captured, args = [], _args(tmp_path, dry_run=dry_run, root=tmp_path)
    monkeypatch.setattr(
        ingest_canonical,
        "_post",
        lambda url, tok, body: captured.append(
            [json.loads(row) for row in body.decode().splitlines()]
        ),
    )
    rows_path = tmp_path / "digests.jsonl"
    with open(rows_path, "w") as manifest:
        stats = ingest_canonical._ship_file(
            args,
            "http://hec",
            "tok",
            manifest,
            name,
            name.split("/", 1)[0],
            lambda p=path: open(p, "rb"),
            ingest_canonical.sourcetype_for(name),
        )
    rows = [json.loads(r) for r in rows_path.read_text().splitlines()]
    return stats, captured, rows


def test_cloudtrail_flatten_eventtime_and_host(tmp_path, monkeypatch):
    recs = [
        {
            "eventTime": "2020-10-09T09:20:12Z",
            "eventName": "ListBuckets",
            "recipientAccountId": "811596193553",
            "awsRegion": "us-east-1",
        },
        {
            "eventTime": "2020-10-09T09:21:30Z",
            "eventName": "GetCallerIdentity",
            "awsRegion": "us-east-1",
        },
    ]
    stats, batches, rows = _ship_one(
        tmp_path,
        "flaws_cloudtrail00.json",
        json.dumps({"Records": recs}),
        monkeypatch,
        dry_run=False,
    )
    assert stats["sent"] == 2 and stats["blank"] == 0
    events = [e for batch in batches for e in batch]
    assert len(events) == 2
    assert events[0]["host"] == "811596193553"  # recipientAccountId wins over awsRegion
    assert events[1]["host"] == "us-east-1"  # falls back to awsRegion
    assert events[0]["sourcetype"] == "aws:cloudtrail"
    assert events[0]["event"] == json.dumps(recs[0], separators=(",", ":"))
    assert events[0]["time"] == f"{calendar.timegm((2020, 10, 9, 9, 20, 12)):.6f}"
    assert events[1]["time"] == f"{calendar.timegm((2020, 10, 9, 9, 21, 30)):.6f}"
    assert [r[0] for r in rows] == ["811596193553", "us-east-1"]
    assert (
        rows[0][3]
        == ingest_canonical.hashlib.sha256(
            f"811596193553|/flaws_cloudtrail00.json|{events[0]['event']}".encode()
        ).hexdigest()[:24]
    )


def test_cloudtrail_gz_member_reads(tmp_path):
    import gzip

    path = tmp_path / "flaws_cloudtrail01.json.gz"
    path.write_bytes(
        gzip.compress(
            json.dumps(
                {"Records": [{"eventTime": "2020-10-09T09:20:12Z", "eventName": "ListBuckets"}]}
            ).encode()
        )
    )
    recs, had = ingest_canonical._read_records(
        lambda: open(path, "rb"), "flaws_cloudtrail01.json.gz"
    )
    assert had is True and len(recs) == 1
    assert json.loads(recs[0])["eventName"] == "ListBuckets"


def test_ship_receipt_and_digest_manifest(tmp_path, monkeypatch, capsys):
    root = _tree(tmp_path)
    out = tmp_path / "out"
    monkeypatch.setenv("LAB_SPLUNK_HEC_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("LAB_SPLUNK_HEC_TOKEN", "tok")
    batches: list[bytes] = []
    monkeypatch.setattr(ingest_canonical, "_post", lambda url, tok, body: batches.append(body))
    rc = main(
        [
            "--root",
            str(root),
            "--index",
            "hb_t",
            "--ship",
            "--manifest-out",
            str(out),
            "--default-year",
            "2022",
        ]
    )
    assert rc == 0
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["sent_total"] == 13
    assert receipt["census"]["zero_labels"] is True
    rows = [json.loads(r) for r in (out / "digests.jsonl").read_text().splitlines()]
    assert len(rows) == 13
    assert all(len(r[3]) == 24 for r in rows)
    assert all(r[4].endswith(r[1].lstrip("/")) for r in rows)
    sent = sum(len(b.decode().splitlines()) for b in batches)
    assert sent == 13
    assert capsys.readouterr().out


def test_keys_flaws_never_referenced_by_engine_code():
    hits = [
        p.relative_to(REPO).as_posix()
        for p in (REPO / "portal").rglob("*.py")
        if "keys_flaws" in p.read_text(errors="replace")
    ]
    assert hits == []
    sibs = [
        p.name
        for p in (REPO / "scripts" / "hunt_bed").glob("*.py")
        if p.name != "keys_flaws.py" and "keys_flaws" in p.read_text(errors="replace")
    ]
    assert sibs == []


def _flaws_corpus(tmp_path: Path) -> Path:
    def mk(**kw):
        return {
            "eventTime": "2020-10-09T09:20:12Z",
            "recipientAccountId": "811596193553",
            "awsRegion": "us-east-1",
            "sourceIPAddress": "5.6.7.8",
            **kw,
        }

    arn = "arn:aws:iam::811596193553:user/level6"
    recs = [
        mk(eventName="GetObject", userIdentity={"userName": "alice"}),  # benign
        mk(eventName="AssumeRole", userIdentity={"userName": "backup"}, sourceIPAddress="1.2.3.4"),
        mk(
            eventName="GetCallerIdentity",
            sourceIPAddress="169.254.169.254",
            userIdentity={"userName": "root"},
        ),  # imds, not the chain group
        mk(eventName="GetCallerIdentity", userIdentity={"arn": arn}),
        mk(eventName="ListBuckets", userIdentity={"arn": arn}),
        mk(
            eventName="PutObject",
            userIdentity={"arn": arn},
            requestParameters={"bucketName": "flaws.cloud-2"},
        ),
        mk(eventName="CreateAccessKey", userIdentity={"arn": arn}),
    ]
    (tmp_path / "flaws_cloudtrail00.json").write_text(json.dumps({"Records": recs}))
    return tmp_path


def test_keys_flaws_join_and_chain(tmp_path, monkeypatch):
    root = _flaws_corpus(tmp_path)
    out = tmp_path / "out"
    monkeypatch.setenv("LAB_SPLUNK_HEC_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("LAB_SPLUNK_HEC_TOKEN", "tok")
    monkeypatch.setattr(ingest_canonical, "_post", lambda *_a: None)
    assert (
        main(
            [
                "--root",
                str(root),
                "--index",
                "hb_flaws_aws",
                "--ship",
                "--manifest-out",
                str(out),
                "--default-year",
                "2020",
            ]
        )
        == 0
    )
    rc = keys_flaws.main(["--manifest", str(out)])
    assert rc == 0
    keys = [json.loads(r) for r in (out / "keys.jsonl").read_text().splitlines()]
    digests = {
        r[2]: r[3]
        for r in (json.loads(x) for x in (out / "digests.jsonl").read_text().splitlines())
    }
    assert digests == {i: digests[i] for i in range(1, 8)}  # 7 records -> 7 digest rows
    by_scenario = Counter(k["scenario"] for k in keys)
    assert by_scenario == Counter(
        {
            "flaws_level6_marker": 4,
            "flaws_user_backup": 1,
            "flaws_imds_ip": 1,
            "flaws_bucket": 1,
            "flaws_persistence": 1,
            "flaws_chain": 1,
        }
    )
    assert {k["line"] for k in keys} == {2, 3, 4, 5, 6, 7}  # line 1 (benign) is never keyed
    chain = next(k for k in keys if k["scenario"] == "flaws_chain")
    assert chain["digest"] == digests[7]  # the CreateAccessKey record is the chain pivot
    assert chain["chain"] == [digests[4], digests[5], digests[7]]


def test_keys_flaws_splunk_locators_and_extra(tmp_path, capsys):
    extra = tmp_path / "cited.json"
    extra.write_text(
        json.dumps(
            [
                {
                    "dataset": "hb_flaws_aws",
                    "scenario": "attacker_key",
                    "value": "AKIAEXAMPLE12345678",
                    "role": "artefact",
                    "citations": ["out of band"],
                }
            ]
        )
    )
    rc = keys_flaws.main(["--splunk", "hb_flaws_aws", "--extra", str(extra)])
    lines = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert len(lines) == len(keys_flaws._IN) + 1
    assert all("index=hb_flaws_aws" in line for line in lines)
    assert "AKIAEXAMPLE12345678" in lines[-1]
