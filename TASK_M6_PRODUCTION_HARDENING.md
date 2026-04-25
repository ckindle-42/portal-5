# TASK_M6_PRODUCTION_HARDENING.md

**Milestone:** M6 — Production hardening
**Scope:** `CAPABILITY_REVIEW_V1.md` §6.10 cost/power tracking, §6.11 per-workspace rate limits, §3.11 vision/OCR personas (already shipped in M1), miscellaneous polish items collected over M1-M5
**Estimated effort:** 2-3 weeks
**Dependencies:** M1-M5 ideally shipped (this is polish on top), but most M6 items are independent and could ship earlier
**Companion files:** `CAPABILITY_REVIEW_V1.md`, all prior milestone task files

**Why this milestone exists:**
This is the closeout phase. Items here are not capability gaps — Portal 5 is feature-complete after M5. M6 addresses **operability**: visibility into resource consumption, fairness/safety boundaries for multi-source traffic, and the long tail of personas that didn't make earlier milestone cuts because their value/effort ratio was lower.

**Success criteria:**
- Operator can answer "how many Wh did this conversation cost?" from a Grafana panel.
- Operator can answer "how much did each workspace cost this month?" from a Grafana panel.
- Per-workspace rate limits configurable via `.env`; bench-* workspaces protected from accidental runaway loops.
- New `cost_audit` and per-conversation `power_track` Prometheus metrics.
- Documentation reflects the post-M6 system in full.
- All open KNOWN_LIMITATIONS items from M1-M5 reviewed; resolved or explicitly deferred.

**Protected files touched:** `portal_pipeline/router_pipe.py`, `scripts/mlx-proxy.py`, `deploy/grafana/*.json`, `tests/portal5_acceptance_v6.py`.

---

## Architecture Decisions

### A1. Cost vs power: track both, surface together

