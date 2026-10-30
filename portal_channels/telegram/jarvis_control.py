"""Jarvis control verbs for the Telegram bot — deterministic parse, requests only.

The bot never executes: `/jarvis` and `jv:` buttons write ``control_requests``
rows to the shared arm store; the host queue runner executes and replies through
the outbox. Control fails closed: a non-empty TELEGRAM_USER_IDS containing the
user is required (chat keeps its empty-allowlist-permits-all behaviour).
"""

from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from portal.modules.orchestration.control import (
    DESTRUCTIVE_VERBS,
    NEEDS_JOB_VERBS,
    VERB_NAMES,
    load_queue_policy,
    telegram_control_enabled,
)
from portal_channels.telegram.arm_bridge import ArmTelegramStore, default_arm_telegram_path

HELP_TEXT = (
    "Jarvis control verbs:\n"
    "/jarvis status — queue ledger at a glance\n"
    "/jarvis digest — one-screen queue digest\n"
    "/jarvis pause — runner stops picking new jobs\n"
    "/jarvis resume — runner picks jobs again\n"
    "/jarvis requeue <job> — requeue a blocked or done job\n"
    "/jarvis cancel <job> — cancel a queued job (confirm)\n"
    "/jarvis canary <job> — last canary SETUP/MODEL counts\n"
    "/jarvis held — list held escalations\n"
    "/jarvis merge <job> — merge a held escalation (confirm)\n"
    "/jarvis keep <job> — keep a held escalation unmerged\n"
    "/jarvis escalate <job> — send a blocked job to a cloud lane\n"
    "/jarvis help — this text"
)


def parse(text: str) -> tuple[str, str]:
    """'/jarvis verb args…' → (verb, args); '/jarvis' alone → ('help', '')."""
    parts = text.split()
    if parts and parts[0].startswith("/"):
        parts = parts[1:]
    if not parts:
        return "help", ""
    return parts[0].lower(), " ".join(parts[1:]).strip()


def control_enabled() -> bool:
    return telegram_control_enabled(load_queue_policy())


def _allowed() -> set[int]:
    from portal_channels.telegram.bot import _allowed_users

    return _allowed_users()


def _store() -> ArmTelegramStore:
    return ArmTelegramStore(default_arm_telegram_path())


async def handle_jarvis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    if not control_enabled():
        await message.reply_text("Jarvis control is not enabled.")
        return
    allowed = _allowed()
    if not allowed:
        await message.reply_text("Jarvis control requires a non-empty TELEGRAM_USER_IDS allowlist.")
        return
    if user is None or user.id not in allowed:
        await message.reply_text("Unauthorized.")
        return
    verb, args = parse(message.text or "")
    if verb == "help":
        await message.reply_text(HELP_TEXT)
        return
    store = _store()
    if verb not in VERB_NAMES:
        store.add_control_request(user.id, verb, args, status="refused", result="unknown verb")
        await message.reply_text(f"Unknown verb: {verb}\n\n{HELP_TEXT}")
        return
    if verb in NEEDS_JOB_VERBS and not args:
        store.add_control_request(user.id, verb, args, status="refused", result="missing <job>")
        await message.reply_text(f"Usage: /jarvis {verb} <job>")
        return
    if verb in DESTRUCTIVE_VERBS:
        request_id = store.add_control_request(user.id, verb, args, status="pending")
        await message.reply_text(
            f"{verb} {args}: confirm?",
            reply_markup=_confirm_keyboard(request_id),
        )
        return
    request_id = store.add_control_request(user.id, verb, args)
    await message.reply_text(f"Queued {verb}" + (f" {args}" if args else ""))


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    data = query.data if query else None
    if not query or not user or not isinstance(data, str):
        return
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "jv" or parts[1] not in {"ask", "confirm", "abort"}:
        await query.answer("Invalid Jarvis control button.", show_alert=True)
        return
    if not control_enabled():
        await query.answer("Jarvis control is not enabled.", show_alert=True)
        return
    allowed = _allowed()
    if not allowed or user.id not in allowed:
        await query.answer("Unauthorized.", show_alert=True)
        return
    store = _store()
    request = store.control_request(parts[2])
    if request is None:
        await query.answer("Unknown Jarvis control request.", show_alert=True)
        return
    action = parts[1]
    if action == "ask" and request.verb in DESTRUCTIVE_VERBS:
        await query.answer(f"Confirm {request.verb} {request.args}?")
        if query.message:
            await query.edit_message_reply_markup(reply_markup=_confirm_keyboard(request.id))
        return
    decided = store.decide_control(request.id, action, user.id, allowed)
    if decided is None:
        await query.answer(
            "This request is closed, expired, or you are not authorized.", show_alert=True
        )
        return
    label = decided.verb + (f" {decided.args}" if decided.args else "")
    await query.answer(f"{label}: {decided.status}.")
    if query.message:
        text = str(query.message.text or "")
        await query.edit_message_text(f"{text}\n\n{label}: {decided.status}.")


def notice_keyboard(store: ArmTelegramStore, task_id: str) -> InlineKeyboardMarkup | None:
    """Buttons for a notice's pending control rows, newest per verb."""
    pending = store.pending_control_requests(task_id)
    if not pending:
        return None
    rows = [
        [InlineKeyboardButton(request.verb.capitalize(), callback_data=_callback_for(request))]
        for request in pending
    ]
    return InlineKeyboardMarkup(rows)


def _callback_for(request: Any) -> str:
    action = "ask" if request.verb in DESTRUCTIVE_VERBS else "confirm"
    return f"jv:{action}:{request.id}"[:64]


def _confirm_keyboard(request_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=f"jv:confirm:{request_id}"),
                InlineKeyboardButton("Abort", callback_data=f"jv:abort:{request_id}"),
            ]
        ]
    )
