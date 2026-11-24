from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.hunt_bed import lab_purple_capture as capture


def _install_mocks(
    monkeypatch: pytest.MonkeyPatch, *, logs: str = ""
) -> tuple[list[dict], list[str]]:
    target = {
        "id": "vulhub-nginx-lfi",
        "source": "vulhub",
        "path": "nginx/CVE-2017-7529",
        "host": "10.10.11.50",
        "port": 8080,
        "cve": "CVE-2017-7529",
    }
    down_calls: list[str] = []
    shipped: list[dict] = []
    monkeypatch.setattr(capture.lab_targets, "_find_target", lambda _target_id: target)
    monkeypatch.setattr(
        capture.lab_targets,
        "cmd_up",
        lambda _target_id: {"status": "running", "host": "10.10.11.50", "port": 8080},
    )
    monkeypatch.setattr(
        capture.lab_targets,
        "cmd_down",
        lambda target_id: down_calls.append(target_id) or {"status": "stopped"},
    )

    def fake_host_exec(command: str, timeout: int = 30) -> dict:
        del timeout
        if "ps --format json" in command:
            return {"ok": True, "output": '{"Name":"vulhub-nginx-1","ID":"abc123"}'}
        if "docker logs" in command:
            return {"ok": True, "output": logs}
        raise AssertionError(f"unexpected lab host command: {command}")

    monkeypatch.setattr(capture.lab_host, "_host_exec", fake_host_exec)
    monkeypatch.setattr(
        capture.lab_host,
        "_host_exec_lxc",
        lambda _command, **_kwargs: {"ok": True, "output": str(int(capture.time.time()))},
    )
    monkeypatch.setattr(capture, "_send_benign_traffic", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(
        capture,
        "_send_attack_probe",
        lambda *_args, **_kwargs: (
            1,
            {
                "headers": {
                    "X-Forwarded-For": capture.ATTACKER_IP,
                    "Range": "bytes=0-0,1-1",
                },
                "method": "GET",
                "path": "/",
            },
        ),
    )
    monkeypatch.setattr(capture, "_ensure_splunk_index", lambda _index: None)
    monkeypatch.setattr(capture, "_ship_events", lambda _index, events: shipped.extend(events))
    return shipped, down_calls


def test_hec_events_use_canonical_sourcetypes_and_have_no_label_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logs = (
        "2026-11-24T12:00:00.000000000Z 192.0.2.11 - - "
        '[24/Nov/2026:12:00:00 +0000] "GET / HTTP/1.1" 200 12 "-" "Mozilla/5.0"\n'
        "2026-11-24T12:00:01.000000000Z nginx[1]: worker started\n"
    )
    shipped, _down_calls = _install_mocks(monkeypatch, logs=logs)

    capture.run_capture("vulhub-nginx-lfi", "hb_lab_nginx", 7, keys_dir=tmp_path)

    assert {row["sourcetype"] for row in shipped} == {"access_combined", "syslog"}
    for row in shipped:
        assert row["sourcetype"] in {"access_combined", "syslog", "redis:log", "solr:log"}
        assert "source" not in row
        assert not any(
            word in key.lower() for key in row for word in ("attack", "label", "scenario")
        )
        assert row["index"] == "hb_lab_nginx"


def test_out_of_band_key_has_exact_ground_truth_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_mocks(monkeypatch)

    result = capture.run_capture("vulhub-nginx-lfi", "hb_lab_nginx", 7, keys_dir=tmp_path)
    key_path = tmp_path / "hb_lab_nginx_key.json"
    answer = json.loads(key_path.read_text())

    assert result["answer_key"] == answer
    assert result["status"] == "complete"
    assert result["container_names"] == ["vulhub-nginx-1"]
    assert result["port"] == 8080
    assert result["events_captured"] == result["hec_events_accepted"] == 0
    assert set(answer) == {
        "target_id",
        "attack_window",
        "attack_start_ts",
        "attack_end_ts",
        "attacker_ips",
        "attacker_indicators",
        "target_host",
        "cve",
        "mitre_techniques",
        "clock_drift_s",
        "benign_count",
        "attack_count",
    }
    assert answer["attack_window"] == {
        "start": answer["attack_start_ts"],
        "end": answer["attack_end_ts"],
    }
    assert answer["attacker_ips"] == [capture.ATTACKER_IP]
    assert answer["target_host"] == "10.10.11.50"
    assert answer["cve"] == "CVE-2017-7529"
    assert answer["mitre_techniques"] == ["T1190"]
    assert answer["benign_count"] == 7
    assert answer["attack_count"] == 1
    assert answer["attacker_indicators"] == {
        "headers": {
            "X-Forwarded-For": capture.ATTACKER_IP,
            "Range": "bytes=0-0,1-1",
        },
        "method": "GET",
        "path": "/",
    }


def test_raw_vulhub_answer_key_records_known_cve_and_t1190_out_of_band(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_mocks(monkeypatch)
    monkeypatch.setattr(capture.lab_targets, "_find_target", lambda _target_id: None)

    result = capture.run_capture("struts2/s2-045", "hb_lab_struts", 0, keys_dir=tmp_path)

    assert result["answer_key"]["cve"] == "CVE-2017-5638"
    assert result["answer_key"]["mitre_techniques"] == ["T1190"]


@pytest.mark.parametrize("failure_point", ["traffic", "shipping"])
def test_target_is_torn_down_when_capture_or_shipping_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure_point: str
) -> None:
    _shipped, down_calls = _install_mocks(monkeypatch)
    if failure_point == "traffic":
        monkeypatch.setattr(
            capture,
            "_send_attack_probe",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("traffic failed")),
        )
        message = "traffic failed"
    else:
        monkeypatch.setattr(
            capture,
            "_ship_events",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("shipping failed")),
        )
        message = "shipping failed"

    with pytest.raises(RuntimeError, match=message):
        capture.run_capture("vulhub-nginx-lfi", "hb_lab_nginx", 0, keys_dir=tmp_path)

    assert down_calls == ["vulhub-nginx-lfi"]


