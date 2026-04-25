#!/usr/bin/env python3
"""MLX Watchdog — monitors proxy, mlx_lm, mlx_vlm with auto-recovery and notifications.

Runs as a background daemon on Apple Silicon. Checks all three MLX components
every 30 seconds. Sends alerts through configured notification channels when
a component dies. Auto-recovers by restarting the dead component.

Components monitored:
  - MLX proxy (:8081) — the model-aware routing proxy
  - mlx_lm server (:18081) — text-only model server
  - mlx_vlm server (:18082) — VLM model server

Notification channels (reads same env vars as pipeline):
  - TELEGRAM_BOT_TOKEN + TELEGRAM_USER_IDS → Telegram
  - PUSHOVER_TOKEN + PUSHOVER_USER → Pushover
  - SLACK_WEBHOOK_URL → Slack
  - WEBHOOK_URL → Generic webhook POST

Usage: python3 mlx-watchdog.py
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx


def _load_dotenv() -> None:
    """Load .env file from project root if env vars are missing.

    Finds .env by walking up from this script's location (up to 3 levels).
    Only sets vars that are not already in the environment — respects caller's env.
    """
    script = Path(__file__).resolve()
    for candidate in [script.parent, script.parent.parent, script.parent.parent.parent]:
        env_file = candidate / ".env"
        if env_file.is_file():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
            return


_load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [mlx-watchdog] %(levelname)s %(message)s",
)
logger = logging.getLogger("mlx-watchdog")

# ── Configuration ────────────────────────────────────────────────────────────

PROXY_PORT = int(os.environ.get("MLX_PROXY_PORT", "8081"))
LM_PORT = int(os.environ.get("MLX_LM_PORT", "18081"))
VLM_PORT = int(os.environ.get("MLX_VLM_PORT", "18082"))

CHECK_INTERVAL = int(os.environ.get("MLX_WATCHDOG_INTERVAL", "30"))
RECOVERY_THRESHOLD = int(os.environ.get("MLX_RECOVERY_THRESHOLD", "2"))
MAX_RECOVERY_ATTEMPTS = int(os.environ.get("MLX_MAX_RECOVERY_ATTEMPTS", "3"))
WATCHDOG_ENABLED = os.environ.get("MLX_WATCHDOG_ENABLED", "true").lower() != "false"
# Seconds to wait for Metal GPU memory reclamation after killing a zombie server.
# 10s was too short for large models (>20GB) — Metal can take 30-60s to fully
# release pages after SIGKILL. Set higher if you see reload failures after zombie kills.
ZOMBIE_KILL_WAIT_S = int(os.environ.get("MLX_ZOMBIE_KILL_WAIT_S", "30"))

PROXY_PID_FILE = Path(os.environ.get("MLX_PROXY_PID_FILE", "/tmp/mlx-proxy.pid"))
WATCHDOG_PID_FILE = Path("/tmp/mlx-watchdog.pid")

# ── Notification config (same env vars as pipeline) ──────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_IDS = os.environ.get("TELEGRAM_USER_IDS", "")
PUSHOVER_TOKEN = os.environ.get("PUSHOVER_API_TOKEN", "")
PUSHOVER_USER = os.environ.get("PUSHOVER_USER_KEY", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# ── State tracking ───────────────────────────────────────────────────────────


@dataclass
class ComponentState:
    name: str
    port: int
    healthy: bool = True
    consecutive_failures: int = 0
    last_recovery_attempt: float = 0.0
    recovery_attempts: int = 0
    last_notification: float = 0.0


COMPONENTS: dict[str, ComponentState] = {}


def init_components() -> None:
    COMPONENTS["proxy"] = ComponentState("MLX Proxy", PROXY_PORT)
    COMPONENTS["mlx_lm"] = ComponentState("mlx_lm server", LM_PORT)
    COMPONENTS["mlx_vlm"] = ComponentState("mlx_vlm server", VLM_PORT)


# ── Health checks ────────────────────────────────────────────────────────────


def check_component(state: ComponentState) -> bool:
    """Check if a component is responding on its port.

    For the proxy (:8081), any HTTP response means it's alive — even 503
    (state=none or down). The proxy's state machine handles its own health
    and server lifecycle. We only care if the proxy process is alive and
    listening. The proxy manages mlx_lm/mlx_vlm servers internally.

    For servers (:18081/:18082), only 200 means healthy. However, server
    monitoring is informational only — the watchdog does NOT attempt server
    recovery because the proxy's ensure_server() manages server lifecycle
    including model loading, GPU memory reclamation, and readiness detection.
    """
    try:
        r = httpx.get(f"http://127.0.0.1:{state.port}/health", timeout=5)
        if state.port == PROXY_PORT:
            # Proxy: any response = alive (state managed internally)
            return True
        return r.status_code == 200
    except Exception:
        return False


def _check_proxy_state() -> dict:
    """Get detailed proxy state for diagnostics."""
    try:
        r = httpx.get(f"http://127.0.0.1:{PROXY_PORT}/health", timeout=5)
        if r.status_code in (200, 503):
            return r.json()
    except Exception:
        pass
    return {}


def check_server_zombies() -> None:
    """Kill MLX server processes that are alive in the OS but dead to HTTP.

    A zombie server holds ~20-46 GB of Metal GPU memory indefinitely.
    The proxy's /health returns state=down and future requests stall
    because the port is occupied by the zombie.

    Detection: pgrep finds the process, but GET /health times out or errors.
    Action: SIGTERM → wait ZOMBIE_KILL_WAIT_S for Metal reclaim → notify.

    This runs on every watchdog cycle, independently of the failure-counter
    recovery path so zombies are cleared promptly without waiting for
    RECOVERY_THRESHOLD failures to accumulate.

    Guard: skips zombie detection when the proxy reports state=switching.
    During a model switch the new server process is alive but its /health
    is not yet responding (model weights are still loading — can take 30-90s
    for large models). Without this guard the watchdog would kill a healthy
    server that is simply still loading, exactly the interference it must avoid.
    """
    # Check proxy state before doing anything — don't interfere with model loads
    try:
        proxy_info = _check_proxy_state()
        proxy_state = proxy_info.get("state", "unknown")
        if proxy_state == "switching":
            logger.debug("check_server_zombies: proxy state=switching, skipping")
            return
    except Exception as e:
        logger.debug("check_server_zombies: could not read proxy state: %s", e)
        # Proxy unreachable — proceed anyway, zombie cleanup is still warranted

    server_specs = [
        ("mlx_lm.server", LM_PORT, "mlx_lm"),
        ("mlx_vlm.server", VLM_PORT, "mlx_vlm"),
    ]
    any_killed = False
    for proc_pattern, port, name in server_specs:
        try:
            res = subprocess.run(
                ["pgrep", "-f", proc_pattern], capture_output=True, text=True
            )
            pids = [int(p) for p in res.stdout.strip().split() if p.isdigit()]
            if not pids:
                continue

            # Process exists — is /health responding?
            alive = False
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
                alive = r.status_code == 200
            except Exception:
                pass

            if alive:
                continue

            # Process up but /health dead → zombie, kill it
            logger.warning(
                "%s zombie detected on :%d — process %s alive but /health unresponsive",
                name,
                port,
                pids,
            )
            send_notification(
                "DOWN",
                f"{name} zombie on :{port} — process {pids} holding GPU memory without serving requests. Killing.",
            )

            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                    logger.info("SIGTERM → %s PID %d", name, pid)
                except ProcessLookupError:
                    pass

            any_killed = True

            # Also free the port if process survives SIGTERM
            time.sleep(3)
            for pid in pids:
                try:
                    os.kill(pid, 0)  # still alive?
                    os.kill(pid, signal.SIGKILL)
                    logger.info("SIGKILL → %s PID %d (survived SIGTERM)", name, pid)
                except ProcessLookupError:
                    pass  # already gone

        except Exception as e:
            logger.warning("Zombie check error for %s: %s", name, e)

    if any_killed:
        logger.info("Waiting %ds for Metal GPU memory reclamation…", ZOMBIE_KILL_WAIT_S)
        time.sleep(ZOMBIE_KILL_WAIT_S)
        # Reset server component state so the proxy won't get stale failure counts
        for name in ("mlx_lm", "mlx_vlm"):
            if name in COMPONENTS:
                COMPONENTS[name].consecutive_failures = 0
                COMPONENTS[name].healthy = True
        send_notification(
            "RECOVERED",
            f"Zombie MLX server(s) cleared. GPU memory releasing. Proxy will reload on next request.",
        )


def run_health_checks() -> None:
    """Check all components and track failures.

    Only the proxy component triggers recovery. Server components are
    informational — alerts are sent but no recovery is attempted because
    the proxy manages server lifecycle internally.
    """
    for name, state in COMPONENTS.items():
        is_healthy = check_component(state)

        if is_healthy:
            if not state.healthy:
                logger.info("%s recovered on :%d", state.name, state.port)
                send_notification(
                    "RECOVERED",
                    f"{state.name} is healthy again on :{state.port}",
                )
            state.healthy = True
            state.consecutive_failures = 0
            state.recovery_attempts = 0
        else:
            state.consecutive_failures += 1
            state.healthy = False
            logger.warning(
                "%s unhealthy (failure %d/%d)",
                state.name,
                state.consecutive_failures,
                RECOVERY_THRESHOLD,
            )

            # Alert on first failure
            if state.consecutive_failures == 1:
                # Include proxy state info for diagnostics
                extra = ""
                if name == "proxy":
                    proxy_state = _check_proxy_state()
                    if proxy_state:
                        extra = f" (state={proxy_state.get('state', '?')}, error={proxy_state.get('last_error', 'none')})"
                send_notification(
                    "DOWN",
                    f"{state.name} is not responding on :{state.port}{extra}",
                )

            # Only attempt recovery for the proxy — servers are managed by the proxy
            if name == "proxy" and state.consecutive_failures >= RECOVERY_THRESHOLD:
                attempt_recovery(name, state)
            elif name != "proxy" and state.consecutive_failures >= RECOVERY_THRESHOLD:
                # Server down — notify but don't recover (proxy manages servers)
                logger.warning(
                    "%s down — proxy will recover it on next request",
                    state.name,
                )


# ── Recovery ─────────────────────────────────────────────────────────────────


def attempt_recovery(name: str, state: ComponentState) -> None:
    """Attempt to recover a dead component."""
    now = time.time()

    # Don't retry too frequently
    if now - state.last_recovery_attempt < 60:
        return

    if state.recovery_attempts >= MAX_RECOVERY_ATTEMPTS:
        logger.error(
            "%s: max recovery attempts (%d) reached, giving up",
            state.name,
            MAX_RECOVERY_ATTEMPTS,
        )
        send_notification(
            "CRITICAL",
            f"{state.name} failed {MAX_RECOVERY_ATTEMPTS} recovery attempts. Manual intervention required.",
        )
        return

    state.last_recovery_attempt = now
    state.recovery_attempts += 1

    logger.info(
        "Attempting recovery #%d for %s",
        state.recovery_attempts,
        state.name,
    )

    try:
        if name == "proxy":
            recover_proxy()
        elif name == "mlx_lm":
            recover_server("lm", LM_PORT)
        elif name == "mlx_vlm":
            recover_server("vlm", VLM_PORT)
    except Exception as e:
        logger.error("Recovery failed for %s: %s", state.name, e)
        send_notification(
            "ERROR",
            f"Recovery attempt #{state.recovery_attempts} failed for {state.name}: {e}",
        )


def recover_proxy() -> None:
    """Kill hung proxy and restart it.

    Uses the same approach as mlx-proxy.py's ensure_server():
    kill all MLX processes, wait for GPU memory reclamation, restart proxy,
    verify it responds on /health.
    """
    # Kill all MLX processes — proxy and any servers it was managing
    for pattern in ["mlx-proxy.py", "mlx_lm.server", "mlx_vlm.server"]:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
        )
        for pid in result.stdout.strip().split("\n"):
            if pid:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    logger.info("Sent SIGTERM to %s (PID %s)", pattern, pid)
                except ProcessLookupError:
                    pass

    # Also kill anything on the ports
    for port in [PROXY_PORT, LM_PORT, VLM_PORT]:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
        )
        for pid in result.stdout.strip().split("\n"):
            if pid:
                try:
                    os.kill(int(pid), signal.SIGKILL)
                    logger.info("Force-killed PID %s on port %d", pid, port)
                except ProcessLookupError:
                    pass

    # Wait for GPU memory reclamation (critical on Apple Silicon)
    logger.info("Waiting 15s for GPU memory reclamation...")
    time.sleep(15)

    # Restart proxy — it will handle server lifecycle on demand
    script_dir = Path(__file__).parent
    proxy_script = script_dir / "mlx-proxy.py"
    if not proxy_script.exists():
        raise FileNotFoundError(f"mlx-proxy.py not found at {proxy_script}")

    subprocess.Popen(
        ["python3", str(proxy_script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("Restarted MLX proxy — it will load models on demand")

    # Wait for proxy to respond (any response = alive)
    for attempt in range(30):
        time.sleep(2)
        try:
            r = httpx.get(f"http://127.0.0.1:{PROXY_PORT}/health", timeout=5)
            if r.status_code in (200, 503):
                name = "MLX Proxy"
                COMPONENTS["proxy"].healthy = True
                COMPONENTS["proxy"].consecutive_failures = 0
                COMPONENTS["proxy"].recovery_attempts = 0
                send_notification("RECOVERED", f"{name} recovered on :{PROXY_PORT}")
                return
        except Exception:
            pass

    raise RuntimeError("MLX proxy did not come up after restart")


def recover_server(stype: str, port: int) -> None:
    """Server recovery is handled by the proxy's ensure_server().

    The watchdog no longer attempts server recovery because:
    1. The proxy manages server lifecycle (start/stop/model loading)
    2. Starting a server without --model loads no model
    3. The proxy's ensure_server() handles GPU memory reclamation
    4. Log-based readiness detection requires proxy-level coordination

    Instead, we just log that the server is down — the proxy will recover
    it on the next incoming request.
    """
    module = f"mlx_{stype}"
    logger.info(
        "%s server down on :%d — proxy will recover on next request",
        module,
        port,
    )


# ── Notifications ────────────────────────────────────────────────────────────


def send_notification(severity: str, message: str) -> None:
    """Send notification through all configured channels."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    title = f"[MLX {severity}] Portal 5"
    body = f"{message}\nTime: {ts}"

    if TELEGRAM_BOT_TOKEN:
        _notify_telegram(title, body)
    if PUSHOVER_TOKEN and PUSHOVER_USER:
        _notify_pushover(severity, message)
    if SLACK_WEBHOOK_URL:
        _notify_slack(severity, message)
    if WEBHOOK_URL:
        _notify_webhook(severity, message)


