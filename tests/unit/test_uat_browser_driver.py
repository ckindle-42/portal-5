"""Offline tests for the Stage 5 browser-GUI driver and multi-turn persistence."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from tests.qat import runner
from tests.qat import uat_behavioral as uat
from tests.qat.browser_ui import (
    CHAT_INPUT_SELECTOR,
    STOP_CIRCLE_SELECTOR,
    BrowserUI,
    PlaywrightUnavailable,
)
from tests.qat.config import Settings
from tests.qat.models import QATScenario, Status
from tests.qat.owui_client import ArtifactDownloadError, OWUIClient


def _settings(tmp_path: Path) -> Settings:
    return Settings.load(
        env_file=tmp_path / "missing.env",
        environ={
            "OPENWEBUI_URL": "http://localhost:8080",
            "PIPELINE_URL": "http://localhost:9099",
            "PIPELINE_API_KEY": "test-key",
            "OPENWEBUI_ADMIN_EMAIL": "admin@portal.local",
            "OPENWEBUI_ADMIN_PASSWORD": "pw",
            "AI_OUTPUT_DIR": str(tmp_path / "AI_Output"),
        },
    )


def _scenario(case: uat.UATCase) -> QATScenario:
    return QATScenario(
        case.scenario_id,
        case.title,
        5,
        uat.UAT_PHASE,
        1,
        case.model_slug,
        kind="uat",
        prompts=case.prompts,
    )


# ----------------------------------------------------------- OWUIClient Turn 2+


def test_send_turn_persists_user_node_before_completions(tmp_path: Path) -> None:
    events: list[tuple[str, str]] = []
    persisted: dict = {}
    completions: list[dict] = []
    store: dict = {}
    current: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        events.append((request.method, path))
        if path == "/api/v1/chats/new":
            chat = json.loads(request.content)["chat"]
            store.update(chat["history"]["messages"])
            current["id"] = chat["history"]["currentId"]
            return httpx.Response(201, json={"id": "chat-1"})
        if path == "/api/chat/completions":
            body = json.loads(request.content)
            completions.append(body)
            mid = body["id"]
            store[mid] = {
                **store.get(mid, {}),
                "id": mid,
                "role": "assistant",
                "content": f"answer {len(completions)}",
                "done": True,
            }
            return httpx.Response(200, json={})
        if path == "/api/v1/chats/chat-1" and request.method == "GET":
            return httpx.Response(
                200,
                json={"chat": {"history": {"messages": store, "currentId": current["id"]}}},
            )
        if path == "/api/v1/chats/chat-1" and request.method == "POST":
            body = json.loads(request.content)
            persisted["body"] = body
            history = body["chat"]["history"]
            store.clear()
            store.update(history["messages"])
            current["id"] = history["currentId"]
            return httpx.Response(200, json={"id": "chat-1"})
        return httpx.Response(404)

    client = OWUIClient(_settings(tmp_path), httpx.MockTransport(handler))
    chat_id = client.create_chat("token", "auto-coding", "UAT", "first question")
    turn1_assistant = current["id"]
    client.send_turn("token", chat_id, "auto-coding", "first question")
    client.send_turn("token", chat_id, "auto-coding", "second question")

    history = persisted["body"]["chat"]["history"]
    messages = history["messages"]
    new_user = next(
        m for m in messages.values() if m["role"] == "user" and m["content"] == "second question"
    )
    new_assistant = messages[new_user["childrenIds"][0]]
    assert new_user["parentId"] == turn1_assistant
    assert new_user["models"] == ["auto-coding"]
    assert new_assistant["parentId"] == new_user["id"]
    assert new_assistant["content"] == "" and new_assistant["done"] is False
    assert history["currentId"] == new_assistant["id"]
    assert new_user["id"] in messages[turn1_assistant]["childrenIds"]
    assert completions[1]["id"] == new_assistant["id"]

    comp_indexes = [i for i, (_, p) in enumerate(events) if p == "/api/chat/completions"]
    persist_indexes = [
        i for i, (m, p) in enumerate(events) if m == "POST" and p == "/api/v1/chats/chat-1"
    ]
    get_indexes = [
        i for i, (m, p) in enumerate(events) if m == "GET" and p == "/api/v1/chats/chat-1"
    ]
    assert len(persist_indexes) == 1  # Turn 1 must not re-post the chat
    assert get_indexes[-1] < persist_indexes[-1] < comp_indexes[1]


def test_send_turn_turn2_raises_when_history_unavailable(tmp_path: Path) -> None:
    completions: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/chats/new":
            return httpx.Response(201, json={"id": "chat-1"})
        if request.url.path == "/api/chat/completions":
            completions.append(json.loads(request.content))
            return httpx.Response(200, json={})
        return httpx.Response(404)  # GET chat detail fails -> no orphaned turn

    client = OWUIClient(_settings(tmp_path), httpx.MockTransport(handler))
    chat_id = client.create_chat("token", "auto", "UAT", "first")
    client.send_turn("token", chat_id, "auto", "first")
    with pytest.raises(RuntimeError):
        client.send_turn("token", chat_id, "auto", "second")
    assert len(completions) == 1  # second turn never reached completions


# ------------------------------------------------------- run_case driver choice


def test_run_case_dispatch_browser_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    case = uat.UATCase("s5-x", "t", "auto", ("p",), "route")
    scenario = _scenario(case)
    monkeypatch.setattr(uat, "discover_cases", lambda discovery, **kw: (case,))
    calls: list[str] = []
    ok = uat.QATResult(scenario.scenario_id, Status.PASS, "ok")
    monkeypatch.setattr(uat, "_run_browser_case", lambda *a: calls.append("browser") or ok)
    monkeypatch.setattr(uat, "_run_chat_case", lambda *a: calls.append("api") or ok)
    monkeypatch.setattr(uat, "_run_memory_case", lambda *a: calls.append("memory") or ok)
    state = SimpleNamespace(discovery=object())
    settings = _settings(tmp_path)

    uat.run_case(settings, scenario, state, SimpleNamespace(api_only=False))
    assert calls == ["browser"]
    calls.clear()
    uat.run_case(settings, scenario, state, object())  # no api_only attribute -> browser
    assert calls == ["browser"]
    calls.clear()
    uat.run_case(settings, scenario, state, SimpleNamespace(api_only=True))
    assert calls == ["api"]


class FakeOWUIClient:
    def __init__(self, settings) -> None:
        self.settings = settings

    def signin(self) -> str:
        return "token"

    def lookup_trace(self, **kw) -> dict:
        return {
            "model": "served-model",
            "backend": "omlx",
            "workspace": kw.get("model_slug", ""),
            "spans": [],
        }

    def download_artifact(self, token: str, url: str) -> bytes:
        return b"data"


class FakeBrowserUI:
    instances: list[FakeBrowserUI] = []
    inject_page_error = False
    orphan_users = False

    def __init__(self, settings, shots_dir) -> None:
        self.settings = settings
        self.shots_dir = shots_dir
        self.calls: list = []
        self.prompts: list[str] = []
        self.page_errors: list[str] = []
        self._visible = (0, 0)
        FakeBrowserUI.instances.append(self)

    def start(self) -> None:
        self.calls.append("start")

    def stop(self) -> None:
        self.calls.append("stop")

    def login(self) -> None:
        self.calls.append("login")

    def new_chat(self) -> None:
        self.calls.append("new_chat")
        self._visible = (0, 0)

    def select_model(self, slug: str, display_name: str = "") -> None:
        self.calls.append(("select_model", slug, display_name))

    def inspect_and_manage_tools(self, expected_tools=()) -> dict:
        self.calls.append("inspect_tools")
        return {"available": False, "tools": [], "toggles": {}, "missing": list(expected_tools)}

    def send_turn(self, prompt: str, upload_path=None, max_wait_s: float = 240.0) -> str:
        self.calls.append(("send_turn", prompt, upload_path))
        self.prompts.append(prompt)
        users, assistants = self._visible
        assistants += 1
        if not FakeBrowserUI.orphan_users:
            users += 1
        self._visible = (users, assistants)
        if FakeBrowserUI.inject_page_error:
            self.page_errors.append("Uncaught TypeError: boom")
        return f"answer to: {prompt}"

    def current_chat_id(self) -> str:
        return "chat-gui-1"

    def visible_turn_count(self) -> tuple[int, int]:
        return self._visible

    def last_artifact_links(self) -> tuple[str, ...]:
        return ()

    def screenshot(self, name: str) -> Path:
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        path = self.shots_dir / f"{name}.png"
        path.write_bytes(b"png")
        return path

    def result_errors(self) -> dict:
        return {"console": [], "page_errors": list(self.page_errors)}


def _wire_browser(monkeypatch: pytest.MonkeyPatch, case: uat.UATCase) -> None:
    monkeypatch.setattr(uat, "discover_cases", lambda discovery, **kw: (case,))
    monkeypatch.setattr(uat, "BrowserUI", FakeBrowserUI)
    monkeypatch.setattr(uat, "OWUIClient", FakeOWUIClient)
    monkeypatch.setattr(runner, "_primary_model_failure", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_finalize_chat", lambda *a, **k: (True, ""))


def _state(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(discovery=SimpleNamespace(presets={}, personas=()), run_dir=tmp_path)


def test_browser_case_records_driver_and_visible_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    FakeBrowserUI.instances.clear()
    case = uat.UATCase(
        "s5-x",
        "t",
        "auto-coding",
        ("question one", "question two"),
        "route",
        {"target": "auto-coding"},
    )
    _wire_browser(monkeypatch, case)
    result = uat.run_case(
        _settings(tmp_path), _scenario(case), _state(tmp_path), SimpleNamespace(api_only=False)
    )
    assert result.status is Status.PASS
    assert result.evidence["driver"] == "browser_gui"
    assert result.evidence["visible_turns"] == {"user": 2, "assistant": 2}
    assert "screenshot" in result.evidence
    ui = FakeBrowserUI.instances[-1]
    assert ui.prompts == ["question one", "question two"]
    assert ("select_model", "auto-coding", "") in ui.calls
    assert "new_chat" in ui.calls and "stop" in ui.calls


def test_browser_case_fails_on_page_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    FakeBrowserUI.instances.clear()
    monkeypatch.setattr(FakeBrowserUI, "inject_page_error", True)
    case = uat.UATCase(
        "s5-x", "t", "auto-coding", ("question",), "route", {"target": "auto-coding"}
    )
    _wire_browser(monkeypatch, case)
    result = uat.run_case(
        _settings(tmp_path), _scenario(case), _state(tmp_path), SimpleNamespace(api_only=False)
    )
    assert result.status is Status.FAIL
    assert "browser page errors" in result.detail
    assert result.evidence["driver"] == "browser_gui"


def test_browser_case_fails_on_orphaned_user_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    FakeBrowserUI.instances.clear()
    monkeypatch.setattr(FakeBrowserUI, "orphan_users", True)
    case = uat.UATCase(
        "s5-x", "t", "auto-coding", ("one", "two"), "route", {"target": "auto-coding"}
    )
    _wire_browser(monkeypatch, case)
    result = uat.run_case(
        _settings(tmp_path), _scenario(case), _state(tmp_path), SimpleNamespace(api_only=False)
    )
    assert result.status is Status.FAIL
    assert "user prompts" in result.detail
    assert result.evidence["visible_turns"] == {"user": 0, "assistant": 2}


def test_playwright_unavailable_fails_without_api_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    case = uat.UATCase("s5-x", "t", "auto", ("p",), "route")
    monkeypatch.setattr(uat, "discover_cases", lambda discovery, **kw: (case,))
    monkeypatch.setattr(uat, "OWUIClient", FakeOWUIClient)
    api_called: list[int] = []
    monkeypatch.setattr(uat, "_run_chat_case", lambda *a: api_called.append(1))

    class UnavailableUI:
        def __init__(self, *a) -> None:
            pass

        def start(self) -> None:
            raise PlaywrightUnavailable(
                "Playwright not installed — run `playwright install chromium`, "
                "or run QAT with --api-only"
            )

    monkeypatch.setattr(uat, "BrowserUI", UnavailableUI)
    result = uat.run_case(
        _settings(tmp_path), _scenario(case), _state(tmp_path), SimpleNamespace(api_only=False)
    )
    assert result.status is Status.FAIL
    assert "playwright" in result.detail.lower()
    assert "--api-only" in result.detail
    assert result.evidence["driver"] == "browser_gui"
    assert not api_called


# --------------------------------------------------------- BrowserUI helpers


def test_current_chat_id_from_url(tmp_path: Path) -> None:
    ui = BrowserUI(_settings(tmp_path), tmp_path)
    ui._page = SimpleNamespace(url="http://localhost:8080/c/12345678-1234-1234-1234-123456789abc")
    assert ui.current_chat_id() == "12345678-1234-1234-1234-123456789abc"
    ui._page = SimpleNamespace(url="http://localhost:8080/")
    assert ui.current_chat_id() == ""


class _Option:
    def __init__(self, attrs: dict, page: _ModelPage) -> None:
        self.attrs = attrs
        self.page = page

    def get_attribute(self, name: str):
        return self.attrs.get(name)

    def inner_text(self) -> str:
        return self.attrs.get("text", "")

    def click(self, **kw) -> None:
        self.page.clicked = self
        self.page.menu_open = False
        self.page.label = self.attrs.get("data-value") or self.attrs.get("text", "")


class _OptionsLocator:
    def __init__(self, page: _ModelPage) -> None:
        self.page = page

    def all(self) -> list[_Option]:
        needle = (self.page.search_filled or "").casefold()
        return [
            _Option(o, self.page)
            for o in self.page.options
            if not needle
            or needle in (o.get("data-value", "") + " " + o.get("text", "")).casefold()
        ]


class _ModelLocator:
    def __init__(self, page: _ModelPage, selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> _ModelLocator:
        return self

    def count(self) -> int:
        if self.selector.startswith("button[id^='model-selector-']"):
            return 1
        if self.selector == "[role='listbox']":
            return 1 if self.page.menu_open else 0
        if "search" in self.selector.lower():
            return 1 if self.page.has_search else 0
        return 0

    def click(self, **kw) -> None:
        if self.selector.startswith("button[id^='model-selector-']"):
            self.page.menu_open = True

    def fill(self, value: str) -> None:
        self.page.search_filled = value

    def inner_text(self) -> str:
        if self.selector.startswith("button[id^='model-selector-']"):
            return self.page.label
        return ""

    def locator(self, sub: str) -> _OptionsLocator:
        return _OptionsLocator(self.page)

    def evaluate(self, js: str):
        return False

    def wait_for(self, **kw) -> None:
        pass


class _ModelPage:
    def __init__(self, options: list[dict], has_search: bool = True) -> None:
        self.options = options
        self.has_search = has_search
        self.menu_open = False
        self.clicked = None
        self.label = "initial"
        self.search_filled = None

    def locator(self, selector: str) -> _ModelLocator:
        return _ModelLocator(self, selector)

    def wait_for_timeout(self, ms: float) -> None:
        pass


def test_select_model_clicks_exact_option_and_verifies_label(tmp_path: Path) -> None:
    ui = BrowserUI(_settings(tmp_path), tmp_path)
    page = _ModelPage(
        [
            {"data-value": "auto-daily", "text": "Portal Daily"},
            {"data-value": "auto-coding", "text": "Portal Code Expert"},
        ]
    )
    ui._page = page
    ui.select_model("auto-coding", "Portal Code Expert")
    assert page.clicked is not None
    assert page.clicked.attrs["data-value"] == "auto-coding"
    assert page.search_filled == "auto-coding"


def test_select_model_matches_display_name_without_slug(tmp_path: Path) -> None:
    ui = BrowserUI(_settings(tmp_path), tmp_path)
    page = _ModelPage(
        [{"aria-label": "Portal Code Expert", "text": "Portal Code Expert"}], has_search=False
    )
    ui._page = page
    ui.select_model("auto-coding", "Portal Code Expert")
    assert page.clicked is not None


def test_select_model_raises_for_missing_option(tmp_path: Path) -> None:
    ui = BrowserUI(_settings(tmp_path), tmp_path)
    ui._page = _ModelPage([{"data-value": "auto-daily", "text": "Portal Daily"}])
    with pytest.raises(RuntimeError):
        ui.select_model("auto-nope")


class _ChatKeyboard:
    def __init__(self, page: _ChatPage) -> None:
        self.page = page

    def press(self, key: str) -> None:
        if key == "Enter":
            self.page.submit()

    def insert_text(self, text: str) -> None:
        self.page.input_value = text
        self.page.inserted.append(text)


class _ChatLocator:
    def __init__(self, page: _ChatPage, selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> _ChatLocator:
        return self

    def count(self) -> int:
        if self.selector == STOP_CIRCLE_SELECTOR:
            return 1 if self.page.streaming else 0
        return 1

    def click(self, **kw) -> None:
        pass

    def evaluate(self, js: str):
        if self.selector == CHAT_INPUT_SELECTOR:
            return self.page.tag
        return False

    def fill(self, value: str) -> None:
        self.page.input_value = value
        self.page.filled.append(value)

    def inner_text(self) -> str:
        return self.page.input_value if self.selector == CHAT_INPUT_SELECTOR else ""

    def input_value(self) -> str:
        return self.page.input_value

    def wait_for(self, **kw) -> None:
        pass


class _ChatPage:
    def __init__(self, answers: list[str], tag: str = "div") -> None:
        self.answers = answers
        self.tag = tag
        self.users = 0
        self.assistants = 0
        self.texts: list[str] = []
        self.streaming = False
        self._countdown = 0
        self._pending = ""
        self.input_value = ""
        self.inserted: list[str] = []
        self.filled: list[str] = []
        self.url = "http://localhost:8080/"
        self.keyboard = _ChatKeyboard(self)

    def submit(self) -> None:
        self.input_value = ""
        self.users += 1
        self.assistants += 1
        self.streaming = True
        self._countdown = 3
        self._pending = self.answers[len(self.texts)]

    def evaluate(self, js: str, arg=None):
        if isinstance(arg, list):
            return [self.users, self.assistants]
        return [{"text": text, "urls": []} for text in self.texts]

    def locator(self, selector: str) -> _ChatLocator:
        return _ChatLocator(self, selector)

    def wait_for_timeout(self, ms: float) -> None:
        if self.streaming:
            self._countdown -= 1
            if self._countdown <= 0:
                self.streaming = False
                self.texts.append(self._pending)


@pytest.mark.parametrize("tag", ["div", "textarea"])
def test_send_turn_waits_for_new_assistant_and_returns_fresh_text(tmp_path: Path, tag: str) -> None:
    ui = BrowserUI(_settings(tmp_path), tmp_path)
    page = _ChatPage(["first answer", "second answer"], tag=tag)
    ui._page = page
    first = ui.send_turn("first question", max_wait_s=5.0)
    second = ui.send_turn("second question", max_wait_s=5.0)
    assert first == "first answer"
    assert second == "second answer"  # not stale prior-turn text
    assert page.users == 2 and page.assistants == 2
    assert ui.visible_turn_count() == (2, 2)
    if tag == "textarea":
        assert page.filled == ["first question", "second question"]
    else:
        assert page.inserted == ["first question", "second question"]


def test_send_turn_times_out_when_no_new_assistant(tmp_path: Path) -> None:
    ui = BrowserUI(_settings(tmp_path), tmp_path)
    page = _ChatPage(["answer"])
    page.submit = lambda: None  # Enter never renders a new assistant message
    ui._page = page
    with pytest.raises(TimeoutError):
        ui.send_turn("question", max_wait_s=0.2)


def test_download_artifact_resolves_filename_when_file_id_was_rewritten(tmp_path: Path) -> None:
    """The QAT STEP link mutated 1fa1e061 → 1fa1e03a; the published filename was right."""
    real_id = "1fa1e061-3a4d-4de6-9029-bf68b8d2bfd0"
    bad_id = "1fa1e03a-3a4d-4de6-9029-bf68b8d2bfd0"
    name = "cube_20mm_54faa8.step"
    body = b"step-bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/api/v1/files/{bad_id}/content/{name}":
            return httpx.Response(404)
        if request.url.path == "/api/v1/files/search":
            assert request.url.params["filename"] == name
            return httpx.Response(
                200,
                json=[
                    {"id": "older", "filename": name, "created_at": 1},
                    {"id": real_id, "filename": name, "created_at": 2},
                    {"id": "other", "filename": "other.step", "created_at": 9},
                ],
            )
        if request.url.path == f"/api/v1/files/{real_id}/content":
            return httpx.Response(200, content=body)
        return httpx.Response(500)

    client = OWUIClient(_settings(tmp_path), httpx.MockTransport(handler))
    url = f"https://chat.example/api/v1/files/{bad_id}/content/{name}"
    assert client.download_artifact("secret", url) == body


def test_download_artifact_404_stays_404_when_filename_is_unpublished(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/files/search":
            return httpx.Response(404, json={"detail": "No files found matching the pattern."})
        return httpx.Response(404)

    client = OWUIClient(_settings(tmp_path), httpx.MockTransport(handler))
    url = "http://localhost:8080/api/v1/files/01234567-89ab-cdef-0123-456789abcdef/content/missing.stl"
    with pytest.raises(ArtifactDownloadError) as caught:
        client.download_artifact("secret", url)
    assert caught.value.status_code == 404
