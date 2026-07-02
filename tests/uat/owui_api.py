"""Portal 5 UAT — OWUI REST helpers, chat archival, response retrieval.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase B). owui_get_last_response and _wait_for_response_arrival are
co-located here so unit-test monkeypatching of
tests.uat.owui_api.owui_get_last_response takes effect.
"""

from __future__ import annotations

import asyncio
import sys
import time
import uuid

import httpx

from tests.uat import state
from tests.uat.config import (
    ADMIN_EMAIL,
    ADMIN_PASS,
    OPENWEBUI_URL,
    POST_STREAM_API_WAIT_S,
)

# OWUI API helpers
# ---------------------------------------------------------------------------


def owui_token() -> str:
    r = httpx.post(
        f"{OPENWEBUI_URL}/api/v1/auths/signin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=10,
    )
    return r.json().get("token", "")


def owui_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def owui_create_chat(token: str, model_slug: str, title: str) -> tuple[str, str]:
    chat_id = str(uuid.uuid4())
    payload = {
        "chat": {
            "id": chat_id,
            "title": title,
            "models": [model_slug],
            "messages": [],
            "history": {"messages": {}, "currentId": None},
            "tags": [],
            "params": {},
            "timestamp": int(time.time()),
        }
    }
    r = httpx.post(
        f"{OPENWEBUI_URL}/api/v1/chats/new",
        json=payload,
        headers=owui_headers(token),
        timeout=10,
    )
    returned_id = r.json().get("id", chat_id)
    state._run_chat_ids.append(returned_id)
    return returned_id, f"{OPENWEBUI_URL}/c/{returned_id}"


def owui_rename_chat(token: str, chat_id: str, title: str) -> None:
    httpx.post(
        f"{OPENWEBUI_URL}/api/v1/chats/{chat_id}",
        json={"chat": {"title": title}},
        headers=owui_headers(token),
        timeout=10,
    )


def _owui_list_folders(token: str) -> list[dict]:
    r = httpx.get(
        f"{OPENWEBUI_URL}/api/v1/folders/",
        headers=owui_headers(token),
        timeout=30,
    )
    if r.status_code == 200:
        try:
            return r.json()
        except Exception:
            pass
    return []


def owui_get_or_create_folder(token: str, name: str, parent_id: str | None = None) -> str | None:
    """Return folder ID for `name` under `parent_id` (root if None), creating if absent."""
    folders = _owui_list_folders(token)
    for folder in folders:
        if folder.get("name") == name and folder.get("parent_id") == parent_id:
            return folder.get("id")

    r = httpx.post(
        f"{OPENWEBUI_URL}/api/v1/folders/",
        json={"name": name, "parent_id": parent_id},
        headers=owui_headers(token),
        timeout=10,
    )
    if r.status_code == 200:
        return r.json().get("id")

    # "already exists" race — re-fetch
    if r.status_code == 400 and "already exists" in r.text:
        for folder in _owui_list_folders(token):
            if folder.get("name") == name and folder.get("parent_id") == parent_id:
                return folder.get("id")

    return None


def owui_assign_chat_folder(token: str, chat_id: str, folder_id: str) -> None:
    """Move a chat into the given folder."""
    try:
        httpx.post(
            f"{OPENWEBUI_URL}/api/v1/chats/{chat_id}/folder",
            json={"folder_id": folder_id},
            headers=owui_headers(token),
            timeout=10,
        )
    except Exception:
        pass


def _archive_run_chats(run_date: str, quiet: bool = False) -> None:
    """Move all chats from this run into UAT/{run_date}. Called at end-of-run and on SIGINT."""
    if not state._run_chat_ids:
        return
    tok = state._archive_token
    fid = state._run_folder_id
    if not tok or not fid:
        if not quiet:
            print(
                f"\n  WARNING: UAT folder unavailable — {len(state._run_chat_ids)} chats remain in root"
            )
        return
    moved = 0
    for cid in state._run_chat_ids:
        try:
            owui_assign_chat_folder(tok, cid, fid)
            moved += 1
        except Exception:
            pass
    if not quiet:
        print(f"\n  Archived {moved}/{len(state._run_chat_ids)} chats → UAT/{run_date}")


def _install_archival_signal_handler(run_date: str) -> None:
    """Install SIGINT handler that archives chats before exiting."""
    import signal

    def _handler(signum, frame):
        print("\n  [interrupted] archiving chats before exit …")
        _archive_run_chats(run_date, quiet=False)
        sys.exit(130)

    signal.signal(signal.SIGINT, _handler)


def owui_migrate_loose_uat_chats(token: str, root_folder_id: str) -> int:
    """Move any root-level UAT chats (no folder_id) into root_folder_id.

    Returns the number of chats migrated.
    """
    moved = 0
    try:
        r = httpx.get(
            f"{OPENWEBUI_URL}/api/v1/chats/",
            headers=owui_headers(token),
            timeout=15,
        )
        if r.status_code != 200:
            return 0
        for chat in r.json():
            chat_id = chat.get("id", "")
            title = chat.get("title", "")
            # Full detail needed to check folder_id
            r2 = httpx.get(
                f"{OPENWEBUI_URL}/api/v1/chats/{chat_id}",
                headers=owui_headers(token),
                timeout=10,
            )
            if r2.status_code != 200:
                continue
            detail = r2.json()
            if detail.get("folder_id"):
                continue  # already in a folder
            if "UAT:" in title:
                owui_assign_chat_folder(token, chat_id, root_folder_id)
                moved += 1
    except Exception as e:
        print(f"  WARNING: migrate error — {e}")
    return moved


