"""Orchestration notice sink backed by the existing Telegram channel process."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from portal_channels.telegram.arm_bridge import ArmTelegramStore, default_arm_telegram_path

_CANARY_SETUP = re.compile(r"^CANARY\s+\S+:\s+SETUP\b")
_CANARY_SETUP_NOTE = (
    "Canary verdict is SETUP: the harness failed before rows ran — a setup problem, "
    "not a model verdict. Check the canary campaign's SETUP rows; the job stopped "
    "before the long step."
)
_RUNNER_EVENT_TEXT = {
    "memory_trip": "Memory safety trip on a job step",
    "orphan_adopted": "Runner restart: adopted an orphaned job step",
    "runner_started": "Queue runner started",
}
_HELD_BUTTONS = ("merge", "keep", "diff")
_BLOCKED_BUTTONS = ("requeue", "escalate", "cancel")


class TelegramNoticeSink:
    """Queue operator gates and block notices for portal_channels.telegram.bot."""

    def __init__(
        self,
        path: Path | None = None,
        poll_interval: float = 2.0,
        approval_ttl_seconds: int | None = None,
    ) -> None:
        self.store = ArmTelegramStore(path or default_arm_telegram_path(), approval_ttl_seconds)
        self.poll_interval = poll_interval

    def approval(
        self,
        task_id: str,
        bite_id: str,
        bite_definition: dict[str, Any],
        reason: str,
        run_id: str,
    ) -> bool | None:
        decision = self.store.request_approval(task_id, bite_id, bite_definition, reason, run_id)
        while decision is None:
            time.sleep(self.poll_interval)
            decision = self.store.request_approval(
                task_id, bite_id, bite_definition, reason, run_id
            )
        return decision

    def blocked(self, task_id: str, bite_id: str, failure: dict[str, Any]) -> None:
        self.store.blocked(task_id, bite_id, failure)

    def job_finished(self, job_id: str, status: str, detail: dict[str, Any]) -> None:
        reason = _one_line(detail.get("reason", ""))
        lines = [
            f"Orchestration job {status}.",
            f"Job: {_one_line(job_id)}",
            f"Purpose: {_one_line(detail.get('purpose', ''))}",
            f"Steps: {_one_line(detail.get('steps', '?'))}",
        ]
        if detail.get("step_id"):
            lines.append(
                f"Step: {_one_line(detail['step_id'])} ({_one_line(detail.get('step_state', ''))})"
            )
        last_output = str(detail.get("last_output") or "").strip()
        if last_output:
            lines.append(f"Last output: {_one_line(last_output)}")
            if _CANARY_SETUP.match(last_output):
                lines.append(_CANARY_SETUP_NOTE)
        if detail.get("report_path"):
            lines.append(f"Report: {_one_line(detail['report_path'])}")
        if detail.get("next_queued"):
            lines.append(f"Next queued: {_one_line(detail['next_queued'])}")
        lines.append(f"Duration: {float(detail.get('duration_seconds') or 0):.0f}s")
        if reason:
            lines.append(f"Reason: {reason}")
        self.store.notify(job_id, "job", "\n".join(lines))
        if str(status).upper() == "BLOCKED":
            self._queue_buttons(job_id, _BLOCKED_BUTTONS)

    def runner_notice(self, event: str, job_id: str, detail: dict[str, Any]) -> None:
        head = _RUNNER_EVENT_TEXT.get(event, f"Runner event {event}")
        lines = [head]
        if job_id and job_id != "queue-runner":
            lines.append(f"Job: {_one_line(job_id)}")
        lines.extend(f"{key}: {_one_line(value)}" for key, value in sorted(detail.items()))
        task_id = job_id or "queue-runner"
        self.store.notify(task_id, event, "\n".join(lines))
        if event == "quota":
            self._queue_buttons(task_id, ("resume",))

    def digest(self, text: str) -> None:
        self.store.notify("queue-digest", "digest", text)

    def escalation(self, job_id: str, event: str, detail: dict[str, Any]) -> None:
        lines = [f"Escalation {event}.", f"Job: {_one_line(job_id)}"]
        for key in (
            "lane",
            "tier",
            "attempt",
            "branch",
            "reason",
            "summary",
            "detail",
            "trigger",
            "retry_until",
        ):
            if detail.get(key):
                lines.append(f"{key}: {_one_line(detail[key])}")
        if detail.get("resume_command"):
            lines.append(f"Resume command:\n{detail['resume_command']}")
        self.store.notify(job_id, "escalation", "\n".join(lines))
        if event == "held":
            self._queue_buttons(job_id, _HELD_BUTTONS)

    def _queue_buttons(self, job_id: str, verbs: tuple[str, ...]) -> None:
        """Pending control rows that become this notice's action buttons."""
        for verb in verbs:
            self.store.add_control_request(user_id=0, verb=verb, args=job_id, status="pending")


def _one_line(value: object) -> str:
    return " ".join(str(value).split())[:300]
