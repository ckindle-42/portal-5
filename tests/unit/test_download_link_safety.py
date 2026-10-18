"""Only successful file creation may justify a Download link in the answer."""

from __future__ import annotations

import json
import time
import typing
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from portal.platform.inference.router import non_streaming, streaming
from portal.platform.inference.router.download_links import DownloadLineFilter

URL = "https://files.mocki.io/downloads/report.docx"


def _non_stream_answer(content: str, *, created: bool) -> str:
    response = non_streaming._apply_non_stream_response(
        {"choices": [{"message": {"role": "assistant", "content": content}}]},
        SimpleNamespace(id="offline-test"),
        "general-fast",
        "model",
        time.monotonic(),
        successful_creation=created,
    )
    return json.loads(response.body)["choices"][0]["message"]["content"]


def test_non_stream_create_turn_keeps_download_link() -> None:
    answer = f"Created it.\n**Download:** {URL}"
    assert _non_stream_answer(answer, created=True) == answer


def test_non_stream_read_turn_removes_fabricated_download_link() -> None:
    answer = _non_stream_answer(f"The document says hello.\nDownload: {URL}", created=False)
    assert answer.rstrip("\n") == "The document says hello."
    assert URL not in answer


def test_non_stream_ordinary_download_word_without_link_stays() -> None:
    answer = "The word download appears in the source text."
    assert _non_stream_answer(answer, created=False) == answer


def _frame(delta: dict, finish: str | None = None) -> str:
    return "data: " + json.dumps(
        {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    )


class _Ctx:
    def __init__(self, lines: list[str]):
        self._lines = lines

    async def __aenter__(self):
        ctx = self

        class _Resp:
            status_code = 200

            async def aiter_lines(self):
                for line in ctx._lines:
                    yield line

        return _Resp()

    async def __aexit__(self, *_: typing.Any):
        pass


async def _stream_answer(
    monkeypatch, hops: list[list[str]], *, tool_name: str, offered: tuple[str, ...] = ()
) -> str:
    client = MagicMock()
    client.stream = MagicMock(side_effect=[_Ctx(hop) for hop in hops])
    monkeypatch.setattr(streaming, "_http_client", client)
    # auto-documents offers read and create tools together; the filter only runs then
    names = dict.fromkeys((tool_name, *(offered or ("create_word_document",))))
    tools = [
        {"type": "function", "function": {"name": n, "parameters": {"type": "object"}}}
        for n in names
    ]

    if tool_name.startswith("create_"):

        async def dispatch(calls, *args):
            return {"role": "assistant", "content": None, "tool_calls": calls}, [
                {
                    "role": "tool",
                    "tool_call_id": calls[0]["id"],
                    "name": tool_name,
                    "content": json.dumps({"success": True, "download_url": URL}),
                }
            ]

        monkeypatch.setattr(streaming, "_dispatch_hop_tool_calls", dispatch)

    body = {"model": "m", "messages": [], "tools": tools}
    frames = [
        chunk
        async for chunk in streaming._stream_with_tool_loop_impl(
            backend_url="http://offline.test/v1/chat/completions",
            body=body,
            workspace_id="general-fast",
            model="m",
            persona="",
            effective_tools={tool_name},
        )
    ]
    return b"".join(frames).decode()


@pytest.mark.anyio
async def test_stream_create_turn_keeps_download_link(monkeypatch) -> None:
    tool_call = {
        "index": 0,
        "id": "call-create",
        "type": "function",
        "function": {"name": "create_word_document", "arguments": "{}"},
    }
    hops = [
        [_frame({"tool_calls": [tool_call]}, "tool_calls"), "data: [DONE]"],
        [
            _frame({"content": f"Created it.\nDownload: {URL}\n"}),
            _frame({}, "stop"),
            "data: [DONE]",
        ],
    ]
    out = await _stream_answer(monkeypatch, hops, tool_name="create_word_document")
    assert URL in out


@pytest.mark.anyio
async def test_stream_read_turn_removes_fabricated_download_link(monkeypatch) -> None:
    hops = [
        [
            _frame({"content": "The document says hello.\nDown"}),
            _frame({"content": f"load: {URL}\n"}),
            _frame({}, "stop"),
            "data: [DONE]",
        ]
    ]
    out = await _stream_answer(monkeypatch, hops, tool_name="read_word_document")
    assert "The document says hello." in out
    assert URL not in out


@pytest.mark.anyio
async def test_stream_without_file_tools_keeps_an_honest_download_link(monkeypatch) -> None:
    hops = [
        [
            _frame({"content": f"Download: {URL}\n"}),
            _frame({}, "stop"),
            "data: [DONE]",
        ]
    ]
    out = await _stream_answer(
        monkeypatch, hops, tool_name="read_word_document", offered=("read_word_document",)
    )
    assert URL in out


def test_stream_filter_does_not_buffer_ordinary_download_text() -> None:
    filt = DownloadLineFilter()
    text = "This sentence contains the word download, with no link."
    assert filt.feed(text) == text
    assert filt.finish() == ""


def test_only_turns_offering_a_file_tool_are_filtered():
    from portal.platform.inference.router.download_links import offers_file_creation

    create = {"type": "function", "function": {"name": "create_word_document"}}
    read = {"type": "function", "function": {"name": "read_pdf"}}
    assert offers_file_creation([read, create])
    assert offers_file_creation([{"name": "convert_document"}])
    # auto-daily may honestly answer "Download VS Code from https://code.visualstudio.com"
    assert not offers_file_creation([read])
    assert not offers_file_creation(None)
