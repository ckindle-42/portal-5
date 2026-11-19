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


@pytest.mark.asyncio
async def test_jarvis_do_and_unknown_verb_route_to_jarvis_never_chat(tmp_path, monkeypatch) -> None:
    """pt-telegram regression: /jarvis do (even without BOT_COMMAND entity or with leading space)
    and unknown /jarvis verbs must reach Jarvis, never call_pipeline_async."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from portal_channels import dispatcher
    from portal_channels.telegram import bot

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "0:test-token")
    monkeypatch.setenv("TELEGRAM_USER_IDS", "5388311056")
    monkeypatch.setattr(bot, "_orchestration_enabled", lambda: True)
    monkeypatch.setattr(jarvis_control, "control_enabled", lambda: True)
    monkeypatch.setattr(jarvis_control, "_tasks_root", lambda: tmp_path)
    monkeypatch.setattr(
        jarvis_control,
        "_store",
        lambda: jarvis_control.ArmTelegramStore(tmp_path / "arm.sqlite3"),
    )

    pipeline_mock = AsyncMock(side_effect=AssertionError("chat pipeline must not be called"))
    monkeypatch.setattr(dispatcher, "call_pipeline_async", pipeline_mock)

    app = bot.build_app()
    replies: list[str] = []

    async def _reply(_self: object, text: str, **_kwargs: object) -> None:
        replies.append(text)

    from datetime import UTC, datetime

    from telegram import Chat, Message, MessageEntity, Update, User

    app.bot._bot_user = User(id=999, first_name="PortalBot", is_bot=True, username="PortalBot")
    monkeypatch.setattr(Message, "reply_text", _reply)
    monkeypatch.setattr(Chat, "send_action", AsyncMock())

    def _make_update(text: str, *, with_command_entity: bool = False) -> Update:
        entities = ()
        if with_command_entity:
            cmd_len = len(text.split()[0])
            entities = (MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=cmd_len),)
        msg = Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=5388311056, type="private"),
            from_user=User(id=5388311056, first_name="Chris", is_bot=False),
            text=text,
            entities=entities,
        )
        msg.set_bot(app.bot)
        return Update(update_id=1, message=msg)

    async def _dispatch(text: str, *, with_command_entity: bool = False) -> None:
        update = _make_update(text, with_command_entity=with_command_entity)
        context = SimpleNamespace(user_data={}, args=None)
        for handler in app.handlers[0]:
            matched = handler.check_update(update)
            if matched is not None and matched is not False:
                await handler.callback(update, context)
                return
        raise AssertionError(f"no handler matched {text!r}")

    # 1. /jarvis do WITHOUT BOT_COMMAND entity (e.g. leading whitespace)
    await _dispatch(" /jarvis do what is the queue status in one paragraph")
    assert len(replies) == 1 and replies[0].startswith("queued pt-")
    # 2. /jarvis do WITHOUT BOT_COMMAND entity (no leading whitespace)
    await _dispatch("/jarvis do what is the queue status in one paragraph")
    assert len(replies) == 2 and replies[1].startswith("queued pt-")
    # 3. Normal Telegram /jarvis do WITH BOT_COMMAND entity
    await _dispatch("/jarvis do check status", with_command_entity=True)
    assert len(replies) == 3 and replies[2].startswith("queued pt-")
    # 4. Unknown /jarvis verb replies with usage
    await _dispatch("/jarvis frobnicate", with_command_entity=True)
    assert len(replies) == 4
    assert "Unknown verb: frobnicate" in replies[3]
    assert "/jarvis do <text>" in replies[3]
    # 5. Also ensure handle_message itself never leaks /jarvis to chat
    await bot.handle_message(
        _make_update("/jarvis do status"),
        SimpleNamespace(user_data={}, args=None),
    )
    assert len(replies) == 5 and replies[4].startswith("queued pt-")
    pipeline_mock.assert_not_awaited()
