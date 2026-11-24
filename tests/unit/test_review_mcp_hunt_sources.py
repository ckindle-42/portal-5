"""Regression coverage for listing Splunk indexes through hunt_sources."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from portal.modules.security.core.hunt import product_jobs
from portal.modules.security.tools import review_mcp


def test_hunt_sources_pages_generator_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {"index": f"index-{letter}", "count": count}
        for letter, count in zip("abcd", (10, 20, 30, 40), strict=True)
    ]

    class Search:
        def iter_post(self, *_args: Any) -> Iterator[dict[str, Any]]:
            return (row for row in rows)

    monkeypatch.setattr(review_mcp, "_hunt_search", Search)
    monkeypatch.setattr(review_mcp, "_hunt_result_byte_limit", lambda: 10_000)

    page = review_mcp.hunt_sources(n=2, offset=1)

    assert "error" not in page
    assert page["indexes"] == [
        {"index": "index-b", "events": 20},
        {"index": "index-c", "events": 30},
    ]
    assert page["total_indexes"] == 4
    assert page["indexes_omitted"] == 1
    assert page["next_offset"] == 3


def test_indexes_view_accepts_generator_rows() -> None:
    rows = (
        {"index": f"index-{letter}", "count": count}
        for letter, count in zip("ab", (10, 20), strict=True)
    )

    page = product_jobs.indexes_view(rows, n=1)

    assert page["indexes"] == [{"index": "index-a", "events": 10}]
    assert page["total_indexes"] == 2
    assert page["indexes_omitted"] == 1
    assert page["next_offset"] == 1