def test_dry_run_plans_without_touching_lab_splunk_or_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("dry-run attempted an external action")

    monkeypatch.setattr(capture.lab_targets, "cmd_up", forbidden)
    monkeypatch.setattr(capture.lab_targets, "cmd_down", forbidden)
    monkeypatch.setattr(capture.lab_host, "_host_exec", forbidden)
    monkeypatch.setattr(capture, "_ensure_splunk_index", forbidden)
    monkeypatch.setattr(capture, "_ship_events", forbidden)

    result = capture.run_capture(
        "vulhub-nginx-lfi", "hb_lab_nginx", 7, dry_run=True, keys_dir=tmp_path
    )

    assert result["status"] == "dry_run"
    assert result["benign_requests"] == 7
    assert result["sourcetypes"] == ["access_combined", "syslog"]
    assert not list(tmp_path.iterdir())


def test_clock_sync_preflight_passes_and_records_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_mocks(monkeypatch)
    commands: list[str] = []
    monkeypatch.setattr(capture.time, "time", lambda: 1000.0)

    def host_exec_lxc(command: str, **_kwargs) -> dict:
        commands.append(command)
        return {"ok": True, "output": "1009"}

    monkeypatch.setattr(capture.lab_host, "_host_exec_lxc", host_exec_lxc)

    result = capture.run_capture("vulhub-nginx-lfi", "hb_lab_clock", 0, keys_dir=tmp_path)

    assert commands == ["date -u +%s"]
    assert result["clock_drift_s"] == 9.0
    assert result["answer_key"]["clock_drift_s"] == 9.0


