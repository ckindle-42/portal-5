"""Portal 5.0 — Slack Channel Adapter

Receives Slack events, forwards to Portal Pipeline, returns response.
Thin adapter: all routing intelligence lives in portal_pipeline/.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_bolt.app import App

logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://portal-pipeline:9099")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "portal-pipeline")
DEFAULT_WORKSPACE = os.environ.get("SLACK_DEFAULT_WORKSPACE", "auto")

slack_app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)


def _get_workspace_for_channel(channel_name: str) -> str:
    """Map channel names to workspaces."""
    channel_map = {
        "coding": "auto-coding",
        "security": "auto-security",
        "images": "auto-images",
        "creative": "auto-creative",
        "documents": "auto-documents",
        "video": "auto-video",
        "music": "auto-music",
        "research": "auto-research",
    }
    for key, ws in channel_map.items():
        if key in channel_name.lower():
            return ws
    return DEFAULT_WORKSPACE


@slack_app.event("app_mention")
def handle_mention(event: dict[str, Any], say: Any, client: Any) -> None:
    """Handle @bot mentions."""
    channel_id = event.get("channel", "")
    channel_info = client.conversations_info(channel=channel_id)
    channel_name = channel_info.get("channel", {}).get("name", "general")
    workspace = _get_workspace_for_channel(channel_name)

    user_text = event.get("text", "").strip()
    thread_ts = event.get("thread_ts", event.get("ts"))

    # Call Pipeline API
    payload = {
        "model": workspace,
        "messages": [{"role": "user", "content": user_text}],
        "stream": False,
    }

    try:
        import httpx
        with httpx.Client(timeout=120.0) as http_client:
            resp = http_client.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {PIPELINE_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
            say(text=reply, thread_ts=thread_ts)
    except Exception as e:
        logger.error("Pipeline error: %s", e)
        say(text=f"⚠️ Pipeline error: {e}", thread_ts=thread_ts)


@slack_app.event("message")
def handle_message(event: dict[str, Any], say: Any, client: Any) -> None:
    """Handle DMs (im channel type)."""
    if event.get("channel_type") != "im":
        return  # Only DMs, channel mentions handled above

    user_text = event.get("text", "").strip()
    workspace = DEFAULT_WORKSPACE

    payload = {
        "model": workspace,
        "messages": [{"role": "user", "content": user_text}],
        "stream": False,
    }

    try:
        with httpx.Client(timeout=120.0) as http_client:
            resp = http_client.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {PIPELINE_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
            say(text=reply)
    except Exception as e:
        logger.error("Pipeline error: %s", e)
        say(text=f"⚠️ Pipeline error: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    handler = SocketModeHandler(slack_app, SLACK_BOT_TOKEN)
    handler.start()
