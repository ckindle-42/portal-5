"""Run one campaign arm under the memory watchdog's PID file and keep its exit status."""

from __future__ import annotations

import argparse
import datetime as dt
import signal
import subprocess
import sys
from pathlib import Path

DEFAULT_PID_FILE = Path("/tmp/portal5-memory-safety-test-pids")


def supervise(cmd: list[str], pid_file: Path, exit_log: Path, label: str) -> int:
    """Start cmd, register its PID for the watchdog, forward signals, log and return its exit."""
    child = subprocess.Popen(cmd)
    with pid_file.open("a") as fh:
        fh.write(f"{child.pid}\n")
    old = {
        s: signal.signal(s, lambda sig, _f: child.send_signal(sig))
        for s in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        rc = child.wait()
    finally:
        for s, h in old.items():
            signal.signal(s, h)
    code = rc if rc >= 0 else 128 - rc
    exit_log.parent.mkdir(parents=True, exist_ok=True)
    with exit_log.open("a") as fh:
        fh.write(f"{dt.datetime.now(dt.UTC).isoformat()} arm={label} pid={child.pid} exit={code}\n")
    return code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pid-file", type=Path, default=DEFAULT_PID_FILE)
    ap.add_argument("--exit-log", type=Path, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("campaign_args", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    rest = a.campaign_args[1:] if a.campaign_args[:1] == ["--"] else a.campaign_args
    return supervise(
        [sys.executable, "-m", "tests.wfe.campaign", *rest], a.pid_file, a.exit_log, a.label
    )


if __name__ == "__main__":
    raise SystemExit(main())
