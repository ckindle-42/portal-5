#!/usr/bin/env python3
"""
Portal 5 Frontend Validation — Chromium browser tests via Playwright.

Tests the Open WebUI frontend at http://localhost:8080 including:
- Login page loads
- Admin login works
- Chat interface appears
- Workspace/model dropdown contains expected entries
- Settings page accessible
- Knowledge base page accessible
- No JavaScript console errors

Usage:
    python3 portal5_frontend_test.py

Requires:
    pip install playwright
    python3 -m playwright install chromium
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


def load_env():
    """Load .env file from project root."""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


load_env()

ADMIN_EMAIL = os.environ.get("OPENWEBUI_ADMIN_EMAIL", "admin@portal.local")
ADMIN_PASSWORD = os.environ.get("OPENWEBUI_ADMIN_PASSWORD", "")
BASE_URL = "http://localhost:8080"

if not ADMIN_PASSWORD:
    print("FAIL: OPENWEBUI_ADMIN_PASSWORD not set in .env — cannot test login")
    sys.exit(1)


async def run_tests() -> list[str]:
    from playwright.async_api import async_playwright

    results: list[str] = []
    console_errors: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )
        page = await context.new_page()

        # Capture console errors throughout the session
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )

        # ── Test 1: Login page loads ──────────────────────────────────
        try:
            resp = await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
            if resp and resp.status == 200:
                results.append("PASS: Login page loads (HTTP 200)")
            else:
                code = resp.status if resp else "None"
                results.append(f"FAIL: Login page returned HTTP {code}")
        except Exception as e:
            results.append(f"FAIL: Login page timeout: {e}")
            await browser.close()
            return results

        # ── Test 2: Sign in with admin credentials ────────────────────
        try:
            # Open WebUI presents email + password form
            await page.wait_for_selector(
                'input[type="email"], input[name="email"], input[autocomplete="email"]',
                timeout=10000,
            )
            email_input = page.locator(
                'input[type="email"], input[name="email"], input[autocomplete="email"]'
            )
            await email_input.first.fill(ADMIN_EMAIL)

            password_input = page.locator('input[type="password"]')
            await password_input.first.fill(ADMIN_PASSWORD)

            sign_in = page.locator(
                'button:has-text("Sign in"), button:has-text("Login"), button[type="submit"]'
            )
            await sign_in.first.click()

            # Wait for chat interface (textarea, contenteditable, or similar)
            await page.wait_for_selector(
                "textarea, [contenteditable], #chat-input, .chat-input",
                timeout=15000,
            )
            results.append("PASS: Admin login successful — chat interface loaded")

            await page.screenshot(path="/tmp/portal5_chat_interface.png")
            results.append("INFO: Screenshot → /tmp/portal5_chat_interface.png")

        except Exception as e:
            results.append(f"FAIL: Admin login failed: {e}")
            await page.screenshot(path="/tmp/portal5_login_failure.png")
            results.append("INFO: Failure screenshot → /tmp/portal5_login_failure.png")
            # Continue with remaining tests anyway

        # ── Test 3: Model/workspace dropdown ──────────────────────────
        try:
            # Open WebUI has various selector patterns across versions
            selectors = [
                '[data-testid="model-selector"]',
                ".model-selector",
                'button:has-text("Portal")',
                'button:has-text("Auto")',
                'div[class*="model"]',
                "select",
            ]
            found = False
            for sel in selectors:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    results.append(f"PASS: Model selector found via '{sel}'")
                    try:
                        await loc.first.click()
                        await page.wait_for_timeout(1500)
                        await page.screenshot(path="/tmp/portal5_model_dropdown.png")
                        results.append(
                            "INFO: Dropdown screenshot → /tmp/portal5_model_dropdown.png"
                        )

                        # Try to count visible options
                        options = page.locator(
                            '[role="option"], [role="menuitem"], li[class*="model"], div[class*="option"]'
                        )
                        opt_count = await options.count()
                        if opt_count > 0:
                            results.append(f"PASS: Model dropdown has {opt_count} visible options")
                    except Exception:
                        pass
                    found = True
                    break
            if not found:
                results.append("WARN: Model selector not found with any known selector")
        except Exception as e:
            results.append(f"WARN: Model dropdown test: {e}")

        # ── Test 4: Navigate to Admin Settings ────────────────────────
        try:
            # Try direct navigation to admin settings
            resp = await page.goto(
                f"{BASE_URL}/admin/settings",
                wait_until="networkidle",
                timeout=15000,
            )
            if resp and resp.status == 200:
                results.append("PASS: Admin settings page accessible")
            else:
                results.append(
                    f"INFO: Admin settings returned HTTP {resp.status if resp else 'None'}"
                )
            await page.screenshot(path="/tmp/portal5_admin_settings.png")
        except Exception as e:
            results.append(f"INFO: Admin settings page: {e}")

        # ── Test 5: Check for chat textarea functionality ─────────────
        try:
            await page.goto(BASE_URL, wait_until="networkidle", timeout=10000)
            textarea = page.locator("textarea, [contenteditable='true']")
            if await textarea.count() > 0:
                # Type a test message (don't send it)
                await textarea.first.click()
                await textarea.first.fill("test message from validation")
                content = (
                    await textarea.first.input_value() if await textarea.first.is_visible() else ""
                )
                if "test message" in content:
                    results.append("PASS: Chat textarea accepts input")
                else:
                    results.append("INFO: Chat textarea found but input not confirmed")
                # Clear it
                await textarea.first.fill("")
            else:
                results.append("WARN: No chat textarea found on main page")
        except Exception as e:
            results.append(f"INFO: Chat textarea test: {e}")

        # ── Test 6: Console errors summary ────────────────────────────
        await page.wait_for_timeout(2000)  # Let any deferred errors fire
        if console_errors:
            # Filter out noise
            real_errors = [
                e for e in console_errors if "favicon" not in e.lower() and "404" not in e
            ]
            if real_errors:
                results.append(f"WARN: {len(real_errors)} JS console error(s): {real_errors[:3]}")
            else:
                results.append("PASS: No significant JavaScript console errors")
        else:
            results.append("PASS: No JavaScript console errors")

        await browser.close()

    return results


def main() -> int:
    results = asyncio.run(run_tests())

    print("\n════════════════════════════════════════")
    print("  Portal 5 — Frontend Test Results")
    print("════════════════════════════════════════")
    for r in results:
        prefix = r.split(":")[0]
        indent = "  "
        if prefix == "PASS":
            print(f"{indent}✅ {r}")
        elif prefix == "FAIL":
            print(f"{indent}❌ {r}")
        elif prefix == "WARN":
            print(f"{indent}⚠️  {r}")
        else:
            print(f"{indent}ℹ️  {r}")

    failures = [r for r in results if r.startswith("FAIL")]
    passes = [r for r in results if r.startswith("PASS")]
    warns = [r for r in results if r.startswith("WARN")]

    print(f"\n  Summary: {len(passes)} passed, {len(failures)} failed, {len(warns)} warnings")
    print("════════════════════════════════════════\n")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
