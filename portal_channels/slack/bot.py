"""Portal 5.2.1 — Slack Channel Adapter

Listens via Socket Mode (no public webhook required).
Handles @mentions in channels and direct messages.
Thin adapter — all intelligence is in portal_pipeline/.

Required environment variables:
  SLACK_BOT_TOKEN      xoxb-... (Bot User OAuth Token)
  SLACK_APP_TOKEN      xapp-... (App-Level Token for Socket Mode)
  SLACK_SIGNING_SECRET Signing secret from app settings

Optional:
  PIPELINE_URL         default: http://portal-pipeline:9099
  PIPELINE_API_KEY     default: value from PIPELINE_API_KEY env
  SLACK_DEFAULT_WORKSPACE  default: auto
"""

from __future__ import annotations

import logging
import os
from typing import Any

from portal_channels.dispatcher import call_pipeline_sync

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE = os.environ.get("SLACK_DEFAULT_WORKSPACE", "auto")

# Channel name → workspace routing (matches current 13 canonical workspace IDs)
CHANNEL_WORKSPACE_MAP: dict[str, str] = {
    "coding": "auto-coding",
    "security": "auto-security",
    "redteam": "auto-redteam",
    "blueteam": "auto-blueteam",
    "images": "auto-vision",  # was "auto-images" (invalid)
    "vision": "auto-vision",
    "creative": "auto-creative",
    "documents": "auto-documents",
    "video": "auto-video",
    "music": "auto-music",
    "research": "auto-research",
    "reasoning": "auto-reasoning",
    "data": "auto-data",
}


def _get_tokens() -> tuple[str, str, str]:
    """Read Slack tokens from environment. Raises clear error if missing."""
    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    app_token = os.environ.get("SLACK_APP_TOKEN", "")
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")

    missing = []
    if not bot_token:
        missing.append("SLACK_BOT_TOKEN (xoxb-...)")
    if not app_token:
        missing.append("SLACK_APP_TOKEN (xapp-...)")
    if not signing_secret:
        missing.append("SLACK_SIGNING_SECRET (from app settings → Basic Information)")

    if missing:
        raise RuntimeError(
            "Slack credentials missing from .env:\n"
            + "\n".join(f"  {m}" for m in missing)
            + "\n\nSee: https://api.slack.com/apps → create app → Socket Mode"
        )
    return bot_token, app_token, signing_secret


def _workspace_for_channel(channel_name: str) -> str:
    for keyword, workspace in CHANNEL_WORKSPACE_MAP.items():
        if keyword in channel_name.lower():
            return workspace
    return DEFAULT_WORKSPACE


def _call_pipeline(text: str, workspace: str) -> str:
    """Delegate to shared dispatcher."""
    return call_pipeline_sync(text, workspace)


def build_app():
    """Build the Slack App and SocketModeHandler. Reads tokens here, not at import."""
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    bot_token, app_token, signing_secret = _get_tokens()
    slack_app = App(token=bot_token, signing_secret=signing_secret)

    @slack_app.event("app_mention")
    def handle_mention(event: dict[str, Any], say: Any, client: Any) -> None:
        """Handle @portal mentions in channels."""
        channel_id = event.get("channel", "")
        channel_name = ""
        try:
            info = client.conversations_info(channel=channel_id)
            channel_name = info.get("channel", {}).get("name", "")
        except Exception:
            pass

        workspace = _workspace_for_channel(channel_name)
        user_text = event.get("text", "").strip()
        thread_ts = event.get("thread_ts", event.get("ts"))

        try:
            reply = _call_pipeline(user_text, workspace)
            say(text=reply, thread_ts=thread_ts)
        except Exception as e:
            logger.error("Pipeline error: %s", e)
            say(text=f"⚠️ Pipeline error: {e}", thread_ts=thread_ts)

    @slack_app.event("message")
    def handle_dm(event: dict[str, Any], say: Any) -> None:
        """Handle direct messages to the bot."""
        if event.get("channel_type") != "im":
            return
        if event.get("subtype") in (
            "bot_message",
            "message_changed",
            "message_deleted",
            "message_replied",
        ):
            return  # skip bot messages, edits, and threaded replies

        user_text = event.get("text", "").strip()
        if not user_text:
            return

        try:
            reply = _call_pipeline(user_text, DEFAULT_WORKSPACE)
            say(text=reply)
        except Exception as e:
            logger.error("Pipeline error: %s", e)
            say(text=f"⚠️ Pipeline error: {e}")

    # SocketModeHandler uses SLACK_APP_TOKEN (xapp-...), NOT the bot token
    handler = SocketModeHandler(slack_app, app_token)
    return slack_app, handler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _, handler = build_app()
    handler.start()
