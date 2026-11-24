"""Capture bounded Vulhub traffic and ship canonical, label-free Splunk events."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shlex
import socket
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from scripts import lab_host, lab_targets
from scripts.hunt_bed.ingest_native import parse_time

KEYS_DIR = Path("/Volumes/data01/hunt_keys")
ATTACKER_IP = "198.51.100.77"
BENIGN_IPS = tuple(f"192.0.2.{number}" for number in range(10, 31))
CANONICAL_SOURCETYPES = {"access_combined", "syslog", "redis:log", "solr:log"}
_INDEX_RE = re.compile(r"^hb_lab_[A-Za-z0-9_-]{1,100}$")
_RAW_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_COMBINED_RE = re.compile(r'^\S+ \S+ \S+ \[[^]]+\] "[A-Z]+ \S+ HTTP/\d(?:\.\d)?"')
_DOCKER_TS_RE = re.compile(r"^(\S+) (.*)$")
_BENIGN_PATHS = (
    "/",
    "/favicon.ico",
    "/robots.txt",
    "/health",
    "/login",
    "/index.html",
    "/assets/app.css",
)
_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "curl/8.5.0",
)


def _target_details(target_id: str) -> tuple[dict[str, Any] | None, str, str]:
    target = lab_targets._find_target(target_id)
    if target:
        if target.get("source") != "vulhub" or not target.get("path"):
            raise ValueError(f"target is not a Vulhub environment: {target_id}")
        path = str(target["path"])
    else:
        if (
            not _RAW_PATH_RE.fullmatch(target_id)
            or target_id.startswith("/")
            or any(part in ("", ".", "..") for part in target_id.split("/"))
        ):
            raise ValueError("raw Vulhub paths must be relative path components")
        path = target_id
    return target, path, _target_kind(target_id, path)


def _target_kind(target_id: str, path: str) -> str:
    identity = f"{target_id}/{path}".lower()
    for marker, kind in (("redis", "redis"), ("solr", "solr"), ("log4j", "solr")):
        if marker in identity:
            return kind
    for marker in ("tomcat", "nginx"):
        if marker in identity:
            return marker
    return "generic"


def canonical_sourcetype(target_id: str, raw_line: str) -> str:
    """Map a raw service log line to its canonical Splunk TA sourcetype."""
    _target, path, kind = _target_details(target_id)
    if kind == "redis":
        return "redis:log"
    if kind == "solr":
        return "solr:log"
    if kind in {"nginx", "tomcat"} and _COMBINED_RE.match(raw_line):
        return "access_combined"
    return "syslog"


def _dry_run_plan(target_id: str, index: str, benign_requests: int) -> dict[str, Any]:
    target, _path, kind = _target_details(target_id)
    host = str((target or {}).get("host", lab_targets.LAB_VULHUB_HOST))
    port = (target or {}).get("port")
    sourcetypes = (
        ["access_combined", "syslog"]
        if kind in {"nginx", "tomcat"}
        else [{"redis": "redis:log", "solr": "solr:log"}.get(kind, "syslog")]
    )
    return {
        "status": "dry_run",
        "target_id": target_id,
        "target_host": host,
        "port": port,
        "index": index,
        "benign_requests": benign_requests,
        "attack_requests": 3 if kind == "tomcat" else 1,
        "sourcetypes": sourcetypes,
        "key_path": str(KEYS_DIR / f"{index}_key.json"),
    }


def _validate_request(index: str, benign_requests: int) -> None:
    if not _INDEX_RE.fullmatch(index):
        raise ValueError("index must start with hb_lab_ and contain only letters, digits, _ or -")
    if benign_requests < 0:
        raise ValueError("benign request count must be non-negative")


def _http_request(
    method: str, url: str, headers: dict[str, str], content: str | None = None
) -> int:
    response = httpx.request(
        method,
        url,
        headers=headers,
        content=content,
        timeout=8.0,
        follow_redirects=False,
        verify=False,
    )
    return int(response.status_code)


def _redis_command(host: str, port: int, *parts: str, client_name: str | None = None) -> None:
    with socket.create_connection((host, port), timeout=5.0) as connection:
        connection.settimeout(5.0)
        if client_name:
            connection.sendall(_resp("CLIENT", "SETNAME", client_name))
            if not connection.recv(1024):
                raise RuntimeError("Redis closed the client-name setup connection")
        connection.sendall(_resp(*parts))
        if not connection.recv(4096):
            raise RuntimeError("Redis returned no response to a read-only request")


def _resp(*parts: str) -> bytes:
    encoded = [part.encode("utf-8") for part in parts]
    return b"*%d\r\n" % len(encoded) + b"".join(
        b"$%d\r\n" % len(part) + part + b"\r\n" for part in encoded
    )


def _send_benign_traffic(
    kind: str, host: str, port: int, target_id: str, index: str, count: int
) -> int:
    rng = random.Random(f"{target_id}:{index}")
    for number in range(count):
        if kind == "redis":
            command = ("PING", "TIME", "DBSIZE", "INFO server")[number % 4]
            _redis_command(host, port, *command.split())
        else:
            headers = {
                "User-Agent": rng.choice(_USER_AGENTS),
                "X-Forwarded-For": rng.choice(BENIGN_IPS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            path = rng.choice(_BENIGN_PATHS)
            _http_request("GET", f"http://{host}:{port}{path}", headers)
        if number + 1 < count:
            time.sleep(rng.uniform(0.04, 0.16))
    return count


def _send_attack_probe(kind: str, host: str, port: int) -> tuple[int, dict[str, object]]:
    if kind == "redis":
        _redis_command(
            host,
            port,
            "EVAL",
            "return redis.call('PING')",
            "0",
            client_name=ATTACKER_IP,
        )
        return 1, {
            "client_name": ATTACKER_IP,
            "protocol": "RESP",
            "command": ["EVAL", "return redis.call('PING')", "0"],
        }
    headers = {"X-Forwarded-For": ATTACKER_IP}
    base_url = f"http://{host}:{port}"
    if kind == "nginx":
        headers["Range"] = "bytes=0-0,1-1"
        _http_request("GET", f"{base_url}/", headers)
        return 1, {"headers": headers, "method": "GET", "path": "/"}
    if kind == "solr":
        headers["User-Agent"] = "${jndi:ldap://127.0.0.1:1/a}"
        _http_request("GET", f"{base_url}/solr/", headers)
        return 1, {"headers": headers, "method": "GET", "path": "/solr/"}
    if kind == "tomcat":
        jsp_url = f"{base_url}/probe.jsp"
        payload = '<%@ page contentType="text/plain" %>ok'
        count = 0
        probe_failed = False
        try:
            count += 1
            _http_request("PUT", jsp_url, headers, payload)
            count += 1
            _http_request("GET", jsp_url, headers)
        except BaseException:
            probe_failed = True
            raise
        finally:
            try:
                count += 1
                status = _http_request("DELETE", jsp_url, headers)
                if status not in {200, 202, 204, 404}:
                    raise RuntimeError(f"Tomcat probe cleanup failed with HTTP {status}")
            except Exception:
                if not probe_failed:
                    raise
        return count, {
            "headers": headers,
            "method_sequence": ["PUT", "GET", "DELETE"],
            "path": "/probe.jsp",
            "body": payload,
        }
    _http_request("GET", f"{base_url}/", headers)
    return 1, {"headers": headers, "method": "GET", "path": "/"}


def _container_names(target_id: str, path: str) -> list[str]:
    compose_path = lab_targets._host_compose_path(path)
    result = lab_host._host_exec(
        f"docker compose -f {shlex.quote(compose_path)} ps --format json", timeout=20
    )
    if not result.get("ok"):
        raise RuntimeError(f"could not list containers for {target_id}: {result.get('output', '')}")
    rows = _parse_json_rows(result.get("output", ""))
    names = [str(row.get("Name") or row.get("Names") or row.get("ID") or "") for row in rows]
    names = sorted({name.strip().lstrip("/") for name in names if name.strip()})
    if not names:
        raise RuntimeError(f"no running containers found for {target_id}")
    return names


def _parse_json_rows(output: str) -> list[dict[str, Any]]:
    try:
        parsed: Any = json.loads(output)
    except json.JSONDecodeError:
        parsed = [json.loads(line) for line in output.splitlines() if line.lstrip().startswith("{")]
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    return []


def _capture_container_logs(containers: list[str], since: str) -> list[tuple[str, str]]:
    captured = []
    for container in containers:
        command = f"docker logs --timestamps --since {shlex.quote(since)} {shlex.quote(container)}"
        result = lab_host._host_exec(command, timeout=60)
        if not result.get("ok"):
            raise RuntimeError(
                f"could not capture logs for {container}: {result.get('output', '')}"
            )
        captured.append((container, str(result.get("output", ""))))
    return captured


def _log_events(
    target_id: str, target_host: str, index: str, logs: list[tuple[str, str]]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    year = datetime.now(UTC).year
    for _container, output in logs:
        for line in output.splitlines():
            if not line.strip():
                continue
            match = _DOCKER_TS_RE.match(line)
            timestamp = parse_time(match.group(1), year) if match else None
            raw = match.group(2) if match and timestamp is not None else line
            sourcetype = canonical_sourcetype(target_id, raw)
            event = {
                "host": target_host,
                "index": index,
                "sourcetype": sourcetype,
                "event": raw,
            }
            if timestamp is not None:
                event["time"] = timestamp
            events.append(event)
    return events


def _ensure_splunk_index(index: str) -> None:
    base_url = os.environ.get("LAB_SPLUNK_URL", "https://10.0.1.30:8089").rstrip("/")
    auth = (
        os.environ.get("LAB_SPLUNK_USER", "admin"),
        os.environ.get("LAB_SPLUNK_PASSWORD", ""),
    )
    response = httpx.request(
        "POST",
        f"{base_url}/services/data/indexes",
        data={"name": index},
        auth=auth,
        timeout=30.0,
        verify=False,
    )
    if response.status_code not in {201, 409}:
        raise RuntimeError(f"Splunk index creation failed with HTTP {response.status_code}")


def _ship_events(index: str, events: list[dict[str, Any]]) -> None:
    hec_base = os.environ.get("LAB_SPLUNK_HEC_URL", "").rstrip("/")
    token = os.environ.get("LAB_SPLUNK_HEC_TOKEN", "")
    if not hec_base or not token:
        raise RuntimeError("LAB_SPLUNK_HEC_URL and LAB_SPLUNK_HEC_TOKEN are required")
    for event in events:
        if event.get("index") != index or event.get("sourcetype") not in CANONICAL_SOURCETYPES:
            raise ValueError("refusing to ship an event outside the canonical capture envelope")
        if set(event) - {"host", "index", "sourcetype", "event", "time"}:
            raise ValueError("refusing to ship event metadata beyond the zero-label envelope")
        response = httpx.request(
            "POST",
            f"{hec_base}/services/collector/event",
            json=event,
            headers={"Authorization": f"Splunk {token}"},
            timeout=30.0,
            verify=False,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Splunk HEC rejected an event with HTTP {response.status_code}")
        payload = response.json()
        if payload.get("code", 0) != 0:
            raise RuntimeError(f"Splunk HEC rejected an event with code {payload.get('code')}")


def _write_answer_key(keys_dir: Path, index: str, answer: dict[str, Any]) -> Path:
    keys_dir.mkdir(parents=True, exist_ok=True)
    destination = keys_dir / f"{index}_key.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(answer, indent=2) + "\n")
    temporary.replace(destination)
    return destination


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def run_capture(
    target_id: str,
    index: str,
    benign_requests: int = 200,
    *,
    keep_up: bool = False,
    dry_run: bool = False,
    keys_dir: Path = KEYS_DIR,
) -> dict[str, Any]:
    _validate_request(index, benign_requests)
    target, path, kind = _target_details(target_id)
    if dry_run:
        return _dry_run_plan(target_id, index, benign_requests)
    up_attempted = False
    primary_error = False
    capture_start = _utc_timestamp()
    try:
        up_attempted = True
        up_result = lab_targets.cmd_up(target_id)
        if up_result.get("status") != "running":
            raise RuntimeError(f"target did not start: {up_result}")
        host = str(
            up_result.get("host") or (target or {}).get("host") or lab_targets.LAB_VULHUB_HOST
        )
        port = int(up_result.get("port") or (target or {}).get("port") or 8080)
        containers = _container_names(target_id, path)
        benign_count = _send_benign_traffic(kind, host, port, target_id, index, benign_requests)
        attack_start = _utc_timestamp()
        attack_count, attacker_indicators = _send_attack_probe(kind, host, port)
        attack_end = _utc_timestamp()
        logs = _capture_container_logs(containers, capture_start)
        events = _log_events(target_id, host, index, logs)
        _ensure_splunk_index(index)
        _ship_events(index, events)
        answer = {
            "target_id": target_id,
            "attack_window": {"start": attack_start, "end": attack_end},
            "attack_start_ts": attack_start,
            "attack_end_ts": attack_end,
            "attacker_ips": [ATTACKER_IP],
            "attacker_indicators": attacker_indicators,
            "target_host": host,
            "cve": (target or {}).get("cve"),
            "mitre_techniques": ["T1190"] if target and target.get("cve") else [],
            "benign_count": benign_count,
            "attack_count": attack_count,
        }
        key_path = _write_answer_key(keys_dir, index, answer)
        return {
            "status": "complete",
            "container_names": containers,
            "target_host": host,
            "port": port,
            "events_captured": len(events),
            "hec_events_accepted": len(events),
            "answer_key_path": str(key_path),
            "answer_key": answer,
        }
    except BaseException:
        primary_error = True
        raise
    finally:
        if up_attempted and not keep_up:
            try:
                result = lab_targets.cmd_down(target_id)
                if result.get("status") != "stopped":
                    raise RuntimeError(f"target teardown failed: {result}")
            except Exception:
                if not primary_error:
                    raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture bounded Vulhub lab traffic into Splunk")
    parser.add_argument("--target", required=True, help="catalog target ID or raw Vulhub path")
    parser.add_argument("--index", required=True, help="zero-label Splunk index (hb_lab_*)")
    parser.add_argument("--benign-requests", type=int, default=200)
    parser.add_argument("--keep-up", action="store_true", help="leave the Vulhub target running")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan without external actions"
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        result = run_capture(
            args.target,
            args.index,
            args.benign_requests,
            keep_up=args.keep_up,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
