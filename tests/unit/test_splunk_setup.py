"""The Splunk setup scripts: normalisation, rendered conf, reindex scope, acceleration, summaries.

Sample lines in ``REAL_LINES`` are copied verbatim from the corpora the reindex reads
(``/Volumes/data01/portal5_hunt/corpora/...``), so the index-time regexes are exercised on the
bytes they will meet, not on a hand-made shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.lab.splunk_setup import cli, conf, plan, reindex, rest

APP_ROOT = Path(conf.__file__).parent / "app"

REAL_LINES: dict[str, tuple[str, dict[str, str]]] = {
    "linux_secure": (
        "Jan 16 06:25:02 inet-dns CRON[17665]: pam_unix(cron:session): session closed for user root",
        {"user": "root"},
    ),
    "linux_audit": (
        "type=USER_ACCT msg=audit(1642118941.127:1320): pid=6526 uid=0 auid=4294967295 "
        'ses=4294967295 msg=\'op=PAM:accounting acct="root" exe="/usr/sbin/cron" '
        "hostname=? addr=? terminal=cron res=success'",
        {"acct": "root", "exe": "/usr/sbin/cron", "uid": "0", "terminal": "cron"},
    ),
    "access_combined": (
        '10.229.1.182 - - [13/Jan/2022:14:45:34 +0000] "GET /login.php HTTP/1.1" 200 2458 '
        '"-" "Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/95.0.4638.69 Safari/537.36"',
        {
            "c_ip": "10.229.1.182",
            "c_user": "-",
            "cs_method": "GET",
            "cs_uri_stem": "/login.php",
            "sc_status": "200",
        },
    ),
    "suricata:fast": (
        "01/17/2022-11:21:43.696785  [**] [1:2220006:1] SURICATA SMTP no server welcome message "
        "[**] [Classification: Generic Protocol Command Decode] [Priority: 3] {TCP} "
        "172.21.131.50:587 -> 172.21.128.119:34318",
        {
            "signature_id": "2220006",
            "signature": "SURICATA SMTP no server welcome message",
            "severity": "3",
            "src": "172.21.131.50",
            "dest": "172.21.128.119",
        },
    ),
    "dnsmasq": (
        "Mar 22 20:36:39 dnsmasq[3460]: query[SRV] _http._tcp.archive.ubuntu.com from 192.42.165.180",
        {"dns_query": "_http._tcp.archive.ubuntu.com", "src": "192.42.165.180"},
    ),
}


def test_every_ingested_sourcetype_normalises() -> None:
    """227 measured names (289 with per-family repeats) must all land on one data type."""
    inventory = plan.load_inventory()
    unmapped, names = [], set()
    for entry in inventory["indexes"].values():
        for sourcetype in entry["sourcetypes"]:
            names.add(sourcetype)
            route = plan.classify(sourcetype)
            if route.target is None and route.note == "unmapped":
                unmapped.append(sourcetype)
            assert route.target is None or route.target in plan.TARGETS
    assert len(names) >= 200
    assert unmapped == []
    assert len({plan.classify(n).target for n in names if plan.classify(n).target}) <= 20


def test_shipped_conf_is_rendered_from_the_plan_and_extracts() -> None:
    """The committed app tree is exactly the renderer's output, and it extracts on real lines."""
    assert conf.diff_app(APP_ROOT) == []
    rendered = conf.conf_files()
    transforms = rendered["transforms.conf"]
    fields = rendered["fields.conf"]
    props = rendered["props.conf"]
    for sourcetype in REAL_LINES:
        for field in conf.INDEX_FIELDS[sourcetype]:
            stanza = f"[ph_ix_{conf._slug(sourcetype)}_{field}]"
            assert stanza in transforms
            assert f"ph_ix_{conf._slug(sourcetype)}_{field}" in props
            assert f"[{field}]" in fields
    for sourcetype, (line, expected) in REAL_LINES.items():
        for field, value in expected.items():
            match = re.search(conf.INDEX_FIELDS[sourcetype][field], line)
            assert match and match.group(1) == value, (sourcetype, field)


def test_reindex_writes_only_new_indexes_and_routes_noise_out(tmp_path: Path) -> None:
    """A receipt row can only ever land in <index>_v2, and noise is counted, never shipped."""
    spec = plan.TUNED_BY_KEY["santos"]
    files = [
        {"host": "ws", "source": "/suricata/stats.log", "sourcetype": "stats.log", "sent": 100},
        {"host": "ws", "source": "/suricata/eve.json", "sourcetype": "eve.json", "sent": 50},
        {"host": "ws", "source": "/auth.log", "sourcetype": "auth.log", "sent": 10},
        {
            "host": "ws",
            "source": "/2022-01-13-system.cpu.log",
            "sourcetype": "2022-01-13-system.cpu.log",
            "sent": 7,
        },
    ]
    built = plan.build_reindex_plan(spec, files, root=tmp_path)
    shipped = [row for row in built.rows if row.sourcetype_out]
    assert {row.index for row in shipped} == {spec.target_index}
    assert spec.target_index == f"{spec.source_index}_v2"
    assert [row.sourcetype_out for row in shipped] == ["suricata", "linux_secure"]
    assert built.noise_total == 107 and built.kept_total == 60
    assert built.source_total == built.kept_total + built.noise_total
    kept = plan.build_reindex_plan(spec, files, keep_metrics=True, root=tmp_path)
    assert "metricbeat:system" in {row.sourcetype_out for row in kept.rows}
    with pytest.raises(SystemExit):
        cli._spec(plan.CONTROL_INDEX)
    tree = tmp_path / "host" / "logs"
    tree.mkdir(parents=True)
    (tree / "auth.log").write_text("x\n")
    assert reindex.resolve_path(tmp_path, "host", "/auth.log") == tree / "auth.log"


