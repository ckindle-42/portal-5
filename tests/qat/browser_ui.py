"""Real-browser UI verification against Open WebUI (:8080).

Playwright is lazy-imported: `tests.qat` imports cleanly (and the runner
reports SKIP with an actionable note) in environments without Playwright
installed. The QAT contract is Obscura (browser-mcp :8923) for *tool*
automation; this module is the optional UI layer only.
"""

from __future__ import annotations

import contextlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings

RELEASE_OVERLAY_TEXTS = ("Okay, Let's Go!", "Okay, Let's Go", "Got it")
STOP_CIRCLE_SELECTOR = "button[aria-label='Stop'], path[d*='9.564a1.312']"
CHAT_INPUT_SELECTOR = "#chat-input"
MODEL_SELECTOR_BUTTON = "button[id^='model-selector-']"
USER_MESSAGE_SELECTOR = ".chat-user, [data-message-author-role='user']"
ASSISTANT_MESSAGE_SELECTOR = ".chat-assistant, [data-message-author-role='assistant']"
_SCROLL_LISTBOX_JS = """(el) => {
    const scroller = el.scrollHeight > el.clientHeight
        ? el
        : Array.from(el.querySelectorAll('*')).find((c) => c.scrollHeight > c.clientHeight) || el;
    const before = scroller.scrollTop;
    scroller.scrollTop = Math.min(
        scroller.scrollHeight, before + Math.max(240, scroller.clientHeight * 0.8)
    );
    return scroller.scrollTop > before;
}"""


class PlaywrightError(RuntimeError):
    """Raised when the playwright package (or its browser) is missing."""


PlaywrightUnavailable = PlaywrightError


