"""Write one personal task row. The runner is what later executes it."""

from __future__ import annotations

import os
from pathlib import Path

from portal.modules.orchestration.personal_store import PersonalStore

USAGE = "Usage: /jarvis do <text>"


def allowlisted_user_ids() -> set[int]:
    """The Telegram control allowlist. An empty list admits nobody."""
    raw = os.environ.get("TELEGRAM_USER_IDS", "")
    return {int(uid.strip()) for uid in raw.split(",") if uid.strip().isdigit()}


def user_may_submit(user_id: int) -> bool:
    allowed = allowlisted_user_ids()
    return bool(allowed) and user_id in allowed


def enqueue_personal(root: Path, source: str, user_id: str, text: str) -> str:
    """Insert a queued row and return its id. Empty text is refused."""
    return PersonalStore(root).add(source, user_id, text).id


def telegram_do_reply(root: Path, user_id: int, args: str) -> str:
    """Immediate bot reply for ``/jarvis do``. No row when the text is empty."""
    if not args.strip():
        return USAGE
    task_id = enqueue_personal(root, "telegram", str(user_id), args)
    return f"queued {task_id}"