def test_acceleration_scope_window_and_control() -> None:
    """Only the doc's models are accelerated, over the whole corpus span, never the control."""
    text = conf.datamodels_conf()
    assert set(re.findall(r"^\[(\w+)\]$", text, re.M)) == set(plan.ACCELERATED)
    assert text.count(f"acceleration.earliest_time = {plan.ACCEL_WINDOW}") == len(plan.ACCELERATED)
    assert plan.ACCEL_WINDOW == "-10y"  # a -90d window would cover no event in these corpora
    with_change = conf.datamodels_conf(with_change=True)
    assert "[Change]" in with_change and "[Change]" not in text
    assert plan.CONTROL_INDEX not in " ".join(s.target_index for s in plan.TUNED)
    assert plan.CONTROL_INDEX not in " ".join(s.source_index for s in plan.TUNED)


def test_one_collect_summary_per_tuned_index() -> None:
    """Stage 4: exactly one scheduled ``collect`` per tuned index, each with its own marker."""
    text = conf.savedsearches_conf()
    stanzas = re.findall(r"^\[(ph_hunt_summary_\w+)\]$", text, re.M)
    assert stanzas == [spec.summary_search for spec in plan.TUNED]
    for spec in plan.TUNED:
        body = conf.summary_search(spec)
        assert f"index={spec.target_index}" in body
        assert "| collect index=summary" in body
        assert f"hunt_entities_index={spec.source_index}" in body
    assert len(set(re.findall(r"hunt_entities_index=(\w+)", text))) == len(plan.TUNED)


class _FakeSplunk:
    """Stateful stand-in for the REST endpoints the setup mutates; counts writes."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, str]] = []
        self.indexes = {
            "hb_kyoushi_s1_v2": {
                "maxTotalDataSizeMB": "20000",
                "frozenTimePeriodInSecs": "365000000",
            }
        }
        self.apps = {"Splunk_TA_nix": True}

    def __call__(self, method: str, path: str, data):
        if method == "POST":
            self.writes.append((path, json.dumps(data, sort_keys=True)))
        if "/configs/" in path:
            return {"entry": []}
        if path.startswith("/services/apps/local/"):
            parts = path.split("?")[0].split("/")
            name = parts[-1]
            if method == "POST" and name in ("enable", "disable"):
                self.apps[parts[-2]] = name == "disable"
                return {}
            if name not in self.apps:
                raise rest.SplunkError("404", status=404)
            return {"entry": [{"content": {"disabled": self.apps[name]}}]}
        if path.startswith("/services/data/indexes"):
            name = path.split("/services/data/indexes")[-1].strip("/").split("?")[0]
            if method == "POST" and not name:
                self.indexes[data["name"]] = {k: v for k, v in data.items() if k != "name"}
                return {}
            if name not in self.indexes:
                raise rest.SplunkError("404", status=404)
            if method == "POST":
                self.indexes[name].update(data)
            return {"entry": [{"content": self.indexes[name]}]}
        if path.startswith("/services/data/inputs/http"):
            return {
                "entry": [
                    {
                        "name": "http://portal5-hec-token-2026",
                        "content": {
                            "token": "portal5-hec-token-2026",
                            "indexes": "portal5_lab,hb_kyoushi_s1_v2",
                        },
                    }
                ]
            }
        return {"entry": []}


def test_stage_one_apply_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second run of the mutating stage issues no write: state is read before it is changed."""
    fake = _FakeSplunk()
    svc = rest.SplunkREST(transport=fake)
    settings = {"maxTotalDataSizeMB": "20000", "frozenTimePeriodInSecs": "365000000"}
    first = [
        svc.ensure_app("Splunk_TA_nix", enabled=True),
        svc.ensure_index("hb_kyoushi_s1_v2", settings),
        svc.ensure_hec_index("portal5-hec-token-2026", "hb_kyoushi_s1_v2"),
    ]
    writes_after_first = list(fake.writes)
    second = [
        svc.ensure_app("Splunk_TA_nix", enabled=True),
        svc.ensure_index("hb_kyoushi_s1_v2", settings),
        svc.ensure_hec_index("portal5-hec-token-2026", "hb_kyoushi_s1_v2"),
    ]
    assert first[0].changed and not first[1].changed and not first[2].changed
    assert writes_after_first == [
        ("/services/apps/local/Splunk_TA_nix/enable?output_mode=json", "null")
    ]
    assert [a.changed for a in second] == [False, False, False]
    assert fake.writes == writes_after_first
    assert reindex.make_plan  # the driver is importable without a live Splunk
