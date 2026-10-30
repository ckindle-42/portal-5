"""Telegram Jarvis control plane — routing, allowlist, confirm flow, host executor.

No network, no live Telegram, no live queue: tmp_path stores and fakes only.
"""

import subprocess
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from portal.modules.orchestration import control
from portal.modules.orchestration.escalate import EscalationLedger, Escalator, held_escalations
from portal.modules.orchestration.telegram import TelegramNoticeSink
from portal_channels.telegram import bot, jarvis_control
from portal_channels.telegram.arm_bridge import ArmTelegramStore, send_outbox_once

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path, monkeypatch):
    db = tmp_path / "arm" / "telegram.sqlite3"
    monkeypatch.setenv("PORTAL_ARM_TELEGRAM_DB", str(db))
    return ArmTelegramStore(db)


@pytest.fixture
def tasks_dir(tmp_path):
    return tmp_path / "tasks"


def _message(text: str, user_id: int) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_message.text = text
    update.effective_message.reply_text = AsyncMock()
    return update


def _callback(data: str, user_id: int) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.edit_message_reply_markup = AsyncMock()
    update.callback_query.message = MagicMock()
    update.callback_query.message.text = "Jarvis cancel job-1: confirm?"
    return update


def _buttons(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _allow(monkeypatch, users: set[int]) -> None:
    # Patch by path: test_channels.py reloads portal_channels.telegram.bot, so a
    # module-object attribute patch can land on a stale module.
    monkeypatch.setattr("portal_channels.telegram.bot._allowed_users", lambda: users)


# ── Parse and routing ────────────────────────────────────────────────────────


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


async def test_jarvis_help_is_answered_without_a_row(store, monkeypatch):
    monkeypatch.setattr(jarvis_control, "control_enabled", lambda: True)
    _allow(monkeypatch, {73})
    update = _message("/jarvis help", 73)
    await jarvis_control.handle_jarvis(update, MagicMock())
    update.effective_message.reply_text.assert_called_once()
    assert "status" in update.effective_message.reply_text.call_args[0][0]
    assert store.latest_control_requests() == []


# ── Fail closed ──────────────────────────────────────────────────────────────


async def test_empty_allowlist_refuses_control_but_chat_still_works(store, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_USER_IDS", "")
    monkeypatch.setattr(jarvis_control, "control_enabled", lambda: True)
    update = _message("/jarvis status", 12345)
    await jarvis_control.handle_jarvis(update, MagicMock())
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "allowlist" in reply
    assert store.latest_control_requests() == []
    assert bot._is_allowed(12345) is True  # chat keeps permitting everyone


async def test_unknown_user_is_refused_without_a_row(store, monkeypatch):
    monkeypatch.setattr(jarvis_control, "control_enabled", lambda: True)
    _allow(monkeypatch, {73})
    update = _message("/jarvis status", 99999)
    await jarvis_control.handle_jarvis(update, MagicMock())
    assert update.effective_message.reply_text.call_args[0][0] == "Unauthorized."
    assert store.latest_control_requests() == []


async def test_callback_refuses_unknown_user(store, monkeypatch):
    monkeypatch.setattr(jarvis_control, "control_enabled", lambda: True)
    _allow(monkeypatch, {73})
    request_id = store.add_control_request(73, "cancel", "job-1", status="pending")
    update = _callback(f"jv:confirm:{request_id}", 99999)
    await jarvis_control.handle_callback(update, MagicMock())
    update.callback_query.answer.assert_called_once()
    assert "nauthorized" in update.callback_query.answer.call_args[0][0]
    assert store.control_request(request_id).status == "pending"


# ── Flag off ─────────────────────────────────────────────────────────────────


def test_the_shipped_config_declares_the_control_flag():
    # The operator turned control on 10-30; the flag must stay an explicit boolean.
    config = yaml.safe_load((ROOT / "config" / "orchestration_arm.yaml").read_text())
    block = config["queue"]["telegram_control"]
    assert isinstance(block["enabled"], bool)


async def test_flag_off_bot_answers_not_enabled_and_never_opens_the_store(tmp_path, monkeypatch):
    db = tmp_path / "arm" / "telegram.sqlite3"
    monkeypatch.setenv("PORTAL_ARM_TELEGRAM_DB", str(db))
    monkeypatch.setattr(jarvis_control, "control_enabled", lambda: False)
    update = _message("/jarvis status", 73)
    await jarvis_control.handle_jarvis(update, MagicMock())
    assert update.effective_message.reply_text.call_args[0][0] == "Jarvis control is not enabled."
    assert not db.exists()


def test_flag_off_runner_never_builds_a_poller(tmp_path, tasks_dir):
    untouched = tmp_path / "arm" / "never.sqlite3"
    assert control.build_control_poller(tasks_dir, ROOT, None, {}) is None
    assert (
        control.build_control_poller(tasks_dir, ROOT, None, {"telegram_control": {"enabled": 1}})
        is None
    )
    assert not untouched.exists()


# ── Queuing, confirm flow, expiry ────────────────────────────────────────────


async def test_non_destructive_verb_queues_a_row(store, monkeypatch):
    monkeypatch.setattr(jarvis_control, "control_enabled", lambda: True)
    _allow(monkeypatch, {73})
    update = _message("/jarvis status", 73)
    await jarvis_control.handle_jarvis(update, MagicMock())
    row = store.latest_control_requests()[0]
    assert (row.user_id, row.verb, row.status) == (73, "status", "queued")
    assert "Queued status" in update.effective_message.reply_text.call_args[0][0]


async def test_destructive_verb_waits_for_confirm_then_queues(store, monkeypatch):
    monkeypatch.setattr(jarvis_control, "control_enabled", lambda: True)
    _allow(monkeypatch, {73})
    update = _message("/jarvis cancel job-1", 73)
    await jarvis_control.handle_jarvis(update, MagicMock())
    row = store.latest_control_requests()[0]
    assert row.status == "pending"
    markup = update.effective_message.reply_text.call_args[1]["reply_markup"]
    callbacks = _buttons(markup)
    assert callbacks == [f"jv:confirm:{row.id}", f"jv:abort:{row.id}"]
    assert all(len(data.encode()) <= 64 for data in callbacks)

    decided = store.decide_control(row.id, "confirm", 73, {73})
    assert decided is not None and decided.status == "queued"


async def test_abort_refuses_a_pending_request(store, monkeypatch):
    monkeypatch.setattr(jarvis_control, "control_enabled", lambda: True)
    _allow(monkeypatch, {73})
    update = _message("/jarvis cancel job-1", 73)
    await jarvis_control.handle_jarvis(update, MagicMock())
    row = store.latest_control_requests()[0]
    decided = store.decide_control(row.id, "abort", 73, {73})
    assert decided is not None and decided.status == "refused"
    assert store.claim_control_requests() == []


async def test_confirm_callback_moves_the_row_to_queued(store, monkeypatch):
    monkeypatch.setattr(jarvis_control, "control_enabled", lambda: True)
    _allow(monkeypatch, {73})
    request_id = store.add_control_request(73, "merge", "job-1", status="pending")
    update = _callback(f"jv:confirm:{request_id}", 73)
    await jarvis_control.handle_callback(update, MagicMock())
    assert store.control_request(request_id).status == "queued"
    update.callback_query.edit_message_text.assert_called_once()


async def test_ask_callback_on_destructive_notice_swaps_in_confirm_buttons(store, monkeypatch):
    monkeypatch.setattr(jarvis_control, "control_enabled", lambda: True)
    _allow(monkeypatch, {73})
    request_id = store.add_control_request(0, "merge", "job-1", status="pending")
    update = _callback(f"jv:ask:{request_id}", 73)
    await jarvis_control.handle_callback(update, MagicMock())
    assert store.control_request(request_id).status == "pending"
    markup = update.callback_query.edit_message_reply_markup.call_args[1]["reply_markup"]
    assert _buttons(markup) == [f"jv:confirm:{request_id}", f"jv:abort:{request_id}"]


async def test_closed_or_expired_callback_is_rejected(store, monkeypatch):
    monkeypatch.setattr(jarvis_control, "control_enabled", lambda: True)
    _allow(monkeypatch, {73})
    request_id = store.add_control_request(73, "cancel", "job-1", status="pending")
    store.decide_control(request_id, "abort", 73, {73})
    update = _callback(f"jv:confirm:{request_id}", 73)
    await jarvis_control.handle_callback(update, MagicMock())
    assert "closed" in update.callback_query.answer.call_args[0][0]
    assert store.control_request(request_id).status == "refused"


def test_expired_queued_requests_never_run(store, tasks_dir, monkeypatch):
    executed = []
    monkeypatch.setitem(control._VERBS, "status", lambda ctx, args: executed.append(args))
    request_id = store.add_control_request(73, "status", "")
    with __import__("sqlite3").connect(store.path) as db:
        db.execute(
            "UPDATE control_requests SET created_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
            (request_id,),
        )
    assert control.process_control_requests(store, tasks_dir, ROOT) is False
    assert executed == []
    assert store.control_request(request_id).status == "expired"


def test_expired_pending_requests_cannot_be_confirmed(store):
    request_id = store.add_control_request(73, "cancel", "job-1", status="pending")
    with __import__("sqlite3").connect(store.path) as db:
        db.execute(
            "UPDATE control_requests SET created_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
            (request_id,),
        )
    assert store.decide_control(request_id, "confirm", 73, {73}) is None
    assert store.control_request(request_id).status == "expired"


# ── Runner executor ──────────────────────────────────────────────────────────


def test_runner_executes_via_shared_helpers_and_writes_result_and_notice(
    store, tasks_dir, monkeypatch
):
    calls = []
    monkeypatch.setitem(
        control._VERBS,
        "status",
        lambda ctx, args: calls.append((str(ctx.root), args)) or "fake status",
    )
    store.add_control_request(73, "status", "extra")
    paused = control.process_control_requests(store, tasks_dir, ROOT)
    assert paused is False
    assert calls == [(str(tasks_dir), "extra")]
    row = store.latest_control_requests()[0]
    assert row.status == "done" and row.result == "fake status"
    notices = [n for n in store.outbox() if n.kind == "control"]
    assert len(notices) == 1
    assert notices[0].message == "Jarvis status extra\nfake status"


def test_runner_marks_unknown_verb_refused(store, tasks_dir):
    store.add_control_request(73, "bogus", "x")
    control.process_control_requests(store, tasks_dir, ROOT)
    row = store.latest_control_requests()[0]
    assert row.status == "refused"
    assert row.result.startswith("refused: unknown verb")


def test_runner_turns_a_helper_fault_into_a_failed_result(store, tasks_dir, monkeypatch):
    monkeypatch.setitem(control._VERBS, "status", lambda ctx, args: 1 / 0)
    store.add_control_request(73, "status", "")
    control.process_control_requests(store, tasks_dir, ROOT)
    row = store.latest_control_requests()[0]
    assert row.status == "done"
    assert row.result.startswith("failed: ZeroDivisionError")


def test_pause_and_resume_round_trip(store, tasks_dir):
    store.add_control_request(73, "pause", "")
    assert control.process_control_requests(store, tasks_dir, ROOT) is True
    store.add_control_request(73, "resume", "")
    assert control.process_control_requests(store, tasks_dir, ROOT) is False


def test_a_control_poll_fault_does_not_kill_the_runner(tmp_path, tasks_dir, monkeypatch):
    db = tmp_path / "arm" / "poll.sqlite3"
    monkeypatch.setattr(control, "default_arm_telegram_path", lambda: db)
    monkeypatch.setattr(
        control,
        "process_control_requests",
        lambda *a, **k: (_ for _ in ()).throw(OSError("locked")),
    )
    poll = control.build_control_poller(
        tasks_dir, ROOT, None, {"telegram_control": {"enabled": True}}
    )
    assert poll is not None
    assert poll() is False


def test_status_reports_the_queue_ledger(store, tasks_dir):
    from portal.modules.orchestration.queue import QueueLedger

    with QueueLedger(tasks_dir) as ledger:
        ledger._insert("job-1", "job", "{}", tasks_dir)
        ledger.db.commit()
    store.add_control_request(73, "status", "")
    control.process_control_requests(store, tasks_dir, ROOT)
    assert store.latest_control_requests()[0].result == "job-1 queued"


def test_queue_status_lists_the_last_ten_control_requests(store, tasks_dir):
    from typer.testing import CliRunner

    from portal.modules.orchestration.cli import orchestration_app

    for i in range(12):
        store.add_control_request(73, "status", f"job-{i}")
    store.add_control_request(73, "bogus", "", status="refused", result="unknown verb")
    result = CliRunner().invoke(orchestration_app, ["queue-status", "--tasks-dir", str(tasks_dir)])
    assert result.exit_code == 0, result.output
    assert "Last control requests:" in result.output
    lines = result.output.split("Last control requests:\n", 1)[1].strip().splitlines()
    assert len(lines) == 10
    assert "refused" in result.output


# ── Notice buttons ───────────────────────────────────────────────────────────


def test_held_escalation_notice_creates_merge_keep_diff_buttons(store):
    sink = TelegramNoticeSink(store.path)
    sink.escalation("job-1", "held", {"lane": "esc-job-1-1", "attempt": 1})
    pending = store.pending_control_requests("job-1")
    assert [row.verb for row in pending] == ["merge", "keep", "diff"]
    markup = jarvis_control.notice_keyboard(store, "job-1")
    labels = [button.text for row in markup.inline_keyboard for button in row]
    callbacks = _buttons(markup)
    assert labels == ["Merge", "Keep", "Diff"]
    assert callbacks[0].startswith("jv:ask:")
    assert callbacks[1].startswith("jv:confirm:")


def test_blocked_job_notice_creates_requeue_escalate_cancel_buttons(store):
    sink = TelegramNoticeSink(store.path)
    sink.job_finished("job-1", "BLOCKED", {"reason": "step exited 2"})
    assert [row.verb for row in store.pending_control_requests("job-1")] == [
        "requeue",
        "escalate",
        "cancel",
    ]


def test_quota_notice_creates_a_resume_button(store):
    sink = TelegramNoticeSink(store.path)
    sink.runner_notice("quota", "queue-runner", {"detail": "cap"})
    assert [row.verb for row in store.pending_control_requests("queue-runner")] == ["resume"]


async def test_outbox_attaches_the_control_keyboard_to_a_notice(store, monkeypatch):
    class FakeBot:
        def __init__(self):
            self.messages = []

        async def send_message(self, **kwargs):
            self.messages.append(kwargs)

    sink = TelegramNoticeSink(store.path)
    sink.escalation("job-1", "held", {"lane": "esc-job-1-1"})
    botfake = FakeBot()
    sent = await send_outbox_once(
        store,
        botfake,
        {73},
        lambda request_id: None,
        control_keyboard=lambda task_id: jarvis_control.notice_keyboard(store, task_id),
    )
    assert sent == 1
    markup = botfake.messages[0]["reply_markup"]
    assert [b.text for row in markup.inline_keyboard for b in row] == ["Merge", "Keep", "Diff"]


def test_notice_buttons_pass_user_rows_by_are_not_shown(store):
    store.add_control_request(73, "cancel", "job-1", status="pending")
    assert jarvis_control.notice_keyboard(store, "job-1") is None


def test_callback_data_fits_the_64_byte_limit(store):
    for verb in sorted(control.VERB_NAMES | {"merge", "keep", "diff"}):
        request_id = store.add_control_request(0, verb, "job-1", status="pending")
        row = store.control_request(request_id)
        data = jarvis_control._callback_for(row)
        assert len(data.encode()) <= 64
        assert data.startswith("jv:")
        assert data.split(":")[2] == request_id


# ── Held escalations: list, merge refusal, keep ──────────────────────────────


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _held_repo(tmp_path):
    repo = tmp_path / "main"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")
    role = "esc-job-1-1"
    lane = tmp_path / f"main-{role}"
    _git(repo, "worktree", "add", "-b", f"lane/{role}", str(lane))
    (lane / "portal").mkdir()
    (lane / "portal" / "guarded.py").write_text("x = 1\n", encoding="utf-8")
    _git(lane, "add", "-A")
    _git(lane, "commit", "-m", "touch portal")
    return repo, lane, role


def test_merge_refuses_a_held_portal_path_with_the_reason(tasks_dir, tmp_path):
    repo, _lane, role = _held_repo(tmp_path)
    EscalationLedger(tasks_dir).add("job-1", 1, role, "held", {"branch": f"lane/{role}"})
    esc = Escalator(tasks_dir, repo_root=repo, main_root=repo)
    result = esc.merge_held("job-1")
    assert result == "refused: portal/guarded.py is under portal/"


def test_merge_refuses_when_no_held_lane_exists(tasks_dir, tmp_path):
    esc = Escalator(tasks_dir, repo_root=tmp_path, main_root=tmp_path)
    assert esc.merge_held("job-1") == "refused: no held lane worktree for job-1"


def test_keep_held_records_the_decision_and_clears_the_held_list(tasks_dir, tmp_path):
    repo, _lane, role = _held_repo(tmp_path)
    EscalationLedger(tasks_dir).add("job-1", 1, role, "held", {"branch": f"lane/{role}"})
    esc = Escalator(tasks_dir, repo_root=repo, main_root=repo)
    assert "kept job-1 held" in esc.keep_held("job-1")
    assert held_escalations(tasks_dir) == []
    events = EscalationLedger(tasks_dir).events("job-1")
    assert events[-1]["event"] == "kept"


def test_held_lists_a_job_whose_latest_decision_is_held(tasks_dir, tmp_path):
    repo, _lane, role = _held_repo(tmp_path)
    ledger = EscalationLedger(tasks_dir)
    ledger.add("job-1", 1, role, "held", {"branch": f"lane/{role}"})
    held = held_escalations(tasks_dir)
    assert len(held) == 1
    assert held[0]["job_id"] == "job-1"
    assert held[0]["lane_id"] == role


def test_diff_reports_a_held_lane_diffstat(tasks_dir, tmp_path):
    repo, _lane, role = _held_repo(tmp_path)
    EscalationLedger(tasks_dir).add("job-1", 1, role, "held", {"branch": f"lane/{role}"})
    esc = Escalator(tasks_dir, repo_root=repo, main_root=repo)
    text = esc.held_diffstat("job-1")
    assert "portal/guarded.py" in text
    assert "Files:" in text


# ── Canary summary ───────────────────────────────────────────────────────────


def test_canary_reports_one_line_setup_model_counts(store, tasks_dir):
    job_dir = tasks_dir / "job-1"
    job_dir.mkdir(parents=True)
    receipt = {
        "status": "BLOCKED",
        "steps": [
            {"id": "long", "argv": ["scripts/long.sh"]},
            {
                "id": "gate",
                "argv": ["scripts/long.sh", "--canary"],
                "stdout_tail": (
                    "row table output\nCANARY realuse_s8_canary: PASS (2 setup row(s) of 5)\n"
                ),
            },
        ],
    }
    (job_dir / "receipt.json").write_text(__import__("json").dumps(receipt), encoding="utf-8")
    assert control.canary_summary(tasks_dir, "job-1") == (
        "canary job-1 [realuse_s8_canary]: PASS — SETUP 2/5, MODEL 3/5"
    )


def test_canary_reports_missing_pieces(store, tasks_dir):
    job_dir = tasks_dir / "job-1"
    job_dir.mkdir(parents=True)
    (job_dir / "receipt.json").write_text('{"steps": []}', encoding="utf-8")
    assert (
        control.canary_summary(tasks_dir, "job-1") == "canary job-1: no canary step in its receipt"
    )
    assert control.canary_summary(tasks_dir, "missing") == "no receipt for missing"


# ── Bot wiring ───────────────────────────────────────────────────────────────


def test_build_app_registers_jarvis_routing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:fake-test-token")
    from telegram.ext import CallbackQueryHandler, CommandHandler

    monkeypatch.setattr(bot, "_orchestration_enabled", lambda: True)
    app = bot.build_app()
    handlers = [handler for group in app.handlers.values() for handler in group]
    assert any(
        isinstance(handler, CommandHandler) and "jarvis" in handler.commands for handler in handlers
    )
    assert any(
        isinstance(handler, CallbackQueryHandler) and handler.pattern.pattern == "^jv:"
        for handler in handlers
    )


def test_disabled_orchestration_registers_no_jv_callbacks(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:fake-test-token")
    from telegram.ext import CallbackQueryHandler

    monkeypatch.setattr(bot, "_orchestration_enabled", lambda: False)
    app = bot.build_app()
    handlers = [handler for group in app.handlers.values() for handler in group]
    assert not any(isinstance(handler, CallbackQueryHandler) for handler in handlers)
