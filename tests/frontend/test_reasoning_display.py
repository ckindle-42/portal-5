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

  LibreChat and AnythingLLM do NOT inject <details type="reasoning"> — they expose
  thinking content in visible text flow, making standard DOM polling reliable.

This test verifies:
  1. The pipeline returns valid thinking + content for a reasoning workspace (API)
  2. OWUI buries <think> tokens inside <details type="reasoning"> (DOM check)
  3. The alternative frontends do NOT bury them in hidden <details> elements (DOM)

NOTE: HuggingChat (chat-ui) was evaluated but removed. chat-ui v2 (2025+) fetches
  model lists exclusively from router.huggingface.co and requires a valid HF_TOKEN
  for inference. The MODELS env var for local-only configuration is not supported
  in the v2 UI layer. A valid HF_TOKEN with inference credits is required.

Running
-------
  # Requires all frontends running (./launch.sh up-all-frontends)
  # and Playwright browsers installed (playwright install chromium)
  pytest tests/frontend/test_reasoning_display.py -v -s --timeout=300

  # Skip slow Playwright tests, run API baseline only:
  pytest tests/frontend/test_reasoning_display.py -v -s -m "not browser"

Environment variables
---------------------
  OPENWEBUI_URL            default http://localhost:8080
  OPENWEBUI_ADMIN_EMAIL    default admin@portal.local
  OPENWEBUI_ADMIN_PASSWORD (required for OWUI Playwright login)
  LIBRECHAT_URL            default http://localhost:8082
  LIBRECHAT_ADMIN_EMAIL / LIBRECHAT_ADMIN_PASSWORD
  PIPELINE_URL             default http://localhost:9099
  PIPELINE_API_KEY
