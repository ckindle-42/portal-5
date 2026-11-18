"""Telegram Jarvis control plane — routing, allowlist, confirm flow, host executor.

No network, no live Telegram, no live queue: tmp_path stores and fakes only.
"""

import pytest

pytest.importorskip("telegram", reason="python-telegram-bot not installed (channels extra)")

from portal.modules.orchestration import control  # noqa: E402
from portal_channels.telegram import jarvis_control  # noqa: E402


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/jarvis status", ("status", "")),
        ("/jarvis requeue job-1", ("requeue", "job-1")),
        ("/jarvis CANCEL Job-9", ("cancel", "Job-9")),
        ("/jarvis canary my-job", ("canary", "my-job")),
        ("/jarvis", ("help", "")),
        ("/jarvis bogus x", ("bogus", "x")),
    ],
)
def test_parse_is_deterministic(text, expected):
    assert jarvis_control.parse(text) == expected


def test_every_control_verb_has_a_host_executor():
    assert jarvis_control.VERB_NAMES == control.VERB_NAMES
    assert "help" not in jarvis_control.VERB_NAMES


def test_plain_jarvis_text_is_a_control_request_not_chat():
    assert jarvis_control.is_plain_jarvis("Jarvis status")
    assert jarvis_control.is_plain_jarvis("jarvis, held")
    assert not jarvis_control.is_plain_jarvis("what is jarvis status")
    assert jarvis_control.parse("Jarvis status") == ("status", "")
    assert jarvis_control.parse("jarvis: canary wfe-x") == ("canary", "wfe-x")


def test_long_notices_are_split_under_the_telegram_cap():
    from portal_channels.telegram.arm_bridge import TELEGRAM_MAX_CHARS, _telegram_chunks

    text = "\n".join(f"  blocked job-{i}: step exited 4" for i in range(400))
    parts = _telegram_chunks(text)
    assert len(parts) > 1
    assert all(len(p) <= TELEGRAM_MAX_CHARS for p in parts)
    assert "".join(parts) == text
    assert _telegram_chunks("x" * 9000) == ["x" * 4096, "x" * 4096, "x" * 808]
