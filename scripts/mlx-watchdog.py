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
    """Check if a component is responding on its port."""
    try:
        r = httpx.get(f"http://127.0.0.1:{state.port}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def run_health_checks() -> None:
    """Check all components and track failures."""
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
                send_notification(
                    "DOWN",
                    f"{state.name} is not responding on :{state.port}",
                )

            # Attempt recovery after threshold
            if state.consecutive_failures >= RECOVERY_THRESHOLD:
                attempt_recovery(name, state)


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
    """Kill hung proxy and restart it."""
    # Kill existing proxy
    if PROXY_PID_FILE.exists():
        try:
            pid = int(PROXY_PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGKILL)
            logger.info("Killed stale proxy PID %d", pid)
        except (ProcessLookupError, ValueError):
            pass
        PROXY_PID_FILE.unlink(missing_ok=True)

    # Also kill anything on the port
    result = subprocess.run(
        ["lsof", "-ti", f":{PROXY_PORT}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    for pid in result.stdout.strip().split("\n"):
        if pid:
            try:
                os.kill(int(pid), signal.SIGKILL)
                logger.info("Killed process %d on port %d", int(pid), PROXY_PORT)
            except ProcessLookupError:
                pass

    time.sleep(2)

    # Restart proxy
    script_dir = Path(__file__).parent
    proxy_script = script_dir / "mlx-proxy.py"
    if not proxy_script.exists():
        raise FileNotFoundError(f"mlx-proxy.py not found at {proxy_script}")

    subprocess.Popen(
        ["python3", str(proxy_script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("Restarted MLX proxy")

    # Wait for it to come up
    time.sleep(5)
    state = COMPONENTS["proxy"]
    if check_component(state):
        state.healthy = True
        state.consecutive_failures = 0
        state.recovery_attempts = 0
        send_notification("RECOVERED", f"{state.name} recovered on :{state.port}")
    else:
        raise RuntimeError("Proxy did not come up after restart")


def recover_server(stype: str, port: int) -> None:
    """Kill and restart mlx_lm or mlx_vlm server.

    Kills ALL processes matching the server module name (not just the port listener)
    to prevent zombie children from contending for Metal GPU resources.
    """
    module_name = f"mlx_{stype}.server"

    # Kill by process name — catches zombies that aren't listening on the port
    result = subprocess.run(
        ["pgrep", "-f", module_name],
        capture_output=True,
        text=True,
    )
    for pid in result.stdout.strip().split("\n"):
        if pid:
            try:
                os.kill(int(pid), signal.SIGKILL)
                logger.info("Killed %s process %d (by name)", module_name, int(pid))
            except ProcessLookupError:
                pass

    # Also kill anything still on the port (belt-and-suspenders)
    result = subprocess.run(
        ["lsof", "-ti", f":{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    for pid in result.stdout.strip().split("\n"):
        if pid:
            try:
                os.kill(int(pid), signal.SIGKILL)
                logger.info("Killed %s process %d on port %d", stype, int(pid), port)
            except ProcessLookupError:
                pass

    time.sleep(2)

    # Restart server
    subprocess.Popen(
        ["python3", "-m", f"mlx_{stype}.server", "--port", str(port), "--host", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("Restarted mlx_%s server on :%d", stype, port)

    # Wait for it to come up
    for _ in range(30):
        time.sleep(2)
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
            if r.status_code == 200:
                name = "mlx_lm server" if stype == "lm" else "mlx_vlm server"
                state_key = "mlx_lm" if stype == "lm" else "mlx_vlm"
                COMPONENTS[state_key].healthy = True
                COMPONENTS[state_key].consecutive_failures = 0
                COMPONENTS[state_key].recovery_attempts = 0
                send_notification("RECOVERED", f"{name} recovered on :{port}")
                return
        except Exception:
            pass

    raise RuntimeError(f"mlx_{stype} did not come up on :{port}")


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
            run_health_checks()
        except Exception as e:
            logger.error("Health check loop error: %s", e)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
