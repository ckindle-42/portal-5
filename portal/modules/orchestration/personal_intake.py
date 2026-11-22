"""Write one personal task row. The runner is what later executes it."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from portal.modules.orchestration.personal_policy import refusal_reason
from portal.modules.orchestration.personal_store import PersonalStore

USAGE = "Usage: /jarvis do <text>"
SCHEDULE_USAGE = "Usage: /jarvis do at <UTC ISO-8601 time> <text>"
_SCHEDULED = re.compile(r"^at\s+(\S+)\s+(.+)$", re.IGNORECASE)


_REPO_ENV = Path(__file__).resolve().parents[3] / ".env"


def _env_file_value(name: str) -> str:
    """The first ``name=`` line of the repo ``.env``. Read-only, never executed."""
    if not _REPO_ENV.is_file():
        return ""
    for raw in _REPO_ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(f"{name}="):
            return line.partition("=")[2].strip().strip("\"'")
    return ""


def allowlisted_user_ids() -> set[int]:
    """The Telegram control allowlist. An empty list admits nobody."""
    # An explicitly empty env value stays fail-closed; only an absent key reads .env.
    raw = os.environ.get("TELEGRAM_USER_IDS")
    if raw is None:
        raw = _env_file_value("TELEGRAM_USER_IDS")
    return {int(uid.strip()) for uid in raw.split(",") if uid.strip().isdigit()}


def user_may_submit(user_id: int) -> bool:
    allowed = allowlisted_user_ids()
    return bool(allowed) and user_id in allowed


def enqueue_personal(
    root: Path, source: str, user_id: str, text: str, not_before: datetime | None = None
) -> str:
    """Insert a queued row and return its id. Empty or refused text is refused."""
    reason = refusal_reason(text)
    if reason is not None:
        raise ValueError(f"refused: {reason}. Nothing was queued.")
    return PersonalStore(root).add(source, user_id, text, not_before).id


def personal_queue_note(root: Path, task_id: str) -> str:
    """Where a just-queued task sits: the operator sees acceptance and position at once."""
    position = PersonalStore(root).live_position(task_id)
    return f"Queue position: {position}" if position else ""


def telegram_do(root: Path, user_id: int, args: str) -> tuple[str, str | None]:
    """Bot reply for ``/jarvis do``, plus the new task id when one was queued."""
    if not args.strip():
        return USAGE, None
    request = args.strip()
    not_before = None
    scheduled = _SCHEDULED.fullmatch(request)
    if request.lower().startswith("at "):
        if scheduled is None:
            return SCHEDULE_USAGE, None
        try:
            not_before = datetime.fromisoformat(scheduled.group(1).replace("Z", "+00:00"))
        except ValueError:
            return SCHEDULE_USAGE, None
        if not_before.tzinfo is None or not_before.utcoffset() is None:
            return SCHEDULE_USAGE, None
        request = scheduled.group(2).strip()
    if not request:
        return (SCHEDULE_USAGE if not_before is not None else USAGE), None
    try:
        task_id = enqueue_personal(root, "telegram", str(user_id), request, not_before)
    except ValueError as exc:
        return str(exc), None
    return f"queued {task_id}", task_id


def telegram_do_reply(root: Path, user_id: int, args: str) -> str:
    """Immediate bot reply for ``/jarvis do``. No row when the text is empty or refused."""
    return telegram_do(root, user_id, args)[0]
