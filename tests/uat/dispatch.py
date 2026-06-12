"""Portal 5 UAT — frontend dispatch shims (_fe_*) over browser + owui_api.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase C). Contains the _fe_* indirection layer, _extract_dom_response, and
_PresetUnreachableError (A7 split of monolith section 6).
"""

from __future__ import annotations

from pathlib import Path

from tests.uat.browser import (
    _download_artifact,
    _enable_tool,
    _login,
    _navigate_to_chat,
    _send_and_wait,
)
from tests.uat.config import MAX_WAIT_NO_PROGRESS
from tests.uat.owui_api import (
    owui_assign_chat_folder,
    owui_create_chat,
    owui_get_last_response,
    owui_get_routed_model,
)

# Frontend dispatch shims — thin wrappers over OWUI helpers.
# ---------------------------------------------------------------------------


async def _fe_login(page) -> None:
    """Login to Open WebUI."""
    await _login(page)


async def _fe_start_chat(
    page,
    token: str,
    model_slug: str,
    title: str,
) -> tuple[str, str]:
    """Create / open a fresh chat. Returns (chat_id, chat_url).

    chat_id is the OWUI UUID (used by API helpers). chat_url is
    `{OPENWEBUI_URL}/c/{chat_id}`.
    """
    chat_id, chat_url = owui_create_chat(token, model_slug, title)
    await _navigate_to_chat(page, chat_url)
    return chat_id, chat_url


class _PresetUnreachableError(RuntimeError):
    """Raised by _fe_start_chat when a persona test cannot select its preset."""


async def _fe_send_and_wait(
    page,
    prompt: str,
    test_id: str = "",
    tier: str = "any",
    max_wait_no_progress: int = MAX_WAIT_NO_PROGRESS,
    *,
    token: str = "",
    chat_id: str = "",
    min_messages: int = 1,
) -> None:
    """Send a prompt and wait for streaming to complete."""
    await _send_and_wait(
        page,
        prompt,
        test_id=test_id,
        tier=tier,
        max_wait_no_progress=max_wait_no_progress,
        token=token,
        chat_id=chat_id,
        min_messages=min_messages,
    )


async def _extract_dom_response(page) -> str:
    """Extract the last assistant response text directly from the OWUI page DOM.

    Used as a fallback when OWUI 0.9.5+ does not immediately commit thinking-model
    responses to the chat history API. OWUI renders markdown content inside .prose
    divs; reasoning blocks are in <details> elements that are stripped before return.
    Returns '' if no suitable content is found (degrades gracefully).
    """
    try:
        return await page.evaluate(
            """() => {
            // OWUI 0.9.x renders markdown with Tailwind 'prose' class.
            // The last .prose element holds the most recent assistant response.
            const selectors = [
                '.prose.dark\\\\:prose-invert',
                '.prose',
                '[data-role="assistant"] .prose',
                '.message-content .prose',
            ];
            let best = '';
            for (const sel of selectors) {
                try {
                    const els = document.querySelectorAll(sel);
                    if (els.length === 0) continue;
                    const el = els[els.length - 1];
                    const clone = el.cloneNode(true);
                    for (const d of clone.querySelectorAll('details')) d.remove();
                    const text = (clone.innerText || '').trim();
                    if (text.length > best.length) best = text;
                } catch (_) {}
            }
            return best;
        }"""
        )
    except Exception:
        return ""


async def _fe_get_last_response(page, token: str, chat_id: str, min_messages: int = 1) -> str:
    """Read the most recent assistant message — OWUI API first, DOM fallback.

    OWUI 0.9.5+ may delay committing thinking-model responses to the chat history
    API until a new user message arrives. When the API returns empty but streaming
    has visually completed, _extract_dom_response reads directly from the rendered
    page content as a fallback.
    """
    api_result = owui_get_last_response(token, chat_id, min_messages=min_messages)
    if api_result:
        return api_result
    return await _extract_dom_response(page)


async def _fe_get_routed_model(test: dict, page, token: str, chat_id: str) -> str:
    """Resolve the actual backend model that handled the most recent response.

    Reads OWUI's stored chat metadata (the workspace/persona name captured from
    the pipeline's SSE stream). Returns "" if no source is available.
    _check_routed_model handles the empty-string case by skipping validation.
    """
    return owui_get_routed_model(token, chat_id)


async def _fe_enable_tool(page, tool_id: str) -> None:
    await _enable_tool(page, tool_id)


async def _fe_assign_folder(page, token: str, chat_id: str, folder_id: str | None) -> None:
    if folder_id:
        owui_assign_chat_folder(token, chat_id, folder_id)


async def _fe_download_artifact(
    page,
    expected_ext: str,
    response_text: str = "",
    timeout_ms: int = 120_000,
    *,
    since_ts: float = 0.0,
) -> Path | None:
    return await _download_artifact(page, expected_ext, timeout_ms, response_text)


def _fe_current_chat_url(page, fallback: str) -> str:
    """Return the API-given chat_url."""
    return fallback
