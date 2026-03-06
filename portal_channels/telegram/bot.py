"""Portal 5.0 — Telegram Channel Adapter

Receives Telegram updates, forwards to Portal Pipeline, streams response back.
Thin adapter: no routing logic — all intelligence is in portal_pipeline/.
"""
from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from portal_channels.dispatcher import VALID_WORKSPACES, is_valid_workspace

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE = os.environ.get("TELEGRAM_DEFAULT_WORKSPACE", "auto")


def _get_token() -> str:
    """Read bot token from environment. Raises clear error if missing."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Get a token from @BotFather and add it to .env"
        )
    return token


def _allowed_users() -> set[int]:
    raw = os.environ.get("TELEGRAM_USER_IDS", "")
    return {int(uid.strip()) for uid in raw.split(",") if uid.strip().isdigit()}


def _is_allowed(user_id: int) -> bool:
    allowed = _allowed_users()
    return not allowed or user_id in allowed


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    await update.effective_message.reply_text(
        "🤖 Portal 5.0 — Local AI Assistant\n\n"
        "Send any message to chat.\n"
        "Commands:\n"
        "/workspace [name] — switch workspace\n"
        "  Available: auto, auto-coding, auto-security, auto-redteam,\n"
        "             auto-blueteam, auto-reasoning, auto-creative,\n"
        "             auto-research, auto-vision, auto-data\n"
        "/clear — clear conversation history\n"
        "/workspaces — list all available workspaces"
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    if context.user_data is not None:
        context.user_data.clear()
    await update.effective_message.reply_text("Conversation history cleared.")


async def list_workspaces(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    text = "Available workspaces:\n" + "\n".join(f"  • {ws}" for ws in sorted(VALID_WORKSPACES))
    await update.effective_message.reply_text(text)


async def set_workspace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    if context.user_data is None:
        return
    args = context.args
    if args:
        ws = args[0].lower().strip()
        if not is_valid_workspace(ws):
            await update.effective_message.reply_text(
                f"Unknown workspace: {ws!r}\n"
                f"Use /workspaces to see available options."
            )
            return
        context.user_data["workspace"] = ws
        await update.effective_message.reply_text(f"Workspace set to: {ws}")
    else:
        current = context.user_data.get("workspace", DEFAULT_WORKSPACE)
        await update.effective_message.reply_text(
            f"Current workspace: {current}\n"
            "Usage: /workspace <name>"
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    if not _is_allowed(update.effective_user.id):
        await update.effective_message.reply_text("Unauthorized.")
        return

    user_text = update.effective_message.text or ""
    if not user_text.strip():
        return

    if context.user_data is None:
        context.user_data = {}

    workspace = context.user_data.get("workspace", DEFAULT_WORKSPACE)

    # Bounded conversation history (20 messages = 10 turns)
    history: list[dict] = context.user_data.get("history", [])
    history.append({"role": "user", "content": user_text})
    if len(history) > 20:
        history = history[-20:]

    await update.effective_message.chat.send_action("typing")

    try:
        from portal_channels.dispatcher import call_pipeline_async
        reply = await call_pipeline_async(user_text, workspace, history=history[:-1])
    except Exception as e:
        logger.error("Pipeline error: %s", e)
        reply = f"⚠️ Pipeline error: {e}"

    history.append({"role": "assistant", "content": reply})
    context.user_data["history"] = history

    # Telegram 4096-char message limit
    for chunk in [reply[i : i + 4000] for i in range(0, len(reply), 4000)]:
        await update.effective_message.reply_text(chunk, parse_mode="Markdown")


def build_app() -> Application:
    """Build the Telegram Application. Reads TELEGRAM_BOT_TOKEN here, not at import."""
    token = _get_token()
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("workspace", set_workspace))
    app.add_handler(CommandHandler("workspaces", list_workspaces))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_app().run_polling()
