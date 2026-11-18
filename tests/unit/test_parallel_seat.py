"""Parallel-seat routing: idle Ollama twin release, and the chat yield gate.

No network. Engines are ``httpx.MockTransport`` and in-process yield state.
"""

from __future__ import annotations

import asyncio

from portal.platform.inference.router.concurrency import RequestSlot
from portal.platform.inference.router.parallel_seat import (
    YIELD,
)


def test_pins_hold_until_every_admission_releases() -> None:
    YIELD.hold("hunt-reasoning")
    YIELD.pin()
    YIELD.pin()
    YIELD.release()
    assert YIELD.holding("hunt-reasoning")
    YIELD.release()
    assert not YIELD.holding("hunt-reasoning")


async def test_a_yield_holds_new_seat_requests_until_release() -> None:
    YIELD.hold("hunt-reasoning")
    slot = RequestSlot()
    task = asyncio.create_task(slot.acquire_workspace("hunt-reasoning"))
    for _ in range(20):
        await asyncio.sleep(0)
    assert not task.done()
    YIELD.release()
    await asyncio.wait_for(task, 1)
    slot.release()


async def test_a_yield_does_not_hold_a_different_workspace() -> None:
    YIELD.hold("hunt-reasoning")
    slot = RequestSlot()
    await asyncio.wait_for(slot.acquire_workspace("auto-daily"), 1)
    slot.release()
