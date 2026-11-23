"""Real-browser UI verification against Open WebUI (:8080).

Playwright is lazy-imported: `tests.qat` imports cleanly (and the runner
reports SKIP with an actionable note) in environments without Playwright
installed. The QAT contract is Obscura (browser-mcp :8923) for *tool*
automation; this module is the optional UI layer only.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings

RELEASE_OVERLAY_TEXTS = ("Okay, Let's Go!", "Okay, Let's Go", "Got it")
STOP_CIRCLE_SELECTOR = "button[aria-label='Stop'], path[d*='9.564a1.312']"


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
        page.fill("input[type='email']", self.settings.owui_user)
        page.fill("input[type='password']", self.settings.owui_pass)
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
        """Workspace names visible in the model selector."""
        page = self._require_page()
        self.dismiss_overlays()
        page.locator("button[id^='model-selector-']").first.click(timeout=15_000)
        page.wait_for_timeout(800)
        names: set[str] = set()
        listbox = page.locator("[role='listbox']")
        for el in listbox.locator("[role='option'], button").all():
            label = (el.inner_text() or "").strip().splitlines()
            if label and label[0]:
                names.add(label[0])
            for attribute in ("data-value", "id", "aria-label"):
                value = el.get_attribute(attribute)
                if value:
                    names.add(value)
        if not names and listbox.count():
            names.update(
                line.strip() for line in listbox.last.inner_text().splitlines() if line.strip()
            )
        page.keyboard.press("Escape")
        return names

    def send_turn(
        self, prompt: str, upload_path: Path | None = None, max_wait_s: float = 240.0
    ) -> str:
        """Send a real UI turn; wait for the stop-circle to clear; return text."""
        page = self._require_page()
        if upload_path is not None:
            page.set_input_files("input[type='file']", str(upload_path))
        page.fill("#chat-input, textarea", prompt)
        page.keyboard.press("Enter")
        deadline = time.monotonic() + max_wait_s
        stop = page.locator(STOP_CIRCLE_SELECTOR)
        grace_deadline = min(deadline, time.monotonic() + 3.0)
        appeared = False
        while time.monotonic() < grace_deadline:
            if stop.count():
                appeared = True
                break
            page.wait_for_timeout(100)
        while appeared and time.monotonic() < deadline and stop.count():
            page.wait_for_timeout(500)
        if appeared and stop.count():
            raise TimeoutError("Open WebUI Stop control remained visible past the scenario budget")
        page.wait_for_timeout(1500)
        return self.last_assistant_text()

    def last_assistant_text(self) -> str:
        page = self._require_page()
        nodes = page.query_selector_all(
            "[data-message-author-role='assistant'] .markdown-prose, "
            "[data-message-author-role='assistant']"
        )
        return nodes[-1].inner_text().strip() if nodes else ""

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
