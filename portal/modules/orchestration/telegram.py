"""Orchestration notice sink backed by the existing Telegram channel process."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from portal_channels.telegram.arm_bridge import ArmTelegramStore, default_arm_telegram_path


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
