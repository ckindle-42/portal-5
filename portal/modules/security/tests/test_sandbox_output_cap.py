"""Regression guard for the red-tool-output truncation cap (2026-07-24).

Found live: meta3's default IIS page embeds a ~1.1MB __VIEWSTATE blob on
essentially one line, so a line-limited `head -20` passed almost the entire
blob through to the model untruncated, and the model stalled trying to make
sense of a wall of hex noise. parse_sandbox_output now caps every red tool
result at _RED_TOOL_OUTPUT_CAP bytes regardless of what truncation (if any)
the model's own command attempted.
"""

import json

from portal.modules.security.core.lab import (
    _RED_TOOL_OUTPUT_CAP,
    parse_sandbox_output,
)


def test_short_output_passes_through_unchanged():
    raw = json.dumps({"success": True, "stdout": "hello world", "stderr": "", "exit_code": 0})
    ok, text = parse_sandbox_output(raw)
    assert ok is True
    assert text == "hello world"


def test_oversized_single_line_output_is_capped():
    huge = "a" * (_RED_TOOL_OUTPUT_CAP + 50_000)
    raw = json.dumps({"success": True, "stdout": huge, "stderr": "", "exit_code": 0})
    ok, text = parse_sandbox_output(raw)
    assert ok is True
    assert len(text) < len(huge)
    assert text.startswith("a" * _RED_TOOL_OUTPUT_CAP)
    assert "bytes truncated" in text


def test_oversized_non_json_output_is_also_capped():
    huge = "b" * (_RED_TOOL_OUTPUT_CAP + 1000)
    ok, text = parse_sandbox_output(huge)
    assert ok is True
    assert "bytes truncated" in text
    assert len(text) < len(huge)
