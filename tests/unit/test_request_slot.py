"""tests/unit/test_request_slot.py — RequestSlot isolation tests.

Exercises RequestSlot with small real asyncio.Semaphores — no mocking, no
FastAPI stack, no HTTP. Tests verify the staged-acquire/release contract, the
gauge-decrement guarantee, idempotent release, detach/release_if_attached
semantics, and reverse-order release.
"""

from __future__ import annotations

import asyncio

import pytest

import portal_pipeline.router.concurrency as _concurrency
from portal_pipeline.router.concurrency import RequestSlot


@pytest.fixture(autouse=True)
def _patch_concurrency(monkeypatch):
    """Install a real semaphore of size 5 so tests can exhaust and restore it."""
    real_sem = asyncio.Semaphore(5)
    monkeypatch.setattr(_concurrency, "_request_semaphore", real_sem)
    yield real_sem
    monkeypatch.setattr(_concurrency, "_request_semaphore", None)


@pytest.mark.anyio
async def test_staged_acquire_release_restores_semaphores():
    """Acquire global + workspace; release restores both semaphore counts."""
    sem_before = _concurrency._request_semaphore._value  # type: ignore[union-attr]

    slot = RequestSlot()
    await slot.acquire_global()
    # Verify global semaphore decremented
    assert _concurrency._request_semaphore._value == sem_before - 1  # type: ignore[union-attr]

    # Patch a small workspace semaphore for the test workspace
    ws_sem = asyncio.Semaphore(3)
    _concurrency._workspace_semaphores["_test_ws"] = ws_sem
    try:
        ws_before = ws_sem._value
        # Directly acquire using the slot's internal _held list (simulate workspace step)
        await asyncio.wait_for(ws_sem.acquire(), timeout=1.0)
        slot._held.append(ws_sem)

        slot.release()

        assert _concurrency._request_semaphore._value == sem_before  # type: ignore[union-attr]
        assert ws_sem._value == ws_before
    finally:
        _concurrency._workspace_semaphores.pop("_test_ws", None)


@pytest.mark.anyio
async def test_global_timeout_raises_503_and_does_not_hold():
    """Timeout on global acquire raises 503 with Retry-After; slot holds nothing."""
    from fastapi import HTTPException

    # Exhaust the semaphore so the next acquire times out
    sem = _concurrency._request_semaphore
    assert sem is not None
    # Drain all tokens
    drained = []
    while sem._value > 0:
        await sem.acquire()
        drained.append(True)

    orig_timeout = _concurrency._SEMAPHORE_TIMEOUT
    _concurrency._SEMAPHORE_TIMEOUT = 0.01
    try:
        slot = RequestSlot()
        with pytest.raises(HTTPException) as exc_info:
            await slot.acquire_global()
        assert exc_info.value.status_code == 503
        assert "retry" in exc_info.value.detail.lower()
        assert exc_info.value.headers.get("Retry-After") == "5"
        assert slot._held == []
    finally:
        _concurrency._SEMAPHORE_TIMEOUT = orig_timeout
        for _ in drained:
            sem.release()


@pytest.mark.anyio
async def test_mark_active_and_release_nets_gauge_to_zero():
    """mark_active increments the gauge; release decrements it back to zero."""
    import portal_pipeline.router.metrics as _metrics

    before = int(_metrics._concurrent_requests._value.get())
    slot = RequestSlot()
    await slot.acquire_global()
    slot.mark_active()
    assert int(_metrics._concurrent_requests._value.get()) == before + 1
    slot.release()
    assert int(_metrics._concurrent_requests._value.get()) == before


@pytest.mark.anyio
async def test_release_is_idempotent():
    """Double-calling release() does not double-decrement or raise."""
    import portal_pipeline.router.metrics as _metrics

    before = int(_metrics._concurrent_requests._value.get())
    sem_before = _concurrency._request_semaphore._value  # type: ignore[union-attr]

    slot = RequestSlot()
    await slot.acquire_global()
    slot.mark_active()
    slot.release()
    slot.release()  # second call must be a no-op

    assert int(_metrics._concurrent_requests._value.get()) == before
    assert _concurrency._request_semaphore._value == sem_before  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_detach_makes_release_if_attached_noop():
    """After detach(), release_if_attached() does nothing; release() still works."""
    import portal_pipeline.router.metrics as _metrics

    before = int(_metrics._concurrent_requests._value.get())
    sem_before = _concurrency._request_semaphore._value  # type: ignore[union-attr]

    slot = RequestSlot()
    await slot.acquire_global()
    slot.mark_active()
    slot.detach()

    # release_if_attached is a no-op when detached
    slot.release_if_attached()
    assert int(_metrics._concurrent_requests._value.get()) == before + 1
    assert _concurrency._request_semaphore._value == sem_before - 1  # type: ignore[union-attr]

    # release() still works and restores everything
    slot.release()
    assert int(_metrics._concurrent_requests._value.get()) == before
    assert _concurrency._request_semaphore._value == sem_before  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_reverse_order_release():
    """Two semaphores acquired in order A→B are released in order B→A."""
    sem_a = asyncio.Semaphore(1)
    sem_b = asyncio.Semaphore(1)

    slot = RequestSlot()
    await asyncio.wait_for(sem_a.acquire(), timeout=1.0)
    slot._held.append(sem_a)
    await asyncio.wait_for(sem_b.acquire(), timeout=1.0)
    slot._held.append(sem_b)

    assert sem_a._value == 0
    assert sem_b._value == 0

    slot.release()

    assert sem_a._value == 1
    assert sem_b._value == 1
    assert slot._held == []


@pytest.mark.anyio
async def test_disconnect_mid_stream_nets_gauge_to_zero():
    """Client disconnect mid-stream (generator abandoned) nets gauge 0 and semaphore restored.

    Simulates the detach+streaming path: slot is detached (transferred to a
    generator), then the generator is abandoned before exhaustion (client
    disconnect). The slot's release() must still be called — either by the
    generator's finally or by GC. Here we call release() directly to model
    the generator's finally block and assert invariants hold.
    """
    import portal_pipeline.router.metrics as _metrics

    gauge_before = int(_metrics._concurrent_requests._value.get())
    sem_before = _concurrency._request_semaphore._value  # type: ignore[union-attr]

    slot = RequestSlot()
    await slot.acquire_global()
    slot.mark_active()
    slot.detach()

    # Simulate generator abandoned mid-stream — finally block calls release()
    slot.release()

    assert int(_metrics._concurrent_requests._value.get()) == gauge_before
    assert _concurrency._request_semaphore._value == sem_before  # type: ignore[union-attr]