def load_playwright() -> object:
    """Lazy import; raises PlaywrightUnavailable with an actionable note."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PlaywrightUnavailable(
            "Playwright not installed — run `uv pip install -e '.[dev]'` plus "
            "`playwright install chromium`, or run QAT with --api-only"
        ) from exc
    return sync_playwright


@dataclass
class UIBrowserErrors:
    console: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)


class BrowserUI:
    """Login, overlay dismissal, roster check, real UI turn, artifacts."""

    def __init__(self, settings: Settings, shots_dir: Path) -> None:
        self.settings = settings
        self.shots_dir = shots_dir
        self.errors = UIBrowserErrors()
        self._pw = None
        self._browser = None
        self._page = None

    def start(self) -> None:
        sync_playwright = load_playwright()
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._page = self._browser.new_page()
        page = self._page

        def on_console(msg) -> None:  # noqa: ANN001 (playwright type, optional dep)
            if msg.type == "error":
                self.errors.console.append(msg.text)

        page.on("console", on_console)
        page.on("pageerror", lambda exc: self.errors.page_errors.append(str(exc)))

    def stop(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._page = self._browser = self._pw = None

    def login(self) -> None:
        page = self._require_page()
        page.goto(f"{self.settings.owui_url}/auth", wait_until="domcontentloaded")
        page.fill("input[type='email'], input[name='email'], input#email", self.settings.owui_user)
        page.fill(
            "input[type='password'], input[name='password'], input#password",
            self.settings.owui_pass,
        )
        page.click("button[type='submit']")
        page.wait_for_url("**/", timeout=30_000)

    def dismiss_overlays(self) -> bool:
        """Dismiss release notes / whats-new overlays; True when one was closed."""
        page = self._require_page()
        dialog = page.locator("[role='dialog'][aria-modal='true']")
        with contextlib.suppress(Exception):
            dialog.first.wait_for(state="visible", timeout=3_000)
        closed = False
        for _ in range(3):
            if dialog.count() == 0:
                break
            clicked = False
            for text in RELEASE_OVERLAY_TEXTS:
                button = page.get_by_role("button", name=text)
                if button.count() > 0:
                    button.first.click()
                    clicked = True
                    closed = True
                    break
            if not clicked:
                close_btn = dialog.first.locator("button[aria-label*='Close' i], button").last
                if close_btn.count() > 0:
                    close_btn.click()
                    closed = True
                else:
                    page.keyboard.press("Escape")
                    closed = True
            page.wait_for_timeout(400)
        return closed

    def workspace_roster(self) -> set[str]:
        """Workspace names visible in the model selector (handles virtualized scroll)."""
        page = self._require_page()
        self.dismiss_overlays()
        page.locator("button[id^='model-selector-']").first.click(timeout=15_000)
        page.wait_for_timeout(800)
        names: set[str] = set()
        listbox = page.locator("[role='listbox']")

        def _collect() -> None:
            for el in listbox.locator("[role='option'], button").all():
                label = (el.inner_text() or "").strip().splitlines()
                if label and label[0]:
                    names.add(label[0])
                for attribute in ("data-value", "id", "aria-label"):
                    value = el.get_attribute(attribute)
                    if value:
                        names.add(value)

        _collect()
        if listbox.count():
            for _ in range(150):
                moved = listbox.first.evaluate(_SCROLL_LISTBOX_JS)
                if not moved:
                    break
                page.wait_for_timeout(150)
                _collect()
        if not names and listbox.count():
            names.update(
                line.strip() for line in listbox.last.inner_text().splitlines() if line.strip()
            )
        page.keyboard.press("Escape")
        return names

    def new_chat(self) -> None:
        """Navigate to a fresh chat and dismiss any overlay."""
        page = self._require_page()
        page.goto(f"{self.settings.owui_url}/", wait_until="domcontentloaded")
        self.dismiss_overlays()
        page.locator(CHAT_INPUT_SELECTOR).first.wait_for(state="visible", timeout=15_000)

    def current_chat_id(self) -> str:
        match = re.search(r"/c/([0-9a-fA-F-]{8,})", self._require_page().url)
        return match.group(1) if match else ""

    def visible_turn_count(self) -> tuple[int, int]:
        """Rendered (user, assistant) message counts, deduped to outermost nodes."""
        page = self._require_page()
        counts = page.evaluate(
            """(selectors) => {
                const tops = (selector) => {
                    const nodes = Array.from(document.querySelectorAll(selector));
                    return nodes.filter((n) => !nodes.some((m) => m !== n && m.contains(n)));
                };
                return [tops(selectors[0]).length, tops(selectors[1]).length];
            }""",
            [USER_MESSAGE_SELECTOR, ASSISTANT_MESSAGE_SELECTOR],
        )
        return int(counts[0]), int(counts[1])

    def select_model(self, model_slug: str, display_name: str = "") -> None:
        """Select the exact workspace/persona option and verify the label updates."""
        page = self._require_page()
        self.dismiss_overlays()
        page.locator(MODEL_SELECTOR_BUTTON).first.click(timeout=15_000)
        page.wait_for_timeout(600)
        search = page.locator("input[type='search'], input[placeholder*='Search' i]")
        if search.count():
            search.first.fill(model_slug)
            page.wait_for_timeout(400)
        option = self._find_model_option(model_slug, display_name)
        if option is None:
            raise RuntimeError(f"model selector has no option for {model_slug!r}")
        chosen_lines = (option.inner_text() or "").strip().splitlines()
        chosen_text = chosen_lines[0].strip() if chosen_lines else ""
        option.click()
        page.wait_for_timeout(400)
        label = page.locator(MODEL_SELECTOR_BUTTON).first.inner_text() or ""
        wanted = [w for w in (model_slug, display_name, chosen_text) if w]
        if not any(w.casefold() in label.casefold() for w in wanted):
            raise RuntimeError(f"model selector label {label!r} does not reflect {model_slug!r}")

    def _find_model_option(self, model_slug: str, display_name: str):
        page = self._require_page()
        listbox = page.locator("[role='listbox']")
        for attempt in range(16):
            match = self._match_model_option(listbox, model_slug, display_name)
            if match is not None:
                return match
            if attempt == 15 or not listbox.count():
                break
            if not listbox.first.evaluate(_SCROLL_LISTBOX_JS):
                break
            page.wait_for_timeout(200)
        return None

    def _match_model_option(self, listbox, model_slug: str, display_name: str):
        wanted = {model_slug.casefold()}
        if display_name:
            wanted.add(display_name.casefold())
        for el in listbox.locator("[role='option'], button").all():
            candidates = [el.get_attribute(a) or "" for a in ("data-value", "id", "aria-label")]
            lines = (el.inner_text() or "").strip().splitlines()
            if lines:
                candidates.append(lines[0])
            if any(c.strip().casefold() in wanted for c in candidates if c):
                return el
        return None

    def inspect_and_manage_tools(self, expected_tools: tuple[str, ...] = ()) -> dict[str, Any]:
        """Report GUI tool toggles when present; Pipeline server-side tools are fine."""
        page = self._require_page()
        info: dict[str, Any] = {"available": False, "tools": [], "toggles": {}, "missing": []}
        trigger = page.locator(
            "button[aria-label*='Integration' i], button[aria-label*='Tool' i], "
            "button[data-testid*='integration' i]"
        )
        if not trigger.count():
            info["note"] = "no GUI tool toggles; tools are served server-side via Pipeline"
            info["missing"] = list(expected_tools)
            return info
        info["available"] = True
        with contextlib.suppress(Exception):
            trigger.first.click(timeout=5_000)
            page.wait_for_timeout(500)
            toggles = page.locator(
                "[role='switch'], [role='menuitemcheckbox'], input[type='checkbox']"
            )
            for el in toggles.all():
                name = (el.get_attribute("aria-label") or el.inner_text() or "").strip()
                if not name:
                    continue
                state = el.get_attribute("aria-checked") or el.get_attribute("checked")
                info["toggles"][name] = state in ("true", "checked", "")
                info["tools"].append(name)
            page.keyboard.press("Escape")
        lowered = {str(name).casefold() for name in info["tools"]}
        info["missing"] = [t for t in expected_tools if t.casefold() not in lowered]
        return info

    def _assistant_turns(self) -> list[dict[str, Any]]:
        """Per rendered assistant message: content text plus its artifact link targets."""
        page = self._require_page()
        return page.evaluate(
            """(selector) => {
                const nodes = Array.from(document.querySelectorAll(selector));
                const tops = nodes.filter((n) => !nodes.some((m) => m !== n && m.contains(n)));
                return tops.map((n) => {
                    const content =
                        n.querySelector('#response-content-container, .markdown-prose') || n;
                    let text = (content.innerText || '').trim();
                    const urls = [];
                    n.querySelectorAll(
                        "a[href*='/api/v1/files/'], img[src*='/api/v1/files/']"
                    ).forEach((el) => {
                        const url = el.getAttribute('href') || el.getAttribute('src') || '';
                        if (url && !urls.includes(url)) urls.push(url);
                    });
                    for (const url of urls) if (!text.includes(url)) text += '\\n' + url;
                    return { text, urls };
                });
            }""",
            ASSISTANT_MESSAGE_SELECTOR,
        )

    def last_artifact_links(self) -> tuple[str, ...]:
        turns = self._assistant_turns()
        return tuple(turns[-1]["urls"]) if turns else ()

    def send_turn(
        self, prompt: str, upload_path: Path | None = None, max_wait_s: float = 240.0
    ) -> str:
        """Send a real GUI turn; wait for a NEW assistant message; return its text."""
        page = self._require_page()
        _, before = self.visible_turn_count()
        if upload_path is not None:
            self._upload_attachment(upload_path)
        self._type_prompt(prompt)
        self._submit_prompt()
        self._await_assistant_turn(before, time.monotonic() + max_wait_s)
        page.wait_for_timeout(1500)
        turns = self._assistant_turns()
        return str(turns[-1]["text"]) if turns else ""

    def _upload_attachment(self, upload_path: Path) -> None:
        page = self._require_page()
        page.set_input_files("input[type='file']", str(upload_path))
        name = upload_path.name
        deadline = time.monotonic() + 120.0
        chip = page.locator("[data-testid*='file' i], .file-item, [data-cy='file-item']")
        spinner = page.locator("[data-testid*='loading' i], .animate-spin")
        while time.monotonic() < deadline:
            body = page.locator("body").inner_text() or ""
            if (name in body or chip.count()) and not spinner.count():
                return
            page.wait_for_timeout(300)
        raise TimeoutError(f"uploaded attachment {name} did not finish processing")

    def _type_prompt(self, prompt: str) -> None:
        page = self._require_page()
        box = page.locator(CHAT_INPUT_SELECTOR).first
        box.click(timeout=15_000)
        tag = str(box.evaluate("el => el.tagName.toLowerCase()"))
        if tag in ("textarea", "input"):
            box.fill(prompt)
        else:
            page.keyboard.press("ControlOrMeta+A")
            page.keyboard.insert_text(prompt)

    def _submit_prompt(self) -> None:
        page = self._require_page()
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
        box = page.locator(CHAT_INPUT_SELECTOR).first
        tag = str(box.evaluate("el => el.tagName.toLowerCase()"))
        left = box.input_value() if tag in ("textarea", "input") else (box.inner_text() or "")
        if left.strip():
            send = page.locator(
                "#send-message-button, button[aria-label*='Send' i], button[type='submit']"
            )
            if send.count():
                send.first.click()

    def _await_assistant_turn(self, before: int, deadline: float) -> None:
        page = self._require_page()
        stop = page.locator(STOP_CIRCLE_SELECTOR)
        appeared = False
        last_text = ""
        stable_since: float | None = None
        while time.monotonic() < deadline:
            stopping = bool(stop.count())
            if stopping:
                appeared = True
            _, count = self.visible_turn_count()
            if count > before:
                turns = self._assistant_turns()
                text = str(turns[-1]["text"]).strip() if len(turns) > before else ""
                if text:
                    if text != last_text:
                        last_text = text
                        stable_since = time.monotonic()
                    elif not stopping and stable_since is not None:
                        elapsed = time.monotonic() - stable_since
                        needed = 1.0 if appeared else 2.5
                        if elapsed >= needed:
                            return
                else:
                    stable_since = None
            page.wait_for_timeout(300)
        raise TimeoutError("Open WebUI assistant turn did not complete within the scenario budget")

    def last_assistant_text(self) -> str:
        page = self._require_page()
        nodes = page.query_selector_all(
            "#response-content-container, "
            ".chat-assistant .markdown-prose, "
            ".chat-assistant, "
            "[data-message-author-role='assistant'] .markdown-prose, "
            "[data-message-author-role='assistant']"
        )
        for node in reversed(nodes):
            text = (node.inner_text() or "").strip()
            if text:
                return text
        return ""

    def toggle_details(self) -> bool:
        """Collapse/expand a <details> reasoning block; True when toggle worked."""
        page = self._require_page()
        details = page.query_selector("details")
        if details is None:
            return False
        before = details.get_attribute("open")
        details.click()
        page.wait_for_timeout(300)
        return details.get_attribute("open") != before

    def screenshot(self, name: str) -> Path:
        page = self._require_page()
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        path = self.shots_dir / f"{name}.png"
        page.screenshot(path=str(path), full_page=True)
        return path

    def _require_page(self):
        if self._page is None:
            raise PlaywrightUnavailable("BrowserUI.start() has not run")
        return self._page

    def result_errors(self) -> dict[str, list[str]]:
        return {"console": list(self.errors.console), "page_errors": list(self.errors.page_errors)}
