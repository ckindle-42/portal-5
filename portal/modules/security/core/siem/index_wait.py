"""Block until HEC-shipped events are searchable, so blue SPL doesn't race ingestion."""

from __future__ import annotations

import json
import os
import time

import httpx


def wait_indexed(
    *,
    host: str,
    since_epoch: float,
    expect_min: int = 1,
    timeout_s: int = 30,
    index: str | None = None,
    episode_id: str | None = None,
) -> bool:
    """Poll a count search until >= expect_min events for this host are searchable, or timeout."""
    url = os.environ.get("LAB_SPLUNK_URL", "https://portal5-lab-splunk:8089")
    user = os.environ.get("LAB_SPLUNK_USER", "admin")
    pw = os.environ.get("LAB_SPLUNK_PASSWORD", "")
    idx = index or os.environ.get("LAB_SPLUNK_INDEX", "portal5_lab")
    episode_clause = f' episode_id="{episode_id}"' if episode_id else ""
    spl = (
        f'search index={idx} host="{host}"{episode_clause} '
        f"earliest={int(since_epoch)} | stats count"
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            r = httpx.post(
                f"{url.rstrip('/')}/services/search/jobs/export",
                auth=(user, pw),
                verify=False,
                timeout=15.0,
                data={
                    "search": spl,
                    "exec_mode": "oneshot",
                    "output_mode": "json",
                },
            )
            for ln in r.text.splitlines():
                if '"count"' in ln:
                    c = int(json.loads(ln).get("result", {}).get("count", "0"))
                    if c >= expect_min:
                        return True
        except Exception:
            pass
        time.sleep(2)
    return False  # caller proceeds; blue scores synthetic-fallback -> indeterminate (honest)
