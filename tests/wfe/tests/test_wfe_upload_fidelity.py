"""Golden Open WebUI v0.12.5 RAG prepends, and context-grounded read checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.wfe import campaign, runner
from tests.wfe.checkers import (
    CheckContext,
    CheckResult,
    check_tool_grounded,
    expect_tools_verdict,
)
from tests.wfe.owui_rag import chunk_file, rag_prefix, split_text
from tests.wfe.schema import Outcome
from tests.wfe.upload_fidelity import rendered_user, row_instrument, turn_injection, user_text

_SUITE = Path(__file__).resolve().parents[1] / "suites" / "realuse_v1.jsonl"
_REPO = Path(__file__).resolve().parents[3]
_LONG = ("word " * 400) + "\n\n" + ("tail " * 400)
_LONG_SHA = "5c07ec79a1dc17d7981108e346501e6e05eb6e9b06561ee27e14059012ef314a"


def _task(task_id: str) -> dict:
    for line in _SUITE.read_text().splitlines():
        item = json.loads(line)
        if item["id"] == task_id:
            return item
    raise AssertionError(task_id)


def _users(task: dict) -> list[str]:
    return [user_text(turn.get("user")) for turn in task["turns"]]


def _invoice_message() -> str:
    return (
        "### Task:\nRespond to the user query using the provided context, incorp"
        "orating inline citations in the format [id] **only when the <source> t"
        'ag includes an explicit id attribute** (e.g., <source id="1">).\n\n### G'
        "uidelines:\n- If you don't know the answer, clearly state that.\n- If un"
        "certain, ask the user for clarification.\n- Respond in the same languag"
        "e as the user's query.\n- If the context is unreadable or of poor quali"
        "ty, inform the user and provide the best possible answer.\n- If the ans"
        "wer isn't present in the context but you possess the knowledge, explai"
        "n this to the user and provide the answer using your own understanding"
        ".\n- **Only include inline citations using [id] (e.g., [1], [2]) when t"
        "he <source> tag includes an id attribute.**\n- Do not cite if the <sour"
        "ce> tag does not contain an id attribute.\n- The context holds excerpts"
        " of attached files. When the full file matters (data, code, totals, or"
        " running a script), use the attached-file path with your tools instead"
        " of answering from excerpts.\n- Do not use XML tags in you"
        "r response.\n- Ensure citations are concise and directly related to the"
        " information provided.\n\n### Example of Citation:\nIf the user asks abou"
        "t a specific topic and the information is found in a source with a pro"
        "vided id attribute, the response should include the citation like in t"
        'he following example:\n* "According to the study, the proposed method i'
        'ncreases efficiency by 20% [1]."\n\n### Output:\nProvide a clear and dire'
        "ct response to the user's query, including inline citations in the for"
        "mat [id] only when the <source> tag with id attribute is present in th"
        'e context.\n\n<context>\n<source id="1" name="final_invoice.pdf" resource'
        '-type="file" resource-id="realuse_v1/ru-v1-001/final_invoice.pdf">Time'
        "line slipped by 3 days\nlabor 2400\nmaterials 890\nmisc supplies 340\nperm"
        "it 180\ncleanup 210\nsubtotal 4020</source>\n</context>\n\nI need a short t"
        "hank-you note for the client. The invoice is final_invoice.pdf. Mentio"
        "n that the timeline slipped by 3 days, and list every charge that is o"
        "n the invoice."
    )


def _notes_message() -> str:
    return (
        "### Task:\nRespond to the user query using the provided context, incorp"
        "orating inline citations in the format [id] **only when the <source> t"
        'ag includes an explicit id attribute** (e.g., <source id="1">).\n\n### G'
        "uidelines:\n- If you don't know the answer, clearly state that.\n- If un"
        "certain, ask the user for clarification.\n- Respond in the same languag"
        "e as the user's query.\n- If the context is unreadable or of poor quali"
        "ty, inform the user and provide the best possible answer.\n- If the ans"
        "wer isn't present in the context but you possess the knowledge, explai"
        "n this to the user and provide the answer using your own understanding"
        ".\n- **Only include inline citations using [id] (e.g., [1], [2]) when t"
        "he <source> tag includes an id attribute.**\n- Do not cite if the <sour"
        "ce> tag does not contain an id attribute.\n- The context holds excerpts"
        " of attached files. When the full file matters (data, code, totals, or"
        " running a script), use the attached-file path with your tools instead"
        " of answering from excerpts.\n- Do not use XML tags in you"
        "r response.\n- Ensure citations are concise and directly related to the"
        " information provided.\n\n### Example of Citation:\nIf the user asks abou"
        "t a specific topic and the information is found in a source with a pro"
        "vided id attribute, the response should include the citation like in t"
        'he following example:\n* "According to the study, the proposed method i'
        'ncreases efficiency by 20% [1]."\n\n### Output:\nProvide a clear and dire'
        "ct response to the user's query, including inline citations in the for"
        "mat [id] only when the <source> tag with id attribute is present in th"
        'e context.\n\n<context>\n<source id="1" name="drive_notes.docx" resource-'
        'type="file" resource-id="realuse_v1/ru-v1-002/drive_notes.docx">Denver'
        " to Boulder: 45 minutes. Eat at The Kitchen.  \nBoulder to Vail: 2 hour"
        "s. Eat at Sweet Basil. Stop for 90 minutes if the day is tight.  \nVail"
        " to Grand Junction: 3 hours. Eat at Bin 707.  \nGrand Junction to Moab:"
        " 1 hour 30 minutes.  \nSnow advisory: I-70 westbound Tuesday and Wednes"
        "day. Pack tire chains.</source>\n</context>\n\nRead drive_notes.docx and "
        "give me the drive plan. I need each leg's time and where to eat."
    )


def test_pdf_prepend_matches_the_v0125_template() -> None:
    task = _task("ru-v1-001")
    message = rendered_user("pipeline", task, 0)
    assert message == _invoice_message()
    assert message.startswith("### Task:\n")
    tag = (
        '<source id="1" name="final_invoice.pdf" resource-type="file" '
        'resource-id="realuse_v1/ru-v1-001/final_invoice.pdf">'
    )
    assert tag in message
    assert "Timeline slipped by 3 days" in message
    assert message.endswith("\n" + task["turns"][0]["user"])
    prefix = turn_injection("pipeline", task, 0, _users(task)).prefix
    assert "thank-you" not in prefix


def test_docx_prepend_matches_the_v0125_template() -> None:
    task = _task("ru-v1-002")
    message = rendered_user("pipeline", task, 0)
    assert message == _notes_message()
    tag = (
        '<source id="1" name="drive_notes.docx" resource-type="file" '
        'resource-id="realuse_v1/ru-v1-002/drive_notes.docx">'
    )
    assert tag in message
    assert "The Kitchen" in message and "tire chains" in message
    # Blank paragraphs are joined with two spaces, as the markdown header splitter does.
    assert "  \n" in message
    assert message.endswith("\n" + task["turns"][0]["user"])


def test_long_text_split_matches_the_locked_langchain_chunks() -> None:
    chunks = split_text(_LONG)
    assert [len(chunk) for chunk in chunks] == [1499, 599, 1499, 599]
    assert chunks[2].startswith("tail ")
    digest = hashlib.sha256("\n--\n".join(chunks).encode()).hexdigest()
    assert digest == _LONG_SHA


def test_a_file_waits_for_the_turn_that_names_it() -> None:
    task = _task("ru-v1-003")
    users = _users(task)
    assert turn_injection("pipeline", task, 0, users).prefix == ""
    named = turn_injection("pipeline", task, 1, users)
    assert named.file_ids == ["realuse_v1/ru-v1-003/manager_notes.docx"]
    assert named.chunks == 1 and named.ranked_standin is False
    assert turn_injection("ollama", task, 1, users).prefix == ""


def test_a_repo_fixture_is_not_an_upload() -> None:
    task = _task("ru-v1-012")
    users = _users(task)
    assert turn_injection("pipeline", task, 0, users).file_ids == []
    assert turn_injection("pipeline", task, 1, users).file_ids == []


def test_images_stay_off_the_rag_path() -> None:
    for task_id in ("ru-v1-025", "ru-v1-026", "ru-v1-033"):
        task = _task(task_id)
        injection = turn_injection("pipeline", task, 0, _users(task))
        assert injection.file_ids == [] and injection.prefix == ""


def test_a_directory_mention_injects_the_csv_only() -> None:
    task = _task("ru-v1-005")
    injection = turn_injection("pipeline", task, 0, _users(task))
    assert injection.file_ids == ["realuse_v1/ru-v1-005/customers.csv"]
    assert injection.chunks == 3 and injection.ranked_standin is True


def test_csv_fixtures_over_top_k_use_the_stand_in() -> None:
    names = {
        "ru-v1-005": "customers.csv",
        "ru-v1-008": "orders.csv",
        "ru-v1-022": "survey.csv",
        "ru-v1-035": "adopted.csv",
    }
    for task_id, name in names.items():
        task = _task(task_id)
        injection = turn_injection("pipeline", task, 0, _users(task))
        assert injection.file_ids == [f"realuse_v1/{task_id}/{name}"]
        assert injection.chunks == 3 and injection.ranked_standin is True


def test_a_code_fixture_beside_a_pdf_is_not_injected() -> None:
    task = _task("ru-v1-048")
    injection = turn_injection("pipeline", task, 1, _users(task))
    assert injection.file_ids == ["realuse_v1/ru-v1-048/changelog.pdf"]
    assert injection.ranked_standin is False


def test_prefix_stays_on_the_current_user_message_only(monkeypatch) -> None:
    monkeypatch.setattr(runner, "ENGINE", "pipeline")
    task = _task("ru-v1-003")
    sandbox = type("Box", (), {"root": Path("/")})()
    loop = runner._Loop("m", task, sandbox, [], None, None, False)
    loop.open_turn(0, loop.scripted[0])
    assert loop.messages[-1]["content"] == task["turns"][0]["user"]
    loop.open_turn(1, loop.scripted[1])
    assert loop.messages[1]["content"] == task["turns"][0]["user"]
    assert loop.messages[-1]["content"].startswith("### Task:\n")
    assert loop.messages[-1]["content"].endswith("\n" + task["turns"][1]["user"])
    assert loop._owui_context.startswith("### Task:\n")
    assert "30 min max" in loop._owui_context


def test_context_grounds_a_read_and_a_real_tool_still_wins() -> None:
    task = _task("ru-v1-001")
    spec = task["turns"][0]["checks"][0]
    prefix = turn_injection("pipeline", task, 0, _users(task)).prefix
    grounded = check_tool_grounded(spec, CheckContext(owui_context=prefix))
    assert grounded.outcome == Outcome.PASS
    assert grounded.evidence["grounded_by"] == "owui_context"
    via_tool = check_tool_grounded(
        spec,
        CheckContext(owui_context=prefix, tool_calls=[{"name": "read_pdf", "output": prefix}]),
    )
    assert via_tool.evidence["grounded_by"] == "read_pdf"
    question_only = check_tool_grounded(
        {"tools": ["read_pdf"], "evidence": ["thank-you"]},
        CheckContext(owui_context=prefix),
    )
    assert question_only.outcome == Outcome.FAIL
    assert check_tool_grounded(spec, CheckContext()).outcome == Outcome.FAIL


def test_four_notes_are_grounded_from_one_prefix() -> None:
    task = _task("ru-v1-006")
    prefix = turn_injection("pipeline", task, 0, _users(task)).prefix
    ctx = CheckContext(owui_context=prefix)
    checks = [item for item in task["turns"][0]["checks"] if item["type"] == "tool_grounded"]
    assert len(checks) == 4
    assert all(check_tool_grounded(spec, ctx).outcome == Outcome.PASS for spec in checks)


def test_non_read_tools_stay_required() -> None:
    missing, carried = expect_tools_verdict(
        {"expect_tools": ["execute_python", "create_word_document"], "checks": []},
        set(),
        CheckResult(Outcome.PASS, "", {}),
        [],
    )
    assert missing == ["execute_python", "create_word_document"] and carried == []
    task = _task("ru-v1-001")
    prefix = turn_injection("pipeline", task, 0, _users(task)).prefix
    refused = check_tool_grounded(
        {"tools": ["execute_python"], "evidence": ["2400"]},
        CheckContext(owui_context=prefix),
    )
    assert refused.outcome == Outcome.FAIL
    assert _task("ru-v1-018")["turns"][1]["expect_tools"] == ["create_word_document"]
    assert _task("ru-v1-048")["turns"][1]["expect_tools"] == ["execute_python"]
    assert task["turns"][0]["expect_tools"] == []
    assert task["turns"][0]["checks"][0]["tools"] == ["read_pdf"]
    kept = _task("ru-v1-012")["turns"][0]["expect_tools"]
    assert kept == ["explore_repository", "read_text_file"]


def test_row_instrument_records_the_rag_shape() -> None:
    delivered = {
        "shape": "owui_rag_v0.12.5+portal_filter_v1",
        "turns": [{"turn": 0, "files": ["realuse_v1/ru-v1-001/final_invoice.pdf"]}],
        "chunks": 1,
        "ranked_standin": False,
    }
    instrument = row_instrument({"fingerprint": "abc"}, {"upload_delivery": delivered})
    assert instrument["upload"] == delivered
    assert (
        campaign.instrument_fingerprint()["upload_delivery"] == "owui-rag-v0.12.5+portal-filter-v1"
    )


def test_pipeline_payload_carries_the_forwarded_attachments(monkeypatch) -> None:
    """Production-faithful pipeline body: the inlet filter's field, with the staged
    path each fixture really has; OWUI pops `files` before this hop, so it is absent."""
    monkeypatch.setattr(runner, "ENGINE", "pipeline")
    task = _task("ru-v1-005")
    injection = turn_injection("pipeline", task, 0, _users(task))
    _, payload, _ = runner._build_pipeline(
        "auto-daily",
        [{"role": "user", "content": _users(task)[0]}],
        "none",
        {},
        None,
        "default",
        False,
        None,
        None,
        injection.attachments,
    )
    assert payload["portal_attached_files"] == [
        {
            "id": "realuse_v1/ru-v1-005/customers.csv",
            "name": "customers.csv",
            "type": "file",
            "size": Path(_REPO / "tests/fixtures/realuse_v1/ru-v1-005/customers.csv")
            .stat()
            .st_size,
            "path": "/workspace/uploads/realuse_v1/ru-v1-005/customers.csv",
        }
    ]
    assert "files" not in payload
    # Direct engines carry neither the field nor the RAG prefix.
    direct = turn_injection("ollama", task, 0, _users(task))
    assert direct.attachments == [] and direct.prefix == ""


def test_docx_attachments_wait_for_their_turn_and_note_the_staged_path(monkeypatch) -> None:
    """The docx case: attachment rides the turn that names it, and the pipeline note
    the forwarded field produces carries the staged path the fixture is staged at."""
    from portal.platform.inference.router.preinject import _inject_attached_files

    task = _task("ru-v1-003")
    users = _users(task)
    assert turn_injection("pipeline", task, 0, users).attachments == []
    injection = turn_injection("pipeline", task, 1, users)
    assert injection.attachments == [
        {
            "id": "realuse_v1/ru-v1-003/manager_notes.docx",
            "name": "manager_notes.docx",
            "type": "file",
            "size": Path(_REPO / "tests/fixtures/realuse_v1/ru-v1-003/manager_notes.docx")
            .stat()
            .st_size,
            "path": "/workspace/uploads/realuse_v1/ru-v1-003/manager_notes.docx",
        }
    ]
    noted = _inject_attached_files(
        {
            "messages": [{"role": "user", "content": users[1]}],
            "portal_attached_files": injection.attachments,
        }
    )
    note = noted["messages"][-1]["content"]
    assert (
        "[Attached file — id: 'realuse_v1/ru-v1-003/manager_notes.docx', "
        "name: 'manager_notes.docx', type: 'file', "
        "path: '/workspace/uploads/realuse_v1/ru-v1-003/manager_notes.docx']" in note
    )


def test_the_template_is_stock_plus_exactly_the_portal_guideline() -> None:
    from tests.wfe.owui_rag import DEFAULT_RAG_TEMPLATE, PORTAL_RAG_GUIDELINE, PORTAL_RAG_TEMPLATE

    stock_lines = set(DEFAULT_RAG_TEMPLATE.splitlines())
    portal_lines = PORTAL_RAG_TEMPLATE.splitlines()
    added = [line for line in portal_lines if line not in stock_lines]
    assert added == [PORTAL_RAG_GUIDELINE]
    prefix = rag_prefix("<context-x>", "q")
    assert prefix.startswith("### Task:\n")
    assert PORTAL_RAG_GUIDELINE in prefix and "{{CONTEXT}}" not in prefix


def test_xlsx_and_pptx_use_the_unstructured_missing_fallback(tmp_path: Path) -> None:
    import openpyxl
    from pptx import Presentation

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Costs"
    sheet["A1"] = "item"
    sheet["A2"] = "nails"
    book.save(tmp_path / "costs.xlsx")
    kept, raw = chunk_file(tmp_path / "costs.xlsx", ".xlsx")
    assert raw == 1 and "Sheet: Costs" in kept[0] and "nails" in kept[0]
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    slide.shapes.add_textbox(0, 0, 100, 100).text_frame.text = "Q3 review"
    deck.save(tmp_path / "deck.pptx")
    kept, raw = chunk_file(tmp_path / "deck.pptx", ".pptx")
    assert raw == 1 and kept[0].startswith("Slide 1:") and "Q3 review" in kept[0]
