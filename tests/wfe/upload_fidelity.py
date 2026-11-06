"""Realuse pipeline turns mirror production: the Open WebUI RAG context (Portal
template) prepended, and the inlet filter's ``portal_attached_files`` field carried."""

from __future__ import annotations

import re
from pathlib import Path

from tests.wfe.owui_rag import copied_content, prefix_for, prepend_message, restore_message
from tests.wfe.realuse_paths import CHECKOUT, upload_tree_suffix

DOCUMENT_SUFFIXES = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv", ".md"}
SHAPE = "owui_rag_v0.12.5+portal_filter_v1"
#: The code sandbox's view of the uploads mount; the filter derives the same prefix.
UPLOADS_MOUNT = "/workspace/uploads"


def user_text(content) -> str:
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return str(content or "")


def _mentions(text: str, token: str) -> bool:
    """A name matches as a whole token. A sentence period may follow it; a further suffix may not."""
    boundary = r"(?:$|[^\w.-]|\.(?!\w))"
    return re.search(rf"(?<![\w.-]){re.escape(token)}{boundary}", text) is not None


def upload_items(task: dict) -> list[dict]:
    """Upload-tree fixtures in fixture order. Repo paths under ``fixtures/realuse_v1/`` are omitted."""
    items: list[dict] = []
    for rel in task.get("fixtures") or []:
        suffix = upload_tree_suffix(str(rel))
        if suffix is None:
            continue
        name = Path(suffix).name
        src = CHECKOUT / str(rel)
        items.append(
            {
                "id": suffix,
                "name": name,
                "path": src,
                "suffix": Path(name).suffix.lower(),
            }
        )
    return items


def _introduced(text: str, item: dict) -> bool:
    folder = str(Path(item["id"]).parent).replace("\\", "/")
    return _mentions(text, item["name"]) or item["id"] in text or f"{folder}/" in text


def introduced_documents(task: dict, turn_index: int, users: list[str]) -> list[dict]:
    """Document fixtures named by this turn or an earlier one. Images and code are not documents."""
    if turn_index < 0:
        return []
    seen = "\n".join(users[: turn_index + 1])
    return [
        item
        for item in upload_items(task)
        if item["suffix"] in DOCUMENT_SUFFIXES and _introduced(seen, item)
    ]


class TurnInjection:
    def __init__(
        self,
        prefix: str,
        file_ids: list[str],
        chunks: int,
        ranked_standin: bool,
        attachments: list[dict] | None = None,
    ) -> None:
        self.prefix = prefix
        self.file_ids = file_ids
        self.chunks = chunks
        self.ranked_standin = ranked_standin
        self.attachments = attachments or []


def attachment_item(item: dict) -> dict:
    """The inlet filter's carried shape for one fixture, with the staged path the
    fixture really has (``<root>/uploads/<id>`` mounted at /workspace/uploads)."""
    src = Path(item["path"])
    return {
        "id": item["id"],
        "name": item["name"],
        "type": "file",
        "size": src.stat().st_size if src.is_file() else None,
        "path": f"{UPLOADS_MOUNT}/{item['id']}",
    }


def attach_request_attachments(payload: dict, attachments: list | None) -> None:
    """Put the forwarded field on the pipeline body. An empty list omits the key."""
    if attachments:
        payload["portal_attached_files"] = attachments


def turn_injection(engine: str, task: dict, turn_index: int, users: list[str]) -> TurnInjection:
    """RAG prefix and forwarded attachments for one pipeline turn. Direct engines
    get neither."""
    if engine != "pipeline" or turn_index < 0 or turn_index >= len(users):
        return TurnInjection("", [], 0, False)
    items = introduced_documents(task, turn_index, users)
    prefix, file_ids, chunks, ranked = prefix_for(
        [(item["path"], item["suffix"], item["id"], item["name"]) for item in items],
        users[turn_index],
    )
    return TurnInjection(prefix, file_ids, chunks, ranked, [attachment_item(i) for i in items])


def rendered_user(engine: str, task: dict, turn_index: int) -> str:
    """The last user message after the prepend, for one scripted turn."""
    users = [user_text(turn.get("user")) for turn in task.get("turns") or []]
    injection = turn_injection(engine, task, turn_index, users)
    user = users[turn_index]
    if not injection.prefix:
        return user
    return f"{injection.prefix}\n{user}"


def apply_turn_prefix(
    messages: list, content, injection: TurnInjection, prior: tuple | None
) -> tuple | None:
    """Append one user turn. Drop the prefix from the previous user message, then prepend this one."""
    if prior is not None:
        index, prefix = prior
        restore_message(messages[index], prefix)
    messages.append({"role": "user", "content": copied_content(content)})
    if not injection.prefix:
        return None
    prepend_message(messages[-1], injection.prefix)
    return (len(messages) - 1, injection.prefix)


def delivery_record(turns: list, chunks: int, ranked_standin: bool) -> dict:
    return {
        "shape": SHAPE,
        "turns": turns,
        "chunks": chunks,
        "ranked_standin": ranked_standin,
    }


def stamp_upload_delivery(out: dict, turns: list, chunks: int, ranked_standin: bool) -> dict:
    """Record the RAG context this run prepended and return the result."""
    out["upload_delivery"] = delivery_record(turns, chunks, ranked_standin)
    return out


def row_instrument(base: dict, out: dict) -> dict:
    """Campaign fingerprint plus the RAG context this row's requests carried."""
    instrument = dict(base)
    delivered = out.get("upload_delivery")
    if delivered:
        instrument["upload"] = delivered
    return instrument