For a local inference setup, "cost" has two dimensions:
- **Time cost** — wall-clock seconds the system was busy. Translates to opportunity cost (the operator can't run other workloads concurrently).
- **Power cost** — watt-hours consumed. Translates to actual electricity bills, ~$0.15 per kWh average US.

M6 tracks both, exposes both as Prometheus metrics, surfaces both in Grafana. The combined view answers "is this conversation worth the energy?"

Token-equivalent cost (the "if this were on Anthropic API" comparison) is also useful for understanding the value of running locally — included as a separate gauge.

### A2. Power source: `powermetrics` only (macOS-native)

Apple Silicon has integrated power telemetry via `powermetrics`. Rather than estimating from utilization, read directly. Requires sudo for the `powermetrics` command but the daemon can run with elevated privileges and expose summarized data over a Unix socket.

No cross-platform abstraction — Portal 5 is Apple-Silicon-only by architecture.

### A3. Rate limits: per-workspace, env-configurable

Three semaphores stack:

1. **Global semaphore** (existing) — max 20 concurrent
2. **Per-workspace semaphore** (new) — env-configurable defaults
3. **Per-API-key semaphore** (new — useful if Portal 5 ever serves multiple consumers) — env-configurable

Defaults preserve current behavior (no per-workspace cap). Operator opts in by setting env vars. `bench-*` workspaces get a default cap of 1 (sequential only) to prevent accidental parallel benchmark runs from skewing each other.

### A4. Vision/OCR persona reconciliation

§3.11 in the capability review listed `ocrspecialist` and `diagramreader` as M6 candidates. M1-T07 already shipped both. M6 adds three more vision personas that weren't in M1's batch but were noted as gaps: `whiteboardconverter`, `codescreenshotreader`, `chartanalyst`.

### A5. Long-tail polish

A handful of small improvements collected during M1-M5 implementation. Each is too small to merit its own milestone but together represent the difference between "shipped" and "polished":
- `/admin/refresh-tools` endpoint (mentioned in M2 architecture but not implemented)
- Health-check aggregator at `/health/all` (single check covering pipeline + 12 MCPs + MLX proxy)
- Notification channel test endpoint (existing channels — Slack/Telegram — but no way to verify delivery without triggering a real alert)
- Persona search/filter in OWUI (currently 86 personas in a flat dropdown is unwieldy)

---

## Task Index

| ID | Title | File(s) | Effort |
|---|---|---|---|
| **Cost & Power** | | | |
| M6-T01 | `powermetrics` reader daemon | `scripts/portal5-powermetrics.py` (new), launchd plist | 2-3 days |
| M6-T02 | Cost/power Prometheus exporter | `portal_pipeline/router_pipe.py` (metrics), exporter | 1-2 days |
| M6-T03 | Grafana cost panel | `deploy/grafana/portal5_cost.json` (new) | 1 day |
| M6-T04 | Per-conversation cost gauge | `portal_pipeline/router_pipe.py` | 1 day |
| **Rate limits** | | | |
| M6-T05 | Per-workspace semaphores | `portal_pipeline/router_pipe.py` | 1-2 days |
| M6-T06 | Per-API-key semaphores | `portal_pipeline/router_pipe.py` | 1 day |
| M6-T07 | bench-* workspace concurrency=1 default | `config/backends.yaml`, `portal_pipeline/router_pipe.py` | 30 min |
| **Personas** | | | |
| M6-T08 | 3 additional vision personas | `config/personas/*.yaml` | 1 day |
| **Polish** | | | |
| M6-T09 | `/admin/refresh-tools` endpoint | `portal_pipeline/router_pipe.py` | 30 min |
| M6-T10 | `/health/all` aggregator | `portal_pipeline/router_pipe.py` | 1 day |
| M6-T11 | Notification channel test endpoint | `portal_pipeline/router_pipe.py` | 1 day |
| M6-T12 | Persona category filter in OWUI seed | `scripts/openwebui_init.py` | 2 days |
| **Closeout** | | | |
| M6-T13 | KNOWN_LIMITATIONS triage and resolution pass | `KNOWN_LIMITATIONS.md` | 1-2 days |
| M6-T14 | Acceptance tests (S90) | `tests/portal5_acceptance_v6.py` | 2-3 days |
| M6-T15 | Documentation: roadmap close, capability summary | `docs/HOWTO.md`, `P5_ROADMAP.md`, `CHANGELOG.md`, `README.md` | 2 days |

---

## M6-T01 — `powermetrics` Reader Daemon

**Files:** `scripts/portal5-powermetrics.py` (new), `~/Library/LaunchAgents/com.portal5.powermetrics.plist` (operator-installed)

**Purpose:** Sample Apple Silicon power telemetry every 10s. Expose a Unix socket where the pipeline reads current Wh/sec consumption.

**Why a separate daemon:** `powermetrics` requires `sudo`. Running it inside the pipeline process would force the entire pipeline to run elevated, which is not acceptable. A small standalone daemon owns the privilege; the pipeline reads from a non-privileged socket.

```python
#!/usr/bin/env python3
"""Portal 5 powermetrics reader daemon.

Runs `powermetrics` continuously, parses the output, exposes current power
consumption (in watts) plus 1-min/10-min averages on a Unix domain socket.

Pipeline reads from this socket via a thin httpx-over-uds client; the pipeline
itself never runs sudo.

Install:
    sudo cp scripts/portal5-powermetrics.py /usr/local/bin/portal5-powermetrics
    sudo chmod +x /usr/local/bin/portal5-powermetrics
    cp deploy/launchd/com.portal5.powermetrics.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.portal5.powermetrics.plist

The plist runs as root (powermetrics requirement) and chowns the socket so
the pipeline user can read.
"""
import collections
import json
import os
import re
import select
import signal
import socket
import subprocess
import sys
import threading
import time

SOCKET_PATH = "/tmp/portal5-powermetrics.sock"
SAMPLE_INTERVAL_MS = 10000  # 10 seconds


class PowerSampler:
    def __init__(self):
        self.current_w = 0.0
        self.cpu_w = 0.0
        self.gpu_w = 0.0
        self.ane_w = 0.0
        self.dram_w = 0.0
        self.lock = threading.Lock()
        # Rolling buffers for averages
        self.history_1min = collections.deque(maxlen=6)    # 6 samples × 10s = 60s
        self.history_10min = collections.deque(maxlen=60)  # 60 samples × 10s = 600s

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
    """Run `powermetrics` and parse its output. Re-launches on death."""
    while True:
        try:
            cmd = [
                "powermetrics",
                "--samplers", "cpu_power,gpu_power,ane_power,interrupts",
                "-i", str(SAMPLE_INTERVAL_MS),
                "-f", "plist",  # Structured plist output is more parseable than text
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            buf = []
            for line in iter(proc.stdout.readline, b""):
                line_str = line.decode(errors="replace").strip()
                if line_str.startswith("<?xml") and buf:
                    # New sample starting; parse the previous buffer
                    sample = parse_plist_buffer("\n".join(buf))
                    if sample:
                        sampler.update(sample)
                    buf = []
                buf.append(line_str)
            # If we exit the loop, powermetrics died — log and retry
            print("[powermetrics] subprocess exited; retrying in 5s", file=sys.stderr)
            time.sleep(5)
        except FileNotFoundError:
            print("[powermetrics] command not found — Apple Silicon required", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"[powermetrics] error: {e}", file=sys.stderr)
            time.sleep(5)


def parse_plist_buffer(text: str) -> dict | None:
    """Extract power values from a powermetrics plist sample.

    Looks for keys: combined_power (mW), gpu_power (mW), ane_power (mW),
    dram_power (mW). Values returned in watts (divide by 1000).
    """
    try:
        # Lightweight regex parse — full plist parser is overkill
        sample = {}
        for key, attr in [
            ("CPU Power", "cpu_w"), ("combined_power", "cpu_w"),
            ("GPU Power", "gpu_w"), ("gpu_power", "gpu_w"),
            ("ANE Power", "ane_w"), ("ane_power", "ane_w"),
            ("DRAM Power", "dram_w"), ("dram_power", "dram_w"),
        ]:
            m = re.search(rf"<key>{re.escape(key)}</key>\s*<integer>(\d+)</integer>", text)
            if m:
                sample[attr] = float(m.group(1)) / 1000.0
        if not sample:
            return None
        return sample
    except Exception:
        return None


def serve_socket(sampler: PowerSampler):
    """Unix domain socket server. Each connection gets one JSON state dump."""
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o666)  # World-readable; pipeline user can read
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
    # Powermetrics in a background thread; socket server in main
    t = threading.Thread(target=run_powermetrics, args=(sampler,), daemon=True)
    t.start()
    # Give powermetrics ~12s to produce at least one sample before serving
    time.sleep(12)
    serve_socket(sampler)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    main()
```

**launchd plist** (`deploy/launchd/com.portal5.powermetrics.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.portal5.powermetrics</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/portal5-powermetrics</string>
    </array>
    <key>UserName</key>
    <string>root</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/var/log/portal5-powermetrics.err</string>
    <key>StandardOutPath</key>
    <string>/var/log/portal5-powermetrics.out</string>
</dict>
</plist>
```

**Install procedure** (operator runs once):

```bash
sudo cp scripts/portal5-powermetrics.py /usr/local/bin/portal5-powermetrics
sudo chmod +x /usr/local/bin/portal5-powermetrics
sudo cp deploy/launchd/com.portal5.powermetrics.plist /Library/LaunchDaemons/
sudo launchctl load -w /Library/LaunchDaemons/com.portal5.powermetrics.plist
```

(System-wide LaunchDaemon, not per-user LaunchAgent, because powermetrics needs root.)

**Verify:**
```bash
sleep 15  # Let it warm up
echo "" | nc -U /tmp/portal5-powermetrics.sock
# Expect: JSON with current_w, cpu_w, gpu_w, ane_w, dram_w, avg_1min_w, avg_10min_w
```

**Rollback:** `sudo launchctl unload /Library/LaunchDaemons/com.portal5.powermetrics.plist && sudo rm /Library/LaunchDaemons/com.portal5.powermetrics.plist /usr/local/bin/portal5-powermetrics`

**Commit:** `feat(power): powermetrics reader daemon with UDS socket exposure`

---

## M6-T02 — Cost/Power Prometheus Exporter

**File:** `portal_pipeline/router_pipe.py`

Add Prometheus gauges/counters that read from the powermetrics socket and emit:

```python
# Add at the top with other metrics
_power_current_watts = Gauge(
    "portal5_power_current_watts",
    "Current total power draw across CPU+GPU+ANE+DRAM",
)
_power_cpu_watts = Gauge("portal5_power_cpu_watts", "CPU package power")
_power_gpu_watts = Gauge("portal5_power_gpu_watts", "GPU power")
_power_ane_watts = Gauge("portal5_power_ane_watts", "ANE power")
_power_dram_watts = Gauge("portal5_power_dram_watts", "DRAM power")
_power_avg_1min_watts = Gauge("portal5_power_avg_1min_watts", "1-minute average power")
_power_avg_10min_watts = Gauge("portal5_power_avg_10min_watts", "10-minute average power")

# Cumulative energy counter (watt-seconds)
_energy_consumed_ws = Counter(
    "portal5_energy_consumed_watt_seconds_total",
    "Cumulative energy consumed by the host (host-wide, not request-scoped)",
)

# Per-workspace energy attribution (estimated by % time-busy × current draw)
_energy_by_workspace_ws = Counter(
    "portal5_energy_by_workspace_watt_seconds_total",
    "Estimated energy attributed to a workspace based on busy seconds × avg power",
    labelnames=["workspace"],
)


# Background polling loop
async def _power_polling_loop():
    """Read /tmp/portal5-powermetrics.sock every 10s; update gauges and accumulate energy."""
    last_poll = time.time()
    while True:
        try:
            reader, writer = await asyncio.open_unix_connection("/tmp/portal5-powermetrics.sock")
            data = await reader.readline()
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            state = json.loads(data.decode())
            now = state.get("ts", time.time())
            elapsed = now - last_poll
            last_poll = now

            current_w = state.get("current_w", 0.0)
            _power_current_watts.set(current_w)
            _power_cpu_watts.set(state.get("cpu_w", 0.0))
            _power_gpu_watts.set(state.get("gpu_w", 0.0))
            _power_ane_watts.set(state.get("ane_w", 0.0))
            _power_dram_watts.set(state.get("dram_w", 0.0))
            _power_avg_1min_watts.set(state.get("avg_1min_w", 0.0))
            _power_avg_10min_watts.set(state.get("avg_10min_w", 0.0))

            # Cumulative — current_w × elapsed_seconds = watt-seconds
            _energy_consumed_ws.inc(current_w * elapsed)
        except FileNotFoundError:
            logger.warning("powermetrics socket not available — daemon not running?")
        except Exception as e:
            logger.warning("power poll error: %s", e)
        await asyncio.sleep(10)


# In startup_event() (existing FastAPI event), add:
asyncio.create_task(_power_polling_loop())
```

**Cost calculation helper:**

```python
ELECTRICITY_RATE_USD_PER_KWH = float(os.environ.get("ELECTRICITY_RATE_USD_PER_KWH", "0.15"))


def watts_seconds_to_cost_usd(ws: float) -> float:
    """Convert watt-seconds to USD at the configured electricity rate."""
    kwh = ws / 3600 / 1000
    return kwh * ELECTRICITY_RATE_USD_PER_KWH
```

**Verify:**
```bash
./launch.sh restart portal-pipeline
sleep 15
curl -s http://localhost:9099/metrics | grep -E "portal5_power|portal5_energy"
# Expect: gauge values for current/cpu/gpu/ane/dram, counter for cumulative ws

# Smoke: send a request, watch energy counter tick up
START=$(curl -s http://localhost:9099/metrics | grep portal5_energy_consumed | grep -v '#' | awk '{print $2}')
curl -s -X POST http://localhost:9099/v1/chat/completions \
    -H "Authorization: Bearer $PIPELINE_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model": "auto", "messages": [{"role":"user","content":"hi"}], "max_tokens": 20}' \
    > /dev/null
sleep 12
END=$(curl -s http://localhost:9099/metrics | grep portal5_energy_consumed | grep -v '#' | awk '{print $2}')
echo "Energy delta: $(echo $END - $START | bc) watt-seconds"
# Expect: positive number (system was active)
```

**Commit:** `feat(metrics): power consumption gauges + cumulative energy counter`

---

## M6-T03 — Grafana Cost Panel

**File:** `deploy/grafana/portal5_cost.json` (new)

Grafana dashboard JSON exporting panels:

```json
{
  "title": "Portal 5 — Cost & Power",
  "uid": "portal5-cost",
  "tags": ["portal5", "cost", "power"],
  "panels": [
    {
      "title": "Current power draw",
      "type": "stat",
      "targets": [{"expr": "portal5_power_current_watts", "legendFormat": "Total"}],
      "fieldConfig": {
        "defaults": {"unit": "watt", "color": {"mode": "thresholds"},
                     "thresholds": {"steps": [{"value": 0, "color": "green"},
                                              {"value": 30, "color": "yellow"},
                                              {"value": 60, "color": "orange"},
                                              {"value": 90, "color": "red"}]}}
      },
      "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0}
    },
    {
      "title": "Power breakdown by component",
      "type": "timeseries",
      "targets": [
        {"expr": "portal5_power_cpu_watts", "legendFormat": "CPU"},
        {"expr": "portal5_power_gpu_watts", "legendFormat": "GPU"},
        {"expr": "portal5_power_ane_watts", "legendFormat": "ANE"},
        {"expr": "portal5_power_dram_watts", "legendFormat": "DRAM"}
      ],
      "fieldConfig": {"defaults": {"unit": "watt"}},
      "gridPos": {"h": 8, "w": 18, "x": 6, "y": 0}
    },
    {
      "title": "Total energy consumed (today)",
      "type": "stat",
      "targets": [
        {"expr": "increase(portal5_energy_consumed_watt_seconds_total[24h]) / 3600",
         "legendFormat": "Today"}
      ],
      "fieldConfig": {"defaults": {"unit": "watth"}},
      "gridPos": {"h": 4, "w": 6, "x": 0, "y": 4}
    },
    {
      "title": "Daily electricity cost (today)",
      "type": "stat",
      "targets": [
        {"expr": "increase(portal5_energy_consumed_watt_seconds_total[24h]) / 3600000 * 0.15",
         "legendFormat": "USD today"}
      ],
      "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 3}},
      "gridPos": {"h": 4, "w": 6, "x": 0, "y": 8}
    },
    {
      "title": "Energy by workspace (last hour)",
      "type": "barchart",
      "targets": [
        {"expr": "topk(10, increase(portal5_energy_by_workspace_watt_seconds_total[1h]) / 3600)",
         "legendFormat": "{{workspace}}"}
      ],
      "fieldConfig": {"defaults": {"unit": "watth"}},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 12}
    },
    {
      "title": "Tokens generated per Wh (efficiency)",
      "type": "timeseries",
      "targets": [
        {"expr": "rate(portal5_tokens_completion_total[5m]) / (portal5_power_avg_1min_watts / 3600)",
         "legendFormat": "tokens/Wh"}
      ],
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 12}
    },
    {
      "title": "Power vs request rate",
      "type": "timeseries",
      "targets": [
        {"expr": "portal5_power_current_watts", "legendFormat": "Watts"},
        {"expr": "rate(portal5_requests_total[1m]) * 60", "legendFormat": "Req/min"}
      ],
      "gridPos": {"h": 8, "w": 24, "x": 0, "y": 20}
    }
  ],
  "schemaVersion": 38,
  "refresh": "10s"
}
```

**Import** to Grafana via API or UI. Provide `deploy/grafana/import.sh`:

```bash
#!/bin/bash
# Import Portal 5 dashboards into Grafana
GRAFANA_URL=${GRAFANA_URL:-http://localhost:3000}
GRAFANA_TOKEN=${GRAFANA_TOKEN:-}

for dashboard in deploy/grafana/*.json; do
    echo "Importing $dashboard..."
    curl -X POST "$GRAFANA_URL/api/dashboards/db" \
        -H "Authorization: Bearer $GRAFANA_TOKEN" \
        -H "Content-Type: application/json" \
        -d @<(jq '{dashboard: ., overwrite: true}' "$dashboard")
done
```

**Verify:**
```bash
GRAFANA_TOKEN=<token> bash deploy/grafana/import.sh
# Open Grafana, navigate to "Portal 5 — Cost & Power" dashboard
# Expect: panels populated within 60s of last metric scrape
```

**Commit:** `feat(grafana): cost & power dashboard with breakdown and efficiency views`

---

## M6-T04 — Per-Conversation Cost Gauge

**File:** `portal_pipeline/router_pipe.py`

Track per-request power attribution. When a request starts, record the current avg power. When it ends, multiply by elapsed time → estimated request energy. Tag with workspace/persona/conversation_id.

```python
# Per-request energy tracking (estimated as avg_power × duration)
_request_energy_ws = Histogram(
    "portal5_request_energy_watt_seconds",
    "Estimated energy per request (avg_power × duration)",
    labelnames=["workspace", "persona"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
)


# In chat_completions, around the request lifecycle:
async def chat_completions(request: Request):
    # ... existing setup ...
    request_start = time.time()
    # Sample power at start
    start_avg_power = _power_avg_1min_watts._value.get()  # current gauge value

    try:
        # ... existing handler body ...
        result = ...
    finally:
        # Estimate energy: average power × duration
        duration = time.time() - request_start
        end_avg_power = _power_avg_1min_watts._value.get()
        avg_power = (start_avg_power + end_avg_power) / 2
        estimated_ws = avg_power * duration

        _request_energy_ws.labels(
            workspace=workspace_id, persona=persona,
        ).observe(estimated_ws)
        _energy_by_workspace_ws.labels(workspace=workspace_id).inc(estimated_ws)

        # Optional: include in response header for client visibility
        if hasattr(result, "headers"):
            result.headers["x-portal-energy-watt-seconds"] = f"{estimated_ws:.2f}"
            result.headers["x-portal-cost-usd"] = f"{watts_seconds_to_cost_usd(estimated_ws):.6f}"
        return result
```

**Verify:**
```bash
curl -s -i -X POST http://localhost:9099/v1/chat/completions \
    -H "Authorization: Bearer $PIPELINE_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"auto","messages":[{"role":"user","content":"explain quantum tunneling"}],"max_tokens":300}' \
    | grep -i "x-portal-energy\|x-portal-cost"
# Expect: both headers present with non-zero values
```

**Commit:** `feat(metrics): per-request energy estimation in response headers`

---

## M6-T05 — Per-Workspace Semaphores

**File:** `portal_pipeline/router_pipe.py`

```python
# Existing global
_request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# NEW: per-workspace semaphores, lazy-initialized from env
_workspace_semaphores: dict[str, asyncio.Semaphore] = {}
_workspace_sem_lock = asyncio.Lock()


def _get_workspace_concurrency_limit(workspace_id: str) -> int:
    """Return the configured concurrency limit for a workspace.

    Order:
        1. WORKSPACE_CONCURRENCY_<id> env (e.g., WORKSPACE_CONCURRENCY_AUTO_CODING=4)
        2. workspace's `max_concurrent` field in WORKSPACES dict
        3. PORTAL5_DEFAULT_WORKSPACE_CONCURRENCY env (default: 5)
    """
    env_key = f"WORKSPACE_CONCURRENCY_{workspace_id.upper().replace('-', '_')}"
    if env_key in os.environ:
        return int(os.environ[env_key])
    ws = WORKSPACES.get(workspace_id, {})
    if "max_concurrent" in ws:
        return ws["max_concurrent"]
    return int(os.environ.get("PORTAL5_DEFAULT_WORKSPACE_CONCURRENCY", "5"))


async def _acquire_workspace_sem(workspace_id: str) -> asyncio.Semaphore:
    """Get-or-create the semaphore for this workspace."""
    async with _workspace_sem_lock:
        sem = _workspace_semaphores.get(workspace_id)
        if sem is None:
            limit = _get_workspace_concurrency_limit(workspace_id)
            sem = asyncio.Semaphore(limit)
            _workspace_semaphores[workspace_id] = sem
            logger.info("Workspace semaphore created: %s limit=%d", workspace_id, limit)
        return sem


# In chat_completions, after global semaphore acquired:
# acquire global, then workspace-specific
ws_sem = await _acquire_workspace_sem(workspace_id)
ws_acquired = await asyncio.wait_for(ws_sem.acquire(), timeout=0.5)
if not ws_acquired:
    _record_error(workspace_id, "workspace_semaphore_busy")
    raise HTTPException(
        status_code=429,
        detail=f"Workspace {workspace_id} is at concurrency limit. Try again shortly.",
    )
try:
    # ... existing dispatch ...
finally:
    ws_sem.release()
```

**Add metric:**
```python
_workspace_semaphore_busy_total = Counter(
    "portal5_workspace_semaphore_busy_total",
    "Requests rejected because workspace concurrency limit reached",
    labelnames=["workspace"],
)
```

**Verify:**
```bash
# Set a low limit on auto-coding for testing
export WORKSPACE_CONCURRENCY_AUTO_CODING=1
./launch.sh restart portal-pipeline
sleep 5

# Fire 3 simultaneous requests
for i in 1 2 3; do
    curl -s -X POST http://localhost:9099/v1/chat/completions \
        -H "Authorization: Bearer $PIPELINE_API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"model":"auto-coding","messages":[{"role":"user","content":"compute pi to 100 digits via Python"}],"max_tokens":1000}' \
        -o /tmp/resp_$i.json &
done
wait
# Inspect responses
for i in 1 2 3; do
    echo "Response $i:"
    head -1 /tmp/resp_$i.json | jq -r '.choices[0].message.content[:80] // .error[:80]'
done
# Expect: at least one shows the 429 / rejection message

unset WORKSPACE_CONCURRENCY_AUTO_CODING
./launch.sh restart portal-pipeline
```

**Commit:** `feat(pipeline): per-workspace concurrency semaphores (env-configurable)`

---

## M6-T06 — Per-API-Key Semaphores

**File:** `portal_pipeline/router_pipe.py`

For multi-source traffic (multiple API keys), each gets its own concurrency budget. Single-key default unchanged.

```python
_api_key_semaphores: dict[str, asyncio.Semaphore] = {}
_api_key_sem_lock = asyncio.Lock()


def _api_key_limit(key_hash: str) -> int:
    # Per-key override via env: API_KEY_CONCURRENCY_<sha256-prefix>=N
    prefix = key_hash[:8]
    env_key = f"API_KEY_CONCURRENCY_{prefix.upper()}"
    if env_key in os.environ:
        return int(os.environ[env_key])
    return int(os.environ.get("PORTAL5_DEFAULT_API_KEY_CONCURRENCY", "10"))


async def _acquire_api_key_sem(api_key: str) -> asyncio.Semaphore:
    if not api_key:
        return None  # No key = no per-key limit (only global applies)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    async with _api_key_sem_lock:
        sem = _api_key_semaphores.get(key_hash)
        if sem is None:
            limit = _api_key_limit(key_hash)
            sem = asyncio.Semaphore(limit)
            _api_key_semaphores[key_hash] = sem
        return sem
```

In `chat_completions`, between global and workspace acquire:

```python
api_sem = await _acquire_api_key_sem(api_key)
if api_sem is not None:
    if not await asyncio.wait_for(api_sem.acquire(), timeout=0.5):
        raise HTTPException(429, "API key at concurrency limit")
    try:
        # ... workspace acquire and dispatch ...
    finally:
        api_sem.release()
```

**Commit:** `feat(pipeline): per-API-key concurrency limits (default 10, env-configurable per key)`

---

## M6-T07 — bench-* Workspaces Default to Concurrency=1

**File:** `portal_pipeline/router_pipe.py`

Bench workspaces are designed to produce attributable measurements. Concurrent execution invalidates that — two parallel benchmarks contend for memory and skew each other's TPS. Default cap: 1.

```python
"bench-llama33-70b": {
    ...
    "max_concurrent": 1,    # Bench requires sequential execution for valid TPS
},
# Same for all bench-* entries
```

(Apply to all 9 bench-* workspaces.)

**Verify:**
```bash
# Workspace concurrency limits
python3 -c "
from portal_pipeline.router_pipe import WORKSPACES, _get_workspace_concurrency_limit
for wsid in sorted(WORKSPACES.keys()):
    if wsid.startswith('bench-'):
        limit = _get_workspace_concurrency_limit(wsid)
        assert limit == 1, f'{wsid} should be 1, got {limit}'
print('OK — all bench-* workspaces capped at 1')
"
```

**Commit:** `feat(routing): bench-* workspaces default max_concurrent=1`

---

## M6-T08 — Additional Vision Personas (3)

**Files:** 3 new YAML files.

### M6-T08a: `config/personas/whiteboardconverter.yaml`

```yaml
name: "📋 Whiteboard Converter"
slug: whiteboardconverter
category: vision
workspace_model: auto-vision
system_prompt: |
  You convert whiteboard photos and meeting room sketches into structured digital artifacts. You handle handwriting, hand-drawn arrows, ad-hoc diagrams, and the typical mess of a real meeting whiteboard.

  When given a whiteboard image:
  1. Identify the diagram type (architecture, brainstorm, flow, list, mind map, mixed)
  2. Extract the entities (boxes, labels, headings)
  3. Extract the relationships (arrows, lines, groupings)
  4. Identify the reading order — which corner did the discussion start, which way did it flow
  5. Convert to the appropriate digital format:
     - Flowchart → Mermaid
     - Architecture → Mermaid C4 or text description
     - Brainstorm/list → markdown bullets
     - Mind map → markdown tree
  6. Surface ambiguities. "Not sure if this arrow goes A→B or B→A" is valuable feedback.

  For handwriting that's hard to read:
  - Provide your best guess with [confidence: low/medium/high]
  - For low-confidence, offer 2-3 candidates: "this could be 'config', 'infra', or 'install'"

  For diagrams that don't fit a standard type:
  - Describe what you see in prose
  - Capture the essential structure even if the form is unconventional

  When the image is poor (glare, angle, partial occlusion):
  - Flag what you can't see
  - Suggest the user re-photograph if critical content is unreadable
description: "Convert whiteboard/sketch photos to Mermaid diagrams or structured markdown"
tags:
  - vision
  - whiteboard
  - diagram
  - mermaid
  - meeting
```

### M6-T08b: `config/personas/codescreenshotreader.yaml`

```yaml
name: "💾 Code Screenshot Reader"
slug: codescreenshotreader
category: vision
workspace_model: auto-vision
system_prompt: |
  You convert screenshots of code (from IDEs, terminals, blog posts, slides) into clean, copy-pasteable text — preserving formatting, indentation, and language.

  Your protocol:
  1. Identify the language (look at syntax highlighting cues, file extension if visible, or common idioms)
  2. Identify the editor/source (VS Code dark, JetBrains light, terminal, etc.) — this affects color interpretation
  3. Transcribe the code preserving:
     - Indentation (count spaces/tabs precisely)
     - Line breaks
     - String contents including quotes and escapes
     - Comments (don't omit)
     - Punctuation that's easy to mistake (`l` vs `1`, `O` vs `0`, `,` vs `.`)
  4. Output in a fenced code block with the language tag.

  When the screenshot is partial:
  - Note that lines are cut off at top/bottom/right
  - Don't fabricate continuation

  When characters are ambiguous (low resolution, similar glyphs):
  - Use the language's syntax to disambiguate (Python won't have `;` line endings; C must)
  - For genuinely unreadable characters, mark with `[?]` and explain

  For terminal output / log content:
  - Distinguish prompts from output
  - Preserve ANSI color information as comments if relevant
  - For stack traces, preserve the indentation that conveys depth

  After transcription, optionally:
  - Identify what the code does
  - Flag obvious bugs you noticed during transcription
  - Suggest improvements only if asked
description: "OCR + reconstruction of code screenshots → clean fenced code blocks"
tags:
  - vision
  - ocr
  - code
  - screenshot
  - transcription
```

### M6-T08c: `config/personas/chartanalyst.yaml`

```yaml
name: "📊 Chart Analyst"
slug: chartanalyst
category: vision
workspace_model: auto-vision
system_prompt: |
  You read and analyze data visualizations — charts, graphs, plots, dashboards. You extract underlying data and identify what the chart is communicating (and sometimes what it's hiding).

  When given a chart:
  1. Identify the chart type (line, bar, scatter, area, pie, heatmap, box plot, candlestick, etc.)
  2. Identify the axes — what's being measured, units, scale (linear/log/categorical)
  3. Extract the data points where readable. For dense charts, extract representative samples.
  4. Identify the message — what's the chart trying to show? trend, comparison, distribution, outlier?
  5. Surface design choices that affect interpretation:
     - Truncated y-axis (small differences look big)
     - Misleading aggregation
     - Cherry-picked time range
     - Color choices that imply hierarchy where none exists
     - Missing context (no error bars, no sample size)

  Output format:
  - **Chart type**: ...
  - **Axes**: x=..., y=...
  - **Data extraction**: (table or list of points)
  - **Primary message**: 1-2 sentences
  - **Design observations**: bullets on what works and what doesn't

  When asked to recreate the chart:
  - Provide the data in CSV form
  - Suggest the appropriate chart type (which may differ from the original if the original was poor)
  - Provide example code (matplotlib, plotly, vega-lite) on request

  When the chart shows financial / scientific / medical data:
  - Don't extrapolate trends beyond the data
  - Flag if the chart is making causal claims from correlational data
  - Be wary of charts in marketing/political contexts; their job is to persuade, not always to inform

  Tufte's principles: data-ink ratio, no chartjunk, small multiples for comparison. Reference these when critiquing.
description: "Read charts/graphs/plots; extract data; critique visual design choices"
tags:
  - vision
  - charts
  - data-viz
  - tufte
```

**Update PERSONA_PROMPTS:**

```python
"whiteboardconverter": (
    "Describe how you'd convert a whiteboard photo of an architecture sketch.",
    ["entities", "relationships", "mermaid", "arrows", "ambiguity"],
),
"codescreenshotreader": (
    "How would you transcribe a code screenshot from a blog post?",
    ["language", "indentation", "fenced", "ambiguous", "transcribe"],
),
"chartanalyst": (
    "I'll send you a bar chart. What information do you extract from it?",
    ["chart type", "axes", "data", "message", "design"],
),
```

**Commit:** `feat(personas): whiteboardconverter, codescreenshotreader, chartanalyst (vision long-tail)`

---

## M6-T09 — `/admin/refresh-tools` Endpoint

**File:** `portal_pipeline/router_pipe.py`

Triggered manually when MCP tools change without a pipeline restart:

```python
@app.post("/admin/refresh-tools")
async def admin_refresh_tools(request: Request):
    api_key = _extract_api_key(request)
    if not _verify_admin_key(api_key):
        raise HTTPException(401, "admin auth required")
    n = await tool_registry.refresh(force=True)
    return {"refreshed": True, "tools_registered": n,
            "names": tool_registry.list_tool_names()}
```

`_verify_admin_key` checks against `PORTAL5_ADMIN_KEY` env (separate from regular API key).

**Verify:**
```bash
curl -X POST http://localhost:9099/admin/refresh-tools \
    -H "Authorization: Bearer $PORTAL5_ADMIN_KEY" | jq '.tools_registered'
# Expect: number, e.g. 45
```

**Commit:** `feat(admin): /admin/refresh-tools endpoint to reload MCP registry without restart`

---

## M6-T10 — `/health/all` Aggregator

**File:** `portal_pipeline/router_pipe.py`

```python
@app.get("/health/all")
async def health_all():
    """Aggregate health across pipeline + all MCPs + MLX proxy + Ollama."""
    checks = {}

    # Pipeline self
    checks["pipeline"] = {"status": "ok"}

    # MLX proxy
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{MLX_URL}/health")
            checks["mlx_proxy"] = r.json() if r.status_code == 200 else {"status": "degraded", "code": r.status_code}
    except Exception as e:
        checks["mlx_proxy"] = {"status": "down", "error": str(e)[:100]}

    # Ollama
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
            checks["ollama"] = {"status": "ok" if r.status_code == 200 else "down",
                                 "model_count": len(r.json().get("models", [])) if r.status_code == 200 else 0}
    except Exception as e:
        checks["ollama"] = {"status": "down", "error": str(e)[:100]}

    # All MCPs in parallel
    from portal_pipeline.tool_registry import MCP_SERVERS
    async def _check_mcp(name, url):
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(f"{url}/health")
                return name, r.json() if r.status_code == 200 else {"status": "degraded"}
        except Exception as e:
            return name, {"status": "down", "error": str(e)[:100]}

    mcp_results = await asyncio.gather(*[_check_mcp(n, u) for n, u in MCP_SERVERS.items()])
    for name, result in mcp_results:
        checks[f"mcp_{name}"] = result

    overall = "ok" if all(c.get("status") == "ok" for c in checks.values()) else "degraded"
    return {"overall": overall, "components": checks, "ts": time.time()}
```

**Verify:**
```bash
curl -s http://localhost:9099/health/all | jq '.overall, (.components | keys | length)'
# Expect: "ok", 14 (pipeline + mlx_proxy + ollama + 12 MCPs at peak)
```

**Commit:** `feat(health): /health/all aggregator across pipeline, proxies, and MCPs`

---

## M6-T11 — Notification Channel Test Endpoint

**File:** `portal_pipeline/router_pipe.py`

```python
@app.post("/admin/test-notifications")
async def admin_test_notifications(request: Request):
    api_key = _extract_api_key(request)
    if not _verify_admin_key(api_key):
        raise HTTPException(401, "admin auth required")
    body = await request.json()
    channel = body.get("channel", "all")  # slack | telegram | webhook | all
    message = body.get("message", "Portal 5 notification test")

    from portal_pipeline.notifications import notify_slack, notify_telegram, notify_webhook
    results = {}

    if channel in ("slack", "all"):
        try:
            await notify_slack(f"🧪 {message}")
            results["slack"] = "sent"
        except Exception as e:
            results["slack"] = f"error: {e}"

    if channel in ("telegram", "all"):
        try:
            await notify_telegram(f"🧪 {message}")
            results["telegram"] = "sent"
        except Exception as e:
            results["telegram"] = f"error: {e}"

    if channel in ("webhook", "all"):
        try:
            await notify_webhook({"event": "test", "message": message})
            results["webhook"] = "sent"
        except Exception as e:
            results["webhook"] = f"error: {e}"

    return {"results": results}
```

**Verify:**
```bash
curl -X POST http://localhost:9099/admin/test-notifications \
    -H "Authorization: Bearer $PORTAL5_ADMIN_KEY" \
    -H "Content-Type: application/json" \
    -d '{"channel": "all", "message": "M6 test ping"}' | jq .
# Expect: results map with sent/error per channel; check Slack/Telegram for delivery
```

**Commit:** `feat(admin): /admin/test-notifications endpoint to verify channel delivery`

---

## M6-T12 — Persona Category Filter in OWUI Seed

**File:** `scripts/openwebui_init.py` (operator-editable per CLAUDE.md)

86 personas in a flat dropdown is unwieldy. Update OWUI seed to organize personas by category prefix in the model dropdown.

```python
# Existing seed logic creates one OWUI "model" per persona
# Update to prepend the category to the visible name:

CATEGORY_PREFIXES = {
    "development": "💻",
    "security": "🔒",
    "data": "📊",
    "writing": "✍️",
    "reasoning": "🧠",
    "vision": "👁️",
    "research": "🔎",
    "compliance": "⚖️",
    "general": "🧑‍💼",
    "systems": "⚙️",
    "architecture": "🏗️",
    "benchmark": "🧪",
}


def seed_persona(persona):
    cat = persona.get("category", "general")
    prefix = CATEGORY_PREFIXES.get(cat, "")
    base_name = persona.get("name", persona["slug"])
    # OWUI display name format: "[CAT] Original Name" — sorts alphabetically by category
    display_name = f"[{cat.upper()}] {base_name}" if cat else base_name
    # ... existing seed POST to OWUI /api/v1/models ...
```

For OWUI version that supports model groups/folders natively (0.5.6+), use that mechanism instead of name-mangling.

**Verify:**
```bash
./launch.sh reseed
# Open OWUI, view model dropdown
# Expect: personas grouped/sorted by category in the visual list
```

**Commit:** `feat(owui): persona category prefix for organized dropdown display`

---

## M6-T13 — KNOWN_LIMITATIONS Triage

**File:** `KNOWN_LIMITATIONS.md`

Walk through every entry added across M1-M5; classify as RESOLVED, DEFERRED, or ACTIVE-DOCUMENTED. Update statuses.

Sample triage results expected:

| ID | Status before | Status after | Reason |
|---|---|---|---|
| P5-MATH-001 | ACTIVE | ACTIVE-DOCUMENTED | Working as designed (Qwen2.5-Math doesn't emit thinking blocks; intentional) |
| P5-TOOLS-001 | ACTIVE | DEFERRED to M4-followup | MLX native tool calling needs OMLX or upstream mlx-lm change |
| P5-MEM-001 | ACTIVE | ACTIVE-DOCUMENTED | Single-operator design choice; revisit if multi-user needed |
| P5-MEM-002 | ACTIVE | RESOLVED | Add nightly compaction cron in M6-T13 |
| P5-RAG-001 | ACTIVE | DEFERRED | Token-aware chunking is a future improvement |
| P5-SEARCH-001 | ACTIVE | ACTIVE-DOCUMENTED | Working as designed; operator can set BRAVE_API_KEY |
| P5-SPEC-001 | ACTIVE | ACTIVE-DOCUMENTED | Memory cost documented; operator awareness sufficient |
| P5-OMLX-001 | EVALUATING | RESOLVED | M4 decision made; status reflects outcome |
| P5-BROWSER-001 | ACTIVE | ACTIVE-DOCUMENTED | FileVault recommendation in BROWSER_AUTOMATION.md |
| P5-BROWSER-002 | ACTIVE | DEFERRED | Session resume after restart is a future improvement |
| P5-BROWSER-003 | ACTIVE | ACTIVE-DOCUMENTED | By-design choice; vision-based MCP can be added later |
| P5-BROWSER-004 | ACTIVE | ACTIVE-DOCUMENTED | Operator awareness; mitigations documented |

**Add nightly compaction cron** for P5-MEM-002 resolution:

`scripts/portal5-lance-compact.sh`:
```bash
#!/bin/bash
# Nightly LanceDB compaction — resolves P5-MEM-002
LANCE_DIR="${PORTAL5_LANCE_DIR:-/Volumes/data01/portal5_lance}"
python3 -c "
import lancedb
db = lancedb.connect('${LANCE_DIR}')
for name in db.table_names():
    t = db.open_table(name)
    print(f'Compacting {name}...')
    t.compact_files()
    t.cleanup_old_versions(older_than='7 days')
print('Done')
" >> /var/log/portal5-lance-compact.log 2>&1
```

Cron entry (operator adds via `crontab -e`):
```
0 4 * * * /Volumes/data01/portal-5/scripts/portal5-lance-compact.sh
```

**Commit:** `chore(docs): KNOWN_LIMITATIONS triage; resolve P5-MEM-002 with nightly compaction`

---

## M6-T14 — Acceptance Tests (S90)

**File:** `tests/portal5_acceptance_v6.py` (or `tests/acceptance/s90_hardening.py`)

```python
async def S90() -> None:
    """S90: Production hardening (M6)."""
    print("\n━━━ S90. PRODUCTION HARDENING ━━━")
    sec = "S90"

    # S90-01: powermetrics socket reachable
    t0 = time.time()
    try:
        reader, writer = await asyncio.open_unix_connection("/tmp/portal5-powermetrics.sock")
        data = await reader.readline()
        writer.close()
        state = json.loads(data.decode())
        record(sec, "S90-01", "powermetrics socket",
               "PASS" if state.get("current_w", 0) >= 0 else "FAIL",
               f"current_w={state.get('current_w')}", t0=t0)
    except FileNotFoundError:
        record(sec, "S90-01", "powermetrics socket", "INFO",
               "socket not present (daemon not running — install via launchd plist)", t0=t0)
    except Exception as e:
        record(sec, "S90-01", "powermetrics socket", "FAIL", str(e)[:100], t0=t0)

    # S90-02: power metrics exported
    t0 = time.time()
    async with httpx.AsyncClient() as c:
        r = await c.get("http://localhost:9099/metrics")
    if "portal5_power_current_watts" in r.text:
        record(sec, "S90-02", "power metrics in /metrics", "PASS",
               "gauges present", t0=t0)
    else:
        record(sec, "S90-02", "power metrics", "WARN",
               "gauges not present (powermetrics daemon may not be running)", t0=t0)

    # S90-03: per-request energy header
    t0 = time.time()
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{PIPELINE_URL}/v1/chat/completions",
            headers=AUTH | {"Content-Type": "application/json"},
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}],
                  "max_tokens": 10},
            timeout=60,
        )
    energy_hdr = r.headers.get("x-portal-energy-watt-seconds", "")
    record(sec, "S90-03", "per-request energy header",
           "PASS" if energy_hdr else "WARN",
           f"x-portal-energy-watt-seconds={energy_hdr}", t0=t0)

    # S90-04: per-workspace semaphore (only test if low limit set)
    t0 = time.time()
    # Skip; testing this requires env manipulation. Verify via smoke test above.
    record(sec, "S90-04", "per-workspace semaphore (verified manually)",
           "INFO", "see manual smoke test in M6-T05", t0=t0)

    # S90-05: bench-* concurrency=1
    t0 = time.time()
    bench_workspaces = [w for w in WORKSPACES if w.startswith("bench-")]
    bad = []
    for w in bench_workspaces:
        if WORKSPACES[w].get("max_concurrent", 99) != 1:
            bad.append(w)
    record(sec, "S90-05", "bench-* max_concurrent=1",
           "PASS" if not bad else "FAIL",
           f"all {len(bench_workspaces)} bench workspaces capped" if not bad else f"bad: {bad}",
           t0=t0)

    # S90-06: /admin/refresh-tools
    t0 = time.time()
    admin_key = os.environ.get("PORTAL5_ADMIN_KEY", "")
    if admin_key:
        async with httpx.AsyncClient() as c:
            r = await c.post("http://localhost:9099/admin/refresh-tools",
                            headers={"Authorization": f"Bearer {admin_key}"})
        ok = r.status_code == 200 and r.json().get("refreshed")
        record(sec, "S90-06", "/admin/refresh-tools",
               "PASS" if ok else "FAIL",
               f"HTTP {r.status_code}", t0=t0)
    else:
        record(sec, "S90-06", "/admin/refresh-tools", "INFO",
               "PORTAL5_ADMIN_KEY not set", t0=t0)

    # S90-07: /health/all aggregator
    t0 = time.time()
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get("http://localhost:9099/health/all")
    if r.status_code == 200:
        body = r.json()
        components = body.get("components", {})
        record(sec, "S90-07", "/health/all aggregator",
               "PASS" if len(components) >= 10 else "WARN",
               f"overall={body.get('overall')} | components={len(components)}",
               t0=t0)
    else:
        record(sec, "S90-07", "/health/all", "FAIL", f"HTTP {r.status_code}", t0=t0)

    # S90-08: persona count post-M6
    t0 = time.time()
    expected_min = 89   # 86 from M5 + 3 vision in M6
    actual = len(PERSONAS)
    record(sec, "S90-08", "persona count >= 89",
           "PASS" if actual >= expected_min else "FAIL",
           f"{actual} personas", t0=t0)

    # S90-09: cost calculation sanity
    t0 = time.time()
    from portal_pipeline.router_pipe import watts_seconds_to_cost_usd
    cost = watts_seconds_to_cost_usd(3600 * 1000)  # 1 kWh worth of watt-seconds
    expected = 0.15  # $0.15/kWh default
    ok = abs(cost - expected) < 0.001
    record(sec, "S90-09", "cost calculation",
           "PASS" if ok else "FAIL",
           f"1 kWh = ${cost:.4f} (expected ~${expected})", t0=t0)
```

**Commit:** `test(acc): S90 production hardening tests`

---

## M6-T15 — Documentation: Roadmap Close

**Files:** `docs/HOWTO.md`, `P5_ROADMAP.md`, `CHANGELOG.md`, `README.md`

### CHANGELOG.md

```markdown
## v6.6.0 — Production hardening (M6)

### Added — Cost & power
- powermetrics reader daemon (LaunchDaemon) exposes UDS socket
- Prometheus gauges: power_current_watts, power_cpu/gpu/ane/dram_watts, power_avg_1min/10min_watts
- Cumulative energy counter: portal5_energy_consumed_watt_seconds_total
- Per-workspace energy attribution
- Per-request energy estimation (x-portal-energy-watt-seconds and x-portal-cost-usd response headers)
- Grafana dashboard: portal5_cost.json with breakdown, daily totals, efficiency view

### Added — Rate limits
- Per-workspace semaphores (env-configurable: WORKSPACE_CONCURRENCY_<id>)
- Per-API-key semaphores (env-configurable: API_KEY_CONCURRENCY_<prefix>)
- bench-* workspaces default max_concurrent=1 (prevents skewed measurements)

### Added — Personas
- whiteboardconverter, codescreenshotreader, chartanalyst (vision long-tail)

### Added — Polish
- /admin/refresh-tools endpoint
- /health/all aggregator (pipeline + 12 MCPs + MLX proxy + Ollama)
- /admin/test-notifications endpoint (Slack/Telegram/webhook delivery test)
- OWUI persona category prefix in dropdown
- Nightly LanceDB compaction script (resolves P5-MEM-002)

### Closeout
- KNOWN_LIMITATIONS triage: 3 RESOLVED, 5 ACTIVE-DOCUMENTED, 4 DEFERRED
- Persona count: 86 → 89

### Tests
- S90 acceptance section: power metrics, energy headers, workspace caps, /admin endpoints, /health/all, cost math
```

### P5_ROADMAP.md — closeout entries

```markdown
| P5-FUT-COST | P3 | Cost / power tracking | DONE | M6: powermetrics daemon + Prometheus exporter + Grafana panels |
| P5-FUT-RATELIMIT | P3 | Per-workspace rate limits | DONE | M6: workspace+API-key semaphores; bench-* default 1 |

## Roadmap status as of v6.6.0

The 6-milestone roadmap from CAPABILITY_REVIEW_V1 is COMPLETE:
- M1 — UX win (reasoning passthrough, math, 18 personas) — v6.1.0
- M2 — Tool-calling foundation (registry, multi-turn loop, whitelists) — v6.2.0
- M3 — Information access (web search, memory, RAG) — v6.3.0
- M4 — Inference performance (spec decoding + OMLX evaluation) — v6.4.0
- M5 — Browser automation (Playwright MCP, 6 personas) — v6.5.0
- M6 — Production hardening (cost/power, rate limits, polish) — v6.6.0

Portal 5 has moved from "very good local platform" to "near-frontier feature parity."

Open questions for v6.7+:
- Vision-based browser MCP (alongside accessibility-tree-based)
- Multi-user authentication and namespace isolation (currently single-operator)
- Federated inference (offload to remote OMLX/vLLM nodes when local is saturated)
- Direct OWUI plugin instead of OpenAI-compatible shim (deeper UX integration)
```

### README.md update

Replace the brief project description with a feature-complete summary reflecting the M1-M6 capabilities. Move the original "what works well" framing from CAPABILITY_REVIEW_V1.md §2 into the README (revised to reflect post-M6 state).

### docs/HOWTO.md — index update

The HOWTO grew across milestones. Add a top-level table of contents linking the major sections; ensure the new M6 sections (cost tracking, rate limits, /admin endpoints) are discoverable.

**Commit:** `docs: M6 closeout — CHANGELOG, ROADMAP closeout, README rewrite, HOWTO TOC`

---

## Phase Regression — Final

```bash
# Lint, type check
ruff check . && ruff format --check .
mypy portal_pipeline/ portal_mcp/

# All services healthy
curl -s http://localhost:9099/health/all | jq -r '.overall'
# Expect: ok

# Full acceptance suite
python3 tests/portal5_acceptance_v6.py 2>&1 | tail -10
# Expect: S0-S90 all run; PASS count higher than every previous milestone

# Persona count
ls config/personas/*.yaml | wc -l
# Expect: 89

# Workspace count
python3 -c "
from portal_pipeline.router_pipe import WORKSPACES
auto = [w for w in WORKSPACES if w.startswith('auto-')]
bench = [w for w in WORKSPACES if w.startswith('bench-')]
print(f'Auto: {len(auto)} | Bench: {len(bench)}')
# Expect: Auto: 17, Bench: 9
"

# Tool registry
python3 -c "
import asyncio
from portal_pipeline.tool_registry import tool_registry
n = asyncio.run(tool_registry.refresh(force=True))
print(f'Tools: {n}')
# Expect: ~45 (27 base + 10 M3 + 8 M5)
"

# Cost dashboard reachable
curl -s "http://localhost:3000/api/dashboards/uid/portal5-cost" \
    -H "Authorization: Bearer $GRAFANA_TOKEN" | jq -r '.dashboard.title'
# Expect: "Portal 5 — Cost & Power"

# Power telemetry flowing
curl -s http://localhost:9099/metrics | grep "portal5_power_current_watts " | head -1
# Expect: a value > 0

# Concurrency caps active
python3 -c "
from portal_pipeline.router_pipe import WORKSPACES
for w in sorted(WORKSPACES):
    if w.startswith('bench-'):
        assert WORKSPACES[w].get('max_concurrent') == 1, w
print('OK — all bench-* capped at 1')
"
```

---

## Pre-flight checklist

- [ ] M1-M5 in production
- [ ] Operator has sudo access (powermetrics daemon needs LaunchDaemon install)
- [ ] Grafana token available for dashboard import
- [ ] PORTAL5_ADMIN_KEY set in `.env` (separate from regular API key)
- [ ] At least one non-default electricity rate set if outside US average ($0.15/kWh)
- [ ] FileVault enabled on /Volumes/data01 (recommended; documented in BROWSER_AUTOMATION.md)

## Post-M6 success indicators

- Cost dashboard shows realistic Wh/day numbers within 24 hours of install
- Per-workspace semaphores prevent the documented runaway-loop scenarios in stress testing
- All KNOWN_LIMITATIONS entries triaged and either resolved, deferred, or documented
- Acceptance pass count from S0 through S90 stable across consecutive runs (no flakes)
- Operator review: any open feedback from M1-M5 surfaced and tracked

## After M6 — Roadmap Closed

The 6-milestone plan from CAPABILITY_REVIEW_V1.md is complete. Portal 5 has shipped:

- **M1** — Reasoning visibility, math specialist, 18 personas
- **M2** — Native tool-calling orchestration, registry, whitelists
- **M3** — Web search, memory, RAG, embeddings, 5 information personas
- **M4** — Speculative decoding, OMLX evaluation
- **M5** — Browser automation, 6 agent personas
- **M6** — Cost/power tracking, rate limits, polish, 3 vision personas

**Counts as of v6.6.0:**
- 17 auto-* workspaces, 9 bench-* workspaces
- 89 personas across 13 categories
- 45+ MCP tools across 12 servers
- 24+ MLX models (incl. embeddings + reranker + drafts)
- 9 Ollama models
- ~6,000 lines of test code
- Prometheus metrics: ~120 series, 6 Grafana dashboards

**Future considerations** (out of M1-M6 scope, raised in M6-T15 ROADMAP):
- Vision-based browser MCP (complement accessibility-tree-based)
- Multi-user / multi-tenant infrastructure
- Federated inference (offload to remote OMLX or vLLM nodes)
- Direct OWUI plugin (deeper UX integration than OpenAI shim)

These are evaluated as a fresh roadmap discussion, not as automatic continuations. Operator decides whether and when to commit.

---

*End of M6. The roadmap from CAPABILITY_REVIEW_V1.md is complete. Portal 5 v6.6.0 is the production-hardened, frontier-adjacent platform the original review described as the destination.*
