"""A published OWUI file is in the answer even when the model only cites a sidecar."""

from __future__ import annotations

import json
import typing
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import portal.platform.inference.router.streaming as streaming
from portal.modules.documents.tools import document_mcp
from portal.platform.inference.router import non_streaming
from portal.platform.inference.router.download_links import missing_published_suffix
from portal.platform.mcp_host.delivery import category_output_dir

DOCX = (
    "https://portal.example/api/v1/files/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    "/content/transcript_abc.docx"
)
MD = (
    "https://portal.example/api/v1/files/11111111-2222-3333-4444-555555555555"
    "/content/transcript_abc.md"
)
HOST = "http://host.docker.internal:8924/files/transcript_abc.docx"


def test_suffix_adds_the_docx_the_answer_omitted() -> None:
    answer = f"Transcript:\n\n[transcript_abc.md]({MD})\n"
    results = [{"role": "tool", "content": json.dumps({"md_url": MD, "docx_url": DOCX})}]
    suffix = missing_published_suffix(answer, results)
    assert DOCX in suffix
    assert MD not in suffix
    assert "transcript_abc.docx" in suffix


def test_suffix_skips_a_file_already_shown_and_ignores_host_urls() -> None:
    answer = f"Download: {DOCX}"
    results = [{"content": json.dumps({"docx_url": DOCX, "local": HOST})}]
    assert missing_published_suffix(answer, results) == ""
    assert missing_published_suffix("no files", [{"content": json.dumps({"url": HOST})}]) == ""


def test_non_stream_answer_gains_the_omitted_docx() -> None:
    data = {"choices": [{"message": {"role": "assistant", "content": f"[markdown]({MD})"}}]}
    non_streaming._attach_published_links(
        data, [{"content": json.dumps({"md_url": MD, "docx_url": DOCX})}]
    )
    text = data["choices"][0]["message"]["content"]
    assert MD in text
    assert DOCX in text


def test_office_writes_use_generated_documents(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(document_mcp, "OUTPUT_DIR", tmp_path)
    path = document_mcp._unique_path("Note", "docx")
    assert path.parent == tmp_path / "generated" / "documents"
    path.write_bytes(b"PK\x03\x04")
    assert document_mcp._lookup_bare_name(path.name) == path.resolve()
    legacy = tmp_path / "legacy.docx"
    legacy.write_bytes(b"PK\x03\x04")
    assert document_mcp._lookup_bare_name("legacy.docx") == legacy.resolve()


def test_category_dir_is_not_nested_when_root_is_already_the_category(tmp_path) -> None:
    root = tmp_path / "generated" / "documents"
    assert category_output_dir("documents", root=root) == root
    assert root.is_dir()


def test_other_generators_use_the_shared_category_dirs() -> None:
    modules = Path("portal/modules")
    expected = {
        "media/tools/music_mcp.py": 'get_generated_dir("music")',
        "media/tools/video_mlx_mcp.py": 'get_generated_dir("videos")',
        "cad/tools/cad_render_mcp.py": 'get_generated_dir("models3d")',
        "media/tools/whisper_mcp.py": 'get_generated_dir("transcripts")',
    }
    for rel, needle in expected.items():
        assert needle in (modules / rel).read_text(encoding="utf-8")
    documents = (modules / "documents/tools/document_mcp.py").read_text(encoding="utf-8")
    assert "category_output_dir" in documents


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
        return None


@pytest.mark.anyio
async def test_stream_appends_published_docx_when_the_model_links_only_markdown(
    monkeypatch,
) -> None:
    payload = json.dumps({"md_url": MD, "docx_url": DOCX})

    async def dispatch(calls, *_args):
        return {"role": "assistant", "content": None, "tool_calls": calls}, [
            {
                "role": "tool",
                "tool_call_id": calls[0]["id"],
                "name": "transcribe_with_speakers",
                "content": payload,
            }
        ]

    client = MagicMock()
    tool_call = {
        "index": 0,
        "id": "call-stt",
        "type": "function",
        "function": {"name": "transcribe_with_speakers", "arguments": "{}"},
    }
    hops = [
        [_frame({"tool_calls": [tool_call]}, "tool_calls"), "data: [DONE]"],
        [
            _frame({"content": f"Here is the transcript.\n[transcript_abc.md]({MD})\n"}),
            _frame({}, "stop"),
            "data: [DONE]",
        ],
    ]
    client.stream = MagicMock(side_effect=[_Ctx(hop) for hop in hops])
    monkeypatch.setattr(streaming, "_http_client", client)
    monkeypatch.setattr(streaming, "_dispatch_hop_tool_calls", dispatch)
    tools = [
        {
            "type": "function",
            "function": {"name": "transcribe_with_speakers", "parameters": {"type": "object"}},
        }
    ]
    frames = [
        chunk
        async for chunk in streaming._stream_with_tool_loop_impl(
            backend_url="http://offline.test/v1/chat/completions",
            body={"model": "m", "messages": [], "tools": tools},
            workspace_id="auto-audio",
            model="m",
            persona="",
            effective_tools={"transcribe_with_speakers"},
        )
    ]
    text = b"".join(frames).decode()
    assert MD in text
    assert DOCX in text
    assert text.count(DOCX) == 1