def owui_get_last_response(token: str, chat_id: str, min_messages: int = 1) -> str:
    """Fetch the last assistant response from OWUI API — avoids Playwright truncation.

    For thinking models (Qwen3/AEON), OWUI only commits an assistant message when
    either streaming ends OR a new user message arrives in the chat. The in-flight
    message is always empty from the API's perspective. This function returns the
    last NON-EMPTY assistant message so that a committed partial response from a
    previous attempt is found as soon as the next attempt's send triggers a commit.

    OWUI embeds reasoning content inline in the content field as:
      <details type="reasoning" done="true" duration="N">...</details>[actual response]
    No separate reasoning field exists in the chat history API.

    min_messages: minimum number of non-empty assistant messages required before
    returning. Use min_messages=2 for multi-turn turn-2 detection to prevent
    turn-1's committed response from satisfying the completion signal prematurely.
    Returns "" (falsy) until the required count of non-empty messages exists.
    """
    try:
        r = httpx.get(
            f"{OPENWEBUI_URL}/api/v1/chats/{chat_id}",
            headers={"Authorization": f"Bearer {token}", "Accept-Encoding": "identity"},
            timeout=10,
        )
        msgs = r.json().get("chat", {}).get("history", {}).get("messages", {})
        assistant_msgs = [m for m in msgs.values() if m.get("role") == "assistant"]
        if not assistant_msgs:
            return ""
        # Collect all non-empty assistant messages in order.
        non_empty: list[str] = []
        for msg in assistant_msgs:
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            if content:
                non_empty.append(content)
        # Guard: for turn-2 in multi-turn tests (min_messages=2), return "" until
        # the second non-empty assistant message has been committed by OWUI.
        # For thinking models, in-flight messages are always empty; the most-recently-
        # committed previous attempt's response is the useful signal (min_messages=1).
        if len(non_empty) < min_messages:
            return ""
        return non_empty[-1]
    except Exception:
        return ""


def owui_get_routed_model(token: str, chat_id: str) -> str:
    """Extract the model actually used from the last assistant message in OWUI chat history.

    Returns the model string or "" if unavailable. Provides diagnostic value
    equivalent to reading x-portal-route: the pipeline embeds the selected
    backend model in the message metadata stored by Open WebUI.
    """
    try:
        r = httpx.get(
            f"{OPENWEBUI_URL}/api/v1/chats/{chat_id}",
            headers={"Authorization": f"Bearer {token}", "Accept-Encoding": "identity"},
            timeout=10,
        )
        data = r.json()
        msgs = data.get("chat", {}).get("history", {}).get("messages", {})
        assistant_msgs = [m for m in msgs.values() if m.get("role") == "assistant"]
        if not assistant_msgs:
            return ""
        last = assistant_msgs[-1]
        # OWUI stores the model that generated the response in the message metadata
        model = last.get("model", "") or last.get("info", {}).get("model", "")
        return str(model) if model else ""
    except Exception:
        return ""


async def _wait_for_response_arrival(
    token: str,
    chat_id: str,
    max_wait: float = POST_STREAM_API_WAIT_S,
    min_messages: int = 1,
) -> str:
    """Poll OWUI API until response content stabilizes (log-driven, not timer-based).

    Polls every 2s and declares done when content length hasn't grown by more
    than 50 chars across 3 consecutive polls. This is content-driven completion:
    the API response log drives the exit decision rather than a fixed sleep.

    OWUI persists the assistant message at end-of-stream with a brief lag
    (typically <500ms, occasionally a few seconds under load).

    min_messages: passed to owui_get_last_response. Set to 2 for multi-turn
    turn-2 to require the second committed assistant response.

    Returns last stable content string, or "" on timeout.
    """
    if not token or not chat_id:
        await asyncio.sleep(2.0)
        return ""

    STABLE_COUNT = 2  # consecutive polls with no meaningful growth (OWUI commits atomically)
    STABLE_THRESHOLD = 50  # chars; ignores minor whitespace/punctuation flushes

    deadline = time.monotonic() + max_wait
    len_history: list[int] = []
    last_text = ""

    while time.monotonic() < deadline:
        text = owui_get_last_response(token, chat_id, min_messages=min_messages)
        cur_len = len(text)
        if text:
            last_text = text
        len_history.append(cur_len)
        if len(len_history) > STABLE_COUNT:
            len_history.pop(0)

        # Stable: enough samples, content exists, and max growth < threshold
        if (
            len(len_history) == STABLE_COUNT
            and cur_len > 0
            and max(len_history) - min(len_history) <= STABLE_THRESHOLD
        ):
            return text

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(2.0, remaining))

    return last_text
