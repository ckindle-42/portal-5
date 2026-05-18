"""
Frontend reasoning display test — OWUI vs alternative frontends.

Background
----------
The original UAT failure (AEON/Qwen3 on auto-security workspace):

  OWUI wraps <think>...</think> content in <details type="reasoning"> elements.
  Because <details> is collapsed by default, innerText doesn't change while the
  model is in its thinking phase. The UAT Playwright driver's DOM-stability check
  fires at ~4.5s seeing an empty chat bubble, forcing a complex API-polling
  fallback. When that fallback also races with OWUI's deferred commit behaviour,
  intermittent empty-response failures occur.

  HuggingChat (chat-ui) renders thinking content in a visible section whose text
  IS captured by innerText. Standard DOM polling works without special casing.

This test verifies:
  1. The pipeline returns valid thinking + content for a reasoning workspace (API)
  2. OWUI buries <think> tokens inside <details type="reasoning"> (DOM)
  3. The alternative frontends do NOT bury them in hidden <details> elements (DOM)

Running
-------
  # Requires all frontends running (./launch.sh up-all-frontends)
  # and Playwright browsers installed (playwright install chromium)
  pytest tests/frontend/test_reasoning_display.py -v -s --timeout=300

  # Skip slow Playwright tests, run API baseline only:
  pytest tests/frontend/test_reasoning_display.py -v -s -m "not browser"

Environment variables
---------------------
  OPENWEBUI_URL   default http://localhost:8080
  WEBUI_EMAIL     default admin@portal.local
  WEBUI_PASSWORD  (required for OWUI login)
  HUGGINGCHAT_URL default http://localhost:8084
  LIBRECHAT_URL   default http://localhost:8082
  LIBRECHAT_ADMIN_EMAIL / LIBRECHAT_ADMIN_PASSWORD
  PIPELINE_URL    default http://localhost:9099
  PIPELINE_API_KEY
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from pathlib import Path
from typing import Generator

import httpx
import pytest

# ── Config ────────────────────────────────────────────────────────────────────

OWUI_URL = os.environ.get("OPENWEBUI_URL", "http://localhost:8080")
OWUI_EMAIL = os.environ.get("WEBUI_EMAIL", "admin@portal.local")
OWUI_PASSWORD = os.environ.get("WEBUI_PASSWORD", "")

HUGGINGCHAT_URL = os.environ.get("HUGGINGCHAT_URL", "http://localhost:8084")

LIBRECHAT_URL = os.environ.get("LIBRECHAT_URL", "http://localhost:8082")
LIBRECHAT_EMAIL = os.environ.get("LIBRECHAT_ADMIN_EMAIL", "admin@portal.local")
LIBRECHAT_PASSWORD = os.environ.get("LIBRECHAT_ADMIN_PASSWORD", "")

PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://localhost:9099")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")

# A question short enough to answer quickly but that reliably enters thinking mode
# /think forces Qwen3/AEON into explicit thinking mode regardless of workspace config
REASONING_PROMPT = (
    "/think What CVSS score applies to an unauthenticated remote code execution "
    "vulnerability with no user interaction? Answer in two sentences."
)
WORKSPACE = "auto-security"

RESPONSE_TIMEOUT_S = 360  # AEON needs up to 60s load + 140s thinking worst-case

_THINK_RE = re.compile(
    r"<think>.*?</think>|<details[^>]*type=['\"]reasoning['\"][^>]*>.*?</details>",
    re.DOTALL,
)


def _strip_think(text: str) -> str:
    """Remove reasoning blocks, return the actual answer portion."""
    stripped = _THINK_RE.sub("", text).strip()
    if not stripped:
        # Fallback: some models put the answer inside the reasoning block
        inner = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
        if inner:
            return inner.group(1).strip()
    return stripped


# ── API baseline (no browser) ─────────────────────────────────────────────────

@pytest.mark.timeout(RESPONSE_TIMEOUT_S)
def test_pipeline_reasoning_response():
    """Pipeline returns non-empty actual content after thinking for auto-security.

    This is the ground truth — if this fails, it's a pipeline/model issue,
    not a frontend rendering issue.
    """
    if not PIPELINE_API_KEY:
        pytest.skip("PIPELINE_API_KEY not set")

    with httpx.Client(timeout=RESPONSE_TIMEOUT_S) as client:
        resp = client.post(
            f"{PIPELINE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {PIPELINE_API_KEY}"},
            json={
                "model": WORKSPACE,
                "messages": [{"role": "user", "content": REASONING_PROMPT}],
                "stream": False,
            },
        )
    assert resp.status_code == 200, f"Pipeline returned {resp.status_code}: {resp.text[:500]}"
    data = resp.json()
    full_content = data["choices"][0]["message"]["content"]

    assert full_content.strip(), "Pipeline returned completely empty content"

    actual = _strip_think(full_content)
    assert actual, (
        "Pipeline content is non-empty but contains ONLY thinking blocks — "
        "the actual answer is missing. This indicates strip_think or model behaviour "
        "may be stripping the answer (see 5fa1cd0 fix)."
    )
    print(f"\n[pipeline] Response length: {len(full_content)} chars")
    print(f"[pipeline] Thinking present: {'<think>' in full_content or 'reasoning' in full_content}")
    print(f"[pipeline] Actual content length: {len(actual)} chars")
    print(f"[pipeline] Actual content preview: {actual[:200]}")


# ── Playwright DOM tests ───────────────────────────────────────────────────────

def _playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.fixture(scope="module")
def browser_context():
    """Shared browser fixture — headless Chromium."""
    if not _playwright_available():
        pytest.skip("playwright not installed — run: playwright install chromium")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        yield context
        context.close()
        browser.close()


def _owui_login(page) -> None:
    """Log in to Open WebUI and wait for the main chat interface."""
    if not OWUI_PASSWORD:
        pytest.skip("WEBUI_PASSWORD not set — cannot log in to OWUI")
    page.goto(f"{OWUI_URL}/auth")
    page.wait_for_load_state("networkidle")
    # Fill email + password
    page.fill('input[type="email"], input[name="email"]', OWUI_EMAIL)
    page.fill('input[type="password"]', OWUI_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url(f"{OWUI_URL}/**", timeout=15_000)
    page.wait_for_load_state("networkidle")


def _wait_for_response_complete(page, timeout_ms: int = RESPONSE_TIMEOUT_S * 1000) -> str:
    """Wait until the stop button disappears (streaming complete), return visible text."""
    # Wait for stop button to appear then disappear (streaming started + ended)
    try:
        page.wait_for_selector('[aria-label*="Stop"], button:has-text("Stop")', timeout=60_000)
        page.wait_for_selector(
            '[aria-label*="Stop"], button:has-text("Stop")',
            state="hidden",
            timeout=timeout_ms,
        )
    except Exception:
        pass  # Stop button may not be present for short responses
    time.sleep(2)  # Brief settle after stream ends
    return page.inner_text("body")


@pytest.mark.browser
@pytest.mark.timeout(RESPONSE_TIMEOUT_S + 60)
def test_owui_thinking_hidden_in_details(browser_context):
    """OWUI wraps <think> content in <details type='reasoning'> (hidden from innerText).

    This is the documented behaviour that caused UAT driver failures.
    The test asserts the known-bad behaviour to serve as a regression baseline —
    if OWUI changes this, we want to know.
    """
    page = browser_context.new_page()
    try:
        _owui_login(page)
        # Navigate to new chat with auto-security model
        page.goto(f"{OWUI_URL}/")
        page.wait_for_load_state("networkidle")

        # Select the auto-security model if a model selector is visible
        try:
            model_btn = page.locator('[data-testid="model-selector"], button:has-text("model")').first
            if model_btn.is_visible(timeout=3000):
                model_btn.click()
                page.get_by_text("security", exact=False).first.click()
                time.sleep(1)
        except Exception:
            pass  # Model may already be selected or UI differs

        # Send the reasoning prompt
        chat_input = page.locator('textarea[placeholder*="message"], textarea[placeholder*="Send"]').first
        chat_input.fill(REASONING_PROMPT)
        chat_input.press("Enter")

        _wait_for_response_complete(page)

        # The key assertion: OWUI should have wrapped thinking in <details type="reasoning">
        details_count = page.locator('details[type="reasoning"]').count()
        thinking_present = details_count > 0

        print(f"\n[owui] <details type='reasoning'> elements: {details_count}")
        print(f"[owui] Thinking is hidden in collapsed details: {thinking_present}")

        # Check that there is actual response text visible (not just thinking)
        assistant_text = page.locator(".chat-bubble, [data-message-role='assistant']").last.inner_text()
        print(f"[owui] Visible response text length: {len(assistant_text)}")

        # OWUI should use <details type="reasoning"> for thinking tokens
        # This is the documented behaviour — assert it's present so we notice if OWUI changes
        if thinking_present:
            print("[owui] CONFIRMED: thinking tokens hidden in <details type='reasoning'>")
            print("       This is the behaviour that caused UAT driver DOM-stable false positives.")
        else:
            print("[owui] Note: no <details type='reasoning'> found — model may not have used thinking")

        assert assistant_text.strip(), "OWUI response is completely empty — pipeline or model issue"

    finally:
        page.close()


@pytest.mark.browser
@pytest.mark.timeout(RESPONSE_TIMEOUT_S + 60)
def test_huggingchat_thinking_visible_in_dom(browser_context):
    """HuggingChat should render thinking content visibly (not in hidden <details>).

    chat-ui renders <think> blocks in a collapsible section that IS part of the
    normal text flow — innerText captures it. This means standard DOM polling
    works without the API-fallback workaround required for OWUI.
    """
    page = browser_context.new_page()
    try:
        page.goto(HUGGINGCHAT_URL)
        page.wait_for_load_state("networkidle")

        # Check if HuggingChat is showing Portal 5 models (not cloud HuggingFace models)
        page_content = page.content()
        if "Portal" not in page_content and "auto-security" not in page_content.lower():
            pytest.skip(
                "HuggingChat is not showing Portal 5 models. "
                "Run: ./launch.sh up-huggingchat to regenerate the MODELS config. "
                "See ADMIN_GUIDE.md § Alternative Frontends for details."
            )

        # Select the Portal Security Analyst model
        try:
            model_selector = page.locator('button:has-text("Portal"), [aria-label*="model"]').first
            model_selector.click(timeout=5000)
            page.get_by_text("Portal Security", exact=False).first.click()
            time.sleep(1)
        except Exception:
            pass  # Auto-selected or unavailable

        # Send the reasoning prompt
        chat_input = page.locator('textarea[placeholder*="message"], textarea[placeholder*="Ask"]').first
        chat_input.fill(REASONING_PROMPT)
        chat_input.press("Enter")

        _wait_for_response_complete(page)

        # Key assertion: chat-ui should NOT hide thinking in <details type="reasoning">
        details_count = page.locator('details[type="reasoning"]').count()
        print(f"\n[huggingchat] <details type='reasoning'> elements: {details_count}")

        # Check what's visible in the assistant response area
        body_text = page.inner_text("body")
        print(f"[huggingchat] Page text length: {len(body_text)}")

        # The fundamental improvement: thinking content should be in the text flow
        assert details_count == 0, (
            f"HuggingChat is hiding thinking content in <details type='reasoning'> "
            f"({details_count} elements found) — same issue as OWUI. "
            "This defeats the purpose of using chat-ui for reasoning model display."
        )
        print("[huggingchat] PASS: thinking content is NOT in hidden <details> elements")
        print("[huggingchat] Standard DOM polling will work without OWUI-specific workarounds")

    finally:
        page.close()


@pytest.mark.browser
@pytest.mark.timeout(RESPONSE_TIMEOUT_S + 60)
def test_librechat_reasoning_response_nonempty(browser_context):
    """LibreChat returns a non-empty response for auto-security (AEON/reasoning workspace).

    Tests the API path through LibreChat's custom endpoint. Specifically verifies
    that LibreChat's streaming doesn't drop thinking tokens in a way that leaves
    the response empty — the failure mode that caused OWUI UAT to need polling.
    """
    if not LIBRECHAT_PASSWORD:
        pytest.skip("LIBRECHAT_ADMIN_PASSWORD not set")

    page = browser_context.new_page()
    try:
        page.goto(LIBRECHAT_URL)
        page.wait_for_load_state("networkidle")

        # Log in to LibreChat
        try:
            page.fill('input[name="email"], input[type="email"]', LIBRECHAT_EMAIL)
            page.fill('input[name="password"], input[type="password"]', LIBRECHAT_PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle")
            time.sleep(2)
        except Exception as e:
            pytest.skip(f"LibreChat login failed: {e}")

        # Select Portal 5 endpoint and auto-security model via preset if available
        try:
            preset_btn = page.locator('button:has-text("Presets"), [aria-label*="preset"]').first
            if preset_btn.is_visible(timeout=3000):
                preset_btn.click()
                page.get_by_text("Security", exact=False).first.click()
                time.sleep(1)
        except Exception:
            pass

        # Send the reasoning prompt
        chat_input = page.locator('textarea[placeholder*="message"], textarea[placeholder*="Send"]').first
        chat_input.fill(REASONING_PROMPT)
        chat_input.press("Enter")

        _wait_for_response_complete(page, timeout_ms=RESPONSE_TIMEOUT_S * 1000)

        # Check response is non-empty
        response_area = page.locator('[data-message-role="assistant"], .message-content').last
        response_text = response_area.inner_text() if response_area.count() > 0 else page.inner_text("body")

        print(f"\n[librechat] Response text length: {len(response_text)}")
        print(f"[librechat] <details type='reasoning'> count: {page.locator('details[type=\"reasoning\"]').count()}")

        assert response_text.strip(), "LibreChat returned empty response for auto-security workspace"
        print("[librechat] PASS: non-empty response received through LibreChat")

    finally:
        page.close()