def test_clock_sync_preflight_rejects_drift_of_ten_seconds_before_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_mocks(monkeypatch)
    commands: list[str] = []
    up_calls: list[str] = []
    monkeypatch.setattr(capture.time, "time", lambda: 1000.0)
    monkeypatch.setattr(
        capture.lab_targets,
        "cmd_up",
        lambda target_id: up_calls.append(target_id) or {"status": "running"},
    )

    def host_exec_lxc(command: str, **_kwargs) -> dict:
        commands.append(command)
        return {"ok": True, "output": "1010"}

    monkeypatch.setattr(capture.lab_host, "_host_exec_lxc", host_exec_lxc)

    with pytest.raises(RuntimeError, match="clock drift"):
        capture.run_capture("vulhub-nginx-lfi", "hb_lab_clock", 0, keys_dir=tmp_path)

    assert commands == ["date -u +%s"]
    assert up_calls == []


def test_sync_clock_attempts_ntp_then_rechecks_before_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_mocks(monkeypatch)
    commands: list[str] = []
    outputs = iter(("1010", "1000"))
    monkeypatch.setattr(capture.time, "time", lambda: 1000.0)

    def host_exec_lxc(command: str, **_kwargs) -> dict:
        commands.append(command)
        return {"ok": True, "output": next(outputs)}

    monkeypatch.setattr(capture.lab_host, "_host_exec_lxc", host_exec_lxc)
    monkeypatch.setattr(
        capture.lab_host,
        "_proxmox_exec",
        lambda command, **_kwargs: (
            commands.append(command) or {"ok": True, "output": "NTP synchronized"}
        ),
    )

    result = capture.run_capture(
        "vulhub-nginx-lfi", "hb_lab_clock", 0, sync_clock=True, keys_dir=tmp_path
    )

    assert commands == ["date -u +%s", "chronyc -a makestep", "date -u +%s"]
    assert result["clock_drift_s"] == 0.0


@pytest.mark.parametrize(
    ("target_id", "raw_line", "expected"),
    [
        (
            "vulhub-nginx-lfi",
            '192.0.2.1 - - [24/Nov/2026:12:00:00 +0000] "GET / HTTP/1.1" 200 0 "-" "UA"',
            "access_combined",
        ),
        (
            "vulhub-tomcat-manager",
            '192.0.2.1 - - [24/Nov/2026:12:00:00 +0000] "GET / HTTP/1.1" 200 0 "-" "UA"',
            "access_combined",
        ),
        ("vulhub-log4shell-solr", "INFO Solr started", "solr:log"),
        ("vulhub-redis-rce", "Ready to accept connections", "redis:log"),
        ("custom/service/path", "service started", "syslog"),
    ],
)
def test_canonical_sourcetype_mapping(target_id: str, raw_line: str, expected: str) -> None:
    assert capture.canonical_sourcetype(target_id, raw_line) == expected


