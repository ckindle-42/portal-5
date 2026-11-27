"""Native Open WebUI chat-turn client for QAT."""

from __future__ import annotations

import base64
import mimetypes
import re
import struct
import time
import uuid
import zlib
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import httpx

from .artifacts import raw_tool_error_leak
from .config import Settings

POLL_INTERVAL_S = 2.0
DEFAULT_TURN_IDLE_TIMEOUT_S = 300.0
_AUDIO_UPLOAD_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
}
_SKIP_OWUI_PROCESS = frozenset({".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".aac", ".mp4"})


def _upload_content_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return (
        _AUDIO_UPLOAD_TYPES.get(suffix)
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )


def _upload_params(filename: str) -> dict[str, str] | None:
    """process=false keeps OWUI from writing an STT JSON sidecar beside the audio."""
    if Path(filename).suffix.lower() in _SKIP_OWUI_PROCESS:
        return {"process": "false"}
    return None


ARTIFACT_URL_RE = re.compile(
    r"/api/v1/files/[0-9a-fA-F-]{8,}/content/(?:[^\s\]\"'<>()]|\([^\s\]\"'<>()]*\))+"
)
_PUBLISHED_FILE_RE = re.compile(r"/api/v1/files/(?P<id>[0-9a-fA-F-]{8,})/content/(?P<name>[^/?#]+)")
TERMINAL_STATES = {"completed", "complete", "done", "success"}
_RED = (255, 0, 0)


class ArtifactDownloadError(RuntimeError):
    """Artifact download died on transport or HTTP; status_code 0 means transport."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class TurnStalledError(TimeoutError):
    def __init__(
        self,
        idle_timeout_s: float,
        elapsed_s: float,
        bytes_received: int,
        message_id: str = "",
        task_ids: tuple[str, ...] = (),
    ) -> None:
        self.idle_timeout_s = idle_timeout_s
        self.elapsed_s = elapsed_s
        self.bytes_received = bytes_received
        self.message_id = message_id
        self.task_ids = task_ids
        super().__init__(f"assistant stream stalled after {idle_timeout_s:.1f}s without new data")


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
    duration_s: float = 0.0


class OWUIClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        idle_timeout_s: float = DEFAULT_TURN_IDLE_TIMEOUT_S,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self.idle_timeout_s = idle_timeout_s
        self._turns: dict[str, dict[str, str]] = {}
        self._pending_message_ids: dict[str, str] = {}
        self._turn_task_ids: dict[str, tuple[str, ...]] = {}
        self._base_model_ids: dict[str, str] = {}

    def _client(self, timeout_s: float | httpx.Timeout | None = None) -> httpx.Client:
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

    def list_models(self, token: str) -> set[str]:
        with self._client(30.0) as client:
            response = client.get(
                f"{self.settings.owui_url}/api/models", headers=self._headers(token)
            )
        if not response.is_success:
            raise RuntimeError(f"OWUI model catalog failed: HTTP {response.status_code}")
        body = response.json()
        rows = body.get("data") or body.get("models") or [] if isinstance(body, dict) else body
        if not isinstance(rows, list):
            raise RuntimeError("OWUI model catalog response is not a list")
        model_ids = {
            str(row.get("id") or row.get("model") or "")
            for row in rows
            if isinstance(row, dict) and (row.get("id") or row.get("model"))
        }
        if not model_ids:
            raise RuntimeError("OWUI model catalog contains no model IDs")
        self._base_model_ids = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = row.get("id") or row.get("model")
            base_model_id = row.get("base_model_id")
            for key in ("info", "model"):
                nested = row.get(key)
                if not base_model_id and isinstance(nested, dict):
                    base_model_id = nested.get("base_model_id")
            if model_id and base_model_id:
                self._base_model_ids[str(model_id)] = str(base_model_id)
        return model_ids

    def snapshot_memories(self, token: str) -> list[dict[str, Any]]:
        with self._client(30.0) as client:
            response = client.get(
                f"{self.settings.owui_url}/api/v1/memories/",
                headers=self._headers(token),
            )
        if response.status_code != 200:
            raise RuntimeError(f"OWUI memory snapshot failed: HTTP {response.status_code}")
        rows = response.json()
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise RuntimeError("OWUI memory snapshot returned an invalid response")
        return [dict(row) for row in rows]

    def clear_memories(self, token: str) -> None:
        with self._client(30.0) as client:
            response = client.delete(
                f"{self.settings.owui_url}/api/v1/memories/delete/user",
                headers=self._headers(token),
            )
        if response.status_code != 200 or response.json() is not True:
            raise RuntimeError(f"OWUI memory clear failed: HTTP {response.status_code}")

    def add_memory(
        self, token: str, content: str, memory_type: str = "user", path: str | None = None
    ) -> dict[str, Any]:
        with self._client(30.0) as client:
            response = client.post(
                f"{self.settings.owui_url}/api/v1/memories/add",
                json={"content": content, "type": memory_type, "path": path},
                headers=self._headers(token),
            )
        if response.status_code != 200 or not isinstance(response.json(), dict):
            raise RuntimeError(f"OWUI memory add failed: HTTP {response.status_code}")
        return response.json()

    def replace_memories(
        self, token: str, memories: list[dict[str, Any]] | tuple[str, ...]
    ) -> None:
        self.clear_memories(token)
        for memory in memories:
            if isinstance(memory, str):
                self.add_memory(token, memory)
            else:
                self.add_memory(
                    token,
                    str(memory.get("content") or ""),
                    memory_type=str(memory.get("type") or "context"),
                    path=memory.get("path"),
                )

    def restore_memories(self, token: str, memories: list[dict[str, Any]]) -> None:
        self.replace_memories(token, memories)
        restored = self.snapshot_memories(token)
        expected = sorted(
            (
                str(row.get("type") or "context"),
                str(row.get("path") or ""),
                str(row.get("content") or ""),
            )
            for row in memories
        )
        actual = sorted(
            (
                str(row.get("type") or "context"),
                str(row.get("path") or ""),
                str(row.get("content") or ""),
            )
            for row in restored
        )
        if actual != expected:
            raise RuntimeError("OWUI memory restore verification failed")

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
        if self._pending_message_ids.get(chat_id):
            self._persist_turn_nodes(token, chat_id, model_slug, content, turn, files, None)
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
        self._pending_message_ids[chat_id] = message_id
        response = self._stream_turn(token, body)
        self._remember_turn_tasks(chat_id, response)
        return response

    def _remember_turn_tasks(self, chat_id: str, response: httpx.Response) -> None:
        """OWUI's task fan-out answers with the completion task ids it registered."""
        if "application/json" not in (response.headers.get("content-type") or ""):
            return
        try:
            body = response.json()
        except ValueError:
            return
        ids = body.get("task_ids") if isinstance(body, dict) else None
        if isinstance(ids, list) and ids:
            self._turn_task_ids[chat_id] = tuple(str(task_id) for task_id in ids if task_id)

    def turn_task_ids(self, chat_id: str) -> tuple[str, ...]:
        return self._turn_task_ids.get(chat_id, ())

    def pending_message_id(self, chat_id: str) -> str:
        return self._pending_message_ids.get(chat_id, "")

    def _stream_turn(self, token: str, body: dict[str, Any]) -> httpx.Response:
        started = time.monotonic()
        timeout = httpx.Timeout(self.idle_timeout_s, connect=10.0, write=10.0, pool=10.0)
        chunks: list[bytes] = []
        bytes_received = 0
        try:
            with (
                self._client(timeout) as client,
                client.stream(
                    "POST",
                    f"{self.settings.owui_url}/api/chat/completions",
                    json=body,
                    headers=self._headers(token),
                ) as source,
            ):
                status_code = source.status_code
                headers = source.headers
                request = source.request
                for chunk in source.iter_bytes():
                    chunks.append(chunk)
                    bytes_received += len(chunk)
        except httpx.ReadTimeout as exc:
            raise TurnStalledError(
                self.idle_timeout_s, time.monotonic() - started, bytes_received
            ) from exc
        response = httpx.Response(
            status_code, headers=headers, content=b"".join(chunks), request=request
        )
        response.extensions["qat_stream_duration_s"] = time.monotonic() - started
        response.extensions["qat_stream_bytes"] = bytes_received
        return response

    def _persist_turn_nodes(
        self,
        token: str,
        chat_id: str,
        model_slug: str,
        content: str | list[dict[str, Any]],
        turn: dict[str, str],
        files: list[dict[str, Any]] | None,
        deadline: float | None,
    ) -> None:
        """Append Turn 2+ user/assistant nodes so OWUI renders every question."""
        del deadline
        prev_assistant_id = self._pending_message_ids[chat_id]
        detail = self.chat_detail(token, chat_id)
        history = (detail.get("chat") or {}).get("history") or {}
        messages = history.get("messages")
        if not isinstance(messages, dict) or not messages:
            raise RuntimeError(f"OWUI chat {chat_id} history unavailable; cannot persist turn")
        user_id, message_id = turn["user_id"], turn["message_id"]
        now = int(time.time())
        user_node: dict[str, Any] = {
            "id": user_id,
            "role": "user",
            "content": content,
            "timestamp": now,
            "models": [model_slug],
            "parentId": prev_assistant_id,
            "childrenIds": [message_id],
        }
        if files is not None:
            user_node["files"] = files
        messages[user_id] = user_node
        messages[message_id] = {
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
        }
        prev = messages.get(prev_assistant_id)
        if isinstance(prev, dict):
            children = prev.get("childrenIds")
            prev["childrenIds"] = [*(children if isinstance(children, list) else []), user_id]
        history["messages"] = messages
        history["currentId"] = message_id
        with self._client(30.0) as client:
            r = client.post(
                f"{self.settings.owui_url}/api/v1/chats/{chat_id}",
                json={"chat": {"history": history}},
                headers=self._headers(token),
            )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"chats/{chat_id} turn persistence failed: HTTP {r.status_code}")

    def upload_attachment(
        self, token: str, relative_path: str, deadline: float | None = None
    ) -> dict[str, str]:
        path = Path(relative_path)
        if not path.is_absolute():
            path = self.settings.repo_root / path
        with path.open("rb") as stream:
            return self.upload_attachment_bytes(token, path.name, stream.read(), deadline)

    def upload_attachment_bytes(
        self, token: str, filename: str, data: bytes, deadline: float | None = None
    ) -> dict[str, str]:
        del deadline
        content_type = _upload_content_type(filename)
        with self._client(30.0) as client:
            response = client.post(
                f"{self.settings.owui_url}/api/v1/files/",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                params=_upload_params(filename),
                files={"file": (filename, data, content_type)},
            )
        return self._uploaded_file_id(response)

    @staticmethod
    def _uploaded_file_id(response: httpx.Response) -> dict[str, str]:
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

    def stop_chat_tasks(self, token: str, chat_id: str) -> list[str]:
        """Stop every completion task OWUI still registers for this chat."""
        with self._client(10.0) as client:
            task_ids = [
                str(task_id)
                for task_id in self.task_status(
                    token, chat_id, client, time.monotonic() + 10.0
                ).get("task_ids", [])
                if task_id
            ]
            self._stop_tasks(token, task_ids, client)
        return task_ids

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
        target, headers = self._artifact_request(token, url)
        try:
            with self._client(30.0) as client:
                r = client.get(target, headers=headers)
                if r.status_code == 404:
                    recovered = self._recover_published_file(client, headers, url)
                    if recovered is not None:
                        return recovered
        except Exception as exc:
            raise ArtifactDownloadError(f"artifact download failed: {exc}") from exc
        if r.status_code != 200:
            raise ArtifactDownloadError(
                f"artifact download failed: HTTP {r.status_code}", status_code=r.status_code
            )
        return r.content

    def _artifact_request(self, token: str, url: str) -> tuple[str, dict[str, str]]:
        parsed = urlsplit(url)
        if "/api/v1/files/" in parsed.path:
            clean_path = parsed.path[parsed.path.index("/api/v1/files/") :]
            target = f"{self.settings.owui_url.rstrip('/')}{clean_path}"
            if parsed.query:
                target = f"{target}?{parsed.query}"
            return target, self._headers(token)
        target = url if parsed.scheme else f"{self.settings.owui_url}{url}"
        headers = self._headers(token) if _same_origin(target, self.settings.owui_url) else {}
        return target, headers

    def _recover_published_file(
        self, client: httpx.Client, headers: dict[str, str], url: str
    ) -> bytes | None:
        """A mistyped file id still names the published filename. Resolve that row."""
        match = _PUBLISHED_FILE_RE.search(urlsplit(url).path)
        if match is None or not headers:
            return None
        name = unquote(match.group("name"))
        listed = client.get(
            f"{self.settings.owui_url.rstrip('/')}/api/v1/files/search",
            params={"filename": name, "content": "false"},
            headers=headers,
        )
        if listed.status_code != 200:
            return None
        rows = listed.json()
        if not isinstance(rows, list):
            return None
        exact = [
            row
            for row in rows
            if isinstance(row, dict) and row.get("filename") == name and row.get("id")
        ]
        if not exact:
            return None

        def _stamp(row: dict[str, Any]) -> int:
            raw = row.get("created_at") or 0
            return int(raw) if isinstance(raw, (int, float)) else 0

        exact.sort(key=_stamp)
        file_id = str(exact[-1]["id"])
        if file_id == match.group("id"):
            return None
        fetched = client.get(
            f"{self.settings.owui_url.rstrip('/')}/api/v1/files/{file_id}/content",
            headers=headers,
        )
        if fetched.status_code != 200 or not fetched.content:
            return None
        return fetched.content

    def _observed_task_ids(
        self, token: str, chat_id: str, client: httpx.Client, poll_deadline: float
    ) -> list[str]:
        task = self.task_status(token, chat_id, client, poll_deadline)
        return [str(task_id) for task_id in task.get("task_ids", []) if task_id]

    def _observed_message(
        self,
        token: str,
        chat_id: str,
        client: httpx.Client,
        poll_deadline: float,
        message_id: str,
    ) -> tuple[dict[str, Any], bool]:
        """Read the answer every pass (F12): a lingering title task must not hold it hostage."""
        detail = self.chat_detail(token, chat_id, client, poll_deadline)
        messages = ((detail.get("chat") or {}).get("history") or {}).get("messages") or {}
        message = messages.get(message_id, {})
        info = message.get("info") or {}
        state = str(message.get("status") or info.get("status") or "").lower()
        if message:
            error = message.get("error") or info.get("error")
            if isinstance(error, dict):
                raise RuntimeError(f"OWUI assistant message failed: {error}")
        return message, message.get("done") is True or state in TERMINAL_STATES

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
        del deadline, max_wait_s, min_messages
        started = time.monotonic()
        message_id = self._pending_message_ids.get(chat_id)
        if not message_id:
            raise RuntimeError(f"no submitted assistant message for {chat_id}")
        message: dict[str, Any] = {}
        task_ids: list[str] = []
        turn_tasks = self._turn_task_ids.get(chat_id, ())
        last_signature: tuple[str, str, bool, tuple[str, ...]] | None = None
        last_progress_at = started
        with self._client(10.0) as client:
            while True:
                poll_deadline = time.monotonic() + 10.0
                task_ids = self._observed_task_ids(token, chat_id, client, poll_deadline)
                message, done = self._observed_message(
                    token, chat_id, client, poll_deadline, message_id
                )
                info = message.get("info") or {}
                state = str(message.get("status") or info.get("status") or "").lower()
                # Liveness: OWUI keeps the turn's completion task registered while it
                # still processes the turn, and unregisters it at completion or abort.
                # The DB content stays "" mid-turn (ENABLE_REALTIME_CHAT_SAVE=False),
                # so a frozen signature alone proves nothing about generation.
                if turn_tasks and set(task_ids) & set(turn_tasks):
                    last_progress_at = time.monotonic()
                signature = (repr(message.get("content")), state, done, tuple(task_ids))
                if signature != last_signature:
                    last_signature = signature
                    last_progress_at = time.monotonic()
                if done:
                    break
                elapsed_idle = time.monotonic() - last_progress_at
                if elapsed_idle >= self.idle_timeout_s:
                    self._stop_tasks(token, task_ids, client)
                    raise TurnStalledError(
                        self.idle_timeout_s,
                        time.monotonic() - started,
                        0,
                        message_id=message_id,
                        task_ids=tuple(task_ids),
                    )
                time.sleep(min(POLL_INTERVAL_S, self.idle_timeout_s - elapsed_idle))
            if not message:
                self._stop_tasks(token, task_ids, client)
                raise TimeoutError(f"Open WebUI assistant message {message_id} was not committed")
            trace = self._lookup_trace(
                client,
                correlation_id,
                model_slug,
                turn_started_at if turn_started_at is not None else time.time(),
                time.monotonic() + 10.0,
                token=token,
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
        token: str | None = None,
    ) -> dict[str, object]:
        del text
        with self._client(_remaining(deadline)) as client:
            return self._lookup_trace(
                client,
                correlation_id,
                model_slug,
                turn_started_at or time.time(),
                deadline,
                token=token,
            )

    def _lookup_trace(
        self,
        client: httpx.Client,
        correlation_id: str | None,
        model_slug: str,
        turn_started_at: float,
        deadline: float | None,
        token: str | None = None,
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
            matchers = {model_slug} if model_slug else set()
            candidates = _trace_candidates(summaries, correlation_id, matchers, turn_started_at)
            if not candidates and token and model_slug and model_slug not in self._base_model_ids:
                with suppress(httpx.HTTPError, RuntimeError, ValueError, TypeError):
                    self.list_models(token)
            if base_model_id := self._base_model_ids.get(model_slug):
                matchers = {model_slug, base_model_id}
                candidates = _trace_candidates(summaries, correlation_id, matchers, turn_started_at)
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


def _trace_row_matches(
    row: dict[str, object], model_slugs: set[str], turn_started_at: float
) -> bool:
    if not model_slugs:
        return False
    if row.get("owui_task"):
        # An OWUI title/tag task is a trace of its own on the same workspace:
        # it must never match the graded turn.
        return False
    identity = {str(row.get(key) or "") for key in ("workspace", "requested", "persona")}
    return (
        bool(model_slugs & identity) and _started_at(row.get("started_at")) >= turn_started_at - 5.0
    )


def _trace_candidates(
    summaries: list[object],
    correlation_id: str | None,
    model_slugs: set[str],
    turn_started_at: float,
) -> list[dict[str, object]]:
    """Correlation id, else the newest workspace/requested/persona slug since the turn."""
    rows = [row for row in summaries if isinstance(row, dict)]
    if correlation_id:
        matched = next((row for row in rows if row.get("correlation_id") == correlation_id), None)
        if matched is not None:
            return [matched]
    candidates = [row for row in rows if _trace_row_matches(row, model_slugs, turn_started_at)]
    candidates = _prefer_served_trace(candidates)
    candidates.sort(key=lambda row: _started_at(row.get("started_at")), reverse=True)
    return candidates


def _prefer_served_trace(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """A pre-route safety refusal shares the requested slug and has no served model.

    ``record_refusal`` stores the client model in ``workspace``, so identity
    matching treats it as the graded turn. When a turn that actually served is
    also in the window, that turn is the one to grade. A lone refusal stays,
    which is the adversarial row's only trace.
    """
    served = [
        row
        for row in rows
        if str(row.get("model") or "") and str(row.get("outcome") or "") != "safety_refusal"
    ]
    return served or rows


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


# Trailing markdown around a link: bold/italic/code ticks plus closers.
# ')' is handled separately so a balanced parenthesis inside a filename stays.
_ARTIFACT_URL_JUNK = set(",].>\"'*_`")


def _clean_artifact_url(raw: str) -> str:
    end = len(raw)
    while end > 0:
        char = raw[end - 1]
        if char in _ARTIFACT_URL_JUNK:
            end -= 1
            continue
        if char == ")" and raw[:end].count(")") > raw[:end].count("("):
            end -= 1
            continue
        break
    return raw[:end]


def artifact_urls(message: dict) -> tuple[str, ...]:
    found: list[str] = []
    for match in ARTIFACT_URL_RE.findall(visible_text(message)):
        found.append(_clean_artifact_url(match))
    for entry in message.get("files") or []:
        url = entry.get("url") if isinstance(entry, dict) else None
        if url:
            found.append(str(url))
    return tuple(dict.fromkeys(found))
