"""Episode-scoped packet capture at the DinD attack boundary.

The attack containers are short-lived children of ``portal5-dind``. Capturing
on the privileged DinD namespace observes bytes that actually crossed the
attacker boundary, independent of whether a target service chose to log them.
The resulting PCAP is primary evidence; the text rendering is a convenience
view for blue's bounded investigation context.
"""

from __future__ import annotations

import base64
import gzip
import ipaddress
import os
import re
import struct
import subprocess
import time
from dataclasses import dataclass, field

from .capture_store import CAPTURE_DIR

_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass
class NetworkCapture:
    episode_id: str
    target_host: str
    remote_path: str = ""
    pid_path: str = ""
    started: bool = False
    error: str = ""
    local_pcap_path: str | None = None
    telemetry: dict[str, list[str]] = field(default_factory=dict)


def _docker(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _decode_http_stream(stream: bytes) -> list[str]:
    """Return plaintext from gzip-encoded HTTP response bodies in a TCP stream."""
    decoded: list[str] = []
    cursor = 0
    while True:
        start = stream.find(b"HTTP/1.", cursor)
        if start < 0:
            break
        header_end = stream.find(b"\r\n\r\n", start)
        if header_end < 0:
            break
        headers = stream[start:header_end].decode("latin-1", errors="replace")
        cursor = header_end + 4
        length_match = re.search(r"(?im)^Content-Length:\s*(\d+)\s*$", headers)
        if not length_match:
            continue
        length = int(length_match.group(1))
        body = stream[cursor : cursor + length]
        cursor += length
        if len(body) != length or not re.search(r"(?im)^Content-Encoding:\s*gzip\s*$", headers):
            continue
        try:
            text = gzip.decompress(body).decode("utf-8", errors="replace")
        except (OSError, EOFError):
            continue
        decoded.extend(text.splitlines() or [text])
    return decoded


def _decode_pcap_http_bodies(path: str) -> list[str]:
    """Reassemble TCP payloads from a classic PCAP and decode gzip HTTP.

    ``tcpdump -i any`` writes Linux cooked-v2 frames and records the same
    packet on multiple interfaces. Sequence-number deduplication makes those
    copies harmless while also joining responses split across TCP segments.
    Ethernet PCAPs are supported for local/test portability.
    """
    try:
        with open(path, "rb") as pcap_file:
            raw = pcap_file.read()
    except OSError:
        return []
    if len(raw) < 24 or raw[:4] not in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"):
        return []
    endian = "<" if raw[:4] == b"\xd4\xc3\xb2\xa1" else ">"
    linktype = struct.unpack_from(endian + "I", raw, 20)[0]
    flows: dict[tuple[bytes, bytes, int, int], dict[int, bytes]] = {}
    offset = 24
    while offset + 16 <= len(raw):
        _, _, included, _ = struct.unpack_from(endian + "IIII", raw, offset)
        offset += 16
        frame = raw[offset : offset + included]
        offset += included
        if len(frame) != included:
            break
        if linktype == 276:  # DLT_LINUX_SLL2
            if len(frame) < 20 or frame[:2] != b"\x08\x00":
                continue
            ip = frame[20:]
        elif linktype == 1:  # DLT_EN10MB
            if len(frame) < 14 or frame[12:14] != b"\x08\x00":
                continue
            ip = frame[14:]
        else:
            continue
        if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 6:
            continue
        ip_hlen = (ip[0] & 0x0F) * 4
        if len(ip) < ip_hlen + 20:
            continue
        tcp = ip[ip_hlen:]
        tcp_hlen = (tcp[12] >> 4) * 4
        if len(tcp) < tcp_hlen:
            continue
        payload = tcp[tcp_hlen:]
        if not payload:
            continue
        sport, dport, seq = struct.unpack_from("!HHI", tcp, 0)
        key = (ip[12:16], ip[16:20], sport, dport)
        flows.setdefault(key, {}).setdefault(seq, payload)
    decoded: list[str] = []
    for segments in flows.values():
        stream = b"".join(segments[seq] for seq in sorted(segments))
        decoded.extend(_decode_http_stream(stream))
    return decoded


def start_network_capture(episode_id: str, target_host: str | None) -> NetworkCapture:
    """Start a packet capture before red dispatches its first command."""
    safe_id = _SAFE_ID_RE.sub("_", episode_id)[:120]
    capture = NetworkCapture(episode_id=safe_id, target_host=target_host or "")
    if os.environ.get("LAB_NETWORK_CAPTURE", "true").lower() not in ("1", "true", "yes"):
        capture.error = "network capture disabled"
        return capture
    try:
        if target_host:
            ipaddress.ip_address(target_host)
    except ValueError:
        capture.error = f"target host is not a literal IP: {target_host}"
        return capture

    dind = os.environ.get("PORTAL_DIND_CONTAINER", "portal5-dind")
    capture.remote_path = f"/tmp/portal5-captures/{safe_id}.pcap"
    capture.pid_path = f"/tmp/portal5-captures/{safe_id}.pid"
    # Do not install a BPF host filter here. The actual attack process runs in
    # a child Docker daemon, so packets can cross the outer DinD namespace
    # after nested NAT has rewritten the endpoint. A filter on the scenario's
    # original target IP produced header-only PCAPs even while tcpdump reported
    # packets received. The episode boundary is already short and isolated;
    # capture the namespace losslessly and retain target_host as metadata.
    script = (
        "mkdir -p /tmp/portal5-captures; "
        f"nohup tcpdump -i any -U -s 0 -w {capture.remote_path} </dev/null "
        f">/tmp/portal5-captures/{safe_id}.log 2>&1 & "
        f"echo $! > {capture.pid_path}"
    )
    result = _docker("exec", dind, "sh", "-lc", script)
    if result.returncode != 0:
        capture.error = (result.stderr or result.stdout or "tcpdump start failed").strip()
        return capture
    # tcpdump creates the output file before its AF_PACKET socket is fully
    # attached. Live nested-container tests showed attacks launched after the
    # old 200 ms delay could finish before capture began (0 captured / dozens
    # received). Two seconds is the measured safe startup floor on DinD.
    time.sleep(2.0)
    ready = _docker(
        "exec",
        dind,
        "sh",
        "-lc",
        f"test -s {capture.pid_path} && kill -0 $(cat {capture.pid_path}) 2>/dev/null && test -f {capture.remote_path}",
    )
    if ready.returncode != 0:
        capture.error = "tcpdump exited before capture became ready"
        return capture
    capture.started = True
    return capture


def stop_network_capture(capture: NetworkCapture) -> NetworkCapture:
    """Stop capture, persist the PCAP, and render observed packet text."""
    if not capture.started:
        return capture
    dind = os.environ.get("PORTAL_DIND_CONTAINER", "portal5-dind")
    # Allow libpcap's one-second read timeout to deliver the last packet batch
    # from the nested bridge before asking tcpdump to close its file.
    time.sleep(1.25)
    stop_script = (
        f"if test -s {capture.pid_path}; then "
        # A process launched as a non-interactive shell background job inherits
        # SIGINT as ignored. SIGTERM is the portable tcpdump shutdown signal;
        # it closes and flushes the PCAP before exiting.
        f"pid=$(cat {capture.pid_path}); kill -TERM $pid 2>/dev/null || true; "
        "for i in $(seq 1 50); do kill -0 $pid 2>/dev/null || break; sleep 0.1; done; "
        "kill -KILL $pid 2>/dev/null || true; fi"
    )
    _docker("exec", dind, "sh", "-lc", stop_script, timeout=10)

    pcap_dir = CAPTURE_DIR / "pcap"
    pcap_dir.mkdir(parents=True, exist_ok=True)
    local_path = pcap_dir / f"{capture.episode_id}.pcap"
    copied = _docker("cp", f"{dind}:{capture.remote_path}", str(local_path), timeout=60)
    if copied.returncode != 0:
        # Docker Desktop can execute/read a file in DinD yet make `docker cp`
        # report it missing (observed live on its LinuxKit overlay). Exporting
        # the exact bytes through exec is slower but preserves the primary PCAP.
        encoded = _docker("exec", dind, "base64", capture.remote_path, timeout=60)
        if encoded.returncode == 0 and encoded.stdout.strip():
            try:
                local_path.write_bytes(base64.b64decode(encoded.stdout))
                copied = subprocess.CompletedProcess(
                    copied.args,
                    0,
                    copied.stdout,
                    copied.stderr,
                )
            except (OSError, ValueError):
                pass
    if copied.returncode == 0 and local_path.exists() and local_path.stat().st_size > 24:
        capture.local_pcap_path = str(local_path)
        decoded_http = _decode_pcap_http_bodies(str(local_path))
        if decoded_http:
            capture.telemetry["network:http-decoded"] = decoded_http
    else:
        capture.error = (copied.stderr or "empty packet capture").strip()

    rendered = _docker(
        "exec",
        dind,
        "tcpdump",
        "-nn",
        "-tttt",
        "-A",
        "-r",
        capture.remote_path,
        timeout=60,
    )
    if rendered.returncode in (0, 1) and rendered.stdout.strip():
        # Preserve observed bytes without manufacturing protocol outcomes.
        lines = rendered.stdout.splitlines()
        # Keep both ends of the episode. A verbose first fingerprint response
        # (JimuReport's landing page is thousands of lines) previously crowded
        # the later exploit request and reflected command proof out of the
        # fixed 2,000-line evidence budget.
        capture.telemetry["network:packet"] = (
            lines if len(lines) <= 2000 else [*lines[:1000], *lines[-1000:]]
        )
    elif not capture.error:
        capture.error = (rendered.stderr or "packet rendering produced no output").strip()
    capture.started = False
    return capture