def test_http_probe_records_bounded_request_details(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[tuple[str, str, dict[str, str], str | None]] = []

    def fake_request(
        method: str, url: str, headers: dict[str, str], content: str | None = None
    ) -> int:
        requests.append((method, url, headers, content))
        return 204

    monkeypatch.setattr(capture, "_http_request", fake_request)

    nginx_count, nginx = capture._send_attack_probe("nginx", "10.10.11.50", 8080)
    solr_count, solr = capture._send_attack_probe("solr", "10.10.11.50", 8983)
    tomcat_count, tomcat = capture._send_attack_probe("tomcat", "10.10.11.50", 8081)

    assert nginx_count == solr_count == 1
    assert nginx["headers"]["Range"] == "bytes=0-0,1-1"
    assert nginx["headers"]["X-Forwarded-For"] == capture.ATTACKER_IP
    assert solr["headers"]["User-Agent"] == "${jndi:ldap://127.0.0.1:1/a}"
    assert tomcat_count == 3
    assert tomcat["method_sequence"] == ["PUT", "GET", "DELETE"]
    assert tomcat["body"] == '<%@ page contentType="text/plain" %>ok'
    assert [item[0] for item in requests] == ["GET", "GET", "PUT", "GET", "DELETE"]


def test_redis_probe_uses_only_read_only_eval(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[tuple[str, int, tuple[str, ...], str | None]] = []

    def fake_command(host: str, port: int, *parts: str, client_name: str | None = None) -> None:
        commands.append((host, port, parts, client_name))

    monkeypatch.setattr(capture, "_redis_command", fake_command)

    count, indicators = capture._send_attack_probe("redis", "10.10.11.50", 6379)

    assert count == 1
    assert commands == [
        (
            "10.10.11.50",
            6379,
            ("EVAL", "return redis.call('PING')", "0"),
            capture.ATTACKER_IP,
        )
    ]
    assert indicators["command"] == ["EVAL", "return redis.call('PING')", "0"]


def test_tomcat_probe_surfaces_failed_jsp_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    methods: list[str] = []

    def fake_request(method: str, *_args, **_kwargs) -> int:
        methods.append(method)
        return 500 if method == "DELETE" else 201

    monkeypatch.setattr(capture, "_http_request", fake_request)

    with pytest.raises(RuntimeError, match="Tomcat probe cleanup failed"):
        capture._send_attack_probe("tomcat", "10.10.11.50", 8081)

    assert methods == ["PUT", "GET", "DELETE"]


@pytest.mark.parametrize("status_code", [201, 409])
def test_index_creation_accepts_created_or_existing_index(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    calls: list[tuple[str, dict]] = []

    def request(method: str, url: str, **kwargs) -> SimpleNamespace:
        calls.append((url, kwargs))
        assert method == "POST"
        return SimpleNamespace(status_code=status_code)

    monkeypatch.setenv("LAB_SPLUNK_URL", "https://splunk.example:8089")
    monkeypatch.setattr(capture.httpx, "request", request)

    capture._ensure_splunk_index("hb_lab_nginx")

    assert calls[0][0] == "https://splunk.example:8089/services/data/indexes"
    assert calls[0][1]["data"] == {"name": "hb_lab_nginx"}


def test_hec_request_contains_only_raw_event_and_canonical_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict] = []

    def request(_method: str, _url: str, **kwargs) -> SimpleNamespace:
        requests.append(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: {"code": 0})

    monkeypatch.setenv("LAB_SPLUNK_HEC_URL", "https://splunk.example:8088")
    monkeypatch.setenv("LAB_SPLUNK_HEC_TOKEN", "test-token")
    monkeypatch.setattr(capture.httpx, "request", request)
    event = {
        "host": "10.10.11.50",
        "index": "hb_lab_nginx",
        "sourcetype": "access_combined",
        "event": '192.0.2.10 - - [24/Nov/2026:12:00:00 +0000] "GET / HTTP/1.1" 200 0',
        "time": 1795521600.0,
    }

    capture._ship_events("hb_lab_nginx", [event])

    assert requests[0]["json"] == event
    assert "source" not in requests[0]["json"]
    assert not any(
        word in key.lower()
        for key in requests[0]["json"]
        for word in ("attack", "label", "scenario")
    )
    assert requests[0]["headers"] == {"Authorization": "Splunk test-token"}


def test_log_events_strip_null_bytes_and_skip_empty_lines_before_hec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logs = (
        "2026-11-24T12:00:00.000000000Z \x00  \n"
        "2026-11-24T12:00:01.000000000Z nginx[1]: worker\x00 started\n"
        "2026-11-24T12:00:02.000000000Z   \n"
        "INFO service ready\n"
        "9999-11-24T12:00:03.000000000Z future timestamp event\n"
        "\x00 \n"
    )
    shipped, _down_calls = _install_mocks(monkeypatch, logs=logs)

    capture.run_capture("vulhub-nginx-lfi", "hb_lab_sanitize", 0, keys_dir=tmp_path)

    assert len(shipped) == 3
    assert shipped[0]["event"] == "nginx[1]: worker started"
    assert "\x00" not in shipped[0]["event"]
    assert shipped[1]["event"] == "INFO service ready"
    assert shipped[2]["event"] == "future timestamp event"
    assert "time" not in shipped[2]


def test_hec_http_error_includes_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAB_SPLUNK_HEC_URL", "https://splunk.example:8088")
    monkeypatch.setenv("LAB_SPLUNK_HEC_TOKEN", "test-token")
    monkeypatch.setattr(
        capture.httpx,
        "request",
        lambda *_args, **_kwargs: SimpleNamespace(
            status_code=400, text='{"text":"No data","code":5}'
        ),
    )
    event = {
        "host": "10.10.11.50",
        "index": "hb_lab_nginx",
        "sourcetype": "syslog",
        "event": "worker started",
    }

    with pytest.raises(RuntimeError, match="No data.*code.*5"):
        capture._ship_events("hb_lab_nginx", [event])


@pytest.mark.parametrize(
    "target_id",
    [
        "httpd/CVE-2021-41773",
        "struts2/s2-045",
        "spring/CVE-2022-22965",
        "postgres/CVE-2019-9193",
        "elasticsearch/CVE-2015-1427",
        "vulhub/arbitrary/service",
    ],
)
def test_raw_vulhub_profiles_have_canonical_label_free_dry_run_plans(target_id: str) -> None:
    plan = capture.run_capture(target_id, "hb_lab_raw", 3, dry_run=True)

    assert plan["status"] == "dry_run"
    assert plan["target_id"] == target_id
    assert plan["sourcetypes"]
    assert set(plan["sourcetypes"]) <= capture.CANONICAL_SOURCETYPES
    assert not any(
        word in key.lower() for key in plan for word in ("label", "scenario", "attacker")
    )


@pytest.mark.parametrize(
    ("target_id", "expected_method", "expected_path"),
    [
        ("httpd/CVE-2021-41773", "GET", "/cgi-bin/.%2e/.%2e/.%2e/etc/passwd"),
        ("struts2/s2-045", "POST", "/"),
        (
            "spring/CVE-2022-22965",
            "POST",
            "/",
        ),
        ("elasticsearch/CVE-2015-1427", "POST", "/_search"),
    ],
)
def test_raw_http_vulhub_profiles_send_bounded_probe_recipes(
    monkeypatch: pytest.MonkeyPatch,
    target_id: str,
    expected_method: str,
    expected_path: str,
) -> None:
    requests: list[tuple[str, str, dict[str, str], str | None]] = []

    def fake_request(
        method: str, url: str, headers: dict[str, str], content: str | None = None
    ) -> int:
        requests.append((method, url, headers, content))
        return 200

    monkeypatch.setattr(capture, "_http_request", fake_request)
    _target, _path, kind = capture._target_details(target_id)

    count, indicators = capture._send_attack_probe(kind, "10.10.11.50", 8080)

    assert count == 1
    assert requests[0][0] == expected_method
    assert requests[0][1] == f"http://10.10.11.50:8080{expected_path}"
    assert requests[0][2]["X-Forwarded-For"] == capture.ATTACKER_IP
    assert indicators["path"] == expected_path
    if target_id.startswith("elasticsearch/"):
        assert requests[0][3] == '{"script_fields":{"probe":{"script":"1+1"}}}'
    if target_id.startswith("spring/"):
        assert requests[0][3] == (
            "class.module.classLoader.resources.context.parent.pipeline.first.pattern=probe"
        )


def test_raw_postgres_profile_sends_startup_probe_without_sql_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int, str]] = []
    monkeypatch.setattr(
        capture,
        "_postgres_startup",
        lambda host, port, application_name: calls.append((host, port, application_name)),
    )
    _target, path, kind = capture._target_details("postgres/CVE-2019-9193")

    count, indicators = capture._send_attack_probe(kind, "10.10.11.50", 5432)

    assert count == 1
    assert calls == [("10.10.11.50", 5432, capture.ATTACKER_IP)]
    assert indicators["protocol"] == "PostgreSQL startup"
    assert path == "postgres/CVE-2019-9193"
