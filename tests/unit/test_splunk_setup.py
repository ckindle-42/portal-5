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

from scripts.lab.splunk_setup import cli, conf, host, plan, reindex, rest

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
        {
            "acct": "root",
            "exe": "/usr/sbin/cron",
            "uid": "0",
            "auid": "4294967295",
            "terminal": "cron",
        },
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

#: One real line of the shipper copy D6 routes out (`/logstash/internal-share/2022-01-13-system.auth.log`):
#: the username ends at the JSON quote, which is what `\S+` used to swallow.
FILEBEAT_JSON_AUTH = (
    '{"message":"Mar 22 15:06:01 aecid-samba-4 sudo: pam_unix(sudo:session): session closed for '
    'user root","@version":"1","log":{"offset":0,"file":{"path":"/var/log/auth.log"}},'
    '"service":{"type":"system"},"fileset":{"name":"auth"},"agent":{"id":'
    '"24e81722-73d2-4687-b08f-a44872cdd879","hostname":"internal-share","ephemeral_id":'
    '"841e5a0c-4d59-41a8-9855-d83605fdeb4f","type":"filebeat","version":"7.13.2",'
    '"name":"internal-share"},"input":{"type":"log"},"host":{"name":"internal-share"},'
    '"@timestamp":"2022-01-13T14:31:36.097Z","tags":["beats_input_codec_plain_applied"],'
    '"event":{"module":"system","dataset":"system.auth","timezone":"+00:00"},'
    '"ecs":{"version":"1.9.0"}}'
)


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


def test_shipped_conf_is_rendered_from_the_plan_and_extracts(tmp_path: Path) -> None:
    """The committed app tree is exactly the renderer's output, and it extracts on real lines."""
    assert conf.diff_app(APP_ROOT) == []
    rendered = conf.conf_files()
    assert "macros.conf" not in rendered  # the CIM app owns the macro; a copy here loses to it
    assert "datamodels.conf" not in rendered  # and the model object, so acceleration is REST
    assert not (APP_ROOT / plan.APP_NAME / "default" / "datamodels.conf").exists()
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
    # an index-time value only reaches the tsidx (and so tstats) when the transform writes meta
    assert transforms.count("WRITE_META = true") == sum(len(f) for f in conf.INDEX_FIELDS.values())
    assert transforms.count("WRITE_META = true") == transforms.count("[ph_ix_")
    # an app installed before the drop keeps the file: tar overwrites, so the installer removes it
    conf.write_app(tmp_path, with_change=True)
    stale = tmp_path / plan.APP_NAME / "default" / "datamodels.conf"
    stale.write_text("[Web]\nacceleration = true\n")
    conf.write_app(tmp_path)
    assert not stale.exists()
    assert f"rm -f /opt/splunk/etc/apps/{plan.APP_NAME}/default/datamodels.conf" in (
        host.install_command(plan.APP_NAME)
    )


