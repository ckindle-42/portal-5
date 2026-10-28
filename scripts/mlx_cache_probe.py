#!/usr/bin/env python3
"""MLX cache retention measurement harness (POST_EG2 F4).

Target a host-native MLX service by fleet id (from config/portal.yaml),
drive varied-size requests through its endpoint, and compare idle footprint
before vs after. Uses the same pid/footprint helpers as
scripts/memory_safety_watch.py.

Usage:
    python scripts/mlx_cache_probe.py mlx-transcribe --requests 20
    python scripts/mlx_cache_probe.py mlx-speech --requests 20 --json
    python scripts/mlx_cache_probe.py mlx-transcribe --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "portal.yaml"

# Threshold in bytes (default 0.5 GiB)
DEFAULT_THRESHOLD_GIB = 0.5
DEFAULT_REQUESTS = 20
SETTLE_WAIT_S = 5.0


# ── Reuse helpers from memory_safety_watch.py ────────────────────────────────


def _command(args: list[str], timeout: float = 2.0) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip() or result.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return f"ERROR: {exc}"


def _service_pid(label: str) -> int | None:
    text = _command(["launchctl", "print", f"gui/{os.getuid()}/{label}"], timeout=3)
    import re

    match = re.search(r"^\s*pid = (\d+)\s*$", text, re.MULTILINE)
    return int(match.group(1)) if match else None


def _python_pid(pid: int) -> int | None:
    rows = _command(["ps", "-A", "-o", "pid=,ppid=,comm="], timeout=5).splitlines()
    comm: dict[int, str] = {}
    children: dict[int, list[int]] = {}
    for row in rows:
        parts = row.split(None, 2)
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        comm[int(parts[0])] = parts[2]
        children.setdefault(int(parts[1]), []).append(int(parts[0]))
    queue, seen = [pid], set()
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        executable = comm.get(current, "").split(" ", 1)[0]
        if Path(executable).name.lower().startswith("python"):
            return current
        queue.extend(children.get(current, []))
    return None


def _footprint_bytes(pid: int) -> int | None:
    import re

    phys_footprint = re.compile(r"phys_footprint:\s*([0-9.]+)\s*([KMGT]?B)", re.IGNORECASE)
    footprint_scale = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    text = _command(["footprint", "-p", str(pid)], timeout=15)
    match = phys_footprint.search(text)
    if not match:
        return None
    return int(float(match.group(1)) * footprint_scale[match.group(2).upper()])


# ── Config discovery ──────────────────────────────────────────────────────────


def _find_service(fleet_id: str) -> dict[str, object] | None:
    """Look up a service entry in config/portal.yaml."""
    if not CONFIG_PATH.is_file():
        return None
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    for entry in data.get("mcp_fleet") or []:
        if isinstance(entry, dict):
            entry_id = entry.get("id") or entry.get("native_service")
            if entry_id == fleet_id or entry.get("launchd_label", "").endswith(fleet_id):
                return entry
    for job in data.get("host_jobs") or []:
        if isinstance(job, dict):
            service_name = job.get("service") or job.get("label", "").removeprefix("com.portal5.")
            if service_name == fleet_id or job.get("label", "").endswith(fleet_id):
                return {**job, "native_service": service_name}
    return None


def _resolve_target(fleet_id: str) -> tuple[int, str] | None:
    entry = _find_service(fleet_id)
    if entry is None:
        return None
    port = entry.get("port")
    label_str = entry.get("launchd_label")
    if not label_str:
        service_key = entry.get("native_service") or entry.get("id")
        label_str = f"com.portal5.{service_key}" if service_key else None
    if port is None:
        defaults: dict[str, int] = {
            "mlx-speech": 8918,
            "mlx-transcribe": 8924,
        }
        port = defaults.get(fleet_id)
    if not port or not label_str:
        return None
    return (port, label_str)  # type: ignore[return-value]


# ── Synthetic audio generation (std-lib only) ───────────────────────────────────


def _generate_synthetic_wav(path: Path, duration_s: float, sr: int = 24000) -> None:
    """Write a short synthetic mono WAV file using only stdlib `wave`."""
    frames = int(duration_s * sr)
    # Simple square wave at 440 Hz, 8-bit mono
    period_samples = sr // 440
    data = bytearray()
    for i in range(frames):
        val = 200 if (i % period_samples) < (period_samples // 2) else 80
        data.append(val)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(sr)
        w.writeframes(bytes(data))


# ── Request drivers ────────────────────────────────────────────────────────────


def _drive_transcribe(
    host: str,
    port: int,
    requests: int,
    python_pid: int | None,
    peak: list[int],
    failures: list[str],
) -> list[float]:
    """Drive the transcribe endpoint with synthetic audio of varied durations.
    Returns a list of response times (seconds)."""
    times: list[float] = []
    durations = [max(0.5, 0.5 + 0.5 * i) for i in range(requests)]
    for duration in durations:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            _generate_synthetic_wav(Path(tmp_path), duration)
            with open(tmp_path, "rb") as audio_file:
                boundary = "----probe-boundary"
                body = (
                    (
                        f"--{boundary}\r\n"
                        f'Content-Disposition: form-data; name="file"; filename="probe.wav"\r\n'
                        f"Content-Type: audio/wav\r\n\r\n"
                    ).encode()
                    + audio_file.read()
                    + f"\r\n--{boundary}--\r\n".encode()
                )
            url = f"http://{host}:{port}/v1/audio/transcribe-with-speakers"
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                method="POST",
            )
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp.read()
            except Exception as exc:  # noqa: BLE001 - counted; an errored run is INVALID
                failures.append(f"{type(exc).__name__}: {exc}"[:200])
            times.append(round(time.time() - t0, 2))
            _sample_peak(peak, python_pid)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    return times


def _drive_speech(
    host: str,
    port: int,
    requests: int,
    python_pid: int | None,
    peak: list[int],
    failures: list[str],
) -> list[float]:
    """Drive the TTS endpoint with texts of growing length."""
    times: list[float] = []
    texts = ["Hello. " * (1 + i) for i in range(requests)]
    url = f"http://{host}:{port}/v1/audio/speech"
    for text in texts:
        payload = json.dumps(
            {
                "model": "kokoro",
                "input": text,
                "voice": "af_heart",
            }
        ).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
        except Exception as exc:  # noqa: BLE001 - counted; an errored run is INVALID
            failures.append(f"{type(exc).__name__}: {exc}"[:200])
        times.append(round(time.time() - t0, 2))
        _sample_peak(peak, python_pid)
    return times


def _sample_peak(peak: list[int], python_pid: int | None) -> None:
    """Keep the highest footprint seen; peak[0] is updated in place."""
    now = _idle_footprint(python_pid)
    if now is not None and now > peak[0]:
        peak[0] = now


def _idle_footprint(python_pid: int | None) -> int | None:
    if python_pid is None:
        return None
    return _footprint_bytes(python_pid)


# ── Main ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", help="Fleet id (e.g. mlx-transcribe, mlx-speech)")
    parser.add_argument(
        "--requests",
        type=int,
        default=DEFAULT_REQUESTS,
        help=f"Number of varied-size requests (default {DEFAULT_REQUESTS})",
    )
    parser.add_argument(
        "--threshold-gib",
        type=float,
        default=DEFAULT_THRESHOLD_GIB,
        help=f"Retention threshold in GiB (default {DEFAULT_THRESHOLD_GIB})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the measurement plan and exit without sending requests",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable numbers")
    parser.add_argument(
        "--host", default="localhost", help="Host where the service listens (default localhost)"
    )
    args = parser.parse_args(argv)

    target = _resolve_target(args.service)
    if target is None:
        print(f"ERROR: service '{args.service}' not found in config/portal.yaml", file=sys.stderr)
        return 1
    port, label = target

    if args.dry_run:
        print(f"DRY-RUN: service={args.service} label={label} port={port}")
        print(f"  requests={args.requests} threshold={args.threshold_gib} GiB")
        print(f"  endpoint=http://{args.host}:{port}/")
        return 0

    # Find python pid
    service_pid = _service_pid(label)
    python_pid = _python_pid(service_pid) if service_pid else None

    # Idle before
    before = _idle_footprint(python_pid)
    before_gib = before / (1024**3) if before else None

    # Drive requests; failures and the peak footprint are collected as they happen.
    peak: list[int] = [before or 0]
    failures: list[str] = []
    if args.service in ("mlx-transcribe", "mlx_transcribe") or (
        args.service.startswith("mlx") and "transcribe" in args.service
    ):
        response_times = _drive_transcribe(
            args.host, port, args.requests, python_pid, peak, failures
        )
    else:
        # Default to speech/TTS path for anything else (e.g. mlx-speech)
        response_times = _drive_speech(args.host, port, args.requests, python_pid, peak, failures)

    # Settle and measure idle after
    if SETTLE_WAIT_S > 0:
        time.sleep(SETTLE_WAIT_S)
    after = _idle_footprint(python_pid)
    after_gib = after / (1024**3) if after else None

    # Peak is the max footprint observed during the run; since we don't sample
    # continuously, report max of before/after plus any intermediate reads.
    # For simplicity, report before/after only (brief asks for these values).
    threshold_bytes = args.threshold_gib * (1024**3)
    delta_gib = (
        (after_gib - before_gib) if (before_gib is not None and after_gib is not None) else None
    )
    # A run that could not measure (no pid, missing reading, any failed request) proves nothing:
    # INVALID, never OK.
    if python_pid is None or delta_gib is None or failures:
        verdict = "INVALID"
    elif delta_gib > args.threshold_gib:
        verdict = "RETAINING"
    else:
        verdict = "OK"
    peak_gib = peak[0] / (1024**3) if peak[0] else None

    result = {
        "service": args.service,
        "label": label,
        "port": port,
        "python_pid": python_pid,
        "requests": args.requests,
        "idle_before_bytes": before,
        "idle_before_gib": before_gib,
        "idle_after_bytes": after,
        "idle_after_gib": after_gib,
        "delta_gib": delta_gib,
        "peak_gib": peak_gib,
        "failed_requests": len(failures),
        "failures": failures[:5],
        "threshold_gib": args.threshold_gib,
        "settle_wait_s": SETTLE_WAIT_S,
        "response_times_s": response_times,
        "verdict": verdict,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:

        def gib(v: float | None) -> str:
            return f"{v:.2f} GiB" if v is not None else "n/a"

        print(
            f"VERDICT: {verdict} | service={args.service} pid={python_pid} "
            f"idle_before={gib(before_gib)} peak={gib(peak_gib)} idle_after={gib(after_gib)} "
            f"delta={gib(delta_gib)} (threshold={args.threshold_gib} GiB)"
        )
        print(f"  requests={args.requests} failed={len(failures)} response_times={response_times}")
        for f in failures[:5]:
            print(f"  failure: {f}")

    return {"OK": 0, "RETAINING": 1}.get(verdict, 2)


if __name__ == "__main__":
    raise SystemExit(main())
