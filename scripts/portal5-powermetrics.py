#!/opt/homebrew/bin/python3
"""Portal 5 powermetrics reader daemon.

Runs `powermetrics` continuously, parses the output, exposes current power
consumption (in watts) plus 1-min/10-min averages on a Unix domain socket.

Install:
    sudo cp scripts/portal5-powermetrics.py /usr/local/bin/portal5-powermetrics
    sudo chmod +x /usr/local/bin/portal5-powermetrics
    sudo cp deploy/launchd/com.portal5.powermetrics.plist /Library/LaunchDaemons/
    sudo launchctl load -w /Library/LaunchDaemons/com.portal5.powermetrics.plist
"""

import collections
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time

SOCKET_PATH = "/tmp/portal5-powermetrics.sock"
SAMPLE_INTERVAL_MS = 10000
MAX_BUFFER_LINES = 20000


class PowerSampler:
    def __init__(self):
        self.current_w = 0.0
        self.cpu_w = 0.0
        self.gpu_w = 0.0
        self.ane_w = 0.0
        self.dram_w = 0.0
        self.lock = threading.Lock()
        self.history_1min = collections.deque(maxlen=6)
        self.history_10min = collections.deque(maxlen=60)

    def update(self, sample: dict):
        with self.lock:
            self.cpu_w = sample.get("cpu_w", 0.0)
            self.gpu_w = sample.get("gpu_w", 0.0)
            self.ane_w = sample.get("ane_w", 0.0)
            self.dram_w = sample.get("dram_w", 0.0)
            total = self.cpu_w + self.gpu_w + self.ane_w + self.dram_w
            self.current_w = total
            self.history_1min.append(total)
            self.history_10min.append(total)

    def get_state(self) -> dict:
        with self.lock:
            return {
                "current_w": round(self.current_w, 2),
                "cpu_w": round(self.cpu_w, 2),
                "gpu_w": round(self.gpu_w, 2),
                "ane_w": round(self.ane_w, 2),
                "dram_w": round(self.dram_w, 2),
                "avg_1min_w": round(sum(self.history_1min) / max(len(self.history_1min), 1), 2),
                "avg_10min_w": round(sum(self.history_10min) / max(len(self.history_10min), 1), 2),
                "samples_1min": len(self.history_1min),
                "samples_10min": len(self.history_10min),
                "ts": time.time(),
            }


def run_powermetrics(sampler: PowerSampler):
    while True:
        try:
            cmd = [
                "powermetrics",
                "--samplers",
                "cpu_power,gpu_power,ane_power",
                "-i",
                str(SAMPLE_INTERVAL_MS),
                "-f",
                "plist",
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            for doc in iter_plist_documents(iter(proc.stdout.readline, b"")):
                sample = parse_plist_buffer(doc)
                if sample:
                    sampler.update(sample)
            print("[powermetrics] subprocess exited; retrying in 5s", file=sys.stderr)
            time.sleep(5)
        except FileNotFoundError:
            print("[powermetrics] command not found — Apple Silicon required", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"[powermetrics] error: {e}", file=sys.stderr)
            time.sleep(5)


def iter_plist_documents(lines):
    """Yield one plist document per powermetrics sample.

    Samples are split on the closing ``</plist>`` tag. The previous split on a
    line *starting* with ``<?xml`` never matched, because powermetrics puts a NUL
    byte between samples, so every line was buffered forever and no sample was
    parsed. The buffer is capped so a format change can never grow it without bound.
    """
    buf: list[str] = []
    for line in lines:
        line_str = line.decode(errors="replace").replace("\x00", "").strip()
        if not line_str:
            continue
        buf.append(line_str)
        if "</plist>" in line_str:
            yield "\n".join(buf)
            buf = []
        elif len(buf) > MAX_BUFFER_LINES:
            print("[powermetrics] no sample boundary found; dropping buffer", file=sys.stderr)
            buf = []


def parse_plist_buffer(text: str) -> dict | None:
    try:
        sample = {}
        # `powermetrics -f plist` reports milliwatts as <real> (e.g. cpu_power
        # 6553.71). combined_power is the CPU+GPU+ANE total, so it is not read.
        for key, attr in [
            ("cpu_power", "cpu_w"),
            ("gpu_power", "gpu_w"),
            ("ane_power", "ane_w"),
            ("dram_power", "dram_w"),
        ]:
            m = re.search(
                rf"<key>{re.escape(key)}</key>\s*<(?:real|integer)>([\d.]+)</(?:real|integer)>",
                text,
            )
            if m:
                sample[attr] = float(m.group(1)) / 1000.0
        if not sample:
            return None
        return sample
    except Exception:
        return None


def serve_socket(sampler: PowerSampler):
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o666)
    sock.listen(8)
    print(f"[powermetrics] socket listening at {SOCKET_PATH}", file=sys.stderr)
    while True:
        try:
            conn, _ = sock.accept()
            try:
                state = sampler.get_state()
                conn.sendall((json.dumps(state) + "\n").encode())
            finally:
                conn.close()
        except Exception as e:
            print(f"[socket] error: {e}", file=sys.stderr)


def main():
    sampler = PowerSampler()
    t = threading.Thread(target=run_powermetrics, args=(sampler,), daemon=True)
    t.start()
    time.sleep(12)
    serve_socket(sampler)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    main()
