"""Follow-up file requests on the fast seat must call the create tool.

realuse_s8_lfm25_sbfix_20261106, Qwen3.6 think:false, auto-daily::fast. Turn 0
called the tool. Turn 1 answered from that prose and invented a download link:
ru-v1-066 r0 (Now a Word file) and ru-v1-032 r0 (Make a second Word file).
The client history is the final answer only — the pipeline tool loop does not
carry its tool result into the next turn.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from portal.platform.inference.router import non_streaming as ns
from portal.platform.inference.router import streaming
from portal.platform.inference.router.download_links import (
    prior_office_filenames,
    strip_unbacked_download_lines,
)
from portal.platform.inference.router.tool_repeat import REQUIRED_TOOL_REQUEST
from portal.platform.inference.router.tools import _own_user_text, _select_explicit_required_tool

OFFERED = [
    "create_word_document",
    "create_excel",
    "create_powerpoint",
    "execute_python",
    "kb_search",
    "read_word_document",
]
WS = "test-followup-ws"

# Verbatim user turns from tests/wfe/suites/realuse_v1.jsonl.
WORD_FILE = (
    "Make a Word file titled Week Plan. Monday meeting prep. Tuesday coding project, "
    "and Tuesday is only 9 to 12. Wednesday travel admin, and I leave by 8am. "
    "Thursday research. Friday wrap-up, and Friday ends at 1pm."
)
SECOND_WORD = (
    "Make a second Word file titled Week Plan Revised. Keep the same days, "
    "add an 11am break on Tuesday, and add a Wednesday travel calendar note."
)
EXCEL_FILE = "Make an Excel file titled Garage Sale Float. Rows: change 40, stickers 6, table 25, subtotal 71."
NOW_WORD = (
    "Now a Word file titled Garage Sale Plan with a heading Setup "
    "and the sentence Bring 71 dollars in change."
)
PUT_EXCEL = (
    "Put those three charges into an Excel file titled utilities_feb "
    "with headers item and amount, and a total row."
)

# Verbatim finals from campaign rows a5b4378cb725 (066 r0) and 188a1f4a875c (032 r0).
EXCEL_PASS = (
    'The Excel file titled "Garage Sale Float" has been created with the following data:\n'
    "\n"
    "| Item     | Price |\n"
    "|----------|-------|\n"
    "| change   | 40    |\n"
    "| stickers | 6     |\n"
    "| table    | 25    |\n"
    "| subtotal | 71    |\n"
    "\n"
    "You can download it from: [Garage_Sale_Float_969565dd.xlsx](out/Garage_Sale_Float_969565dd.xlsx)"
)
WORD_PASS = (
    "Your Word document **Week_Plan_c6cc1d7a.docx** is ready. Here's a quick summary "
    "of what's included:\n"
    "\n"
    "You can download it here: [Week_Plan_c6cc1d7a.docx](/out/Week_Plan_c6cc1d7a.docx)"
)
FAKE_066 = (
    'The Word document titled "Garage Sale Plan" has been created with the following content:\n'
    "\n"
    "# Setup\n"
    "Bring 71 dollars in change.\n"
    "\n"
    "You can download it from: [Garage_Sale_Plan_549e2801.docx](out/Garage_Sale_Plan_549e2801.docx)"
)
FAKE_032 = (
    "Your Word document **Week_Plan_Revised_c9b08c1e.docx** is ready.\n"
    "\n"
    "You can download it here: [Week_Plan_Revised_c9b08c1e.docx](/out/Week_Plan_Revised_c9b08c1e.docx)\n"
    "\n"
    "Let me know if you'd like any changes!"
)
REAL = (
    "Here is your Garage Sale Plan.\n"
    "\n"
    "You can download it from: [Garage_Sale_Plan.docx](out/Garage_Sale_Plan.docx)\n"
)
REAL_URL = "out/Garage_Sale_Plan.docx"


def _tools() -> set[str]:
    return set(OFFERED)


def _history(user0: str, assistant: str, user1: str) -> list[dict[str, str]]:
    return [
        {"role": "user", "content": user0},
        {"role": "assistant", "content": assistant},
        {"role": "user", "content": user1},
    ]


def test_turn0_word_file_stays_unforced_and_followups_select_the_create_tool() -> None:
    # 032 turn 0 passes today without a narrowed schema. A first "Word file" stays on auto.
    assert (
        _select_explicit_required_tool([{"role": "user", "content": WORD_FILE}], _tools()) is None
    )
    assert (
        _select_explicit_required_tool([{"role": "user", "content": EXCEL_FILE}], _tools())
        == "create_excel"
    )
    assert (
        _select_explicit_required_tool(_history(WORD_FILE, WORD_PASS, SECOND_WORD), _tools())
        == "create_word_document"
    )
    assert (
        _select_explicit_required_tool(_history(EXCEL_FILE, EXCEL_PASS, NOW_WORD), _tools())
        == "create_word_document"
    )
    # "Now a Word file" with no prior turn is not a follow-up; the strict matcher still misses it.
    assert _select_explicit_required_tool([{"role": "user", "content": NOW_WORD}], _tools()) is None


def test_followup_does_not_force_a_read_a_lookup_or_two_files() -> None:
    assert (
        _select_explicit_required_tool(
            _history(WORD_FILE, WORD_PASS, "Read the word file and summarize the Friday line."),
            _tools(),
        )
        is None
    )
    assert (
        _select_explicit_required_tool(
            _history(
                "Search knowledge base realuse-v1 for our farmers market note.",
                "Saturdays, stall 14.",
                "And the recycling note — which morning do the bins go out?",
            ),
            _tools(),
        )
        is None
    )
    assert (
        _select_explicit_required_tool(
            _history(
                "With execute_python, print each amount scaled to 12 servings.",
                "Beans 3.0 kg.",
                "And down to 4 servings — print the three scaled amounts.",
            ),
            _tools(),
        )
        is None
    )
    assert (
        _select_explicit_required_tool(
            _history(
                EXCEL_FILE,
                EXCEL_PASS,
                "Create an Excel workbook and a Word document from these notes.",
            ),
            _tools(),
        )
        is None
    )
    assert (
        _select_explicit_required_tool(
            _history(
                "February utilities hit the card in three charges: 38, 29 and 19.",
                "The total is 86.",
                PUT_EXCEL,
            ),
            _tools() - {"create_excel"},
        )
        is None
    )


def test_ungrounded_office_link_is_removed_and_a_created_file_answer_is_unchanged() -> None:
    assert "Garage_Sale_Plan_549e2801.docx" not in strip_unbacked_download_lines(FAKE_066)
    assert "Bring 71 dollars in change." in strip_unbacked_download_lines(FAKE_066)
    assert "/out/Week_Plan_Revised_c9b08c1e.docx" not in strip_unbacked_download_lines(FAKE_032)
    assert "Let me know if you'd like any changes!" in strip_unbacked_download_lines(FAKE_032)
    # Lines with no office link are byte-identical, including a bare "download".
    plain = "The word download appears in the source text.\nBring 71 dollars in change.\n"
    assert strip_unbacked_download_lines(plain) == plain
    kept = ns._apply_non_stream_response(
        {"choices": [{"message": {"role": "assistant", "content": EXCEL_PASS}}]},
        SimpleNamespace(id="offline-test"),
        WS,
        "m",
        0.0,
        successful_creation=True,
    )
    assert json.loads(kept.body)["choices"][0]["message"]["content"] == EXCEL_PASS


def _patch_registry(monkeypatch: pytest.MonkeyPatch, module: object) -> None:
    from portal.platform.inference import tool_registry as registry_mod

    async def refresh() -> None:
        return None

    monkeypatch.setattr(registry_mod.tool_registry, "refresh", refresh)
    monkeypatch.setattr(
        registry_mod.tool_registry,
        "get_openai_tools",
        lambda names: [
            {"type": "function", "function": {"name": name, "parameters": {}}} for name in names
        ],
    )
    monkeypatch.setattr(module, "_resolve_persona_tools", lambda *_a: list(OFFERED))
    monkeypatch.setattr(module, "_model_supports_tools", lambda _m: True)
    monkeypatch.setattr(module, "_inject_omlx_options", lambda body, _ws: dict(body))
    monkeypatch.setattr(module, "_inject_ollama_options", lambda body, _ws: dict(body))
    monkeypatch.setitem(module.WORKSPACES, WS, {})


def _names(body: dict) -> list[str]:
    return [tool["function"]["name"] for tool in body.get("tools") or []]


class _StreamResp:
    def __init__(self, lines: list[str]) -> None:
        self.status_code = 200
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _StreamCtx:
    def __init__(self, resp: _StreamResp) -> None:
        self._resp = resp

    async def __aenter__(self) -> _StreamResp:
        return self._resp

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _sse(content: str = "", call: str | None = None) -> _StreamResp:
    if call:
        chunk = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "c1",
                                "function": {"name": call, "arguments": "{}"},
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    else:
        chunk = {"choices": [{"delta": {"content": content}, "finish_reason": "stop"}]}
    return _StreamResp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


def _joined(raw: bytes) -> str:
    parts: list[str] = []
    for line in raw.decode().splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        for choice in json.loads(line[6:]).get("choices") or []:
            parts.append((choice.get("delta") or {}).get("content") or "")
    return "".join(parts)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("messages", "fake", "gone"),
    [
        (_history(EXCEL_FILE, EXCEL_PASS, NOW_WORD), FAKE_066, "Garage_Sale_Plan_549e2801.docx"),
        (
            _history(WORD_FILE, WORD_PASS, SECOND_WORD),
            FAKE_032,
            "/out/Week_Plan_Revised_c9b08c1e.docx",
        ),
    ],
)
async def test_stream_followup_requires_the_tool_and_drops_the_fake_link(
    monkeypatch: pytest.MonkeyPatch, messages: list, fake: str, gone: str
) -> None:
    _patch_registry(monkeypatch, streaming)
    body, effective, has_tools, _ = await streaming._build_streaming_request(
        {"messages": messages, "model": "m"},
        SimpleNamespace(type="omlx"),
        "m",
        WS,
        "",
    )
    assert has_tools and body["tool_choice"] == "required"
    assert _names(body) == ["create_word_document"]

    posted: list[dict] = []

    class _Client:
        def stream(self, _method: str, _url: str, json: dict | None = None):  # noqa: A002
            posted.append(
                {"tool_choice": json.get("tool_choice"), "messages": list(json["messages"])}
            )
            return _StreamCtx(_sse(fake))

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda _url: "omlx")
    out = b""
    async for chunk in streaming._tool_loop_frames(
        "http://omlx.test/v1/chat/completions", body, WS, "m", "", set(effective)
    ):
        out += chunk

    text = _joined(out)
    assert gone not in text
    assert posted[0]["tool_choice"] == "required"
    assert posted[1]["messages"][-1] == REQUIRED_TOOL_REQUEST
    assert "Bring 71" in text or "Let me know if you'd like any changes!" in text


@pytest.mark.anyio
async def test_stream_followup_keeps_the_answer_when_the_tool_is_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_registry(monkeypatch, streaming)
    messages = _history(EXCEL_FILE, EXCEL_PASS, NOW_WORD)
    body, effective, _, _ = await streaming._build_streaming_request(
        {"messages": messages, "model": "m"},
        SimpleNamespace(type="omlx"),
        "m",
        WS,
        "",
    )
    answers = [_sse(call="create_word_document"), _sse(REAL)]

    class _Client:
        def stream(self, _method: str, _url: str, json: dict | None = None):  # noqa: A002
            return _StreamCtx(answers.pop(0))

    async def dispatch(tc, *_a, **_k):
        assert tc["function"]["name"] == "create_word_document"
        return {
            "role": "tool",
            "tool_call_id": tc.get("id"),
            "name": "create_word_document",
            "content": json.dumps({"success": True, "download_url": REAL_URL}),
        }

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda _url: "omlx")
    monkeypatch.setattr(streaming, "_dispatch_tool_call", dispatch)
    out = b""
    async for chunk in streaming._tool_loop_frames(
        "http://omlx.test/v1/chat/completions", body, WS, "m", "", set(effective)
    ):
        out += chunk
    assert _joined(out) == REAL


class _NSClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.bodies: list[dict] = []

    async def post(self, url: str, json: dict, timeout: object):  # noqa: A002
        self.bodies.append(dict(json))
        resp = self.responses.pop(0)
        resp.request = httpx.Request("POST", url)
        return resp


def _ns_reply(content: str = "", call: str | None = None) -> httpx.Response:
    msg: dict = {"role": "assistant", "content": content}
    if call:
        msg["tool_calls"] = [
            {"id": "c1", "type": "function", "function": {"name": call, "arguments": "{}"}}
        ]
    return httpx.Response(200, json={"choices": [{"message": msg}]})


@pytest.fixture
def ns_followup(monkeypatch: pytest.MonkeyPatch):
    _patch_registry(monkeypatch, ns)
    monkeypatch.setattr(ns, "registry", SimpleNamespace(request_timeout=5.0))
    executed: list[str] = []

    async def dispatch(tc, *_a, **_k):
        executed.append(tc["function"]["name"])
        return {
            "role": "tool",
            "tool_call_id": tc.get("id"),
            "name": tc["function"]["name"],
            "content": json.dumps({"success": True, "download_url": REAL_URL}),
        }

    monkeypatch.setattr(ns, "_dispatch_tool_call", dispatch)
    backend = SimpleNamespace(
        id="b",
        type="omlx",
        chat_url="http://omlx.test/v1/chat/completions",
        models=["m"],
        resolve_model=lambda hint: hint,
    )
    return backend, executed


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("messages", "fake", "gone"),
    [
        (_history(EXCEL_FILE, EXCEL_PASS, NOW_WORD), FAKE_066, "Garage_Sale_Plan_549e2801.docx"),
        (
            _history(WORD_FILE, WORD_PASS, SECOND_WORD),
            FAKE_032,
            "/out/Week_Plan_Revised_c9b08c1e.docx",
        ),
    ],
)
async def test_nonstream_followup_requires_the_tool_and_drops_the_fake_link(
    monkeypatch: pytest.MonkeyPatch, ns_followup, messages: list, fake: str, gone: str
) -> None:
    backend, executed = ns_followup
    client = _NSClient([_ns_reply(fake), _ns_reply(fake)])
    monkeypatch.setattr(ns, "_http_client", client)
    result = await ns._try_non_streaming(
        backend, {"messages": messages, "model": "m"}, WS, 0.0, max_hops=4
    )
    assert result is not None
    text = json.loads(result.body)["choices"][0]["message"]["content"]
    assert _names(client.bodies[0]) == ["create_word_document"]
    assert client.bodies[0]["tool_choice"] == "required"
    assert client.bodies[1]["messages"][-1] == REQUIRED_TOOL_REQUEST
    assert gone not in text and text == strip_unbacked_download_lines(fake)
    assert executed == []


@pytest.mark.anyio
async def test_nonstream_followup_keeps_the_answer_when_the_tool_is_called(
    monkeypatch: pytest.MonkeyPatch, ns_followup
) -> None:
    backend, executed = ns_followup
    messages = _history(WORD_FILE, WORD_PASS, SECOND_WORD)
    client = _NSClient([_ns_reply(call="create_word_document"), _ns_reply(REAL)])
    monkeypatch.setattr(ns, "_http_client", client)
    result = await ns._try_non_streaming(
        backend, {"messages": messages, "model": "m"}, WS, 0.0, max_hops=4
    )
    assert result is not None
    assert json.loads(result.body)["choices"][0]["message"]["content"] == REAL
    assert executed == ["create_word_document"]
    assert client.bodies[0]["tool_choice"] == "required"


@pytest.mark.anyio
async def test_both_paths_leave_a_first_word_file_on_auto(
    monkeypatch: pytest.MonkeyPatch, ns_followup
) -> None:
    """032 turn 0 is a passing 'Make a Word file' that the strict matcher does not narrow."""
    _patch_registry(monkeypatch, streaming)
    streamed, _, _, _ = await streaming._build_streaming_request(
        {"messages": [{"role": "user", "content": WORD_FILE}], "model": "m"},
        SimpleNamespace(type="omlx"),
        "m",
        WS,
        "",
    )
    assert streamed["tool_choice"] == "auto"
    assert set(_names(streamed)) == set(OFFERED)

    backend, _executed = ns_followup
    client = _NSClient([_ns_reply("Week plan noted.")])
    monkeypatch.setattr(ns, "_http_client", client)
    result = await ns._try_non_streaming(
        backend,
        {"messages": [{"role": "user", "content": WORD_FILE}], "model": "m"},
        WS,
        0.0,
    )
    assert result is not None
    assert client.bodies[0]["tool_choice"] == "auto"
    assert set(_names(client.bodies[0])) == set(OFFERED)
    assert json.loads(result.body)["choices"][0]["message"]["content"] == "Week plan noted."


# Produce verb + office noun, but no request for the assistant to produce a file.
HOWTO_EXCEL = "How do I make a pivot table in Excel?"
EXPLAIN_WORD = "Can you explain how to update a Word doc's TOC?"
BESTWAY_PPT = "What's the best way to build a slide deck?"
EDIT_MYSELF = "I'll edit the spreadsheet myself, thanks"
MORE_NON_PRODUCE = (
    "How do I open the file on my iPad tonight?",
    "Can you explain what a pivot table is before I build one?",
    "I'll fill in the last two rows myself over the weekend.",
)


def test_followup_howto_and_first_person_turns_never_force_a_file_tool() -> None:
    for turn in (HOWTO_EXCEL, EXPLAIN_WORD, BESTWAY_PPT, EDIT_MYSELF, *MORE_NON_PRODUCE):
        assert (
            _select_explicit_required_tool(_history(EXCEL_FILE, EXCEL_PASS, turn), _tools()) is None
        )


WHERE_AGAIN = "Where can I get the Garage Sale Float file again?"
REPEAT_LINK_REPLY = (
    "You already have it from the first step.\n"
    "\n"
    "Download it here: [Garage_Sale_Float_969565dd.xlsx](out/Garage_Sale_Float_969565dd.xlsx)"
)
INVENTED_NAME = "Summary_Notes_83ba1f.docx"
BOTH_REPLY = (
    "Here are both files.\n"
    "\n"
    "Download the notes: [Summary_Notes_83ba1f.docx](out/Summary_Notes_83ba1f.docx)\n"
    "Download the float: [Garage_Sale_Float_969565dd.xlsx](out/Garage_Sale_Float_969565dd.xlsx)"
)
REPEAT_HISTORY = _history(EXCEL_FILE, EXCEL_PASS, WHERE_AGAIN)


def test_a_link_to_a_file_created_in_an_earlier_turn_is_kept() -> None:
    """The prior tool result made this file real: the repeated link survives the strip."""
    assert "Garage_Sale_Float_969565dd.xlsx" in REPEAT_HISTORY[1]["content"]
    assert _select_explicit_required_tool(REPEAT_HISTORY, _tools()) is None
    names = prior_office_filenames(REPEAT_HISTORY)
    assert names == {"Garage_Sale_Float_969565dd.xlsx"}
    kept = strip_unbacked_download_lines(REPEAT_LINK_REPLY, names)
    assert "Garage_Sale_Float_969565dd.xlsx" in kept
    assert "You already have it from the first step." in kept
    kept_default = ns._apply_non_stream_response(
        {"choices": [{"message": {"role": "assistant", "content": REPEAT_LINK_REPLY}}]},
        SimpleNamespace(id="offline-test"),
        WS,
        "m",
        0.0,
        keep_names=names,
    )
    assert (
        "Garage_Sale_Float_969565dd.xlsx"
        in json.loads(kept_default.body)["choices"][0]["message"]["content"]
    )


def test_an_invented_name_is_stripped_even_alongside_a_real_earlier_name() -> None:
    stripped = strip_unbacked_download_lines(BOTH_REPLY, prior_office_filenames(REPEAT_HISTORY))
    assert INVENTED_NAME not in stripped
    assert "Garage_Sale_Float_969565dd.xlsx" in stripped


@pytest.mark.anyio
async def test_nonstream_keeps_an_earlier_turn_link_and_strips_an_invented_one(
    monkeypatch: pytest.MonkeyPatch, ns_followup
) -> None:
    backend, executed = ns_followup
    client = _NSClient([_ns_reply(BOTH_REPLY)])
    monkeypatch.setattr(ns, "_http_client", client)
    result = await ns._try_non_streaming(
        backend, {"messages": REPEAT_HISTORY, "model": "m"}, WS, 0.0, max_hops=4
    )
    assert result is not None
    text = json.loads(result.body)["choices"][0]["message"]["content"]
    assert executed == []
    assert INVENTED_NAME not in text
    assert "Garage_Sale_Float_969565dd.xlsx" in text


@pytest.mark.anyio
async def test_stream_keeps_an_earlier_turn_link_and_strips_an_invented_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_registry(monkeypatch, streaming)
    body, effective, has_tools, _ = await streaming._build_streaming_request(
        {"messages": REPEAT_HISTORY, "model": "m"},
        SimpleNamespace(type="omlx"),
        "m",
        WS,
        "",
    )
    assert has_tools and body["tool_choice"] == "auto"

    class _Client:
        def stream(self, _method: str, _url: str, json: dict | None = None):  # noqa: A002
            return _StreamCtx(_sse(BOTH_REPLY))

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda _url: "omlx")
    out = b""
    async for chunk in streaming._tool_loop_frames(
        "http://omlx.test/v1/chat/completions", body, WS, "m", "", set(effective)
    ):
        out += chunk
    text = _joined(out)
    assert INVENTED_NAME not in text
    assert "Garage_Sale_Float_969565dd.xlsx" in text


# ru-v1-006 (realuse_s8_fast_followup_20261106, r0): turn 1's create request rode on
# an attachment turn, so OWUI v0.12.5 had prepended the rendered rag_template with the
# <context> excerpts to the user's words (utils/misc.py update_message_content,
# append=False) — the template's "explain" used to trip _NON_PRODUCE_RE and every
# attachment turn lost forcing.
TURN0 = (
    "Read all four notes: note_01.docx, note_02.docx, note_03.docx, and note_04.docx. "
    "What do they agree on, and where do they clash?"
)
TURN1 = "Make a Word file titled Meeting Themes Summary. Include a heading for the clash and both months."
TURN0_REPLY = (
    "The notes agree the launch is Priya's; they clash on the date: "
    "September (note_01.docx) versus October (note_03.docx)."
)
_RAG_TEMPLATE = (
    Path(__file__).resolve().parents[2] / "imports" / "openwebui" / "rag_template.txt"
).read_text(encoding="utf-8")


def _sources(*bodies: str) -> str:
    return "".join(
        f'<source id="{i}" name="note_0{i}.docx" resource-type="file" '
        f'resource-id="realuse_v1/ru-v1-006/note_0{i}.docx">{body}</source>\n'
        for i, body in enumerate(bodies, 1)
    ).strip()


def _wrapped(user_text: str, context: str) -> str:
    return _RAG_TEMPLATE.replace("{{CONTEXT}}", context) + "\n" + user_text


def test_own_user_text_strips_the_owui_rag_wrapper() -> None:
    wrapped = _wrapped(TURN1, _sources("Launch target is September. Owner: Priya."))
    assert _own_user_text([{"role": "user", "content": wrapped}]) == TURN1
    assert _own_user_text([{"role": "user", "content": NOW_WORD}]) == NOW_WORD


def test_own_user_text_strips_a_wrapper_on_multimodal_content() -> None:
    content = [
        {"type": "text", "text": _wrapped(TURN1, _sources("Budget is frozen."))},
        {"type": "text", "text": "Second part."},
    ]
    assert _own_user_text([{"role": "user", "content": content}]) == f"{TURN1} Second part."


def test_wrapped_006_turn1_still_selects_create_word_document() -> None:
    wrapped = _wrapped(TURN1, _sources("Launch target is September.", "Budget is frozen."))
    assert (
        _select_explicit_required_tool(_history(TURN0, TURN0_REPLY, wrapped), _tools())
        == "create_word_document"
    )


def test_wrapped_howto_question_stays_unforced() -> None:
    wrapped = _wrapped(HOWTO_EXCEL, _sources("Budget is frozen."))
    assert _select_explicit_required_tool(_history(TURN0, TURN0_REPLY, wrapped), _tools()) is None


def test_excerpts_containing_howto_phrasing_do_not_block_a_create() -> None:
    wrapped = _wrapped(
        TURN1,
        _sources("How do I file this? See the guide.", "What is the best way to store these?"),
    )
    assert (
        _select_explicit_required_tool(_history(TURN0, TURN0_REPLY, wrapped), _tools())
        == "create_word_document"
    )