def test_vhost_combined_lines_keep_the_client_in_c_ip() -> None:
    """`other_vhosts_access.log` is `vhost:port client - - [...]`: c_ip is the client, not the vhost."""
    fields = conf.INDEX_FIELDS["access_combined"]
    vhost_line = (
        "cloud.dmz.smith.santos.com:443 172.21.129.224 - - [17/Jan/2022:06:38:41 +0000] "
        '"GET / HTTP/1.1" 302 4067 "-" "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) HeadlessChrome/95.0.4638.69 Safari/537.36"'
    )
    assert re.search(fields["c_ip"], vhost_line).group(1) == "172.21.129.224"
    assert re.search(fields["c_user"], vhost_line).group(1) == "-"
    assert re.search(fields["vhost"], vhost_line).group(1) == "cloud.dmz.smith.santos.com"
    combined = REAL_LINES["access_combined"][0]
    assert re.search(fields["c_ip"], combined).group(1) == "10.229.1.182"
    assert re.search(fields["vhost"], combined) is None
    # an IPv6 client is not a `vhost:port` prefix, so `::1` stays the c_ip
    ipv6 = (
        '::1 - - [17/Jan/2022:06:32:17 +0000] "OPTIONS * HTTP/1.0" 200 110 "-" '
        '"Apache/2.4.29 (Ubuntu) OpenSSL/1.1.1 (internal dummy connection)"'
    )
    assert re.search(fields["c_ip"], ipv6).group(1) == "::1"
    # one sourcetype, and the vhost is an indexed field `tstats` can group by
    assert plan.classify("other_vhosts_access.log").target == "access_combined"
    transforms, props, fields_conf = (
        conf.conf_files()[name] for name in ("transforms.conf", "props.conf", "fields.conf")
    )
    assert "[ph_ix_access_combined_vhost]" in transforms and "FORMAT = vhost::$1" in transforms
    assert "ph_ix_access_combined_vhost" in props and "EVAL-site = vhost" in props
    assert "[vhost]\nINDEXED = true" in fields_conf
    assert "vhost_indexed" in {p.name for p in plan.verify_probes(plan.TUNED_BY_KEY["santos"])}


def test_index_time_user_and_auid_are_the_real_values() -> None:
    """A JSON shape stops at the quote, and `auid` reaches the tsidx beside `uid`."""
    fields = conf.INDEX_FIELDS["linux_secure"]
    match = re.search(fields["user"], FILEBEAT_JSON_AUTH)
    assert match and match.group(1) == "root"
    assert re.search(fields["user"], REAL_LINES["linux_secure"][0]).group(1) == "root"
    audit = (
        "type=LOGIN msg=audit(1642420697.752:2279): pid=20750 uid=0 old-auid=4294967295 "
        "auid=1002 tty=(none) old-ses=4294967295 ses=318 res=1"
    )
    assert re.search(conf.INDEX_FIELDS["linux_audit"]["auid"], audit).group(1) == "1002"
    rendered = conf.conf_files()
    assert "[auid]\nINDEXED = true" in rendered["fields.conf"]
    assert "ph_ix_linux_audit_auid" in rendered["props.conf"]
    assert (
        "[ph_ix_linux_audit_auid]\nREGEX = (?:^|\\s)auid=(\\d+)\nFORMAT = auid::$1"
        in (rendered["transforms.conf"])
    )


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
        {
            "host": "ws",
            "source": "/logstash/ws/2022-01-13-system.service.log",
            "sourcetype": "2022-01-13-system.service.log",
            "sent": 5000,
        },
        {
            "host": "ws",
            "source": "/logstash/ws/2022-01-13-system.auth.log",
            "sourcetype": "2022-01-13-system.auth.log",
            "sent": 70,
        },
        {
            "host": "ws",
            "source": "/journal/x/system.journal.txt",
            "sourcetype": "system.journal.txt",
            "sent": 900,
        },
    ]
    built = plan.build_reindex_plan(spec, files, root=tmp_path)
    shipped = [row for row in built.rows if row.sourcetype_out]
    assert {row.index for row in shipped} == {spec.target_index}
    assert spec.target_index == f"{spec.source_index}_v2"
    assert [row.sourcetype_out for row in shipped] == ["suricata", "linux_secure"]
    assert built.noise_total == 6077 and built.kept_total == 60
    assert built.source_total == built.kept_total + built.noise_total
    # one event family, one copy: the shipper's JSON re-ship and the journald export are dropped
    copies = [
        "2022-01-13-system.service.log",
        "2022-01-13-system.auth.log",
        "2022-01-13-system.syslog.log",
        "system.journal.txt",
    ]
    assert [plan.classify(name).target for name in copies] == [None] * len(copies)
    assert all(plan.classify(name).kind == "noise" for name in copies)
    # a per-user journal holds events no other file has, so it is not a duplicate
    assert plan.classify("user-1000.journal.txt").target == "syslog"
    kept = plan.build_reindex_plan(spec, files, keep_metrics=True, root=tmp_path)
    assert "metricbeat:system" in {row.sourcetype_out for row in kept.rows}
    with pytest.raises(SystemExit):
        cli._spec(plan.CONTROL_INDEX)
    tree = tmp_path / "host" / "logs"
    tree.mkdir(parents=True)
    (tree / "auth.log").write_text("x\n")
    assert reindex.resolve_path(tmp_path, "host", "/auth.log") == tree / "auth.log"


