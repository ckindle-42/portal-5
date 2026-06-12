"""Fire-and-forget bench notifications (Pushover / Telegram / Slack).

Extracted byte-for-byte from tests/benchmarks/bench_tps.py except the .env
path now resolves via PROJECT_ROOT (this file is one level deeper).
"""

import json
import os

from .config import PROJECT_ROOT


def _load_dotenv_for_notifications() -> None:
    """Pull notification env vars from .env without overwriting existing values."""
    # PROJECT_ROOT-based: this module is one level deeper than the original
    # bench_tps.py, so the old parent-counting expression would miss the repo root.
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    needed = {
        "PUSHOVER_API_TOKEN",
        "PUSHOVER_USER_KEY",
        "TELEGRAM_ALERT_BOT_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALERT_CHANNEL_ID",
        "TELEGRAM_USER_IDS",
        "SLACK_ALERT_WEBHOOK_URL",
    }
    try:
        for raw in env_file.read_text().splitlines():
            line = raw.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k in needed and k not in os.environ:
                os.environ[k] = v.strip().strip('"').strip("'")
    except Exception:
        pass


def _send_bench_notification(message: str, title: str = "Portal 5 Bench") -> None:
    """Fire-and-forget: send message to every configured notification channel."""
    import urllib.parse
    import urllib.request

    _load_dotenv_for_notifications()

    # Pushover
    token = os.environ.get("PUSHOVER_API_TOKEN", "")
    user = os.environ.get("PUSHOVER_USER_KEY", "")
    if token and user:
        try:
            data = urllib.parse.urlencode(
                {
                    "token": token,
                    "user": user,
                    "title": title,
                    "message": message[:512],
                }
            ).encode()
            urllib.request.urlopen(
                urllib.request.Request("https://api.pushover.net/1/messages.json", data=data),
                timeout=8,
            )
        except Exception:
            pass

    # Telegram
    bot_token = os.environ.get("TELEGRAM_ALERT_BOT_TOKEN") or os.environ.get(
        "TELEGRAM_BOT_TOKEN", ""
    )
    raw_ids = os.environ.get("TELEGRAM_ALERT_CHANNEL_ID") or os.environ.get("TELEGRAM_USER_IDS", "")
    chat_id = raw_ids.split(",")[0].strip() if raw_ids else ""
    if bot_token and chat_id:
        try:
            data = urllib.parse.urlencode(
                {
                    "chat_id": chat_id,
                    "text": f"*{title}*\n{message}",
                    "parse_mode": "Markdown",
                }
            ).encode()
            urllib.request.urlopen(
                urllib.request.Request(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage", data=data
                ),
                timeout=8,
            )
        except Exception:
            pass

    # Slack
    slack_url = os.environ.get("SLACK_ALERT_WEBHOOK_URL", "")
    if slack_url:
        try:
            data = json.dumps({"text": f"*{title}*\n{message}"}).encode()
            urllib.request.urlopen(
                urllib.request.Request(
                    slack_url, data=data, headers={"Content-Type": "application/json"}
                ),
                timeout=8,
            )
        except Exception:
            pass
