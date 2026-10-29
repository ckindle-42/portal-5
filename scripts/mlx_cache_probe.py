#!/usr/bin/env python3
"""MLX cache retention measurement harness (POST_EG2 F4).

Warm the service, then judge footprint growth on the measured series only.
A cold model load before the warm baseline is not retention.

Usage:
    python scripts/mlx_cache_probe.py mlx-transcribe --requests 20
    python scripts/mlx_cache_probe.py mlx-speech --requests 20 --json
    python scripts/mlx_cache_probe.py mlx-transcribe --dry-run
    python scripts/mlx_cache_probe.py mlx-transcribe --requests 10 --input-seconds 30
    python scripts/mlx_cache_probe.py mlx-speech --requests 10 --chars 2000
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
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "portal.yaml"

N_WARM = 2
GROWTH_REL_TOL = 0.03
GROWTH_ABS_TOL_BYTES = 150 * 1024 * 1024
DEFAULT_REQUESTS = 20
SETTLE_WAIT_S = 5.0
GIB = 1024**3


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


def _is_transcribe(service: str) -> bool:
    if service in ("mlx-transcribe", "mlx_transcribe"):
        return True
    return service.startswith("mlx") and "transcribe" in service


# ── Synthetic audio generation (std-lib only) ─────────────────────────────────


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


def _transcribe_durations(count: int, input_seconds: float | None) -> list[float]:
    """Measured clip lengths. None keeps the short varied default."""
    if input_seconds is not None:
        return [float(input_seconds)] * count
    return [max(0.5, 0.5 + 0.5 * i) for i in range(count)]


def _warm_transcribe_durations(count: int) -> list[float]:
    """Short clips so warm-up loads the model without sizing the cache."""
    return [0.5] * count


def _speech_text(chars: int) -> str:
    unit = "Hello. "
    reps = max(1, (chars + len(unit) - 1) // len(unit))
    return (unit * reps)[:chars]


def _speech_texts(count: int, chars: int | None) -> list[str]:
    """Measured texts. None keeps the short growing default."""
    if chars is not None:
        return [_speech_text(chars)] * count
    return ["Hello. " * (1 + i) for i in range(count)]


def _warm_speech_texts(count: int) -> list[str]:
    """Short lines so warm-up loads the model without sizing the cache."""
    return ["Hello. "] * count


# ── Request drivers ────────────────────────────────────────────────────────────


def _post(url: str, data: bytes, content_type: str) -> None:
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": content_type},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def _transcribe_body(wav_bytes: bytes) -> tuple[bytes, str]:
    boundary = "----probe-boundary"
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="probe.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n"
        ).encode()
        + wav_bytes
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


def _send_transcribe(host: str, port: int, duration: float) -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        _generate_synthetic_wav(Path(tmp_path), duration)
        body, content_type = _transcribe_body(Path(tmp_path).read_bytes())
        _post(f"http://{host}:{port}/v1/audio/transcribe-with-speakers", body, content_type)
    finally:
        with suppress(OSError):
            os.unlink(tmp_path)


def _send_speech(host: str, port: int, text: str) -> None:
    payload = json.dumps({"model": "kokoro", "input": text, "voice": "af_heart"}).encode()
    _post(f"http://{host}:{port}/v1/audio/speech", payload, "application/json")


def _run_series(
    send: Callable[..., None],
    items: list[object],
    failures: list[str],
    python_pid: int | None,
    *,
    sample: bool,
) -> tuple[list[float], list[int | None]]:
    """Send items. sample=False is the untimed warm-up and records no footprints."""
    times: list[float] = []
    samples: list[int | None] = []
    for item in items:
        started = time.perf_counter()
        try:
            send(item)
        except Exception as exc:  # noqa: BLE001 - counted; an errored run is INVALID
            failures.append(f"{type(exc).__name__}: {exc}"[:200])
        if sample:
            times.append(round(time.perf_counter() - started, 2))
            samples.append(_idle_footprint(python_pid))
    return times, samples


def _idle_footprint(python_pid: int | None) -> int | None:
    if python_pid is None:
        return None
    return _footprint_bytes(python_pid)


# ── Verdict ───────────────────────────────────────────────────────────────────


def _projected_growth(points: list[int]) -> int:
    """Bytes implied by a least-squares slope from the first point to the last."""
    count = len(points)
    if count < 2:
        return 0
    mean_x = (count - 1) / 2
    mean_y = sum(points) / count
    numer = 0.0
    denom = 0.0
    for index, value in enumerate(points):
        dx = index - mean_x
        numer += dx * (value - mean_y)
        denom += dx * dx
    if denom == 0:
        return 0
    return int(round((numer / denom) * (count - 1)))


def _within_tolerance(observed: int, warm_baseline: int) -> bool:
    """True when growth is under 150 MiB or under 3% of the warm baseline."""
    if observed < GROWTH_ABS_TOL_BYTES:
        return True
    if warm_baseline <= 0:
        return False
    return (observed / warm_baseline) < GROWTH_REL_TOL


def judge_retention(
    warm_baseline: int | None,
    samples: list[int | None],
    *,
    measurable: bool,
) -> tuple[str, int | None, int | None, int | None]:
    """Return verdict, signed end growth, observed growth, and slope growth."""
    if not measurable or warm_baseline is None or not samples:
        return "INVALID", None, None, None
    if any(sample is None for sample in samples):
        return "INVALID", None, None, None
    clean = [int(sample) for sample in samples]
    end_growth = clean[-1] - warm_baseline
    slope_growth = _projected_growth([warm_baseline, *clean])
    observed = max(end_growth, slope_growth, 0)
    verdict = "FLAT" if _within_tolerance(observed, warm_baseline) else "RETAINING"
    return verdict, end_growth, observed, slope_growth


def _gib(value: int | None) -> float | None:
    if value is None:
        return None
    return value / GIB


def _fraction(growth: int | None, baseline: int | None) -> float | None:
    if growth is None or not baseline or baseline <= 0:
        return None
    return growth / baseline


# ── Main ──────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", help="Fleet id (e.g. mlx-transcribe, mlx-speech)")
    parser.add_argument(
        "--requests",
        type=int,
        default=DEFAULT_REQUESTS,
        help=f"Measured requests after warm-up (default {DEFAULT_REQUESTS})",
    )
    parser.add_argument(
        "--warm",
        type=int,
        default=N_WARM,
        help=f"Untimed warm-up requests before the baseline (default {N_WARM})",
    )
    parser.add_argument(
        "--input-seconds",
        type=float,
        default=None,
        help="Transcribe: fixed WAV seconds for each measured request (default: short varied clips)",
    )
    parser.add_argument(
        "--chars",
        type=int,
        default=None,
        help="Speech: fixed character count for each measured request (default: short growing texts)",
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
    return parser


def _validate_args(args: argparse.Namespace) -> str | None:
    if args.requests < 1:
        return "ERROR: --requests must be >= 1"
    if args.warm < 1:
        return "ERROR: --warm must be >= 1"
    if args.input_seconds is not None and args.input_seconds <= 0:
        return "ERROR: --input-seconds must be > 0"
    if args.chars is not None and args.chars < 1:
        return "ERROR: --chars must be >= 1"
    transcribe = _is_transcribe(args.service)
    if args.input_seconds is not None and not transcribe:
        return "ERROR: --input-seconds applies to mlx-transcribe"
    if args.chars is not None and transcribe:
        return "ERROR: --chars applies to mlx-speech"
    return None


def _dry_run_report(args: argparse.Namespace, port: int, label: str) -> int:
    abs_mib = GROWTH_ABS_TOL_BYTES // (1024 * 1024)
    print(
        f"DRY-RUN: service={args.service} label={label} port={port} "
        f"measured_requests={args.requests} warm={args.warm}"
    )
    print(
        f"  input_seconds={args.input_seconds} chars={args.chars} "
        f"tolerance=<{GROWTH_REL_TOL:.0%} or <{abs_mib} MiB"
    )
    print(f"  endpoint=http://{args.host}:{port}/")
    return 0


def _plan(
    args: argparse.Namespace, port: int
) -> tuple[Callable[..., None], list[object], list[object]]:
    host = args.host
    if _is_transcribe(args.service):

        def send_audio(duration: float) -> None:
            _send_transcribe(host, port, duration)

        return (
            send_audio,
            _warm_transcribe_durations(args.warm),
            _transcribe_durations(args.requests, args.input_seconds),
        )

    def send_text(text: str) -> None:
        _send_speech(host, port, text)

    return send_text, _warm_speech_texts(args.warm), _speech_texts(args.requests, args.chars)


def _measure(args: argparse.Namespace, port: int, label: str) -> dict[str, object]:
    service_pid = _service_pid(label)
    python_pid = _python_pid(service_pid) if service_pid else None
    baseline = _idle_footprint(python_pid)
    failures: list[str] = []
    send, warm_items, measured_items = _plan(args, port)
    _run_series(send, warm_items, failures, python_pid, sample=False)
    if SETTLE_WAIT_S > 0:
        time.sleep(SETTLE_WAIT_S)
    warm_baseline = _idle_footprint(python_pid)
    times, samples = _run_series(send, measured_items, failures, python_pid, sample=True)
    verdict, growth, observed, slope = judge_retention(
        warm_baseline,
        samples,
        measurable=python_pid is not None and not failures,
    )
    return {
        "service": args.service,
        "label": label,
        "port": port,
        "python_pid": python_pid,
        "requests": args.requests,
        "warm_requests": args.warm,
        "baseline_bytes": baseline,
        "baseline_gib": _gib(baseline),
        "warm_baseline_bytes": warm_baseline,
        "warm_baseline_gib": _gib(warm_baseline),
        "per_request_bytes": samples,
        "per_request_gib": [_gib(sample) for sample in samples],
        "growth_bytes": growth,
        "growth_gib": _gib(growth),
        "growth_fraction": _fraction(growth, warm_baseline),
        "observed_growth_bytes": observed,
        "slope_growth_bytes": slope,
        "rel_tol": GROWTH_REL_TOL,
        "abs_tol_bytes": GROWTH_ABS_TOL_BYTES,
        "input_seconds": args.input_seconds,
        "chars": args.chars,
        "failed_requests": len(failures),
        "failures": failures[:5],
        "settle_wait_s": SETTLE_WAIT_S,
        "response_times_s": times,
        "verdict": verdict,
    }


def _fmt_gib(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f} GiB"


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _emit_text(result: dict[str, object]) -> None:
    abs_mib = GROWTH_ABS_TOL_BYTES // (1024 * 1024)
    print(
        f"VERDICT: {result['verdict']} | service={result['service']} pid={result['python_pid']} "
        f"baseline={_fmt_gib(_as_float(result['baseline_gib']))} "
        f"warm_baseline={_fmt_gib(_as_float(result['warm_baseline_gib']))} "
        f"growth={_fmt_gib(_as_float(result['growth_gib']))} "
        f"(tol <{GROWTH_REL_TOL:.0%} or <{abs_mib} MiB)"
    )
    per_request = result["per_request_gib"]
    values = per_request if isinstance(per_request, list) else []
    rendered = ", ".join(_fmt_gib(_as_float(value)) for value in values)
    print(f"  per_request=[{rendered}]")
    print(
        f"  requests={result['requests']} warm={result['warm_requests']} "
        f"failed={result['failed_requests']} response_times={result['response_times_s']}"
    )
    failures = result["failures"]
    if isinstance(failures, list):
        for item in failures:
            print(f"  failure: {item}")


def _emit(result: dict[str, object], as_json: bool) -> int:
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        _emit_text(result)
    verdict = str(result["verdict"])
    return {"FLAT": 0, "RETAINING": 1}.get(verdict, 2)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    error = _validate_args(args)
    if error:
        print(error, file=sys.stderr)
        return 1
    target = _resolve_target(args.service)
    if target is None:
        print(f"ERROR: service '{args.service}' not found in config/portal.yaml", file=sys.stderr)
        return 1
    port, label = target
    if args.dry_run:
        return _dry_run_report(args, port, label)
    return _emit(_measure(args, port, label), args.json)


if __name__ == "__main__":
    raise SystemExit(main())