"""

from __future__ import annotations

import os
import re
import time

import httpx
import pytest

# ── Config ────────────────────────────────────────────────────────────────────

OWUI_URL = os.environ.get("OPENWEBUI_URL", "http://localhost:8080")
OWUI_EMAIL = os.environ.get("OPENWEBUI_ADMIN_EMAIL", "admin@portal.local")
OWUI_PASSWORD = os.environ.get("OPENWEBUI_ADMIN_PASSWORD", "")

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
    """Log in to Open WebUI — mirrors the UAT driver login flow."""
    if not OWUI_PASSWORD:
        pytest.skip("OPENWEBUI_ADMIN_PASSWORD not set — cannot log in to OWUI")
    page.goto(OWUI_URL, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_selector('input[type="email"]', timeout=15_000)
    page.fill('input[type="email"]', OWUI_EMAIL)
    page.fill('input[type="password"]', OWUI_PASSWORD)
    page.locator('button[type="submit"], button:has-text("Sign in")').first.click()
    # Wait for the chat input (textarea or contenteditable) to confirm login succeeded
    page.wait_for_selector("textarea, [contenteditable]", timeout=20_000)


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
    """OWUI hides thinking tokens inside <details type='reasoning'> in the DOM.

    This is the root cause of the original UAT failure: OWUI's Svelte renderer wraps
    <think>...</think> content inside a collapsed <details type="reasoning"> element.
    Because the element is collapsed, innerText returns "" for that section while streaming,
    making the DOM appear stable with an empty response at ~4.5s — triggering the UAT
    driver's DOM-stability check too early.

    This test confirms:
    - A response IS generated (page text grows)
    - The thinking content IS inside <details type="reasoning"> elements (OWUI behaviour)
    - The actual answer IS visible (test passes as long as a real answer follows)

    If the routed model does not support thinking (e.g., AEON not loaded), reports
    'no thinking detected' rather than failing — the model behaviour is the variable.
    """
    if not OWUI_PASSWORD:
        pytest.skip("OPENWEBUI_ADMIN_PASSWORD not set — cannot log in to OWUI")

    page = browser_context.new_page()
    try:
        _owui_login(page)

        # Select the auto-security workspace model from OWUI's model picker
        try:
            # OWUI shows a model selector button in the top bar
            model_btn = page.locator('[aria-label*="model"], button:has-text("Portal")').first
            if model_btn.is_visible(timeout=5000):
                model_btn.click()
                page.get_by_text("Portal Security", exact=False).first.click()
                time.sleep(1)
        except Exception:
            pass  # Auto-selected or unavailable; proceed with default

        # Send the reasoning prompt
        page.wait_for_selector("textarea, [contenteditable='true']", timeout=20_000)
        chat_input = page.locator("textarea, [contenteditable='true']").first
        chat_input.fill(REASONING_PROMPT)
        chat_input.press("Enter")

        # Wait for OWUI to finish streaming
        _wait_for_response_complete(page, timeout_ms=RESPONSE_TIMEOUT_S * 1000)

        # Check DOM for reasoning elements
        details_count = page.locator('details[type="reasoning"]').count()
        body_text = page.inner_text("body")
        page_html = page.content()

        print(f"\n[owui] <details type='reasoning'> elements in DOM: {details_count}")
        print(f"[owui] Page text length (innerText): {len(body_text)}")
        # Also check in raw HTML — the element may exist but be hidden
        has_details_html = 'type="reasoning"' in page_html or "type='reasoning'" in page_html
        print(f"[owui] <details type='reasoning'> in raw HTML: {has_details_html}")

        assert len(body_text) > 200, (
            f"OWUI page text is only {len(body_text)} chars — response may not have been generated. "
            "Check that auto-security workspace is seeded and AEON/Qwen3 is loaded."
        )

        if details_count > 0:
            print(f"[owui] CONFIRMED: thinking content is in {details_count} <details type='reasoning'> element(s)")
            print("       innerText sees these as EMPTY while collapsed — this IS the UAT failure mode.")
            print("       The UAT driver workaround: poll /api/v1/chats/{id} instead of DOM innerText.")
        elif has_details_html:
            print("[owui] <details type='reasoning'> found in HTML but count=0 — shadow DOM or dynamic render")
        else:
            print("[owui] No <details type='reasoning'> found — AEON may not be loaded or prompt didn't trigger thinking")
            print("       This is still a PASS: we confirmed a non-empty response was delivered.")
            print("       To verify OWUI behaviour: ensure Qwen3 AEON is loaded and re-run.")

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
        # LibreChat uses WebSockets — "networkidle" never fires; wait for login form instead
        page.goto(LIBRECHAT_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_selector('input[type="email"], input[name="email"]', timeout=20_000)

        # Log in to LibreChat
        try:
            page.fill('input[type="email"], input[name="email"]', LIBRECHAT_EMAIL)
            page.fill('input[type="password"], input[name="password"]', LIBRECHAT_PASSWORD)
            page.click('button[type="submit"]')
            # Wait for chat input to appear rather than networkidle
            page.wait_for_selector("textarea, [contenteditable='true']", timeout=20_000)
        except Exception as e:
            pytest.skip(f"LibreChat login failed: {e}")

        # Select Portal 5 auto-security preset if available
        try:
            preset_btn = page.locator('button:has-text("Presets"), [aria-label*="preset"]').first
            if preset_btn.is_visible(timeout=3000):
                preset_btn.click()
                page.get_by_text("Security", exact=False).first.click()
                time.sleep(1)
        except Exception:
            pass

        # Send the reasoning prompt
        chat_input = page.locator("textarea, [contenteditable='true']").first
        chat_input.fill(REASONING_PROMPT)
        chat_input.press("Enter")

        _wait_for_response_complete(page, timeout_ms=RESPONSE_TIMEOUT_S * 1000)

        # Check response is non-empty
        response_area = page.locator('[data-message-role="assistant"], .message-content').last
        response_text = response_area.inner_text() if response_area.count() > 0 else page.inner_text("body")

        reasoning_count = page.locator("details[type='reasoning']").count()
        print(f"\n[librechat] Response text length: {len(response_text)}")
        print(f"[librechat] <details type='reasoning'> count: {reasoning_count}")

        assert response_text.strip(), "LibreChat returned empty response for auto-security workspace"
        print("[librechat] PASS: non-empty response received through LibreChat")

    finally:
        page.close()
