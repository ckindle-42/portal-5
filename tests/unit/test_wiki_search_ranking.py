"""Wiki search top-hit regression gate.

TASK_WIKI_ZERO_DEBT_V1 Phase 7 — kind-weighted search ranking. The flat
keyword score treated a design unit and a test-section unit identically on
equal keyword evidence, so "workspace routing" surfaced `unit-acceptance-s03_routing`
(a UAT section) ahead of `unit-router-routing` (the routing design). Search now
ranks by keyword score plus a small kind tier and verification boost, and the
top hit for every baseline query is pinned in the fixture so search quality is
a gate rather than a spot check.
"""

from __future__ import annotations

import json
from pathlib import Path

from portal_wiki.mcp import wiki_search

REPO = Path(__file__).resolve().parent.parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "wiki_search_baseline.json"


def test_all_baseline_queries_return_expected_top_hit():
    baseline = json.loads(FIXTURE.read_text())
    assert baseline["queries"], "fixture must not be empty"
    for entry in baseline["queries"]:
        query = entry["query"]
        expected = entry["top_hit"]
        result = wiki_search(query, top_k=1)
        assert result["results"], f"query {query!r} returned no results"
        actual = result["results"][0]["unit_id"]
        assert actual == expected, (
            f"query {query!r}: expected top hit {expected!r}, got {actual!r} "
            f"(score {result['results'][0]['score']})"
        )


def test_workspace_routing_demotes_test_section_unit():
    """The Phase 7 defect: a test-section unit must not outrank the design unit."""
    result = wiki_search("workspace routing", top_k=3)
    ids = [r["unit_id"] for r in result["results"]]
    assert ids[0] == "unit-router-routing", ids
    assert "unit-acceptance-s03_routing" not in ids[:2], ids


def test_fixture_is_fresh_against_store():
    """The pinned top hits must match what search currently returns."""
    baseline = json.loads(FIXTURE.read_text())
    for entry in baseline["queries"]:
        result = wiki_search(entry["query"], top_k=1)
        actual = result["results"][0]["unit_id"] if result["results"] else None
        assert actual == entry["top_hit"], (
            f"fixture stale for {entry['query']!r}: expected {entry['top_hit']!r}, got {actual!r}"
        )
