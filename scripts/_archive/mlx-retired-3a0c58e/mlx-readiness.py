#!/usr/bin/env python3
"""MLX Proxy Readiness Watcher

Polls the MLX proxy /health endpoint and writes a readiness state file that
UAT driver and other tools can read instead of polling the proxy directly.

This decouples readiness logic from test timing: tests read a stable file
written by a dedicated background watcher rather than implementing their own
"wait and see" timer loops.

State file: /tmp/portal5-mlx-readiness.json
Format:
    {
        "state": "ready" | "switching" | "none" | "down" | "unreachable",
        "loaded_model": "mlx-community/..." | null,
        "timestamp": 1234567890.123,          # epoch seconds, last successful poll
        "consecutive_ready": 3,               # number of consecutive ready polls
        "stable": true,                       # ready for >= STABLE_POLLS consecutive polls
        "switch_start": null | float,         # epoch when state first became "switching"
        "switch_elapsed": null | float,       # seconds spent in switching state so far
    }

Usage:
    # Run in background before a UAT suite:
    python3 scripts/mlx-readiness.py &

    # Run with explicit proxy URL:
    python3 scripts/mlx-readiness.py --proxy-url http://192.168.1.10:8081

    # One-shot check (exit after first stable-ready or after --timeout seconds):
    python3 scripts/mlx-readiness.py --wait --timeout 1200

    # Verbose (prints every state change):
    python3 scripts/mlx-readiness.py --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MLX_PROXY_URL = os.environ.get("MLX_PROXY_URL", "http://localhost:8081")
READINESS_FILE = os.environ.get("MLX_READINESS_FILE", "/tmp/portal5-mlx-readiness.json")
POLL_INTERVAL_S = 10.0  # seconds between /health polls
STABLE_POLLS = 2  # consecutive ready polls before stable=True
MAX_STALE_S = 60.0  # file older than this is considered stale by readers

_running = True


def _signal_handler(sig: int, _frame: object) -> None:
    global _running
    _running = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


# ---------------------------------------------------------------------------
# State file helpers
# ---------------------------------------------------------------------------


def _write_state(
    state: str,
    loaded_model: str | None,
    consecutive_ready: int,
    switch_start: float | None,
) -> None:
    stable = consecutive_ready >= STABLE_POLLS
    switch_elapsed = (time.time() - switch_start) if switch_start else None
    payload = {
        "state": state,
        "loaded_model": loaded_model,
        "timestamp": time.time(),
        "consecutive_ready": consecutive_ready,
        "stable": stable,
        "switch_start": switch_start,
        "switch_elapsed": switch_elapsed,
    }
    tmp = READINESS_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh)
    os.replace(tmp, READINESS_FILE)


def read_state(path: str = READINESS_FILE) -> dict | None:
    """Read and return the current readiness state, or None if missing/stale."""
    try:
        with open(path) as fh:
            data = json.load(fh)
        age = time.time() - data.get("timestamp", 0)
        if age > MAX_STALE_S:
            return None
        return data
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Poll loop
# ---------------------------------------------------------------------------


def poll_once(proxy_url: str) -> tuple[str, str | None]:
    """Return (state, loaded_model). state = 'unreachable' on error."""
    try:
        resp = httpx.get(f"{proxy_url}/health", timeout=5)
        if resp.status_code in (200, 503):
            data = resp.json()
            return data.get("state", "unknown"), data.get("loaded_model")
    except Exception:
        pass
    return "unreachable", None


def run_watcher(
    proxy_url: str = MLX_PROXY_URL,
    poll_interval: float = POLL_INTERVAL_S,
    verbose: bool = False,
) -> None:
    """Main watch loop — runs until SIGTERM/SIGINT."""
    consecutive_ready = 0
    switch_start: float | None = None
    last_state: str | None = None

    print(f"[mlx-readiness] watching {proxy_url}, writing {READINESS_FILE}", flush=True)

    while _running:
        state, loaded_model = poll_once(proxy_url)

        if state == "ready":
            consecutive_ready += 1
            switch_start = None
        else:
            consecutive_ready = 0
            if state == "switching" and switch_start is None:
                switch_start = time.time()
            elif state != "switching":
                switch_start = None

        _write_state(state, loaded_model, consecutive_ready, switch_start)

        if verbose or state != last_state:
            stable = consecutive_ready >= STABLE_POLLS
            model_label = f" model={loaded_model}" if loaded_model else ""
            stable_label = " [STABLE]" if stable else f" [{consecutive_ready}/{STABLE_POLLS}]"
            switch_label = f" switching={time.time() - switch_start:.0f}s" if switch_start else ""
            print(
                f"[mlx-readiness] state={state}{model_label}{stable_label}{switch_label}",
                flush=True,
            )
            last_state = state

        time.sleep(poll_interval)

    print("[mlx-readiness] stopped", flush=True)


def wait_for_stable(
    expected_model: str | None = None,
    proxy_url: str = MLX_PROXY_URL,
    timeout_s: float = 1200.0,
    poll_interval: float = POLL_INTERVAL_S,
    verbose: bool = False,
) -> bool:
    """Block until stable-ready (optionally for a specific model), or timeout.

    Returns True if stable-ready reached within timeout, False otherwise.
    Reads the state file if it's fresh; falls back to polling the proxy directly.
    """
    t0 = time.time()
    last_state: str | None = None

    while time.time() - t0 < timeout_s:
        # Prefer reading the shared state file (written by a background watcher)
        data = read_state()
        if data is None:
            # No watcher running — poll proxy directly
            state, loaded_model = poll_once(proxy_url)
            stable = False
        else:
            state = data["state"]
            loaded_model = data.get("loaded_model")
            stable = data.get("stable", False)

        if verbose or state != last_state:
            elapsed = time.time() - t0
            model_label = f" model={loaded_model}" if loaded_model else ""
            print(
                f"[mlx-readiness] wait: state={state}{model_label} "
                f"stable={stable} elapsed={elapsed:.0f}s",
                flush=True,
            )
            last_state = state

        if state == "ready" and stable:
            if expected_model is None:
                return True
            if loaded_model and expected_model in loaded_model:
                return True

        time.sleep(poll_interval)

    elapsed = time.time() - t0
    data = read_state()
    state = (data or {}).get("state", "unknown")
    loaded_model = (data or {}).get("loaded_model", "-")
    print(
        f"[mlx-readiness] timeout after {elapsed:.0f}s — state={state}, model={loaded_model}",
        flush=True,
    )
    return False


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    global READINESS_FILE
    parser = argparse.ArgumentParser(description="MLX Proxy Readiness Watcher")
    parser.add_argument(
        "--proxy-url",
        default=MLX_PROXY_URL,
        help="MLX proxy base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--state-file",
        default=READINESS_FILE,
        help="Path to write the readiness JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=POLL_INTERVAL_S,
        help="Seconds between health polls (default: %(default)s)",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="One-shot mode: wait for stable-ready then exit 0 (exit 1 on timeout)",
    )
    parser.add_argument(
        "--expected-model",
        default=None,
        help="In --wait mode, only exit 0 when this model name substring is loaded",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1200.0,
        help="Timeout for --wait mode in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every poll result, not just state changes",
    )
    parser.add_argument(
        "--read",
        action="store_true",
        help="Print the current state file and exit",
    )
    args = parser.parse_args()

    READINESS_FILE = args.state_file

    if args.read:
        data = read_state(args.state_file)
        if data is None:
            print("(no state file or stale)")
            sys.exit(1)
        print(json.dumps(data, indent=2))
        sys.exit(0)

    if args.wait:
        ok = wait_for_stable(
            expected_model=args.expected_model,
            proxy_url=args.proxy_url,
            timeout_s=args.timeout,
            poll_interval=args.poll_interval,
            verbose=args.verbose,
        )
        sys.exit(0 if ok else 1)

    run_watcher(
        proxy_url=args.proxy_url,
        poll_interval=args.poll_interval,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
