"""Native Open WebUI chat-turn client for QAT."""

from __future__ import annotations

import base64
import mimetypes
import re
import struct
import time
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from .artifacts import raw_tool_error_leak
from .config import Settings

POLL_INTERVAL_S = 2.0
ARTIFACT_URL_RE = re.compile(r"/api/v1/files/[0-9a-fA-F-]{8,}/content/\S+")
TERMINAL_STATES = {"completed", "complete", "done", "success"}
_RED = (255, 0, 0)


def red_square_png(side: int = 64) -> bytes:
    raw = b"".join(b"\x00" + bytes(_RED) * side for _ in range(side))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def vision_message_content(prompt: str, png: bytes) -> list[dict[str, Any]]:
    url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": url}},
    ]


@dataclass
class TurnOutcome:
    chat_id: str
    text: str
    done: bool
    served_model: str
    artifact_urls: tuple[str, ...]
    leak_marker: str | None
    trace: dict[str, object]
    tool_calls: tuple[dict[str, Any], ...] = ()


class OWUIClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport
        self._turns: dict[str, dict[str, str]] = {}
        self._pending_message_ids: dict[str, str] = {}

    def _client(self, timeout_s: float | None = None) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=timeout_s)

    def signin(self) -> str:
        if self.settings.owui_api_key:
            return self.settings.owui_api_key
        with self._client(30.0) as client:
            r = client.post(
                f"{self.settings.owui_url}/api/v1/auths/signin",
                json={"email": self.settings.owui_user, "password": self.settings.owui_pass},
            )
        if r.status_code != 200:
            raise RuntimeError(f"OWUI signin failed: HTTP {r.status_code}")
        return str(r.json().get("token", ""))

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def create_chat(
        self,
        token: str,
        model_slug: str,
        title: str,
        prompt: str = "",
        deadline: float | None = None,
    ) -> str:
        user_id, message_id = str(uuid.uuid4()), str(uuid.uuid4())
        session_id = f"portal-qat-{uuid.uuid4()}"
        now = int(time.time())
        payload = {
            "chat": {
                "title": title,
                "models": [model_slug],
                "history": {
                    "currentId": message_id,
                    "messages": {
                        user_id: {
                            "id": user_id,
                            "role": "user",
                            "content": prompt,
                            "timestamp": now,
                            "models": [model_slug],
                            "childrenIds": [message_id],
                        },
                        message_id: {
                            "id": message_id,
                            "role": "assistant",
                            "content": "",
                            "parentId": user_id,
                            "childrenIds": [],
                            "model": model_slug,
                            "modelName": model_slug,
                            "modelIdx": 0,
                            "done": False,
                            "timestamp": now + 1,
                        },
                    },
                },
            }
        }
        with self._client(_remaining(deadline) if deadline else 30.0) as client:
            r = client.post(
                f"{self.settings.owui_url}/api/v1/chats/new",
                json=payload,
                headers=self._headers(token),
            )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"chats/new failed: HTTP {r.status_code}")
        body = r.json()
        chat_id = body.get("id") if isinstance(body, dict) else None
        if not chat_id:
            raise RuntimeError("chats/new response is missing outer id")
        chat_id = str(chat_id)
        self._turns[chat_id] = {
            "user_id": user_id,
            "message_id": message_id,
            "session_id": session_id,
        }
        return chat_id

    def send_turn(
        self,
        token: str,
        chat_id: str,
        model_slug: str,
        prompt: str,
        tool_ids: tuple[str, ...] = (),
        function_calling: bool = False,
        prior_messages: list[dict[str, Any]] | None = None,
        files: list[dict[str, Any]] | None = None,
        image_png: bytes | None = None,
        deadline: float | None = None,
    ) -> httpx.Response:
        turn = self._turns.get(chat_id)
        if turn is None:
            raise RuntimeError(f"unknown QAT chat {chat_id}")
        if self._pending_message_ids.get(chat_id):
            turn = {**turn, "user_id": str(uuid.uuid4()), "message_id": str(uuid.uuid4())}
            self._turns[chat_id] = turn
        message_id = turn["message_id"]
        content: str | list[dict[str, Any]] = prompt
        if image_png is not None:
            content = vision_message_content(prompt, image_png)
        body: dict[str, Any] = {
            "model": model_slug,
            "messages": [*(prior_messages or []), {"role": "user", "content": content}],
            "stream": True,
            "id": message_id,
            "chat_id": chat_id,
            "session_id": turn["session_id"],
            "features": {
                "web_search": False,
                "code_interpreter": False,
                "image_generation": False,
                "memory": False,
            },
            "tool_ids": list(tool_ids),
            "params": {"function_calling": function_calling},
        }
        if files is not None:
            body["files"] = files
        remaining = _remaining(deadline)
        with self._client(remaining) as client:
            response = client.post(
                f"{self.settings.owui_url}/api/chat/completions",
                json=body,
                headers=self._headers(token),
            )
        self._pending_message_ids[chat_id] = message_id
        return response

    def upload_attachment(
        self, token: str, relative_path: str, deadline: float | None = None
    ) -> dict[str, str]:
        path = Path(relative_path)
        if not path.is_absolute():
            path = self.settings.repo_root / path
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as stream, self._client(_remaining(deadline)) as client:
            response = client.post(
                f"{self.settings.owui_url}/api/v1/files/",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                files={"file": (path.name, stream, content_type)},
            )
        if not response.is_success:
            raise RuntimeError(f"OWUI file upload failed: HTTP {response.status_code}")
        body = response.json()
        file_id = body.get("id") if isinstance(body, dict) else None
        if not file_id:
            raise RuntimeError("OWUI file upload response is missing id")
        return {"type": "file", "id": str(file_id)}

    def task_status(
        self,
        token: str,
        chat_id: str,
        client: httpx.Client | None = None,
        deadline: float | None = None,
    ) -> dict:
        if client is None:
            with self._client(10.0) as owned:
                return self.task_status(token, chat_id, owned, deadline)
        r = client.get(
            f"{self.settings.owui_url}/api/tasks/chat/{chat_id}",
            headers=self._headers(token),
            timeout=_remaining(deadline),
        )
        return r.json() if r.status_code == 200 else {}

    def chat_detail(
        self,
        token: str,
        chat_id: str,
        client: httpx.Client | None = None,
        deadline: float | None = None,
    ) -> dict:
        if client is None:
            with self._client(10.0) as owned:
                return self.chat_detail(token, chat_id, owned, deadline)
        r = client.get(
            f"{self.settings.owui_url}/api/v1/chats/{chat_id}",
            headers={**self._headers(token), "Accept-Encoding": "identity"},
            timeout=_remaining(deadline),
        )
        return r.json() if r.status_code == 200 else {}

    def download_artifact(self, token: str, url: str) -> bytes:
        target = url if urlsplit(url).scheme else f"{self.settings.owui_url}{url}"
        headers = self._headers(token) if _same_origin(target, self.settings.owui_url) else {}
        try:
            with self._client(30.0) as client:
                r = client.get(target, headers=headers)
        except Exception:
            return b""
        return r.content if r.status_code == 200 else b""

    def poll_turn(
        self,
        token: str,
        chat_id: str,
        max_wait_s: float = 180.0,
        min_messages: int = 1,
        correlation_id: str | None = None,
        model_slug: str = "",
        turn_started_at: float | None = None,
        deadline: float | None = None,
    ) -> TurnOutcome:
        del min_messages
        deadline = deadline or (time.monotonic() + max_wait_s)
        message_id = self._pending_message_ids.get(chat_id)
        if not message_id:
            raise RuntimeError(f"no submitted assistant message for {chat_id}")
        message: dict[str, Any] = {}
        task_ids: list[str] = []
        with self._client(_remaining(deadline)) as client:
            while time.monotonic() < deadline:
                task = self.task_status(token, chat_id, client, deadline)
                task_ids = [str(task_id) for task_id in task.get("task_ids", []) if task_id]
                if task_ids:
                    time.sleep(min(POLL_INTERVAL_S, max(0.0, deadline - time.monotonic())))
                    continue
                detail = self.chat_detail(token, chat_id, client, deadline)
                messages = ((detail.get("chat") or {}).get("history") or {}).get("messages") or {}
                message = messages.get(message_id, {})
                if message:
                    info = message.get("info") or {}
                    error = message.get("error") or info.get("error")
                    if isinstance(error, dict):
                        raise RuntimeError(f"OWUI assistant message failed: {error}")
                    state = str(message.get("status") or info.get("status") or "").lower()
                    done = message.get("done") is True or state in TERMINAL_STATES
                    if done:
                        break
                time.sleep(min(POLL_INTERVAL_S, max(0.0, deadline - time.monotonic())))
            else:
                self._stop_tasks(token, task_ids, client)
                raise TimeoutError(f"Open WebUI chat {chat_id} timed out")
            if not message:
                self._stop_tasks(token, task_ids, client)
                raise TimeoutError(f"Open WebUI assistant message {message_id} was not committed")
            trace = self._lookup_trace(
                client,
                correlation_id,
                model_slug,
                turn_started_at if turn_started_at is not None else time.time(),
                deadline,
            )
        spans = trace.get("spans", []) if isinstance(trace, dict) else []
        tool_spans = (
            tuple(
                span
                for span in spans
                if isinstance(span, dict)
                and span.get("name") == "tool.completed"
                and span.get("outcome") == "ok"
            )
            if isinstance(spans, list)
            else ()
        )
        if isinstance(spans, list) and ("spans" in trace or "tool_spans" in trace):
            trace["tool_spans"] = list(tool_spans)
        calls = _message_tool_calls(message)
        if not calls:
            calls = tool_spans
        text = visible_text(message)
        info = message.get("info") or {}
        state = str(message.get("status") or info.get("status") or "").lower()
        return TurnOutcome(
            chat_id=chat_id,
            text=text,
            done=message.get("done") is True or state in TERMINAL_STATES,
            served_model=served_model(message),
            artifact_urls=artifact_urls(message),
            leak_marker=raw_tool_error_leak(text),
            trace=trace,
            tool_calls=calls,
        )

    def _stop_tasks(self, token: str, task_ids: list[str], client: httpx.Client) -> None:
        for task_id in task_ids:
            try:
                client.post(
                    f"{self.settings.owui_url}/api/tasks/stop/{quote(task_id, safe='')}",
                    headers=self._headers(token),
                )
            except httpx.HTTPError:
                continue

    def lookup_trace(
        self,
        text: str = "",
        correlation_id: str | None = None,
        model_slug: str = "",
        turn_started_at: float | None = None,
        deadline: float | None = None,
    ) -> dict[str, object]:
        del text
        with self._client(_remaining(deadline)) as client:
            return self._lookup_trace(
                client, correlation_id, model_slug, turn_started_at or time.time(), deadline
            )

    def _lookup_trace(
        self,
        client: httpx.Client,
        correlation_id: str | None,
        model_slug: str,
        turn_started_at: float,
        deadline: float | None,
    ) -> dict[str, object]:
        try:
            r = client.get(
                f"{self.settings.pipeline_url}/v1/trace",
                headers=self.settings.auth_headers(),
                timeout=_remaining(deadline),
            )
            if r.status_code != 200:
                return {}
            body = r.json()
            summaries = body.get("data", []) if isinstance(body, dict) else body
            if not isinstance(summaries, list):
                return {}
            if correlation_id:
                summary = next(
                    (row for row in summaries if row.get("correlation_id") == correlation_id), None
                )
                candidates = [summary] if summary else []
            else:
                candidates = [
                    row
                    for row in summaries
                    if row.get("workspace") == model_slug
                    and _started_at(row.get("started_at")) >= turn_started_at - 5.0
                ]
                candidates.sort(key=lambda row: _started_at(row.get("started_at")), reverse=True)
            for summary in candidates:
                if not isinstance(summary, dict):
                    continue
                trace_id = str(summary.get("correlation_id", ""))
                if trace_id:
                    record = self._trace_detail(client, trace_id, deadline)
                    if record:
                        return record
        except (httpx.HTTPError, ValueError, TypeError):
            return {}
        return {}

    def _trace_detail(
        self, client: httpx.Client, correlation_id: str, deadline: float | None = None
    ) -> dict[str, object]:
        r = client.get(
            f"{self.settings.pipeline_url}/v1/trace/{correlation_id}",
            headers=self.settings.auth_headers(),
            timeout=_remaining(deadline),
        )
        return r.json() if r.status_code == 200 else {}

    def rename_chat(self, token: str, chat_id: str, title: str) -> None:
        with self._client(30.0) as client:
            client.post(
                f"{self.settings.owui_url}/api/v1/chats/{chat_id}",
                json={"chat": {"title": title}},
                headers=self._headers(token),
            )

    def archive_chat(self, token: str, chat_id: str, date: str) -> tuple[bool, str]:
        parent_id = self._folder_id(token, "QAT")
        if not parent_id:
            return False, "could not create or find QAT folder"
        folder_id = self._folder_id(token, date, parent_id=parent_id)
        if not folder_id:
            return False, f"could not create or find QAT/{date} folder"
        with self._client(30.0) as client:
            r = client.post(
                f"{self.settings.owui_url}/api/v1/chats/{chat_id}/folder",
                json={"folder_id": folder_id},
                headers=self._headers(token),
            )
        if r.status_code not in (200, 201):
            return False, f"chat folder assignment failed: HTTP {r.status_code}"
        return True, "archived"

    def delete_chat(self, token: str, chat_id: str) -> bool:
        with self._client(30.0) as client:
            r = client.delete(
                f"{self.settings.owui_url}/api/v1/chats/{chat_id}",
                headers=self._headers(token),
            )
        return r.status_code in (200, 204)

    def _folder_id(self, token: str, name: str, parent_id: str | None = None) -> str | None:
        with self._client(30.0) as client:
            r = client.get(
                f"{self.settings.owui_url}/api/v1/folders/", headers=self._headers(token)
            )
            body = r.json() if r.status_code == 200 else []
            folders = body.get("folders", []) if isinstance(body, dict) else body
            if isinstance(folders, list):
                for folder in folders:
                    if (
                        isinstance(folder, dict)
                        and folder.get("name") == name
                        and folder.get("parent_id") == parent_id
                        and folder.get("id")
                    ):
                        return str(folder["id"])
            payload = {"name": name}
            if parent_id is not None:
                payload["parent_id"] = parent_id
            created = client.post(
                f"{self.settings.owui_url}/api/v1/folders/",
                json=payload,
                headers=self._headers(token),
            )
        if created.status_code in (200, 201):
            folder_id = created.json().get("id")
            return str(folder_id) if folder_id else None
        return None