def test_reindex_refuses_to_ship_into_an_index_the_box_does_not_have(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A DELETE removes the index, not the recipe's memory of it: on 2026-11-21 a rebuild shipped
    7,260,795 events into three deleted indexes — HEC 200-acked every batch (the receipt read
    `shipped == expected`) while the indexer dropped them (`lastChanceIndex` unset). The ship must
    stop before the first post when the target index is not on the box."""
    shipped: list[str] = []
    monkeypatch.setattr(
        cli.reindex, "make_plan", lambda spec, keep_metrics=False: plan.ReindexPlan(spec=spec)
    )

    def fake_ship(*_args, **_kwargs) -> reindex.ShipReceipt:
        shipped.append("called")
        return reindex.ShipReceipt(index="x", root="r")

    monkeypatch.setattr(cli.reindex, "ship", fake_ship)

    class _Svc:
        def __init__(self, settings: dict | None) -> None:
            self._settings = settings

        def index_settings(self, _name: str) -> dict | None:
            return self._settings

        def search(self, _spl: str, **_kwargs) -> rest.SearchResult:
            return rest.SearchResult(rows=[{"count": "0"}])

    monkeypatch.setattr(cli.rest, "SplunkREST", lambda transport=None: _Svc(None))
    with pytest.raises(SystemExit) as stopped:
        cli.main(["reindex", "--index", "santos", "--ship"])
    assert "does not exist" in str(stopped.value)
    assert shipped == []

    monkeypatch.setattr(
        cli.rest, "SplunkREST", lambda transport=None: _Svc({"maxTotalDataSizeMB": "20000"})
    )
    assert cli.main(["reindex", "--index", "santos", "--ship"]) == 0
    assert shipped == ["called"]


_ORIGINAL_V2 = (
    "hb_kyoushi_s1_v2",
    "hb_ait_santos_v2",
    "hb_ait_russellmitchell_v2",
)
_EXTENDED_HUNT = (
    "hb_ait_fox",
    "hb_ait_harrison",
    "hb_ait_shaw",
    "hb_ait_wardbeck",
    "hb_ait_wilson",
    "hb_flaws_aws",
    "hb_uwf_zeek24",
    "hb_lmd_2023",
    "hb_lmd_2023_v2",
    "hb_ics_pcap",
    "hb_otrf_apt3",
    "hb_cyber4ot",
    "hb_iec104",
    "hb_sherlock_grid",
    "hb_icssim",
    "hb_pdmfc_ot",
    "hb_robotdog_audit",
)


def test_cim_macros_name_extended_indexes_and_exclude_botsv2() -> None:
    """Every accelerated model's allowlist macro covers the _v2 indexes and the extended corpora."""
    definition = plan.cim_macro_definition()
    assert plan.cim_macros() == tuple(f"cim_{model}_indexes" for model in plan.ACCELERATED)
    assert len(plan.cim_macros()) == 6
    for name in _ORIGINAL_V2 + _EXTENDED_HUNT:
        assert f"index={name}" in definition
    assert plan.cim_allowlist_indexes() == _ORIGINAL_V2 + _EXTENDED_HUNT
    assert plan.CONTROL_INDEX not in definition
    assert "botsv2" not in definition
    assert definition.count(" OR ") == len(_ORIGINAL_V2 + _EXTENDED_HUNT) - 1


def test_acceleration_scope_window_and_control() -> None:
    """Only the doc's models are accelerated, over the whole corpus span, never the control."""
    settings = plan.accel_settings()
    assert settings["acceleration"] == "true"
    assert settings["acceleration.earliest_time"] == plan.ACCEL_WINDOW == "-10y"
    assert settings["acceleration.cron_schedule"] == "*/10 * * * *"
    assert settings["acceleration.max_concurrent"] == "1"
    assert plan.accelerated_models() == (
        "Authentication",
        "Endpoint",
        "Intrusion_Detection",
        "Network_Resolution",
        "Network_Traffic",
        "Web",
    )
    assert plan.accelerated_models(with_change=True)[-1] == "Change"
    assert plan.CIM_APP == "Splunk_SA_CIM"
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
        self.macros = dict.fromkeys(plan.cim_macros(True), plan.CIM_DEFAULT_DEFINITION)
        self.defaults = {
            model: {"enabled": False, "earliest_time": "-1y"}
            for model in plan.accelerated_models(with_change=True)
        }
        self.models = {model: dict(state) for model, state in self.defaults.items()}

    def _datamodel(self, method: str, path: str, data):
        """Only Splunk_SA_CIM's row reaches the model: a copy in any other app reports nothing."""
        clean = path.split("?")[0]
        app = clean.split("/servicesNS/nobody/")[-1].split("/")[0]
        model = clean.rsplit("/", 1)[-1]
        if app == plan.CIM_APP and method == "POST":
            current = self.models[model]
            self.models[model] = {
                "enabled": str(data.get("acceleration", "")).lower() == "true",
                "earliest_time": data.get("acceleration.earliest_time", current["earliest_time"]),
            }
        if app == plan.CIM_APP and method == "DELETE":
            self.models[model] = dict(self.defaults[model])
        return {"entry": [{"content": {"acceleration": dict(self.models[model])}}]}

    def _config(self, method: str, path: str, data):
        name = path.split("/configs/conf-macros/")[-1].split("?")[0]
        if method == "POST":
            self.macros[name] = data["definition"]
        if name not in self.macros:
            raise rest.SplunkError("404", status=404)
        return {"entry": [{"content": {"definition": self.macros[name]}}]}

    def __call__(self, method: str, path: str, data):
        if method == "POST":
            self.writes.append((path, json.dumps(data, sort_keys=True)))
        if "/configs/conf-macros/" in path:
            return self._config(method, path, data)
        if "/datamodel/model/" in path or "/configs/conf-datamodels/" in path:
            return self._datamodel(method, path, data or {})
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
    macro, definition = plan.cim_macros()[0], plan.cim_macro_definition()

    def run() -> list[rest.Action]:
        return [
            svc.ensure_app("Splunk_TA_nix", enabled=True),
            svc.ensure_index("hb_kyoushi_s1_v2", settings),
            svc.ensure_hec_index("portal5-hec-token-2026", "hb_kyoushi_s1_v2"),
            svc.ensure_macro(plan.CIM_APP, macro, definition),
        ]

    first = run()
    writes_after_first = list(fake.writes)
    second = run()
    assert [a.changed for a in first] == [True, False, False, True]
    assert writes_after_first == [
        ("/services/apps/local/Splunk_TA_nix/enable?output_mode=json", "null"),
        (
            f"/servicesNS/nobody/{plan.CIM_APP}/configs/conf-macros/{macro}?output_mode=json",
            json.dumps({"definition": definition}, sort_keys=True),
        ),
    ]
    assert fake.macros[macro] == definition
    assert [a.changed for a in second] == [False, False, False, False]
    assert fake.writes == writes_after_first
    restored = svc.ensure_macro(plan.CIM_APP, macro, plan.CIM_DEFAULT_DEFINITION)
    assert restored.changed and fake.macros[macro] == plan.CIM_DEFAULT_DEFINITION
    assert reindex.make_plan  # the driver is importable without a live Splunk


def test_verify_fails_a_zero_row_entity_tstats(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The property is tstats rows, not the conf text: a `by acct` that returns nothing fails."""
    spec = plan.TUNED_BY_KEY["santos"]

    class _Svc:
        zero = spec.target_index
        absent_rows: list[dict[str, str]] = []

        def macro_expansion(self, macro: str) -> str:
            return f"litsearch {plan.cim_macro_definition()}"

        def search(self, spl: str, **_kwargs) -> rest.SearchResult:
            if "/data/models" in spl:
                rows = [
                    {"title": model, "acceleration.earliest_time": plan.ACCEL_WINDOW}
                    for model in plan.ACCELERATED
                ]
                return rest.SearchResult(rows=rows)
            if "/services/admin/summarization" in spl:
                rows = [
                    {
                        "summary.id": f"DM_{plan.CIM_APP}_{model}",
                        "summary.size": "1024",
                        "summary.complete": "1",
                    }
                    for model in plan.ACCELERATED
                ]
                # a child object is its own id; only the six model roots are checked
                rows.append(
                    {
                        "summary.id": f"DM_{plan.CIM_APP}_Endpoint.Processes",
                        "summary.size": "0",
                        "summary.complete": "1",
                    }
                )
                return rest.SearchResult(rows=rows)
            if "hunt_entities_index=" in spl:
                return rest.SearchResult(rows=[{"count": "7"}])
            if 'source="*system' in spl or "length(user) > 64" in spl:
                # live Splunk: a bare no-match count still answers one {"count": "0"} row
                rows = list(self.absent_rows) if " by " in spl else [{"count": "0"}]
                return rest.SearchResult(rows=rows, run_seconds=0.1)
            zero = self.zero
            rows = [] if zero and f"index={zero}" in spl and "by acct" in spl else [{"count": "1"}]
            return rest.SearchResult(rows=rows, run_seconds=0.1)

    monkeypatch.setattr(cli.rest, "SplunkREST", lambda transport=None: _Svc())
    for key, tuned in plan.TUNED_BY_KEY.items():
        _Svc.zero, _Svc.absent_rows = tuned.target_index, [{"count": "3"}, {"count": "1"}]
        args = cli.build_parser().parse_args(["verify", "--index", key])
        assert cli.cmd_verify(args) == 1
        report = json.loads(capsys.readouterr().out)
        assert {"acceleration_window", "summaries_complete"} <= {row["name"] for row in report}
        failed = {row["name"]: row for row in report if not row["ok"]}
        # the absence probes fail on rows, not on a missing conf line
        assert set(failed) == {
            f"entity_indexed:{tuned.target_index}",
            "service_log_absent",
            "user_clean",
        }
        assert "got fewer than 1 rows" in str(failed[f"entity_indexed:{tuned.target_index}"])
        assert "got more than 0 rows" in str(failed["service_log_absent"]["detail"])
        summaries = {row["name"]: row for row in report}["summaries_complete"]
        assert summaries["ok"] is True and "complete 6/6" in summaries["detail"]
        assert "auid_indexed" in {row["name"] for row in report}

    args = cli.build_parser().parse_args(["verify", "--index", "santos"])
    _Svc.zero, _Svc.absent_rows = "", []
    assert cli.cmd_verify(args) == 0


def test_verify_judges_the_parser_expansion_not_the_conf_row(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The macro passes only when the parser expands it to the whole allowlist; `()` fails, and a
    check that raises is one FAIL row while every other check is still reported."""
    expansion = f"litsearch {plan.cim_macro_definition()}"

    class _Svc:
        def macro_expansion(self, macro: str) -> str:
            if macro == "cim_Endpoint_indexes":
                raise rest.SplunkError("POST parser -> 400: bad q", status=400)
            return expansion if macro == "cim_Web_indexes" else "litsearch ()"

        def search(self, spl: str, **_kwargs) -> rest.SearchResult:
            raise rest.SplunkError("offline: search job unavailable")

    monkeypatch.setattr(cli.rest, "SplunkREST", lambda transport=None: _Svc())
    args = cli.build_parser().parse_args(["verify"])
    assert cli.cmd_verify(args) == 1
    rows = {row["name"]: row for row in json.loads(capsys.readouterr().out)}
    assert set(rows) == (
        {f"cim_macro:{macro}" for macro in plan.cim_macros()}
        | {"acceleration_window", "summaries_complete"}
        | {f"summary_index:{spec.source_index}" for spec in plan.TUNED}
        | {probe.name for probe in plan.CONTROL_PROBES}
    )
    assert rows["cim_macro:cim_Web_indexes"]["ok"] is True
    assert rows["cim_macro:cim_Web_indexes"]["detail"] == expansion
    assert rows["cim_macro:cim_Authentication_indexes"]["ok"] is False
    assert "does not name" in str(rows["cim_macro:cim_Authentication_indexes"]["detail"])
    assert rows["cim_macro:cim_Endpoint_indexes"]["ok"] is False
    assert "400" in str(rows["cim_macro:cim_Endpoint_indexes"]["detail"])
    assert rows["acceleration_window"]["ok"] is False
    assert "offline" in str(rows["acceleration_window"]["detail"])


def test_verify_rejects_a_partial_allowlist_and_the_control_index() -> None:
    """Three `_v2` indexes are not enough, and naming botsv2 fails the macro check."""
    partial = "(" + " OR ".join(f"index={name}" for name in _ORIGINAL_V2) + ")"

    class _Partial:
        def macro_expansion(self, macro: str) -> str:
            return f"litsearch {partial}"

    class _Control:
        def macro_expansion(self, macro: str) -> str:
            return f"litsearch {plan.cim_macro_definition()} OR index=botsv2"

    class _Full:
        def macro_expansion(self, macro: str) -> str:
            return f"litsearch {plan.cim_macro_definition()}"

    for macro in plan.cim_macros():
        partial_ok, partial_detail = cli._macro_check(_Partial(), macro)  # type: ignore[arg-type]
        assert partial_ok is False
        assert "hb_ait_fox" in partial_detail and "hb_ics_pcap" in partial_detail
        control_ok, control_detail = cli._macro_check(_Control(), macro)  # type: ignore[arg-type]
        assert control_ok is False and "botsv2" in control_detail
        full_ok, full_detail = cli._macro_check(_Full(), macro)  # type: ignore[arg-type]
        assert full_ok is True
        for name in _ORIGINAL_V2 + _EXTENDED_HUNT:
            assert name in full_detail


def test_cim_command_rebuilds_acceleration_without_touching_indexes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`cim` writes the six macros and rebuilds DMA; a second run writes nothing and no index."""
    fake = _FakeSplunk()
    for model in fake.models:
        fake.models[model] = {"enabled": True, "earliest_time": "-10y"}
    real = rest.SplunkREST
    monkeypatch.setattr(cli.rest, "SplunkREST", lambda transport=None: real(transport=fake))
    args = cli.build_parser().parse_args(["cim", "--offline"])
    assert cli.cmd_cim(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["indexes_written"] == []
    assert report["definition"] == plan.cim_macro_definition()
    macro_writes = [path for path, _body in fake.writes if "/configs/conf-macros/" in path]
    assert len(macro_writes) == len(plan.cim_macros())
    for macro in plan.cim_macros():
        assert any(macro in path for path in macro_writes)
        assert fake.macros[macro] == plan.cim_macro_definition()
    model_posts = [
        json.loads(body) for path, body in fake.writes if "/configs/conf-datamodels/" in path
    ]
    assert model_posts[0::2] == [{"acceleration": "false"}] * len(plan.ACCELERATED)
    assert model_posts[1::2] == [plan.accel_settings()] * len(plan.ACCELERATED)
    assert all("rebuilt over -10y" in str(row["detail"]) for row in report["actions"][6:])
    assert not any(
        "/services/data/indexes" in path or "/saved/searches/" in path
        for path, _body in fake.writes
    )
    writes_after_first = list(fake.writes)
    assert cli.cmd_cim(args) == 0
    second = json.loads(capsys.readouterr().out)
    assert fake.writes == writes_after_first
    assert [row["changed"] for row in second["actions"]] == [False] * (
        len(plan.cim_macros()) + len(plan.ACCELERATED)
    )


def test_cim_dry_run_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSplunk()
    real = rest.SplunkREST
    monkeypatch.setattr(cli.rest, "SplunkREST", lambda transport=None: real(transport=fake))
    args = cli.build_parser().parse_args(["cim", "--offline", "--dry-run"])
    assert cli.cmd_cim(args) == 0
    assert fake.writes == []
    assert set(fake.macros.values()) == {plan.CIM_DEFAULT_DEFINITION}


def test_acceleration_is_written_where_the_model_reports_it() -> None:
    """`apply --accelerate` writes Splunk_SA_CIM's row; the model endpoint is what decides a write."""
    fake = _FakeSplunk()
    svc = rest.SplunkREST(transport=fake)
    first = cli._accelerate(svc, with_change=False, dry_run=False)
    assert [action["changed"] for action in first] == [True] * len(plan.ACCELERATED)
    assert [path for path, _data in fake.writes] == [
        f"/servicesNS/nobody/{plan.CIM_APP}/configs/conf-datamodels/{model}?output_mode=json"
        for model in plan.accelerated_models()
    ]
    assert json.loads(fake.writes[0][1]) == plan.accel_settings()
    assert fake.models["Authentication"] == {"enabled": True, "earliest_time": "-10y"}
    # idempotent: the second run reads the models and writes nothing
    writes_after_first = list(fake.writes)
    second = cli._accelerate(svc, with_change=False, dry_run=False)
    assert [action["changed"] for action in second] == [False] * len(plan.ACCELERATED)
    assert fake.writes == writes_after_first
    # rollback drops the local row, so the model reports the CIM default again
    reverted = [
        svc.revert_datamodel_acceleration(plan.CIM_APP, model)
        for model in plan.accelerated_models()
    ]
    assert all(action.changed for action in reverted)
    assert fake.models["Web"] == fake.defaults["Web"]
    assert not svc.revert_datamodel_acceleration(plan.CIM_APP, "Web").changed


def test_datamodel_acceleration_parses_splunk_10_2_5_json_string() -> None:
    """Splunk 10.2.5 reports content.acceleration as a JSON string, not a dict or flat keys."""

    def payload(acceleration: object, **flat: str) -> rest.SplunkREST:
        content: dict[str, object] = {"acceleration": acceleration, **flat}
        return rest.SplunkREST(transport=lambda *_: {"entry": [{"content": content}]})

    state = payload('{"enabled": true, "earliest_time": "-10y"}').datamodel_acceleration(
        plan.CIM_APP, "Authentication"
    )
    assert state == {"enabled": True, "earliest_time": "-10y"}
    # invalid JSON falls back to the flat acceleration.* keys instead of raising
    fallback = payload(
        "not-json", **{"acceleration.enabled": "1", "acceleration.earliest_time": "-30d"}
    ).datamodel_acceleration(plan.CIM_APP, "Web")
    assert fallback == {"enabled": True, "earliest_time": "-30d"}


def test_verify_fails_a_model_that_reports_no_acceleration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stage 3's property is the model endpoint: enabled over `-10y`, not the conf row."""

    class _Svc:
        reports = {
            model: {"enabled": True, "earliest_time": plan.ACCEL_WINDOW}
            for model in plan.accelerated_models()
        }

        def macro_expansion(self, macro: str) -> str:
            return f"litsearch {plan.cim_macro_definition()}"

        def search(self, spl: str, **_kwargs) -> rest.SearchResult:
            return rest.SearchResult(rows=[{"count": "1"}])

        def datamodel_acceleration(self, app: str, model: str) -> dict:
            return dict(self.reports[model])

    svc = _Svc()
    clean = {row["name"]: row for row in cli._model_rows(svc)}
    assert set(clean) == {f"acceleration:{model}" for model in plan.ACCELERATED}
    assert all(row["ok"] for row in clean.values())
    svc.reports["Web"] = {"enabled": False, "earliest_time": "-1y"}
    svc.reports["Endpoint"] = {"enabled": True, "earliest_time": "-3mon"}
    report = {row["name"]: row for row in cli._model_rows(svc)}
    assert {name for name, row in report.items() if not row["ok"]} == {
        "acceleration:Web",
        "acceleration:Endpoint",
    }
    assert "reports enabled=False -1y" in report["acceleration:Web"]["detail"]
    assert cli.build_parser().parse_args(["verify", "--accelerate"]).accelerate
    # the flag wires those rows into the JSON report
    monkeypatch.setattr(cli.rest, "SplunkREST", lambda transport=None: _Svc())
    svc.reports["Web"] = {"enabled": True, "earliest_time": plan.ACCEL_WINDOW}
    svc.reports["Endpoint"] = {"enabled": True, "earliest_time": plan.ACCEL_WINDOW}
    args = cli.build_parser().parse_args(["verify", "--accelerate"])
    assert cli.cmd_verify(args) == 1  # control probes return one row from the fake
    rows = {row["name"]: row for row in json.loads(capsys.readouterr().out)}
    assert {f"acceleration:{model}" for model in plan.ACCELERATED} <= set(rows)


def test_macro_expansion_reads_the_parser_endpoint() -> None:
    """The live API answers a POST to `nobody/search/search/parser` with `normalizedSearch`."""
    calls: list[tuple[str, str, dict[str, str] | None]] = []

    def transport(method: str, path: str, data):
        calls.append((method, path, data))
        return {"normalizedSearch": f"litsearch {plan.cim_macro_definition()}"}

    expansion = rest.SplunkREST(transport=transport).macro_expansion("cim_Web_indexes")
    assert expansion == f"litsearch {plan.cim_macro_definition()}"
    assert calls == [
        (
            "POST",
            "/servicesNS/nobody/search/search/parser?output_mode=json",
            {"q": "search `cim_Web_indexes`"},
        )
    ]
    other = rest.SplunkREST(transport=lambda *_: {"optimizedSearch": expansion})
    with pytest.raises(rest.SplunkError):
        other.macro_expansion("cim_Web_indexes")


def test_cim_objects_are_global_and_alias_the_dns_and_process_fields() -> None:
    """The accelerator searches in Splunk_SA_CIM: app-scoped tags are invisible there."""
    meta = (APP_ROOT / plan.APP_NAME / "metadata" / "default.meta").read_text()
    assert "export = system" in meta
    rendered = conf.conf_files()
    tags, props = rendered["tags.conf"], rendered["props.conf"]
    assert (
        "[eventtype=ph_dns_dnsmasq]\nnetwork = enabled\nresolution = enabled\ndns = enabled" in tags
    )
    assert "EVAL-query = dns_query" in props
    assert "EVAL-process = comm" in props and "EVAL-process_path = exe" in props
    assert "EVAL-parent_process_id = ppid" in props


def test_apply_materialises_a_cim_lookup_shipped_as_default(monkeypatch) -> None:
    """The box's Splunk_SA_CIM has only `cim_dns_reply_codes2.csv.default`; the model needs the csv."""
    calls: list[list[str]] = []

    class _Run:
        returncode = 0
        stdout = "copied\n"
        stderr = ""

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        return _Run()

    monkeypatch.setattr(host.subprocess, "run", fake_run)
    assert host.ensure_lookup_file(plan.CIM_APP, plan.CIM_DNS_LOOKUP_FILE) == "copied"
    remote = calls[0][-1]
    assert plan.CIM_DNS_LOOKUP_FILE in remote and "cp " in remote
    assert "$f.default" in remote
