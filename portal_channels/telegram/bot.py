"""Portal 5.0 — Telegram Channel Adapter

Receives Telegram updates, forwards to Portal Pipeline, streams response back.
Thin adapter: no routing logic here, all intelligence is in portal_pipeline/.
"""
from __future__ import annotations

import logging
import os

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://portal-pipeline:9099")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "portal-pipeline")
ALLOWED_USER_IDS_RAW = os.environ.get("TELEGRAM_USER_IDS", "")
ALLOWED_USER_IDS: set[int] = {
    int(uid.strip()) for uid in ALLOWED_USER_IDS_RAW.split(",") if uid.strip().isdigit()
}
DEFAULT_WORKSPACE = os.environ.get("TELEGRAM_DEFAULT_WORKSPACE", "auto")


def _is_allowed(user_id: int) -> bool:
    return not ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "� Portal 5.0 — Local AI Assistant\n\n"
        "Send any message to get started.\n"
        "Commands:\n"
        "/workspace [name] — switch workspace (auto, auto-coding, auto-security...)\n"
        "/clear — clear conversation history"
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.message.reply_text("Conversation history cleared.")


async def set_workspace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if args:
        ws = args[0].lower()
        context.user_data["workspace"] = ws
        await update.message.reply_text(f"Workspace set to: {ws}")
    else:
        current = context.user_data.get("workspace", DEFAULT_WORKSPACE)
        await update.message.reply_text(f"Current workspace: {current}\nUsage: /workspace [auto|auto-coding|auto-security|...]")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    if not _is_allowed(update.effective_user.id):
        await update.message.reply_text("Unauthorized.")
        return

    user_text = update.message.text or ""
    workspace = context.user_data.get("workspace", DEFAULT_WORKSPACE)

    # Build message history (last 10 turns)
    history: list[dict] = context.user_data.get("history", [])
    history.append({"role": "user", "content": user_text})
    if len(history) > 20:
        history = history[-20:]

    # Send typing indicator
    await update.message.chat.send_action("typing")

    # Call Pipeline API
    payload = {
        "model": workspace,
        "messages": history,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {PIPELINE_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("Pipeline error: %s", e)
        reply = f"⚠️ Pipeline error: {e}"

    # Store assistant reply in history
    history.append({"role": "assistant", "content": reply})
    context.user_data["history"] = history

    # Telegram has a 4096 char limit
    if len(reply) > 4000:
        for chunk in [reply[i:i+4000] for i in range(0, len(reply), 4000)]:
            await update.message.reply_text(chunk, parse_mode="Markdown")
    else:
        await update.message.reply_text(reply, parse_mode="Markdown")


def build_app() -> Application:
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("workspace", set_workspace))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    bot_app = build_app()
    bot_app.run_polling()
