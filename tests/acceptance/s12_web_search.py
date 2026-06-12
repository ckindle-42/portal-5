"""S12: Web search tests."""

import time

from tests.acceptance._common import (
    SEARXNG_URL,
    _get_acc_client,
    record,
)


async def run() -> None:
    """S12: Web search tests."""
    print("\n━━━ S12. WEB SEARCH ━━━")
    sec = "S12"

    # S12-01: SearXNG direct query
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(
            f"{SEARXNG_URL}/search", params={"q": "test query", "format": "json"}, timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            record(sec, "S12-01", "SearXNG search", "PASS", f"{len(results)} results", t0=t0)
        else:
            record(sec, "S12-01", "SearXNG search", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S12-01", "SearXNG search", "WARN", str(e)[:100], t0=t0)
