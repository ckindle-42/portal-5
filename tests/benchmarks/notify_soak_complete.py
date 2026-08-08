"""Send a completion summary for bench_omlx_soak.py to all configured
notification channels (Slack/Telegram/Pushover), reusing the same
NotificationDispatcher pattern as tests/uat/notify.py.

Usage:
  python3 tests/benchmarks/notify_soak_complete.py <results.json>
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


async def main(result_path: Path) -> None:
    from portal.platform.inference.notifications.channels.pushover import PushoverChannel
    from portal.platform.inference.notifications.channels.slack import SlackChannel
    from portal.platform.inference.notifications.channels.telegram import TelegramChannel
    from portal.platform.inference.notifications.dispatcher import NotificationDispatcher
    from portal.platform.inference.notifications.events import AlertEvent, EventType

    d = json.loads(result_path.read_text())

    outages = d.get("outages", [])
    peak_gb = round(d.get("peak_memory_bytes", 0) / 1e9, 1)
    ceiling_gb = round((d.get("ceiling_bytes") or 0) / 1e9, 1)
    per_model = d.get("per_model", {})
    fail_lines = [f"{name}: {v['fail']} fail" for name, v in per_model.items() if v.get("fail")]

    message_lines = [
        f"oMLX 10-model fleet soak complete ({d.get('duration_s', 0) // 3600}h @ concurrency={d.get('concurrency')})",
        f"Requests: {d.get('total_requests')} total, {d.get('ok')} ok, {d.get('failures')} failed",
        f"Peak engine memory: {peak_gb}GB / {ceiling_gb}GB ceiling",
        f"Outages: {len(outages)}"
        + (
            f" (longest {max((o.get('duration_s') or 0) for o in outages):.0f}s)" if outages else ""
        ),
    ]
    if fail_lines:
        message_lines.append("Failures by model: " + ", ".join(fail_lines))
    message = "\n".join(message_lines)

    dispatcher = NotificationDispatcher()
    for ch in [SlackChannel, TelegramChannel, PushoverChannel]:
        dispatcher.add_channel(ch())

    event = AlertEvent(
        type=EventType.TEST_SUMMARY,
        message=message,
        workspace="omlx-fleet-soak",
        metadata={
            "total_requests": d.get("total_requests"),
            "failures": d.get("failures"),
            "outage_count": len(outages),
            "peak_memory_gb": peak_gb,
        },
    )
    results = await dispatcher.dispatch(event)
    print("dispatch results:", results)


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