def _remaining(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("QAT scenario deadline expired")
    return left


def _same_origin(url: str, base_url: str) -> bool:
    target, base = urlsplit(url), urlsplit(base_url)
    return (target.scheme, target.hostname, target.port) == (base.scheme, base.hostname, base.port)


def _started_at(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0


def _message_tool_calls(message: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    info = message.get("info") or {}
    calls = message.get("tool_calls") or info.get("tool_calls") or info.get("calls") or []
    return (
        tuple(call for call in calls if isinstance(call, dict)) if isinstance(calls, list) else ()
    )


def visible_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, list):
        content = " ".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("text")
        )
    if isinstance(content, str) and content.strip():
        return content
    visible: list[str] = []
    for item in message.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        if item.get("role") not in (None, "assistant"):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                visible.append(str(part.get("text", "")))
    return "\n".join(visible)


def served_model(message: dict) -> str:
    return str(message.get("model") or (message.get("info") or {}).get("model") or "")


def artifact_urls(message: dict) -> tuple[str, ...]:
    found: list[str] = []
    for match in ARTIFACT_URL_RE.findall(visible_text(message)):
        found.append(match.rstrip("),].>\"'"))
    for entry in message.get("files") or []:
        url = entry.get("url") if isinstance(entry, dict) else None
        if url:
            found.append(str(url))
    return tuple(dict.fromkeys(found))