def _notify_telegram(title: str, body: str) -> None:
    """Send via Telegram Bot API (plain text to avoid Markdown parse errors)."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        user_ids = [
            int(uid.strip()) for uid in TELEGRAM_USER_IDS.split(",") if uid.strip().isdigit()
        ]
        text = f"{title}\n\n{body}"
        for uid in user_ids:
            httpx.post(
                url,
                json={"chat_id": uid, "text": text},
                timeout=10,
            )
        logger.info("Telegram notification sent")
    except Exception as e:
        logger.warning("Telegram notification failed: %s", e)


def _notify_pushover(severity: str, message: str) -> None:
    """Send via Pushover API."""
    try:
        priority = {"DOWN": 1, "CRITICAL": 2, "ERROR": 1, "RECOVERED": 0}.get(severity, 0)
        httpx.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_TOKEN,
                "user": PUSHOVER_USER,
                "title": f"MLX {severity}",
                "message": message,
                "priority": priority,
            },
            timeout=10,
        )
        logger.info("Pushover notification sent")
    except Exception as e:
        logger.warning("Pushover notification failed: %s", e)


def _notify_slack(severity: str, message: str) -> None:
    """Send via Slack webhook."""
    try:
        emoji = {
            "DOWN": ":warning:",
            "CRITICAL": ":rotating_light:",
            "RECOVERED": ":white_check_mark:",
        }.get(severity, ":bell:")
        httpx.post(
            SLACK_WEBHOOK_URL,
            json={
                "text": f"{emoji} *MLX {severity}*\n{message}",
            },
            timeout=10,
        )
        logger.info("Slack notification sent")
    except Exception as e:
        logger.warning("Slack notification failed: %s", e)


def _notify_webhook(severity: str, message: str) -> None:
    """Send via generic webhook POST."""
    try:
        httpx.post(
            WEBHOOK_URL,
            json={
                "source": "mlx-watchdog",
                "severity": severity,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            timeout=10,
        )
        logger.info("Webhook notification sent")
    except Exception as e:
        logger.warning("Webhook notification failed: %s", e)


# ── Main loop ────────────────────────────────────────────────────────────────


def write_pid_file() -> None:
    WATCHDOG_PID_FILE.write_text(str(os.getpid()))
    logger.info("Watchdog PID %d written to %s", os.getpid(), WATCHDOG_PID_FILE)


def cleanup(signum=None, frame=None):
    """Clean up on exit."""
    sig_name = signal.Signals(signum).name if signum else "UNKNOWN"
    logger.info("Watchdog shutting down (signal: %s)", sig_name)
    send_notification("STOPPED", f"MLX Watchdog shutting down (signal: {sig_name})")
    WATCHDOG_PID_FILE.unlink(missing_ok=True)
    logger.info("Watchdog stopped")
    sys.exit(0)


def _acquire_singleton_lock() -> bool:
    """Check PID file and exit if another watchdog is already running.

    Returns True if lock acquired, False (and exits) if another instance holds it.
    Also cleans up stale PID files from crashed watchdogs.
    """
    if WATCHDOG_PID_FILE.exists():
        try:
            old_pid = int(WATCHDOG_PID_FILE.read_text().strip())
            if old_pid == os.getpid():
                # launch.sh wrote our PID before we started — that's us
                return True
            # Check if process is alive by sending signal 0
            os.kill(old_pid, 0)
            logger.error("Another watchdog is already running (PID %d) — exiting", old_pid)
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            # Stale PID file from crashed watchdog — clean it up
            logger.info("Cleaning stale watchdog PID file (old PID dead)")
            WATCHDOG_PID_FILE.unlink(missing_ok=True)
    return True


def main() -> None:
    if not WATCHDOG_ENABLED:
        logger.info("MLX Watchdog disabled via MLX_WATCHDOG_ENABLED=false — exiting")
        sys.exit(0)

    _acquire_singleton_lock()

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    init_components()
    write_pid_file()

    logger.info(
        "MLX Watchdog started — monitoring proxy :%d, mlx_lm :%d, mlx_vlm :%d",
        PROXY_PORT,
        LM_PORT,
        VLM_PORT,
    )
    logger.info(
        "Check interval: %ds, recovery threshold: %d, max attempts: %d",
        CHECK_INTERVAL,
        RECOVERY_THRESHOLD,
        MAX_RECOVERY_ATTEMPTS,
    )

    channels = []
    if TELEGRAM_BOT_TOKEN:
        channels.append("Telegram")
    if PUSHOVER_TOKEN and PUSHOVER_USER:
        channels.append("Pushover")
    if SLACK_WEBHOOK_URL:
        channels.append("Slack")
    if WEBHOOK_URL:
        channels.append("Webhook")
    if channels:
        logger.info("Notification channels: %s", ", ".join(channels))
    else:
        logger.warning(
            "No notification channels configured — set TELEGRAM_BOT_TOKEN, PUSHOVER_TOKEN, etc."
        )

    send_notification(
        "STARTED",
        f"MLX Watchdog started — monitoring proxy :{PROXY_PORT}, mlx_lm :{LM_PORT}, mlx_vlm :{VLM_PORT}. Channels: {', '.join(channels) if channels else 'none configured'}",
    )

    while True:
        try:
            # Zombie check runs first: a zombie server occupies the port and
            # prevents the proxy from recovering it on demand. Kill zombies
            # before the standard health checks so failure counters reflect
            # the state after cleanup, not before.
            check_server_zombies()
            run_health_checks()
        except Exception as e:
            logger.error("Health check loop error: %s", e)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
