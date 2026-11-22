"""Native Open WebUI chat turn client (Release 1.0 QAT).

Flow per turn: POST /api/v1/chats/new -> POST /api/chat/completions carrying
the workspace preset's tool_ids and function_calling -> poll
/api/tasks/chat/{chat_id} (best-effort completion signal) -> read the
persisted assistant message from chat history -> query Pipeline /v1/trace for
tool spans and backend/model -> collect artifact URLs -> rename [PASS]/[FAIL]
and archive into the QAT/{YYYY-MM-DD} folder (or delete under --cleanup-chats).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import httpx

from .artifacts import raw_tool_error_leak
from .config import Settings

SETTLE_POLLS = 3
SETTLE_THRESHOLD = 50
POLL_INTERVAL_S = 2.0


@dataclass
class TurnOutcome:
    chat_id: str
    text: str
    done: bool
    served_model: str
    artifact_urls: tuple[str, ...]
    leak_marker: str | None
    trace: dict[str, object]


class OWUIClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=30.0)

    def signin(self) -> str:
        if self.settings.owui_api_key:
            return self.settings.owui_api_key
        with self._client() as client:
            r = client.post(
                f"{self.settings.owui_url}/api/v1/auths/signin",
                json={"email": self.settings.owui_user, "password": self.settings.owui_pass},
            )
        if r.status_code != 200:
            raise RuntimeError(f"OWUI signin failed: HTTP {r.status_code}")
        return str(r.json().get("token", ""))

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def create_chat(self, token: str, model_slug: str, title: str) -> str:
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
        with self._client() as client:
            r = client.post(
                f"{self.settings.owui_url}/api/v1/chats/new",
                json=payload,
                headers=self._headers(token),
            )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"chats/new failed: HTTP {r.status_code}")
        return str(r.json().get("id", chat_id))

    def send_turn(
        self,
        token: str,
        chat_id: str,
        model_slug: str,
        prompt: str,
        tool_ids: tuple[str, ...] = (),
        function_calling: bool = False,
    ) -> httpx.Response:
        body: dict[str, object] = {
            "model": model_slug,
            "messages": [{"role": "user", "content": prompt}],
            "chat_id": chat_id,
            "tool_ids": list(tool_ids),
            "stream": False,
        }
        if function_calling:
            body["params"] = {"function_calling": "native"}
        with self._client() as client:
            return client.post(
                f"{self.settings.owui_url}/api/chat/completions",
                json=body,
                headers=self._headers(token),
            )

    def chat_detail(self, token: str, chat_id: str) -> dict:
        with self._client() as client:
            r = client.get(
                f"{self.settings.owui_url}/api/v1/chats/{chat_id}",
                headers={**self._headers(token), "Accept-Encoding": "identity"},
            )
        return r.json() if r.status_code == 200 else {}

    def task_status(self, token: str, chat_id: str) -> dict:
        """GET /api/tasks/chat/{chat_id} — absent on some OWUI builds; {} tolerated."""
        with self._client() as client:
            r = client.get(
                f"{self.settings.owui_url}/api/tasks/chat/{chat_id}",
                headers=self._headers(token),
            )
        return r.json() if r.status_code == 200 else {}

    def download_artifact(self, token: str, url: str) -> bytes:
        """Fetch an artifact produced by a tool turn (files carry absolute or
        OWUI-relative URLs); empty bytes on any failure."""
        target = url if url.startswith("http") else f"{self.settings.owui_url}{url}"
        try:
            with self._client() as client:
                r = client.get(target, headers=self._headers(token))
        except Exception:
            return b""
        return r.content if r.status_code == 200 else b""

    def poll_turn(
        self, token: str, chat_id: str, max_wait_s: float = 180.0, min_messages: int = 1
    ) -> TurnOutcome:
        """Wait until the assistant message is committed and stable."""
        deadline = time.monotonic() + max_wait_s
        history_lens: list[int] = []
        text = ""
        done = False
        detail: dict = {}
        assistants: list[dict] = []
        while time.monotonic() < deadline:
            self.task_status(token, chat_id)
            detail = self.chat_detail(token, chat_id)
            messages = list(
                (detail.get("chat") or {}).get("history", {}).get("messages", {}).values()
            )
            assistants = [m for m in messages if m.get("role") == "assistant" and visible_text(m)]
            if len(assistants) >= min_messages:
                last = assistants[-1]
                text = visible_text(last)
                done = last.get("done") is True
                history_lens.append(len(text))
                stable = (
                    len(history_lens) >= SETTLE_POLLS
                    and max(history_lens[-SETTLE_POLLS:]) - min(history_lens[-SETTLE_POLLS:])
                    <= SETTLE_THRESHOLD
                )
                if stable or done:
                    break
            time.sleep(POLL_INTERVAL_S)
        return TurnOutcome(
            chat_id=chat_id,
            text=text,
            done=done,
            served_model=served_model(assistants[-1] if assistants else {}),
            artifact_urls=artifact_urls(assistants[-1] if assistants else {}),
            leak_marker=raw_tool_error_leak(text),
            trace=self.lookup_trace(text),
        )

    def lookup_trace(self, text: str) -> dict[str, object]:
        """Pipeline /v1/trace — find the turn's spans (tools, backend, model)."""
        with self._client() as client:
            r = client.get(
                f"{self.settings.pipeline_url}/v1/trace",
                headers=self.settings.auth_headers(),
            )
        if r.status_code != 200:
            return {}
        needle = text[:64] if text else None
        for summary in r.json():
            record = self._trace_detail(client, str(summary.get("correlation_id", "")))
            if record and (not needle or needle in str(record)):
                return record
        return {}

    def _trace_detail(self, client: httpx.Client, correlation_id: str) -> dict[str, object]:
        r = client.get(
            f"{self.settings.pipeline_url}/v1/trace/{correlation_id}",
            headers=self.settings.auth_headers(),
        )
        return r.json() if r.status_code == 200 else {}

    def rename_chat(self, token: str, chat_id: str, title: str) -> None:
        with self._client() as client:
            client.post(
                f"{self.settings.owui_url}/api/v1/chats/{chat_id}",
                json={"chat": {"title": title}},
                headers=self._headers(token),
            )

    def archive_chat(self, token: str, chat_id: str, date: str) -> bool:
        folder_id = self._folder_id(token, f"QAT/{date}")
        if not folder_id:
            return False
        with self._client() as client:
            r = client.post(
                f"{self.settings.owui_url}/api/v1/chats/{chat_id}/folder",
                json={"folder_id": folder_id},
                headers=self._headers(token),
            )
        return r.status_code in (200, 201)

    def delete_chat(self, token: str, chat_id: str) -> bool:
        with self._client() as client:
            r = client.delete(
                f"{self.settings.owui_url}/api/v1/chats/{chat_id}",
                headers=self._headers(token),
            )
        return r.status_code in (200, 204)

    def _folder_id(self, token: str, name: str) -> str | None:
        with self._client() as client:
            r = client.get(
                f"{self.settings.owui_url}/api/v1/folders/", headers=self._headers(token)
            )
            folders = r.json() if r.status_code == 200 else []
            for folder in folders:
                if folder.get("name") == name:
                    return str(folder.get("id"))
            r = client.post(
                f"{self.settings.owui_url}/api/v1/folders/",
                json={"name": name},
                headers=self._headers(token),
            )
        if r.status_code in (200, 201):
            return str(r.json().get("id"))
        return None


def visible_text(message: dict) -> str:
    """Assistant text from legacy content or the Responses-API output shape."""
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
    urls: list[str] = []
    for entry in message.get("files") or []:
        url = entry.get("url") if isinstance(entry, dict) else None
        if url:
            urls.append(str(url))
    return tuple(urls)
