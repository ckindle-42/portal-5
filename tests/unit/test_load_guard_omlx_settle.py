"""The oMLX async-unload settle window before a quiet Ollama HTTP 507.

oMLX 0.8.1's POST /admin/api/models/{id}/unload answers HTTP 202 and reclaims
Metal GPU memory over the next seconds while /v1/models/status's counter still
reads flat (release_1_0_final QAT, 2026-11-22: ``auto-audio`` and
``auto-reasoning::math`` both refused within ~1 GiB right after an oMLX turn,
"with nothing in flight to wait for"). A cold Ollama load that does not fit the
stale headroom now polls the counter for a bounded window before refusing.
"""

from __future__ import annotations

import httpx
import pytest

from portal.platform.inference import load_guard as lg

GIB = 1024**3

OLLAMA_URL = "http://ollama:11434"

OMLX_URL = "http://omlx:8085"


class SettlingOmlx:
    """Ollama answers cold; oMLX's counter still holds an unload issued before this
    admission (nothing loaded left to evict) and drops it only after
    ``release_after`` status reads — never, when ``never``."""

    def __init__(
        self,
        *,
        ceiling: float,
        stale_used: float,
        release_after: int,
        never: bool = False,
    ) -> None:
        self.ceiling = ceiling
        self.stale_used = stale_used
        self.release_after = release_after
        self.never = never
        self.status_reads = 0
        self.unload_calls: list[str] = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/v1/models/status":
            self.status_reads += 1
            settled = not self.never and self.status_reads > self.release_after
            return httpx.Response(
                200,
                json={
                    "final_ceiling": self.ceiling,
                    "current_model_memory": 0.0 if settled else self.stale_used,
                    "models": [{"id": "evicted-seat", "loaded": False, "estimated_size": 0}],
                },
            )
        if path == "/api/status":
            return httpx.Response(200, json={"active_requests": 0, "waiting_requests": 0})
        if path == "/admin/api/login":
            return httpx.Response(200, json={"success": True})
        if path == "/admin/api/models":
            return httpx.Response(200, json=[])
        if path.endswith("/unload"):
            self.unload_calls.append(path)
            return httpx.Response(202, json={})
        if path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "gguf", "size": 8 * GIB}]})
        if path == "/api/show":
            return httpx.Response(200, json={})
        return httpx.Response(404)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture(autouse=True)
def _fast(monkeypatch, tmp_path):
    monkeypatch.setattr(lg, "_POLL_S", 0.0)
    monkeypatch.setattr(lg, "_PROCESS_LOCK_DIR", tmp_path / "guard-locks")
    # oMLX's own prefill-safe share and reclaim tier, pinned like the main suite.
    monkeypatch.setattr(lg, "_OMLX_PREFILL_ZONE", 0.8)
    monkeypatch.setattr(lg, "_OMLX_RECLAIM_RATIO", 0.25)
    # A real but tiny settle window: the step advances the clock, the fake decides
    # on which read the async release lands.
    monkeypatch.setattr(lg, "_OMLX_SETTLE_S", 0.2)
    monkeypatch.setattr(lg, "_OMLX_SETTLE_STEP_S", 0.02)
    monkeypatch.delenv("LOAD_GUARD", raising=False)
    monkeypatch.delenv("OMLX_PREFILL_SAFE_ZONE_RATIO", raising=False)
    monkeypatch.delenv("OMLX_OTHER_APP_RECLAIM_RATIO", raising=False)
    monkeypatch.delenv("OMLX_MEMORY_GUARD_TIER", raising=False)
    monkeypatch.delenv("LOAD_GUARD_OMLX_SETTLE_S", raising=False)
    monkeypatch.delenv("LOAD_GUARD_OMLX_SETTLE_STEP_S", raising=False)
    lg.set_load_wait(None)
    monkeypatch.setattr(lg, "_WAIT_S", 0.0)
    from portal.platform.inference.router.parallel_seat import YIELD

    YIELD._pins = 0
    YIELD._held.clear()
    YIELD._clear.set()


def guard(e: SettlingOmlx) -> lg.LoadGuard:
    return lg.LoadGuard(
        omlx_url=lambda: OMLX_URL,
        pinned=lambda: "router",
        client=lambda: httpx.AsyncClient(transport=e.transport()),
        ollama_url=lambda: OLLAMA_URL,
    )


async def test_a_cold_load_admits_once_the_stale_omlx_counter_settles():
    """The release_1_0_final race: the 202 unload's bytes are still on the counter,
    headroom is short by less than the gap, and the load fits once memory lands."""
    # need 10.0 GiB (8 GiB tag x1.25); stale headroom leaves 8.5, settled 10.0.
    e = SettlingOmlx(ceiling=12 * GIB, stale_used=1.5 * GIB, release_after=4)
    g = guard(e)
    lg.set_load_wait("30")

    release = await g.admit(OLLAMA_URL, "gguf")

    assert release is not None
    assert e.unload_calls == []  # nothing was evictable; the settle window admitted it
    assert e.status_reads >= 5  # it polled the counter, not refused at the flat read
    release()
    assert not g._lock.locked()


async def test_a_genuinely_insufficient_load_still_refuses_cleanly_after_settle():
    """A counter that never drops expires the window and refuses with the quiet 507."""
    e = SettlingOmlx(ceiling=12 * GIB, stale_used=1.5 * GIB, release_after=4, never=True)
    g = guard(e)
    lg.set_load_wait("30")

    with pytest.raises(lg.LoadRefusedError) as err:
        await g.admit(OLLAMA_URL, "gguf")

    assert err.value.reason == "quiet"
    assert "with nothing in flight to wait for" in str(err.value)
    assert "projected memory 10.0 GiB" in str(err.value)
    assert e.status_reads >= 4  # the window polled before the refusal, bounded by it
    assert not g._lock.locked()
